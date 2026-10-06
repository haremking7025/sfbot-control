# SFKeyword Control

ศูนย์ควบคุม **SFKeyword** — โปรแกรมเดสก์ท็อปอัตโนมัติสำหรับเกม Special Force

Repo นี้ใช้เป็น **เซิร์ฟเวอร์อัปเดต + สวิตช์ปิดโปรแกรมระยะไกล (kill switch)** ให้กับแอป `SFKeyword` ทุกเครื่องที่เปิดใช้งาน

## ไฟล์ใน repo นี้

| ไฟล์ | หน้าที่ |
|---|---|
| `update.json` | ประกาศเวอร์ชันล่าสุด + ลิงก์ดาวน์โหลด **EXE** + SHA-256 + ขนาดไฟล์ (bytes) + `notes` ที่หน้าต่างอัปเดตแสดงให้ผู้ใช้เห็น |
| `kill_switch.json` | สั่งปิดโปรแกรมทุกเครื่องจากระยะไกล (กรณีต้องการปิดปรับปรุงชั่วคราว) |
| `README.md` | เอกสารนี้ |
| `docs/RELEASE_CHECKLIST.md` | ขั้นตอนปล่อยเวอร์ชันใหม่แบบละเอียด (build → EXE/ZIP → sha256 → release → update.json) — ดูได้ที่ [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) |
| `docs/release_history.csv` | ประวัติการปล่อยทุกเวอร์ชัน (ชื่อไฟล์ · SHA-256 · วันเวลา) — สคริปต์ปล่อยเติมแถวให้เอง |
| `docs/WORDING.md` | ดิกชันนารีคำที่ผู้ใช้เห็น + กติกาถ้อยคำ (รวมข้อความใน `notes`) |
| `docs/build-protected.md` | วิธี build แบบกันโค้ด (Cython + PyArmor) โดยไม่ใช้ vcvarsall + ขั้นตอน Release — ดูได้ที่ [docs/build-protected.md](docs/build-protected.md) |
| `docs/README.md` | เอกสารเต็มของโปรเจกต์ SFKeyword (ความสามารถ, โครงสร้างโค้ด, แก้ปัญหา) — ดูได้ที่ [docs/README.md](docs/README.md) |

แอปจะอ่านไฟล์ทั้งสองผ่าน `https://raw.githubusercontent.com/haremking7025/sfbot-control/main/...` ทุกครั้งที่เปิดโปรแกรม

---

## 🚀 ปล่อยเวอร์ชันใหม่ (Auto-update)

> 📋 มีขั้นตอนละเอียดทุกขั้นตอนใน [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) — ไล่ตามลำดับทุกครั้ง
> ตัวอย่างข้างล่างใช้ **v1.3.99** — แทนที่ด้วยเลขรุ่นจริงทุกจุด

1. **บิ้ว EXE ใหม่** จากโปรเจกต์ SFKeyword (เลขรุ่นอ่านจาก `sfkeyword_lib/core/constants.py` ผ่าน `tools/get_version.py`) → ได้ `dist\SFKeyword\SFKeyword_v1.3.99.exe` พร้อม `SFKeyword_v1.3.99.zip` (ZIP เก็บไว้เป็นหลักฐานของรุ่น — **ไม่ใช่** ไฟล์ที่เครื่องลูกค้าดาวน์โหลด)
2. **คำนวณ SHA-256 + ขนาดของ EXE** (`update.json` ชี้ EXE ตรง ๆ):
   ```powershell
   (Get-FileHash .\dist\SFKeyword\SFKeyword_v1.3.99.exe -Algorithm SHA256).Hash   # hex 64 ตัว
   (Get-Item .\dist\SFKeyword\SFKeyword_v1.3.99.exe).Length                       # ขนาดเป็น bytes
   ```
3. **อัปเดต `update.json`** — schema ที่ใช้จริง:

   ```json
   {
     "version": "1.3.99",
     "url": "https://github.com/haremking7025/sfbot-control/releases/download/v1.3.99/SFKeyword_v1.3.99.exe",
     "sha256": "479D9B9A4A83D1653513918C8DEB2C363646625DA578FB41A211D764B3FEAA78",
     "size": 28766074,
     "notes": "หัวข้อสรุปหนึ่งบรรทัด\n\n• สิ่งที่เปลี่ยนข้อ 1\n• สิ่งที่เปลี่ยนข้อ 2"
   }
   ```

   | ฟิลด์ | ความหมาย |
   |---|---|
   | `version` | เวอร์ชันล่าสุด (เปรียบเทียบกับเวอร์ชันเครื่อง) |
   | `url` | ลิงก์ดาวน์โหลด — ต้องชี้ไป asset ของ release จริง (**EXE** ไม่ใช่ ZIP) |
   | `sha256` | เช็คความถูกต้องของไฟล์หลังดาวน์โหลด — hex 64 ตัว (ไฟล์ในรีโปนี้ใช้ตัวพิมพ์ใหญ่ · ตัวตรวจเทียบแบบไม่สนตัวพิมพ์) |
   | `size` | ขนาดไฟล์เป็น bytes — เช็คความสมบูรณ์ก่อนโหลด |
   | `notes` | ข้อความที่หน้าต่างอัปเดตแสดงให้ผู้ใช้เห็น (เขียนไทย · กติกาถ้อยคำอยู่ใน `docs/WORDING.md`) |

   > updater รองรับ schema เก่า (`latest_version` / `download_url` / `release_notes` / `force_update`) อยู่ด้วย แต่ repo นี้ใช้ schema ใหม่ข้างต้น · `force_update: true` = เด้งหน้าต่างอัปเดตแบบบังคับ

4. **ปล่อยด้วยคำสั่งเดียว** — สร้าง release + อัปโหลด EXE/ZIP + เขียน `update.json` + เติมแถว CSV + commit/push เฉพาะ metadata:
   ```bash
   venv/Scripts/python.exe tools/release_publish.py --version 1.3.99 \
     --summary-file dist/release_summary_v1.3.99.txt --apply
   ```
   ด่านที่รันให้เองก่อนแตะ GitHub: รุ่นต้องไม่ถอยหลัง · สวิตช์ปิดปรับปรุงต้องปิดอยู่ · ชุดด่านต้องเขียว · EXE ต้องเปิดขึ้นจริง — ไม่ผ่านข้อใด = **ไม่ commit** (เครื่องนี้ไม่มี `gh` CLI จึงใช้ GitHub REST API ผ่าน token จาก `git credential fill` · ถ้าจะสั่งเองด้วย gh ก็ได้: `gh release create v1.3.99 <EXE> <ZIP> --repo haremking7025/sfbot-control` · ถ้าอยาก commit เองให้เติม `--no-commit`)

5. **ตรวจหลังปล่อย** — ดาวน์โหลดไฟล์จาก release จริงมาเทียบ size + SHA-256 กับ `update.json` (`tools/_release_consistency_verify.py --strict-net --deep`) → ตรงแล้วทุกเครื่องที่เปิด SFKeyword จะเห็นหน้าต่าง "มีอัปเดตใหม่" → กดอัปเดต → ดาวน์โหลด + ตรวจ SHA-256/ขนาด → รีสตาร์ทอัตโนมัติ

---

## 🛑 สั่งปิดโปรแกรมทุกเครื่อง (Kill Switch)

แก้ `kill_switch.json`:

```json
{
  "active": true,
  "message": "โปรแกรมอยู่ระหว่างการปิดปรับปรุง — กรุณารอเวอร์ชันใหม่อีกครั้ง",
  "min_version": "1.0.0"
}
```

| ฟิลด์ | ความหมาย |
|---|---|
| `active` | `true` = บล็อก, `false` = ปลดบล็อก |
| `message` | ข้อความที่แสดงในหน้าต่างปิดปรับปรุง |
| `min_version` | เวอร์ชันต่ำสุดที่ไม่โดนบล็อก (เครื่องที่เวอร์ชัน ≥ ค่านี้เปิดได้ปกติ) — **ไม่ใส่คีย์นี้เลย = บล็อกทุกเวอร์ชัน** |

แล้ว commit + push → ทุกเครื่องที่เปิด SFKeyword จะเจอหน้าต่าง "ปิดปรับปรุงชั่วคราว" ทันที

> **ค่าที่ใช้อยู่จริงตอนนี้**: `active: false` และไม่มี `min_version` ⇒ ถ้าเปิดสวิตช์โดยไม่ใส่ `min_version` ทุกเวอร์ชันจะโดนบล็อก (ไม่เว้นรุ่นล่าสุด) · สคริปต์ปล่อยเวอร์ชันหยุดให้เองถ้าเห็น `active: true` (ข้ามได้เฉพาะเมื่อสั่ง `--allow-maintenance`)

---

## ⚠️ หมายเหตุ

- GitHub CDN (`raw.githubusercontent.com`) อาจแคชไฟล์เก่าได้ **1–5 นาที** หลัง push — ถ้าเครื่องไคลเอนต์ยังเห็นเวอร์ชันเก่า ให้รอสักครู่
- `sha256` และ `size` ใน `update.json` ต้องตรงกับ **EXE** จริงที่อัปโหลด (ไม่ใช่ ZIP) ไม่งั้นแอปจะปฏิเสธการอัปเดต (กันไฟล์เสียหาย/ถูกแทรกแซง)
- อย่าอัปโหลดไฟล์ EXE/ZIP ลงใน repo ตรงๆ (history bloat) — แนบเป็น release asset เท่านั้น (แนบ ZIP ไว้ด้วยเป็นหลักฐานของรุ่น — เปลี่ยนชื่อ asset ได้โดยไม่กระทบ sha ที่ใช้จริง)
- ใช้เวอร์ชันนี้ร่วมกับแอป SFKeyword v1.0.0 ขึ้นไปเท่านั้น

---

## 📦 ตัวอย่างไฟล์ปัจจุบัน

**update.json** (รุ่นที่ปล่อยอยู่จริง = v1.3.98)

```json
{
  "version": "1.3.98",
  "url": "https://github.com/haremking7025/sfbot-control/releases/download/v1.3.98/SFKeyword_v1.3.98.exe",
  "sha256": "FCF5D4A88996065ADD6C31FBE557EE82E0D27F9169CC565446BCDC011FE4BE7A",
  "size": 28792291,
  "notes": "ตรวจรุ่นใหม่ได้โดยไม่ต้องปิดโปรแกรม และโปรแกรมจดคำตอบของเว็บที่อ่านผลไม่ได้ไว้ทบทวน\n\n• ตรวจเปิดตัวโปรแกรมที่แพ็กแล้วได้ขณะโปรแกรมเปิดอยู่ ไม่ปิดและไม่แตะหน้าต่างของคุณ\n• โปรแกรมจดคำตอบของเว็บที่อ่านผลไม่ได้ไว้ทบทวนเป็นรอบ เพื่อเติมคำและแก้อาการค้างหรือยิงซ้ำได้ตรงจุด\n• ถ้อยคำรอบอัตโนมัติตอนตีห้านาทีมีฉากตรวจครบทั้งสำเร็จ ยังไม่ทราบผล และยังไม่พบคีย์"
}
```

**kill_switch.json**

```json
{
  "active": false,
  "message": "ปิดปรับปรุงชั่วคราว"
}
```

---

สร้างโดย [haremking7025](https://github.com/haremking7025) · สำหรับ SFKeyword Desktop
