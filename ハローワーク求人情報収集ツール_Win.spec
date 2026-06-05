# -*- mode: python ; coding: utf-8 -*-
# Windows版 PyInstaller spec
import certifi
import os

CA_BUNDLE = certifi.where()

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        (CA_BUNDLE, 'certifi'),
    ],
    hiddenimports=[
        'lxml',
        'lxml._elementpath',
        'lxml.etree',
        'bs4',
        'requests',
        'requests.adapters',
        'requests.auth',
        'requests.cookies',
        'requests.exceptions',
        'requests.packages.urllib3',
        'urllib3',
        'urllib3.util.retry',
        'certifi',
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.utils',
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
    ],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ハローワーク求人情報収集ツール',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
    version=None,
)
