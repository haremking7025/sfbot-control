"""Auto-update and kill-switch via GitHub.

GitHub repo: haremking7025/sfbot-control

- **Kill switch**: checks ``kill_switch.json`` on ``main`` branch.
  If ``active=true`` the app shows a dialog and exits.
- **Auto-update**: checks ``update.json`` on ``main`` branch.
  Downloads and replaces the running EXE, then restarts.

Both checks happen once at startup (``check_on_startup``) and are
non-blocking — network errors are silently ignored so the app always
starts even offline.
"""

import hashlib
import json
import logging
import os
import random
import re
import sys
import subprocess
import tempfile
import time

try:
    from packaging.version import Version
except ImportError:
    Version = None

from .constants import (
    ACC,
    ACC2,
    BG,
    BG2,
    BG3,
    BG4,
    FG,
    FG2,
    FG3,
    GREEN,
    VERSION,
    _HTTP_HEADERS,
)
from .paths import DATA_DIR, _resource_path
from .ui_theme import _page_header

log = logging.getLogger("sfkeyword.updater")

# ── GitHub config ────────────────────────────────────────────────
_GITHUB_OWNER = "haremking7025"
_GITHUB_REPO = "sfbot-control"
_RAW_BASE = f"https://raw.githubusercontent.com/{_GITHUB_OWNER}/{_GITHUB_REPO}/main"

_KILL_SWITCH_URL = f"{_RAW_BASE}/kill_switch.json"
# raw.githubusercontent.com แคชตาม path (ไม่สนใจ query string) — cache-bust แบบ
# ?nocache=... ใช้ไม่ได้กับ CDN ของ GitHub เลย ต้องเช็คผ่าน GitHub Contents API
# (api.github.com ไม่แคช เห็นเวอร์ชันใหม่ทันที) แล้วค่อย fallback ไป raw
_UPDATE_API_URL = (
    f"https://api.github.com/repos/{_GITHUB_OWNER}/{_GITHUB_REPO}/contents/update.json"
)
_UPDATE_JSON_URL_NOCACHE = f"{_RAW_BASE}/update.json?nocache="
_DOWNLOAD_TIMEOUT = (10, 20)

# Timeout for quick checks (seconds)
_TIMEOUT_SHORT = 5


# ── Helpers ──────────────────────────────────────────────────────
def _parse_version(v: str):
    """Parse version string to comparable object."""
    v = v.strip().lstrip("v")
    if Version is not None:
        try:
            return Version(v)
        except Exception:
            pass
    # Fallback: tuple of ints
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0,)


def _is_newer(remote: str, local: str) -> bool:
    """Return True if *remote* is strictly newer than *local*."""
    try:
        return _parse_version(remote) > _parse_version(local)
    except Exception:
        return False


def _get(path: str, timeout: int = _TIMEOUT_SHORT, as_json: bool = True):
    """Simple GET via requests (imported lazily to avoid circular import)."""
    import requests
    headers = dict(_HTTP_HEADERS)
    headers["Accept"] = "application/vnd.github+json"
    r = requests.get(path, headers=headers, timeout=(5, timeout), allow_redirects=True)
    r.raise_for_status()
    if as_json:
        # try r.json() first, but fall back to manual parse + repair
        # (raw CDN occasionally serves stale JSON with literal \n in strings)
        try:
            return r.json()
        except (json.JSONDecodeError, requests.exceptions.JSONDecodeError):
            import re as _re
            text = r.text
            # replace literal newlines/tabs inside quoted strings
            fixed = _re.sub(
                r'"([^"]*?[\n\r\t][^"]*?)"',
                lambda m: '"' + m.group(1).replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t') + '"',
                text, flags=_re.DOTALL
            )
            return json.loads(fixed)
    return r.text


def _fetch_update_json():
    """ดึง update.json — ลอง GitHub Contents API (ไม่แคช) ก่อน แล้ว fallback ไป
    raw.githubusercontent.com (แคช ~5 นาที) เผื่อ API ถูก rate-limit/ล่ม"""
    import base64

    try:
        data = _get(_UPDATE_API_URL, timeout=_TIMEOUT_SHORT)
        if isinstance(data, dict) and data.get("content"):
            try:
                decoded = base64.b64decode(data["content"])
                parsed = json.loads(decoded.decode("utf-8"))
                if isinstance(parsed, dict) and (parsed.get("latest_version") or parsed.get("version")):
                    return parsed
            except Exception:
                pass
    except Exception as exc:
        log.debug("update.json via API failed (fallback to raw): %s", exc)
    try:
        return _get(f"{_UPDATE_JSON_URL_NOCACHE}{random.randint(0, 999999)}")
    except Exception as exc:
        log.debug("update.json via raw failed: %s", exc)
        return None


# ── Kill switch ──────────────────────────────────────────────────
def check_kill_switch() -> dict | None:
    """Check if a remote kill switch is active.

    Returns the kill-switch payload dict if active, ``None`` otherwise.
    Payload example::

        {
            "active": true,
            "message": "โปรแกรมถูกปิดปรับปรุงชั่วคราว กรุณารอ",
            "min_version": "1.0.0"
        }

    ``min_version`` is optional — if present, versions >= min_version
    are NOT affected by the kill switch (only older clients are).
    """
    import base64
    try:
        # ลอง API ก่อน (ไม่แคช)
        data = None
        try:
            raw = _get(
                f"https://api.github.com/repos/{_GITHUB_OWNER}/{_GITHUB_REPO}/contents/kill_switch.json",
                timeout=_TIMEOUT_SHORT,
            )
            if isinstance(raw, dict) and raw.get("content"):
                try:
                    decoded = base64.b64decode(raw["content"])
                    text = decoded.decode("utf-8")
                    # กัน JSON เสีย (เช่น \n จริงใน string แทนที่จะเป็น \\n)
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError:
                        # fallback: แก้ control chars ใน string values
                        import re
                        # แทนที่ unescaped newline/tab/cr ภายใน string values
                        fixed = re.sub(
                            r'"([^"]*?[\n\r\t][^"]*?)"',
                            lambda m: '"' + m.group(1).replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t') + '"',
                            text
                        )
                        data = json.loads(fixed)
                except Exception:
                    pass
        except Exception as exc:
            log.debug("kill switch via API failed (fallback to raw): %s", exc)
        # fallback: raw
        if not isinstance(data, dict):
            try:
                data = _get(_KILL_SWITCH_URL)
            except Exception as exc:
                log.debug("kill switch via raw failed: %s", exc)
                return None

        if not isinstance(data, dict):
            return None
        if not data.get("active"):
            return None
        # Check min_version — if our version is >= min_version, ignore kill switch
        min_ver = data.get("min_version")
        if min_ver:
            if not _is_newer(min_ver, VERSION):
                log.info("kill switch active but does not apply to v%s", VERSION)
                return None
        return data
    except Exception as exc:
        log.debug("kill switch check failed (ignored): %s", exc)
        return None


# ── Auto-update ──────────────────────────────────────────────────
def check_for_update() -> dict | None:
    """Check ``update.json`` for a newer version.

    Returns release info dict if an update is available::

        {
            "version": "1.1.0",
            "download_url": "https://github.com/.../SFKeyword_v1.0.1.exe",
            "body": "Release notes...",
            "sha256": "A1B2C3...",
            "force_update": false,
        }

    Returns ``None`` if already on latest version or check fails.
    ``force_update`` can be set to ``true`` to force the update dialog
    even when the remote version is the same as the local version.
    """
    try:
        data = _fetch_update_json()
        if not isinstance(data, dict):
            return None

        remote = (data.get("latest_version") or data.get("version") or "").strip()
        if not remote:
            return None

        force = bool(data.get("force_update", False))
        download_url = (data.get("download_url") or data.get("url") or "").strip()
        if not download_url:
            log.warning("update.json has no download_url / url")
            return None

        if not force and not _is_newer(remote, VERSION):
            log.info("already on latest version (%s)", VERSION)
            return None

        return {
            "version": remote,
            "download_url": download_url,
            "body": (data.get("release_notes") or data.get("notes") or ""),
            "sha256": data.get("sha256", "").strip(),
            "size": data.get("size", 0),
            "force_update": force,
        }
    except Exception as exc:
        log.debug("update check failed (ignored): %s", exc)
        return None


def _sha256_file(path: str) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def download_update(url: str, expected_sha256: str = "", progress_callback=None) -> str | None:
    """Download the update EXE to a temp path.

    Args:
        url: Direct download URL.
        expected_sha256: If non-empty, verify the downloaded file matches.
        progress_callback: Optional ``fn(bytes_downloaded, total_bytes)``.

    Returns:
        Path to downloaded file, or None on failure.
    """
    import requests
    try:
        # Determine filename from URL
        fname = url.split("/")[-1].split("?")[0]
        tmp_dir = tempfile.gettempdir()
        tmp_path = os.path.join(tmp_dir, fname)

        # connect 15s / read 30s — กันค้างนาน 2 นาทีเหมือนเดิม
        # (timeout=120 ตัวเดียว = รอ connect ค้างได้ถึง 120 วิ โดยไม่มี feedback)
        last_exc = None
        for attempt in range(1, 4):
            try:
                downloaded = os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0
                headers = dict(_HTTP_HEADERS)
                if downloaded:
                    headers["Range"] = f"bytes={downloaded}-"  # resume ไฟล์ครึ่งทาง
                r = requests.get(url, headers=headers, timeout=_DOWNLOAD_TIMEOUT, stream=True, allow_redirects=True)
                # ไฟล์ชั่วคราวอาจดาวน์โหลดครบแล้ว แต่การลองซ้ำส่ง Range
                # bytes=ขนาดไฟล์- ทำให้ GitHub ตอบ 416; ตรวจ SHA ก่อนเริ่มใหม่
                if downloaded and r.status_code == 416:
                    if expected_sha256 and _sha256_file(tmp_path).upper() == expected_sha256.upper():
                        log.info("partial file is already complete; reusing it")
                        downloaded = os.path.getsize(tmp_path)
                        total = downloaded
                        r.close()
                        break
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                    downloaded = 0
                    r.close()
                    continue
                r.raise_for_status()
                if downloaded and r.status_code != 206:
                    downloaded = 0  # เซิร์ฟเวอร์ไม่รองรับ resume — เริ่มใหม่
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                content_length = int(r.headers.get("content-length", 0))
                total = content_length + downloaded if r.status_code == 206 else content_length
                if downloaded and r.status_code == 206:
                    content_range = r.headers.get("Content-Range", "")
                    match = re.search(r"/([0-9]+)$", content_range)
                    if match:
                        total = int(match.group(1))

                # หากเซิร์ฟเวอร์ตอบ 200 ทั้งที่ขอ Range ต้องเริ่มเขียนใหม่ ไม่เช่นนั้น
                # ไฟล์จะถูกต่อท้ายจนเสียและตรวจ SHA ไม่ผ่าน
                write_mode = "ab" if downloaded and r.status_code == 206 else "wb"
                if write_mode == "wb":
                    downloaded = 0
                with open(tmp_path, write_mode) as f:
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback:
                                progress_callback(downloaded, total)
                if total and downloaded < total:
                    raise IOError(f"incomplete {downloaded}/{total}")
                break
            except Exception as exc:
                last_exc = exc
                log.warning("download attempt %d/3 failed: %s", attempt, exc)
                import time as _t
                _t.sleep(2)
        else:
            log.error("download failed after 3 attempts: %s", last_exc)
            return None

        log.info("downloaded update to %s (%d bytes)", tmp_path, downloaded)

        # ── SHA-256 verification ──
        if expected_sha256:
            actual = _sha256_file(tmp_path)
            if actual != expected_sha256.upper():
                log.error("SHA-256 mismatch! expected=%s, got=%s", expected_sha256, actual)
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                return None
            log.info("SHA-256 verified: %s", actual)

        return tmp_path
    except Exception as exc:
        log.error("download failed: %s", exc)
        return None


_UPDATE_LOG_FILE = os.path.join(DATA_DIR, "update_log.txt")


def _update_log(msg):
    """บันทึกขั้นตอนอัปเดตลงไฟล์ถาวรใน AppData (update_log.txt) — เผื่ออัปเดต
    พลาดที่เครื่องลูกค้าแล้วต้องย้อนดูว่าพลาดตรงไหน (ดาวน์โหลด/ตรวจไฟล์/copy/
    rename/เปิดโปรแกรมใหม่) ไม่ทำให้โปรแกรมพังถ้าเขียนไฟล์ไม่ได้"""
    try:
        from datetime import datetime

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(_UPDATE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def _cleanup_old_exe_backups():
    """ลบ EXE รุ่นก่อนหน้า (.exe.old) หลังเปิดเวอร์ชันใหม่สำเร็จแล้ว."""
    if not getattr(sys, "frozen", False):
        return
    try:
        folder = os.path.dirname(os.path.abspath(sys.executable))
        for name in os.listdir(folder):
            if name.lower().endswith(".exe.old"):
                try:
                    os.remove(os.path.join(folder, name))
                    _update_log(f"ลบไฟล์ EXE รุ่นก่อนหน้าแล้ว: {name}")
                except Exception as exc:
                    _update_log(f"ลบไฟล์ EXE รุ่นก่อนหน้าไม่สำเร็จ ({name}): {exc}")
    except Exception as exc:
        _update_log(f"ตรวจไฟล์ EXE รุ่นก่อนหน้าไม่สำเร็จ: {exc}")


def _is_zip_file(path: str) -> bool:
    """เช็คว่าไฟล์เป็น ZIP จริงไหม (ดู magic bytes PK) — กันพึ่งนามสกุลอย่างเดียว."""
    try:
        with open(path, "rb") as f:
            return f.read(2) == b"PK"
    except OSError:
        return False


def _extract_exe_from_zip(zip_path: str) -> str | None:
    """แตก ZIP ที่ดาวน์โหลดมา แล้วคืน path ของ EXE ตัวแรกที่เจอข้างใน

    ตั้งแต่ v1.2.2 release แจกเป็น ZIP (update.json → SFKeyword_vX.Y.Z.zip) แต่
    apply_update เดิมเขียนไว้สำหรับ EXE ตรงๆ — ถ้าไม่แตก ZIP ก่อนจะได้ไฟล์ ZIP
    ปลอมชื่อ .exe ที่ Windows เปิดไม่ได้ (เด้ง 'Unsupported 16-Bit Application'
    / 'This app can't run on your PC' — เจอจริงใน v1.2.3)
    """
    import zipfile

    try:
        with zipfile.ZipFile(zip_path) as z:
            exe_names = [
                n for n in z.namelist()
                if n.lower().endswith(".exe") and not n.startswith("__MACOSX")
            ]
            if not exe_names:
                log.error("ZIP ไม่มีไฟล์ .exe ข้างใน: %s", zip_path)
                _update_log(f"ZIP ไม่มีไฟล์ .exe ข้างใน: {zip_path}")
                return None
            exe_name = exe_names[0]
            # แตกไปที่ temp folder ใหม่ (ไม่ทับไฟล์อื่น) แล้วคืน path ไฟล์ EXE
            tmp_dir = tempfile.mkdtemp(prefix="sfkeyword_update_extract_")
            z.extract(exe_name, tmp_dir)
            extracted = os.path.join(tmp_dir, exe_name)
            if not os.path.isfile(extracted):
                log.error("แตก ZIP แล้วไม่พบ EXE: %s", extracted)
                _update_log(f"แตก ZIP แล้วไม่พบ EXE: {extracted}")
                return None
            log.info("แตก ZIP แล้ว: %s", extracted)
            _update_log(f"แตก ZIP แล้ว: {extracted}")
            return extracted
    except zipfile.BadZipFile as exc:
        log.error("ไฟล์ที่ดาวน์โหลดเป็น ZIP เสีย: %s (%s)", zip_path, exc)
        _update_log(f"ไฟล์ที่ดาวน์โหลดเป็น ZIP เสีย: {exc}")
        return None
    except Exception as exc:
        log.error("แตก ZIP ไม่สำเร็จ: %s (%s)", zip_path, exc)
        _update_log(f"แตก ZIP ไม่สำเร็จ: {exc}")
        return None


def apply_update(downloaded_path: str, new_version: str = "") -> bool:
    """สลับไฟล์ EXE + รีสตาร์ทผ่าน apply_update.bat (แบบเดียวกับ v3.9.7).

    รับไฟล์ที่ดาวน์โหลดมาซึ่งอาจเป็น EXE ตรงๆ (schema เก่า) หรือ ZIP (schema ใหม่
    ตั้งแต่ v1.2.2) — ถ้าเป็น ZIP จะแตกหา EXE ข้างในก่อน แล้วค่อยสลับไฟล์

    PyInstaller --onefile รัน 2 โปรเซส: bootloader (แม่) ถือ handle ล็อกไฟล์
    .exe กับแอป (ลูก) — เขียนทับไฟล์ที่กำลังรันตรงๆ เลยไม่ได้ วิธีที่ปลอดภัยคือ:

    ไฟล์ที่เครื่องผู้ใช้ใช้ชื่อคงที่ "SFKeyword.exe" (ไม่ผูกเวอร์ชัน) — ถ้าชื่อผูก
    เวอร์ชัน (SFKeyword_v1.0.5.exe) ทุกอัปเดตจะเกิดไฟล์ใหม่ = Windows สร้างไอคอน
    เดสก์ท็อปใหม่ไปวางช่องว่างถัดไป (ไอคอนที่ผู้ใช้วางไว้ย้ายที่) วิธีปลอดภัย:

    1. รอให้โปรเซสเดิมจบ (bootloader ปล่อย handle ล็อกไฟล์แล้ว)
    2. rename ไฟล์เดิมเป็น SFKeyword.exe — Windows เก็บตำแหน่งไอคอนเดิมไว้ตอน rename
    3. เก็บไฟล์เก่าเป็น .exe.old แบบซ่อน (rollback ได้ ไม่โผล่เป็นไอคอนใหม่)
    4. copy ไฟล์ใหม่ทับ SFKeyword.exe แล้วเปิดโปรแกรม — รอบถัดไปก็ copy ทับที่เดิม
    5. ถ้า rename/copy ล้มเหลวหลังลองครบ 10 รอบ → fallback วิธีเดิม
       (copy ไฟล์ใหม่ + เก็บเก่า .old) และเปิดไฟล์เดิมกลับถ้า copy พลาด
    """
    current_exe = sys.executable
    if not current_exe or not os.path.isfile(current_exe):
        log.error("cannot determine current exe path: %s", current_exe)
        _update_log(f"cannot determine current exe: {current_exe}")
        return False

    # ถ้าไฟล์ที่ดาวน์โหลดเป็น ZIP → แตกหา EXE ข้างในก่อน (schema ใหม่แจก ZIP)
    if _is_zip_file(downloaded_path):
        extracted = _extract_exe_from_zip(downloaded_path)
        if not extracted:
            return False
        downloaded_path = extracted

    # หาเวอร์ชันใหม่จากชื่อไฟล์ที่ดาวน์โหลด (SFKeyword_v1.0.5.exe → 1.0.5) — ใช้ใน log
    if not new_version:
        m = re.search(r"v?(\d+(?:\.\d+)+)", os.path.basename(downloaded_path))
        new_version = m.group(1) if m else VERSION

    pid = os.getpid()
    folder = os.path.dirname(os.path.abspath(current_exe))
    # ชื่อไฟล์คงที่ SFKeyword.exe (ไม่ผูกเวอร์ชัน) — ตามที่ผู้ใช้กำหนด กันไอคอน
    # เดสก์ท็อปย้ายที่ทุกอัปเดต (รายละเอียดใน docstring)
    new_named_exe = os.path.join(folder, "SFKeyword.exe")
    old_backup_exe = current_exe + ".old"
    log_path = _UPDATE_LOG_FILE

    updater_bat = os.path.join(tempfile.gettempdir(), "apply_update.bat")
    with open(updater_bat, "w", encoding="utf-8") as f:
        f.write(
            "@echo off\r\n"
            "setlocal enabledelayedexpansion\r\n"
            # PyInstaller 6.22.1+ adds a bootloader security check: the child
            # process verifies its parent's executable path matches its own.
            # When apply_update.bat relaunches the new EXE via `start "" "%~4"`,
            # cmd.exe (the parent) exits right away, so that check fails with
            # "Security validation failure: failed to obtain executable path for
            # parent process". PYINSTALLER_RESET_ENVIRONMENT=1 tells the bootloader
            # to treat the launched EXE as a fresh top-level process (documented
            # use case: implementing application restart) and skip the check.
            "set PYINSTALLER_RESET_ENVIRONMENT=1\r\n"
            f'echo [%date% %time%] apply_update.bat start (old pid %1) >> "{log_path}" 2>nul\r\n'
            ":WAIT_LOOP\r\n"
            'tasklist /fi "PID eq %1" 2>nul | find "%1" >nul\r\n'
            "if not errorlevel 1 (\r\n"
            "    timeout /t 1 /nobreak >nul\r\n"
            "    goto WAIT_LOOP\r\n"
            ")\r\n"
            # PyInstaller --onefile bootloader (โปรเซสแม่ที่ถือ handle ล็อกไฟล์ .exe)
            # อาจปล่อย handle ช้ากว่า PID ลูก เผื่อเวลาไว้กันโดน 'file in use'
            "timeout /t 2 /nobreak >nul\r\n"
            # ── เป้าหมาย: ไฟล์ชื่อ SFKeyword.exe คงที่ + ไอคอนเดสก์ท็อปอยู่ที่เดิม ──
            # เดิม copy ไฟล์ใหม่เป็นชื่อตามเวอร์ชัน (SFKeyword_v1.3.4.exe) = Windows
            # สร้างไอคอนใหม่ไปวางช่องว่างถัดไป (ไอคอนที่ผู้ใช้วางไว้ย้ายเป็น .old)
            # แก้: rename ไฟล์เดิมเป็น SFKeyword.exe ก่อน (rename ไม่ย้ายไอคอน) แล้ว
            # copy ตัวใหม่ทับเนื้อหา — รอบถัดไปก็ทับที่เดิม ไอคอนไม่เคยย้าย
            "if /I \"%~3\"==\"%~4\" goto REPLACE_SAME\r\n"
            "if exist \"%~4\" goto TRY_DELETE_TARGET\r\n"
            "goto TRY_RENAME\r\n"
            "\r\n"
            ":TRY_DELETE_TARGET\r\n"
            "rem มี SFKeyword.exe เก่าอยู่แล้ว (สำเนา/อัปเดตค้าง) — ลบออกก่อน\r\n"
            "set DEL_OK=0\r\n"
            "for /L %%i in (1,1,10) do (\r\n"
            '    del /f /q "%~4" >nul 2>nul\r\n'
            '    if not exist "%~4" set DEL_OK=1\r\n'
            '    if "!DEL_OK!"=="1" goto DEL_DONE\r\n'
            "    timeout /t 1 /nobreak >nul\r\n"
            ")\r\n"
            ":DEL_DONE\r\n"
            'if not "!DEL_OK!"=="1" goto COPY_NEW\r\n'
            "goto TRY_RENAME\r\n"
            "\r\n"
            ":TRY_RENAME\r\n"
            "rem rename ไฟล์เดิมเป็น SFKeyword.exe — ไอคอนเดสก์ท็อปอยู่ที่เดิม\r\n"
            "set REN_OK=0\r\n"
            "for /L %%i in (1,1,10) do (\r\n"
            '    ren "%~3" "%~nx4" >nul 2>nul\r\n'
            '    if exist "%~4" set REN_OK=1\r\n'
            '    if "!REN_OK!"=="1" goto REN_DONE\r\n'
            "    timeout /t 1 /nobreak >nul\r\n"
            ")\r\n"
            ":REN_DONE\r\n"
            "rem เก็บไฟล์เก่าเป็นสำรอง .exe.old แบบซ่อน (attrib +h) กันโผล่เป็น\r\n"
            "rem ไอคอนใหม่บนเดสก์ท็อป — ระบบลบ .old อัตโนมัติตอนเปิดรอบถัดไป\r\n"
            'if "!REN_OK!"=="1" (\r\n'
            f'    echo [%date% %time%] renamed old exe to %~4 >> "{log_path}" 2>nul\r\n'
            '    del /f /q "%~5" >nul 2>nul\r\n'
            '    copy /Y "%~4" "%~5" >nul 2>nul\r\n'
            '    attrib +h "%~5" >nul 2>nul\r\n'
            "    goto COPY_INTO_TARGET\r\n"
            ")\r\n"
            "goto COPY_NEW\r\n"
            "\r\n"
            ":REPLACE_SAME\r\n"
            "rem ไฟล์เดิมชื่อ SFKeyword.exe อยู่แล้ว — copy ทับตรงๆ (ตำแหน่งเดิม)\r\n"
            "set COPY_OK=0\r\n"
            "for /L %%i in (1,1,10) do (\r\n"
            '    copy /Y "%~2" "%~4" >nul 2>nul\r\n'
            '    if exist "%~4" set COPY_OK=1\r\n'
            '    if "!COPY_OK!"=="1" goto COPY_DONE_SAME\r\n'
            "    timeout /t 1 /nobreak >nul\r\n"
            ")\r\n"
            ":COPY_DONE_SAME\r\n"
            'if "!COPY_OK!"=="0" (\r\n'
            f'    echo [%date% %time%] copy FAILED after 10 tries, reopening old exe >> "{log_path}" 2>nul\r\n'
            '    start "" "%~3"\r\n'
            "    exit /b 1\r\n"
            ")\r\n"
            "goto LAUNCH\r\n"
            "\r\n"
            ":COPY_INTO_TARGET\r\n"
            "rem rename สำเร็จ — ตอนนี้ %~4 ยังมีเนื้อหาเก่า; copy ตัวใหม่ทับ\r\n"
            "set COPY_OK=0\r\n"
            "for /L %%i in (1,1,10) do (\r\n"
            '    copy /Y "%~2" "%~4" >nul 2>nul\r\n'
            '    if exist "%~4" set COPY_OK=1\r\n'
            '    if "!COPY_OK!"=="1" goto COPY_DONE_TARGET\r\n'
            "    timeout /t 1 /nobreak >nul\r\n"
            ")\r\n"
            ":COPY_DONE_TARGET\r\n"
            'if "!COPY_OK!"=="0" (\r\n'
            f'    echo [%date% %time%] copy FAILED after 10 tries, reopening old exe >> "{log_path}" 2>nul\r\n'
            "    rem ไฟล์เดิมถูก rename เป็น %~4 แล้ว (เนื้อหายังเป็นเวอร์ชันเก่า)\r\n"
            '    start "" "%~4"\r\n'
            "    exit /b 1\r\n"
            ")\r\n"
            f'echo [%date% %time%] copy new exe OK (rename-in-place) >> "{log_path}" 2>nul\r\n'
            "goto LAUNCH\r\n"
            "\r\n"
            ":COPY_NEW\r\n"
            "rem วิธีเดิม (fallback: rename ไม่ได้ / ลบไฟล์เก่าไม่ได้) — copy ไฟล์\r\n"
            "rem ใหม่เป็น SFKeyword.exe แล้วเก็บไฟล์เก่าเป็น .old\r\n"
            "set COPY_OK=0\r\n"
            "for /L %%i in (1,1,10) do (\r\n"
            '    copy /Y "%~2" "%~4" >nul 2>nul\r\n'
            '    if exist "%~4" set COPY_OK=1\r\n'
            '    if "!COPY_OK!"=="1" goto COPY_DONE_NEW\r\n'
            "    timeout /t 1 /nobreak >nul\r\n"
            ")\r\n"
            ":COPY_DONE_NEW\r\n"
            'if "!COPY_OK!"=="0" (\r\n'
            f'    echo [%date% %time%] copy FAILED after 10 tries, reopening old exe >> "{log_path}" 2>nul\r\n'
            '    start "" "%~3"\r\n'
            "    exit /b 1\r\n"
            ")\r\n"
            f'echo [%date% %time%] copy new exe OK >> "{log_path}" 2>nul\r\n'
            "rem เก็บไฟล์เก่าเป็นสำรอง (.exe.old) — ระบบลบ .old อัตโนมัติรอบถัดไป\r\n"
            'if /I "%~3"=="%~4" goto LAUNCH\r\n'
            'del /f /q "%~5" >nul 2>nul\r\n'
            "set BACKUP_OK=0\r\n"
            "for /L %%i in (1,1,10) do (\r\n"
            '    ren "%~3" "%~n5%~x5" >nul 2>nul\r\n'
            '    if exist "%~5" set BACKUP_OK=1\r\n'
            '    if "!BACKUP_OK!"=="1" goto BACKUP_DONE\r\n'
            "    timeout /t 1 /nobreak >nul\r\n"
            ")\r\n"
            ":BACKUP_DONE\r\n"
            f'echo [%date% %time%] backup old exe as %~5 (ok=!BACKUP_OK!) >> "{log_path}" 2>nul\r\n'
            "\r\n"
            ":LAUNCH\r\n"
            f'echo [%date% %time%] launching new exe %~4 >> "{log_path}" 2>nul\r\n'
            'start "" "%~4"\r\n'
        )

    _update_log(
        f"เริ่มสลับไฟล์ (v{new_version}): target={new_named_exe}, "
        f"old backup={old_backup_exe}"
    )
    try:
        subprocess.Popen(
            [
                "cmd",
                "/c",
                updater_bat,
                str(pid),
                downloaded_path,
                current_exe,
                new_named_exe,
                old_backup_exe,
            ],
            # ใช้ CREATE_NO_WINDOW ตัวเดียว (0x08000000) เหมือน v3.9.7 เดิม —
            # เติม DETACHED_PROCESS ต่อท้ายแล้วบน Windows 11 + Windows Terminal
            # หน้าต่าง cmd จะโผล่ขึ้นมาให้เห็นตอนรอสลับไฟล์
            creationflags=0x08000000 if sys.platform == "win32" else 0,
            close_fds=True,
        )
        log.info("apply_update.bat launched (pid=%d)", pid)
        _update_log("เรียก apply_update.bat แล้ว กำลังรอปิดโปรแกรมเดิมเพื่อสลับไฟล์")
        return True
    except Exception as exc:
        log.error("failed to launch apply_update.bat: %s", exc)
        _update_log(f"เรียก apply_update.bat ไม่สำเร็จ: {exc}")
        return False


# ── Startup orchestrator ─────────────────────────────────────────
def check_on_startup_sync(root):
    """Run kill switch + update check BEFORE main window appears.

    Called from sfkeyword.pyw BEFORE App(root) is created.  Blocks until
    the kill switch / update window is dismissed, then returns control
    so the main app can continue loading.

    Args:
        root: Hidden tk.Tk root (must exist but can be withdrawn).

    Returns:
        ``True`` if the app should proceed (no kill switch, or update
        was applied and the process is exiting anyway).
        ``False`` if kill switch was shown and user dismissed it
        (caller should exit).
    """

    # ลบ .exe.old ที่เหลือจากการอัปเดตรอบก่อน
    _cleanup_old_exe_backups()

    # bg thread: fetch network data only (NO tk operations)
    # main thread: polls until done (pumping tk events so splash stays alive),
    # then handles any popup windows itself (wait_window must be on main thread)
    import threading as _th
    _ks_data = [None]
    _up_data = [None]
    _done = [False]

    def _fetch():
        try:
            _ks_data[0] = check_kill_switch()
            _up_data[0] = check_for_update()
        except Exception:
            pass
        finally:
            _done[0] = True

    _th.Thread(target=_fetch, daemon=True).start()

    # pump tk events while waiting (splash stays responsive, progress bar moves)
    _deadline = time.time() + 10.0
    while not _done[0] and time.time() < _deadline:
        try:
            root.update()
        except Exception:
            return True
        time.sleep(0.02)

    # bg thread timed out or errored — proceed anyway (no popups)
    if not _done[0]:
        return True

    # ── NOW handle popups on main thread ──
    ks = _ks_data[0]
    if ks:
        win = _show_kill_switch_window(root, ks)
        root.wait_window(win)
        return False

    update = _up_data[0]
    if update:
        win = _show_update_window(root, update)
        root.wait_window(win)
        try:
            root.winfo_exists()
        except Exception:
            return False

    return True


def _logo_photo(size=56, master=None):
    """โหลดรูปโลโก้ SF (sf_logo.jpg / sf_logo.ico) เป็น PhotoImage
    แสดงรูปเต็มตามสัดส่วนเดิม (โลโก้ SF เป็นรูปโล่ — ตัดวงกลมจะโดนมุม/ปลายโล่ตัด
    ดูแปลก) ขนาดพอดีกรอบ ``size``×``size`` — คืน None ถ้าหาไฟล์ไม่เจอ
    (หน้าต่างจะวาดไอคอน fallback เอง)

    ``master`` ต้องเป็น Tk/Toplevel ที่สร้างแล้ว เพราะ PhotoImage ต้องมี root
    ก่อน (เรียกจากใน _show_update_window / _show_kill_switch_window เสมอ)"""
    try:
        from PIL import Image, ImageTk

        # ใน EXE รูปถูกฝังไว้ที่ _MEIPASS ผ่าน --add-data → _resource_path ใช้ได้
        # ใน dev mode (รันจาก .pyw) รูปอยู่ใต้ assets/ → ลองทั้งสองตำแหน่ง
        candidates = [
            _resource_path("sf_logo.jpg"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "sf_logo.jpg"),
            _resource_path("sf_logo.ico"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "sf_logo.ico"),
        ]
        path = next((p for p in candidates if os.path.exists(p)), None)
        if not path:
            return None
        img = Image.open(path).convert("RGBA")
        # รักษาสัดส่วนเดิม ไม่ตัด ไม่บีบ — ขยาย/ย่อให้พอดีกรอบ size×size
        scale = min(size / img.width, size / img.height)
        nw = max(1, int(img.width * scale))
        nh = max(1, int(img.height * scale))
        img = img.resize((nw, nh), Image.LANCZOS)
        return ImageTk.PhotoImage(img, master=master)
    except Exception as exc:
        log.debug("load logo photo failed: %s", exc)
        return None


# ── Kill switch window ───────────────────────────────────────────
def _show_kill_switch_window(parent, ks: dict):
    """Show a polished 'maintenance' window. Returns the Toplevel so
    caller can wait_window() on it."""
    import tkinter as tk

    msg = ks.get("message", "โปรแกรมถูกปิดปรับปรุงชั่วคราว กรุณารออัปเดตใหม่")


    win = tk.Toplevel(parent)
    win.title("ปิดปรับปรุง")
    win.resizable(False, False)
    win.configure(bg=BG)
    # ห้ามใช้ transient() ตอน parent withdraw — Windows จะซ่อนหน้าต่างลูก
    # ทำให้ wait_window รอสิ่งที่มองไม่เห็น = splash ค้างตลอดไป
    win.attributes("-topmost", True)
    win.grab_set()

    w, h = 420, 300
    # center on screen (not on parent, since parent may be hidden)
    sw = parent.winfo_screenwidth()
    sh = parent.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    win.geometry(f"{w}x{h}+{x}+{y}")

    # หัวสไตล์เดียวกับหัวแท็บ: ไอคอน + ชื่อหนา + เส้นคั่น
    _page_header(win, "ปิดปรับปรุงชั่วคราว", "🛠", padx=16)

    # ── Message card ──
    card = tk.Frame(win, bg=BG3)
    card.pack(fill="x", padx=16, pady=(14, 8))
    tk.Label(
        card, text=msg, font=("Leelawadee UI", 10),
        bg=BG3, fg=FG2, wraplength=330,
        padx=18, pady=18, justify="center",
    ).pack()

    def _quit():
        try:
            win.destroy()
        except Exception:
            pass
        try:
            parent.destroy()
        except Exception:
            pass

    tk.Button(
        win, text="ออกจากโปรแกรม", command=_quit,
        font=("Leelawadee UI", 11, "bold"),
        bg=ACC, fg="white", activebackground="#C9303A",
        activeforeground="white",
        relief="flat", padx=40, pady=12, borderwidth=0,
        cursor="hand2",
    ).pack(pady=(14, 24))

    win.protocol("WM_DELETE_WINDOW", _quit)
    # ดันหน้าต่างขึ้นบนสุดเหนือ splash + ขึ้นโฟกัส
    try:
        win.lift()
        win.focus_force()
        win.after(200, lambda: win.attributes("-topmost", False))
    except Exception:
        pass
    return win


# ── Update window ────────────────────────────────────────────────
def _show_update_window(parent, update: dict):
    """Show a polished update window with progress bar."""
    import tkinter as tk
    from tkinter import ttk

    new_version = update["version"]
    body = (update.get("body") or "").strip()
    size_bytes = update.get("size", 0) or 0
    dl_url = update["download_url"]
    expected_sha256 = update.get("sha256", "")

    win = tk.Toplevel(parent)
    win.title("อัปเดตโปรแกรม")
    win.resizable(False, False)
    win.configure(bg=BG)
    # ห้ามใช้ transient() ตอน parent withdraw — เหตุผลเดียวกับ kill switch
    win.attributes("-topmost", True)
    win.grab_set()

    w, h = 480, 560
    # center on screen (parent root may be hidden/withdrawn at this point,
    # so winfo_x/winfo_width would give 0/1 → window would land at (0,0))
    sw = parent.winfo_screenwidth()
    sh = parent.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    win.geometry(f"{w}x{h}+{max(0,x)}+{max(0,y)}")

    # หัวสไตล์เดียวกับหัวแท็บ: ไอคอน + ชื่อหนา + เส้นคั่น
    _page_header(win, "มีเวอร์ชันใหม่ให้อัปเดต", "🚀", padx=16)

    # ── Outer padding frame ──
    outer = tk.Frame(win, bg=BG)
    outer.pack(fill="both", expand=True, padx=0, pady=0)

    # ── Subtitle ──
    tk.Label(
        outer,
        text=f"เวอร์ชัน {new_version} พร้อมใช้งานแล้ว",
        font=("Leelawadee UI", 10),
        bg=BG,
        fg=FG2,
    ).pack(anchor="w", padx=16, pady=(2, 0))

    # ── Version cards ──
    cards = tk.Frame(outer, bg=BG)
    cards.pack(fill="x", padx=16, pady=(18, 0))

    def _version_card(frame, label, version, is_new=False):
        card = tk.Frame(frame, bg=BG3)
        bd = ACC2 if is_new else BG4
        tk.Frame(card, bg=bd, height=2).pack(fill="x")
        inner = tk.Frame(card, bg=BG3)
        inner.pack(fill="x", padx=16, pady=(12, 14))
        tk.Label(inner, text=label, font=("Leelawadee UI", 8),
                 bg=BG3, fg=FG3).pack(anchor="w")
        tk.Label(inner, text=version, font=("Consolas", 15, "bold"),
                 bg=BG3, fg=(ACC2 if is_new else FG2)).pack(anchor="w", pady=(2, 0))
        return card

    cur_card = _version_card(cards, "เวอร์ชันปัจจุบัน", f"v{VERSION}")
    cur_card.pack(side="left", fill="both", expand=True, padx=(0, 6))

    arrow = tk.Canvas(cards, width=26, height=34, bg=BG, highlightthickness=0)
    arrow.pack(side="left")
    arrow.create_line(4, 17, 22, 17, fill=ACC2, width=2, capstyle="round")
    arrow.create_polygon(22, 17, 15, 11, 15, 23, fill=ACC2, outline="")

    new_card = _version_card(cards, "เวอร์ชันใหม่", f"v{new_version}", True)
    new_card.pack(side="left", fill="both", expand=True, padx=(6, 0))

    # ── Info chips (ขนาดไฟล์) ──
    if size_bytes:
        info_row = tk.Frame(outer, bg=BG)
        info_row.pack(fill="x", padx=16, pady=(10, 0))
        size_mb = size_bytes / (1024 * 1024)
        chip = tk.Frame(info_row, bg=BG3)
        chip.pack(side="left")
        tk.Label(chip, text=f"  📦 ขนาดไฟล์ {size_mb:.1f} MB  ",
                 font=("Leelawadee UI", 8), bg=BG3, fg=FG2).pack(pady=4)

    # ── Release notes (กล่องเลื่อนได้) ──
    notes_outer = tk.Frame(outer, bg=BG3)
    notes_outer.pack(fill="both", expand=True, padx=16, pady=(12, 0))
    tk.Frame(notes_outer, bg=BG4, height=2).pack(fill="x")

    notes_inner = tk.Frame(notes_outer, bg=BG3)
    notes_inner.pack(fill="both", expand=True, padx=14, pady=(10, 12))

    notes_header = tk.Frame(notes_inner, bg=BG3)
    notes_header.pack(anchor="w")
    tk.Frame(notes_header, bg=ACC2, width=3, height=13).pack(side="left", padx=(0, 8))
    tk.Label(notes_header, text="อัปเดตเวอร์ชันนี้",
             font=("Leelawadee UI", 10, "bold"),
             bg=BG3, fg=FG).pack(side="left")

    notes_box = tk.Text(notes_inner, wrap="word", bg=BG2, fg=FG2,
                        relief="flat", borderwidth=0, highlightthickness=0,
                        font=("Leelawadee UI", 9), padx=12, pady=10,
                        height=6, state="disabled", cursor="arrow")
    notes_scroll = tk.Scrollbar(notes_inner, command=notes_box.yview,
                                width=10, troughcolor=BG2)
    notes_box.configure(yscrollcommand=notes_scroll.set)
    notes_box.pack(side="left", fill="both", expand=True, pady=(8, 0))
    notes_scroll.pack(side="right", fill="y", pady=(8, 0))

    def _set_notes(txt):
        txt = (txt or "").strip()
        if not txt:
            return
        # แปลง markdown bullet ง่ายๆ เป็น • และตัด markdown หัวข้อ
        import re as _re
        txt = _re.sub(r"^#{1,6}\s*", "", txt, flags=_re.MULTILINE)
        txt = _re.sub(r"^[-*]\s+", "•  ", txt, flags=_re.MULTILINE)
        txt = _re.sub(r"\*\*([^*]+)\*\*", r"\1", txt)
        lines = [ln for ln in txt.splitlines() if ln.strip()][:20]
        notes_box.configure(state="normal")
        notes_box.delete("1.0", "end")
        notes_box.insert("1.0", "\n".join(lines))
        notes_box.configure(state="disabled")

    if body:
        _set_notes(body)
    else:
        # ไม่มี notes ใน update.json → ดึงจาก GitHub Release body (background)
        def _fetch_notes_bg():
            try:
                rel = _get(f"https://api.github.com/repos/{_GITHUB_OWNER}/{_GITHUB_REPO}"
                           f"/releases/tags/v{new_version}", timeout=_TIMEOUT_SHORT)
                txt = (rel.get("body") or "").strip() if isinstance(rel, dict) else ""
                if txt:
                    try:
                        win.after(0, lambda: _set_notes(txt))
                    except Exception:
                        pass
            except Exception:
                pass
        import threading as _th
        _th.Thread(target=_fetch_notes_bg, daemon=True).start()

    # ── Progress section (hidden initially) ──
    progress_outer = tk.Frame(outer, bg=BG)

    # Custom styled progress bar
    style = ttk.Style()
    style.theme_use("default")
    style.configure("Update.Horizontal.TProgressbar",
                    troughcolor=BG3, background=ACC2,
                    bordercolor=BG3, lightcolor=ACC2,
                    darkcolor=ACC2)
    progress_bar = ttk.Progressbar(
        progress_outer, mode="determinate", length=400,
        style="Update.Horizontal.TProgressbar",
    )

    status_label = tk.Label(
        progress_outer, text="", font=("Leelawadee UI", 8),
        bg=BG, fg=FG3,
    )

    # ── Buttons ──
    btn_frame = tk.Frame(outer, bg=BG)
    btn_frame.pack(side="bottom", fill="x", padx=16, pady=(0, 24))

    def _make_btn(text, bg_color, fg_color, hover_color, cmd=None):
        btn = tk.Button(
            btn_frame, text=text,
            font=("Leelawadee UI", 10, "bold"),
            bg=bg_color, fg=fg_color, activebackground=hover_color,
            activeforeground=fg_color,
            relief="flat", padx=32, pady=10,
            cursor="hand2", borderwidth=0,
        )
        if cmd:
            btn.configure(command=cmd)
        return btn

    update_btn = _make_btn("อัปเดตเลย", ACC2, "white", "#7C5CBF")
    update_btn.pack(side="right")

    skip_btn = tk.Button(
        btn_frame, text="ไว้ทีหลัง",
        font=("Leelawadee UI", 10),
        bg=BG, fg=FG3, activebackground=BG3, activeforeground=FG2,
        relief="flat", padx=20, pady=10,
        cursor="hand2", borderwidth=0,
        command=win.destroy,
    )
    skip_btn.pack(side="right", padx=(0, 8))

    win.protocol("WM_DELETE_WINDOW", win.destroy)

    # ── Download logic ──
    def _start_download():
        # Tkinter ไม่ thread-safe: worker ห้ามเรียก win.after/configure โดยตรง
        # ใช้ queue ส่งเหตุการณ์กลับมา แล้วให้ main loop อัปเดต UI เพียงจุดเดียว
        import queue
        import threading
        import time as _time

        update_btn.configure(state="disabled", text="กำลังเชื่อมต่อ...",
                             bg=BG4, fg=FG3)
        skip_btn.configure(state="disabled")

        progress_outer.pack(fill="x", padx=16, pady=(16, 0))
        progress_bar.pack(fill="x", pady=(0, 6))
        status_label.pack()

        events = queue.Queue()
        state = {
            "watch": None,
            "poll": None,
            "last_done": 0,
            "last_time": _time.monotonic(),
            "speed": 0.0,
        }

        def _set_watchdog():
            if state["watch"]:
                try:
                    win.after_cancel(state["watch"])
                except Exception:
                    pass
            state["watch"] = win.after(45000, _stall_warning)

        def _stall_warning():
            state["watch"] = None
            if update_btn["state"] == "disabled":
                status_label.configure(
                    text="เครือข่ายช้าหรือหลุด — กำลังลองเชื่อมต่อใหม่อัตโนมัติ...",
                    fg=ACC,
                )

        def _progress(done, total):
            # callback นี้ทำงานใน worker thread จึงทำได้แค่ใส่ข้อมูลลง queue
            events.put(("progress", done, total))

        def _show_failure(message):
            if state["watch"]:
                try:
                    win.after_cancel(state["watch"])
                except Exception:
                    pass
            if state["poll"]:
                try:
                    win.after_cancel(state["poll"])
                except Exception:
                    pass
            status_label.configure(text=message, fg=ACC)
            update_btn.configure(state="normal", text="ลองอีกครั้ง", bg=ACC2, fg="white")
            skip_btn.configure(text="ปิด", state="normal", command=win.destroy)

        def _finish(downloaded):
            if state["watch"]:
                try:
                    win.after_cancel(state["watch"])
                except Exception:
                    pass
            if state["poll"]:
                try:
                    win.after_cancel(state["poll"])
                except Exception:
                    pass
            progress_bar["value"] = 100
            status_label.configure(text="ดาวน์โหลดเสร็จสมบูรณ์ — กำลังรีสตาร์ท...", fg=GREEN)
            update_btn.configure(text="รีสตาร์ท...", bg=GREEN, fg="white")
            launched = apply_update(downloaded, new_version)
            if launched:
                try:
                    win.destroy()
                except Exception:
                    pass
                try:
                    parent.destroy()
                except Exception:
                    pass
                import threading as _th
                def _force_exit():
                    import time as _t
                    _t.sleep(1.0)
                    os._exit(0)
                _th.Thread(target=_force_exit, daemon=True).start()
            else:
                status_label.configure(text="เริ่มรีสตาร์ทไม่สำเร็จ — ลองอัปเดตด้วยตัวเอง", fg=ACC)
                update_btn.configure(state="normal", text="ลองอีกครั้ง", bg=ACC2, fg="white")
                skip_btn.configure(text="ปิด", state="normal", command=win.destroy)

        def _poll_events():
            # ฟังก์ชันนี้รันใน Tk main thread เท่านั้น
            latest = None
            finished = None
            failure = None
            try:
                while True:
                    event = events.get_nowait()
                    if event[0] == "progress":
                        latest = event[1:]
                    elif event[0] == "done":
                        finished = event[1]
                    elif event[0] == "fail":
                        failure = event[1]
            except queue.Empty:
                pass

            if latest is not None:
                done, total = latest
                now = _time.monotonic()
                elapsed = now - state["last_time"]
                if elapsed >= 0.2:
                    state["speed"] = max(0, done - state["last_done"]) / elapsed
                    state["last_done"], state["last_time"] = done, now
                pct = min(100, int(done * 100 / total)) if total else 0
                progress_bar["value"] = pct
                mb_done = done / (1024 * 1024)
                mb_total = total / (1024 * 1024) if total else 0
                text = f"{pct}%  ·  {mb_done:.1f} / {mb_total:.1f} MB"
                if state["speed"] > 0:
                    text += f"  ·  {state['speed'] / (1024 * 1024):.1f} MB/s"
                status_label.configure(text=text, fg=FG3)
                _set_watchdog()

            if failure is not None:
                _show_failure(failure)
                return
            if finished is not None:
                _finish(finished)
                return
            state["poll"] = win.after(100, _poll_events)

        def _dl_thread():
            try:
                downloaded = download_update(dl_url, expected_sha256=expected_sha256,
                                             progress_callback=_progress)
                if downloaded:
                    events.put(("done", downloaded))
                else:
                    events.put(("fail", "ดาวน์โหลดไม่สำเร็จ — เช็คอินเทอร์เน็ตแล้วลองใหม่"))
            except Exception:
                log.exception("update worker failed")
                events.put(("fail", "เกิดข้อผิดพลาดระหว่างอัปเดต"))

        state["poll"] = win.after(100, _poll_events)
        threading.Thread(target=_dl_thread, daemon=True).start()

    update_btn.configure(command=_start_download)
    # ดันหน้าต่างขึ้นบนสุดเหนือ splash + ขึ้นโฟกัส
    try:
        win.lift()
        win.focus_force()
        win.after(200, lambda: win.attributes("-topmost", False))
    except Exception:
        pass
    return win
