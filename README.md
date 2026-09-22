<img width="917" height="654" alt="image" src="https://github.com/user-attachments/assets/82d3e11e-9cf8-447e-927b-cfce1c1757ea" />

# pz-nvml-dcgm-exporter

Windows NVML exporter that exposes GPU telemetry in **NVIDIA dcgm-exporter** Prometheus format. A compact dashboard shows the same data locally; Prometheus scrapes `/metrics` as usual.

Run it on each office PC so you can watch GPU usage across many machines on the company LAN from one Prometheus or Grafana view.

This project is **not affiliated with NVIDIA**. Metric names and labels follow [dcgm-exporter](https://github.com/NVIDIA/dcgm-exporter) so existing Grafana dashboards can keep working on Windows hosts where DCGM is unavailable.

## Features

- Built for company LAN monitoring: one exporter per PC, central view of GPU status
- Prometheus `/metrics` on port **9400** (same default as dcgm-exporter)
- Dark dashboard: GPU util, temperature, power, framebuffer, SM clock, with usage bars
- Per-process VRAM and GPU usage (NVML + Windows PDH)
- **Cancel** on the Processes tab to terminate a process (confirmation required)
- Process rows colored by usage: green ≥ 40%, yellow ≥ 70%, red ≥ 85%
- System tray, start at login, IP/URL dropdown
- English / 中文 UI (English by default); browser preview page is English
- Scrapes stay `text/plain; version=0.0.4`

## Requirements

- Windows with an NVIDIA GPU and current Game Ready / Studio / datacenter driver (`nvml.dll`)
- Python 3.10+ to run from source (3.12 recommended)
- Official CPython is recommended for packaging (conda Tk/Tcl can break the windowed exe)

## Run from source

```powershell
pip install -r requirements.txt
python main.py
```

| Flag | Meaning |
| --- | --- |
| `--port 9400` | Exporter port |
| `--bind 0.0.0.0` | Listen address |
| `--interval 1` | NVML sample interval (seconds) |
| `--no-gui` | Exporter only |
| `--tray` | Start hidden in the system tray |

Prometheus URL: `http://127.0.0.1:9400/metrics`  
Browser preview: `http://127.0.0.1:9400/`

## Prometheus scrape

```yaml
scrape_configs:
  - job_name: pz-nvml-dcgm-exporter
    scrape_interval: 5s
    static_configs:
      - targets: ["<gpu-host>:9400"]
```

Label set matches dcgm-exporter (`gpu`, `UUID`, `device`, `modelName`, `Hostname`, `DCGM_FI_DRIVER_VERSION`). Extra series:

- `NVML_PROCESS_FB_USED` — process framebuffer MiB
- `NVML_PROCESS_GPU_UTIL` — process GPU util %

DCP profiling counters (tensor activity, FP16/FP32/FP64) are omitted when NVML cannot provide them.

## Build the Windows exe

```powershell
.\build.ps1
```

Output: `dist/pz-nvml-dcgm-exporter.exe`

Close any running copy of the exe before rebuilding (Windows locks the file). Tag `v*` or run the **Build Windows exe** GitHub Action to produce an artifact.

## Project layout

```
main.py                         # launcher
build.ps1                       # PyInstaller helper
pz-nvml-dcgm-exporter.spec
src/pz_nvml_dcgm_exporter/      # application package
```

## License

MIT. See [LICENSE](LICENSE).

---

## 中文

以 NVML 采集 GPU 指標，輸出與 NVIDIA dcgm-exporter 相容的 Prometheus `/metrics`，並附暗色儀表板。方便在區域網路內管理公司多台電腦的使用狀態：每台機器各跑一份，即可集中查看 GPU 占用。

- 預設介面英文，右下角可切換中文；瀏覽器檢查頁固定英文
- Processes 左側 **Cancel / 終止** 可關閉占用 GPU 的程式（會先確認）
- 列顏色依 GPU／VRAM 用量：綠 ≥ 40%、黃 ≥ 70%、紅 ≥ 85%
- Prometheus 刮取仍是標準 `text/plain`

```powershell
pip install -r requirements.txt
python main.py
.\build.ps1
```

