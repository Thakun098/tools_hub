# Free SRT

Free SRT เป็นเว็บแอปขนาดเล็กที่ทำงานในเครื่องสำหรับแปลงไฟล์เสียงหรือวิดีโอเป็นคำบรรยาย `.srt` โดยใช้ FFmpeg แปลงเสียงและใช้ [whisper.cpp](https://github.com/ggml-org/whisper.cpp) ถอดเสียง

โปรเจกต์ออกแบบสำหรับผู้ใช้กลุ่มเล็กและกำลังเตรียมไปสู่ Portable Windows `.exe` ในอนาคต ปัจจุบันยังรันด้วย Python เพื่อให้พัฒนาและทดสอบได้สะดวก

## ความสามารถปัจจุบัน

- รับไฟล์เสียงและวิดีโอที่ FFmpeg สามารถอ่านได้ เช่น MP3, WAV, FLAC, M4A, MP4, MOV และ MKV
- แปลง audio stream เป็น WAV 16 kHz mono ก่อนส่งให้ whisper.cpp
- เลือกภาษา โมเดล และจำนวน CPU threads
- เลือกโหมด CPU เท่านั้น หรือเร่งความเร็วด้วย GPU พร้อมเลือกอัตโนมัติ, NVIDIA CUDA หรือ Vulkan
- Portable ZIP หลักรวมทั้ง CPU, NVIDIA CUDA 11.8 และ Vulkan runtime พร้อมใช้ โดย CPU จะ fallback ให้อัตโนมัติเมื่อ GPU หรือ driver ใช้ไม่ได้
- ดาวน์โหลดและยกเลิกการดาวน์โหลดโมเดลได้
- ยกเลิกได้ทั้งระหว่าง upload, FFmpeg conversion และ Whisper transcription พร้อม ETA แบบ smoothing สำหรับ upload, transcription และ render
- ลบไฟล์ชั่วคราวและ SRT ที่สร้างไม่สมบูรณ์หลังยกเลิกหรือล้มเหลว
- แสดงคำแนะนำโมเดลด้วยภาษาที่เข้าใจง่าย
- Subtitle Editor พร้อม media playback และเล่นเฉพาะช่วงคำบรรยาย
- Editor แบบสองพาเนลตามหน้าจอ Free SRT: วิดีโออยู่ด้านซ้ายและรายการ subtitle อยู่ด้านขวา พร้อม live subtitle overlay ที่แสดงตั้งแต่ cue แรกและอัปเดตทันทีขณะแก้ข้อความหรือเวลา
- สลับธีมสว่าง/มืดจากแถบด้านบนได้ และระบบจำธีมที่เลือกระหว่างการเปิดใช้งาน
- แก้ข้อความและ timestamp, เพิ่ม/ลบ/แยก/รวม subtitle
- Undo/Redo, Find/Replace และ keyboard shortcuts
- Quality checks สำหรับเวลาซ้อน ข้อความว่าง จำนวนบรรทัด ความยาว ความเร็วในการอ่าน และระยะเวลา พร้อมปุ่มไปยังปัญหาถัดไป
- บันทึก SRT ที่แก้แล้ว พร้อมคืนค่าผลลัพธ์ต้นฉบับจาก Whisper
- สมุดคำศัพท์ถาวรแบบ autosave พร้อม Import/Export สำหรับแก้ชื่อเฉพาะซ้ำและส่งคำที่ถูกต้องเป็น initial prompt ในงานถัดไป
- เลือกฟอนต์คำบรรยายได้ โดยใช้ `Leelawadee UI` เป็นค่าเริ่มต้น และปรับขนาดตัวอักษรได้
- สร้าง พรีวิว และดาวน์โหลดวิดีโอ MP4 ที่ฝังคำบรรยายลงในภาพแล้ว
- จำโมเดล ภาษา CPU threads ธีม และรูปแบบซับล่าสุดใน data/preferences.json
- สำรองคำบรรยายที่กำลังแก้อัตโนมัติและกู้คืนหลังโปรแกรมปิดผิดปกติได้
- Preview และดาวน์โหลดผลลัพธ์ `.srt`
- ส่งออก `.txt` จากคำบรรยายฉบับล่าสุดใน Editor โดยไม่ต้องถอดเสียงใหม่

## สิ่งที่ต้องมีสำหรับการพัฒนา

- Windows 10/11
- Python 3.11 หรือใหม่กว่า
- FFmpeg และ `ffprobe` อยู่ใน `PATH`
- whisper.cpp Windows binaries ใน `bin/Release/`
- โมเดล GGML ใน `models/` หรือดาวน์โหลดผ่านหน้าโปรแกรม

ติดตั้ง Python packages:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

ถ้ายังไม่มี whisper.cpp binary สามารถใช้สคริปต์เดิมได้:

```powershell
python download_whisper.py
```

## การรัน

```powershell
.\venv\Scripts\python.exe app.py
```

จากนั้นเปิด `http://127.0.0.1:5000` โปรแกรม bind เฉพาะ loopback เพื่อไม่เปิดให้เครื่องอื่นใน LAN เข้าถึงโดยไม่ได้ตั้งใจ

### การทำงานผ่าน Tools Hub

FreeSRT ยังรัน standalone จาก `app.py` เหมือนเดิม และมี Hub adapter แยกใน `__init__.py` สำหรับ mount ที่ `/srt` โดยไม่แก้ domain behavior ตัว adapter รับ resource และ writable roots จาก Hub ดังนั้น preferences, glossary, models, runtimes, uploads และ outputs ของ Hub ไม่ถูกเขียนใต้ bundled `_MEIPASS` resources

Python implementation ใช้ namespace `toolshub_free_srt` เมื่อโหลดผ่าน Hub ส่วน package `freesrt` เดิมยังคงไว้เป็น compatibility path สำหรับ standalone และ tests เดิม Frontend อ่าน base URL จากหน้า HTML เพื่อให้ API, static assets, media preview และ downloads ทำงานได้ทั้งที่ root และใต้ `/srt`


#### Separate Tools Hub plugin package

Tools Hub core no longer bundles FreeSRT. Build the downloadable plugin ZIP from the monorepo root:

```powershell
$env:FFMPEG_SOURCE = (Get-Command ffmpeg).Source
$env:FFPROBE_SOURCE = (Get-Command ffprobe).Source
python -m hub.plugin_package plugins/free_srt --output-dir dist/plugins
```

Extract `toolshub-plugin-free_srt-<version>.zip` into the portable Tools Hub `plugins` directory, then restart Tools Hub. The installed manifest will be at `plugins/free_srt/plugin.json`. Models and user data remain outside the plugin directory and are not included in the ZIP.

## โครงสร้างโค้ด

`app.py` เป็น portable entry point และ compatibility façade โดยรองรับ `create_app(config)` และ isolated runtime modules สำหรับ Hub ขณะเดียวกันยัง export module-level `app` และชื่อฟังก์ชันเดิมที่ tests/launcher ใช้งาน ส่วน implementation แบ่งตามหน้าที่ดังนี้:

- `freesrt/workers.py` — model download, FFmpeg conversion, whisper.cpp transcription และ video rendering
- `freesrt/routes/transcription.py` — model, local-file selection, transcription และ diagnostics endpoints
- `freesrt/routes/video.py` — video preview/render/status/cancel/download endpoints
- `freesrt/routes/editor.py` — preferences, recovery backup, glossary และ subtitle editing endpoints
- `freesrt/subtitles.py` — parse/normalize/serialize และ atomic SRT writes
- `freesrt/subtitle_style.py` — font allow-list, style validation และ FFmpeg `force_style`
- `freesrt/settings.py`, `freesrt/glossary.py`, `freesrt/files.py` — validation และ persistence helpers
- freesrt/compute.py — catalog, GPU hint detection, runtime validation และ backend selection
- `freesrt/model_catalog.py` — `MODELS_INFO` ซึ่งเป็นแหล่งข้อมูลโมเดลเพียงจุดเดียว
- `static/js/` — state, DOM/format helpers และ SRT parsing ที่ใช้ร่วมกันใน frontend; `static/app.js` เป็น UI orchestration entry point

route และ worker modules รับ dependency จาก compatibility façade ตอน register/run เพื่อให้ path ของ portable build และ test overrides ยังเปลี่ยนได้โดยไม่สร้าง circular import

## ไฟล์สื่อขนาดใหญ่

สำหรับ MP4 หรือไฟล์สื่อขนาดหลาย GB ให้กด “เลือกไฟล์จากเครื่อง” โปรแกรมจะเปิด Windows file dialog แล้วให้ FFmpeg อ่านไฟล์เดิมโดยตรง จึงไม่คัดลอกไฟล์เข้า `uploads/` และจะไม่แก้ไขหรือลบไฟล์ต้นฉบับ

ก่อนเริ่มงาน โปรแกรมใช้ `ffprobe` ตรวจว่าอ่านไฟล์ได้ มีแทร็กเสียง และมีพื้นที่ว่างสำหรับ WAV ชั่วคราว 16 kHz mono PCM แล้ว หากพื้นที่ไม่พอหรือไฟล์ถูกย้ายไป จะหยุดพร้อมข้อความแจ้งก่อนเรียก FFmpeg. สำหรับการอัปโหลด โปรแกรมตรวจ `Content-Length` เทียบกับพื้นที่ว่างของโฟลเดอร์ชั่วคราวและ `uploads/` ก่อน parse multipart และลบสำเนาบางส่วนหากการบันทึกล้มเหลว ส่วนการอัปโหลดและลากวางยังเหมาะสำหรับไฟล์ขนาดเล็กหรือการใช้งานแบบ server.
## การใช้ Subtitle Editor

เมื่อถอดเสียงสำเร็จ ระบบจะเปลี่ยนเข้าสู่ Editor เต็มพื้นที่ในรูปแบบวิดีโอด้านซ้ายและรายการ subtitle ด้านขวา ไฟล์ที่อัปโหลดจะเล่นจาก browser `File` เดิม ส่วนไฟล์ที่เลือกจากเครื่องจะเล่นผ่าน endpoint ภายในแบบ opaque โดยไม่เผย path จริง บนหน้าจอแคบ Editor จะเรียงวิดีโอไว้เหนือรายการเพื่อคงพื้นที่แก้ไขที่อ่านง่าย

- คลิก “เล่นช่วงนี้” เพื่อฟังเฉพาะ subtitle นั้น
- ระหว่างเล่น ระบบจะ highlight cue ปัจจุบันและแสดง subtitle overlay บนวิดีโอ
- การแก้ข้อความหรือเวลาในรายการด้านขวาจะอัปเดต overlay ทันทีโดยไม่เรียก FFmpeg
- กด `Aa` เพื่อปรับขนาด เส้นขอบ พื้นหลัง เงา ตำแหน่งแนวตั้ง และระยะจากขอบแบบทศนิยม; ระบบจำค่าล่าสุดและพรีวิวตามพื้นที่เฟรมจริงด้วยสเกล SRT/ASS ของ FFmpeg
- บน desktop วิดีโอและ toolbar ของ Editor จะคงอยู่ขณะเลื่อนรายการ cue ซึ่งมีพื้นที่ scroll แยกต่างหาก
- คลิกข้อความที่แสดงบนวิดีโอหรือหมายเลข cue เพื่อไปยัง cue ที่เกี่ยวข้อง
- แก้ข้อความหรือเวลาในรูปแบบ `HH:MM:SS,mmm`
- ใช้ “แยก” เพื่อแบ่ง cue ณ ตำแหน่ง playback ปัจจุบัน หรือกึ่งกลาง cue
- ใช้ “รวมถัดไป” เพื่อนำข้อความและเวลาของ cue ถัดไปมารวม
- บันทึกก่อนดาวน์โหลด ระบบจะ validate SRT ที่ backend อีกครั้ง
- “คืนค่าต้นฉบับ” จะ validate ผลลัพธ์แรกจาก Whisper และเขียนกลับแบบ atomic เพื่อไม่ให้ผู้อ่านเห็นไฟล์ครึ่งหนึ่ง

## การสร้างวิดีโอพร้อมซับ

เลือกฟอนต์ ขนาด เส้นขอบ พื้นหลัง เงา ตำแหน่ง และระยะจากขอบ แล้วกด “สร้างวิดีโอพร้อมซับ” ระบบจะ validate ค่ารูปแบบทั้งหมด (รวมค่าทศนิยมสูงสุด 2 ตำแหน่ง) และบันทึก SRT ล่าสุด สร้างสำเนา SRT เฉพาะงาน และใช้ FFmpeg/libass เผาคำบรรยายลงในวิดีโอ H.264/AAC MP4 เมื่อเสร็จแล้วสามารถพรีวิวไฟล์จริงและดาวน์โหลดได้จากหน้าเดิม

- ฟอนต์เริ่มต้นคือ `Leelawadee UI`; รายการปัจจุบันมี Tahoma, Segoe UI และ Arial และเพิ่มรายการใหม่ได้จาก `SUBTITLE_FONTS` ใน backend
- ไฟล์ที่เลือกจากเครื่องจะถูกอ่านโดยตรงและไม่ถูกลบ
- สำหรับไฟล์ที่อัปโหลด browser จะส่งไฟล์เดิมอีกครั้งตอนเริ่ม render; สำเนาสำหรับ render จะถูกลบเมื่อจบ ยกเลิก หรือผิดพลาด
- การยกเลิก render จะ terminate process tree และลบ MP4/SRT ชั่วคราวที่ยังไม่สมบูรณ์

Keyboard shortcuts:

- `Space` เล่น/หยุด media เมื่อไม่ได้พิมพ์ในช่องข้อความ
- `Ctrl+S` บันทึก
- `Ctrl+Z` Undo
- `Ctrl+Y` หรือ `Ctrl+Shift+Z` Redo

Quality checks เป็นคำเตือนเพื่อช่วยตรวจ ไม่ได้แก้ข้อความเองหรือขัดขวางการบันทึก ยกเว้นโครงสร้างพื้นฐานที่ทำให้ SRT ใช้งานไม่ได้ เช่น เวลาสิ้นสุดก่อนเวลาเริ่มหรือข้อความว่าง

## สมุดคำศัพท์

สมุดคำศัพท์เก็บใน `data/glossary.json` และใช้งานสองแบบ:

1. กด “ใช้กับคำบรรยายนี้” เพื่อ Find/Replace คำที่ระบบฟังผิดใน Editor โดยมี confirmation ก่อนแก้
2. นำรายการ “คำที่ถูกต้อง” ส่งให้ whisper.cpp ผ่าน `--prompt` เพื่อช่วยให้ระบบรู้จักคำเหล่านั้นในงานถัดไป

ตัวอย่าง:

```text
พรีเมียโปร -> Premiere Pro
โอเพ่นเอไอ -> OpenAI
```

สมุดคำศัพท์รองรับสูงสุด 500 รายการ คำซ้ำแบบไม่สนตัวพิมพ์เล็ก/ใหญ่จะถูกปฏิเสธ และไม่ควรเก็บข้อมูลลับในไฟล์นี้หากมีการแชร์โฟลเดอร์โปรแกรม ระบบบันทึกอัตโนมัติเมื่อกรอกคำในช่องซ้าย เขียนไฟล์แบบ atomic และรองรับการนำเข้า/ส่งออก JSON รวมถึงนำเข้า text/CSV แบบสองคอลัมน์ หากเว้นช่องคำที่ถูกต้องว่าง ระบบจะลบคำทางซ้ายออกจากคำบรรยายเมื่อใช้สมุดคำ และจะไม่นำรายการลบไปสร้าง Whisper prompt
## การทดสอบ

ชุดทดสอบที่ไม่ต้องดาวน์โหลดโมเดลหรือเรียก FFmpeg จริง:

```powershell
.\venv\Scripts\python.exe -m unittest scratch.test_app_unit -v
```

ตรวจ syntax:

```powershell
.\venv\Scripts\python.exe -m py_compile app.py download_whisper.py
```

ไฟล์ `scratch/test_app.py` เป็น integration test แบบเดิม ซึ่งต้องเปิด server และมี dependency จริงก่อน จึงอาจดาวน์โหลดโมเดลและใช้เวลานาน

## โครงสร้างสำคัญ

```text
app.py                     Flask API, job state, cancellation และ workers
templates/index.html        โครงหน้า UI
static/styles.css           รูปแบบ responsive ของหน้าและ Editor
static/app.js               upload, transcription, Editor, glossary และ quality checks
scratch/test_app_unit.py    automated unit/API tests
scratch/test_app.py         manual integration test เดิม
bin/Release/                whisper.cpp executables และ DLLs
models/                     โมเดล GGML (ไม่ควร commit)
uploads/                    ไฟล์ชั่วคราว
outputs/                    SRT ปัจจุบันและสำเนา `.original.srt`
data/glossary.json          สมุดคำศัพท์ถาวรของผู้ใช้
data/preferences.json       โมเดล ภาษา threads ธีม และรูปแบบซับล่าสุด
data/editor-backup.json     คำบรรยายสำรองล่าสุดสำหรับ crash recovery
update.log.md               ประวัติการเปลี่ยนแปลง
AGENTS.md                   แนวทางสำหรับผู้พัฒนาและ coding agents
```

## Cancellation contract

สถานะงานถอดเสียง:

```text
queued -> converting -> transcribing -> completed
   |          |              |
   +----------+--------------+-> cancelling -> cancelled

ข้อผิดพลาดที่ไม่ใช่การยกเลิก -> failed
```

- `POST /api/transcribe/<task_id>/cancel` เป็น idempotent สำหรับงานที่กำลังยกเลิก
- `POST /api/models/<filename>/cancel` ยกเลิก download stream และลบ `.tmp`
- `POST /api/video-render/<task_id>` เริ่มสร้าง MP4 พร้อมซับ และ `POST /api/video-render/<render_id>/cancel` ยกเลิกแบบ idempotent
- Browser ใช้ `XMLHttpRequest.abort()` สำหรับช่วง upload ที่ยังไม่ได้ task ID
- Backend เก็บ cancel token และ process handle ไว้ใน key ที่ขึ้นต้นด้วย `_` ซึ่งจะไม่ถูก serialize ออก API
- งานที่ `completed`, `failed` หรือ `cancelled` แล้วจะไม่ถูกเปลี่ยนสถานะเมื่อกดยกเลิกภายหลัง

## ข้อจำกัดปัจจุบัน

- Job state อยู่ใน memory และหายเมื่อปิดโปรแกรม
- เหมาะกับ local single-process เท่านั้น ไม่ควรรัน Flask หลาย worker
- Portable mode อนุญาตถอดเสียงครั้งละหนึ่งงาน เพื่อควบคุม CPU, RAM และพื้นที่ดิสก์
- Upload cancellation ฝั่ง browser หยุดการส่งข้อมูล แต่ Flask/Werkzeug เป็นผู้จัดการ multipart temporary data ก่อนเข้า route
- การตรวจไฟล์ทำก่อนเริ่มงานด้วย `ffprobe`; upload ขนาดใหญ่มากยังไม่เหมาะกับ server และควรใช้ตัวเลือกไฟล์จากเครื่องใน portable mode
- Media preview อาศัย File object ใน browser จึงไม่สามารถเปิด Editor เดิมหลัง refresh หน้าได้
- Browser อาจเล่น codec/container ต้นฉบับบางชนิดไม่ได้ แม้ FFmpeg จะอ่านและสร้าง MP4 ผลลัพธ์ได้
- Portable `.exe` build พร้อมใช้งานผ่าน `build_portable.ps1`


หากเครื่องอื่นแจ้งว่าไม่พบ folder/module ตอนเริ่มถอดเสียง ให้เปิด endpoint นี้ในเครื่องนั้นเพื่อดู path ที่ executable ใช้:

```text
http://127.0.0.1:<port>/api/diagnostics
```

รุ่น portable จะตรวจ FFmpeg และ whisper.cpp ก่อนรับงาน และแสดงชื่อ component/path ที่มีปัญหาแทน error กว้างๆ ของ Windows
## Portable EXE ที่สร้างแล้ว

Build artifact อยู่ที่:

```text
dist/FreeSRT/FreeSRT.exe
dist/FreeSRT-portable.zip
```

ผู้ใช้เพียงแตก `FreeSRT-portable.zip` แล้วเปิด `FreeSRT.exe` ได้เลย ไม่ต้องติดตั้ง Python, Flask, FFmpeg, whisper.cpp, CUDA Toolkit หรือ Vulkan SDK เพิ่ม (ยังต้องมี driver การ์ดจอจากผู้ผลิต) โปรแกรมจะเลือก loopback port ว่าง เปิด browser และเก็บข้อมูลผู้ใช้ในโฟลเดอร์ข้าง executable:

- `models/` โมเดลที่ดาวน์โหลด
- `outputs/` SRT ที่สร้างและสำเนาต้นฉบับ
- `uploads/` ไฟล์ชั่วคราวระหว่างประมวลผล
- `gpu-runtimes/` — CUDA และ Vulkan runtime ที่มากับ Portable ZIP หลัก
- `data/glossary.json` สมุดคำศัพท์
- `data/preferences.json` ค่าที่ใช้ล่าสุด
- `data/editor-backup.json` ข้อมูลกู้คืนคำบรรยายที่ยังแก้ไม่เสร็จ

Build script จะสำรองไฟล์ JSON ของผู้ใช้ก่อนสร้าง dist/FreeSRT ใหม่ คืนข้อมูลให้ executable ที่ใช้ทดสอบหลัง build และสร้าง ZIP ก่อนคืนข้อมูลเพื่อไม่บรรจุข้อมูลส่วนตัวลง release นอกจากนี้ build จะหยุดทันทีหากพบ whisper test executable, DLL นอก CPU runtime allow-list หรือ CPU backend DLL กลุ่ม AVX-512 (`cascadelake`, `skylakex`, `icelake`, `cannonlake`) ใน runnable package.

Build ซ้ำด้วย:

```powershell
.\build_portable.ps1
```

ใช้รูปแบบ one-folder แทน one-file เพราะ binary/DLL มีขนาดใหญ่ และทำให้ข้อมูลที่ผู้ใช้สร้างไม่ปะปนกับ runtime ภายใน executable

โมเดลยังไม่รวมใน ZIP เพื่อควบคุมขนาดและเปิดให้ผู้ใช้เลือกตาม RAM/ความเร็วเครื่อง หากต้องใช้งาน offline ให้คัดลอกไฟล์โมเดล GGML ไปยัง `models/` ก่อนเปิดโปรแกรม

การแจกจ่าย FFmpeg ต้องปฏิบัติตาม license/notice ของ build FFmpeg ที่นำมาใช้ด้วย

## Job safety และการรองรับอุปกรณ์ต่างสเปก (2026-07-30)

งานถอดเสียงและงานสร้างวิดีโอใช้ API แบบ reserve-first เพื่อให้ browser ได้ ID ที่ยกเลิกได้ก่อนเริ่มส่งไฟล์หรือตรวจ preflight:

- `POST /api/transcribe/reservations` คืน `task_id` และสถานะ `reserved`
- `POST /api/transcribe?task_id=<task_id>` claim ID แบบใช้ครั้งเดียวแล้วเริ่มงาน
- `POST /api/video-render/<task_id>/reservations` คืน `render_id`
- `POST /api/video-render/<task_id>?render_id=<render_id>` claim ID แล้วเริ่ม render
- การเรียก start endpoint โดยไม่ reserve ก่อนจะได้ HTTP 428 พร้อม code `reservation_required`; ID ที่หมดอายุ ถูกยกเลิก หรือถูก claim แล้วจะนำกลับมาใช้ไม่ได้

Cancel endpoint เดิมใช้ได้ตั้งแต่สถานะ `reserved`, `uploading`, `preflighting`, `queued` ไปจนถึง process ทำงานอยู่ การยกเลิกซ้ำยังปลอดภัย และ terminal job จะไม่ถูกเปลี่ยนย้อนหลัง Upload copy และ subprocess preflight ตรวจ cancellation token ระหว่างทำงาน

If multipart parsing is interrupted by a browser disconnect, the claimed job is finalized as `cancelled`; malformed multipart input is finalized as `failed`, so neither case can block later work.

สำหรับไฟล์จากเครื่อง path จริงถูกเก็บเป็น internal metadata เท่านั้น Log/error จะถูก redact ก่อนจัดเก็บและ `public_state()` ตรวจซ้ำแบบ recursive ก่อนตอบ API โดยรองรับความต่างของตัวพิมพ์ใหญ่/เล็กและ slash บน Windows

ก่อน render โปรแกรมประเมิน MP4 แบบ conservative จากค่าที่มากกว่าระหว่างขนาด source คูณสองกับ resolution-duration bitrate แล้วบวก safety margin และ emergency floor การตรวจใช้ volume ของ `OUTPUT_FOLDER` โดยตรง หาก duration/resolution ไม่ครบจะไม่เริ่มงาน และระหว่าง FFmpeg ทำงานจะหยุด process tree พร้อมลบ partial MP4 เมื่อพื้นที่ต่ำกว่า emergency floor

นโยบายไฟล์ runtime อยู่ที่ `freesrt/runtime_policy.py` แห่งเดียว ทั้ง UI GPU installer, `FreeSRT.spec` และ `build_portable.ps1` ใช้ allow-list เดียวกัน Archive จะ extract เฉพาะ `whisper-cli.exe` และ DLL ที่อนุมัติ ไม่ติดตั้งเครื่องมืออื่นหรือ AVX-512 CPU DLL

GPU runtime DLLs use a finite backend-specific inventory: common whisper/ggml CPU DLLs, the selected accelerator DLL, and narrowly version-shaped CUDA dependencies. Any other DLL rejects the archive before promotion.

`build_portable.ps1` สร้างทุกอย่างใน `build/portable-staging/<id>` และเก็บ user JSON ไว้ใน `build/portable-recovery/<id>` ก่อนเริ่ม build ZIP ถูกสร้างและตรวจว่าไม่มีข้อมูลส่วนตัวก่อน restore JSON เข้า runnable staged folder; `dist/FreeSRT` จะถูก promote หลัง validation เท่านั้น และ rollback ของ runnable/ZIP เดิมจะถูกเก็บไว้หากมีอยู่ ดูรายละเอียดและ recovery test ใน `PORTABLE_BUILD.md`
