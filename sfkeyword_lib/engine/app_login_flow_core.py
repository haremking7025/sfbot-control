"""The login flow — core state-machine half: `do_login` (full first-login
path: navigate, fill credentials, submit, verify, handle locked/suspended
accounts, retry on network errors) and `login_only` (cookie-based fast path
for accounts that already have a saved session).

⚠ เปลี่ยนจาก Selenium/Chrome เป็น **pure HTTP** แล้ว (v3.9.8+): ทุกขั้นตอน
ล็อกอิน (GET login -> POST -> StartGames -> SSO ticket -> LandingPlatform ->
session บน member.sf.in.th) ใช้ `requests` ล้วนๆ ผ่าน `http_flow.py` —
ไม่เปิด Chrome เลย `driver`/`wait` ในพารามิเตอร์เหลือไว้เพื่อความเข้ากันได้
กับตัวเรียกเก่าเท่านั้น (ไม่มีผลแล้ว)
"""

from ..core.constants import _HTTP_HEADERS
from ..core.exceptions import LoginFailedError, LoginLockedError
from ..core import http_flow
from ..core.http_flow import (
    clear_cookies_http,
    cookie_exists_http,
    cookie_login_type_http,
    http_login,
    is_cookie_fresh_http,
    load_cookies_http,
    new_http_session,
    save_cookies_http,
    session_is_valid,
)


class AppLoginFlowCoreMixin:
    def _http_session_store(self):
        if not hasattr(self, "_http_sessions"):
            self._http_sessions = {}
        return self._http_sessions

    def _set_http_session(self, username, sess):
        self._http_session_store()[username] = sess

    def _get_http_session(self, username):
        """คืน requests.Session ที่ล็อกอินอยู่ของไอดีนี้ (จาก session dict ก่อน แล้ว
        ค่อยเช็ค store ของ do_login — autoitem ใช้ path หลัง)"""
        with self._sessions_lock:
            for s in self._sessions:
                if s.get("username") == username:
                    return s.get("http")
        return self._http_session_store().get(username)

    def do_login(
        self, driver, wait, username, password, login_type="gameid", silent_cookie=False,
        skip_cookie_validate=False,
    ):
        """ล็อกอินด้วย HTTP (driver/wait เหลือไว้ compatibility เท่านั้น)

        พยายามใช้ cookie เก็บไว้ก่อน (ถ้าใหม่พอ + ยังใช้ได้) — ไม่ได้ก็ล็อกอินเต็ม
        สำเร็จ: บันทึก session ลง _http_sessions + save cookie

        silent_cookie: ถ้า True จะไม่ log บรรทัด 'คุกกี้หมดอายุ'/'ใช้คุกกี้เดิม'
        รายไอดี (ฝากไว้ให้ batch summary แทน)

        skip_cookie_validate: ถ้า True จะข้ามการ GET หน้า Keyword มาตรวจสอบว่า
        cookie ยังใช้ได้ (ประหยัด 1 request ต่อบัญชี) แล้วเชื่อ cookie ที่ใหม่พอ
        ตรงๆ เลย — ⚠ ปัจจุบันไม่มีผู้เรียกใช้แล้ว (autoitem เคยใช้ แต่เลิกแล้ว
        เพราะ cookie ค้างที่ session ตายฝั่งเซิร์ฟเวอร์อาจทำหน้า Keyword ผิดพลาด
        เป็น error แบบอื่นที่ไม่ใช่ SessionExpiredError ทำให้ไม่ล็อกอินซ้ำ —
        ตอนนี้ autoitem ตรวจ cookie จริงเสมอ: ตาย = ล้าง + ล็อกอินใหม่ในตัว)

        raises LoginLockedError / LoginFailedError"""
        with self._sessions_lock:
            self._cookie_login_result[username] = False

        sess = new_http_session()
        sess.headers.update(_HTTP_HEADERS)

        # ---- cookie fast-path ----
        if cookie_exists_http(username) and is_cookie_fresh_http(username):
            saved_type = cookie_login_type_http(username)
            if saved_type and saved_type != login_type:
                # ประเภทไอดีเปลี่ยน (เช่น เคยล็อกอินแบบ GG Passport แล้วเปลี่ยนแถว
                # เป็น Game ID) — อย่าลบคุกกี้เดิมทิ้งทันที เพราะถ้าล็อกอินเต็มเส้นทาง
                # นี้ล้มเหลว (รหัสผิด/เว็บขัดข้อง) ผู้ใช้จะเสียคุกกี้ที่ยังใช้ได้ของ
                # ประเภทเดิมไปเปล่า ๆ → แค่ข้ามไปล็อกอินเต็ม เสร็จแล้วค่อยทับคุกกี้ใหม่
                self.log(f"   เปลี่ยนประเภท: {saved_type} → {login_type}")
            else:
                load_cookies_http(sess, username)
                if skip_cookie_validate or session_is_valid(sess):
                    if not silent_cookie:
                        self.log("   ใช้คุกกี้เดิม (ไม่ต้องล็อกอิน)")
                    self._set_http_session(username, sess)
                    with self._sessions_lock:
                        self._cookie_login_result[username] = True
                    return
                if not silent_cookie:
                    self.log("   คุกกี้หมดอายุ — ล็อกอินใหม่")
                clear_cookies_http(username)
                sess.cookies.clear()  # reuse session, just wipe stale cookies

        # ---- ล็อกอินเต็มเส้นทาง ----
        http_login(
            sess,
            username,
            password,
            login_type,
            log_fn=self.log,
            is_stopped=self._stop_event.is_set,
            stop_event=self._stop_event,
        )
        self._set_http_session(username, sess)
        save_cookies_http(sess, username, login_type)

    def login_only(self, username, password, ver, login_type="gameid", rank="rank1", silent_cookie=False):
        """ล็อกอิน (HTTP) + สร้าง session dict ลง _sessions — ver เหลือไว้
        compatibility เท่านั้น (ควบคุม rate limit ผ่าน http_flow.MIN_LOGIN_INTERVAL_SEC)"""
        import time
        if self._stop_event.is_set():
            return
        t_start = time.time()
        # ฟิลด์ "หน่วงระหว่างล็อกอิน (วินาที)" (เดิมคือเวอร์ชัน Chrome) — ควบคุม
        # อัตราการ POST ล็อกอิน HTTP กันบัญชีโดนล็อก 15 นาที
        try:
            http_flow.MIN_LOGIN_INTERVAL_SEC = max(0.1, min(60.0, float(ver)))
        except Exception:
            pass
        max_retries = self._get_max_retries()
        normal_attempt = 0

        for attempt in range(1, max_retries + 2):
            if self._stop_event.is_set():
                break

            is_cookie_attempt = attempt == 1 and is_cookie_fresh_http(username)
            if not is_cookie_attempt:
                normal_attempt += 1
            try:
                attempt_lbl = (
                    f" (ลองใหม่ {normal_attempt - 1}/{max_retries})"
                    if normal_attempt > 1
                    else ""
                )
                login_type_label = {"gameid": "Game ID", "ggpassport": "GG Passport"}.get(login_type, login_type)
                self.log(f"▶ {username}  เข้าสู่ระบบ  ({login_type_label}){attempt_lbl}")

                self.do_login(None, None, username, password, login_type, silent_cookie=silent_cookie)
                if self._stop_event.is_set():
                    break

                elapsed = time.time() - t_start
                self.log(f"✔ {username}  เข้าสู่ระบบสำเร็จ  {elapsed:.1f}วิ")
                session = {
                    "username": username,
                    "password": password,
                    "driver": None,
                    "wait": None,
                    "http": self._get_http_session(username),
                    "login_type": login_type,
                    "rank": rank,
                }
                with self._sessions_lock:
                    self._sessions.append(session)
                    self._logged_in_users.add(username)

                # ล็อกเฉพาะประเภทไอดีหลังล็อกอินสำเร็จ ส่วนแรงค์/หน่วยยังตั้งค่าได้
                # จนถึงก่อนกดรับคีย์ตามที่ผู้ใช้ต้องการ
                def _lock_logged_in_type():
                    for row in getattr(self, "_rows", []):
                        try:
                            if row.user_var.get().strip() == username:
                                row.set_type_locked(True)
                                break
                        except Exception:
                            pass
                try:
                    self.root.after(0, _lock_logged_in_type)
                except Exception:
                    pass

                self._task_done()
                return session

            except LoginLockedError:
                self.log(f"✗ {username}  --  บัญชีถูกล็อก 15 นาที")
                self._record_failure(username, "login_locked", detail="บัญชีถูกล็อก 15 นาที")
                break

            except LoginFailedError as e:
                err_str = str(e)

                is_locked = any(
                    kw in err_str.lower()
                    for kw in [
                        "temporarily locked",
                        "login locked",
                        "too many login",
                        "too many attempts",
                        "wait 15 min",
                        "wait 15 minute",
                        "รอ 15 นาที",
                        "ถูกระงับ",
                        "ลองใหม่ภายหลัง",
                    ]
                )
                non_retryable = any(
                    kw in err_str.lower()
                    for kw in [
                        "รหัสผ่าน",
                        "password",
                        "ไม่พบผู้ใช้",
                        "user not found",
                        "banned",
                        "suspended",
                        "ถูกระงับ",
                        "ไม่มีสิทธิ์",
                    ]
                )

                # log ข้อความ error จริงจากเว็บ (สาเหตุที่แท้จริงที่ล็อกอินไม่ผ่าน)
                _err_short = err_str.split("] ")[-1].strip()
                if len(_err_short) > 130:
                    _err_short = _err_short[:130] + "..."

                is_last_attempt = attempt >= max_retries + 1
                if is_locked or non_retryable or is_last_attempt:
                    reason = (
                        "ถูกล็อก 15 นาที"
                        if is_locked
                        else "รหัสผ่านหรือไอดีไม่ถูกต้อง"
                        if non_retryable
                        else "เกินจำนวนครั้งที่ลอง"
                    )
                    self.log(f"✗ {username}  --  {reason}")
                    self.log(f"   ⚠ {username}  เหตุผล: {_err_short}")
                    self._record_failure(
                        username,
                        "login_locked" if is_locked else "login",
                        detail=_err_short or reason,
                    )
                    break
                else:
                    is_network_err = any(
                        kw in err_str.lower()
                        for kw in ["connection", "connect", "timeout",
                                   "timed out", "network", "reset", "refused"]
                    )
                    wait_sec = (
                        self._network_retry_delay(normal_attempt)
                        if is_network_err
                        else min(2 * normal_attempt, 20)
                    )
                    self.log(f"↻ {username}  ลองใหม่ {normal_attempt}/{max_retries}  ({wait_sec}วิ)")
                    self.log(f"   ⚠ {username}  เหตุผล: {_err_short}")
                    self._interruptible_sleep(wait_sec)

            except RuntimeError:
                if self._stop_event.is_set():
                    break
                if attempt >= max_retries + 1:
                    self.log(f"✗ {username}  --  เกิดข้อผิดพลาด")
                    self._record_failure(username, "login_other", detail="เกิดข้อผิดพลาดระหว่างล็อกอิน")
                    break
                wait_sec = min(2 * normal_attempt, 20)
                self.log(f"↻ {username}  ลองใหม่ {normal_attempt}/{max_retries}  ({wait_sec}วิ)")
                self._interruptible_sleep(wait_sec)

            except Exception:
                if attempt >= max_retries + 1:
                    self.log(f"✗ {username}  --  เกิดข้อผิดพลาด")
                    self._record_failure(username, "login_other", detail="เกิดข้อผิดพลาดระหว่างล็อกอิน")
                    break
                wait_sec = min(2 * normal_attempt, 20)
                self.log(f"↻ {username}  ลองใหม่ {normal_attempt}/{max_retries}  ({wait_sec}วิ)")
                self._interruptible_sleep(wait_sec)

        if not self._stop_event.is_set():
            with self._lock_stats:
                already_recorded = username in self._success_ids or any(
                    u == username for u, _ in self._failed_ids
                )
            if not already_recorded:
                self.log(f"✗ {username}  --  เกินจำนวนครั้ง")
                self._record_failure(username, "login_other", detail="เกินจำนวนครั้งที่ลอง")

        self._task_done()
        return None
