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
  สลับครบ + กริดการ์ดตั้งค่าเสมอกัน) / E2E ดาวน์โหลดจริง MATCH (size + sha)

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
  venv/Scripts/ruff.exe check .        # ตรวจบั๊ก/เดดโค้ด (build รันให้อัตโนมัติ)
  ```

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
  > เดดโค้ด (`python -m ruff check .`) — ถ้าติดให้แก้ก่อน ไม่งั้น build หยุดทันที (errorlevel 1)
  > ใช้ build ไม่ป้องกัน (headless ตอบ n) — อยากป้องกันจริงตั้ง `SFKeyword_PROTECT=y`
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

> เครื่องนี้ไม่มี `gh` CLI — ใช้ GitHub REST API ผ่าน script ชั่วคราว `_do_release_<ver>.py`
> (token ดึงจาก `git credential fill`) ตามที่ทำจริงใน v1.3.44–1.3.47:

- [ ] เขียน `_do_release_<ver>.py`:
  1. `git credential fill` → แยก `password=` เป็น token
  2. `POST /repos/haremking7025/sfbot-control/releases` (tag_name/name/body = สรุปที่เปลี่ยน)
  3. อัปโหลด asset EXE + ZIP → `POST /uploads.github.com/.../assets?name=...` (201 ทั้งคู่)

- [ ] รัน: `venv/Scripts/python.exe _do_release_<ver>.py` → ตรวจ `create release: 201` + `upload ...: 201` ×2

  > ⚠️ tag ต้องตรงกับ `url` ใน update.json (ขั้นตอน 6) ทุกจุด

- [ ] ยืนยัน asset อัปโหลดครบ (EXE + ZIP) + digest ตรงเครื่อง

- [ ] ถ้ามี `gh` CLI ใช้วิธีเดิมได้:

  ```bash
  gh release create v1.2.2 dist/SFKeyword/SFKeyword_v1.2.2.exe dist/SFKeyword/SFKeyword_v1.2.2.zip \
    --repo haremking7025/sfbot-control --title "SFKeyword v1.2.2" --notes "📝 สรุปสิ่งที่เปลี่ยนในเวอร์ชันนี้"
  ```

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

- [ ] ลบ release เก่าบน GitHub ไหม? (เก็บเฉพาะล่าสุด — API script, ลบ release ด้วย id ก่อนแล้วค่อยลบ tag):

  ```python
  # token จาก git credential fill → h = {"Authorization": f"token {tok}"}
  # 1) GET /repos/{repo}/releases?per_page=100 → ลบทุกตัวที่ tag != ล่าสุด:
  #    DELETE /repos/{repo}/releases/{id}         → 204
  # 2) DELETE /repos/{repo}/git/refs/tags/{tag}   → 204
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
constants.py (VERSION) → gates (ruff + compile + boot smoke 7 แท็บ)
    → build_client.bat headless (EXE) → zip → sha256/size
    → _do_release_<ver>.py (API: create release + upload EXE/ZIP, token จาก git credential)
    → update.json (version/url/sha256/size) + docs/release_history.csv → commit + push
    → E2E ดาวน์โหลดจริง MATCH (size + sha) → ล้างของเก่า (wrapper/script/log/zip/dist/build)
    → ลบ release/tag เก่าบน GitHub เหลือแค่ล่าสุด → ✅ เสร็จ
```

สร้างโดย [haremking7025](https://github.com/haremking7025) · สำหรับ SFKeyword Desktop
