"""The 'ฝาก/เบิก' tab (TDP Inventory) — engine half: runs deposit or
withdraw over the tab's own account list, reusing the normal HTTP login/session
(do_login) — the only difference from the keyword flow is the target page
(http://member.sf.in.th/Inventory/) which shares the same session cookie.

UI half lives in app_inventory_tab.py (widgets + row CRUD). Still mixins over
the shared App state, same as AppAutoitemEngineMixin.
"""

import logging
import threading
import time

from ..core.constants import STATUS_FAIL, STATUS_OK, TYPE_MAP
from ..core.exceptions import LoginLockedError, SessionExpiredError
from ..core.http_flow import clear_cookies_http
from ..core.inventory_flow import (
    fetch_all_items,
    item_can_deposit,
    item_can_withdraw,
    item_display_name,
    item_operation,
    open_inventory,
)

_logger = logging.getLogger(__name__)

# verb ไทย + ไอคอนของแต่ละโหมด
_MODE_META = {
    "DEPOSIT": ("ฝาก", "📥"),
    "WITHDRAW": ("เบิก", "📤"),
}

# สถานะจบต่อบัญชี (ใช้รวมผล popup/log)
_ST_OK = "ok"            # ทำครบทุกชิ้น (หรือไม่มีอะไรให้ทำ = none แยกต่างหาก)
_ST_PART = "part"        # มีบางรายการไม่สำเร็จ
_ST_LOGIN = "login"      # ล็อกอินไม่สำเร็จ
_ST_NONE = "none"        # ล็อกอินผ่าน แต่ไม่มีไอเทมให้ฝาก/เบิก


def _err_short(exc, limit=2000):
    text = str(exc) or exc.__class__.__name__
    if len(text) > limit:
        text = text[:limit] + "…"
    return text


class AppInventoryEngineMixin:
    # ------------------------------------------------------------------
    # entry points (เรียกจากปุ่ม 📥 ฝากทั้งหมด / 📤 เบิกทั้งหมด)
    # ------------------------------------------------------------------
    def _inv_deposit_all(self):
        self._inv_run("DEPOSIT")

    def _inv_withdraw_all(self):
        self._inv_run("WITHDRAW")

    def _inv_run(self, mode):
        """เริ่มรอบฝาก/เบิกทั้งหมด (ทุกไอเทมที่กดได้ของทุกบัญชี)"""
        if getattr(self, "_inv_busy", False):
            return
        if getattr(self, "_inv_picker_active", False):
            self._alert_warning(
                "ปิดหน้าต่างดู/เลือกไอเทมก่อน",
                "ปิดหน้าต่าง '👁 ดู/เลือกไอเทม' ให้เรียบร้อยก่อนกดฝาก/เบิกทั้งหมด",
            )
            return
        accs = self._inv_valid_accounts()
        if not accs:
            self._alert_warning(
                "ไม่มีบัญชี",
                "กรุณาเพิ่มบัญชี (แท็บฝาก/เบิก) ก่อนกดฝาก/เบิก",
            )
            return

        verb, _icon = _MODE_META[mode]

        usernames = [r["user"].get().strip() for r in accs]
        dupes = [u for u in set(usernames) if usernames.count(u) > 1]
        if dupes:
            self._alert_warning(
                "พบบัญชีซ้ำ",
                "ไม่เริ่มล็อกอินซ้อนเพื่อป้องกัน session ชนกันหรือบัญชีถูกล็อก\n"
                f"กรุณาลบหรือแก้ไขไอดีที่ซ้ำ: {', '.join(sorted(set(dupes)))}",
            )
            return

        stop = threading.Event()
        self._inv_stop_evt = stop
        self._inv_busy = True
        self._inv_set_busy(True, verb=verb)
        # อ่านค่าแถว (StringVar) บน UI thread ก่อน submit — worker thread
        # อ่าน tkinter var ไม่ได้ (RuntimeError: main thread is not in main loop)
        acc_tuples = [
            (r["user"].get().strip(), r["pwd"].get().strip(), r["type"].get().strip())
            for r in accs
        ]

        def _reset_rows():
            for r in self._inv_rows:
                try:
                    r["status_lbl"].configure(text="⏳ กำลังทำงาน...", fg="#F5C542")
                except Exception:
                    pass

        self.root.after(0, _reset_rows)
        self.root.after(
            0,
            lambda: self.log(
                f"{_icon} {verb}ไอเทมทั้งหมด — {len(acc_tuples)} บัญชี "
                f"พร้อมกัน {self._inv_max_concurrent(len(acc_tuples))}"
            ),
        )

        self._worker_manager.submit(
            self._inv_run_worker,
            accs=acc_tuples,
            mode=mode,
            stop=stop,
            label="app_inventory.run",
        )

    def _inv_deposit_chosen(self, chosen):
        self._inv_run_chosen_from_dialog("DEPOSIT", chosen)

    def _inv_withdraw_chosen(self, chosen):
        self._inv_run_chosen_from_dialog("WITHDRAW", chosen)

    def _inv_run_chosen_from_dialog(self, mode, chosen):
        """รันฝาก/เบิกเฉพาะรายการที่เลือก จากหน้าต่าง 'ดู/เลือกไอเทม'

        chosen: list ของ dict {user, pwd, type, items:[(serial, ชื่อ), ...]}
        (รองรับได้หลายบัญชี ถ้าหน้าต่างส่งมาหลายชุด)
        """
        if getattr(self, "_inv_busy", False):
            return
        if getattr(self, "_inv_picker_active", False):
            return  # หน้าต่างยังไม่ปิด — ป้องกัน submit ซ้อน
        chosen = [c for c in chosen if c.get("items")]
        if not chosen:
            return
        verb, _icon = _MODE_META[mode]
        # บัญชีที่หน้าต่างส่งมา อาจไม่อยู่ในแถว (ไม่ได้เพิ่มลงแท็บ) — ต้องรันโดยตรง
        # ไม่พึ่ง _inv_valid_accounts()
        chosen_map = {c["user"]: list(c["items"]) for c in chosen}
        stop = threading.Event()
        self._inv_stop_evt = stop
        self._inv_busy = True
        self._inv_set_busy(True, verb=verb)

        acc_tuples = [
            (c["user"], c["pwd"], c.get("type", "Game ID")) for c in chosen
        ]

        def _reset_rows():
            for r in self._inv_rows:
                try:
                    r["status_lbl"].configure(text="⏳ กำลังทำงาน...", fg="#F5C542")
                except Exception:
                    pass

        self.root.after(0, _reset_rows)
        n_chosen = sum(len(v) for v in chosen_map.values())
        self.root.after(
            0,
            lambda: self.log(
                f"{_icon} {verb}ไอเทมที่เลือก — {len(acc_tuples)} บัญชี "
                f"({n_chosen} ชิ้น) พร้อมกัน {self._inv_max_concurrent(len(acc_tuples))}"
            ),
        )

        self._worker_manager.submit(
            self._inv_run_worker,
            accs=acc_tuples,
            mode=mode,
            stop=stop,
            chosen_map=chosen_map,
            label="app_inventory.run_selected",
        )

    def _inv_fetch_preview(self, username, password, login_type_label):
        """ล็อกอิน + เปิดหน้า Inventory + ดึงไอเทมทั้งหมด (ไม่ฝาก/เบิก) — ใช้เปิด
        หน้าต่าง 'ดู/เลือกไอเทม' แบบ preview

        คืน items: list ของ dict ไอเทม (เรียงตามเว็บ)
        raises LoginLockedError / SessionExpiredError / Exception"""
        _sess, _page_url, items = self._inv_open_and_fetch(
            username, password, login_type_label
        )
        return items

    def _inv_max_concurrent(self, n_accounts):
        """จำนวนล็อกอินพร้อมกันของแท็บนี้ (แยกจากแดชบอร์ด/แท็บรับไอเทมฟรี)"""
        try:
            value = int(self._inv_concurrency_var.get())
        except Exception:
            value = n_accounts
        return max(1, min(n_accounts, value))

    def _inv_run_worker(self, accs, mode, stop, chosen_map=None):
        """accs = list ของ (username, password, type_label) — อ่านค่าจาก UI ไว้ก่อนแล้ว

        chosen_map = dict {username: [(ItemSerial, ชื่อ), ...]} — ถ้ามี ให้ทำเฉพาะ
        รายการที่เลือก (จากหน้าต่าง 'ดู/เลือกไอเทม') ของบัญชีนั้น ไม่ใช่ทุกตัว"""
        verb, _icon = _MODE_META[mode]
        t_start = time.time()
        sem = threading.Semaphore(self._inv_max_concurrent(len(accs)))
        results = []
        results_lock = threading.Lock()
        threads = []

        def _worker(uname, pwd, ltype_label):
            if stop.is_set():
                return
            with sem:
                if stop.is_set():
                    return
                chosen = (chosen_map or {}).get(uname)
                res = self._inv_account_round(
                    uname, pwd, ltype_label, mode, stop, chosen=chosen
                )
            if res is not None:
                with results_lock:
                    results.append(res)

        for uname, pwd, ltype_label in accs:
            if stop.is_set():
                break
            t = self._worker_manager.spawn_tracked(
                _worker,
                args=(uname, pwd, ltype_label),
                label="app_inventory.worker",
            )
            threads.append(t)
            t.start()

        JOIN_TIMEOUT_PER_ACC = 180
        for t in threads:
            t.join(timeout=JOIN_TIMEOUT_PER_ACC)
            if t.is_alive():
                self.root.after(
                    0,
                    lambda: self.log(
                        "⚠ [ฝาก/เบิก] มีบัญชีทำงานค้างเกิน "
                        f"{JOIN_TIMEOUT_PER_ACC} วิ — ข้ามไปทำรายการถัดไป"
                    ),
                )

        self.root.after(0, self._inv_summary, results, mode, t_start)
        self.root.after(0, lambda: self._inv_set_busy(False, verb=verb))

    # ------------------------------------------------------------------
    # per-account round
    # ------------------------------------------------------------------
    def _inv_set_row_status(self, username, text, fg="#888"):
        """อัปเดตคอลัมน์สถานะของแถวในแท็บฝาก/เบิก (ต้องเรียกบน UI thread)"""
        for r in getattr(self, "_inv_rows", []):
            try:
                if r["user"].get().strip() == username:
                    r["status_lbl"].configure(text=text, fg=fg)
                    break
            except Exception:
                pass

    def _inv_log(self, msg):
        try:
            self.root.after(0, lambda m=msg: self.log(m))
        except Exception:
            pass

    def _inv_open_and_fetch(self, username, password, login_type_label):
        """ล็อกอิน (เหมือนรอบรับคีย์) + เปิดหน้า Inventory + ดึงไอเทมทั้งหมด

        คืน (sess, page_url, items)
        session ตายจริงระหว่างทาง → ล้าง cookie + ล็อกอินใหม่ให้ 1 ครั้ง
        raises LoginLockedError / SessionExpiredError / Exception"""
        ltype = TYPE_MAP.get(login_type_label, "gameid")
        t_login = time.time()
        self.do_login(None, None, username, password, login_type=ltype)
        sess = self._get_http_session(username)
        if sess is None:
            raise Exception("ล็อกอินไม่สำเร็จ (ไม่มี session)")
        self._inv_log(
            f"   ✔ [{username}] ล็อกอินสำเร็จ {time.time()-t_login:.1f}วิ — "
            "เปิดหน้า Inventory..."
        )
        for attempt in range(2):
            try:
                page_url = open_inventory(sess, username=username)
                items = fetch_all_items(
                    sess,
                    page_url,
                    username=username,
                    log_fn=lambda m: self._inv_log(m),
                )
                return sess, page_url, items
            except SessionExpiredError:
                if attempt == 0:
                    self._inv_log(
                        f"   ⚠ [{username}] session หมดอายุจริง — "
                        "ล้าง cookie แล้วล็อกอินใหม่..."
                    )
                    clear_cookies_http(username)
                    self._inv_log(f"   🔄 [{username}] ล็อกอินใหม่...")
                    t_login = time.time()
                    self.do_login(None, None, username, password, login_type=ltype)
                    sess = self._get_http_session(username)
                    if sess is None:
                        raise Exception("ล็อกอินใหม่ไม่สำเร็จ (ไม่มี session)")
                    self._inv_log(
                        f"   ✔ [{username}] ล็อกอินใหม่สำเร็จ "
                        f"{time.time()-t_login:.1f}วิ"
                    )
                    continue
                raise
        raise Exception("เรียกหน้า Inventory ไม่สำเร็จ")

    def _inv_account_round(self, username, password, login_type_label, mode, stop,
                           chosen=None):
        """ฝาก/เบิกของ 1 บัญชี (รันใน worker)

        chosen: list ของ (ItemSerial, ชื่อไอเทม) ที่ผู้ใช้เลือกจากหน้าต่าง
        'ดู/เลือกไอเทม' — ถ้าเป็น None ให้ทำทุกตัวที่กดได้ (โหมดฝาก/เบิกทั้งหมด)
        """
        verb, _icon = _MODE_META[mode]
        self.root.after(
            0,
            lambda u=username: self._inv_set_row_status(
                u, f"⏳ กำลัง{verb}...", fg="#F5C542"
            ),
        )

        def _fail_login(msg):
            return {
                "u": username, "state": _ST_LOGIN, "msg": msg,
                "attempted": 0, "done": 0, "item_fail": [],
            }

        try:
            _sess, _page_url, items = self._inv_open_and_fetch(
                username, password, login_type_label
            )
        except LoginLockedError as e:
            self._inv_log(f"   🔒 [{username}] {e}")
            return _fail_login("บัญชีถูกล็อก 15 นาที")
        except SessionExpiredError as e:
            self._inv_log(f"   ❌ [{username}] {_err_short(e)}")
            return _fail_login(_err_short(e))
        except Exception as e:
            err = _err_short(e)
            self._inv_log(f"   ❌ [{username}] {err}")
            return _fail_login(err)

        # ── คัดรายการเป้าหมาย ──
        # ปกติ (chosen=None): ฝากได้ = ถาวร+ยังไม่หมดอายุ+ยังอยู่ที่ตัว, เบิกได้ =
        # ฝากไว้+ไม่หมดอายุ
        # เลือกเฉพาะ (chosen=[(serial,name),...]): เอาเฉพาะ ItemSerial ที่ผู้ใช้เลือก
        # จากหน้าต่าง 'ดู/เลือกไอเทม' — ชิ้นที่เลือกไว้แต่หาไม่เจอ/สถานะเปลี่ยนไปแล้ว
        # จะนับเป็น "ไม่สำเร็จ" ทีละตัว (ผู้ใช้เห็นว่าทำไมถึงไม่ได้ครบ)
        if mode == "DEPOSIT":
            elig = [i for i in items if item_can_deposit(i)]
        else:
            elig = [i for i in items if item_can_withdraw(i)]
        if chosen is None:
            targets = elig
            missed = []
        else:
            by_serial = {str(i.get("ItemSerial")): i for i in items}
            targets = []
            missed = []
            for _serial, _name in chosen:
                it = by_serial.get(str(_serial))
                if it is not None and (
                    item_can_deposit(it) if mode == "DEPOSIT" else item_can_withdraw(it)
                ):
                    targets.append(it)
                else:
                    missed.append((_name or str(_serial), "ไม่พบ/สถานะเปลี่ยนไปแล้ว"))

        if not targets:
            if missed:
                # เลือกไว้แต่ตอนล็อกอินใหม่ไม่มีชิ้นนั้นให้ทำแล้ว (โดนฝาก/เบิกไปแล้ว
                # หรือหมดอายุระหว่างรอ) — แจ้งให้รู้แทนการเงียบๆ ว่าทำไมไม่ได้
                for _nm, _rs in missed:
                    self._inv_log(f"   ⏭ [{username}] {verb} '{_nm}' ข้าม — {_rs}")
                _n_missed = len(missed)
                self.root.after(
                    0,
                    lambda u=username, c=_n_missed: self._inv_set_row_status(
                        u, f"⏭ ไม่ได้{verb} ({c} ชิ้นที่เลือกเปลี่ยนสถานะ)", fg="#888"
                    ),
                )
                return {
                    "u": username, "state": _ST_PART, "msg": "",
                    "attempted": len(missed), "done": 0,
                    "item_fail": list(missed),
                }
            self.root.after(
                0,
                lambda u=username: self._inv_set_row_status(
                    u, f"⏭ ไม่มีไอเทมให้{verb}", fg="#888"
                ),
            )
            self._inv_log(
                f"   ⏭ [{username}] ไม่มีไอเทมให้{verb} (มีทั้งหมด {len(items)} รายการ)"
            )
            return {
                "u": username, "state": _ST_NONE, "msg": "",
                "attempted": 0, "done": 0, "item_fail": [],
            }

        n = len(targets) + len(missed)
        done = 0
        item_fail = list(missed)  # ชิ้นที่เลือกแต่ไม่สามารถทำได้แล้ว + ชิ้นที่ทำไม่สำเร็จ
        _op_lock = threading.Lock()
        # สรุปขั้นตอนแบบไม่รก: บอกได้กี่ชิ้นจากทั้งหมด + เหตุผลที่เหลือไม่ได้ทำ
        if chosen is None and len(items) != len(targets):
            skip = len(items) - len(targets)
            self._inv_log(
                f"   ℹ [{username}] {verb}ได้ {len(targets)} จาก {len(items)} รายการ"
                f" (ข้าม {skip} — ฝากไว้แล้ว/หมดอายุ/ไม่อยู่ที่ตัว)"
            )
        elif chosen is not None:
            self._inv_log(
                f"   ℹ [{username}] {verb}ที่เลือก: {len(targets)} ชิ้น"
                + (f" (ข้าม {len(missed)} ที่เปลี่ยนสถานะ)" if missed else "")
            )
        self._inv_log(
            f"   ▶ [{username}] เริ่ม{verb} {len(targets)} ชิ้น "
            f"(พร้อมกัน {min(5, len(targets))})"
        )
        t_op = time.time()

        def _run_op(item):
            """ฝาก/เบิก 1 ชิ้น (worker thread) — อัปเดต done/item_fail ผ่าน lock"""
            nonlocal done
            name = item_display_name(item)
            try:
                ok, msg = item_operation(_sess, _page_url, mode, item, username)
            except Exception as e:
                ok, msg = False, _err_short(e)
            with _op_lock:
                if ok:
                    done += 1
                else:
                    short = str(msg or "เว็บไม่ตอบกลับสำเร็จ").strip()
                    if len(short) > 120:
                        short = short[:120] + "…"
                    item_fail.append((name, short))
                    if len(item_fail) <= 5:
                        self._inv_log(f"   ✗ [{username}] {verb} '{name}' ไม่สำเร็จ — {short}")
            return ok

        # ฝาก/เบิกหลายชิ้นพร้อมกัน (สูงสุด 5 ต่อบัญชี) — เทสจริง: 5 เร็วสุด
        # (1891 ชิ้น ~62 วิ), 8 ชิ้นช้ากว่า (79 วิ) เพราะเว็บแถวคอย — 5 คือสมดุล
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=min(5, n)) as _ex:
            futures = []
            for item in targets:
                if stop.is_set():
                    break
                futures.append(_ex.submit(_run_op, item))
            _reported = [0]
            _progress_id = [None]

            def _progress():
                """อัปเดต X/Y เรียลไทม์ (ทุก 150ms) — cancel ตัวเองเมื่อทำงานเสร็จ
                กัน after() สะสมค้างหลังจบรอบ"""
                with _op_lock:
                    d = done
                if d != _reported[0]:
                    _reported[0] = d
                    self.root.after(
                        0,
                        lambda u=username, a=d, b=n, v=verb: self._inv_set_row_status(
                            u, f"⏳ {v} {a}/{b}...", fg="#F5C542"
                        ),
                    )
                if d < len(futures) and not stop.is_set():
                    _progress_id[0] = self.root.after(150, _progress)
                else:
                    _progress_id[0] = None

            _progress_id[0] = self.root.after(0, _progress)
            for f in futures:
                f.result()
            # งานจบแล้ว — ยกเลิก poll ที่ยังค้าง (กัน after() วนสะสมตลอดอายุแอป)
            if _progress_id[0] is not None:
                try:
                    self.root.after_cancel(_progress_id[0])
                except Exception:
                    pass
                _progress_id[0] = None
        state = _ST_OK if (done == n and done > 0) else _ST_PART
        dt_op = time.time() - t_op
        if done == n:
            self._inv_log(
                f"   ✓ [{username}] {verb}ครบ {done}/{n} รายการ ({dt_op:.1f}วิ)"
                + (f" (ข้าม {len(missed)} รายการที่เลือกไว้)" if missed else "")
            )
        else:
            self._inv_log(
                f"   ⚠ [{username}] {verb}สำเร็จ {done}/{n} ({dt_op:.1f}วิ) "
                f"(ไม่สำเร็จ {len(item_fail)})"
            )
        self.root.after(
            0,
            lambda u=username: self._inv_set_row_status(
                u,
                (
                    f"✅ {verb}ครบ {done}/{n}"
                    if done == n
                    else f"⚠ {verb} {done}/{n} (พลาด {len(item_fail)})"
                ),
                fg=STATUS_OK if done == n else STATUS_FAIL,
            ),
        )
        return {
            "u": username, "state": state, "msg": "",
            "attempted": n, "done": done, "item_fail": item_fail,
        }

    # ------------------------------------------------------------------
    # summary / popup
    # ------------------------------------------------------------------
    def _inv_summary(self, results, mode, t_start):
        verb, _icon = _MODE_META[mode]
        if not results:
            self.log(f"{_icon} ไม่มีบัญชีไหนทำงาน (ถูกยกเลิกก่อนเริ่ม)")
            return
        ok_ids = [r["u"] for r in results if r["state"] == _ST_OK]
        # เก็บ dict เต็มของบัญชีที่ "ทำได้บางส่วน" ไว้ (ต้องใช้ r['done']/attempted
        # ตอนพิมพ์บรรทัดสรุป — เก็บแค่ username เหมือนหมวดอื่นไม่ได้)
        part_ids = [r for r in results if r["state"] == _ST_PART]
        login_ids = [r for r in results if r["state"] == _ST_LOGIN]
        none_ids = [r["u"] for r in results if r["state"] == _ST_NONE]
        total_done = sum(r["done"] for r in results)
        total_fail = sum(len(r["item_fail"]) for r in results)
        total_attempted = sum(r["attempted"] for r in results)

        elapsed = time.time() - t_start
        mm, ss = divmod(int(elapsed), 60)

        self.log(
            f"── สรุป{verb}  สำเร็จ={len(ok_ids)}  มีบางรายการพลาด={len(part_ids)}  "
            f"ล็อกอินไม่ผ่าน={len(login_ids)}  ไม่มีไอเทม={len(none_ids)}"
        )
        for u in ok_ids:
            self.log(f"  ✓ {u}")
        for r in part_ids:
            self.log(f"  ⚠ {r['u']}  {verb} {r['done']}/{r['attempted']}")
        for r in login_ids:
            self.log(f"  ✗ {r['u']}  ล็อกอินไม่ผ่าน — {r['msg']}")
        for u in none_ids:
            self.log(f"  ⏭ {u}  ไม่มีไอเทมให้{verb}")
        if total_attempted:
            self.log(
                f"── รวม{verb}  {total_done}/{total_attempted} รายการ"
                + (f" (ไม่สำเร็จ {total_fail})" if total_fail else "")
            )
        self.log(f"── TOTAL  {mm:02d}:{ss:02d}")

        fail_names = []
        for r in results:
            for name, _m in r.get("item_fail", [])[:3]:
                fail_names.append(name)
        if len(fail_names) > 8:
            fail_names = fail_names[:8] + ["…"]

        # สรุปกระชับ: แสดงเฉพาะหมวดที่ไม่ใช่ 0 (ยกเว้น ครบ/สำเร็จ) — ไม่รก
        line1 = f"{verb}ครบ {len(ok_ids)}"
        if part_ids:
            line1 += f" · บางรายการพลาด {len(part_ids)}"
        if login_ids:
            line1 += f" · ล็อกอินไม่ผ่าน {len(login_ids)}"
        if none_ids:
            line1 += f" · ไม่มีไอเทม {len(none_ids)}"
        lines = [line1]
        if total_attempted:
            lines.append(
                f"รวมที่{verb}: {total_done}/{total_attempted} รายการ"
                + (f" (ไม่สำเร็จ {total_fail})" if total_fail else "")
            )
        if login_ids:
            lines.append(
                "ล็อกอินไม่ผ่าน: "
                + ", ".join(r["u"] for r in login_ids[:8])
            )
        if fail_names:
            lines.append(f"รายการที่{verb}ไม่สำเร็จ: {', '.join(fail_names)}")
        lines.append(f"⏱ เวลารวม: {mm:02d}:{ss:02d}")

        has_fail = bool(part_ids or login_ids)
        if has_fail:
            self._alert_warning(f"{verb}ไอเทมเสร็จสิ้น!", "\n".join(lines))
        else:
            self._alert_info(f"{verb}ไอเทมเสร็จสิ้น!", "\n".join(lines))


__all__ = ["AppInventoryEngineMixin"]
