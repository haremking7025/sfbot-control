"""Webhook message history window: browse everything ever sent through the app's Discord webhooks and delete selected messages."""

from ..core.constants import ACC2, BG, BG2, BG3, FG, FG2, INFO_BLUE, STATUS_FAIL, STATUS_OK, STATUS_WARN
from ..core.deps import csv, datetime, os, tk
from ..core.paths import RESULTS_DIR
from ..core.ui_theme import _center_window_on_parent, _page_header
from typing import ClassVar

from ..core.webhook import delete_discord_webhook_message_verified, fetch_discord_webhook_message, load_webhook_message_history, remove_webhook_messages_from_history, strip_discord_markdown_light, webhook_message_preview_matches


class AppWebhookHistoryMixin:
    _WEBHOOK_HISTORY_KIND_LABELS: ClassVar[dict[str, str]] = {
        "daily_key": "🔑 คีย์ประจำวัน",
        "manual_key": "🔑 คีย์ (ส่งเอง)",
        "autoitem_result": "🎁 ผลรับไอเทมฟรี",
        "test": "🧪 ทดสอบ",
        "other": "💬 อื่นๆ",
    }

    def _export_webhook_history_csv(self, history):
        """ส่งออกประวัติข้อความ Webhook (list ของ dict จาก
        load_webhook_message_history) เป็นไฟล์ CSV ในโฟลเดอร์เดียวกับที่
        ผลลัพธ์อื่นๆ ถูกส่งออก (RESULTS_DIR) — คืน path ถ้าสำเร็จ, None ถ้าไม่"""
        try:
            path = os.path.join(
                RESULTS_DIR,
                f"sfkeyword_webhook_history_{datetime.now():%Y%m%d_%H%M%S}.csv",
            )
            os.makedirs(RESULTS_DIR, exist_ok=True)
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    ["sent_at", "kind", "webhook_name", "preview", "message_id"]
                )
                for e in history:
                    writer.writerow(
                        [
                            e.get("sent_at", ""),
                            self._WEBHOOK_HISTORY_KIND_LABELS.get(
                                e.get("kind", "other"), e.get("kind", "other")
                            ),
                            e.get("webhook_name", ""),
                            e.get("preview", ""),
                            e.get("message_id", ""),
                        ]
                    )
            self.log(f"📊 ส่งออกประวัติ Webhook: {os.path.basename(path)}")
            return path
        except Exception as exc:
            self.log(f"⚠ ส่งออกประวัติ Webhook ไม่สำเร็จ: {type(exc).__name__}")
            return None

    def _open_webhook_history_window(self):
        """เปิดหน้าต่างแสดงประวัติข้อความที่เคยส่งผ่าน Webhook ทั้งหมด (ทุกช่อง ทุก
        ประเภท) เรียงใหม่->เก่า พร้อมให้เลือกลบข้อความจริงใน Discord ได้หลายอันพร้อมกัน"""
        history = list(reversed(load_webhook_message_history()))

        win = tk.Toplevel(self.root)
        win.title("ข้อความที่เคยส่งผ่าน Webhook")
        win.configure(bg=BG)
        win.geometry("760x480")
        win.transient(self.root)

        _page_header(win, "ข้อความที่เคยส่งผ่าน Webhook", "📤", padx=16)
        header_lbl = tk.Label(
            win,
            text="",
            font=("Leelawadee UI", 10),
            bg=BG,
            fg=FG2,
            wraplength=720,
            justify="left",
        )
        header_lbl.pack(anchor="w", padx=16, pady=(4, 2))

        list_frame = tk.Frame(win, bg=BG)
        list_frame.pack(fill="both", expand=True, padx=16)
        sb = tk.Scrollbar(list_frame, orient="vertical")
        lb = tk.Listbox(
            list_frame,
            font=("Consolas", 10),
            bg=BG2,
            fg=FG,
            selectbackground=ACC2,
            selectmode="extended",
            activestyle="none",
            yscrollcommand=sb.set,
            highlightthickness=0,
            relief="flat",
        )
        sb.configure(command=lb.yview)
        # ซ่อนแถบเลื่อน (เหมือนหน้าต่างเลือกคีย์) - Listbox เลื่อนด้วยล้อเมาส์ได้เองอยู่แล้ว
        lb.pack(side="left", fill="both", expand=True)

        def _render_history_list():
            """วาดรายการ + หัวข้อ + สถานะปุ่มใหม่ทั้งหมดจาก `history` ปัจจุบัน โดยไม่ปิด/
            เปิดหน้าต่างใหม่ — เรียกได้ทั้งตอนเปิดครั้งแรกและหลังลบสำเร็จ เพื่อให้รายการ
            อัปเดตทันทีในหน้าต่างเดิม (real-time, ไม่ต้องให้ผู้ใช้ปิดแล้วเปิดใหม่)"""
            header_lbl.configure(
                text=(
                    f"({len(history)} รายการ) "
                    "— เลือกแล้วกดลบเพื่อลบข้อความจริงใน Discord"
                )
            )
            lb.configure(state="normal")
            lb.delete(0, "end")
            if not history:
                lb.insert("end", "— ยังไม่มีประวัติข้อความที่ส่งไป —")
                lb.configure(state="disabled")
            else:
                for e in history:
                    kind_lbl = self._WEBHOOK_HISTORY_KIND_LABELS.get(
                        e.get("kind"), e.get("kind") or "?"
                    )
                    wh_name = e.get("webhook_name") or "(ไม่มีชื่อ)"
                    preview = (e.get("preview") or "").replace("\n", " ")
                    if len(preview) > 70:
                        preview = preview[:70] + "…"
                    lb.insert(
                        "end",
                        f"{e.get('sent_at', '?')}  ▸ {kind_lbl}  ▸ [{wh_name}]  {preview}",
                    )
            has_rows = bool(history)
            del_btn.configure(state="normal" if has_rows else "disabled")
            select_all_btn.configure(state="normal" if has_rows else "disabled")
            deselect_all_btn.configure(state="normal" if has_rows else "disabled")
            _set_details("เลือกรายการด้านบนเพื่อดึงรายละเอียดข้อความจริงจาก Discord")

        status_lbl = tk.Label(
            win, text="", font=("Leelawadee UI", 9), bg=BG, fg=FG2
        )
        status_lbl.pack(anchor="w", padx=16, pady=(4, 0))

        # แผงแสดง "รายละเอียดข้อความ" (Message Details) ของรายการที่เพิ่งเลือกล่าสุด
        # — ดึงสดจาก Discord จริงทุกครั้งที่เลือก (ไม่ใช่แค่ preview สั้นๆ ที่เก็บไว้
        # ในประวัติ) เพื่อให้เห็นเนื้อหา/เวลา/ผู้ส่ง/Message ID ที่ตรงกับข้อความจริง
        # ก่อนตัดสินใจกดลบ — ลดความเสี่ยงลบผิดรายการ
        details_frame = tk.Frame(win, bg=BG2)
        details_frame.pack(fill="x", padx=16, pady=(8, 0))
        tk.Label(
            details_frame,
            text="รายละเอียดข้อความ (Message Details)",
            font=("Leelawadee UI", 9, "bold"),
            bg=BG2,
            fg=ACC2,
            anchor="w",
        ).pack(fill="x", padx=8, pady=(6, 0))
        details_lbl = tk.Text(
            details_frame,
            font=("Consolas", 9),
            bg=BG2,
            fg=FG2,
            wrap="word",
            height=8,
            relief="flat",
            highlightthickness=0,
            padx=8,
            pady=4,
            state="disabled",
            cursor="arrow",
        )
        details_sb = tk.Scrollbar(details_frame, orient="vertical", command=details_lbl.yview)
        details_lbl.configure(yscrollcommand=details_sb.set)
        details_lbl.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=(2, 8))
        # ซ่อนแถบเลื่อน (ไม่ pack/grid details_sb) - Text widget เลื่อนด้วยล้อเมาส์ได้เอง
        # อยู่แล้วโดย Tk, และยังเลื่อนผ่านโค้ดได้ปกติผ่าน details_sb.set/details_lbl.yview
        # ไม่เรียก self._bind_mousewheel ที่นี่ — ฟังก์ชันนั้นออกแบบมาสำหรับ Canvas
        # (เทียบ inner_frame.winfo_reqheight() กับ canvas.winfo_height()) ใช้กับ Text
        # โดยตรงจะเลื่อนพัง เพราะ Text widget เลื่อนด้วยล้อเมาส์ได้เองอยู่แล้วโดย Tk

        def _set_details(text, fg=FG2):
            """เขียนข้อความเต็มลง details_lbl (ตอนนี้เป็น Text ไม่ใช่ Label) — แสดงเนื้อหา
            เต็มความยาวจริง ตัดบรรทัดอัตโนมัติ (word wrap) และเลื่อนดูได้ถ้ายาวเกินพื้นที่
            แทนการตัดข้อความทิ้งแบบเดิม"""
            details_lbl.configure(state="normal", fg=fg)
            details_lbl.delete("1.0", "end")
            details_lbl.insert("1.0", text)
            details_lbl.configure(state="disabled")

        _details_req_id = {"n": 0}

        def _on_history_select(_evt=None):
            sel = list(lb.curselection())
            if not sel or not history:
                return
            entry = history[sel[-1]]
            _details_req_id["n"] += 1
            my_req = _details_req_id["n"]
            _set_details("⏳ กำลังดึงรายละเอียดข้อความจาก Discord...")

            def worker(entry=entry, my_req=my_req):
                ok, err, details, _already_gone = fetch_discord_webhook_message(
                    entry.get("webhook_url"), entry.get("message_id")
                )
                self.root.after(
                    0, lambda: _show_details(my_req, entry, ok, err, details)
                )

            self._worker_manager.submit(worker, label="app_webhook_history.detail_worker")

        def _show_details(my_req, entry, ok, err, details):
            if my_req != _details_req_id["n"]:
                return  # ผู้ใช้เลือกรายการอื่นไปแล้วระหว่างรอผล — ทิ้งผลลัพธ์เก่านี้
            if not ok:
                _set_details(f"❌ ไม่พบข้อความเป้าหมาย — {err}", fg=STATUS_FAIL)
                return
            # แสดงเนื้อหาเต็ม ไม่ตัดทิ้งเอง — ตัดแค่ที่ขีดจำกัดจริงของ Discord เอง
            # (content 2000 ตัวอักษร, embed description 4096 ตัวอักษร) เผื่อกรณีข้อมูล
            # ผิดปกติ ส่วนที่เหลือปล่อยให้ Text widget ตัดบรรทัด/เลื่อนดูเอง
            content = (details.get("content") or "").strip()
            if len(content) > 2000:
                content = content[:2000] + "…"
            embed_title = (details.get("embed_title") or "").strip()
            embed_desc = strip_discord_markdown_light(details.get("embed_description") or "")
            if len(embed_desc) > 4096:
                embed_desc = embed_desc[:4096] + "…"
            match_ok = webhook_message_preview_matches(entry.get("preview", ""), details)
            match_tag = "\n⚠ เนื้อหาไม่ตรงกับประวัติที่บันทึกไว้!" if not match_ok else ""
            lines = [
                f"Message ID : {details.get('id', '?')}",
                f"เวลาส่ง     : {details.get('timestamp', '?')}",
                f"ผู้ส่ง       : {details.get('author') or '-'}",
            ]
            if content:
                lines.append(f"เนื้อหา      :\n{content}")
            if embed_title:
                lines.append(f"หัวข้อ (Embed): {embed_title}")
            if embed_desc:
                lines.append(f"รายละเอียด   :\n{embed_desc}")
            if not content and not embed_title and not embed_desc:
                lines.append("เนื้อหา      : (ไม่มีข้อความ/ไม่มี embed)")
            text = "\n".join(lines) + match_tag
            _set_details(text, fg=STATUS_FAIL if not match_ok else FG)

        lb.bind("<<ListboxSelect>>", _on_history_select)

        btn_row = tk.Frame(win, bg=BG)
        btn_row.pack(fill="x", padx=16, pady=10)

        def select_all():
            if not history:
                return
            lb.selection_set(0, "end")

        def deselect_all():
            lb.selection_clear(0, "end")

        def do_delete_selected():
            if not history:
                return
            sel = list(lb.curselection())
            if not sel:
                status_lbl.configure(text="⚠ ยังไม่ได้เลือกข้อความที่จะลบ", fg=STATUS_WARN)
                return
            targets = [history[i] for i in sel]
            if not self._confirm_dialog(
                "ยืนยันการลบข้อความ",
                lines=[f"ต้องการลบข้อความที่เลือกไว้ {len(targets)} ข้อความออกจาก Discord หรือไม่?"],
                warning="⚠ การกระทำนี้ย้อนกลับไม่ได้!",
                confirm_text="ลบข้อความ",
                cancel_text="ยกเลิก",
                danger=True,
            ):
                return
            del_btn.configure(state="disabled", text="⏳ กำลังลบ...")
            status_lbl.configure(
                text=f"⏳ กำลังลบ {len(targets)} ข้อความ...", fg=FG2
            )

            def worker():
                removed = []
                not_removed = 0
                for e in targets:
                    # ดึงรายละเอียดข้อความจริงจาก Discord + เทียบกับ preview เดิม
                    # ก่อนลบเสมอ (delete_discord_webhook_message_verified) — ถ้าไม่
                    # พบข้อความเป้าหมาย เนื้อหาจริงไม่ตรงกับประวัติ หรือลบไม่สำเร็จ
                    # จะไม่ถือว่าลบแล้ว และ log สาเหตุที่แท้จริงไว้เสมอ
                    ok, err, details, already_gone = delete_discord_webhook_message_verified(
                        e.get("webhook_url"),
                        e.get("message_id"),
                        expected_preview=e.get("preview", ""),
                    )
                    mid = e.get("message_id")
                    if ok:
                        removed.append(e)
                        if already_gone:
                            self.root.after(
                                0,
                                lambda mid=mid: self.log(
                                    f"   🔍 ตรวจสอบข้อความก่อนลบ: ID={mid} "
                                    f"→ ไม่พบใน Discord แล้ว (ถูกลบไปก่อนหน้านี้) "
                                    f"ล้างออกจากประวัติ"
                                ),
                            )
                        else:
                            author = (details or {}).get("author", "")
                            ts = (details or {}).get("timestamp", "")
                            self.root.after(
                                0,
                                lambda mid=mid, a=author, t=ts: self.log(
                                    f"   🔍 ตรวจสอบข้อความก่อนลบ: ID={mid} "
                                    f"ผู้ส่ง={a or '-'} เวลา={t or '-'} → ลบแล้ว"
                                ),
                            )
                    else:
                        not_removed += 1
                        self.root.after(
                            0,
                            lambda mid=mid, err=err: self.log(
                                f"   ⚠ ไม่ได้ลบ ID={mid}: {err}"
                            ),
                        )
                remove_webhook_messages_from_history(removed)
                self.root.after(
                    0, lambda: _on_delete_done(removed, not_removed)
                )

            self._worker_manager.submit(worker, label="app_webhook_history.delete_worker")

        def _on_delete_done(removed, n_not_removed):
            n_removed = len(removed)
            if n_removed:
                self.log(f"🗑 ลบข้อความ Webhook ที่เคยส่งไปแล้ว {n_removed} ข้อความ")
                # ลบรายการที่ลบสำเร็จออกจาก `history` ในหน่วยความจำโดยตรง (ใช้คู่
                # webhook_url+message_id เทียบ เหมือนที่ remove_webhook_messages_from_history
                # ใช้เทียบตอนลบออกจากไฟล์บนดิสก์) แล้ววาดหน้าต่างเดิมใหม่ทันที — ไม่ต้อง
                # ปิด/เปิดหน้าต่างใหม่ ผู้ใช้เห็นผลลัพธ์แบบ real-time
                removed_keys = {
                    (e.get("webhook_url"), e.get("message_id")) for e in removed
                }
                history[:] = [
                    e
                    for e in history
                    if (e.get("webhook_url"), e.get("message_id")) not in removed_keys
                ]
                lb.selection_clear(0, "end")
                _render_history_list()
            if n_not_removed:
                status_lbl.configure(
                    text=(
                        f"✅ ลบสำเร็จ {n_removed} ข้อความ — "
                        f"ไม่ได้ลบ {n_not_removed} ข้อความ (ดู log ประกอบ)"
                    ),
                    fg=STATUS_FAIL,
                )
            else:
                status_lbl.configure(
                    text=f"✅ ลบสำเร็จ {n_removed} ข้อความ", fg=STATUS_OK
                )
            del_btn.configure(text="🗑 ลบข้อความที่เลือก")

        del_btn = tk.Button(
            btn_row,
            text="🗑 ลบข้อความที่เลือก",
            font=("Leelawadee UI", 10),
            bg="#3A1E24",
            fg=STATUS_FAIL,
            relief="flat",
            cursor="hand2",
            command=do_delete_selected,
        )
        del_btn.pack(side="left", ipadx=8, ipady=3)

        def _copy_selected_row(_evt=None):
            try:
                sel = lb.curselection()
                idx = sel[0] if sel else 0
                text = lb.get(idx)
            except Exception:
                return "break"
            win.clipboard_clear()
            win.clipboard_append(text)
            win.update()
            status_lbl.configure(
                text=f"📋 คัดลอกข้อความแล้ว (แถว {idx + 1})", fg=STATUS_OK
            )
            win.after(2500, lambda: status_lbl.configure(text=""))
            return "break"

        def _on_history_key(_evt):
            # Delete = ลบข้อความที่เลือก, Ctrl+C = คัดลอกแถวที่เลือก
            # ตรวจ keycode ด้วย (67 = C) เพื่อรองรับคีย์บอร์ดไทยที่ keysym เปลี่ยน
            if _evt.state & 0x0004:
                ks = (getattr(_evt, "keysym", "") or "").lower()
                if ks == "c" or getattr(_evt, "keycode", None) == 67:
                    return _copy_selected_row()
                return None
            if (getattr(_evt, "keysym", "") or "") == "Delete":
                win.after(0, do_delete_selected)
                return "break"
            return None

        lb.bind("<Delete>", _on_history_key)
        lb.bind("<Control-c>", _copy_selected_row)
        lb.bind("<Control-C>", _copy_selected_row)
        lb.bind("<KeyPress>", _on_history_key, add="+")

        select_all_btn = tk.Button(
            btn_row,
            text="เลือกทั้งหมด",
            font=("Leelawadee UI", 10),
            bg=BG3,
            fg=FG2,
            relief="flat",
            cursor="hand2",
            command=select_all,
        )
        select_all_btn.pack(side="left", padx=(8, 0), ipadx=8, ipady=3)

        deselect_all_btn = tk.Button(
            btn_row,
            text="ยกเลิกเลือก",
            font=("Leelawadee UI", 10),
            bg=BG3,
            fg=FG2,
            relief="flat",
            cursor="hand2",
            command=deselect_all,
        )
        deselect_all_btn.pack(side="left", padx=(8, 0), ipadx=8, ipady=3)

        def do_export_csv():
            if not history:
                status_lbl.configure(text="⚠ ยังไม่มีประวัติให้ส่งออก", fg=STATUS_WARN)
                return
            path = self._export_webhook_history_csv(history)
            if path:
                status_lbl.configure(
                    text=f"📊 ส่งออก CSV แล้ว: {os.path.basename(path)}", fg=STATUS_OK
                )
                self._alert_info("ส่งออกสำเร็จ", f"บันทึกประวัติ Webhook แล้ว:\n{path}")
            else:
                status_lbl.configure(text="❌ ส่งออก CSV ไม่สำเร็จ (ดู Log)", fg=STATUS_FAIL)

        export_csv_btn = tk.Button(
            btn_row,
            text="📊 ส่งออก CSV",
            font=("Leelawadee UI", 10),
            bg=BG3,
            fg=INFO_BLUE,
            relief="flat",
            cursor="hand2",
            command=do_export_csv,
        )
        export_csv_btn.pack(side="left", padx=(8, 0), ipadx=8, ipady=3)

        close_btn = tk.Button(
            btn_row,
            text="ปิด",
            font=("Leelawadee UI", 10),
            bg=BG3,
            fg=FG2,
            relief="flat",
            cursor="hand2",
            command=win.destroy,
        )
        close_btn.pack(side="left", padx=(8, 0), ipadx=8, ipady=3)

        win.protocol("WM_DELETE_WINDOW", win.destroy)
        _center_window_on_parent(win, self.root)

        # เรียกครั้งแรกตอนเปิดหน้าต่าง (ตอนนี้ del_btn/select_all_btn/deselect_all_btn/
        # details_lbl ถูกสร้างแล้วทั้งหมด) — ฟังก์ชันเดียวกันนี้ถูกเรียกซ้ำอีกครั้งหลังลบ
        # สำเร็จ เพื่ออัปเดตหน้าต่างเดิมทันทีแทนการปิด/เปิดใหม่
        _render_history_list()
