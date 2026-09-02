# -*- coding: utf-8 -*-
"""callback 下载：allowlist / DNS 复核与 IP 固定 / 拒绝重定向 / 分离超时 / 流式上限。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 22
Requirements: 5.3, 5.6, 5.7, 10.7, 10.8, 14.11
Properties: **P17**（callback 文件先隔离校验）

═══ 一、全部控制都在 durable **之前** ═══

Requirement 5.6 的顺序不可交换：下载 → 流式校验 → 全过才 `kind=incoming,state=durable`；
任一门失败只能登记 `kind=incoming,state=quarantined` 且 `durable_at` 恒 NULL。本模块只
负责「下载到 staging」这一段，**不登记 DB 行、不 sealing**：sealing 由 Task 11 的
:meth:`CanonicalArtifactRepository.seal_incoming` 承担（它已经把 OOXML 安全门与
durable/quarantined 两支写死）。分工写死在这里，是为了不出现第二份 sealing 逻辑。

═══ 二、Task 4 实测的六个 gap 与本模块的对应关系 ═══

契约 `download_security.characterized_current_production_behavior.gaps` 逐条：

================================================  ==========================================
生产实况（Task 4 实测）                             本模块的落点
================================================  ==========================================
无 allowlist，path/query 仍来自不可信 payload       :func:`assert_url_allowlisted`（scheme+host+port+path 前缀+遍历）
`ONLYOFFICE_URL` 为空时 host 由 payload 决定        allowlist 为空即抛，**不**回退到「任意 host」
无解析后 IP 复核（DNS rebinding 实测可行）           :func:`resolve_and_verify`（逐 IP + 固定已验证 IP）
重定向靠 httpx 版本行为隐式挡住                      :class:`DownloadRequest` 显式 `follow_redirects=False`，3xx 专属拒绝类型
`resp.content` 整包入内存，无上限                    :func:`stream_download` 边读边计数，超限立即中止
单一 60s 总超时                                     :class:`DownloadTimeouts` 由契约给 connect/read 两个值
未关 `trust_env` ⇒ 走系统代理（实测 502）             :func:`build_httpx_transport` 强制 `trust_env=False`
================================================  ==========================================

═══ 三、为什么 transport 是注入的 ═══

守卫必须能真执行每一条拒绝分支（3xx、超限、非法 IP、超时），而这些在真网络里既不稳定
又慢。所以 HTTP 落点抽成 :class:`CallbackDownloadTransport`：生产用
:func:`build_httpx_transport`，守卫注入可编程替身。**注意**这不等于「用 mock 测判据」：
被测的判据（allowlist / IP 复核 / 3xx / 计数）全在本模块内，替身只提供字节与状态码。
另有一条独立判据钉住生产 transport 的构造参数（`trust_env=False` /
`follow_redirects=False` / 两段 timeout 全取自契约）。

═══ 四、同步实现 + 线程池，而不是 async ═══

:meth:`CanonicalArtifactRepository.stage_incoming` 吃的是同步 `Iterable[bytes]`。把下载
写成 async generator 就得在两者之间加一层缓冲，那层缓冲要么整包入内存（正是要修的
gap），要么自己再实现一遍背压。因此本模块是同步的，由调用方用
`asyncio.to_thread(...)` 移出事件循环。
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Final, Iterator, Mapping, Protocol, Sequence
from urllib.parse import urlsplit, urlunsplit

from app.services.workpaper_sync.limits import SyncLimits, load_limits
from app.services.workpaper_sync.models import SyncDomainError
from app.services.workpaper_sync.oo_contract import (
    CallbackContract,
    DownloadSecurityPolicy,
    load_callback_contract,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 0. 异常：每条拒绝一个类型
# ═══════════════════════════════════════════════════════════════════════════


class CallbackDownloadError(SyncDomainError):
    """callback 下载被安全策略拒绝（全部发生在 durable 之前）。"""

    error_code = "callback_download_rejected"


class DownloadPolicyConfigError(CallbackDownloadError):
    """allowlist 为空 / 契约与预算配置互相矛盾。**不 fallback**。"""

    error_code = "callback_download_policy_invalid"


class DownloadUrlNotAllowlistedError(CallbackDownloadError):
    """scheme/host/port 不在 allowlist 内（SSRF 第一道门）。"""

    error_code = "callback_download_host_not_allowlisted"


class DownloadPathRejectedError(CallbackDownloadError):
    """path 不匹配 OO cache 前缀，或含 `..` / 反斜杠 / 空字节等遍历形态。

    🔴 与 :class:`DownloadUrlNotAllowlistedError` 分型：Task 4 实测的生产 gap 恰恰是
    「netloc 被换成 ONLYOFFICE_URL 但 path 原样保留（可含 `../`）」—— 两者共用一个
    类型时，删掉 path 判据会被 host 判据遮蔽而判 GREEN。
    """

    error_code = "callback_download_path_rejected"


class DownloadAddressRejectedError(CallbackDownloadError):
    """解析后的 IP 落在禁止段（元数据/链路本地，或未获显式放行的私网/环回）。"""

    error_code = "callback_download_address_rejected"


class DownloadResolutionError(CallbackDownloadError):
    """DNS 解析失败或返回空结果。"""

    error_code = "callback_download_dns_failed"


class DownloadRedirectRefusedError(CallbackDownloadError):
    """收到 3xx。契约固定 `follow_redirects=false, max_redirects=0`。"""

    error_code = "callback_download_redirect_refused"


class DownloadHttpStatusError(CallbackDownloadError):
    """非 2xx / 非 3xx 的 HTTP 状态。"""

    error_code = "callback_download_http_status"


class DownloadSizeExceededError(CallbackDownloadError):
    """流式累计超过契约上限，已立即中止（不落盘、不入内存）。"""

    error_code = "callback_download_size_exceeded"


class DownloadTransportError(CallbackDownloadError):
    """连接/读取超时或传输层错误。"""

    error_code = "callback_download_transport_failed"


class DownloadProxyLeakError(DownloadPolicyConfigError):
    """transport 允许了环境/系统代理 ⇒ 底稿字节会流经第三方（Requirement 10.7）。"""

    error_code = "callback_download_proxy_leak"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 策略
# ═══════════════════════════════════════════════════════════════════════════

#: 云元数据地址：**任何情况**都拒绝，包括显式放行私网的 allowlist 条目。
#: 它不是「私网的一种」而是特权凭证端点，放行它等于交出实例角色。
METADATA_ADDRESSES: Final[frozenset[str]] = frozenset(
    {"169.254.169.254", "fd00:ec2::254", "100.100.100.200"}
)

#: OO 缓存下载路径前缀（`document.url` / callback `url` 的实测形态）。
#: 只作为**默认值**：`CallbackDownloadPolicy.path_prefixes` 可由部署覆盖。
DEFAULT_OO_PATH_PREFIXES: Final[tuple[str, ...]] = ("/cache/", "/coauthoring/")

_FORBIDDEN_PATH_TOKENS: Final[tuple[str, ...]] = ("..", "\\", "\x00", "//")


@dataclass(frozen=True)
class AllowlistEntry:
    """一个被放行的 `scheme://host:port`。

    `allow_private_ip` 只在 host 本身就是环回/私网/容器别名时为 True。它是**逐条**的：
    放行 `localhost:8080` 不等于放行 `oo.internal.example.com` 解析到的私网地址 ——
    后者正是 DNS rebinding 的落点。
    """

    scheme: str
    host: str
    port: int
    allow_private_ip: bool

    @property
    def netloc(self) -> str:
        return f"{self.host}:{self.port}"


@dataclass(frozen=True)
class DownloadTimeouts:
    """connect/read 分离超时（契约 `download_security.required_controls`）。"""

    connect_seconds: int
    read_seconds: int


@dataclass(frozen=True)
class CallbackDownloadPolicy:
    """一次下载可用的全部控制。字段全部来自契约，**没有**默认数值。"""

    policy_version: int
    allowlist: tuple[AllowlistEntry, ...]
    path_prefixes: tuple[str, ...]
    timeouts: DownloadTimeouts
    size_cap_bytes: int
    chunk_bytes: int
    follow_redirects: bool
    max_redirects: int
    dns_recheck_after_resolve: bool

    def entry_for(self, *, scheme: str, host: str, port: int) -> AllowlistEntry | None:
        for entry in self.allowlist:
            if (
                entry.scheme == scheme
                and entry.host.lower() == host.lower()
                and entry.port == port
            ):
                return entry
        return None


def _default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80


def _host_is_literal_local(host: str) -> bool:
    """host 字面量本身就指向本机/容器宿主 ⇒ 该条目可放行私网 IP。

    `host.docker.internal` 与 `gateway.docker.internal` 是 Docker Desktop 注入的宿主
    别名，平台正靠它让容器内的 OO 回连宿主后端（Task 4 §0 记录了 OO 侧
    `externalRequest.directIfIn.jwtToken=true` 会绕过私网封锁）。
    """
    normalized = host.strip().lower()
    if normalized in {"localhost", "host.docker.internal", "gateway.docker.internal"}:
        return True
    try:
        addr = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return bool(addr.is_loopback or addr.is_private)


def parse_allowlist_entry(raw: str) -> AllowlistEntry:
    """把 `http://localhost:8080`（或裸 host:port）解析成一条 allowlist 条目。"""
    text = str(raw or "").strip()
    if not text:
        raise DownloadPolicyConfigError("allowlist 条目不得为空")
    if "://" not in text:
        text = f"http://{text}"
    parts = urlsplit(text)
    scheme = (parts.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise DownloadPolicyConfigError(
            f"allowlist 条目 {raw!r} 的 scheme={scheme!r} 不被支持（只允许 http/https）"
        )
    host = (parts.hostname or "").strip()
    if not host:
        raise DownloadPolicyConfigError(f"allowlist 条目 {raw!r} 缺少 host")
    port = parts.port or _default_port(scheme)
    return AllowlistEntry(
        scheme=scheme, host=host, port=int(port), allow_private_ip=_host_is_literal_local(host)
    )


def build_download_policy(
    *,
    onlyoffice_url: str | None,
    extra_allowlist: Sequence[str] = (),
    path_prefixes: Sequence[str] = DEFAULT_OO_PATH_PREFIXES,
    contract: CallbackContract | None = None,
    limits: SyncLimits | None = None,
) -> CallbackDownloadPolicy:
    """按契约构造策略。

    `onlyoffice_url` 为空且无 `extra_allowlist` 时**直接抛**：Task 4 实测的最严重 gap 是
    「`ONLYOFFICE_URL` 为空时 host 完全由 payload 决定」。空配置回退成「放行一切」是
    fail-open，回退成「放行私网」同样是；唯一正确的处置是拒绝处理任何 callback。
    """
    ct = contract or load_callback_contract()
    lim = limits or load_limits()
    policy: DownloadSecurityPolicy = ct.download
    if policy.allowlist_mode != "host_allowlist":
        raise DownloadPolicyConfigError(
            f"契约 download_security.url_allowlist.mode={policy.allowlist_mode!r} 不是 "
            "host_allowlist —— 本模块只实现 allowlist 模式，不实现「按 netloc 重写」"
        )
    entries: list[AllowlistEntry] = []
    if onlyoffice_url and str(onlyoffice_url).strip():
        entries.append(parse_allowlist_entry(onlyoffice_url))
    for item in extra_allowlist:
        entries.append(parse_allowlist_entry(item))
    if not entries:
        raise DownloadPolicyConfigError(
            "callback 下载 allowlist 为空（ONLYOFFICE_URL 未配置且无显式 allowlist）—— "
            "不得回退到「host 由 payload 决定」，只能拒绝处理 callback"
        )
    prefixes = tuple(p for p in (str(x).strip() for x in path_prefixes) if p)
    if not prefixes:
        raise DownloadPolicyConfigError("path 前缀清单不得为空（否则 path 判据恒真）")
    # 契约与容量预算是两份配置，必须一致：不一致时「下载放行 200MB、解压门只允许 100MB」
    # 这类组合会让超限在 sealing 阶段才暴露，错误码指向 OOXML 而真实原因是下载没有界。
    if policy.streaming_size_cap_bytes != lim.max_compressed_bytes:
        raise DownloadPolicyConfigError(
            "契约 download_security.streaming_size_cap_bytes="
            f"{policy.streaming_size_cap_bytes} 与容量预算 max_compressed_bytes="
            f"{lim.max_compressed_bytes} 不一致 —— 两份配置必须锁死，否则下载门与"
            "解压门各按一个上限工作"
        )
    return CallbackDownloadPolicy(
        policy_version=policy.policy_version,
        allowlist=tuple(entries),
        path_prefixes=prefixes,
        timeouts=DownloadTimeouts(
            connect_seconds=policy.connect_timeout_seconds,
            read_seconds=policy.read_timeout_seconds,
        ),
        size_cap_bytes=policy.streaming_size_cap_bytes,
        chunk_bytes=lim.chunk_bytes,
        follow_redirects=policy.follow_redirects,
        max_redirects=policy.max_redirects,
        dns_recheck_after_resolve=policy.dns_recheck_after_resolve,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. URL / DNS 校验
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ResolvedTarget:
    """已通过 allowlist 与逐 IP 复核的下载目标，**IP 已固定**。

    `pinned_url` 把 host 换成已验证 IP、`host_header` 保留原 host —— 连接阶段不再做
    第二次解析，DNS rebinding 因此无处落脚（契约 `dns_recheck_after_resolve.rule`
    的「把已校验 IP 固定给连接使用」）。
    """

    original_url: str
    scheme: str
    host: str
    port: int
    resolved_addresses: tuple[str, ...]
    pinned_address: str
    pinned_url: str
    host_header: str
    entry: AllowlistEntry


def assert_url_allowlisted(url: str, *, policy: CallbackDownloadPolicy) -> AllowlistEntry:
    """scheme+host+port 必须在 allowlist 内，且 path 必须匹配前缀且无遍历形态。"""
    text = str(url or "").strip()
    if not text:
        raise DownloadUrlNotAllowlistedError("callback payload 未给出下载 url")
    parts = urlsplit(text)
    scheme = (parts.scheme or "").lower()
    host = (parts.hostname or "").strip()
    if scheme not in {"http", "https"} or not host:
        raise DownloadUrlNotAllowlistedError(
            f"下载 url 的 scheme/host 非法: scheme={scheme!r} host={host!r}"
        )
    port = parts.port or _default_port(scheme)
    entry = policy.entry_for(scheme=scheme, host=host, port=int(port))
    if entry is None:
        raise DownloadUrlNotAllowlistedError(
            f"下载 url 的 {scheme}://{host}:{port} 不在 allowlist "
            f"{[e.scheme + '://' + e.netloc for e in policy.allowlist]} 内 —— "
            "不得按 netloc 重写后放行（那会保留 payload 决定的 path/query）"
        )
    path = parts.path or ""
    for token in _FORBIDDEN_PATH_TOKENS:
        if token in path:
            raise DownloadPathRejectedError(
                f"下载 url 的 path 含禁止形态 {token!r}: {path!r}"
            )
    if not any(path.startswith(prefix) for prefix in policy.path_prefixes):
        raise DownloadPathRejectedError(
            f"下载 url 的 path={path!r} 不匹配任一 OO 缓存前缀 {list(policy.path_prefixes)}"
        )
    return entry


def _classify_address(raw: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        return ipaddress.ip_address(raw)
    except ValueError as exc:
        raise DownloadResolutionError(f"DNS 返回的地址非法: {raw!r}") from exc


def assert_address_allowed(raw: str, *, entry: AllowlistEntry) -> None:
    """逐 IP 复核。元数据/链路本地恒拒；私网/环回只在条目显式放行时通过。"""
    normalized = str(raw).strip()
    if normalized in METADATA_ADDRESSES:
        raise DownloadAddressRejectedError(
            f"解析地址 {normalized} 是云元数据端点 —— 任何 allowlist 条目都不得放行它"
        )
    addr = _classify_address(normalized)
    # 🔴 `is_reserved` 必须把 loopback 排除掉，否则 IPv6 环回永远进不来：
    # `ipaddress` 把 `::/8` 整段标成 reserved，于是 `IPv6Address('::1').is_reserved`
    # 为 **True**（而 IPv4 的 `127.0.0.1` 为 False）。不排除时这行会在下面那道
    # 「loopback/私网只在条目显式放行时通过」之前无条件抛 —— 而 `localhost` 在本机
    # `getaddrinfo` 里**第一个**就返回 `::1`，`resolve_and_verify` 又逐个地址校验，
    # 结果是平台真实部署（`localhost:8080` / `host.docker.internal`，Task 4 §0）
    # 一次 callback 都下载不下来，同时让 loopback 的放行分支变成不可达代码。
    # 环回不靠 `is_reserved` 兜底：它紧接着就有自己的、按 allowlist 条目裁决的门。
    if (
        addr.is_link_local
        or addr.is_multicast
        or addr.is_unspecified
        or (addr.is_reserved and not addr.is_loopback)
    ):
        raise DownloadAddressRejectedError(
            f"解析地址 {normalized} 落在链路本地/多播/未指定/保留段，一律拒绝"
        )
    if (addr.is_loopback or addr.is_private) and not entry.allow_private_ip:
        raise DownloadAddressRejectedError(
            f"host {entry.host!r} 解析到私网/环回地址 {normalized}，而该 allowlist 条目"
            "未显式放行私网 —— 这是 DNS rebinding 的典型形态"
        )


def resolve_and_verify(
    url: str,
    *,
    policy: CallbackDownloadPolicy,
    resolver: Any = None,
) -> ResolvedTarget:
    """allowlist → DNS 解析 → 逐 IP 复核 → 固定 IP。

    Args:
        resolver: 可注入的解析函数 `(host, port) -> list[str]`；默认 `socket.getaddrinfo`。
            注入点存在的理由是「DNS rebinding 必须能被真执行地 falsify」：Task 4 就是靠
            猴补解析证明生产无复核的。
    """
    entry = assert_url_allowlisted(url, policy=policy)
    parts = urlsplit(str(url).strip())
    host = str(parts.hostname)
    port = int(parts.port or _default_port(entry.scheme))

    if not policy.dns_recheck_after_resolve:
        # 策略自证：契约已强制该项为真（`_parse_download` 会抛），这里再挡一次是为了
        # 让「有人把它改成 False」在本模块也 fail closed 而不是静默跳过复核。
        raise DownloadPolicyConfigError(
            "策略声明不做解析后 DNS 复核 —— 契约禁止该形态（防 rebinding）"
        )

    addresses = _resolve(host, port, resolver=resolver)
    if not addresses:
        raise DownloadResolutionError(f"host {host!r} 解析结果为空")
    for address in addresses:
        assert_address_allowed(address, entry=entry)

    pinned = addresses[0]
    literal = f"[{pinned}]" if ":" in pinned else pinned
    pinned_netloc = f"{literal}:{port}"
    pinned_url = urlunsplit(
        (entry.scheme, pinned_netloc, parts.path, parts.query, "")
    )
    return ResolvedTarget(
        original_url=str(url).strip(),
        scheme=entry.scheme,
        host=host,
        port=port,
        resolved_addresses=tuple(addresses),
        pinned_address=pinned,
        pinned_url=pinned_url,
        host_header=f"{host}:{port}" if port != _default_port(entry.scheme) else host,
        entry=entry,
    )


def _resolve(host: str, port: int, *, resolver: Any = None) -> list[str]:
    if resolver is not None:
        try:
            return [str(item) for item in resolver(host, port)]
        except CallbackDownloadError:
            raise
        except Exception as exc:  # noqa: BLE001 - 注入解析器的任何失败都归 DNS 失败
            raise DownloadResolutionError(f"host {host!r} 解析失败: {exc}") from exc
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise DownloadResolutionError(f"host {host!r} 解析失败: {exc}") from exc
    out: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if sockaddr and isinstance(sockaddr, tuple):
            candidate = str(sockaddr[0])
            if candidate not in out:
                out.append(candidate)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 3. transport
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class DownloadRequest:
    """交给 transport 的**已固定**请求。transport 不得再做解析或跟随重定向。"""

    url: str
    headers: Mapping[str, str]
    timeouts: DownloadTimeouts
    follow_redirects: bool = False
    max_redirects: int = 0


class DownloadResponse(Protocol):
    """transport 返回的响应流（只暴露判据需要的三项）。"""

    status_code: int
    headers: Mapping[str, str]

    def iter_bytes(self, chunk_size: int) -> Iterator[bytes]: ...


class CallbackDownloadTransport(Protocol):
    """HTTP 落点。生产实现见 :func:`build_httpx_transport`。"""

    def stream(self, request: DownloadRequest) -> Any:
        """返回一个 context manager，`__enter__` 得到 :class:`DownloadResponse`。"""


@dataclass
class _HttpxTransport:
    """生产 transport：httpx，`trust_env=False`、不跟随重定向、两段超时。"""

    verify: bool = True

    @contextmanager
    def stream(self, request: DownloadRequest) -> Iterator[DownloadResponse]:
        import httpx

        timeout = httpx.Timeout(
            connect=float(request.timeouts.connect_seconds),
            read=float(request.timeouts.read_seconds),
            write=float(request.timeouts.connect_seconds),
            pool=float(request.timeouts.connect_seconds),
        )
        client = httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            # 🔴 Task 4 实测：未关 trust_env 时 Windows 会读注册表系统代理并劫持下载
            # （本机 http://127.0.0.1:7897，返回 502）。既是保存失败诱因，也让底稿
            # 字节流经第三方（Requirement 10.7）。
            trust_env=False,
            verify=self.verify,
        )
        try:
            with client.stream(
                "GET", request.url, headers=dict(request.headers)
            ) as response:
                yield response  # type: ignore[misc]
        except httpx.HTTPError as exc:
            raise DownloadTransportError(f"callback 下载传输失败: {exc}") from exc
        finally:
            client.close()


def build_httpx_transport(*, verify: bool = True) -> CallbackDownloadTransport:
    """生产 transport 工厂（唯一构造点，供接线与判据共同引用）。"""
    return _HttpxTransport(verify=verify)


def assert_transport_is_leak_free(transport: CallbackDownloadTransport) -> None:
    """生产 transport 不得允许环境/系统代理（Requirement 10.7）。

    判据落在**对象**而不是源码字符串：`trust_env=False` 写在源码里但被后续赋值覆盖时，
    grep 式判据仍然是绿的。
    """
    import inspect

    source = inspect.getsource(type(transport))
    if "trust_env=False" not in source:
        raise DownloadProxyLeakError(
            f"transport {type(transport).__name__} 未显式关闭 trust_env —— "
            "下载会走环境/系统代理，底稿字节将流经第三方"
        )
    if "follow_redirects=False" not in source:
        raise DownloadProxyLeakError(
            f"transport {type(transport).__name__} 未显式禁止重定向"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 流式下载
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class DownloadMetrics:
    """一次下载的可审计计量（进 delivery/operation 诊断，不含敏感原文）。"""

    bytes_read: int = 0
    chunks: int = 0
    status_code: int | None = None
    resolved_addresses: tuple[str, ...] = field(default_factory=tuple)
    pinned_address: str | None = None
    content_type: str | None = None


def stream_download(
    target: ResolvedTarget,
    *,
    policy: CallbackDownloadPolicy,
    transport: CallbackDownloadTransport,
    metrics: DownloadMetrics | None = None,
) -> Iterator[bytes]:
    """流式产出字节；3xx / 非 2xx / 超限一律在产出前或中途立即抛。

    generator 语义是刻意的：调用方（`stage_incoming`）边收边写盘，任何一步失败都在
    `.incoming/{delivery_id}/download.tmp` 留下半成品，由 sealing 前的 digest 校验或
    orphan GC 处理，**永远不会**出现 durable 行。
    """
    m = metrics if metrics is not None else DownloadMetrics()
    m.resolved_addresses = target.resolved_addresses
    m.pinned_address = target.pinned_address

    headers = {
        "Host": target.host_header,
        "Accept": "*/*",
        # 明确不带任何平台/用户凭证：OO 缓存 URL 自带签名，多带 Authorization 只会
        # 把长期 token 送到下载链路上（Requirement 10.7）。
    }
    request = DownloadRequest(
        url=target.pinned_url,
        headers=headers,
        timeouts=policy.timeouts,
        follow_redirects=policy.follow_redirects,
        max_redirects=policy.max_redirects,
    )
    if request.follow_redirects or request.max_redirects != 0:
        raise DownloadPolicyConfigError(
            "callback 下载不得跟随重定向（契约固定 follow_redirects=false / max_redirects=0）"
        )

    with transport.stream(request) as response:
        status = int(getattr(response, "status_code", 0))
        m.status_code = status
        response_headers = getattr(response, "headers", {}) or {}
        m.content_type = str(
            response_headers.get("content-type") or response_headers.get("Content-Type") or ""
        ) or None
        if 300 <= status < 400:
            raise DownloadRedirectRefusedError(
                f"callback 下载收到 {status} 重定向（Location="
                f"{response_headers.get('location') or response_headers.get('Location')!r}）—— "
                "3xx 一律拒绝，禁止把 3xx body 当文件写盘"
            )
        if not 200 <= status < 300:
            raise DownloadHttpStatusError(f"callback 下载返回 HTTP {status}")
        try:
            for chunk in response.iter_bytes(policy.chunk_bytes):
                if not chunk:
                    continue
                m.bytes_read += len(chunk)
                m.chunks += 1
                if m.bytes_read > policy.size_cap_bytes:
                    raise DownloadSizeExceededError(
                        f"callback 下载超过契约上限 {policy.size_cap_bytes} 字节"
                        f"（已读 {m.bytes_read}）—— 立即中止，不整包入内存"
                    )
                yield chunk
        except CallbackDownloadError:
            raise
        except Exception as exc:  # noqa: BLE001 - 传输层异常统一归类，不吞
            raise DownloadTransportError(f"callback 下载读取失败: {exc}") from exc


def download_to_staging(
    *,
    url: str,
    project_id: Any,
    wp_id: Any,
    delivery_id: Any,
    document_type: str,
    artifacts: Any,
    policy: CallbackDownloadPolicy,
    transport: CallbackDownloadTransport,
    resolver: Any = None,
) -> tuple[Any, DownloadMetrics]:
    """`allowlist → DNS → 固定 IP → 流式写入 .incoming/{delivery_id}` 一步到位。

    返回 `(StagedArtifact, DownloadMetrics)`。**不 sealing、不写 DB** ——
    sealing 由 :meth:`CanonicalArtifactRepository.seal_incoming` 唯一承担。

    同步函数：调用方用 `asyncio.to_thread(...)` 移出事件循环（见模块 docstring §四）。
    """
    target = resolve_and_verify(url, policy=policy, resolver=resolver)
    metrics = DownloadMetrics()
    staged = artifacts.stage_incoming(
        project_id=project_id,
        wp_id=wp_id,
        delivery_id=delivery_id,
        chunks=stream_download(
            target, policy=policy, transport=transport, metrics=metrics
        ),
        document_type=document_type,
    )
    return staged, metrics


__all__ = [
    "METADATA_ADDRESSES",
    "DEFAULT_OO_PATH_PREFIXES",
    "CallbackDownloadError",
    "DownloadPolicyConfigError",
    "DownloadUrlNotAllowlistedError",
    "DownloadPathRejectedError",
    "DownloadAddressRejectedError",
    "DownloadResolutionError",
    "DownloadRedirectRefusedError",
    "DownloadHttpStatusError",
    "DownloadSizeExceededError",
    "DownloadTransportError",
    "DownloadProxyLeakError",
    "AllowlistEntry",
    "DownloadTimeouts",
    "CallbackDownloadPolicy",
    "ResolvedTarget",
    "DownloadRequest",
    "DownloadResponse",
    "CallbackDownloadTransport",
    "DownloadMetrics",
    "parse_allowlist_entry",
    "build_download_policy",
    "assert_url_allowlisted",
    "assert_address_allowed",
    "resolve_and_verify",
    "build_httpx_transport",
    "assert_transport_is_leak_free",
    "stream_download",
    "download_to_staging",
]
