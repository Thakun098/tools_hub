# Tools Hub — Implementation Plan

> แผนการแปลง Free SRT จาก standalone app เป็น **Hub** ที่รวม handcraft local AI tools  
> สถานะ: **อนุมัติ** | วันที่: 2026-07-31

---

## 1. สรุปภาพรวม

### เป้าหมาย

สร้าง **Tools Hub** — launcher ที่รวม local AI tools หลายตัวเข้าด้วยกัน ทำงานแบบ "Game Launcher" pattern:

- Hub เปิดขึ้น → แสดง dashboard ของ tools ทั้งหมด
- Free SRT มา bundled เป็น default tool
- ผู้ใช้สามารถ download/install tools เพิ่มจาก GitHub Releases ได้
- ทุก tool แชร์ infrastructure ร่วมกัน (GPU detection, job queue, disk management, ฯลฯ)

### Decisions ที่ตกลงแล้ว

| หัวข้อ | ตัดสินใจ |
|--------|---------|
| Repo strategy | **Multi-repo (Option B)** — Hub เป็น repo ใหม่, Free SRT repo เดิมเก็บ archive |
| Folder naming | `free_srt` (underscore, ไม่มีเว้นวรรค) |
| URL routing | Hub dashboard อยู่ที่ `/` — Free SRT อยู่ที่ `/srt/...` |
| Plugin location | `plugins/free_srt/` subfolder ใน Hub repo |
| Distribution | Game Launcher pattern — Hub + Free SRT bundled, tools อื่น download เพิ่ม |
| Hub ชื่ออะไร | ยังไม่ตัดสินใจ — ใช้ "Tools Hub" ไปก่อนเป็น working title |

---

## 2. โครงสร้างเป้าหมาย

```
tools_hub/
│
├── hub/                              # Hub core package
│   ├── __init__.py
│   ├── app.py                        # Hub Flask app + plugin router
│   ├── launcher.py                   # Desktop launcher (port, browser, thread)
│   ├── plugin_loader.py              # Plugin discovery & Blueprint registration
│   ├── manifest.py                   # Remote/Local manifest manager
│   ├── download_manager.py           # Plugin download + checksum + install
│   │
│   ├── core/                         # Shared infrastructure (extracted from freesrt/)
│   │   ├── __init__.py
│   │   ├── compute.py                # GPU detection (Windows Registry)
│   │   ├── capacity.py               # Disk capacity checks & emergency floor
│   │   ├── diagnostics.py            # Path redaction for privacy
│   │   ├── files.py                  # Atomic JSON read/write, safe file ops
│   │   ├── jobs.py                   # Job reservation state machine
│   │   └── runtime_policy.py         # Binary security & ZIP extraction policy
│   │
│   ├── templates/
│   │   └── hub.html                  # Hub dashboard SPA
│   │
│   └── static/
│       └── hub/
│           ├── hub.js                # Dashboard frontend logic
│           └── hub.css               # Dashboard styles
│
├── plugins/
│   └── free_srt/                     # Free SRT as plugin
│       ├── plugin.json               # Plugin metadata
│       ├── __init__.py               # register(app) entry point
│       ├── app_srt.py                # SRT-specific Flask setup (from app.py)
│       │
│       ├── freesrt/                  # SRT domain logic
│       │   ├── __init__.py
│       │   ├── glossary.py           # Whisper vocabulary prompt
│       │   ├── model_catalog.py      # Whisper GGUF model catalog
│       │   ├── settings.py           # SRT-specific preferences
│       │   ├── subtitle_style.py     # Font catalog & ASS filter generator
│       │   ├── subtitles.py          # SRT parser, serializer, timestamp math
│       │   ├── workers.py            # Download, Whisper, FFmpeg workers
│       │   └── routes/
│       │       ├── __init__.py
│       │       ├── transcription.py
│       │       ├── editor.py
│       │       └── video.py
│       │
│       ├── templates/
│       │   └── index.html            # Free SRT SPA
│       ├── static/
│       │   ├── app.js
│       │   ├── styles.css
│       │   └── js/
│       │       ├── dom.js
│       │       ├── srt.js
│       │       └── state.js
│       │
│       ├── bin/                      # whisper-cli, ffmpeg (SRT-specific binaries)
│       └── models/                   # Whisper GGUF models
│
├── data/                             # Hub-level user data
│   ├── manifest_local.json           # Installed plugins registry
│   └── hub_preferences.json          # Hub-level settings
│
├── manifest_remote.json              # Dev copy of remote manifest
├── requirements.txt                  # flask, requests
├── launcher.py                       # Top-level entry point
├── ToolsHub.spec                     # PyInstaller build spec
└── hub-implementation-plan.md        # ← this file
```

---

## 3. Shared Infrastructure Mapping

ตาราง: module ไหนย้ายไป `hub/core/` (shared) — module ไหนอยู่ใน `plugins/free_srt/freesrt/` (SRT-specific)

| Module เดิม (`freesrt/`) | ย้ายไป `hub/core/` | อยู่ใน `freesrt/` | หมายเหตุ |
|--------------------------|:--:|:--:|-----------|
| `compute.py` | ✅ | — | GPU detection, zip validation — ลบ SRT-specific URLs ออก |
| `capacity.py` | ✅ | — | Generalize disk check — ลบ video bitrate formula |
| `diagnostics.py` | ✅ | — | ใช้ได้ตรงๆ ไม่ต้องแก้ |
| `files.py` | ✅ | — | ใช้ได้ตรงๆ ไม่ต้องแก้ |
| `jobs.py` | ✅ | — | ใช้ได้ตรงๆ ไม่ต้องแก้ |
| `runtime_policy.py` | ✅ | — | Generalize binary allow-list |
| `workers.py` | — | ✅ | SRT-specific (Whisper, FFmpeg workers) |
| `model_catalog.py` | — | ✅ | Whisper model definitions |
| `glossary.py` | — | ✅ | Whisper prompt builder |
| `subtitle_style.py` | — | ✅ | Font catalog & ASS filter |
| `subtitles.py` | — | ✅ | SRT parser & serializer |
| `settings.py` | — | ✅ | SRT-specific preferences |

---

## 4. Plugin Spec

### 4.1 `plugin.json` format

```json
{
  "id": "free_srt",
  "name": "Free SRT",
  "description": "แปลงเสียง/วิดีโอเป็นซับไตเติ้ล SRT ด้วย AI",
  "icon": "🎬",
  "version": "2.1.0",
  "entry_point": "__init__:register",
  "url_prefix": "/srt",
  "bundled": true,
  "user_data_dirs": ["output", "models", "data"]
}
```

### 4.2 Plugin entry point

```python
# plugins/free_srt/__init__.py

from flask import Blueprint

def register(app, plugin_dir):
    """Called by Hub plugin_loader to register this plugin."""
    bp = Blueprint(
        "free_srt",
        __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path="/srt/static"
    )
    # register SRT routes onto the blueprint
    # ...
    app.register_blueprint(bp, url_prefix="/srt")
```

### 4.3 Remote manifest format

```json
{
  "manifest_version": 1,
  "hub_min_version": "1.0.0",
  "plugins": [
    {
      "id": "free_srt",
      "name": "Free SRT",
      "description": "แปลงเสียง/วิดีโอเป็นซับไตเติ้ล SRT ด้วย AI",
      "icon": "🎬",
      "version": "2.1.0",
      "min_hub_version": "1.0.0",
      "size_bytes": 52428800,
      "download_url": "https://github.com/.../releases/download/free_srt-v2.1.0/free_srt.zip",
      "checksum": "sha256:...",
      "requires": ["ffmpeg"],
      "bundled": true,
      "changelog": "- เพิ่ม GPU acceleration\n- แก้ bug การ cancel งาน"
    }
  ],
  "shared_deps": {
    "ffmpeg": {
      "version": "7.1",
      "download_url": "https://github.com/.../releases/download/deps/ffmpeg-7.1-win64.zip",
      "size_bytes": 83886080,
      "checksum": "sha256:..."
    }
  }
}
```

### 4.4 Local manifest format

```json
{
  "hub_version": "1.0.0",
  "installed": {
    "free_srt": {
      "version": "2.1.0",
      "installed_at": "2026-07-31T09:00:00+07:00",
      "path": "plugins/free_srt"
    }
  },
  "installed_deps": {
    "ffmpeg": {
      "version": "7.1",
      "path": "bin/ffmpeg"
    }
  }
}
```

---

## 5. Implementation Phases

### Phase 1: Hub Shell (Foundation)

> **เป้าหมาย:** Hub เปิดได้ มี dashboard แสดง Free SRT card กดเข้าใช้งานได้  
> **ความยาก:** ⭐⭐ | **เวลา:** ~1-2 วัน

| ไฟล์ | Action | รายละเอียด |
|------|--------|-----------|
| `hub/__init__.py` | NEW | Package init |
| `hub/app.py` | NEW | Flask app หลัก, mount Free SRT blueprint, route `/` → dashboard, route `/api/hub/plugins` → plugin list |
| `hub/launcher.py` | NEW | Dynamic port + background thread + browser open (ดัดแปลงจาก `launcher.py` เดิม) |
| `hub/templates/hub.html` | NEW | Dashboard SPA — plugin card grid, dark/light theme |
| `hub/static/hub/hub.css` | NEW | Card grid layout, responsive, theme styles |
| `hub/static/hub/hub.js` | NEW | Fetch plugin list → render cards, theme toggle, navigation |
| `launcher.py` (root) | NEW | Top-level entry: `from hub.app import app` |

**ตรวจสอบ:**
- `python launcher.py` → เปิดเบราว์เซอร์ → เห็น Hub dashboard
- กด Free SRT card → ไปที่ `/srt/` → Free SRT ทำงานปกติ

---

### Phase 2: Plugin Interface & Free SRT Adaptation

> **เป้าหมาย:** กำหนด plugin spec, แปลง Free SRT เป็น plugin ที่ Hub โหลดได้อัตโนมัติ  
> **ความยาก:** ⭐⭐⭐ | **เวลา:** ~2-3 วัน

| ไฟล์ | Action | รายละเอียด |
|------|--------|-----------|
| `hub/plugin_loader.py` | NEW | Scan `plugins/` หา `plugin.json` → dynamic import → register blueprint |
| `plugins/free_srt/plugin.json` | NEW | Plugin metadata (id, name, version, entry_point, url_prefix) |
| `plugins/free_srt/__init__.py` | NEW | `register(app, plugin_dir)` — สร้าง Blueprint, register routes |
| `plugins/free_srt/app_srt.py` | ADAPT | SRT-specific code จาก `app.py` เดิม (ลบ shared infrastructure ออก) |
| `plugins/free_srt/freesrt/routes/*.py` | MODIFY | เปลี่ยน routes ให้ register กับ Blueprint, import shared จาก `hub.core.*` |
| `plugins/free_srt/static/app.js` | MODIFY | API paths ใส่ prefix `/srt/api/...`, เพิ่มปุ่ม "← Back to Hub" |
| `plugins/free_srt/templates/index.html` | MODIFY | เพิ่ม navigation link กลับ Hub |

**ตรวจสอบ:**
- Hub เปิด → scan plugins → พบ Free SRT → register blueprint อัตโนมัติ
- ทุก feature ของ Free SRT ทำงานเหมือนเดิม 100%

---

### Phase 2.5: Extract Shared Infrastructure

> **เป้าหมาย:** ดึง shared modules ออกมาเป็น `hub/core/` ให้ plugin อื่นใช้ร่วมได้  
> **ความยาก:** ⭐⭐ | **เวลา:** ~1-2 วัน

| ไฟล์ | Action | รายละเอียด |
|------|--------|-----------|
| `hub/core/__init__.py` | NEW | Package init |
| `hub/core/compute.py` | NEW | ย้ายจาก `freesrt/compute.py` — ลบ SRT-specific default URLs |
| `hub/core/capacity.py` | NEW | ย้ายจาก `freesrt/capacity.py` — generalize estimator |
| `hub/core/diagnostics.py` | NEW | ย้ายจาก `freesrt/diagnostics.py` (ไม่ต้องแก้) |
| `hub/core/files.py` | NEW | ย้ายจาก `freesrt/files.py` (ไม่ต้องแก้) |
| `hub/core/jobs.py` | NEW | ย้ายจาก `freesrt/jobs.py` (ไม่ต้องแก้) |
| `hub/core/runtime_policy.py` | NEW | ย้ายจาก `freesrt/runtime_policy.py` — generalize allow-list |
| `plugins/free_srt/freesrt/*.py` | MODIFY | เปลี่ยน import จาก `freesrt.xxx` เป็น `hub.core.xxx` |

**ตรวจสอบ:**
- Free SRT ทำงานเหมือนเดิมหลัง import path เปลี่ยน
- `hub/core/` modules ไม่มี import อะไรจาก `freesrt/` (zero dependency on plugin)

---

### Phase 3: Plugin Manager (Download/Install/Update)

> **เป้าหมาย:** ผู้ใช้ดาวน์โหลด/อัปเดต/ลบ plugin ผ่าน Hub UI ได้  
> **ความยาก:** ⭐⭐⭐⭐ | **เวลา:** ~3-5 วัน

| ไฟล์ | Action | รายละเอียด |
|------|--------|-----------|
| `hub/manifest.py` | NEW | Fetch remote manifest จาก GitHub, อ่าน/เขียน local manifest, เปรียบเทียบ version |
| `hub/download_manager.py` | NEW | Streaming download, SHA-256 checksum, ZIP extract, user data backup/restore |
| `hub/app.py` | MODIFY | เพิ่ม API routes: `POST /api/hub/plugins/{id}/install`, `/update`, `DELETE`, `/download-status` |
| `hub/templates/hub.html` | MODIFY | Plugin store view, download progress bar, update badge, uninstall dialog |
| `hub/static/hub/hub.js` | MODIFY | Install/update/uninstall UI logic, progress polling |
| `manifest_remote.json` | NEW | Dev copy ของ remote manifest |
| `data/manifest_local.json` | NEW | Local installed plugins registry |

**ตรวจสอบ:**
- Hub เปิด → fetch remote manifest → แสดง available plugins
- กดติดตั้ง → download + checksum verify + extract → plugin พร้อมใช้
- กดอัปเดต → backup user data → download ใหม่ → restore user data
- กดลบ → ลบ plugin folder → อัปเดต local manifest
- Offline mode: ใช้ local manifest อย่างเดียว ไม่ crash

---

### Phase 4: Polish & Portable Build

> **เป้าหมาย:** Hub dashboard สวยงาม, build เป็น exe ได้  
> **ความยาก:** ⭐⭐⭐ | **เวลา:** ~2-3 วัน

| ไฟล์ | Action | รายละเอียด |
|------|--------|-----------|
| `hub/templates/hub.html` | MODIFY | Premium card design, micro-animations, glassmorphism |
| `hub/static/hub/hub.css` | MODIFY | Polish visual design |
| `ToolsHub.spec` | NEW | PyInstaller spec: bundle hub + free_srt plugin |
| `build_portable.ps1` | NEW | Build script สำหรับ Hub portable exe |

---

## 6. Flows

### 6.1 เปิด Hub (Startup)

```
launcher.py
  │
  ▼
hub.launcher.main()
  ├─ find_port()
  ├─ import hub.app
  │    ├─ สร้าง Flask app
  │    ├─ plugin_loader.discover_plugins("plugins/")
  │    │    ├─ scan plugins/free_srt/plugin.json ✓
  │    │    └─ scan plugins/free_tts/plugin.json ✓ (อนาคต)
  │    └─ plugin_loader.load_plugin(app, plugin_info)
  │         └─ importlib → register(app, plugin_dir)
  │              └─ app.register_blueprint(bp, url_prefix="/srt")
  ├─ start background thread (Flask server)
  ├─ wait_for_server()
  └─ webbrowser.open("http://127.0.0.1:{port}/")
        │
        ▼
  User เห็น Hub Dashboard ที่ /
```

### 6.2 เข้าใช้ Plugin

```
User กด Free SRT card บน Dashboard
  │
  ▼
Navigate ไป /srt/
  │
  ▼
Flask serve free_srt blueprint
  ├─ GET /srt/ → templates/index.html
  ├─ GET /srt/static/app.js
  └─ API calls: /srt/api/models, /srt/api/transcribe, ...
```

### 6.3 ติดตั้ง Plugin ใหม่ (Phase 3)

```
Hub เปิด
  │
  ▼
Fetch remote manifest จาก GitHub
  │
  ▼
เทียบกับ local manifest
  ├─ free_srt: installed ✅
  └─ free_tts: not installed 📦
  │
  ▼
User กด "ติดตั้ง" Free TTS
  │
  ▼
download_manager.download_plugin()
  ├─ ตรวจ dependencies (requires: ["ffmpeg"])
  ├─ GET free_tts.zip จาก download_url
  ├─ แสดง progress bar
  ├─ SHA-256 checksum verify
  ├─ extract ZIP → plugins/free_tts/
  └─ อัปเดต manifest_local.json
  │
  ▼
plugin_loader.load_plugin(app, free_tts_info)
  └─ register blueprint → /tts/
  │
  ▼
"Free TTS พร้อมใช้งาน! ✅"
```

---

## 7. แนะนำลำดับการทำ

| ลำดับ | Phase | ความยาก | ประมาณเวลา | เมื่อไหร่ |
|:-----:|-------|:-------:|:---------:|----------|
| 1 | Phase 1: Hub Shell | ⭐⭐ | 1-2 วัน | ทำเลย |
| 2 | Phase 2: Plugin Interface | ⭐⭐⭐ | 2-3 วัน | ต่อจาก Phase 1 |
| 3 | Phase 2.5: Extract Shared | ⭐⭐ | 1-2 วัน | ต่อจาก Phase 2 |
| 4 | Phase 3: Plugin Manager | ⭐⭐⭐⭐ | 3-5 วัน | ตอนมี plugin ตัวที่ 2 |
| 5 | Phase 4: Polish & Build | ⭐⭐⭐ | 2-3 วัน | ก่อน release |

> **Tip:** ทำ Phase 1+2+2.5 ก่อน = Hub ทำงานได้ + Free SRT เป็น plugin  
> Phase 3 (Plugin Manager) เพิ่มทีหลังตอนมี plugin ตัวที่ 2 (เช่น Free TTS) ก็ได้
