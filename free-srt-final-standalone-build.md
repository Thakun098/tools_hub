# Free_SRT Final Standalone Build

Date: 2026-08-04
Status: FINAL STANDALONE - READY FOR MANUAL TEST

## Primary artifact

D:	ools_hub\pluginsree_srt\dist\FreeSRT-portable.zip

Size: 487,084,987 bytes
SHA-256: AFD3D652E92DB56E8CBAE90B60B84DFD7FF80F7C0CF3C523F5989F5E1085E65E

Included runtimes:
- CPU whisper.cpp runtime
- CUDA 11.8 runtime, version 1.9.1-freesrt.1
- Vulkan runtime, version 1.9.1-freesrt.1
- FFmpeg and FFprobe
- Standalone FreeSRT.exe and all static/runtime dependencies

## Validation

- 95 Python tests passed.
- 3 JavaScript tests passed.
- Portable runtime binary policy passed.
- ZIP integrity passed (127 entries).
- CUDA entries: 17.
- Vulkan entries: 8.
- Runtime manifests for CUDA and Vulkan are present.
- Archive contains no files from data, uploads, outputs, or models.
- Final executable returned HTTP 200.
- Runtime smoke detected CUDA installed and Vulkan installed.
- Vulkan was available and selected on the current machine.
- CUDA is packaged but was not available on the current hardware.
- No smoke-test process remains running.

## Additional artifacts

CPU-only:
D:	ools_hub\pluginsree_srt\dist\FreeSRT-portable-CPU.zip
SHA-256: 799CBEF3BF6EE3F530906B5FB0A918F7D29AD6B366BF7B8CBEBA6EEFBC8B26FD

Runnable folder:
D:	ools_hub\pluginsree_srt\dist\FreeSRT\FreeSRT.exe
SHA-256: BC686CD0E9391F4945AC8EA19652DCAAEF72DF62EE1CE470DEF97D07511FB659

Previous standalone rollback:
D:	ools_hub\pluginsree_srt\dist\.FreeSRT.rollback-ea1f21a739504eb38220eff19826f5e6

Source changes remain uncommitted pending manual acceptance.
