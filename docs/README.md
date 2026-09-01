# SFBOT — เจ้าพี ออโต้ คีย์เวิร์ด

บอทเดสก์ท็อป (Windows, Tkinter) สำหรับเกม **Special Force** — ล็อกอินหลายบัญชีพร้อมกัน
กรอกคีย์เวิร์ด/โค้ดกิจกรรมให้ทุกไอดีอัตโนมัติ ดึงคีย์ของแจกประจำวันส่งเข้า Discord
และรับไอเทมฟรีอัตโนมัติ

เวอร์ชันปัจจุบัน: **1.2.8**

---

## ✨ ความสามารถหลัก

| แท็บ | ความสามารถ |
|---|---|
| ▶ แดชบอร์ด | ล็อกอินทุกบัญชี, กรอกคีย์เวิร์ด, เริ่มรันอัตโนมัติ, log/สถิติ |
| ◉ บัญชี | จัดการบัญชี (เพิ่มทีละราย / โหลด .txt), เลือกหน่วยเซิร์ฟเวอร์, บันทึกรหัสแบบเข้ารหัส, เก็บ cookie ต่อไอดี |
| ▤ คีย์เวิร์ด | จัดการลิสต์คีย์เวิร์ด/โค้ดกิจกรรม |
| 🔑 คีย์ประจำวัน | ดึงคีย์แจกประจำวัน + ส่งเข้า Discord Webhook อัตโนมัติ (00:05 ทุกวัน) / ด้วยมือ, ประวัติข้อความที่เคยส่ง |
| 🎁 รับไอเทมฟรี | ระบบแยกต่างหาก (บัญชี/Webhook ของตัวเอง) รับไอเทมฟรีอัตโนมัติ |
| ⚙ ตั้งค่า | หน่วงระหว่างล็อกอิน (กันล็อก 15 นาที), เปิดพร้อมวินโดวส์ |

ระบบเสริม: ถาดระบบ (ซ่อนลงถาดเมื่อกด X), เปิดพร้อมวินโดวส์ (Run key), single-instance
กันเปิดซ้อน, rate limit กันบัญชีโดนล็อก 15 นาที,
บันทึก cookie ต่อไอดี (ล็อกอินครั้งเดียวใช้ข้ามรอบ), redaction รหัสผ่าน/cookie ในทุก log

---

## 🖥 ความต้องการ

- **Windows 10/11** (โค้ดพึ่งพา registry, `pythonw.exe`, Windows mutex, Run key)
- **Python 3.10+** พร้อม Tkinter (ติดตั้งจาก python.org แล้วติ๊ก "tcl/tk and IDLE")
- ตอน build เท่านั้น: Microsoft Visual C++ Build Tools **เฉพาะถ้าต้องการกันโค้ด
  (Cython + PyArmor)** — build แบบไม่กันโค้ดไม่ต้องใช้

---

## 🚀 วิธีเปิดใช้

### รันจากซอร์สโค้ด

```bat
:: ติดตั้ง dependencies ครั้งแรก (manifest กลางที่ root)
pip install -r requirements.txt

:: เปิดโปรแกรม
python sfbot.pyw
```

หรือดับเบิลคลิก `sfbot.pyw` โดยตรง (Windows จะรันด้วย `pythonw.exe` ให้อัตโนมัติ ไม่มี
console ค้าง)

**อาร์กิวเมนต์ที่รองรับ:**
- `--tray` — เปิดแล้วซ่อนลงถาดระบบทันที (ใช้โดย "เปิดพร้อมวินโดวส์")

**หมายเหตุ:**
- เปิดได้แค่หน้าต่างเดียว — ถ้าเปิดซ้ำจะเด้งแจ้งเตือน "เปิดโปรแกรมซ้ำ"
- ข้อมูลทั้งหมด (บัญชี/คีย์เวิร์ด/cookie/log) เก็บที่ `%LOCALAPPDATA%\SFBOT\`
  ไม่ใช่ข้างไฟล์ .exe — โครงสร้างโฟลเดอร์ดูได้ที่หัวข้อ "ข้อมูลที่เก็บ"

### เปิดใช้งานครั้งแรก (สรุป)

1. แท็บ **◉ บัญชี** → เพิ่มบัญชี (หรือโหลด .txt) → กด **💾 บันทึก**
2. แท็บ **▤ คีย์เวิร์ด** → เพิ่มคีย์เวิร์ด
3. แท็บ **▶ แดชบอร์ด** → กด **⚿ ล็อกอิน** รอจนเสร็จ
4. กด **➤ กรอกคีย์เวิร์ด** (หรือ **▶ เริ่มรันอัตโนมัติ** ทำทีเดียว)

---

## 🔨 วิธี build (.exe)

รัน `build_client.bat` จากโฟลเดอร์โปรเจกต์ (ดับเบิลคลิก หรือรันจาก cmd):

```bat
build_client.bat
```

สคริปต์จะทำตามลำดับ:

1. อ่านเวอร์ชันจาก `sfbot_lib/core/constants.py` (`VERSION = "1.0.0"`) ผ่าน `tools/get_version.py`
   → ตั้งชื่อไฟล์เป็น `SFBOT_v1.0.0.exe` อัตโนมัติ
2. สร้าง virtualenv (`venv/`) แล้วติดตั้ง dependencies จาก `tools/requirements.txt`
3. รัน `tools/check_bugs.py` ตรวจหา bug pattern ก่อน build — เจอปัญหาจะหยุดทันที
   และรัน `ruff` ตรวจบั๊ก/เดดโค้ด (`python -m ruff check .` ตั้งค่าใน
   `pyproject.toml`) พร้อมสแกนเดดโค้ด (`tools/find_dead_code.py`) —
   ผิดพลาดจุดไหนหยุด build ทันที
4. ถามว่าต้องการกันโค้ดหรือไม่ (`y/N`):
   - **y** — ติดตั้ง `tools/requirements-build.txt` (Cython + PyArmor) แล้วก็อปปี้โปรเจกต์
     ไป `build_protected/` → compile `sfbot_lib/` ด้วย Cython → obfuscate `sfbot.pyw`
     ด้วย PyArmor → build จากสำเนาที่กันโค้ดแล้ว *(ต้องมี MSVC Build Tools)*
   - **N** — build จากซอร์สตรงๆ
5. `PyInstaller --onefile --noconsole` → ไฟล์ออกที่ **`dist\SFBOT\SFBOT_v1.0.0.exe`**
6. คำนวณ SHA-256 และบันทึกลง `docs/release_history.csv` **เฉพาะเมื่อยืนยันว่าเป็น release**
   (ตอบ "y" หรือตั้ง `SFBOT_LOG_RELEASE=y`) — ประวัติเก็บเฉพาะเวอร์ชันที่ปล่อยบน GitHub จริง

> ไฟล์ `.exe` ตัวเดียวเท่านั้นที่ต้องแจกจ่ายให้ลูกค้า — ทำงานได้เองโดยไม่ต้องมีไฟล์อื่น
> ข้างๆ

### กันโค้ด (Cython + PyArmor) — ทางเลือก

```bat
set SFBOT_PROTECT=y
build_client.bat
```

ต้องติดตั้ง **"Desktop development with C++"** จาก
[visualstudio.microsoft.com/visual-cpp-build-tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
ก่อน — `build_client.bat` จะตรวจเจอ vswhere ให้อัตโนมัติ ถ้าไม่มีจะถามให้ข้ามไป build
แบบไม่กันโค้ดแทน

> ⚠️ `vcvarsall.bat` ค้างได้ใน shell ที่ไม่ใช่ interactive (Git Bash / CI / sandbox)
> — `build_client.bat` ตั้ง environment ของ MSVC + Windows SDK ตรงๆ แล้วไม่เรียก
> vcvarsall แต่ถ้าเจอ `cmd.exe` ค้างเอง ให้ใช้ driver แบบ Python แทน:
>
> ```bash
> venv/Scripts/python.exe -X utf8 tools/build_tools/build_protected_driver.py
> ```
>
> ดูรายละเอียดทั้งสองวิธี + ขั้นตอน ZIP/Release/update.json ได้ที่
> **`docs/build-protected.md`**

---

## 📁 ข้อมูลที่เก็บ (`%LOCALAPPDATA%\SFBOT\`)

| ไฟล์/โฟลเดอร์ | เนื้อหา |
|---|---|
| `config/` | ตั้งค่าปัจจุบันแยกหมวด (ui / automation / account / webhook / system) |
| `sfbot_settings.json` | ไฟล์ตั้งค่าเก่า (legacy — migrate ครั้งเดียวแล้วเลิกใช้) |
| `sf_cookies/` | cookie ต่อบัญชี (ใช้ล็อกอินข้ามรอบ ไม่ต้องล็อกอินใหม่ทุกครั้ง) |
| `logs/` | `sfbot_YYYYMMDD.log` + `.jsonl` (หมุนรายวัน, เก็บ 7 วัน), `error_YYYYMMDD.log` |
| `results/` | ผลลัพธ์รอบการรันแบบ CSV |
| `account_history.csv` | ประวัติบัญชี |
| `settings_backups/` | สำรองตั้งค่า (สำหรับ "กู้คืนการตั้งค่า") |
| `webhook_sent_messages.json` | ประวัติข้อความ Discord ที่เคยส่ง |
| `sfbot_crash.log` | crash log (กันหลุดตอน callback UI) |

---

## 🗂 โครงสร้างโปรเจกต์

### ไฟล์ระดับบนสุด

| ไฟล์ | หน้าที่ |
|---|---|
| `sfbot.pyw` | **Entry point** — bootstrap เท่านั้น: DPI awareness, spawn `pythonw.exe`, single-instance mutex, `--tray` / auto-start detection, สร้าง `App` แล้วเข้า mainloop |
| `build_client.bat` | สคริปต์ build .exe (venv → check_bugs → กันโค้ด (ไม่บังคับ) → PyInstaller) |
| `tools/get_version.py` | อ่าน `VERSION` จาก `sfbot_lib/core/constants.py` ให้ build script ตั้งชื่อไฟล์ |
| `tools/check_bugs.py` | ตรวจ bug pattern ทั่วทั้งแพ็กเกจก่อน build (missing method, import shadowing ฯลฯ) |
| `tools/find_dead_code.py` | สแกนเดดโค้ด (module-level def ที่ไม่ถูกใช้) ก่อน build — เจอจะหยุด build |
| `tools/requirements.txt` | dependencies รันจริง (requests, cryptography, Pillow, pystray, pyinstaller …) |
| `tools/requirements-build.txt` | dependencies สำหรับกันโค้ด (Cython, PyArmor) |
| `requirements.txt` | manifest กลาง (root) — รวม dependencies ทั้งหมดผ่าน `-r` ไปยัง `tools/requirements*.txt` (ใช้ `pip install -r requirements.txt` ได้ครบ) |
| `tools/build_tools/` | สคริปต์กันโค้ด: `cythonize_lib.py`, `obfuscate_entry.py`, `list_lib_modules.py`, `build_protected_driver.py` (driver build แบบกันโค้ด ไม่ต้องใช้ vcvarsall) |
| `docs/README.md` | เอกสารนี้ |
| `docs/build-protected.md` | วิธี build แบบกันโค้ด (Cython + PyArmor) โดยไม่ใช้ vcvarsall.bat + ขั้นตอน Release |
| `pyproject.toml` | config `ruff` — ตรวจบั๊ก/เดดโค้ด (รัน `python -m ruff check .`) |
| `docs/release_history.csv` | ประวัติ release (ตรงกับ release จริงบน GitHub) |
| `docs/RELEASE_CHECKLIST.md` | checklist ปล่อยเวอร์ชันใหม่ (build → zip → sha256 → release → update.json) — ไล่ตามลำดับทุกครั้ง |
| `assets/sf_logo.ico` + `sf_logo.jpg` | ไอคอนแอป |

### แพ็กเกจ `sfbot_lib/`

`App` เป็นคลาสเดียวที่ประกอบจาก mixin หลายไฟล์ (split-by-feature-area) — ทุก `app_*`
แชร์สถานะผ่าน `self.xxx` ที่ตั้งไว้ใน `AppCoreMixin.__init__` / `_build_ui()`

| โมดูล | หน้าที่ |
|---|---|
| `deps` | รวม import ของ third-party/optional (tkinter, PIL, requests, cryptography) + ตัวแปรบอกความพร้อม (`_PIL_OK` …) |
| `constants` | `VERSION`, URL, สีธีม, ตัวเลือก dropdown (หน่วย/แรงค์/ประเภทไอดี), ความกว้างคอลัมน์ตาราง |
| `paths` | ตำแหน่งโฟลเดอร์ข้อมูล, migrate ข้อมูลรุ่นเก่า, `_resource_path`, จัดการ Run key "เปิดพร้อมวินโดวส์" |
| `security` | เข้ารหัสรหัสผ่านตอนเก็บ (DPAPI / Fernet / XOR fallback) |
| `http_flow` | **Pure-HTTP engine** (backend ปัจจุบัน): ล็อกอิน, cookie fast-path, ส่งคีย์เวิร์ด, เลือกแรงค์/หน่วย, ยืนยันรับไอเทม, rate limit กันล็อก 15 นาที |
| `webhook` | ดึงคูปอง SF (`fetch_sf_coupons`), ส่ง/จัดรูปแบบ Discord webhook |
| `labels` | แปลงโค้ดภายใน → label ภาษาไทย (เช่น `gameid` → "Game ID") |
| `exceptions` | exception เฉพาะของ flow ล็อกอิน/คีย์เวิร์ด |
| `ui_theme` | วิดเจ็ต Tk ธีมมืด + helper (toast, popup, toggle switch, overlay ยืนยัน) |
| `rows` | วิดเจ็ตแถวตาราง: `AccountRow` / `WebhookRow` / `KeywordRow` |
| `log_system` | ระบบ logging ส่วนกลาง: หมุนรายวัน 3 รูปแบบ, redaction password/cookie, retention 7 วัน |
| `perf_logger` | บันทึก RAM/thread ของโปรแกรมทุก 60 วิ ลง `logs/sfbot_perf_YYYYMMDD.log` (audit memory leak) |
| `updater` | อัปเดตอัตโนมัติ + kill-switch ผ่าน GitHub (`update.json` / `kill_switch.json`) |
| `worker_manager` | จัดการ background thread ส่วนกลาง (สร้าง/ติดตาม/หยุดเป็นระบบ แทนที่การ `threading.Thread(...).start()` กระจาย) |
| `app` | คลาส `App` — ประกอบ mixin ทั้งหมด (ไม่มีความ logic เอง) |
| `app_core` | `__init__`, properties กัน thread race, geometry, `_build_ui()` ทั้งหน้าต่าง |
| `app_settings` | โหลด/บันทึกตั้งค่า, migrate ไฟล์ตั้งค่า, reset, สำรอง/กู้คืน |
| `app_settings_diagnostics` | stub class สำหรับ MRO compatibility (ฟีเจอร์ diagnostic ถูกลบแล้ว) |
| `app_settings_tab` | UI แท็บ "ตั้งค่า" |
| `app_tables` | เพิ่ม/ลบ/reindex/นับแถวในตารางบัญชี/คีย์เวิร์ด/webhook |
| `app_webhook_ui` | ยูทิลิตี้ webhook ร่วม: redaction, ส่งทุกช่อง, จัดแบ่ง embed, ทดสอบการเชื่อมต่อ |
| `app_coupon_picker` | หน้าต่างเลือกคูปองคีย์ประจำวัน (ดึง/เลือก/ก็อปปี้/เพิ่มเข้าคีย์เวิร์ด/ส่ง) |
| `app_manual_key_sender` | หน้าต่างส่งคีย์ด้วยมือ (พิมพ์/วาง แล้วส่ง) |
| `app_daily_key_watcher` | poller คีย์ประจำวันเบื้องหลัง + toggle/nับถอยหลัง |
| `app_webhook_history` | ดู/ลบข้อความ Discord ที่เคยส่ง |
| `app_autoitem_ui` / `app_autoitem_webhook` / `app_autoitem_engine` | แท็บ "รับไอเทมฟรี": UI, webhook, เอนจินรับของ |
| `app_logging` | แผง log ในแอป: queue, filter, ค้นหา, เขียนไฟล์ run-log |
| `app_stats` | สถิติการรัน, ประวัติต่อบัญชี, ส่งออก CSV |
| `app_runtime` | timer, progress bar, deadlock watchdog |
| `app_automation` | `run_session_multi` (ตัวรันคีย์เวิร์ดต่อบัญชี), ปิดเซสชัน, ปุ่มสถานะ |
| `app_login_flow_core` | `do_login` / `login_only` (cookie fast-path) — ใช้ `http_flow` (Pure HTTP) |
| `app_keyword_flow_core` | `do_keyword` — ใช้ `http_flow.submit_keyword` |
| `app_window` | global shortcuts (Ctrl+C/V/X/A คีย์บอร์ดไทย), ถาดระบบ, ซ่อน/ปิดลงถาด |
| `app_run_control_session` / `app_run_control_helpers` / `app_run_control_flows` | relogin รายแถว, run-summary dialog, `start_login` / `start_keyword` / `start_auto_run` |
| `app_dialogs` | popup กลางที่แชร์ทั้งแอป: alert/confirm/toast helper (ทุก mixin เรียกใช้) |
| `app_accounts_tab` / `app_keywords_tab` / `app_dashboard_tab` / `app_dailykey_tab` / `app_settings_tab` | UI ของแต่ละแท็บ |

`check_bugs.py` รู้จักการแยกแบบ mixin นี้ (ดู `_MIXIN_GROUP_PREFIXES`) — ตรวจไฟล์
`app_*.py` ทั้งกลุ่มเป็นหน่วยเดียวตอนหา missing method

---

## 🔒 ความปลอดภัย

- **ไม่มี network call ตอนเปิดโปรแกรม** — เส้นทาง import → สร้างหน้าต่าง → mainloop
  ไม่ติดต่ออินเทอร์เน็ต (ตรวจสอบแล้วทั้งแบบ static และ dynamic)- network call ที่เหลือทั้งหมดเป็นฟีเจอร์หลักและเกิดจากผู้ใช้กดเท่านั้น:
  - หน้าเว็บ SF ระหว่างล็อกอิน/กรอกคีย์เวิร์ด — ผ่าน HTTP (requests) โดยตรง
  - ส่ง/ดึงข้อมูล Discord webhook ตาม URL ที่ผู้ใช้ตั้งเอง
- **กันล็อก 15 นาที**: ล็อกอิน HTTP มี rate limit ในตัว (ค่าเริ่มต้น 8 วิ/ไอดี ปรับได้ที่แท็บตั้งค่า)
- รหัสผ่านถูกเข้ารหัสตอนเก็บ (DPAPI/Fernet) และทุก log ผ่าน redaction filter —
  password/cookie/token ไม่เคยหลุดลงไฟล์หรือจอ

---

## 🛠 แก้ปัญหา

| อาการ | วิธีแก้ |
|---|---|
| ล็อกอินไม่ผ่านซ้ำๆ ทั้งที่รหัสถูก | แดชบอร์ด → **🍪 ล้าง Cookie ทั้งหมด** แล้วล็อกอินใหม่ |
| กรอกคีย์เวิร์ดแล้วไม่มีอะไรเกิดขึ้น | ต้องล็อกอินผ่านก่อนเสมอ — ดูการ์ดสรุปผลในแดชบอร์ด |
| บัญชีโดนล็อก 15 นาที (ข้อความ "suspicious activity") | รอ 15 นาที หรือเพิ่ม "หน่วงระหว่างล็อกอิน" ในแท็บตั้งค่า — อย่ายิงล็อกอินซ้ำเร็วๆ |
| อยากล็อกเอาต์เซสชันที่ค้าง | แดชบอร์ด → **ปิดเซสชันทั้งหมด** แล้วล็อกอินใหม่ |
| Webhook ไม่ส่งข้อความ | กด "ทดสอบส่งข้อความ" ก่อน — มักเป็น URL ผิด หรือ Webhook ถูกลบฝั่ง Discord |
| ยังแก้ไม่ได้ | ดูไฟล์ใน `%LOCALAPPDATA%\SFBOT\logs/` แล้วส่งให้ทีมตรวจ |
