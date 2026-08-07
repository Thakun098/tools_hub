# Phase 0 baseline — FreeSRT before standalone rework

Date: 2026-08-04

## Snapshot

FreeSRT is a nested Git repository at `plugins/free_srt/`.

- Baseline before the Hub spike: `d0c9309` (`Free_SRT_v4_beta`)
- Preservation branch: `preserve/hub-spike-20260804`
- Preservation commit: `0476677` (`chore: preserve hub integration spike before standalone rework`)
- Working tree after the preservation commit: clean

The preservation commit contains only the Hub integration spike files:

- `app.py`
- `static/app.js`
- `templates/index.html`
- `__init__.py`
- `plugin.json`

The commit intentionally excludes user data, downloaded models, runtimes, virtual environments, build output, and generated media.

## Baseline validation

Command:

```powershell
.\venv\Scripts\python.exe -m py_compile app.py download_whisper.py
```

Result: passed.

Command:

```powershell
.\venv\Scripts\python.exe -m unittest scratch.test_app_unit -v
```

Result: failed before any test body ran: 79 errors. Every case fails in `scratch/test_app_unit.py:57` because the preserved Hub spike removed the standalone `app.app` Flask object and route registration from `app.py`.

This is the expected pre-rollback failure and is recorded here so Phase 1 can prove the standalone contract was restored.

## Environment recorded

- Python 3.11.15
- Flask 3.1.3
- requests 2.34.2
- PyInstaller 6.21.0
- Werkzeug 3.1.8
- Jinja2 3.1.6

Full dependency declarations remain in `plugins/free_srt/requirements.txt` and `plugins/free_srt/requirements-dev.txt`.

## User-data safety check

The following directories were present but were not staged or committed:

`data/`, `models/`, `uploads/`, `outputs/`, `output/`, `gpu-runtimes/`, `venv/`, `build/`, and `dist/`.

Phase 0 does not delete, move, or rewrite any of them. The preservation commit is therefore recoverable with:

```powershell
cd plugins/free_srt
git switch preserve/hub-spike-20260804
```

The next phase may restore the standalone baseline from `d0c9309`; this preservation branch must remain available until the standalone acceptance gate passes.
