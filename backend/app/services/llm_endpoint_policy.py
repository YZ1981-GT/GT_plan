"""LLM endpoint 出站策略：保存时校验结构，调用前复核 DNS/IP。"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from urllib.parse import urlsplit

import anyio
import httpx

from app.core.config import settings
from app.services.ai_model_presets import BUILTIN_TRUSTED_ENDPOINTS
from app.services.endpoint_dns_compat import (
    PinnedAddressTransport,
    discover_real_address,
    is_fake_ip,
    last_outcome,
)
from app.services.llm_provider_registry import ProviderProfile


class LLMEndpointPolicyError(ValueError):
    """endpoint 不满足出站安全策略。"""


@dataclass(frozen=True)
class SafeEndpoint:
    """出站前复核通过的 endpoint；pinned_address 非空表示 TCP 连接需改投到该地址。"""

    url: str
    host: str
    pinned_address: str | None = None
    pinned_via: str = ""

    def transport(self) -> httpx.AsyncBaseTransport | None:
        if not self.pinned_address:
            return None
        return PinnedAddressTransport({self.host: self.pinned_address})


def _port(parts) -> int:
    try:
        return parts.port or (443 if parts.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise LLMEndpointPolicyError("模型端点端口非法") from exc


def _normalized_allowlist() -> tuple[str, ...]:
    # 企业预设仅放行精确 base URL；环境 allowlist 用于其他部署私网端点。
    values = [item.rstrip("/") for item in BUILTIN_TRUSTED_ENDPOINTS]
    for raw in str(settings.LLM_ENDPOINT_ALLOWLIST or "").replace(";", ",").split(","):
        item = raw.strip().rstrip("/")
        if item:
            values.append(item)
    return tuple(values)


def _matches_allowlist(endpoint: str) -> bool:
    target = urlsplit(endpoint)
    target_port = _port(target)
    target_path = (target.path or "/").rstrip("/")
    for item in _normalized_allowlist():
        allowed = urlsplit(item)
        if (
            target.scheme.lower() == allowed.scheme.lower()
            and (target.hostname or "").lower() == (allowed.hostname or "").lower()
            and target_port == _port(allowed)
        ):
            prefix = (allowed.path or "/").rstrip("/")
            if target_path == prefix or target_path.startswith(prefix + "/"):
                return True
    return False


def validate_endpoint_structure(endpoint: str, profile: ProviderProfile) -> str:
    """校验 URL 结构和 provider host/path 约束，返回去尾斜杠的规范值。"""
    value = str(endpoint or profile.default_endpoint or "").strip().rstrip("/")
    if not value:
        raise LLMEndpointPolicyError("该提供商必须填写模型端点")
    parts = urlsplit(value)
    scheme = (parts.scheme or "").lower()
    host = (parts.hostname or "").lower()
    if scheme not in {"http", "https"} or not host:
        raise LLMEndpointPolicyError("模型端点必须是有效的 http/https URL")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise LLMEndpointPolicyError("模型端点不得包含账号、密码、query 或 fragment")
    _port(parts)

    if profile.official_hosts or profile.official_host_suffixes:
        official_match = host in profile.official_hosts or any(
            host.endswith(suffix) and host != suffix.lstrip(".")
            for suffix in profile.official_host_suffixes
        )
        if not official_match:
            raise LLMEndpointPolicyError("该提供商只能使用官方 API 域名")
    if profile.expected_path_prefix and not (parts.path or "").startswith(
        profile.expected_path_prefix
    ):
        raise LLMEndpointPolicyError(
            f"该提供商端点路径必须以 {profile.expected_path_prefix} 开头"
        )

    allowlisted = _matches_allowlist(value)
    literal = None
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    is_loopback_name = host == "localhost" or bool(literal and literal.is_loopback)
    if is_loopback_name and not (profile.allow_loopback or allowlisted):
        raise LLMEndpointPolicyError("该提供商不允许访问本机环回端点")
    if scheme != "https" and not (is_loopback_name or allowlisted):
        raise LLMEndpointPolicyError("非本机模型端点必须使用 HTTPS")
    if not (
        profile.official_hosts
        or profile.official_host_suffixes
        or profile.allow_public_custom_host
        or profile.allow_loopback
        or allowlisted
    ):
        raise LLMEndpointPolicyError("模型端点不在服务端允许范围内")
    return value


def _assert_address_allowed(address: str, *, allow_private: bool, allow_loopback: bool) -> None:
    ip = ipaddress.ip_address(address)
    # IPv6 ::1 在部分 Python 版本同时被标记为 is_reserved；已明确允许的 loopback
    # 必须先单独裁决，否则本地 vLLM/Ollama 会被 reserved 分支误拒。
    if ip.is_loopback:
        if allow_loopback:
            return
        raise LLMEndpointPolicyError("模型端点解析到未经允许的环回地址")
    if ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        # metadata/link-local、多播、未指定地址即使写进 allowlist 也不得放行。
        raise LLMEndpointPolicyError("模型端点解析到禁止的网络地址")
    if ip.is_reserved and not allow_private:
        # 198.18/15 等 VPN/TUN fake-IP 只允许经精确 endpoint allowlist 放行。
        raise LLMEndpointPolicyError("模型端点解析到未经 allowlist 放行的保留地址")
    if ip.is_private and not allow_private:
        raise LLMEndpointPolicyError("模型端点解析到未经 allowlist 放行的私网地址")


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


async def resolve_endpoint(endpoint: str, profile: ProviderProfile) -> SafeEndpoint:
    """出站前解析 DNS 并逐地址复核；任何一个危险地址都会 fail-closed。

    allowlist 端点被本机代理解析成 fake-IP（或解析失败）时，改用绕过代理 DNS 得到的
    真实地址（ADR-LLM-015）；发现的地址同样逐个复核，且连接时 SNI/证书仍按域名。
    """
    value = validate_endpoint_structure(endpoint, profile)
    parts = urlsplit(value)
    host = parts.hostname or ""
    allowlisted = _matches_allowlist(value)
    loopback_allowed = profile.allow_loopback or allowlisted

    resolve_error: OSError | None = None
    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo, host, _port(parts), 0, socket.SOCK_STREAM
        )
        addresses = {item[4][0] for item in infos if item and item[4]}
    except OSError as exc:
        addresses, resolve_error = set(), exc

    hijacked = not addresses or all(is_fake_ip(address) for address in addresses)
    if allowlisted and settings.LLM_FAKE_IP_COMPAT and hijacked and not _is_ip_literal(host):
        outcome = await discover_real_address(host)
        if outcome.addresses:
            for address in outcome.addresses:
                # 发现的地址不得是环回：fake-IP 兼容只用于改投到真实的远端服务。
                _assert_address_allowed(address, allow_private=True, allow_loopback=False)
            return SafeEndpoint(value, host, outcome.addresses[0], outcome.via)

    if resolve_error is not None:
        raise LLMEndpointPolicyError("模型端点 DNS 解析失败") from resolve_error
    if not addresses:
        raise LLMEndpointPolicyError("模型端点 DNS 未返回地址")
    for address in addresses:
        _assert_address_allowed(
            address,
            allow_private=allowlisted,
            allow_loopback=loopback_allowed,
        )
    return SafeEndpoint(value, host)


async def assert_endpoint_safe(endpoint: str, profile: ProviderProfile) -> str:
    """兼容旧调用方：只返回复核后的 URL。需要真正出站的调用方应使用 resolve_endpoint。"""
    return (await resolve_endpoint(endpoint, profile)).url


def _exception_chain(exc: BaseException, limit: int = 8) -> list[BaseException]:
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in chain and len(chain) < limit:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


async def _fake_ip_addresses(endpoint: str) -> list[str]:
    host = urlsplit(endpoint).hostname or ""
    if not host:
        return []
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None, 0, socket.SOCK_STREAM)
    except OSError:
        return []
    hits: set[str] = set()
    for item in infos:
        try:
            if is_fake_ip(item[4][0]):
                hits.add(item[4][0])
        except (IndexError, TypeError):
            continue
    return sorted(hits)


async def describe_network_failure(endpoint: str, exc: BaseException) -> str:
    """把出站失败归类成可安全展示的中文原因（不含上游正文、请求头或密钥）。

    2026-10-19 实测：企业域名只在公司内网 DNS 可解析，本机代理 TUN 用 fake-IP
    （198.18.x.x）先接下 TCP，再用公网 DNS 解析失败后直接关连接；客户端只看到
    TLS 握手 EOF。只报「端点不可达」会让用户误以为是 Key 或模型名错了。
    """
    chain = _exception_chain(exc)

    def seen(*types: type[BaseException]) -> bool:
        return any(isinstance(item, types) for item in chain)

    if seen(ssl.SSLCertVerificationError):
        return "TLS 证书校验失败（证书不受信任或与域名不匹配）"
    if seen(ssl.SSLError):
        reason = "TLS 握手被中断"
    elif seen(ConnectionRefusedError):
        reason = "连接被拒绝（端口未监听）"
    elif seen(ConnectionResetError, ConnectionAbortedError, BrokenPipeError, anyio.BrokenResourceError):
        # 同一代理故障在不同时刻会表现为 RST 而非 TLS EOF（2026-10-19 实测两种都出现）。
        reason = "连接被对端重置"
    elif seen(anyio.EndOfStream, httpx.RemoteProtocolError):
        reason = "连接被对端提前关闭"
    elif seen(socket.gaierror):
        reason = "域名解析失败"
    elif seen(TimeoutError):
        reason = "连接超时"
    else:
        reason = "网络连接失败"
    fake_ips = await _fake_ip_addresses(endpoint)
    if not fake_ips:
        return reason
    outcome = last_outcome(urlsplit(endpoint).hostname or "")
    if outcome and outcome.addresses:
        # 兼容层已绕过代理 DNS 改投真实地址，失败与代理 DNS 无关。
        return f"{reason}（已绕过本机代理 DNS 直连 {outcome.addresses[0]}，仍然失败）"
    reason += f"。该域名被本机代理/VPN 解析为 fake-IP {', '.join(fake_ips)}"
    if outcome and outcome.status == "nxdomain":
        servers = "、".join(outcome.servers) or "本机网卡 DNS"
        return reason + (
            f"，公司 DNS（{servers}）也没有该域名的记录：当前网络可能不在公司内网，"
            "企业模型只能在公司网络或 VPN 下使用"
        )
    if outcome and outcome.status in ("unreachable", "no_servers"):
        return reason + (
            "，且绕过代理查询本机网卡 DNS 未成功。可在服务端 .env 设置 "
            "LLM_ENDPOINT_HOST_OVERRIDES=<域名>=<内网地址>，或在代理中把该域名设为直连并交给公司内网 DNS 解析"
        )
    return reason + (
        "，连接经代理转发后被关闭，常见原因是代理的 DNS 解析不到企业内网域名。"
        "请在代理中将该域名设为直连并交给公司内网 DNS 解析，或关闭 TUN 模式后重试"
    )
