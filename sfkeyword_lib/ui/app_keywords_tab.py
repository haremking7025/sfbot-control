"""The 'keywords' tab: keyword list header (add/load/clear) and the
scrollable keyword rows area.

แยกออกมาจาก AppCoreMixin._build_ui (เดิมยาว ~1,570 บรรทัดในเมธอดเดียว) ตาม
รูปแบบเดียวกับ _build_autoitem_tab ที่มีอยู่แล้วในโปรเจกต์
— โค้ดข้างในเหมือนเดิมทุกบรรทัด แค่ย้ายที่อยู่ ไม่มีการเปลี่ยน logic ใด ๆ"""

from ..core.constants import BG, BG2, BORDER, DANGER, FG2, GREEN, INFO_BLUE, STATUS_OK
from ..core.deps import tk, ttk
from ..core.ui_theme import _bind_button_hover, _page_header


class AppKeywordsTabMixin:
    def _build_keywords_tab(self, tab_kw):
        _page_header(tab_kw, "คีย์เวิร์ด", "▤", padx=16)
        frm_kw_hdr = tk.Frame(tab_kw, bg=BG)
        frm_kw_hdr.pack(fill="x", padx=16, pady=(2, 2))
        self.kw_count_label = tk.Label(
            frm_kw_hdr, text="0 คีย์เวิร์ด", font=("Leelawadee UI", 10), bg=BG, fg=FG2
        )
        self.kw_count_label.pack(side="left", padx=8)
        # dropdown เลือกไฟล์ .txt ที่เคยโหลด (เลือกแล้วโหลดคีย์เวิร์ดของไฟล์นั้น
        # มาแทนที่ลิสต์ปัจจุบัน — ดู _on_kw_file_selected ใน app_tables.py)
        # ครอบด้วย Frame วาดกรอบ static (สีไม่เปลี่ยนตอนโฟกัส) เพราะตัว combobox
        # ถูกถอด native field ออกแล้ว — วิธีเดียวกับแถวบัญชี (rows.py)
        kw_file_box = tk.Frame(
            frm_kw_hdr,
            bg=BG2,
            highlightthickness=1,
            highlightbackground="#2E313F",
            highlightcolor="#2E313F",
        )
        kw_file_box.pack(side="left", padx=(10, 0))
        self.kw_file_cb = ttk.Combobox(
            kw_file_box,
            state="readonly",
            style="Dark.TCombobox",
            font=("Leelawadee UI", 9),
            width=24,
        )
        self.kw_file_cb.pack(fill="both", expand=True, padx=1, pady=1)
        self.kw_file_cb.bind("<<ComboboxSelected>>", self._on_kw_file_selected)
        self._refresh_file_combobox(
            getattr(self, "_kw_recent_files", None) or [],
            "kw_file_cb",
            "_kw_file_cb_paths",
        )
        self._bind_file_cb_context_menu(
            self.kw_file_cb,
            "_kw_recent_files",
            "_kw_last_loaded_path",
            "kw_file_cb",
            "_kw_file_cb_paths",
        )
        clear_kw_btn = tk.Button(
            frm_kw_hdr,
            text="ล้างทั้งหมด",
            font=("Leelawadee UI", 10),
            bg=BG2,
            fg=DANGER,
            relief="flat",
            cursor="hand2",
            command=self._clear_all_keywords,
        )
        clear_kw_btn.pack(side="right", ipadx=8, ipady=3)
        _bind_button_hover(clear_kw_btn, BG2)
        load_kw_btn = tk.Button(
            frm_kw_hdr,
            text="โหลด .txt",
            font=("Leelawadee UI", 10),
            bg=BG2,
            fg=INFO_BLUE,
            relief="flat",
            cursor="hand2",
            command=self._load_keyword_file,
        )
        load_kw_btn.pack(side="right", ipadx=8, ipady=3, padx=4)
        _bind_button_hover(load_kw_btn, BG2)
        save_kw_btn = tk.Button(
            frm_kw_hdr,
            text="💾 บันทึก .txt",
            font=("Leelawadee UI", 10),
            bg=BG2,
            fg=STATUS_OK,
            relief="flat",
            cursor="hand2",
            command=self._save_keywords_file,
        )
        save_kw_btn.pack(side="right", ipadx=8, ipady=3, padx=4)
        _bind_button_hover(save_kw_btn, BG2)
        add_kw_btn = tk.Button(
            frm_kw_hdr,
            text="+ เพิ่มคีย์เวิร์ด",
            font=("Leelawadee UI", 10, "bold"),
            bg=GREEN,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=lambda: self._add_keyword_row(user_action=True),
        )
        add_kw_btn.pack(side="right", ipadx=8, ipady=3, padx=4)
        _bind_button_hover(add_kw_btn, GREEN)

        kw_outer = tk.Frame(
            tab_kw,
            bg=BG2,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            highlightthickness=1,
            takefocus=0,
        )
        kw_outer.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        kw_canvas = tk.Canvas(kw_outer, bg=BG2, highlightthickness=0)
        kw_sb = tk.Scrollbar(kw_outer, orient="vertical", command=kw_canvas.yview)
        kw_canvas.configure(yscrollcommand=kw_sb.set)
        kw_canvas.pack(side="left", fill="both", expand=True)
        # ซ่อนแถบเลื่อน - เลื่อนด้วยล้อเมาส์ได้ปกติผ่าน _bind_mousewheel ด้านล่าง
        self.kw_rows_frame = tk.Frame(kw_canvas, bg=BG2)
        self._kw_canvas_window = kw_canvas.create_window(
            (0, 0), window=self.kw_rows_frame, anchor="nw"
        )
        # debounce scrollregion update (กัน 750+ Configure events ตอนมีหลายแถว)
        self._kw_scroll_after = None
        def _kw_schedule_scroll():
            if self._kw_scroll_after is not None:
                kw_canvas.after_cancel(self._kw_scroll_after)
            self._kw_scroll_after = kw_canvas.after(50, _kw_update_scroll)
        def _kw_update_scroll():
            self._kw_scroll_after = None
            kw_canvas.configure(scrollregion=kw_canvas.bbox("all"))
        self.kw_rows_frame.bind("<Configure>", lambda e: _kw_schedule_scroll())
        _kw_last_width = [None]

        def _resize_kw_canvas(e):
            if e.width != _kw_last_width[0]:
                _kw_last_width[0] = e.width
                kw_canvas.itemconfig(self._kw_canvas_window, width=e.width)

        kw_canvas.bind("<Configure>", _resize_kw_canvas)
        self._bind_mousewheel(kw_canvas, self.kw_rows_frame)
        self.kw_canvas = kw_canvas
        self._add_keyword_row("KEYWORD1")


__all__ = ["AppKeywordsTabMixin"]
