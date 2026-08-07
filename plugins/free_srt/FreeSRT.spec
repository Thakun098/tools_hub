# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT

ROOT = Path(SPECPATH).resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from freesrt.runtime_policy import is_allowed_cpu_release_binary
ffmpeg_source = os.environ.get("FFMPEG_SOURCE")
ffprobe_source = os.environ.get("FFPROBE_SOURCE")
if not ffmpeg_source or not ffprobe_source:
    raise RuntimeError("FFMPEG_SOURCE and FFPROBE_SOURCE must point to Windows FFmpeg binaries")

release_dir = ROOT / "bin" / "Release"
release_binaries = [
    (str(path), "bin/Release")
    for path in release_dir.iterdir()
    if path.is_file() and is_allowed_cpu_release_binary(path)
]
media_binaries = [(ffmpeg_source, "bin"), (ffprobe_source, "bin")]
datas = [
    (str(ROOT / "templates"), "templates"),
    (str(ROOT / "static"), "static"),
]

a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=release_binaries + media_binaries,
    datas=datas,
    hiddenimports=["flask", "requests"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FreeSRT",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="FreeSRT",
)





