# 📋 RELEASE CHECKLIST — ปล่อยเวอร์ชันใหม่ SFKeyword

ใช้ checklist นี้ทุกครั้งที่ปล่อยเวอร์ชันใหม่ ไล่ตามลำดับ **ห้ามข้ามขั้นตอน** ตัวที่ทำแล้วให้ติ๊ก ☐ → ☑ หรือลบออก

> ตัวอย่างในเอกสารนี้ใช้ **v1.2.2** — ให้แทนที่ด้วยเวอร์ชันจริงทุกจุด (ห้ามพลาดเพราะจุดนี้แหละที่ทำบ่อยที่สุด)

---

## 0. ตรวจสภาพก่อนเริ่ม

- [ ] โปรเจกต์อยู่ในโฟลเดอร์ถูกต้อง (`sfkeyword.pyw` + `sfkeyword_lib\` อยู่ด้วยกัน)
- [ ] venv พร้อม (`venv\` มีอยู่ หรือ build จะสร้างให้เอง) — ถ้าสร้างใหม่ ให้ติดตั้ง
  dependencies ผ่าน manifest กลางที่ root (รวม runtime + build ทั้งหมด):

  ```bat
  venv\Scripts\python.exe -m pip install -r requirements.txt
  ```
- [ ] ติดต่อ GitHub ได้ (`gh auth status` ผ่าน)
- [ ] ไฟล์ source ผ่านชุดตรวจ (build จะรันให้อัตโนมัติ แต่ตรวจเองก่อนดีกว่า):

  ```bash
  python -m py_compile sfkeyword.pyw sfkeyword_lib/core/*.py sfkeyword_lib/engine/*.py sfkeyword_lib/features/*.py sfkeyword_lib/ui/*.py
  python -m ruff check .
  python tools/check_bugs.py
  python tools/find_dead_code.py
  ```

---

## 1. อัปเดตเวอร์ชัน

- [ ] แก้ `VERSION` ใน `sfkeyword_lib/core/constants.py`:

  ```python
  VERSION = "1.2.2"   # ← เปลี่ยนเป็นเวอร์ชันใหม่ เช่น "1.3.0"
  ```

- [ ] รันชุดตรวจรอบสั้น (py_compile + ruff) ยืนยันเขียวก่อน build

---

## 2. Build EXE

- [ ] รัน build แบบป้องกัน (Cython + PyArmor) — ตั้ง `SFKeyword_PROTECT=y` กันบั๊กป้อน stdin:

  ```bat
  set SFKeyword_PROTECT=y
  build_client.bat
  ```

  > รันแบบอัตโนมัติ/headless (ส่ง input ไม่ได้) ให้เพิ่ม `set SFKeyword_NO_PAUSE=y`
  > เพื่อข้ามทุก `pause` ท้ายสคริปต์ (กันค้างรอ keypress)

  > build จะรัน 3 ชุดตรวจอัตโนมัติ (check_bugs → ruff → find_dead_code) — ถ้าติดให้แก้ก่อน
  > ไม่งั้น build หยุดทันที (errorlevel 1)
  > Cython compile 43 โมดูลแบบขนาน (`-j`) + แคช `.pyd` ข้าม build (`.cython-cache\`) —
  > รอบแรก ~50 วิ รอบถัดไป (เนื้อหาไม่เปลี่ยน) เหลือ ~20-25 วิ ไม่ใช่ 10 นาที

- [ ] ยืนยัน EXE เกิดที่: `dist\SFKeyword\SFKeyword_v1.2.2.exe`
- [ ] บันทึก release_history.csv: ตอบ "y" ข้อถาม "Release build - log this build to
  docs/release_history.csv?" (หรือตั้ง `SFKeyword_LOG_RELEASE=y` ล่วงหน้า) — CSV ควรเก็บเฉพาะ
  เวอร์ชันที่ปล่อยจริง ตรวจว่ามีแถวใหม่ 1 แถว

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

- [ ] สร้าง release พร้อมแนบ **ทั้ง EXE และ ZIP**:

  ```bash
  gh release create v1.2.2 dist/SFKeyword/SFKeyword_v1.2.2.exe dist/SFKeyword/SFKeyword_v1.2.2.zip \
    --repo haremking7025/sfbot-control \
    --title "SFKeyword v1.2.2" \
    --notes "📝 สรุปสิ่งที่เปลี่ยนในเวอร์ชันนี้"
  ```

  > ⚠️ tag ต้องตรงกับ `url` ใน update.json (ขั้นตอน 6) ทุกจุด

- [ ] ยืนยัน asset อัปโหลดครบ (EXE + ZIP) + digest ตรงเครื่อง

---

## 6. อัปเดต `update.json` (repo sfbot-control)

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
  | `sha256` | จากขั้นตอน 4 (sha ของ EXE, ตัวพิมพ์เล็ก) |
  | `size` | จากขั้นตอน 4 (bytes ของ EXE) |
  | `notes` | สรุปสิ่งที่เปลี่ยน — updater เอาไปแสดงในหน้าต่างอัปเดต |

  > ⚠️ update.json ต้องชี้ไปที่ **EXE** ตรงๆ (sha/size ของ EXE) —
  > ไม่ใช้ ZIP เป็น target อัปเดตแล้ว กัน updater ดาวน์โหลดผิดไฟล์

- [ ] commit + push:

  ```bash
  git add update.json && git commit -m "Update v1.2.2 checksum" && git push origin main
  ```

- [ ] **ซิงค์ RELEASE_CHECKLIST.md ไปยัง repo** (ถ้าแก้ checklist ในรอบนี้):

  ```bash
  python tools/sync_checklist.py --push
  ```

  > สคริปต์คัดลอก `docs/RELEASE_CHECKLIST.md` → repo + commit + push อัตโนมัติ
  > (หา clone จาก env `SFKeyword_CONTROL_DIR` หรือ `%TEMP%\sfbot-control`) — กันลืมซิงค์
  > ถ้าไม่ได้แก้ checklist รอบนี้ ข้ามได้

> ⚠️ **ห้าม commit ไฟล์ ZIP/EXE ลงใน repo** — .gitignore กันไว้แล้ว แนบเป็น release asset เท่านั้น

---

## 7. ทดสอบอัปเดตจริง (สำคัญที่สุด)

- [ ] ดาวน์โหลดจาก URL ใน update.json แล้วเทียบ sha256/size กับที่บันทึก:

  ```python
  import json, hashlib, urllib.request
  u = json.load(open(r"C:\Users\thepw\Desktop\SFKeyword\update.json"))  # หรืออ่านจาก GitHub
  # ดาวน์โหลด u["url"] → hashlib.sha256(ไฟล์).hexdigest() == u["sha256"] และ os.path.getsize == u["size"]
  ```

  → ต้องได้ **MATCH** (sha + size ตรงเป๊ะ) ไม่งั้นผู้ใช้อัปเดตไม่ได้

- [ ] เปิดแอปเวอร์ชันเก่า (เช่น v1.2.1) → กดอัปเดต → ดาวน์โหลด EXE → รีสตาร์ทเป็นเวอร์ชันใหม่
- [ ] หลังอัปเดต: ไอคอน/โลโก้ยังคม ไม่เบลอ + แอปเปิดปกติ

---

## 8. ล้างของเก่า (แล้วแต่)

- [ ] ลบ release เก่าบน GitHub ไหม? (เก็บเฉพาะล่าสุด):

  ```bash
  gh release delete v1.2.1 --repo haremking7025/sfbot-control --cleanup-tag --yes
  ```

- [ ] ลบ EXE/ZIP เก่าในโปรเจกต์ + build artifacts (`build\` `build_protected\`) ไหม?
  > ⚠️ **ห้ามลบ `.cython-cache\`** — เป็นแคช .pyd ที่ทำให้ build รอบหน้าวิ่งแบบ cache hit
  > (ลบแล้วรอบหน้าต้อง compile ทั้ง 43 โมดูลใหม่ ~50 วิ)
- [ ] อัปเดต `docs/release_history.csv` ให้ตรง release จริง (ถ้าลบ release เก่า ให้ลบแถวด้วย)
  — ตั้งแต่ build ใหม่ ระบบถามยืนยันก่อนเขียน CSV (`SFKeyword_LOG_RELEASE=y`) จึงควรมีเฉพาะ
  เวอร์ชันที่ปล่อยจริงอยู่แล้ว

---

## 🔁 สรุป flow คร่าวๆ

```
constants.py (VERSION) → build_client.bat (EXE) → zip → sha256/size
    → gh release create (EXE+ZIP) → update.json (version/url/sha256/size) → push
    → ทดสอบดาวน์โหลด MATCH → ล้างของเก่า → ✅ เสร็จ
```

สร้างโดย [haremking7025](https://github.com/haremking7025) · สำหรับ SFKeyword Desktop
