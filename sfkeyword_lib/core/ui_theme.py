"""Reusable dark-theme Tkinter widgets and helpers: hex color blending,
mouse-wheel/right-click bindings, hover effects, toast notifications, themed
popups, and the on/off toggle switch widget."""

import logging

from .constants import (
    ACC,
    ACC2,
    BG,
    BG2,
    BG3,
    BORDER,
    DANGER,
    DANGER_STRONG,
    FG,
    FG2,
    FG3,
    GREEN,
    INFO_BLUE,
    STATUS_ACTIVE,
    STATUS_ERR,
    STATUS_FAIL,
    STATUS_OK,
    STATUS_WARN,
)
from .deps import Image, ImageTk, os, sys, tk

_logger = logging.getLogger(__name__)

# แคชโลโก้ SFKeyword ต่อขนาด (กันโหลด/resize ไฟล์ภาพซ้ำทุกครั้งที่ popup เด้ง เช่น
# toast ที่โผล่ถี่ๆ) — เก็บ reference ไว้ในนี้ด้วยเพื่อกัน PhotoImage โดน garbage
# collect หลัง widget ที่ถืออยู่ถูกทำลายไปแล้ว
_LOGO_PHOTO_CACHE = {}


def _page_header(parent, title, icon="", padx=16, bg=None, fg=None, acc=None, border=None):
    """หัวแท็บมาตรฐาน (เหมือนกันทุกหน้า): ไอคอน + ชื่อหนา + เส้นคั่นด้านล่าง.

    ใช้เป็นบรรทัดแรกของทุกแท็บ (แดชบอร์ด/บัญชี/คีย์เวิร์ด/รับไอเทมฟรี/คีย์
    ประจำวัน/ตั้งค่า) เพื่อให้หัวเรื่องของทั้งแอปเป็นแบบเดียวกัน ดูเป็นระเบียบ
    — แต่ละแท็บส่ง padx ตามระยะห่างของเนื้อหาแท็บนั้น (16 หรือ 20)
    """
    bg = bg or BG
    fg = fg or FG
    acc = acc or ACC
    border = border or BORDER
    hdr = tk.Frame(parent, bg=bg)
    hdr.pack(fill="x", padx=padx, pady=(12, 6))
    row = tk.Frame(hdr, bg=bg)
    row.pack(fill="x")
    if icon:
        tk.Label(row, text=icon, font=("Leelawadee UI", 12), bg=bg, fg=acc).pack(
            side="left", padx=(0, 8)
        )
    tk.Label(row, text=title, font=("Leelawadee UI", 13, "bold"), bg=bg, fg=fg).pack(
        side="left"
    )
    tk.Frame(hdr, bg=border, height=1).pack(fill="x", pady=(8, 0))
    return hdr


def _window_icon_size(win=None):
    """คืนขนาดพิกเซลจริงของไอคอนหน้าต่างตาม DPI ของจอ.

    ไอคอน 32px แบบคงที่ถูก Windows ขยายบนจอ 125/150/200% จนเบลอ
    แม้ไฟล์ ICO จะมีเฟรมความละเอียดสูงอยู่แล้ว จึงสร้าง PhotoImage ให้มี
    ขนาดกายภาพพอดีกับ DPI ก่อนส่งเข้า Tk."""
    size = 32
    if sys.platform != "win32":
        return size
    try:
        import ctypes
        dpi = 96
        if win is not None:
            try:
                dpi = int(ctypes.windll.user32.GetDpiForWindow(int(win.winfo_id()))) or 96
            except Exception:
                pass
        if dpi == 96:
            try:
                dpi = int(ctypes.windll.user32.GetDpiForSystem()) or 96
            except Exception:
                pass
        size = max(32, round(32 * dpi / 96))
    except Exception:
        pass
    return size


def _get_window_icon_photo(win=None):
    """สร้างไอคอนหน้าต่างจาก JPG ต้นฉบับด้วยขนาดกายภาพตาม DPI."""
    size = _window_icon_size(win)
    if size in _LOGO_PHOTO_CACHE:
        return _LOGO_PHOTO_CACHE[size]
    photo = None
    try:
        from .deps import Image, ImageTk, _PIL_OK
        from .paths import _resource_path
        if _PIL_OK:
            src = _resource_path("sf_logo.jpg")
            if os.path.exists(src):
                image = Image.open(src).resize((size, size), Image.LANCZOS)
                photo = ImageTk.PhotoImage(image, master=win)
    except Exception as exc:
        _logger.debug("ignored error at ui_theme.py:_get_window_icon_photo: %s", exc)
    _LOGO_PHOTO_CACHE[size] = photo
    return photo


def _get_logo_photo(size=28):
    """คืน ImageTk.PhotoImage ของโลโก้ SFKeyword จากภาพต้นฉบับความละเอียดสูง
    (sf_logo.jpg, fallback sf_logo.ico) resize เป็นสี่เหลี่ยมจัตุรัสขนาด size
    พิกเซล ใช้แปะหัว popup/toast ทุกจุด
    ในโปรแกรม ให้เห็นชัดว่าเป็นของ SFKeyword จริง — คืนค่า None ถ้าไม่มี
    PIL หรือหาไฟล์โลโก้ไม่เจอ (ผู้เรียกต้อง fallback ไปใช้ไอคอน emoji เฉยๆ)"""
    if size in _LOGO_PHOTO_CACHE:
        return _LOGO_PHOTO_CACHE[size]
    photo = None
    try:
        from .deps import Image, ImageTk, _PIL_OK
        from .paths import _resource_path

        if _PIL_OK:
            # ใช้ภาพต้นฉบับความละเอียดสูงก่อน ICO เพราะ ICO บางไฟล์มีเฟรมเล็ก
            src = _resource_path("sf_logo.jpg")
            if not os.path.exists(src):
                src = _resource_path("sf_logo.ico")
            if os.path.exists(src):
                # ให้เหมือน v3.9.7: เปิด JPEG แบบ RGB แล้ว resize ตรงขนาด
                # ด้วย LANCZOS; ไม่แปลงเป็น RGBA/thumbnail และไม่กำหนด master
                # เพราะเส้นทางนี้ให้ Tk วาดภาพคมกว่าใน Windows รุ่นอ้างอิง
                img = Image.open(src).convert("RGBA").resize((size, size), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
    except Exception as _e:
        _logger.debug("ignored error at ui_theme.py:_get_logo_photo: %s", _e)
        photo = None
    _LOGO_PHOTO_CACHE[size] = photo
    return photo


def _round_logo_photo(size=56, master=None, circular=True):
    """คืน ImageTk.PhotoImage โลโก้ SFKeyword (sf_logo.jpg / sf_logo.ico)

    ``circular=True``  → ตัดเป็นวงกลม (ขอบโปร่งใส) — ใช้กับจุดที่อยากได้ทรงกลม
    ``circular=False`` → แสดงรูปเต็มตามสัดส่วนเดิม (โลโก้ SF เป็นรูปโล่ —
    ตัดวงกลมจะโดนมุม/ปลายโล่ตัด ดูแปลก) — ใช้กับ sidebar / splash screen

    ``master`` ต้องเป็น Tk/Toplevel ที่สร้างแล้ว (PhotoImage ต้องมี root)
    คืน None ถ้าไม่มี PIL หรือหาไฟล์ไม่เจอ — ผู้เรียก fallback เอง"""
    try:
        from .deps import Image, ImageTk, _PIL_OK
        from .paths import _resource_path

        if not _PIL_OK:
            return None
        from PIL import ImageDraw
        # ใน EXE รูปถูกฝังไว้ที่ _MEIPASS ผ่าน --add-data → _resource_path ใช้ได้
        # ใน dev mode (รันจาก .pyw) รูปอยู่ใต้ assets/ → ลองทั้งสองตำแหน่ง
        _assets_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "assets",
        )
        src = _resource_path("sf_logo.jpg")
        if not os.path.exists(src):
            src = os.path.join(_assets_dir, "sf_logo.jpg")
        if not os.path.exists(src):
            src = _resource_path("sf_logo.ico")
        if not os.path.exists(src):
            src = os.path.join(_assets_dir, "sf_logo.ico")
        if not os.path.exists(src):
            return None
        img = Image.open(src)
        if circular:
            side = min(img.width, img.height)
            left = (img.width - side) // 2
            top = (img.height - side) // 2
            img = img.crop((left, top, left + side, top + side)).resize(
                (size, size), Image.LANCZOS
            )
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
            img = img.convert("RGBA")
            img.putalpha(mask)
        else:
            # รักษาสัดส่วนเดิม ไม่ตัด ไม่บีบ — ขยาย/ย่อให้พอดีกรอบ size×size
            img = img.convert("RGBA")
            scale = min(size / img.width, size / img.height)
            nw = max(1, int(img.width * scale))
            nh = max(1, int(img.height * scale))
            img = img.resize((nw, nh), Image.LANCZOS)
        return ImageTk.PhotoImage(img, master=master)
    except Exception as _e:
        _logger.debug("ignored error at ui_theme.py:_round_logo_photo: %s", _e)
        return None


def _set_toplevel_icon(win):
    """ตั้งไอคอน title bar ของหน้าต่าง Toplevel ให้เป็นโลโก้ SFKeyword เรียกใช้กับทุก
    หน้าต่าง/popup ที่ผุดขึ้นมาในโปรแกรม เพื่อให้ตรงกับหน้าต่างหลักเสมอ
    ไม่ใช่ไอคอน Tk เริ่มต้น — เงียบไว้ถ้าหาไฟล์ไม่เจอหรือแพลตฟอร์มไม่รองรับ

    ใช้แนวทางเดียวกับ v3.9.7: สร้าง PhotoImage จาก JPEG ต้นฉบับ 288×288
    แล้วลดด้วย LANCZOS เป็น 32×32 ก่อนส่งให้ Tk ซึ่งเป็นวิธีที่ให้ไอคอน
    บน title bar/taskbar คมที่สุดในรุ่นอ้างอิง ส่วน ICO ใช้เป็น fallback เท่านั้น"""
    try:
        photo = _get_window_icon_photo(win)
        if photo is not None:
            win._window_icon_photo = photo
            win.iconphoto(False, photo)
            return
    except Exception as _e:
        _logger.debug("ignored error at ui_theme.py:_set_toplevel_icon iconphoto: %s", _e)
    try:
        from .paths import _resource_path

        icon_src = _resource_path("sf_logo.ico")
        if os.path.exists(icon_src):
            win.iconbitmap(icon_src)
    except Exception as _e:
        _logger.debug("ignored error at ui_theme.py:_set_toplevel_icon: %s", _e)


def _lighten_hex(hex_color, amount=0.15):
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    r = min(255, int(r + (255 - r) * amount))
    g = min(255, int(g + (255 - g) * amount))
    b = min(255, int(b + (255 - b) * amount))
    return f"#{r:02x}{g:02x}{b:02x}"


def _blend_hex(hex_a, hex_b, t):
    """ผสมสี hex_a เข้ากับ hex_b ตามสัดส่วน t (0 = hex_a ล้วน, 1 = hex_b ล้วน)."""
    a = hex_a.lstrip("#")
    b = hex_b.lstrip("#")
    ar, ag, ab = (int(a[i : i + 2], 16) for i in (0, 2, 4))
    br, bg, bb = (int(b[i : i + 2], 16) for i in (0, 2, 4))
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg - ag) * t)
    bl = round(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{bl:02x}"


def _bind_combobox_wheel_local(cb):
    """เลื่อนสกอลล์เมาส์ตอนชี้อยู่เหนือ Combobox แล้วให้เปลี่ยนค่าใน Combobox นั้นเท่านั้น
    (ของเดิม canvas ที่ครอบตารางบัญชีดัก <MouseWheel> ไว้แบบ bind_all ทำให้เลื่อนสกอลล์
    เพื่อเปลี่ยนค่า Game ID/GG Passport แล้วทั้งตารางเลื่อนตามไปด้วย)"""

    def _on_wheel(event):
        try:
            values = cb.cget("values")
            if not values:
                return "break"
            cur = cb.current()
            if cur < 0:
                cur = 0
            step = -1 if event.delta > 0 else 1
            new_idx = max(0, min(len(values) - 1, cur + step))
            if new_idx != cur:
                cb.current(new_idx)
                cb.event_generate("<<ComboboxSelected>>")
        except Exception as _e:
            _logger.debug("ignored error at ui_theme.py:48: %s", _e)
        return "break"

    cb.bind("<MouseWheel>", _on_wheel)


def _bind_entry_context_menu(entry):
    """เพิ่มเมนูคลิกขวา ตัด/คัดลอก/วาง/เลือกทั้งหมด ให้ช่องกรอกข้อความ
    (ของเดิมคลิกขวาไม่มีเมนูอะไรเลย ผู้ใช้เลยก็อป/วางไม่ได้)"""
    menu = tk.Menu(
        entry,
        tearoff=0,
        bg=BG3,
        fg=FG,
        activebackground="#2A2B36",
        activeforeground="white",
        relief="flat",
        bd=0,
    )

    def _cut():
        try:
            entry.event_generate("<<Cut>>")
        except Exception as _e:
            _logger.debug("ignored error at ui_theme.py:72: %s", _e)

    def _copy():
        try:
            entry.event_generate("<<Copy>>")
        except Exception as _e:
            _logger.debug("ignored error at ui_theme.py:78: %s", _e)

    def _paste():
        try:
            entry.event_generate("<<Paste>>")
        except Exception as _e:
            _logger.debug("ignored error at ui_theme.py:84: %s", _e)

    def _select_all():
        try:
            entry.selection_range(0, "end")
            entry.icursor("end")
        except Exception as _e:
            _logger.debug("ignored error at ui_theme.py:91: %s", _e)

    menu.add_command(label="ตัด", command=_cut)
    menu.add_command(label="คัดลอก", command=_copy)
    menu.add_command(label="วาง", command=_paste)
    menu.add_separator()
    menu.add_command(label="เลือกทั้งหมด", command=_select_all)

    def _show_menu(event):
        try:
            entry.focus_set()
        except Exception as _e:
            _logger.debug("ignored error at ui_theme.py:103: %s", _e)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    entry.bind("<Button-3>", _show_menu)
    entry.bind("<Control-a>", lambda e: (_select_all(), "break"))
    entry.bind("<Control-A>", lambda e: (_select_all(), "break"))
    return menu


def _bind_button_hover(btn, base_bg, amount=0.15):
    try:
        parent_bg = btn.master.cget("bg")
    except Exception:
        parent_bg = base_bg
    try:
        # เดิม: ทุกปุ่มตอน disabled ใช้สีเทาแบนเดียวกันหมด (#55575E) ดูจืด/ไม่เข้า
        # กับธีมของแต่ละปุ่ม (ปุ่มแดง ปุ่มม่วง ปุ่มเหลือง กลายเป็นเทาเหมือนกันหมด)
        # ตอนนี้: ผสมสีตัวอักษรเดิมของปุ่มเข้ากับพื้นหลังของมันเอง ทำให้ตอน disabled
        # ยังเห็น "โทนสี" เดิมของปุ่มนั้นจาง ๆ อยู่ — ดูกลมกลืนกับธีมมากกว่าสีเทาเดียวทั้งแอป
        own_fg = str(btn.cget("fg")) or FG2
        dim_fg = _blend_hex(own_fg, str(parent_bg), 0.62)
    except Exception:
        dim_fg = "#55575E"
    try:
        btn.configure(
            highlightthickness=0,
            takefocus=0,
            bd=0,
            disabledforeground=dim_fg,
            highlightbackground=parent_bg,
            highlightcolor=parent_bg,
        )
    except Exception as _e:
        _logger.debug("ignored error at ui_theme.py:139: %s", _e)

    def _kill_focus(e=None, b=btn):
        try:
            b.winfo_toplevel().focus_set()
        except Exception as _e:
            _logger.debug("ignored error at ui_theme.py:145: %s", _e)

    btn.bind("<ButtonPress-1>", _kill_focus, add="+")
    btn.bind("<ButtonRelease-1>", _kill_focus, add="+")
    btn.bind("<FocusIn>", _kill_focus, add="+")

    hover_bg = _lighten_hex(base_bg, amount)

    def _on_enter(e, b=btn, hb=hover_bg):
        try:
            if str(b["state"]) != "disabled":
                b.configure(bg=hb)
        except tk.TclError:
            pass

    def _on_leave(e, b=btn, nb=base_bg):
        # เดิม: เช็ค state != 'disabled' ก่อนคืนสีพื้นหลัง — ถ้าปุ่มถูกสั่ง disabled
        # ระหว่างที่เมาส์ยังค้างอยู่บนปุ่ม (เช่นกด "ปิดเซสชันทั้งหมด"/"ล้าง Cookie"
        # แล้ว handler สั่ง disabled ทันที) เงื่อนไขนี้จะเป็นเท็จ ทำให้สีพื้นหลังค้าง
        # เป็นสี hover (สว่างกว่าปกติ) ไปตลอดจนกว่าจะ enable แล้ว hover ใหม่อีกรอบ
        # ตอนนี้: คืนสีพื้นหลังกลับเป็นค่าปกติเสมอตอนเมาส์ออกจากปุ่ม ไม่ว่าจะ
        # disabled อยู่หรือไม่ก็ตาม (โทน disabled คุมด้วย disabledforeground อยู่แล้ว)
        try:
            b.configure(bg=nb)
        except tk.TclError:
            pass

    btn.bind("<Enter>", _on_enter)
    btn.bind("<Leave>", _on_leave)


def _center_window_on_parent(win, parent):
    """จัดหน้าต่างลูก (Toplevel) ให้อยู่ตรงกลางของ parent หลัง layout เสร็จ
    (win.update_idletasks) — ดึงตำแหน่งจริงของทั้งคู่แล้ว set geometry ใหม่
    ใช้ร่วมกันทุกหน้าต่างลอย (coupon picker / manual key sender / webhook
    history) เพื่อให้การจัดวางตรงกลางเหมือนกันทั้งแอป"""
    win.update_idletasks()
    rx, ry = parent.winfo_x(), parent.winfo_y()
    rw, rh = parent.winfo_width(), parent.winfo_height()
    tw, th = win.winfo_width(), win.winfo_height()
    win.geometry(f"+{rx + max(0, (rw - tw) // 2)}+{ry + max(0, (rh - th) // 2)}")


def _round_window_corners(win, radius=10):
    """ทำมุมมนให้หน้าต่าง (Windows) — ใช้ DWM API ก่อน (Windows 11 รองรับ
    DWMWA_WINDOW_CORNER_PREFERENCE แบบระบบ) แล้ว fallback เป็นการตัด region
    มน (SetWindowRgn) สำหรับ Windows 10 ที่ DWM ไม่มี attribute นี้

    ทำงานเงียบๆ ถ้าทำไม่ได้ (ไม่ใช่ Windows / ไม่มีสิทธิ / window ยังไม่
    พร้อม) — แอปยังเปิดได้ปกติ แค่มุมเหลี่ยมเหมือนเดิม
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        try:
            hwnd = win.winfo_id()
            # DWM: มุมมนแบบระบบ (Windows 11) — radius ระบบจะเลือกเองให้เข้ากับธีม
            # ค่าคงที่: DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2
            pref = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref)
            )
        except Exception:
            # fallback: Windows 10 — สร้าง region มนด้วย GDI แล้วผูก window
            # (ต้อง update_idletasks ก่อนเพื่อให้ winfo_width/height มีค่าจริง)
            win.update_idletasks()
            w, h = win.winfo_width(), win.winfo_height()
            if w > 1 and h > 1:
                rgn = ctypes.windll.gdi32.CreateRoundRectRgn(
                    0, 0, w + 1, h + 1, radius * 2, radius * 2
                )
                if rgn:
                    ctypes.windll.user32.SetWindowRgn(win.winfo_id(), rgn, True)
    except Exception:
        pass


def _themed_popup(
    parent,
    title,
    message,
    kind="info",
    buttons="ok",
    confirm_text="ยืนยัน",
    cancel_text="ยกเลิก",
):
    """กล่องแจ้งเตือน/ยืนยันธีมเข้มแบบเดียวกันทั้งโปรแกรม (ใช้แทน tkinter.messagebox
    มาตรฐานทุกจุด ไม่ว่าจะเป็นแจ้งเตือนป้องกันเปิดโปรแกรมซ้ำ, แจ้งผลเมื่อเสร็จ,
    แจ้งเตือน/คำเตือน/ข้อผิดพลาดทั่วไป — หน้าตาเหมือนกันหมดทั้งแอป)

    kind: "info" | "success" | "warning" | "error"
    buttons: "ok" (ปุ่มเดียว คืนค่า True เสมอ) | "yesno" (คืนค่า True/False)
    คืนค่า: bool
    """
    STYLE = {
        "info": ("ℹ", "#5B8DEF"),
        "success": ("✅", STATUS_OK),
        "warning": ("⚠", STATUS_WARN),
        "error": ("❌", STATUS_ERR),
    }
    icon, color = STYLE.get(kind, STYLE["info"])

    result = {"ok": False}
    top = tk.Toplevel(parent)
    top.title(title)
    top.configure(bg=BG2)
    top.resizable(False, False)
    _set_toplevel_icon(top)
    try:
        if parent.winfo_viewable():
            top.transient(parent)
    except Exception as _e:
        _logger.debug("ignored error at ui_theme.py:284: %s", _e)

    pad = tk.Frame(top, bg=BG2)
    pad.pack(fill="both", expand=True, padx=24, pady=20)

    head = tk.Frame(pad, bg=BG2)
    head.pack(fill="x", pady=(0, 2))

    logo_photo = _get_logo_photo(30)
    if logo_photo is not None:
        logo_lbl = tk.Label(head, image=logo_photo, bg=BG2)
        logo_lbl.image = logo_photo  # กันโดน garbage collect
        logo_lbl.pack(side="left", padx=(0, 10))

    tk.Label(
        head,
        text=f"{icon}  {title}",
        font=("Leelawadee UI", 14, "bold"),
        bg=BG2,
        fg=color,
        anchor="w",
        justify="left",
    ).pack(side="left", fill="x")

    # เส้นคั่นใต้หัว — สไตล์เดียวกับ _page_header ของแท็บ เพื่อให้ทุก popup/
    # dialog ของแอปมีหัวเป็นชุดเดียวกันกับหัวแท็บ
    tk.Frame(head, bg=BORDER, height=1).pack(fill="x", pady=(10, 0))

    for line in str(message).split("\n"):
        tk.Label(
            pad,
            text=(line if line.strip() else " "),
            font=("Leelawadee UI", 11),
            bg=BG2,
            fg=FG,
            anchor="w",
            justify="left",
            wraplength=420,
        ).pack(fill="x", pady=(0, 4))

    btn_row = tk.Frame(pad, bg=BG2)
    btn_row.pack(fill="x", pady=(18, 0))

    def _close(val):
        result["ok"] = val
        top.destroy()

    def _copy_message():
        try:
            parent.clipboard_clear()
            parent.clipboard_append(f"{title}\n\n{message}")
            copy_btn.configure(text="คัดลอกแล้ว")
        except Exception as _e:
            _logger.debug("ignored error at ui_theme.py:324: %s", _e)

    if kind == "error":
        copy_btn = tk.Button(
            btn_row,
            text="คัดลอกข้อความ",
            font=("Leelawadee UI", 10, "bold"),
            bg=BG3,
            fg=FG,
            relief="flat",
            cursor="hand2",
            command=_copy_message,
        )
        copy_btn.pack(side="left", ipadx=10, ipady=6)
        _bind_button_hover(copy_btn, BG3)

    if buttons == "yesno":
        no_btn = tk.Button(
            btn_row,
            text=cancel_text,
            font=("Leelawadee UI", 11, "bold"),
            bg=BG3,
            fg=FG,
            relief="flat",
            cursor="hand2",
            command=lambda: _close(False),
        )
        no_btn.pack(side="right", ipadx=16, ipady=7)
        _bind_button_hover(no_btn, BG3)

        yes_bg = DANGER_STRONG if kind == "error" else GREEN
        yes_btn = tk.Button(
            btn_row,
            text=confirm_text,
            font=("Leelawadee UI", 11, "bold"),
            bg=yes_bg,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=lambda: _close(True),
        )
        yes_btn.pack(side="right", ipadx=16, ipady=7, padx=(0, 8))
        _bind_button_hover(yes_btn, yes_bg)
        top.protocol("WM_DELETE_WINDOW", lambda: _close(False))
    else:
        ok_btn = tk.Button(
            btn_row,
            text="ตกลง",
            font=("Leelawadee UI", 11, "bold"),
            bg=color,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=lambda: _close(True),
        )
        ok_btn.pack(side="right", ipadx=22, ipady=7)
        _bind_button_hover(ok_btn, color)
        top.protocol("WM_DELETE_WINDOW", lambda: _close(True))

    top.update_idletasks()
    try:
        if not parent.winfo_viewable():
            raise RuntimeError("parent not viewable")
        rx, ry = parent.winfo_x(), parent.winfo_y()
        rw, rh = parent.winfo_width(), parent.winfo_height()
    except Exception:
        rx, ry = 0, 0
        rw, rh = top.winfo_screenwidth(), top.winfo_screenheight()
    tw, th = top.winfo_width(), top.winfo_height()
    top.geometry(f"+{rx + max(0, (rw - tw) // 2)}+{ry + max(0, (rh - th) // 2)}")
    # กล่องแจ้งเตือนจากโปรเซสที่สองไม่มีหน้าต่างหลักให้ Windows อ้างอิง
    # จึงต้องยก Toplevel ขึ้นเอง มิฉะนั้นอาจถูกเปิดไว้ด้านหลังหน้าต่างเดิม
    try:
        top.deiconify()
        top.lift()
        top.attributes("-topmost", True)
        top.focus_force()
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.SetForegroundWindow(top.winfo_id())
    except Exception as _e:
        _logger.debug("ignored error at ui_theme.py:406: %s", _e)
    try:
        top.grab_set()
    except Exception as _e:
        _logger.debug("ignored error at ui_theme.py:410: %s", _e)
    top.wait_window()
    return result["ok"]


def _inline_toast(app, title, message, kind="info", duration=4200):
    """แจ้งเตือนแบบไม่บล็อกการใช้งาน ฝังอยู่ในหน้าต่างหลักเอง (ไม่สร้างหน้าต่าง
    แยกแบบ tk.Toplevel อีกต่อไป) ลอยอยู่มุมล่างขวาของโปรแกรม ซ้อนกันได้หลายอัน
    ถ้าเด้งถี่ ๆ แล้วหายไปเองเมื่อครบเวลา หรือคลิกเพื่อปิดก่อนได้"""
    host = getattr(app, "_root_pane", None) or getattr(app, "root", app)
    STYLE = {
        "info": ("ℹ", "#5B8DEF"),
        "success": ("✅", STATUS_OK),
    }
    icon, color = STYLE.get(kind, STYLE["info"])

    frame = tk.Frame(host, bg=color, bd=0)
    body = tk.Frame(frame, bg=BG2)
    body.pack(fill="both", expand=True, padx=2, pady=2)

    head = tk.Frame(body, bg=BG2)
    head.pack(fill="x", padx=14, pady=(11, 0))

    logo_photo = _get_logo_photo(20)
    if logo_photo is not None:
        logo_lbl = tk.Label(head, image=logo_photo, bg=BG2)
        logo_lbl.image = logo_photo  # กันโดน garbage collect
        logo_lbl.pack(side="left", padx=(0, 6))

    tk.Label(
        head,
        text=f"{icon}  {title}",
        font=("Leelawadee UI", 11, "bold"),
        bg=BG2,
        fg=color,
        anchor="w",
    ).pack(side="left", fill="x")
    # เส้นคั่นใต้หัว — สไตล์เดียวกับ popup/หัวแท็บ
    tk.Frame(head, bg=BORDER, height=1).pack(fill="x", pady=(8, 0))
    tk.Label(
        body,
        text=str(message),
        font=("Leelawadee UI", 10),
        bg=BG2,
        fg=FG,
        anchor="w",
        justify="left",
        wraplength=360,
    ).pack(fill="x", padx=14, pady=(0, 11))

    stack_index = getattr(app, "_sfkeyword_toast_count", 0)
    app._sfkeyword_toast_count = stack_index + 1
    frame.place(relx=1.0, rely=1.0, x=-16, y=-(16 + stack_index * 76), anchor="se")
    frame.lift()

    closed = {"value": False}

    def _close(event=None):
        if closed["value"]:
            return
        closed["value"] = True
        try:
            frame.destroy()
        except tk.TclError:
            pass
        try:
            app._sfkeyword_toast_count = max(0, app._sfkeyword_toast_count - 1)
        except Exception as _e:
            _logger.debug("ignored error at ui_theme.py:_inline_toast close: %s", _e)

    frame.bind("<Button-1>", _close)
    for child in body.winfo_children():
        child.bind("<Button-1>", _close)
    frame.after(duration, _close)
    return True


def _make_toggle(
    parent,
    var,
    text,
    command=None,
    bg=BG2,
    fg=FG,
    font=("Leelawadee UI", 10),
    eye_mode=False,
):
    """toggle widget — eye_mode=True ใช้ลูกตาเปิด/ปิดแทนติ๊กถูก/วงกลม
    (ใช้กับปุ่มแสดง/ซ่อนรหัสผ่านโดยเฉพาะ)
    """
    ON_BG = "#1E3A2F"
    ON_FG = STATUS_ACTIVE
    OFF_BG = "#2A2B36"
    OFF_FG = "#4B5563"
    frame = tk.Frame(parent, bg=bg, cursor="hand2")

    def _eye_text(on):
        return "👁" if on else "👁\u200d🗨"

    def _chk_text(on):
        return "\u2714" if on else "\u25cb"

    chk_lbl = tk.Label(
        frame,
        text=_eye_text(var.get()) if eye_mode else _chk_text(var.get()),
        font=("Leelawadee UI", 12) if eye_mode else ("Leelawadee UI", 13, "bold"),
        bg=ON_BG if var.get() else OFF_BG,
        fg=ON_FG if var.get() else OFF_FG,
        width=2,
        relief="flat",
        cursor="hand2",
    )
    chk_lbl.pack(side="left", padx=(0, 5), pady=1)
    txt_lbl = tk.Label(frame, text=text, font=font, bg=bg, fg=fg, cursor="hand2")
    txt_lbl.pack(side="left")

    def _update():
        on = var.get()
        chk_lbl.configure(
            text=_eye_text(on) if eye_mode else _chk_text(on),
            bg=ON_BG if on else OFF_BG,
            fg=ON_FG if on else OFF_FG,
        )

    _click_busy = {"v": False}

    def _click(e=None):
        if _click_busy["v"]:
            return
        _click_busy["v"] = True
        var.set(not var.get())
        _update()
        if command:
            command()
        frame.after(200, lambda: _click_busy.update(v=False))

    chk_lbl.bind("<Button-1>", _click)
    txt_lbl.bind("<Button-1>", _click)
    frame.bind("<Button-1>", _click)
    return frame, _update


# ── จานสีเลือกเอง (ธีมเข้ม ไร้เส้นกรอบ) — ใช้แทน colorchooser ของ Windows ──
# Windows colorchooser (tkinter) เป็น dialog ธีมสว่าง มีกรอบนูน/เส้นประที่โผล่
# มาขัดกับธีมเข้มของแอป — เลยเขียนจานสีเอง: พื้น BG3, สวอตช์ flat ไม่มีเส้น
# focus, ใช้แค่ hex + R/G/B slider ธรรมดา ไม่พึ่ง native dialog
# ── กลุ่มสีสำเร็จรูปแบ่งตามหมวด ──
# แต่ละ section = (หัวข้อ, [สี...]) — section แรกคือสีทั่วไป ส่วนที่เหลือจัดกลุ่ม
# ตามหมวด log (error/warn/success/login/cookie) โดยเอาสีค่าเริ่มต้นของแอปเป็นสีแรก
_ASK_COLOR_SECTIONS = [
    ("สีทั่วไป", [
        "#FF5C5C", STATUS_WARN, STATUS_OK, "#7DD3FC", "#C4B5FD", "#9CA3AF",
        "#E8455A", "#FFB74D", INFO_BLUE, "#059669", "#A78BFA", "#FFD700",
        STATUS_FAIL, "#FF8A65", "#4FC3F7", "#BA68C8", "#AED581", "#4DB6AC",
        "#F06292", "#7986CB", "#DCE775", "#90A4AE", "#E57373", "#81D4FA",
        "#FFFFFF", "#E5E7EB", "#D1D5DB", "#6B7280", "#374151", "#B0BEC5",
        "#FFAB91", "#CE93D8", "#80CBC4", "#FFF59D", "#BCAAA4",
    ]),
    ("Error ❌", [
        "#FF5C5C", STATUS_ERR, "#E8455A", DANGER_STRONG, "#F87171",
        "#EF4444", "#B91C1C", "#7F1D1D",
    ]),
    ("คำเตือน ⚠", [
        STATUS_WARN, "#FACC15", "#F59E0B", "#FFB74D", "#FFCA28",
        "#EAB308", "#D97706", "#92400E",
    ]),
    ("สำเร็จ ✅", [
        STATUS_OK, "#34D399", "#10B981", "#059669", "#4ADE80",
        "#22C55E", "#16A34A", "#14532D",
    ]),
    ("ล็อกอิน 🔁", [
        "#7DD3FC", "#38BDF8", "#0EA5E9", "#0284C7", "#60A5FA",
        "#3B82F6", "#2563EB", "#1E3A8A",
    ]),
    ("คุกกี้ 🍪", [
        "#C4B5FD", "#A78BFA", "#8B5CF6", "#7C3AED", "#B39DDB",
        "#9575CD", "#6D28D9", "#4C1D95",
    ]),
    ("คีย์เวิร์ด 🗝", [
        "#FFD700", STATUS_WARN, "#FFC107", "#FFB300", "#FFA000",
        "#FF8F00", "#E6A817", "#B8860B",
    ]),
]


def _hex_to_rgb(hex_color):
    """"#RRGGBB" → (r, g, b) ints; คืน (160,160,160) ถ้าค่าเสีย"""
    try:
        h = str(hex_color or "").strip().lstrip("#")
        if len(h) == 6:
            return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
    except Exception:
        pass
    return (160, 160, 160)


def _rgb_to_hex(rgb):
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(x))) for x in rgb)


def _rgb_to_hsl(rgb):
    """(r,g,b) 0-255 → (h 0-360, s 0-100, l 0-100)"""
    try:
        r, g, b = (max(0, min(255, int(x))) / 255.0 for x in rgb)
        mx, mn = max(r, g, b), min(r, g, b)
        lgt = (mx + mn) / 2.0
        if mx == mn:
            return 0, 0, round(lgt * 100)
        d = mx - mn
        s = d / (2.0 - mx - mn) if lgt > 0.5 else d / (mx + mn)
        if mx == r:
            h = (g - b) / d + (6 if g < b else 0)
        elif mx == g:
            h = (b - r) / d + 2
        else:
            h = (r - g) / d + 4
        return round(h * 60), round(s * 100), round(lgt * 100)
    except Exception:
        return 0, 0, 50


def _hsl_to_rgb(hsl):
    """(h 0-360, s 0-100, l 0-100) → (r,g,b) 0-255"""
    try:
        h, s, lgt = float(hsl[0]), max(0.0, min(100.0, float(hsl[1]))) / 100.0, \
            max(0.0, min(100.0, float(hsl[2]))) / 100.0
        h = (h % 360) / 360.0
        if s == 0:
            v = round(lgt * 255)
            return v, v, v

        def _hue2rgb(p, q, t):
            t = t % 1.0
            if t < 1 / 6:
                return p + (q - p) * 6 * t
            if t < 1 / 2:
                return q
            if t < 2 / 3:
                return p + (q - p) * (2 / 3 - t) * 6
            return p

        q = lgt * (1 + s) if lgt < 0.5 else lgt + s - lgt * s
        p = 2 * lgt - q
        return (
            round(_hue2rgb(p, q, h + 1 / 3) * 255),
            round(_hue2rgb(p, q, h) * 255),
            round(_hue2rgb(p, q, h - 1 / 3) * 255),
        )
    except Exception:
        return 160, 160, 160


# ชื่อหมวด log → ชื่อ section ใน _ASK_COLOR_SECTIONS (สำหรับแสดงเฉพาะหมวดที่เลือก)
_CATEGORY_SECTION_TITLE = {
    "error": "Error ❌",
    "warn": "คำเตือน ⚠",
    "success": "สำเร็จ ✅",
    "login": "ล็อกอิน 🔁",
    "cookie": "คุกกี้ 🍪",
    "keyword": "คีย์เวิร์ด 🗝",
}


def _ask_color(parent, title="เลือกสี", initial=FG2, preset_cat=None):
    """จานสีธีมเข้มแบบ modal (ใช้แทน tkinter.colorchooser ที่เป็นธีม Windows
    สว่าง/มีเส้นกรอบ) — คืน hex string หรือ None ถ้ากดยกเลิก/ปิด

    หน้าตา: พื้น BG3 ทั้งหมด ปุ่ม/สวอตช์ flat ไม่มี border ไม่มีเส้น focus,
    มีสวอตช์สำเร็จรูปให้คลิก + slider R/G/B + ช่อง hex (เลือกได้ทั้ง 3 ทาง
    ซิงก์กันทันที)"""
    top = tk.Toplevel(parent)
    top.title(title)
    top.configure(bg=BG3)
    top.resizable(False, False)
    try:
        _set_toplevel_icon(top)
    except Exception:
        pass
    try:
        if parent is not None and parent.winfo_viewable():
            top.transient(parent)
    except Exception:
        pass

    result = {"hex": None}

    # ── หัวข้อ + เส้นคั่น (สไตล์เดียวกับหัวแท็บ) ──
    _page_header(top, title, "🎨", padx=24, bg=BG3)

    preview = tk.Label(
        top, text="", width=16, height=3,
        bg=initial, relief="flat", highlightthickness=0,
        font=("Leelawadee UI", 12),
    )
    preview.pack(fill="x", padx=24, pady=(0, 8))

    hex_var = tk.StringVar(value=str(initial or "").upper())
    hex_entry = tk.Entry(
        top, textvariable=hex_var, font=("Consolas", 13),
        bg=BG2, fg=FG, insertbackground=FG,
        relief="flat", highlightthickness=1,
        highlightbackground=ACC2, highlightcolor=ACC2,
        justify="center",
    )
    hex_entry.pack(fill="x", padx=24, pady=(0, 8))

    # ── จานสีไล่ระดับ: กล่องความเข้ม (S/L) + แถบสี (H) — คลิกเลือกสีได้อิสระ ──
    hue_var = tk.IntVar(value=0)
    sat_var = tk.IntVar(value=100)
    lig_var = tk.IntVar(value=50)
    grad_size = {"w": 452, "h": 108}
    grad_photo = {"img": None}

    grad_frame = tk.Frame(top, bg=BG3)
    grad_frame.pack(fill="x", padx=24, pady=(0, 4))
    grad_cv = tk.Canvas(
        grad_frame,
        width=grad_size["w"],
        height=grad_size["h"],
        bg=BG3,
        highlightthickness=0,
        cursor="crosshair",
        takefocus=0,
    )
    grad_cv.pack(side="left")
    hue_cv = tk.Canvas(
        grad_frame,
        width=26,
        height=grad_size["h"],
        bg=BG3,
        highlightthickness=0,
        cursor="hand2",
        takefocus=0,
    )
    hue_cv.pack(side="left", padx=(6, 0))

    def _gradient_image(hue):
        """สร้างรูปไล่ระดับ S (แกน x) × L (แกน y) ของ hue ที่กำหนด — คืน
        PhotoImage พร้อมสีจุดที่ (sat, lig) ต่างกันตรงจุดกากบาท"""
        w, h = grad_size["w"], grad_size["h"]
        img = Image.new("RGB", (w, h))
        px = img.load()
        for y in range(h):
            lig = round(100 - (y / (h - 1)) * 100)
            for x in range(w):
                sat = round((x / (w - 1)) * 100)
                px[x, y] = _hsl_to_rgb((hue, sat, lig))
        return ImageTk.PhotoImage(img)

    def _draw_gradient():
        img = _gradient_image(hue_var.get())
        grad_photo["img"] = img
        grad_cv.delete("all")
        grad_cv.create_image(0, 0, anchor="nw", image=img)
        _draw_grad_marker()

    def _draw_grad_marker():
        w, h = grad_size["w"], grad_size["h"]
        x = round((sat_var.get() / 100.0) * (w - 1))
        y = round((100 - lig_var.get()) / 100.0 * (h - 1))
        grad_cv.delete("marker")
        grad_cv.create_oval(
            max(0, x - 6), max(0, y - 6), x + 6, y + 6,
            outline="#FFFFFF", width=2, tags="marker",
        )
        grad_cv.create_oval(
            max(0, x - 6), max(0, y - 6), x + 6, y + 6,
            outline=BG, width=1, tags="marker",
        )

    def _draw_hue_strip():
        """แถบสี H ไล่ 360 องศา — กดที่แถบเพื่อเปลี่ยน hue"""
        w, hgt = 26, grad_size["h"]
        img = Image.new("RGB", (w, hgt))
        px = img.load()
        for y in range(hgt):
            hue = round((y / (hgt - 1)) * 360)
            color = _hsl_to_rgb((hue, 100, 50))
            for x in range(w):
                px[x, y] = color
        photo = ImageTk.PhotoImage(img)
        hue_photo["img"] = photo
        hue_cv.delete("all")
        hue_cv.create_image(0, 0, anchor="nw", image=photo)
        yy = round((hue_var.get() / 360.0) * (hgt - 1))
        hue_cv.create_rectangle(0, max(0, yy - 2), w, yy + 3,
                                outline="#FFFFFF", width=2)

    hue_photo = {"img": None}

    def _grad_click(_evt=None):
        w, h = grad_size["w"], grad_size["h"]
        x = max(0, min(w - 1, _evt.x))
        y = max(0, min(h - 1, _evt.y))
        sat_var.set(round((x / (w - 1)) * 100))
        lig_var.set(round(100 - (y / (h - 1)) * 100))
        _draw_grad_marker()
        _sync_rgb_from_hsl()

    def _hue_click(_evt=None):
        hgt = grad_size["h"]
        y = max(0, min(hgt - 1, _evt.y))
        hue_var.set(round((y / (hgt - 1)) * 360))
        _draw_hue_strip()
        _draw_gradient()
        _sync_rgb_from_hsl()

    def _sync_rgb_from_hsl():
        """HSL vars → RGB vars/hex/preview (ใช้เมื่อคลิกจานสี/แถบ hue)"""
        rgb = _hsl_to_rgb((hue_var.get(), sat_var.get(), lig_var.get()))
        r_var.set(rgb[0])
        g_var.set(rgb[1])
        b_var.set(rgb[2])
        _refresh_labels()
        hx = _rgb_to_hex(rgb)
        hex_var.set(hx)
        preview.configure(bg=hx)
        _update_hsl_readout()

    def _sync_hsl_from_rgb():
        """RGB vars → HSL vars + วาดจานสีใหม่ (ใช้เมื่อเลื่อน R/G/B / พิมพ์ hex)"""
        hh, ss, ll = _rgb_to_hsl((r_var.get(), g_var.get(), b_var.get()))
        hue_var.set(hh)
        sat_var.set(ss)
        lig_var.set(ll)
        _draw_hue_strip()
        _draw_gradient()
        _update_hsl_readout()

    def _update_hsl_readout():
        h_lbl.configure(
            text=f"H {hue_var.get():>3}°"
        )
        s_lbl.configure(text=f"S {sat_var.get():>3}%")
        l_lbl.configure(text=f"L {lig_var.get():>3}%")

    grad_cv.bind("<Button-1>", _grad_click)
    grad_cv.bind("<B1-Motion>", _grad_click)
    hue_cv.bind("<Button-1>", _hue_click)
    hue_cv.bind("<B1-Motion>", _hue_click)

    # แถว HSL readout
    hsl_row = tk.Frame(top, bg=BG3)
    hsl_row.pack(fill="x", padx=26, pady=(0, 2))
    h_lbl = tk.Label(hsl_row, text="H 0°", font=("Consolas", 10, "bold"),
                     bg=BG3, fg=DANGER)
    h_lbl.pack(side="left")
    s_lbl = tk.Label(hsl_row, text="S 100%", font=("Consolas", 10, "bold"),
                     bg=BG3, fg="#6BCB77")
    s_lbl.pack(side="left", padx=(12, 0))
    l_lbl = tk.Label(hsl_row, text="L 50%", font=("Consolas", 10, "bold"),
                     bg=BG3, fg="#6BA3FF")
    l_lbl.pack(side="left", padx=(12, 0))

    # ── ปรับสีอิสระ: slider R/G/B (วางก่อน presets ให้เห็น/ใช้ได้ชัดเจน) ──
    bar = tk.Frame(top, bg=BG3)
    bar.pack(fill="x", padx=26, pady=(6, 4))

    def _make_slider(name, color, var):
        row = tk.Frame(bar, bg=BG3)
        row.pack(fill="x", pady=3)
        tk.Label(
            row, text=name, width=2, font=("Consolas", 12, "bold"),
            bg=BG3, fg=color,
        ).pack(side="left")
        sc = tk.Scale(
            row, from_=0, to=255, orient="horizontal",
            variable=var, showvalue=False,
            bg=BG3, fg=FG, troughcolor=BG2,
            activebackground=ACC2, highlightthickness=0,
            relief="flat", bd=0, sliderrelief="flat",
            sliderlength=26, length=260,
            takefocus=0, command=lambda _v: _on_slider(),
        )
        sc.pack(side="left", fill="x", expand=True, padx=(8, 6))
        val = tk.Label(row, text="0", width=4, font=("Consolas", 11),
                       bg=BG3, fg=FG)
        val.pack(side="left")
        return sc, val

    r_var, g_var, b_var = tk.IntVar(value=160), tk.IntVar(value=160), tk.IntVar(value=160)
    _, r_v = _make_slider("R", DANGER, r_var)
    _, g_v = _make_slider("G", "#6BCB77", g_var)
    _, b_v = _make_slider("B", "#6BA3FF", b_var)

    def _refresh_labels():
        r_v.configure(text=str(r_var.get()))
        g_v.configure(text=str(g_var.get()))
        b_v.configure(text=str(b_var.get()))

    def _on_slider():
        _refresh_labels()
        hx = _rgb_to_hex((r_var.get(), g_var.get(), b_var.get()))
        hex_var.set(hx)
        preview.configure(bg=hx)
        _sync_hsl_from_rgb()

    def _apply_hex(hex_color):
        try:
            h = str(hex_color or "").strip().lstrip("#")
            if len(h) != 6:
                return
            int(h, 16)
        except Exception:
            return
        hx = "#" + h.upper()
        hex_var.set(hx)
        preview.configure(bg=hx)
        r, g, b = _hex_to_rgb(hx)
        r_var.set(r)
        g_var.set(g)
        b_var.set(b)
        _refresh_labels()
        _sync_hsl_from_rgb()

    # ── สีสำเร็จรูป: โชว์เฉพาะหมวดที่กำลังแก้ + สีทั่วไป เปิดมาเห็นเลย (ไม่พับ กันล้น) ──
    # แสดงเฉพาะหมวดที่กำลังแก้ (preset_cat) + สีทั่วไป — ไม่เอา 7 หมวดมารวม
    # กันหน้าต่างล้นจอ ("ของใครของมัน") ถ้าไม่ได้ระบุให้โชว์แค่สีทั่วไป
    shown_sections = [s for s in _ASK_COLOR_SECTIONS if s[0] == "สีทั่วไป"]
    if preset_cat:
        target_title = _CATEGORY_SECTION_TITLE.get(preset_cat)
        if target_title:
            shown_sections += [s for s in _ASK_COLOR_SECTIONS if s[0] == target_title]

    secs = tk.Frame(top, bg=BG3)
    _cols = 8
    _row = 0
    for sec_title, colors in shown_sections:
        tk.Label(
            secs, text=sec_title, font=("Leelawadee UI", 9, "bold"),
            bg=BG3, fg=FG3, anchor="w",
        ).grid(row=_row, column=0, columnspan=_cols, sticky="ew", pady=(5, 0))
        _row += 1
        for i, color in enumerate(colors):
            sw = tk.Button(
                secs,
                text="",
                width=4,
                height=1,
                bg=color,
                activebackground=color,
                relief="flat",
                borderwidth=0,
                highlightthickness=0,
                takefocus=0,
                cursor="hand2",
                command=lambda c=color: _apply_hex(c),
            )
            sw.grid(row=_row, column=i % _cols, padx=2, pady=1, sticky="nsew")
            if i % _cols == _cols - 1:
                _row += 1
        if len(colors) % _cols:
            _row += 1

    secs.pack(fill="x", padx=24, pady=(4, 6))

    # ── ปุ่มล่าง ──
    btns = tk.Frame(top, bg=BG3)
    btns.pack(fill="x", padx=24, pady=(10, 18))

    def _ok():
        result["hex"] = hex_var.get()
        top.destroy()

    ok_btn = tk.Button(
        btns, text="ตกลง", font=("Leelawadee UI", 12, "bold"),
        bg=ACC2, fg=BG, activebackground=ACC2, activeforeground=BG,
        relief="flat", borderwidth=0, highlightthickness=0, takefocus=0,
        cursor="hand2", command=_ok,
    )
    ok_btn.pack(side="right", ipadx=22, ipady=7)
    cancel_btn = tk.Button(
        btns, text="ยกเลิก", font=("Leelawadee UI", 12),
        bg=BG2, fg=FG2, activebackground=BG2, activeforeground=FG2,
        relief="flat", borderwidth=0, highlightthickness=0, takefocus=0,
        cursor="hand2", command=top.destroy,
    )
    cancel_btn.pack(side="right", ipadx=18, ipady=7, padx=(0, 12))
    _bind_button_hover(ok_btn, ACC2)
    _bind_button_hover(cancel_btn, BG2)

    # init ค่าตามสีเริ่มต้น
    _apply_hex(initial)

    # ── จัดวางตรงกลาง parent / กึ่งกลางจอ ──
    def _center_picker_window():
        top.update_idletasks()
        # กันหน้าต่างเล็กเกินไป: บังคับความกว้าง/สูงขั้นต่ำให้พอดีอ่านง่าย
        # และกันล้นจอ: สูงต้องไม่เกินความสูงจอ (เผื่อ taskbar ~40px)
        w = max(top.winfo_reqwidth() + 24, 500)
        h = max(top.winfo_reqheight() + 20, 560)
        try:
            sh = top.winfo_screenheight()
            h = min(h, max(400, sh - 60))
        except Exception:
            pass
        try:
            if parent is not None and parent.winfo_viewable():
                x = parent.winfo_rootx() + max(0, (parent.winfo_width() - w) // 2)
                y = parent.winfo_rooty() + max(0, (parent.winfo_height() - h) // 2)
            else:
                x = (top.winfo_screenwidth() - w) // 2
                y = (top.winfo_screenheight() - h) // 2
        except Exception:
            x = (top.winfo_screenwidth() - w) // 2
            y = (top.winfo_screenheight() - h) // 2
        top.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")

    _center_picker_window()

    hex_entry.bind("<Return>", lambda e: _ok())
    top.bind("<Escape>", lambda e: top.destroy())
    try:
        top.grab_set()
    except Exception:
        pass
    try:
        top.focus_force()
    except Exception:
        pass
    top.wait_window()
    return result["hex"]


__all__ = [
    "_bind_button_hover",
    "_bind_combobox_wheel_local",
    "_bind_entry_context_menu",
    "_blend_hex",
    "_center_window_on_parent",
    "_get_logo_photo",
    "_get_window_icon_photo",
    "_round_logo_photo",
    "_inline_toast",
    "_lighten_hex",
    "_ask_color",
    "_hex_to_rgb",
    "_hsl_to_rgb",
    "_make_toggle",
    "_rgb_to_hex",
    "_rgb_to_hsl",
    "_set_toplevel_icon",
    "_themed_popup",
]
