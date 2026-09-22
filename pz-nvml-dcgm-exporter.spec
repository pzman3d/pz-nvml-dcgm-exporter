# NVML to dcgm-exporter compatible Prometheus exporter for Windows
# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules

hidden = collect_submodules("pynvml") + collect_submodules("pystray") + collect_submodules("PIL") + [
    "pz_nvml_dcgm_exporter",
    "pz_nvml_dcgm_exporter.app",
    "pz_nvml_dcgm_exporter.autostart",
    "pz_nvml_dcgm_exporter.collector",
    "pz_nvml_dcgm_exporter.gui",
    "pz_nvml_dcgm_exporter.i18n",
    "pz_nvml_dcgm_exporter.icon",
    "pz_nvml_dcgm_exporter.metrics",
    "pz_nvml_dcgm_exporter.netinfo",
    "pz_nvml_dcgm_exporter.server",
    "pz_nvml_dcgm_exporter.win_gpu_pdh",
]

a = Analysis(
    ["main.py"],
    pathex=["src"],
    binaries=[],
    datas=[("src/pz_nvml_dcgm_exporter/assets/app.ico", "pz_nvml_dcgm_exporter/assets")],
    hiddenimports=hidden,
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
    a.datas,
    [],
    name="pz-nvml-dcgm-exporter",
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
    icon="src/pz_nvml_dcgm_exporter/assets/app.ico",
)
