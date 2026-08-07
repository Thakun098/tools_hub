# Phase 1 — Standalone FreeSRT baseline

Date: 2026-08-04

## Result

The nested FreeSRT repository is restored to the standalone baseline:

- Branch: `main`
- Commit: `d0c9309` (`Free_SRT_v4_beta`)
- Working tree: clean
- Hub preservation remains available at `preserve/hub-spike-20260804` / `0476677`

No source changes were needed in this phase; switching back to the verified baseline restored the standalone contract.

## Contract checks

- `app.py` exports a Flask `app` object.
- Standalone routes are mounted at `/` and `/api/*`.
- `/srt/` is not a registered route.
- `launcher.py` starts on `127.0.0.1` using a free port and serves `/` successfully.
- `RESOURCE_DIR` remains separate from writable `APP_DIR` paths.
- Existing `data/`, `models/`, `uploads/`, `outputs/`, and `gpu-runtimes/` directories were not deleted or rewritten.

## Validation gate

```powershell
.\venv\Scripts\python.exe -m py_compile app.py download_whisper.py
```

Result: passed.

```powershell
.\venv\Scripts\python.exe -m unittest scratch.test_app_unit -v
```

Result: `Ran 79 tests ... OK`.

Additional checks passed:

- route smoke: 36 routes, root and `/api/models` available, no `/srt` route;
- launcher smoke: local server responded `200` at `http://127.0.0.1:<free-port>/`.

## Scope boundary

Phase 1 only restores and validates the standalone baseline. Whisper segmentation flags, automatic post-processing, manual split behavior, and the golden corpus remain for later phases.
