"""Top-level window chrome: global shortcuts, system tray icon, and the
close/minimize-to-tray handlers."""

import logging

from ..core.constants import ACC, VERSION
from ..core.deps import os, threading
from ..core.paths import _resource_path, set_startup_enabled

_logger = logging.getLogger(__name__)


class AppWindowMixin:
    def _clear_entry_focus_on_bg_click(self, event):
        """คลิกที่ไหนก็ตามที่ไม่ใช่ช่องกรอกข้อความ → ดึงโฟกัสออกจากช่องเดิมทันที
        (ของเดิม Label/Frame รับคลิกไม่ได้ โฟกัสเลยค้างอยู่ที่ช่องพิมพ์ล่าสุด
        พอผู้ใช้เผลอพิมพ์ต่อ ตัวอักษรเลยไปแทรกในช่องเก่าโดยไม่รู้ตัว)"""
        try:
            w = event.widget
            cls = w.winfo_class()
        except Exception:
            return
        if cls in (
            "Entry", "TEntry", "TCombobox", "Spinbox", "TSpinbox", "Listbox",
            "Text", "Menu", "Scrollbar",
        ):
            return
        try:
            self.root.focus_set()
        except Exception as _e:
            _logger.debug("ignored error at app_window.py:30: %s", _e)

    def _log_main_button_click(self, event):
        """บันทึกชื่อปุ่มทุกปุ่มที่ผู้ใช้กดในหน้าต่างหลักเพียงครั้งเดียว.

        ใช้ class binding เพื่อให้ครอบคลุมปุ่มที่เพิ่มภายหลัง เช่น ปุ่มลบบัญชี
        หรือปุ่มล็อกอินรายแถว โดยไม่แตะ callback ของปุ่มและไม่ทำให้คำสั่งเดิม
        ถูกเรียกซ้ำ.
        """
        try:
            button = event.widget
            if button.winfo_toplevel() is not self.root:
                return
            if str(button.cget("state")) == "disabled":
                return
            label = " ".join(str(button.cget("text") or "").split())
            self.log(f"🖱 กดปุ่ม: {label or '(ปุ่มไม่มีชื่อ)'}")
        except Exception as _e:
            _logger.debug("ignored error at app_window.py:48: %s", _e)

    def _global_clipboard_shortcut(self, event):
        """ดัก Ctrl+C/V/X/A จาก keycode ของปุ่มจริง แทนการอิง keysym ตามภาษาคีย์บอร์ด
        ที่เลือกไว้ตอนนั้น (ค่า keycode ของปุ่ม C/V/X/A บนคีย์บอร์ดจะคงที่เสมอ
        ไม่ว่าจะสลับไปใช้ภาษาไทยหรืออังกฤษ) ช่วยให้ก็อปวางได้แม้เปิดคีย์บอร์ดภาษาไทยอยู่

        สำคัญ: ทำงานเฉพาะตอน keysym ไม่ใช่ v/c/x/a ปกติ (เช่น กำลังใช้เลย์เอาต์ภาษาไทย)
        เท่านั้น เพราะถ้าเป็นคีย์บอร์ดอังกฤษปกติ Tk จะมี class-binding เดิมของ
        Entry/Text ที่ดัก Ctrl+V ให้ทำงานอยู่แล้วโดยอัตโนมัติ — ถ้าเรา event_generate
        ซ้ำเข้าไปอีกจะกลายเป็นวางซ้อนสอง (เบิ้ล) ตามที่ผู้ใช้แจ้ง"""
        if not (event.state & 0x0004):
            return None
        widget = event.widget
        try:
            cls = widget.winfo_class()
        except Exception:
            return None
        if cls not in ("Entry", "TEntry", "Text", "TCombobox"):
            return None
        keysym = (getattr(event, "keysym", "") or "").lower()
        if keysym in ("v", "c", "x", "a"):
            return None
        kc = getattr(event, "keycode", None)
        try:
            if kc == 67:
                widget.event_generate("<<Copy>>")
            elif kc == 86:
                widget.event_generate("<<Paste>>")
            elif kc == 88:
                widget.event_generate("<<Cut>>")
            elif kc == 65:
                if cls == "Text":
                    widget.tag_add("sel", "1.0", "end")
                else:
                    widget.selection_range(0, "end")
                    widget.icursor("end")
            else:
                return None
        except Exception:
            return None
        return "break"

    def _on_toggle_start_with_windows(self):
        enabled = self._start_with_windows_var.get()
        ok = set_startup_enabled(enabled)
        if ok:
            self.log(
                f"🔧 ตั้งค่า 'เปิดพร้อมวินโดวส์' → {'✅ เปิด' if enabled else '⬜ ปิด'} — "
                f"เปิดคอมค้างไว้ โปรแกรมจะรันซ่อนในถาดอัตโนมัติหลังบูต"
            )
        else:
            self.log("⚠ ตั้งค่าเปิดพร้อมวินโดวส์ไม่สำเร็จ (รองรับเฉพาะ Windows)")

    def _init_tray_icon(self):
        """สร้างไอคอนในถาดระบบ (system tray) — ให้โปรแกรมซ่อนทำงานอยู่เบื้องหลังได้
        เหมือนโปรแกรมอื่นๆ (การ์ดจอ/แอนตี้ไวรัส ฯลฯ) แทนที่จะปิดโปรแกรมไปเลย"""
        if getattr(self, "_tray_icon", None) is not None:
            return
        try:
            import pystray
            from PIL import Image

            icon_path = _resource_path("sf_logo.ico")
            if os.path.exists(icon_path):
                img = Image.open(icon_path)
            else:
                jpg_path = _resource_path("sf_logo.jpg")
                img = (
                    Image.open(jpg_path)
                    if os.path.exists(jpg_path)
                    else Image.new("RGB", (64, 64), ACC)
                )
            menu = pystray.Menu(
                pystray.MenuItem("เปิดหน้าต่าง", self._tray_show, default=True),
                pystray.MenuItem("ออกจากโปรแกรม", self._tray_quit),
            )
            self._tray_icon = pystray.Icon(
                "sfkeyword", img, f"SFKeyword v{VERSION}", menu
            )
            threading.Thread(target=self._tray_icon.run, daemon=True).start()
        except Exception as e:
            self._tray_icon = None
            try:
                self.log(f"⚠ เปิดระบบ tray ไม่สำเร็จ: {e} (รัน: pip install pystray)")
            except Exception as _e:
                _logger.debug("ignored error at app_window.py:131: %s", _e)

    def _tray_show(self, icon=None, item=None):
        def _do():
            self.root.deiconify()
            self.root.state("normal")
            self.root.lift()
            self.root.focus_force()
            # ทำมุมมนใหม่ตอนคืนจากถาด (region ของ Windows 10 หลุดได้ตอน resize/ซ่อน)
            try:
                from ..core.ui_theme import _round_window_corners

                _round_window_corners(self.root)
            except Exception:
                pass

        self.root.after(0, _do)

    def _tray_quit(self, icon=None, item=None):
        if getattr(self, "_tray_icon", None):
            # pystray.Icon.stop() อาจค้างได้ (รอให้ event loop ของ daemon thread
            # ประมวลผล quit message — ถ้า thread ติด busy-loop จะ hang ไปตลอด)
            # ใช้ thread แยก + timeout 3 วิ กัน on_close_window ถูกบล็อก
            def _stop_tray():
                try:
                    self._tray_icon.stop()
                except Exception:
                    pass
            t = threading.Thread(target=_stop_tray, daemon=True)
            t.start()
            t.join(timeout=3.0)
        self.root.after(0, self.on_close_window)

    def _hide_to_tray(self):
        """กด X บนหน้าต่าง → ซ่อนลงถาดระบบแทนการปิดโปรแกรม
        (งาน/ตารางเวลาที่กำลังรันอยู่เบื้องหลังไม่ถูกตัด)
        ถ้า tray เปิดไม่สำเร็จ → ปิดโปรแกรมแทน (กัน process ค้าง)"""
        self._init_tray_icon()
        if self._tray_icon is None:
            # tray icon เปิดไม่สำเร็จ — ซ่อนหน้าต่าง = ผู้ใช้มองไม่เห็น = zombie process
            # ปิดโปรแกรมแทนดีกว่าค้างอยู่ใน Task Manager แบบไม่มี UI
            self.on_close_window()
            return
        self.root.withdraw()
        try:
            self.log(
                "ℹ️ ซ่อนหน้าต่างลงถาดระบบแล้ว — คลิกไอคอนเพื่อเปิดใหม่ "
                "หรือคลิกขวา → ออกจากโปรแกรม เพื่อปิดจริง"
            )
        except Exception as _e:
            _logger.debug("ignored error at app_window.py:161: %s", _e)

    def on_close_window(self):
        self._stop_event.set()
        if self._timer_after_id:
            self.root.after_cancel(self._timer_after_id)
            self._timer_after_id = None
        self._save_settings()
        # ตั้งค่า 'ปิดเซสชันเมื่อปิดหน้าต่างแอป' (หน้าตั้งค่า) — ล้าง session
        # ทั้งหมดในหน่วยความจำก่อนออกโปรแกรม ไม่เหลือค้าง (คุกกี้บนดิสก์ยังอยู่
        # → รอบหน้าเปิดมาล็อกอินผ่านคุกกี้ได้ไวเหมือนเดิม) ทำแบบ sync ตรงนี้
        # เพราะ root กำลังจะ destroy — ใช้ root.after ไม่ทัน
        try:
            _ce = getattr(self, "_close_on_exit_var", None)
            if _ce is not None and _ce.get():
                with self._sessions_lock:
                    users = [
                        s.get("username") for s in self._sessions
                        if s.get("username")
                    ]
                    self._sessions.clear()
                    self._logged_in_users.clear()
                store = self._http_session_store()
                for u in users:
                    store.pop(u, None)
                if users:
                    self.log(
                        f"⛔ ปิดเซสชันทั้งหมดก่อนออก ({len(users)} บัญชี)"
                    )
        except Exception as _e:
            _logger.debug("ignored error at on_close_window session close: %s", _e)
        # โหมด Pure HTTP — ไม่มี Chrome ให้บังคับปิด worker ตรวจ _stop_event แล้วหยุดเอง
        perf_logger = getattr(self, "_perf_logger", None)
        if perf_logger is not None:
            perf_logger.stop()
        worker_manager = getattr(self, "_worker_manager", None)
        if worker_manager is not None:
            # wait=False: ไม่บล็อกตอนปิดโปรแกรมรองาน background ที่อาจค้าง
            # (เช่น request เครือข่ายที่ timeout นาน) — os._exit(0) ด้านล่าง
            # จะเคลียร์ process ทั้งหมดอยู่แล้ว แค่บอก manager ให้เลิกรับงานใหม่
            worker_manager.shutdown(wait=False)
        # เขียน log ที่ยังค้างในคิวไฟล์ log ให้ครบก่อนตาย (daemon thread จะโดน
        # ฆ่าพร้อม os._exit(0) ไม่งั้นบรรทัดท้ายๆ จะหายไป)
        drain = getattr(self, "_drain_file_log_queue", None)
        if drain is not None:
            try:
                drain()
            except Exception:
                pass
        # root.destroy + os._exit ต้องทำงานเสมอ — ถ้าไม่ทำ process จะค้าง
        # ใน Task Manager แบบไม่มีหน้าต่าง (zombie) เพราะ mainloop ไม่เคยหยุด
        self.root.destroy()
        os._exit(0)
