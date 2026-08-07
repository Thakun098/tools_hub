## 2026-08-07 - Atomic Tools Hub registration

- Changed the Hub adapter to return a side-effect-free `PluginRegistration`; the Hub loader now preflights and commits its Blueprint atomically.
- Added regression coverage for malformed manifests, duplicate preflight, and Blueprint registration failures that must not leak routes.
- Reject cached package or submodule origins outside the declared plugin package without replacing the existing modules.
- Added separate plugin distribution metadata so FreeSRT is built and downloaded independently from Tools Hub core.
- Moved `RuntimePolicyError` into the unique `toolshub_free_srt.contracts` module and removed the global `freesrt.runtime_policy` compatibility alias.

## 2026-08-05 — Tools Hub integration

- Added a standalone-compatible `create_app(config)` path with isolated runtime globals and configurable resource/data/model/runtime/upload/output roots.
- Added the `toolshub_free_srt` package namespace, validated plugin manifest, thin Blueprint adapter, and `/srt` base-path-aware frontend behavior.
- Added Hub app/loader factories with bundled/external plugin separation, duplicate contract checks, and no plugin-directory `sys.path` injection.
- Added source integration tests for Hub APIs, writable persistence, plugin namespace isolation, duplicate prefixes, and per-app runtime-state isolation.
- Updated `ToolsHub.spec` to bundle the adapter, Python sources, assets, allow-listed whisper.cpp runtime, FFmpeg, and ffprobe while excluding user data.

## 2026-07-30 — High-finding remediation: cancellation, privacy, capacity, runtime policy, and build recovery

- Added reserve-first transcription and video-render APIs so the browser owns a cancellable server ID before multipart upload or preflight; unreserved callers receive HTTP 428 migration guidance.
- Added cancellable upload copying and process-registered preflight probes, preserving idempotent cancellation, terminal-state immutability, ownership cleanup, and underscore-key privacy.
- Added write-time and serialization-time redaction for private local-source paths across logs, errors, nested JSON, slash variants, and Windows case variants.
- Added conservative output-volume render admission using source size, duration, and resolution, plus a pre-FFmpeg recheck and an emergency low-disk process-tree stop with partial-file cleanup.
- Centralized CPU/GPU executable, DLL, archive-path, accelerator, and AVX-512 selection in `freesrt/runtime_policy.py`; the UI installer, PyInstaller spec, and portable build now share it.
- Changed portable builds to isolated staging, durable byte-for-byte personal-JSON recovery, ZIP exclusion verification, delayed dist promotion, and automatic rollback on promotion faults.
- Added focused Python regressions and an isolated PowerShell suite covering eight build fault points. No real portable build, network download, model operation, or hardware test was run in this remediation.
- Terminalized interrupted/malformed multipart parsing so claimed transcription and render reservations cannot remain active after ClientDisconnected or BadRequest.
- Replaced the catch-all GPU DLL predicate with a finite shared/backend-specific inventory and fail-closed rejection of arbitrary archive or staged-tree DLLs.
## 2026-07-30 — Audit remediation for subtitle safety, uploads, glossary rendering, and portable binaries

- Changed subtitle reset and original-output preservation to validate SRT content and use temporary files followed by atomic replacement.
- Added pre-multipart upload capacity checks across the upload and system temporary volumes, plus cleanup and controlled errors for partial upload-write failures.
- Rebuilt glossary rows with DOM nodes and input value properties so glossary text is never interpolated into HTML attributes.
- Restricted the CPU portable runtime to `whisper-cli.exe` and its allow-listed DLLs, excluded AVX-512 CPU backends from GPU runtime extraction, and added build-time binary-policy assertions before both release ZIPs are created.
- Added regression coverage for invalid reset sources, atomic reset writes, oversized and failed uploads, safe glossary rendering, and portable AVX-512 filtering.

## 2026-07-24 — Plain-text subtitle export

- Added UTF-8 TXT export from the latest saved Editor subtitles without running Whisper again.
- TXT output removes sequence numbers and timestamps, keeps one cue per line, and joins multi-line cue text into a single line.
- Added Editor controls and API coverage for SRT-to-TXT export.
## 2026-07-24 — All-in-one CUDA and Vulkan portable runtime

- Changed the main `FreeSRT-portable.zip` to include CPU, NVIDIA CUDA 11.8, and Vulkan whisper.cpp 1.9.1 runtimes from the start.
- Added a smaller `FreeSRT-portable-CPU.zip` as an alternative for machines that do not need GPU acceleration.
- Built the Vulkan runtime from the official whisper.cpp v1.9.1 source (`f049fff95a089aa9969deb009cdd4892b3e74916`) with LunarG Vulkan SDK 1.4.350.0.
- Pinned the official CUDA 11.8 Windows runtime URL and SHA-256 and exposed its source/size through the backend API.
- Clarified the GPU status UI so detected hardware is not confused with an installed runtime.
- Fixed GPU probing so a CUDA CLI that silently loads only its CPU backend is not reported as a working CUDA device.
## 2026-07-24 — Frontend startup and GPU runtime fixes

- Fixed an extra JavaScript closing brace that prevented the entire frontend from starting, which broke theme switching, file opening, and left model cards stuck on the loading placeholder.
- Added browser-module syntax validation to the portable build when Node.js is available so this class of frontend startup regression is caught before packaging.
- Fixed GPU download cancellation so a connection error after cancellation remains `cancelled` rather than becoming `failed`.
- Fixed reinstalling over an incomplete GPU runtime directory and corrected the GPU probe/retry button and download error display.
- Verified theme interaction, five-model rendering, CPU transcription with the Base model, backend unit tests, and portable build behavior.
## 2026-07-24 — Optional GPU acceleration foundation

- Added CPU-only and GPU-accelerated compute modes with automatic, CUDA, and Vulkan backend selection.
- Added optional user-downloaded GPU runtime catalog, checksum/archive validation, probe status, cancellation state, and CPU fallback orchestration.
- Added portable UI controls, preferences persistence, backend status/download endpoints, and GPU runtime diagnostics.
- This initial implementation kept the main ZIP CPU-only; it was superseded later the same day by the all-in-one CUDA/Vulkan package above.

## 2026-07-15 — Portable EXE build validation

- Built the refactored application with PyInstaller in an isolated `build_test` output before publishing to `dist`.
- Found and fixed a missing `json` import in the real ffprobe path; added a direct `probe_media` regression test so this portable-only failure is covered.
- Passed an end-to-end isolated EXE smoke test through server startup, upload, bundled FFmpeg conversion, bundled whisper.cpp transcription, and completed SRT output.
- Rebuilt the production one-folder application and portable ZIP with `build_portable.ps1`.
- Verified the production EXE serves the app and diagnostics successfully and finds its bundled FFmpeg, ffprobe, whisper-cli, templates, and frontend ES modules.
- Verified the release ZIP contains the required runtime files and excludes model files and personal glossary/preferences/editor-backup JSON.

## 2026-07-15 — Maintainability and separation-of-concerns refactor

- Reduced `app.py` from a backend hero file of more than 1,100 lines to a small portable entry point and compatibility façade.
- Split Flask routes into transcription/model, video rendering, and editor/settings modules.
- Moved download, FFmpeg, whisper.cpp, transcription, and render worker implementations into a dedicated worker module while preserving existing patch points and cancellation behavior.
- Extracted SRT handling, atomic JSON/file helpers, glossary rules, preference/recovery validation, subtitle styling, and model metadata into focused domain modules.
- Split shared frontend state, DOM/ETA helpers, and SRT parsing into ES modules under `static/js/`.
- Preserved all existing API routes, Windows/PyInstaller paths, opaque local sources, state locking, terminal-state behavior, process-tree cancellation, and cleanup invariants.
- Verified Python imports, JavaScript syntax, Flask route registration, and all 38 backend unit tests after the refactor.

## 2026-07-15 — Glossary deletion rules

- อนุญาตให้เว้นค่าคำที่ถูกต้องว่าง เพื่อใช้เป็นกฎลบคำที่พบออกจากคำบรรยาย
- รายการลบรองรับ autosave และ Import/Export เช่นเดียวกับรายการแทนที่ปกติ
- ไม่นำรายการที่มีค่าปลายทางว่างไปใส่ใน initial prompt ของ whisper.cpp

## 2026-07-15 — Quality-of-life persistence, ETA, recovery, and logo

- Added smoothed remaining-time estimates for browser uploads, FFmpeg conversion, Whisper transcription, video re-upload, and FFmpeg render progress.
- Added backend-persisted preferences for the latest model, language, CPU threads, theme, font, and subtitle appearance so random portable loopback ports do not reset settings.
- Added atomic editor backup and restart recovery for validated SRT content without persisting or owning the user's source media.
- Added glossary autosave plus JSON export and JSON/text/CSV import.
- Added a cyclic “next quality issue” action and visible autosave status.
- Added the supplied “Free SRT x Great” logo to the app header, welcome state, favicon, and portable static assets.
- Updated the portable build to preserve personal JSON data in the runnable dist folder while keeping it out of the release ZIP.
# Update log

## 2026-07-15 — Editor layout and FFmpeg preview parity

- Fixed the quality-check bar being pushed over cue timestamps when optional Editor panels are hidden by assigning every Editor section to a stable grid row.
- Increased the desktop Editor workspace by roughly 200–300 px so opening subtitle appearance controls leaves a useful cue-editing area.
- Subtitle size, outline, shadow, and edge margin now support decimal precision end to end.
- Reworked live subtitle preview scaling around FFmpeg's 288-high SRT-to-SSA script space and the video's real contained frame, including letterboxed video, hard shadow offsets, and opaque-box padding.

## 2026-07-15 — Subtitle appearance controls and sticky editor

- Added live controls for font size, outline/stroke width, translucent background, shadow depth, vertical position, and edge margin.
- Passed the same validated style settings to FFmpeg/libass render jobs; arbitrary force-style values are not accepted from the browser.
- Added persistent subtitle-style preferences in local browser storage.
- Made the video panel and Editor toolbar sticky on desktop, with the cue list scrolling independently; retained a normal stacked flow on tablet/mobile.
- Verified the SRT-to-SSA alignment mapping through real FFmpeg output (`6` top-center, `10` middle-center, `2` bottom-center) to keep rendered text centered like the live preview.
- Added regression coverage for style defaults, validation, generated FFmpeg style values, and render-job option propagation.

## 2026-07-15 — Windows local-file dialog hotfix

- Fixed the native Windows file picker failing before opening with `c_wchar_Array ... instead of c_wchar_p` by explicitly casting the writable path buffer to `LPWSTR`.
- Added explicit `GetOpenFileNameW` argument/return types and now distinguish user cancellation from a Windows Common Dialog error.
- Added a Windows regression test that constructs the exact dialog structure without opening interactive UI.

## 2026-07-15 — Editor visual redesign and theme switcher

- Rebuilt the Editor shell to match the approved Free SRT design: compact product header, video preview on the left, cue editor and font controls on the right, quality summary below the cue list, and render results across the bottom.
- Added persistent light and dark themes, with accessible theme controls and shared color tokens across setup, editor, dialogs, progress, and render states.
- The preview now seeks to the first subtitle cue after media metadata loads so the live subtitle overlay is visible immediately instead of showing a bare first frame.
- Kept the side-by-side desktop layout through laptop widths and added a deliberate stacked mobile layout with subtitle preview scaling for small screens.
- Clarified the portable artifact location: use `dist/FreeSRT/FreeSRT.exe` or the executable inside `dist/FreeSRT-portable.zip`; the stale top-level `dist/FreeSRT.exe` is not the current one-folder build.

## 2026-07-15 — Live video subtitle editor and MP4 rendering

- Changed the Subtitle Editor to a responsive two-panel workspace with video preview on the left and cue editing on the right.
- Added a live HTML subtitle overlay that updates immediately when cue text or timestamps change, highlights the active cue, and links overlay/cue navigation.
- Added a backend font registry with `Leelawadee UI` as the default plus Tahoma, Segoe UI, and Arial; the same font and size selections drive preview and FFmpeg output.
- Added opaque HTTP Range-capable preview for user-owned local video sources without exposing filesystem paths.
- Added cancellable FFmpeg render jobs that burn a validated SRT snapshot into H.264/AAC MP4, report progress, preview/download the final result, and clean uploaded input, SRT snapshots, and partial MP4 files.
- Added regression coverage for font metadata, source privacy, render start/cancellation idempotency, terminal-state races, and render cleanup.

## 2026-07-13 — Large local media workflow

- Added an opaque, expiring local-file selection API backed by the Windows native file dialog for large media, without exposing source paths to the browser.
- Added fprobe media/audio validation and temporary-WAV free-space checks before transcription starts.
- Local source files are now explicitly marked as user-owned and are never deleted; uploaded copies retain existing cleanup behavior.
- Portable mode now allows one active transcription at a time.
- Kept upload and drag-and-drop workflow for small files/server use, with clearer UI guidance.
- Added regression coverage for opaque selections, local-source cleanup, and single-job enforcement.

# Update log

## 2026-07-13 — Whisper zero-duration subtitle repair

- Fixed completed Whisper output being rejected when a cue had equal start/end timestamps (`Subtitle block N must end after it starts`).
- Generated Whisper SRT is now repaired to a minimum 500 ms duration and normalized before the original copy is stored.
- Strict validation remains unchanged for user-edited SRT saves.
- Added a regression test; the suite now contains 19 tests.
- Rebuilt and completed an end-to-end portable transcription using bundled FFmpeg and whisper.cpp.
- Corrected the PyInstaller one-folder spec to avoid embedding binaries twice; `FreeSRT.exe` is now about 6 MB and the portable ZIP about 192 MB.


## 2026-07-13 — Clean-machine runtime diagnostics hotfix

- Fixed the confirmed root cause of clean-machine `[WinError 2]`: FFmpeg conversion used the literal `ffmpeg` system-PATH command while preflight checked the bundled executable. Conversion now invokes `FFMPEG_EXE` by absolute bundled path.
- Added explicit Windows DLL/PATH search setup for bundled FFmpeg and whisper.cpp child processes.
- Added preflight checks before a transcription job starts; missing/unloadable runtime components now return a component-specific message.
- Added `GET /api/diagnostics` exposing frozen state, resource/app paths, bundled binary existence, model directory, and writable data directories.
- Rebuilt and smoke-tested the portable executable with `frozen=True`, HTTP 200, five model records, and both bundled binaries detected. Added diagnostics and bundled-FFmpeg command regression tests; the suite now has 18 tests. Completed an end-to-end portable smoke test: upload → bundled FFmpeg conversion → bundled whisper.cpp → generated SRT.


## 2026-07-11 — Portable Windows EXE

### Added

- PyInstaller one-folder build with `FreeSRT.exe` launcher.
- `launcher.py` chooses an available loopback port, starts Flask, waits for readiness, and opens the browser.
- Frozen-runtime path handling separates bundled `_MEIPASS` resources from writable data beside the executable.
- `FreeSRT.spec` includes templates, static assets, whisper.cpp runtime DLLs, `whisper-cli.exe`, FFmpeg, and ffprobe.
- `build_portable.ps1` validates inputs, installs PyInstaller when needed, builds the folder, creates writable data directories, and creates `dist/FreeSRT-portable.zip`.
- `PORTABLE_BUILD.md` documents build, clean-machine testing, runtime layout, and shutdown behavior.
- `requirements-dev.txt` records the PyInstaller build dependency separately from runtime requirements.

### Verified

- `dist/FreeSRT/FreeSRT.exe` starts without importing Python/Flask from the host environment.
- Built executable served `/` with HTTP 200 and returned all five model records from `/api/models`.
- Bundled FFmpeg responds to `-version`.
- Bundled whisper.cpp responds to `-h` and exposes the expected `--prompt` option.
- Final artifact: `dist/FreeSRT-portable.zip` (models intentionally excluded).

### Distribution note

- The current bundle is Windows x64 and CPU/GGML oriented.
- FFmpeg redistribution requires following the license and notices for the selected FFmpeg build.
- The windowless launcher remains active after the browser closes; terminate `FreeSRT.exe` from Task Manager until a tray/quit workflow is added.


## 2026-07-11 — Editor timestamp overlap hotfix

- Fixed timestamp inputs overflowing their CSS Grid track and appearing underneath the subtitle textarea.
- Changed cue columns and the two timestamp tracks to `minmax(0, ...)` so intrinsic input width cannot expand the grid.
- Added `min-width: 0` constraints to time, text, and action grid children.
- Applied the same constraint at the medium-screen breakpoint and allowed long subtitle text to wrap safely.
## 2026-07-11 — Phase 5–6 Subtitle Editor and glossary

### Added

- In-page Subtitle Editor with local audio/video playback and active-cue highlighting.
- Per-cue play, text/time editing, add, delete, split, and merge operations.
- Undo/Redo history and keyboard shortcuts for save, playback, undo, and redo.
- Find/Replace All with match count and confirmation.
- Persistent glossary (“สมุดคำศัพท์”) stored at `data/glossary.json`.
- Glossary replacement workflow for the current subtitles.
- whisper.cpp initial prompt populated from glossary preferred terms using the verified `--prompt` option.
- Backend SRT parser, validation, normalization, atomic save, and reset APIs.
- Original Whisper output stored as `<task_id>.original.srt` before editing.
- Quality checks for empty text, invalid/overlapping time, line count, line/total length, reading speed, and long duration.
- Responsive Editor layout, visible saved/unsaved state, unsaved-page warning, and accessible input labels.
- Eight additional automated tests; total test count is now 16.

### API

- `GET|PUT /api/glossary`
- `GET|PUT /api/subtitles/<task_id>`
- `POST /api/subtitles/<task_id>/reset`

### UX decisions

- Media preview uses the browser's existing local File object and does not upload the source again.
- Automated quality checks only flag issues; they never rewrite transcript content.
- Glossary application and bulk replacement require user confirmation.
- Download automatically saves pending valid edits first.

### Known limitations

- Refreshing the page loses the local media File object and in-memory task state.
- Editor state is not yet a persistent project format.
- Visual browser automation against localhost is restricted by the current sandbox; syntax, assets, Flask rendering, APIs, and interaction logic are covered by static checks and automated tests.
- 
## 2026-07-11 — Phase 1–4 cancellation and model guidance

### Added

- Cancel endpoint for active model downloads: `POST /api/models/<filename>/cancel`.
- Cancel endpoint for queued/converting/transcribing jobs: `POST /api/transcribe/<task_id>/cancel`.
- Browser-side upload cancellation using `XMLHttpRequest.abort()`.
- Explicit `cancelling` and `cancelled` states for model downloads and transcription jobs.
- Cross-platform process-tree termination helper for FFmpeg and whisper.cpp.
- Cancel tokens and active subprocess tracking in internal job state.
- Plain-language Thai metadata for all five offered Whisper models, including speed, accuracy, recommended use, memory guidance, and badges.
- Responsive model guide cards and cancel controls in the frontend.
- Eight automated unit/API tests covering cancellation, cleanup, metadata, serialization, and queued job creation.
- Project documentation in `README.md` and development invariants in `AGENTS.md`.

### Changed

- Application now binds to `127.0.0.1` with debug mode disabled by default, matching the local-first distribution goal.
- Download state is initialized before its worker thread starts, removing a race where cancellation could arrive before state existed.
- Internal synchronization/process objects are excluded from status API responses.
- Download requests now use connect/read timeouts and validate HTTP response status.
- CPU thread input is validated and constrained to 1–64.
- Invalid model names are rejected before transcription starts.
- UI language and model explanations were rewritten for non-technical Thai users.
- Model and transcription finalization now share the state lock with cancellation to avoid contradictory terminal states.

### Cleanup behavior

- Cancelled model downloads remove the incomplete `.tmp` file.
- Cancelled/failed transcription jobs remove the uploaded original, converted WAV, and incomplete SRT.
- A completed SRT is preserved and cannot be invalidated by a late cancellation request.

### Known limitations

- State remains in memory and is intended for a single Flask process.
- Concurrent transcription jobs are not yet queued or rate-limited.
- Media validation still relies on FFmpeg; dedicated `ffprobe` validation is planned.
- Portable `.exe` packaging is planned for the next phase and is not part of this release.
