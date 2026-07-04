# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [('logo.ico', '.'), ('logo.png', '.')]
datas += collect_data_files('escpos')


a = Analysis(
    ['Software.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['matplotlib', 'pandas'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['scipy', 'torch', 'PyQt5', 'PySide6', 'PySide2', 'PyQt6', 'IPython', 'notebook', 'jedi', 'sphinx', 'pytest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='GestPro',
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
    icon='logo.ico',
)

