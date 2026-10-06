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
set SFKEYWORD_PROTECT=y
build_client.bat
```

- `SFKEYWORD_PROTECT=y` = ตอบ "y" ข้อ "Protect source with Cython + PyArmor?" อัตโนมัติ
- `SFKEYWORD_NO_PAUSE=y` = ข้ามทุก `pause` ท้ายสคริปต์ (ใช้ตอนรันอัตโนมัติ/headless กันค้าง)
- Cython compile แบบขนาน (`-j` ตามจำนวน CPU) + แคช `.pyd` ข้าม build
  (`.cython-cache\` ที่ root โปรเจกต์ — ห้ามลบ ไม่งั้นรอบหน้าต้อง compile ใหม่ทั้งหมด)
  → รอบแรก ~50 วิ รอบถัดไป (เนื้อหาไม่เปลี่ยน) เหลือ ~20-25 วิ
- ผลลัพธ์: `dist\SFKeyword\SFKeyword_v<เวอร์ชัน>.exe`
- บันทึก `docs/release_history.csv` **เฉพาะเมื่อยืนยันว่าเป็น release** — ตั้ง `SFKEYWORD_LOG_RELEASE=y`
  หรือตอบ "y" ข้อถาม "Release build - log this build to docs/release_history.csv?" (ค่าเริ่มต้น N = ไม่บันทึก)
- ถ้าเจอ MSVC ไม่ครบ สคริปต์จะถามให้ข้ามไป build แบบไม่กันโค้ดแทน
  (ตอบอัตโนมัติได้ด้วย env `SFKEYWORD_SKIP_PROTECT=y`)

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
0. รัน ruff (`python -m ruff check --no-respect-gitignore .`) ตรวจบั๊ก/เดดโค้ด
   เหมือนวิธีที่ 1 — เจอปัญหาหยุดทันที
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
จะรัน **`python -m ruff check --no-respect-gitignore .`** — เจอปัญหา หยุด build ทันที
โดยตั้งค่าใน
`pyproject.toml`:

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
    # กลุ่ม "ของล้าสมัย/เสี่ยงบั๊ก" ที่ไล่เก็บครบทั้งโปรเจกต์แล้ว
    "PIE790",   # pass ที่ไม่จำเป็น (มี docstring/คำสั่งอื่นเป็น body อยู่แล้ว)
    "PLW2901",  # ตัวแปรลูปถูกเขียนทับ
    "PLW3301",  # min()/max() ซ้อนกัน
    "RET504",   # ตั้งตัวแปรแล้ว return ทันที
    "UP024",    # IOError/… เป็น alias ของ OSError ตั้งแต่ Python 3.3
    "UP009",    # coding declaration ที่ไม่จำเป็น
]

# กฎที่ "ตรวจแล้วและตัดสินใจไม่แก้" — ระบุไว้เป็นลายลักษณ์อักษร (ดูเหตุผลในไฟล์)
ignore = ["PLW0603", "B904", "RUF022", "RUF023"]
```

> star imports (`import *`) ถูกลบออกจากโค้ดทั้งหมดและแปลงเป็น explicit imports แล้ว
> ถ้ามีใครเติม `import *` กลับมา `F403`/`F405` จะฟ้องให้ build หยุดทันที

> ⚠️ อย่ารัน ruff ด้วย `--select …` ทาง command line เพื่อตรวจแบบกว้าง — ruff จะ
> **ทับค่า `ignore` ใน `pyproject.toml`** กฎที่ตั้งใจยกเว้นจะกลับมาเตือน ทำให้เข้าใจผิด
> ว่าโค้ดยังไม่สะอาด (ให้ใช้ `ruff check --no-respect-gitignore .` ตามที่ gate ใช้)

ถัดจาก ruff driver จะรัน **`tools/build_tools/check_cython_safe.py`** อีกด่าน — สแกน
AST หา construct ที่ทำให้ Cython crash (เช่น `sorted(a or b)`) ก่อนเริ่มคอมไพล์
เพราะถ้าปล่อยไปเจอตอนคอมไพล์ จะเสียเวลา build ทั้งชุดกว่าจะรู้ตัว

> ตั้งใจไม่เปิด: `BLE001` broad except, `S110` try-except-pass, `I001` เรียง import,
> `E501` บรรทัดยาว — เป็นสไตล์ของโปรเจกต์ ไม่ใช่บั๊ก

### ด่านตรวจที่รันเองได้ (ไม่ผูกกับ driver — build จึงเร็วเท่าเดิม)

| คำสั่ง | ตรวจอะไร |
|---|---|
| `python -X utf8 tools/_deadcode_verify.py` | เดดโค้ด: ฟังก์ชัน/ค่าคงที่ที่ไม่มีใครเรียก |
| `python -X utf8 tools/_tamper_verify.py` | ชั้นกันการถูกแกะตอนรัน (19 เคส) |
| `python -X utf8 tools/_redact_verify.py` | ความลับไม่หลุดลง log — 6 รูปแบบ + ชุด generate + ยิงผ่าน `logging` จริง |
| `python -X utf8 tools/_buildhygiene_verify.py` | PATH ที่ใช้ build ถูกตัดแล้ว + บิลด์ไม่มี DLL ของโปรแกรมอื่นหลุดติด (H1–H5) |
| `python -X utf8 tools/_startupreg_verify.py` | ค่าเปิดพร้อม Windows ต้องชี้ `sfkeyword.pyw` ไม่ใช่สคริปต์ทดสอบใน tools\ (S1–S12) |
| `python -X utf8 tools/_leftover_verify.py` | ไม่มีของค้างจากรอบทดสอบ: Run/RunOnce · Startup · scheduled task · ไฟล์ชั่วคราว · โฟลเดอร์ %TEMP% ค้าง (B1–B6) |
| `python -X utf8 tools/_bootpopup_proof.py` | ไม่มีสภาพตัวติดตั้ง Python ค้างที่ทำป๊อปอัปเด้งตอนบูต + ค่าเปิดพร้อม Windows ชี้ไฟล์จริง (P1–P5) |

`_redact_verify.py` รายงานเวลาให้ด้วย: บรรทัด log ปกติ ~0.65 µs (เดิมต้องสแกน
ทุก pattern ทุกบรรทัด ~3.9 µs) เพราะมีด่านเร็วตัดจบบรรทัดที่ไม่มีคำต้องสงสัย
⇒ ปริมาณ log ไม่กระทบความลื่นของโปรแกรม

วัดเวลาเปิดโปรแกรม (ไม่ใช่ด่าน pass/fail — ใช้ดูผลของการปรับ):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/build_tools/measure_startup.ps1 `
    -Exe dist\SFKeyword\SFKeyword_v<ver>.exe -Runs 5
```

### เวลาเปิดโปรแกรม — วัดจริงแล้วปรับไปแล้ว

วัดจากสั่ง `Start-Process` จนหน้าต่างโผล่จริง (ผ่าน Win32 `EnumWindows` ไม่ใช่
`MainWindowTitle` เพราะ splash กับหน้าต่างหลักใช้ชื่อเดียวกัน ต้องแยกด้วยขนาด):

| build | แตกไฟล์ (child) | splash ขึ้น | หน้าต่างหลักพร้อมใช้ |
|---|---|---|---|
| onefile (ก่อนแก้) | 376 ms | 717 ms | **2,462 ms** |
| onefile (หลังแก้ splash) | 363 ms | 723 ms | **1,607 ms** |
| onedir (หลังแก้ splash) | — ไม่ต้องแตกไฟล์ | 319 ms | **1,108 ms** |

(median จาก 5 รัน — ค่าที่แกว่งมาจากด่านเช็คเน็ต/อัปเดตตอนเปิด ซึ่งบล็อกก่อนหน้าต่างหลัก)

**สิ่งที่แก้:** `_show_splash()` เดิมวน 40 เฟรม × `time.sleep(0.02)` = *หน่วงตายตัว
0.8 วิ* ก่อนไปเช็ค kill switch/อัปเดตและสร้าง Dashboard ⇒ เป็นเวลาที่ผู้ใช้รอเปล่า ๆ
ตอนนี้เปลี่ยนเป็นอนิเมชันแบบ `after()` ที่ไม่บล็อก ระหว่างที่
`check_on_startup_sync` วน `root.update()` รอเน็ตอยู่ callback จะได้ทำงานด้วย
⇒ เห็นแถบวิ่งจริงระหว่าง "รอของจริง" และไม่ต้องจ่าย 0.8 วิล่วงหน้า

**`--layout onedir`** (ตัวเลือกใหม่ของ driver) เร็วกว่าอีก ~500 ms เพราะไม่ต้อง
แตกไฟล์ทุกครั้งที่เปิด **แต่ยังไม่ตั้งเป็นค่าเริ่มต้น** — onedir แจกจ่ายเป็น
โฟลเดอร์/ZIP ไม่ใช่ EXE เดี่ยว ⇒ `update.json` ที่ชี้ไปที่ EXE ตรง ๆ และ
`apply_update.bat` เดิมใช้ไม่ได้ ต้องมีขั้นตอนติดตั้ง/แตกไฟล์ก่อน
(`--layout` แยก distpath ให้เองที่ `dist/SFKeyword_onedir/`)

> ⚠️ **ข้อที่วัดแล้วเจอ:** ถ้าเครื่องที่เปิดโปรแกรมมี **proxy/DNS ที่ไม่ตอบสนอง**
> (ไม่ใช่ "เน็ตล่มแบบปฏิเสธทันที") ด่านเช็ค kill switch/อัปเดตตอนเปิดจะรอจนครบ
> **เพดาน 10 วิ** ก่อนหน้าต่างหลักจะขึ้น (วัดได้ 9.7 วิ) — เป็นพฤติกรรมเดิมของ
> `check_on_startup_sync` (`_deadline = time.time() + 10.0`) ไม่ได้เกิดจากการ
> ปรับรอบนี้ การลดเพดานเป็นเรื่องตัดสินใจเชิงนโยบาย (ยอมข้ามการเช็คอัปเดตเร็วขึ้น)

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
- `build_protected\sfkeyword.pyw` ขึ้นต้นด้วย `# Pyarmor 9.x ...` +
  `from pyarmor_runtime_000000 import __pyarmor__`
- PyInstaller analysis มี `pyarmor_runtime_000000` ใน TOC
  (`grep pyarmor build/SFKeyword/*/Analysis-00.toc`)
- เปิด EXE แล้วค้างค้างหน้าต่างได้ (ไม่ crash ทันที)

---

### ตรวจ EXE จริงแบบอัตโนมัติหลัง build (smoke test)

`tools/build_tools/smoke_test_exe.ps1` เปิด EXE จริง (ไม่ใช่แค่ build ผ่าน) แล้วตรวจ
3 สถานการณ์ คืน exit code 0/1 ⇒ ใช้เป็น gate ได้ทั้ง x64 และ x86:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/build_tools/smoke_test_exe.ps1 `
    -Exe dist\SFKeyword\SFKeyword_v1.4.0.exe        # หรือ ..._x86.exe
```

| เคส | ต้องผ่าน |
|---|---|
| `1-clean` | หน้าต่างหลักขึ้น · **ไม่** เขียน log diagnostics |
| `2-inspect` (`PYTHONINSPECT=1`) | หน้าต่างหลักขึ้น · เขียน log ที่มีบรรทัด `TAMPER: … PYTHONINSPECT` |
| `3-inspect+enforce` (`PYTHONINSPECT=1` + `SFKEYWORD_TAMPER_ENFORCE=y`) | **ไม่** ขึ้นหน้าต่างหลัก · ขึ้นป๊อปอัปแทน |

> ไฟล์ `.ps1` มีข้อความไทย ⇒ ต้องบันทึกเป็น **UTF-8 with BOM** ไม่งั้น
> Windows PowerShell 5.1 จะอ่านเป็น ANSI แล้ว parse พลาด (ไฟล์นี้ใส่ BOM ไว้แล้ว)

## ชั้นกันการถูกแกะตอนรัน (tamper guard)

นอกจาก "ทำให้อ่านโค้ดยาก" (Cython + PyArmor) โปรแกรมยังตรวจ **สภาพแวดล้อมตอนเปิด**
ด้วย `sfkeyword_lib/core/tamper_guard.py` — เรียกครั้งเดียวจาก `sfkeyword.pyw`
ช่วงต้น `main()` **ก่อนสร้าง splash และหน้าต่างหลัก**:

| ชั้น | ตรวจอะไร |
|---|---|
| ระบบ | ดีบักเกอร์ต่อกับโปรเซส (`IsDebuggerPresent` / `CheckRemoteDebuggerPresent`) |
| Python | tracer/profile ที่เกาะอยู่ (`sys.gettrace()` · โมดูล `pydevd` `debugpy` `pdb`) |
| โปรเซสข้าง ๆ | ชื่อเครื่องมือวิเคราะห์ที่รู้จัก (x64dbg · IDA · Ghidra · Process Hacker · Cheat Engine · Frida · pyinstxtractor · uncompyle6 …) |
| ชุดไฟล์ | โฟลเดอร์ที่แตกออกมามี `sfkeyword_lib/*.py` ต้นฉบับโผล่ (ถูกแตก/ประกอบใหม่) |
| สภาพแวดล้อม | `PYTHONINSPECT` · `PYTHONSTARTUP` · `PYTHONBREAKPOINT` · `PYTHONDEBUG` |

**พฤติกรรม**

- พบสัญญาณ = จดลง `sfkeyword_diagnostics.log` ในโฟลเดอร์ข้อมูล + `logger.warning`
  **ครั้งเดียวต่อการรัน** และ **ไม่ปิดโปรแกรมเอง** (เจ้าของเครื่องยังดีบัก/ทดสอบงานได้)
- ต้องการให้หยุดทำงานจริงตอนปล่อย: ตั้ง `TAMPER_ENFORCE = True` ใน
  `sfkeyword_lib/core/constants.py` **ก่อน build** — ค่านี้ถูกคอมไพล์ติดไปกับ `.pyd`
  ⇒ ผู้ใช้ปลายทางแก้เองไม่ได้ (ต่างจากตัวแปรสภาพแวดล้อมที่ใครก็ตั้งได้)
- ยังสั่งเปิดชั่วคราวด้วย `SFKEYWORD_TAMPER_ENFORCE=y` ตอนรันได้ — แต่มีผลเฉพาะ
  บิลด์ที่ **ยังไม่ได้ฝังค่า** (ไว้ทดสอบ) และปิดไม่ได้เมื่อค่านี้เป็น `True`
- พบสัญญาณ + โหมดบังคับ ⇒ ขึ้นกล่อง "ตรวจพบการดัดแปลงโปรแกรม" แล้วปิดโปรแกรม
- ชั้นนี้ไม่แตะโปรเซส/ไฟล์อื่นเลย และ **ไม่มีผลข้างเคียงตอน import**

## ข้อกำหนดเครื่อง build ที่ต้องเพิ่ม

- ต้องมี **VC++ tools ของ Visual Studio** (`cl.exe` + Windows SDK) ไม่ใช่แค่ตัว IDE —
  เครื่องที่มี VS Community แต่ไม่ได้ติ๊ก workload "Desktop development with C++"
  จะ **ไม่มี `cl.exe`** ⇒ Cython compile ไม่ได้ ตรวจด้วย
  `vswhere -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64`
  (คืนค่าว่าง = ยังไม่ได้ติดตั้ง workload)
- PyArmor ต้องเป็น **9.x** (ตาม `requirements-build.txt`) — PyArmor 8.5 ปฏิเสธ
  Python 3.14 ด้วยข้อความ `"windows.x86_64" is still not supported`

## กับดักตอน build ที่เจอจริง (แก้ไว้แล้ว)

- **Cython 3.3 crash เมื่อ argument แรกของ `sorted()` เป็นนิพจน์ `a or b` ตรง ๆ**
  จะพังที่ `Optimize._handle_simple_function_sorted` ด้วย
  `AttributeError: 'NoneType' object has no attribute 'is_pylist_type'`
  แล้วทำให้ build หยุดทั้งรอบ (ไม่ใช่แค่โมดูลนั้น) — เลี่ยงโดยห่อด้วย `list(...)`
  หรือผูกค่าลงตัวแปรก่อน เช่น `sorted(list(a or b))` (โปรเจกต์นี้แก้ที่
  `sfkeyword_lib/engine/app_settings.py` แล้ว)
- **path ของไฟล์กลางยาวเกิน 260 ตัวอักษร → `link.exe` ล้มด้วย LNK1104**
  (`cannot open file ...lib`) เฉพาะโมดูลที่ชื่อยาว ๆ — `cythonize_lib.py` จึงส่ง
  **relative path** เป็น source ของ `Extension` (ไม่ใช่ absolute) เพราะ Cython +
  setuptools จะ mirror path ของ source ไว้ใต้ `_cybuild\c\` แล้ว build_ext
  mirror ต่อใต้ `_cybuild\temp\Release\` อีกชั้น ⇒ ถ้าเป็น absolute path ยาว ๆ
  (เช่น `C:\Users\...\build_protected\_cybuild\...`) พาธของ `.c`/`.obj`/`.lib`
  จะบวกกันจนเกิน 260 ตัวอักษร
  (สังเกตง่าย ๆ: โมดูลที่ชื่อสั้น compile ผ่าน แต่ที่ชื่อยาวล้ม)

- **ใช้ Python "embeddable" รันโปรแกรมได้ แต่ใช้ build ไม่ได้** — `python-<ver>-embed-win32.zip`
  ขาด 3 อย่างที่ขั้นตอน build ต้องใช้ ⇒ อาการที่เจอจริง:
  1. ไม่มี `Include\` + `libs\python<ver>.lib` ⇒ `cl.exe` ฟ้อง
     `fatal error C1083: Cannot open include file: 'Python.h'`
     (ข้อความของ `cythonize_lib.py` จะสรุปว่า "ปัญหาอยู่ที่ MSVC/SDK ไม่ใช่ตัวโค้ด"
     ซึ่งถูกในเชิง *แยกสาเหตุ* แต่รอบนี้สาเหตุจริงคือ header หาย ไม่ใช่ MSVC หาย)
  2. ไม่มี `tkinter\` + `_tkinter.pyd` + DLL ของ Tcl/Tk ⇒ ไม่มี `tkinter` ให้เก็บ
     ⇒ PyInstaller ขึ้น `ERROR: Hidden import 'tkinter' not found` และได้ EXE ที่เปิดไม่ขึ้น
     (hook `hook-_tkinter` จะ `SystemExit` ทันทีถ้าเก็บ Tcl/Tk data directory ไม่ได้)
  3. Tcl 9 ส่ง script library มาเป็น `libtcl9.0.<x>.zip` / `libtk9.0.<x>.zip` ยังไม่คลาย
     เป็นโฟลเดอร์ ⇒ ต้องคลายเป็น `tcl\tcl9.0` + `tcl\tk9.0` ก่อน PyInstaller จึงเก็บได้
     เป็น path ธรรมดา (ไม่ต้องพึ่ง zipfs ตอนรัน)
  ⇒ ใช้ **`tools/build_tools/prepare_x86_python.py`** ดึงครบทั้ง 3 จาก
  `pythonx86.<ver>.nupkg` (nuget) + `python-<ver>-32.exe` (python.org) แล้วตรวจปิดท้าย
  ด้วยการรัน `tkinter.Tcl()` จริง (ต้องมี 7-Zip ใน PATH; ใช้ `msiexec /a` ซึ่งเป็นแค่แตกไฟล์
  ไม่ได้ติดตั้งลงเครื่อง)

- **PATH ตอน build มีโฟลเดอร์ของโปรแกรมอื่น ⇒ PyInstaller ลอกสำเนา UCRT ติดไปกับบิลด์**
  PyInstaller หา DLL ที่โปรแกรมต้องใช้ผ่าน `PATH` — เครื่องนี้มี
  `C:\Program Files (x86)\Windows Kits\10\Windows Performance Toolkit` อยู่ใน PATH
  (โผล่หลังรีสตาร์ตเครื่อง) ซึ่งพ่วง `ucrtbase.dll` + `api-ms-win-*` มาเอง 41 ไฟล์
  ⇒ x64 onefile บวมขึ้น 895 KB (32.39 → 33.28 MB) และผล build ขึ้นกับ PATH ของเครื่องที่ build
  (พิสูจน์ด้วย sha256: ไฟล์ที่ติดไปตรงกับสำเนาในโฟลเดอร์นั้นเป๊ะ = `c04daeba…` · x86 ไม่โดน
  เพราะสำเนานั้นเป็น 64-bit) ⇒ driver รัน PyInstaller ด้วย PATH ที่ตัดเหลือเฉพาะ
  `venv\Scripts` + `System32` + `C:\Windows` (Windows 10+ มี UCRT เป็นส่วนของระบบอยู่แล้ว
  ไม่ต้องแพ็กไปด้วย) — ตรวจง่าย ๆ หลัง build: `dist\SFKeyword_onedir\<ver>\_internal\`
  ต้องไม่มี `ucrtbase.dll` · ด่านที่ล็อกไว้กันถอยหลัง: `tools/_buildhygiene_verify.py`
  (H1–H3 ตรวจฟังก์ชัน `pyinstaller_env()` กับขั้นรัน PyInstaller · H4 สแกน EXE/โฟลเดอร์
  ที่ build แล้ว · H5 ตัวควบคุมเชิงลบ)
- **ค่าเปิดพร้อม Windows ชี้สคริปต์ทดสอบ** — `_get_startup_command()` เดิมสร้างคำสั่งจาก `__main__.__file__` / `sys.argv[0]`
  ⇒ วันที่ 6 ต.ค. 2569 รันชุดด่านแล้วค่าใน `HKCU\...\Run` กลายเป็น `"...	ools\_tray_exit_harness.py" --tray` ⇒ เครื่องเปิดสคริปต์ทดสอบแทนโปรแกรมทุกครั้งที่บูต
  และค่าค้างจนกว่าจะกดสวิตช์ซ้ำ
  · แก้โดย `_app_entry_path()` หา `sfkeyword.pyw` จากโฟลเดอร์ของแพ็กเจ้าเอง (ไม่ใช่สคริปต์ที่ถูกเรียก) · หาไม่เจอ = `set_startup_enabled()` ไม่แตะ registry เลย
  · ด่านที่ล็อกไว้: `tools/_startupreg_verify.py` (S1–S12) · `tools/_leftover_verify.py` (B1–B6)

## รองรับวินโดวส์เวอร์ชัน/สถาปัตยกรรมไหน

บิลด์เป็น **PyInstaller onefile ที่ฝังตัวรัน Python 3.14** ⇒ พื้นขั้นต่ำของ
ระบบปฏิบัติการถูกกำหนดโดย »ตัวรัน« ไม่ใช่โดยโค้ดแอป (เขียนโค้ดดีแค่ไหนก็ไม่ช่วย
Windows 7) และแต่ละบิลด์โหลดได้เฉพาะ **สถาปัตยกรรมเดียวกัน**:

| บิลด์ | รันได้บน | ต้อง build ด้วย |
|---|---|---|
| `SFKeyword_v<ver>.exe` | Windows 10/11 64-bit | Python 3.14 x64 (ตัวหลัก) |
| `SFKeyword_v<ver>_x86.exe` | Windows 10/11 32-bit | Python 3.14 32-bit |
| `SFKeyword_v<ver>_arm64.exe` | Windows 11 on ARM | Python 3.14 ARM64 |

- **Windows 7 / 8.1 ใช้ไม่ได้** — Python 3.14 ไม่รองรับแล้ว การจะรองรับต้องถอย
  ทั้งโปรเจกต์ไป Python 3.8 (EOL แล้ว) ⇒ ไม่คุ้มกับความเสี่ยงด้านความปลอดภัย
- โปรแกรม **ไม่ปิดตัวเอง** เมื่อพบวินโดวส์รุ่นต่ำกว่า — `core/windows_compat.py`
  บันทึกเวอร์ชัน/สถาปัตยกรรมลง log แล้วขึ้นกล่องเตือน "ระบบปฏิบัติการที่อาจไม่รองรับ"
  ให้ผู้ใช้ตัดสินใจต่อ (ดูเหตุผลใน `sfkeyword.pyw`)
- ทุกจุดที่เรียก API วินโดวส์รุ่นใหม่ต้อง**ตรวจก่อนเรียก** ด้วย
  `windows_compat.api_available()` แล้วถอยไปใช้ค่าเริ่มต้นเสมอ
  (เช่น `GetDpiForWindow` = Win10 1607 · `psapi` · `SHGetKnownFolderPath`)

### build หลายสถาปัตยกรรม

ก่อน build x86 ต้องเตรียม interpreter 32-bit ให้ครบก่อน (ดูกับดักข้อ "embeddable ใช้ build ไม่ได้"):

```bat
python tools\build_tools\prepare_x86_python.py ^
    --nupkg <path>\pythonx86.3.14.7.nupkg ^
    --installer <path>\python-3.14.7-32.exe ^
    --target C:\py32emb
C:\py32emb\python.exe -m pip install -r tools\requirements.txt -r tools\requirements-build.txt
```

จากนั้น driver รับ `--python` (เลือก interpreter) และ `--arch` (แยกชื่อ EXE + workpath):

```bat
venv\Scripts\python.exe   tools\build_tools\build_protected_driver.py                                         :: x64
C:\py32emb\python.exe     tools\build_tools\build_protected_driver.py --arch x86 --python C:\py32emb\python.exe
```

แต่ละ interpreter ต้องมี Cython / PyInstaller / PyArmor / ruff ของตัวเอง และต้องมี MSVC
toolchain ของสถาปัตยกรรมนั้น — driver เลือก `bin\Hostx64\<target>` + `lib\<target>` +
SDK ให้เอง. `.cython-cache` แยกคีย์ตาม ABI (`cpython-314|win-amd64|64bit` กับ
`cpython-314|win32|32bit`) จึงไม่ชนกันข้ามสถาปัตยกรรม

**ARM64: ยัง build บนเครื่องนี้ไม่ได้** — ติด 3 ข้อพร้อมกัน
1. `pyarmor.cli.core` ไม่มี wheel `win_arm64` เผยแพร่เลย (มีแค่ `win_amd64` และ `win32`)
2. MSVC บนเครื่องนี้มี `bin\Hostx64\{x64,x86}` + `bin\HostArm64` แต่ **ไม่มี `bin\Hostx64\arm64`**
   ⇒ ต้องเพิ่ม workload `Microsoft.VisualStudio.Component.VC.Tools.ARM64`
3. Windows x64 รัน binary ARM64 เพื่อทดสอบไม่ได้ ⇒ ต้องมีเครื่อง ARM64 จริง

## ข้อควรรู้: PyArmor trial

- PyArmor ที่ติดตั้งผ่าน `requirements-build.txt` (`pyarmor>=9,<10`) เป็น
  **trial (evaluation)** — **ไม่มีวันหมดอายุ** แต่มีข้อจำกัด:
  - code object สูงสุด ~32 KB (ใช้ obfuscate แค่ `sfkeyword.pyw` ที่เล็กมาก จึงไม่กระทบ)
  - สคริปต์ที่ obfuscate ด้วย trial "ไม่ private" — ใครก็แกะกลับได้
  - **โค้ดจริงทั้งหมดถูก Cython คอมไพล์เป็น `.pyd` แล้ว** (native code) —
    ความเสี่ยงนี้จึงจำกัดอยู่ที่ entry point บางบรรทัด
- ถ้าต้องการระดับ private เต็มรูปแบบ ต้องซื้อ license PyArmor แล้วลงทะเบียน
  บนเครื่อง build ก่อน (`pyarmor register`)
