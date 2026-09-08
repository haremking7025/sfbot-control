"""The 'settings' tab: login delay, run options, Discord Webhook config,
and the save/reset footer.

แยกออกมาจาก AppCoreMixin._build_ui ตามรูปแบบเดียวกับไฟล์ tab อื่น ๆ — โค้ด
ข้างในเหมือนเดิมทุกบรรทัด แค่ย้ายที่อยู่ ไม่มีการเปลี่ยน logic ใด ๆ ตรรกะการ
บันทึก/โหลด/รีเซ็ตค่าตั้งค่ายังอยู่ที่ AppSettingsMixin (app_settings.py) เดิม
— ไฟล์นี้มีแค่ส่วนสร้าง UI ของแท็บเท่านั้น (เหมือนที่ webhook.py แยกจาก
app_webhook_ui.py อยู่แล้ว)"""

from ..core.constants import (
    ACC2,
    BG,
    BG2,
    BG3,
    BORDER,
    FG2,
    FG3,
    FIXED_DELAY_SEC,
    FIXED_RETRY_COUNT,
    INFO_BLUE,
    LOGIN_DELAY_PRESETS,
    NETWORK_RETRY_BASE_SEC,
    STATUS_FAIL,
    STATUS_OK,
    STATUS_WARN,
)
from ..core.deps import tk, ttk
from ..core.ui_theme import (
    _ask_color,
    _bind_button_hover,
    _make_toggle,
    _page_header,
)
from ..engine.app_logging import (
    DEFAULT_ID_PALETTE,
    DEFAULT_LOG_COLORS,
    normalize_hex_color,
)


class AppSettingsTabMixin:
    def _build_settings_tab(self, tab_cfg):
        cfg_canvas = tk.Canvas(tab_cfg, bg=BG, highlightthickness=0)
        cfg_scrollbar = tk.Scrollbar(
            tab_cfg, orient="vertical", command=cfg_canvas.yview
        )
        cfg_canvas.pack(side="left", fill="both", expand=True)
        # ซ่อนแถบเลื่อน - เลื่อนด้วยล้อเมาส์ได้ปกติผ่าน _bind_mousewheel ด้านล่าง
        cfg_content = tk.Frame(cfg_canvas, bg=BG)
        cfg_window = cfg_canvas.create_window((0, 0), window=cfg_content, anchor="nw")

        def _cfg_frame_configure(e=None):
            cfg_canvas.configure(scrollregion=cfg_canvas.bbox("all"))

        cfg_content.bind("<Configure>", _cfg_frame_configure)
        cfg_canvas.configure(yscrollcommand=cfg_scrollbar.set)
        _cfg_last_width = [None]

        def _resize_cfg_canvas(e):
            if e.width != _cfg_last_width[0]:
                _cfg_last_width[0] = e.width
                cfg_canvas.itemconfig(cfg_window, width=e.width)

        cfg_canvas.bind("<Configure>", _resize_cfg_canvas)
        self._bind_mousewheel(cfg_canvas, cfg_content)

        def _section(title, parent=None):
            parent = parent or cfg_content
            inner = parent is not cfg_content
            hdr = tk.Frame(parent, bg=BG)
            hdr.pack(fill="x", padx=10 if inner else 20, pady=(10, 0))
            tk.Label(
                hdr, text=title, font=("Leelawadee UI", 9, "bold"), bg=BG, fg=ACC2
            ).pack(side="left")
            tk.Frame(hdr, bg=BORDER, height=1).pack(
                side="left", fill="x", expand=True, padx=(8, 0)
            )
            card = tk.Frame(
                parent,
                bg=BG2,
                highlightbackground=BORDER,
                highlightcolor=BORDER,
                highlightthickness=1,
                takefocus=0,
            )
            card.pack(fill="x", padx=10 if inner else 20, pady=(4, 0))
            return card

        def _row(parent, pady=(8, 4)):
            f = tk.Frame(parent, bg=BG2)
            f.pack(fill="x", padx=16, pady=pady)
            return f

        def _lbl(parent, text=""):
            lbl = tk.Label(
                parent,
                text=text,
                font=("Leelawadee UI", 10),
                bg=BG2,
                fg=FG2,
                anchor="w",
            )
            if text:
                lbl.pack(fill="x")  # แนวตั้ง — ป้ายชื่อเต็มบรรทัด
            return lbl

        _page_header(cfg_content, "การตั้งค่าบอท", "⚙", padx=20)

        # ── การ์ดบนจัด 2 คอลัมน์ (การเชื่อมต่อ | ตัวเลือก) — ย่อความสูงแท็บ ──
        _top_cols = tk.Frame(cfg_content, bg=BG)
        _top_cols.pack(fill="x")
        _col_l = tk.Frame(_top_cols, bg=BG)
        _col_l.pack(side="left", fill="x", expand=True)
        _col_r = tk.Frame(_top_cols, bg=BG)
        _col_r.pack(side="left", fill="x", expand=True)

        card_http = _section("🌐  การเชื่อมต่อ (HTTP — ไม่เปิด Chrome)", _col_l)
        # แนวตั้ง: ป้ายชื่อ → ช่องกรอก + ปุ่มใช้ค่า → toggle ใช้ค่าอัตโนมัติ
        r1a = _row(card_http, (12, 2))
        _lbl(r1a, "หน่วงระหว่างล็อกอิน (วินาที)")
        r1b = _row(card_http, (0, 2))
        # dropdown เลือกค่าได้เลย ไม่ต้องพิมพ์เอง (หน่วย = วินาที)
        self._login_delay_values = list(LOGIN_DELAY_PRESETS)
        self.version_entry = ttk.Combobox(
            r1b,
            values=self._login_delay_values,
            state="readonly",
            style="Dark.TCombobox",
            font=("Leelawadee UI", 11),
            width=6,
        )
        self.version_entry.set("0.1")
        self.version_entry.pack(side="left", ipady=3)
        self._apply_delay_btn = tk.Button(
            r1b,
            text="💾 ใช้ค่า",
            font=("Leelawadee UI", 10),
            bg=BG3,
            fg=INFO_BLUE,
            relief="flat",
            cursor="hand2",
            command=self._apply_login_delay,
        )
        self._apply_delay_btn.pack(side="left", padx=(10, 0), ipadx=8, ipady=3)
        _bind_button_hover(self._apply_delay_btn, BG3)
        self._auto_apply_delay_var = tk.BooleanVar(value=True)
        _tgl_autover, self._tgl_autover_update = _make_toggle(
            card_http,
            self._auto_apply_delay_var,
            "ใช้ค่าอัตโนมัติตอนเปิดโปรแกรม",
            command=lambda: self.log(
                f"🔧 ใช้ค่าอัตโนมัติตอนเปิดโปรแกรม → "
                f"{'✅ เปิด' if self._auto_apply_delay_var.get() else '⬜ ปิด'} — "
                f"โหลดค่าหน่วงระหว่างล็อกอินกลับมาใช้เองตอนเปิด ปิดถ้าอยากตั้งใหม่ทุกครั้ง"
            ),
            bg=BG2,
            fg=FG2,
        )
        _tgl_autover.pack(anchor="w", padx=16, pady=(2, 12))

        self._fixed_delay = FIXED_DELAY_SEC
        self._fixed_retry = FIXED_RETRY_COUNT
        self._network_retry_base_sec = NETWORK_RETRY_BASE_SEC

        card_opt = _section("⚙️  ตัวเลือก", _col_r)

        def _log_bool(var, label, explain=""):
            extra = f" — {explain}" if explain else ""
            self.log(
                f"🔧 ตั้งค่า '{label}' → {'✅ เปิด' if var.get() else '⬜ ปิด'}{extra}"
            )

        def _opt_toggle(var, label, command=None, explain=""):
            tgl, updater = _make_toggle(
                card_opt,
                var,
                label,
                command=(
                    command if command else (lambda: _log_bool(var, label, explain))
                ),
                bg=BG2,
                fg=FG2,
            )
            tgl.pack(anchor="w", padx=16, pady=(8, 0))
            return updater

        # เรียงลำดับความสำคัญจากบนลงล่าง
        # 1) แจ้งเตือนเมื่อเสร็จ — ใช้บ่อยแทบทุกรอบรัน
        self.notify_var = tk.BooleanVar(value=True)
        self._tgl_notify_update = _opt_toggle(
            self.notify_var,
            "แจ้งเตือนเมื่อเสร็จ",
            explain="ส่งเสียง/แจ้งเตือนถาดระบบเมื่อรันเสร็จ — เปิดไว้ไม่ต้องเฝ้าจอ",
        )

        # 2) ข้ามรายการที่ทำสำเร็จแล้ว — ลดงานซ้ำรอบถัดไป
        self._resume_var = tk.BooleanVar(value=True)
        self._tgl_resume_update = _opt_toggle(
            self._resume_var,
            "ข้ามรายการที่ทำสำเร็จแล้ว",
            explain="ไม่กรอกคีย์ซ้ำกับไอดีที่สำเร็จไปแล้ว — ลดงานซ้ำและกันคีย์ถูกใช้ซ้ำ",
        )

        # 3) เปิดพร้อมวินโดวส์ — เปิดคอมค้างไว้แล้วค่อยรัน (สำคัญน้อยสุด)
        self._start_with_windows_var = tk.BooleanVar(value=False)
        self._tgl_startup_update = _opt_toggle(
            self._start_with_windows_var,
            "เปิดพร้อมวินโดวส์ + ซ่อนอัตโนมัติ",
            command=self._on_toggle_start_with_windows,
        )
        # padding ด้านล่างการ์ดให้หายใจ
        tk.Frame(card_opt, bg=BG2, height=8).pack(fill="x")

        # ── 🎨 สี Log — ผู้ใช้เปลี่ยนสีของแต่ละหมวดได้เอง ใช้ทันทีทั้งหน้าจอ ──
        # แต่ละหมวด 1 บรรทัดเต็มการ์ด (ป้ายชื่อกว้างคงที่ → ปุ่มสี+hex เรียงตรงกัน
        # ทุกแถว ไม่มีข้างสั้นข้างยาว) — ย่อความสูงการ์ดจากเดิม 2 บรรทัด/หมวด
        card_log = _section("🎨  สี Log (เปลี่ยนได้ทันที)")
        self._log_color_rows = {}

        def _log_color_row(cat, label):
            row = tk.Frame(card_log, bg=BG2)
            row.pack(fill="x", padx=16, pady=(6, 2))
            tk.Label(
                row,
                text=label,
                width=36,
                font=("Leelawadee UI", 10),
                bg=BG2,
                fg=FG2,
                anchor="w",
            ).pack(side="left")
            color = self._log_colors.get(cat, DEFAULT_LOG_COLORS[cat])
            swatch = tk.Button(
                row,
                text="",
                width=2,
                bg=color,
                activebackground=color,
                relief="flat",
                cursor="hand2",
                command=lambda c=cat: self._pick_log_color(c),
            )
            swatch.pack(side="left", ipady=3, padx=(4, 6))
            hex_lbl = tk.Label(
                row,
                text=color,
                font=("Consolas", 10),
                bg=BG2,
                fg=color,
            )
            hex_lbl.pack(side="left")
            tk.Label(
                row,
                text="คลิกปุ่มสีเพื่อเลือก",
                font=("Leelawadee UI", 9),
                bg=BG2,
                fg=FG3,
            ).pack(side="right")
            self._log_color_rows[cat] = (swatch, hex_lbl)

        # เฉพาะหมวดที่เห็นบ่อยที่สุด — หมวดอื่นใช้สีเริ่มต้น (เรียงแนวตั้งเต็มการ์ด)
        _log_color_row("error", "Error — ผิดพลาด/ล้มเหลว")
        _log_color_row("warn", "คำเตือน ⚠")
        _log_color_row("success", "สำเร็จ ✅")
        _log_color_row("login", "ล็อกอิน 🔁")
        _log_color_row("keyword", "คีย์เวิร์ด 🗝")
        _log_color_row("cookie", "คุกกี้ 🍪")
        _log_color_row("system", "ข้อความทั่วไป")

        reset_row = _row(card_log, (6, 12))
        reset_log_btn = tk.Button(
            reset_row,
            text="↺ คืนสีเริ่มต้น",
            font=("Leelawadee UI", 10),
            bg=BG3,
            fg=STATUS_WARN,
            relief="flat",
            cursor="hand2",
            command=self._reset_log_colors,
        )
        reset_log_btn.pack(side="left", ipadx=10, ipady=4)
        _bind_button_hover(reset_log_btn, BG3)

        # ── โหมดสี: ตามหมวด vs ตามไอดี ──
        self._color_by_category_var = tk.BooleanVar(value=True)
        _tgl_colormode, self._tgl_color_mode_update = _make_toggle(
            card_log,
            self._color_by_category_var,
            "ระบายสีตามหมวด (Error/คำเตือน/สำเร็จ...)",
            command=self._on_toggle_color_by_category,
            bg=BG2,
            fg=FG2,
        )
        _tgl_colormode.pack(anchor="w", padx=16, pady=(2, 4))
        tk.Label(
            card_log,
            text="ปิด = แต่ละไอดีทาสีทั้งบรรทัด (โหมดเดิม ไล่ตามบัญชีง่ายขึ้น)",
            font=("Leelawadee UI", 9),
            bg=BG2,
            fg=FG3,
        ).pack(anchor="w", padx=28, pady=(0, 4))

        # ── สีประจำไอดี [username] — พาเล็ตที่ปรับเองได้ ──
        id_lbl_row = _row(card_log, (8, 2))
        _lbl(id_lbl_row, "สีประจำไอดี [username]")
        self._id_swatch_row_parent = tk.Frame(card_log, bg=BG2)
        self._id_swatch_row_parent.pack(fill="x", padx=16)
        self._id_color_rows = []
        for i in range(len(self._log_id_palette)):
            self._add_id_swatch(i)

        id_btn_row = _row(card_log, (2, 12))
        for text, fg, cmd in (
            ("➕ เพิ่มสี", STATUS_OK, self._add_id_color),
            ("➖ ลบสี", STATUS_FAIL, self._remove_id_color),
            ("↺ คืนค่าเริ่มต้น", STATUS_WARN, self._reset_id_palette),
        ):
            b = tk.Button(
                id_btn_row,
                text=text,
                font=("Leelawadee UI", 10),
                bg=BG3,
                fg=fg,
                relief="flat",
                cursor="hand2",
                command=cmd,
            )
            b.pack(side="left", ipadx=8, ipady=3, padx=(0, 6))
            _bind_button_hover(b, BG3)

        tk.Frame(cfg_content, bg=BG, height=20).pack(fill="x")
    def _pick_log_color(self, cat):
        """เปิดจานสีธีมเข้มของแอปให้เลือกสีหมวด log นั้น — เปลี่ยนทันทีทั้ง
        หน้าจอ (tag_config มีผลกับข้อความที่ tag ไว้แล้ว) + บันทึก settings
        (ใช้ _ask_color จานสีที่เขียนเอง แทน colorchooser ของ Windows ที่เป็น
        ธีมสว่าง/มีเส้นกรอบขัดกับแอป)"""
        try:
            current = self._log_colors.get(cat, DEFAULT_LOG_COLORS.get(cat, FG2))
            hex_color = _ask_color(
                getattr(self, "root", None),
                title=f"สี log — {cat}",
                initial=current,
                preset_cat=cat,
            )
        except Exception:
            hex_color = None
        if not hex_color:
            return
        hex_color = normalize_hex_color(hex_color, current)
        self._log_colors[cat] = hex_color
        self._apply_log_colors()
        self._refresh_log_color_row(cat)
        try:
            self._save_settings()
        except Exception:
            pass
        self.log(f"🎨 เปลี่ยนสี log '{cat}' → {hex_color} — มีผลทันทีและบันทึกแล้ว")

    def _refresh_log_color_row(self, cat):
        """อัปเดตปุ่มตัวอย่าง + ตัวเลข hex ในหน้าตั้งค่าให้ตรงกับสีที่ตั้งไว้"""
        row = getattr(self, "_log_color_rows", {}).get(cat)
        if not row:
            return
        swatch, hex_lbl = row
        color = self._log_colors.get(cat, DEFAULT_LOG_COLORS.get(cat, FG2))
        swatch.configure(bg=color, activebackground=color)
        hex_lbl.configure(text=color, fg=color)

    def _reset_log_colors(self):
        """คืนสี log ทุกหมวดเป็นค่าเริ่มต้น (DEFAULT_LOG_COLORS) ทันที + บันทึก"""
        self._log_colors = dict(DEFAULT_LOG_COLORS)
        self._apply_log_colors()
        for cat in list(getattr(self, "_log_color_rows", {})):
            self._refresh_log_color_row(cat)
        try:
            self._save_settings()
        except Exception:
            pass
        self.log("🎨 คืนสี log ทั้งหมดเป็นค่าเริ่มต้นแล้ว")

    # ── โหมดสีตามหมวด / สีตามไอดี ──

    def _on_toggle_color_by_category(self):
        """สลับโหมดสี log: เปิด = ทาสีตามหมวด / ปิด = ไอดีทาสีทั้งบรรทัด
        — วาด log ที่มีอยู่ใหม่ให้เป็นโหมดใหม่ทันที + บันทึก"""
        try:
            self._render_log_lines()
        except Exception:
            pass
        try:
            self._save_settings()
        except Exception:
            pass
        mode = (
            "ระบายสีตามหมวด"
            if self._color_by_category_var.get()
            else "สีตามไอดีทั้งบรรทัด"
        )
        self.log(f"🎨 โหมดสี log → {mode} — ใช้กับบรรทัดใหม่และวาดใหม่ทั้งช่องทันที")

    # ── สีประจำไอดี (พาเล็ต) ──

    def _add_id_swatch(self, idx):
        """สร้างปุ่มสวอตช์สีไอดีตำแหน่ง idx ในแถวพาเล็ต"""
        palette = self._log_id_palette
        color = palette[idx % len(palette)]
        sw = tk.Button(
            self._id_swatch_row_parent,
            text="",
            width=3,
            bg=color,
            activebackground=color,
            relief="flat",
            cursor="hand2",
            command=lambda i=idx: self._pick_id_color(i),
        )
        sw.pack(side="left", ipady=5, padx=(0, 4), pady=(0, 4))
        self._id_color_rows.append(sw)

    def _rebuild_id_color_rows(self):
        """สร้างแถวสวอตช์ไอดีใหม่ทั้งหมด (ใช้เมื่อจำนวนสีเปลี่ยน) — ทำลายของเก่าทิ้ง"""
        for sw in getattr(self, "_id_color_rows", []):
            try:
                sw.destroy()
            except Exception:
                pass
        self._id_color_rows = []
        for i in range(len(self._log_id_palette)):
            self._add_id_swatch(i)

    def _refresh_id_color_rows(self):
        """อัปเดตสีของปุ่มสวอตช์ให้ตรงกับพาเล็ตปัจจุบัน (จำนวนสีไม่เปลี่ยน)"""
        palette = self._log_id_palette
        for i, sw in enumerate(self._id_color_rows):
            color = palette[i % len(palette)]
            sw.configure(bg=color, activebackground=color)

    def _pick_id_color(self, idx):
        """เปิดจานสีธีมเข้มของแอปให้เปลี่ยนสีไอดีตำแหน่ง idx ในพาเล็ต"""
        try:
            palette = self._log_id_palette
            current = palette[idx % len(palette)]
            hex_color = _ask_color(
                getattr(self, "root", None),
                title=f"สีไอดี #{idx % len(palette) + 1}",
                initial=current,
            )
        except Exception:
            hex_color = None
        if not hex_color:
            return
        hex_color = normalize_hex_color(hex_color, current)
        palette[idx % len(palette)] = hex_color
        self._apply_id_palette()
        self._refresh_id_color_rows()
        try:
            self._save_settings()
        except Exception:
            pass
        self.log(f"🎨 เปลี่ยนสีไอดี #{(idx % len(palette)) + 1} → {hex_color} — มีผลทันที")

    def _add_id_color(self):
        """เพิ่มสีในพาเล็ตไอดี (สูงสุด 24 สี)"""
        if len(self._log_id_palette) >= 24:
            self.log("🎨 สีไอดีเต็มแล้ว (สูงสุด 24 สี)")
            return
        self._log_id_palette.append(ACC2)
        self._rebuild_id_color_rows()
        self._apply_id_palette()
        try:
            self._save_settings()
        except Exception:
            pass
        self.log(f"🎨 เพิ่มสีไอดีแล้ว — พาเล็ตมี {len(self._log_id_palette)} สี")

    def _remove_id_color(self):
        """ลบสีสุดท้ายของพาเล็ตไอดี (ต้องเหลืออย่างน้อย 1 สี)"""
        if len(self._log_id_palette) <= 1:
            self.log("🎨 ลบสีไอดีไม่ได้ — ต้องเหลืออย่างน้อย 1 สี")
            return
        self._log_id_palette.pop()
        self._rebuild_id_color_rows()
        self._apply_id_palette()
        try:
            self._save_settings()
        except Exception:
            pass
        self.log(f"🎨 ลบสีไอดีแล้ว — เหลือ {len(self._log_id_palette)} สี")

    def _reset_id_palette(self):
        """คืนพาเล็ตสีไอดีเป็นค่าเริ่มต้น (DEFAULT_ID_PALETTE) ทันที + บันทึก"""
        self._log_id_palette = list(DEFAULT_ID_PALETTE)
        self._rebuild_id_color_rows()
        self._apply_id_palette()
        try:
            self._save_settings()
        except Exception:
            pass
        self.log("🎨 คืนสีไอดีเป็นค่าเริ่มต้นแล้ว")


__all__ = ["AppSettingsTabMixin"]
