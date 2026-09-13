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

> เครื่องนี้ไม่มี `gh` CLI — ใช้ GitHub REST API ผ่านเครื่องมือถาวร `tools/release_publish.py`
> (token ดึงจาก `git credential fill`) ⇒ **ไม่ต้องเขียนสคริปต์ชั่วคราวรายรุ่นอีก**

- [ ] ปล่อยทั้งชุดในคำสั่งเดียว (release + อัปโหลด EXE/ZIP + `update.json` + CSV):

  ```bash
  venv/Scripts/python.exe tools/release_publish.py              # ดูเฉย ๆ ก่อน (ดีฟอลต์ ไม่ทำอะไร)
  venv/Scripts/python.exe tools/release_publish.py --apply      # ปล่อยจริง
  venv/Scripts/python.exe tools/release_publish.py --selftest   # ตรวจตรรกะในเครื่อง (ไม่แตะเน็ต)
  ```

  - ตรวจไฟล์ EXE/ZIP + sha ก่อนแตะ GitHub · สร้าง release + อัปโหลด · ยืนยันด้วย digest ที่ GitHub
    รายงาน + ดาวน์โหลดจริงมาเทียบ sha · เขียน `update.json` และ append CSV ให้เอง · รันซ้ำได้ไม่พัง
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
  > ในเครื่องลูกค้าอยู่แล้ว (ถอยได้เฉพาะเครื่องนั้น — ไม่ใช่ทั้งฐาน)

- [ ] **บทเรียนการเก็บของเก่า: ZIP คือหลักฐานที่เชื่อถือได้ ไม่ใช่ `dist\*.exe`**
      → ตอนนำเข้ารุ่นยุค SFBOT (1.2.8/1.3.0/1.3.1) เข้าคลัง เจอว่า `dist\SFBOT_v1.2.8.exe`
      ถูก **build ทับใหม่ทีหลัง** (1 ก.ย. → 2 ก.ย.) ⇒ sha ไม่ตรงกับประวัติปล่อยเดิม
        แต่ `SFBOT_v1.2.8.zip` ยังเป็นไบต์วันปล่อย ⇒ แกะ exe ข้างในได้ sha ตรงประวัติเป๊ะ
      ⇒ เก็บ ZIP ไว้ทุกครั้ง · ติ่งชื่อ asset ใหม่ได้โดยไม่เปลี่ยนไบต์ (sha เดิม)

- [ ] **ถอยลูกค้าทั้งฐาน (ฉุกเฉิน)** — ใช้สคริปต์ถาวร `tools/release_rollback.py`
      ที่ตั้ง `force_update: true` ให้เอง (แฟล็กนี้ข้ามการเทียบเวอร์ชัน ⇒ รุ่นเก่าถูกเสนอ
      ให้ติดตั้งได้) และ **รันด่านความสอดคล้องก่อน push ทุกครั้ง**:

  ```bash
  venv/Scripts/python.exe tools/release_rollback.py --list                # รุ่นที่ถอยได้ทั้งหมด
  venv/Scripts/python.exe tools/release_rollback.py --to 1.3.83            # ดูแผน (ดีฟอลต์ ไม่ทำอะไร)
  venv/Scripts/python.exe tools/release_rollback.py --to 1.3.83 --apply    # ถอยจริง
  venv/Scripts/python.exe tools/release_rollback.py --stop --apply         # เลิกบังคับ + กลับรุ่นใหม่สุด
  venv/Scripts/python.exe tools/release_rollback.py --selftest             # ตรวจตรรกะในเครื่อง
  ```

  → กฎความปลอดภัย: รุ่นเป้าหมายต้องมี **release บน GitHub + asset EXE + digest + แถวในประวัติ**
  และ sha ตรงกันทุกชั้น ขาดข้อใด = หยุด (บอกทางแก้ เช่นให้ `restore_release.py` ติดตั้งกลับก่อน) ·
  ด่านไม่ผ่าน = คืน `update.json` เดิม ไม่ commit · commit เฉพาะ `update.json`
  · ⚠ `force_update` ไม่แยกรุ่น ⇒ ลูกค้าที่อยู่รุ่นเป้าหมายแล้วจะถูกเสนอรุ่นเดิมซ้ำ
  ⇒ **ถอยเสร็จแล้วรัน `--stop --apply`** (พร้อมออกเวอร์ชันแก้ไขต่อไป) · ด่านกันถอยหลัง: `tools/_rollback_verify.py`

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
  — ตั้งแต่ build ใหม่ ระบบถามยืนยันก่อนเขียน CSV (`SFKeyword_LOG_RELEASE=y`) จึงควรมีเฉพาะ
  เวอร์ชันที่ปล่อยจริงอยู่แล้ว
- [ ] **ด่านบังคับอัตโนมัติ** `tools/_release_consistency_verify.py` (อยู่ในชุด harness ⇒ build
      รันให้ก่อน build เสมอ) ตรวจสามที่ให้ตรงกัน: GitHub releases/tags ↔ `docs/release_history.csv`
      ↔ `update.json` — **ไม่ตรงแล้ว build หยุดทันที** กันเคสที่ลูกค้าเจอ "กดอัปเดตแล้วพัง"

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
    → ลบ release/tag เก่าบน GitHub เหลือ 2 ตัวล่าสุด (เก็บตัวก่อนหน้าไว้เป็นทางถอย) → ✅ เสร็จ
    ถ้าต้องติดตั้ง release เก่ากลับขึ้น GitHub: tools/restore_release.py --tag <tag> --apply (ตรวจ sha กับ manifest)
    ถ้าต้องให้ลูกค้าทุกเครื่องถอยรุ่น: tools/release_rollback.py --to <รุ่น> --apply → แล้ว --stop --apply
```

สร้างโดย [haremking7025](https://github.com/haremking7025) · สำหรับ SFKeyword Desktop
