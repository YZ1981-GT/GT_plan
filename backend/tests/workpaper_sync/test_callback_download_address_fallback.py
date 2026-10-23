"""callback 下载在「已验证地址」之间回退（spec d2-skeleton-slot-reuse-and-writeback-speed R4）。

真栈实测（2026-10-23）：`localhost` 先解析出 `::1`，本机 Docker 只在 IPv4 上转发 OnlyOffice 的
8080 ⇒ 固定到 `[::1]:8080` 恒报 WinError 10013，平台从 2026-10-21 起拒收全部 OO 保存回调
（`working_paper_callback_delivery.state=rejected`），在线编辑的修改一条也没回到表单。

判据：
1. 首个地址连不上 ⇒ 换下一个**已验证**地址，且 Host 头 / path / query 不变；
2. 拿到任何 HTTP 响应（含 4xx）都不再换地址（回退只覆盖「连不上」）；
3. 全部连不上 ⇒ 点名每个地址的失败原因；
4. 候选只来自 `resolve_and_verify` 的结果 —— 不在已验证集合里的地址永远不会被连。
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync.callback_download import (  # noqa: E402
    DownloadAddressRejectedError,
    DownloadHttpStatusError,
    DownloadMetrics,
    DownloadRequest,
    DownloadTransportError,
    build_download_policy,
    resolve_and_verify,
    stream_download,
)
from app.services.workpaper_sync.oo_contract import load_callback_contract  # noqa: E402

URL = "http://localhost:8080/cache/files/data/k/output.xlsx/output.xlsx?md5=a&expires=1"


@pytest.fixture(scope="module")
def policy() -> Any:
    return build_download_policy(
        onlyoffice_url="http://localhost:8080", contract=load_callback_contract()
    )


class _Response:
    def __init__(self, status: int, chunks: list[bytes]):
        self.status_code = status
        self.headers = {"content-type": "application/octet-stream"}
        self._chunks = chunks

    def iter_bytes(self, chunk_size: int) -> Iterator[bytes]:
        yield from self._chunks


class _Transport:
    """按 URL 里的地址决定：连不上（抛 DownloadTransportError）或给一个响应。"""

    def __init__(self, unreachable: set[str], status: int = 200):
        self.unreachable = unreachable
        self.status = status
        self.requests: list[DownloadRequest] = []

    @contextmanager
    def stream(self, request: DownloadRequest) -> Iterator[_Response]:
        self.requests.append(request)
        if any(f"//{addr}:" in request.url or f"//[{addr}]:" in request.url for addr in self.unreachable):
            raise DownloadTransportError("callback 下载传输失败: [WinError 10013]")
        yield _Response(self.status, [b"PK\x03\x04", b"rest"])


def _target(policy: Any, addresses: list[str]) -> Any:
    return resolve_and_verify(URL, policy=policy, resolver=lambda host, port: list(addresses))


def test_unreachable_first_address_falls_back_to_the_next_verified_one(policy: Any) -> None:
    transport = _Transport(unreachable={"::1"})
    metrics = DownloadMetrics()
    data = b"".join(
        stream_download(_target(policy, ["::1", "127.0.0.1"]), policy=policy,
                        transport=transport, metrics=metrics)
    )
    assert data == b"PK\x03\x04rest"
    assert [r.url.split("/cache/")[0] for r in transport.requests] == [
        "http://[::1]:8080", "http://127.0.0.1:8080",
    ]
    second = transport.requests[1]
    assert second.headers["Host"] == "localhost:8080", "Host 头仍是原 host（OO 按它校验签名）"
    assert second.url.endswith("/cache/files/data/k/output.xlsx/output.xlsx?md5=a&expires=1")
    assert second.follow_redirects is False and second.max_redirects == 0
    assert metrics.pinned_address == "127.0.0.1"


def test_any_http_response_stops_the_fallback(policy: Any) -> None:
    transport = _Transport(unreachable=set(), status=403)
    with pytest.raises(DownloadHttpStatusError):
        list(stream_download(_target(policy, ["::1", "127.0.0.1"]), policy=policy, transport=transport))
    assert len(transport.requests) == 1, "拿到 HTTP 响应就不是「连不上」，不得换地址重试"


def test_all_unreachable_names_every_address(policy: Any) -> None:
    transport = _Transport(unreachable={"::1", "127.0.0.1"})
    with pytest.raises(DownloadTransportError, match=r"2 个已验证地址都连不上.*::1.*127\.0\.0\.1"):
        list(stream_download(_target(policy, ["::1", "127.0.0.1"]), policy=policy, transport=transport))
    assert len(transport.requests) == 2


def test_fallback_never_reaches_an_address_that_failed_verification(policy: Any) -> None:
    """有一个解析结果没过复核 ⇒ 整个目标在解析阶段就被拒，回退根本不会发生。"""
    with pytest.raises(DownloadAddressRejectedError):
        _target(policy, ["127.0.0.1", "169.254.169.254"])
