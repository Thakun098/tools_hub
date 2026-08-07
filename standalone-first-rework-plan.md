# Standalone-First Rework Plan

> สถานะ: Proposed  
> วันที่จัดทำ: 2026-08-04  
> เป้าหมายระยะสั้น: กลับไปพัฒนา FreeSRT แบบ standalone เพื่อแก้ logic การตัดคำให้เสถียร  
> เป้าหมายระยะยาว: นำ FreeSRT ที่ผ่าน regression แล้วกลับมาเชื่อมกับ Tools Hub โดยไม่ทำลาย standalone contract

## 1. หลักการและขอบเขต

ลำดับงานของ rework นี้คือ:

1. เก็บหลักฐานและสำเนา Hub integration spike ปัจจุบัน
2. ย้อน FreeSRT กลับสู่ standalone baseline ที่ทดสอบผ่าน
3. นิยามและแก้ logic การตัดคำด้วย test corpus ที่ตกลงร่วมกัน
4. ทำ standalone release candidate และทดสอบ portable build
5. พักงานจนกว่าจะพร้อมเริ่ม Hub integration รอบใหม่
6. เชื่อม Hub ผ่าน app factory/plugin adapter โดยรักษา standalone เป็นเส้นทางหลัก

งานรอบแรกไม่รวม plugin marketplace, remote manifest, download/update manager, shared infrastructure extraction หรือการเพิ่ม framework ใหม่

## 2. สิ่งที่ทราบจาก snapshot ปัจจุบัน

- FreeSRT เป็น nested Git repository ที่ `plugins/free_srt/`
- candidate baseline ปัจจุบันคือ commit `d0c9309` (`Free_SRT_v4_beta`) แต่ต้องยืนยันด้วย test ก่อนใช้เป็น rollback target
- Hub spike ปัจจุบันแก้ `app.py`, `static/app.js`, `templates/index.html` และเพิ่ม `__init__.py`, `plugin.json`
- source-mode ของ Hub โหลด FreeSRT ได้ แต่ portable ToolsHub build ไม่มี plugin
- standalone launcher ยังต้องการ `from app import app` แต่ snapshot ปัจจุบันไม่มี Flask `app`
- unit suite 79 tests เคยผ่านตาม `.agent-work/status.md`; snapshot Hub ปัจจุบันทำให้ทั้ง 79 tests ล้มที่ standalone app contract
- quality check ปัจจุบันเตือนเมื่อเกิน 2 บรรทัด, 42 ตัวอักษรต่อบรรทัด, 84 ตัวอักษรต่อ cue และ 20 ตัวอักษรต่อวินาที แต่ยังไม่ใช่ข้อกำหนดของตัวตัดคำอัตโนมัติ

## 3. Phase 0 — Preserve ก่อน rollback

### งาน

- บันทึก commit hash, `git status`, dependency versions และผล test ปัจจุบัน
- เก็บ Hub spike ใน safety branch/commit หรือ archive ที่รวมไฟล์ tracked และ untracked ที่เกี่ยวข้อง
- เก็บเอกสาร Hub ระดับ root ได้แก่ `hub/`, `ToolsHub.spec`, `hub-implementation-plan.md`, `progress-log.md` และ prototype ไว้เป็น reference
- ห้ามรวม models, uploads, outputs, data ส่วนบุคคล, build artifacts, virtual environment หรือ downloaded runtimes ใน archive
- บันทึกรายการ user-data directories ก่อน rollback โดยไม่อ่านเนื้อหาสื่อหรือข้อมูลส่วนบุคคล

### Exit criteria

- สามารถกู้ Hub spike กลับมาได้โดยไม่พึ่ง working tree ปัจจุบัน
- ระบุตำแหน่งและ checksum/commit ของ snapshot ได้
- ไม่มี user data ถูกลบหรือเขียนทับ

## 4. Phase 1 — Restore standalone baseline

### งาน

- ตรวจว่า `d0c9309` คือ standalone baseline ที่ต้องการจริง; ถ้าไม่ใช่ ให้เลือก commit จากประวัติด้วย behavior และ test evidence ไม่ใช่จากชื่อ commit เพียงอย่างเดียว
- rollback เฉพาะ nested FreeSRT repository หลังจาก Phase 0 ผ่านแล้ว
- คืน contract ต่อไปนี้:
  - `plugins/free_srt/app.py` export Flask `app`
  - `plugins/free_srt/launcher.py` เปิด server บน `127.0.0.1` และ free port ได้
  - routes เดิมไม่ต้องมี `/srt` prefix
  - portable path แยก `RESOURCE_DIR` และ writable `APP_DIR` ตาม invariants เดิม
- ตรวจว่า personal glossary, preferences, editor backup, models และ outputs ยังอยู่ครบ

### Validation gate

```powershell
.\venv\Scripts\python.exe -m py_compile app.py download_whisper.py
.\venv\Scripts\python.exe -m unittest scratch.test_app_unit -v
```

เพิ่ม smoke test แบบไม่ดาวน์โหลดโมเดลสำหรับ `/`, `/api/models`, preferences, glossary และ editor round trip ส่วน `scratch/test_app.py` ห้ามรันโดยไม่ตั้งใจเพราะอาจดาวน์โหลดโมเดล

### Exit criteria

- unit tests เดิมผ่านทั้งหมด
- standalone launcher เปิดหน้าเว็บได้
- ไม่มี Hub-specific prefix/import/manifest อยู่ใน runtime path ของ standalone
- สร้าง baseline tag หรือ release marker สำหรับเริ่มงานตัดคำ

## 5. Phase 2 — Specify logic การตัดคำ

ก่อนเขียนโค้ดต้องตกลงว่า “ตัดคำ” หมายถึงอะไร เพราะเป็นคนละปัญหากัน:

- tokenization: หาขอบเขตคำภาษาไทย/อังกฤษ
- line wrapping: แบ่งข้อความหนึ่ง cue เป็นไม่เกินจำนวนบรรทัดที่กำหนด
- cue segmentation: แบ่ง cue ยาวเป็นหลาย cue และต้องกระจายเวลาใหม่
- transcript cleanup: จัดวรรคตอน/ช่องว่างโดยไม่เปลี่ยนเวลา

### Decision record ที่ต้องอนุมัติ

- ภาษาที่รองรับ: ไทย, อังกฤษ และข้อความผสม
- เป้าหมายจำนวนบรรทัดและความยาวต่อบรรทัด; ค่า 2 บรรทัด/42 ตัวอักษรเป็นเพียงค่าเริ่มต้นจาก quality checker เดิม
- หน่วยวัด: Unicode code points, grapheme clusters, display width หรือคำ
- จุดแบ่งที่ให้คะแนนสูง: จบประโยค, เครื่องหมายวรรคตอน, phrase boundary, whitespace และ Thai word boundary
- การจัดการชื่อเฉพาะ ตัวเลข หน่วย URL อีเมล emoji combining marks และ glossary terms
- เมื่อข้อความยาวเกินหนึ่ง cue จะปรับเวลาอย่างไร และกำหนด minimum cue duration/gap เท่าใด
- ทำอัตโนมัติทุกงาน, เป็น option หรือเป็นคำสั่งใน editor
- raw Whisper output ต้องเก็บเป็น `.original.srt`; ผลตัดคำเป็น working `.srt` ที่ reset กลับได้

### Golden corpus

สร้าง fixture ที่เป็นข้อความสังเคราะห์และไม่ใช้ข้อมูลส่วนบุคคล ครอบคลุมอย่างน้อย:

- ภาษาไทยไม่มีช่องว่าง
- อังกฤษและไทยผสมกัน
- ตัวเลข วันที่ เวลา สกุลเงิน เปอร์เซ็นต์ และหน่วยวัด
- ชื่อบุคคล/แบรนด์/ศัพท์ใน glossary
- punctuation หลายชนิด, quote และวงเล็บ
- emoji, combining marks และ newline ที่ผู้ใช้กำหนดเอง
- ข้อความสั้นมาก ยาวมาก และ cue ที่มีเวลาจำกัด
- กรณีที่ไม่มีจุดแบ่งเหมาะสม

แต่ละ fixture ต้องระบุ input, expected tokens/lines/cues, expected timestamps และเหตุผลของ boundary สำคัญ

### Exit criteria

- มีตัวอย่างที่อนุมัติแล้วเพียงพอให้ตัดสิน pass/fail ได้โดยไม่อาศัยความรู้สึก
- behavior สำหรับ fallback และ edge cases ระบุครบ
- dependency ใหม่ (ถ้ามี) ผ่านการประเมิน license, package size, offline operation และ PyInstaller compatibility

## 6. Phase 3 — Implement segmentation เป็น pure domain logic

### โครงสร้างที่แนะนำ

- เพิ่มโมดูลเฉพาะ เช่น `freesrt/segmentation.py`
- API หลักรับ cues/config แล้วคืน cues ใหม่โดยไม่มี Flask, filesystem หรือ process dependency
- แยก tokenizer, boundary scoring, line wrapping และ timestamp allocation ออกจากกัน
- ให้ backend เป็น source of truth; frontend มีหน้าที่ preview/edit เท่านั้น
- ไม่แก้ raw Whisper output และไม่ silently เปลี่ยนข้อความที่ผู้ใช้แก้เอง
- output ต้องผ่าน `parse_srt()`/`serialize_srt()` และ invariant เรื่อง timestamp ก่อนเขียนแบบ atomic

### คุณสมบัติที่ต้องรักษา

- ลำดับข้อความและเนื้อหาต้องไม่สูญหายหรือซ้ำ
- ไม่มี cue เวลาเป็นศูนย์, เวลาถอยหลัง หรือ overlap ที่เกิดจากตัวแบ่ง
- การรันซ้ำต้องได้ผลเดิม และไม่แบ่งซ้ำเรื่อย ๆ
- newline ที่ผู้ใช้ตั้งใจไว้ต้องมี policy ชัดเจน
- cancellation, cleanup, original reset, glossary และ editor backup เดิมต้องไม่ถดถอย
- complexity ต้องมีขอบเขตสำหรับ transcript ขนาดใหญ่; หลีกเลี่ยง algorithm แบบกำลังสองกับจำนวนคำ/cues

### Test layers

- unit tests ของ tokenizer/boundary/wrapper/timestamp allocator
- property tests สำหรับ text conservation, timestamp monotonicity และ idempotence
- regression tests จาก golden corpus
- API tests สำหรับ save/reset/export/editor backup
- frontend tests สำหรับ preview ที่ตรงกับ SRT จริง
- performance fixture สำหรับ transcript ยาวโดยไม่ใช้ไฟล์สื่อจริง

### Exit criteria

- golden corpus ผ่านทั้งหมด
- unit suite เดิมผ่านทั้งหมด
- ไม่มีข้อความหาย ซ้ำ หรือ timestamps ผิด invariant
- ผล preview, saved SRT, TXT export และ rendered subtitle ใช้ผล segmentation เดียวกัน

## 7. Phase 4 — Standalone stabilization และ release candidate

### งาน

- ทดสอบ clean startup, restart, editor recovery และ reset-to-original
- ทดสอบ CPU-only path และ missing/incompatible binary error โดยไม่ดาวน์โหลด runtime ใหม่ระหว่าง test
- ทดสอบ cancel ก่อนเริ่ม, ระหว่าง process และใกล้ completion
- build one-folder portable จาก clean virtual environment ที่ pin dependencies
- รัน `portable_smoke_test.py` ใน isolated temporary directory
- ตรวจ release ZIP ว่าไม่มี models, outputs, uploads, personal data, caches หรือ build tree ซ้ำ
- อัปเดต `README.md`, `update.log.md` และ documentation ของ segmentation behavior

### Exit criteria

- standalone source และ portable build ผ่าน acceptance suite เดียวกัน
- มี release candidate ที่ rollback กลับ baseline ได้
- logic การตัดคำผ่านตัวอย่างจริงที่เจ้าของโครงการอนุมัติ
- known limitations และ unsupported cases ถูกบันทึกไว้

## 8. Phase 5 — Freeze standalone contract ก่อนกลับสู่ Hub

เมื่อ standalone เสถียร ให้กำหนด contract ที่ Hub ห้ามทำลาย:

- `create_app(config=None)` สร้าง standalone Flask app
- domain/services ไม่ import Hub
- routes สามารถประกอบกับ Flask app หรือ Blueprint ผ่าน factory เดียวกัน
- paths, state stores และ runtime binaries ถูกส่งผ่าน config/dependency injection
- standalone test suite เป็น mandatory gate สำหรับทุก Hub change
- version ของ FreeSRT และ plugin adapter แยกกันได้

ควร tag standalone release ก่อนเริ่ม Hub integration รอบใหม่ และพัฒนา Hub adapter ใน branch แยก

## 9. Phase 6 — Hub integration รอบใหม่

### ลำดับที่แนะนำ

1. สร้าง thin adapter ที่เรียก service/route factories ของ standalone โดยไม่แก้ domain logic
2. ใช้ namespace เฉพาะต่อ plugin; ห้ามเพิ่ม plugin directory ลง global `sys.path` แบบถาวรหรือ import module ชื่อ generic เช่น `app`
3. ให้ manifest `url_prefix` เป็น source of truth และส่งเข้า adapter
4. แยก immutable bundled resources, external plugin directory และ writable per-plugin data directory
5. ทำ source-mode integration tests สำหรับ dashboard, `/srt`, APIs และ static assets
6. ทำ packaged-mode tests ที่ยืนยันว่า bundled FreeSRT และ binaries อยู่ในตำแหน่งที่ runtime ใช้จริง
7. ทดสอบ standalone suite ซ้ำทั้งหมดก่อน merge
8. ค่อยพิจารณา plugin download/update manager หลัง plugin contract และ packaged build ผ่านแล้ว

### Hub acceptance criteria

- FreeSRT ทำงานทั้ง standalone และ Hub จาก codebase เดียวกัน
- ไม่มี module/import collision เมื่อโหลด plugin จำลองอย่างน้อยสองตัว
- manifest paths ตรงกับ directories ที่ใช้งานจริง เช่น `outputs` ไม่ใช่ `output`
- packaged ToolsHub ค้นพบ bundled FreeSRT และ runtime binaries ได้บน clean machine
- การถอน/อัปเดต plugin ไม่ลบ models, outputs, glossary, preferences หรือ editor backup
- Hub failure ไม่ทำให้ standalone regression suite ล้ม

## 10. Rollback strategy ในแต่ละระยะ

- Phase 1: rollback กลับ snapshot ของ Hub spike ได้
- Phase 2–3: ปิด segmentation feature หรือกลับ baseline serializer ได้โดยไม่แตะ `.original.srt`
- Phase 4: เก็บ previous portable release และ user-data migration ต้อง backward-compatible
- Phase 6: หาก Hub adapter ล้ม ให้ถอด adapter โดยไม่ revert domain logic ของ standalone
- ทุก destructive operation ต้องระบุ target แบบเจาะจงและตรวจ resolved path ก่อน; ห้ามลบ models/data/outputs เพื่อแก้ test หรือ build

## 11. Milestones และลำดับการอนุมัติ

| Milestone | ผลส่งมอบ | ต้องอนุมัติก่อนเดินต่อ |
|---|---|---|
| M0 | Hub spike snapshot + rollback candidate | ยืนยัน baseline commit |
| M1 | Standalone tests ผ่านและ launcher ใช้งานได้ | ยืนยัน baseline behavior |
| M2 | Segmentation decision record + golden corpus | อนุมัติตัวอย่าง expected output |
| M3 | Pure segmentation implementation | อนุมัติผล regression/quality |
| M4 | Standalone portable release candidate | อนุมัติ release candidate |
| M5 | Frozen standalone contract | อนุมัติเริ่ม Hub integration ใหม่ |
| M6 | Hub adapter + packaged integration tests | อนุมัติ Hub release |

## 12. Definition of Done สำหรับรอบ standalone-first

รอบนี้ถือว่าเสร็จเมื่อ M0–M4 ผ่านครบ: standalone ใช้งานได้, tests เดิมและ segmentation tests ผ่าน, portable release candidate ผ่าน smoke test, ข้อมูลผู้ใช้ปลอดภัย และยังไม่มี Hub-specific dependency รั่วเข้า domain logic การตัดคำ งาน Hub ใน M5–M6 เป็นงานรอบถัดไปและไม่ควรเริ่มก่อนเจ้าของโครงการอนุมัติผล standalone release candidate
