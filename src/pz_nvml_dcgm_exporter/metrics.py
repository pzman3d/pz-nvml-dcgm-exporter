"""dcgm-exporter default-counters.csv metric definitions and Prometheus text format."""

from __future__ import annotations

from typing import Iterable

# Name, Prometheus type, help text — aligned with NVIDIA dcgm-exporter default-counters.csv
METRIC_DEFS: dict[str, tuple[str, str]] = {
    "DCGM_FI_DEV_SM_CLOCK": ("gauge", "SM clock frequency (in MHz)."),
    "DCGM_FI_DEV_MEM_CLOCK": ("gauge", "Memory clock frequency (in MHz)."),
    "DCGM_FI_DEV_MEMORY_TEMP": ("gauge", "Memory temperature (in C)."),
    "DCGM_FI_DEV_GPU_TEMP": ("gauge", "GPU temperature (in C)."),
    "DCGM_FI_DEV_POWER_USAGE": ("gauge", "Power draw (in W)."),
    "DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION": (
        "counter",
        "Total energy consumption since boot (in mJ).",
    ),
    "DCGM_FI_DEV_PCIE_REPLAY_COUNTER": ("counter", "Total number of PCIe retries."),
    "DCGM_FI_DEV_GPU_UTIL": ("gauge", "GPU utilization (in %)."),
    "DCGM_FI_DEV_MEM_COPY_UTIL": ("gauge", "Memory utilization (in %)."),
    "DCGM_FI_DEV_ENC_UTIL": ("gauge", "Encoder utilization (in %)."),
    "DCGM_FI_DEV_DEC_UTIL": ("gauge", "Decoder utilization (in %)."),
    "DCGM_FI_DEV_XID_ERRORS": ("gauge", "Value of the last XID error encountered."),
    "DCGM_FI_DEV_FB_FREE": ("gauge", "Framebuffer memory free (in MiB)."),
    "DCGM_FI_DEV_FB_USED": ("gauge", "Framebuffer memory used (in MiB)."),
    "DCGM_FI_DEV_FB_RESERVED": ("gauge", "Framebuffer memory reserved (in MiB)."),
    "DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL": (
        "gauge",
        "Total number of NVLink bandwidth counters for all lanes.",
    ),
    "DCGM_FI_DEV_VGPU_LICENSE_STATUS": ("gauge", "vGPU License status"),
    "DCGM_FI_DEV_UNCORRECTABLE_REMAPPED_ROWS": (
        "counter",
        "Number of remapped rows for uncorrectable errors",
    ),
    "DCGM_FI_DEV_CORRECTABLE_REMAPPED_ROWS": (
        "counter",
        "Number of remapped rows for correctable errors",
    ),
    "DCGM_FI_DEV_ROW_REMAP_FAILURE": ("gauge", "Whether remapping of rows has failed"),
    "DCGM_FI_PROF_GR_ENGINE_ACTIVE": ("gauge", "Ratio of time the graphics engine is active."),
    "DCGM_FI_PROF_PIPE_TENSOR_ACTIVE": (
        "gauge",
        "Ratio of cycles the tensor (HMMA) pipe is active.",
    ),
    "DCGM_FI_PROF_DRAM_ACTIVE": (
        "gauge",
        "Ratio of cycles the device memory interface is active sending or receiving data.",
    ),
    "DCGM_FI_PROF_PCIE_TX_BYTES": (
        "gauge",
        "The rate of data transmitted over the PCIe bus - including both protocol headers and data payloads - in bytes per second.",
    ),
    "DCGM_FI_PROF_PCIE_RX_BYTES": (
        "gauge",
        "The rate of data received over the PCIe bus - including both protocol headers and data payloads - in bytes per second.",
    ),
    "NVML_PROCESS_FB_USED": ("gauge", "Per-process framebuffer memory used (in MiB)."),
    "NVML_PROCESS_GPU_UTIL": ("gauge", "Per-process GPU utilization (in %)."),
}

METRIC_ORDER = list(METRIC_DEFS.keys())

# Display units for the GUI (not part of Prometheus output)
METRIC_UNITS: dict[str, str] = {
    "DCGM_FI_DEV_SM_CLOCK": "MHz",
    "DCGM_FI_DEV_MEM_CLOCK": "MHz",
    "DCGM_FI_DEV_MEMORY_TEMP": "°C",
    "DCGM_FI_DEV_GPU_TEMP": "°C",
    "DCGM_FI_DEV_POWER_USAGE": "W",
    "DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION": "mJ",
    "DCGM_FI_DEV_PCIE_REPLAY_COUNTER": "",
    "DCGM_FI_DEV_GPU_UTIL": "%",
    "DCGM_FI_DEV_MEM_COPY_UTIL": "%",
    "DCGM_FI_DEV_ENC_UTIL": "%",
    "DCGM_FI_DEV_DEC_UTIL": "%",
    "DCGM_FI_DEV_XID_ERRORS": "",
    "DCGM_FI_DEV_FB_FREE": "MiB",
    "DCGM_FI_DEV_FB_USED": "MiB",
    "DCGM_FI_DEV_FB_RESERVED": "MiB",
    "DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL": "",
    "DCGM_FI_DEV_VGPU_LICENSE_STATUS": "",
    "DCGM_FI_DEV_UNCORRECTABLE_REMAPPED_ROWS": "",
    "DCGM_FI_DEV_CORRECTABLE_REMAPPED_ROWS": "",
    "DCGM_FI_DEV_ROW_REMAP_FAILURE": "",
    "DCGM_FI_PROF_GR_ENGINE_ACTIVE": "ratio",
    "DCGM_FI_PROF_PIPE_TENSOR_ACTIVE": "ratio",
    "DCGM_FI_PROF_DRAM_ACTIVE": "ratio",
    "DCGM_FI_PROF_PCIE_TX_BYTES": "B/s",
    "DCGM_FI_PROF_PCIE_RX_BYTES": "B/s",
    "NVML_PROCESS_FB_USED": "MiB",
    "NVML_PROCESS_GPU_UTIL": "%",
}


def escape_label(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )


def format_prometheus_value(value: float) -> str:
    if value != value:  # NaN
        return "NaN"
    if value == float("inf"):
        return "+Inf"
    if value == float("-inf"):
        return "-Inf"
    if float(value).is_integer() and abs(value) < 1e15:
        return str(int(value))
    return repr(float(value))


def render_labels(labels: dict[str, str]) -> str:
    parts = [f'{key}="{escape_label(val)}"' for key, val in labels.items()]
    return "{" + ",".join(parts) + "}"


def render_prometheus(
    hostname: str,
    driver_version: str,
    rows: Iterable[tuple[str, dict[str, str], float]],
) -> str:
    """Render samples grouped like dcgm-exporter (HELP/TYPE once per family)."""
    grouped: dict[str, list[tuple[dict[str, str], float]]] = {}
    for name, labels, value in rows:
        grouped.setdefault(name, []).append((labels, value))

    lines: list[str] = [
        "# Generated by pz-nvml-dcgm-exporter (NVML backend, dcgm-exporter compatible)",
    ]
    for name in METRIC_ORDER:
        samples = grouped.get(name)
        if not samples:
            continue
        metric_type, help_text = METRIC_DEFS[name]
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {metric_type}")
        for labels, value in samples:
            lines.append(f"{name}{render_labels(labels)} {format_prometheus_value(value)}")

    # Keep extra families (if any) after the known order
    for name, samples in grouped.items():
        if name in METRIC_DEFS:
            continue
        lines.append(f"# HELP {name} {name}")
        lines.append(f"# TYPE {name} gauge")
        for labels, value in samples:
            lines.append(f"{name}{render_labels(labels)} {format_prometheus_value(value)}")

    lines.append("")
    return "\n".join(lines)
