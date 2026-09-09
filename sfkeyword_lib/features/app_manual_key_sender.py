"""Manual key sender window: let the user type/paste a title+code and send it as a Discord embed through the app's webhooks."""

from ..core.constants import BG, BG2, BG3, DANGER, FG, FG2, GREEN, KEYWORD_URL, STATUS_WARN
from ..core.deps import tk
from ..core.ui_theme import (
    _bind_button_hover,
    _bind_entry_context_menu,
    _center_window_on_parent,
    _page_header,
)


class AppManualKeySenderMixin:
    def open_manual_key_sender(self):
        win = tk.Toplevel(self.root)
        win.title("ส่งคีย์พิเศษเข้า Webhook")
        win.configure(bg=BG)
        win.geometry("600x560")
        win.minsize(520, 420)
        win.transient(self.root)

        _page_header(win, "ส่งคีย์พิเศษเข้า Discord Webhook", "🎁", padx=16)

        rows_outer = tk.Frame(win, bg=BG)
        rows_outer.pack(fill="both", expand=True, padx=16)

        rows_canvas = tk.Canvas(rows_outer, bg=BG, highlightthickness=0)
        rows_canvas.pack(side="left", fill="both", expand=True)

        rows_frame = tk.Frame(rows_canvas, bg=BG)
        rows_canvas_window = rows_canvas.create_window(
            (0, 0), window=rows_frame, anchor="nw"
        )
        rows_frame.bind(
            "<Configure>",
            lambda e: rows_canvas.configure(scrollregion=rows_canvas.bbox("all")),
        )
        _manual_key_last_width = [None]

        def _resize_manual_key_canvas(e):
            if e.width != _manual_key_last_width[0]:
                _manual_key_last_width[0] = e.width
                rows_canvas.itemconfigure(rows_canvas_window, width=e.width)

        rows_canvas.bind("<Configure>", _resize_manual_key_canvas)
        self._bind_mousewheel(rows_canvas, rows_frame)

        key_rows = []  # each item: {"frame","name_entry","key_entry","send_btn","num_lbl"}

        def _reindex_rows():
            for i, r in enumerate(key_rows, 1):
                r["num_lbl"].configure(text=f"{i}.")

        def _update_rows_count(_e=None):
            n = sum(1 for r in key_rows if r["key_entry"].get().strip())
            rows_count_lbl.configure(text=f"{n} คีย์" if n else "")

        def _delete_row(row):
            if row in key_rows:
                key_rows.remove(row)
            row["frame"].destroy()
            _reindex_rows()
            _update_rows_count()

        def _send_one_row(row):
            name = row["name_entry"].get().strip() or "คีย์พิเศษ"
            code = row["key_entry"].get().strip()
            if not code:
                self._alert_warning("ยังไม่ได้กรอกคีย์", "กรุณากรอกคีย์เวิร์ดของแถวนี้ก่อน")
                return
            if not self._get_enabled_webhook_urls():
                if self._get_webhook_urls():
                    self._alert_warning(
                        "ยังไม่ได้เปิดใช้งาน Webhook",
                        "ทุกช่อง Webhook ถูกติ๊กปิดใช้งานไว้หมด (ไม่ได้ลบ แค่ไม่ได้ติ๊กเปิด)",
                    )
                else:
                    self._alert_warning(
                        "ยังไม่ได้ตั้งค่า Webhook",
                        "กรุณาเพิ่ม Discord Webhook URL อย่างน้อย 1 ช่องก่อน (ในหน้าตั้งค่า)",
                    )
                return
            row["send_btn"].configure(state="disabled", text="⏳ กำลังส่ง...")

            def worker():
                try:
                    embed = self._format_manual_key_discord_embed(name, code)
                    ok, errs = self._send_to_all_webhooks(embed=embed, kind="manual_key")
                except Exception as e:
                    # กันปุ่ม "🔔 ส่ง" ค้างที่ "⏳" ถ้าเกิด error ไม่คาดคิด
                    ok, errs = False, [str(e)]
                self.root.after(0, lambda: _on_one_done(row, name, ok, errs))

            self._worker_manager.submit(worker, label="app_manual_key_sender.worker")

        def _on_one_done(row, name, ok, errs):
            try:
                row["send_btn"].configure(state="normal", text="🔔 ส่ง")
            except tk.TclError:
                pass  # แถวถูกลบไปแล้วระหว่างกำลังส่ง
            if ok:
                self.log(
                    f"🔔 ส่งคีย์พิเศษ ({name}) เข้า Discord แล้ว "
                    f"({len(self._get_enabled_webhook_urls())} ช่อง)"
                )
            else:
                self._alert_error("ส่งไม่สำเร็จ", "\n".join(errs))

        def _add_key_row(name_text="", key_text=""):
            row_frame = tk.Frame(rows_frame, bg=BG2)
            row_frame.pack(fill="x", pady=3)

            num_lbl = tk.Label(
                row_frame,
                text="",
                font=("Consolas", 10),
                bg=BG2,
                fg="#6B7280",
                width=3,
                anchor="w",
            )
            num_lbl.pack(side="left", padx=(6, 0))

            fields = tk.Frame(row_frame, bg=BG2)
            fields.pack(side="left", fill="x", expand=True, padx=4, pady=4)

            name_entry = tk.Entry(
                fields,
                highlightthickness=0,
                font=("Leelawadee UI", 9),
                bg=BG,
                fg=FG,
                insertbackground="white",
                relief="flat",
                bd=4,
            )
            name_entry.pack(fill="x", pady=(0, 2), ipady=2)
            name_entry.insert(0, name_text or "คีย์พิเศษ")
            _bind_entry_context_menu(name_entry)

            key_entry = tk.Entry(
                fields,
                highlightthickness=0,
                font=("Consolas", 11),
                bg=BG,
                fg=STATUS_WARN,
                insertbackground="white",
                relief="flat",
                bd=4,
            )
            key_entry.pack(fill="x", ipady=3)
            key_entry.insert(0, key_text)
            _bind_entry_context_menu(key_entry)
            key_entry.bind("<KeyRelease>", _update_rows_count)

            row = {
                "frame": row_frame,
                "name_entry": name_entry,
                "key_entry": key_entry,
                "num_lbl": num_lbl,
            }

            send_one_btn = tk.Button(
                row_frame,
                text="🔔 ส่ง",
                font=("Leelawadee UI", 9, "bold"),
                bg="#5865F2",
                fg="white",
                relief="flat",
                cursor="hand2",
                command=lambda: _send_one_row(row),
            )
            send_one_btn.pack(side="left", padx=4, ipadx=6, ipady=8)
            _bind_button_hover(send_one_btn, "#5865F2")
            row["send_btn"] = send_one_btn

            del_btn = tk.Button(
                row_frame,
                text="✕",
                font=("Leelawadee UI", 10),
                bg=BG2,
                fg=DANGER,
                relief="flat",
                cursor="hand2",
                command=lambda: _delete_row(row),
            )
            del_btn.pack(side="left", padx=(0, 6), ipady=8)
            _bind_button_hover(del_btn, BG2)

            key_rows.append(row)
            _reindex_rows()
            _update_rows_count()
            return row

        list_footer = tk.Frame(win, bg=BG)
        list_footer.pack(fill="x", padx=16, pady=(6, 0))
        add_row_btn = tk.Button(
            list_footer,
            text="+ เพิ่มแถว",
            font=("Leelawadee UI", 9, "bold"),
            bg=BG3,
            fg=FG2,
            relief="flat",
            cursor="hand2",
            command=lambda: _add_key_row(),
        )
        add_row_btn.pack(side="left", ipadx=8, ipady=4)
        _bind_button_hover(add_row_btn, BG3)
        rows_count_lbl = tk.Label(
            list_footer, text="", font=("Leelawadee UI", 8), bg=BG, fg="#6B7280"
        )
        rows_count_lbl.pack(side="left", padx=8)

        _add_key_row()  # เริ่มด้วย 1 แถวว่างให้กรอกทันที
        if key_rows:
            key_rows[0]["key_entry"].focus_set()

        btn_row = tk.Frame(win, bg=BG)
        btn_row.pack(fill="x", padx=16, pady=14, side="bottom")

        def _filled_rows():
            result = []
            for r in key_rows:
                code = r["key_entry"].get().strip()
                if code:
                    name = r["name_entry"].get().strip() or "คีย์พิเศษ"
                    result.append((name, code))
            return result

        def add_all_to_keywords():
            items = _filled_rows()
            if not items:
                self._alert_warning("ยังไม่ได้กรอก", "กรุณากรอกคีย์เวิร์ดอย่างน้อย 1 แถว")
                return
            for _name, code in items:
                self._add_keyword_row(code)
            self.log(f"🎁 เติมคีย์พิเศษ {len(items)} รายการลงคีย์เวิร์ดแล้ว")
            win.destroy()

        def send_all_to_discord():
            items = _filled_rows()
            if not items:
                self._alert_warning("ยังไม่ได้กรอก", "กรุณากรอกคีย์เวิร์ดอย่างน้อย 1 แถว")
                return
            if not self._get_enabled_webhook_urls():
                if self._get_webhook_urls():
                    self._alert_warning(
                        "ยังไม่ได้เปิดใช้งาน Webhook",
                        "ทุกช่อง Webhook ถูกติ๊กปิดใช้งานไว้หมด (ไม่ได้ลบ แค่ไม่ได้ติ๊กเปิด)",
                    )
                else:
                    self._alert_warning(
                        "ยังไม่ได้ตั้งค่า Webhook",
                        "กรุณาเพิ่ม Discord Webhook URL อย่างน้อย 1 ช่องก่อน (ในหน้าตั้งค่า)",
                    )
                return
            send_all_btn.configure(
                state="disabled", text=f"⏳ กำลังส่ง 0/{len(items)}..."
            )

            embeds = [
                self._format_manual_key_discord_embed(name, code)
                for name, code in items
            ]

            def _on_progress(i, total):
                send_all_btn.configure(text=f"⏳ กำลังส่ง {i}/{total}...")

            def _on_done(ok, errs):
                _on_all_done(ok, errs, items)

            # เว้นจังหวะ 1.2 วิระหว่างข้อความกัน Discord rate-limit เวลาส่งหลายคีย์รัวๆ
            self._send_embeds_to_discord_async(
                embeds,
                kind="manual_key",
                per_item_delay=1.2,
                on_progress=_on_progress,
                on_done=_on_done,
            )

        def _on_all_done(ok, errs, items):
            n = len(items)
            if not win.winfo_exists():
                if ok:
                    self.log(f"🔔 ส่งคีย์พิเศษ {n} รายการเข้า Discord แล้ว (แยกข้อความ)")
                return
            send_all_btn.configure(state="normal", text="🔔 ส่งทั้งหมด")
            if ok:
                self.log(
                    f"🔔 ส่งคีย์พิเศษ {n} รายการเข้า Discord แล้ว "
                    f"({len(self._get_enabled_webhook_urls())} ช่อง, แยกข้อความ)"
                )
                self._alert_info("สำเร็จ", f"ส่งเข้า Discord แล้วทั้งหมด {n} คีย์ (แยกข้อความ)")
            else:
                self._alert_error("ส่งไม่สำเร็จบางรายการ", "\n".join(errs))

        add_btn = tk.Button(
            btn_row,
            text="➤ เติมทั้งหมดลงคีย์เวิร์ด",
            font=("Leelawadee UI", 10, "bold"),
            bg=GREEN,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=add_all_to_keywords,
        )
        add_btn.pack(side="left", ipadx=8, ipady=6)
        _bind_button_hover(add_btn, GREEN)

        send_all_btn = tk.Button(
            btn_row,
            text="🔔 ส่งทั้งหมด",
            font=("Leelawadee UI", 10, "bold"),
            bg="#5865F2",
            fg="white",
            relief="flat",
            cursor="hand2",
            command=send_all_to_discord,
        )
        send_all_btn.pack(side="left", padx=8, ipadx=8, ipady=6)
        _bind_button_hover(send_all_btn, "#5865F2")

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
        close_btn.pack(side="right", ipadx=8, ipady=6)
        _bind_button_hover(close_btn, BG3)

        win.protocol("WM_DELETE_WINDOW", win.destroy)
        _center_window_on_parent(win, self.root)

    def _format_manual_key_discord_embed(self, title, code):
        embed = {
            "title": f"🎁  {title}",
            "description": (f"```{code}```\n**[👉 กดกรอกคีย์เวิร์ดที่นี่]({KEYWORD_URL})**"),
            "color": 0xA78BFA,
            "footer": {"text": "SFKeyword"},
        }
        avatar_url = self._get_discord_avatar_url()
        if avatar_url:
            embed["thumbnail"] = {"url": avatar_url}
        return embed
