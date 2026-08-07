# Phase 6 Hub Integration — Final Scrutinize Review

> วันที่ตรวจ: 2026-08-05  
> ขอบเขต: source-mode Hub, FreeSRT standalone compatibility, plugin isolation, frontend `/srt` base path และ packaged ToolsHub  
> กติกา: บันทึก findings หลัง implementation และไม่แก้ findings ในรอบนี้

## Intent

เป้าหมายคือให้ FreeSRT ทำงานจาก codebase เดียวกันทั้ง standalone และ Tools Hub โดย mount ใต้ `/srt`, แยก writable data ออกจาก bundled resources และไม่ทำให้ plugin imports ชนกัน

### Simpler-alternative pass

แนวทางที่เล็กกว่าคือ mount standalone Flask app ด้วย `DispatcherMiddleware` แต่ frontend ยังต้องแก้ base path และจะเพิ่ม WSGI lifecycle อีกชั้น แนวทาง Blueprint ปัจจุบันจึงเหมาะกับ Hub มากกว่า อย่างไรก็ตามการใช้ `RuntimeServices` object ที่ชัดเจนจะเรียบง่ายต่อ lifecycle ระยะยาวกว่าการ import `app.py` ซ้ำเป็น runtime modules แม้ต้อง refactor มากกว่าในตอนแรก

## Verification performed

- FreeSRT standalone: 79 tests ผ่าน
- Segmentation: 16 tests ผ่าน
- JavaScript SRT/manual-split: 3 tests ผ่าน และ `node --check static/app.js` ผ่าน
- Hub source integration/isolation: 5 tests ผ่าน
- PyInstaller `ToolsHub.spec`: build one-folder สำเร็จ
- Packaged executable smoke: health `ok`, `free_srt` loaded, `/srt/`, `/srt/api/models`, `/srt/static/app.js` ได้ HTTP 200
- Packaged binaries: `whisper-cli.exe`, `ffmpeg.exe`, `ffprobe.exe` อยู่ใน runtime paths ที่กำหนด

## Findings

### Blocker — malformed manifest หนึ่งไฟล์ทำลาย metadata ของ plugin ที่ค้นพบก่อนหน้า

**Finding:** `discover_plugins()` ใช้ `locals().get("manifest")` ใน exception path ทำให้ iteration ที่อ่าน JSON ไม่ได้สามารถนำ dict ของ plugin ก่อนหน้ามาแก้ `_dir` และ `_error` ได้ (`hub/plugin_loader.py:60-71`)

**Why it matters:** external plugin ที่มี `plugin.json` เสียเพียงไฟล์เดียวสามารถทำให้ bundled FreeSRT record ก่อนหน้ากลายเป็น failed และ Hub ข้ามทั้งสอง records

**Evidence:** fixture ที่มี plugin `a` ถูกต้องตามด้วย manifest `b` ที่เป็น `{broken` คืน list สองรายการซึ่ง `plugins[0] is plugins[1]` เป็น `True`; ทั้งสองมี ID `a`, directory ของ `b` และ JSON error เดียวกัน

**Suggested change:** initialize fallback manifest ใหม่ภายในแต่ละ loop ก่อน `try` และห้าม reuse local variable จาก iteration ก่อนหน้า; เพิ่ม regression test valid manifest ตามด้วย invalid JSON

### Major — package namespace ที่มีอยู่แล้วใน `sys.modules` ถูกเชื่อถือโดยไม่ตรวจ origin

**Finding:** `_load_package()` คืน module เดิมทันทีเมื่อชื่อ package มีใน `sys.modules` โดยไม่ตรวจว่า `module.__file__` อยู่ใต้ plugin directory (`hub/plugin_loader.py:83-92`)

**Why it matters:** dependency หรือ plugin ที่โหลดก่อนหน้าซึ่งใช้ชื่อเดียวกันสามารถ hijack imports ของ plugin ปัจจุบัน แม้ manifest จะชี้ไปยัง package source ที่ถูกต้อง

**Evidence:** path validation เกิดกับ `plugin_dir/<package>/__init__.py` แต่ branch ที่ `hub/plugin_loader.py:85-86` ไม่เปรียบเทียบ path ของ cached module กับไฟล์นั้น

**Suggested change:** resolve และเปรียบเทียบ cached module origin กับ expected package init; reject mismatch ก่อนโหลด adapter

### Major — duplicate contracts ถูกตรวจหลัง plugin ตัวแรก register routes แล้ว

**Finding:** `load_all_plugins()` ตรวจ duplicates และ register ทีละรายการ ดังนั้นตัวแรกถูก mount ก่อนจึงรู้ว่าตัวถัดไปมี ID/package/prefix ซ้ำ (`hub/plugin_loader.py:133-157`)

**Why it matters:** configuration ที่ไม่ valid ถูกยอมรับบางส่วนและ behavior ขึ้นกับ root/order; ไม่ตรงกับแผนที่กำหนดให้ปฏิเสธ duplicates ก่อน route registration

**Evidence:** test ปัจจุบันยืนยันว่ากรณี prefix `/same` ซ้ำ ตัวแรกยัง loaded และ `/same/` ยังถูก register (`hub/tests/test_plugin_isolation.py:55-67`)

**Suggested change:** preflight manifests ทั้งชุด สร้าง conflict groups และ mark ทุกสมาชิกของ conflict เป็น failed ก่อนเรียก `load_plugin()` ใด ๆ

### Major — generic compatibility alias ทำให้ isolation acceptance ไม่เป็นจริง

**Finding:** runtime policy เพิ่ม `freesrt.runtime_policy` ลง global `sys.modules` เมื่อโหลดผ่าน namespace `toolshub_free_srt` (`plugins/free_srt/freesrt/runtime_policy.py:49-52`)

**Why it matters:** plugin อื่นที่ import generic `freesrt.runtime_policy` สามารถชนหรือ reuse FreeSRT module ได้ แม้ loader ไม่แก้ `sys.path`

**Evidence:** หลัง import `hub.app`, expression `'freesrt.runtime_policy' in sys.modules` เป็น `True`; isolation tests ตรวจเฉพาะ fake package names และไม่ตรวจ generic alias นี้

**Suggested change:** จำกัด compatibility alias ให้เฉพาะ standalone bootstrap หรือย้าย shared exception type ไป module/package contract ที่มีชื่อ unique โดยให้ tests import contract เดียวกัน

### Major — isolated runtime modules และ Flask app ที่สร้างระหว่าง bootstrap ไม่มี lifecycle cleanup

**Finding:** `create_runtime_context()` exec `app.py` ใต้ชื่อใหม่ทุกครั้ง และ `app.py` สร้าง module-level Flask app ก่อน adapter นำ runtime เดิมไป register routes บน Blueprint อีกครั้ง (`plugins/free_srt/toolshub_free_srt/app_factory.py:23-38`, `plugins/free_srt/app.py:430-450`, `plugins/free_srt/__init__.py:32-33`)

**Why it matters:** ทุก `create_app()` ของ Hub ทิ้ง runtime module, route closures, locks และ Flask app ที่ไม่ได้ใช้งานไว้ใน `sys.modules`; test process หรือ future reload/update flow จะสะสม state โดยไม่มี unload contract

**Evidence:** packaged/source path ใช้ Blueprint ที่ adapter สร้าง แต่ imported runtime module สร้าง `_build_current_app()` ของตัวเองเสมอ และไม่มี code ถอน `toolshub_plugins.free_srt.runtime_*`

**Suggested change:** แยก runtime construction ออกจาก standalone Flask app construction; สร้าง module-level `app` เฉพาะ standalone entry path หรือแทน module cloning ด้วย explicit `RuntimeServices` instance

## Verdict

**fix-then-ship** — source และ packaged happy paths ทำงานจริง แต่ malformed manifest สามารถทำให้ bundled plugin ที่ถูกต้องถูกปิดใช้งานได้ และ import/lifecycle isolation ยังไม่ตรงกับ contract ที่ประกาศ
