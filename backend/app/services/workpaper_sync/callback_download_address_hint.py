"""回调下载「上次连得上的那个已验证地址」的进程内提示（spec writeback-followup-issue-closure R7.1）。

`localhost` 先解析出 `::1`，而本机 Docker 只在 IPv4 上转发 OnlyOffice 的 8080：每次回调都先在
`[::1]` 上失败一次，再由 `callback_download._open_first_reachable` 回退到 `127.0.0.1`。本机这一跳
立即失败（WinError 10013，实测 0.1~17 ms），但 IPv6 被静默丢弃的网络里它要等满契约的连接超时
（`download_connect_timeout_seconds`=5）——每次保存都多等 5 秒，且每次都打一条回退告警。

这里记住上次连通的地址，下次把它排到首位。只用于给**本次已逐个验证**的地址重新排序：提示里的地址
不在本次解析结果里就忽略，allowlist / 私网判据 / 解析后复核（DNS rebinding 防线）一条不放宽。
进程内、按 (host, port) 有界、线程安全（下载在工作线程里跑）。提示的地址连不上就照旧回退，
成功后改记新地址；下载失败不改记。
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import replace
from typing import Any, Final

__all__ = ["MAX_HINTS", "clear", "prefer_last_reachable", "remember_reachable"]

#: 最多记多少个 (host, port)。回调来源只有一两个文档服务器，这个上限只防异常输入撑大内存。
MAX_HINTS: Final[int] = 64

_lock = threading.Lock()
_hints: OrderedDict[tuple[str, int], str] = OrderedDict()


def _key(target: Any) -> tuple[str, int]:
    return (str(target.host).lower(), int(target.port))


def prefer_last_reachable(target: Any) -> Any:
    """上次连通的地址仍在本次已验证集合里 ⇒ 把它固定为首选（其余已验证地址仍作回退）。"""
    with _lock:
        hint = _hints.get(_key(target))
    if hint is None or hint == target.pinned_address or hint not in target.resolved_addresses:
        return target
    from app.services.workpaper_sync.callback_download import _pinned_url_for

    return replace(target, pinned_address=hint, pinned_url=_pinned_url_for(target, hint))


def remember_reachable(target: Any, address: str | None) -> None:
    """下载成功后记下这次连通的地址（只记本次已验证集合里的）。"""
    if not address or address not in target.resolved_addresses:
        return
    key = _key(target)
    with _lock:
        _hints[key] = address
        _hints.move_to_end(key)
        while len(_hints) > MAX_HINTS:
            _hints.popitem(last=False)


def clear() -> None:
    """清空（测试隔离用）。"""
    with _lock:
        _hints.clear()
