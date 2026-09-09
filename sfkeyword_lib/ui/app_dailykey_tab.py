"""The 'daily key' tab — everything about fetching/sending the daily coupon
key and its Discord Webhook destinations, all in one place.

ก่อนหน้านี้ฟีเจอร์นี้กระจายอยู่ 2 ที่: ปุ่ม "ดึงคีย์วันนี้"/"ส่งคีย์พิเศษเข้า
Webhook" อยู่ในแผง TOOLS ของแท็บ Dashboard ส่วนการตั้งค่า Webhook (URL,
รูป/ชื่อบอท, toggle ดึงอัตโนมัติ+countdown, ทดสอบส่ง, ประวัติ) อยู่ในการ์ด
"Discord Webhook" ของแท็บตั้งค่า — ทั้งที่ Webhook นี้ใช้เฉพาะฟีเจอร์คีย์
ประจำวันเท่านั้น ไม่ได้แชร์กับส่วนอื่นเลย

ย้ายมารวมเป็นแท็บเดียวที่นี่ทั้งหมด ตาม pattern เดียวกับที่แท็บ "รับไอเทมฟรี"
(app_autoitem_ui.py) ใช้อยู่แล้ว คือฟีเจอร์ที่มีทั้ง config และ action ของ
ตัวเอง ควรอยู่รวมกันในแท็บเดียว ไม่ต้องสลับไปมาระหว่าง Dashboard/Settings
โค้ดข้างในแต่ละบรรทัดยกมาจากตำแหน่งเดิมทุกประการ ไม่มีการเปลี่ยน logic ใดๆ
มีแค่ปรับ layout ให้เข้ากับหน้าใหม่ (ปุ่มลัดด่วนขึ้นก่อน ตามด้วยการตั้งค่า)"""

from ..core.constants import ACC2, BG, BG2, BG3, BG4, BORDER, DANGER, FG2, GREEN, INFO_BLUE, STATUS_OK, STATUS_WARN, _DISCORD_BOT_NAME
from ..core.deps import tk
from ..core.ui_theme import (
    _bind_button_hover,
    _bind_entry_context_menu,
    _make_toggle,
    _page_header,
)


class AppDailyKeyTabMixin:
    def _build_dailykey_tab(self, parent):
        dk_canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        dk_scrollbar = tk.Scrollbar(parent, orient="vertical", command=dk_canvas.yview)
        dk_canvas.pack(side="left", fill="both", expand=True)
        # ซ่อนแถบเลื่อน - เลื่อนด้วยล้อเมาส์ได้ปกติผ่าน _bind_mousewheel ด้านล่าง
        dk_content = tk.Frame(dk_canvas, bg=BG)
        dk_window = dk_canvas.create_window((0, 0), window=dk_content, anchor="nw")

        def _dk_frame_configure(e=None):
            dk_canvas.configure(scrollregion=dk_canvas.bbox("all"))

        dk_content.bind("<Configure>", _dk_frame_configure)
        dk_canvas.configure(yscrollcommand=dk_scrollbar.set)
        _dk_last_width = [None]

        def _resize_dk_canvas(e):
            if e.width != _dk_last_width[0]:
                _dk_last_width[0] = e.width
                dk_canvas.itemconfig(dk_window, width=e.width)

        dk_canvas.bind("<Configure>", _resize_dk_canvas)
        self._bind_mousewheel(dk_canvas, dk_content)

        def _section(title):
            hdr = tk.Frame(dk_content, bg=BG)
            hdr.pack(fill="x", padx=16, pady=(16, 0))
            tk.Label(
                hdr, text=title, font=("Leelawadee UI", 9, "bold"), bg=BG, fg=ACC2
            ).pack(side="left")
            tk.Frame(hdr, bg=BORDER, height=1).pack(
                side="left", fill="x", expand=True, padx=(8, 0)
            )
            card = tk.Frame(
                dk_content,
                bg=BG2,
                highlightbackground=BORDER,
                highlightcolor=BORDER,
                highlightthickness=1,
                takefocus=0,
            )
            card.pack(fill="x", padx=16, pady=(4, 0))
            return card

        def _row(parent, pady=(8, 4)):
            f = tk.Frame(parent, bg=BG2)
            f.pack(fill="x", padx=16, pady=pady)
            return f

        def _lbl(parent, text=""):
            lbl = tk.Label(
                parent, text=text, font=("Leelawadee UI", 10), bg=BG2, fg=FG2
            )
            lbl.pack(side="left")
            return lbl

        _page_header(dk_content, "คีย์ประจำวัน", "🔑", padx=16)

        # --- ปุ่มลัดด่วน (ย้ายมาจากแผง TOOLS ของ Dashboard) --------------
        card_actions = _section("⚡  ใช้งานด่วน")
        r_actions = _row(card_actions, (10, 10))

        self.fetch_key_btn = tk.Button(
            r_actions,
            text="🔑 ดึงคีย์วันนี้",
            font=("Leelawadee UI", 11),
            bg=BG3,
            fg=STATUS_WARN,
            relief="flat",
            activebackground=BG4,
            cursor="hand2",
            command=self.open_daily_key_picker,
        )
        self.fetch_key_btn.pack(side="left", ipadx=10, ipady=6)
        _bind_button_hover(self.fetch_key_btn, BG3)

        self.manual_key_btn = tk.Button(
            r_actions,
            text="🎁 ส่งคีย์พิเศษเข้า Webhook",
            font=("Leelawadee UI", 11),
            bg=BG3,
            fg=ACC2,
            relief="flat",
            activebackground=BG4,
            cursor="hand2",
            command=self.open_manual_key_sender,
        )
        self.manual_key_btn.pack(side="left", padx=(8, 0), ipadx=10, ipady=6)
        _bind_button_hover(self.manual_key_btn, BG3)

        # --- ตั้งค่า Webhook (ย้ายมาจากการ์ด Discord Webhook ในแท็บตั้งค่า) --
        card_discord = _section("🔔  ปลายทาง Discord Webhook")

        r7_hdr = _row(card_discord, (8, 2))
        _lbl(r7_hdr, "Webhook URL")
        self.webhook_count_label = tk.Label(
            r7_hdr, text="0 ช่อง", font=("Leelawadee UI", 10), bg=BG2, fg=FG2
        )
        self.webhook_count_label.pack(side="left", padx=8)
        clear_wh_btn = tk.Button(
            r7_hdr,
            text="ล้างทั้งหมด",
            font=("Leelawadee UI", 10),
            bg=BG3,
            fg=DANGER,
            relief="flat",
            cursor="hand2",
            command=lambda: self._clear_all_webhooks(),
        )
        clear_wh_btn.pack(side="right", ipadx=8, ipady=2)
        _bind_button_hover(clear_wh_btn, BG3)
        add_wh_btn = tk.Button(
            r7_hdr,
            text="+ เพิ่ม Webhook",
            font=("Leelawadee UI", 10, "bold"),
            bg=GREEN,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=lambda: self._on_click_add_webhook(),
        )
        add_wh_btn.pack(side="right", ipadx=8, ipady=2, padx=(0, 6))
        _bind_button_hover(add_wh_btn, GREEN)

        self._webhook_rows = []
        self.webhook_rows_frame = tk.Frame(card_discord, bg=BG2)
        self.webhook_rows_frame.pack(fill="x", padx=16, pady=(2, 4))
        self._add_webhook_row()

        r7b = _row(card_discord, (4, 4))
        self._auto_daily_key_var = tk.BooleanVar(value=False)
        _tgl_daily_key, self._update_daily_key_toggle_visual = _make_toggle(
            r7b,
            self._auto_daily_key_var,
            "ดึงคีย์ประจำวันอัตโนมัติ (00:05) → ส่งเข้า Discord",
            command=self._toggle_daily_key_watcher,
            bg=BG2,
            fg=FG2,
        )
        _tgl_daily_key.pack(side="left", padx=(0, 6), pady=2)

        self._daily_key_countdown_lbl = tk.Label(
            r7b, text="", font=("Leelawadee UI", 9), bg=BG2, fg=INFO_BLUE
        )
        self._daily_key_countdown_lbl.pack(side="left", padx=(10, 0))
        self._update_daily_key_countdown()

        r7c = _row(card_discord, (0, 4))
        # คอลัมน์ label กว้างคงที่ — ให้ช่องกรอกของแถวนี้เสมอกับแถว 'ชื่อบอท' ด้านล่าง
        r7c.columnconfigure(0, minsize=110)
        r7c.columnconfigure(1, weight=1)
        tk.Label(
            r7c,
            text="URL รูปโปรไฟล์บอท",
            font=("Leelawadee UI", 10),
            bg=BG2,
            fg=FG2,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self.discord_avatar_entry = tk.Entry(
            r7c,
            highlightthickness=0,
            font=("Leelawadee UI", 9),
            width=52,
            bg=BG3,
            fg=FG2,
            insertbackground="white",
            relief="flat",
            bd=4,
        )
        self.discord_avatar_entry.grid(row=0, column=1, sticky="ew", padx=(4, 0), ipady=3)
        _bind_entry_context_menu(self.discord_avatar_entry)
        self.discord_avatar_entry.insert(
            0, "วางลิงก์รูป .jpg/.png ที่นี่ (เช่น https://i.imgur.com/xxx.jpg)"
        )
        self.discord_avatar_entry.bind(
            "<FocusIn>", lambda e: self._avatar_entry_focus_in()
        )
        self.discord_avatar_entry.bind(
            "<FocusOut>", lambda e: self._avatar_entry_focus_out()
        )
        self._avatar_placeholder_shown = True

        r7d = _row(card_discord, (0, 4))
        r7d.columnconfigure(0, minsize=110)
        r7d.columnconfigure(1, weight=1)
        tk.Label(
            r7d,
            text="ชื่อบอท",
            font=("Leelawadee UI", 10),
            bg=BG2,
            fg=FG2,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self.discord_botname_entry = tk.Entry(
            r7d,
            highlightthickness=0,
            font=("Leelawadee UI", 9),
            width=52,
            bg=BG3,
            fg=FG2,
            insertbackground="white",
            relief="flat",
            bd=4,
        )
        self.discord_botname_entry.grid(row=0, column=1, sticky="ew", padx=(4, 0), ipady=3)
        _bind_entry_context_menu(self.discord_botname_entry)
        self.discord_botname_entry.insert(0, f"ปล่อยว่าง = {_DISCORD_BOT_NAME}")
        self.discord_botname_entry.bind(
            "<FocusIn>", lambda e: self._botname_entry_focus_in()
        )
        self.discord_botname_entry.bind(
            "<FocusOut>", lambda e: self._botname_entry_focus_out()
        )
        self._botname_placeholder_shown = True

        r7test = _row(card_discord, (0, 10))
        test_wh_btn = tk.Button(
            r7test,
            text="ทดสอบส่งข้อความ (ส่งทุกช่อง)",
            font=("Leelawadee UI", 10),
            bg=BG3,
            fg=INFO_BLUE,
            relief="flat",
            cursor="hand2",
            command=self._test_discord_webhook,
        )
        test_wh_btn.pack(side="left", ipadx=8, ipady=3)
        _bind_button_hover(test_wh_btn, BG3)

        history_wh_btn = tk.Button(
            r7test,
            text="🗑 ข้อความที่เคยส่ง",
            font=("Leelawadee UI", 10),
            bg=BG3,
            fg=STATUS_WARN,
            relief="flat",
            cursor="hand2",
            command=self._open_webhook_history_window,
        )
        history_wh_btn.pack(side="left", padx=(6, 0), ipadx=8, ipady=3)
        _bind_button_hover(history_wh_btn, BG3)

        self._discord_test_lbl = tk.Label(
            r7test, text="", font=("Leelawadee UI", 10), bg=BG2, fg=STATUS_OK
        )
        self._discord_test_lbl.pack(side="left", padx=8)

        tk.Frame(dk_content, bg=BG, height=20).pack(fill="x")


__all__ = ["AppDailyKeyTabMixin"]
