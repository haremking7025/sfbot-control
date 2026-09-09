"""Start/stop button support — main run-flow half: start_login,
start_keyword, and start_auto_run — the actual
batch/thread-spawning automation entry points triggered by the UI buttons."""

import logging

from ..core.constants import RANK_MAP, UNIT_MAP
from ..core.deps import threading

_logger = logging.getLogger(__name__)


class AppRunControlFlowsMixin:
    def start_login(self):
        if self._is_busy():
            self._alert_warning("กำลังทำงาน", "โปรแกรมกำลังล็อกอินหรือกรอกคีย์เวิร์ดอยู่")
            return

        accounts, _ = self._collect_valid_accounts()
        if not accounts:
            self._alert_warning("แจ้งเตือน", "กรุณาใส่บัญชีอย่างน้อย 1 ไอดี!")
            return

        if not self._validate_unique_login_accounts(accounts):
            return

        try:
            ver = float(self.version_entry.get().strip())
        except Exception:
            ver = 2.0
        if not self._use_resume():
            self._completed_pairs_reset()

        self.login_btn.configure(state="disabled", text="กำลังล็อกอิน...")
        self.keyword_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        self._reset_stats()
        self._set_stats_total(len(accounts))
        self._stop_event.clear()

        with self._sessions_lock:
            self._sessions.clear()
            self._logged_in_users.clear()

        self._is_running = True
        self._start_timer(len(accounts))

        self.log(f"── เข้าสู่ระบบ  {len(accounts)} บัญชี")

        # อ่าน 'พร้อมกัน' บน UI thread (tkinter var ปลอดภัยแค่ main thread)
        # แล้วส่งเข้าคลอเชอร์ worker เป็นค่าธรรมดา — worker ห้ามแตะ tk var
        login_slots = self._get_max_concurrent(len(accounts))

        def run_logins():
            n = 0
            try:
                self._start_deadlock_watchdog(timeout_sec=360)
                sem = threading.Semaphore(login_slots)
                self.log(f"   พร้อมกัน {len(accounts)} บัญชี")

                _cookie_used = [0]
                _normal_login = [0]
                _counter_lock = threading.Lock()

                def do_login(user, pwd, ltype, rank):
                    if self._stop_event.is_set():
                        return
                    with sem:
                        self.login_only(user, pwd, ver, ltype, rank, silent_cookie=True)
                    with self._sessions_lock:
                        session_exists = any(
                            s["username"] == user for s in self._sessions
                        )
                        used_cookie = self._cookie_login_result.get(user, False)
                    with _counter_lock:
                        if session_exists:
                            if used_cookie:
                                _cookie_used[0] += 1
                            else:
                                _normal_login[0] += 1

                self._run_login_threads(accounts, do_login, login_slots, "ล็อกอิน")

                total_str = self._stop_elapsed_timer()
                with self._sessions_lock:
                    n = len(self._sessions)
                self.log(f"── เข้าสู่ระบบสำเร็จ  {n}/{len(accounts)} บัญชี  |  ใช้คุกกี้เดิม {_cookie_used[0]}  |  ล็อกอินใหม่ {_normal_login[0]}  |  {total_str}")

                with self._lock_stats:
                    failed_logins = list(self._failed_ids)
                if failed_logins:
                    for u, reason in failed_logins:
                        tag = {"login_locked": "ถูกล็อก", "login": "ไม่สำเร็จ", "login_other": "ผิดพลาด"}.get(reason, reason)
                        self.log(f"✗ {u}  --  {tag}")
                if n == 0:
                    self.root.after(
                        0,
                        lambda: self._alert_warning("แจ้งเตือน", "ไม่มีไอดีที่ล็อกอินสำเร็จเลย"),
                    )
            except Exception as e:
                self.log(f"✗ ผิดพลาดร้ายแรง (ล็อกอิน): {e}")
                self._stop_elapsed_timer()
            finally:
                self._stop_deadlock_watchdog()
                self._is_running = False
                with self._sessions_lock:
                    n_final = len(self._sessions)
                self.root.after(
                    0, lambda: self.stop_btn.configure(state="disabled", text="หยุด")
                )
                if n_final > 0:
                    self.root.after(
                        0,
                        lambda: self.login_btn.configure(
                            state="disabled", text="ล็อกอินแล้ว"
                        ),
                    )
                else:
                    self.root.after(
                        0,
                        lambda: self.login_btn.configure(state="normal", text="ล็อกอิน"),
                    )
                if n_final > 0:
                    self.root.after(
                        0,
                        lambda: self.stat_pending_title_r.configure(
                            text="⏳  ล็อกอินแล้ว รอกรอกคีย์เวิร์ด"
                        ),
                    )
                if n_final > 0:
                    self.root.after(
                        0, lambda: self.keyword_btn.configure(state="normal")
                    )
                    self.root.after(0, lambda: self.close_btn.configure(state="normal"))
                    self.root.after(0, self._refresh_clear_cookie_btn)

        self._worker_manager.submit(run_logins, label="app_run_control.run_logins")

    def start_keyword(self):
        """กรอกคีย์เวิร์ดทั้งหมดในลิสต์กับบัญชีที่ล็อกอินไว้แล้ว — ปุ่ม
        '➤ กรอกคีย์เวิร์ด' อ่านคีย์เวิร์ดจากแถวคีย์เวิร์ด แล้วส่งให้ทุกบัญชี
        ที่ล็อกอินอยู่"""
        if self._is_busy():
            self._alert_warning("กำลังทำงาน", "โปรแกรมกำลังล็อกอินหรือกรอกคีย์เวิร์ดอยู่")
            return
        try:
            self.stat_pending_title_r.configure(text="⏳  กำลังดำเนินการ")
        except Exception as _e:
            _logger.debug("ignored error at app_run_control.py:640: %s", _e)
        codes = [r.get_data() for r in self._keyword_rows if r.get_data()]
        if not codes:
            self._alert_warning("แจ้งเตือน", "กรุณาใส่คีย์เวิร์ดอย่างน้อย 1 อัน!")
            return

        dupes = [c for c in set(codes) if codes.count(c) > 1]
        if dupes:
            ans = self._ask_dialog(
                "พบคีย์เวิร์ดซ้ำ", f"พบคีย์เวิร์ดซ้ำ: {', '.join(set(dupes))}\nรันต่อหรือไม่?"
            )
            if not ans:
                return

        with self._sessions_lock:
            sessions = list(self._sessions)
        if not sessions:
            self._alert_warning("แจ้งเตือน", "ยังไม่มีไอดีที่ล็อกอินสำเร็จ กรุณากด 'ล็อกอิน' ก่อน")
            return
        code_delay = self._fixed_delay

        notify = self.notify_var.get()
        total = len(sessions) * len(codes)

        self._reset_stats()
        self._set_stats_total(len(sessions))
        self._stop_event.clear()
        self._is_running = True
        self._start_timer(total)
        for row in self._rows:
            try:
                row.set_selection_locked(True)
            except Exception:
                pass
        self.keyword_btn.configure(state="disabled", text="กำลังกรอกคีย์เวิร์ด...")
        self.stop_btn.configure(state="normal")
        self.log(f"── กรอกคีย์  {len(sessions)} บัญชี × {len(codes)} คีย์")

        live_rank_map = {}
        live_unit_map = {}
        live_unit2_map = {}
        for row in self._rows:
            data = row.get_data()
            if data:
                u = data[0]
                live_rank_map[u] = RANK_MAP.get(row.rank_var.get(), "rank1")
                live_unit_map[u] = UNIT_MAP.get(row.unit_var.get(), "skip")
                live_unit2_map[u] = UNIT_MAP.get(row.unit2_var.get(), "skip")

        def run_keywords():
            try:
                self._start_deadlock_watchdog(timeout_sec=360)
                threads = []
                for s in sessions:
                    if self._stop_event.is_set():
                        break
                    rank = live_rank_map.get(s["username"], s.get("rank", "rank1"))
                    unit = live_unit_map.get(s["username"], s.get("unit", "skip"))
                    unit2 = live_unit2_map.get(s["username"], s.get("unit2", "skip"))
                    self.root.after(0, lambda u=s["username"]: self._set_account_status(u, "⏳ กำลังส่ง"))
                    t = self._worker_manager.spawn_tracked(
                        self.run_session_multi,
                        args=(s, codes, rank, code_delay, unit, unit2),
                        label="keyword_flow.run_session_multi",
                    )
                    threads.append(t)
                    t.start()
                kw_join_timeout = max(60, len(codes) * 20 + 60)
                self._join_threads_bounded(
                    threads, per_thread_timeout=kw_join_timeout, label="กรอกคีย์เวิร์ด"
                )

                total_str = self._stop_elapsed_timer()
                self._print_summary()
                self.log(f"── TOTAL  {total_str}")
                stopped = self._stop_event.is_set()
                if notify and not stopped:
                    ok_n, fail_n, login_fail_n, already_n = self._stats_breakdown()
                    k_ok, k_already, _k_pv, k_fail = self._key_result_counts()
                    _ = (k_ok, k_already, _k_pv, k_fail)
                    icon = (
                        "✅"
                        if fail_n == 0 and login_fail_n == 0 and not (already_n and not ok_n)
                        else "⚠️"
                    )
                    failed_txt = self._failed_summary_text(max_lines=10)
                    self.root.after(
                        0,
                        lambda t=total_str, i=icon, o=ok_n, f=fail_n, lf=login_fail_n, \
                                a=already_n, ft=failed_txt: (
                            self._notify_popup(
                                "เสร็จสิ้น!",
                                f"{i} กรอกคีย์เวิร์ดเสร็จแล้ว!\n"
                                f"สำเร็จ {o}"
                                + (f" · เคยใช้ไปแล้ว {a}" if a else "")
                                + (f" · ไม่สำเร็จ {f}" if f else "")
                                + (f" · ล็อกอินไม่ผ่าน {lf}" if lf else "")
                                + f"\n⏱ เวลารวม: {t}"
                                + (f"\n\n{ft}" if ft else ""),
                            )
                        ),
                    )
            except Exception as e:
                self.log(f"✗ ผิดพลาดร้ายแรง (คีย์เวิร์ด): {e}")
                self._stop_elapsed_timer()
            finally:
                self._stop_deadlock_watchdog()
                self._is_running = False
                self.root.after(0, lambda: [r.set_selection_locked(False) for r in self._rows])
                self.root.after(
                    0,
                    lambda: self.keyword_btn.configure(
                        state="normal", text="กรอกคีย์เวิร์ด"
                    ),
                )
                self.root.after(
                    0, lambda: self.stop_btn.configure(state="disabled", text="หยุด")
                )

        self._worker_manager.submit(run_keywords, label="app_run_control.run_keywords")

    def start_auto_run(self):
        """รันอัตโนมัติ (ล็อกอิน + กรอกคีย์เวิร์ด) กับบัญชีในตาราง — ปุ่ม
        '▶ เริ่มรันอัตโนมัติ' อ่านบัญชีและคีย์ทั้งหมดจากตาราง/แถวคีย์เวิร์ด"""
        if self._is_busy():
            self._alert_warning("กำลังทำงาน", "โปรแกรมกำลังล็อกอินหรือกรอกคีย์เวิร์ดอยู่")
            return

        accounts, _ = self._collect_valid_accounts()
        if not accounts:
            self._alert_warning("แจ้งเตือน", "กรุณาใส่บัญชีอย่างน้อย 1 ไอดี!")
            return

        codes = [r.get_data() for r in self._keyword_rows if r.get_data()]
        if not codes:
            self._alert_warning("แจ้งเตือน", "กรุณาใส่คีย์เวิร์ดอย่างน้อย 1 อัน!")
            return

        if not self._validate_unique_login_accounts(accounts):
            return
        dupe_codes = [c for c in set(codes) if codes.count(c) > 1]
        if dupe_codes:
            if not self._ask_dialog(
                "พบคีย์เวิร์ดซ้ำ", f"พบคีย์เวิร์ดซ้ำ: {', '.join(set(dupe_codes))}\nรันต่อหรือไม่?"
            ):
                return

        try:
            ver = float(self.version_entry.get().strip())
        except Exception:
            ver = 2.0
        notify = self.notify_var.get()
        code_delay = self._fixed_delay
        if not self._use_resume():
            self._completed_pairs_reset()

        kw_tasks = len(accounts) * len(codes)
        total_tasks = len(accounts) + kw_tasks

        self.auto_run_btn.configure(state="disabled", text="กำลังรัน...")
        self.auto_stop_btn.configure(state="normal")
        self.login_btn.configure(state="disabled")
        self.keyword_btn.configure(state="disabled")
        # ปิดปุ่ม ⛔ ปิดเซสชันระหว่างรันอัตโนมัติ — ถ้าเปิดค้างจากรอบก่อน (มี session)
        # แล้วกดตอนกลางรันจะเคลียร์ session ที่ worker กำลังใช้อยู่กลางคัน
        self.close_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self._set_auto_status("⏳ กำลังล็อกอิน...")

        self._reset_stats()
        self._set_stats_total(len(accounts))
        self._stop_event.clear()
        with self._sessions_lock:
            self._sessions.clear()
            self._logged_in_users.clear()

        self._is_running = True
        self._start_timer(total_tasks)
        for row in self._rows:
            try:
                row.set_selection_locked(True)
            except Exception:
                pass

        self.log(f"━━ เริ่มรัน  {len(accounts)} บัญชี × {len(codes)} คีย์")

        live_rank_map = {}
        live_unit_map = {}
        live_unit2_map = {}
        for row in self._rows:
            data = row.get_data()
            if data:
                live_rank_map[data[0]] = RANK_MAP.get(row.rank_var.get(), "rank1")
                live_unit_map[data[0]] = UNIT_MAP.get(row.unit_var.get(), "skip")
                live_unit2_map[data[0]] = UNIT_MAP.get(row.unit2_var.get(), "skip")

        def _reset_ui():
            self.auto_run_btn.configure(state="normal", text="▶  เริ่มรันอัตโนมัติ")
            self.auto_stop_btn.configure(state="disabled")
            self.login_btn.configure(state="normal")
            self.keyword_btn.configure(state="disabled")
            self.stop_btn.configure(state="disabled", text="หยุด")

        # อ่าน 'พร้อมกัน' บน UI thread ก่อน submit — worker ห้ามแตะ tk var
        login_slots = self._get_max_concurrent(len(accounts))

        def run_auto():
            try:
                self._start_deadlock_watchdog(timeout_sec=360)
                sem = threading.Semaphore(login_slots)

                self.log("   โหมดแข่ง: ใครล็อกอินเสร็จก่อน กรอกคีย์ก่อนทันที")

                def do_account(user, pwd, ltype, rank, unit, unit2):
                    if self._stop_event.is_set():
                        return
                    with sem:
                        if self._stop_event.is_set():
                            return
                        session = self.login_only(user, pwd, ver, ltype, rank, silent_cookie=True)
                    if session is None or self._stop_event.is_set():
                        return
                    live_rank = live_rank_map.get(user, rank)
                    live_unit = live_unit_map.get(user, unit)
                    live_unit2 = live_unit2_map.get(user, unit2)
                    self.run_session_multi(
                        session, codes, live_rank, code_delay, live_unit, live_unit2
                    )
                    if not self._stop_event.is_set():
                        with self._sessions_lock:
                            self._sessions = [
                                s for s in self._sessions if s.get("username") != user
                            ]
                        self.root.after(0, self._refresh_clear_cookie_btn)

                account_threads = []
                for user, pwd, ltype, rank, unit, unit2 in accounts:
                    if self._stop_event.is_set():
                        break
                    t = self._worker_manager.spawn_tracked(
                        do_account,
                        args=(user, pwd, ltype, rank, unit, unit2),
                        label="autoitem_flow.do_account",
                    )
                    account_threads.append(t)
                    t.start()

                run_join_timeout = max(120, login_slots * 90 + len(codes) * 20 + 60)
                self._join_threads_bounded(
                    account_threads,
                    per_thread_timeout=run_join_timeout,
                    label="รันอัตโนมัติ (ล็อกอิน+กรอกคีย์เวิร์ด)",
                )

                if self._stop_event.is_set():
                    self._stop_elapsed_timer()
                    self.log("⏹ หยุดทำงาน")
                    self.root.after(0, _reset_ui)
                    self.root.after(0, lambda: self._set_auto_status("⏹ หยุดแล้ว"))
                    return

                with self._sessions_lock:
                    n_login = len(self._logged_in_users)

                self.log(f"── ล็อกอินสำเร็จ  {n_login}/{len(accounts)} บัญชี")

                if n_login == 0:
                    self._stop_elapsed_timer()
                    self.root.after(0, _reset_ui)
                    self.root.after(
                        0, lambda: self._set_auto_status("❌ ไม่มีไอดีที่ล็อกอินสำเร็จ")
                    )
                    self.root.after(
                        0,
                        lambda: self._alert_warning("แจ้งเตือน", "ไม่มีไอดีที่ล็อกอินสำเร็จเลย"),
                    )
                    return

                # ✅ ปิดเซสชันทั้งหมดหลังรอบอัตโนมัติจบ: log + ปลดล็อกประเภทไอดี
                # + ล้างสถิติ pending + รีเซ็ตปุ่ม (เหมือนกด ⛔ ปิดเซสชันทั้งหมด)
                # ก่อนหน้านี้ทิ้ง session ค้างไว้ ไม่ได้ปิดให้จริง
                with self._sessions_lock:
                    closed_users = sorted(self._logged_in_users)
                    self._logged_in_users.clear()
                    self._sessions.clear()
                if closed_users:
                    self.root.after(
                        0, lambda: self._set_auto_status("🔒 ปิดเซสชัน...")
                    )
                self._close_sessions_cleanup(
                    closed_users, log_count=len(closed_users)
                )

                total_str = self._stop_elapsed_timer()
                self._print_summary()
                self.log(f"── TOTAL  {total_str}")

                self.root.after(0, _reset_ui)
                self.root.after(
                    0, lambda: self._set_auto_status(f"✅ เสร็จสิ้น! ใช้เวลา {total_str}")
                )
                if notify:
                    ok_n, fail_n, login_fail_n, already_n = self._stats_breakdown()
                    k_ok, k_already, _k_pv, k_fail = self._key_result_counts()
                    _ = (k_ok, k_already, _k_pv, k_fail)
                    icon = (
                        "✅"
                        if fail_n == 0 and login_fail_n == 0 and not (already_n and not ok_n)
                        else "⚠️"
                    )
                    failed_txt = self._failed_summary_text(max_lines=10)
                    self.root.after(
                        0,
                        lambda t=total_str, i=icon, o=ok_n, f=fail_n, lf=login_fail_n, \
                                a=already_n, ft=failed_txt: (
                            self._notify_popup(
                                "เสร็จสิ้น!",
                                f"{i} รันอัตโนมัติเสร็จแล้ว!\n"
                                f"สำเร็จ {o}"
                                + (f" · เคยใช้ไปแล้ว {a}" if a else "")
                                + (f" · ไม่สำเร็จ {f}" if f else "")
                                + (f" · ล็อกอินไม่ผ่าน {lf}" if lf else "")
                                + f"\n⏱ เวลารวม: {t}"
                                + (f"\n\n{ft}" if ft else ""),
                            )
                        ),
                    )
            except Exception as e:
                self.log(f"✗ ผิดพลาดร้ายแรง (รันอัตโนมัติ): {e}")
                self._stop_elapsed_timer()
                with self._sessions_lock:
                    closed_users = sorted(self._logged_in_users)
                    self._logged_in_users.clear()
                    self._sessions.clear()
                if closed_users:
                    self._close_sessions_cleanup(
                        closed_users, log_count=len(closed_users)
                    )
                self.root.after(0, _reset_ui)
                self.root.after(
                    0, lambda: self._set_auto_status("❌ หยุดกะทันหันเพราะข้อผิดพลาด")
                )
            finally:
                self._stop_deadlock_watchdog()
                self._is_running = False
                self.root.after(0, lambda: [r.set_selection_locked(False) for r in self._rows])

        self._worker_manager.submit(run_auto, label="app_run_control.run_auto")
