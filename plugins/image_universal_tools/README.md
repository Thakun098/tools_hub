# Image Universal Tools

Tools Hub Plugin สำหรับลบพื้นหลังและแปลงไฟล์ภาพบนเครื่องผู้ใช้

## รุ่นแรก

- รองรับ PNG, JPEG/JPG, WebP, BMP และ TIFF หน้าแรก
- ลบพื้นหลังเป็น PNG โปร่งใสด้วย CPU
- แปลงไฟล์แบบหลายรายการด้วย queue ทีละงาน
- apply EXIF orientation, แปลงสีเป็น sRGB และลบ metadata โดยค่าเริ่มต้น
- จำกัดภาพไม่เกิน 50 megapixels และไม่เขียนทับไฟล์เดิม
- โมเดล Fast, Balanced และ Quality ดาวน์โหลดเมื่อผู้ใช้สั่งเท่านั้น

## Development

```powershell
uv venv .\plugins\image_universal_tools\venv --python 3.11
.\plugins\image_universal_tools\venv\Scripts\python.exe -m pip install -r .\plugins\image_universal_tools\requirements-dev.txt
```

Build engine sidecar and Plugin ZIP:

```powershell
.\plugins\image_universal_tools\build_engine.ps1
$env:IMAGE_ENGINE_SOURCE=(Resolve-Path .\plugins\image_universal_tools\dist\image-engine.exe)
.\plugins\image_universal_tools\venv\Scripts\python.exe -m hub.plugin_package .\plugins\image_universal_tools --output-dir .\dist\plugins
```

โมเดลและไฟล์ของผู้ใช้ไม่อยู่ใน Plugin ZIP แต่จัดเก็บผ่าน `HubPaths` เท่านั้น
