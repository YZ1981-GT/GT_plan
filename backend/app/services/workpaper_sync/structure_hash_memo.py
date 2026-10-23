"""normalized structure hash 的内容寻址记忆化（spec writeback-followup-issue-closure R4 / D6）。

`excel_instrumentation.normalized_structure_hash` 把整册结构指纹折成 64 字符的摘要。
结构指纹本身含整册值 / 样式（数 MB），`excel_structure_fingerprint` 里它的 LRU 只有 16 份，
而冷注册要算 36 份不同模板 ⇒ 第二轮（基线 projection 预热 / 目标底稿绑定）全部重新整册
解析（实测预热期间这一项占事件循环 19 s）。这里只存「字节 sha256 → 结果摘要」：

- 纯函数、入参逐字节相同 ⇒ 输出相同，key 是内容摘要，不会过期；
- 计算抛错不入缓存（与指纹缓存同口径：抛错路径不得占用 key）；
- 有界（:data:`MEMO_MAX`，按最近使用淘汰）；加锁，因为预热在工作线程里写、事件循环里读。

单独成模块的原因：`excel_instrumentation.py` 已超行数门，且这段与 instrumentation 业务无关。
计算本身仍在 `excel_instrumentation`（它持有 `structure_fingerprint` 与错误类型）。
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from typing import Callable, Final

MEMO_MAX: Final[int] = 512

_MEMO: "OrderedDict[str, str]" = OrderedDict()
_LOCK = threading.Lock()


def memoized(data: bytes, compute: Callable[[bytes], str]) -> str:
    """返回 ``compute(data)``；同一份字节只真正计算一次（直到被淘汰或 :func:`clear`）。"""
    key = hashlib.sha256(data).hexdigest()
    with _LOCK:
        hit = _MEMO.get(key)
        if hit is not None:
            _MEMO.move_to_end(key)
            return hit
    digest = compute(data)
    with _LOCK:
        _MEMO[key] = digest
        while len(_MEMO) > MEMO_MAX:
            _MEMO.popitem(last=False)
    return digest


def clear() -> None:
    """清空记忆（测试用；生产不需要）。"""
    with _LOCK:
        _MEMO.clear()
