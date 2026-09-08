"""Static configuration: URLs, colors, dropdown option maps, and table
column widths used throughout the UI."""

VERSION = "1.3.37"

# ค่าให้เลือกในช่อง 'พร้อมกัน' (dropdown — กดเลือกได้ หรือพิมพ์เองได้ 1–99)
CONCURRENCY_PRESETS = [str(i) for i in range(1, 31)] + [
    str(i) for i in range(35, 100, 5)
]

# ค่าให้เลือกในช่อง 'หน่วงระหว่างล็อกอิน (วินาที)' — ทศนิยม 0.1–60
LOGIN_DELAY_PRESETS = ["0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "0.9", "1"] + [
    "1.5", "2", "2.5", "3", "4", "5", "8", "10", "12", "15", "20", "30", "45", "60",
]

LOGIN_URL = "https://auth.gg.in.th/authenticate_v3/Auth_Full/Login.aspx?appid=1&scope=&state=1&sourceid=1&redirecturi=http%3a%2f%2fmember.sf.in.th%2fLandingPlatform.aspx&fblogin=true"
KEYWORD_URL = "http://member.sf.in.th/Keyword/"

HOME_URL = "http://keyword.gg.in.th/"
DAILY_KEY_PREFIX = "คีย์ของแจกประจำวัน"
SF_GAME_HINT = "Special Force"
_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
}


_DISCORD_BOT_NAME = "SFKeyword"
_DISCORD_AVATAR_URL = "https://i.postimg.cc/654K0GmL/sf-logo.jpg"


BG = "#0E0F14"
BG2 = "#15161D"
BG3 = "#1C1D27"
BG4 = "#242631"
ACC = "#E8455A"
ACC2 = "#A78BFA"
FG = "#E5E7EB"
FG2 = "#9CA3AF"
FG3 = "#8B93A7"
GREEN = "#059669"

# ── สีสถานะ/ผลลัพธ์ (ใช้ร่วมกันทั้งแอป — แก้ที่นี่จุดเดียวเปลี่ยนทุกหน้า) ──
STATUS_OK = "#2DD4BF"        # ✅ สำเร็จ (log/สถานะ/ตัวนับ/ป้าย)
STATUS_ACTIVE = "#00ff99"    # ✅ เปิดใช้/พร้อมใช้ (ตัวเลขที่ต้องการเด่น)
STATUS_FAIL = "#F05252"      # ❌ ล้มเหลว (สถานะ/ตัวนับ/ข้อความ)
STATUS_ERR = "#F0495C"       # ❌ ผิดพลาดรุนแรง (popup/ข้อความ error)
STATUS_WARN = "#F5C542"      # ⚠ เตือน/รอ/ปุ่มเตือน
DANGER = "#ff6b6b"           # 🔴 ปุ่มลบ/ล้าง (แดงอ่อน)
DANGER_STRONG = "#DC2626"    # 🔴 ปุ่มยืนยันการกระทำอันตราย (แดงเข้ม)
INFO_BLUE = "#60C8F5"        # ℹ ปุ่มโหลด/ข้อมูล (ฟ้า)

# ค่าหน่วง/ลองซ้ำที่ engine ใช้ — เดิม hardcode ไว้ใน UI builder ของแท็บตั้งค่า
# ย้ายมารวมที่ constants ให้แก้จุดเดียว (ไม่เกี่ยวกับช่องกรอก "หน่วงระหว่างล็อกอิน")
FIXED_DELAY_SEC = 0         # หน่วงระหว่างส่งคีย์เวิร์ด (วินาที) — ค่าเริ่มต้นเร็วสุด: ไม่หน่วง
FIXED_RETRY_COUNT = 2        # จำนวนลองซ้ำต่อคีย์เวิร์ด
NETWORK_RETRY_BASE_SEC = 1   # backoff เริ่มต้นของปัญหาเครือข่าย (วินาที) — เร็วสุดที่ปลอดภัย

TYPE_OPTIONS = ["Game ID", "GG Passport"]
TYPE_MAP = {"Game ID": "gameid", "GG Passport": "ggpassport"}

RANK_OPTIONS = ["แรงค์ 1", "แรงค์ 2", "ไม่เลือก"]
RANK_MAP = {"แรงค์ 1": "rank1", "แรงค์ 2": "rank2", "ไม่เลือก": "skip"}

UNIT_OPTIONS = [
    "ไม่เลือก",
    "SAS",
    "DELTA",
    "GIGN",
    "GSG9",
    "SpetSnaz",
    "ROKMC",
    "KSF",
    "SASR",
    "FORCERECOX",
    "PSU",
    "SRG",
    "SSD",
    "EID",
    "SIAM",
]
UNIT_MAP = {u: u for u in UNIT_OPTIONS}
UNIT_MAP["ไม่เลือก"] = "skip"

# aliases สำหรับจับคู่ชื่อหน่วยที่เว็บอาจแสดงต่างกัน (ตัวเล็ก/ตัวใหญ่/ชื่อย่อ)
# ใช้ใน _pick_grid_row เพื่อให้จับคู่ได้ยืดหยุ่นขึ้น
UNIT_ALIASES = {
    # DELTA
    "delta": "DELTA",
    "delta force": "DELTA",
    # FORCERECOX
    "forcerecox": "FORCERECOX",
    "force recon": "FORCERECOX",
    "force recon usa": "FORCERECOX",
    # SpetSnaz
    "spetsnaz": "SpetSnaz",
    "spet snaz": "SpetSnaz",
    # SAS
    "sas": "SAS",
    "sas uk": "SAS",
    # GIGN
    "gign": "GIGN",
    # GSG9
    "gsg9": "GSG9",
    # ROKMC
    "rokmc": "ROKMC",
    # KSF
    "ksf": "KSF",
    # SASR
    "sasr": "SASR",
    # PSU
    "psu": "PSU",
    # SRG
    "srg": "SRG",
    # SSD
    "ssd": "SSD",
    # EID
    "eid": "EID",
    # SIAM
    "siam": "SIAM",
}

BORDER = "#4A4F70"

COL_NUM, COL_USER, COL_PWD, COL_TYPE, COL_RANK, COL_UNIT, COL_UNIT2 = (
    38,
    140,
    140,
    122,
    100,
    104,
    150,
)
COL_KEYWORD_NUM, COL_KEYWORD_VAL = 38, 560

__all__ = [
    "ACC",
    "ACC2",
    "BG",
    "BG2",
    "BG3",
    "BG4",
    "BORDER",
    "COL_KEYWORD_NUM",
    "COL_KEYWORD_VAL",
    "COL_NUM",
    "COL_PWD",
    "COL_RANK",
    "COL_TYPE",
    "COL_UNIT",
    "COL_UNIT2",
    "COL_USER",
    "DAILY_KEY_PREFIX",
    "DANGER",
    "DANGER_STRONG",
    "FG",
    "FG2",
    "FG3",
    "GREEN",
    "HOME_URL",
    "INFO_BLUE",
    "STATUS_ACTIVE",
    "STATUS_ERR",
    "STATUS_FAIL",
    "STATUS_OK",
    "STATUS_WARN",
    "KEYWORD_URL",
    "LOGIN_URL",
    "RANK_MAP",
    "RANK_OPTIONS",
    "SF_GAME_HINT",
    "TYPE_MAP",
    "TYPE_OPTIONS",
    "UNIT_ALIASES",
    "UNIT_MAP",
    "UNIT_OPTIONS",
    "VERSION",
    "_DISCORD_AVATAR_URL",
    "_DISCORD_BOT_NAME",
    "_HTTP_HEADERS",
]
