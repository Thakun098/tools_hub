# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Tools Hub — the handcrafted utility launcher.

Produces a one-folder portable build (COLLECT) containing:
  - ToolsHub.exe          (the console-less launcher)
  - hub/templates/        (Jinja2 HTML templates)
  - hub/static/hub/       (CSS + JS assets)
  - plugins/              (empty directory for user-installed plugins)
  - data/                 (empty directory for runtime data)
"""
import os
from pathlib import Path
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT

ROOT = Path(SPECPATH).resolve()
HUB_DIR = ROOT / "hub"

datas = [
    (str(HUB_DIR / "templates"), os.path.join("hub", "templates")),
    (str(HUB_DIR / "static"), os.path.join("hub", "static")),
]

a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
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
    name="ToolsHub",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,   # console=True for this test build so we can see output
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ToolsHub",
)
