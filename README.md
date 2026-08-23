# SFBOT Control

ศูนย์ควบคุม **SFBOT** — โปรแกรมเดสก์ท็อปอัตโนมัติสำหรับเกม Special Force

Repo นี้ใช้เป็น **เซิร์ฟเวอร์อัปเดต + สวิตช์ปิดโปรแกรมระยะไกล (kill switch)** ให้กับแอป `SFBOT` ทุกเครื่องที่เปิดใช้งาน

## ไฟล์ใน repo นี้

| ไฟล์ | หน้าที่ |
|---|---|
| `update.json` | ประกาศเวอร์ชันล่าสุด + ลิงก์ดาวน์โหลด EXE + SHA-256 สำหรับตรวจสอบความถูกต้อง |
| `kill_switch.json` | สั่งปิดโปรแกรมทุกเครื่องจากระยะไกล (กรณีต้องการปิดปรับปรุงชั่วคราว) |
| `README.md` | เอกสารนี้ |

แอปจะอ่านไฟล์ทั้งสองผ่าน `https://raw.githubusercontent.com/haremking7025/sfbot-control/main/...` ทุกครั้งที่เปิดโปรแกรม

---

## 🚀 ปล่อยเวอร์ชันใหม่ (Auto-update)

1. **บิ้ว EXE ใหม่** จากโปรเจกต์ SFBOT (เช่น `SFBOT_v1.0.5.exe`)
2. **คำนวณ SHA-256** ของ EXE:
   ```powershell
   Get-FileHash .\SFBOT_v1.0.5.exe -Algorithm SHA256
   ```
3. **อัปเดต `update.json`**:

   ```json
   {
     "latest_version": "1.0.5",
     "download_url": "https://github.com/haremking7025/sfbot-control/releases/download/v1.0.5/SFBOT_v1.0.5.exe",
     "sha256": "ใส่ค่า SHA-256 ตัวพิมพ์ใหญ่จากขั้นตอนที่ 2",
     "release_notes": "📝 สรุปสิ่งที่เปลี่ยนในเวอร์ชันนี้",
     "force_update": false
   }
   ```

   > `force_update: true` = บังคับให้ทุกเครื่องอัปเดต แม้เวอร์ชันเท่ากัน (ใช้เมื่อด่วนจริง)

4. **สร้าง GitHub Release** พร้อมแนบ EXE เป็น asset:
   ```bash
   gh release create v1.0.5 SFBOT_v1.0.5.exe \
     --repo haremking7025/sfbot-control \
     --title "SFBOT v1.0.5" \
     --notes "รายละเอียดเวอร์ชัน"
   ```
   > ต้องแน่ใจว่า tag ตรงกับ `download_url` และ `latest_version` ใน `update.json`

5. ทุกเครื่องที่เปิด SFBOT จะเห็นหน้าต่าง "มีอัปเดตใหม่" → กดอัปเดต → ดาวน์โหลด + ตรวจ SHA-256 → รีสตาร์ทอัตโนมัติ

---

## 🛑 สั่งปิดโปรแกรมทุกเครื่อง (Kill Switch)

แก้ `kill_switch.json`:

```json
{
  "active": true,
  "message": "ปิดปรับปรุงชั่วคราว กรุณารอ",
  "min_version": "1.0.0"
}
```

| ฟิลด์ | ความหมาย |
|---|---|
| `active` | `true` = บล็อก, `false` = ปลดบล็อก |
| `message` | ข้อความที่แสดงในหน้าต่างปิดปรับปรุง |
| `min_version` | เวอร์ชันต่ำสุดที่ไม่โดนบล็อก (เครื่องที่เวอร์ชัน ≥ ค่านี้เปิดได้ปกติ) |

แล้ว commit + push → ทุกเครื่องที่เปิด SFBOT จะเจอหน้าต่าง "ปิดปรับปรุงชั่วคราว" ทันที

---

## ⚠️ หมายเหตุ

- GitHub CDN (`raw.githubusercontent.com`) อาจแคชไฟล์เก่าได้ **1–5 นาที** หลัง push — ถ้าเครื่องไคลเอนต์ยังเห็นเวอร์ชันเก่า ให้รอสักครู่
- `sha256` ใน `update.json` ต้องตรงกับ EXE จริงที่อัปโหลด ไม่งั้นแอปจะปฏิเสธการอัปเดต (กันไฟล์เสียหาย/ถูกแทรกแซง)
- ใช้เวอร์ชันนี้ร่วมกับแอป SFBOT v1.0.0 ขึ้นไปเท่านั้น

---

## 📦 ตัวอย่างไฟล์ปัจจุบัน

**update.json**

```json
{
  "latest_version": "1.0.4",
  "download_url": "https://github.com/haremking7025/sfbot-control/releases/download/v1.0.4/SFBOT_v1.0.4.exe",
  "sha256": "E44340C54388BA3A030AFD5B7EBBE6B06AB391C3EF094B13654F285C4BC2FB9A",
  "release_notes": "🛡 ป้องกันโค้ด Cython + PyArmor\n🎨 หน้าต่างอัปเดตสวยงาม\n🔧 แก้บั๊ก Security validation หลังรีสตาร์ท",
  "force_update": false
}
```

**kill_switch.json**

```json
{
  "active": false,
  "message": "ปิดปรับปรุงชั่วคราว",
  "min_version": "1.0.0"
}
```

---

สร้างโดย [haremking7025](https://github.com/haremking7025) · สำหรับ SFBOT Desktop
