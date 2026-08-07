# Tools Hub — Progress Log

---

## 2026-08-01 — ทดสอบ Build ToolsHub.exe (ครั้งแรก)

### รายละเอียด Build

| รายการ     | ค่า                                     |
| ------------| -----------------------------------------|
| Build tool | PyInstaller 6.21.0                      |
| Python     | 3.14 (system)                           |
| Spec file  | `ToolsHub.spec`                         |
| Output     | `dist\ToolsHub\ToolsHub.exe` (~14.4 MB) |
| Mode       | one-folder, `console=True`              |

### ผลการทดสอบ

- ✅ **รันได้ แสดงผลปกติ** — exe เปิด Flask server และแสดง dashboard ในเบราว์เซอร์ได้สำเร็จ
- ⚠️ **ยังคงไม่พบ plugin ของ SRT** — Free SRT plugin ยังไม่ถูกโหลด (คาดว่าเพราะยังไม่ได้ bundle plugin เข้าไปใน build)
- ✅ **การเปลี่ยน Theme ทำงานได้ปกติ** — สลับ Terminal Dark / Editorial Light ได้ถูกต้อง
- ✅ **ไม่มีการแสดงผลที่ผิดเพี้ยนจากที่คาด** — UI ตรงตาม prototype

### หมายเหตุ

- Build ใช้ system Python 3.14 ซึ่งมี packages จำนวนมาก (numpy, PIL, IPython ฯลฯ) ถูก pull เข้ามาด้วย ทำให้ขนาดใหญ่กว่าที่ควร — แนะนำให้ build จาก venv เฉพาะในอนาคต
- Plugin จะถูกติดตั้งแยกโดยผู้ใช้ภายหลัง
