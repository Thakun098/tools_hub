# Subtitle Segmentation Rework Plan

> สถานะ: Proposed  
> วันที่จัดทำ: 2026-08-04  
> ขอบเขต: FreeSRT standalone ใน `plugins/free_srt/`  
> แผนแม่: `standalone-first-rework-plan.md`  
> เป้าหมาย: ป้องกัน subtitle แบบ paragraph, แก้ปัญหาการแยกภาษาไทยแล้วได้ `...` และสร้างการแบ่ง cue ที่อ่านง่ายโดยไม่ทำข้อความหรือ timestamp เสียหาย

## 1. Problem statement

ปัญหาที่ได้รับจากผู้ใช้มีสองส่วน:

1. ผล SRT รอบแรกจาก Whisper บางครั้งรวมข้อความยาวเป็น paragraph ใน subtitle event เดียว
2. คำสั่งแยก cue ปัจจุบันแบ่งข้อความด้วย whitespace เมื่อข้อความไทยไม่มีช่องว่าง ฝั่งขวาจึงว่างและถูกแทนด้วย `...` ขณะที่ข้อความยาวเดิมยังไม่ถูกแบ่งจริง

สาเหตุที่ยืนยันจาก snapshot ปัจจุบัน:

- `freesrt/workers.py` เรียก `whisper-cli` โดยไม่ส่ง `--max-len` และ `--split-on-word`
- `static/app.js` ใช้ `cue.text.trim().split(/\s+/)` และ fallback เป็น `right || '...'`
- quality checker เตือนเมื่อ cue ยาว แต่ไม่ได้แก้หรือแบ่ง cue อัตโนมัติ
- SRT ที่ Whisper สร้างมี timestamp ระดับ cue; การแบ่งข้อความเพิ่มภายหลังจึงต้องมี policy สำหรับ timestamp ที่ชัดเจน

## 2. Desired outcome

หลัง rework:

- ผลจาก Whisper ไม่ควรสร้าง paragraph ยาวโดยไม่มีการตรวจ
- cue ที่เกินข้อกำหนดถูกแบ่งซ้ำจนผ่านทุก hard constraint หรือถูกแจ้งเป็น unresolved อย่างชัดเจน
- ภาษาไทยที่ไม่มี whitespace สามารถแบ่งได้โดยไม่สร้างข้อความปลอม
- ไม่มีข้อความหาย ซ้ำ หรือถูกเปลี่ยนความหมาย
- ไม่มี cue ที่เวลาเป็นศูนย์ เวลาถอยหลัง หรือ overlap จากตัว segmenter
- raw Whisper output ยังคงอยู่ใน `<task_id>.original.srt`
- working output ที่ผ่าน segmentation อยู่ใน `<task_id>.srt` และ reset กลับ original ได้
- preview, editor, SRT export, TXT export และ video render เห็น cue ชุดเดียวกัน

## 3. Non-goals

งานนี้ยังไม่รวม:

- การแปลหรือย่อความบทสนทนาด้วย LLM
- การลบคำพูดเพื่อให้พอดีกับเวลาโดยอัตโนมัติ
- speaker diarization
- Hub/plugin integration
- plugin marketplace หรือ updater
- การเปลี่ยนจาก whisper.cpp เป็น transcription engine อื่น
- การรับประกัน linguistic word segmentation ที่สมบูรณ์สำหรับทุกภาษา

## 4. Proposed default policy

### 4.1 Layout

- สูงสุด 2 บรรทัดต่อ cue
- ภาษาไทย: สูงสุด 35 display characters ต่อบรรทัด
- hard maximum ต่อ cue: 70 display characters
- พยายามให้เป็นหนึ่งบรรทัดหากข้อความไม่เกิน 35 display characters
- เมื่อต้องมีสองบรรทัด ให้เลือกจุดแบ่งที่อ่านเป็นธรรมชาติและหลีกเลี่ยงบรรทัดบนที่สั้นมาก

`display characters` ต้องไม่นับ Thai combining marks แยกเป็นตัวอักษรเต็ม และต้องไม่ตัด grapheme cluster กลางชุด

### 4.2 Timing

- target duration: 2–5 วินาที
- hard maximum: 7 วินาที
- minimum duration: 833 ms
- reading-speed ceiling สำหรับค่าเริ่มต้น: 20 display characters/second
- optional child-content profile: 17 display characters/second
- ไม่สร้าง gap หรือ overlap ใหม่ระหว่าง fragments ที่มาจาก cue เดียวกัน

ช่วง 3–5 วินาทีใช้เป็นเป้าหมาย ไม่ใช้เป็น hard cap เดี่ยว เพราะ cue ที่มีข้อความมากอาจต้องใช้เวลานานกว่าเพื่อไม่ให้อ่านเร็วเกินไป

### 4.3 Word count

- 10 คำเป็น soft warning สำหรับภาษาที่มี whitespace word boundaries
- ห้ามใช้ whitespace word count เป็น hard limit สำหรับภาษาไทย
- hard constraints หลักคือ display characters, duration, line count และ reading speed

### 4.4 Ellipsis

- ห้ามสร้าง `...` หรือ `…` เป็น placeholder เมื่อ split ไม่สำเร็จ
- ellipsis ใช้ได้เฉพาะเมื่อมีอยู่ใน transcript หรือผู้ใช้เพิ่มเองเพื่อสื่อ pause/interruption
- การแบ่งประโยคต่อเนื่องระหว่าง cues ไม่เพิ่ม ellipsis โดยอัตโนมัติ

## 5. Boundary selection policy

เมื่อจำเป็นต้องแบ่งข้อความ ให้หาจุดแบ่งใกล้ตำแหน่งเป้าหมายและให้คะแนนตามลำดับ:

1. silence หรือ token timestamp boundary ที่เชื่อถือได้
2. จบประโยค เช่น `.`, `?`, `!`, `。`, `？`, `！`
3. เครื่องหมายแบ่งวลี เช่น `,`, `;`, `:`, `—`, `-`, `ๆ`
4. whitespace boundary
5. Thai/Unicode word boundary จาก tokenizer ที่อนุมัติ
6. grapheme-cluster boundary เป็น fallback สุดท้าย

ข้อห้าม:

- ไม่แยก combining mark ออกจาก base character
- ไม่แยกตัวเลขจากหน่วย, วันที่, เวลา, URL, email หรือ decimal หากมีจุดอื่นที่เหมาะสม
- ไม่แยกคำที่ตรงกับ glossary term หากยังมี boundary อื่นที่ผ่านข้อกำหนด
- ไม่สร้าง fragment ว่างหรือ fragment ที่มีเพียง punctuation โดยไม่จำเป็น

## 6. Segmentation algorithm

### Step A — Normalize โดยไม่เปลี่ยนความหมาย

- normalize line endings
- trim เฉพาะ whitespace ต้น/ท้าย cue
- รักษา punctuation และข้อความเดิมทั้งหมด
- แปลงข้อความเป็น grapheme/display units สำหรับการนับ

### Step B — Evaluate cue

คำนวณ:

- duration
- display character count
- line count และความยาวแต่ละบรรทัด
- reading speed
- whitespace word count เฉพาะภาษาที่เหมาะสม

cue ผ่านได้เมื่อไม่ละเมิด hard constraints ทั้งหมด

### Step C — Determine fragment count

จำนวน fragments เริ่มต้นเป็นค่าสูงสุดจาก:

- `ceil(display_chars / 70)`
- `ceil(duration / 7000ms)`
- จำนวนที่จำเป็นเพื่อให้แต่ละ fragment จัดได้ไม่เกินสองบรรทัด

จากนั้นเพิ่มจำนวน fragments หาก reading speed หรือ boundary quality ยังไม่ผ่าน โดยต้องมี minimum duration เพียงพอสำหรับทุก fragment

### Step D — Choose text boundaries

- กระจาย target sizes ให้ใกล้เคียงกัน
- ค้นหา candidate boundary รอบ target
- ให้คะแนนจาก boundary policy, line balance และระยะห่างจาก target
- ใช้ dynamic programming หรือ bounded search เพื่อเลือกชุด boundaries ทั้ง cue พร้อมกัน แทน greedy split ซ้ำที่อาจทิ้ง fragment สุดท้ายยาวมาก

### Step E — Allocate timestamps

ลำดับความน่าเชื่อถือ:

1. token/word timestamps จาก Whisper
2. silence boundaries จาก VAD ที่ตรงกับ text boundary
3. สัดส่วน display units พร้อม minimum-duration constraints

fallback แบบสัดส่วนต้อง:

- ใช้ช่วงเวลาเดิมทั้งหมด
- ให้ fragment แรกเริ่มที่เวลาเดิมและ fragment สุดท้ายจบที่เวลาเดิม
- timestamps เป็น monotonic
- ไม่มี fragment ต่ำกว่า minimum duration
- ไม่ขยายเวลาไปทับ cue ข้างเคียง

ถ้าไม่สามารถแบ่งโดยรักษาข้อกำหนดได้ ให้คืน cue เดิมพร้อม issue code เช่น `SEGMENTATION_UNRESOLVED`; ห้ามทิ้งข้อความหรือสร้าง `...`

### Step F — Validate result

- concatenate ข้อความทุก fragment แบบ normalization ที่กำหนดแล้วต้องเท่ากับข้อความต้นฉบับ
- timestamps ต้องเรียงลำดับและอยู่ภายในช่วงเดิม
- `parse_srt(serialize_srt(result))` ต้อง round-trip
- การ segment ผลลัพธ์ซ้ำต้องได้ผลเดิม

## 7. Whisper integration

### Phase 1 experiment

ทดลองเพิ่ม flags หลังตรวจ `whisper-cli -h` ของ runtime:

```text
--max-len 35
--split-on-word
```

เงื่อนไข:

- เพิ่มผ่าน config/constants ไม่ hard-code ซ้ำใน CPU/GPU paths
- CPU และ GPU fallback ต้องใช้ segmentation flags ชุดเดียวกัน
- ถ้า runtime รุ่นใดไม่รองรับ flag ต้อง fail ด้วยข้อความชัดเจนหรือปิด option อย่างตั้งใจ ไม่ silently เปลี่ยน behavior
- เปรียบเทียบผลไทย อังกฤษ และข้อความผสมกับ baseline ก่อนเปิดเป็นค่าเริ่มต้น

### ข้อจำกัด

- `--max-len` ช่วยจำกัดความยาว segment แต่ไม่รับประกัน layout สองบรรทัด
- `--split-on-word` อาจไม่ตรงกับ lexical word boundary ของภาษาไทย
- ห้ามใช้ `--duration` เพื่อจำกัด subtitle event เพราะเป็นระยะเสียงทั้งหมดที่ CLI จะประมวลผล
- VAD `--vad-max-speech-duration-s` พิจารณาได้ภายหลังเมื่อมี VAD model และ validation แยก ไม่ใช่ dependency ของ fix รอบแรก

### Proposed pipeline

```text
audio
  -> whisper.cpp พร้อม max-len/split hint
  -> raw validated cues
  -> write <task_id>.original.srt
  -> deterministic backend segmenter
  -> write <task_id>.srt
  -> editor / export / render
```

## 8. Manual split rework

แก้ `handleCueAction('split')` ให้ทำงานดังนี้:

1. ถ้าผู้ใช้เลือกข้อความหรือวาง caret ใน textarea ให้ใช้ boundary ใกล้ caret
2. หากไม่มี caret ที่ใช้ได้และ media time อยู่ใน cue ให้คำนวณ target text position จากสัดส่วนเวลา
3. หากไม่มีทั้งสองอย่าง ให้ใช้ best boundary ใกล้กึ่งกลาง cue
4. ใช้ boundary engine เดียวกับ backend ไม่ใช้ `split(/\s+/)` โดยตรง
5. สร้าง cue ใหม่เฉพาะเมื่อข้อความทั้งสองฝั่งไม่ว่าง
6. ถ้าแบ่งไม่ได้ ให้คง state เดิมและแสดงข้อความแจ้งผู้ใช้
7. checkpoint/undo ต้องคืนทั้งข้อความและ timestamps ได้สมบูรณ์
8. ห้ามใช้ `right || '...'`

ในระยะยาว frontend ควรเรียก backend split API หรือใช้ผล boundary metadata จาก backend เพื่อไม่ให้กฎ Python และ JavaScript แตกต่างกัน

## 9. Proposed code boundaries

### New module

`plugins/free_srt/freesrt/segmentation.py`

ความรับผิดชอบที่เสนอ:

- `display_units(text, language)`
- `find_boundary_candidates(text, language, glossary_terms=None)`
- `wrap_fragment(text, max_line_units, max_lines)`
- `allocate_fragment_times(cue, fragments, token_times=None)`
- `segment_cue(cue, policy, token_times=None)`
- `segment_cues(cues, policy, token_times=None)`
- `validate_segmentation(original, result, policy)`

โมดูลนี้ต้องเป็น pure domain logic: ไม่ import Flask, filesystem, subprocess หรือ global job state

### Existing files

- `freesrt/workers.py`: เพิ่ม Whisper flags, เก็บ original ก่อน post-processing และเรียก segmenter
- `freesrt/subtitles.py`: ใช้ parser/serializer เดิมและเพิ่ม helper เฉพาะเมื่อเป็น invariant ทั่วไปจริง
- `app.py`: expose policy/config ผ่าน service layer หลัง standalone rollback
- `static/app.js`: ลบ whitespace-only split และ placeholder ellipsis
- `static/js/srt.js`: หลีกเลี่ยงการทำ segmentation logic ซ้ำ; คง parser/serializer ฝั่ง UI
- `templates/index.html`: เพิ่ม setting/ข้อความอธิบายเฉพาะเมื่อ UX decision อนุมัติ
- `scratch/test_app_unit.py`: regression และ integration tests
- `README.md`, `update.log.md`: behavior, defaults และ limitations

## 10. Golden corpus

สร้าง fixtures ที่ไม่ใช้ข้อมูลส่วนบุคคล ครอบคลุมอย่างน้อย:

1. ไทยยาวต่อเนื่องโดยไม่มีช่องว่าง
2. ไทยที่มีวรรคตอนหลายตำแหน่ง
3. ไทยและอังกฤษผสมกัน
4. ชื่อบุคคล/แบรนด์และ glossary phrases
5. ตัวเลข วันที่ เวลา เงิน เปอร์เซ็นต์ และหน่วยวัด
6. URL, email และรหัสสินค้า
7. emoji และ Thai combining marks
8. cue สั้นกว่า minimum duration แต่ข้อความยาว
9. cue ยาวเกิน 7 วินาทีแต่ข้อความสั้น
10. paragraph ที่ต้องแบ่งมากกว่าสอง fragments
11. ข้อความที่ไม่มี boundary ที่ดี
12. multiline text ที่ผู้ใช้แก้เอง
13. dual speakers
14. punctuation-only และ malformed whitespace

แต่ละ fixture ระบุ:

- input cue และ language
- expected text fragments
- expected timestamp ranges หรือ timestamp invariants
- expected line wrapping
- expected issue codes
- เหตุผลที่เลือก boundary

## 11. Required tests

### Regression tests

- ภาษาไทยไม่มี whitespace ไม่สร้าง `...`
- split ที่ไม่มี valid boundary ไม่เปลี่ยน cue
- paragraph ถูกแบ่งมากกว่าหนึ่งครั้งจนผ่านข้อกำหนด
- raw original ไม่ถูก post-processing ทับ
- reset คืน raw original

### Invariant/property tests

- text conservation
- no duplication
- timestamp monotonicity
- no new overlaps
- result stays within original cue interval
- minimum duration
- maximum two lines
- idempotence
- SRT round trip
- atomic non-overwrite เมื่อ validation ล้ม

### Whisper command tests

- CPU command มี flags ที่อนุมัติ
- CUDA/Vulkan command มี flags ชุดเดียวกัน
- CPU fallback ไม่ทำ flags หาย
- prompt ยังใช้ `--prompt` ไม่ใช่ `-p`
- unsupported CLI flags ให้ error ที่วินิจฉัยได้

### Editor tests

- split จาก caret
- split จาก playback position
- undo/redo หลัง split
- split ไทย/อังกฤษ/ข้อความผสม
- save/export/render ใช้ cue ล่าสุด
- ไม่มี literal placeholder ellipsis

### Performance tests

- transcript จำนวนมากไม่แสดงพฤติกรรม O(n²) ตามจำนวน cues
- cue paragraph ขนาดใหญ่มี bounded search และ timeout/limit ที่ชัดเจน

## 12. Rollout phases

### S0 — Restore standalone baseline

- rollback Hub modifications หลังเก็บ snapshot
- unit tests เดิม 79 รายการต้องผ่าน
- ยังไม่เปลี่ยน segmentation behavior

### S1 — Fix destructive/manual split bug

- ลบ `right || '...'`
- เพิ่ม safe boundary fallback
- เพิ่ม regression tests ภาษาไทย
- behavior ใหม่ยังเป็น manual only

### S2 — Whisper segmentation hints

- เพิ่ม `--max-len 35 --split-on-word` หลัง capability check
- รัน corpus comparison
- เก็บผล raw และ metrics เทียบ baseline
- เปิดด้วย config flag ก่อน

### S3 — Backend deterministic segmenter

- เพิ่ม pure segmentation module
- ใช้หลัง Whisper output
- เก็บ original ก่อน segmentation
- เปิดด้วย setting/feature flag และเก็บ issue summary

### S4 — Make default after acceptance

- ให้เจ้าของโครงการตรวจตัวอย่างไทยจริง
- ปรับ defaults จาก corpus evidence
- เปิด automatic segmentation เป็นค่าเริ่มต้น
- ยังมี option ปิดเพื่อ recovery

### S5 — Portable validation

- clean-environment build
- portable smoke test
- ตรวจ CPU/GPU paths
- ตรวจว่า dependency tokenizer ที่เลือกถูก bundle และ license ถูกต้อง

## 13. Observability

ต่อหนึ่ง transcription job ให้บันทึกข้อมูลที่ไม่เปิดเผยข้อความส่วนบุคคล:

- จำนวน cues ก่อนและหลัง segmentation
- จำนวน cues ที่ถูกแบ่ง
- จำนวน unresolved cues แยกตาม issue code
- max duration, max display characters และ max reading speed แบบ aggregate
- policy version
- Whisper flags ที่ใช้โดยไม่บันทึก prompt หรือ transcript

ห้ามส่ง transcript, local paths หรือ glossary contents ออกนอกเครื่อง

## 14. Acceptance criteria

ถือว่า rework เสร็จเมื่อ:

1. standalone baseline และ test suite เดิมผ่าน
2. ไม่สามารถ reproduce กรณี split ภาษาไทยแล้วสร้าง `...` ได้อีก
3. golden corpus ผ่านทุก fixture ที่อนุมัติ
4. ทุก cue ผ่าน hard constraints หรือมี unresolved issue ที่ชัดเจนโดยไม่สูญเสียข้อความ
5. original SRT, reset, editor backup และ export invariants ยังทำงาน
6. CPU, GPU และ CPU fallback ใช้ policy เดียวกัน
7. source และ portable build ให้ behavior เดียวกัน
8. segmentation สามารถปิดเพื่อ rollback ได้
9. README/update log อธิบายค่าตั้งต้นและข้อจำกัด
10. เจ้าของโครงการอนุมัติผลตัวอย่างภาษาไทยก่อนเปิดเป็นค่าเริ่มต้น

## 15. Decisions required before implementation

ค่าแนะนำสำหรับรอบแรก:

| Decision | Recommended default |
|---|---|
| Thai line limit | 35 display characters |
| Lines per cue | 2 |
| Target duration | 2–5 seconds |
| Hard maximum duration | 7 seconds |
| Minimum duration | 833 ms |
| Adult reading speed | 20 display characters/second |
| Child reading speed | 17 display characters/second |
| Word-count limit | Soft warning only, 10 words for whitespace languages |
| Whisper hints | `--max-len 35 --split-on-word` behind feature flag |
| Failed split behavior | Preserve original cue + issue code; never `...` |
| Original preservation | Raw Whisper output in `.original.srt` |
| Automatic segmentation | Opt-in during corpus validation, default-on only after approval |

ต้องตัดสินใจเพิ่มเติมก่อน implementation:

- จะใช้ tokenizer ภาษาไทยตัวใด หรือเริ่มจาก grapheme/punctuation/token timestamps โดยไม่เพิ่ม dependency
- จะ expose profiles เช่น Standard/Children/Custom ใน UI รอบนี้หรือภายหลัง
- จะใช้ Whisper token timestamps/JSON output ในรอบแรกหรือเริ่มจาก proportional fallback
- automatic segmentation ทำทันทีหลัง transcription หรือเป็นคำสั่งที่ผู้ใช้กดใน editorระหว่างช่วงทดลอง

## 16. Recommended first implementation slice

slice แรกควรเล็กและย้อนกลับง่าย:

1. restore standalone baseline
2. เพิ่ม fixture ภาษาไทยที่ reproduce `...`
3. แก้ manual split ไม่ให้สร้างข้อความปลอมและไม่แก้ state เมื่อแบ่งไม่ได้
4. เพิ่ม pure helpers สำหรับ grapheme-safe midpoint และ text-conservation validation
5. รัน unit suite ทั้งหมด

ยังไม่เพิ่ม Whisper flags หรือ automatic post-processing ใน slice แรก เพื่อแยกการแก้ confirmed bug ออกจากการเปลี่ยน segmentation behavior ระดับผลิตภัณฑ์
