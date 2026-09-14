# -*- coding: utf-8 -*-
"""进程内、线程安全、有界 LRU —— OO/HTML 回写热点的整簿解析产物缓存。

spec: oo-html-writeback-performance · 批次 1

═══ 为什么是进程内 LRU + 内容寻址键 ═══

三个热点端点（store-projection / materialize verify / OO apply）每次都用 openpyxl
把整本 46-sheet 大工作簿完整解析多遍，而解析产物（extract 出的 Projection、未管理区域
digest）是 substrate **字节的纯函数**：同一份 substrate 字节永远解析出同一产物。

substrate 是**已发布不可变 artifact**（canonical/published，内容寻址存储），因此：

* 键 = substrate 字节的 sha256（`resolution` 已带 `artifact_sha256`）。sha256 一变即 key
  变即天然失效——**无需任何"何时清除缓存"的推理**：新 substrate = 新 sha256 = 新 key =
  自然 miss，旧 key 由 LRU 淘汰。
* 命中返回的产物与重新解析**逐字节等价**（纯函数），不弱化任何校验（只避免重算不变量）。
* 多 worker 不共享 = 正确性无损（各自算，结果相同）；重启失效 = 冷启动重算。

═══ 只缓存不可变派生产物 ═══

值只能是 frozen 的解析产物（``Projection`` / digest bytes / dataclass）。**绝不**缓存
会话、可变状态、或任何跨请求会被改写的对象。缓存本身不感知 wp / revision 语义——
语义全部压进"内容寻址键"这一个决定里。

═══ 线程安全 ═══

热点里 `asyncio.to_thread` 的工作线程与事件循环线程都会读写同一缓存，故内部用一把
`threading.Lock`。LRU 有上限（`maxsize`），淘汰最久未用项，绝不无界增长。
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Callable, Generic, Hashable, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class BoundedLruCache(Generic[K, V]):
    """线程安全、有界 LRU。

    只提供 ``get`` / ``put`` / ``get_or_compute`` / ``invalidate`` / ``clear`` 与 hit/miss
    计数。刻意不做 TTL：内容寻址键下 substrate 字节不变则产物不变，无需过期。
    """

    __slots__ = ("_store", "_maxsize", "_lock", "_hits", "_misses")

    def __init__(self, *, maxsize: int) -> None:
        if maxsize <= 0:
            raise ValueError("BoundedLruCache maxsize 必须为正 —— 无界缓存会内存泄漏")
        self._store: "OrderedDict[K, V]" = OrderedDict()
        self._maxsize = int(maxsize)
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: K) -> V | None:
        """命中则返回值并把该键移到最近使用端；miss 返回 ``None``。"""
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                self._hits += 1
                return self._store[key]
            self._misses += 1
            return None

    def put(self, key: K, value: V) -> None:
        """写入并按 LRU 淘汰超出上限的最久未用项。"""
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = value
            while len(self._store) > self._maxsize:
                self._store.popitem(last=False)  # 淘汰最久未用

    def get_or_compute(self, key: K, compute: Callable[[], V]) -> V:
        """命中返回缓存；否则调用 ``compute()`` 并写入。

        🔴 ``compute()`` 在锁**外**执行（它可能是数十秒的整簿解析，持锁会把并发全串行）。
        代价是同键可能被并发重复计算一次——对纯函数产物无正确性影响，只是偶发多算一次。
        """
        cached = self.get(key)
        if cached is not None:
            return cached
        value = compute()
        self.put(key, value)
        return value

    def invalidate(self, key: K) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """清空（测试隔离用）。不重置计数。"""
        with self._lock:
            self._store.clear()

    @property
    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": len(self._store),
                "maxsize": self._maxsize,
            }


# ─────────────────────────────────────────────────────────────────
# 模块级单例（各自独立上限）。键均为内容寻址字符串（见各消费点）。
# ─────────────────────────────────────────────────────────────────

#: ROI-1：store-projection 的 baseline extract（substrate → Projection）。
#: 键 = f"{contract_id}:{artifact_sha256}"。单条是一个 frozen Projection。
BASELINE_EXTRACT_CACHE: "BoundedLruCache[str, object]" = BoundedLruCache(maxsize=64)

#: ROI-4：materialize verify 的 before 侧 unmanaged-region digest（不变量）。
#: 键 = f"{substrate_sha256}:{sheet_part}:{table_key}:{extra_parts_joined}"。
BEFORE_DIGEST_CACHE: "BoundedLruCache[str, object]" = BoundedLruCache(maxsize=128)


def clear_all_parse_caches() -> None:
    """清空全部解析缓存（测试隔离/运维用）。"""
    BASELINE_EXTRACT_CACHE.clear()
    BEFORE_DIGEST_CACHE.clear()


__all__ = [
    "BoundedLruCache",
    "BASELINE_EXTRACT_CACHE",
    "BEFORE_DIGEST_CACHE",
    "clear_all_parse_caches",
]
