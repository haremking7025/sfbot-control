"""The HTTP automation core shared by both flows: per-account session runner
(run_session_multi, close-all, cookie cleanup) and retry/resume config.
The login-specific and keyword-specific flows live in
app_login_flow_core.py and app_keyword_flow_core.py -- split out of this
file because each was large and self-contained enough to read/maintain on
its own; this file keeps only what both of them share."""

import logging

from ..core.deps import os, random, threading
from ..core.exceptions import KeywordPreviewOnly, LoginLockedError, SessionExpiredError
from ..core.http_flow import clear_cookies_http
from ..core.paths import COOKIE_DIR

_logger = logging.getLogger(__name__)


class AppAutomationMixin:
    """ตัวรันคีย์เวิร์ดต่อบัญชี (`run_session_multi`) + จัดการเซสชัน/ปุ่มสถานะ

    ⚠ โหมด Pure HTTP (v3.9.8+): โค้ด Selenium ทั้งหมด (injected JS, คลิกปุ่ม,
    รอ AJAX endRequest) ถูกลบออกแล้ว — การทำงานจริงอยู่ใน `http_flow`"""

    def _get_max_retries(self):
        return self._fixed_retry

    def _network_retry_delay(self, attempt):
        """backoff ของปัญหาเครือข่ายเท่านั้น; ปัญหารหัสผ่านไม่เข้ามาถึงจุดนี้."""
        return min(self._network_retry_base_sec * max(1, attempt), 30)

    def _use_resume(self):
        return bool(getattr(self, "_resume_var", None) and self._resume_var.get())

    def run_session_multi(
        self, session, codes, rank="rank1", code_delay=1.5, unit="skip", unit2="skip"
    ):
        import time
        driver, wait, username = session["driver"], session["wait"], session["username"]
        t_start = time.time()
        success_count = 0
        skipped_count = 0
        processed = 0
        locked_out = False
        max_retries = self._get_max_retries()
        use_resume = self._use_resume()
        try:
            for i, code in enumerate(codes):
                if self._stop_event.is_set():
                    break

                if use_resume and self._completed_pairs_has((username, code)):
                    # คีย์นี้เคยส่งสำเร็จให้ไอดีนี้แล้วในเซสชันนี้ — ข้าม ไม่ส่งซ้ำ
                    # (ส่งซ้ำเว็บจะปฏิเสธ) และบันทึกเป็น "เคยใช้ไปแล้ว" แยกจาก
                    # "สำเร็จ" เพื่อไม่ให้สรุป/popup หลอกว่าเพิ่งรับของสำเร็จ
                    self.log(f" ⏭ {username}  {code}  เคยใช้ไปแล้ว (ข้าม)")
                    skipped_count += 1
                    processed += 1
                    self._record_result(username, code, "already")
                    self._task_done()
                    continue

                if i > 0 and code_delay > 0:
                    wait_sec = code_delay * random.uniform(0.7, 1.3)
                    self._interruptible_sleep(wait_sec)
                    if self._stop_event.is_set():
                        break
                attempt = 0
                stop_now = False
                while True:
                    try:
                        self.do_keyword(driver, wait, code, username, rank, unit, unit2)
                        success_count += 1
                        self._completed_pairs_add((username, code))
                        self._record_result(username, code, "success")
                        break
                    except RuntimeError:
                        stop_now = True
                        break
                    except KeywordPreviewOnly:
                        self._record_result(username, code, "previewed")
                        break
                    except SessionExpiredError as e:
                        err_str = str(e)
                        self.log(f" ⚠ {username}  เซสชันหมดอายุ — กำลังล็อกอินใหม่")
                        clear_cookies_http(username)

                        relogin_ok = False
                        try:
                            if self._stop_event.is_set():
                                stop_now = True
                                break
                            self.do_login(
                                None,
                                None,
                                username,
                                session.get("password", ""),
                                session.get("login_type", "gameid"),
                            )
                            session["http"] = self._get_http_session(username)
                            relogin_ok = True
                        except LoginLockedError:
                            self.log(f"✗ {username}  {code}  --  ถูกล็อก 15 นาที")
                            self._record_result(username, code, "fail")
                            locked_out = True
                            stop_now = True
                            break
                        except Exception:
                            pass
                        if relogin_ok and attempt < max_retries:
                            attempt += 1
                            self.log(f"↻ {username}  {code}  retry {attempt}/{max_retries}")
                            self._interruptible_sleep(0.3)
                            if self._stop_event.is_set():
                                stop_now = True
                                break
                            continue
                        self.log(f"✗ {username}  {code}  --  {err_str}")
                        self._record_result(username, code, "fail")
                        if not relogin_ok:
                            stop_now = True
                        break
                    except Exception as e:
                        err_str = str(e)
                        non_retryable = any(
                            k in err_str
                            for k in (
                                "ถูกใช้งานแล้ว", "รับรางวัลแล้ว", "คุณได้รับ",
                                "ได้รับไปแล้ว", "เคยรับ", "ซ้ำ", "already", "used",
                                "duplicate", "หมดอายุ", "expired", "เต็มแล้ว",
                                "limit", "ไม่ถูกต้อง", "ไม่พบ", "invalid",
                                "not found", "ตรวจสอบ Keyword", "ตรวจสอบคีย์เวิร์ด",
                            )
                        )
                        if not non_retryable and attempt < max_retries:
                            attempt += 1
                            self.log(f"↻ {username}  {code}  retry {attempt}/{max_retries}")
                            self._interruptible_sleep(0.3)
                            if self._stop_event.is_set():
                                stop_now = True
                                break
                            continue
                        self.log(f"✗ {username}  {code}  --  {err_str}")
                        self._record_result(username, code, "fail")
                        break
                self._task_done()
                processed += 1
                if stop_now:
                    break

            remaining = len(codes) - processed
            for _ in range(remaining):
                self._task_done()

            elapsed = time.time() - t_start
            if success_count == len(codes):
                self.log(f"✓ {username}  done  {success_count}/{len(codes)}  {elapsed:.1f}วิ")
                self._record_success(username)
            elif success_count > 0:
                self.log(f"◑ {username}  done  {success_count}/{len(codes)}  {elapsed:.1f}วิ")
                self._record_success(username)
            elif skipped_count == len(codes):
                self.log(f"⏭ {username}  done  เคยใช้คีย์นี้ไปแล้วทั้งหมด {skipped_count}/{len(codes)}")
                self._record_already(username)
            elif locked_out:
                self._record_failure(username, "login_locked", detail="บัญชีถูกล็อกระหว่างส่งคีย์")
            else:
                self._record_failure(username, "keyword", detail="ส่งคีย์ไม่สำเร็จทุกตัว")
        except Exception as e:
            self.log(f"✗ {username}  ERR  {e}")
            self._record_failure(username, "keyword_other", detail=str(e))

    def close_all_sessions(self):
        try:
            self.close_btn.configure(state="disabled", text="⛔ กำลังปิด...")
        except Exception as _e:
            _logger.debug("ignored error at app_automation.py:1958: %s", _e)
        threading.Thread(target=self._do_close_all_sessions, daemon=True).start()

    def _close_sessions_cleanup(self, closed_users, log_count=None):
        """ทำความสะอาดหลังปิดเซสชัน: log + รีเซ็ตปุ่มล็อกอิน/คีย์เวิร์ด + ล้างสถิติ
        pending + ปลดล็อกประเภทไอดี (Game ID/GG Passport)

        ใช้ร่วมกัน 2 ที่: ปุ่ม ⛔ ปิดเซสชันทั้งหมด และจบรอบ ▶ เริ่มรันอัตโนมัติ
        (ก่อนหน้านี้ auto-run ทิ้ง session แค่ถอดออกจากลิสต์ ไม่ปลดล็อกประเภทไอดี
        ไม่ล้าง pending ทำให้ UI ค้างสถานะ 'มีเซสชัน' อยู่หลังจบรอบ)"""
        if log_count is not None:
            try:
                self.log(f"── close  {log_count} sessions")
            except Exception as _e:
                _logger.debug("ignored error at sessions cleanup log: %s", _e)
        try:
            self.root.after(
                0,
                lambda: self.keyword_btn.configure(
                    state="disabled", text="กรอกคีย์เวิร์ด"
                ),
            )
            self.root.after(
                0,
                lambda: self.close_btn.configure(
                    state="disabled", text="⛔ ปิดเซสชันทั้งหมด"
                ),
            )
            self.root.after(
                0, lambda: self.login_btn.configure(state="normal", text="ล็อกอิน")
            )
            for u in closed_users:
                self.root.after(
                    0, lambda u=u: self._remove_pending_stat_for_username(u)
                )
            # ปลดล็อกเฉพาะประเภทไอดีเมื่อปิด session แล้ว เพื่อให้เปลี่ยน
            # Game ID/GG Passport และทดสอบใหม่ได้ ส่วนแรงค์/หน่วยไม่ถูกแตะ
            closed_set = set(closed_users)

            def _unlock_closed_types():
                for row in getattr(self, "_rows", []):
                    try:
                        if row.user_var.get().strip() in closed_set:
                            row.set_type_locked(False)
                    except Exception:
                        pass

            self.root.after(0, _unlock_closed_types)
        except Exception as _e:
            _logger.debug("ignored error at sessions cleanup ui: %s", _e)

    def _do_close_all_sessions(self):
        n = 0
        closed_users = []
        try:
            with self._sessions_lock:
                sessions = list(self._sessions)
                self._sessions.clear()
                closed_users = [s.get("username", "") for s in sessions]
            n = len(sessions)
        except Exception as e:
            try:
                self.log(f"⚠ close_all: {e}")
            except Exception as _e:
                _logger.debug("ignored error at close_all read: %s", _e)
        finally:
            self._close_sessions_cleanup(closed_users, log_count=n)

    def _cookie_dir_has_files(self):
        try:
            return os.path.isdir(COOKIE_DIR) and any(
                f.endswith((".json", ".pkl")) for f in os.listdir(COOKIE_DIR)
            )
        except Exception:
            return False

    def _refresh_clear_cookie_btn(self):
        try:
            self.clear_cookie_btn.configure(
                state=("normal" if self._cookie_dir_has_files() else "disabled")
            )
        except Exception as _e:
            _logger.debug("ignored error at app_automation.py:2030: %s", _e)

    def clear_all_cookies(self):
        try:
            if not self._cookie_dir_has_files():
                self.log("🍪 ไม่มี cookie เก็บไว้ในเครื่อง")
                self._refresh_clear_cookie_btn()
                return
            files = [f for f in os.listdir(COOKIE_DIR) if f.endswith((".json", ".pkl"))]
            n = 0
            for fname in files:
                try:
                    os.remove(os.path.join(COOKIE_DIR, fname))
                    n += 1
                except Exception as _e:
                    _logger.debug("ignored error at app_automation.py:2099: %s", _e)
            self.log(f"🍪 ล้าง cookie แล้ว {n} ไฟล์ — รอบถัดไปจะล็อกอินใหม่ทุกบัญชี")
        except Exception as e:
            self.log(f"⚠️ ล้าง cookie ล้มเหลว: {e}")
        finally:
            self._refresh_clear_cookie_btn()
