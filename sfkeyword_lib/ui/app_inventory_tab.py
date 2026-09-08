"""The 'ฝาก/เบิก' tab (TDP Inventory) — UI half: widgets + account row
CRUD (add/remove/load-from-file/counts). Engine half lives in
app_inventory_engine.py.

โครงสร้างลอกแบบแท็บ 'รับไอเทมฟรี' (app_autoitem_ui.py) แต่ตัด webhook /
เปิดอัตโนมัติ 00:05 ออก เหลือ: ปุ่มฝากทั้งหมด / เบิกทั้งหมด + รายการบัญชีของ
แท็บนี้เอง (แยกจากระบบรันหลัก)
"""

import logging

from ..core.constants import (
    ACC,
    ACC2,
    BG,
    BG2,
    BORDER,
    COL_NUM,
    COL_PWD,
    COL_TYPE,
    COL_USER,
    CONCURRENCY_PRESETS,
    DANGER,
    FG,
    FG2,
    GREEN,
    INFO_BLUE,
    STATUS_ACTIVE,
    STATUS_OK,
    STATUS_WARN,
)
from ..core.deps import os, tk, ttk
from ..core.inventory_flow import (
    INV_CATEGORIES,
    inv_category_options,
    item_can_deposit,
    item_can_withdraw,
    item_detail_lines,
    item_display_name,
    item_in_category,
    item_summary_line,
)
from ..core.rows import AccountRow
from ..core.ui_theme import (
    _bind_button_hover,
    _bind_combobox_wheel_local,
    _bind_entry_context_menu,
    _center_window_on_parent,
    _make_toggle,
    _page_header,
)

_logger = logging.getLogger(__name__)

_INV_STATUS_COL = 200


class AppInventoryUIMixin:
    def _build_inventory_tab(self, parent):
        outer = tk.Frame(parent, bg=BG)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0, bd=0)
        vsb = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        self._inv_canvas = canvas
        inner = tk.Frame(canvas, bg=BG)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        _last_width = [None]

        def _on_canvas_resize(e):
            if e.width != _last_width[0]:
                _last_width[0] = e.width
                canvas.itemconfig(inner_id, width=e.width)

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_resize)
        self._bind_mousewheel(canvas, inner)

        _page_header(inner, "ฝาก/เบิก", "📦", bg=BG, acc=ACC, border=BORDER)

        pad = {"padx": 16, "pady": (0, 10)}

        def _section(title):
            card = tk.Frame(inner, bg=BG2, bd=0, relief="flat")
            card.pack(fill="x", **pad)
            tk.Label(
                card, text=title, font=("Leelawadee UI", 9, "bold"), bg=BG2, fg=ACC2
            ).pack(anchor="w", padx=14, pady=(10, 4))
            tk.Frame(card, bg=BORDER, height=1).pack(fill="x", padx=14, pady=(0, 6))
            return card

        def _row(parent, pady=(4, 2)):
            f = tk.Frame(parent, bg=BG2)
            f.pack(fill="x", padx=14, pady=pady)
            return f

        card_top = _section("📦  ฝาก / เบิก (TDP Inventory บน member.sf.in.th)")
        r_top = _row(card_top, (8, 4))
        self._inv_status_lbl = tk.Label(
            r_top,
            text="พร้อมทำงาน — ล็อกอินเหมือนรอบรับคีย์ แล้วไปที่หน้า Inventory",
            font=("Leelawadee UI", 10),
            bg=BG2,
            fg=FG2,
        )
        self._inv_status_lbl.pack(side="left")

        self._inv_btn_dep = tk.Button(
            r_top,
            text="📥 ฝากทั้งหมด",
            font=("Leelawadee UI", 10, "bold"),
            bg=GREEN,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self._inv_deposit_all,
            padx=12,
            pady=3,
        )
        self._inv_btn_dep.pack(side="right", padx=(8, 0))
        _bind_button_hover(self._inv_btn_dep, GREEN)

        r_cat = tk.Frame(r_top, bg=BG2)
        r_cat.pack(side="right", padx=(8, 0))
        tk.Label(
            r_cat, text="หมวด", font=("Leelawadee UI", 10), bg=BG2, fg=FG2
        ).pack(side="left")
        self._inv_cat_var = tk.StringVar(value="ทั้งหมด")
        _cat = ttk.Combobox(
            r_cat,
            values=INV_CATEGORIES,
            textvariable=self._inv_cat_var,
            state="readonly",
            style="Dark.TCombobox",
            font=("Leelawadee UI", 10),
            width=24,
        )
        _cat.pack(side="left", padx=(6, 0))
        _bind_combobox_wheel_local(_cat)
        self._inv_cat_combo = _cat

        self._inv_btn_wd = tk.Button(
            r_top,
            text="📤 เบิกทั้งหมด",
            font=("Leelawadee UI", 10, "bold"),
            bg=STATUS_WARN,
            fg="#1A1A1A",
            relief="flat",
            cursor="hand2",
            command=self._inv_withdraw_all,
            padx=12,
            pady=3,
        )
        self._inv_btn_wd.pack(side="right", padx=(8, 0))
        _bind_button_hover(self._inv_btn_wd, STATUS_WARN)

        r_conc = tk.Frame(r_top, bg=BG2)
        r_conc.pack(side="right", padx=(8, 0))
        tk.Label(
            r_conc, text="พร้อมกัน", font=("Leelawadee UI", 10), bg=BG2, fg=FG2
        ).pack(side="left")
        self._inv_concurrency_var = tk.StringVar(value="8")
        ttk.Combobox(
            r_conc,
            values=CONCURRENCY_PRESETS,
            textvariable=self._inv_concurrency_var,
            style="Dark.TCombobox",
            font=("Consolas", 10),
            width=4,
        ).pack(side="left", padx=(6, 0))

        card_acc = _section("👤  บัญชีที่ใช้ฝาก/เบิก (แยกจากระบบรันหลัก)")
        r_acc_hdr = _row(card_acc, (8, 2))
        self._inv_count_lbl = tk.Label(
            r_acc_hdr, text="[0 ไอดี]", font=("Leelawadee UI", 10), bg=BG2, fg=FG2
        )
        self._inv_count_lbl.pack(side="left")

        inv_file_box = tk.Frame(
            r_acc_hdr,
            bg=BG2,
            highlightthickness=1,
            highlightbackground="#2E313F",
            highlightcolor="#2E313F",
        )
        inv_file_box.pack(side="left", padx=(10, 0))
        self.inv_file_cb = ttk.Combobox(
            inv_file_box,
            state="readonly",
            style="Dark.TCombobox",
            font=("Leelawadee UI", 9),
            width=24,
        )
        self.inv_file_cb.pack(fill="both", expand=True, padx=1, pady=1)
        self.inv_file_cb.bind("<<ComboboxSelected>>", self._on_inv_file_selected)
        self._refresh_file_combobox(
            getattr(self, "_inv_recent_files", None) or [],
            "inv_file_cb",
            "_inv_file_cb_paths",
        )
        self._bind_file_cb_context_menu(
            self.inv_file_cb,
            "_inv_recent_files",
            "_inv_last_loaded_path",
            "inv_file_cb",
            "_inv_file_cb_paths",
        )

        self._inv_show_pwd = tk.BooleanVar(value=False)
        _tgl_pwd, _ = _make_toggle(
            r_acc_hdr,
            self._inv_show_pwd,
            "แสดงรหัสผ่าน",
            command=self._inv_toggle_pwd_mask,
            bg=BG2,
            fg=FG2,
            eye_mode=True,
        )
        _tgl_pwd.pack(side="left", padx=(10, 0))

        btn_clear = tk.Button(
            r_acc_hdr,
            text="ล้างทั้งหมด",
            font=("Leelawadee UI", 10),
            bg=BG2,
            fg=DANGER,
            relief="flat",
            cursor="hand2",
            command=self._inv_clear_acc,
            padx=8,
            pady=2,
        )
        btn_clear.pack(side="right")
        _bind_button_hover(btn_clear, BG2)
        btn_load = tk.Button(
            r_acc_hdr,
            text="โหลด .txt",
            font=("Leelawadee UI", 10),
            bg=BG2,
            fg=INFO_BLUE,
            relief="flat",
            cursor="hand2",
            command=self._inv_load_file,
            padx=8,
            pady=2,
        )
        btn_load.pack(side="right", padx=(0, 6))
        _bind_button_hover(btn_load, BG2)
        btn_add = tk.Button(
            r_acc_hdr,
            text="+ เพิ่มบัญชี",
            font=("Leelawadee UI", 10, "bold"),
            bg=GREEN,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=lambda: self._inv_add_acc(user_action=True),
            padx=8,
            pady=2,
        )
        btn_add.pack(side="right", padx=(0, 6))
        _bind_button_hover(btn_add, GREEN)

        r_acc_col = _row(card_acc, (2, 0))
        for txt, w, px in [
            ("#", COL_NUM, 0),
            ("ไอดี", COL_USER, 2),
            ("รหัสผ่าน", COL_PWD, 2),
            ("ประเภทไอดี", COL_TYPE, 2),
            ("สถานะ", _INV_STATUS_COL, 2),
        ]:
            box = tk.Frame(r_acc_col, width=w, height=32, bg=BG2)
            box.pack_propagate(False)
            box.pack(side="left", padx=px)
            tk.Label(
                box,
                text=txt,
                font=("Leelawadee UI", 10, "bold"),
                bg=BG2,
                fg=FG2,
                anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=(4, 0), pady=6)

        self._inv_rows = []
        self._inv_acc_frame = tk.Frame(card_acc, bg=BG2)
        self._inv_acc_frame.pack(fill="x", padx=14, pady=(2, 8))
        tk.Label(
            inner,
            text=(
                "หมายเหตุ: ฝาก = เก็บไอเทมถาวรที่ยังอยู่ที่ตัวเข้าระบบฝาก "
                "· เบิก = ดึงไอเทมที่ฝากไว้ออกมา — รอบเดียวจะล็อกอินบัญชีแล้วทำตามปุ่มที่กด"
            ),
            font=("Leelawadee UI", 9),
            bg=BG,
            fg=FG2,
            anchor="w",
            justify="left",
            wraplength=900,
        ).pack(fill="x", padx=18, pady=(0, 14))

        self._inv_busy = False
        self._inv_add_acc()

    # ------------------------------------------------------------------
    # account row CRUD
    # ------------------------------------------------------------------
    def _inv_add_acc(self, user="", pwd="", login_type="Game ID", user_action=False):
        AccountRow._ensure_styles()
        BG_ROW, ENT, _FG, DIM = BG2, BG, FG, FG2
        idx = len(self._inv_rows) + 1
        frm = tk.Frame(self._inv_acc_frame, bg=BG_ROW)
        frm.pack(fill="x", pady=2)

        user_var = tk.StringVar(value=user)
        pwd_var = tk.StringVar(value=pwd)
        type_var = tk.StringVar(value=login_type)

        def _box(width, height=34):
            b = tk.Frame(frm, width=width, height=height, bg=BG_ROW)
            b.pack_propagate(False)
            b.pack(side="left", padx=2)
            return b

        idx_box = _box(COL_NUM, 34)
        idx_lbl = tk.Label(
            idx_box,
            text=f"{idx}.",
            anchor="w",
            font=("Consolas", 11),
            bg=BG_ROW,
            fg=DIM,
        )
        idx_lbl.pack(fill="both", expand=True, padx=(4, 0))

        user_box = _box(COL_USER, 34)
        user_entry = tk.Entry(
            user_box,
            highlightthickness=0,
            textvariable=user_var,
            font=("Leelawadee UI", 10),
            bg=ENT,
            fg=_FG,
            insertbackground="white",
            relief="flat",
            bd=1,
        )
        user_entry.pack(fill="both", expand=True, ipady=4, padx=1, pady=1)
        _bind_entry_context_menu(user_entry)
        user_var.trace_add("write", lambda *_: self._inv_update_acc_count())

        pwd_box = _box(COL_PWD, 34)
        pwd_entry = tk.Entry(
            pwd_box,
            highlightthickness=0,
            textvariable=pwd_var,
            font=("Leelawadee UI", 10),
            bg=ENT,
            fg=DIM,
            insertbackground="white",
            relief="flat",
            bd=1,
            show="•",
        )
        pwd_entry.pack(fill="both", expand=True, ipady=4, padx=1, pady=1)
        _bind_entry_context_menu(pwd_entry)
        pwd_var.trace_add("write", lambda *_: self._inv_update_acc_count())

        type_box = _box(COL_TYPE, 34)
        _locked = bool(getattr(self, "_inv_busy", False))
        type_cb = ttk.Combobox(
            type_box,
            textvariable=type_var,
            values=["Game ID", "GG Passport"],
            state=("disabled" if _locked else "readonly"),
            font=("Leelawadee UI", 10),
            style="AccType.GameID.TCombobox"
            if login_type == "Game ID"
            else "AccType.IGG.TCombobox",
        )
        type_cb.pack(fill="both", expand=True)

        def _on_type_change(_evt=None):
            type_cb.configure(
                style="AccType.GameID.TCombobox"
                if type_var.get() == "Game ID"
                else "AccType.IGG.TCombobox"
            )
            type_cb.selection_clear()
            type_cb.icursor(0)
            self._save_settings()

        type_cb.bind("<<ComboboxSelected>>", _on_type_change)
        _bind_combobox_wheel_local(type_cb)

        status_box = _box(_INV_STATUS_COL, 34)
        status_lbl = tk.Label(
            status_box,
            text="พร้อมทำงาน",
            anchor="w",
            font=("Leelawadee UI", 9),
            bg=BG_ROW,
            fg=FG2,
        )
        status_lbl.pack(fill="both", expand=True, padx=(4, 0))

        def open_picker():
            self._inv_open_item_picker(row_data)

        view_btn = tk.Button(
            frm,
            text="👁 ดู/เลือกไอเทม",
            font=("Leelawadee UI", 9),
            bg=BG_ROW,
            fg=ACC2,
            relief="flat",
            cursor="hand2",
            command=open_picker,
        )
        view_btn.pack(side="left", padx=(0, 2))
        _bind_button_hover(view_btn, BG_ROW)

        def delete():
            self._inv_rows.remove(row_data)
            frm.destroy()
            self._inv_reindex()
            self._inv_update_acc_count()
            self.log(f"🗑 ลบบัญชีฝาก/เบิก (เหลือ {len(self._inv_rows)} บัญชี)")

        del_btn = tk.Button(
            frm,
            text="✕",
            font=("Leelawadee UI", 9),
            bg=BG_ROW,
            fg=DANGER,
            relief="flat",
            cursor="hand2",
            command=delete,
        )
        del_btn.pack(side="left", padx=4)
        _bind_button_hover(del_btn, BG_ROW)

        row_data = {
            "frm": frm,
            "idx_lbl": idx_lbl,
            "user": user_var,
            "pwd": pwd_var,
            "type": type_var,
            "pwd_entry": pwd_entry,
            "type_cb": type_cb,
            "status_lbl": status_lbl,
            "view_btn": view_btn,
        }
        self._inv_rows.append(row_data)
        if getattr(self, "_inv_show_pwd", None) and self._inv_show_pwd.get():
            pwd_entry.configure(show="", fg=FG)
        self._inv_update_acc_count()
        if user_action:
            self.log(
                f"➕ เพิ่มบัญชีฝาก/เบิก #{idx} (รวม {len(self._inv_rows)} บัญชี)"
            )

    def _inv_reindex(self):
        for i, r in enumerate(self._inv_rows, 1):
            r["idx_lbl"].configure(text=f"{i}.")

    def _inv_update_acc_count(self, *_):
        valid = len(self._inv_valid_accounts())
        lbl = getattr(self, "_inv_count_lbl", None)
        if lbl:
            lbl.configure(text=f"[{valid} ไอดี]", fg=STATUS_ACTIVE if valid else "#888")

    def _inv_valid_accounts(self):
        return [
            r
            for r in self._inv_rows
            if r["user"].get().strip() and r["pwd"].get().strip()
        ]

    def _inv_toggle_pwd_mask(self):
        visible = self._inv_show_pwd.get()
        for r in self._inv_rows:
            entry = r.get("pwd_entry")
            if entry:
                entry.configure(show="" if visible else "•", fg=FG if visible else FG2)
        self.log(
            f"{'👁 แสดง' if visible else '🙈 ซ่อน'}รหัสผ่านบัญชีฝาก/เบิก "
            f"({len(self._inv_rows)} บัญชี)"
        )

    def _inv_clear_acc(self, silent=False):
        n = len(self._inv_rows)
        for r in self._inv_rows:
            r["frm"].destroy()
        self._inv_rows.clear()
        self._inv_update_acc_count()
        self._inv_last_loaded_path = None
        self._refresh_file_combobox(
            getattr(self, "_inv_recent_files", None) or [],
            "inv_file_cb",
            "_inv_file_cb_paths",
        )
        if not silent:
            self.log(f"🗑 ล้างบัญชีฝาก/เบิกทั้งหมด ({n} บัญชี)")

    def _inv_load_file(self):
        from ..core.deps import filedialog

        path = filedialog.askopenfilename(
            title="เลือกไฟล์บัญชี (.txt)",
            filetypes=[("ไฟล์ข้อความ", "*.txt"), ("ทั้งหมด", "*.*")],
        )
        if not path:
            return
        try:
            parsed = self._read_account_file_rows(path)
            existing = {
                r["user"].get().strip()
                for r in self._inv_rows
                if r["user"].get().strip()
            }
            added, skipped = 0, 0
            for u, p, t in parsed:
                if u in existing:
                    skipped += 1
                    continue
                self._inv_add_acc(u, p, t)
                existing.add(u)
                added += 1
            self._remember_recent_file(
                path,
                "_inv_recent_files",
                "_inv_last_loaded_path",
                "inv_file_cb",
                "_inv_file_cb_paths",
            )
            msg = f" โหลด {added} บัญชี (ฝาก/เบิก) จาก: {path}"
            if skipped:
                msg += f" (ข้ามซ้ำ {skipped} บัญชี)"
            self.log(msg)
        except Exception as e:
            self._alert_error("ข้อผิดพลาด", f"โหลดไฟล์ไม่ได้: {e}")

    def _on_inv_file_selected(self, _evt=None):
        cb = getattr(self, "inv_file_cb", None)
        paths = getattr(self, "_inv_file_cb_paths", None) or []
        if cb is None:
            return
        idx = cb.current()
        if idx < 0 or idx >= len(paths):
            return
        path = paths[idx]
        if not os.path.exists(path):
            self._remove_recent_file(
                path,
                "_inv_recent_files",
                "_inv_last_loaded_path",
                "inv_file_cb",
                "_inv_file_cb_paths",
            )
            self._alert_error("ข้อผิดพลาด", f"ไม่พบไฟล์: {path}")
            return
        try:
            parsed = self._read_account_file_rows(path)
        except Exception as e:
            self._alert_error("ข้อผิดพลาด", f"โหลดไฟล์ไม่ได้: {e}")
            return
        current = self._inv_valid_accounts()
        if current and getattr(self, "_inv_last_loaded_path", None) != path:
            if not self._confirm_dialog(
                "แทนที่บัญชีฝาก/เบิก",
                lines=[
                    f"แทนที่บัญชีปัจจุบัน ({len(current)} บัญชี) ด้วยบัญชีจากไฟล์ "
                    f"'{os.path.basename(path)}' ({len(parsed)} บัญชี) หรือไม่?"
                ],
                confirm_text="แทนที่",
                cancel_text="ยกเลิก",
            ):
                self._refresh_file_combobox(
                    getattr(self, "_inv_recent_files", None) or [],
                    "inv_file_cb",
                    "_inv_file_cb_paths",
                    selected_path=getattr(self, "_inv_last_loaded_path", None),
                )
                return
        for r in self._inv_rows:
            r["frm"].destroy()
        self._inv_rows.clear()
        for u, p, t in parsed:
            self._inv_add_acc(u, p, t)
        self._inv_update_acc_count()
        if getattr(self, "_inv_canvas", None):
            self._inv_canvas.yview_moveto(0)
        self._remember_recent_file(
            path,
            "_inv_recent_files",
            "_inv_last_loaded_path",
            "inv_file_cb",
            "_inv_file_cb_paths",
        )
        self.log(
            f"📂 สลับเป็นบัญชีฝาก/เบิกจากไฟล์: "
            f"{os.path.basename(path)} ({len(parsed)} บัญชี)"
        )

    # ------------------------------------------------------------------
    # หน้าต่าง "👁 ดู/เลือกไอเทม" (preview + เลือกชิ้นที่จะฝาก/เบิก)
    # ------------------------------------------------------------------
    def _inv_open_item_picker(self, row):
        """เปิดหน้าต่างแสดงไอเทมทั้งหมดของบัญชีแถวนี้ (ล็อกอิน + ดึงสดจากเว็บ)
        ให้ดูรายละเอียดแต่ละชิ้น + เลือกเฉพาะชิ้นที่จะฝาก/เบิก — กดปุ่มล่างเพื่อส่ง
        ฝาก/เบิกเฉพาะที่เลือก (engine: _inv_deposit_chosen / _inv_withdraw_chosen)"""
        win = getattr(self, "_inv_picker_win", None)
        if win is not None:
            try:
                if win.winfo_exists():
                    win.lift()
                    return
            except Exception:
                pass
            self._inv_picker_win = None
        if getattr(self, "_inv_busy", False):
            self._alert_warning(
                "กำลังทำงาน", "รอรอบฝาก/เบิกปัจจุบันให้เสร็จก่อนเปิดดู/เลือกไอเทม"
            )
            return

        username = row["user"].get().strip()
        password = row["pwd"].get().strip()
        ltype = row["type"].get().strip()
        if not username or not password:
            self._alert_warning(
                "ข้อมูลไม่ครบ",
                f"กรอกไอดีและรหัสผ่านของแถว '{username or '-'}' ก่อนเปิดดูไอเทม",
            )
            return

        win = tk.Toplevel(self.root)
        win.title(f"👁 ดู/เลือกไอเทม — {username}")
        win.configure(bg=BG)
        win.geometry("880x600")
        win.transient(self.root)
        self._inv_picker_win = win

        _page_header(win, f"ไอเทมของ {username}", "👁", padx=14)

        # ── แถวบน: ตัวกรอง + ช่องค้นหา ──
        top_row = tk.Frame(win, bg=BG)
        top_row.pack(fill="x", padx=14, pady=(2, 4))
        tk.Label(
            top_row, text="แสดง", font=("Leelawadee UI", 10), bg=BG, fg=FG2
        ).pack(side="left")
        self._inv_pk_filter_var = tk.StringVar(value="ทั้งหมด")
        _filt = ttk.Combobox(
            top_row,
            textvariable=self._inv_pk_filter_var,
            values=["ทั้งหมด", "เฉพาะที่ฝากได้", "เฉพาะที่เบิกได้"],
            state="readonly",
            style="Dark.TCombobox",
            font=("Leelawadee UI", 10),
            width=16,
        )
        _filt.pack(side="left", padx=(4, 12))
        _bind_combobox_wheel_local(_filt)
        _filt.bind("<<ComboboxSelected>>", self._inv_pk_render)

        tk.Label(
            top_row, text="หมวด", font=("Leelawadee UI", 10), bg=BG, fg=FG2
        ).pack(side="left")
        self._inv_pk_cat_var = tk.StringVar(value="ทั้งหมด")
        _cat = ttk.Combobox(
            top_row,
            textvariable=self._inv_pk_cat_var,
            values=["ทั้งหมด"],
            state="readonly",
            style="Dark.TCombobox",
            font=("Leelawadee UI", 10),
            width=24,
        )
        _cat.pack(side="left", padx=(4, 12))
        _bind_combobox_wheel_local(_cat)
        _cat.bind("<<ComboboxSelected>>", self._inv_pk_render)
        self._inv_pk_cat_combo = _cat

        tk.Label(
            top_row, text="ค้นหา", font=("Leelawadee UI", 10), bg=BG, fg=FG2
        ).pack(side="left")
        self._inv_pk_search_var = tk.StringVar()
        _search = tk.Entry(
            top_row,
            textvariable=self._inv_pk_search_var,
            font=("Leelawadee UI", 10),
            bg=BG2,
            fg=FG,
            insertbackground="white",
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            width=28,
        )
        _search.pack(side="left", padx=(4, 0))
        _bind_entry_context_menu(_search)
        self._inv_pk_search_var.trace_add("write", self._inv_pk_render)

        info_lbl = tk.Label(
            win, text="", font=("Leelawadee UI", 9), bg=BG, fg=FG2
        )
        info_lbl.pack(anchor="w", padx=14, pady=(0, 2))
        self._inv_pk_info_lbl = info_lbl

        # ── Listbox รายการไอเทม ──
        list_frame = tk.Frame(win, bg=BG)
        list_frame.pack(fill="both", expand=True, padx=14)
        sb = tk.Scrollbar(list_frame, orient="vertical")
        lb = tk.Listbox(
            list_frame,
            font=("Consolas", 10),
            bg=BG2,
            fg=FG,
            selectbackground=ACC2,
            selectforeground="#0B0B10",
            selectmode="extended",
            activestyle="none",
            yscrollcommand=sb.set,
            highlightthickness=0,
            relief="flat",
        )
        sb.configure(command=lb.yview)
        lb.pack(side="left", fill="both", expand=True)
        self._inv_pk_listbox = lb
        lb.bind("<<ListboxSelect>>", self._inv_pk_on_select)

        # ── แผงรายละเอียดไอเทมที่เลือก ──
        details_frame = tk.Frame(win, bg=BG2)
        details_frame.pack(fill="x", padx=14, pady=(6, 0))
        tk.Label(
            details_frame,
            text="รายละเอียดไอเทม (ดึงจากเว็บ)",
            font=("Leelawadee UI", 9, "bold"),
            bg=BG2,
            fg=ACC2,
            anchor="w",
        ).pack(fill="x", padx=8, pady=(6, 0))
        self._inv_pk_detail_lbl = tk.Text(
            details_frame,
            font=("Consolas", 9),
            bg=BG2,
            fg=FG2,
            wrap="word",
            height=9,
            relief="flat",
            highlightthickness=0,
            padx=8,
            pady=4,
            state="disabled",
            cursor="arrow",
        )
        self._inv_pk_detail_lbl.pack(fill="both", expand=False, padx=(8, 0), pady=(2, 8))

        # ── แถวล่าง: ปุ่มฝาก/เบิกที่เลือก ──
        btn_row = tk.Frame(win, bg=BG)
        btn_row.pack(fill="x", padx=14, pady=8)
        sel_lbl = tk.Label(
            btn_row, text="เลือก 0 ชิ้น", font=("Leelawadee UI", 9), bg=BG, fg=FG2
        )
        sel_lbl.pack(side="left", padx=(0, 8))
        self._inv_pk_sel_lbl = sel_lbl

        def _select_all_in_mode(mode):
            """เลือกทั้งหมดในรายการที่แสดงอยู่ (ตามตัวกรอง/ค้นหาปัจจุบัน) ที่ฝาก/เบิกได้
            ตามโหมด — กันต้องไล่กดทีละชิ้นตอนมีไอเทมเยอะ"""
            try:
                view = self._inv_pk_current_view()
                check = item_can_deposit if mode == "DEPOSIT" else item_can_withdraw
                idxs = [i for i, it in enumerate(view) if check(it)]
                lb = self._inv_pk_listbox
                lb.selection_clear(0, "end")
                for i in idxs:
                    lb.selection_set(i)
                lb.event_generate("<<ListboxSelect>>")
            except Exception:
                pass

        btn_sel_dep = tk.Button(
            btn_row,
            text="☑ เลือกฝากได้ทั้งหมด",
            font=("Leelawadee UI", 9),
            bg=BG2,
            fg=GREEN,
            relief="flat",
            cursor="hand2",
            command=lambda: _select_all_in_mode("DEPOSIT"),
            padx=8,
            pady=2,
        )
        btn_sel_dep.pack(side="left", padx=(0, 4))
        _bind_button_hover(btn_sel_dep, BG2)

        btn_sel_wd = tk.Button(
            btn_row,
            text="☑ เลือกเบิกได้ทั้งหมด",
            font=("Leelawadee UI", 9),
            bg=BG2,
            fg=STATUS_WARN,
            relief="flat",
            cursor="hand2",
            command=lambda: _select_all_in_mode("WITHDRAW"),
            padx=8,
            pady=2,
        )
        btn_sel_wd.pack(side="left", padx=(0, 4))
        _bind_button_hover(btn_sel_wd, BG2)

        def _run_chosen(mode):
            items = self._inv_pk_selected_items()
            if not items:
                self._alert_warning(
                    "ยังไม่ได้เลือก", "เลือกไอเทมในรายการก่อนกดฝาก/เบิกที่เลือก"
                )
                return
            verb = "ฝาก" if mode == "DEPOSIT" else "เบิก"
            n = len(items)
            if not self._confirm_dialog(
                f"{verb}ไอเทมที่เลือก",
                lines=[
                    f"ต้องการ{verb}ไอเทมที่เลือก {n} ชิ้นของ {username} หรือไม่?",
                ],
                confirm_text=f"{verb} {n} ชิ้น",
                cancel_text="ยกเลิก",
                danger=False,
            ):
                return
            chosen = [(str(i.get("ItemSerial") or ""), item_display_name(i)) for i in items]
            chosen = [(s, n_) for s, n_ in chosen if s]
            if not chosen:
                self._alert_error(
                    "ไม่มีรหัสไอเทม",
                    f"ไอเทมที่เลือกไม่มี ItemSerial — ไม่สามารถ{verb}ได้",
                )
                return
            self._inv_picker_win = None
            try:
                if win.winfo_exists():
                    win.destroy()
            except Exception:
                pass
            self.log(
                f"👁 เลือกไอเทม {n} ชิ้นของ {username} เพื่อ{verb} "
                f"(จากหน้าต่างดู/เลือกไอเทม)"
            )
            # ปลดล็อกจากโหมดดู แล้วส่งต่อให้ engine รันเฉพาะชิ้นที่เลือก
            self._inv_set_picker_lock(False)
            if mode == "DEPOSIT":
                self._inv_deposit_chosen(
                    [{"user": username, "pwd": password, "type": ltype, "items": chosen}]
                )
            else:
                self._inv_withdraw_chosen(
                    [{"user": username, "pwd": password, "type": ltype, "items": chosen}]
                )

        btn_dep = tk.Button(
            btn_row,
            text="📥 ฝากที่เลือก",
            font=("Leelawadee UI", 10, "bold"),
            bg=GREEN,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=lambda: _run_chosen("DEPOSIT"),
            padx=10,
            pady=3,
        )
        btn_dep.pack(side="right", padx=(6, 0))
        _bind_button_hover(btn_dep, GREEN)

        btn_wd = tk.Button(
            btn_row,
            text="📤 เบิกที่เลือก",
            font=("Leelawadee UI", 10, "bold"),
            bg=STATUS_WARN,
            fg="#1A1A1A",
            relief="flat",
            cursor="hand2",
            command=lambda: _run_chosen("WITHDRAW"),
            padx=10,
            pady=3,
        )
        btn_wd.pack(side="right", padx=(6, 0))
        _bind_button_hover(btn_wd, STATUS_WARN)

        btn_refresh = tk.Button(
            btn_row,
            text="🔄 ดึงใหม่",
            font=("Leelawadee UI", 10),
            bg=BG2,
            fg=FG2,
            relief="flat",
            cursor="hand2",
            command=lambda: self._inv_pk_load(username, password, ltype, win),
            padx=10,
            pady=3,
        )
        btn_refresh.pack(side="right", padx=(6, 0))
        _bind_button_hover(btn_refresh, BG2)

        def _close_win():
            # ปิดหน้าต่าง + ปลดล็อก (ให้กดฝาก/เบิกทั้งหมดได้อีกครั้ง)
            self._inv_picker_win = None
            try:
                if win.winfo_exists():
                    win.destroy()
            except Exception:
                pass
            self._inv_set_picker_lock(False)

        btn_close = tk.Button(
            btn_row,
            text="ปิด",
            font=("Leelawadee UI", 10),
            bg=BG2,
            fg=FG2,
            relief="flat",
            cursor="hand2",
            command=_close_win,
            padx=10,
            pady=3,
        )
        btn_close.pack(side="right")
        _bind_button_hover(btn_close, BG2)

        win.protocol("WM_DELETE_WINDOW", _close_win)
        _center_window_on_parent(win, self.root)

        self._inv_pk_items = []  # ไอเทมทั้งหมดที่ดึงได้ล่าสุด
        # ล็อกไม่ให้กด ฝาก/เบิกทั้งหมด พร้อมกับเปิดหน้าต่างนี้ (กัน session ชน)
        self._inv_set_picker_lock(True)
        self._inv_pk_load(username, password, ltype, win)

    def _inv_sync_main_categories(self, items):
        """อัปเดตหมวดในปุ่มหลัก (แถวบน) ให้มีหมวดย่อยจริงที่เจอจาก items — เช่น
        'อาวุธ › ปืนไรเฟิลจู่โจม' — กันซ้ำ และเก็บหมวดที่เลือกไว้ถ้ายังมีอยู่"""
        combo = getattr(self, "_inv_cat_combo", None)
        if combo is None:
            return
        try:
            opts = inv_category_options(items or [])
            combo.configure(values=opts)
            cur = self._inv_cat_var.get()
            if cur not in opts:
                self._inv_cat_var.set("ทั้งหมด")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # picker helpers
    # ------------------------------------------------------------------
    def _inv_pk_load(self, username, password, ltype, win):
        """ล็อกอิน + ดึงไอเทมสด (worker) แล้ววาดรายการ"""
        win = win or getattr(self, "_inv_picker_win", None)
        if win is None:
            return
        try:
            info = self._inv_pk_info_lbl
            info.configure(text=f"⏳ กำลังล็อกอิน/ดึงไอเทมของ {username}...", fg=STATUS_WARN)
            lb = self._inv_pk_listbox
            lb.delete(0, "end")
            lb.insert("end", "⏳ กำลังโหลด...")
            lb.configure(state="disabled")
        except Exception:
            pass

        def _done(items, err):
            try:
                if not win.winfo_exists():
                    return
                lb.configure(state="normal")
                lb.delete(0, "end")
                if err:
                    self._inv_pk_info_lbl.configure(text=f"❌ {err}", fg=DANGER)
                    lb.insert("end", "(โหลดไม่สำเร็จ — กด 🔄 ดึงใหม่)")
                    lb.configure(state="disabled")
                    self._inv_pk_set_details("")
                    return
                self._inv_pk_items = items or []
                # เติมรายการหมวดหมู่ที่พบ (จาก ParentCategoryName › CategoryName)
                combo = getattr(self, "_inv_pk_cat_combo", None)
                if combo is not None:
                    try:
                        combo.configure(values=inv_category_options(self._inv_pk_items))
                        self._inv_pk_cat_var.set("ทั้งหมด")
                    except Exception:
                        pass
                self._inv_sync_main_categories(self._inv_pk_items)
                self._inv_pk_render()
            except Exception:
                pass

        def worker():
            err = None
            items = None
            try:
                items = self._inv_fetch_preview(username, password, ltype)
            except Exception as e:
                err = str(e) or e.__class__.__name__
            self.root.after(0, lambda: _done(items, err))

        self._worker_manager.submit(worker, label="app_inventory.picker_fetch")

    def _inv_pk_current_view(self):
        """ไอเทมที่ควรแสดงตามตัวกรอง/ช่องค้นหาปัจจุบัน"""
        filt = self._inv_pk_filter_var.get() if hasattr(self, "_inv_pk_filter_var") else "ทั้งหมด"
        cat = (
            self._inv_pk_cat_var.get() if hasattr(self, "_inv_pk_cat_var") else "ทั้งหมด"
        )
        q = (
            (self._inv_pk_search_var.get() or "").strip().lower()
            if hasattr(self, "_inv_pk_search_var")
            else ""
        )
        out = []
        for it in getattr(self, "_inv_pk_items", []) or []:
            if filt == "เฉพาะที่ฝากได้" and not item_can_deposit(it):
                continue
            if filt == "เฉพาะที่เบิกได้" and not item_can_withdraw(it):
                continue
            if cat != "ทั้งหมด" and not item_in_category(it, cat):
                continue
            if q:
                hay = (item_display_name(it) + " " + str(it.get("ItemSerial") or "")).lower()
                if q not in hay:
                    continue
            out.append(it)
        return out

    def _inv_pk_render(self, *_):
        try:
            lb = getattr(self, "_inv_pk_listbox", None)
            if lb is None:
                return
            view = self._inv_pk_current_view()
            lb.configure(state="normal")
            lb.delete(0, "end")
            for it in view:
                lb.insert("end", item_summary_line(it))
            if not view:
                lb.insert("end", "(ไม่พบไอเทมที่ตรงกับเงื่อนไข)")
                lb.configure(state="disabled")
            else:
                lb.configure(state="normal")
            all_items = getattr(self, "_inv_pk_items", []) or []
            n_dep = sum(1 for i in all_items if item_can_deposit(i))
            n_wd = sum(1 for i in all_items if item_can_withdraw(i))
            self._inv_pk_info_lbl.configure(
                text=(
                    f"รวม {len(all_items)} ชิ้น  |  ฝากได้ {n_dep}  |  เบิกได้ {n_wd}  "
                    f"|  กำลังแสดง {len(view)} ชิ้น — ลากคลุม/กด Ctrl เพื่อเลือกหลายชิ้น"
                ),
                fg=FG2,
            )
            self._inv_pk_update_sel()
        except Exception:
            pass

    def _inv_pk_view_index_to_item(self, idx):
        try:
            view = self._inv_pk_current_view()
            if 0 <= idx < len(view):
                return view[idx]
        except Exception:
            pass
        return None

    def _inv_pk_selected_items(self):
        try:
            lb = self._inv_pk_listbox
            sel = lb.curselection()
            return [
                self._inv_pk_view_index_to_item(int(i)) for i in sel
            ]
        except Exception:
            return []

    def _inv_pk_on_select(self, _evt=None):
        try:
            self._inv_pk_update_sel()
            sel = self._inv_pk_listbox.curselection()
            if not sel:
                self._inv_pk_set_details("")
                return
            item = self._inv_pk_view_index_to_item(int(sel[-1]))
            if not item:
                self._inv_pk_set_details("")
                return
            lines = item_detail_lines(item)
            text = "\n".join(f"{k:<18}: {v}" for k, v in lines)
            self._inv_pk_set_details(text)
        except Exception:
            pass

    def _inv_pk_update_sel(self):
        try:
            sel = self._inv_pk_selected_items()
            sel = [i for i in sel if i]
            n_dep = sum(1 for i in sel if item_can_deposit(i))
            n_wd = sum(1 for i in sel if item_can_withdraw(i))
            self._inv_pk_sel_lbl.configure(
                text=(
                    f"เลือก {len(sel)} ชิ้น"
                    + (f"  (ฝากได้ {n_dep} · เบิกได้ {n_wd})" if sel else "")
                ),
                fg=STATUS_OK if sel else FG2,
            )
        except Exception:
            pass

    def _inv_pk_set_details(self, text):
        try:
            lbl = self._inv_pk_detail_lbl
            lbl.configure(state="normal")
            lbl.delete("1.0", "end")
            lbl.insert("1.0", text)
            lbl.configure(state="disabled")
        except Exception:
            pass

    def _inv_set_picker_lock(self, active):
        """ล็อก/ปลดล็อกปุ่มฝาก/เบิกทั้งหมด ขณะเปิดหน้าต่าง '👁 ดู/เลือกไอเทม' — ใช้
        flag แยก (_inv_picker_active) ไม่อิง _inv_busy เพื่อไม่ให้ปุ่มหลักแสดงข้อความ
        'กำลัง...' ค้างตอนแค่เปิดดู"""
        self._inv_picker_active = bool(active)
        for _nm in ("_inv_btn_dep", "_inv_btn_wd"):
            b = getattr(self, _nm, None)
            if b is not None:
                try:
                    b.configure(state="disabled" if active else "normal")
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # busy state (เรียกจาก engine)
    # ------------------------------------------------------------------
    def _inv_set_busy(self, busy, verb=""):
        """เปลี่ยนสถานะปุ่มฝาก/เบิก + ข้อความสถานะ + ล็อก dropdown ประเภทไอดี
        ระหว่างรัน (เรียกบน UI thread เท่านั้น)"""
        self._inv_busy = busy
        dep = getattr(self, "_inv_btn_dep", None)
        if dep is not None:
            dep.configure(
                state="disabled" if busy else "normal",
                text=f"⏳ กำลัง{verb}..." if busy else "📥 ฝากทั้งหมด",
            )
        wd = getattr(self, "_inv_btn_wd", None)
        if wd is not None:
            wd.configure(
                state="disabled" if busy else "normal",
                text=f"⏳ กำลัง{verb}..." if busy else "📤 เบิกทั้งหมด",
            )
        lbl = getattr(self, "_inv_status_lbl", None)
        if lbl is not None:
            if busy:
                lbl.configure(
                    text=f"⏳ กำลัง{verb}ไอเทมให้ทุกบัญชี...",
                    fg=STATUS_WARN,
                )
            else:
                lbl.configure(
                    text=(
                        "พร้อมทำงาน — ล็อกอินเหมือนรอบรับคีย์ แล้วไปที่หน้า Inventory"
                    ),
                    fg=FG2,
                )
        if not busy:
            # แถวที่ยังค้าง "⏳ กำลังทำงาน..." (ไม่ได้เข้า�รอบนี้) → กลับเป็นพร้อม
            for r in getattr(self, "_inv_rows", []):
                try:
                    if (r["status_lbl"].cget("text") or "").startswith("⏳"):
                        r["status_lbl"].configure(text="พร้อมทำงาน", fg=FG2)
                except Exception:
                    pass
        cat_combo = getattr(self, "_inv_cat_combo", None)
        if cat_combo is not None:
            try:
                cat_combo.configure(state="disabled" if busy else "readonly")
            except Exception:
                pass
        for r in getattr(self, "_inv_rows", []):
            cb = r.get("type_cb")
            if cb is None:
                continue
            try:
                cb.configure(state="disabled" if busy else "readonly")
            except Exception:
                pass


__all__ = ["AppInventoryUIMixin"]
