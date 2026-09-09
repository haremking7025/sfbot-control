"""Run statistics: success/failure counters, per-account history, and
CSV export."""

import logging

from ..core.constants import FG3, STATUS_FAIL, STATUS_OK
from ..core.deps import csv, datetime, os, time, timedelta
from ..core.paths import DATA_DIR, HISTORY_FILE, RESULTS_DIR

_logger = logging.getLogger(__name__)

# ป้ายชื่อเหตุผลความล้มเหลวต่อไอดี — ใช้ใน _failed_summary_text และ _print_summary
_FAIL_TAG_LABEL = {
    "login_locked": "ถูกล็อก",
    "login": "ล็อกอินไม่ผ่าน",
    "login_other": "ผิดพลาด",
    "keyword": "คีย์ไม่ผ่าน",
    "keyword_other": "ผิดพลาด",
}

# ป้ายชื่อสถานะผลลัพธ์สำหรับไฟล์ CSV (sfkeyword_result_*.csv) และประวัติรายไอดี
# (account_history.csv) — ไฟล์ทั้งสองอ่านเพื่อโชว์คน ไม่ได้ใช้เป็นค่าในโค้ด เลย
# แปลงเป็นภาษาไทยให้เห็นชัด "เคยใช้ไปแล้ว" ต่างจาก "สำเร็จ" (เดิมเขียน status
# ดิบ success/already ภาษาอังกฤษ ผู้อ่านสับสน)
_STATUS_LABEL = {
    "success": "สำเร็จ",
    "failed": "ไม่สำเร็จ",
    "fail": "ไม่สำเร็จ",
    "already": "เคยใช้ไปแล้ว",
    "previewed": "พรีวิว",
}


class AppStatsMixin:
    def _set_account_status(self, username, status):
        """เก็บสถานะล่าสุดต่อบัญชีไว้สำหรับ UI/diagnostics โดยไม่ผูกกับผลรวม"""
        statuses = getattr(self, "_account_statuses", None)
        if statuses is None:
            statuses = self._account_statuses = {}
        statuses[username] = status
        for row in getattr(self, "_rows", []):
            try:
                if row.user_var.get().strip() == username:
                    row.status_var.set(status)
                    row.status_lbl.configure(fg=STATUS_OK if status.startswith("✅") else STATUS_FAIL if status.startswith("❌") else FG3)
                    break
            except Exception:
                pass

    def _record_success(self, username):
        with self._lock_stats:
            self._failed_ids = [(u, r) for u, r in self._failed_ids if u != username]
            self._failure_details.pop(username, None)
            if username not in self._success_ids:
                self._success_ids.append(username)
        self._append_account_history(username, "login", "success")
        self._request_stats_gui_update()

    def _record_already(self, username):
        """บันทึกไอดีที่ถูกข้ามเพราะเคยใช้คีย์นี้ไปแล้วในเซสชันนี้ (ทุกคีย์โดน
        ข้าม) — ไม่นับเป็นสำเร็จใหม่ ไม่นับเป็นล้มเหลว แยกหมวด "เคยใช้ไปแล้ว"
        ให้สรุป/popup บอกตรงๆ (ก่อนหน้านี้ข้ามแล้วนับเป็นสำเร็จ — หลอกผู้ใช้)"""
        with self._lock_stats:
            self._failed_ids = [(u, r) for u, r in self._failed_ids if u != username]
            self._failure_details.pop(username, None)
            if username not in self._already_ids:
                self._already_ids.append(username)
        self._append_account_history(username, "keyword", "already")
        self._request_stats_gui_update()

    def _record_failure(self, username, reason="keyword_other", detail=None):
        """บันทึกไอดีที่ล้มเหลว + สาเหตุจริง (detail) เพื่อให้ log สรุปตอนจบรอบรัน
        และ popup แจ้งเตือนบอกได้ว่าไอดีไหนล้มเหลวเพราะอะไร (ไม่ใช่แค่ป้ายสั้น)
        detail เก็บเฉพาะสาเหตุล่าสุดของไอดีนั้น ปลอดภัยภายใต้ _lock_stats"""
        with self._lock_stats:
            if username in self._success_ids and reason in ("keyword", "keyword_other"):
                self._success_ids.remove(username)
            self._failed_ids = [(u, r) for u, r in self._failed_ids if u != username]
            self._failed_ids.append((username, reason))
            if detail:
                self._failure_details[username] = str(detail)
            else:
                self._failure_details.pop(username, None)
        self._append_account_history(username, "login", "failed", reason)
        self._request_stats_gui_update()

    def _failure_detail(self, username, max_len=220):
        """คืนสาเหตุจริงที่บันทึกไว้ของไอดีนี้ (ถ้ามี) ตัดยาวเกินไว้ให้อ่านง่าย"""
        with self._lock_stats:
            detail = self._failure_details.get(username, "")
        if not detail:
            return ""
        detail = str(detail).strip()
        return detail[:max_len] + ("…" if len(detail) > max_len else "")

    # เหตุผลของความล้มเหลวที่ถือว่าเป็น "เข้าสู่ระบบไม่สำเร็จ" (ไม่นับซ้ำเป็น
    # "ทำรายการไม่สำเร็จ" ด้วย) — ส่วนที่เหลือทั้งหมดใน self._failed_ids ถือว่า
    # เป็นความล้มเหลวตอนทำรายการ (กรอกคีย์เวิร์ดไม่ผ่าน) เท่านั้น
    _LOGIN_FAIL_REASONS = ("login", "login_locked", "login_other")

    def _request_stats_gui_update(self):
        """ขออัปเดตการ์ดสถิติ — รวมคำขอจาก worker thread หลายๆ ตัวที่จบพร้อมกัน
        ให้เหลือหลัง(0) เพียงครั้งเดียว (ถ้ามีคำขอค้างอยู่แล้วก็ข้ามไป) กัน burst
        ของบัญชีหลายสิบตัวที่จบพร้อมกันยิง after(0) เข้า event loop ทีละตัว"""
        if getattr(self, "_stats_gui_pending", False):
            return
        self._stats_gui_pending = True
        try:
            self.root.after(0, self._stats_gui_update_apply)
        except Exception:
            self._stats_gui_pending = False
            self._update_stats_gui()

    def _stats_gui_update_apply(self):
        self._stats_gui_pending = False
        self._update_stats_gui()

    def _update_stats_gui(self):
        with self._lock_stats:
            ok = len(self._success_ids)
            login_fail = sum(
                1 for _, r in self._failed_ids if r in self._LOGIN_FAIL_REASONS
            )
            fail = len(self._failed_ids) - login_fail
            already = len(self._already_ids)
            # กำลังดำเนินการ = เป้าหมายทั้งหมดของรอบนี้ ลบด้วยไอดีที่จบสถานะแล้ว
            # (ไม่ว่าจะจบแบบสำเร็จ/เคยใช้ไปแล้ว/ล้มเหลวก็ตาม) กันค่าติดลบไว้เผื่อ
            # บางรอบที่ไม่ได้ตั้ง total ใหม่ (เช่น ล็อกอินซ้ำรายแถว)
            pending = max(0, self._stats_total - ok - fail - login_fail - already)
        self.stat_ok_label_r.configure(text=str(ok))
        self.stat_fail_label_r.configure(text=str(fail))
        self.stat_login_fail_label_r.configure(text=str(login_fail))
        self.stat_pending_label_r.configure(text=str(pending))

    def _set_stats_total(self, total):
        """เรียกตอนเริ่มรอบใหม่ (หลัง _reset_stats) เพื่อบอกว่ารอบนี้มีกี่ไอดีที่
        ต้องทำให้จบ — ใช้คำนวณตัวเลข 'กำลังดำเนินการ' ให้ตรงกับความเป็นจริง"""
        with self._lock_stats:
            self._stats_total = total
        self._update_stats_gui()

    def _remove_pending_stat_for_username(self, username):
        """เอาไอดีนี้ออกจากจำนวน 'ล็อกอินแล้ว รอกรอกคีย์เวิร์ด' (pending) เมื่อ
        session ของไอดีนี้ถูกปิดไปแล้ว — ไม่ต้องรอกรอกคีย์เวิร์ดต่ออีกแล้ว ลด
        _stats_total ลง 1 เฉพาะกรณีที่ไอดีนี้ยังไม่เคยถูกบันทึกผลสำเร็จ/ล้มเหลว
        มาก่อน (ถ้าบันทึกไปแล้วแปลว่าไม่ได้อยู่ในจำนวน pending อยู่แล้ว ไม่ต้องลด)"""
        try:
            with self._lock_stats:
                already_done = (
                    username in self._success_ids
                    or username in self._already_ids
                    or any(u == username for u, _ in self._failed_ids)
                )
                if not already_done and self._stats_total > 0:
                    self._stats_total -= 1
            self._update_stats_gui()
        except Exception as _e:
            _logger.debug("ignored error at app_stats.py:75: %s", _e)

    def _reset_stats(self):
        with self._lock_stats:
            self._success_ids.clear()
            self._already_ids.clear()
            self._failed_ids.clear()
            self._failure_details.clear()
            self._result_rows.clear()
            self._stats_total = 0
        self._update_stats_gui()

    def _record_result(self, user, keyword, status):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock_stats:
            self._result_rows.append((user, keyword, status, ts))
        self._append_account_history(user, "keyword", status)

    def _append_account_history(self, username, action, status, reason=""):
        """ประวัติสะสมที่ใช้วิเคราะห์ไอดีที่ล้มเหลวบ่อย; เก็บเฉพาะ metadata ปลอดภัย.

        เขียนภายใต้ _lock_stats (ตัวเรียกทั้ง 4 จุดเรียกนอกล็อกอยู่แล้ว) — ตอน
        50-200 ไอดีจบพร้อมกัน thread หลายตัวเขียนไฟล์ CSV เดียวกันพร้อมกัน ถ้า
        ไม่ล็อก แถวจะ interleave/ปนกันได้ และ _trim_account_history ที่อ่าน+
        เขียนไฟล์ทั้งไฟล์ใหม่ก็จะชนกับ append กลางคันได้ เสียประวัติไปเงียบๆ
        """
        try:
            with self._lock_stats:
                os.makedirs(DATA_DIR, exist_ok=True)
                new_file = not os.path.exists(HISTORY_FILE)
                with open(HISTORY_FILE, "a", encoding="utf-8-sig", newline="") as f:
                    writer = csv.writer(f)
                    if new_file:
                        writer.writerow(["timestamp", "user", "action", "status", "reason"])
                    writer.writerow(
                        [
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            username,
                            action,
                            _STATUS_LABEL.get(status, status),
                            reason,
                        ]
                    )
                self._maybe_trim_account_history()
        except Exception as exc:
            self.log(f"⚠ บันทึกประวัติรายไอดีไม่ได้: {type(exc).__name__}")

    _HISTORY_TRIM_INTERVAL_SEC = 300.0
    _HISTORY_TRIM_MIN_FILE_SIZE = 1_000_000  # bytes — ถ้าไฟล์ยังเล็ก ไม่ต้องรอครบ 5 นาทีก็ตัดได้

    def _maybe_trim_account_history(self):
        """ตัดประวัติเก่าเกิน 90 วัน — แต่จำกัดความถี่ไม่ให้อ่าน+เขียนไฟล์ทั้งไฟล์ใหม่
        ทุกครั้งที่บันทึก 1 บรรทัด (เดิม _append_account_history เรียก
        _trim_account_history ตรงๆ ทุกรอบ ทำให้ตอนมีบัญชีหลายสิบไอดีจบพร้อมกัน
        ต้องอ่าน/เขียนไฟล์ประวัติทั้งไฟล์ซ้ำเป็นสิบๆ รอบ — ทั้งที่ข้อมูลส่วนใหญ่
        ยังไม่เก่าและไม่ถูกตัดออกเลย เปลือง CPU/ดิสก์โดยใช่เหตุ)

        กติกา: ตัดจริงเมื่อผ่านไป >= 5 นาทีตั้งแต่รอบล่าสุด หรือไฟล์โตเกิน 1MB
        (กรณีหลังยอมตัดทันทีเพื่อกันไฟล์บวมเรื้อรัง) — ระหว่างนั้นก็ยัง append
        บรรทัดใหม่ตามปกติ แค่ข้ามขั้นตอนการกวาดล้างของเก่าไปก่อน"""
        try:
            now = time.monotonic()
            last = getattr(self, "_last_history_trim_ts", 0.0)
            if now - last < self._HISTORY_TRIM_INTERVAL_SEC:
                try:
                    big = os.path.getsize(HISTORY_FILE) > self._HISTORY_TRIM_MIN_FILE_SIZE
                except OSError:
                    big = False
                if not big:
                    return
            self._last_history_trim_ts = now
            self._trim_account_history()
        except Exception as _e:
            _logger.debug("ignored error at app_stats.py:maybe_trim: %s", _e)

    def _trim_account_history(self, days=90):
        """เก็บประวัติไว้ 90 วันเพื่อลดขนาดไฟล์ โดยไม่กระทบไฟล์ CSV ที่ส่งออกแล้ว."""
        try:
            cutoff = datetime.now() - timedelta(days=days)
            with open(HISTORY_FILE, "r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            kept = []
            for row in rows:
                try:
                    if (
                        datetime.strptime(row.get("timestamp", ""), "%Y-%m-%d %H:%M:%S")
                        >= cutoff
                    ):
                        kept.append(row)
                except ValueError:
                    kept.append(row)  # แถวที่อ่านวันเวลาไม่ได้ ไม่ลบทิ้งโดยคาดเดา
            if len(kept) == len(rows):
                return
            with open(HISTORY_FILE, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["timestamp", "user", "action", "status", "reason"]
                )
                writer.writeheader()
                writer.writerows(kept)
        except Exception as _e:
            _logger.debug("ignored error at app_stats.py:138: %s", _e)

    def _export_csv(self):
        with self._lock_stats:
            rows = list(self._result_rows)
        if not rows:
            return None
        try:
            fname = f"sfkeyword_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            os.makedirs(RESULTS_DIR, exist_ok=True)
            path = os.path.join(RESULTS_DIR, fname)
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["user", "keyword", "status", "timestamp"])
                writer.writerows(
                    [u, k, _STATUS_LABEL.get(s, s), t] for u, k, s, t in rows
                )
            return path
        except Exception as e:
            self.log(f"บันทึก CSV ล้มเหลว: {e}")
            return None

    def _stats_breakdown(self):
        """คืนค่า (สำเร็จ, ทำรายการไม่สำเร็จ, เข้าสู่ระบบไม่สำเร็จ, เคยใช้ไปแล้ว) —
        ใช้ร่วมกันทั้งการ์ดสถานะ, log สรุปผล, และ popup แจ้งเตือนเสร็จสิ้น กันไม่ให้
        แต่ละจุดนับไม่ตรงกันเหมือนที่เคยเกิดปัญหามาก่อน"""
        with self._lock_stats:
            ok_n = len(self._success_ids)
            login_fail_n = sum(
                1 for _, r in self._failed_ids if r in self._LOGIN_FAIL_REASONS
            )
            fail_n = len(self._failed_ids) - login_fail_n
            already_n = len(self._already_ids)
        return ok_n, fail_n, login_fail_n, already_n

    def _key_result_counts(self):
        """นับจำนวนคีย์ที่ส่งสำเร็จ / เคยใช้ไปแล้ว / previewed / ล้มเหลว จาก
        _result_rows — ใช้ใน popup แจ้งเตือนเสร็จสิ้น ให้บอกจำนวนคีย์ที่สำเร็จต่อ
        รอบ (ผู้ใช้ขอเพิ่ม) + แยกหมวด "เคยใช้ไปแล้ว" (คีย์ซ้ำที่ถูกข้าม)"""
        with self._lock_stats:
            rows = list(self._result_rows)
        ok = sum(1 for _, _, s, _ in rows if s == "success")
        already = sum(1 for _, _, s, _ in rows if s == "already")
        previewed = sum(1 for _, _, s, _ in rows if s == "previewed")
        fail = sum(1 for _, _, s, _ in rows if s == "fail")
        return ok, already, previewed, fail

    def _failed_summary_text(self, max_lines=10):
        """คืนข้อความสรุปรายไอดีที่ไม่สำเร็จ (✗ username — สาเหตุ) สำหรับโชว์ใน
        popup ตอนเสร็จสิ้น — เอาสาเหตุจริง (detail) มาแสดงต่อท้ายเหมือน log สรุป
        ถ้าเกิน max_lines ตัดเหลือด้วยข้อความ +N อีก"""
        with self._lock_stats:
            failed_ids = list(self._failed_ids)
        printed = set()
        lines = []
        for u, reason in failed_ids:
            if u in printed:
                continue
            printed.add(u)
            if len(lines) >= max_lines:
                lines.append(f"…และอีก {len(failed_ids) - len(printed) + 1} ไอดี")
                break
            tag = _FAIL_TAG_LABEL.get(reason, reason)
            detail = self._failure_detail(u)
            line = f"✗ {u}  {tag}" if not detail else f"✗ {u}  {tag} — {detail}"
            lines.append(line)
        if not lines:
            return ""
        return "\n".join(lines)

    def _print_summary(self):
        ok_n, fail_n, login_fail_n, already_n = self._stats_breakdown()
        with self._lock_stats:
            success_ids = list(self._success_ids)
            already_ids = list(self._already_ids)
            failed_ids = list(self._failed_ids)
        _sum = f"── สรุป  สำเร็จ={ok_n}  ไม่สำเร็จ={fail_n}  ล็อกอินไม่ผ่าน={login_fail_n}"
        if already_n:
            _sum += f"  เคยใช้ไปแล้ว={already_n}"
        self.log(_sum)
        for u in success_ids:
            self.log(f"  ✓ {u}")
        for u in already_ids:
            self.log(f"  ⏭ {u}  เคยใช้คีย์นี้ไปแล้ว")
        printed = set()
        for u, reason in failed_ids:
            if u in printed:
                continue
            printed.add(u)
            tag = _FAIL_TAG_LABEL.get(reason, reason)
            detail = self._failure_detail(u)
            if detail:
                self.log(f"  ✗ {u}  {tag} — {detail}")
            else:
                self.log(f"  ✗ {u}  {tag}")
        csv_path = self._export_csv()
        if csv_path:
            self.log(f"   csv: {os.path.basename(csv_path)}")
