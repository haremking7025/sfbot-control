"""Daily-key coupon picker window: fetch today's coupons from the SF site and let the user pick, copy, add-to-keywords, or send them to Discord."""

from ..core.constants import ACC2, BG, BG2, BG3, FG, FG2, GREEN, KEYWORD_URL
from ..core.deps import requests, tk
from ..core.ui_theme import _bind_button_hover, _center_window_on_parent, _page_header
from ..core.webhook import fetch_sf_coupons


class AppCouponPickerMixin:
    def open_daily_key_picker(self):
        if requests is None:
            self._alert_error(
                "ขาดไลบรารี", "ฟีเจอร์นี้ต้องใช้ไลบรารี requests\nติดตั้งด้วย: pip install requests"
            )
            return

        self.fetch_key_btn.configure(state="disabled", text="⏳ กำลังดึง...")
        self.log("🔑 กำลังดึงคีย์วันนี้...")

        def worker():
            try:
                coupons = fetch_sf_coupons()
                err = None
            except Exception as e:
                coupons, err = [], str(e)
            self.root.after(0, lambda: self._on_coupons_fetched(coupons, err))

        self._worker_manager.submit(worker, label="app_coupon_picker.fetch_worker")

    def _on_coupons_fetched(self, coupons, err):
        self.fetch_key_btn.configure(state="normal", text="🔑 ดึงคีย์วันนี้")
        if err:
            self.log(f"🔑 ดึงคีย์วันนี้ ล้มเหลว: {err}")
            self._alert_error("ดึงคีย์ไม่สำเร็จ", f"เกิดข้อผิดพลาด:\n{err}")
            return
        if not coupons:
            self.log("🔑 ดึงคีย์วันนี้ สำเร็จ — ไม่พบคีย์เวิร์ดในหน้า printable ตอนนี้")
            self._alert_info("ไม่พบคีย์", "ไม่พบคีย์เวิร์ด Special Force ในหน้า printable ตอนนี้")
            return
        self.log(f"🔑 ดึงคีย์วันนี้ สำเร็จ พบ {len(coupons)} คีย์")
        self._show_coupon_picker_window(coupons)

    def _show_coupon_picker_window(self, coupons):
        win = tk.Toplevel(self.root)
        win.title("เลือกคีย์ไอเทม SF วันนี้")
        win.configure(bg=BG)
        win.geometry("940x460")
        win.transient(self.root)

        _page_header(win, "คีย์เวิร์ด Special Force วันนี้", "🔑", padx=16)

        list_frame = tk.Frame(win, bg=BG)
        list_frame.pack(fill="both", expand=True, padx=16)
        sb = tk.Scrollbar(list_frame, orient="vertical")
        hb = tk.Scrollbar(list_frame, orient="horizontal")
        lb = tk.Listbox(
            list_frame,
            font=("Consolas", 11),
            bg=BG2,
            fg=FG,
            selectbackground=ACC2,
            activestyle="none",
            yscrollcommand=sb.set,
            xscrollcommand=hb.set,
            highlightthickness=0,
            relief="flat",
        )
        sb.configure(command=lb.yview)
        hb.configure(command=lb.xview)
        lb.pack(side="left", fill="both", expand=True)
        # ซ่อนแถบเลื่อนทั้งแนวตั้ง/นอน - Listbox เลื่อนแนวตั้งด้วยล้อเมาส์ได้เอง
        # อยู่แล้ว ส่วนแนวนอนใช้ Shift+ล้อเมาส์ (bind ด้านล่าง)
        lb.bind(
            "<Shift-MouseWheel>",
            lambda e: lb.xview_scroll(int(-1 * (e.delta / 120)), "units"),
        )

        for c in coupons:
            tag = "🔑 [ไม่มีเงื่อนไข]" if c["is_daily_key"] else "🎮 [มีเงื่อนไข]"
            lb.insert("end", f"{tag}  {c['title']}  ->  {c['code']}")
        if coupons:
            lb.selection_set(0)

        copy_hint_lbl = tk.Label(
            win, text="", font=("Leelawadee UI", 9), bg=BG, fg="#00cc66"
        )
        copy_hint_lbl.pack(anchor="w", padx=16, pady=(0, 0))

        def _copy_code(code):
            win.clipboard_clear()
            win.clipboard_append(code)
            win.update()
            copy_hint_lbl.configure(text=f"📋 คัดลอกคีย์เวิร์ด '{code}' แล้ว")
            win.after(2000, lambda: copy_hint_lbl.configure(text=""))
            self.log(f"📋 คัดลอกคีย์เวิร์ด '{code}' แล้ว")

        def _copy_by_index(idx):
            if 0 <= idx < len(coupons):
                lb.selection_clear(0, "end")
                lb.selection_set(idx)
                _copy_code(coupons[idx]["code"])

        def _on_double_click(_evt):
            idx = lb.nearest(_evt.y)
            _copy_by_index(idx)

        def _on_right_click(_evt):
            idx = lb.nearest(_evt.y)
            _copy_by_index(idx)

        lb.bind("<Double-Button-1>", _on_double_click)
        lb.bind("<Button-3>", _on_right_click)

        def _copy_selected_key(_evt=None):
            try:
                sel = lb.curselection()
            except Exception:
                return "break"
            _copy_by_index(sel[0] if sel else 0)
            return "break"

        def _on_listbox_key(_evt):
            # Ctrl+C คัดลอกคีย์ที่เลือก — ตรวจทั้ง keysym (คีย์บอร์ดอังกฤษ) และ
            # keycode 67 (คีย์บอร์ดไทยที่ keysym กลายเป็นตัวอักษรไทย) แบบเดียวกับ
            # _global_clipboard_shortcut ของหน้าต่างหลัก
            if not (_evt.state & 0x0004):
                return None
            ks = (getattr(_evt, "keysym", "") or "").lower()
            if ks == "c" or getattr(_evt, "keycode", None) == 67:
                return _copy_selected_key()
            return None

        lb.bind("<Control-c>", _copy_selected_key)
        lb.bind("<Control-C>", _copy_selected_key)
        lb.bind("<KeyPress>", _on_listbox_key, add="+")

        btn_row = tk.Frame(win, bg=BG)
        btn_row.pack(fill="x", padx=16, pady=12)

        def get_selected():
            sel = lb.curselection()
            if not sel:
                self._alert_warning("ยังไม่ได้เลือก", "กรุณาเลือกคีย์ก่อน")
                return None
            return coupons[sel[0]]

        def copy_selected():
            c = get_selected()
            if not c:
                return
            _copy_code(c["code"])

        def add_to_keywords():
            c = get_selected()
            if not c:
                return
            self._add_keyword_row(c["code"])
            self.log(f"🔑 เติมคีย์ '{c['code']}' ({c['title']}) ลงคีย์เวิร์ดแล้ว")
            win.destroy()

        def send_to_discord():
            c = get_selected()
            if not c:
                return
            embed = self._format_coupon_discord_embed(c)
            send_dc_btn.configure(state="disabled", text="⏳ กำลังส่ง...")

            def worker():
                try:
                    ok, errs = self._send_to_all_webhooks(embed=embed, kind="daily_key")
                except Exception as e:
                    # กันปุ่ม "🔔 ส่งเข้า Discord" ค้างที่ "⏳" ถ้าเกิด error ไม่คาดคิด
                    ok, errs = False, [str(e)]
                self.root.after(0, lambda: _on_send_one_done(ok, errs, c))

            self._worker_manager.submit(worker, label="app_coupon_picker.send_one_worker")

        def _on_send_one_done(ok, errs, c):
            if not win.winfo_exists():
                if ok:
                    self.log(f"🔔 ส่งคีย์ '{c['code']}' เข้า Discord แล้ว")
                return
            send_dc_btn.configure(state="normal", text="🔔 ส่งเข้า Discord")
            if ok:
                self.log(
                    f"🔔 ส่งคีย์ '{c['code']}' เข้า Discord แล้ว ({len(self._get_enabled_webhook_urls())} ช่อง)"
                )
                self._alert_info("สำเร็จ", "ส่งเข้า Discord แล้ว")
            else:
                self._alert_error("ส่งไม่สำเร็จ", "\n".join(errs))

        def send_all_to_discord():
            if not coupons:
                return
            embeds = self._format_coupons_discord_embeds(coupons)
            send_all_dc_btn.configure(state="disabled", text="⏳ กำลังส่ง...")
            self._send_embeds_to_discord_async(
                embeds, kind="daily_key", on_done=_on_send_all_done
            )

        def _on_send_all_done(all_ok, all_errs):
            if not win.winfo_exists():
                if all_ok:
                    self.log(f"🔔 ส่งคีย์ทั้งหมด {len(coupons)} รายการเข้า Discord แล้ว")
                return
            send_all_dc_btn.configure(state="normal", text="🔔 ส่งทั้งหมดเข้า Discord")
            if all_ok:
                self.log(
                    f"🔔 ส่งคีย์ทั้งหมด {len(coupons)} รายการเข้า Discord แล้ว ({len(self._get_enabled_webhook_urls())} ช่อง)"
                )
                self._alert_info(
                    "สำเร็จ", f"ส่งคีย์ทั้งหมด {len(coupons)} รายการเข้า Discord แล้ว"
                )
            else:
                self._alert_error("ส่งไม่สำเร็จ", "\n".join(all_errs))

        add_kw_dlg_btn = tk.Button(
            btn_row,
            text="➤ เติมลงคีย์เวิร์ด",
            font=("Leelawadee UI", 10, "bold"),
            bg=GREEN,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=add_to_keywords,
        )
        add_kw_dlg_btn.pack(side="left", ipadx=8, ipady=6)
        _bind_button_hover(add_kw_dlg_btn, GREEN)
        copy_btn = tk.Button(
            btn_row,
            text="📋 คัดลอกคีย์เวิร์ด",
            font=("Leelawadee UI", 10, "bold"),
            bg="#374151",
            fg="white",
            relief="flat",
            cursor="hand2",
            command=copy_selected,
        )
        copy_btn.pack(side="left", padx=8, ipadx=8, ipady=6)
        _bind_button_hover(copy_btn, "#374151")
        send_dc_btn = tk.Button(
            btn_row,
            text="🔔 ส่งเข้า Discord",
            font=("Leelawadee UI", 10, "bold"),
            bg="#5865F2",
            fg="white",
            relief="flat",
            cursor="hand2",
            command=send_to_discord,
        )
        send_dc_btn.pack(side="left", padx=8, ipadx=8, ipady=6)
        _bind_button_hover(send_dc_btn, "#5865F2")
        send_all_dc_btn = tk.Button(
            btn_row,
            text="🔔 ส่งทั้งหมดเข้า Discord",
            font=("Leelawadee UI", 10, "bold"),
            bg="#4752C4",
            fg="white",
            relief="flat",
            cursor="hand2",
            command=send_all_to_discord,
        )
        send_all_dc_btn.pack(side="left", padx=8, ipadx=8, ipady=6)
        _bind_button_hover(send_all_dc_btn, "#4752C4")
        close_dlg_btn = tk.Button(
            btn_row,
            text="ปิด",
            font=("Leelawadee UI", 10),
            bg=BG3,
            fg=FG2,
            relief="flat",
            cursor="hand2",
            command=win.destroy,
        )
        close_dlg_btn.pack(side="right", ipadx=8, ipady=6)
        _bind_button_hover(close_dlg_btn, BG3)

        win.protocol("WM_DELETE_WINDOW", win.destroy)
        _center_window_on_parent(win, self.root)

    def _format_coupon_discord_embed(self, c):
        tag = "🔑 ไม่มีเงื่อนไข" if c["is_daily_key"] else "🎮 ต้องเล่นครบเวลา"
        embed = {
            "title": f"🎁  {c['title']}",
            "description": (
                f"`{tag}`\n\n```{c['code']}```\n**[👉 กดกรอกคีย์เวิร์ดที่นี่]({KEYWORD_URL})**"
            ),
            "color": 0xE8455A,
            "footer": {"text": "SFKeyword"},
        }
        avatar_url = self._get_discord_avatar_url()
        if avatar_url:
            embed["thumbnail"] = {"url": avatar_url}
        return embed
