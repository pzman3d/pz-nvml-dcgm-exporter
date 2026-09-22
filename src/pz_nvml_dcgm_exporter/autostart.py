"""Current-user auto-start via the Windows Run registry key."""

from __future__ import annotations

import sys
from pathlib import Path

from pz_nvml_dcgm_exporter import APP_NAME

APP_VALUE = APP_NAME
_LEGACY_VALUE = "nvml-dcgm-exporter"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    main = Path(__file__).resolve().parents[2] / "main.py"
    return f'"{sys.executable}" "{main}" --tray'


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            for name in (APP_VALUE, _LEGACY_VALUE):
                try:
                    value, _typ = winreg.QueryValueEx(key, name)
                    if value:
                        return True
                except FileNotFoundError:
                    continue
    except OSError:
        return False
    return False


def set_enabled(enabled: bool) -> None:
    if sys.platform != "win32":
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_VALUE, 0, winreg.REG_SZ, launch_command())
            try:
                winreg.DeleteValue(key, _LEGACY_VALUE)
            except FileNotFoundError:
                pass
            return
        for name in (APP_VALUE, _LEGACY_VALUE):
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
