"""Enumerate this machine's reachable IP addresses for the Prometheus URL menu."""

from __future__ import annotations

import socket
import sys


def access_hosts() -> list[tuple[str, str]]:
    """Return [(display_label, host), ...] unique by host."""
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(label: str, host: str, *, loopback: bool = False) -> None:
        host = (host or "").strip()
        if not host or host in seen:
            return
        if not loopback and (host.startswith("169.254.") or host.startswith("127.")):
            return
        seen.add(host)
        rows.append((label, host))

    add("localhost", "127.0.0.1", loopback=True)
    hostname = socket.gethostname()
    add(f"Hostname {hostname}", hostname, loopback=True)
    for label, ip in _adapter_ipv4():
        add(label, ip)
    primary = _primary_ipv4()
    if primary:
        add("Default NIC", primary)
    try:
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM):
            add("LAN", info[4][0])
    except OSError:
        pass
    return rows


def metrics_url(host: str, port: int) -> str:
    return f"http://{_host_for_url(host)}:{int(port)}/metrics"


def browse_url(host: str, port: int) -> str:
    return f"http://{_host_for_url(host)}:{int(port)}/"


def _host_for_url(host: str) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def _primary_ipv4() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.2)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return ""


def _adapter_ipv4() -> list[tuple[str, str]]:
    if sys.platform == "win32":
        named = _windows_adapters()
        if named:
            return named
    return []


def _windows_adapters() -> list[tuple[str, str]]:
    import ctypes
    from ctypes import Structure, c_void_p, wintypes

    class SOCKADDR_IN(Structure):
        _fields_ = [
            ("sin_family", wintypes.USHORT),
            ("sin_port", wintypes.USHORT),
            ("sin_addr", ctypes.c_ubyte * 4),
            ("sin_zero", ctypes.c_ubyte * 8),
        ]

    class SOCKET_ADDRESS(Structure):
        _fields_ = [("lpSockaddr", c_void_p), ("iSockaddrLength", ctypes.c_int)]

    class IP_ADAPTER_UNICAST_ADDRESS(Structure):
        _fields_ = [
            ("Length", wintypes.ULONG),
            ("Flags", wintypes.DWORD),
            ("Next", c_void_p),
            ("Address", SOCKET_ADDRESS),
        ]

    class IP_ADAPTER_ADDRESSES(Structure):
        _fields_ = [
            ("Length", wintypes.ULONG),
            ("IfIndex", wintypes.DWORD),
            ("Next", c_void_p),
            ("AdapterName", c_void_p),
            ("FirstUnicastAddress", c_void_p),
            ("FirstAnycastAddress", c_void_p),
            ("FirstMulticastAddress", c_void_p),
            ("FirstDnsServerAddress", c_void_p),
            ("DnsSuffix", c_void_p),
            ("Description", c_void_p),
            ("FriendlyName", c_void_p),
            ("PhysicalAddress", ctypes.c_ubyte * 8),
            ("PhysicalAddressLength", wintypes.DWORD),
            ("Flags", wintypes.DWORD),
            ("Mtu", wintypes.DWORD),
            ("IfType", wintypes.DWORD),
            ("OperStatus", ctypes.c_int),
        ]

    GAA_FLAGS = 0x2 | 0x4 | 0x8
    IfOperStatusUp = 1
    iphlpapi = ctypes.windll.iphlpapi
    size = wintypes.ULONG(0)
    iphlpapi.GetAdaptersAddresses(0, GAA_FLAGS, None, None, ctypes.byref(size))
    if size.value == 0:
        return []
    buf = ctypes.create_string_buffer(size.value)
    if iphlpapi.GetAdaptersAddresses(0, GAA_FLAGS, None, buf, ctypes.byref(size)) != 0:
        return []

    def wstr(ptr: int | None) -> str:
        return ctypes.wstring_at(ptr) if ptr else ""

    rows: list[tuple[str, str]] = []
    ptr = ctypes.addressof(buf)
    while ptr:
        info = IP_ADAPTER_ADDRESSES.from_address(ptr)
        name = wstr(info.FriendlyName) or wstr(info.Description) or "NIC"
        ucast = info.FirstUnicastAddress
        while ucast:
            uni = IP_ADAPTER_UNICAST_ADDRESS.from_address(ucast)
            if uni.Address.lpSockaddr:
                sin = SOCKADDR_IN.from_address(uni.Address.lpSockaddr)
                if sin.sin_family == 2:
                    ip = ".".join(str(b) for b in sin.sin_addr)
                    if (
                        ip
                        and not ip.startswith("127.")
                        and not ip.startswith("0.")
                        and not ip.startswith("169.254.")
                        and info.OperStatus == IfOperStatusUp
                    ):
                        rows.append((name, ip))
            ucast = uni.Next
        ptr = info.Next
    return rows


def choice_label(label: str, host: str, port: int) -> str:
    return f"{label}  {host}   {metrics_url(host, port)}"


def parse_choice(choice: str) -> str:
    """Extract host from a dropdown label; fall back to the whole string."""
    text = (choice or "").strip()
    if "://" in text:
        after = text.rsplit("://", 1)[-1]
        hostport = after.split("/", 1)[0]
        host = hostport.rsplit(":", 1)[0].strip("[]")
        return host
    parts = text.split()
    for part in reversed(parts):
        if part.count(".") == 3 or ":" in part:
            return part.strip("[]")
    return text
