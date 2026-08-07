# Phase 2–5 — Subtitle segmentation implementation and build gate

Date: 2026-08-04

## Implemented

- Added framework-independent `freesrt/segmentation.py` with:
  - grapheme-safe units for Thai combining marks and emoji sequences;
  - 35 display-unit line target, 2-line layout, and 70-unit cue cap;
  - 7-second hard duration target and 20 display-units/second reading-speed check;
  - natural punctuation/whitespace boundaries with grapheme fallback;
  - proportional timestamp allocation without overlap or zero-length cues;
  - explicit `SEGMENTATION_UNRESOLVED`/`MIN_DURATION_UNRESOLVED` issues;
  - text-conservation and idempotent behavior covered by tests.
- Whisper invocation now includes `--max-len 35 --split-on-word`.
- Worker flow writes repaired raw Whisper cues to `<task_id>.original.srt`, then writes segmented/wrapped cues to the working `<task_id>.srt`.
- Segmentation issues are retained in job state and logs; no placeholder `...` is generated.
- Manual editor split now uses grapheme-aware midpoint/natural boundaries, enforces a safe 500 ms minimum on both sides, preserves the original cue end, and never emits a placeholder.
- Frontend quality checks now use grapheme-aware counts and the 35/70 policy.

## Validation gate

- Existing application unit suite: `79` tests, `OK`.
- Segmentation unit suite: `7` tests, `OK`.
- Segmentation integration suite: `2` tests, `OK`.
- Combined result: `88` tests, `OK`.
- Python compile gate: passed for app, workers, segmentation, routes, and new tests.
- JavaScript syntax gate: passed for `static/app.js` and all `static/js/*.js` modules.
- Bundled `whisper-cli.exe -h` confirmed both `--max-len` and `--split-on-word`.
- PyInstaller standalone staging build: passed with `FreeSRT.spec` into `build/phase5-dist`.
- Staged portable runtime policy: passed for `build/phase5-dist/FreeSRT`.
- Built executable launcher smoke: served `/` with HTTP `200` on a loopback free port; the test process was terminated afterward.

## Safety and scope

The implementation remains on standalone `main` and does not reintroduce Hub imports or `/srt` routes. The Hub spike is still recoverable from `preserve/hub-spike-20260804` / `0476677`. Existing user-data directories under the source checkout were not copied into the staged build or modified by the gate.

The current source changes are intentionally left uncommitted for review. The next recommended step is a real-media acceptance pass using Thai, mixed Thai/English, and long-paragraph recordings before creating a release commit/tag.
