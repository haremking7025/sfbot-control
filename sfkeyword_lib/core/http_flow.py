"""Pure-HTTP engine: login + keyword submit + confirm — ผ่าน `requests` ล้วนๆ
(ไม่เปิด Chrome / ไม่ใช้ Selenium)

พิสูจน์แล้วจริงกับบัญชีและคีย์จริง (สิงหาคม 2026) — ดู FEASIBILITY_PURE_HTTP.md
เส้นทางทั้งหมด:

  GET Login.aspx -> POST (GG Passport / Game ID) -> 302 StartGames.aspx
  -> POST ImageButton1 -> 302 RedirectPage.aspx
  -> อ่าน REFRESH header (SSO ticket) -> GET LandingPlatform.aspx -> cookie "Members"
  -> GET /Keyword/ -> async postback (UpdatePanel) -> redirect script ไป Confirm.aspx
  -> ยืนยัน (btnConfirm) / เลือกแรงค์ใน GridView (txtChkItem + txtItemSRL) -> ยืนยัน

ข้อควรรู้:
- ปุ่มในหน้า Keyword/Confirm เป็น async postback (UpdatePanel) — POST ธรรมดาไม่ทำงาน
- delta response รูปแบบ: <len>|<type>|<id>|<data> (len = ความยาว data)
- __VIEWSTATE/__EVENTVALIDATION เปลี่ยนทุก postback — ต้อง re-parse จาก delta
- ล็อก 15 นาทีเกิดจากใส่รหัสผิดซ้ำในบัญชีเดียวกัน — MIN_LOGIN_INTERVAL_SEC คือ
  หน่วงจังหวะล็อกอินของไอดีเดียวกัน (ไอดีต่างกันล็อกอินพร้อมกันได้ตาม concurrency)
"""

import hashlib
import json
import logging
import os
import re
import threading
import time

import requests

from .constants import KEYWORD_URL, LOGIN_URL
from .exceptions import (
    KeywordPreviewOnly,
    LoginFailedError,
    LoginLockedError,
    SessionExpiredError,
)
from .paths import COOKIE_DIR, COOKIE_MAX_DAYS
from .security import decrypt_pwd, encrypt_pwd

_logger = logging.getLogger(__name__)

CONFIRM_URL = "http://member.sf.in.th/Keyword/Confirm.aspx"

# ---- rate limit: กันล็อก 15 นาที ----
# ⚠ ล็อก 15 นาทีเกิดจาก "ใส่รหัสผิดติดต่อกันหลายครั้งในบัญชีเดียวกัน" ไม่ใช่
# การล็อกอินเร็วข้ามไอดี — ดังนั้นหน่วงแบบ per-account (คีย์ตาม username) ไม่ใช่
# global: ไอดีต่างกันล็อกอินพร้อมกันได้เต็ม concurrency ที่ผู้ใช้ตั้ง (ค่าจริง
# "พร้อมกัน" บนแดชบอร์ด) ขณะที่บัญชีเดียวกันยังมีระยะห่างขั้นต่ำระหว่าง POST
# ล็อกอินแต่ละครั้ง (กันยิงซ้ำถี่ๆ ในไอดีเดียวจนโดนล็อก)
MIN_LOGIN_INTERVAL_SEC = 0.1
_login_lock = threading.Lock()
_last_login_by_user = {}
_LOGIN_SLOT_CLEAN_EVERY = 256
_login_slot_calls = [0]

_HIDDEN_RE = re.compile(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"')

LOCKED_HINTS = (
    "กรุณารอ 15 นาที",
    "รอ 15 นาที",
    "please wait 15 minute",
    "wait 15 min",
    "try again after 15 minute",
    "try again in 15 minute",
    "temporarily locked",
    "login locked",
    "too many login",
    "too many attempts",
    "ลองใหม่ภายหลัง",
    "ลองเข้าสู่ระบบใหม่",
    "โปรดลองอีกครั้งหลังจาก 15 นาที",
    "ลองอีกครั้งหลังจาก 15 นาที",
    "การเข้าถึงที่ไม่ถูกต้อง",
    "พฤติกรรมที่น่าสงสัยหรือถูกแฮ็ก",
    "incorrect access",
    "suspicious activity",
    "has been hacked",
)

KEYWORD_ERROR_PATTERNS = (
    "ถูกใช้งานแล้ว",
    "ถูกใช้ไปแล้ว",
    "ใช้ไปแล้ว",
    "คูปอง",
    "คียเวิร์ดนี้ไปแล้ว",
    "already",
    "used",
    "ซ้ำ",
    "duplicate",
    "หมดอายุ",
    "หมดเวลา",
    "expired",
    "เต็มแล้ว",
    "จำนวนเต็ม",
    "ครบจำนวน",
    "limit",
    "ไม่ถูกต้อง",
    "ตรวจสอบ keyword",
    "ตรวจสอบคีย์เวิร์ด",
    "invalid",
    "not found",
    "ไม่พบ",
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _log(log_fn, msg):
    if log_fn is not None:
        try:
            log_fn(msg)
        except Exception:
            pass


def _sleep_interruptible(seconds, is_stopped=None, stop_event=None):
    if stop_event is not None:
        stop_event.wait(timeout=seconds)
    elif is_stopped is not None:
        deadline = time.time() + seconds
        while time.time() < deadline:
            if is_stopped():
                return
            time.sleep(0.05)
    else:
        time.sleep(seconds)


def _wait_login_slot(username="", is_stopped=None, stop_event=None):
    """รอให้ถึงจังหวะปลอดภัยที่จะ POST ล็อกอินของไอดีนี้เท่านั้น (หน่วงจังหวะ
    ล็อกอินไอดีเดียวกัน — ล็อก 15 นาทีจริงๆ เกิดจากใส่รหัสผิดซ้ำในบัญชีเดียว)

    เดิมหน่วงแบบ global (ทุกไอดีรอคิวเดียวกัน) — ไอดีต่างกันต้องมารอต่อกัน
    ทำให้ "พร้อมกัน" หลายบัญชีไม่ช่วยให้จบเร็วขึ้นเลย จึงหน่วงต่อไอดีแทน:
    ไอดีใหม่ล็อกอินพร้อมกันได้ทันทีตาม concurrency
    """
    if not username:
        return
    while True:
        with _login_lock:
            now = time.time()
            wait = MIN_LOGIN_INTERVAL_SEC - (now - _last_login_by_user.get(username, 0.0))
            if wait <= 0:
                _last_login_by_user[username] = now
                # เก็บเฉพาะไอดีที่เพิ่งล็อกอินไม่นาน (ภายในช่วงหน่วง) — ลบทิ้ง
                # ของเก่าเป็นระยะ กัน dict โตไม่มีที่สิ้นสุดถ้าใช้หลายพันไอดี
                _login_slot_calls[0] += 1
                if _login_slot_calls[0] % _LOGIN_SLOT_CLEAN_EVERY == 0:
                    cutoff = now - MIN_LOGIN_INTERVAL_SEC * 4
                    for u, ts in list(_last_login_by_user.items()):
                        if ts < cutoff:
                            _last_login_by_user.pop(u, None)
                return
        _sleep_interruptible(wait, is_stopped, stop_event)


def _hidden_fields(text):
    return {k: v for k, v in _HIDDEN_RE.findall(text)}


def _req(session, method, url, retries=3, sleep=0.2, **kwargs):
    """ยิง request พร้อม retry เฉพาะ network error แบบ exponential backoff
    ไม่ retry POST สำคัญที่ผู้เรียกกำหนด retries=1 ไว้แล้ว"""
    last = None
    for i in range(retries):
        try:
            return session.request(method, url, **kwargs)
        except requests.RequestException as e:
            last = e
            if i < retries - 1:
                delay = min(sleep * (2 ** i), 8.0)
                time.sleep(delay)
    raise last


def _async_post(session, url, data, referer):
    """POST แบบ async postback (UpdatePanel) — ใช้กับปุ่มทุกปุ่มบนหน้า Keyword/Confirm

    retries=1 เสมอ (ไม่ retry อัตโนมัติ): ปุ่มยืนยันรับไอเทม (btnConfirm) เป็น
    POST ที่ไม่ idempotent — ถ้า server รับ POST ไปแล้วแต่ตัด connection ทิ้ง
    แล้วเราส่งซ้ำ จะกลายเป็น "รับไอเทมซ้ำ" หรือยิง POST ซ้ำโดยใช่เหตุ ปล่อยให้
    outer loop (run_session_multi / _autoitem_submit_one) เปิดหน้าใหม่ + ส่งใหม่
    เองตามเดิม"""
    return _req(
        session,
        "POST",
        url,
        data=data,
        headers={
            "Referer": referer,
            "X-MicrosoftAjax": "Delta=true",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=(5, 20),
        allow_redirects=True,
        retries=1,
    )


def _refresh_target(r):
    m = re.search(
        r"URL\s*=\s*(https?://[^\s'\"]+)", r.headers.get("Refresh") or "", re.I
    )
    return m.group(1) if m else None


def parse_delta(text):
    """parse ASP.NET UpdatePanel delta -> list of (type, id, data)
    รูปแบบ: <len>|<type>|<id>|<data> โดย len = ความยาว data (ไบต์)"""
    out = []
    i = 0
    n = len(text)
    while i < n:
        bar = text.find("|", i)
        if bar == -1:
            break
        try:
            ln = int(text[i:bar])
        except ValueError:
            break
        rest = text[bar + 1:]
        p1 = rest.find("|")
        if p1 == -1:
            break
        typ = rest[:p1]
        rest2 = rest[p1 + 1:]
        p2 = rest2.find("|")
        if p2 == -1:
            break
        sid = rest2[:p2]
        data = rest2[p2 + 1:p2 + 1 + ln]
        out.append((typ, sid, data))
        i = bar + 1 + p1 + 1 + p2 + 1 + ln
        if i < n and text[i] == "|":
            i += 1
        else:
            break
    return out


def delta_hidden_fields(delta_text):
    out = {}
    for typ, sid, data in parse_delta(delta_text):
        if typ == "hiddenField":
            out[sid] = data
    return out


# Pre-compiled regex for hot-path functions
_STRIP_SCRIPT_RE = re.compile(r"<script.*?</script>", re.S)
_STRIP_STYLE_RE = re.compile(r"<style.*?</style>", re.S)
_STRIP_TAGS_RE = re.compile(r"<[^>]+>")
_STRIP_WS_RE = re.compile(r"\s+")


def _strip_tags(html):
    text = _STRIP_SCRIPT_RE.sub(" ", html)
    text = _STRIP_STYLE_RE.sub(" ", text)
    text = _STRIP_TAGS_RE.sub(" ", text)
    return _STRIP_WS_RE.sub(" ", text).strip()


class ParsedDelta:
    """ASP.NET UpdatePanel delta, parsed once — cached access to hidden fields,
    panel HTML, and redirect target. Avoids re-parsing the same raw delta text."""
    __slots__ = ('parts', '_panel', '_target')

    def __init__(self, delta_text):
        self.parts = parse_delta(delta_text)
        self._panel = None
        self._target = None

    @property
    def panel_html(self):
        if self._panel is None:
            for typ, sid, data in self.parts:
                if typ == "updatePanel" and "ItemPanel" in sid:
                    self._panel = data
                    return self._panel
            self._panel = ""
        return self._panel

    @property
    def redirect_target(self):
        if self._target is None:
            for typ, _sid, data in self.parts:
                if typ in ("scriptStartupBlock", "scriptBlock"):
                    m = re.search(
                        r"window\.location\.href\s*=\s*['\"]([^'\"]+)['\"]", data
                    )
                    if m:
                        self._target = m.group(1)
                        return self._target
            self._target = ""
        return self._target


def _contains_any(text, patterns):
    low = text.lower()
    for p in patterns:
        if p.lower() in low:
            return p
    return None


def _raise_if_locked(text, username=""):
    hit = _contains_any(text, LOCKED_HINTS)
    if hit:
        tag = f"[{username}] " if username else ""
        raise LoginLockedError(f"{tag}บัญชีถูกระงับชั่วคราว 15 นาที ({hit})")


def _extract_alert_msg(text):
    """ดึงข้อความจริงจาก alert('...') ที่เว็บตอบกลับตอนล็อกอินไม่ผ่าน
    (เช่น '[V0] Invalid Username or Password') — กรอง alert เรื่อง cookie ออก"""
    for m in re.finditer(r"alert\s*\(\s*['\"]([^'\"]{1,200})['\"]\s*\)", text, re.IGNORECASE):
        msg = m.group(1).strip()
        low = msg.lower()
        # ข้าม alert เรื่อง cookie (อังกฤษ/ไทย) ที่มีอยู่ประจำทุกหน้า — ไม่ใช่เหตุผลล็อกอินจริง
        if not msg or "cookie" in low or "คุกกี้" in msg:
            continue
        return msg
    return ""


# ---------------------------------------------------------------------------
# cookie persistence (HTTP) — ไฟล์ <md5>.http.json ใน COOKIE_DIR, เข้ารหัส
# ---------------------------------------------------------------------------

def _cookie_pkl_path(username):
    safe = hashlib.md5(username.encode()).hexdigest()
    return os.path.join(COOKIE_DIR, f"{safe}.http.json")


def cookie_exists_http(username):
    return os.path.exists(_cookie_pkl_path(username))


def _read_cookie_payload_http(username):
    path = _cookie_pkl_path(username)
    try:
        with open(path, "r", encoding="utf-8") as f:
            envelope = json.load(f)
        protected = envelope.get("payload", "") if isinstance(envelope, dict) else ""
        payload = json.loads(decrypt_pwd(protected))
        if not isinstance(payload, dict) or not isinstance(payload.get("cookies"), list):
            return None
        return payload
    except Exception:
        return None


def is_cookie_fresh_http(username, max_days=COOKIE_MAX_DAYS):
    payload = _read_cookie_payload_http(username)
    if not payload or not payload.get("saved_at"):
        return False
    try:
        saved = time.mktime(time.strptime(payload["saved_at"], "%Y-%m-%dT%H:%M:%S.%f"))
    except ValueError:
        try:
            saved = time.mktime(time.strptime(payload["saved_at"], "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            return False
    return (time.time() - saved) / 86400 < max_days


def cookie_login_type_http(username):
    payload = _read_cookie_payload_http(username)
    if not payload:
        return None
    return payload.get("login_type") or None


def save_cookies_http(session, username, login_type=""):
    try:
        os.makedirs(COOKIE_DIR, exist_ok=True)
        cookies = [
            {
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path,
                "secure": bool(c.secure),
                "expires": c.expires,
            }
            for c in session.cookies
        ]
        if not cookies:
            return False
        payload = {
            "cookies": cookies,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "username": username,
            "login_type": login_type,
        }
        protected = encrypt_pwd(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        if not protected:
            return False
        with open(_cookie_pkl_path(username), "w", encoding="utf-8") as f:
            json.dump({"version": 1, "payload": protected}, f, ensure_ascii=False)
        return True
    except Exception as e:
        _logger.debug("save_cookies_http failed: %s", e)
        return False


def load_cookies_http(session, username):
    try:
        payload = _read_cookie_payload_http(username)
        cookies = payload.get("cookies", []) if payload else []
        if not cookies:
            return False
        for c in cookies:
            if not c.get("name") or c.get("value") is None:
                continue
            session.cookies.set(
                c["name"],
                c["value"],
                domain=c.get("domain"),
                path=c.get("path", "/"),
                secure=bool(c.get("secure", False)),
            )
        return True
    except Exception:
        return False


def clear_cookies_http(username):
    try:
        path = _cookie_pkl_path(username)
        if os.path.exists(path):
            os.remove(path)
        return True
    except Exception:
        return False


# ── Connection pool ร่วม (shared HTTPAdapter) ──
# ทุก requests.Session() สร้าง connection pool ของตัวเอง → แต่ละบัญชีต้องจ่าย
# TCP+TLS handshake ใหม่หมด (~50-200ms ต่อบัญชี) ตอนล็อกอิน/ส่งคีย์พร้อมกันหลาย
# บัญชี แชร์ adapter ตัวเดียวให้ทุก session ใช้ connection ซ้ำข้ามบัญชี
# (urllib3 PoolManager เป็น thread-safe) → บัญชีถัดไป/รอบถัดไปประหยัด handshake
_SHARED_ADAPTER = None
_SHARED_ADAPTER_LOCK = threading.Lock()


def new_http_session():
    """requests.Session ที่ mount connection pool กลางไว้แล้ว (ใช้ซ้ำข้ามบัญชี)"""
    global _SHARED_ADAPTER
    sess = requests.Session()
    try:
        from requests.adapters import HTTPAdapter

        with _SHARED_ADAPTER_LOCK:
            if _SHARED_ADAPTER is None:
                _SHARED_ADAPTER = HTTPAdapter(
                    pool_connections=32, pool_maxsize=32, max_retries=0
                )
        sess.mount("https://", _SHARED_ADAPTER)
        sess.mount("http://", _SHARED_ADAPTER)
    except Exception:
        pass  # ไม่มี requests/adapters — ใช้ Session ปกติ
    return sess


def session_is_valid(session):
    """เช็คว่า session นี้ล็อกอินอยู่จริง: GET หน้า Keyword แล้วเจอปุ่ม Logout

    เก็บ HTML หน้า Keyword ไว้ที่ session (ถ้าผ่าน) ให้ submit_keyword ใช้ต่อได้
    โดยไม่ต้อง GET หน้าเดิมซ้ำ — ประหยัด 1 request ต่อบัญชีต่อรอบ"""
    try:
        r = _req(session, "GET", KEYWORD_URL, timeout=(5, 10))
        ok = "btnLogout" in r.text
        if ok:
            try:
                session._sf_kw_html = r.text
            except Exception:
                pass
        return ok
    except Exception:
        return False


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------

def http_login(session, username, password, login_type="gameid", log_fn=None, is_stopped=None, stop_event=None):
    """ล็อกอินเต็มเส้นทาง (ไม่ใช้ cookie) — ใช้ requests.Session ที่ส่งเข้ามา
    raises LoginLockedError / LoginFailedError"""
    _wait_login_slot(username, is_stopped, stop_event)
    if is_stopped is not None and is_stopped():
        raise LoginFailedError("หยุดทำงานแล้ว")
    if stop_event is not None and stop_event.is_set():
        raise LoginFailedError("หยุดทำงานแล้ว")

    t0 = time.time()
    # timeout=(connect, read): กัน request ค้าง 20-25 วิ × 3 retry ตอนเว็บช้า
    r = _req(session, "GET", LOGIN_URL, timeout=(5, 15))
    _raise_if_locked(r.text, username)
    data = _hidden_fields(r.text)
    t1 = time.time()
    _log(log_fn, f" [{username}] ① เปิดหน้าล็อกอิน     {t1-t0:.1f}วิ ✓")

    if login_type == "ggpassport":
        data.update(
            {
                "txtTabVal": "1",
                "txt_username": username,
                "txt_password": password,
                "imb_login.x": "10",
                "imb_login.y": "10",
            }
        )
    else:
        data.update(
            {
                "txtTabVal": "2",
                "txt_username_by_game": username,
                "txt_password_by_game": password,
                "txtAdd": "@sf",  # เลือกเกม SF (showsf() ในหน้า login ตั้งค่านี้)
                "imb_login2.x": "10",
                "imb_login2.y": "10",
            }
        )
    data.update({"Menu1_txtLang": "EN"})

    # ⚠ POST ล็อกอินห้าม retry อัตโนมัติ (retries=1) — ถ้า server รับ POST ไปแล้วแต่
    # ตัด connection ทิ้ง แล้วเราส่งซ้ำ จะกลายเป็น "พยายามล็อกอินซ้ำ" เสี่ยงโดนล็อก
    # 15 นาที ปล่อยให้ outer loop (login_only) ทำ GET หน้าใหม่ + POST ใหม่ห่างกัน
    # ตาม backoff แทน
    r2 = _req(
        session,
        "POST",
        LOGIN_URL,
        data=data,
        headers={"Referer": r.url},
        timeout=(5, 20),
        allow_redirects=False,
        retries=1,
    )
    loc = r2.headers.get("Location")
    if not loc:
        _raise_if_locked(r2.text, username)
        alert_msg = _extract_alert_msg(r2.text)
        detail = f" — {alert_msg}" if alert_msg else ""
        raise LoginFailedError(f"[{username}] ล็อกอินไม่ผ่าน (เว็บตอบกลับมาหน้าเดิม){detail}")
    t2 = time.time()
    _log(log_fn, f" [{username}] ② ยืนยันรหัสผ่าน      {t2-t1:.1f}วิ ✓")

    start_url = requests.compat.urljoin(LOGIN_URL, loc)
    r3 = _req(session, "GET", start_url, timeout=(5, 15))
    _raise_if_locked(r3.text, username)
    d2 = _hidden_fields(r3.text)
    d2.update({"Menu1_txtLang": "EN", "ImageButton1.x": "150", "ImageButton1.y": "22"})
    r4 = _req(
        session,
        "POST",
        start_url,
        data=d2,
        headers={"Referer": r3.url},
        timeout=(5, 20),
        allow_redirects=False,
        retries=1,
    )
    loc2 = r4.headers.get("Location")
    if not loc2:
        _raise_if_locked(r4.text, username)
        raise LoginFailedError(f"[{username}] ยืนยันตัวตน (StartGames) ไม่สำเร็จ")
    t3 = time.time()
    _log(log_fn, f" [{username}] ③ ยืนยันสิทธิ์   {t3-t2:.1f}วิ ✓")

    r5 = _req(
        session,
        "GET",
        requests.compat.urljoin(start_url, loc2),
        timeout=(5, 15),
        allow_redirects=False,
    )
    tgt = _refresh_target(r5)
    if not tgt:
        _raise_if_locked(r5.text, username)
        raise LoginFailedError(f"[{username}] ไม่พบ SSO redirect (REFRESH header)")
    t4 = time.time()
    _log(log_fn, f" [{username}] ④ รับโทเค็น          {t4-t3:.1f}วิ ✓")

    _req(session, "GET", tgt, timeout=(5, 15), allow_redirects=True)
    t5 = time.time()

    # ตรวจ session จากหน้า Keyword เพียงครั้งเดียวหลัง SSO สำเร็จ
    if not session_is_valid(session):
        raise LoginFailedError(f"[{username}] ล็อกอินครบเส้นทางแต่ session ยังไม่ผ่าน")
    _log(log_fn, f" [{username}] ⑤ ลงชื่อเข้าใช้เสร็จ    {t5-t4:.1f}วิ ✓   Σ {t5-t0:.1f}วิ")
    return session


# ---------------------------------------------------------------------------
# keyword flow
# ---------------------------------------------------------------------------

def _grid_rows(html):
    """หาแถวตัวเลือกใน GridView (คีย์ EXP/หน่วย) -> [(checkbox_name, srl, label)]"""
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        m_srl = re.search(r'txtItemSRL[^>]*value="(\d+)"', row)
        m_cb = re.search(
            r'<input[^>]*type="checkbox"[^>]*name="([^"]*txtChkItem[^"]*)"', row
        )
        if m_srl and m_cb:
            label = _strip_tags(row)
            rows.append((m_cb.group(1), int(m_srl.group(1)), label))
    return rows


def _normalize_label(text):
    """ปรับ label ให้จับคู่แม่นขึ้น: ตัดช่องว่างซ้ำ, ตัวพิมพ์เล็ก, เอาเครื่องหมาย/แท็ก
    ออก เหลือคำหลัก — "Rank  2" กับ "rank2" กับ "แรงค์ที่ 2" จะเข้าคู่กันได้"""
    if not text:
        return ""
    low = text.lower()
    # เอาเครื่องหมายวรรคตอน/สัญลักษณ์ที่ไม่เกี่ยวกับคำออก (กัน "Rank-2" vs "Rank 2")
    low = re.sub(r"[\s_\-–—.,:;()\[\]{}|/\\]+", " ", low)
    low = re.sub(r"\s+", " ", low).strip()
    return low


def _pick_grid_row(rows, rank, unit, unit2):
    """เลือกตัวเลือกจากชื่อบนหน้าเว็บ โดยหน่วย 1 เป็นตัวเลือกหลักและหน่วย 2 เป็นตัวสำรอง
    เท่านั้น ไม่ได้เลือกหรือติ๊กพร้อมกันทั้งสองหน่วย

    คืน (cb_name, srl, label, via) — via บอกวิธีที่เลือก: 'text:เลข' / 'text:คำ'
    / 'unit' ใช้ log เพื่อดูว่าถูกเลือกจากชื่อที่พบจริงเท่านั้น

    ห้ามเลือกจากตำแหน่งแถว เพราะลำดับตัวเลือกบนเว็บไซต์อาจเปลี่ยนได้"""
    if not rows:
        return None
    if rank in ("rank1", "rank2"):
        rank_num = "1" if rank == "rank1" else "2"
        # 1) หาแถวที่ label ตรงตัวเลขแรงค์เป๊ะ ("rank 1"/"แรงค์ 1", "rank 2"/"แรงค์ 2")
        for i, (_, _, label) in enumerate(rows):
            # รองรับ "rank 2", "Rank-2", "แรงค์ 2", "แรงค์ที่ 2" (มีคำเชื่อม "ที่")
            if re.search(
                rf"\brank\s*{rank_num}\b|แรงค์(?:\s*ที่)?\s*{rank_num}",
                _normalize_label(label),
            ):
                return (rows[i][0], rows[i][1], rows[i][2], f"text:{rank_num}")
        # 2) มีคำ rank/แรงค์ ธรรมดา (แบบ v3.9.7): rank2=แถวที่มีคำ, rank1=แถวอื่นตัวแรก
        rank_idx = None
        for i, (_, _, label) in enumerate(rows):
            if re.search(r"\brank\b|แรงค์", _normalize_label(label)):
                rank_idx = i
                break
        if rank_idx is not None:
            if rank == "rank2":
                return (rows[rank_idx][0], rows[rank_idx][1], rows[rank_idx][2], "text:คำ")
            for i, row in enumerate(rows):
                if i != rank_idx:
                    return (row[0], row[1], row[2], "text:คำ")
            return (rows[rank_idx][0], rows[rank_idx][1], rows[rank_idx][2], "text:คำ")
        # ไม่ใช้ตำแหน่งแถวเป็น fallback เด็ดขาด — ต้องพบชื่อแรงค์บนหน้าเว็บเท่านั้น
        return None
    # rank == skip — หน่วย 1 เป็นตัวเลือกหลัก; หน่วย 2 ใช้เฉพาะเมื่อไม่พบหน่วย 1
    # รองรับชื่อหน่วยที่เว็บอาจแสดงต่างกัน (ตัวเล็ก/ตัวใหญ่/ชื่อย่อ) ด้วย UNIT_ALIASES
    from sfkeyword_lib.core.constants import UNIT_ALIASES
    for priority, want in ((1, unit), (2, unit2)):
        if want and want != "skip":
            wanted = _normalize_label(want)
            # หา alias ที่ตรงกับ want (เช่น "delta force" -> "DELTA")
            canonical = UNIT_ALIASES.get(wanted, want.upper())
            for row in rows:
                norm_row = _normalize_label(row[2])
                if not norm_row:
                    continue
                # จับคู่ 3 วิธี: 1) ชื่อ want ตรงๆ, 2) canonical name, 3) alias อื่นที่ map ไป canonical เดียวกัน
                if (wanted in norm_row or
                    _normalize_label(canonical) in norm_row or
                    any(_normalize_label(alias) in norm_row for alias, c in UNIT_ALIASES.items() if c == canonical)):
                    return (row[0], row[1], row[2], f"unit{priority}:{canonical}")
    return None


def _alert_text_from_delta(delta_parts):
    texts = []
    for typ, _sid, data in delta_parts:
        if typ in ("scriptStartupBlock", "scriptBlock"):
            for m in re.finditer(r"alert\(\s*['\"]([^'\"]+)['\"]\s*\)", data):
                texts.append(m.group(1))
    return texts


def _raise_if_keyword_error(html, code, parts=None):
    """ตรวจ error จาก delta (alert script) หรือ HTML — โยน Exception ที่มีคำหลัก
    ที่ run_session_multi ใช้ตัดสิน non-retryable
    
    NOTE: "คุณได้รับ"/"รับรางวัลแล้ว"/"ได้รับไปแล้ว"/"เคยรับ" เป็นข้อความ
    SUCCESS (รับของสำเร็จแล้ว) ไม่ใช่ error — ต้องไม่โยน exception"""
    if parts is not None:
        for t in _alert_text_from_delta(parts):
            hit = _contains_any(t, KEYWORD_ERROR_PATTERNS)
            if hit:
                raise Exception(f"คีย์เวิร์ด '{code}' ถูกปฏิเสธ: {t} ({hit})")
    hit = _contains_any(html, KEYWORD_ERROR_PATTERNS)
    if hit:
        raise Exception(f"คีย์เวิร์ด '{code}' ถูกปฏิเสธ: {hit}")


_LOGIN_FORM_MARKERS = (
    "txt_username_by_game",
    "txt_password_by_game",
    "txtTabVal",
    "imb_login2",
    "imb_login",
)


def _looks_like_login_page(text):
    """ตรวจว่าหน้าที่เว็บตอบกลับมาเป็นหน้า Login (session หลุด/ยังไม่ล็อกอิน) หรือไม่

    ใช้แยกกรณี session ตายกลางทางออกจาก "คีย์ถูกใช้ไปแล้ว" — ถ้า POST คีย์
    ตอบกลับมาเป็นหน้า Login (redirect กลับหน้าแรก) แสดงว่า session หมดอายุจริง
    ไม่ใช่คีย์เสีย ต้องโยน SessionExpiredError ให้ผู้เรียก (autoitem / main flow)
    ล้างคุกกี้ + ล็อกอินใหม่ + ส่งคีย์ใหม่เอง แทนที่จะแจ้ง "คีย์ถูกใช้ไปแล้ว"
    (เข้าใจผิด) แล้วปล่อยให้ไอดีหลุดต้องเข้าใหม่ด้วยมือ"""
    if not text or "btnLogout" in text:
        return False
    return any(m in text for m in _LOGIN_FORM_MARKERS)


def submit_keyword(session, code, rank="rank1", unit="skip", unit2="skip",
                   log_fn=None, is_stopped=None, username=""):
    """ส่งคีย์เวิร์ด + ยืนยันรับไอเทมเต็มเส้นทาง
    คืนข้อความผลลัพธ์ (เช่น "คุณได้รับ ... จบ")
    raises SessionExpiredError / KeywordPreviewOnly / Exception(ข้อความ error)"""
    if is_stopped is not None and is_stopped():
        raise Exception("หยุดทำงานแล้ว")
    lbl = username or code

    t0 = time.time()
    # 1) GET หน้า Keyword — เช็ค session
    # timeout=(connect, read): หน้าเว็บปกติตอบใน <1 วิ — กัน request ค้าง
    # 25 วิ × 3 retry (เกือบ 80 วิต่อบัญชี) ตอนเว็บช้า/ค้าง
    # ถ้า http_login/session_is_valid เพิ่งเช็ค session ผ่านมาไม่กี่มิลลิวินาที จะ
    # มี HTML ค้างไว้ใน session — ใช้ต่อได้เลย ไม่ต้อง GET หน้าเดิมซ้ำ (ประหยัด
    # 1 request ต่อบัญชีต่อรอบ)
    cached = getattr(session, "_sf_kw_html", None)
    if cached:
        body = cached
        try:
            del session._sf_kw_html
        except Exception:
            pass
    else:
        r = _req(session, "GET", KEYWORD_URL, timeout=(5, 15))
        body = r.text
    if "ContentPlaceHolder1_txtKeyword" not in body:
        if "btnLogout" not in body:
            raise SessionExpiredError("ยังไม่ล็อกอิน — ไม่พบปุ่ม Logout บนหน้า Keyword")
        raise SessionExpiredError("ล็อกอินอยู่แต่ไม่พบช่องกรอกคีย์เวิร์ด")
    t1 = time.time()
    _log(log_fn, f" [{lbl}] ① เปิดหน้าคีย์      {t1-t0:.1f}วิ ✓")

    # 2) async POST คีย์เวิร์ด
    data = _hidden_fields(body)
    data.update(
        {
            "ctl00$ContentPlaceHolder1$txtKeyword": code,
            "__EVENTTARGET": "ctl00$ContentPlaceHolder1$btnNext",
            "__EVENTARGUMENT": "",
            "__ASYNCPOST": "true",
            "ctl00$ScriptManager1": (
                "ctl00$ContentPlaceHolder1$ItemPanel|ctl00$ContentPlaceHolder1$btnNext"
            ),
        }
    )
    # ⚠ POST คีย์ห้าม retry อัตโนมัติ (retries=1) — ถ้า server รับ POST ไปแล้วแต่
    # ตัด connection ทิ้ง แล้วส่งซ้ำ คีย์จะถูกใช้ไปแล้ว/โดนปฏิเสธ ปล่อยให้
    # outer loop (run_session_multi) เปิดหน้าคีย์ใหม่ + ส่งใหม่เองแทน
    r2 = _req(
        session,
        "POST",
        KEYWORD_URL,
        data=data,
        headers={
            "Referer": KEYWORD_URL,
            "X-MicrosoftAjax": "Delta=true",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=(5, 20),
        allow_redirects=True,
        retries=1,
    )
    delta2 = ParsedDelta(r2.text)
    # session หลุดระหว่าง POST คีย์: เว็บตอบกลับมาเป็นหน้า Login (ไม่มี delta
    # redirect) — ต้องแจ้ง SessionExpiredError ก่อนตรวจ error ของคีย์ เพราะหน้า
    # Login ไม่มีปุ่ม/ฟอร์มของคีย์ เลยอาจจับคำผิดเป็น "คีย์ถูกใช้ไปแล้ว" ได้
    if _looks_like_login_page(r2.text):
        raise SessionExpiredError(
            f"[{lbl}] session หมดอายุระหว่างส่งคีย์ — เว็บเด้งกลับหน้า Login "
            "(ล็อกอินใหม่ให้อัตโนมัติ)"
        )
    _raise_if_keyword_error(delta2.panel_html, code, delta2.parts)
    t2 = time.time()
    _log(log_fn, f" [{lbl}] ② ส่งคีย์เวิร์ด     {t2-t1:.1f}วิ ✓")

    # 3) redirect ไป Confirm.aspx
    target = delta2.redirect_target
    if not target:
        raise Exception(f"คีย์ '{code}' ถูกใช้ไปแล้วหรือหมดอายุ — เว็บไม่ redirect กลับมาหน้ายืนยัน")
    confirm_url = requests.compat.urljoin(KEYWORD_URL, target)
    rc = _req(session, "GET", confirm_url, timeout=(5, 15))
    cbody = rc.text
    # เว็บตอบ alert script ล้วนๆ เมื่อคีย์มีปัญหา (เช่น "คุณได้รับคียเวิร์ดนี้ไปแล้ว",
    # "คูปองโค้ดนี้ถูกใช้ไปแล้ว") — ไม่มีฟอร์มยืนยันให้ไปต่อ จับข้อความมาแจ้งผู้ใช้ตรงๆ
    # ก่อนอื่นเช็คว่าหน้าที่ตอบกลับมาเป็นหน้า Login (session หลุดตอนเปิดหน้ายืนยัน)
    if _looks_like_login_page(cbody):
        raise SessionExpiredError(
            f"[{lbl}] session หมดอายุระหว่างเปิดหน้ายืนยัน — เว็บเด้งกลับหน้า Login "
            "(ล็อกอินใหม่ให้อัตโนมัติ)"
        )
    if "btnConfirm" not in cbody:
        m_alert = re.search(r"alert\(\s*['\"]([^'\"]+)['\"]\s*\)", cbody)
        if m_alert:
            raise Exception(f"คีย์ '{code}' เว็บแจ้ง: {m_alert.group(1).strip()}")
        raise Exception(f"คีย์ '{code}' หน้ายืนยันผิดปกติ (ไม่พบปุ่มยืนยัน)")
    t3 = time.time()
    _log(log_fn, f" [{lbl}] ③ ยืนยันการรับ     {t3-t2:.1f}วิ ✓")

    # 4) มีตัวเลือก (GridView)? -> เลือกแรงค์/หน่วยก่อนยืนยัน
    rows = _grid_rows(cbody)
    if rows:
        pick = _pick_grid_row(rows, rank, unit, unit2)
        if pick is None:
            labels = " | ".join(lbl for _, _, lbl in rows)
            raise KeywordPreviewOnly(
                f"ต้องเลือกแรงค์/หน่วยก่อน — ตัวเลือก: {labels}"
            )
        cb_name, srl, _lbl, via = pick
        _via_desc = {
            "text:1": "แรงค์ 1 (จากชื่อบนเว็บ)",
            "text:2": "แรงค์ 2 (จากชื่อบนเว็บ)",
            "text:คำ": "แรงค์ (จากชื่อบนเว็บ)",
        }.get(via, f"{_lbl} (จากชื่อบนเว็บ)")
        _log(log_fn, f" [{lbl}]  · เลือก {_via_desc} SRL={srl}")
        data = _hidden_fields(cbody)
        data.update(
            {
                cb_name: "on",
                "__EVENTTARGET": cb_name,
                "__EVENTARGUMENT": "",
                "__ASYNCPOST": "true",
                "ctl00$ScriptManager1": f"ctl00$ContentPlaceHolder1$ItemPanel|{cb_name}",
            }
        )
        r3 = _async_post(session, confirm_url, data, confirm_url)
        if _looks_like_login_page(r3.text):
            raise SessionExpiredError(
                f"[{lbl}] session หมดอายุระหว่างเลือกแรงค์/หน่วย — เว็บเด้งกลับหน้า "
                "Login (ล็อกอินใหม่ให้อัตโนมัติ)"
            )
        if "scriptStartupBlock" not in r3.text:
            raise Exception(f"เลือกหน่วย '{srl}' ไม่สำเร็จ")
        data.update(delta_hidden_fields(r3.text))
        data.update(
            {
                "__EVENTTARGET": "ctl00$ContentPlaceHolder1$btnConfirm",
                "__EVENTARGUMENT": "",
                "ctl00$ScriptManager1": (
                    "ctl00$ContentPlaceHolder1$ItemPanel|ctl00$ContentPlaceHolder1$btnConfirm"
                ),
            }
        )
        r4 = _async_post(session, confirm_url, data, confirm_url)
    else:
        # 5) ยืนยันตรงๆ
        data = _hidden_fields(cbody)
        data.update(
            {
                "ctl00$ContentPlaceHolder1$hdfModal": "",
                "__EVENTTARGET": "ctl00$ContentPlaceHolder1$btnConfirm",
                "__EVENTARGUMENT": "",
                "__ASYNCPOST": "true",
                "ctl00$ScriptManager1": (
                    "ctl00$ContentPlaceHolder1$ItemPanel|ctl00$ContentPlaceHolder1$btnConfirm"
                ),
            }
        )
        r4 = _async_post(session, confirm_url, data, confirm_url)

    # 6) ตรวจผลลัพธ์ — "คุณได้รับ ... จบ" = สำเร็จ
    delta4 = ParsedDelta(r4.text)
    # session หลุดตอนกดยืนยัน: เว็บตอบหน้า Login กลับมา — แจ้ง SessionExpiredError
    # ให้ผู้เรียกล็อกอินใหม่ + ส่งคีย์ใหม่แทนการแจ้ง "ไม่พบข้อความยืนยัน"
    if _looks_like_login_page(r4.text):
        raise SessionExpiredError(
            f"[{lbl}] session หมดอายุระหว่างยืนยันรับ — เว็บเด้งกลับหน้า Login "
            "(ล็อกอินใหม่ให้อัตโนมัติ)"
        )
    text = _strip_tags(delta4.panel_html)
    if "คุณได้รับ" in text:
        m = re.search(r"(คุณได้รับ.*?จบ)", text)
        result_msg = m.group(1) if m else text
        t4 = time.time()
        _log(log_fn, f" [{lbl}] ④ แสดงผลลัพธ์     {t4-t3:.1f}วิ ✓   รวม {t4-t0:.1f}วิ")
        return result_msg
    # ไม่มีข้อความรับของ — ตรวจ error จริง (alert จากเว็บก่อนเสมอ)
    _raise_if_keyword_error(delta4.panel_html, code, delta4.parts)
    alerts4 = _alert_text_from_delta(delta4.parts)
    if alerts4:
        raise Exception(f"คีย์ '{code}' เว็บแจ้ง: {' | '.join(a.strip() for a in alerts4)}")
    raise Exception(f"คีย์ '{code}' ยืนยันแล้วแต่ไม่พบข้อความยืนยันรับ")


__all__ = [
    "CONFIRM_URL",
    "MIN_LOGIN_INTERVAL_SEC",
    "clear_cookies_http",
    "cookie_exists_http",
    "cookie_login_type_http",
    "delta_hidden_fields",
    "ParsedDelta",
    "http_login",
    "is_cookie_fresh_http",
    "load_cookies_http",
    "new_http_session",
    "parse_delta",
    "save_cookies_http",
    "session_is_valid",
    "submit_keyword",
]
