"""The 'accounts' tab: account list header (add/load/clear/show-password),
column header row, scrollable account rows, and save footer.

แยกออกมาจาก AppCoreMixin._build_ui ตามรูปแบบเดียวกับไฟล์ tab อื่น ๆ — โค้ด
ข้างในเหมือนเดิมทุกบรรทัด แค่ย้ายที่อยู่ ไม่มีการเปลี่ยน logic ใด ๆ"""

from ..core.constants import (
    ACC2,
    BG,
    BG2,
    BORDER,
    COL_NUM,
    COL_PWD,
    COL_RANK,
    COL_TYPE,
    COL_UNIT,
    COL_UNIT2,
    COL_USER,
    DANGER,
    FG2,
    GREEN,
    INFO_BLUE,
    STATUS_OK,
)
from ..core.deps import tk, ttk
from ..core.ui_theme import _bind_button_hover, _make_toggle, _page_header


class AppAccountsTabMixin:
    def _build_accounts_tab(self, tab_acc):
        _page_header(tab_acc, "บัญชี", "◉", padx=16)
        frm_acc_hdr = tk.Frame(tab_acc, bg=BG)
        frm_acc_hdr.pack(fill="x", padx=16, pady=(2, 2))
        self.acc_count_label = tk.Label(
            frm_acc_hdr, text="0 ไอดี", font=("Leelawadee UI", 10), bg=BG, fg=FG2
        )
        self.acc_count_label.pack(side="left", padx=8)
        # dropdown เลือกไฟล์ .txt ที่เคยโหลด (เลือกแล้วโหลดบัญชีของไฟล์นั้นมา
        # แทนที่ลิสต์ปัจจุบัน — ดู _on_acc_file_selected ใน app_tables.py)
        # ครอบด้วย Frame วาดกรอบ static (สีไม่เปลี่ยนตอนโฟกัส) เพราะตัว combobox
        # ถูกถอด native field ออกแล้ว — วิธีเดียวกับแถวบัญชี (rows.py)
        acc_file_box = tk.Frame(
            frm_acc_hdr,
            bg=BG2,
            highlightthickness=1,
            highlightbackground="#2E313F",
            highlightcolor="#2E313F",
        )
        acc_file_box.pack(side="left", padx=(10, 0))
        self.acc_file_cb = ttk.Combobox(
            acc_file_box,
            state="readonly",
            style="Dark.TCombobox",
            font=("Leelawadee UI", 9),
            width=24,
        )
        self.acc_file_cb.pack(fill="both", expand=True, padx=1, pady=1)
        self.acc_file_cb.bind("<<ComboboxSelected>>", self._on_acc_file_selected)
        self._refresh_file_combobox(
            getattr(self, "_acc_recent_files", None) or [],
            "acc_file_cb",
            "_acc_file_cb_paths",
        )
        self._bind_file_cb_context_menu(
            self.acc_file_cb,
            "_acc_recent_files",
            "_acc_last_loaded_path",
            "acc_file_cb",
            "_acc_file_cb_paths",
        )

        self._show_pwd = tk.BooleanVar(value=False)
        _tgl_pwd, _ = _make_toggle(
            frm_acc_hdr,
            self._show_pwd,
            "แสดงรหัสผ่าน",
            command=self._toggle_pwd_mask,
            bg=BG,
            fg=FG2,
            eye_mode=True,
        )
        _tgl_pwd.pack(side="left", padx=(10, 0))

        clear_acc_btn = tk.Button(
            frm_acc_hdr,
            text="ล้างทั้งหมด",
            font=("Leelawadee UI", 10),
            bg=BG2,
            fg=DANGER,
            relief="flat",
            cursor="hand2",
            command=self._clear_all,
        )
        clear_acc_btn.pack(side="right", ipadx=8, ipady=3)
        _bind_button_hover(clear_acc_btn, BG2)
        load_acc_btn = tk.Button(
            frm_acc_hdr,
            text="โหลด .txt",
            font=("Leelawadee UI", 10),
            bg=BG2,
            fg=INFO_BLUE,
            relief="flat",
            cursor="hand2",
            command=self._load_file,
        )
        load_acc_btn.pack(side="right", ipadx=8, ipady=3, padx=4)
        _bind_button_hover(load_acc_btn, BG2)
        add_acc_btn = tk.Button(
            frm_acc_hdr,
            text="+ เพิ่มบัญชี",
            font=("Leelawadee UI", 10, "bold"),
            bg=GREEN,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self._on_click_add_row,
        )
        add_acc_btn.pack(side="right", ipadx=8, ipady=3, padx=4)
        _bind_button_hover(add_acc_btn, GREEN)

        apply_all_btn = tk.Button(
            frm_acc_hdr,
            text="ใช้แรงค์/หน่วยกับทุกบัญชี",
            font=("Leelawadee UI", 9),
            bg=BG2,
            fg=ACC2,
            relief="flat",
            cursor="hand2",
            command=self._apply_selection_to_all_accounts,
        )
        apply_all_btn.pack(side="right", ipadx=8, ipady=3, padx=4)
        _bind_button_hover(apply_all_btn, BG2)
        preview_btn = tk.Button(
            frm_acc_hdr,
            text="ดู Preview",
            font=("Leelawadee UI", 9),
            bg=BG2,
            fg=INFO_BLUE,
            relief="flat",
            cursor="hand2",
            command=self._preview_account_selections,
        )
        preview_btn.pack(side="right", ipadx=8, ipady=3, padx=4)
        _bind_button_hover(preview_btn, BG2)

        col_hdr = tk.Frame(tab_acc, bg=BG, height=32)
        col_hdr.pack(fill="x", padx=16)
        col_hdr.pack_propagate(False)
        for txt, w, px in [
            ("#", COL_NUM, 0),
            ("ไอดี", COL_USER, 2),
            ("รหัสผ่าน", COL_PWD, 2),
            ("ประเภทไอดี", COL_TYPE, 2),
            ("แรงค์", COL_RANK, 2),
            ("หน่วย 1", COL_UNIT, 2),
        ]:
            box = tk.Frame(col_hdr, width=w, height=32, bg=BG)
            box.pack_propagate(False)
            box.pack(side="left", padx=px)
            tk.Label(
                box, text=txt, font=("Leelawadee UI", 10, "bold"), bg=BG, fg=FG2, anchor="w"
            ).pack(side="left", fill="x", expand=True, padx=(4, 0), pady=6)

        unit2_hdr_box = tk.Frame(col_hdr, width=COL_UNIT2, height=32, bg=BG)
        unit2_hdr_box.pack_propagate(False)
        unit2_hdr_box.pack(side="left", padx=2)
        unit2_hdr_inner = tk.Frame(unit2_hdr_box, bg=BG)
        unit2_hdr_inner.pack(side="left", fill="x", expand=True, padx=(4, 0), pady=6)
        tk.Label(
            unit2_hdr_inner,
            text="หน่วย 2 (สำรอง)",
            font=("Leelawadee UI", 10, "bold"),
            bg=BG,
            fg=FG2,
            anchor="w",
        ).pack(side="left")

        acc_outer = tk.Frame(
            tab_acc,
            bg=BG2,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            highlightthickness=1,
            takefocus=0,
        )
        acc_outer.pack(fill="both", expand=True, padx=16, pady=(2, 10))
        acc_canvas = tk.Canvas(acc_outer, bg=BG2, highlightthickness=0)
        acc_sb = tk.Scrollbar(acc_outer, orient="vertical", command=acc_canvas.yview)
        acc_canvas.configure(yscrollcommand=acc_sb.set)
        acc_canvas.pack(side="left", fill="both", expand=True)
        # ซ่อนแถบเลื่อน - เลื่อนด้วยล้อเมาส์ได้ปกติผ่าน _bind_mousewheel ด้านล่าง
        self.rows_frame = tk.Frame(acc_canvas, bg=BG2)
        self._canvas_window = acc_canvas.create_window(
            (0, 0), window=self.rows_frame, anchor="nw"
        )
        # debounce: 50 rows × 15 widgets = 750 Configure events →
        # อัปเดต scrollregion แค่ครั้งเดียวทุก 50ms (after cancel+reschedule)
        self._scroll_after = None
        def _schedule_scroll():
            if self._scroll_after is not None:
                acc_canvas.after_cancel(self._scroll_after)
            self._scroll_after = acc_canvas.after(50, _update_scroll)
        def _update_scroll():
            self._scroll_after = None
            acc_canvas.configure(scrollregion=acc_canvas.bbox("all"))
        self.rows_frame.bind("<Configure>", lambda e: _schedule_scroll())
        _acc_last_width = [None]

        def _resize_acc_canvas(e):
            # ให้แถวบัญชีขยายตามความกว้างจริงของเนื้อหา (คอลัมน์+ปุ่มท้ายแถว)
            # ถ้ากว้างกว่าหน้าต่าง — ไม่งั้น canvas คิดว่าไม่มีเนื้อหาล้นแนวนอน
            # เลื่อน Shift+ล้อเมาส์ไม่ได้เลย (xview ตายตัวที่ 0.0–1.0)
            target = max(e.width, self.rows_frame.winfo_reqwidth())
            if target != _acc_last_width[0]:
                _acc_last_width[0] = target
                acc_canvas.itemconfig(self._canvas_window, width=target)

        acc_canvas.bind("<Configure>", _resize_acc_canvas)
        # Shift+ล้อเมาส์ = เลื่อนแนวนอน ดูปุ่มท้ายแถว (🔁/✕) ตอนย่อหน้าต่างเล็ก —
        # ทำงานอยู่ใน _bind_mousewheel (app_core.py) เพราะ Windows ส่ง wheel event
        # มาเป็น <MouseWheel> อย่างเดียว ไม่มี <Shift-MouseWheel> แยกต่างหาก
        self._bind_mousewheel(acc_canvas, self.rows_frame)
        self.main_canvas = acc_canvas
        self._add_row()

        frm_acc_foot = tk.Frame(tab_acc, bg=BG)
        frm_acc_foot.pack(fill="x", padx=16, pady=(0, 10))
        save_btn = tk.Button(
            frm_acc_foot,
            text="💾 บันทึก",
            font=("Leelawadee UI", 10, "bold"),
            bg=GREEN,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self.manual_save,
        )
        save_btn.pack(side="right", ipadx=10, ipady=3)
        _bind_button_hover(save_btn, GREEN)
        self.save_lbl = tk.Label(
            frm_acc_foot, text="", font=("Leelawadee UI", 10), bg=BG, fg=STATUS_OK
        )
        self.save_lbl.pack(side="right", padx=8)


__all__ = ["AppAccountsTabMixin"]
