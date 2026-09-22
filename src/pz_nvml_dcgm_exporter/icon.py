"""GPU-card app icon for window, tray, and the packaged exe."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw


def _draw_gpu(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = float(size)
    stroke = max(1, size // 28)
    m = s * 0.10
    body = [m, m + s * 0.06, s - m, s - m - s * 0.04]
    d.rounded_rectangle(body, radius=max(2, int(s * 0.10)), fill=(18, 24, 32, 255), outline=(118, 185, 0, 255), width=stroke)
    # green shroud bar
    d.rounded_rectangle(
        [m + s * 0.06, m + s * 0.12, s - m - s * 0.06, m + s * 0.30],
        radius=max(2, int(s * 0.05)),
        fill=(118, 185, 0, 255),
    )
    # fans
    r = s * 0.10
    for cx in (s * 0.32, s * 0.68):
        cy = s * 0.52
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(196, 206, 216, 255), width=max(1, stroke))
        d.ellipse([cx - r * 0.28, cy - r * 0.28, cx + r * 0.28, cy + r * 0.28], fill=(118, 185, 0, 255))
    # GPU die
    d.rounded_rectangle(
        [s * 0.40, s * 0.40, s * 0.60, s * 0.64],
        radius=max(1, int(s * 0.03)),
        fill=(28, 38, 28, 255),
        outline=(168, 220, 80, 255),
        width=max(1, stroke // 2),
    )
    # PCIe gold edge
    d.rectangle([s * 0.22, s - m - s * 0.02, s * 0.78, s - m + s * 0.02], fill=(214, 176, 64, 255))
    return img


def make_icon_image(size: int = 64) -> Image.Image:
    return _draw_gpu(size)


def icon_file() -> Path:
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        bundled = meipass / "pz_nvml_dcgm_exporter" / "assets" / "app.ico"
        if bundled.exists():
            return bundled
        beside = Path(sys.executable).with_name("app.ico")
        if beside.exists():
            return beside
    here = Path(__file__).resolve().parent / "assets" / "app.ico"
    return here


def save_app_ico(path: Path | None = None) -> Path:
    dest = path or (Path(__file__).resolve().parent / "assets" / "app.ico")
    dest.parent.mkdir(parents=True, exist_ok=True)
    sizes = [(16, 16), (20, 20), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    _draw_gpu(256).save(dest, format="ICO", sizes=sizes)
    return dest
