"""Application entry: NVML collector + Prometheus /metrics + optional GUI."""

from __future__ import annotations

import argparse
import socket
import sys
import time

from pz_nvml_dcgm_exporter import APP_NAME, __version__
from pz_nvml_dcgm_exporter.collector import NvmlCollector
from pz_nvml_dcgm_exporter.metrics import render_prometheus
from pz_nvml_dcgm_exporter.server import MetricsServer


def _enable_windows_dpi() -> None:
    if sys.platform != "win32":
        return
    try:
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            from ctypes import windll

            windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description=(
            "Collect GPU metrics with NVML and expose a Prometheus /metrics "
            "endpoint compatible with NVIDIA dcgm-exporter."
        ),
    )
    parser.add_argument("--port", type=int, default=9400, help="Prometheus exporter port (default 9400, same as dcgm-exporter)")
    parser.add_argument("--bind", default="0.0.0.0", help="Listen address (default 0.0.0.0)")
    parser.add_argument("--interval", type=float, default=1.0, help="NVML collection interval in seconds (default 1)")
    parser.add_argument("--no-gui", action="store_true", help="Run as exporter only, without the dashboard window")
    parser.add_argument("--tray", action="store_true", help="Start minimized to the system tray")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    collector = NvmlCollector(interval=args.interval)
    server = MetricsServer(collector, host=args.bind, port=args.port)

    collector.start()
    try:
        server.start()
    except OSError as exc:
        collector.stop()
        msg = f"Could not listen on {args.bind}:{args.port}: {exc}"
        if args.no_gui:
            print(msg, file=sys.stderr)
            return 1
        _enable_windows_dpi()
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, msg)
        return 1

    if args.no_gui:
        print(f"{APP_NAME} {__version__}  listening on {server.url}")
        print("GET /metrics  GET /health")
        try:
            while True:
                time.sleep(1)
                snap = collector.snapshot()
                if snap.ok:
                    n = len(snap.gpus)
                    print(f"\r{n} GPU  ready    scrapes={server.scrape_count}   ", end="", flush=True)
                else:
                    print(f"\r{snap.error}   ", end="", flush=True)
        except KeyboardInterrupt:
            print("\nstopping")
        finally:
            server.stop()
            collector.stop()
        return 0

    _enable_windows_dpi()
    from pz_nvml_dcgm_exporter.gui import ExporterApp

    app = ExporterApp(collector, server, start_hidden=args.tray)
    app.mainloop()
    return 0


def dump_metrics_once() -> str:
    collector = NvmlCollector(interval=1.0)
    collector.start()
    time.sleep(0.4)
    snap = collector.snapshot()
    collector.stop()
    return render_prometheus(snap.hostname or socket.gethostname(), snap.driver_version, snap.prometheus_rows())
