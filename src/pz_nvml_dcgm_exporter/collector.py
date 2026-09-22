"""Collect GPU telemetry via NVML and map it onto dcgm-exporter field names."""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from pz_nvml_dcgm_exporter.metrics import METRIC_DEFS
from pz_nvml_dcgm_exporter.win_gpu_pdh import WinGpuPdh, resolve_process_name

try:
    import pynvml
except ImportError:  # pragma: no cover
    pynvml = None  # type: ignore[assignment]


def _to_str(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _call(fn: Callable[..., Any], *args: Any) -> Any:
    try:
        return fn(*args)
    except Exception:
        return None


@dataclass
class GpuIdentity:
    index: int
    uuid: str
    name: str
    device: str


@dataclass
class ProcessUsage:
    pid: int
    name: str
    gpu_index: int
    vram_mib: Optional[float] = None
    gpu_util: Optional[float] = None
    kind: str = ""


@dataclass
class Snapshot:
    ok: bool
    error: str = ""
    hostname: str = ""
    driver_version: str = ""
    collected_at: float = 0.0
    gpus: list[GpuIdentity] = field(default_factory=list)
    # gpu index -> metric name -> value
    values: dict[int, dict[str, float]] = field(default_factory=dict)
    processes: list[ProcessUsage] = field(default_factory=list)

    def prometheus_rows(self) -> list[tuple[str, dict[str, str], float]]:
        rows: list[tuple[str, dict[str, str], float]] = []
        gpu_by_index = {gpu.index: gpu for gpu in self.gpus}
        for gpu in self.gpus:
            metrics = self.values.get(gpu.index, {})
            labels = {
                "gpu": str(gpu.index),
                "UUID": gpu.uuid,
                "device": gpu.device,
                "modelName": gpu.name,
                "Hostname": self.hostname,
                "DCGM_FI_DRIVER_VERSION": self.driver_version,
                "container": "",
                "namespace": "",
                "pod": "",
            }
            for name in METRIC_DEFS:
                if name in metrics:
                    rows.append((name, labels, metrics[name]))
        for proc in self.processes:
            gpu = gpu_by_index.get(proc.gpu_index)
            labels = {
                "gpu": str(proc.gpu_index),
                "pid": str(proc.pid),
                "process": proc.name,
                "UUID": gpu.uuid if gpu else "",
                "device": gpu.device if gpu else f"nvidia{proc.gpu_index}",
                "modelName": gpu.name if gpu else "",
                "Hostname": self.hostname,
                "DCGM_FI_DRIVER_VERSION": self.driver_version,
            }
            if proc.vram_mib is not None:
                rows.append(("NVML_PROCESS_FB_USED", labels, proc.vram_mib))
            if proc.gpu_util is not None:
                rows.append(("NVML_PROCESS_GPU_UTIL", labels, proc.gpu_util))
        return rows


class NvmlCollector:
    def __init__(self, interval: float = 1.0) -> None:
        self.interval = max(0.2, float(interval))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._initialized = False
        self._pdh = WinGpuPdh()
        self._name_cache: dict[int, str] = {}
        self._util_ts: dict[int, int] = {}
        self._snapshot = Snapshot(
            ok=False,
            error="NVML not initialized yet",
            hostname=socket.gethostname(),
        )

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._pdh.start()
        self._thread = threading.Thread(target=self._loop, name="nvml-collector", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._pdh.close()
        self._shutdown()

    def restart(self) -> None:
        self.stop()
        self.start()

    def snapshot(self) -> Snapshot:
        with self._lock:
            return self._snapshot

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                snap = self._collect()
            except Exception as exc:
                snap = Snapshot(
                    ok=False,
                    error=f"Collector exception: {exc}",
                    hostname=socket.gethostname(),
                    collected_at=time.time(),
                )
            with self._lock:
                self._snapshot = snap
            self._stop.wait(self.interval)

    def _ensure_init(self) -> Optional[str]:
        if pynvml is None:
            return "nvidia-ml-py is not installed. Install NVIDIA drivers and the package first."
        if self._initialized:
            return None
        try:
            pynvml.nvmlInit()
            self._initialized = True
            return None
        except Exception as exc:
            return f"NVML init failed: {exc}"

    def _shutdown(self) -> None:
        if self._initialized and pynvml is not None:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass
        self._initialized = False

    def _collect(self) -> Snapshot:
        hostname = socket.gethostname()
        err = self._ensure_init()
        if err:
            return Snapshot(ok=False, error=err, hostname=hostname, collected_at=time.time())

        driver = _to_str(_call(pynvml.nvmlSystemGetDriverVersion) or "")
        count = _call(pynvml.nvmlDeviceGetCount)
        if count is None:
            self._initialized = False
            return Snapshot(
                ok=False,
                error="Could not read GPU count; NVML will be reinitialized next cycle",
                hostname=hostname,
                driver_version=driver,
                collected_at=time.time(),
            )

        gpus: list[GpuIdentity] = []
        values: dict[int, dict[str, float]] = {}
        for index in range(int(count)):
            handle = _call(pynvml.nvmlDeviceGetHandleByIndex, index)
            if handle is None:
                continue
            uuid = _to_str(_call(pynvml.nvmlDeviceGetUUID, handle) or f"GPU-{index}")
            name = _to_str(_call(pynvml.nvmlDeviceGetName, handle) or f"GPU {index}")
            identity = GpuIdentity(
                index=index,
                uuid=uuid,
                name=name,
                device=f"nvidia{index}",
            )
            gpus.append(identity)
            values[index] = self._collect_device(handle)

        if not gpus:
            return Snapshot(
                ok=False,
                error="NVML initialized, but no GPU was detected",
                hostname=hostname,
                driver_version=driver,
                collected_at=time.time(),
            )

        return Snapshot(
            ok=True,
            hostname=hostname,
            driver_version=driver,
            collected_at=time.time(),
            gpus=gpus,
            values=values,
            processes=self._collect_processes(gpus),
        )

    def _collect_device(self, handle: Any) -> dict[str, float]:
        out: dict[str, float] = {}

        def put(name: str, value: Any) -> None:
            if value is None:
                return
            try:
                out[name] = float(value)
            except (TypeError, ValueError):
                return

        sm = _call(pynvml.nvmlDeviceGetClockInfo, handle, pynvml.NVML_CLOCK_SM)
        put("DCGM_FI_DEV_SM_CLOCK", sm)
        mem_clk = _call(pynvml.nvmlDeviceGetClockInfo, handle, pynvml.NVML_CLOCK_MEM)
        put("DCGM_FI_DEV_MEM_CLOCK", mem_clk)
        put(
            "_SM_CLOCK_MAX",
            _call(getattr(pynvml, "nvmlDeviceGetMaxClockInfo", lambda *_: None), handle, pynvml.NVML_CLOCK_SM),
        )

        gpu_temp = _call(pynvml.nvmlDeviceGetTemperature, handle, pynvml.NVML_TEMPERATURE_GPU)
        put("DCGM_FI_DEV_GPU_TEMP", gpu_temp)
        slowdown = getattr(pynvml, "NVML_TEMPERATURE_THRESHOLD_SLOWDOWN", None)
        if slowdown is not None:
            put(
                "_GPU_TEMP_SLOWDOWN",
                _call(pynvml.nvmlDeviceGetTemperatureThreshold, handle, slowdown),
            )
        mem_temp_sensor = getattr(pynvml, "NVML_TEMPERATURE_MEMORY", None)
        if mem_temp_sensor is not None:
            put(
                "DCGM_FI_DEV_MEMORY_TEMP",
                _call(pynvml.nvmlDeviceGetTemperature, handle, mem_temp_sensor),
            )
        if "DCGM_FI_DEV_MEMORY_TEMP" not in out:
            mem_temp_field = getattr(pynvml, "NVML_FI_DEV_MEMORY_TEMP", None)
            if mem_temp_field is not None:
                put("DCGM_FI_DEV_MEMORY_TEMP", self._field_value(handle, mem_temp_field))

        power_mw = _call(pynvml.nvmlDeviceGetPowerUsage, handle)
        if power_mw is not None:
            put("DCGM_FI_DEV_POWER_USAGE", float(power_mw) / 1000.0)
        limit_mw = _call(getattr(pynvml, "nvmlDeviceGetEnforcedPowerLimit", lambda *_: None), handle)
        if limit_mw is None:
            limit_mw = _call(getattr(pynvml, "nvmlDeviceGetPowerManagementLimit", lambda *_: None), handle)
        if limit_mw is not None:
            put("_POWER_LIMIT_W", float(limit_mw) / 1000.0)

        energy = _call(pynvml.nvmlDeviceGetTotalEnergyConsumption, handle)
        put("DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION", energy)

        pcie_replay = _call(pynvml.nvmlDeviceGetPcieReplayCounter, handle)
        put("DCGM_FI_DEV_PCIE_REPLAY_COUNTER", pcie_replay)

        util = _call(pynvml.nvmlDeviceGetUtilizationRates, handle)
        if util is not None:
            put("DCGM_FI_DEV_GPU_UTIL", getattr(util, "gpu", None))
            put("DCGM_FI_DEV_MEM_COPY_UTIL", getattr(util, "memory", None))

        enc = _call(pynvml.nvmlDeviceGetEncoderUtilization, handle)
        if isinstance(enc, tuple) and enc:
            put("DCGM_FI_DEV_ENC_UTIL", enc[0])
        elif enc is not None and not isinstance(enc, tuple):
            put("DCGM_FI_DEV_ENC_UTIL", enc)

        dec = _call(pynvml.nvmlDeviceGetDecoderUtilization, handle)
        if isinstance(dec, tuple) and dec:
            put("DCGM_FI_DEV_DEC_UTIL", dec[0])
        elif dec is not None and not isinstance(dec, tuple):
            put("DCGM_FI_DEV_DEC_UTIL", dec)

        mem = self._memory_info(handle)
        if mem is not None:
            total = getattr(mem, "total", 0) or 0
            used = getattr(mem, "used", 0) or 0
            free = getattr(mem, "free", 0) or 0
            reserved = getattr(mem, "reserved", None)
            put("DCGM_FI_DEV_FB_USED", round(used / (1024 * 1024)))
            put("DCGM_FI_DEV_FB_FREE", round(free / (1024 * 1024)))
            if reserved is not None:
                put("DCGM_FI_DEV_FB_RESERVED", round(reserved / (1024 * 1024)))
            elif total:
                inferred = max(0, total - used - free)
                put("DCGM_FI_DEV_FB_RESERVED", round(inferred / (1024 * 1024)))

        remap = _call(pynvml.nvmlDeviceGetRemappedRows, handle)
        if isinstance(remap, tuple) and len(remap) >= 4:
            corr, unc, _pending, failure = remap[:4]
            put("DCGM_FI_DEV_CORRECTABLE_REMAPPED_ROWS", corr)
            put("DCGM_FI_DEV_UNCORRECTABLE_REMAPPED_ROWS", unc)
            put("DCGM_FI_DEV_ROW_REMAP_FAILURE", 1 if failure else 0)

        tx_counter = getattr(pynvml, "NVML_PCIE_UTIL_TX_BYTES", getattr(pynvml, "NVML_PCIE_UTIL_TX", None))
        rx_counter = getattr(pynvml, "NVML_PCIE_UTIL_RX_BYTES", getattr(pynvml, "NVML_PCIE_UTIL_RX", None))
        if tx_counter is not None:
            tx = _call(pynvml.nvmlDeviceGetPcieThroughput, handle, tx_counter)
            # NVML reports KB/s; dcgm-exporter PROF_*_BYTES is bytes/sec.
            if tx is not None:
                put("DCGM_FI_PROF_PCIE_TX_BYTES", float(tx) * 1024.0)
        if rx_counter is not None:
            rx = _call(pynvml.nvmlDeviceGetPcieThroughput, handle, rx_counter)
            if rx is not None:
                put("DCGM_FI_PROF_PCIE_RX_BYTES", float(rx) * 1024.0)

        nvlink = self._nvlink_bandwidth(handle)
        put("DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL", nvlink)
        return out

    def _field_value(self, handle: Any, field_id: int) -> Optional[float]:
        getter = getattr(pynvml, "nvmlDeviceGetFieldValues", None)
        if getter is None:
            return None
        values = _call(getter, handle, [field_id])
        if not values:
            return None
        item = values[0]
        nvml_return = getattr(item, "nvmlReturn", 0)
        if nvml_return not in (0, None):
            return None
        value_type = getattr(item, "valueType", None)
        value = getattr(item, "value", None)
        if value is None:
            return None
        mapping = {
            getattr(pynvml, "NVML_VALUE_TYPE_DOUBLE", 0): "dVal",
            getattr(pynvml, "NVML_VALUE_TYPE_UNSIGNED_INT", 1): "uiVal",
            getattr(pynvml, "NVML_VALUE_TYPE_UNSIGNED_LONG", 2): "ulVal",
            getattr(pynvml, "NVML_VALUE_TYPE_UNSIGNED_LONG_LONG", 3): "ullVal",
            getattr(pynvml, "NVML_VALUE_TYPE_SIGNED_LONG_LONG", 4): "sllVal",
            getattr(pynvml, "NVML_VALUE_TYPE_SIGNED_INT", 5): "siVal",
            getattr(pynvml, "NVML_VALUE_TYPE_UNSIGNED_SHORT", 6): "usVal",
        }
        attr = mapping.get(value_type, "uiVal")
        raw = getattr(value, attr, None)
        try:
            return float(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    def _memory_info(self, handle: Any) -> Any:
        version = getattr(pynvml, "nvmlMemory_v2", None)
        if version is not None:
            info = _call(pynvml.nvmlDeviceGetMemoryInfo, handle, version)
            if info is not None:
                return info
        return _call(pynvml.nvmlDeviceGetMemoryInfo, handle)

    def _nvlink_bandwidth(self, handle: Any) -> Optional[float]:
        get_counter = getattr(pynvml, "nvmlDeviceGetNvLinkUtilizationCounter", None)
        if get_counter is None:
            return None
        total = 0.0
        found = False
        for link in range(18):
            result = _call(get_counter, handle, link, 0)
            if result is None:
                if link == 0:
                    return None
                break
            if isinstance(result, tuple):
                total += float(result[0] or 0) + float(result[1] or 0)
            else:
                total += float(result)
            found = True
        return total if found else None

    def _collect_processes(self, gpus: list[GpuIdentity]) -> list[ProcessUsage]:
        pdh_mem, pdh_util = self._pdh.sample()
        gpu_count = max(len(gpus), 1)
        merged: dict[tuple[int, int], ProcessUsage] = {}

        def slot(pid: int, gpu_index: int) -> ProcessUsage:
            key = (pid, gpu_index)
            proc = merged.get(key)
            if proc is None:
                proc = ProcessUsage(pid=pid, name=self._process_name(pid), gpu_index=gpu_index)
                merged[key] = proc
            return proc

        for (pid, phys), mib in pdh_mem.items():
            gpu_index = phys if phys < gpu_count else 0
            proc = slot(pid, gpu_index)
            proc.vram_mib = round(mib, 1)
        for (pid, phys), util in pdh_util.items():
            gpu_index = phys if phys < gpu_count else 0
            proc = slot(pid, gpu_index)
            proc.gpu_util = round(min(100.0, max(0.0, util)), 1)

        for gpu in gpus:
            handle = _call(pynvml.nvmlDeviceGetHandleByIndex, gpu.index)
            if handle is None:
                continue
            kinds: dict[int, set[str]] = {}
            for flag, getter_name in (
                ("C", "nvmlDeviceGetComputeRunningProcesses"),
                ("G", "nvmlDeviceGetGraphicsRunningProcesses"),
            ):
                getter = getattr(pynvml, getter_name, None)
                for item in _call(getter, handle) or []:
                    pid = int(getattr(item, "pid", 0) or 0)
                    if pid <= 0:
                        continue
                    kinds.setdefault(pid, set()).add(flag)
                    used = getattr(item, "usedGpuMemory", None)
                    proc = slot(pid, gpu.index)
                    if used is not None and proc.vram_mib is None:
                        proc.vram_mib = round(float(used) / (1024 * 1024), 1)

            last_ts = self._util_ts.get(gpu.index, 0)
            samples = _call(pynvml.nvmlDeviceGetProcessUtilization, handle, last_ts)
            newest = last_ts
            for sample in samples or []:
                pid = int(getattr(sample, "pid", 0) or 0)
                if pid <= 0:
                    continue
                proc = slot(pid, gpu.index)
                sm = getattr(sample, "smUtil", None)
                if sm is not None:
                    proc.gpu_util = float(sm)
                ts = int(getattr(sample, "timeStamp", 0) or 0)
                newest = max(newest, ts)
            if newest:
                self._util_ts[gpu.index] = newest

            for pid, flags in kinds.items():
                proc = slot(pid, gpu.index)
                proc.kind = "+".join(sorted(flags))

        out = list(merged.values())
        out.sort(key=lambda p: (-(p.vram_mib or 0.0), -(p.gpu_util or 0.0), p.name.lower()))
        return out

    def _process_name(self, pid: int) -> str:
        cached = self._name_cache.get(pid)
        if cached:
            return cached
        name = resolve_process_name(pid)
        if name.startswith("pid:") and pynvml is not None:
            nvml_name = _call(getattr(pynvml, "nvmlSystemGetProcessName", lambda *_: None), pid)
            if nvml_name:
                raw = _to_str(nvml_name).replace("/", "\\")
                name = raw.rsplit("\\", 1)[-1] or raw
        self._name_cache[pid] = name
        return name
