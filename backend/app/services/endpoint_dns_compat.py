"""allowlist 端点的本机代理 fake-IP 兼容解析（ADR-LLM-015）。

开启 TUN 的代理客户端（Clash / mihomo / Mesl 等）会劫持本机所有 DNS：先给域名分配
198.18/15 的 fake-IP，连接时再用代理自己的上游 DNS 解析。企业内网域名在公网 DNS 不存在，
代理解析失败后直接关闭连接，应用只看到 TLS 握手中断（2026-10-19 实测）。

本模块只在**系统解析结果全部是 fake-IP（或解析失败）**时由 endpoint policy 调用：
绕过代理 DNS，向本机网卡配置的 DNS 查询真实地址；连接只改 TCP 目标，URL、Host、
TLS SNI 与证书校验仍按原域名，被投毒的地址拿不到该域名的有效证书。
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import random
import socket
import ssl
import struct
import sys
import time
from dataclasses import dataclass
from typing import Callable, Mapping
from urllib.parse import urlsplit

import httpcore
import httpx

from app.core.config import settings

FAKE_IP_NETWORK = ipaddress.ip_network("198.18.0.0/15")
_QUERY_TIMEOUT = 1.5      # 单次 DNS 尝试
_DISCOVERY_BUDGET = 6.0   # 一次发现的总时长上限
_MIN_TTL, _MAX_TTL, _NEGATIVE_TTL = 30, 300, 30
_MAX_SERVERS = 4


@dataclass(frozen=True)
class DiscoveryOutcome:
    """一次真实地址发现的结果；status ∈ found / override / nxdomain / unreachable / no_servers。"""

    host: str
    addresses: tuple[str, ...]
    status: str
    servers: tuple[str, ...] = ()
    via: str = ""
    expires_at: float = 0.0


_cache: dict[str, DiscoveryOutcome] = {}
_locks: dict[str, asyncio.Lock] = {}


def is_fake_ip(address: str) -> bool:
    try:
        return ipaddress.ip_address(address) in FAKE_IP_NETWORK
    except ValueError:
        return False


def last_outcome(host: str) -> DiscoveryOutcome | None:
    """最近一次发现结果（含已过期的），供错误诊断使用。"""
    return _cache.get(host.lower())


def clear_cache() -> None:
    _cache.clear()
    _locks.clear()


def _split(raw: str) -> list[str]:
    return [item.strip() for item in str(raw or "").replace(";", ",").split(",") if item.strip()]


def host_override(host: str) -> str | None:
    for item in _split(settings.LLM_ENDPOINT_HOST_OVERRIDES):
        name, _, address = item.partition("=")
        if name.strip().lower() == host.lower() and address.strip():
            return address.strip()
    return None


# ---------------------------------------------------------------------------
# DNS 报文（只查 A 记录）
# ---------------------------------------------------------------------------


def _encode_query(host: str) -> tuple[int, bytes]:
    labels = host.rstrip(".").encode("idna").split(b".")
    if not labels or any(not label or len(label) > 63 for label in labels):
        raise ValueError("非法域名")
    qid = random.randint(0, 0xFFFF)
    qname = b"".join(bytes([len(label)]) + label for label in labels) + b"\x00"
    return qid, struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0) + qname + struct.pack(">HH", 1, 1)


def _skip_name(buf: bytes, offset: int) -> int:
    while True:
        if offset >= len(buf):
            raise ValueError("DNS 响应被截断")
        length = buf[offset]
        if length == 0:
            return offset + 1
        if length & 0xC0 == 0xC0:
            return offset + 2
        offset += 1 + length


def _decode_answer(buf: bytes, qid: int) -> tuple[str, list[tuple[str, int]]]:
    """返回 (status, [(ip, ttl)])；status ∈ found / nxdomain / nodata / error。"""
    if len(buf) < 12:
        raise ValueError("DNS 响应过短")
    rid, flags, qdcount, ancount, _, _ = struct.unpack(">HHHHHH", buf[:12])
    if rid != qid or not flags & 0x8000:
        raise ValueError("DNS 响应与查询不匹配")
    rcode = flags & 0x000F
    if rcode == 3:
        return "nxdomain", []
    if rcode != 0:
        return "error", []
    offset = 12
    for _ in range(qdcount):
        offset = _skip_name(buf, offset) + 4
    records: list[tuple[str, int]] = []
    for _ in range(ancount):
        offset = _skip_name(buf, offset)
        if offset + 10 > len(buf):
            raise ValueError("DNS 响应被截断")
        rtype, rclass, ttl, rdlength = struct.unpack(">HHIH", buf[offset:offset + 10])
        offset += 10
        if rtype == 1 and rclass == 1 and rdlength == 4:
            records.append((socket.inet_ntoa(buf[offset:offset + 4]), ttl))
        offset += rdlength
    return ("found" if records else "nodata"), records


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("连接被关闭")
        data += chunk
    return data


def _exchange_tcp(sock: socket.socket, packet: bytes) -> bytes:
    sock.sendall(struct.pack(">H", len(packet)) + packet)
    length = struct.unpack(">H", _recv_exact(sock, 2))[0]
    return _recv_exact(sock, length)


def _query_tcp(server: str, packet: bytes) -> bytes:
    with socket.create_connection((server, 53), timeout=_QUERY_TIMEOUT) as sock:
        sock.settimeout(_QUERY_TIMEOUT)
        return _exchange_tcp(sock, packet)


def _query_via_proxy(proxy: tuple[str, int], server: str, packet: bytes) -> bytes:
    """经本机 HTTP 代理 CONNECT 到 DNS 服务器的 TCP 53（代理进程不受自身 DNS 拦截规则约束）。"""
    with socket.create_connection(proxy, timeout=_QUERY_TIMEOUT) as sock:
        sock.settimeout(_QUERY_TIMEOUT)
        sock.sendall(f"CONNECT {server}:53 HTTP/1.1\r\nHost: {server}:53\r\n\r\n".encode("ascii"))
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = sock.recv(1024)
            if not chunk or len(head) > 8192:
                raise ConnectionError("代理未完成 CONNECT")
            head += chunk
        header, _, early_data = head.partition(b"\r\n\r\n")
        parts = header.split(b"\r\n", 1)[0].split()
        # 隧道建立前不应有 DNS 数据；有就说明不是标准 CONNECT 代理，宁可放弃。
        if len(parts) < 2 or parts[1] != b"200" or early_data:
            raise ConnectionError("代理拒绝 CONNECT")
        return _exchange_tcp(sock, packet)


def _query_udp(server: str, packet: bytes) -> bytes:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(_QUERY_TIMEOUT)
        sock.sendto(packet, (server, 53))
        return sock.recvfrom(4096)[0]


# ---------------------------------------------------------------------------
# 上游 DNS 服务器与本机代理发现
# ---------------------------------------------------------------------------


def _usable_dns_server(value: str) -> str | None:
    try:
        ip = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if ip.version != 4 or ip in FAKE_IP_NETWORK:
        return None
    if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast:
        return None
    return str(ip)


def _windows_dns_servers() -> list[str]:
    import winreg

    root = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
    found: list[str] = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root) as interfaces:
            for index in range(winreg.QueryInfoKey(interfaces)[0]):
                with winreg.OpenKey(interfaces, winreg.EnumKey(interfaces, index)) as iface:
                    for name in ("NameServer", "DhcpNameServer"):
                        try:
                            value, _ = winreg.QueryValueEx(iface, name)
                        except OSError:
                            continue
                        found.extend(str(value).replace(",", " ").split())
    except OSError:
        return []
    return found


def _resolv_conf_servers() -> list[str]:
    try:
        with open("/etc/resolv.conf", encoding="utf-8", errors="ignore") as fh:
            return [line.split()[1] for line in fh if line.startswith("nameserver") and len(line.split()) > 1]
    except OSError:
        return []


def upstream_dns_servers() -> tuple[str, ...]:
    raw = _split(settings.LLM_UPSTREAM_DNS_SERVERS)
    if not raw:
        raw = _windows_dns_servers() if sys.platform == "win32" else _resolv_conf_servers()
    servers: list[str] = []
    for value in raw:
        server = _usable_dns_server(value)
        if server and server not in servers:
            servers.append(server)
    return tuple(servers[:_MAX_SERVERS])


def _loopback_http_proxy(value: str) -> tuple[str, int] | None:
    text = str(value or "").strip()
    if not text:
        return None
    parts = urlsplit(text if "://" in text else f"http://{text}")
    if parts.scheme.lower() != "http":
        return None
    host = (parts.hostname or "").lower()
    host = "127.0.0.1" if host == "localhost" else host
    try:
        if not ipaddress.ip_address(host).is_loopback:
            return None
        return host, parts.port or 80
    except ValueError:
        return None


def _wininet_proxy_values() -> list[str]:
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "ProxyServer")
    except OSError:
        return []
    values: list[str] = []
    for part in str(value).split(";"):
        scheme, sep, address = part.strip().partition("=")
        if not sep:
            values.append(scheme)
        elif scheme.strip().lower() in ("http", "https"):
            values.append(address)
    return values


def local_proxies() -> tuple[tuple[str, int], ...]:
    """只接受环回地址的 HTTP 代理：DNS 查询内容不发往任何远端代理。"""
    raw = [settings.LLM_UPSTREAM_DNS_PROXY] if settings.LLM_UPSTREAM_DNS_PROXY else []
    if not raw:
        raw = [os.environ.get(name, "") for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy")]
        if sys.platform == "win32":
            raw += _wininet_proxy_values()
    proxies: list[tuple[str, int]] = []
    for value in raw:
        proxy = _loopback_http_proxy(value)
        if proxy and proxy not in proxies:
            proxies.append(proxy)
    return tuple(proxies)


# ---------------------------------------------------------------------------
# 发现主流程
# ---------------------------------------------------------------------------


def _discover_blocking(
    host: str, servers: tuple[str, ...], proxies: tuple[tuple[str, int], ...]
) -> DiscoveryOutcome:
    deadline = time.monotonic() + _DISCOVERY_BUDGET
    authoritative_miss = False
    for server in servers:
        qid, packet = _encode_query(host)
        # TCP 直连在 strict-route 下会立即被拒（WinError 10013），代理隧道随后补上；UDP 放最后（被拦时要等超时）。
        attempts: list[tuple[str, Callable[[], bytes]]] = [("tcp", lambda s=server: _query_tcp(s, packet))]
        attempts += [("proxy", lambda p=proxy, s=server: _query_via_proxy(p, s, packet)) for proxy in proxies]
        attempts.append(("udp", lambda s=server: _query_udp(s, packet)))
        for via, attempt in attempts:
            if time.monotonic() >= deadline:
                break
            try:
                status, records = _decode_answer(attempt(), qid)
            except (OSError, ValueError, ConnectionError):
                continue
            real = tuple(dict.fromkeys(ip for ip, _ in records if not is_fake_ip(ip)))
            if status == "found" and real:
                ttl = max(_MIN_TTL, min(_MAX_TTL, min(t for _, t in records)))
                return DiscoveryOutcome(host, real, "found", servers, via, time.monotonic() + ttl)
            if status in ("nxdomain", "nodata"):
                authoritative_miss = True
                break  # 该服务器已明确回答，不再换传输方式
    status = "nxdomain" if authoritative_miss else "unreachable"
    return DiscoveryOutcome(host, (), status, servers, "", time.monotonic() + _NEGATIVE_TTL)


async def discover_real_address(host: str) -> DiscoveryOutcome:
    """绕过本机代理 DNS 取真实地址；结果按域名缓存（成功 30~300s、失败 30s）。"""
    key = host.lower()
    cached = _cache.get(key)
    if cached and cached.expires_at > time.monotonic():
        return cached
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        cached = _cache.get(key)
        if cached and cached.expires_at > time.monotonic():
            return cached
        override = host_override(key)
        if override:
            outcome = DiscoveryOutcome(key, (override,), "override", (), "override", time.monotonic() + _MAX_TTL)
        else:
            servers = upstream_dns_servers()
            if not servers:
                outcome = DiscoveryOutcome(key, (), "no_servers", (), "", time.monotonic() + _NEGATIVE_TTL)
            else:
                outcome = await asyncio.to_thread(_discover_blocking, key, servers, local_proxies())
        _cache[key] = outcome
        return outcome


# ---------------------------------------------------------------------------
# 钉选地址的 HTTP 传输
# ---------------------------------------------------------------------------


class _PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, pins: Mapping[str, str]):
        self._pins = {name.lower(): address for name, address in pins.items()}
        self._inner = httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        return await self._inner.connect_tcp(
            self._pins.get(host.lower(), host), port,
            timeout=timeout, local_address=local_address, socket_options=socket_options,
        )

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        return await self._inner.connect_unix_socket(path, timeout=timeout, socket_options=socket_options)

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class PinnedAddressTransport(httpx.AsyncHTTPTransport):
    """只把 TCP 连接改投到已校验的地址；URL、Host 头、TLS SNI 与证书校验仍按原域名。"""

    def __init__(self, pins: Mapping[str, str], *, verify: ssl.SSLContext | bool = True):
        super().__init__(verify=verify, trust_env=False)
        # httpx 不暴露 network_backend：按其默认连接池参数重建一份，只替换网络后端。
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(verify=verify, trust_env=False),
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=5.0,
            network_backend=_PinnedNetworkBackend(pins),
        )
