"""Windows PDH counters for per-process GPU dedicated memory and engine util."""

from __future__ import annotations

import ctypes
import re
import sys
import time
from ctypes import byref, c_void_p, wintypes

PDH_FMT_DOUBLE = 0x00000200
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_PID_MEM = re.compile(
    r"pid_(\d+)_luid_0x[0-9A-Fa-f]+_0x[0-9A-Fa-f]+_phys_(\d+)",
    re.IGNORECASE,
)
_PID_ENG = re.compile(
    r"pid_(\d+)_luid_0x[0-9A-Fa-f]+_0x[0-9A-Fa-f]+_phys_(\d+)_eng_\d+_engtype_(\w+)",
    re.IGNORECASE,
)


class PDH_FMT_COUNTERVALUE(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [
            ("longValue", ctypes.c_long),
            ("doubleValue", ctypes.c_double),
            ("largeValue", ctypes.c_longlong),
        ]

    _anonymous_ = ("u",)
    _fields_ = [("CStatus", wintypes.DWORD), ("u", _U)]


class PDH_FMT_COUNTERVALUE_ITEM_W(ctypes.Structure):
    _fields_ = [("szName", ctypes.c_wchar_p), ("FmtValue", PDH_FMT_COUNTERVALUE)]


def resolve_process_name(pid: int) -> str:
    if sys.platform != "win32" or pid <= 0:
        return f"pid:{pid}"
    k32 = ctypes.windll.kernel32
    handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if handle:
        try:
            size = wintypes.DWORD(32768)
            buf = ctypes.create_unicode_buffer(size.value)
            if k32.QueryFullProcessImageNameW(handle, 0, buf, byref(size)):
                path = buf.value.replace("/", "\\")
                return path.rsplit("\\", 1)[-1] or path
        finally:
            k32.CloseHandle(handle)
    return f"pid:{pid}"


class WinGpuPdh:
    def __init__(self) -> None:
        self._pdh = None
        self._query = c_void_p()
        self._mem = c_void_p()
        self._eng = c_void_p()
        self._ok = False
        self._primed = False

    def start(self) -> None:
        if sys.platform != "win32":
            return
        try:
            self._pdh = ctypes.windll.pdh
            if self._pdh.PdhOpenQueryW(None, None, byref(self._query)) != 0:
                return
            mem_path = r"\GPU Process Memory(*)\Dedicated Usage"
            eng_path = r"\GPU Engine(*)\Utilization Percentage"
            if self._pdh.PdhAddEnglishCounterW(self._query, mem_path, None, byref(self._mem)) != 0:
                self.close()
                return
            self._pdh.PdhAddEnglishCounterW(self._query, eng_path, None, byref(self._eng))
            self._pdh.PdhCollectQueryData(self._query)
            self._ok = True
        except Exception:
            self.close()

    def sample(self) -> tuple[dict[tuple[int, int], float], dict[tuple[int, int], float]]:
        """Return ({(pid, phys): MiB}, {(pid, phys): util%})."""
        mem: dict[tuple[int, int], float] = {}
        util: dict[tuple[int, int], float] = {}
        if not self._ok or self._pdh is None:
            return mem, util
        self._pdh.PdhCollectQueryData(self._query)
        if not self._primed:
            time.sleep(0.05)
            self._pdh.PdhCollectQueryData(self._query)
            self._primed = True

        for name, value in self._read_array(self._mem):
            m = _PID_MEM.search(name)
            if not m:
                continue
            pid, phys = int(m.group(1)), int(m.group(2))
            mib = float(value) / (1024 * 1024)
            key = (pid, phys)
            mem[key] = mem.get(key, 0.0) + mib

        for name, value in self._read_array(self._eng):
            m = _PID_ENG.search(name)
            if not m:
                continue
            pid, phys = int(m.group(1)), int(m.group(2))
            key = (pid, phys)
            util[key] = max(util.get(key, 0.0), float(value))
        return mem, util

    def _read_array(self, counter: c_void_p) -> list[tuple[str, float]]:
        if not counter:
            return []
        buf_size = wintypes.DWORD(0)
        item_count = wintypes.DWORD(0)
        self._pdh.PdhGetFormattedCounterArrayW(
            counter, PDH_FMT_DOUBLE, byref(buf_size), byref(item_count), None
        )
        if buf_size.value == 0 or item_count.value == 0:
            return []
        buf = ctypes.create_string_buffer(buf_size.value)
        status = self._pdh.PdhGetFormattedCounterArrayW(
            counter, PDH_FMT_DOUBLE, byref(buf_size), byref(item_count), buf
        )
        if status != 0:
            return []
        arr_t = PDH_FMT_COUNTERVALUE_ITEM_W * item_count.value
        items = arr_t.from_buffer(buf)
        out: list[tuple[str, float]] = []
        for item in items:
            if not item.szName:
                continue
            out.append((item.szName, float(item.FmtValue.doubleValue)))
        return out

    def close(self) -> None:
        if self._ok and self._pdh is not None and self._query:
            try:
                self._pdh.PdhCloseQuery(self._query)
            except Exception:
                pass
        self._ok = False
        self._primed = False
        self._query = c_void_p()
        self._mem = c_void_p()
        self._eng = c_void_p()
