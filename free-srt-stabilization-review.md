# Free_SRT Stabilization Review (post Phase 0-5)

Date: 2026-08-04
Method: scrutinize outsider review plus end-to-end trace
Verdict: SHIP TO MANUAL TEST

## Intent and simpler alternative

Goal: keep Free_SRT standalone while producing readable, deterministic subtitle cues without lost text, synthetic ellipses, invalid timing, or destructive edits.

The deterministic post-processor remains necessary because whisper.cpp flags are hints rather than a hard contract. One smaller correction was made during review: proportional splitting cannot improve aggregate reading speed, so the ineffective speed-driven fragment count was removed. Excess reading speed is now reported explicitly as READING_SPEED_UNRESOLVED.

## Findings fixed before build

1. Visual layout could silently produce a 36-character line because cue capacity excluded spaces while line capacity included them.
2. Natural-boundary selection could prefer a distant whitespace over a balanced split.
3. Proportional time allocation could still create fragments longer than the 7-second hard limit.
4. Re-segmenting wrapped punctuation could split a previously stable cue because an inserted newline became a space.
5. Python and browser grapheme counting disagreed for Thai Sara Am.
6. Manual split ignored caret position and text/media ratio.
7. Editing a textarea and immediately clicking Split lost the click during DOM re-render; undo also lacked a separate pending-edit checkpoint.
8. PowerShell code-page corruption was detected and repaired; an encoding sweep now guards the changed sources.

## Verified trace

Whisper command (--max-len 35, --split-on-word) -> parse/repair -> immutable <task_id>.original.srt -> deterministic backend segmentation -> <task_id>.srt -> editor/export/render.

The working output is the file consumed by editor, SRT/TXT export, and video rendering. Reset restores the original Whisper output.

## Gates passed

- Python unit/integration: 95 tests passed.
- JavaScript helper tests: 3 passed.
- Deterministic property sweep: 2,000 cases passed.
- Python compilation and all frontend JavaScript syntax checks passed.
- Text conservation, monotonic timestamps, no new gaps/overlaps, hard line cap, hard duration cap-or-explicit-unresolved, idempotence, and Unicode/Thai checks passed.
- Real-browser Playwright flow passed:
  - caret split produced the expected two text parts and proportional timestamp;
  - edit-then-split produced a third cue without losing text;
  - first Undo reverted split, second Undo reverted the pending edit.
- PyInstaller build passed.
- Portable runtime policy passed.
- Built executable smoke returned HTTP 200 and the Free SRT page.
- No test browser or fixture server remains running.

## Manual-test artifact

Executable:
D:	ools_hub\pluginsree_srtuild\scrutinize-dist\FreeSRT\FreeSRT.exe

Keep FreeSRT.exe beside its _internal directory. The artifact has empty models, uploads, outputs, data, and gpu-runtimes directories.

Executable SHA-256:
527BAB58F475A4BD9D4B07B34E952E0C76B75BA300D95DD993A0970DF26CBD06

## Suggested manual acceptance

1. Transcribe one real Thai file with long speech and little punctuation.
2. Confirm generated cues stay at two lines and 35 display graphemes per line.
3. Confirm no placeholder ... is invented.
4. Verify original reset, manual caret split, edit-then-split, and two-step Undo.
5. Export SRT/TXT and render a short video; compare cue text/timestamps across all outputs.
6. Inspect any *_UNRESOLVED log entries instead of expecting the app to hide impossible timing or reading-speed constraints.

Source changes remain uncommitted for review.
