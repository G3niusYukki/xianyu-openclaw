# -*- mode: python ; coding: utf-8 -*-

"""
PyInstaller spec for 闲鱼 OpenClaw Windows 一键部署工具.

Build command:
    pyinstaller pyinstaller.spec

Output: dist/xianyu-openclaw-launcher/ (onedir mode)
"""

import importlib
from pathlib import Path

block_cipher = None

# SPECPATH is provided by PyInstaller at runtime
ROOT_DIR = Path(SPECPATH)  # noqa: F821
SRC_DIR = ROOT_DIR / 'src'

# Locate customtkinter package data
ctk_spec = importlib.util.find_spec('customtkinter')
if ctk_spec and ctk_spec.origin:
    CTK_DIR = str(Path(ctk_spec.origin).parent)
else:
    # Fallback: try common venv path
    CTK_DIR = str(ROOT_DIR / '.venv' / 'Lib' / 'site-packages' / 'customtkinter')

datas = [
    (str(SRC_DIR), 'src'),
    (str(ROOT_DIR / 'config'), 'config'),
    (str(ROOT_DIR / 'docker-compose.yml'), '.'),
    (str(ROOT_DIR / '.env.example'), '.'),
    (CTK_DIR, 'customtkinter'),
]

# Optionally include skills/ if present
if (ROOT_DIR / 'skills').exists():
    datas.append((str(ROOT_DIR / 'skills'), 'skills'))

a = Analysis(
    ['src/windows_launcher.py'],
    pathex=[str(ROOT_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'customtkinter',
        'darkdetect',
        'yaml',
        'dotenv',
        'pydantic',
        'loguru',
        'src.setup_wizard',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'playwright',
        'streamlit',
        'fastapi',
        'uvicorn',
        'aiosqlite',
        'aiofiles',
        'openai',
        'httpx',
        'websockets',
        'cryptography',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='xianyu-openclaw-launcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT_DIR / 'build' / 'icon.ico') if (ROOT_DIR / 'build' / 'icon.ico').exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='xianyu-openclaw-launcher',
)
