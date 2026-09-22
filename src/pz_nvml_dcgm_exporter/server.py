"""HTTP server exposing /metrics in Prometheus exposition format."""

from __future__ import annotations

import html
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import urlparse

from pz_nvml_dcgm_exporter import APP_NAME, __version__
from pz_nvml_dcgm_exporter.collector import NvmlCollector
from pz_nvml_dcgm_exporter.metrics import render_prometheus

PROM_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


class MetricsServer:
    def __init__(self, collector: NvmlCollector, host: str = "0.0.0.0", port: int = 9400) -> None:
        self.collector = collector
        self.host = host
        self.port = int(port)
        self.scrape_count = 0
        self.last_scrape: Optional[float] = None
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @property
    def url(self) -> str:
        shown = "127.0.0.1" if self.host in ("0.0.0.0", "::") else self.host
        return f"http://{shown}:{self.port}/metrics"

    @property
    def browse_url(self) -> str:
        shown = "127.0.0.1" if self.host in ("0.0.0.0", "::") else self.host
        return f"http://{shown}:{self.port}/"

    def start(self) -> None:
        handler = self._make_handler()
        httpd = ThreadingHTTPServer((self.host, self.port), handler)
        httpd.allow_reuse_address = True
        httpd.daemon_threads = True
        self._httpd = httpd
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="metrics-http", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def restart(self, port: Optional[int] = None) -> None:
        old_port = self.port
        self.stop()
        time.sleep(0.15)
        if port is not None:
            self.port = int(port)
        try:
            self.start()
        except OSError:
            if self.port != old_port:
                self.port = old_port
                try:
                    self.start()
                except OSError:
                    pass
            raise

    def note_scrape(self) -> None:
        with self._lock:
            self.scrape_count += 1
            self.last_scrape = time.time()

    def metrics_text(self) -> str:
        snap = self.collector.snapshot()
        return render_prometheus(
            snap.hostname,
            snap.driver_version,
            snap.prometheus_rows(),
        )

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                return

            def _wants_html(self) -> bool:
                accept = self.headers.get("Accept", "")
                if "application/openmetrics-text" in accept:
                    return False
                if "text/plain;version" in accept.replace(" ", "").lower():
                    return False
                return "text/html" in accept

            def do_GET(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                if path in ("/metrics", "/metrics/"):
                    body_text = server.metrics_text()
                    if self._wants_html():
                        html_page = _metrics_html(server, body_text)
                        self._send(200, html_page.encode("utf-8"), "text/html; charset=utf-8")
                    else:
                        server.note_scrape()
                        self._send(200, body_text.encode("utf-8"), PROM_CONTENT_TYPE)
                    return
                if path in ("/health", "/healthz"):
                    snap = server.collector.snapshot()
                    status = 200 if snap.ok else 503
                    payload = "ok\n" if snap.ok else f"error: {snap.error}\n"
                    self._send(status, payload.encode("utf-8"), "text/plain; charset=utf-8")
                    return
                if path in ("/", "/index.html"):
                    html_page = _metrics_html(server, server.metrics_text())
                    self._send(200, html_page.encode("utf-8"), "text/html; charset=utf-8")
                    return
                self._send(404, b"not found\n", "text/plain; charset=utf-8")

            def _send(self, code: int, body: bytes, content_type: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

        return Handler


def _metrics_html(server: MetricsServer, metrics_text: str) -> str:
    snap = server.collector.snapshot()
    status = "Ready" if snap.ok else (snap.error or "Not ready")
    escaped = html.escape(metrics_text if metrics_text.strip() else "# No metrics yet")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="color-scheme" content="dark"/>
  <title>{APP_NAME}</title>
  <style>
    html, body {{
      background: #101418;
      color: #eef2f6;
      font-family: Segoe UI, sans-serif;
      margin: 0;
    }}
    header {{
      padding: 20px 28px 12px;
      border-bottom: 1px solid #2c3644;
    }}
    h1 {{ margin: 0 0 8px; font-size: 20px; }}
    .muted {{ color: #8a97a8; }}
    a {{ color: #76b900; }}
    pre {{
      margin: 0;
      padding: 20px 28px 32px;
      background: #0c1014;
      color: #c5e1a5;
      font: 13px/1.45 Consolas, ui-monospace, monospace;
      white-space: pre-wrap;
      word-break: break-all;
    }}
  </style>
</head>
<body>
  <header>
    <h1>{APP_NAME} {__version__}</h1>
    <p>Status: {html.escape(status)} | <a href="/metrics">/metrics</a> (Prometheus scrape) | <a href="/health">/health</a></p>
    <p class="muted">Browsers show this preview. Prometheus scrapes /metrics as standard text/plain, same as dcgm-exporter.</p>
  </header>
  <pre>{escaped}</pre>
</body>
</html>
"""
