# SFKeyword Control

ศูนย์ควบคุม **SFKeyword** — โปรแกรมเดสก์ท็อปอัตโนมัติสำหรับเกม Special Force

Repo นี้ใช้เป็น **เซิร์ฟเวอร์อัปเดต + สวิตช์ปิดโปรแกรมระยะไกล (kill switch)** ให้กับแอป `SFKeyword` ทุกเครื่องที่เปิดใช้งาน

## ไฟล์ใน repo นี้

| ไฟล์ | หน้าที่ |
|---|---|
| `update.json` | ประกาศเวอร์ชันล่าสุด + ลิงก์ดาวน์โหลด EXE + SHA-256 + ขนาดไฟล์ (bytes) |
| `kill_switch.json` | สั่งปิดโปรแกรมทุกเครื่องจากระยะไกล (กรณีต้องการปิดปรับปรุงชั่วคราว) |
| `README.md` | เอกสารนี้ |
| `RELEASE_CHECKLIST.md` | ขั้นตอนปล่อยเวอร์ชันใหม่แบบละเอียด (build → zip → sha256 → release → update.json) — ดูได้ที่ [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) |
| `docs/build-protected.md` | วิธี build แบบกันโค้ด (Cython + PyArmor) โดยไม่ใช้ vcvarsall + ขั้นตอน Release — ดูได้ที่ [docs/build-protected.md](docs/build-protected.md) |
| `docs/README.md` | เอกสารเต็มของโปรเจกต์ SFKeyword (ความสามารถ, โครงสร้างโค้ด, แก้ปัญหา) — ดูได้ที่ [docs/README.md](docs/README.md) |

แอปจะอ่านไฟล์ทั้งสองผ่าน `https://raw.githubusercontent.com/haremking7025/sfbot-control/main/...` ทุกครั้งที่เปิดโปรแกรม

---

## 🚀 ปล่อยเวอร์ชันใหม่ (Auto-update)

> 📋 มีขั้นตอนละเอียดทุกขั้นตอนใน [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) — ไล่ตามลำดับทุกครั้ง

1. **บิ้ว EXE + ZIP ใหม่** จากโปรเจกต์ SFKeyword (เช่น `SFKeyword_v1.2.2.exe` และ `SFKeyword_v1.2.2.zip`)
2. **คำนวณ SHA-256 ของ ZIP** (ตัวที่แจกให้ผู้ใช้ดาวน์โหลด):
   ```powershell
   Get-FileHash .\SFKeyword_v1.2.2.zip -Algorithm SHA256
   ```
3. **อัปเดต `update.json`** — schema ที่ใช้จริง:

   ```json
   {
     "version": "1.2.2",
     "url": "https://github.com/haremking7025/sfbot-control/releases/download/v1.2.2/SFKeyword_v1.2.2.zip",
     "sha256": "8feaf14f55e96320a08f3c793b92c4a8c1c86a260f299ffbcf48ac5056728664",
     "size": 28589633
   }
   ```

   | ฟิลด์ | ความหมาย |
   |---|---|
   | `version` | เวอร์ชันล่าสุด (เปรียบเทียบกับเวอร์ชันเครื่อง) |
   | `url` | ลิงก์ดาวน์โหลด — ต้องชี้ไป asset ของ release จริง |
   | `sha256` | เช็คความถูกต้องของไฟล์หลังดาวน์โหลด (ตัวพิมพ์เล็ก) |
   | `size` | ขนาดไฟล์เป็น bytes — เช็คความสมบูรณ์ก่อนโหลด |

   > updater รองรับ schema เก่า (`latest_version` / `download_url` / `release_notes` / `force_update`) อยู่ด้วย แต่ repo นี้ใช้ schema ใหม่ข้างต้น

4. **สร้าง GitHub Release** พร้อมแนบ **ทั้ง EXE และ ZIP** เป็น asset:
   ```bash
   gh release create v1.2.2 SFKeyword_v1.2.2.exe SFKeyword_v1.2.2.zip \
     --repo haremking7025/sfbot-control \
     --title "SFKeyword v1.2.2" \
     --notes "รายละเอียดเวอร์ชัน"
   ```
   > ต้องแน่ใจว่า tag ตรงกับ `url` ใน `update.json` และ asset ZIP ที่แนบคือไฟล์เดียวกับที่คำนวณ sha256 ไว้

5. **Commit + push** `update.json` → ทุกเครื่องที่เปิด SFKeyword จะเห็นหน้าต่าง "มีอัปเดตใหม่" → กดอัปเดต → ดาวน์โหลด + ตรวจ SHA-256/ขนาด → รีสตาร์ทอัตโนมัติ

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
| `min_version` | เวอร์ชันต่ำสุดที่ไม่โดนบล็อก (เครื่องที่เวอร์ชัน ≥ ค่านี้เปิดได้ปกติ) |

แล้ว commit + push → ทุกเครื่องที่เปิด SFKeyword จะเจอหน้าต่าง "ปิดปรับปรุงชั่วคราว" ทันที

---

## ⚠️ หมายเหตุ

- GitHub CDN (`raw.githubusercontent.com`) อาจแคชไฟล์เก่าได้ **1–5 นาที** หลัง push — ถ้าเครื่องไคลเอนต์ยังเห็นเวอร์ชันเก่า ให้รอสักครู่
- `sha256` และ `size` ใน `update.json` ต้องตรงกับ ZIP จริงที่อัปโหลด ไม่งั้นแอปจะปฏิเสธการอัปเดต (กันไฟล์เสียหาย/ถูกแทรกแซง)
- อย่าอัปโหลดไฟล์ ZIP/EXE ลงใน repo ตรงๆ (history bloat) — แนบเป็น release asset เท่านั้น
- ใช้เวอร์ชันนี้ร่วมกับแอป SFKeyword v1.0.0 ขึ้นไปเท่านั้น

---

## 📦 ตัวอย่างไฟล์ปัจจุบัน

**update.json** (v1.2.2)

```json
{
  "version": "1.2.2",
  "url": "https://github.com/haremking7025/sfbot-control/releases/download/v1.2.2/SFKeyword_v1.2.2.zip",
  "sha256": "8feaf14f55e96320a08f3c793b92c4a8c1c86a260f299ffbcf48ac5056728664",
  "size": 28589633
}
```

**kill_switch.json**

```json
{
  "active": false,
  "message": "โปรแกรมอยู่ระหว่างการปิดปรับปรุง — กรุณารอเวอร์ชันใหม่อีกครั้ง",
  "min_version": "1.0.0"
}
```

---

สร้างโดย [haremking7025](https://github.com/haremking7025) · สำหรับ SFKeyword Desktop
