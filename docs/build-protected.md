# Build แบบกันโค้ด (Cython + PyArmor) — โดยไม่ใช้ vcvarsall.bat

คู่มือนี้สำหรับ build `.exe` แบบ **กันโค้ด** (protected) — compile `sfkeyword_lib\`
เป็น native `.pyd` ด้วย **Cython** และ obfuscate entry point (`sfkeyword.pyw`) ด้วย
**PyArmor** — โดยไม่ต้องพึ่ง `vcvarsall.bat` ซึ่ง **ค้างได้ใน shell ที่ไม่ใช่
interactive** (Git Bash, ระบบ automation, CI) แม้จะติดตั้ง Build Tools ครบแล้วก็ตาม

ใช้ได้ตั้งแต่รอบ v1.1.9 เป็นต้นไป

---

## ทำไมต้องมีวิธีนี้

`build_client.bat` เวอร์ชันก่อนหน้าเรียก `vcvarsall.bat` เพื่อตั้ง
PATH/INCLUDE/LIB ของ MSVC ตอนเลือกตอบ "y" (กันโค้ด) — บนเครื่องบางเครื่อง
(รวมถึงเครื่อง build ของโปรเจกต์นี้) `vcvarsall.bat` ค้างนานเกิน 10 นาที
โดยไม่จบ แก้ที่ `build_client.bat` แล้วให้ **ตั้ง environment ของ MSVC + Windows
SDK ตรงๆ** แทน (หาเวอร์ชันล่าสุดจากโฟลเดอร์ที่ติดตั้ง ไม่เรียก vcvarsall)
และมีสคริปต์ driver แยกให้ใช้ในทุก shell

---

## ข้อกำหนด

- Windows 10/11, **Python 3.12** (ตาม venv ที่ใช้อยู่)
- **Microsoft Visual C++ Build Tools** ต้องติดตั้ง workload
  **"Desktop development with C++"** (มี `cl.exe` และ Windows SDK)
  ดาวน์โหลด: <https://visualstudio.microsoft.com/visual-cpp-build-tools/>
- ติดตั้ง dependencies ให้ venv ก่อน (ถ้ายัง) — ใช้ manifest กลางที่ root
  (ดูหัวข้อ [Dependencies](#dependencies-จัดการผ่าน-manifest-กลาง) ข้างล่าง):
  ```bat
  venv\Scripts\python.exe -m pip install -r requirements.txt
  ```

ตรวจว่าเครื่องมี compiler ครบ (ผลลัพธ์ต้องเจอ `cl.exe` และ SDK):

```bash
ls "/c/Program Files (x86)/Microsoft Visual Studio/"*/BuildTools/VC/Tools/MSVC/*/bin/Hostx64/x64/cl.exe
ls "/c/Program Files (x86)/Windows Kits/10/Include/"
```

---

## Dependencies (จัดการผ่าน manifest กลาง)

โปรเจกต์มี **manifest กลางจุดเดียว** ที่ root: `requirements.txt` — รวม
dependencies ทั้งหมดผ่าน `-r` ไปยังไฟล์ย่อย 2 ไฟล์ เพื่อไม่ให้ลิสต์ซ้ำ
(แก้จุดเดียว ได้ครบทั้ง runtime + build):

| ไฟล์ | เนื้อหา | ใช้ตอน |
|---|---|---|
| `tools/requirements.txt` | runtime + tooling: `packaging`, `requests`, `cryptography`, `Pillow`, `pystray`, `pyinstaller`, `ruff` | รันแอป / ตรวจโค้ด / แพ็ก EXE |
| `tools/requirements-build.txt` | build: `Cython`, `pyarmor`, `setuptools` | ขั้นกันโค้ด (Cython + PyArmor) |

ติดตั้งครั้งแรก (หลังสร้าง venv):

```bash
python -m venv venv
venv/Scripts/python.exe -m pip install --upgrade pip
venv/Scripts/python.exe -m pip install -r requirements.txt
```

อัปเดต/ซิงค์ venv ให้ตรง manifest (ติดตั้งตัวใหม่ + อัปเกรดตัวเก่า):

```bash
venv/Scripts/python.exe -m pip install -r requirements.txt --upgrade
```

ตรวจว่า venv ตรง manifest — top-level ต้องเป็นชุดเดียวกับที่ลิสต์ไว้:

```bash
venv/Scripts/python.exe -m pip list --not-required
```

> `pip` เป็นตัวจัดการแพ็กเกจเอง ไม่ต้องลิสต์ และ venv ปัจจุบันตรง manifest
> ครบแล้ว — ไม่มีแพ็กเกจเกิน (เช่น selenium ยุคเก่า) ติดค้าง

---

## วิธีที่ 1 — `build_client.bat` (แนะนำสำหรับใช้ปกติ)

สคริปต์หา MSVC + Windows SDK เอง และตั้ง environment ตรงๆ (ไม่เรียก
vcvarsall) รันจาก **Command Prompt** ปกติ:

```bat
set SFKeyword_PROTECT=y
build_client.bat
```

- `SFKeyword_PROTECT=y` = ตอบ "y" ข้อ "Protect source with Cython + PyArmor?" อัตโนมัติ
- `SFKeyword_NO_PAUSE=y` = ข้ามทุก `pause` ท้ายสคริปต์ (ใช้ตอนรันอัตโนมัติ/headless กันค้าง)
- Cython compile แบบขนาน (`-j` ตามจำนวน CPU) + แคช `.pyd` ข้าม build
  (`.cython-cache\` ที่ root โปรเจกต์ — ห้ามลบ ไม่งั้นรอบหน้าต้อง compile ใหม่ทั้งหมด)
  → รอบแรก ~50 วิ รอบถัดไป (เนื้อหาไม่เปลี่ยน) เหลือ ~20-25 วิ
- ผลลัพธ์: `dist\SFKeyword\SFKeyword_v<เวอร์ชัน>.exe`
- บันทึก `docs/release_history.csv` **เฉพาะเมื่อยืนยันว่าเป็น release** — ตั้ง `SFKeyword_LOG_RELEASE=y`
  หรือตอบ "y" ข้อถาม "Release build - log this build to docs/release_history.csv?" (ค่าเริ่มต้น N = ไม่บันทึก)
- ถ้าเจอ MSVC ไม่ครบ สคริปต์จะถามให้ข้ามไป build แบบไม่กันโค้ดแทน
  (ตอบอัตโนมัติได้ด้วย env `SFKeyword_SKIP_PROTECT=y`)

> ⚠️ ถ้ารันใน Git Bash / sandbox แล้ว `cmd.exe` ค้างเอง (แม้แต่ `echo` ก็ไม่จบ)
> ให้ใช้ **วิธีที่ 2** ข้างล่างแทน

---

## วิธีที่ 2 — Python driver (ใช้ได้ทุก shell)

สคริปต์ `tools/build_tools/build_protected_driver.py` ทำทุกขั้นตอนใน Python
ตัวเดียว ตั้ง MSVC env เองแล้วรัน Cython → PyArmor → PyInstaller ตามลำดับ
(ไม่แตะ `cmd.exe` / `vcvarsall.bat` เลย):

```bash
venv/Scripts/python.exe -X utf8 tools/build_tools/build_protected_driver.py
```

รันจากโฟลเดอร์โปรเจกต์ (ที่มี `sfkeyword.pyw` และ `venv\`)

สคริปต์จะ:
0. รัน 3 ชุดตรวจ (check_bugs → ruff → find_dead_code) เหมือนวิธีที่ 1 — เจอปัญหาหยุดทันที
1. อ่านเวอร์ชันจาก `sfkeyword_lib/core/constants.py` → `SFKeyword_v<เวอร์ชัน>.exe` อัตโนมัติ
2. หา Build Tools + Windows SDK เวอร์ชันล่าสุด (vswhere / scan โฟลเดอร์)
3. ก็อปปี้โปรเจกต์ไป `build_protected\` (กันโฟลเดอร์ขยะ รวม `.cython-cache` เหมือน robocopy ใน bat)
4. `cythonize_lib.py` → compile `sfkeyword_lib\` เป็น `.pyd` (ยกเว้น `__init__.py`)
   — แบบขนาน (`-j`) + แคช `.cython-cache` ข้าม build: compile เฉพาะโมดูลที่แก้จริง
5. `obfuscate_entry.py` → obfuscate `sfkeyword.pyw` + ก็อปปี้ `pyarmor_runtime_*`
6. PyInstaller `--onefile --noconsole` → `dist\SFKeyword\SFKeyword_v<เวอร์ชัน>.exe`
7. พิมพ์ `size` + `sha256` ให้เอาไปใส่ `update.json`

**จุดสำคัญของ driver** (เทียบกับ vcvarsall):
```python
env["PATH"]  += msvc_bin + kits_bin        # cl.exe + rc.exe (Resource Compiler!)
env["INCLUDE"] = msvc_inc; kits\ucrt; kits\um; kits\shared
env["LIB"]     = msvc_lib; kits\ucrt\x64; kits\um\x64
env["DISTUTILS_USE_SDK"] = "1"             # ให้ setuptools ใช้ env นี้ ไม่หา vcvarsall
env["MSSdk"] = "1"
```

> อย่าลืม `rc.exe` (Windows Kits `bin\<ver>\x64`) — ถ้าไม่ใส่ PATH
> link จะล้มด้วย `LNK1158: cannot run 'rc.exe'`

---

## การตรวจโค้ดอัตโนมัติก่อน build

ก่อนถึงขั้นตอน Cython/PyArmor/PyInstaller ทุก build (ทั้งวิธีที่ 1 และ 2)
จะรัน **3 ชุดตรวจ** — เจอปัญหา หยุด build ทันที:

1. **`tools/check_bugs.py`** — custom check: method หาย, import shadowing, compile error
2. **`python -m ruff check .`** — ตั้งค่าใน `pyproject.toml`:

```toml
select = [
    "F",        # pyflakes: import/ตัวแปรไม่ใช้, ชื่อไม่นิยาม, f-string ไร้ placeholder
    "B007",     # loop control variable ที่ไม่ใช้ใน body
    "B008",     # function call ใน default argument
    "B023",     # closure จับตัวแปร loop โดยไม่ bind ค่า
    "B905",     # zip() โดยไม่ระบุ strict=  (กัน list ยาวไม่เท่ากันเงียบๆ)
    "E741",     # ชื่อตัวแปรกำกวม (l, I, O)
    "PLC0414",  # import alias ที่ไม่ได้เปลี่ยนชื่อ
    "RUF012",   # class attribute เป็น mutable default
    "RUF019",   # เช็ค key ก่อนเข้าถึง dict ซ้ำซ้อน
    "RUF046",   # cast int ที่ซ้ำซ้อน
    "RUF059",   # unpacked variable ที่ไม่ใช้
    "SIM114",   # if สองกิ่งทำสิ่งเดียวกัน → รวมเป็น or
    "TRY401",   # ส่ง exception ซ้ำใน logging.exception
]
```

> ไม่มี `ignore` แล้ว — star imports (`import *`) ถูกลบออกจากโค้ดทั้งหมดและแปลงเป็น
> explicit imports ไปแล้ว ถ้ามีใครเติม `import *` กลับมา `F403`/`F405` จะฟ้องให้
> build หยุดทันที

3. **`tools/find_dead_code.py`** — สแกนหา module-level functions/classes/constants
   ที่ไม่ถูกอ้างถึงทั่วทั้งโปรเจกต์ (AST) — เจอเดดโค้ด จะคืน exit code 1 ให้ build
   หยุด (เหมือนขั้นตอนอื่น) ใช้สแกนซ้ำได้เอง: `python tools/find_dead_code.py`

> ตั้งใจไม่เปิด: `BLE001` broad except, `S110` try-except-pass, `I001` เรียง import,
> `E501` บรรทัดยาว — เป็นสไตล์ของโปรเจกต์ ไม่ใช่บั๊ก

---

## หลัง build — แจกจ่าย

1. **สร้าง ZIP** (จาก EXE ตัวเดียว):

   ```bash
   powershell -NoProfile -Command "Compress-Archive -Path 'dist/SFKeyword/SFKeyword_v<ver>.exe' -DestinationPath 'SFKeyword_v<ver>.zip' -Force"
   ```

2. **อัปเดต release บน GitHub** (`gh` ต้อง login แล้ว):

   ```bash
   gh release delete-asset v<ver> SFKeyword_v<ver>.zip --repo haremking7025/sfbot-control -y
   gh release upload v<ver> "dist/SFKeyword/SFKeyword_v<ver>.exe#/SFKeyword_v<ver>.exe" "SFKeyword_v<ver>.zip#/SFKeyword_v<ver>.zip" --repo haremking7025/sfbot-control --clobber
   ```

   ตรวจว่า asset ถูกต้อง (ขนาด + digest ตรงกับเครื่อง):

   ```bash
   gh release view v<ver> --repo haremking7025/sfbot-control --json assets -q '.assets[] | .name + " " + (.size|tostring) + " " + .digest'
   ```

3. **อัปเดต `update.json`** ใน repo `haremking7025/sfbot-control` (clone ไว้ที่ `/tmp/sfbot-control`):

   ```json
   {
     "version": "<ver>",
     "url": "https://github.com/haremking7025/sfbot-control/releases/download/v<ver>/SFKeyword_v<ver>.exe",
     "sha256": "<sha256 ของ EXE>",
     "size": <ขนาด EXE>,
     "notes": "สรุปสิ่งที่เปลี่ยนในเวอร์ชันนี้ (แสดงในหน้าต่างอัปเดต)"
   }
   ```

   > ⚠️ ชี้ไปที่ **EXE** ตรงๆ (sha256/size ต้องเป็นของ EXE ไม่ใช่ ZIP) —
   > ไม่ใช้ ZIP เป็น target อัปเดตแล้ว กัน updater ดาวน์โหลดผิดไฟล์

   ```bash
   cd /tmp/sfbot-control && git add update.json && git commit -m "Update v<ver> checksum" && git push origin main
   ```

4. **ตรวจดาวน์โหลดจริง** (sha + size ต้องตรง):

   ```python
   python -X utf8 -c "
   import urllib.request, json, hashlib
   j = json.load(urllib.request.urlopen('https://raw.githubusercontent.com/haremking7025/sfbot-control/main/update.json'))
   data = urllib.request.urlopen(urllib.request.Request(j['url'], headers={'User-Agent': 'Mozilla/5.0'})).read()
   print('MATCH', hashlib.sha256(data).hexdigest() == j['sha256'] and len(data) == j['size'])
   "
   ```

---

## การตรวจสอบว่า "กันโค้ดจริง"

- ใน `build_protected\sfkeyword_lib\` เหลือไฟล์ `.py` แค่ `__init__.py` เท่านั้น
  ที่เหลือเป็น `.pyd` (เช่น `app.cp312-win_amd64.pyd`)
- `.cython-cache\` (root โปรเจกต์) เก็บ .pyd แบบแคช — robocopy ยกเว้นไว้
  ไม่ถูกคัดลอกเข้า `build_protected\` จึงไม่รั่วเข้า EXE
- `build_protected\sfkeyword.pyw` ขึ้นต้นด้วย `# Pyarmor 8.5.12 ...` +
  `from pyarmor_runtime_000000 import __pyarmor__`
- PyInstaller analysis มี `pyarmor_runtime_000000` ใน TOC
  (`grep pyarmor build/SFKeyword/*/Analysis-00.toc`)
- เปิด EXE แล้วค้างค้างหน้าต่างได้ (ไม่ crash ทันที)

---

## ข้อควรรู้: PyArmor trial

- PyArmor ที่ติดตั้งผ่าน `requirements-build.txt` (`pyarmor>=8.5,<9`) เป็น
  **trial (evaluation)** — **ไม่มีวันหมดอายุ** แต่มีข้อจำกัด:
  - code object สูงสุด ~32 KB (ใช้ obfuscate แค่ `sfkeyword.pyw` ที่เล็กมาก จึงไม่กระทบ)
  - สคริปต์ที่ obfuscate ด้วย trial "ไม่ private" — ใครก็แกะกลับได้
  - **โค้ดจริงทั้งหมดถูก Cython คอมไพล์เป็น `.pyd` แล้ว** (native code) —
    ความเสี่ยงนี้จึงจำกัดอยู่ที่ entry point บางบรรทัด
- ถ้าต้องการระดับ private เต็มรูปแบบ ต้องซื้อ license PyArmor แล้วลงทะเบียน
  บนเครื่อง build ก่อน (`pyarmor register`)
