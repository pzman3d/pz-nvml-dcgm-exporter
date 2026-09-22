"""Compact dark-themed window showing dcgm-exporter compatible metrics."""

from __future__ import annotations

import os
import sys
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from typing import Optional

from pz_nvml_dcgm_exporter import APP_NAME, __version__
from pz_nvml_dcgm_exporter import autostart
from pz_nvml_dcgm_exporter.collector import NvmlCollector, ProcessUsage, Snapshot
from pz_nvml_dcgm_exporter.i18n import LANG_EN, LANG_ZH, get_lang, set_lang, t
from pz_nvml_dcgm_exporter.icon import icon_file, make_icon_image
from pz_nvml_dcgm_exporter.metrics import METRIC_DEFS, METRIC_ORDER, METRIC_UNITS, format_prometheus_value, render_prometheus
from pz_nvml_dcgm_exporter.netinfo import _primary_ipv4, access_hosts, browse_url, choice_label, metrics_url
from pz_nvml_dcgm_exporter.server import MetricsServer

BG = "#101418"
CARD = "#1b222c"
BORDER = "#2c3644"
ACCENT = "#76b900"
TEXT = "#eef2f6"
MUTED = "#8a97a8"
WARN = "#f5a623"
ERR = "#ff6b6b"
MONO = ("Consolas", 10)
UI = ("Segoe UI", 10)
UI_B = ("Segoe UI", 11, "bold")
UI_S = ("Segoe UI", 9)
TITLE = ("Segoe UI", 14, "bold")
BIG = ("Segoe UI", 18, "bold")
BAR_FONT = ("Segoe UI", 8, "bold")
BAR_BG = "#121820"
BAR_TRACK = "#121820"


class UsageBar(tk.Canvas):
    """Horizontal usage bar with the percentage drawn in the center."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(
            master,
            height=16,
            bg=BAR_BG,
            highlightthickness=1,
            highlightbackground=BORDER,
            bd=0,
        )
        self._pct: Optional[float] = None
        self.pack_propagate(False)
        self.bind("<Configure>", lambda _e: self._draw())

    def set_percent(self, pct: Optional[float]) -> None:
        if pct is None:
            self._pct = None
        else:
            try:
                self._pct = max(0.0, min(100.0, float(pct)))
            except (TypeError, ValueError):
                self._pct = None
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        w = max(int(self.winfo_width()), 2)
        h = max(int(self.winfo_height()), 2)
        self.create_rectangle(0, 0, w, h, fill=BAR_TRACK, outline="")
        if self._pct is None:
            label = "—"
        else:
            fill_w = int(round(w * self._pct / 100.0))
            color = ACCENT
            if self._pct >= 85:
                color = ERR
            elif self._pct >= 70:
                color = WARN
            if fill_w > 0:
                self.create_rectangle(0, 0, fill_w, h, fill=color, outline="")
            label = f"{self._pct:.0f}%"
        self.create_text(w / 2, h / 2, text=label, fill=TEXT, font=BAR_FONT)


class ExporterApp(tk.Tk):
    def __init__(
        self,
        collector: NvmlCollector,
        server: MetricsServer,
        start_hidden: bool = False,
    ) -> None:
        super().__init__()
        self.collector = collector
        self.server = server
        self._cards: list[tk.Frame] = []
        self._last_gpu_count = -1
        self._restarting = False
        self._update_btn: Optional[tk.Button] = None
        self._tray = None
        self._quitting = False

        self.title(f"{APP_NAME}  v{__version__}")
        self.configure(bg=BG)
        self.geometry("920x660")
        self.minsize(820, 560)
        self._apply_icon()

        self._style()
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        self.bind("<Unmap>", self._on_unmap)
        self._setup_tray()
        self.after(200, self._refresh)
        if start_hidden:
            self.withdraw()

    def _style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=CARD, foreground=TEXT, padding=(14, 6), font=UI)
        style.map("TNotebook.Tab", background=[("selected", ACCENT)], foreground=[("selected", "#101418")])
        style.configure(
            "Treeview",
            background=CARD,
            foreground=TEXT,
            fieldbackground=CARD,
            borderwidth=0,
            font=UI_S,
            rowheight=24,
        )
        style.configure("Treeview.Heading", background="#151b23", foreground=MUTED, font=("Segoe UI", 9, "bold"), relief="flat")
        style.map("Treeview", background=[("selected", "#2d3b22")], foreground=[("selected", TEXT)])
        style.configure("Vertical.TScrollbar", background=CARD, troughcolor=BG, bordercolor=BG)
        style.configure(
            "Dark.TCombobox",
            fieldbackground=CARD,
            background=CARD,
            foreground=ACCENT,
            arrowcolor=ACCENT,
            bordercolor=BORDER,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", CARD)],
            foreground=[("readonly", ACCENT)],
            background=[("readonly", CARD)],
        )

    def _build(self) -> None:
        pad = {"padx": 14, "pady": 8}
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", **pad)

        self.autostart_var = tk.BooleanVar(value=autostart.is_enabled())
        self.autostart_cb = tk.Checkbutton(
            header,
            text=t("autostart"),
            variable=self.autostart_var,
            command=self._on_autostart_toggle,
            bg=BG,
            fg=TEXT,
            activebackground=BG,
            activeforeground=ACCENT,
            selectcolor=CARD,
            highlightthickness=0,
            bd=0,
            font=UI_S,
            cursor="hand2",
        )
        self.autostart_cb.pack(side="right")

        self.host_var = tk.StringVar(value=self.collector.snapshot().hostname)
        tk.Label(header, textvariable=self.host_var, fg=ACCENT, bg=BG, font=TITLE).pack(side="left")
        tk.Label(header, text=APP_NAME, fg=TEXT, bg=BG, font=UI).pack(side="left", padx=(12, 0))

        self.status_dot = tk.Label(header, text="●", fg=WARN, bg=BG, font=("Segoe UI", 14))
        self.status_dot.pack(side="left", padx=(16, 4))
        self.status_lbl = tk.Label(header, text=t("starting"), fg=MUTED, bg=BG, font=UI)
        self.status_lbl.pack(side="left")

        self.cards_host = tk.Frame(self, bg=BG)
        self.cards_host.pack(fill="x", padx=14)

        info = tk.Frame(self, bg=BG)
        info.pack(fill="x", padx=14, pady=(8, 0))
        self.port_var = tk.StringVar(value=str(self.server.port))
        self.url_var = tk.StringVar()
        self._url_hosts: list[str] = []
        self._url_kinds: list[str] = []
        tk.Label(info, text="Prometheus", fg=MUTED, bg=BG, font=UI_S).pack(side="left")
        self.url_combo = ttk.Combobox(
            info,
            textvariable=self.url_var,
            state="readonly",
            font=MONO,
            style="Dark.TCombobox",
        )
        self.url_combo.pack(side="left", fill="x", expand=True, padx=8, ipady=2)
        self.url_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_url_selected())
        self._refresh_url_choices(keep=False)

        self.port_lbl = tk.Label(info, text=t("port"), fg=MUTED, bg=BG, font=UI_S)
        self.port_lbl.pack(side="left", padx=(4, 4))
        port_entry = tk.Entry(
            info,
            textvariable=self.port_var,
            width=6,
            bg=CARD,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=MONO,
            justify="center",
        )
        port_entry.pack(side="left", ipady=4, padx=(0, 8))
        port_entry.bind("<Return>", lambda _e: self._restart_service())

        self._update_btn = self._make_action_btn(info, t("update"), self._restart_service)
        self._copy_btn = self._make_action_btn(info, t("copy"), self._copy_url)
        self._open_btn = self._make_action_btn(info, t("open"), self._open_url)

        footer = tk.Frame(self, bg=BG)
        foot_row = tk.Frame(footer, bg=BG)
        foot_row.pack(fill="x")
        self.footer_lbl = tk.Label(foot_row, text="", fg=MUTED, bg=BG, font=UI_S, anchor="w")
        self.footer_lbl.pack(side="left", fill="x", expand=True)
        lang_box = tk.Frame(foot_row, bg=BG)
        lang_box.pack(side="right")
        self.lang_zh_btn = tk.Label(lang_box, text="ä¸­æ?", bg=BG, cursor="hand2")
        self.lang_sep = tk.Label(lang_box, text=" | ", fg=MUTED, bg=BG, font=UI_S)
        self.lang_en_btn = tk.Label(lang_box, text="English", bg=BG, cursor="hand2")
        self.lang_zh_btn.pack(side="left")
        self.lang_sep.pack(side="left")
        self.lang_en_btn.pack(side="left")
        self.lang_zh_btn.bind("<Button-1>", lambda _e: self._set_lang(LANG_ZH))
        self.lang_en_btn.bind("<Button-1>", lambda _e: self._set_lang(LANG_EN))
        self.footer_hint = tk.Label(
            footer,
            text=t("tray_hint"),
            fg=MUTED,
            bg=BG,
            font=UI_S,
            anchor="w",
        )
        self.footer_hint.pack(fill="x", pady=(2, 0))
        self._style_lang_buttons()
        footer.pack(side="bottom", fill="x", padx=14, pady=(0, 10))
        footer.update_idletasks()
        footer.configure(height=max(int(footer.winfo_reqheight()), 56))
        footer.pack_propagate(False)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=14, pady=10)

        table_frame = tk.Frame(self.nb, bg=CARD)
        proc_frame = tk.Frame(self.nb, bg=CARD)
        raw_frame = tk.Frame(self.nb, bg=CARD)
        self.nb.add(table_frame, text=t("tab_metrics"))
        self.nb.add(proc_frame, text=t("tab_proc"))
        self.nb.add(raw_frame, text=t("tab_raw"))

        cols = ("metric", "gpu", "value", "unit", "help")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        headings = {
            "metric": ("col_metric", 280),
            "gpu": ("col_gpu", 50),
            "value": ("col_value", 110),
            "unit": ("col_unit", 70),
            "help": ("col_help", 280),
        }
        for key, (title_key, width) in headings.items():
            self.tree.heading(key, text=t(title_key), anchor="w")
            self.tree.column(key, width=width, anchor="w", stretch=key in ("metric", "help"))
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        vsb.pack(side="right", fill="y", pady=8, padx=(0, 8))

        proc_cols = ("cancel", "gpu", "pid", "name", "vram", "util", "kind")
        self.proc_tree = ttk.Treeview(proc_frame, columns=proc_cols, show="headings", selectmode="browse")
        proc_headings = {
            "cancel": ("col_cancel", 78),
            "gpu": ("col_gpu", 50),
            "pid": ("col_pid", 80),
            "name": ("col_name", 240),
            "vram": ("col_vram", 110),
            "util": ("col_util", 110),
            "kind": ("col_kind", 70),
        }
        for key, (title_key, width) in proc_headings.items():
            anchor = "center" if key == "cancel" else "w"
            self.proc_tree.heading(key, text=t(title_key), anchor=anchor)
            self.proc_tree.column(key, width=width, anchor=anchor, stretch=key == "name")
        self.proc_tree.tag_configure("usage_idle", foreground=MUTED)
        self.proc_tree.tag_configure("usage_ok", foreground=TEXT)
        self.proc_tree.tag_configure("usage_mid", foreground=ACCENT)
        self.proc_tree.tag_configure("usage_warn", foreground=WARN)
        self.proc_tree.tag_configure("usage_high", foreground=ERR)
        self.proc_tree.bind("<Button-1>", self._on_proc_click)
        self.proc_tree.bind("<Motion>", self._on_proc_motion)
        proc_vsb = ttk.Scrollbar(proc_frame, orient="vertical", command=self.proc_tree.yview)
        self.proc_tree.configure(yscrollcommand=proc_vsb.set)
        self.proc_tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        proc_vsb.pack(side="right", fill="y", pady=8, padx=(0, 8))

        self.raw = tk.Text(
            raw_frame,
            bg="#0c1014",
            fg="#c5e1a5",
            insertbackground=TEXT,
            relief="flat",
            font=MONO,
            wrap="none",
        )
        raw_vsb = ttk.Scrollbar(raw_frame, orient="vertical", command=self.raw.yview)
        raw_hsb = ttk.Scrollbar(raw_frame, orient="horizontal", command=self.raw.xview)
        self.raw.configure(yscrollcommand=raw_vsb.set, xscrollcommand=raw_hsb.set)
        self.raw.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=(8, 0))
        raw_vsb.grid(row=0, column=1, sticky="ns", pady=(8, 0), padx=(0, 8))
        raw_hsb.grid(row=1, column=0, sticky="ew", padx=(8, 0), pady=(0, 8))
        raw_frame.grid_rowconfigure(0, weight=1)
        raw_frame.grid_columnconfigure(0, weight=1)
        self.raw.bind("<Key>", lambda e: "break")

    def _make_action_btn(self, parent: tk.Misc, text: str, command) -> tk.Button:
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg="#243018",
            fg=ACCENT,
            activebackground=ACCENT,
            activeforeground="#101418",
            relief="flat",
            font=UI_S,
            padx=12,
            pady=4,
            cursor="hand2",
        )
        btn.pack(side="left", padx=(0, 6))
        return btn

    def _style_lang_buttons(self) -> None:
        zh = get_lang() == LANG_ZH
        self.lang_zh_btn.configure(text=t("lang_zh"), fg=ACCENT if zh else MUTED, font=UI_B if zh else UI_S)
        self.lang_en_btn.configure(text=t("lang_en"), fg=ACCENT if not zh else MUTED, font=UI_B if not zh else UI_S)

    def _set_lang(self, lang: str) -> None:
        if get_lang() == lang:
            return
        set_lang(lang)
        self._apply_i18n()
        self._paint()

    def _apply_i18n(self) -> None:
        self.autostart_cb.configure(text=t("autostart"))
        self.port_lbl.configure(text=t("port"))
        if self._update_btn is not None:
            self._update_btn.configure(text=t("updating") if self._restarting else t("update"))
        self._copy_btn.configure(text=t("copy"))
        self._open_btn.configure(text=t("open"))
        self.nb.tab(0, text=t("tab_metrics"))
        self.nb.tab(1, text=t("tab_proc"))
        self.nb.tab(2, text=t("tab_raw"))
        for key, title_key in (
            ("metric", "col_metric"),
            ("gpu", "col_gpu"),
            ("value", "col_value"),
            ("unit", "col_unit"),
            ("help", "col_help"),
        ):
            self.tree.heading(key, text=t(title_key))
        for key, title_key in (
            ("cancel", "col_cancel"),
            ("gpu", "col_gpu"),
            ("pid", "col_pid"),
            ("name", "col_name"),
            ("vram", "col_vram"),
            ("util", "col_util"),
            ("kind", "col_kind"),
        ):
            self.proc_tree.heading(key, text=t(title_key))
        self.footer_hint.configure(text=t("tray_hint"))
        self._style_lang_buttons()
        self._refresh_url_choices(keep=True)
        for card in self._cards:
            captions = getattr(card, "_captions", {})
            for key, lbl in captions.items():
                lbl.configure(text=t(f"card_{key}"))
        for child in self.cards_host.winfo_children():
            if isinstance(child, tk.Label):
                child.configure(text=t("no_gpu"))

    def _copy_url(self) -> None:
        url = self._selected_metrics_url()
        self.clipboard_clear()
        self.clipboard_append(url)
        self.footer_lbl.configure(text=t("copied", url=url))

    def _open_url(self) -> None:
        webbrowser.open(self._selected_browse_url())

    def _selected_host(self) -> str:
        idx = self.url_combo.current()
        if 0 <= idx < len(self._url_hosts):
            return self._url_hosts[idx]
        return "127.0.0.1"

    def _selected_metrics_url(self) -> str:
        return metrics_url(self._selected_host(), self.server.port)

    def _selected_browse_url(self) -> str:
        return browse_url(self._selected_host(), self.server.port)

    def _host_display_label(self, label: str) -> str:
        if label == "localhost":
            return t("host_localhost")
        if label.startswith("Hostname "):
            return t("host_hostname", name=label[len("Hostname "):])
        if label == "Default NIC":
            return t("host_primary")
        if label == "LAN":
            return t("host_lan")
        if label == "NIC":
            return t("host_nic")
        return label

    def _on_url_selected(self) -> None:
        self.footer_lbl.configure(text=t("prometheus", url=self._selected_metrics_url()))

    def _refresh_url_choices(self, keep: bool = True) -> None:
        previous = self._selected_host() if keep and self._url_hosts else ""
        hosts = access_hosts()
        if not hosts:
            hosts = [("localhost", "127.0.0.1")]
        self._url_kinds = [label for label, _host in hosts]
        self._url_hosts = [host for _label, host in hosts]
        labels = [
            choice_label(self._host_display_label(label), host, self.server.port)
            for label, host in hosts
        ]
        self.url_combo["values"] = labels
        idx = 0
        if previous:
            for i, host in enumerate(self._url_hosts):
                if host == previous:
                    idx = i
                    break
        else:
            primary = _primary_ipv4()
            for i, host in enumerate(self._url_hosts):
                if host == primary:
                    idx = i
                    break
        self.url_combo.current(idx)

    def _parse_port(self) -> Optional[int]:
        raw = self.port_var.get().strip()
        try:
            port = int(raw)
        except ValueError:
            messagebox.showerror(t("invalid_port_title"), t("invalid_port_int"))
            self.port_var.set(str(self.server.port))
            return None
        if port < 1 or port > 65535:
            messagebox.showerror(t("invalid_port_title"), t("invalid_port_range"))
            self.port_var.set(str(self.server.port))
            return None
        return port

    def _restart_service(self) -> None:
        if self._restarting:
            return
        port = self._parse_port()
        if port is None:
            return
        self._restarting = True
        if self._update_btn is not None:
            self._update_btn.configure(state="disabled", text=t("updating"))
        self.footer_lbl.configure(text=t("restarting", port=port))
        self.update_idletasks()
        try:
            self.collector.restart()
            self.server.restart(port)
        except OSError as exc:
            self.port_var.set(str(self.server.port))
            self._refresh_url_choices(keep=True)
            messagebox.showerror(
                t("restart_fail_title"),
                t("restart_fail_body", host=self.server.host, port=port, exc=exc, old=self.server.port),
            )
            self.footer_lbl.configure(text=t("restart_fail_footer", port=self.server.port))
        else:
            self.port_var.set(str(self.server.port))
            self._refresh_url_choices(keep=True)
            self.footer_lbl.configure(text=t("restarted", url=self._selected_metrics_url()))
        finally:
            self._restarting = False
            if self._update_btn is not None:
                self._update_btn.configure(state="normal", text=t("update"))

    def _refresh(self) -> None:
        self._paint()
        self.after(1000, self._refresh)

    def _paint(self) -> None:
        if self._restarting:
            return
        try:
            snap = self.collector.snapshot()
            self._render_status(snap)
            self._render_cards(snap)
            self._render_table(snap)
            self._render_processes(snap)
            self._render_raw(snap)
            self._render_footer(snap)
        except Exception as exc:
            self.status_lbl.configure(text=t("refresh_fail", exc=exc), fg=ERR)

    def _render_status(self, snap: Snapshot) -> None:
        if snap.hostname:
            self.host_var.set(snap.hostname)
        if snap.ok:
            self.status_dot.configure(fg=ACCENT)
            self.status_lbl.configure(
                text=t("ready", url=self._selected_metrics_url(), driver=snap.driver_version or "—"),
                fg=TEXT,
            )
        else:
            self.status_dot.configure(fg=ERR)
            self.status_lbl.configure(text=snap.error or t("nvml_unavailable"), fg=ERR)

    def _render_cards(self, snap: Snapshot) -> None:
        if len(snap.gpus) != self._last_gpu_count:
            for child in self.cards_host.winfo_children():
                child.destroy()
            self._cards = []
            self._last_gpu_count = len(snap.gpus)
            if not snap.gpus:
                empty = tk.Label(
                    self.cards_host,
                    text=t("no_gpu"),
                    fg=MUTED,
                    bg=BG,
                    font=UI,
                    anchor="w",
                    justify="left",
                )
                empty.pack(fill="x", pady=6)
                return
            for gpu in snap.gpus:
                self._cards.append(self._make_card(gpu.index, gpu.name, gpu.uuid))

        for gpu in snap.gpus:
            if gpu.index >= len(self._cards):
                continue
            vals = snap.values.get(gpu.index, {})
            card = self._cards[gpu.index]
            mem_used = vals.get("DCGM_FI_DEV_FB_USED")
            mem_free = vals.get("DCGM_FI_DEV_FB_FREE")
            mem_rsv = vals.get("DCGM_FI_DEV_FB_RESERVED", 0.0) or 0.0
            mem_total = None
            if mem_used is not None and mem_free is not None:
                mem_total = mem_used + mem_free + mem_rsv
            updates = {
                "util": _fmt(vals.get("DCGM_FI_DEV_GPU_UTIL"), "%"),
                "temp": _fmt(vals.get("DCGM_FI_DEV_GPU_TEMP"), "Â°C"),
                "power": _fmt(vals.get("DCGM_FI_DEV_POWER_USAGE"), "W", digits=1),
                "mem": _fmt_mem(mem_used, mem_total),
                "clock": _fmt(vals.get("DCGM_FI_DEV_SM_CLOCK"), "MHz"),
            }
            percents = {
                "util": vals.get("DCGM_FI_DEV_GPU_UTIL"),
                "temp": _pct_of(vals.get("DCGM_FI_DEV_GPU_TEMP"), vals.get("_GPU_TEMP_SLOWDOWN") or 100.0),
                "power": _pct_of(vals.get("DCGM_FI_DEV_POWER_USAGE"), vals.get("_POWER_LIMIT_W")),
                "mem": _pct_of(mem_used, mem_total),
                "clock": _pct_of(vals.get("DCGM_FI_DEV_SM_CLOCK"), vals.get("_SM_CLOCK_MAX")),
            }
            vars_map = getattr(card, "_vars")
            bars_map = getattr(card, "_bars")
            for key, text in updates.items():
                vars_map[key].set(text)
                bars_map[key].set_percent(percents.get(key))

    def _make_card(self, index: int, name: str, uuid: str) -> tk.Frame:
        card = tk.Frame(self.cards_host, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x", pady=5)
        top = tk.Frame(card, bg=CARD)
        top.pack(fill="x", padx=12, pady=(8, 2))
        tk.Label(top, text=f"GPU {index}", fg=ACCENT, bg=CARD, font=UI_B).pack(side="left")
        tk.Label(top, text=name, fg=TEXT, bg=CARD, font=UI).pack(side="left", padx=10)
        tk.Label(top, text=uuid, fg=MUTED, bg=CARD, font=UI_S).pack(side="right")

        stats = tk.Frame(card, bg=CARD, height=96)
        stats.pack(fill="x", padx=8, pady=(0, 12))
        stats.pack_propagate(False)
        vars_map: dict[str, tk.StringVar] = {}
        bars_map: dict[str, UsageBar] = {}
        captions_map: dict[str, tk.Label] = {}
        fields = (
            ("util", "card_util"),
            ("temp", "card_temp"),
            ("power", "card_power"),
            ("mem", "card_mem"),
            ("clock", "card_clock"),
        )
        n = len(fields)
        for i, (key, caption_key) in enumerate(fields):
            box = tk.Frame(stats, bg=CARD)
            box.place(relx=i / n, rely=0, relwidth=1 / n, relheight=1)
            inner = tk.Frame(box, bg=CARD)
            inner.pack(fill="both", expand=True, padx=8, pady=2)
            var = tk.StringVar(value="—")
            vars_map[key] = var
            tk.Label(inner, textvariable=var, fg=TEXT, bg=CARD, font=BIG, anchor="w").pack(fill="x")
            bar = UsageBar(inner)
            bar.pack(fill="x", pady=(4, 4))
            bars_map[key] = bar
            cap = tk.Label(inner, text=t(caption_key), fg=MUTED, bg=CARD, font=UI_S, anchor="w")
            cap.pack(fill="x")
            captions_map[key] = cap
        setattr(card, "_vars", vars_map)
        setattr(card, "_bars", bars_map)
        setattr(card, "_captions", captions_map)
        return card

    def _render_table(self, snap: Snapshot) -> None:
        existing = self.tree.get_children()
        if existing:
            self.tree.delete(*existing)
        for gpu in snap.gpus:
            vals = snap.values.get(gpu.index, {})
            for name in METRIC_ORDER:
                if name not in vals:
                    continue
                _type, help_text = METRIC_DEFS[name]
                self.tree.insert(
                    "",
                    "end",
                    values=(
                        name,
                        gpu.index,
                        format_prometheus_value(vals[name]),
                        METRIC_UNITS.get(name, ""),
                        help_text,
                    ),
                )

    def _render_processes(self, snap: Snapshot) -> None:
        yview = self.proc_tree.yview()
        existing = self.proc_tree.get_children()
        if existing:
            self.proc_tree.delete(*existing)
        for proc in snap.processes:
            vram = f"{proc.vram_mib:.1f} MiB" if proc.vram_mib is not None else "—"
            util = f"{proc.gpu_util:.0f}%" if proc.gpu_util is not None else "—"
            self.proc_tree.insert(
                "",
                "end",
                iid=f"{proc.gpu_index}:{proc.pid}",
                values=(t("col_cancel"), proc.gpu_index, proc.pid, proc.name, vram, util, proc.kind or "—"),
                tags=(self._process_usage_tag(snap, proc),),
            )
        self.proc_tree.yview_moveto(yview[0])

    def _gpu_fb_total(self, snap: Snapshot, gpu_index: int) -> Optional[float]:
        vals = snap.values.get(gpu_index, {})
        used = vals.get("DCGM_FI_DEV_FB_USED")
        free = vals.get("DCGM_FI_DEV_FB_FREE")
        reserved = vals.get("DCGM_FI_DEV_FB_RESERVED") or 0.0
        if used is None or free is None:
            return None
        return used + free + reserved

    def _process_usage_tag(self, snap: Snapshot, proc: ProcessUsage) -> str:
        score = 0.0
        if proc.gpu_util is not None:
            score = max(score, float(proc.gpu_util))
        total = self._gpu_fb_total(snap, proc.gpu_index)
        if proc.vram_mib is not None and total:
            score = max(score, 100.0 * float(proc.vram_mib) / total)
        if score >= 85:
            return "usage_high"
        if score >= 70:
            return "usage_warn"
        if score >= 40:
            return "usage_mid"
        if score > 0:
            return "usage_ok"
        return "usage_idle"

    def _on_proc_motion(self, event: tk.Event) -> None:
        region = self.proc_tree.identify_region(event.x, event.y)
        col = self.proc_tree.identify_column(event.x)
        if region == "cell" and col == "#1":
            self.proc_tree.configure(cursor="hand2")
        else:
            self.proc_tree.configure(cursor="")

    def _on_proc_click(self, event: tk.Event) -> None:
        if self.proc_tree.identify_region(event.x, event.y) != "cell":
            return
        if self.proc_tree.identify_column(event.x) != "#1":
            return
        item = self.proc_tree.identify_row(event.y)
        if not item:
            return
        values = self.proc_tree.item(item, "values")
        if len(values) < 4:
            return
        try:
            pid = int(values[2])
        except (TypeError, ValueError):
            return
        name = str(values[3] or f"pid:{pid}")
        self.after(0, lambda: self._cancel_process(pid, name))

    def _cancel_process(self, pid: int, name: str) -> None:
        if pid <= 0:
            return
        if pid == os.getpid():
            messagebox.showinfo(t("cancel_confirm_title"), t("cancel_self"))
            return
        if not messagebox.askyesno(t("cancel_confirm_title"), t("cancel_confirm_body", name=name, pid=pid)):
            return
        try:
            _terminate_pid(pid)
        except PermissionError:
            messagebox.showerror(t("cancel_confirm_title"), t("cancel_denied"))
            self.footer_lbl.configure(text=t("cancel_denied"))
            return
        except OSError as exc:
            messagebox.showerror(t("cancel_confirm_title"), t("cancel_fail", name=name, pid=pid, exc=exc))
            self.footer_lbl.configure(text=t("cancel_fail", name=name, pid=pid, exc=exc))
            return
        self.footer_lbl.configure(text=t("cancel_ok", name=name, pid=pid))

    def _render_raw(self, snap: Snapshot) -> None:
        text = render_prometheus(snap.hostname, snap.driver_version, snap.prometheus_rows())
        if not text.strip():
            text = t("no_metrics")
        yview = self.raw.yview()
        self.raw.delete("1.0", "end")
        self.raw.insert("1.0", text)
        self.raw.yview_moveto(yview[0])

    def _render_footer(self, snap: Snapshot) -> None:
        age = ""
        if snap.collected_at:
            age = t("collected", time=time.strftime("%H:%M:%S", time.localtime(snap.collected_at)))
        scrape = t("scrapes", n=self.server.scrape_count)
        if self.server.last_scrape:
            scrape += t("last_scrape", time=time.strftime("%H:%M:%S", time.localtime(self.server.last_scrape)))
        gpu_n = t("gpu_count", n=len(snap.gpus), p=len(snap.processes))
        self.footer_lbl.configure(
            text=t(
                "stats_line",
                gpu_n=gpu_n,
                age=age,
                scrape=scrape,
                interval=self.collector.interval,
                port=self.server.port,
            )
        )

    def _apply_icon(self) -> None:
        try:
            path = icon_file()
            if not path.exists():
                from pz_nvml_dcgm_exporter.icon import save_app_ico

                path = save_app_ico(path)
            if path.exists():
                self.iconbitmap(str(path))
        except Exception:
            pass

    def _setup_tray(self) -> None:
        try:
            import pystray
            from pystray import Menu, MenuItem
        except Exception:
            return
        image = make_icon_image(64)
        menu = Menu(
            MenuItem(lambda _item: t("tray_show"), self._tray_show, default=True),
            MenuItem(lambda _item: t("tray_autostart"), self._tray_toggle_autostart, checked=lambda _: autostart.is_enabled()),
            Menu.SEPARATOR,
            MenuItem(lambda _item: t("tray_quit"), self._tray_quit),
        )
        self._tray = pystray.Icon(APP_NAME, image, APP_NAME, menu)
        self._tray.run_detached()

    def _on_unmap(self, event: tk.Event) -> None:
        if self._quitting or event.widget is not self:
            return
        try:
            if self.state() == "iconic":
                self.after(0, self._hide_to_tray)
        except tk.TclError:
            pass

    def _hide_to_tray(self) -> None:
        if self._quitting:
            self._quit_app()
            return
        self.withdraw()

    def _restore_window(self) -> None:
        self.deiconify()
        self.state("normal")
        self.lift()
        self._refresh_url_choices(keep=True)
        try:
            self.focus_force()
        except tk.TclError:
            pass

    def _tray_show(self, _icon=None, _item=None) -> None:
        self.after(0, self._restore_window)

    def _tray_quit(self, _icon=None, _item=None) -> None:
        self.after(0, self._quit_app)

    def _tray_toggle_autostart(self, _icon=None, _item=None) -> None:
        self.after(0, self._toggle_autostart_from_tray)

    def _toggle_autostart_from_tray(self) -> None:
        self.autostart_var.set(not autostart.is_enabled())
        self._on_autostart_toggle()

    def _on_autostart_toggle(self) -> None:
        enabled = bool(self.autostart_var.get())
        try:
            autostart.set_enabled(enabled)
        except OSError as exc:
            self.autostart_var.set(autostart.is_enabled())
            messagebox.showerror(t("autostart_title"), t("autostart_fail", exc=exc))
            return
        self.footer_lbl.configure(text=t("autostart_on") if enabled else t("autostart_off"))

    def _quit_app(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        if self._tray is not None:
            try:
                self._tray.stop()
            except Exception:
                pass
            self._tray = None
        try:
            self.server.stop()
        except Exception:
            pass
        try:
            self.collector.stop()
        except Exception:
            pass
        self.destroy()


def _fmt(value: Optional[float], unit: str, digits: int = 0) -> str:
    if value is None:
        return "—"
    if digits == 0 and float(value).is_integer():
        return f"{int(value)}{unit}"
    return f"{value:.{digits}f}{unit}"


def _fmt_mem(used: Optional[float], total: Optional[float]) -> str:
    if used is None:
        return "—"
    if total:
        return f"{used / 1024:.1f}/{total / 1024:.1f}G"
    return f"{used:.0f} MiB"


def _pct_of(value: Optional[float], total: Optional[float]) -> Optional[float]:
    if value is None or total is None or total <= 0:
        return None
    return float(value) / float(total) * 100.0


def _terminate_pid(pid: int) -> None:
    pid = int(pid)
    if pid <= 0:
        raise OSError("invalid pid")
    if sys.platform != "win32":
        os.kill(pid, 15)
        return
    import ctypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = k32.OpenProcess(0x0001, False, pid)
    if not handle:
        err = ctypes.get_last_error()
        if err == 5:
            raise PermissionError(err, "OpenProcess")
        raise ctypes.WinError(err)
    try:
        if not k32.TerminateProcess(handle, 1):
            err = ctypes.get_last_error()
            if err == 5:
                raise PermissionError(err, "TerminateProcess")
            raise ctypes.WinError(err)
    finally:
        k32.CloseHandle(handle)
