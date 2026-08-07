# Third-party notices

Free SRT distributes separate third-party executables and runtime libraries. Free SRT invokes FFmpeg and whisper.cpp as child processes; this notice does not replace the license texts supplied in `licenses\`.

## FFmpeg 8.1.1 full build

- Files: `ffmpeg.exe`, `ffprobe.exe`
- Binary provider: Gyan Doshi Windows builds — https://www.gyan.dev/ffmpeg/builds/
- Upstream: https://ffmpeg.org/
- Corresponding upstream source tag: https://github.com/FFmpeg/FFmpeg/tree/n8.1.1
- License of this build: GNU GPL version 3 because its configuration contains `--enable-gpl --enable-version3` and GPL components including libx264/libx265.
- License text: `licenses\GPL-3.0.txt`

The packaged binaries report `ffmpeg version 8.1.1-full_build-www.gyan.dev`, are statically built, and expose their complete configure line through `ffmpeg -version`. Distributors should host the exact corresponding source/build information alongside release downloads and review FFmpeg's current compliance checklist at https://ffmpeg.org/legal.html.

## whisper.cpp 1.9.1 / ggml

- Files: CPU, CUDA, and Vulkan `whisper-cli.exe` plus `ggml*.dll` and `whisper.dll`
- Upstream: https://github.com/ggml-org/whisper.cpp
- Pinned source commit: `f049fff95a089aa9969deb009cdd4892b3e74916`
- License: MIT
- License text: `licenses\whisper.cpp-MIT.txt`

The CUDA package is the official whisper.cpp v1.9.1 Windows x64 CUDA 11.8 release. The Vulkan package was built locally from the pinned source commit with `GGML_VULKAN=ON` and LunarG Vulkan SDK 1.4.350.0.

## NVIDIA CUDA 11.8 runtime libraries

- Files include CUDA runtime/NVRTC libraries shipped in the official whisper.cpp CUDA archive.
- NVIDIA CUDA Toolkit 11.8 documentation and EULA: https://docs.nvidia.com/cuda/archive/11.8.0/
- CUDA library redistribution guidance: https://docs.nvidia.com/cuda/archive/11.8.0/cuda-c-best-practices-guide/index.html#cuda-toolkit-library-redistribution

The NVIDIA display driver is not included. End users must install a compatible NVIDIA driver.

## Vulkan

The Vulkan SDK is used only to build `ggml-vulkan.dll` and is not included in the release. At runtime, the application uses the Vulkan loader and GPU driver installed by the graphics hardware vendor. LunarG Vulkan SDK: https://vulkan.lunarg.com/

This notice is informational and is not legal advice. Anyone redistributing the ZIP should independently verify obligations for their release channel and jurisdiction.