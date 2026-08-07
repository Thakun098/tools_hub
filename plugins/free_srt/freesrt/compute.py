"""Compute backend catalog, validation, and lightweight GPU discovery helpers."""

import hashlib
import os
import re
import zipfile


COMPUTE_MODES = {"cpu", "gpu"}
GPU_BACKENDS = {"auto", "cuda", "vulkan"}
GPU_RUNTIME_VERSION = os.environ.get("FREESRT_GPU_RUNTIME_VERSION", "1.9.1-freesrt.1")

DEFAULT_GPU_RUNTIME_ARTIFACTS = {
    "cuda": {
        "url": "https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.1/whisper-cublas-11.8.0-bin-x64.zip",
        "sha256": "aecdce0e4d4bb758a7c72a31f3f9f19a7b6d861405fd2da743cd86398633c963",
        "size": "ประมาณ 266 MB",
        "source": "whisper.cpp 1.9.1 (CUDA 11.8) รุ่นทางการ",
    },
    "vulkan": {
        "url": "",
        "sha256": "",
        "size": "",
        "source": "FreeSRT build จาก source ทางการของ whisper.cpp 1.9.1",
    },
}


def _runtime_artifact(backend):
    specific = os.environ.get(f"FREESRT_GPU_{backend.upper()}_URL", "").strip()
    base = os.environ.get("FREESRT_GPU_RUNTIME_BASE_URL", "").strip().rstrip("/")
    configured_url = specific
    if not configured_url and base:
        configured_url = f"{base}/FreeSRT-whisper-{backend}-win-x64-{GPU_RUNTIME_VERSION}.zip"
    if configured_url:
        return {
            "url": configured_url,
            "sha256": os.environ.get(f"FREESRT_GPU_{backend.upper()}_SHA256", "").strip().lower(),
            "size": os.environ.get(f"FREESRT_GPU_{backend.upper()}_SIZE", "").strip(),
            "source": "แพ็กเกจที่ผู้ดูแลระบบกำหนด",
        }
    return dict(DEFAULT_GPU_RUNTIME_ARTIFACTS[backend])


CUDA_ARTIFACT = _runtime_artifact("cuda")
VULKAN_ARTIFACT = _runtime_artifact("vulkan")


GPU_BACKENDS_INFO = {
    "cuda": {
        "name": "NVIDIA CUDA",
        "description": "เร่งด้วย CUDA สำหรับการ์ดจอ NVIDIA",
        **CUDA_ARTIFACT,
        "version": GPU_RUNTIME_VERSION,
        "vendors": ["nvidia"],
        "badge": "NVIDIA",
    },
    "vulkan": {
        "name": "Vulkan",
        "description": "เร่งด้วย Vulkan สำหรับการ์ดจอ AMD, Intel และ NVIDIA",
        **VULKAN_ARTIFACT,
        "version": GPU_RUNTIME_VERSION,
        "vendors": ["amd", "intel", "nvidia"],
        "badge": "ข้ามค่าย",
    },
}


def normalize_compute_mode(value):
    value = str(value or "cpu").lower()
    if value not in COMPUTE_MODES:
        raise ValueError("ไม่รองรับโหมดประมวลผลที่เลือก")
    return value


def normalize_gpu_backend(value):
    value = str(value or "auto").lower()
    if value not in GPU_BACKENDS:
        raise ValueError("ไม่รองรับ GPU backend ที่เลือก")
    return value


def runtime_root(app_dir, backend):
    if backend not in GPU_BACKENDS_INFO:
        raise ValueError("ไม่รองรับ GPU backend ที่เลือก")
    return os.path.join(app_dir, "gpu-runtimes", backend, GPU_RUNTIME_VERSION)


def runtime_executable(root):
    if not root or not os.path.isdir(root):
        return None
    for current, _, files in os.walk(root):
        for filename in files:
            if filename.lower() == "whisper-cli.exe":
                return os.path.join(current, filename)
    return None


def runtime_manifest(root):
    if not root:
        return None
    manifest_path = os.path.join(root, "runtime-manifest.json")
    if not os.path.isfile(manifest_path):
        return None
    try:
        import json
        with open(manifest_path, "r", encoding="utf-8-sig") as source:
            value = json.load(source)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def installed_runtime(app_dir, backend):
    if backend not in GPU_BACKENDS_INFO:
        return None
    root = runtime_root(app_dir, backend)
    executable = runtime_executable(root)
    if not executable:
        return None
    return {
        "backend": backend,
        "root": root,
        "executable": executable,
        "manifest": runtime_manifest(root),
        "version": GPU_BACKENDS_INFO[backend]["version"],
    }


def sha256_file(path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_archive_members(names):
    for name in names:
        normalized = name.replace("\\", "/")
        if not normalized or normalized.endswith("/"):
            continue
        if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
            raise ValueError("GPU runtime archive มี path ที่ไม่ปลอดภัย")
        parts = [part for part in normalized.split("/") if part not in ("", ".")]
        if ".." in parts:
            raise ValueError("GPU runtime archive มี path ที่ไม่ปลอดภัย")


def validate_runtime_archive(path):
    try:
        with zipfile.ZipFile(path) as archive:
            validate_archive_members(archive.namelist())
            names = [name.replace("\\", "/").lower() for name in archive.namelist()]
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError("ไฟล์ GPU runtime ไม่ใช่ ZIP ที่ใช้ได้") from error
    if not any(name.rsplit("/", 1)[-1] == "whisper-cli.exe" for name in names):
        raise ValueError("GPU runtime ไม่มี whisper-cli.exe")
    return True


def detect_gpu_vendors():
    """Return vendor hints without treating hardware presence as runtime support."""
    forced = os.environ.get("FREESRT_GPU_VENDOR", "").strip().lower()
    if forced:
        return sorted({item for item in re.split(r"[,; ]+", forced) if item in {"nvidia", "amd", "intel"}})
    if os.name != "nt":
        return []
    try:
        import winreg
        root = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}",
        )
    except (ImportError, OSError):
        return []
    vendors = set()
    try:
        for index in range(64):
            try:
                child = winreg.OpenKey(root, f"{index:04d}")
            except OSError:
                continue
            try:
                values = []
                for name in ("ProviderName", "DriverDesc", "MatchingDeviceId"):
                    try:
                        values.append(str(winreg.QueryValueEx(child, name)[0]).lower())
                    except OSError:
                        pass
                text = " ".join(values)
                if "nvidia" in text or "ven_10de" in text:
                    vendors.add("nvidia")
                if "advanced micro devices" in text or "amd" in text or "ven_1002" in text:
                    vendors.add("amd")
                if "intel" in text or "ven_8086" in text:
                    vendors.add("intel")
            finally:
                winreg.CloseKey(child)
    finally:
        winreg.CloseKey(root)
    return sorted(vendors)


def recommended_backend(vendors):
    vendors = set(vendors or [])
    if "nvidia" in vendors:
        return "cuda"
    if vendors.intersection({"amd", "intel"}):
        return "vulkan"
    return None


def is_gpu_error(message):
    text = str(message or "").lower()
    markers = (
        "cuda", "vulkan", "gpu", "vram", "out of memory", "out-of-memory",
        "ggml_cuda", "ggml_vulkan", "no device", "device initialization",
        "failed to load backend", "backend init",
    )
    return any(marker in text for marker in markers)

