# Free SRT Portable Build

This project produces a Windows x64 one-folder portable release.

## Release packages

Running the build creates two ZIP files:

- `dist\FreeSRT-portable.zip` — the default all-in-one package with CPU, NVIDIA CUDA 11.8, and Vulkan runtimes.
- `dist\FreeSRT-portable-CPU.zip` — a smaller CPU-only alternative.

Models and personal data are intentionally excluded from both ZIP files. The first launch downloads the model selected by the user into `models\`.

GPU acceleration still requires a compatible graphics driver. If a GPU runtime cannot start or runs out of memory, Free SRT automatically falls back to the bundled CPU runtime.

## Build on the development machine

From the project root in PowerShell:

```powershell
.\build_portable.ps1
```

The script validates Python/frontend assets, runs PyInstaller, creates the CPU-only archive, verifies the official CUDA runtime SHA-256, adds both GPU runtimes, and creates the all-in-one archive. Before each ZIP is created it enforces the portable binary allow-list and rejects AVX-512 CPU backend DLLs (`cascadelake`, `skylakex`, `icelake`, and `cannonlake`) in both the base and GPU runtimes. It preserves developer/user JSON data in the runnable `dist\FreeSRT\data` folder but never puts those files into release ZIPs.

The pinned CUDA asset is the official whisper.cpp 1.9.1 CUDA 11.8 Windows x64 release. The Vulkan runtime is built from official whisper.cpp v1.9.1 source commit `f049fff95a089aa9969deb009cdd4892b3e74916` with LunarG Vulkan SDK 1.4.350.0.

To rebuild Vulkan from source:

```powershell
.\build_gpu_runtimes.ps1 `
  -WhisperCppSource .\build\whisper.cpp-v1.9.1 `
  -OutputRoot .\build\gpu-artifacts `
  -Backend vulkan `
  -VulkanSdk .\build\vulkan-sdk
```

The build script expects `build\gpu-artifacts\FreeSRT-whisper-vulkan-win-x64-1.9.1-freesrt.1.zip`. It downloads CUDA automatically when the cached official archive is missing or fails checksum validation.

## Test the built folder

```powershell
.\dist\FreeSRT\FreeSRT.exe
```

The executable starts a local server on an available loopback port and opens the browser. This release is windowless; terminate `FreeSRT.exe` from Task Manager when you want to stop the local server. A console build can be made by changing `console=False` to `console=True` in `FreeSRT.spec` for debugging.

For troubleshooting, open `/api/diagnostics` on the local port to inspect frozen/resource paths, bundled executable availability, and GPU hardware/runtime status. The response does not expose user-owned media paths.

## Clean-machine test

Copy only the extracted `FreeSRT-portable.zip` contents to a Windows machine without Python, Flask, FFmpeg, whisper.cpp, CUDA Toolkit, or Vulkan SDK. Install the current GPU driver from NVIDIA/AMD/Intel, launch `FreeSRT.exe`, download a model, and transcribe a short WAV/MP4 using Auto, CUDA, and Vulkan as applicable.

The portable build includes `ffprobe.exe` and uses the Windows Common Dialog API for its native file picker. Large media selected through the app is processed in place; only the generated WAV is created under the writable `uploads\` directory. The source media is never deleted.

Review the FFmpeg license and ship its required notices when redistributing the package.

## Transactional staging and recovery

`build_portable.ps1` no longer builds over the runnable developer dist. Each invocation uses `build\portable-staging\<build-id>` for PyInstaller output and release archives. Before any build work, the approved personal JSON files (`glossary.json`, `preferences.json`, and `editor-backup.json`) are copied byte-for-byte to `build\portable-recovery\<build-id>`.

The CPU and all-in-one ZIP files are created before personal JSON is restored to the staged runnable folder. Both archives are inspected and the build stops if any approved personal JSON entry is present. The existing `dist\FreeSRT` and release ZIPs are not moved until the staged runnable, binary policy, and archive exclusions have passed.

Promotion retains the previous runnable and ZIPs under unique `.rollback-<build-id>` names. If a move or archive promotion fails, the helper restores the previous paths and moves the failed new artifact back to staging with a `.failed-promotion` suffix. Recovery and failed staging paths are printed on every failure; they are intentionally not deleted automatically.

Path validation in `build_portable_helpers.ps1` rejects recovery, staging, rollback, or promotion targets outside the project workspace. The isolated recovery suite uses only a generated system temporary directory and does not invoke PyInstaller, download runtimes, touch the real dist, or inspect real user data:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scratch\test_build_portable_recovery.ps1
```

The `-ExecutionPolicy Bypass` value applies only to that PowerShell process and does not change the machine policy. A real `build_portable.ps1` run can install PyInstaller, download the official CUDA archive when absent, and replace release artifacts after validation; run it only when those operations are explicitly intended.