"""SFKeyword entry point.

This file used to contain the entire application (~9700 lines). It has been
split into the `sfkeyword_lib` package sitting next to this file — see
`sfkeyword_lib/__init__.py` for the module map. This file is now just the
`--tray` / single-instance / mainloop bootstrap that used to live in the
`if __name__ == "__main__":` block at the bottom of the old sfkeyword.pyw.
"""

import os
import sys
import json
import subprocess
from datetime import datetime

from sfkeyword_lib.app import App
from sfkeyword_lib.core.constants import VERSION
from sfkeyword_lib.core.deps import tk
from sfkeyword_lib.core.paths import DATA_DIR, _resource_path, CONFIG_SYSTEM_FILE, SAVE_FILE
from sfkeyword_lib.core.ui_theme import (
    _round_window_corners,
    _get_window_icon_photo,
    _round_logo_photo,
    _themed_popup,
)
from sfkeyword_lib.core.updater import check_on_startup_sync

import traceback


def _write_crash_log(tb_text, tag="CRASH"):
    """เขียน traceback ลง sfkeyword_crash.log พร้อม rotation กันไฟล์บวมไม่จำกัด
    (คงไว้ที่ไม่เกิน 1MB ต่อไฟล์) ใช้ร่วมกันทั้งตอนโปรแกรม crash ตั้งแต่ startup
    (ก่อน mainloop) และตอน callback ของปุ่ม/UI throw exception ที่ไม่ได้ดักไว้
    ระหว่างโปรแกรมรันอยู่ปกติ (ของเดิมกรณีหลังนี้ Tkinter จะ print ไป stderr
    เฉยๆ ซึ่งใน .pyw ไม่มี console ให้เห็นเลย เท่ากับ exception หายไปเงียบๆ)"""
    try:
        _err_path = os.path.join(DATA_DIR, "sfkeyword_crash.log")
        max_log_size = 1024 * 1024  # 1MB
        if os.path.exists(_err_path) and os.path.getsize(_err_path) > max_log_size:
            try:
                os.remove(_err_path)
            except Exception:
                pass
        tb_to_write = tb_text[-1500:] if len(tb_text) > 1500 else tb_text
        with open(_err_path, "a", encoding="utf-8") as _f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _f.write(f"\n[{timestamp}] {tag}:\n{tb_to_write}\n")
    except Exception:
        pass


def _recently_booted(threshold_sec=120):
    """True ถ้าเครื่องเพิ่งเปิด/รีสตาร์ทมาไม่เกิน threshold_sec วินาที

    ใช้ร่วมกับ _startup_wants_autostart() เพื่อดักเคส Windows เปิดโปรแกรมกลับมา
    เองหลังรีสตาร์ท/ล็อกอินโดยไม่ผ่าน --tray ของเรา (ฟีเจอร์ "จำแอปที่เปิดค้าง
    แล้วเปิดกลับอัตโนมัติ" ของ Windows เอง) — ดูคอมเมนต์ตรงจุดใช้งานใน
    __main__ ด้านล่างว่าทำไมต้องเช็คร่วมกับค่าติ๊กถูก 'เปิดพร้อมวินโดวส์' ด้วย
    ไม่ใช่ใช้เวลาบูตอย่างเดียว (ไม่งั้นคนเปิดโปรแกรมเองด้วยมือภายใน
    threshold_sec วินาทีแรกหลังบูตจะโดนเข้าใจผิดว่าเป็น auto-start ไปด้วย)"""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        uptime_ms = ctypes.windll.kernel32.GetTickCount64()
        return (uptime_ms / 1000.0) < threshold_sec
    except Exception:
        return False


def _startup_wants_autostart():
    """อ่านค่า 'เปิดพร้อมวินโดวส์' ล่าสุดจากไฟล์ตั้งค่าโดยตรง (ไม่ผ่าน UI/App
    เพราะยังไม่มีหน้าต่างตอนนี้) — อ่าน config/system.json ก่อน (ไฟล์ย่อยของ
    ตั้งค่าปัจจุบัน) แล้ว fallback ไปไฟล์เก่า sfkeyword_settings.json ถ้ายังไม่เคย
    migrate เป็นไฟล์ย่อย อ่านไม่ได้/ไม่มีไฟล์ถือว่ายังไม่เปิดใช้ (False)"""
    for path in (CONFIG_SYSTEM_FILE, SAVE_FILE):
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "start_with_windows" in data:
                    return bool(data["start_with_windows"])
        except Exception:
            continue
    return False


def _force_window_foreground(win):
    """บังคับให้หน้าต่างได้โฟกัสจริงตอนเปิดโปรแกรม

    จำเป็นเพราะโปรแกรมนี้เปิดผ่านการ spawn โปรเซส pythonw.exe แยกต่างหาก
    (ดูโค้ดด้านล่าง) ซึ่ง Windows จะไม่ยกหน้าต่างของโปรเซสที่ถูกสร้างแบบ
    background ขึ้นมาโฟกัสให้อัตโนมัติ (foreground lock) ผลคือหน้าต่างเปิด
    ขึ้นมาแต่ยังไม่ได้รับโฟกัสจริง — คลิกครั้งแรกที่ปุ่ม/checkbox/toggle ใดๆ
    เลยกลายเป็นแค่คลิกเพื่อโฟกัสหน้าต่างก่อน ไม่ถูกส่งต่อให้ widget จริง
    ต้องคลิกซ้ำครั้งที่สองสถานะถึงจะเปลี่ยน (ตรงกับปัญหาที่ทุก checkbox/
    toggle ในโปรแกรมต้องกด 2 ครั้งเหมือนกันหมด) — ใช้ trick ตั้ง topmost
    ชั่วคราวเพราะ focus_force() เฉยๆ มักโดน Windows บล็อกเงียบๆ ถ้าโปรเซส
    ไม่ได้เพิ่งรับ input จากผู้ใช้มาก่อน"""
    try:
        win.update_idletasks()
        win.deiconify()
        win.lift()
        win.attributes("-topmost", True)
        win.focus_force()
        win.after(150, lambda: win.attributes("-topmost", False))
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.SetForegroundWindow(win.winfo_id())
        except Exception:
            pass
    # มุมมนหน้าต่างหลัก (Windows) — โชว์แล้วค่อยทำ จะได้มี HWND/ขนาดจริง
    # (Windows 10 fallback = SetWindowRgn ซึ่งหลุดเมื่อ resize → bind ยิงซ้ำ)
    _round_window_corners(win)
    try:
        win.bind("<Configure>", lambda _e: _round_window_corners(win), add="+")
    except Exception:
        pass


def _set_windows_dpi_awareness():
    """ตั้งค่า DPI awareness ให้โปรแกรมก่อนสร้างหน้าต่างแรก — ต้องเรียกให้เร็ว
    ที่สุดตั้งแต่ก่อน tk.Tk() ตัวแรก ไม่งั้น Windows จะ scale หน้าต่างเป็นภาพ
    บิตแมป (ไม่ใช่ vector) ให้ ทำให้ตัวอักษร/ไอคอนเบลอเมื่อจอตั้งค่า scaling
    มากกว่า 100% (พบบ่อยทั้งบน Windows 10 และ 11 โดยเฉพาะจอแล็ปท็อป)

    ลองไล่ตาม API ใหม่ไปเก่าเพราะแต่ละตัวรองรับ Windows คนละรุ่น:
    - SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2): Windows 10 1703+
      (รวม Windows 11 ทุก build) — คมชัดสุดและรองรับหลายจอ DPI ไม่เท่ากันด้วย
    - SetProcessDpiAwareness(PER_MONITOR_DPI_AWARE): Windows 8.1+ เผื่อรัน
      บน Windows 10 รุ่นเก่ากว่า 1703 ที่ยังไม่มี API ตัวบน
    - SetProcessDPIAware(): Windows Vista+ เป็น fallback สุดท้ายถ้าสอง
      ตัวบนไม่มีในเครื่อง (system-DPI aware อย่างเดียว ไม่ per-monitor)
    ไล่ลองทีละตัวเงียบๆ ไม่ throw ถ้าไม่มี ไม่ต้องมี admin สิทธิ์"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
            ctypes.windll.user32.SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)
            return
        except Exception:
            pass
        try:
            PROCESS_PER_MONITOR_DPI_AWARE = 2
            ctypes.windll.shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)
            return
        except Exception:
            pass
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    except Exception:
        pass


_SINGLE_INSTANCE_MUTEX = None


def _acquire_single_instance_lock():
    """กันเปิดโปรแกรมซ้อนกันหลายหน้าต่างพร้อมกัน

    ใช้ named mutex ของ Windows แทนไฟล์ lock ธรรมดา เพราะถ้าโปรแกรม crash
    ไฟล์ lock จะค้างและกันไม่ให้เปิดโปรแกรมใหม่ได้อีกเลย ส่วน mutex นั้น OS
    จะปล่อยคืนให้อัตโนมัติทันทีที่โปรเซสตาย ไม่มีทางค้าง
    คืนค่า True = อินสแตนซ์แรก (เปิดได้ปกติ), False = มีโปรแกรมรันอยู่แล้ว"""
    global _SINGLE_INSTANCE_MUTEX
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        ERROR_ALREADY_EXISTS = 183
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel32.CloseHandle.restype = ctypes.c_bool
        # Local namespace ใช้ได้โดยไม่ต้องยกระดับสิทธิ์ และกันซ้ำใน session ของผู้ใช้ได้พอดี
        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(None, False, "Local\\SFKeyword_Client_SingleInstance_9F3E2B7A")
        if not handle:
            return False
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        _SINGLE_INSTANCE_MUTEX = handle
        return True
    except Exception:
        return True


def _warn_already_running():
    try:
        _warn_root = tk.Tk()
        _warn_root.withdraw()
        try:
            from PIL import Image, ImageTk as _ITk
            # ใช้วิธีเดียวกับ v3.9.7: JPEG ต้นฉบับ → LANCZOS → iconphoto
            _icon_src = _resource_path("sf_logo.jpg")
            if os.path.exists(_icon_src):
                _warn_icon_img = Image.open(_icon_src).resize((32, 32), Image.LANCZOS)
                _warn_icon_photo = _ITk.PhotoImage(_warn_icon_img)
                _warn_root._icon_photo = _warn_icon_photo
                _warn_root.iconphoto(True, _warn_icon_photo)
        except Exception:
            pass
        try:
            _warn_root.attributes("-topmost", True)
        except Exception:
            pass
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.SetForegroundWindow(_warn_root.winfo_id())
            except Exception:
                pass
        _themed_popup(
            _warn_root,
            "เปิดโปรแกรมซ้ำ",
            "โปรแกรมเปิดอยู่แล้ว กรุณาปิดหน้าต่างเดิมก่อน\n"
            "ไม่เห็นหน้าต่าง ลองเช็คไอคอนในถาดระบบข้างนาฬิกา",
            kind="warning", buttons="ok")
        _warn_root.destroy()
    except Exception:
        pass


def _show_splash(root):
    """Splash screen แสดงโลโก้ SF + ชื่อโปรแกรม + เวอร์ชัน ระหว่างสร้าง UI หลัก

    ใช้ Toplevel แบบไร้กรอบ (overrideredirect) วางกึ่งกลางจอ — โชว์ทันทีที่
    เรียก แล้วคืน obj ให้ __main__ ปิด (destroy) หลัง App สร้างเสร็จก่อนโชว์
    หน้าต่างหลัก คืน None ถ้าสร้างไม่สำเร็จ (โปรแกรมยังเปิดต่อได้ปกติ)"""
    import time as _time

    splash = None
    try:
        splash = tk.Toplevel(root)
        splash.overrideredirect(True)
        w, h = 400, 300
        x = (splash.winfo_screenwidth() - w) // 2
        y = (splash.winfo_screenheight() - h) // 2
        splash.geometry(f"{w}x{h}+{x}+{y}")
        splash.configure(bg="#0E0F14")

        # โลโก้ SF เป็นรูปโล่ — แสดงรูปเต็มตามสัดส่วนเดิม (circular=False)
        # ไม่ตัดเป็นวงกลม (มุม/ปลายโล่จะโดนตัด ดูแปลก)
        logo_img = _round_logo_photo(96, master=splash, circular=False)
        if logo_img is not None:
            splash._logo_img = logo_img  # กัน garbage collection
            tk.Label(splash, image=logo_img, bg="#0E0F14").pack(pady=(30, 8))

        tk.Label(
            splash,
            text="SFKeyword",
            font=("Leelawadee UI", 24, "bold"),
            fg="#E8455A", bg="#0E0F14",
        ).pack()

        tk.Label(
            splash,
            text=f"v{VERSION}",
            font=("Consolas", 9),
            fg="#A78BFA", bg="#0E0F14",
        ).pack(pady=(14, 0))

        # progress bar สั้นๆ กัน splash ดูนิ่งเกินไป
        bar = tk.Canvas(splash, width=180, height=4, bg="#1C1D27",
                        highlightthickness=0)
        bar.pack(pady=(18, 0))
        bar.create_rectangle(0, 0, 0, 4, fill="#A78BFA", width=0)

        splash.update_idletasks()
        splash.update()
        for i in range(1, 41):
            bar.coords(1, 0, 0, 180 * i // 40, 4)
            splash.update_idletasks()
            _time.sleep(0.02)
        return splash
    except Exception:
        try:
            if splash is not None:
                splash.destroy()
        except Exception:
            pass
        return None


if __name__ == "__main__":
    _set_windows_dpi_awareness()

    if sys.platform == "win32" and os.path.basename(sys.executable).lower() == "python.exe":
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.exists(pythonw):
            subprocess.Popen([pythonw] + sys.argv,
                             creationflags=0x08000000)
            sys.exit()

    if not _acquire_single_instance_lock():
        _warn_already_running()
        sys.exit()

    try:
        root = tk.Tk()

        def _handle_tk_callback_exception(exc, val, tb):
            """Priority 2: Global Exception Handler — ของเดิม Tkinter จะ print
            traceback ไป stderr เฉยๆ เวลา callback ของปุ่ม/widget ใดๆ throw
            exception ที่ไม่ได้ดักไว้ ซึ่งใน .pyw (ไม่มี console แนบมาด้วย)
            เท่ากับ exception หายไปเงียบๆ ทั้งที่โปรแกรมอาจค้างสถานะผิดอยู่
            ตอนนี้ log ลงไฟล์เดียวกับตอน crash ตั้งแต่ startup แทน"""
            tb_text = "".join(traceback.format_exception(exc, val, tb))
            _write_crash_log(tb_text, tag="UNHANDLED CALLBACK EXCEPTION")

        root.report_callback_exception = _handle_tk_callback_exception
        # ซ่อนหน้าต่างทันทีหลังสร้าง กันหน้าต่างเปล่า (ชื่อ default "tk") โผล่วาบ
        # ขึ้นมาระหว่างสร้าง Dashboard (App) — ค่อย deiconify ทีหลังตอน Dashboard
        # พร้อมแสดงจริง (ผ่าน _force_window_foreground)
        root.withdraw()
        # --tray = เราสั่งเปิดเองผ่าน Run key ตอนติ๊ก "เปิดพร้อมวินโดวส์" ไว้ —
        # คนที่ติ๊กไว้จะได้ --tray มาด้วยเสมอ จึงไม่ต้องเดาอะไรเพิ่ม (รันปกติ
        # เหมือน tray-start ตามเดิม) ส่วนคนที่ "เอาติ๊กออก" (start_with_windows
        # = False ในไฟล์ตั้งค่า) แต่ Windows ยังสั่งเปิดโปรแกรมกลับมาเองอยู่ดี
        # ผ่านฟีเจอร์ "จำแอปที่เปิดค้างไว้แล้วเปิดกลับหลังล็อกอิน" ของ Windows
        # เอง (ไม่มี --tray ติดมา เพราะ Windows ไม่รู้จัก Run key ของเรา) — เคส
        # นี้เท่านั้นที่ใช้เวลาบูตเครื่องมาช่วยดัก (ถือว่า auto-start ถ้าเพิ่งบูต
        # มาไม่เกิน 2 นาที) แล้วปฏิบัติเหมือน --tray คือไม่เด้งอะไรเลย ส่วนคนที่
        # ติ๊กไว้ (True) หรือเปิดโปรแกรมเองด้วยมือหลัง 2 นาทีไปแล้ว จะไม่โดน
        # เงื่อนไขนี้แตะเลย เปิดให้ตามปกติทุกครั้งที่คลิกเปิดเอง
        _is_tray_start = "--tray" in sys.argv
        if not _is_tray_start and _recently_booted() and not _startup_wants_autostart():
            _is_tray_start = True
        root.option_add("*Button.takeFocus", 0)
        root.option_add("*Button.highlightThickness", 0)
        root.option_add("*Button.borderWidth", 0)
        root.option_add("*Button.disabledForeground", "#55575E")
        root.option_add("*Button.highlightBackground", "#15161D")
        root.option_add("*Button.highlightColor", "#15161D")
        # ใช้วิธีเดียวกับ v3.9.7: สร้าง PhotoImage จากภาพต้นฉบับ
        # ความละเอียดสูง แล้วลดด้วย LANCZOS เป็น 32×32 ก่อนส่งให้ Tk
        # ห้ามใช้ iconbitmap() กับหน้าต่างหลัก เพราะ Tk บางเวอร์ชันเลือกเฟรม
        # 16×16 ของ ICO แล้วขยายบน taskbar จนภาพแตก
        try:
            # สร้างขนาดภาพตาม DPI จริงของจอ แทนการบังคับ 32×32 ที่ถูก
            # Windows ขยายบนจอ 125/150/200% แล้วทำให้ Taskbar เบลอ
            _icon_photo = _get_window_icon_photo(root)
            if _icon_photo is not None:
                root._icon_photo = _icon_photo
                root.iconphoto(True, _icon_photo)
        except Exception:
            pass
        root.resizable(True, True)
        root.title(f"SFKeyword v{VERSION}")
        root.configure(bg="#15161D")

        # Splash screen — แสดงโลโก้ SF ระหว่างสร้าง Dashboard (App) ให้ดู
        # มืออาชีพ ไม่โชว์ตอน auto-start แบบ --tray (เปิดเงียบๆ ลงถาด)
        _splash = None
        if not _is_tray_start:
            # ── Splash FIRST (before network checks) ──
            # user sees immediate visual feedback — ถ้า network checks
            # ค้าง (DNS/DDoS/rate-limit) จะได้ไม่เห็นหน้าต่างเปล่า + process
            # zombie ใน Task Manager แบบไร้วี่แวว
            _splash = _show_splash(root)
            # ── Kill switch + auto-update BEFORE main window ──
            # ต้องเช็คก่อนสร้าง Dashboard จะได้ไม่เห็นหน้าต่างหลักโผล่แวบ
            # แล้วค่อยเด้ง popup ทับ — check_on_startup_sync บล็อกจนกว่า
            # ผู้ใช้จะกดปิด popup หรืออัปเดตเสร็จ
            try:
                ok = check_on_startup_sync(root)
                if not ok:
                    # kill switch active — user clicked exit
                    sys.exit()
            except Exception:
                pass  # network error → เปิดโปรแกรมต่อได้
        # สร้าง Dashboard (App) ตรงๆ เลย ไม่มีหน้าเช็คใดๆ ให้แสดงก่อน
        # (App.__init__ จะจัดการ title/ขนาดหน้าต่าง/กึ่งกลางจอ/WM_DELETE_WINDOW ให้เอง)
        app = App(root)
        try:
            app._refresh_clear_cookie_btn()
        except Exception:
            pass
        if _splash is not None:
            try:
                _splash.destroy()
            except Exception:
                pass
        # เปิดแบบ --tray (auto-start ตอนเปิดคอม) → ซ่อนลงถาดเงียบๆ ไม่โชว์หน้าต่าง
        # ส่วนเปิดเอง (ไม่มี --tray) → บังคับให้หน้าต่างโฟกัสขึ้นมาทันที
        if _is_tray_start:
            try:
                app._hide_to_tray()
            except Exception:
                pass
        else:
            _force_window_foreground(root)

        root.mainloop()
    except Exception:
        _tb = traceback.format_exc()
        try:
            _err_root = tk.Tk()
            _err_root.withdraw()
            _themed_popup(
                _err_root,
                "ข้อผิดพลาดขณะเริ่มต้น",
                f"โปรแกรม crash:\n\n{_tb[-800:]}",
                kind="error", buttons="ok")
            _err_root.destroy()
        except Exception:
            pass
        _write_crash_log(_tb, tag="CRASH")
        raise
