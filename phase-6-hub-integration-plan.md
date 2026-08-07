# Phase 6 — Hub Integration รอบใหม่: Implementation Plan

> Historical implementation plan. The current adapter contract is documented in `hub/PLUGIN_CONTRACT.md`; entry points return `PluginRegistration` and never receive the Hub Flask app.

> สถานะ: Revised — architecture decisions resolved  
> วันที่จัดทำ: 2026-08-04  
> ปรับปรุง: 2026-08-05  
> อ้างอิง: [standalone-first-rework-plan.md](./standalone-first-rework-plan.md) § Phase 5–6  
> Milestone เป้าหมาย: **M6** — Hub adapter + packaged integration tests

---

## 1. เป้าหมายและหลักการ

เชื่อม FreeSRT เข้ากับ Tools Hub ผ่าน adapter บาง ๆ โดย:

- standalone ยังคงเป็นเส้นทางหลักและใช้ `app = create_app()` ได้เหมือนเดิม
- domain logic ไม่ import Hub
- Hub mount FreeSRT ที่ `/srt` โดยใช้ manifest เป็น source of truth
- plugin modules มี namespace เฉพาะและไม่พึ่ง global `sys.path` injection
- bundled resources, external plugins และ writable user data แยกจากกัน
- source-mode และ packaged-mode มี integration gates ชัดเจน

งานรอบนี้ไม่รวม marketplace, remote update manager หรือ shared worker infrastructure

### สถานะปัจจุบันที่ยืนยันจากโค้ด

| ส่วน | สถานะ |
|---|---|
| `hub/app.py` | มี Flask app และ plugin discovery แต่ paths ยังผูกกับ source/resource root |
| `hub/plugin_loader.py` | เพิ่ม plugin dir ลง `sys.path` ถาวร; submodules ยังใช้ชื่อ global |
| `plugins/free_srt/app.py` | export `app` แต่ paths/state/services เป็น module globals; ยังไม่มี injectable app factory จริง |
| `plugins/free_srt/freesrt/routes/` | มี `register_*_routes(target, services)` และสามารถรับ Blueprint เป็น target ได้ |
| FreeSRT frontend | asset/API URLs ยังอิง root; ยังไม่รองรับ `/srt` |
| manifest/adapter | ยังไม่มี |
| `ToolsHub.spec` | ยังไม่ bundle FreeSRT adapter, resources และ runtime binaries |
| Hub integration tests | ยังไม่มี |

---

## 2. Architecture Decisions

ส่วนนี้ถือว่าอนุมัติแล้วสำหรับ implementation รอบนี้

### D1 — ใช้ Flask Blueprint

- adapter สร้าง Blueprint ชื่อ unique เช่น `free_srt_plugin`
- `url_prefix` อ่านจาก manifest เท่านั้น ห้าม hardcode `/srt` ซ้ำใน adapter หรือ routes
- route factories รับ Blueprint ผ่าน `target` และรับ runtime/services แยกต่างหาก
- endpoint names ถูก scope ด้วย Blueprint name

เหตุผล: เข้ากับ Hub Flask app เดิม ใช้ test client เดียวกัน และไม่เพิ่ม WSGI dispatcher อีกชั้น

### D2 — ใช้ namespaced imports; ห้าม sys.path push/pop

- plugin contract บังคับ Python package ชื่อ globally unique เช่น `toolshub_free_srt`
- modules ภายในใช้ relative หรือ fully-qualified imports ใต้ package นี้
- loader โหลด adapter ใต้ namespace `toolshub_plugins.<plugin_id>`
- ห้ามเพิ่ม plugin directory ลง global `sys.path` ไม่ว่าชั่วคราวหรือถาวร
- plugin ID, Python package และ URL prefix ต้องไม่ซ้ำกัน

การลบ path หลัง import ไม่ถือเป็น isolation เพราะ modules ยังค้างใน `sys.modules`

### D3 — แยก resource root และ writable roots

| Root | ตัวอย่าง packaged mode | การใช้งาน |
|---|---|---|
| Bundled resource | `<_MEIPASS>/plugins/free_srt/` | templates, static, Python source, binaries |
| External plugins | `<exe-dir>/plugins/` | plugins ที่ติดตั้งภายนอกในอนาคต |
| Plugin data | `<exe-dir>/data/plugins/free_srt/` | preferences, glossary, editor backup |
| Models | `<exe-dir>/models/free_srt/` | Whisper models |
| Runtime | `<exe-dir>/runtimes/free_srt/` | downloaded GPU runtimes |
| Uploads | `<exe-dir>/uploads/free_srt/` | browser uploads และไฟล์ชั่วคราว |
| Outputs | `<exe-dir>/outputs/free_srt/` | SRT และวิดีโอผลลัพธ์ |

- bundled และ external roots ถูกค้นหาแยกกัน
- duplicate ID ระหว่างสอง roots ถูกปฏิเสธใน Phase 6; ยังไม่มี override/update semantics
- การถอนหรืออัปเดต plugin ห้ามลบ writable roots
- tests ใช้ temporary writable roots และไม่เขียนลง source tree

### D4 — Frontend ใช้ base-path contract

- backend ส่ง base path ให้ template เช่น `window.FREESRT_BASE_URL`
- static assets ใช้ Blueprint-aware `url_for()`
- frontend มี helper กลาง `pluginUrl(path)` สำหรับ API, media และ downloads
- หน้า `/srt/` ต้องไม่มี request หลุดไป `/api/*` หรือ `/static/*`
- standalone ใช้ base path ว่าง จึงรักษา URLs เดิม

---

## 3. ลำดับงาน

### Step 0 — Phase 5a prerequisite: app factory และ runtime context

ต้องเสร็จก่อนสร้าง Hub adapter เพราะ routes ปัจจุบันพึ่ง module globals ใน `app.py`

#### [MODIFY] `plugins/free_srt/app.py`

เพิ่ม contract:

```python
def create_app(config=None):
    runtime = create_runtime_context(config or {})
    flask_app = Flask(
        __name__,
        template_folder=runtime.resource_paths.templates,
        static_folder=runtime.resource_paths.static,
    )
    register_routes(flask_app, runtime)
    flask_app.extensions[free_srt_runtime] = runtime
    return flask_app


# Standalone compatibility contract
app = create_app()
```

ข้อกำหนด:

- ย้าย paths, state dictionaries, locks และ worker dependencies เข้า instance-scoped runtime context/services facade
- แยก resource, data, model, output, upload และ runtime roots อย่างชัดเจน
- ห้ามเปลี่ยน domain behavior, cancellation semantics หรือ cleanup invariants
- compatibility exports เดิมอาจคงชั่วคราว แต่ app instance ใหม่ต้องไม่พึ่งการ patch module globals
- เพิ่ม tests สร้างสอง app instances ด้วย temp roots แยกกันและยืนยันว่า state/files ไม่รั่ว

#### [MODIFY] `plugins/free_srt/freesrt/routes/*.py`

- เปลี่ยนชื่อ argument แรกจาก `app` เป็น `target` เพื่อรับ Flask app หรือ Blueprint
- ทุก route ใช้ runtime/services ที่ได้รับมา
- template route ส่ง base URL และใช้ Blueprint-aware `url_for()`

#### Gate

```powershell
cd plugins/free_srt
.\venv\Scripts\python.exe -m py_compile app.py download_whisper.py
.\venv\Scripts\python.exe -m unittest scratch.test_app_unit -v
```

ห้ามเริ่ม Step 1 หาก standalone gate หรือ app-instance isolation tests ยังไม่ผ่าน

---

### Step 1 — กำหนดและตรวจ plugin contract ใน Hub loader

#### [MODIFY] `hub/plugin_loader.py`

- ลบ `sys.path.insert()` ทั้งหมด
- validate manifest และปฏิเสธ duplicate plugin ID, package name และ URL prefix ก่อน register route
- โหลด package ที่ manifest ประกาศด้วย `spec_from_file_location()` และ `submodule_search_locations=[package_dir]` ภายใต้ชื่อ unique ที่ประกาศ โดยไม่แก้ `sys.path`
- หลัง package พร้อมแล้วจึงโหลด adapter เป็น `toolshub_plugins.<plugin_id>` ด้วย `importlib`
- เรียก `register(app, plugin_dir, manifest, hub_paths)` ให้ signature ตรงกันทุกจุด
- mark `_loaded=True` หลัง register สำเร็จเท่านั้น
- หาก import/validation ล้มก่อน register ให้ถอนเฉพาะ modules ใน namespace ของ plugin นั้นออกจาก `sys.modules`

Adapter ต้อง validate config/resources ก่อน และเรียก `app.register_blueprint()` เพียงครั้งเดียวเป็น side effect ขั้นสุดท้าย เพราะ Flask rollback partial route registration ได้ไม่ปลอดภัย

#### [MODIFY] `hub/app.py`

- เพิ่ม `create_app(config=None)` เพื่อให้ tests inject roots ได้
- แยก `BUNDLED_PLUGINS_DIR`, `EXTERNAL_PLUGINS_DIR` และ `HUB_DATA_DIR`
- source และ frozen mode resolve roots ด้วยกติกาเดียวกัน
- คง `app = create_app()` สำหรับ launcher ปัจจุบัน

---

### Step 2 — สร้าง FreeSRT manifest

#### [NEW] `plugins/free_srt/plugin.json`

```json
{
  "id": "free_srt",
  "name": "FreeSRT",
  "description": "ถอดเสียงและแก้ไข subtitle ด้วย Whisper.cpp",
  "icon": "🎬",
  "version": "4.0.0",
  "adapter_version": "1.0.0",
  "url_prefix": "/srt",
  "entry_point": "__init__:register",
  "python_package": "toolshub_free_srt",
  "bundled": true
}
```

ชื่อ writable directories ไม่อยู่ใน manifest ของ plugin package; Hub สร้างและส่ง absolute roots ที่ผ่าน validation เข้า adapter

---

### Step 3 — สร้าง namespaced FreeSRT package และ Hub adapter

#### [NEW/MOVE] `plugins/free_srt/toolshub_free_srt/`

- ย้าย `freesrt/` เป็น package ชื่อ unique แบบ mechanical migration
- ใช้ relative imports ภายใน package
- standalone และ Hub import package เดียวกัน
- adapter ห้ามเพิ่ม alias ชื่อ generic เช่น `app` หรือ `freesrt` ลง `sys.modules`
- ห้ามเปลี่ยน domain behavior ในงานย้าย package นี้

#### [NEW] `plugins/free_srt/__init__.py`

```python
"""FreeSRT Hub adapter."""

from flask import Blueprint
from toolshub_free_srt.app_factory import (
    build_runtime_config,
    create_runtime_context,
    register_routes,
)


def register(hub_app, plugin_dir, manifest, hub_paths):
    runtime_config = build_runtime_config(
        resource_root=plugin_dir,
        data_root=hub_paths.plugin_data(manifest["id"]),
        model_root=hub_paths.plugin_models(manifest["id"]),
        runtime_root=hub_paths.plugin_runtimes(manifest["id"]),
        upload_root=hub_paths.plugin_uploads(manifest["id"]),
        output_root=hub_paths.plugin_outputs(manifest["id"]),
        url_prefix=manifest["url_prefix"],
    )
    runtime = create_runtime_context(runtime_config)
    blueprint = Blueprint(
        "free_srt_plugin",
        __name__,
        template_folder=runtime.resource_paths.templates,
        static_folder=runtime.resource_paths.static,
        static_url_path="/static",
    )
    register_routes(blueprint, runtime)

    # Validate first; route registration is the final side effect.
    hub_app.register_blueprint(
        blueprint,
        url_prefix=manifest["url_prefix"],
    )
```

ตัวอย่างนี้แสดง contract เท่านั้น การ import ต้องเกิดภายใต้ namespace ที่ loader จัดเตรียมไว้ Adapter ห้ามมี domain logic และห้าม hardcode `/srt`

---

### Step 4 — ทำ frontend ให้รองรับ base path

#### [MODIFY] `plugins/free_srt/templates/index.html`

- ใช้ `url_for('.static', filename=...)` สำหรับ CSS, JavaScript และรูปภาพเมื่ออยู่ใน Blueprint
- inject base URL ที่ escape แล้วจาก backend

#### [MODIFY] `plugins/free_srt/static/app.js`

- เพิ่ม helper กลาง `pluginUrl(path)`
- เปลี่ยน API, XHR, media preview และ download URLs ทุกจุดให้ผ่าน helper
- ห้ามเปลี่ยน business behavior หรือ payload schemas

#### Gate

- standalone requests ยังคงเป็น `/api/*` และ `/static/*`
- Hub requests เป็น `/srt/api/*` และ `/srt/static/*`
- เพิ่ม JavaScript test หรือ browser smoke assertion ว่าไม่มี root request หลุดจาก `/srt`

---

### Step 5 — Source-mode integration tests

#### [NEW] `hub/tests/test_hub_integration.py`

- Hub dashboard `/` → HTTP 200
- `/api/hub/plugins` มี FreeSRT ที่ `loaded: true` และ `url_prefix: /srt`
- health endpoint รายงาน FreeSRT loaded โดยไม่ผูกกับจำนวน plugins แบบตายตัว
- `/srt/` → HTTP 200 และ `/srt/api/models` → JSON list
- preferences และ glossary ใช้ GET + PUT round-trip
- editor backup ใช้ GET + PUT + DELETE round-trip
- assets จริง `/srt/static/app.js` และ `/srt/static/styles.css` → HTTP 200
- root `/api/models` และ `/static/app.js` ไม่ถูก FreeSRT จับใน Hub mode
- tests ใช้ temporary writable roots และไม่แตะ personal data

#### [NEW] `hub/tests/test_plugin_isolation.py`

- `sys.path` ไม่เปลี่ยนหลัง discovery/load
- ไม่มี generic plugin package name ถูกเพิ่มใน `sys.modules`
- plugins จำลองสองตัวที่มี internal module basename เหมือนกันโหลดพร้อมกันได้
- duplicate ID, package name และ URL prefix ถูกปฏิเสธก่อน route registration
- failure ก่อน final registration ไม่ทิ้ง partial routes

#### [NEW] `hub/tests/test_runtime_isolation.py`

- standalone และ Hub app ใช้ data/model/output roots ต่างกันได้
- app instances สองตัวไม่แชร์ jobs, locks, preferences หรือ output files

---

### Step 6 — Packaged build integration

#### [MODIFY] `ToolsHub.spec`

ต้อง bundle อย่างน้อย:

```python
datas = [
    ("hub/templates", "hub/templates"),
    ("hub/static", "hub/static"),
    ("plugins/free_srt/plugin.json", "plugins/free_srt"),
    ("plugins/free_srt/__init__.py", "plugins/free_srt"),
    ("plugins/free_srt/templates", "plugins/free_srt/templates"),
    ("plugins/free_srt/static", "plugins/free_srt/static"),
    ("plugins/free_srt/toolshub_free_srt", "plugins/free_srt/toolshub_free_srt"),
]

binaries = [
    # whisper-cli.exe, required DLLs, ffmpeg.exe และ ffprobe.exe
    # วางใต้ plugins/free_srt/bin ตาม runtime_config ที่ใช้จริง
]
```

ถ้าเลือก PyInstaller hidden imports แทน source-data loading ต้องใช้วิธีเดียวอย่างชัดเจน และ smoke test ต้องยืนยันว่า loader ใช้วิธีนั้นจริง

ห้าม bundle models, uploads, outputs, personal data, downloaded GPU runtimes หรือ build caches

#### [NEW] `hub/tests/test_packaged_hub.py` หรือ packaged smoke script

- เริ่ม built executable ใน isolated temporary directory
- รอ health endpoint แล้วตรวจ FreeSRT loaded
- ตรวจ `/srt/`, `/srt/api/models` และ assets จริง
- เรียก runtime preflight ที่ FreeSRT ใช้จริงแทนการตรวจเพียงว่า binary file มีอยู่
- เขียน preferences/glossary ลง writable root ข้าง executable และยืนยันว่าไม่เขียนใต้ `_MEIPASS`
- ปิด process และเก็บ startup log เมื่อ smoke test ล้ม

---

### Step 7 — Regression และ packaging gates

```powershell
# FreeSRT standalone
cd plugins/free_srt
.\venv\Scripts\python.exe -m py_compile app.py download_whisper.py
.\venv\Scripts\python.exe -m unittest scratch.test_app_unit -v

# Hub source-mode
cd ../..
python -m unittest discover -s hub/tests -v

# Packaged mode
# build ToolsHub แล้วรัน packaged smoke test จาก isolated temp directory
```

ห้าม merge หาก standalone, Hub source-mode หรือ packaged smoke test ล้ม

---

## 4. Acceptance Criteria

- [ ] FreeSRT ทำงานทั้ง standalone และ Hub จาก domain/runtime code ชุดเดียวกัน
- [ ] `create_app(config)` สร้าง app instances ที่มี state และ writable roots แยกกันได้
- [ ] ไม่มีการเพิ่ม plugin directory ลง global `sys.path`
- [ ] ไม่มี module collision เมื่อโหลด plugin จำลองอย่างน้อยสองตัว
- [ ] manifest เป็น source of truth ของ ID, package, version และ `/srt`
- [ ] หน้า `/srt/` ส่งทุก API/static/media/download request ใต้ `/srt`
- [ ] bundled resources, external plugins และ writable user data แยก roots กัน
- [ ] packaged ToolsHub ค้นพบ FreeSRT และเรียก runtime binaries ได้บน clean machine
- [ ] ไม่มี user data ถูกเก็บใต้ `_MEIPASS` หรือถูกลบเมื่อถอน plugin
- [ ] plugin load failure ไม่ทิ้ง partial routes ที่ดูเหมือน loaded
- [ ] standalone regression, Hub integration และ packaged smoke tests ผ่านทั้งหมด

---

## 5. Rollback Strategy

การ rollback ต้องย้อนเป็นกลุ่มตาม dependency ไม่ใช่ลบเฉพาะ adapter:

1. เก็บ standalone release/tag ก่อนเริ่ม Step 0
2. หาก Step 0 ล้ม ให้ revert app factory/runtime-context migration ทั้งชุดกลับ standalone tag โดยไม่แตะ user-data roots
3. หาก Step 1–5 ล้มหลัง Step 0 ผ่านแล้ว ให้ถอด manifest/adapter/Hub loader changes แต่คง app factory ที่ standalone tests ยืนยันแล้วได้
4. หาก packaged build ล้ม ให้ revert `ToolsHub.spec` และ packaged launcher/path resolution เท่านั้น
5. ทุก rollback ต้องรัน standalone suite ซ้ำ และห้ามลบ models, outputs, data หรือ GPU runtimes เพื่อทำให้ tests ผ่าน

Hub ต้องข้าม plugin ที่ไม่มี manifest หรือโหลดไม่สำเร็จ พร้อมแสดง error ใน `/api/hub/plugins`; standalone ต้องเปิดได้โดยไม่ import Hub

---

## 6. Implementation Order Summary

```text
Step 0: Phase 5a — app factory + instance-scoped runtime context
    ↓ standalone + instance-isolation gate
Step 1: Hub create_app + validated namespaced loader + separated roots
    ↓
Step 2: FreeSRT manifest
    ↓
Step 3: unique package namespace + Blueprint adapter
    ↓
Step 4: frontend base-path migration
    ↓
Step 5: source-mode integration/isolation tests
    ↓
Step 6: ToolsHub.spec + packaged smoke test
    ↓
Step 7: standalone + Hub + packaged regression gates
    ↓
Merge / M6 approval
```

---

## 7. ไฟล์ที่เกี่ยวข้อง

| ไฟล์ | Action | หมายเหตุ |
|---|---|---|
| `hub/plugin_loader.py` | MODIFY | validation, namespaced import, ไม่มี sys.path injection |
| `hub/app.py` | MODIFY | app factory และแยก bundled/external/data roots |
| `plugins/free_srt/plugin.json` | NEW | plugin contract |
| `plugins/free_srt/__init__.py` | NEW | thin Blueprint adapter |
| `plugins/free_srt/app.py` | MODIFY | standalone-compatible app factory |
| `plugins/free_srt/toolshub_free_srt/` | NEW/MOVE | unique Python package namespace |
| `plugins/free_srt/freesrt/` | MIGRATE | mechanical move; ห้ามเปลี่ยน domain behavior |
| `plugins/free_srt/toolshub_free_srt/routes/*.py` | MODIFY/MOVE | target + runtime/services injection |
| `plugins/free_srt/templates/index.html` | MODIFY | Blueprint static URL + base URL |
| `plugins/free_srt/static/app.js` | MODIFY | central base-path helper |
| `plugins/free_srt/scratch/test_app_unit.py` | MODIFY | factory/runtime isolation coverage |
| `ToolsHub.spec` | MODIFY | adapter, source/resources และ binaries |
| `hub/tests/test_hub_integration.py` | NEW | source-mode integration |
| `hub/tests/test_plugin_isolation.py` | NEW | namespace/duplicate/failure isolation |
| `hub/tests/test_runtime_isolation.py` | NEW | app instance และ writable-root isolation |
| `hub/tests/test_packaged_hub.py` | NEW | packaged smoke test |
| `plugins/free_srt/README.md` | MODIFY | standalone/Hub paths และ behavior |
| `plugins/free_srt/update.log.md` | MODIFY | architectural and user-visible changes |
