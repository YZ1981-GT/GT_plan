"""本机代理 fake-IP 兼容解析（ADR-LLM-015）与 OCR 连接测试图（ADR-LLM-016）。

现场（2026-10-19，Mesl/mihomo TUN + strict-route）：后端进程直连公司 DNS 被拦（TCP WinError 10013、
UDP 超时），只有经本机代理 HTTP CONNECT 到公司 DNS:53 的 DNS-over-TCP 能拿到真实地址。
这里全部离线：DNS 服务器与代理用本机回环上的假服务模拟，不发任何外部请求。
"""

from __future__ import annotations

import socket
import struct
import threading
import time
from unittest.mock import AsyncMock, MagicMock

import httpcore
import httpx
import pytest

from app.core.config import settings
from app.models.ai_models import AIProvider
from app.services import endpoint_dns_compat as compat
from app.services.endpoint_dns_compat import DiscoveryOutcome, PinnedAddressTransport
from app.services.llm_provider_registry import provider_profile

HOST = "ai.gt-china.com.cn"
ENTERPRISE = "https://ai.gt-china.com.cn:10010/v1"


@pytest.fixture(autouse=True)
def _isolate_cache():
    compat.clear_cache()
    yield
    compat.clear_cache()


# ---------------------------------------------------------------------------
# 回环上的假 CONNECT 代理：完成 CONNECT 后自己充当 DNS 服务器回答
# ---------------------------------------------------------------------------


def _recv_exact(conn: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = conn.recv(size - len(data))
        if not chunk:
            raise ConnectionError("eof")
        data += chunk
    return data


def _dns_response(query: bytes, ip: str | None, rcode: int, ttl: int) -> bytes:
    header = query[:2] + struct.pack(">HHHHH", 0x8180 | rcode, 1, 1 if ip else 0, 0, 0)
    answer = struct.pack(">HHHIH", 0xC00C, 1, 1, ttl, 4) + socket.inet_aton(ip) if ip else b""
    return header + query[12:] + answer


class _FakeConnectProxy:
    def __init__(self, *, answer_ip: str | None = "192.168.0.41", rcode: int = 0,
                 ttl: int = 3600, status: bytes = b"200 Connection established",
                 answer_even_if_refused: bool = False):
        self.answer_ip, self.rcode, self.ttl, self.status = answer_ip, rcode, ttl, status
        # 拒绝 CONNECT 后仍回 DNS 应答：只有「检查状态行」能挡住，用来钉死该校验。
        self.answer_even_if_refused = answer_even_if_refused
        self.targets: list[str] = []
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self.address = self._sock.getsockname()
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            with conn:
                try:
                    conn.settimeout(5)
                    head = b""
                    while b"\r\n\r\n" not in head:
                        head += conn.recv(1024)
                    self.targets.append(head.split(b" ")[1].decode("ascii"))
                    conn.sendall(b"HTTP/1.1 " + self.status + b"\r\n\r\n")
                    if not self.status.startswith(b"200") and not self.answer_even_if_refused:
                        continue
                    query = _recv_exact(conn, struct.unpack(">H", _recv_exact(conn, 2))[0])
                    response = _dns_response(query, self.answer_ip, self.rcode, self.ttl)
                    conn.sendall(struct.pack(">H", len(response)) + response)
                except (OSError, ConnectionError):
                    continue

    def close(self) -> None:
        self._sock.close()


@pytest.fixture
def proxy_factory():
    created: list[_FakeConnectProxy] = []

    def make(**kwargs) -> _FakeConnectProxy:
        proxy = _FakeConnectProxy(**kwargs)
        created.append(proxy)
        return proxy

    yield make
    for proxy in created:
        proxy.close()


@pytest.fixture
def strict_route(monkeypatch):
    """模拟 strict-route：直连 DNS 的 TCP 立即被拒、UDP 超时。"""
    def blocked(*args, **kwargs):
        raise PermissionError(10013, "blocked by strict-route")

    def timed_out(*args, **kwargs):
        raise TimeoutError("udp dropped")

    monkeypatch.setattr(compat, "_query_tcp", blocked)
    monkeypatch.setattr(compat, "_query_udp", timed_out)


# ---------------------------------------------------------------------------
# 发现流程
# ---------------------------------------------------------------------------


def test_proxy_tunnel_recovers_real_address_when_direct_dns_is_blocked(strict_route, proxy_factory):
    proxy = proxy_factory()
    outcome = compat._discover_blocking(HOST, ("192.168.0.102",), (proxy.address,))
    assert outcome.status == "found"
    assert outcome.addresses == ("192.168.0.41",)
    assert outcome.via == "proxy"
    assert proxy.targets == ["192.168.0.102:53"]
    # 记录 TTL 3600 夹到上限 300s。
    assert 290 < outcome.expires_at - time.monotonic() <= 300


@pytest.mark.parametrize(
    ("answer_ip", "rcode", "status"),
    [(None, 3, "nxdomain"), ("198.18.0.5", 0, "unreachable")],
)
def test_nxdomain_and_fake_ip_answers_never_yield_an_address(
    strict_route, proxy_factory, answer_ip, rcode, status
):
    proxy = proxy_factory(answer_ip=answer_ip, rcode=rcode)
    outcome = compat._discover_blocking(HOST, ("192.168.0.102",), (proxy.address,))
    assert outcome.addresses == ()
    assert outcome.status == status


def test_proxy_refusing_connect_is_not_trusted(strict_route, proxy_factory):
    proxy = proxy_factory(status=b"403 Forbidden", answer_even_if_refused=True)
    outcome = compat._discover_blocking(HOST, ("192.168.0.102",), (proxy.address,))
    assert (outcome.status, outcome.addresses) == ("unreachable", ())


@pytest.mark.asyncio
async def test_discovery_is_cached_per_host(strict_route, proxy_factory, monkeypatch):
    proxy = proxy_factory()
    monkeypatch.setattr(compat, "upstream_dns_servers", lambda: ("192.168.0.102",))
    monkeypatch.setattr(compat, "local_proxies", lambda: (proxy.address,))
    first = await compat.discover_real_address(HOST)
    second = await compat.discover_real_address(HOST.upper())
    assert first.addresses == second.addresses == ("192.168.0.41",)
    assert len(proxy.targets) == 1, "缓存期内不得重复查询"


@pytest.mark.asyncio
async def test_explicit_override_wins_without_touching_the_network(monkeypatch):
    monkeypatch.setattr(settings, "LLM_ENDPOINT_HOST_OVERRIDES", f"other.example=10.0.0.9, {HOST}=192.168.0.41")
    monkeypatch.setattr(compat, "upstream_dns_servers", MagicMock(side_effect=AssertionError("不应查询 DNS")))
    outcome = await compat.discover_real_address(HOST)
    assert (outcome.status, outcome.addresses, outcome.via) == ("override", ("192.168.0.41",), "override")


def test_upstream_servers_and_proxies_are_filtered(monkeypatch):
    monkeypatch.setattr(
        settings, "LLM_UPSTREAM_DNS_SERVERS",
        "198.18.0.2, 127.0.0.1, 192.168.0.102, 192.168.0.102, 169.254.1.1, ::1, 10.0.0.53",
    )
    assert compat.upstream_dns_servers() == ("192.168.0.102", "10.0.0.53")
    assert compat._loopback_http_proxy("http://127.0.0.1:7897") == ("127.0.0.1", 7897)
    assert compat._loopback_http_proxy("localhost:7890") == ("127.0.0.1", 7890)
    # DNS 查询内容不得发往远端代理或非 HTTP 代理。
    assert compat._loopback_http_proxy("http://10.0.0.1:8080") is None
    assert compat._loopback_http_proxy("socks5://127.0.0.1:7891") is None


# ---------------------------------------------------------------------------
# endpoint policy：触发条件与复核
# ---------------------------------------------------------------------------


def _resolve_to(*addresses: str):
    return lambda *args, **kwargs: [(2, 1, 6, "", (address, 443)) for address in addresses]


def _found(*addresses: str) -> AsyncMock:
    return AsyncMock(return_value=DiscoveryOutcome(HOST, addresses, "found", ("192.168.0.102",), "proxy"))


@pytest.mark.asyncio
async def test_allowlisted_endpoint_on_fake_ip_is_pinned_to_the_discovered_address(monkeypatch):
    from app.services import llm_endpoint_policy as policy

    monkeypatch.setattr(policy.socket, "getaddrinfo", _resolve_to("198.18.0.224"))
    discover = _found("192.168.0.41")
    monkeypatch.setattr(policy, "discover_real_address", discover)
    safe = await policy.resolve_endpoint(ENTERPRISE, provider_profile(AIProvider.custom))
    assert (safe.url, safe.host, safe.pinned_address, safe.pinned_via) == (
        ENTERPRISE, HOST, "192.168.0.41", "proxy",
    )
    assert isinstance(safe.transport(), PinnedAddressTransport)
    discover.assert_awaited_once_with(HOST)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "provider", "addresses", "compat_on"),
    [
        # 非 allowlist 端点：即使是 fake-IP 也不走兼容（仍由原策略拒绝）。
        ("https://untrusted.example:10010/v1", AIProvider.custom, ("198.18.0.9",), True),
        # 系统 DNS 给出真实地址：保持系统 DNS。
        (ENTERPRISE, AIProvider.custom, ("192.168.0.41",), True),
        # 部分 fake 部分真实：不算被劫持。
        (ENTERPRISE, AIProvider.custom, ("198.18.0.224", "192.168.0.41"), True),
        # 总开关关闭。
        (ENTERPRISE, AIProvider.custom, ("198.18.0.224",), False),
    ],
)
async def test_compat_is_not_triggered_outside_its_scope(monkeypatch, endpoint, provider, addresses, compat_on):
    from app.services import llm_endpoint_policy as policy

    monkeypatch.setattr(settings, "LLM_FAKE_IP_COMPAT", compat_on)
    monkeypatch.setattr(settings, "LLM_ENDPOINT_ALLOWLIST", "")
    monkeypatch.setattr(policy.socket, "getaddrinfo", _resolve_to(*addresses))
    discover = _found("192.168.0.41")
    monkeypatch.setattr(policy, "discover_real_address", discover)
    try:
        safe = await policy.resolve_endpoint(endpoint, provider_profile(provider))
        assert safe.pinned_address is None
    except policy.LLMEndpointPolicyError:
        pass  # 非 allowlist 的 fake-IP 仍按原策略拒绝
    discover.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["169.254.169.254", "127.0.0.1", "0.0.0.0"])
async def test_discovered_address_still_passes_the_ip_policy(monkeypatch, bad):
    from app.services import llm_endpoint_policy as policy

    monkeypatch.setattr(policy.socket, "getaddrinfo", _resolve_to("198.18.0.224"))
    monkeypatch.setattr(policy, "discover_real_address", _found(bad))
    with pytest.raises(policy.LLMEndpointPolicyError):
        await policy.resolve_endpoint(ENTERPRISE, provider_profile(AIProvider.custom))


@pytest.mark.asyncio
async def test_failed_discovery_keeps_previous_behaviour(monkeypatch):
    from app.services import llm_endpoint_policy as policy

    monkeypatch.setattr(policy.socket, "getaddrinfo", _resolve_to("198.18.0.224"))
    monkeypatch.setattr(policy, "discover_real_address", AsyncMock(
        return_value=DiscoveryOutcome(HOST, (), "unreachable", ("192.168.0.102",))
    ))
    safe = await policy.resolve_endpoint(ENTERPRISE, provider_profile(AIProvider.custom))
    assert safe.pinned_address is None and safe.transport() is None


@pytest.mark.asyncio
async def test_nxdomain_on_system_dns_can_still_be_rescued(monkeypatch):
    from app.services import llm_endpoint_policy as policy

    def nxdomain(*args, **kwargs):
        raise socket.gaierror(11001, "getaddrinfo failed")

    monkeypatch.setattr(policy.socket, "getaddrinfo", nxdomain)
    monkeypatch.setattr(policy, "discover_real_address", _found("192.168.0.41"))
    safe = await policy.resolve_endpoint(ENTERPRISE, provider_profile(AIProvider.custom))
    assert safe.pinned_address == "192.168.0.41"
    monkeypatch.setattr(policy, "discover_real_address", AsyncMock(
        return_value=DiscoveryOutcome(HOST, (), "nxdomain", ("192.168.0.102",))
    ))
    with pytest.raises(policy.LLMEndpointPolicyError, match="DNS 解析失败"):
        await policy.resolve_endpoint(ENTERPRISE, provider_profile(AIProvider.custom))


# ---------------------------------------------------------------------------
# 钉选传输：TCP 改投，SNI / Host 仍按域名
# ---------------------------------------------------------------------------


class _RecordingStream(httpcore.AsyncNetworkStream):
    def __init__(self, record: dict, response: bytes):
        self._record, self._chunks = record, [response]

    async def read(self, max_bytes, timeout=None):
        return self._chunks.pop(0) if self._chunks else b""

    async def write(self, buffer, timeout=None):
        self._record["written"] = self._record.get("written", b"") + buffer

    async def aclose(self):
        return None

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        self._record["server_hostname"] = server_hostname
        return self

    def get_extra_info(self, info):
        return None


class _RecordingBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, record: dict, response: bytes):
        self._record, self._response = record, response

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self._record["connect"] = (host, port)
        return _RecordingStream(self._record, self._response)

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise NotImplementedError

    async def sleep(self, seconds):
        return None


@pytest.mark.asyncio
async def test_pinned_transport_redirects_tcp_but_keeps_sni_and_host(monkeypatch):
    record: dict = {}
    response = b"HTTP/1.1 401 Unauthorized\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}"
    monkeypatch.setattr(compat.httpcore, "AnyIOBackend", lambda: _RecordingBackend(record, response))
    transport = PinnedAddressTransport({HOST: "192.168.0.41"})
    async with httpx.AsyncClient(transport=transport) as client:
        resp = await client.get(f"https://{HOST}:10010/v1/models")
    assert resp.status_code == 401
    assert record["connect"] == ("192.168.0.41", 10010)
    # 证书校验依赖 SNI = 原域名；Host 头不变，网关按域名路由。
    assert record["server_hostname"] == HOST
    assert f"Host: {HOST}:10010".encode() in record["written"]


@pytest.mark.asyncio
async def test_llm_and_ocr_clients_use_the_pinned_transport(monkeypatch):
    from app.services import llm_runtime, remote_ocr_runtime as remote
    from app.services.llm_endpoint_policy import SafeEndpoint

    pinned = SafeEndpoint(ENTERPRISE, HOST, "192.168.0.41", "proxy")
    monkeypatch.setattr(llm_runtime, "resolve_endpoint", AsyncMock(return_value=pinned))
    captured = MagicMock()
    monkeypatch.setattr(llm_runtime.httpx, "AsyncClient", captured)
    config = llm_runtime.ResolvedLLMConfig(
        model_name="qwen3.8", model_type=llm_runtime.AIModelType.chat, provider=AIProvider.custom,
        endpoint_url=ENTERPRISE, api_key=None, profile=provider_profile(AIProvider.custom), source="test",
    )
    await llm_runtime.build_runtime_client(config, timeout=5.0)
    kwargs = captured.call_args.kwargs
    assert isinstance(kwargs["transport"], PinnedAddressTransport)
    assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False

    seen: dict = {}

    class _Client:
        def __init__(self, *args, **kw):
            seen.update(kw)

        async def __aenter__(self):
            raise httpx.ConnectError("stop after capture")

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(remote, "resolve_endpoint", AsyncMock(return_value=SafeEndpoint(
        "https://ai.gt-china.com.cn:10080", HOST, "192.168.0.41", "proxy",
    )))
    monkeypatch.setattr(remote.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(remote, "describe_network_failure", AsyncMock(return_value="x"))
    ocr_config = remote.RemoteOCRConfig(
        model_id=None, model_name="paddleocrv6", capability="ocr", protocol="paddlex_json",
        endpoint_url="https://ai.gt-china.com.cn:10080", api_path="/ocr", auth_scheme="none",
        auth_header_name=None, api_key=None, timeout_seconds=60,
    )
    with pytest.raises(remote.RemoteOCRRuntimeError):
        await remote.recognize_remote_bytes(ocr_config, remote._TEST_PNG, filename="t.png")
    assert isinstance(seen["transport"], PinnedAddressTransport)


# ---------------------------------------------------------------------------
# 诊断文案与 OCR 测试图
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (DiscoveryOutcome(HOST, (), "nxdomain", ("192.168.0.102",)), "可能不在公司内网"),
        (DiscoveryOutcome(HOST, (), "unreachable", ("192.168.0.102",)), "LLM_ENDPOINT_HOST_OVERRIDES"),
        (DiscoveryOutcome(HOST, ("192.168.0.41",), "found", (), "proxy"), "已绕过本机代理 DNS 直连 192.168.0.41"),
    ],
)
async def test_failure_message_reflects_the_discovery_outcome(monkeypatch, outcome, expected):
    import ssl

    from app.services import llm_endpoint_policy as policy

    monkeypatch.setattr(policy.socket, "getaddrinfo", _resolve_to("198.18.0.224"))
    monkeypatch.setattr(policy, "last_outcome", lambda host: outcome)
    try:
        raise ssl.SSLEOFError(8, "EOF")
    except ssl.SSLError as inner:
        try:
            raise httpx.ConnectError("x") from inner
        except httpx.ConnectError as exc:
            text = await policy.describe_network_failure(ENTERPRISE, exc)
    assert text.startswith("TLS 握手被中断")
    assert expected in text


def test_ocr_connection_test_image_is_a_real_text_image():
    from app.services.remote_ocr_runtime import _TEST_PNG

    assert _TEST_PNG[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", _TEST_PNG[16:24])
    # PaddleX 对 1x1 PNG 回 422 Invalid input file；240x64 文字图两条企业 OCR 均能识别。
    assert (width, height) == (240, 64)
