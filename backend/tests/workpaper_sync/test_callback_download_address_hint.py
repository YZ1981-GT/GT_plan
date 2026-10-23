"""回调下载记住上次连通的已验证地址（spec writeback-followup-issue-closure R7.1）。

`localhost` 先解析出 `::1`，本机 Docker 只在 IPv4 上转发 8080：每次回调都先在 `[::1]` 上失败一次
再回退（回退本身见 `test_callback_download_address_fallback.py`）。IPv6 被静默丢弃的网络里这一跳要
等满 5 秒连接超时。判据：
1. 回退成功后，下一次直接先连上次连通的地址（不再先撞 `::1`）；
2. 提示只给**本次已验证**的地址排序：提示的地址不在本次解析结果里 ⇒ 忽略，绝不去连它；
3. 提示的地址连不上 ⇒ 照旧回退并改记新地址；整次下载失败不改记；
4. 按 (host, port) 区分，存量有界。
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import pytest

from app.services.workpaper_sync import callback_download_address_hint as hint
from app.services.workpaper_sync.callback_download import (
    DownloadRequest,
    DownloadTransportError,
    build_download_policy,
    download_to_staging,
)
from app.services.workpaper_sync.oo_contract import load_callback_contract

URL = "http://localhost:8080/cache/files/data/k/output.xlsx/output.xlsx?md5=a&expires=1"


@pytest.fixture(scope="module")
def policy() -> Any:
    return build_download_policy(onlyoffice_url="http://localhost:8080", contract=load_callback_contract())


@pytest.fixture(autouse=True)
def _isolated_hints() -> Iterator[None]:
    hint.clear()
    yield
    hint.clear()


class _Response:
    status_code = 200
    headers = {"content-type": "application/octet-stream"}

    def iter_bytes(self, chunk_size: int) -> Iterator[bytes]:
        yield b"PK\x03\x04rest"


class _Transport:
    def __init__(self, unreachable: set[str]):
        self.unreachable = unreachable
        self.requests: list[DownloadRequest] = []

    @contextmanager
    def stream(self, request: DownloadRequest) -> Iterator[_Response]:
        self.requests.append(request)
        if any(f"//{a}:" in request.url or f"//[{a}]:" in request.url for a in self.unreachable):
            raise DownloadTransportError("callback 下载传输失败: [WinError 10013]")
        yield _Response()

    def hosts(self) -> list[str]:
        return [r.url.split("/cache/")[0] for r in self.requests]


class _Artifacts:
    def stage_incoming(self, *, chunks: Iterator[bytes], **_kw: Any) -> bytes:
        return b"".join(chunks)


def _download(policy: Any, transport: _Transport, addresses: list[str], url: str = URL) -> Any:
    staged, metrics = download_to_staging(
        url=url, project_id="p", wp_id="w", delivery_id="d", document_type="xlsx",
        artifacts=_Artifacts(), policy=policy, transport=transport,
        resolver=lambda host, port: list(addresses),
    )
    assert staged == b"PK\x03\x04rest"
    return metrics


def test_second_download_goes_straight_to_the_address_that_worked(policy: Any) -> None:
    first = _Transport(unreachable={"::1"})
    _download(policy, first, ["::1", "127.0.0.1"])
    assert first.hosts() == ["http://[::1]:8080", "http://127.0.0.1:8080"]

    second = _Transport(unreachable={"::1"})
    metrics = _download(policy, second, ["::1", "127.0.0.1"])
    assert second.hosts() == ["http://127.0.0.1:8080"], "上次连通的地址应排到首位"
    assert second.requests[0].headers["Host"] == "localhost:8080"
    assert second.requests[0].url.endswith("/cache/files/data/k/output.xlsx/output.xlsx?md5=a&expires=1")
    assert metrics.pinned_address == "127.0.0.1"
    assert metrics.resolved_addresses == ("::1", "127.0.0.1"), "已验证集合不因提示而改变"


def test_hint_outside_this_resolution_is_ignored(policy: Any) -> None:
    _download(policy, _Transport(unreachable={"::1"}), ["::1", "127.0.0.1"])
    transport = _Transport(unreachable=set())
    _download(policy, transport, ["::1", "127.0.0.2"])
    assert transport.hosts() == ["http://[::1]:8080"], "提示的地址不在本次已验证集合里 ⇒ 绝不去连它"


def test_hint_that_stops_working_falls_back_and_is_replaced(policy: Any) -> None:
    _download(policy, _Transport(unreachable={"::1"}), ["::1", "127.0.0.1"])
    flipped = _Transport(unreachable={"127.0.0.1"})
    _download(policy, flipped, ["::1", "127.0.0.1"])
    assert flipped.hosts() == ["http://127.0.0.1:8080", "http://[::1]:8080"]
    again = _Transport(unreachable={"127.0.0.1"})
    _download(policy, again, ["::1", "127.0.0.1"])
    assert again.hosts() == ["http://[::1]:8080"], "回退成功后改记新地址"


def test_failed_download_does_not_change_the_hint(policy: Any) -> None:
    _download(policy, _Transport(unreachable={"::1"}), ["::1", "127.0.0.1"])
    with pytest.raises(DownloadTransportError):
        _download(policy, _Transport(unreachable={"::1", "127.0.0.1"}), ["::1", "127.0.0.1"])
    transport = _Transport(unreachable={"::1"})
    _download(policy, transport, ["::1", "127.0.0.1"])
    assert transport.hosts() == ["http://127.0.0.1:8080"]


def test_hints_are_per_host_and_port_and_bounded(policy: Any) -> None:
    _download(policy, _Transport(unreachable={"::1"}), ["::1", "127.0.0.1"])
    target = type("T", (), {"host": "localhost", "port": 9090, "pinned_address": "::1",
                            "resolved_addresses": ("::1", "127.0.0.1")})()
    assert hint.prefer_last_reachable(target) is target, "端口不同不共用提示"
    for n in range(hint.MAX_HINTS + 5):
        other = type("T", (), {"host": f"h{n}", "port": 1, "resolved_addresses": ("10.0.0.1",)})()
        hint.remember_reachable(other, "10.0.0.1")
    assert len(hint._hints) == hint.MAX_HINTS
    assert ("localhost", 8080) not in hint._hints, "最久未用的先淘汰"
