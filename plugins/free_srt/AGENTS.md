# AGENTS.md

## Project purpose

Free SRT is a local-first Flask application that converts audio/video into SRT subtitles through FFmpeg and whisper.cpp. The primary distribution target is a portable Windows one-folder ZIP; Docker may be added later as an optional server deployment.

## Current development boundary

- Keep Flask and the framework-free frontend unless a feature clearly requires a client framework.
- Bind local development/portable builds to `127.0.0.1` by default.
- Do not package or commit model files, generated SRT files, uploads, virtual environments, downloaded archives, or compiled caches.
- Preserve Windows compatibility. If adding Linux support, isolate platform-specific process handling.
- Do not add Redis/Celery or multi-worker serving until persistent/multi-user job state is explicitly designed.

## Architecture invariants

- FFmpeg converts every supported input to 16 kHz mono PCM WAV.
- whisper.cpp is the only transcription engine unless a future requirement says otherwise.
- Active jobs own a `threading.Event` cancellation token and, when applicable, a `subprocess.Popen` handle.
- Keys beginning with `_` are internal job state and must never be returned as JSON. Use `public_state()`.
- Cancellation is not failure. It must finish as `cancelled`, never `failed`.
- Cancellation endpoints must remain safe to call more than once.
- A terminal job (`completed`, `failed`, `cancelled`) must not be changed by a late cancel request.
- Always remove original uploads and converted WAV files in worker cleanup. Remove partial SRT/model `.tmp` files on cancellation or failure.
- Local-file selections are opaque, single-use, and expiring. Their source files are user-owned and must never be removed; only browser-upload copies are app-owned.
- Finalization and cancellation must use `state_lock` to prevent completion/cancellation races.
- Terminate the whole child process tree, not only the immediate process.
- Video render jobs follow the same cancellation rules as transcription jobs. Render from a validated per-job SRT snapshot, finalize MP4 with `os.replace` under `state_lock`, and remove uploaded render inputs, SRT snapshots, and partial MP4 files on every non-success path.
- Local-source video preview and rendering must use the job's private opaque source reference. Never expose the user's filesystem path or delete a user-owned source file.

## Model metadata

`MODELS_INFO` is the single source of truth for model descriptions shown in the UI. Every model must provide:

- `name`
- `url`
- `size`
- `description`
- `speed`
- `accuracy`
- `recommended_for`
- `memory_hint`
- `badge`

Use plain Thai wording suitable for non-technical users. Avoid promising exact accuracy or processing time.

## Editor and glossary invariants

- Preserve the first successful Whisper output as `<task_id>.original.srt`; edits only replace `<task_id>.srt`.
- Validate and normalize SRT on the backend before every save. Never trust browser-only validation.
- Write edited SRT and glossary data through a temporary file followed by `os.replace`.
- `data/glossary.json` is user data. Do not overwrite it during upgrades or package it with personal entries.
- Use the glossary `to` values with whisper.cpp's `--prompt` long option. `-p` means processors and must not be used for prompts.
- Glossary replacements must show a count and require confirmation before applying multiple edits.
- Quality checks advise the user but must not silently rewrite spoken content.
- Keep media playback local through the browser File object unless persistent projects are explicitly designed.
- Persist portable UI preferences and crash-recovery subtitle content under DATA_FOLDER; never rely on browser localStorage alone because the launcher uses a different loopback port each run.
- Editor backup may persist validated subtitle content and style metadata, but must not persist or copy source media paths/files.
- Personal glossary, preferences, and editor backup files may be restored to the runnable developer dist after a build, but must never be included in the release ZIP.
- Preserve accessible labels, keyboard shortcuts, visible save state, and unsaved-change protection when changing Editor UX.
- Subtitle appearance values must be range-validated on the backend with at most two decimal places. Live preview must scale from the contained video frame using FFmpeg's 288-high SRT-to-SSA script space and preserve libass-style per-line backgrounds.
- Subtitle appearance values must be backend allow-listed and range-validated before building FFmpeg `force_style`; the live overlay and rendered MP4 must use the same selected values.
- `SUBTITLE_FONTS` is the single source of truth for selectable preview/render fonts. Keep `Leelawadee UI` as the default unless a future requirement changes it; font keys received from the browser must be allow-listed.
- Live subtitle preview must update without invoking FFmpeg. FFmpeg runs only when the user explicitly starts creation of the final video.

For Editor/glossary changes, test SRT round trips, invalid input non-overwrite, original reset, glossary persistence/duplicates, and the exact whisper.cpp prompt flag.
## Portable build invariants

- PyInstaller uses `launcher.py` as the entry point and builds a Windows x64 one-folder application named `FreeSRT` with `exclude_binaries=True`; binaries belong only in COLLECT and must not be embedded twice.
- `RESOURCE_DIR`/`sys._MEIPASS` is for bundled templates, static assets, whisper.cpp, and FFmpeg; `APP_DIR` is for user-writable models, outputs, uploads, and data.
- Never write user data under the PyInstaller internal resource directory.
- Build includes only `whisper-cli.exe`, its DLLs, `ffmpeg.exe`, and `ffprobe.exe`; do not include whisper.cpp test executables.
- Runtime uses a free loopback port and opens the browser automatically. It must never bind publicly by default.
- Model files are not bundled into the release ZIP unless an explicitly named offline bundle is requested.
- Keep `dist/` and `build/` out of source control; release artifacts are generated by `build_portable.ps1`.
- Review FFmpeg licensing and include the required notices before distributing the ZIP.
## Testing requirements

Before handing off a code change, run:

```powershell
.\venv\Scripts\python.exe -m py_compile app.py download_whisper.py
.\venv\Scripts\python.exe -m unittest scratch.test_app_unit -v
```

For changes to subprocess control, cover at least:

- cancellation before process start
- cancellation while a process is active
- cancellation near successful completion
- idempotent repeated cancellation
- cleanup of input, WAV, partial SRT, and model `.tmp`
- absence of internal state in API JSON

The manual `scratch/test_app.py` integration test may download a model and must not be run unintentionally.

## Updating documentation

- Record user-visible and architectural changes in `update.log.md`.
- Update `README.md` when setup, behavior, endpoints, limitations, or packaging plans change.
- Update this file when development invariants change.

## Ruflo integration

For future multi-file or complex feature work, use Ruflo ToolSearch/MCP tools when they are available in the active environment. If unavailable, state that briefly and continue with local inspection, a written plan, focused edits, and verification.

# Safety Rules

- Ask before running rm, chmod, or sudo.
- Never delete outside the temporary folder.
- Do not rewrite git history.
