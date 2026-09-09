"""The 'auto free item claim' tab — UI half: builds the tab's widgets and
handles account/webhook row CRUD (add/remove/load-from-file/counts).

แยกมาจาก app_autoitem.py เดิม (1175 บรรทัด รวม UI+webhook+engine ในไฟล์เดียว)
เป็นส่วนที่ 1/3 — เก็บเฉพาะ widget building + row management ตรงนี้
ดู app_autoitem_webhook.py (ส่วน webhook send/test) และ app_autoitem_engine.py
(ส่วน toggle/loop/claim automation) สำหรับอีก 2 ไฟล์ที่เหลือ

ยังเป็น mixin แบบเดิมทุกประการ (AppAutoitemUIMixin ยังแชร์ self. เดียวกับ
mixin อื่นๆ ผ่าน multiple inheritance ใน app.py) — การแยกไฟล์รอบนี้แค่จัด
กลุ่มโค้ดใหม่ ไม่ได้เปลี่ยนสถาปัตยกรรม state/dependency ใดๆ เลย เพื่อความเสี่ยง
ต่ำสุดเท่าที่จะทำได้"""

import logging

from ..core.constants import (
    ACC,
    ACC2,
    BG,
    BG2,
    BG3,
    BORDER,
    COL_NUM,
    CONCURRENCY_PRESETS,
    COL_PWD,
    COL_TYPE,
    COL_USER,
    DANGER,
    FG,
    FG2,
    GREEN,
    INFO_BLUE,
    STATUS_ACTIVE,
    STATUS_OK,
    STATUS_WARN,
    _DISCORD_BOT_NAME,
)
from ..core.deps import filedialog, os, tk, ttk
from ..core.rows import AccountRow, WebhookRow
from ..core.ui_theme import (
    _bind_button_hover,
    _bind_combobox_wheel_local,
    _bind_entry_context_menu,
    _make_toggle,
    _page_header,
)

_logger = logging.getLogger(__name__)


class AppAutoitemUIMixin:
    def _build_autoitem_tab(self, parent):
        # ใช้สีกลางของทั้งแอป (constants) เพื่อให้แท็บนี้เข้ากับแท็บอื่นทั้งหมด
        outer = tk.Frame(parent, bg=BG)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0, bd=0)
        vsb = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        self._autoitem_canvas = canvas
        # ซ่อนแถบเลื่อน (scrollbar) ไว้ - ยังเลื่อนด้วยล้อเมาส์ได้ปกติผ่าน
        # _bind_mousewheel ด้านล่าง แค่ไม่โชว์แถบเลื่อนให้เกะกะสายตา
        inner = tk.Frame(canvas, bg=BG)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        _autoitem_last_width = [None]

        def _on_canvas_resize(e):
            if e.width != _autoitem_last_width[0]:
                _autoitem_last_width[0] = e.width
                canvas.itemconfig(inner_id, width=e.width)

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_resize)
        self._bind_mousewheel(canvas, inner)

        _page_header(inner, "รับไอเทมฟรี", "🎁", bg=BG, acc=ACC, border=BORDER)

        pad = {"padx": 16, "pady": (0, 10)}

        def _section(title):
            card = tk.Frame(
                inner,
                bg=BG2,
                highlightbackground=BORDER,
                highlightcolor=BORDER,
                highlightthickness=1,
                takefocus=0,
            )
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

        def _lbl(parent, text, width=None):
            # width=None = ขยายตามเนื้อหา (ข้อความไทยกว้างกว่าตัวอักษรละติน —
            # กำหนด width=18 ไว้ตายตัวจะตัด "URL รูปโปรไฟล์บอท" ทิ้ง)
            kw = {"width": width} if width else {}
            tk.Label(
                parent,
                text=text,
                font=("Leelawadee UI", 10),
                bg=BG2,
                fg=FG2,
                anchor="w",
                **kw,
            ).pack(side="left")

        card_status = _section("🎁  รับไอเทมฟรีอัตโนมัติ (00:05 ทุกวัน)")
        r_status = _row(card_status, (8, 4))
        self._autoitem_status_lbl = tk.Label(
            r_status, text="⏸ ปิดอยู่", font=("Leelawadee UI", 10), bg=BG2, fg="#888"
        )
        self._autoitem_status_lbl.pack(side="left")
        self._autoitem_var = tk.BooleanVar(value=False)
        # เดิม toggle นี้เป็น Label ตัวอักษร ✔/○ เขียนเอง แยกดีไซน์จากสวิตช์กลาง
        # ของ _make_toggle (ที่ใช้กับ toggle อื่นในไฟล์เดียวกันนี้เองอยู่แล้ว เช่น
        # ด้านล่าง) ทำให้หน้าตาไม่ตรงกันทั้งโปรแกรม — เปลี่ยนมาใช้ตัวเดียวกัน (รวม
        # ข้อความ "เปิดใช้งานอัตโนมัติ" ไว้ในตัวสวิตช์เองแล้ว ตัด label ซ้ำทิ้งด้วย)
        _tgl_autoitem_enable, self._update_autoitem_toggle_visual = _make_toggle(
            r_status,
            self._autoitem_var,
            "เปิดใช้งานอัตโนมัติ",
            command=self._toggle_autoitem,
            bg=BG2,
            fg=FG2,
        )
        _tgl_autoitem_enable.pack(side="left", padx=(12, 6))

        self._autoitem_claim_btn = tk.Button(
            r_status,
            text="🎁 รับตอนนี้",
            font=("Leelawadee UI", 10, "bold"),
            bg=STATUS_WARN,
            fg="#1A1A1A",
            relief="flat",
            cursor="hand2",
            command=self._autoitem_claim_now,
            padx=12,
            pady=3,
        )
        self._autoitem_claim_btn.pack(side="left", padx=(8, 0))
        _bind_button_hover(self._autoitem_claim_btn, STATUS_WARN)
        self._autoitem_claim_busy = False

        # ── พร้อมกัน (เฉพาะแท็บนี้) — แยกจาก 'พร้อมกัน' ของแดชบอร์ด ──
        # ให้ตั้งจำนวนล็อกอินพร้อมกันของรอบรับไอเทมฟรีสูงได้อิสระโดยไม่ไปยุ่งกับ
        # concurrency ของระบบรันหลัก (แดชบอร์ด)
        self._autoitem_concurrency_var = tk.StringVar(value="8")
        r_conc = tk.Frame(r_status, bg=BG2)
        r_conc.pack(side="left", padx=(16, 0))

        tk.Label(
            r_conc, text="พร้อมกัน", font=("Leelawadee UI", 10), bg=BG2, fg=FG2
        ).pack(side="left")
        # dropdown เลือกค่าได้ (กดลูกศร) หรือพิมพ์เองก็ได้ 1–200
        self._autoitem_concurrency_spin = ttk.Combobox(
            r_conc,
            values=CONCURRENCY_PRESETS,
            textvariable=self._autoitem_concurrency_var,
            style="Dark.TCombobox",
            font=("Consolas", 10),
            width=4,
        )
        self._autoitem_concurrency_spin.pack(side="left", padx=(6, 0))

        # ปิด session หลังจบรอบ = ค่าถาวร (ทำเสมอ ไม่มี toggle ให้ปิดได้)
        # — โค้ด engine ส่ง auto_close=True เสมอ ดู app_autoitem_engine

        card_acc = _section("👤  ที่ใช้รับไอเทม (แยกจากระบบรันหลัก)")
        r_acc_hdr = _row(card_acc, (8, 2))
        self._autoitem_acc_count_lbl = tk.Label(
            r_acc_hdr, text="[0 ไอดี]", font=("Leelawadee UI", 10), bg=BG2, fg=FG2
        )
        self._autoitem_acc_count_lbl.pack(side="left")
        # dropdown เลือกไฟล์ .txt ที่เคยโหลด (เลือกแล้วโหลดบัญชีของไฟล์นั้นมา
        # แทนที่ลิสต์ปัจจุบัน — ดู _on_autoitem_file_selected ในไฟล์นี้)
        # ครอบด้วย Frame วาดกรอบ static (สีไม่เปลี่ยนตอนโฟกัส) เพราะตัว combobox
        # ถูกถอด native field ออกแล้ว — วิธีเดียวกับแถวบัญชี (rows.py)
        # bg = BG2 (= #15161D) ตรงกับ field ของ Dark.TCombobox ใน app_core
        # กันเส้นหลอนรอบ widget
        autoitem_file_box = tk.Frame(
            r_acc_hdr,
            bg=BG2,
            highlightthickness=1,
            highlightbackground="#2E313F",
            highlightcolor="#2E313F",
        )
        autoitem_file_box.pack(side="left", padx=(10, 0))
        self.autoitem_file_cb = ttk.Combobox(
            autoitem_file_box,
            state="readonly",
            style="Dark.TCombobox",
            font=("Leelawadee UI", 9),
            width=24,
        )
        self.autoitem_file_cb.pack(fill="both", expand=True, padx=1, pady=1)
        self.autoitem_file_cb.bind(
            "<<ComboboxSelected>>", self._on_autoitem_file_selected
        )
        self._refresh_file_combobox(
            getattr(self, "_autoitem_recent_files", None) or [],
            "autoitem_file_cb",
            "_autoitem_file_cb_paths",
        )
        self._bind_file_cb_context_menu(
            self.autoitem_file_cb,
            "_autoitem_recent_files",
            "_autoitem_last_loaded_path",
            "autoitem_file_cb",
            "_autoitem_file_cb_paths",
        )
        self._autoitem_show_pwd = tk.BooleanVar(value=False)
        _tgl_autoitem_pwd, _ = _make_toggle(
            r_acc_hdr,
            self._autoitem_show_pwd,
            "แสดงรหัสผ่าน",
            command=self._autoitem_toggle_pwd_mask,
            bg=BG2,
            fg=FG2,
            eye_mode=True,
        )
        _tgl_autoitem_pwd.pack(side="left", padx=(10, 0))
        btn_clear_acc = tk.Button(
            r_acc_hdr,
            text="ล้างทั้งหมด",
            font=("Leelawadee UI", 10),
            bg=BG3,
            fg=DANGER,
            relief="flat",
            cursor="hand2",
            command=self._autoitem_clear_acc,
            padx=8,
            pady=2,
        )
        btn_clear_acc.pack(side="right")
        _bind_button_hover(btn_clear_acc, BG3)
        btn_load_acc = tk.Button(
            r_acc_hdr,
            text="โหลด .txt",
            font=("Leelawadee UI", 10),
            bg=BG3,
            fg=INFO_BLUE,
            relief="flat",
            cursor="hand2",
            command=self._autoitem_load_file,
            padx=8,
            pady=2,
        )
        btn_load_acc.pack(side="right", padx=(0, 6))
        _bind_button_hover(btn_load_acc, BG3)
        btn_add_acc = tk.Button(
            r_acc_hdr,
            text="+ เพิ่มบัญชี",
            font=("Leelawadee UI", 10, "bold"),
            bg=GREEN,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=lambda: self._autoitem_add_acc(user_action=True),
            padx=8,
            pady=2,
        )
        btn_add_acc.pack(side="right", padx=(0, 6))
        _bind_button_hover(btn_add_acc, GREEN)

        r_acc_col = _row(card_acc, (2, 0))
        # padx เดียวกับแถว (notify/num ไม่มี padx, ที่เหลือ padx=2) — ให้หัวตาราง
        # เสมอกับช่องกรอกพอดี ไม่เยื้องขวาเหมือนเดิม
        for txt, w, px in [
            ("แจ้งเตือน", 66, 0),
            ("#", COL_NUM, 0),
            ("ไอดี", COL_USER, 2),
            ("รหัสผ่าน", COL_PWD, 2),
            ("ประเภทไอดี", COL_TYPE, 2),
        ]:
            box = tk.Frame(r_acc_col, width=w, height=32, bg=BG2)
            box.pack_propagate(False)
            box.pack(side="left", padx=px)
            tk.Label(
                box, text=txt, font=("Leelawadee UI", 10, "bold"), bg=BG2, fg=FG2, anchor="w"
            ).pack(side="left", fill="x", expand=True, padx=(4, 0), pady=6)

        self._autoitem_acc_rows = []
        self._autoitem_acc_frame = tk.Frame(card_acc, bg=BG2)
        self._autoitem_acc_frame.pack(fill="x", padx=14, pady=(2, 8))

        card_wh = _section("📣  Discord Webhook (แจ้งผลการรับไอเทมฟรี)")
        r_wh_hdr = _row(card_wh, (8, 2))
        tk.Label(
            r_wh_hdr,
            text="Webhook URL",
            font=("Leelawadee UI", 10),
            bg=BG2,
            fg=FG2,
            anchor="w",
        ).pack(side="left", padx=(0, 8))
        self._autoitem_wh_count_lbl = tk.Label(
            r_wh_hdr, text="0 ช่อง", font=("Leelawadee UI", 10), bg=BG2, fg=FG2
        )
        self._autoitem_wh_count_lbl.pack(side="left", padx=8)
        btn_clear_wh = tk.Button(
            r_wh_hdr,
            text="ล้างทั้งหมด",
            font=("Leelawadee UI", 10),
            bg=BG3,
            fg=DANGER,
            relief="flat",
            cursor="hand2",
            command=self._autoitem_clear_wh,
        )
        btn_clear_wh.pack(side="right", ipadx=8, ipady=2)
        _bind_button_hover(btn_clear_wh, BG3)
        btn_add_wh = tk.Button(
            r_wh_hdr,
            text="+ เพิ่ม Webhook",
            font=("Leelawadee UI", 10, "bold"),
            bg=GREEN,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=lambda: self._autoitem_add_wh(user_action=True),
        )
        btn_add_wh.pack(side="right", ipadx=8, ipady=2, padx=(0, 6))
        _bind_button_hover(btn_add_wh, GREEN)

        self._autoitem_wh_rows = []
        self._autoitem_wh_frame = tk.Frame(card_wh, bg=BG2)
        self._autoitem_wh_frame.pack(fill="x", padx=14, pady=(2, 4))

        r_wh_avatar = _row(card_wh, (0, 4))
        # คอลัมน์ label กว้างคงที่ — ให้ช่องกรอกของแถวนี้เสมอกับแถว 'ชื่อบอท' ด้านล่าง
        r_wh_avatar.columnconfigure(0, minsize=110)
        r_wh_avatar.columnconfigure(1, weight=1)
        tk.Label(
            r_wh_avatar,
            text="URL รูปโปรไฟล์บอท",
            font=("Leelawadee UI", 10),
            bg=BG2,
            fg=FG2,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self._autoitem_avatar_entry = tk.Entry(
            r_wh_avatar,
            highlightthickness=0,
            font=("Leelawadee UI", 9),
            width=52,
            bg=BG3,
            fg=FG2,
            insertbackground="white",
            relief="flat",
            bd=4,
        )
        self._autoitem_avatar_entry.grid(row=0, column=1, sticky="ew", padx=(4, 0), ipady=3)
        _bind_entry_context_menu(self._autoitem_avatar_entry)
        self._autoitem_avatar_entry.insert(
            0, "วางลิงก์รูป .jpg/.png ที่นี่ (เช่น https://i.imgur.com/xxx.jpg)"
        )
        self._autoitem_avatar_entry.bind(
            "<FocusIn>", lambda e: self._autoitem_avatar_entry_focus_in()
        )
        self._autoitem_avatar_entry.bind(
            "<FocusOut>", lambda e: self._autoitem_avatar_entry_focus_out()
        )
        self._autoitem_avatar_placeholder_shown = True

        r_wh_botname = _row(card_wh, (0, 4))
        r_wh_botname.columnconfigure(0, minsize=110)
        r_wh_botname.columnconfigure(1, weight=1)
        tk.Label(
            r_wh_botname,
            text="ชื่อบอท",
            font=("Leelawadee UI", 10),
            bg=BG2,
            fg=FG2,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self._autoitem_botname_entry = tk.Entry(
            r_wh_botname,
            highlightthickness=0,
            font=("Leelawadee UI", 9),
            width=52,
            bg=BG3,
            fg=FG2,
            insertbackground="white",
            relief="flat",
            bd=4,
        )
        self._autoitem_botname_entry.grid(row=0, column=1, sticky="ew", padx=(4, 0), ipady=3)
        _bind_entry_context_menu(self._autoitem_botname_entry)
        self._autoitem_botname_entry.insert(0, f"ปล่อยว่าง = {_DISCORD_BOT_NAME}")
        self._autoitem_botname_entry.bind(
            "<FocusIn>", lambda e: self._autoitem_botname_entry_focus_in()
        )
        self._autoitem_botname_entry.bind(
            "<FocusOut>", lambda e: self._autoitem_botname_entry_focus_out()
        )
        self._autoitem_botname_placeholder_shown = True

        r_wh_test = _row(card_wh, (0, 10))
        btn_test_wh = tk.Button(
            r_wh_test,
            text="ทดสอบส่งข้อความ (ส่งทุกช่อง)",
            font=("Leelawadee UI", 10),
            bg=BG3,
            fg=INFO_BLUE,
            relief="flat",
            cursor="hand2",
            command=self._autoitem_test_wh,
        )
        btn_test_wh.pack(side="left", ipadx=8, ipady=3)
        _bind_button_hover(btn_test_wh, BG3)
        self._autoitem_wh_test_lbl = tk.Label(
            r_wh_test, text="", font=("Leelawadee UI", 10), bg=BG2, fg=STATUS_OK
        )
        self._autoitem_wh_test_lbl.pack(side="left", padx=8)

        self._autoitem_add_acc()
        self._autoitem_add_wh()

    def _autoitem_add_acc(
        self, user="", pwd="", login_type="Game ID", notify=True, user_action=False
    ):
        AccountRow._ensure_styles()
        BG_ROW, ENT, _FG, DIM = BG2, BG, FG, FG2
        NOTIFY_COL = 66
        idx = len(self._autoitem_acc_rows) + 1
        frm = tk.Frame(self._autoitem_acc_frame, bg=BG_ROW)
        frm.pack(fill="x", pady=2)

        notify_var = tk.BooleanVar(value=notify)
        user_var = tk.StringVar(value=user)
        pwd_var = tk.StringVar(value=pwd)
        type_var = tk.StringVar(value=login_type)

        notify_box = tk.Frame(frm, width=NOTIFY_COL, height=34, bg=BG_ROW)
        notify_box.pack_propagate(False)
        notify_box.pack(side="left")

        # เดิม toggle นี้เป็น Label ตัวอักษร ✔/○ เขียนเอง แยกดีไซน์จากสวิตช์กลาง
        # ของ _make_toggle ทำให้หน้าตาไม่ตรงกันทั้งโปรแกรม — เปลี่ยนมาใช้ตัวเดียว
        # กัน (ไม่ต้องมี command= เพราะ notify_var.trace_add ด้านล่างทำงานกับ
        # var.set() ทุกทาง รวมถึงตอน _make_toggle flip ให้เองอยู่แล้ว)
        notify_chk, _update_notify_chk = _make_toggle(
            notify_box, notify_var, "", bg=BG_ROW, fg="#F2F1EC"
        )
        notify_chk.pack(side="left", padx=(6, 0), pady=2)
        notify_var.trace_add("write", lambda *_: self._autoitem_update_acc_count())

        num_box = tk.Frame(frm, width=COL_NUM, height=34, bg=BG_ROW)
        num_box.pack_propagate(False)
        num_box.pack(side="left")
        idx_lbl = tk.Label(
            num_box,
            text=f"{idx}.",
            anchor="w",
            font=("Consolas", 11),
            bg=BG_ROW,
            fg=DIM,
        )
        idx_lbl.pack(fill="both", expand=True, padx=(4, 0))

        user_box = tk.Frame(frm, width=COL_USER, height=34, bg=BG_ROW)
        user_box.pack_propagate(False)
        user_box.pack(side="left", padx=2)
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
        user_var.trace_add("write", lambda *_: self._autoitem_update_acc_count())

        pwd_box = tk.Frame(frm, width=COL_PWD, height=34, bg=BG_ROW)
        pwd_box.pack_propagate(False)
        pwd_box.pack(side="left", padx=2)
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
        pwd_var.trace_add("write", lambda *_: self._autoitem_update_acc_count())

        type_box = tk.Frame(frm, width=COL_TYPE, height=34, bg=BG_ROW)
        type_box.pack_propagate(False)
        type_box.pack(side="left", padx=2)
        _initial_locked = bool(
            getattr(self, "_autoitem_var", None) and self._autoitem_var.get()
        ) or bool(getattr(self, "_autoitem_claim_busy", False))
        type_cb = ttk.Combobox(
            type_box,
            textvariable=type_var,
            values=["Game ID", "GG Passport"],
            state=("disabled" if _initial_locked else "readonly"),
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
            # เรียกตรงๆ ใน UI thread — _save_settings อ่าน widget โดยตรง
            # ถ้า spawn thread จะเกิด Tkinter race condition (not thread-safe)
            self._save_settings()

        type_cb.bind("<<ComboboxSelected>>", _on_type_change)
        _bind_combobox_wheel_local(type_cb)

        def delete():
            self._autoitem_acc_rows.remove(row_data)
            frm.destroy()
            self._autoitem_reindex()
            self._autoitem_update_acc_count()
            self.log(f"🗑 ลบบัญชีรับไอเทมฟรี (เหลือ {len(self._autoitem_acc_rows)} บัญชี)")

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
            "notify": notify_var,
            "user": user_var,
            "pwd": pwd_var,
            "type": type_var,
            "pwd_entry": pwd_entry,
            "type_cb": type_cb,
        }
        self._autoitem_acc_rows.append(row_data)
        if getattr(self, "_autoitem_show_pwd", None) and self._autoitem_show_pwd.get():
            pwd_entry.configure(show="", fg=FG)
        self._autoitem_update_acc_count()
        if user_action:
            self.log(
                f"➕ เพิ่มบัญชีรับไอเทมฟรี #{idx} (รวม {len(self._autoitem_acc_rows)} บัญชี)"
            )

    def _autoitem_reindex(self):
        for i, r in enumerate(self._autoitem_acc_rows, 1):
            r["idx_lbl"].configure(text=f"{i}.")

    def _refresh_autoitem_type_lock(self):
        """ล็อกดรอปดาวน์ประเภทไอดีของทุกบัญชีรับไอเทมฟรีไว้ ตอนที่ 'เปิดใช้งาน
        อัตโนมัติ' ติ๊กอยู่ หรือระหว่างกำลังกด 'รับตอนนี้' (busy) — กันมือไปโดน
        เปลี่ยนประเภทไอดีโดยไม่ตั้งใจ ปลดล็อกอัตโนมัติเมื่อปิดออโต้และไม่ได้กำลัง
        รับไอเทมอยู่แล้วเท่านั้น"""
        locked = bool(
            getattr(self, "_autoitem_var", None) and self._autoitem_var.get()
        ) or bool(getattr(self, "_autoitem_claim_busy", False))
        for r in self._autoitem_acc_rows:
            cb = r.get("type_cb")
            if cb is None:
                continue
            try:
                cb.configure(state="disabled" if locked else "readonly")
            except Exception as _e:
                _logger.debug("ignored error at app_autoitem.py:503: %s", _e)

    def _autoitem_toggle_pwd_mask(self):
        visible = self._autoitem_show_pwd.get()
        for r in self._autoitem_acc_rows:
            entry = r.get("pwd_entry")
            if entry:
                entry.configure(
                    show="" if visible else "•", fg=FG if visible else FG2
                )
        self.log(
            f"{'👁 แสดง' if visible else '🙈 ซ่อน'}รหัสผ่านบัญชีรับไอเทมฟรี ({len(self._autoitem_acc_rows)} บัญชี)"
        )

    def _autoitem_update_acc_count(self, *_):
        enabled = len(self._autoitem_valid_accounts())
        lbl = getattr(self, "_autoitem_acc_count_lbl", None)
        if lbl:
            lbl.configure(text=f"[{enabled} ไอดี]", fg=STATUS_ACTIVE if enabled else "#888")

    def _autoitem_valid_accounts(self):
        """แหล่งกลางของบัญชี AutoItem ที่กรอกครบ ลดการเช็คซ้ำคนละแบบในแต่ละเมธอด."""
        return [
            r
            for r in self._autoitem_acc_rows
            if r["user"].get().strip() and r["pwd"].get().strip()
        ]

    def _autoitem_account_values(self):
        return [
            (
                r["user"].get().strip(),
                r["pwd"].get().strip(),
                r["type"].get().strip(),
                r["notify"].get(),
            )
            for r in self._autoitem_valid_accounts()
        ]

    def _autoitem_clear_acc(self, silent=False):
        n = len(self._autoitem_acc_rows)
        for r in self._autoitem_acc_rows:
            r["frm"].destroy()
        self._autoitem_acc_rows.clear()
        self._autoitem_update_acc_count()
        self._autoitem_last_loaded_path = None
        self._refresh_file_combobox(
            getattr(self, "_autoitem_recent_files", None) or [],
            "autoitem_file_cb",
            "_autoitem_file_cb_paths",
        )
        if not silent:
            self.log(f"🗑 ล้างบัญชีรับไอเทมฟรีทั้งหมด ({n} บัญชี)")

    def _read_autoitem_account_rows(self, path):
        """อ่านไฟล์บัญชี .txt ของโหมดรับไอเทมฟรี (บรรทัดละ ไอดี,รหัส,ประเภท)
        กลับเป็น list ของ (user, password, login_type) — ใช้ร่วมกันทั้งปุ่ม
        'โหลด .txt' และ dropdown เลือกไฟล์ เพื่อให้ผลลัพธ์ตรงกันเสมอ"""
        parsed = []
        with open(path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        for line in lines:
            parts = line.split(",")
            u = parts[0].strip() if len(parts) > 0 else ""
            p = parts[1].strip() if len(parts) > 1 else ""
            if not u or not p:
                continue
            t_raw = parts[2].strip().lower() if len(parts) > 2 else "gameid"
            t = "GG Passport" if "gg" in t_raw else "Game ID"
            parsed.append((u, p, t))
        return parsed

    def _autoitem_load_file(self):
        path = filedialog.askopenfilename(
            title="เลือกไฟล์บัญชี (.txt)",
            filetypes=[("ไฟล์ข้อความ", "*.txt"), ("ทั้งหมด", "*.*")],
        )
        if not path:
            return
        try:
            parsed = self._read_autoitem_account_rows(path)
            existing = {
                r["user"].get().strip()
                for r in self._autoitem_acc_rows
                if r["user"].get().strip()
            }
            added, skipped = 0, 0
            for u, p, t in parsed:
                if u in existing:
                    skipped += 1
                    continue
                self._autoitem_add_acc(u, p, t)
                existing.add(u)
                added += 1
            self._remember_recent_file(
                path,
                "_autoitem_recent_files",
                "_autoitem_last_loaded_path",
                "autoitem_file_cb",
                "_autoitem_file_cb_paths",
            )
            msg = f" โหลด {added} บัญชี (รับไอเทมฟรี) จาก: {path}"
            if skipped:
                msg += f" (ข้ามซ้ำ {skipped} บัญชี)"
            self.log(msg)
        except Exception as e:
            self._alert_error("ข้อผิดพลาด", f"โหลดไฟล์ไม่ได้: {e}")

    def _on_autoitem_file_selected(self, _evt=None):
        """เลือกไฟล์จาก dropdown (แท็บรับไอเทมฟรี) → โหลดบัญชีของไฟล์นั้นแทนที่
        ลิสต์ปัจจุบัน (มี confirm ถ้าลิสต์ปัจจุบันมีบัญชีอยู่)"""
        cb = getattr(self, "autoitem_file_cb", None)
        paths = getattr(self, "_autoitem_file_cb_paths", None) or []
        if cb is None:
            return
        idx = cb.current()
        if idx < 0 or idx >= len(paths):
            return
        path = paths[idx]
        if not os.path.exists(path):
            self._remove_recent_file(
                path,
                "_autoitem_recent_files",
                "_autoitem_last_loaded_path",
                "autoitem_file_cb",
                "_autoitem_file_cb_paths",
            )
            self._alert_error("ข้อผิดพลาด", f"ไม่พบไฟล์: {path}")
            return
        try:
            parsed = self._read_autoitem_account_rows(path)
        except Exception as e:
            self._alert_error("ข้อผิดพลาด", f"โหลดไฟล์ไม่ได้: {e}")
            return
        current = self._autoitem_valid_accounts()
        if current and getattr(self, "_autoitem_last_loaded_path", None) != path:
            if not self._confirm_dialog(
                "แทนที่บัญชีรับไอเทมฟรี",
                lines=[
                    f"แทนที่บัญชีรับไอเทมฟรีปัจจุบัน ({len(current)} บัญชี) ด้วยบัญชีจากไฟล์ "
                    f"'{os.path.basename(path)}' ({len(parsed)} บัญชี) หรือไม่?"
                ],
                confirm_text="แทนที่",
                cancel_text="ยกเลิก",
            ):
                self._refresh_file_combobox(
                    getattr(self, "_autoitem_recent_files", None) or [],
                    "autoitem_file_cb",
                    "_autoitem_file_cb_paths",
                    selected_path=getattr(self, "_autoitem_last_loaded_path", None),
                )
                return
        for r in self._autoitem_acc_rows:
            r["frm"].destroy()
        self._autoitem_acc_rows.clear()
        for u, p, t in parsed:
            self._autoitem_add_acc(u, p, t)
        self._autoitem_update_acc_count()
        if getattr(self, "_autoitem_canvas", None):
            self._autoitem_canvas.yview_moveto(0)
        self._remember_recent_file(
            path,
            "_autoitem_recent_files",
            "_autoitem_last_loaded_path",
            "autoitem_file_cb",
            "_autoitem_file_cb_paths",
        )
        self.log(
            f"📂 สลับเป็นบัญชีรับไอเทมฟรีจากไฟล์: "
            f"{os.path.basename(path)} ({len(parsed)} บัญชี)"
        )

    def _autoitem_add_wh(self, url="", enabled=True, name_text="", user_action=False):
        idx = len(self._autoitem_wh_rows) + 1

        def delete_wh(row=None):
            if row in self._autoitem_wh_rows:
                self._autoitem_wh_rows.remove(row)
            row.destroy()
            self._autoitem_reindex_wh()
            self._autoitem_update_wh_count()
            self.log(f"🗑 ลบ Webhook รับไอเทมฟรี (เหลือ {len(self._autoitem_wh_rows)} ช่อง)")

        row = WebhookRow(
            self._autoitem_wh_frame,
            idx,
            lambda: delete_wh(row),
            self._autoitem_update_wh_count,
            enabled=enabled,
            log_fn=self.log,
            name_text=name_text,
        )
        if url:
            row.url_var.set(url)
        row.sync_url_log_baseline()
        self._autoitem_wh_rows.append(row)
        self._autoitem_update_wh_count()
        if user_action:
            self.log(
                f"➕ เพิ่ม Webhook รับไอเทมฟรี #{idx} (รวม {len(self._autoitem_wh_rows)} ช่อง)"
            )

    def _autoitem_reindex_wh(self):
        for i, r in enumerate(self._autoitem_wh_rows, 1):
            r.set_index(i)

    def _autoitem_update_wh_count(self, *_):
        total = sum(1 for r in self._autoitem_wh_rows if r.get_data())
        enabled = sum(
            1 for r in self._autoitem_wh_rows if r.get_data() and r.is_enabled()
        )
        lbl = getattr(self, "_autoitem_wh_count_lbl", None)
        if lbl:
            if total:
                lbl.configure(
                    text=f"{enabled}/{total} ช่อง (เปิดใช้/ทั้งหมด)",
                    fg=STATUS_ACTIVE if enabled else "#888",
                )
            else:
                lbl.configure(text="0 ช่อง", fg="#888")

    def _autoitem_clear_wh(self, silent=False):
        n = len(self._autoitem_wh_rows)
        for r in self._autoitem_wh_rows:
            r.destroy()
        self._autoitem_wh_rows.clear()
        self._autoitem_update_wh_count()
        if not silent:
            self.log(f"🗑 ล้าง Webhook รับไอเทมฟรีทั้งหมด ({n} ช่อง)")

    def _autoitem_get_enabled_wh_urls(self):
        return [
            r.get_data()
            for r in self._autoitem_wh_rows
            if r.get_data() and r.is_enabled()
        ]

