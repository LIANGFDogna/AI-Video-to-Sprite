# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app/main.py'],
    pathex=['E:/AI Video to Sprite'],
    binaries=[],
    datas=[('app/i18n/zh_CN.json', 'app/i18n'), ('app/i18n/en_US.json', 'app/i18n')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AI Video to Sprite',
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AI Video to Sprite',
)
