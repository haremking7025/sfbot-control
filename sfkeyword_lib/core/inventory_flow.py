"""Pure-HTTP engine สำหรับหน้า "TDP Inventory" (ฝาก/เบิกไอเทม) บน member.sf.in.th

หน้าอยู่ที่ http://member.sf.in.th/Inventory/ — เป็น ASP.NET Web Forms หน้าเดียวกับ
ระบบคีย์เวิร์ด (master page SF Event Center + session "Members" เดียวกัน) เลยใช้
session ที่ do_login สร้างไว้ได้ตรงๆ โดยไม่ต้องล็อกอินใหม่

การทำงานของหน้าเว็บ (จาก JS ของหน้า Default.aspx):
- โหลดหมวดหมู่:   POST  Default.aspx/GetCategoriesTree   -> {d:{success,data}}
- ค้นหาไอเทม:     POST  Default.aspx/GetPlayerItems     -> {d:{success,data,totalPages,totalItems}}
- ฝาก/เบิก/ลบ:    POST  Default.aspx/PerformItemOperation -> {d:{success,message}}

เงื่อนไขปุ่มบนหน้าเว็บ (ลอกจาก createItemRowHtml/updateBulkActionsDisplay ใน JS):
- ฝากได้ (DEPOSIT): ItemStatus == 'PERMANENT' และยังไม่หมดอายุ และ IsDeposited == 'N'
- เบิกได้ (WITHDRAW): IsDeposited == 'Y' และยังไม่หมดอายุ

⚠ POST ฝาก/เบิกเป็น operation ที่ไม่ idempotent — ห้าม retry อัตโนมัติ
"""

import logging
import re

import requests

from .exceptions import SessionExpiredError

_logger = logging.getLogger(__name__)

INVENTORY_URL = "http://member.sf.in.th/Inventory/"

# หมวดหลักของไอเทม (ParentCategoryName จากเว็บ) — ใช้กรองฝาก/เบิกทั้งหมด
INV_CATEGORIES = ["ทั้งหมด", "อาวุธ", "เครื่องแต่งกาย", "ของใช้งาน"]


def inv_category_label(item):
    """ป้ายหมวดของไอเทม 1 ชิ้น — 'พ่อ › ลูก' ถ้ามีหมวดย่อย, 'ลูก' ถ้าไม่มีพ่อ
    (ตรงกับที่เว็บส่ง ParentCategoryName/CategoryName มาใน item)
    ถ้ามีพ่อแต่ลูกว่าง → คืนแค่พ่อ (กันป้าย 'อาวุธ › ' งี่เง่า)"""
    p = str(item.get("ParentCategoryName") or "").strip()
    c = str(item.get("CategoryName") or "").strip()
    if p and c:
        return f"{p} › {c}"
    return p or c


def inv_category_options(items=None):
    """รายการหมวดให้เลือกในปุ่มหลัก — หมวดหลักคงที่ + หมวดย่อยจริงที่เจอจาก items
    (เช่น 'อาวุธ › ปืนไรเฟิลจู่โจม') — กันซ้ำ (รวมชนกับหมวดหลักคงที่ด้วย)
    และ 'ทั้งหมด' อยู่แรกเสมอ"""
    opts = list(INV_CATEGORIES)
    if items:
        for it in items:
            label = inv_category_label(it)
            if label and label not in opts:
                opts.append(label)
    return opts

_WM_TIMEOUT = (5, 20)

# สัญญาณของ "ยังไม่ล็อกอิน/โดนเด้งกลับหน้าแรก" ของ master page SF Event Center
# (ฟอร์มล็อกอินของ master ใช้ชื่อ ctl00$txtUsername / ปุ่ม btnSignin)
_LOGIN_FORM_MARKERS = (
    "ctl00$txtUsername",
    "id=\"txtUsername\"",
    "btnSignin",
    "WebForm_FireDefaultButton",
)

_PERMANENT_END = "30001231000000"


def _log(log_fn, msg):
    if log_fn is not None:
        try:
            log_fn(msg)
        except Exception:
            pass


def _looks_like_login_page(text):
    """ตรวจว่าหน้าที่ตอบกลับมาเป็นหน้า Login ของ master page (session หลุด) หรือไม่"""
    if not text or "btnLogout" in text:
        return False
    low = text
    return any(m in low for m in _LOGIN_FORM_MARKERS)


def _webmethod_base(page_url):
    """คืน URL ของหน้า Default.aspx (ใช้ต่อท้าย /MethodName สำหรับ WebMethod)

    page_url อาจเป็น http://member.sf.in.th/Inventory/ (folder → เสิร์ฟ Default.aspx)
    หรือ http://member.sf.in.th/Inventory/Default.aspx ก็ได้
    """
    base = (page_url or INVENTORY_URL).split("#")[0].split("?")[0].rstrip("/")
    if not base.endswith("/Default.aspx"):
        base += "/Default.aspx"
    return base


def _http_get(session, url, retries=2, timeout=(5, 15)):
    last = None
    for i in range(retries):
        try:
            return session.get(url, timeout=timeout, allow_redirects=True)
        except requests.RequestException as e:
            last = e
            if i < retries - 1:
                import time

                time.sleep(0.2 * (2 ** i))
    raise last


def open_inventory(session, log_fn=None, username=""):
    """GET หน้า Inventory เพื่อ (1) ยืนยัน session ยังล็อกอินอยู่ (2) หา URL
    จริงของหน้า Default.aspx ไว้เรียก WebMethod

    คืน: page_url (เช่น .../Inventory/Default.aspx)
    raises SessionExpiredError ถ้า session หลุด
    """
    r = _http_get(session, INVENTORY_URL)
    page_url = r.url
    body = r.text
    if "btnLogout" not in body and _looks_like_login_page(body):
        raise SessionExpiredError(
            f"[{username}] session หมดอายุ — หน้า Inventory เด้งกลับหน้า Login "
            "(ล็อกอินใหม่ให้อัตโนมัติ)"
        )
    if "inventory-wrapper" not in body and "GetPlayerItems" not in body:
        # ไม่ใช่หน้า inventory จริง (ผิดพลาดฝั่งเว็บ/หน้าเปลี่ยน) — พยายามไปต่อ
        # ไม่ได้เพราะจะไม่มี WebMethod ให้เรียก
        snippet = re.sub(r"\s+", " ", body)[:120]
        raise Exception(f"[{username}] หน้า Inventory ผิดปกติ — {snippet}")
    return _webmethod_base(page_url)


def _wm_call(session, page_url, method, payload, username=""):
    """เรียก ASP.NET PageMethod (WebMethod) ตัวเดียว — คืน dict 'd'

    raises SessionExpiredError / Exception(ข้อความ error จากเว็บ)
    """
    url = page_url + "/" + method
    r = session.post(
        url,
        json=payload,
        headers={
            "Referer": page_url,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        },
        timeout=_WM_TIMEOUT,
    )
    try:
        data = r.json()
    except Exception:
        body = r.text
        if _looks_like_login_page(body):
            raise SessionExpiredError(
                f"[{username}] session หมดอายุระหว่างเรียก {method} — "
                "เว็บเด้งกลับหน้า Login (ล็อกอินใหม่ให้อัตโนมัติ)"
            )
        snippet = re.sub(r"\s+", " ", body)[:160]
        raise Exception(f"[{username}] {method} ตอบกลับไม่ใช่ JSON — {snippet}")
    d = data.get("d") if isinstance(data, dict) else None
    if d is None:
        raise Exception(f"[{username}] {method} ตอบกลับว่างเปล่า")
    return d


def fetch_items_page(
    session,
    page_url,
    page_number=1,
    page_size=100,
    username="",
    status_filter="A",
):
    """เรียก GetPlayerItems หนึ่งหน้า — คืน dict d (data/totalPages/totalItems)"""
    payload = {
        "categoryCode": None,
        "itemName": None,
        "showDeposited": status_filter,
        "enhancementLevel": -99,
        "elementGrade": -99,
        "enchantmentType": -99,
        "pageSize": page_size,
        "pageNumber": page_number,
    }
    d = _wm_call(session, page_url, "GetPlayerItems", payload, username)
    if not isinstance(d, dict):
        raise Exception(f"[{username}] GetPlayerItems ตอบกลับผิดรูปแบบ")
    if not d.get("success"):
        raise Exception(
            f"[{username}] GetPlayerItems ล้มเหลว: {d.get('message') or 'ไม่ทราบสาเหตุ'}"
        )
    return d


def fetch_all_items(session, page_url, username="", stop_check=None, log_fn=None):
    """ดึงไอเทมทั้งหมด — หน้าแรก sequential (รู้ totalPages) แล้วเรียกหน้าที่เหลือ
    แบบ parallel (สูงสุด 5 หน้า/รอบ)

    หมายเหตุ: เทสจริงแล้วเว็บเป็นคอขวด (~1.6 วิ/หน้า คงที่ไม่ว่า parallel กี่หน้า)
    และห้ามล็อกอิน session ซ้ำบัญชีเดียวกัน (เคยลอง dual-session ได้ 25 วิ แทน 33
    แต่บัญชีโดนล็อก 15 นาที — เว็บนับล็อกอินซ้ำเร็วเป็นผิด → ใช้ session เดียวเสมอ)

    stop_check: callable คืน True เมื่อผู้ใช้กดหยุด (เช็คระหว่างรอบหน้า)
    """
    items = []
    page_size = 100

    def _stop():
        return stop_check is not None and stop_check()

    d1 = fetch_items_page(
        session, page_url, page_number=1, page_size=page_size, username=username
    )
    data1 = d1.get("data") or []
    items.extend(data1)
    try:
        total_pages = int(d1.get("totalPages") or 1)
    except (TypeError, ValueError):
        total_pages = 1
    if not data1:
        _log(log_fn, f" [{username}] ดึงรายการไอเทม: พบ {len(items)} รายการ")
        return items

    from concurrent.futures import ThreadPoolExecutor

    def _fetch(pg):
        if _stop():
            return []
        try:
            d = fetch_items_page(
                session, page_url, page_number=pg, page_size=page_size, username=username
            )
            return d.get("data") or []
        except Exception:
            return None  # หน้าพัง — ถอยไปดึงแบบ sequential เก็บเฉพาะหน้าที่เหลือ

    pending = list(range(2, total_pages + 1))
    with ThreadPoolExecutor(max_workers=5) as ex:
        while pending:
            if _stop():
                break
            batch = pending[:5]
            pending = pending[5:]
            for pg, chunk in zip(batch, ex.map(_fetch, batch), strict=False):
                if chunk is None:
                    # หน้าพลาด (network/เว็บ) — ดึงหน้าคืนแบบเดี่ยว ๆ กันยิงซ้ำ
                    if _stop():
                        break
                    try:
                        d = fetch_items_page(
                            session, page_url, page_number=pg, page_size=page_size,
                            username=username,
                        )
                        items.extend(d.get("data") or [])
                    except Exception:
                        pass
                else:
                    items.extend(chunk)
    _log(log_fn, f" [{username}] ดึงรายการไอเทม: พบ {len(items)} รายการ")
    return items


# จำนวนวันก่อนหมดอายุที่ถือว่า 'ใกล้หมดอายุ' (กรองดูของที่จะหายเร็ว)
INV_NEAR_EXPIRE_DAYS = 3


def item_is_expired(item, now=None):
    end = str(item.get("EndDate") or "")
    if end == _PERMANENT_END or not end:
        return False
    if now is None:
        from datetime import datetime

        now = datetime.now().strftime("%Y%m%d%H%M%S")
    return end <= now


def item_expires_within_days(item, days=INV_NEAR_EXPIRE_DAYS, now=None):
    """ไอเทมยังใช้ได้ (ยังไม่หมดอายุ) แต่เหลือไม่ถึง days วัน — ใช้กรอง
    'ใกล้หมดอายุ' เพื่อดูของที่จะหายเร็ว"""
    end = str(item.get("EndDate") or "")
    if not end or end == _PERMANENT_END:
        return False
    if item_is_expired(item, now):
        return False
    try:
        from datetime import datetime

        dt = datetime.strptime(end, "%Y%m%d%H%M%S")
        base = datetime.now() if now is None else datetime.strptime(now, "%Y%m%d%H%M%S")
        return 0 <= (dt - base).total_seconds() <= days * 86400
    except Exception:
        return False


def item_can_deposit(item):
    return (
        item.get("ItemStatus") == "PERMANENT"
        and not item_is_expired(item)
        and item.get("IsDeposited") == "N"
    )


def item_can_withdraw(item):
    return item.get("IsDeposited") == "Y" and not item_is_expired(item)


def item_can_delete(item):
    """ลบได้ = ของไม่ถาวร (ItemStatus ≠ PERMANENT เช่น ของชั่วคราว/หมดอายุ) —
    ของถาวรห้ามลบเด็ดขาด (ลบแล้วหายถาวร) — ไม่รู้สถานะ = ไม่ให้ลบ (กันพลาด)"""
    status = str(item.get("ItemStatus") or "").strip()
    return bool(status) and status != "PERMANENT"


def item_in_category(item, category):
    """ไอเทมอยู่ในหมวดที่เลือกไหม — รองรับทั้งหมวดหลัก ('อาวุธ') และหมวดย่อย
    ('อาวุธ › ปืนไรเฟิลจู่โจม')

    - 'ทั้งหมด' = ไม่กรอง
    - 'พ่อ › ลูก' = ตรง ParentCategoryName และ CategoryName พร้อมกัน
    - 'ของใช้งาน' = CategoryName เป็น 'ของใช้งาน' หรือไอเทมไม่มีหมวดพ่อ (กันหลุด
      จาก 'ทั้งหมด' เท่านั้น ให้อยู่ใน 'ของใช้งาน' ด้วย)
    - หมวดอื่น = ตรง ParentCategoryName หรือ CategoryName (รองรับหมวดไม่มีพ่อ
      เช่น 'EXP X5' ที่ label เป็นชื่อหมวดลูกตรงๆ)
    """
    if not category or category == "ทั้งหมด":
        return True
    p = str(item.get("ParentCategoryName") or "").strip()
    c = str(item.get("CategoryName") or "").strip()
    if "›" in category:
        parent, _, child = category.partition("›")
        return p == parent.strip() and c == child.strip()
    if p == category or c == category:
        return True
    if category == "ของใช้งาน":
        return c == "ของใช้งาน" or not p
    return False


def item_display_name(item):
    return (
        str(item.get("CleanItemName") or item.get("ItemName") or item.get("ItemCode") or "?")
    ).strip()


_STATUS_TH = {"PERMANENT": "ถาวร", "TEMPORARY": "ชั่วคราว"}


def _status_th(status):
    """แปลง ItemStatus เป็นไทยอ่านง่าย — PERMANENT→ถาวร, TEMPORARY→ชั่วคราว
    (เก็บรหัสเดิมต่อท้ายด้วย กันข้อมูลหาย) สถานะอื่นคืนแบบดิบ"""
    status = str(status or "").strip()
    if status in _STATUS_TH:
        return f"{_STATUS_TH[status]} ({status})"
    return status or "-"


def _fmt_end(end):
    """แปลง EndDate (yyyyMMddHHmmss) เป็นข้อความที่อ่านง่าย — ถาวร/ว่างเปล่า → 'ถาวร'"""
    end = str(end or "").strip()
    if not end or end == _PERMANENT_END:
        return "ถาวร"
    if len(end) == 14 and end.isdigit():
        try:
            return f"{end[6:8]}/{end[4:6]}/{end[:4]} {end[8:10]}:{end[10:12]}"
        except Exception:
            return end
    return end


def _fmt_remaining(item, now=None):
    """เวลาที่เหลือก่อนหมดอายุของไอเทม — ถาวร / หมดอายุแล้ว / เหลืออีก X วัน (หรือ ชม.)"""
    end = str(item.get("EndDate") or "")
    if not end or end == _PERMANENT_END:
        return "ถาวร"
    if item_is_expired(item, now):
        return "หมดอายุแล้ว"
    try:
        from datetime import datetime

        dt = datetime.strptime(end, "%Y%m%d%H%M%S")
        base = datetime.now() if now is None else datetime.strptime(now, "%Y%m%d%H%M%S")
        secs = (dt - base).total_seconds()
        # ceil (กัน drift ไมโครวินาที) + int (กัน '5.0') — กัน 1 วันพอดี (86399.99 วิ)
        # ตกไปฝั่งชั่วโมงด้วย epsilon 1 นาที
        if secs >= 86400 - 60:
            return f"เหลืออีก {int(-(-secs // 86400))} วัน"
        return f"เหลืออีก {int(max(1, -(-secs // 3600)))} ชม."
    except Exception:
        return ""


def item_summary_line(item):
    """บรรทัดเดียวสั้นๆ สำหรับ Listbox — ฝาก/เบิกได้ไหม + ชื่อ + วันหมดอายุ
    (⏳ หน้าชื่อ = หมดอายุแล้ว ฝาก/เบิกไม่ได้)"""
    name = item_display_name(item)
    src = "ARMS" if item.get("SourceTable") == "ARMS" else "ITEM"
    dep = "ฝากได้" if item_can_deposit(item) else "-"
    wd = "เบิกได้" if item_can_withdraw(item) else "-"
    end = _fmt_end(item.get("EndDate"))
    mark = "·"
    if item_is_expired(item):
        mark = "⏳"
    elif item_can_delete(item):
        mark = "🗑"  # ลบได้ (ของไม่ถาวร)
    elif item_expires_within_days(item):
        mark = "◷"  # ใกล้หมดอายุ — ยังใช้ได้แต่จะหายเร็ว
    return f"[{dep:^5}/{wd:^5}] {mark} ({src}) {name}  |  สิ้นสุด {end}"


def item_detail_lines(item):
    """รายละเอียดเต็มของไอเทม 1 ชิ้น (จาก fields ที่เว็บส่งมา) — ใช้แสดงในหน้าต่าง
    'ดู/เลือกไอเทม' เพื่อให้เห็นรายละเอียดเยอะๆ ก่อนตัดสินใจฝาก/เบิก

    คืน list ของ (label, value) — แปลง field ที่รู้จักให้อ่านง่ายก่อน แล้วไล่ field
    ที่เหลือแบบดิบ (key เดิมจากเว็บ) ให้ครบทุกอัน เพื่อกันข้อมูลหาย"""
    out = []
    name = item_display_name(item)
    out.append(("ชื่อไอเทม", name))
    out.append(("รหัส (ItemSerial)", str(item.get("ItemSerial") or "-")))
    out.append(("ตารางต้นทาง", "ARMS (อาวุธ)" if item.get("SourceTable") == "ARMS" else str(item.get("SourceTable") or "-")))
    out.append(("รหัสเว็บ (ItemCode)", str(item.get("ItemCode") or "-")))
    out.append(("สถานะ (ItemStatus)", _status_th(item.get("ItemStatus"))))
    out.append(("ฝากไว้แล้ว?", "ใช่ (IsDeposited=Y)" if item.get("IsDeposited") == "Y" else "ยังอยู่ที่ตัว"))
    out.append(("หมดอายุ / เหลือ", f"{_fmt_end(item.get('EndDate'))} ({_fmt_remaining(item)})"))
    out.append(("ฝากได้ไหม", "ได้" if item_can_deposit(item) else "ไม่ได้"))
    out.append(("เบิกได้ไหม", "ได้" if item_can_withdraw(item) else "ไม่ได้"))
    out.append(("ลบได้ไหม", "ได้ (ของไม่ถาวร)" if item_can_delete(item) else "ไม่ได้ (ของถาวร)"))
    # fields ที่เหลือแบบดิบ (key อื่นๆ ที่เว็บส่งมา — กันข้อมูลหาย)
    known = {
        "CleanItemName", "ItemName", "ItemCode", "ItemSerial", "SourceTable",
        "ItemStatus", "IsDeposited", "EndDate",
    }
    for k in sorted(item.keys()):
        if k in known:
            continue
        v = item[k]
        if v is None or v == "":
            continue
        out.append((str(k), str(v)))
    return out


def item_operation(session, page_url, operation, item, username=""):
    """ฝาก/เบิก/ลบไอเทม 1 รายการ — คืน (ok, message)

    operation: 'DEPOSIT' / 'WITHDRAW' / 'DELETE' (WebMethod เดียวกันทั้ง 3)
    ⚠ ไม่ retry — POST เปลี่ยนสถานะไอเทมจริง (ลบ = หายถาวร) ห้ามส่งซ้ำมั่วๆ
    """
    item_type = "A" if item.get("SourceTable") == "ARMS" else "I"
    ref_id = item.get("ItemSerial")
    payload = {
        "operation": operation,
        "itemType": item_type,
        "itemRefId": ref_id,
    }
    d = _wm_call(session, page_url, "PerformItemOperation", payload, username)
    ok = bool(d.get("success"))
    msg = str(d.get("message") or "").strip()
    return ok, msg


__all__ = [
    "INVENTORY_URL",
    "INV_CATEGORIES",
    "INV_NEAR_EXPIRE_DAYS",
    "fetch_all_items",
    "fetch_items_page",
    "inv_category_label",
    "inv_category_options",
    "item_can_delete",
    "item_can_deposit",
    "item_can_withdraw",
    "item_detail_lines",
    "item_display_name",
    "item_expires_within_days",
    "item_in_category",
    "item_is_expired",
    "item_operation",
    "item_summary_line",
    "open_inventory",
]
