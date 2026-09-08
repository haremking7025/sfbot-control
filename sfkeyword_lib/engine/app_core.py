"""Core state: __init__, thread-safety properties, window geometry, and the
main _build_ui() that constructs every Tkinter widget/tab."""

import logging

from ..core.constants import (
    ACC,
    ACC2,
    BG,
    BG2,
    BG3,
    BG4,
    BORDER,
    FG,
    FG2,
    FG3,
    VERSION,
)
from ..core.deps import Image, ImageTk, os, queue, re, threading, tk, ttk
from ..core.paths import SAVE_FILE, _resource_path, set_startup_enabled
from ..core.perf_logger import PerformanceLogger
from ..core.worker_manager import WorkerManager

_logger = logging.getLogger(__name__)


class AppCoreMixin:
    MAX_LOG_LINES = 2000

    # Bug 3 fix: self._is_running เดิมเขียนจาก UI thread แต่อ่านจาก worker thread
    # พร้อมกันโดยไม่มี lock — ใช้ property ผูกกับ lock แทน ให้ปลอดภัยอัตโนมัติทุกจุด
    @property
    def _is_running(self):
        with self._is_running_lock:
            return self._is_running_flag

    @_is_running.setter
    def _is_running(self, value):
        with self._is_running_lock:
            self._is_running_flag = value

    def _is_busy(self):
        """True ขณะมีงานทำงานอยู่ หรือกำลังรอ worker ที่ค้างปิดตัวลง หรือกำลังมี
        การล็อกอินใหม่เฉพาะรายไอดี (_relogin_row) อยู่อย่างน้อย 1 ไอดี"""
        with self._workers_draining_lock:
            draining = self._workers_draining
        with self._active_relogins_lock:
            has_active_relogin = self._active_relogins > 0
        return self._is_running or draining or has_active_relogin

    def _drain_stuck_workers(self, threads, label):
        """ปิดงานที่เกินเวลาและกันไม่ให้เริ่มรอบใหม่จนกว่า worker เดิมจะจบจริง"""
        with self._workers_draining_lock:
            if self._workers_draining:
                return
            self._workers_draining = True
        self._stop_event.set()
        self.log(f"⚠ [{label}] กำลังหยุด worker ที่ค้างอยู่ — ยังเริ่มรอบใหม่ไม่ได้")
        # โหมด Pure HTTP — ไม่มี Chrome ให้บังคับปิด worker ตรวจ _stop_event แล้ว
        # หยุดเอง; เหลือแค่ join รอให้จบจริงก่อนเริ่มรอบใหม่

        def _wait_for_workers():
            for worker in threads:
                worker.join()
            with self._workers_draining_lock:
                self._workers_draining = False
            self.log(f"✔ [{label}] worker ที่ค้างปิดตัวครบแล้ว — พร้อมเริ่มงานใหม่")

        threading.Thread(target=_wait_for_workers, daemon=True).start()

    def _completed_pairs_has(self, pair):
        with self._completed_pairs_lock:
            return pair in self._completed_pairs

    def _completed_pairs_add(self, pair):
        with self._completed_pairs_lock:
            self._completed_pairs.add(pair)

    def _completed_pairs_reset(self):
        with self._completed_pairs_lock:
            self._completed_pairs = set()

    def _completed_pairs_restore(self, pairs_iterable):
        with self._completed_pairs_lock:
            self._completed_pairs = set(pairs_iterable)

    def _snapshot_completed_pairs(self):
        with self._completed_pairs_lock:
            return [list(p) for p in self._completed_pairs]

    def __init__(self, root, container=None):
        self.root = root
        self.container = container if container is not None else root
        if container is None:
            _title = f"SFKeyword v{VERSION}"
            self.root.title(_title)
            self.root.update_idletasks()

            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            w = min(1200, int(sw * 0.78))
            h = min(850, int(sh * 0.82))
            x = (sw - w) // 2
            y = (sh - h) // 2
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self.root.minsize(1050, 700)
            self.root.resizable(True, True)
            self.root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        self.container.configure(bg=BG)

        # จุดศูนย์กลางสำหรับงานพื้นหลังแบบ fire-and-forget (ปุ่มกดต่างๆ,
        # polling loop ฯลฯ) แทนการเปิด threading.Thread(daemon=True) เองทุกจุด
        # ดู worker_manager.py — ยังไม่ครอบคลุม thread-per-account ของ
        # login/keyword/autoitem ซึ่งมี concurrency control เฉพาะของมันเองอยู่แล้ว
        self._worker_manager = WorkerManager(max_workers=16)

        # Tkinter ไม่ thread-safe: การเรียก `root.after` จาก worker thread ตรงๆ
        # จะฟ้อง "RuntimeError: main thread is not in main loop" เป็นครั้งคราว
        # (จังหวะที่ main thread ไม่อยู่ใน mainloop ชั่วขณะ เช่น กำลังบันทึกไฟล์
        # settings/เปิด file dialog/วาด UI เยอะๆ) — ถ้าเกิดกับ worker ตัวสำคัญ
        # (run_auto/run_logins/relogin/autoitem loop) จะ crash กลางคันและปุ่ม UI
        # ค้างสถานะ "กำลังรัน..." อยู่ตลอดไป หรือขึ้น "❌ หยุดกะทันหัน" ทั้งที่
        # ไม่ได้มีอะไรผิดปกติ — แก้โดย wrapper ให้ call จาก worker thread ไปเข้า
        # คิว แล้ว _drain_log_queue (UI thread, ทุก 80ms) เป็นคนเรียก root.after
        # จริงบน main thread อีกที (รูปแบบเดียวกับ _ui_log_queue ที่ใช้อยู่แล้ว)
        self._ui_callback_queue = queue.Queue()
        _orig_root_after = self.root.after

        def _safe_after(ms, func=None, *args):
            if threading.current_thread() is threading.main_thread():
                return _orig_root_after(ms, func, *args)
            try:
                self._ui_callback_queue.put((ms, func, args))
            except Exception:
                pass
            return None

        self.root.after = _safe_after
        self._orig_root_after = _orig_root_after

        # เขียน log ของหน้าจอ (ทุกบรรทัด = เขียนไฟล์ .log/.jsonl/error.log)
        # ผ่าน thread เดicated แทนการเขียนบน UI thread ตรงๆ — เดิม
        # _drain_log_queue วนบน UI thread แล้ว _write_run_log_line เขียนไฟล์
        # + flush ทีละบรรทัด ตอนมีหลายเธรดยิง log พร้อมกันเป็นชุดใหญ่
        # UI จะหน่วงเพราะต้องรอเขียนดิสก์ทุกบรรทัด (ดู app_logging.py)
        self._file_log_queue = queue.Queue()
        self._file_log_thread = threading.Thread(
            target=self._file_log_loop, daemon=True
        )
        self._file_log_thread.start()

        # เก็บ RAM/thread ของโปรแกรมเองทุก 60 วิ ลง
        # sfkeyword_perf.log — ใช้เป็นข้อมูลจริงประกอบ memory leak audit (อ่านโค้ด
        # เฉยๆ บอกไม่ได้ว่า RAM โตขึ้นเรื่อยๆ ระหว่างใช้งานจริงหลายชั่วโมงหรือไม่)
        self._perf_logger = PerformanceLogger(
            worker_manager=self._worker_manager, interval_sec=60
        )
        self._perf_logger.start()

        self._rows = []
        self._keyword_rows = []
        # รายชื่อไฟล์ .txt ที่เคยโหลด (dropdown เลือกไฟล์ในแท็บคีย์เวิร์ด/บัญชี)
        # — เก็บ path ไว้ใน memory + settings เพื่อเลือกโหลดซ้ำได้
        self._kw_recent_files = []
        self._kw_last_loaded_path = None
        self._kw_file_cb_paths = []
        self._acc_recent_files = []
        self._acc_last_loaded_path = None
        self._acc_file_cb_paths = []
        self._autoitem_recent_files = []
        self._autoitem_last_loaded_path = None
        self._autoitem_file_cb_paths = []
        self._ui_log_queue = queue.Queue()
        # ไฟล์ log จริง (.log/.jsonl/error.log) และการลบไฟล์เก่าเกิน
        # LOG_RETENTION_DAYS ถูกจัดการโดย log_system.setup_logging() ที่เรียก
        # ครั้งเดียวตอนโหลดแพ็กเกจแล้ว (ดู app.py) ไม่ต้องทำซ้ำที่นี่
        self._lock_stats = threading.Lock()
        self._success_ids = []
        # ไอดีที่ถูกข้ามเพราะเคยใช้คีย์นี้ไปแล้วในเซสชันนี้ (ทุกคีย์โดนข้าม) —
        # แยกหมวดออกจาก "สำเร็จ" เพื่อให้สรุป/popup บอก "เคยใช้ไปแล้ว" ตรงๆ
        # ไม่หลอกว่าเพิ่งรับของสำเร็จ (ดู run_session_multi)
        self._already_ids = []
        self._failed_ids = []
        self._result_rows = []
        self._failure_details = {}  # สาเหตุจริงต่อไอดีที่ล้มเหลว (ใช้ในสรุปจบรอบรัน + popup)
        self._stats_total = 0  # จำนวนไอดีทั้งหมดที่ตั้งเป้าไว้ในรอบนี้ (ไว้คำนวณ "กำลังดำเนินการ")

        self._sessions = []
        self._sessions_lock = threading.Lock()
        # แยก "เคยล็อกอินสำเร็จในรอบนี้" ออกจาก session ที่ยังค้างอยู่ในลิสต์
        # (session อาจถูกปิด/เคลียร์ได้โดยไม่ใช่การล็อกอินล้มเหลว)
        self._logged_in_users = set()
        # เก็บผลจริงของ do_login แต่ละไอดีว่า "ข้ามล็อกอินด้วย cookie ได้จริง"
        # หรือไม่ (ไม่ใช่แค่เช็คว่าตอนเริ่มมี cookie ใหม่พอ) ใช้คู่กับ _sessions_lock
        # เพื่อให้สถิติ "ใช้ cookie กี่ไอดี / ล็อกอินใหม่กี่ไอดี" ตรงกับสิ่งที่เกิดขึ้นจริง
        self._cookie_login_result = {}

        self._stop_event = threading.Event()
        self._workers_draining = False
        self._workers_draining_lock = threading.Lock()
        self._is_running_lock = threading.Lock()
        self._is_running = False
        # นับ "ล็อกอินใหม่เฉพาะไอดีเดียว" ที่กำลังทำงาน — แยกจาก self._is_running
        # เพราะ relogin รายแถวไม่แตะ state ของรอบใหญ่ แต่ _is_busy() ต้องรู้ด้วย
        # ไม่งั้นกดรันรอบใหญ่ระหว่างนั้นจะเคลียร์ session ที่ relogin ใช้อยู่
        self._active_relogins = 0
        self._active_relogins_lock = threading.Lock()

        self._run_start_time = None
        self._total_tasks = 0
        self._done_tasks = 0
        self._timer_after_id = None

        # Bug 1 fix: _completed_pairs เป็น set() ธรรมดา ถูกอ่าน/เขียนพร้อมกันจากหลาย thread
        # ใน run_session_multi โดยไม่มี lock มาก่อน อาจเกิด RuntimeError: Set changed size
        self._completed_pairs = set()
        self._completed_pairs_lock = threading.Lock()

        self._watchdog_active = False
        self._watchdog_last_done = 0

        self._build_ui()
        self._drain_log_queue()
        self._load_settings()

        self.root.bind_all("<Button-1>", self._clear_entry_focus_on_bg_click, add="+")
        # Audit every clickable tk.Button in the main window from one central
        # place.  Individual commands do not need to repeat this logging code.
        # Dialog buttons are deliberately excluded so normal confirmations do
        # not clutter the main activity log.
        # Press is used (rather than release) so destructive button commands
        # such as deleting an account are logged before they destroy themselves.
        self.root.bind_class(
            "Button", "<ButtonPress-1>", self._log_main_button_click, add="+"
        )

        self.root.bind_all("<Key>", self._global_clipboard_shortcut, add="+")

        if self.container is self.root:
            self._init_tray_icon()
            if not os.path.exists(SAVE_FILE):
                self._start_with_windows_var.set(True)
                set_startup_enabled(True)
                if getattr(self, "_tgl_startup_update", None):
                    self._tgl_startup_update()

        self._bind_all_setting_logs()
        if self._auto_apply_delay_var.get():
            self.root.after(400, lambda: self._apply_login_delay(silent=True))

        self._schedule_autosave()

    def _clamp_geometry_to_screen(self, geo_str):
        try:
            m = re.match(r"^(\d+)x(\d+)(?:([+-]\d+)([+-]\d+))?$", geo_str.strip())
            if not m:
                return geo_str
            w, h = int(m.group(1)), int(m.group(2))
            x = int(m.group(3)) if m.group(3) else None
            y = int(m.group(4)) if m.group(4) else None

            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()

            w = max(400, min(w, screen_w - 40))
            h = max(300, min(h, screen_h - 40))

            if x is not None and y is not None:
                x = max(0, min(x, screen_w - 150))
                y = max(0, min(y, screen_h - 60))
                return f"{w}x{h}+{x}+{y}"
            return f"{w}x{h}"
        except Exception:
            return geo_str

    def _build_ui(self):
        # ใช้สีกลางจาก constants โดยตรง (เดิมนิยาม local ซ้ำค่าคงที่)
        root = self.container

        style = ttk.Style(root)
        style.theme_use("default")

        style.configure("Dark.TFrame", background=BG)
        # สีขอบคงที่ (ไม่เปลี่ยนตอนโฟกัส/คลิก) — เดียวกับกรอบของแถวบัญชี
        _cb_border = "#2E313F"
        style.configure(
            "Dark.TCombobox",
            fieldbackground=BG2,
            background=BG2,
            foreground=FG2,
            selectbackground=BG2,
            selectforeground=FG2,
            bordercolor=_cb_border,
            lightcolor=_cb_border,
            darkcolor=_cb_border,
            # Tk 8.6+ วาด "focus ring" แยกจาก bordercolor ด้วย -focuscolor เอง —
            # ต้องล็อกให้เป็นสีเดียวกับขอบ ไม่งั้นกรอบเส้นปะเปลี่ยนสีตอนคลิก/โฟกัส
            focuscolor=_cb_border,
            arrowcolor=FG2,
            relief="flat",
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", "focus", BG2), ("readonly", BG2)],
            background=[("readonly", "focus", BG2), ("readonly", BG2)],
            selectbackground=[("readonly", "focus", BG2), ("readonly", BG2)],
            selectforeground=[("readonly", "focus", FG2), ("readonly", FG2)],
            # บังคับขอบ + focus ring เป็นสีเดียวกันทุกสถานะ (ปกติ/โฟกัส/readonly/
            # pressed/active) ไม่ให้ดึงสีไฮไลต์ของธีมระบบมาใช้ตอนคลิก
            bordercolor=[
                ("readonly", "focus", _cb_border),
                ("readonly", _cb_border),
                ("focus", _cb_border),
                ("!focus", _cb_border),
                ("pressed", _cb_border),
                ("active", _cb_border),
                (_cb_border,),
            ],
            lightcolor=[
                ("readonly", "focus", _cb_border),
                ("readonly", _cb_border),
                ("focus", _cb_border),
                ("!focus", _cb_border),
                ("pressed", _cb_border),
                ("active", _cb_border),
                (_cb_border,),
            ],
            darkcolor=[
                ("readonly", "focus", _cb_border),
                ("readonly", _cb_border),
                ("focus", _cb_border),
                ("!focus", _cb_border),
                ("pressed", _cb_border),
                ("active", _cb_border),
                (_cb_border,),
            ],
            focuscolor=[
                ("readonly", "focus", _cb_border),
                ("readonly", _cb_border),
                ("focus", _cb_border),
                ("!focus", _cb_border),
                ("pressed", _cb_border),
                ("active", _cb_border),
                (_cb_border,),
            ],
        )
        # ถอด native field ออกจาก layout (ที่วาด focus ring ของตัวเอง) เหลือแค่
        # ลูกศร + พื้นที่กรอก — กรอบ static ให้ Frame ที่ครอบ widget เป็นคนวาด
        # (วิธีเดียวกับสไตล์ AccType.* ของแถวบัญชีใน rows.py)
        try:
            style.layout(
                "Dark.TCombobox",
                [
                    ("Combobox.downarrow", {"side": "right", "sticky": "ns"}),
                    (
                        "Combobox.padding",
                        {
                            "sticky": "nswe",
                            "children": [("Combobox.textarea", {"sticky": "nswe"})],
                        },
                    ),
                ],
            )
        except Exception as _e:
            _logger.debug("ignored layout override error for Dark.TCombobox: %s", _e)
        root.option_add("*TCombobox*Listbox.background", BG2)
        root.option_add("*TCombobox*Listbox.foreground", FG)
        root.option_add("*TCombobox*Listbox.selectBackground", ACC)
        root.option_add("*TCombobox*Listbox.selectForeground", "white")
        root.option_add("*Button.highlightThickness", 0)
        root.option_add("*Button.takeFocus", 0)

        root_pane = tk.Frame(root, bg=BG)
        root_pane.pack(fill="both", expand=True)
        # เก็บ reference ไว้ให้ _inline_toast (ui_theme.py) ใช้เป็น host ของ
        # overlay แจ้งเตือน แทนการเปิด tk.Toplevel แยกหน้าต่าง —
        # ครอบคลุมทั้งแถบเมนูด้านข้างและเนื้อหา กันคลิกหลุดไปโดนปุ่มอื่นระหว่างที่
        # มี overlay ค้างอยู่
        self._root_pane = root_pane

        sidebar = tk.Frame(root_pane, bg=BG2, width=224)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        content = tk.Frame(root_pane, bg=BG)
        content.pack(side="left", fill="both", expand=True)

        logo_area = tk.Frame(sidebar, bg=BG2, height=84)
        logo_area.pack(fill="x")
        logo_area.pack_propagate(False)

        self._logo_img = None
        try:
            # ตรงกับ v3.9.7: ใช้ JPEG ต้นฉบับแบบ RGB แล้ว resize ตรงขนาด
            # ด้วย LANCZOS; ไม่ผ่าน ICO/alpha/thumbnail เพราะจุดนี้คือโลโก้
            # ที่เห็นบนหน้าโปรแกรม และการแปลงเป็น RGBA ทำให้บาง Windows วาดเบลอ
            _logo_path = _resource_path("sf_logo.jpg")
            if os.path.exists(_logo_path):
                _logo_img = Image.open(_logo_path).convert("RGBA").resize((38, 38), Image.LANCZOS)
                self._logo_img = ImageTk.PhotoImage(_logo_img)
                tk.Label(logo_area, image=self._logo_img, bg=BG2).pack(
                    side="left", padx=(18, 8), pady=23
                )
        except Exception as _e:
            _logger.debug("ignored error at app_core.py:logo: %s", _e)
            try:
                self.log(f"⚠ โหลดรูปโลโก้ไม่สำเร็จ: {_e}")
            except Exception as _e2:
                _logger.debug("ignored error at app_core.py:logo2: %s", _e2)

        logo_text = tk.Frame(logo_area, bg=BG2)
        logo_text.pack(side="left", pady=14)
        tk.Label(
            logo_text,
            text="SFKeyword",
            font=("Leelawadee UI", 10, "bold"),
            bg=BG2,
            fg=ACC,
            anchor="w",
            justify="left",
            wraplength=190,
        ).pack(anchor="w")
        tk.Label(
            logo_text,
            text=f"พรีเมียม  ·  v{VERSION}",
            font=("Leelawadee UI", 8, "bold"),
            bg=BG2,
            fg=ACC2,
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        _logo_div = tk.Canvas(sidebar, height=2, bg=BG2, highlightthickness=0)
        _logo_div.pack(fill="x")

        def _draw_logo_div(e=None, c=_logo_div):
            c.delete("all")
            w = c.winfo_width()
            steps = 24
            for i in range(steps):
                x0 = w * i / steps
                x1 = w * (i + 1) / steps
                t = 1 - abs((i / steps) - 0.5) * 2
                shade = int(31 + t * 90)
                color = f"#{shade:02x}{int(shade * 0.30):02x}{int(shade * 0.39):02x}"
                c.create_rectangle(x0, 0, x1, 2, fill=color, width=0)

        _logo_div.bind("<Configure>", _draw_logo_div)

        clock_frame = tk.Frame(sidebar, bg=BG2)
        clock_frame.pack(fill="x", pady=(10, 0))
        self.clock_lbl = tk.Label(
            clock_frame, text="", font=("Consolas", 10), bg=BG2, fg=FG2
        )
        self.clock_lbl.pack(padx=16)
        self._update_clock()

        tk.Frame(sidebar, bg=BORDER, height=1).pack(fill="x", pady=(10, 0))

        self._content_frames = {}
        self._current_page = None

        # แบ่ง sidebar navigation เป็นหมวดพร้อมหัวข้อ (group header) เพื่อให้
        # ดูเป็นระเบียบ ไม่กองรวมกัน — ลำดับตามการใช้งาน: ทำงาน → ข้อมูล → เครื่องมือ
        main_nav_groups = [
            ("ทำงาน", [
                ("run", "▶", "แดชบอร์ด"),
            ]),
            ("ข้อมูล", [
                ("accounts", "◉", "บัญชี"),
                ("keywords", "▤", "คีย์เวิร์ด"),
            ]),
            ("เครื่องมือ", [
                ("autoitem", "🎁", "รับไอเทมฟรี"),
                ("inventory", "📦", "ฝาก/ถอนไอเทม"),
                ("dailykey", "🔑", "คีย์ประจำวัน"),
            ]),
        ]

        bottom_nav_items = [
            ("settings", "⚙", "ตั้งค่า"),
        ]

        nav_frame = tk.Frame(sidebar, bg=BG2)
        nav_frame.pack(fill="x", pady=(14, 0), padx=10)

        bottom_nav_frame = tk.Frame(sidebar, bg=BG2)
        bottom_nav_frame.pack(fill="x", side="bottom", padx=10, pady=(0, 14))

        tk.Frame(sidebar, bg=BORDER, height=1).pack(
            fill="x", side="bottom", pady=(0, 8)
        )

        tk.Frame(sidebar, bg=BORDER, height=1).pack(
            fill="x", side="bottom", pady=(0, 0)
        )

        self._nav_pills = {}
        self._nav_icon_lbls = {}
        self._nav_text_lbls = {}

        def _round_rect(canvas, x0, y0, x1, y1, r, **kw):
            pts = [
                x0 + r,
                y0,
                x1 - r,
                y0,
                x1,
                y0,
                x1,
                y0 + r,
                x1,
                y1 - r,
                x1,
                y1,
                x1 - r,
                y1,
                x0 + r,
                y1,
                x0,
                y1,
                x0,
                y1 - r,
                x0,
                y0 + r,
                x0,
                y0,
            ]
            return canvas.create_polygon(pts, smooth=True, **kw)

        def _build_nav_pill(parent_frame, key, icon, label):
            row_h = 46
            pill = tk.Canvas(
                parent_frame, height=row_h, bg=BG2, highlightthickness=0, cursor="hand2"
            )
            pill.pack(fill="x", pady=3)
            self._nav_pills[key] = pill

            def _redraw(c=pill, k=key):
                c.delete("bg")
                w = c.winfo_width()
                active = self._current_page == k
                if active:
                    _round_rect(c, 0, 0, w, row_h, 10, fill=BG4, outline="", tags="bg")
                    c.create_rectangle(
                        0, 6, 3, row_h - 6, fill=ACC, outline="", tags="bg"
                    )
                c.tag_lower("bg")

            pill.bind("<Configure>", lambda e, f=_redraw: f())
            pill._redraw = _redraw

            icon_lbl = tk.Label(
                pill, text=icon, font=("Leelawadee UI", 12), bg=BG2, fg=ACC2
            )
            pill.create_window(18, row_h // 2, window=icon_lbl, anchor="w")
            text_lbl = tk.Label(
                pill, text=label, font=("Leelawadee UI", 11), bg=BG2, fg=FG3
            )
            pill.create_window(44, row_h // 2, window=text_lbl, anchor="w")
            self._nav_icon_lbls[key] = icon_lbl
            self._nav_text_lbls[key] = text_lbl

            for widget in (pill, icon_lbl, text_lbl):
                widget.bind("<Button-1>", lambda e, k=key: self._nav_switch(k))
                widget.bind("<Enter>", lambda e, k=key: self._nav_hover(k, True))
                widget.bind("<Leave>", lambda e, k=key: self._nav_hover(k, False))

            frm = tk.Frame(content, bg=BG)
            frm.place(x=0, y=0, relwidth=1, relheight=1)
            self._content_frames[key] = frm

        _first_group = [True]
        for header, items in main_nav_groups:
            # หัวข้อหมวด (สีจาง ตัวเล็ก) — คั่นแต่ละกลุ่มให้เห็นเป็นหมวดชัดเจน
            _pad_top = 4 if _first_group[0] else 14
            tk.Label(
                nav_frame,
                text=header,
                font=("Leelawadee UI", 8, "bold"),
                bg=BG2,
                fg=FG3,
                anchor="w",
            ).pack(fill="x", padx=(8, 0), pady=(_pad_top, 0))
            _first_group[0] = False
            for key, icon, label in items:
                _build_nav_pill(nav_frame, key, icon, label)
        for key, icon, label in bottom_nav_items:
            _build_nav_pill(bottom_nav_frame, key, icon, label)

        def _nav_hover(key, on):
            if self._current_page == key:
                return
            bg = BG3 if on else BG2
            self._nav_icon_lbls[key].configure(bg=bg, fg=(FG2 if on else ACC2))
            self._nav_text_lbls[key].configure(bg=bg, fg=(FG2 if on else FG3))
            c = self._nav_pills[key]
            c.configure(bg=bg)

        self._nav_hover = _nav_hover

        def _mk_nav_switch():
            def _nav_switch(key):
                prev = self._current_page
                if prev == key:
                    return
                if prev:
                    self._nav_pills[prev].configure(bg=BG2)
                    self._nav_icon_lbls[prev].configure(
                        bg=BG2, fg=ACC2, font=("Leelawadee UI", 12)
                    )
                    self._nav_text_lbls[prev].configure(
                        bg=BG2, fg=FG3, font=("Leelawadee UI", 11)
                    )
                self._nav_pills[key].configure(bg=BG4)
                self._nav_icon_lbls[key].configure(
                    bg=BG4, fg=ACC, font=("Leelawadee UI", 12, "bold")
                )
                self._nav_text_lbls[key].configure(
                    bg=BG4, fg=FG, font=("Leelawadee UI", 11, "bold")
                )
                self._current_page = key

                def _do_switch():
                    self._content_frames[key].tkraise()
                    if prev:
                        self._nav_pills[prev]._redraw()
                    self._nav_pills[key]._redraw()
                    # flush geometry ทันที — 50+ แถวจะ render เสร็จใน frame เดียว
                    # แทนที่จะเห็นเป็นคลื่น (widget reflow ทีละตัว)
                    self.root.update_idletasks()

                _do_switch()

            return _nav_switch

        self._nav_switch = _mk_nav_switch()

        tab_run = self._content_frames["run"]
        tab_kw = self._content_frames["keywords"]
        tab_acc = self._content_frames["accounts"]
        tab_cfg = self._content_frames["settings"]
        tab_autoitem = self._content_frames["autoitem"]
        tab_dailykey = self._content_frames["dailykey"]
        tab_inventory = self._content_frames["inventory"]
        self._build_autoitem_tab(tab_autoitem)
        self._build_inventory_tab(tab_inventory)

        self._build_keywords_tab(tab_kw)
        self._build_accounts_tab(tab_acc)
        self._build_dashboard_tab(tab_run)
        self._build_dailykey_tab(tab_dailykey)
        self._build_settings_tab(tab_cfg)

        self._nav_switch("run")

    def _bind_mousewheel(self, canvas, inner_frame):
        """เดิมใช้ <Enter>/<Leave> ผูก/ถอด bind_all("<MouseWheel>") ที่ตัว canvas/inner_frame
        เอง ปัญหาคือถ้าเมาส์ขยับไปอยู่เหนือวิดเจ็ตลูกที่วางทับอยู่ (Entry, Label,
        Combobox, ปุ่ม ฯลฯ ในแต่ละแถวของตาราง) จะเกิด <Leave> ของ canvas/inner_frame
        ทันที (เพราะเมาส์ไม่ได้อยู่เหนือตัว widget นั้นตรง ๆ แล้ว) ทำให้ bind_all ถูกถอด
        ทิ้งไปเลยและเลื่อนสกอลล์ไม่ได้อีก ต้องขยับเมาส์ไปจ่อพื้นหลังที่ไม่มีวิดเจ็ตลูก
        (พื้นสีดำ) ถึงจะเลื่อนได้ แก้โดยเปลี่ยนมาผูก MouseWheel แบบ global ตลอดเวลา
        (add="+" ไม่ทับ handler ของ canvas อื่น) แล้วเช็คตำแหน่งเมาส์จริงว่าอยู่ในกรอบ
        canvas นี้หรือไม่ก่อนเลื่อน แทนการเช็คว่าเมาส์ "อยู่เหนือ widget ไหน" """

        def _pointer_over_canvas():
            try:
                if not canvas.winfo_ismapped():
                    return False
                x, y = canvas.winfo_pointerxy()
                x0, y0 = canvas.winfo_rootx(), canvas.winfo_rooty()
                x1, y1 = x0 + canvas.winfo_width(), y0 + canvas.winfo_height()
                return x0 <= x <= x1 and y0 <= y <= y1
            except Exception:
                return False

        def _scroll(ev):
            if not _pointer_over_canvas():
                return
            if ev.state & 0x0001:
                # Shift+ล้อเมาส์ = เลื่อนแนวนอน (ตารางบัญชีที่กว้างกว่าหน้าต่าง
                # ตอนย่อเล็กสุด) — Windows ส่ง wheel มาเป็น <MouseWheel> อย่างเดียว
                # ต้องแยกด้วย state ตรงนี้ ไม่มี <Shift-MouseWheel> ให้ bind
                if inner_frame.winfo_reqwidth() > canvas.winfo_width():
                    canvas.xview_scroll(1 if ev.delta > 0 else -1, "units")
                else:
                    canvas.xview_moveto(0)
                return
            if inner_frame.winfo_reqheight() > canvas.winfo_height():
                canvas.yview_scroll(-1 if ev.delta > 0 else 1, "units")
            else:
                canvas.yview_moveto(0)

        canvas.bind_all("<MouseWheel>", _scroll, add="+")
