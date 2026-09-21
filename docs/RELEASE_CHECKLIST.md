# 📋 RELEASE CHECKLIST — ปล่อยเวอร์ชันใหม่ SFKeyword

ใช้ checklist นี้ทุกครั้งที่ปล่อยเวอร์ชันใหม่ ไล่ตามลำดับ **ห้ามข้ามขั้นตอน** ตัวที่ทำแล้วให้ติ๊ก ☐ → ☑ หรือลบออก

> ตัวอย่างในเอกสารนี้ใช้ **v1.2.2** — ให้แทนที่ด้วยเวอร์ชันจริงทุกจุด (ห้ามพลาดเพราะจุดนี้แหละที่ทำบ่อยที่สุด)

---

## 📦 สรุปชุด v1.3.47 (แนวปฏิบัติล่าสุด)

ชุดที่ปล่อยเป็น v1.3.47 มีงานเหล่านี้ (เป็นเกณฑ์มาตรฐานก่อนปล่อยเวอร์ชันถัดไป):

- 🔒 **ล็อกการเขียนประวัติรายไอดี (CSV)** — `_append_account_history` ครอบด้วย
  `_lock_stats` กันแถวปนกันตอน 50-200 ไอดีจบพร้อมกัน + กัน `_trim_account_history`
  (เขียนไฟล์ใหม่ทั้งไฟล์) ชน append กลางคัน — ประวัติไม่เสียหายแม้รัน concurrency สูง
- ⚡ **ยืนยันเส้นทางหลัก/รองเร็วสุด** — รับคีย์ (หน่วงคีย์=0, retry เฉพาะ error, cache หน้า
  Keyword), ฝาก/เบิก (op 5 ชิ้น/บัญชี + fetch หน้า parallel 5), รับไอเทมฟรี (ดึงคีย์ขนาน
  กับล็อกอิน), จุดรอง (ดึงคีย์วันนี้/webhook/updater) — ไม่มี sleep/retry ที่ไม่จำเป็น
- 🧵 **ตรวจ thread/timer ไม่มี leak** — after() ทุกตัวหยุดเอง/cancel ได้, worker ทั้งหมด
  daemon + ตรวจ `_stop_event`, เส้นปิดแอป = stop event + after_cancel + ล้าง session +
  `worker_manager.shutdown(wait=False)` + `root.destroy()` + `os._exit(0)`
- ✅ **Gates ก่อนปล่อย** — ruff ✓ / compileall ✓ / boot smoke headless (7 แท็บสร้าง +
  สลับครบ + กริดการ์ดตั้งค่าเสมอกัน) / **harness ทั้งชุด** (`tools/run_harness_suite.py`,
  ~150 วิ) / E2E ดาวน์โหลดจริง MATCH (size + sha)

---

## 0. ตรวจสภาพก่อนเริ่ม

- [ ] โปรเจกต์อยู่ในโฟลเดอร์ถูกต้อง (`sfkeyword.pyw` + `sfkeyword_lib\` อยู่ด้วยกัน)
- [ ] venv พร้อม (`venv\` มีอยู่ หรือ build จะสร้างให้เอง) — ถ้าสร้างใหม่ ให้ติดตั้ง
  dependencies ผ่าน manifest กลางที่ root (รวม runtime + build ทั้งหมด):

  ```bat
  venv\Scripts\python.exe -m pip install -r requirements.txt
  ```
- [ ] ติดต่อ GitHub ได้ (token อยู่ใน git credential manager — `git credential fill`
  ดึงได้; เครื่องนี้ไม่มี `gh` CLI ใช้ API script แทน ดูขั้นตอน 5)
- [ ] ไฟล์ source ผ่านชุดตรวจ (build จะรันให้อัตโนมัติ แต่ตรวจเองก่อนดีกว่า):

  ```bash
  venv/Scripts/python.exe -m compileall -q sfkeyword_lib sfkeyword.pyw
  venv/Scripts/ruff.exe check --no-respect-gitignore .        # ตรวจบั๊ก/เดดโค้ด (build รันให้อัตโนมัติ)
  ```

- [ ] **Harness ทั้งชุด** — build รันให้อัตโนมัติก่อน build จริง (แดงแม้ตัวเดียว = หยุด)
      แต่วิ่งเองก่อนก็ได้เพื่อดูผลไว ๆ:

  ```bash
  venv/Scripts/python.exe -X utf8 tools/run_harness_suite.py
  ```

  → ต้องขึ้น `HARNESS SUITE OK — เขียว N/N`

- [ ] **อ่านบรรทัดที่จะขึ้นจอ ก่อนกด build** — ตัวรันแห้งรัน **เส้นทางจริงทั้งสาม**
      (กรอกคีย์ · ฝาก/เบิก · รับไอเทมฟรี) โดยแทนแค่ชั้นเครือข่าย แล้วดัมป์
      "บรรทัดที่จะขึ้นจอ" ให้อ่านรวดเดียว ทั้งบรรทัด log และข้อความในกล่องแจ้งเตือน
      (`[popup]`) — ใช้เวลาราว 0.2 วิ และไม่ยิงเว็บ/ไม่แตะคุกกี้เลย:

  ```bash
  venv/Scripts/python.exe -X utf8 tools/log_preview.py                     # ทุกเส้นทาง ทุกฉาก
  venv/Scripts/python.exe -X utf8 tools/log_preview.py --route inventory   # เฉพาะฝาก/เบิก
  venv/Scripts/python.exe -X utf8 tools/log_preview.py --check             # ด่าน (มีในชุด harness)
  ```

  > อ่านแล้วเจอคำที่ยังงง/ยังเป็นศัพท์ระบบ = แก้ที่ถ้อยคำ **ก่อน** ปล่อย ไม่ใช่รอผู้ใช้ทัก

- [ ] **ทบทวนคำที่โปรแกรม "อ่านผลไม่ได้"** — ทุกครั้งที่อ่านคำตอบของเว็บไม่ได้ (คำไม่เข้าตาราง
      คำไหนเลย) โปรแกรมจดคำพูดของเว็บไว้ที่ `<โฟลเดอร์ข้อมูล>/unknown_web_messages.jsonl`
      ก่อนปล่อยให้เปิดรายงานดูว่ามีคำอะไรมาใหม่ แล้วเติมลงเกณฑ์ให้ตรงเส้นทาง:

      ```bash
      venv/Scripts/python.exe -X utf8 tools/unknown_messages_report.py        # สรุปจากไฟล์ปัจจุบัน
      venv/Scripts/python.exe -X utf8 tools/unknown_messages_report.py --all  # รวมไฟล์ที่หมุนไว้ด้วย
      venv/Scripts/python.exe -X utf8 tools/unknown_messages_report.py --logs # ขุดจากล็อกจริง
      ```

      > ที่เก็บกลางว่างได้ (โปรแกรมเพิ่งได้ความสามารถนี้ / ยังไม่มีรอบที่เจอคำแปลก)
      > — ใช้ `--logs` ขุด “คำพูดของเว็บ” จากล็อกจริงแทนได้ทันที (ยกคำพูดจาก
      > บรรทัดที่แอปอ้างเว็บมา) แล้วรายงานจะบอกว่าแต่ละคำเข้าเกณฑ์ของ
      > เส้นทางที่ถูกแล้วหรือยัง (คำที่ยังไม่รู้จักจะขึ้นด้วย ❗)
      > เติมคำแล้ว **ต้อง** รันชุดด่านต่อ: `SESSION_LOST_PATTERNS` + ป้ายกลาง
      > `SESSION_LOST_REASON` (`core/web_signals.py`) · `WEB_FAIL_REASONS` (`core/inventory_flow.py`) ·
      > `KEYWORD_ERROR_PATTERNS` (`core/http_flow.py`)
      > · ด่านที่ผูกกับเรื่องนี้: `tools/_unknownmsg_verify.py` · `tools/_realphrase_verify.py`
      >   (ล็อกคำจริงที่ขุดได้ไว้แล้ว: คำปฏิเสธคีย์ 94× · คำสั่งล็อกอิน 4× — ต้องเข้า
      >   เกณฑ์ของเส้นทางที่ถูกทุกคำ) (อยู่ในชุด harness — build รันเอง)
      > ไฟล์นี้ไม่มีรหัสผ่าน/คุกกี้ (ตัวจดปิดค่าลับก่อนเขียน) และเป็นไฟล์ในเครื่องเท่านั้น

- [ ] **ด่านล็อกรหัส** — `tools/_toollock_verify.py` (อยู่ในชุด harness ⇒ build รันเอง):
      ล็อกได้ **ทุกส่วนที่มีเมนู** (แดชบอร์ด · บัญชี · คีย์เวิร์ด · 3 แท็บเครื่องมือ · ตั้งค่า)
      ด้วย `รหัสล็อก` 4–32 ตัว เก็บเป็นค่าแปลงกลับไม่ได้ · เปิดใช้/ปิดใช้ · เลือกได้หลายส่วน
      และ "ล็อกเดี๋ยวนี้" ได้จากหน้าตั้งค่า · **เปลี่ยน/ปิด/ลบรหัสต้องยืนยันรหัสเดิม** ·
      **เพดานไอดีตั้งได้เอง** (ค่าเริ่มต้น 5 · เว้นว่าง = ไม่จำกัด · 0 = ทุกแถว)
      · **ตัวเลือกถามรหัสตั้งแต่เปิดโปรแกรม**

      > กติกาที่ด่านล็อกไว้: ประตูอยู่ที่ `_nav_switch` จุดเดียว · รายการที่ล็อกได้มาจาก
      > `core/tool_lock.LOCKABLE_MENU` (ลิสต์เดียวกับเมนู + แผงเลือกบนการ์ด) ·
      > เปิดโปรแกรมใหม่ = ล็อกเสมอ · ไม่มีรหัสจริงในโฟลเดอร์ข้อมูล (ด่านค้นทั้งโฟลเดอร์) ·
      > โปรเซสใหม่ยืนยันรหัสเดิมได้ · ใส่ผิดครบเพดานแล้วพักการลอง · ป้าย 🔒 ตรงสถานะจริง
      > · **รายการที่เลือก (`tools_lock_pages`)**: ไม่มีคีย์/ค่าเสีย = 3 แท็บเครื่องมือ ·
      >   ลิสต์ว่าง = ยังไม่ล็อกอะไร · ป้าย/สถานะ/ประตู อ่านรายการเดียวกันเสมอ (L13–L17)
      > · **เพดานไอดี (`tools_lock_cap`)**: ประตูเดียว `_tools_lock_allow_add_rows`
      >   คุมปุ่มเพิ่มแถว/โหลดไฟล์/สลับไฟล์ (L18–L21) · ค่าที่ตั้งต้องรอดข้ามโปรเซส (L29/L31)
      > · **เปลี่ยน/ปิด/ลบรหัส (`_tools_lock_guard_change`)**: รหัสเดิมผิด/ยกเลิก = ไม่สำเร็จ
      >   และสวิตช์บนจอกลับไปตรงสถานะจริง (L22–L27)
      > · **ถามรหัสตอนเปิดโปรแกรม** (`_tools_lock_startup_gate`): ยกเลิก = ยังล็อกอยู่และ
      >   โปรแกรมไม่ปิดตัวเอง (L30)
      > · เพิ่ม/ถอดเมนูต้องแก้ที่ `LOCKABLE_MENU` ที่เดียว แล้วรันชุดด่านนี้ซ้ำ

- [ ] **ด่านเปิด EXE จริง** — ยกขึ้นเป็นด่านอัตโนมัติแล้ว (`tools/_packaged_exe_verify.py`):
      เปิด EXE ที่ build แล้วจริง ซ่อนหน้าต่างทันที แล้วยืนยันว่าชื่อหน้าต่างตรงเวอร์ชัน +
      หน้าต่างอยู่ในพื้นที่ใช้งานของจอหลัก + ขนาดใช้งานจริง + เปิดมากลางจอ (ไม่กู้พิกัดเก่า)
      จับเคส **"แพ็กเกจผ่านแต่เปิดไม่ขึ้น"** ซึ่งด่าน sha/ขนาด จับไม่ได้เลย

      ```bash
      venv/Scripts/python.exe -X utf8 tools/_packaged_exe_verify.py            # ยอม SKIP ถ้ายังไม่ build
      venv/Scripts/python.exe -X utf8 tools/_packaged_exe_verify.py --require  # บังคับ (ใช้ตอนปล่อย)
      ```

      > ในชุด harness ตัวนี้จะ **SKIP อย่างชัดเจน** เมื่อยังไม่มี `dist\SFKeyword\SFKeyword_v<ver>.exe`
      > (build ล้าง dist ก่อนรัน suite) · และจะ **รันจริงเอง** ถ้ามี EXE ของเวอร์ชันนั้นอยู่
      > → ตัวรัน `tools/_single_screen_e2e.py` (อยู่ในรายการ NON_TESTS) เป็นผู้ทำงานจริง

      > ✅ **เปิดโปรแกรมค้างอยู่ก็รันด่านนี้ได้** (แก้ 18 ก.ย. 2569) — เทสต์ **ไม่แตะโปรแกรม
      > ของคุณเลย** ด้วยสองกลไก:
      > · กุญแจกันเปิดซ้อนของเทสต์เป็น *คนละดอก* เพราะเทสต์ใช้โฟลเดอร์ข้อมูลชั่วคราวของตัวเอง
      >   (`sfkeyword_lib/core/instance_lock.py` — ชื่อกุญแจคำนวณจากโฟลเดอร์ข้อมูล ส่วนโฟลเดอร์
      >   มาตรฐานยังได้ชื่อเดิมทุกไบต์ ⇒ รุ่นเก่า/ใหม่ที่ติดตั้งทับกันยังกันเปิดซ้อนได้เหมือนเดิม)
      > · ตัวรันเลือกหน้าต่างจาก **PID ในสายโปรเซสของตัวที่เทสต์เปิดเองเท่านั้น** ไม่ใช่แค่ชื่อเรื่อง
      >   ⇒ หน้าต่างของคุณไม่ถูกซ่อน/วัด แม้ชื่อเรื่องจะเหมือนกันเป๊ะ (ก่อนหน้านี้ต้องปิดโปรแกรมคุณ
      >   ก่อนทุกครั้ง เพราะชื่อเรื่อง+gุญแจชนกันทั้งคู่)
      >
      > ด่านกันถอยหลังของสองกลไกนี้: `tools/_instancelock_verify.py` (ยึดกุญแจจริงในโปรเซสลูก)
      > + `tools/_e2eguard_verify.py` (ตรรกะการตัดสิน) — ทั้งคู่อยู่ในชุด harness
      > (สวิตช์ `SFKEYWORD_E2E_KEEP_OPEN=1` ยังใช้ได้สำหรับกรณีที่รันแบบ **ไม่** แยกข้อมูล:
      > ตัวรันจะปฏิเสธจะรัน แทนที่จะไปแตะหน้าต่างของคุณ)
- [ ] **ด่านเอกสารตรงกับของจริง** — `tools/_doccmd_verify.py` (อยู่ในชุด harness ⇒ build รันเอง)
      ตรวจสองชั้น:
      · **ชั้นคำสั่ง** — อ่าน `docs/*.md` + `README.md` เทียบทุกคำสั่ง `tools/…py --flag`
        กับเครื่องมือจริง (flag อ่านจาก AST ทั้ง `add_argument` และแบบตรวจมือ `in sys.argv`)
      · **ชั้นสวิตช์** — สคริปต์ build ไม่มี argument เลย (ไม่มี `%~1`/`shift`) ผู้ใช้ป้อน
        ทุกอย่างผ่าน env ⇒ เทียบสวิตช์ที่เอกสารสั่งตั้งกับสวิตช์ที่ `build_client.bat`
        อ่านจริง: เอกสารสั่งตั้งตัวที่สคริปต์ไม่รับ = **B1** · สคริปต์รับแต่เอกสารไม่พูดถึง
        = **B2** · `set X=` ค่าว่าง (cmd ถือว่าไม่ตั้ง) = **B3** · ชื่อพิมพ์ปนตัวพิมพ์ = **B5**
        · ตัวแปรที่สคริปต์ตั้งเอง (เช่น `SFKEYWORD_VERSION`) ไม่ถูกนับเป็นสวิตช์ผู้ใช้

      ```bash
      venv/Scripts/python.exe -X utf8 tools/_doccmd_verify.py         # ด่าน (พร้อมตัวควบคุม 28 ข้อ)
      venv/Scripts/python.exe -X utf8 tools/_doccmd_verify.py --list  # ดัมป์คำสั่ง + สวิตช์ทั้งหมด
      ```

      > เกิดจากของจริง: เอกสารเคยสั่ง `tools/release_publish.py --selftest` ที่ **ไม่มี flag นี้**
      > และเคยเขียนชื่อสวิตช์ของ build ปนตัวพิมพ์เล็ก พร้อมไม่เคยพูดถึง
      > `SFKEYWORD_SKIP_PROTECT` เลย · ด่านอื่นจับไม่ได้เพราะตรวจแต่โค้ด/ไฟล์ไบนารี ไม่มีตัวไหน
      > อ่าน "คำสั่งที่เอกสารเขียน" · ชื่อไฟล์ตัวอย่างต้องประกาศใน `PLACEHOLDERS` และสวิตช์ที่
      > เป็นของเครื่องมืออื่นต้องระบุเจ้าของใน `OTHER_SWITCH_OWNERS` — ทั้งคู่มีด่านกันการยกเว้น
      > ที่เน่าค้าง (ของที่อ้างว่ายกเว้น ต้องยังมีอยู่จริง)
- [ ] **Boot smoke headless** (จำลองเปิดแอปจากซอร์ส — DATA_DIR ชี้ temp กันแตะ config จริง):
  สร้าง `App(root)` → สลับครบ 7 แท็บ (`run/accounts/keywords/autoitem/inventory/dailykey/settings`)
  → ทุกแท็บมี widget + ไม่มี exception → วัดกริดการ์ดตั้งค่า (การ์ดบน 2 ใบ y/size เท่ากัน)

---

## 1. อัปเดตเวอร์ชัน

- [ ] แก้ `VERSION` ใน `sfkeyword_lib/core/constants.py`:

  ```python
  VERSION = "1.2.2"   # ← เปลี่ยนเป็นเวอร์ชันใหม่ เช่น "1.3.0"
  ```

- [ ] รันชุดตรวจรอบสั้น (py_compile + ruff) ยืนยันเขียวก่อน build

---

## 2. Build EXE

- [ ] รัน build แบบ headless (แบบที่ทำจริง v1.3.44–1.3.47 — ข้าม pip + ไม่ถาม + ไม่เขียน CSV
  เอง กันค้างรอ stdin):

  ```bat
  rem สร้าง wrapper _run_build_<ver>.bat แล้วรัน detached:
  @echo off
  cd /d "%~dp0"
  set SFKEYWORD_NO_PAUSE=y
  set SFKEYWORD_SKIP_PIP=y
  set SFKEYWORD_LOG_RELEASE=n
  call "%~dp0build_client.bat"
  ```

  ```bash
  # Git Bash:
  (cmd //c ".\\_run_build_<ver>.bat" > _build_<ver>.log 2>&1 &)
  # poll log จนเจอ "Done! Files ready"
  ```

  > build จะล้าง artifacts รอบก่อนอัตโนมัติ (spec/exe/zip/workdir) + รัน ruff ตรวจบั๊ก/
  > เดดโค้ด (`python -m ruff check --no-respect-gitignore .`) + **harness ทั้งชุด**
  > (`python tools/run_harness_suite.py`) — ถ้าติดข้อใดให้แก้ก่อน ไม่งั้น build หยุดทันที
  > (errorlevel 1) · รันเดี่ยวตัวที่แดงได้:
  > `venv\Scripts\python.exe -X utf8 tools\<ชื่อไฟล์>.py`
  > ⚠️ **ปิดโปรแกรม SFKeyword ให้หมดก่อน build** — ถ้ามีตัวเก่าเปิดค้างอยู่ ไฟล์ EXE
  > จะถูกล็อก ลบ/เขียนทับไม่ได้; ด่านจะหยุดทันทีพร้อมป้าย `EXE_LOCKED` แทนที่จะปล่อย
  > "Done!" ปลอมที่แนบ SHA ของไฟล์เก่า (ดูโปรเซสค้าง: `tasklist | findstr /i SFKeyword`)
  > ใช้ build ไม่ป้องกัน (headless ตอบ n) — อยากป้องกันจริงตั้ง `SFKEYWORD_PROTECT=y`
  > หมายเหตุ: build ไม่ deterministic — SHA ของ build เทสรอบนั้นจะต่างจากตัวที่ปล่อยจริง
  > (timestamp ต่างกัน) ไม่ใช่ปัญหา

- [ ] ยืนยัน EXE เกิดที่: `dist\SFKeyword\SFKeyword_v1.2.2.exe`
- [ ] บันทึก release_history.csv: append แถวใหม่เองตอนปล่อยจริง
  (headless mode ตอบ `n` อัตโนมัติ → ต้องเติมแถวหลัง build เช่น
  `printf '1.3.47,SFKeyword_v1.3.47.exe,<SHA>,"Wed 09/09/2026 18:13:00"\r\n' >> docs/release_history.csv`
  — CSV เก็บเฉพาะเวอร์ชันที่ปล่อยจริง)

---

## 3. สร้าง ZIP

- [ ] สร้าง ZIP จาก EXE:

  ```powershell
  Compress-Archive -Path "dist\SFKeyword\SFKeyword_v1.2.2.exe" -DestinationPath "SFKeyword_v1.2.2.zip"
  ```

- [ ] ตรวจว่าใน ZIP มี **EXE ตัวเดียว** ไม่มี `.py`/`.pyc` รั่วออกมา:

  ```powershell
  tar -tf SFKeyword_v1.2.2.zip
  ```

---

## 4. คำนวณ SHA-256 + ขนาด (ของ EXE)

- [ ] คำนวณ sha256 (ตัวพิมพ์เล็ก) + ขนาดไฟล์ของ **EXE** (update.json ชี้ EXE ตรงๆ ไม่ใช่ ZIP):

  ```powershell
  (Get-FileHash .\dist\SFKeyword\SFKeyword_v1.2.2.exe -Algorithm SHA256).Hash.ToLower()
  (Get-Item .\dist\SFKeyword\SFKeyword_v1.2.2.exe).Length
  ```

- [ ] บันทึกค่าไว้ (ต้องใช้ 2 จุด: update.json + ตรวจอัปเดต)

---

## 5. ปล่อย GitHub Release

> เครื่องนี้ไม่มี `gh` CLI — ใช้ GitHub REST API ผ่านเครื่องมือถาวร `tools/release_publish.py`
> (token ดึงจาก `git credential fill`) ⇒ **ไม่ต้องเขียนสคริปต์ชั่วคราวรายรุ่นอีก**

- [ ] ปล่อยทั้งชุดในคำสั่งเดียว (release + อัปโหลด EXE/ZIP + `update.json` + CSV):

  ```bash
  venv/Scripts/python.exe tools/release_publish.py --summary "แก้บั๊กเปิดโปรแกรมไม่ขึ้น"                       # ดูเฉย ๆ ก่อน (ดีฟอลต์ ไม่ทำอะไร)
  venv/Scripts/python.exe tools/release_publish.py --apply --summary "แก้บั๊กเปิดโปรแกรมไม่ขึ้น" --detail "ลบโค้ดช่อง 'พร้อมกัน' ที่ไม่ใช้แล้ว"   # ปล่อยจริง
  venv/Scripts/python.exe tools/release_publish.py --apply --summary-file สรุป.txt                           # สรุปจากไฟล์ (บรรทัดแรก = หัวข้อ · บรรทัดขึ้นต้นด้วย - = ข้อ)
  venv/Scripts/python.exe tools/release_publish.py --selftest                                                # ตรวจตรรกะในเครื่อง (ไม่แตะเน็ต)
  ```

  - **`notes` (ข้อความที่ลูกค้าเห็นทุกคนในหน้าต่างอัปเดต) มาจาก `--summary`/`--detail`** —
    สคริปต์จัดรูปแบบให้เอง (บรรทัดแรก = หัวข้อ ที่เหลือเป็น `•` ข้อ) แล้ว **ตรวจก่อนใช้**:
    ห้ามคำอังกฤษปน (ยกเว้นคำเทคนิค/เลขรุ่น/ชื่อไฟล์) · ห้ามคำในคอลัมน์ "ห้ามใช้" ของ
    `docs/WORDING.md` · จับคำอังกฤษที่พิมพ์ผิดบ่อย · ห้ามบรรทัดซ้ำ · ไม่เกิน 20 บรรทัด
    (เท่าที่หน้าต่างอัปเดตแสดง) ⇒ **ไม่ผ่าน = ไม่ปล่อย**
    เกิดจากของจริง: notes v1.3.95 หลุดว่า `revive script bug` (ที่ต้องเป็น revert) และปนอังกฤษ
    ทั้งรุ่น ทั้งที่รุ่นก่อน ๆ เป็นไทย · ทางเดิม `--notes`/`--notes-file` ยังใช้ได้ แต่ต้องผ่าน
    กติกาเดียวกัน · ถ้าเป็นคำเทคนิคจริงที่ยังไม่มี ให้เพิ่มคำนั้นในคอลัมน์ "ใช้คำนี้" ของ
    `docs/WORDING.md` (กติกาจะรับทันที เพราะอ่านจากเอกสาร ไม่ก๊อปไว้ในโค้ด)

  - ตรวจไฟล์ EXE/ZIP + sha ก่อนแตะ GitHub · สร้าง release + อัปโหลด · ยืนยันด้วย digest ที่ GitHub
    รายงาน + ดาวน์โหลดจริงมาเทียบ sha · เขียน `update.json` และ append CSV ให้เอง · รันซ้ำได้ไม่พัง
  - **ขั้น 1 ของ `--apply` = ด่านกันพลาดก่อนปล่อย 4 ข้อ** (ถอยรุ่นไม่ได้แล้ว ⇒ ห้ามข้าม):
    ① รุ่นที่จะปล่อยต้องไม่ต่ำกว่ารุ่นล่าสุดในประวัติ ② สวิตช์ปิดปรับปรุงต้องปิดอยู่
    (เปิดอยู่ = เครื่องลูกค้าปิดตัวเองก่อนถึงขั้นตรวจอัปเดต ⇒ ปล่อยไปก็ไม่มีใครได้)
    ③ **ชุดด่านทั้งหมด** (`tools/run_harness_suite.py`) ④ EXE ที่ build เปิดขึ้นจริง
    (`_packaged_exe_verify.py --require`) — ข้อใดไม่ผ่าน = **หยุดก่อนอัปโหลด** · ไม่แตะ GitHub
    เลย ⇒ ของที่พัง/เปิดไม่ขึ้น/รุ่นถอยหลัง ไม่มีทางขึ้น GitHub
  - ⚙ ข้ามได้เฉพาะ ③/④ (`--skip-suite` · `--skip-exe-open`) และ **เฉพาะเมื่อมีหลักฐานจริง**
    ของรุ่น/ไฟล์นั้นที่ยังสด (ไม่เกิน 6 ชม. · ไฟล์หลักฐานอยู่ใต้ `tools/`): รันรอบจริงผ่าน
    จึงเกิดหลักฐาน · EXE ถูก build ใหม่ (sha เปลี่ยน) = ต้องเปิดตรวจใหม่ — ไม่มีธง "ข้ามด่านทั้งหมด"
    · กรณีฉุกเฉินที่ต้องปล่อยขณะปิดปรับปรุงอยู่ ต้องพิมพ์ `--allow-maintenance` เองเท่านั้น
    (ด่าน ①② ไม่มี flag ข้าม)
  - หลังปล่อยแล้วรันด่านไขว้: `tools/_release_consistency_verify.py --strict-net --deep`

  > ⚠️ tag ต้องตรงกับ `url` ใน update.json ทุกจุด (เครื่องมือเขียนให้เอง ถ้าทำมือต้องเช็ค)

- [ ] ยืนยัน asset อัปโหลดครบ (EXE + ZIP) + digest ตรงเครื่อง

- [ ] วิธีทำมือ (เก็บไว้อ้างกลไก — ไม่ต้องใช้แล้ว): `POST /repos/haremking7025/sfbot-control/releases`
      (tag_name/name/body = สรุปที่เปลี่ยน) แล้ว `POST /uploads.github.com/.../assets?name=...` (201 ทั้งคู่)

- [ ] ถ้ามี `gh` CLI ใช้วิธีเดิมได้:

  ```bash
  gh release create v1.2.2 dist/SFKeyword/SFKeyword_v1.2.2.exe dist/SFKeyword/SFKeyword_v1.2.2.zip \
    --repo haremking7025/sfbot-control --title "SFKeyword v1.2.2" --notes "📝 สรุปสิ่งที่เปลี่ยนในเวอร์ชันนี้"
  ```

---

## 6. อัปเดต `update.json` + `docs/release_history.csv` (repo sfbot-control)

> ใช้ `tools/release_publish.py` (ขั้นตอน 5) = จบทั้งสองไฟล์ในคำสั่งเดียว · หัวข้อนี้เก็บไว้เป็น
> ข้อมูลอ้างอิง schema และวิธีทำมือ

- [ ] `docs/release_history.csv` — คอลัมน์คงที่ 7 ตัว (BOM + LF เสมอ):
      `version,exe_name,sha256,build_datetime,zip_name,zip_sha256,zip_size`
  - `build_datetime` = **เวลาสร้างจริงจาก build** (มีคำพูดครอบเพราะมีช่องว่าง) — อย่าเปลี่ยนเป็นวันปล่อย
  - `sha256` / `zip_sha256` = digest ของ asset จริงบน GitHub (hex 64 ตัว พิมพ์ใหญ่) · `zip_size` = ไบต์
  - ตรวจ/ซ่อมให้ตรงกับ release จริงได้เอง: `tools/_release_consistency_verify.py --fix --apply --yes`

- [ ] clone/pull repo ควบคุม:

  ```bash
  cd /tmp/sfbot-control && git pull --ff-only
  ```

- [ ] แก้ `update.json` เป็น schema ใหม่:

  ```json
  {
    "version": "1.2.2",
    "url": "https://github.com/haremking7025/sfbot-control/releases/download/v1.2.2/SFKeyword_v1.2.2.exe",
    "sha256": "8feaf14f55e96320a08f3c793b92c4a8c1c86a260f299ffbcf48ac5056728664",
    "size": 28965123,
    "notes": "สรุปสิ่งที่เปลี่ยนในเวอร์ชันนี้ (แสดงในหน้าต่างอัปเดต)"
  }
  ```

  | ฟิลด์ | แหล่งค่า |
  |---|---|
  | `version` | VERSION ใน constants.py |
  | `url` | release download URL ของ **EXE** (ไม่ใช่ ZIP) |
  | `sha256` | จากขั้นตอน 4 (sha ของ EXE, hex 64 ตัว พิมพ์ใหญ่) |
  | `size` | จากขั้นตอน 4 (bytes ของ EXE) |
  | `notes` | สรุปสิ่งที่เปลี่ยน (ไทยล้วน) — updater เอาไปแสดงในหน้าต่างอัปเดต · `tools/release_publish.py` สร้างให้เองจาก `--summary`/`--detail` พร้อมตรวจถ้อยคำ (ดูขั้นตอน 5) |

  > ⚠️ update.json ต้องชี้ไปที่ **EXE** ตรงๆ (sha/size ของ EXE) —
  > ไม่ใช้ ZIP เป็น target อัปเดตแล้ว กัน updater ดาวน์โหลดผิดไฟล์

- [ ] commit + push:

  ```bash
  git add update.json && git commit -m "Update v1.2.2 checksum" && git push origin main
  ```

> ⚠️ **ห้าม commit ไฟล์ ZIP/EXE ลงใน repo** — .gitignore กันไว้แล้ว แนบเป็น release asset เท่านั้น

> 🔒 **แนวปฏิบัติถาวร (v1.3.50+):** แอปอ่าน `update.json` + `kill_switch.json` แบบ **raw-first**
> — เรียก `raw.githubusercontent.com` ก่อน (ไม่มี rate limit) แล้วค่อย fallback ไป
> GitHub Contents API เผื่อ raw ล่ม **ห้ามสลับกลับเป็น API-first**: Contents API แบบไม่ login
> จำกัด 60 req/hr/IP (IP ร่วมของ NAT เบิร์นหมดเร็ว) และ api.github.com contents ก็แคช CDN จริง
> (ไม่ได้ "เห็นใหม่ทันที" ตามที่เคยเข้าใจ) — raw จึงทั้งไม่จำกัดและสดพอใช้ (อัปเดตโค้ดใน
> `sfkeyword_lib/core/updater.py`: `_fetch_update_json` + `check_kill_switch`)

---

## 7. ทดสอบอัปเดตจริง (สำคัญที่สุด)

- [ ] ดาวน์โหลดจาก URL ใน update.json แล้วเทียบ sha256/size กับที่บันทึก:

  ```python
  import json, hashlib, urllib.request
  u = json.load(open(r"C:\Users\<ชื่อผู้ใช้>\Desktop\<โฟลเดอร์โปรเจกต์>\update.json"))  # หรืออ่านจาก GitHub
  # ดาวน์โหลด u["url"] → hashlib.sha256(ไฟล์).hexdigest() == u["sha256"] และ os.path.getsize == u["size"]
  ```

  → ต้องได้ **MATCH** (sha + size ตรงเป๊ะ) ไม่งั้นผู้ใช้อัปเดตไม่ได้

- [ ] เปิดแอปเวอร์ชันเก่า (เช่น v1.2.1) → กดอัปเดต → ดาวน์โหลด EXE → รีสตาร์ทเป็นเวอร์ชันใหม่
- [ ] หลังอัปเดต: ไอคอน/โลโก้ยังคม ไม่เบลอ + แอปเปิดปกติ

---

## 8. ล้างของเก่า (แล้วแต่)

- [ ] **สำรอง asset ก่อนลบ (บังคับ)** — ลบ release/tag บน GitHub กู้คืนไม่ได้ ถ้าไม่สำรอง
      แล้ว asset หาย = ลูกค้าที่ค้างเวอร์ชันเก่าจะอัปเดตไม่ได้ · ใช้สคริปต์ถาวร
      `tools/prune_releases.py` ที่ **ดาวน์โหลด → ตรวจ sha256 + ขนาด → ค่อยลบ** และ
      **ไม่ลบอะไรเลยถ้ามีไฟล์เดียวที่ไม่ผ่าน**:

  ```bash
  venv/Scripts/python.exe tools/prune_releases.py                    # ดูเฉย ๆ ก่อน (ดีฟอลต์ ไม่ลบ)
  venv/Scripts/python.exe tools/prune_releases.py --apply            # ลบจริงหลังสำรอง+ตรวจผ่านครบ
  venv/Scripts/python.exe tools/prune_releases.py --keep-last 2      # เก็บ 2 ตัวใหม่สุด (นโยบายปกติ)
  venv/Scripts/python.exe tools/prune_releases.py --keep v1.2.2      # ระบุ tag เอง (ระบุซ้ำ/คั่นจุลภาคได้)
  venv/Scripts/python.exe tools/prune_releases.py --selftest         # ตรวจตรรกะในเครื่อง (ไม่แตะเน็ต)
  ```

  → สำรองลง `C:\tmp\gh_release_backup\<tag>\` พร้อม `manifest.json` (เก็บ tag · วันที่ปล่อย ·
  release notes เดิม · url เดิม ไว้กู้คืน) · token ดึงจาก `git credential fill` (ไม่ฝังในไฟล์) ·
  ลบ release ด้วย id ก่อนแล้วค่อยลบ tag · **exit 1 = มีอะไรไม่ผ่าน → ไม่ลบอะไรเลย**
  · `tools/` อยู่ใน .gitignore ⇒ สคริปต์นี้อยู่เฉพาะเครื่องนี้ ไม่ขึ้น repo (คู่กับ harness อื่น ๆ)
  — อย่าลบไฟล์นี้ทิ้ง

- [ ] **ทางกลับ ถ้าต้องติดตั้ง release เก่าคืน** (เช่นลูกค้ารายงานว่าเวอร์ชันใหม่มีปัญหา) —
      ใช้สคริปต์ถาวร `tools/restore_release.py` ที่ **ตรวจ sha กับ `manifest.json` ก่อน**
      แตะ GitHub เสมอ และไม่เชื่อรหัส HTTP เพียงอย่างเดียว (ตรวจ digest จริงซ้ำอีกรอบ):

  ```bash
  venv/Scripts/python.exe tools/restore_release.py --list                  # มีอะไรสำรองไว้ + อยู่บน GitHub ไหม
  venv/Scripts/python.exe tools/restore_release.py --tag v1.2.2             # ดูเฉย ๆ ก่อน (ดีฟอลต์ ไม่ทำอะไร)
  venv/Scripts/python.exe tools/restore_release.py --tag v1.2.2 --apply     # ติดตั้งกลับจริง
  venv/Scripts/python.exe tools/restore_release.py --tag v1.2.2 --apply --force   # แทนที่ asset เดิมที่ไม่ตรง
  venv/Scripts/python.exe tools/restore_release.py --rehearsal              # ซ้อมจริงด้วย release ชั่วคราว (ลบเอง)
  venv/Scripts/python.exe tools/restore_release.py --selftest               # ตรวจตรรกะในเครื่อง (ไม่แตะเน็ต)
  ```

  → กฎความปลอดภัย: **ไม่มี sha ใน manifest = พิสูจน์ไม่ได้ = ไม่ติดตั้ง** · ไฟล์ในเครื่อง
  ต้องมีอยู่ ไม่ว่าง ขนาดตรง sha ตรง **ครบทุกไฟล์** จึงเริ่มแตะ GitHub · release ที่มีอยู่
  ตรงกับ manifest อยู่แล้ว = ไม่ทำอะไรซ้ำ (รันคำสั่งเดิมได้เรื่อย ๆ) · มีอยู่แต่ไม่ตรง = หยุด
  บอกให้ใส่ `--force` เอง · หลังอัปโหลดจะยืนยันด้วย digest ที่ GitHub รายงาน + ดาวน์โหลดจริง
  มาเทียบ sha อีกชั้น · `--rehearsal` ซ้อมทั้งเส้น (สร้าง→อัปโหลด→ตรวจ→ลบ) ด้วย tag ชั่วคราว
  `v0.0.0-restore-test` แล้วลบทิ้งให้เอง เหลือแต่ release จริงบน GitHub
  (หมายเหตุ: GitHub ตั้ง `published_at` ใหม่เอง — วันปล่อยเดิมกู้คืนไม่ได้)

  > ⚠️ ตัวอัปเดตในแอปเสนอเฉพาะรุ่นที่ **ใหม่กว่า** (`updater._is_newer`) ⇒ แค่ชี้ `update.json`
  > ไปรุ่นเก้า **ไม่มีอะไรเกิดขึ้นกับลูกค้า** · แอปเก็บ EXE ตัวเดิมไว้เป็น `.exe.old`
  > ในเครื่องลูกค้า (ตัวกันอัปเดตพังเท่านั้น — ไม่ใช่ทางย้อนเวอร์ชัน)

- [ ] **บทเรียนการเก็บของเก่า: ZIP คือหลักฐานที่เชื่อถือได้ ไม่ใช่ `dist\*.exe`**
      → ตอนนำเข้ารุ่นยุค SFBOT (1.2.8/1.3.0/1.3.1) เข้าคลัง เจอว่า `dist\SFBOT_v1.2.8.exe`
      ถูก **build ทับใหม่ทีหลัง** (1 ก.ย. → 2 ก.ย.) ⇒ sha ไม่ตรงกับประวัติปล่อยเดิม
        แต่ `SFBOT_v1.2.8.zip` ยังเป็นไบต์วันปล่อย ⇒ แกะ exe ข้างในได้ sha ตรงประวัติเป๊ะ
      ⇒ เก็บ ZIP ไว้ทุกครั้ง · ติ่งชื่อ asset ใหม่ได้โดยไม่เปลี่ยนไบต์ (sha เดิม)

- [ ] **นโยบายล็อกจากศูนย์กลาง** — `lock_policy.json` ที่ root (ด่าน `tools/_lockpolicy_verify.py`):
      เครื่องลูกค้าดึงทุกครั้งที่เปิดโปรแกรมแล้วทับค่าล็อกของเครื่อง ⇒ ล็อก/ถอน/เปลี่ยนรหัส
      จาก repo ทีเดียวถึงทุกเครื่อง

  ```bash
  # เปิดล็อกทุกเครื่อง (แก้ไฟล์ → push) · ก่อนเปิดควรมีรหัสจริงทดสอบแล้ว 1 เครื่อง
  #   "active": true, "pages": ["accounts", "settings", "startup"], "code": "sha256$…"
  # ปิดทั้งฐานทันที
  #   "active": false   → ทุกเครื่องกลับมาใช้ค่าของตัวเองรอบเปิดโปรแกรมถัดไป
  venv/Scripts/python.exe -X utf8 tools/_lockpolicy_verify.py   # ด่านกันพลาดของกลไกนี้ (อยู่ในชุด harness)
  ```

      > กติกาที่ห้ามหลุด: `active` เท่านั้นที่มีผล · "ไม่ระบุ" ≠ "ระบุเป็นค่าว่าง" (`pages: []` = ไม่ล็อกอะไร
      > · `cap: null` = ไม่จำกัด) · รหัสในรับเป็นค่าแปลงกลับไม่ได้เท่านั้น · `devices["<รหัสเครื่อง>"]`
      > ชนะค่ารวมและสืบทอดค่ากลาง · **ดึงไม่ได้ = คงนโยบายเดิม (ไม่ปลดล็อกให้เอง)** · นโยบาย active
      > = เครื่องลูกค้าแก้เองไม่ได้ ⇒ ถ้าล็อกผิดให้แก้ `active: false` แล้ว push
      > · ⚠ รหัสเครื่อง = MachineGuid (โปรแกรมโชว์ในหน้าตั้งค่า) — เครื่องโคลน/ก็อปวินโดวส์มา
      > อาจได้รหัสเดียวกัน ให้ตรวจก่อนใส่ `devices` รายเครื่อง

- [ ] **ทิศทางการอัปเดต = ขึ้นรุ่นใหม่เท่านั้น (ไม่มีทางย้อนในโปรแกรม)** — ถอดปุ่ม/หน้าต่าง
      "ย้อนกลับเวอร์ชัน", สคริปต์ถอยรุ่นของเรา และตัวกันอัปเดตของรุ่นที่ถอยหนี (`rollback_pin`)
      ออกหมด 21 ก.ย. 2569 ตามคำสั่ง *"ลบฟีเจอร์ย้อนเวอร์ชั่นทั้งหมด"*
      ⇒ ⚠ **ห้ามปล่อยรุ่นที่เปิดไม่ขึ้น/พังงานหลัก** เพราะไม่มีทางถอยทั้งฐานอีก
      วิธีกันคือ: รันด่านทั้งหมด + เปิด EXE ที่ build แล้วจริง (ด้านบน) ก่อนปล่อยทุกครั้ง
      · `force_update: true` ยังใช้บังคับ **ขึ้นรุ่นใหม่** ได้ตามปกติ (ตรวจครั้งเดียวตอนเปิดโปรแกรม)
      → ตรวจเร็ว: `tools/_updateflow_verify.py` (V1 ไม่เหลือร่องรอยระบบที่ถอดออก ·
      V6–V8 ตรวจไฟล์/ความเร็ว/ลำดับ sha) และ `tools/_release_consistency_verify.py`

- [ ] **สำรองรุ่นที่ยังอยู่บน GitHub ลงเครื่อง (ไม่ลบอะไร)** — ปกติตัวสำรองเกิดตอน prune เท่านั้น
      ⇒ รุ่นที่ยังไม่ถูกลบ (เช่นรุ่นที่เพิ่งปล่อย) **จะไม่มีสำเนาในเครื่องเลย** ถ้า release หายไป
      จะกู้ไม่ได้ · โหมดนี้สำรองเพิ่มเฉพาะตัวที่ยังไม่มี/สำเนาไม่ตรง (รันซ้ำได้ ไม่โหลดซ้ำ):

  ```bash
  venv/Scripts/python.exe tools/prune_releases.py --backup-only              # ดูว่าจะสำรองอะไร
  venv/Scripts/python.exe tools/prune_releases.py --backup-only --apply      # สำรองจริง (ไม่ลบ)
  venv/Scripts/python.exe tools/prune_releases.py --backup-only --tags v1.3.85 --apply   # เจาะจงรุ่น
  venv/Scripts/python.exe tools/restore_release.py --list                    # ดูคลังที่สำรองไว้
  ```

  → ตรวจ sha ทุกไฟล์ตอนสำรอง · ไฟล์ที่ "หายไปจากเครื่อง" ภายหลังจะถูกสำรองใหม่รอบถัดไป
  · ด่านคุม: `tools/_release_consistency_verify.py` B1–B4 (พร้อม selftest P17–P22 ของเครื่องมือ)

  > **นโยบายเก็บของ (ตัดสิน 13 ก.ย. 2569): เก็บตัวล่าสุด + ตัวก่อนหน้าไว้เป็นทางถอย**
  > ⇒ ใช้ `--keep-last 2` เป็นค่าปกติ **อย่าใช้ค่าดีฟอลต์ (เก็บตัวเดียว)** เพราะจะลบตัวก่อนหน้า
  > ทิ้งทันทีที่ปล่อยรอบใหม่ — ซึ่งเป็นตัวที่ต้องใช้เวลาลูกค้ารายงานว่าเวอร์ชันใหม่มีปัญหา
  > (ตัวที่ยังอยู่บน GitHub ติดตั้งเองได้ทันทีโดยไม่ต้องพึ่งสำรองในเครื่อง)

- [ ] ตรวจผลหลังลบ: คำสั่ง `--apply` จะพิมพ์ release ที่เหลือบน GitHub ให้ดูก่อนจบ
      → ต้องเหลืออย่างน้อย 2 ตัว (ล่าสุด + ตัวก่อนหน้า) และอัปเดต `docs/release_history.csv`
      ให้ตรงกับที่เหลือจริง (ข้อถัดไป) · ด่าน `_release_consistency_verify.py` บังคับว่าทุกแถว
      ต้องมี release และทุก release ต้องมีแถว

- [ ] ลบ EXE/ZIP เก่าในโปรเจกต์ + build artifacts (`build\` `build_protected\`) ไหม?
  > ⚠️ **ห้ามลบ `.cython-cache\`** — เป็นแคช .pyd ที่ทำให้ build รอบหน้าวิ่งแบบ cache hit
  > (ลบแล้วรอบหน้าต้อง compile ทั้ง 43 โมดูลใหม่ ~50 วิ)
- [ ] อัปเดต `docs/release_history.csv` ให้ตรง release จริง (ถ้าลบ release เก่า ให้ลบแถวด้วย)
  — ตั้งแต่ build ใหม่ ระบบถามยืนยันก่อนเขียน CSV (`SFKEYWORD_LOG_RELEASE=y`) จึงควรมีเฉพาะ
  เวอร์ชันที่ปล่อยจริงอยู่แล้ว
- [ ] **ด่านบังคับอัตโนมัติ** `tools/_release_consistency_verify.py` (อยู่ในชุด harness ⇒ build
      รันให้ก่อน build เสมอ) ตรวจสามที่ให้ตรงกัน: GitHub releases/tags ↔ `docs/release_history.csv`
      ↔ `update.json` — **ไม่ตรงแล้ว build หยุดทันที** กันเคสที่ลูกค้าเจอ "กดอัปเดตแล้วพัง"

> ⚠️ ก่อนปล่อยทุกครั้ง ให้เช็คว่า **"งานไม่จบ = ห้ามบอกว่าจบ"** ยังจริงอยู่
> (นโยบาย + ตารางจุดที่เคยพลาดอยู่ใน `docs/WORDING.md` หัวข้อ *งานยังไม่จบ = ห้ามบอกว่าจบ*)
> ด่านที่คุมเรื่องนี้: `tools/_stuckround_verify.py` (อยู่ในชุด harness ⇒ build รันให้ก่อน build)
> — ครอบ "รอเธรดแบบมีเพดานแล้วสรุปทันที" ทั้ง 4 จุด: ด่านรอ worker เดิม · รอบไอเทมฟรี ·
> ปุ่มปิดเซสชันรายแถว · จุดที่เริ่มงานไม่ได้ (ปุ่มค้าง "กำลัง…")

> ⚠️ ก่อนปล่อยทุกครั้ง ให้เช็คว่า **"บัญชีไอเทมหลักล้านชิ้นยังทำจบ"** ยังจริงอยู่
> ด่านที่คุม: `tools/_bigscale_verify.py` (อยู่ในชุด harness ⇒ build รันก่อน build)
> — งานที่ค้างในคิวมีเพดาน (workers × 4) · ตัวดึงหน้าไม่ถือรายการทั้งชุด · หน้าต่าง
> ดู/เลือกไอเทมจำผลคำนวณและแสดงไม่เกิน 2,000 แถว (พร้อมบอกผู้ใช้ว่ายังมีมากกว่านั้น)

  ```bash
  venv/Scripts/python.exe tools/_release_consistency_verify.py            # รันมือ (เร็ว)
  venv/Scripts/python.exe tools/_release_consistency_verify.py --deep     # ดาวน์โหลด EXE จริงมาเทียบ sha
  venv/Scripts/python.exe tools/_release_consistency_verify.py --strict-net  # เน็ตใช้ไม่ได้ = ไม่ผ่าน
  ```

  → จับอะไรบ้าง: แถว CSV ที่ไม่มี release (แถวผี) · release ที่ยังไม่มีแถว CSV · tag กำพร้า ·
  digest ของ asset ไม่ตรงกับ CSV · `update.json` ชี้ release/asset ที่ไม่มีหรือ sha/ขนาดไม่ตรง ·
  ชื่อไฟล์ใน url ไม่ตรงรุ่น · CSV ผิดรูปแบบ — และมีตัวควบคุมพิสูจน์ว่าจับของผิดได้จริงทุกกติกา
  · เน็ตใช้ไม่ได้ = เตือนแล้วผ่านไป (ไม่บล็อก build) เว้นแต่ใส่ `--strict-net`
  · รุ่นที่กำลังปล่อย (`VERSION` ในซอร์ส) ยังไม่มีแถว CSV ได้ = ช่วงกลางการปล่อย
  · เจอแบบ "ลบ release แล้วลืมลบแถว CSV" ⇒ แก้ CSV หรือใช้ `tools/prune_releases.py`
  (ไฟล์อยู่ใน `tools/` ซึ่ง gitignore ⇒ อยู่เฉพาะเครื่องนี้ อย่าลบ)

---

## 🔁 สรุป flow คร่าวๆ

```
constants.py (VERSION) → gates (ruff + compile + boot smoke 7 แท็บ + harness ทั้งชุด)
    → build_client.bat headless (EXE) → zip → sha256/size
    → tools/release_publish.py --apply (API: create release + upload EXE/ZIP + update.json + CSV)
    → commit + push docs/release_history.csv
    → E2E ดาวน์โหลดจริง MATCH (size + sha) → ล้างของเก่า (wrapper/script/log/zip/dist/build)
    → สำรอง asset + ตรวจ sha ผ่านครบ (tools/prune_releases.py --apply)
    → ลบ release/tag เก่าบน GitHub เหลือ 2 ตัวล่าสุด (เก็บตัวก่อนหน้าไว้ตรวจซ้ำเท่านั้น) → ✅ เสร็จ
    ถ้าต้องติดตั้ง release เก่ากลับขึ้น GitHub: tools/restore_release.py --tag <tag> --apply (ตรวจ sha กับ manifest)
```

สร้างโดย [haremking7025](https://github.com/haremking7025) · สำหรับ SFKeyword Desktop
