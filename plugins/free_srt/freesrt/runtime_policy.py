"""Single binary policy for CPU packaging and GPU runtime installation."""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import zipfile


from toolshub_free_srt.contracts import RuntimePolicyError

AVX512_CPU_VARIANTS = ("cascadelake", "skylakex", "icelake", "cannonlake")
CPU_BASE_DLLS = frozenset({"whisper.dll", "ggml.dll", "ggml-base.dll"})
PORTABLE_CPU_RUNTIME_DLLS = frozenset({
    *CPU_BASE_DLLS,
    "ggml-cpu.dll",
    "ggml-cpu-x64.dll",
    "ggml-cpu-sse42.dll",
    "ggml-cpu-sandybridge.dll",
    "ggml-cpu-haswell.dll",
    "ggml-cpu-alderlake.dll",
})
SKIPPED_RUNTIME_DLLS = frozenset({"parakeet.dll", "sdl2.dll"})
RUNTIME_EXECUTABLE = "whisper-cli.exe"
ACCELERATOR_MARKERS = {
    "cuda": ("ggml-cuda.dll",),
    "vulkan": ("ggml-vulkan.dll",),
}
BACKEND_RUNTIME_DLLS = {
    "cuda": frozenset({"ggml-cuda.dll"}),
    "vulkan": frozenset({"ggml-vulkan.dll"}),
}
CUDA_DEPENDENCY_PATTERNS = tuple(re.compile(pattern) for pattern in (
    r"(?:cublas|cublaslt)64_\d+\.dll",
    r"cudart(?:32|64)_\d+\.dll",
    r"cuinj64_\d+\.dll",
    r"nvrtc64_[0-9_]+\.dll",
    r"nvrtc-builtins64_\d+\.dll",
))




def is_forbidden_avx512(name):
    lowered = str(name).casefold()
    return lowered.endswith(".dll") and any(variant in lowered for variant in AVX512_CPU_VARIANTS)


def is_allowed_cpu_release_binary(path_or_name):
    name = Path(path_or_name).name.casefold()
    if name == RUNTIME_EXECUTABLE:
        return True
    if not name.endswith(".dll") or is_forbidden_avx512(name):
        return False
    return name in CPU_BASE_DLLS or name.startswith("ggml-cpu-")


def normalize_archive_member(name):
    normalized = str(name).replace("\\", "/")
    if not normalized or normalized.endswith("/"):
        return None
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        raise RuntimePolicyError("GPU runtime archive contains an absolute path.")
    path = PurePosixPath(normalized)
    if any(part in ("", ".", "..") for part in path.parts):
        raise RuntimePolicyError("GPU runtime archive contains an unsafe path.")
    return path


def is_allowed_runtime_dll(name, backend):
    lowered = str(name).casefold()
    if backend not in ACCELERATOR_MARKERS:
        raise RuntimePolicyError(f"Unsupported runtime backend: {backend}")
    if (
        not lowered.endswith(".dll")
        or lowered in SKIPPED_RUNTIME_DLLS
        or is_forbidden_avx512(lowered)
    ):
        return False
    if lowered in PORTABLE_CPU_RUNTIME_DLLS or lowered in BACKEND_RUNTIME_DLLS[backend]:
        return True
    return backend == "cuda" and any(
        pattern.fullmatch(lowered) for pattern in CUDA_DEPENDENCY_PATTERNS
    )


def select_runtime_members(names, backend):
    selected = []
    leaves = set()
    for name in names:
        path = normalize_archive_member(name)
        if path is None:
            continue
        leaf = path.name
        lowered = leaf.casefold()
        if (
            lowered.endswith(".dll")
            and lowered not in SKIPPED_RUNTIME_DLLS
            and not is_forbidden_avx512(lowered)
            and not is_allowed_runtime_dll(lowered, backend)
        ):
            raise RuntimePolicyError(f"DLL outside GPU runtime policy: {leaf}")
        allowed = lowered == RUNTIME_EXECUTABLE or is_allowed_runtime_dll(lowered, backend)
        if not allowed:
            continue
        if lowered in leaves:
            raise RuntimePolicyError(f"GPU runtime archive contains duplicate file: {leaf}")
        leaves.add(lowered)
        selected.append((str(path), leaf))
    if RUNTIME_EXECUTABLE not in leaves:
        raise RuntimePolicyError("GPU runtime archive does not contain whisper-cli.exe.")
    if not any(any(name.startswith(marker) for marker in ACCELERATOR_MARKERS[backend]) for name in leaves):
        raise RuntimePolicyError(f"GPU runtime archive does not contain the {backend} accelerator DLL.")
    return selected


def validate_staged_runtime(root, backend):
    root = Path(root)
    if not root.is_dir():
        raise RuntimePolicyError("GPU runtime staging directory is missing.")
    files = [path for path in root.rglob("*") if path.is_file()]
    names = {path.name.casefold() for path in files}
    if RUNTIME_EXECUTABLE not in names:
        raise RuntimePolicyError("GPU runtime staging does not contain whisper-cli.exe.")
    for path in files:
        name = path.name.casefold()
        if name.endswith(".exe") and name != RUNTIME_EXECUTABLE:
            raise RuntimePolicyError(f"Unexpected executable in GPU runtime staging: {path.name}")
        if is_forbidden_avx512(name):
            raise RuntimePolicyError(f"Forbidden AVX-512 DLL in GPU runtime staging: {path.name}")
        if name.endswith(".dll") and not is_allowed_runtime_dll(name, backend):
            raise RuntimePolicyError(f"DLL outside GPU runtime policy: {path.name}")
        if not name.endswith((".dll", ".exe")) and name != "runtime-manifest.json":
            raise RuntimePolicyError(f"Unexpected file in GPU runtime staging: {path.name}")
    if not any(any(name.startswith(marker) for marker in ACCELERATOR_MARKERS[backend]) for name in names):
        raise RuntimePolicyError(f"GPU runtime staging does not contain the {backend} accelerator DLL.")
    return files


def extract_runtime_archive(archive_path, backend, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise RuntimePolicyError("GPU runtime staging directory must be empty.")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            selected = select_runtime_members(archive.namelist(), backend)
            info_by_name = {info.filename.replace("\\", "/"): info for info in archive.infolist()}
            for member, leaf in selected:
                info = info_by_name.get(member)
                if info is None:
                    raise RuntimePolicyError(f"Archive member disappeared: {member}")
                target = destination / leaf
                with archive.open(info) as source, open(target, "wb") as output:
                    shutil.copyfileobj(source, output)
    except zipfile.BadZipFile as error:
        raise RuntimePolicyError("GPU runtime archive is not a valid ZIP file.") from error
    validate_staged_runtime(destination, backend)
    return [destination / leaf for _, leaf in selected]


def validate_cpu_release_tree(release_root):
    release_root = Path(release_root)
    if not release_root.is_dir():
        raise RuntimePolicyError(f"CPU release directory is missing: {release_root}")
    files = [path for path in release_root.iterdir() if path.is_file()]
    names = {path.name.casefold() for path in files}
    if RUNTIME_EXECUTABLE not in names:
        raise RuntimePolicyError("CPU release directory does not contain whisper-cli.exe.")
    unexpected = [path.name for path in files if not is_allowed_cpu_release_binary(path)]
    if unexpected:
        raise RuntimePolicyError("CPU release directory contains files outside policy: " + ", ".join(unexpected))
    return files


def validate_portable_tree(portable_root):
    release_root = Path(portable_root) / "_internal" / "bin" / "Release"
    return validate_cpu_release_tree(release_root)


def _main(argv=None):
    parser = argparse.ArgumentParser(description="FreeSRT runtime binary policy")
    subparsers = parser.add_subparsers(dest="command", required=True)
    extract = subparsers.add_parser("extract-runtime")
    extract.add_argument("--archive", required=True)
    extract.add_argument("--backend", choices=sorted(ACCELERATOR_MARKERS), required=True)
    extract.add_argument("--destination", required=True)
    validate = subparsers.add_parser("validate-portable")
    validate.add_argument("--root", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "extract-runtime":
            extract_runtime_archive(args.archive, args.backend, args.destination)
        else:
            validate_portable_tree(args.root)
    except (OSError, RuntimePolicyError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
