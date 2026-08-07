# แนวทางเพิ่ม GPU Acceleration สำหรับ Free SRT
> อัปเดตการตัดสินใจ 2026-07-24: รุ่นแจกจ่ายหลักเปลี่ยนเป็น all-in-one โดยแนบ CPU, CUDA 11.8 และ Vulkan runtime มาตั้งแต่แรก ผู้ใช้ไม่ต้องดาวน์โหลด runtime เพิ่มเองอีก ส่วน CPU-only ZIP ยังคงมีเป็นทางเลือกขนาดเล็กกว่า แนวทางดาวน์โหลดเพิ่มด้านล่างยังคงใช้เป็น fallback หาก runtime ถูกลบหรือผู้ดูแลต้องการเปลี่ยน URL ภายหลัง

## สรุปแนวทาง

Free SRT จะแจก `FreeSRT-portable.zip` รุ่นหลักแบบ all-in-one ซึ่งรวม `whisper.cpp` รุ่น CPU, CUDA 11.8 และ Vulkan เพื่อให้ผู้ใช้แตกไฟล์แล้วใช้งานได้ทันที ส่วน `FreeSRT-portable-CPU.zip` เป็นทางเลือกขนาดเล็กสำหรับเครื่องที่ไม่ต้องใช้ GPU

เมื่อโปรแกรมตรวจพบ GPU จะเลือก backend ที่เหมาะสมและ probe runtime ที่แนบมา โดยยัง fallback เป็น CPU หาก driver, VRAM หรือ runtime ใช้งานไม่ได้:

- NVIDIA: แนะนำ CUDA เป็นอันดับแรก และให้เลือก Vulkan ได้
- AMD: แนะนำ Vulkan
- Intel: แนะนำ Vulkan
- ไม่พบ GPU ที่รองรับ: ใช้ CPU และไม่รบกวนผู้ใช้ด้วยการดาวน์โหลดส่วนเสริม

การพบชื่อ GPU เป็นเพียงการแนะนำเบื้องต้น หลังดาวน์โหลดแล้วโปรแกรมต้องตรวจว่า backend, driver และอุปกรณ์ใช้งานกับ `whisper.cpp` ได้จริงก่อนเปิดใช้งาน GPU

## เป้าหมาย

- ทำให้ Portable ZIP หลักพร้อมใช้ทั้ง CPU, CUDA และ Vulkan โดยไม่ต้องดาวน์โหลด runtime ภายหลัง
- รักษา CPU เป็นเส้นทางที่พร้อมใช้และเป็น fallback เสมอ
- รองรับ NVIDIA ผ่าน CUDA
- รองรับ AMD, Intel และ NVIDIA ผ่าน Vulkan
- มี CPU-only ZIP ขนาดเล็กเป็นทางเลือก และคงระบบดาวน์โหลด runtime ไว้เป็น fallback
- ใช้โมเดล GGML ชุดเดิมร่วมกันระหว่าง CPU, CUDA และ Vulkan
- รักษากฎการยกเลิกงาน การ cleanup และการป้องกัน completion/cancellation race ของระบบเดิม
- ไม่เปลี่ยน FFmpeg, รูปแบบ WAV 16 kHz mono PCM หรือขั้นตอนสร้าง SRT

## สิ่งที่ยังไม่ทำในระยะแรก

- ไม่รองรับ ROCm แยกต่างหาก
- ไม่รองรับ OpenVINO encoder model
- ไม่เลือก GPU หลายใบพร้อมกัน
- ไม่ดาวน์โหลด GPU runtime โดยอัตโนมัติโดยไม่ได้รับคำยืนยัน
- ไม่รับประกันว่า GPU ทุกตัวที่ Windows ตรวจพบจะมี driver หรือ VRAM เพียงพอ
- ไม่เปลี่ยน video rendering ให้ใช้ GPU; GPU acceleration ระยะแรกใช้กับ Whisper transcription เท่านั้น

## ประสบการณ์ผู้ใช้

### ตัวเลือกหลัก

หน้าเลือกไฟล์จะแสดงตัวเลือกวิธีประมวลผล:

```text
วิธีประมวลผล

○ CPU เท่านั้น
● เร่งความเร็วด้วย GPU
```

เมื่อเลือก GPU ให้แสดง backend:

```text
GPU Backend

● อัตโนมัติ
○ NVIDIA CUDA
○ Vulkan
```

ไม่มีโหมดบังคับใช้ GPU หาก GPU ใช้ไม่ได้ โปรแกรมจะกลับไปใช้ CPU อย่างปลอดภัยและแจ้งเหตุผลใน log

### พฤติกรรมครั้งแรก

1. โปรแกรมเริ่มด้วย CPU runtime ที่มากับ Portable ZIP
2. โปรแกรมตรวจข้อมูล GPU แบบ read-only โดยไม่ดาวน์โหลดอะไร
3. หากพบ NVIDIA ให้แสดง:

   ```text
   พบ NVIDIA GPU เครื่องนี้สามารถดาวน์โหลด CUDA acceleration เพิ่มได้
   [ดาวน์โหลด CUDA] [ใช้ CPU ต่อ]
   ```

4. หากพบ AMD หรือ Intel GPU ที่รองรับ Vulkan ให้แสดง:

   ```text
   พบ GPU ที่อาจใช้ Vulkan acceleration ได้
   [ดาวน์โหลด Vulkan] [ใช้ CPU ต่อ]
   ```

5. หากพบ NVIDIA อาจแสดง Vulkan เป็นทางเลือกในรายละเอียด แต่แนะนำ CUDA ก่อน
6. หากไม่พบ GPU ที่เหมาะสม ให้เลือก CPU เท่านั้นโดยไม่แสดงคำเตือน

### ค่าเริ่มต้น

- ยังไม่มี GPU runtime: `CPU เท่านั้น`
- ติดตั้ง CUDA และ probe ผ่าน: `GPU / อัตโนมัติ` โดยเลือก CUDA
- ไม่มี CUDA แต่ติดตั้ง Vulkan และ probe ผ่าน: `GPU / อัตโนมัติ` โดยเลือก Vulkan
- GPU runtime เสีย ใช้ไม่ได้ หรือ driver เปลี่ยน: fallback เป็น CPU สำหรับงานนั้น
- หากผู้ใช้เลือก CPU เอง ให้จดจำค่าและไม่เปลี่ยนกลับเป็น GPU อัตโนมัติ
- หากผู้ใช้เลือก backend เอง ให้จดจำค่า แต่ยัง fallback เป็น CPU ได้เมื่อ backend นั้นใช้ไม่ได้

ค่าที่ผู้ใช้เลือกต้องบันทึกใต้ `DATA_FOLDER` ผ่านระบบ preferences เดิม ไม่พึ่ง browser `localStorage` เพียงอย่างเดียว

## การตรวจหา GPU

แบ่งเป็นสองระดับเพื่อไม่สรุปจากชื่อการ์ดจอเพียงอย่างเดียว

### ระดับที่ 1: Hardware hint

ใช้ Windows API เพื่ออ่าน GPU adapter และ vendor แบบ read-only:

- NVIDIA vendor ID: ใช้แนะนำ CUDA
- AMD vendor ID: ใช้แนะนำ Vulkan
- Intel vendor ID: ใช้แนะนำ Vulkan

ผลระดับนี้ใช้เพื่อแสดงคำแนะนำดาวน์โหลดเท่านั้น ห้ามถือว่า backend พร้อมใช้งานแล้ว

ควรหลีกเลี่ยงการใช้ชื่อ GPU เพียงอย่างเดียว เพราะชื่อเปลี่ยนได้และอาจมี virtual adapter หรือ Microsoft Basic Display Adapter ปะปนอยู่

### ระดับที่ 2: Runtime probe

หลังดาวน์โหลดและติดตั้ง GPU runtime:

1. ตรวจไฟล์ executable และ DLL ที่จำเป็น
2. เรียก executable ของ backend ด้วย timeout
3. ตรวจว่า backend โหลดสำเร็จและพบอุปกรณ์ชนิดที่ต้องการ
4. เมื่อมีโมเดลแล้ว ให้ทำ model-aware probe ก่อนงานจริง หรือให้การสร้าง Whisper context ตอนเริ่มงานเป็นการตรวจขั้นสุดท้าย
5. เก็บเฉพาะสถานะทั่วไป เช่น `available`, `unavailable`, `needs_driver_update` และข้อความที่ปลอดภัยต่อการแสดงผล

การ probe ต้องไม่คืน filesystem path ภายในหรือข้อมูลที่ขึ้นต้นด้วย `_` ผ่าน API

## ลำดับเลือก backend

เมื่อผู้ใช้เลือก `อัตโนมัติ`:

```text
CUDA runtime ติดตั้งแล้วและ probe ผ่าน
    -> CUDA

มิฉะนั้น Vulkan runtime ติดตั้งแล้วและ probe ผ่าน
    -> Vulkan

มิฉะนั้น
    -> CPU
```

เมื่อผู้ใช้เลือก CUDA หรือ Vulkan โดยตรง:

```text
backend ที่เลือกพร้อม
    -> ใช้ backend นั้น

backend ที่เลือกไม่พร้อม
    -> แจ้งเหตุผลและ fallback เป็น CPU
```

## โครงสร้างไฟล์

CPU runtime ยังคงเป็นส่วนหนึ่งของ resource ที่มากับโปรแกรม ส่วน GPU runtime เป็นไฟล์ที่ดาวน์โหลดภายหลังและต้องเขียนใต้ `APP_DIR` เท่านั้น

ตัวอย่าง:

```text
FreeSRT/
├─ FreeSRT.exe
├─ _internal/
│  └─ bin/
│     └─ Release/                 # CPU runtime ที่ bundle มากับโปรแกรม
├─ gpu-runtimes/
│  ├─ cuda/
│  │  └─ 1.9.1-freesrt.1/
│  │     ├─ whisper-cli.exe
│  │     ├─ whisper.dll
│  │     ├─ ggml-*.dll
│  │     └─ runtime-manifest.json
│  └─ vulkan/
│     └─ 1.9.1-freesrt.1/
│        ├─ whisper-cli.exe
│        ├─ whisper.dll
│        ├─ ggml-*.dll
│        └─ runtime-manifest.json
├─ models/
├─ outputs/
├─ uploads/
└─ data/
```

ห้ามเขียน GPU runtime ลง `RESOURCE_DIR` หรือ `sys._MEIPASS` เพราะเป็น bundled resource และอาจเป็นพื้นที่ชั่วคราวหรือเขียนไม่ได้

แยก CUDA และ Vulkan คนละโฟลเดอร์เพื่อ:

- ป้องกัน DLL จากคนละ build ชนกัน
- ป้องกัน NVIDIA ตัวเดียวถูกพบซ้ำผ่าน CUDA และ Vulkan ใน process เดียว
- เลือก executable และ environment ของแต่ละ backend ได้ชัดเจน
- ถอนหรือติดตั้ง runtime ใหม่ได้โดยไม่กระทบ CPU

## แหล่งดาวน์โหลด GPU runtime

GPU runtime ควรเป็น release asset ที่ Free SRT สร้างและทดสอบเองจาก whisper.cpp version เดียวกับ CPU runtime ไม่ควรดาวน์โหลดไฟล์ DLL แบบแยกชิ้นจากแหล่งสุ่ม

เสนอชื่อไฟล์:

```text
FreeSRT-whisper-cuda-win-x64-1.9.1-freesrt.1.zip
FreeSRT-whisper-vulkan-win-x64-1.9.1-freesrt.1.zip
```

ทุกแพ็กต้องมี:

- `whisper-cli.exe`
- DLL ที่จำเป็นสำหรับ backend นั้น
- `runtime-manifest.json`
- version ของ whisper.cpp
- Free SRT runtime revision
- architecture
- backend
- SHA-256 ของไฟล์สำคัญ
- license และ third-party notices ที่จำเป็น

ข้อมูล catalog ในแอปควรมี single source of truth เช่น `GPU_BACKENDS_INFO`:

```python
GPU_BACKENDS_INFO = {
    "cuda": {
        "name": "NVIDIA CUDA",
        "url": "...",
        "size": "...",
        "sha256": "...",
        "version": "1.9.1-freesrt.1",
        "vendors": ["nvidia"],
    },
    "vulkan": {
        "name": "Vulkan",
        "url": "...",
        "size": "...",
        "sha256": "...",
        "version": "1.9.1-freesrt.1",
        "vendors": ["nvidia", "amd", "intel"],
    },
}
```

URL, checksum และ version ต้องถูก allow-list ฝั่ง backend ผู้ใช้หรือ browser ห้ามส่ง URL ดาวน์โหลดเอง

## การดาวน์โหลดและติดตั้ง

ใช้รูปแบบเดียวกับ model download แต่แยก state และ directory:

1. ดาวน์โหลดเป็นไฟล์ `.tmp`
2. รองรับ progress, cancellation และ repeated cancellation
3. ตรวจ SHA-256 ก่อนเปิด archive
4. ตรวจสมาชิกทุกไฟล์ใน ZIP เพื่อป้องกัน path traversal/Zip Slip
5. แตกไปยัง staging directory ใต้ `gpu-runtimes/.tmp/`
6. ตรวจ manifest, executable และ DLL
7. probe runtime จาก staging directory
8. finalize ด้วย atomic rename/replace เท่าที่ Windows รองรับ
9. เมื่อยกเลิกหรือล้มเหลว ลบ archive `.tmp`, staging directory และไฟล์ที่ติดตั้งไม่ครบ
10. ห้ามเปลี่ยน runtime ที่ใช้งานอยู่กลางงาน transcription

สถานะดาวน์โหลดต้องใช้ cancellation token และ response handle เช่นเดียวกับ model download และต้องไม่คืน internal state ผ่าน JSON

## API ที่เสนอ

### อ่านความสามารถและสถานะ

```http
GET /api/compute/backends
```

ตัวอย่าง response:

```json
{
  "selected_mode": "gpu",
  "selected_backend": "auto",
  "recommended_backend": "cuda",
  "hardware": {
    "gpu_detected": true,
    "vendors": ["nvidia"]
  },
  "backends": [
    {
      "id": "cpu",
      "installed": true,
      "available": true
    },
    {
      "id": "cuda",
      "installed": false,
      "available": false,
      "download_recommended": true
    },
    {
      "id": "vulkan",
      "installed": false,
      "available": false,
      "download_recommended": false
    }
  ]
}
```

อย่าส่งชื่อ driver, path หรือรายละเอียด hardware เกินความจำเป็นหาก UI ไม่ได้ใช้

### เริ่มดาวน์โหลด

```http
POST /api/compute/backends/<backend>/download
```

อนุญาตเฉพาะ `cuda` และ `vulkan`

### อ่านสถานะดาวน์โหลด

```http
GET /api/compute/backends/download-status
```

### ยกเลิกดาวน์โหลด

```http
POST /api/compute/backends/<backend>/cancel
```

ต้องปลอดภัยเมื่อเรียกซ้ำ

### ตรวจ runtime ใหม่

```http
POST /api/compute/backends/<backend>/probe
```

ใช้หลังผู้ใช้อัปเดต driver หรือเมื่อ runtime เคยถูกระบุว่าใช้ไม่ได้

## Preferences

เพิ่มข้อมูลใน preferences:

```json
{
  "compute_mode": "cpu",
  "gpu_backend": "auto",
  "gpu_prompt_dismissed": false
}
```

ค่าที่อนุญาต:

- `compute_mode`: `cpu`, `gpu`
- `gpu_backend`: `auto`, `cuda`, `vulkan`

backend ต้อง validate และ allow-list ฝั่ง Flask เสมอ

`gpu_prompt_dismissed` ควรมีวิธีเปิดคำแนะนำกลับมาได้จากหน้าตั้งค่า

## การส่งค่างาน transcription

เพิ่ม form fields:

```text
compute_mode=cpu|gpu
gpu_backend=auto|cuda|vulkan
```

backend ต้อง:

1. validate ค่า
2. resolve runtime ที่พร้อมใช้
3. บันทึก backend ที่เลือกจริงไว้ใน job state
4. ไม่รับ executable path จาก browser
5. ส่งเฉพาะสถานะที่ปลอดภัยผ่าน `public_state()`

CPU threads ยังคงใช้ต่อ เพราะ FFmpeg และบางส่วนของ Whisper ยังใช้ CPU แม้เปิด GPU

## การเรียก whisper.cpp

### CPU

ใช้ CPU executable ที่ bundle มากับโปรแกรม และส่ง:

```text
--no-gpu
```

### CUDA

ใช้ executable และ DLL จากโฟลเดอร์ CUDA โดยกำหนด `cwd` และ `PATH` ให้เฉพาะ runtime นั้น

### Vulkan

ใช้ executable และ DLL จากโฟลเดอร์ Vulkan โดยกำหนด `cwd` และ `PATH` ให้เฉพาะ runtime นั้น

ไม่ควรนำ CUDA และ Vulkan directory ทั้งคู่เข้า `PATH` ของ process เดียว

คำสั่งเดิมอื่น ๆ ต้องคงไว้ โดยเฉพาะ:

- model path
- WAV input path
- `-osrt`
- output base
- language
- CPU threads
- `-pp`
- glossary ผ่าน `--prompt`

## CPU Fallback

Fallback ต้องเกิดเฉพาะเมื่อ:

- GPU backend โหลดไม่ได้
- ไม่พบ device ที่เลือก
- driver/runtime ไม่รองรับ
- GPU allocation หรือ VRAM ไม่เพียงพอ
- GPU process หยุดก่อนสร้าง SRT และ error ถูกจัดประเภทว่าเกี่ยวกับ GPU

ก่อน fallback:

1. ตรวจ cancellation token
2. terminate process tree เดิม
3. ล้าง `_process` ภายใต้ `state_lock`
4. ลบ SRT บางส่วนและไฟล์ชั่วคราวของรอบ GPU
5. เพิ่ม log ที่อ่านเข้าใจง่าย
6. เริ่ม CPU process ใหม่

ตัวอย่าง log:

```text
กำลังถอดเสียงด้วย NVIDIA CUDA...
CUDA ใช้งานกับโมเดลนี้ไม่ได้หรือหน่วยความจำไม่เพียงพอ
กำลังลองใหม่ด้วย CPU...
```

ห้าม fallback เมื่อ:

- ผู้ใช้ยกเลิกงาน
- input หรือ WAV ไม่ถูกต้อง
- model เสียหรือหาไม่พบ
- glossary/prompt validation ล้มเหลว
- error ไม่เกี่ยวกับ GPU

Cancellation ระหว่าง GPU, ระหว่าง cleanup และก่อนเริ่ม CPU fallback ต้องจบเป็น `cancelled` เสมอ ไม่ใช่ `failed`

## Job state และ diagnostics

เพิ่ม public fields ที่จำเป็น:

```json
{
  "compute_backend": "cuda",
  "compute_label": "NVIDIA CUDA",
  "used_cpu_fallback": false
}
```

เก็บ path, process handle, cancellation token และ probe details เป็น key ที่ขึ้นต้นด้วย `_`

หน้า diagnostics อาจรายงาน:

- CPU runtime พร้อมหรือไม่
- CUDA runtime ติดตั้งหรือไม่
- CUDA probe ผ่านหรือไม่
- Vulkan runtime ติดตั้งหรือไม่
- Vulkan probe ผ่านหรือไม่
- runtime version

ห้ามเปิดเผย absolute user paths หรือข้อมูลที่ไม่จำเป็น

## Packaging

Portable ZIP หลักรวม:

- FreeSRT executable และ Python runtime
- frontend/templates
- CPU whisper runtime
- CUDA 11.8 whisper runtime
- Vulkan whisper runtime
- FFmpeg และ ffprobe

ไม่รวม model files, downloaded archives/cache หรือ user preferences ส่วน `FreeSRT-portable-CPU.zip` จะไม่รวม CUDA/Vulkan เพื่อเป็นทางเลือกขนาดเล็ก

`FreeSRT.spec` ยังคง bundle เฉพาะ CPU runtime ใน resource directory แล้ว `build_portable.ps1` วาง GPU runtimes ใต้ writable `APP_DIR/gpu-runtimes` ก่อนสร้าง ZIP หลัก

build/release process สร้าง:

1. `FreeSRT-portable.zip` (CPU + CUDA + Vulkan)
2. `FreeSRT-portable-CPU.zip`
3. runtime manifest และ checksum ในแต่ละ backend

## ความปลอดภัยและความน่าเชื่อถือ

- ใช้ HTTPS
- pin URL, version และ SHA-256 ใน catalog
- ปฏิเสธ checksum ที่ไม่ตรง
- ป้องกัน Zip Slip และ symlink/reparse-point escape
- ไม่ execute runtime ก่อนตรวจ manifest และ checksum
- จำกัดชนิดไฟล์และ archive layout
- ใช้ staging directory ใต้ APP_DIR เท่านั้น
- ไม่เขียนใน resource directory
- ไม่ให้ browser ระบุ URL, path หรือ command-line argument อิสระ
- จำกัด log จาก subprocess ไม่ให้โตไม่สิ้นสุด
- ระบุ license/redistribution notice ของ CUDA, Vulkan และ whisper.cpp ให้ครบก่อนปล่อยจริง

## การจัดการ version

CPU, CUDA และ Vulkan runtime ควรสร้างจาก whisper.cpp revision เดียวกัน

เมื่อ Free SRT อัปเดต:

- ตรวจ compatibility ของ GPU runtime ที่ติดตั้งอยู่
- หาก compatible ให้ใช้ต่อ
- หากไม่ compatible ให้ปิด GPU ชั่วคราวและเสนออัปเดต runtime
- ดาวน์โหลดรุ่นใหม่ไป staging ก่อน
- อย่าลบ runtime รุ่นเดิมจนกว่ารุ่นใหม่จะ probe ผ่าน
- หากอัปเดตไม่สำเร็จ ให้ CPU ยังใช้งานได้

## แผนแก้ไขโค้ด

ไฟล์และส่วนที่คาดว่าจะเกี่ยวข้อง:

- `app.py`
  - runtime paths
  - backend catalog
  - environment/probe helpers
- `freesrt/workers.py`
  - GPU runtime download
  - executable selection
  - classified CPU fallback
- `freesrt/routes/transcription.py`
  - backend status/download/cancel/probe endpoints
  - transcription form validation
- preferences route/module
  - `compute_mode`
  - `gpu_backend`
  - prompt dismissal
- `templates/index.html`
  - compute mode
  - backend selection
  - GPU runtime download UI
- `static/app.js`
  - detection/status rendering
  - download progress
  - preference persistence
  - transcription form fields
- `FreeSRT.spec`
  - ยืนยันว่า bundle เฉพาะ CPU runtime
- `build_portable.ps1`
  - สร้าง Portable ZIP โดยไม่รวม downloaded GPU runtimes
- GPU runtime build scripts
  - pinned CUDA build
  - pinned Vulkan build
  - manifest/checksum generation
- `README.md`
  - วิธีใช้และข้อจำกัด
- `PORTABLE_BUILD.md`
  - วิธีสร้าง runtime artifacts
- `update.log.md`
  - บันทึกการเปลี่ยนแปลง

## แผนทดสอบ

### Unit tests

- hardware hint: NVIDIA -> CUDA recommendation
- hardware hint: AMD/Intel -> Vulkan recommendation
- ไม่พบ GPU -> CPU default
- user-selected CPU ไม่ถูก auto-switch
- preferences allow-list และ persistence
- backend ID ที่ไม่รู้จักถูกปฏิเสธ
- URL จาก client ถูกละเว้น/ปฏิเสธ
- checksum ถูกและผิด
- archive path traversal ถูกปฏิเสธ
- incomplete runtime ไม่ถูก finalize
- repeated download cancellation ปลอดภัย
- public state ไม่มี key ภายใน
- CPU command มี `--no-gpu`
- CUDA command ใช้เฉพาะ CUDA runtime directory
- Vulkan command ใช้เฉพาะ Vulkan runtime directory
- glossary ยังใช้ `--prompt` ไม่ใช่ `-p`

### Fallback tests

- CUDA backend โหลดไม่ได้ -> CPU
- Vulkan backend โหลดไม่ได้ -> CPU
- GPU ไม่มี device -> CPU
- GPU allocation/VRAM failure -> CPU
- error ที่ไม่เกี่ยวกับ GPU -> failed โดยไม่ retry
- cancellation ก่อน GPU process start
- cancellation ระหว่าง GPU process
- cancellation ระหว่าง GPU cleanup
- cancellation ก่อน CPU fallback
- cancellation ระหว่าง CPU fallback
- cancellation ใกล้ GPU completion
- repeated cancellation
- partial SRT ถูกลบก่อน fallback
- original SRT ถูกสร้างจากผลสำเร็จครั้งแรกเท่านั้น
- terminal job ไม่ถูก late cancel เปลี่ยนสถานะ

### Integration matrix

- Windows ไม่มี GPU runtime
- NVIDIA + CUDA
- NVIDIA + Vulkan
- NVIDIA มี CUDA runtime แต่ driver ใช้ไม่ได้
- AMD + Vulkan
- Intel integrated GPU + Vulkan
- เครื่องมีหลาย GPU
- GPU VRAM ไม่พอกับโมเดลใหญ่
- Portable folder path มีช่องว่างและอักษรไทย
- clean Windows ที่ไม่มี Python หรือ developer tools

### Regression commands

ก่อนส่งมอบการเปลี่ยนแปลงต้องรัน:

```powershell
.\venv\Scripts\python.exe -m py_compile app.py download_whisper.py
.\venv\Scripts\python.exe -m unittest scratch.test_app_unit -v
```

ห้ามรัน `scratch/test_app.py` โดยไม่ตั้งใจ เพราะอาจดาวน์โหลดโมเดล

## ลำดับการพัฒนา

### ระยะที่ 1: Backend abstraction

- แยกการเลือก executable/environment ออกจาก transcription command
- เพิ่ม CPU mode และ `--no-gpu`
- เพิ่ม tests โดยยังไม่ดาวน์โหลด GPU runtime

### ระยะที่ 2: Detection และ UI

- เพิ่ม hardware hint
- เพิ่ม compute preferences
- เพิ่ม UI สองโหมดและ backend selector
- ค่าเริ่มต้นยังเป็น CPU

### ระยะที่ 3: Runtime download

- เพิ่ม catalog, download, checksum, staging และ cancellation
- เพิ่ม CUDA/Vulkan probe
- เพิ่ม download progress UI

### ระยะที่ 4: GPU transcription และ fallback

- เชื่อม CUDA/Vulkan executable
- เพิ่ม error classification
- เพิ่ม atomic cleanup และ CPU fallback
- เพิ่ม job status/log

### ระยะที่ 5: Release pipeline

- สร้างและทดสอบ CUDA/Vulkan artifacts
- เพิ่ม checksums และ notices
- ทดสอบ clean-machine matrix
- อัปเดตเอกสารและ release checklist

## เกณฑ์ยอมรับ

งานถือว่าเสร็จเมื่อ:

- Portable ZIP หลักยังถอดเสียงด้วย CPU ได้โดยไม่ดาวน์โหลดส่วนเพิ่ม
- โปรแกรมไม่ดาวน์โหลด GPU runtime จนกว่าผู้ใช้จะยืนยัน
- NVIDIA ได้รับคำแนะนำ CUDA และยังเลือก Vulkan ได้
- AMD/Intel ได้รับคำแนะนำ Vulkan
- GPU runtime ทุกแพ็กผ่าน checksum และ archive validation
- GPU ที่ probe ผ่านสามารถสร้าง SRT ด้วยโมเดลเดิมได้
- GPU ที่ใช้ไม่ได้ fallback เป็น CPU พร้อม log ที่เข้าใจง่าย
- การยกเลิกทุกช่วงจบเป็น `cancelled`
- ไม่มี partial SRT, WAV, upload หรือ runtime `.tmp` ค้างหลัง failure/cancellation
- internal state และ filesystem paths ไม่รั่วผ่าน API
- build หลักไม่รวม GPU runtime หรือข้อมูลผู้ใช้
- unit tests, portable build และ clean-machine smoke tests ผ่าน

