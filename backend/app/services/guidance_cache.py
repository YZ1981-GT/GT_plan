"""底稿编制说明 LRU 缓存 — mtime 失效策略

使用 collections.OrderedDict 实现 LRU 淘汰，结合模板文件 mtime
实现缓存一致性：文件修改后下次读取自动失效。

线程安全：通过 threading.Lock 保护并发访问（多个 async 线程可能
通过 asyncio.to_thread 并发调用缓存方法）。
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.guidance_extractor import GuidanceResult

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """缓存条目：存储提取结果 + 文件 mtime + 缓存时间戳"""

    result: GuidanceResult
    mtime: float  # os.path.getmtime() 时的值；template_path 不存在时为 0
    cached_at: float = field(default_factory=time.time)


class GuidanceCache:
    """LRU 缓存 + mtime 失效

    - maxsize: 缓存最大条目数，默认 128
    - 缓存键: wp_code（字符串）
    - 命中条件: wp_code 存在且对应 template_path 的 mtime 未变化
    - 失效条件: mtime 变化 → 删除旧条目，返回 None
    - LRU 淘汰: put 时若超 maxsize，淘汰最久未访问条目
    """

    def __init__(self, maxsize: int = 128) -> None:
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._maxsize = maxsize
        self._lock = threading.Lock()
        # 统计
        self._hits = 0
        self._misses = 0

    @property
    def hits(self) -> int:
        """缓存命中次数"""
        return self._hits

    @property
    def misses(self) -> int:
        """缓存未命中次数"""
        return self._misses

    @property
    def size(self) -> int:
        """当前缓存条目数"""
        with self._lock:
            return len(self._cache)

    def get(self, wp_code: str, template_path: Path | None) -> GuidanceResult | None:
        """获取缓存的编制说明结果

        命中且 mtime 未变 → 返回缓存结果（并将条目移到末尾表示最近使用）
        mtime 变化 → 失效删除，返回 None
        未命中 → 返回 None

        Args:
            wp_code: 底稿编码
            template_path: 模板文件路径，可为 None

        Returns:
            GuidanceResult 或 None（未命中/失效）
        """
        with self._lock:
            entry = self._cache.get(wp_code)
            if entry is None:
                self._misses += 1
                return None

            # 计算当前 mtime
            current_mtime = self._get_mtime(template_path)

            # mtime 校验：变化则失效
            if current_mtime != entry.mtime:
                del self._cache[wp_code]
                self._misses += 1
                logger.debug(
                    "缓存失效(mtime变化): wp_code=%s, old=%.2f, new=%.2f",
                    wp_code,
                    entry.mtime,
                    current_mtime,
                )
                return None

            # 命中：移到末尾（最近使用）
            self._cache.move_to_end(wp_code)
            self._hits += 1
            return entry.result

    def put(
        self,
        wp_code: str,
        template_path: Path | None,
        result: GuidanceResult,
    ) -> None:
        """写入缓存条目，超 maxsize 时 LRU 淘汰最旧条目

        Args:
            wp_code: 底稿编码
            template_path: 模板文件路径，可为 None
            result: 提取结果
        """
        mtime = self._get_mtime(template_path)

        with self._lock:
            # 如果已存在，先删除再重新插入（更新位置到末尾）
            if wp_code in self._cache:
                del self._cache[wp_code]

            self._cache[wp_code] = CacheEntry(
                result=result,
                mtime=mtime,
                cached_at=time.time(),
            )

            # LRU 淘汰：超 maxsize 时删除最旧（OrderedDict 头部）
            while len(self._cache) > self._maxsize:
                evicted_key, _ = self._cache.popitem(last=False)
                logger.debug("LRU 淘汰: wp_code=%s", evicted_key)

    def invalidate(self, wp_code: str) -> bool:
        """手动失效指定 wp_code 的缓存

        Args:
            wp_code: 底稿编码

        Returns:
            是否实际删除了条目
        """
        with self._lock:
            if wp_code in self._cache:
                del self._cache[wp_code]
                return True
            return False

    def clear(self) -> None:
        """清空全部缓存"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    @staticmethod
    def _get_mtime(template_path: Path | None) -> float:
        """获取模板文件 mtime，路径为 None 或文件不存在时返回 0"""
        if template_path is None:
            return 0.0
        try:
            return os.path.getmtime(template_path)
        except OSError:
            return 0.0
