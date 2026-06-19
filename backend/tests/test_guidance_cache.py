"""GuidanceCache 单元测试

测试覆盖：
1. put/get 往返一致性
2. mtime 变化时自动失效
3. LRU 淘汰（超 maxsize 时删最旧）
4. 线程安全基本检查
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.guidance_cache import CacheEntry, GuidanceCache
from app.services.guidance_extractor import GuidanceResult, GuidanceSection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cache() -> GuidanceCache:
    """默认 maxsize=128 的缓存实例"""
    return GuidanceCache(maxsize=128)


@pytest.fixture
def small_cache() -> GuidanceCache:
    """maxsize=3 的小缓存，用于测试 LRU 淘汰"""
    return GuidanceCache(maxsize=3)


def _make_result(wp_code: str, source: str = "template_sheet") -> GuidanceResult:
    """构造一个简单的 GuidanceResult"""
    return GuidanceResult(
        wp_code=wp_code,
        source=source,  # type: ignore[arg-type]
        sections=[GuidanceSection(heading="测试章节", content="测试内容", order=0)],
        raw_text=f"{wp_code} 编制说明文本",
    )


# ---------------------------------------------------------------------------
# Test 1: put/get 往返一致性
# ---------------------------------------------------------------------------


class TestPutGetRoundtrip:
    """put 后 get 应返回相同结果"""

    def test_basic_roundtrip(self, cache: GuidanceCache) -> None:
        """基本存取：put 后立即 get 应返回存入的结果"""
        result = _make_result("D2-1")
        cache.put("D2-1", None, result)

        got = cache.get("D2-1", None)
        assert got is not None
        assert got.wp_code == "D2-1"
        assert got.raw_text == "D2-1 编制说明文本"
        assert got.source == "template_sheet"

    def test_get_miss(self, cache: GuidanceCache) -> None:
        """未存入的 key 应返回 None"""
        got = cache.get("NOT_EXIST", None)
        assert got is None

    def test_roundtrip_with_real_file(self, cache: GuidanceCache) -> None:
        """使用真实文件路径的 put/get"""
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(b"dummy")
            tmp_path = Path(f.name)

        try:
            result = _make_result("A17")
            cache.put("A17", tmp_path, result)

            got = cache.get("A17", tmp_path)
            assert got is not None
            assert got.wp_code == "A17"
        finally:
            os.unlink(tmp_path)

    def test_stats_tracking(self, cache: GuidanceCache) -> None:
        """hits/misses 统计正确"""
        result = _make_result("B60")
        cache.put("B60", None, result)

        cache.get("B60", None)  # hit
        cache.get("B60", None)  # hit
        cache.get("MISS", None)  # miss

        assert cache.hits == 2
        assert cache.misses == 1

    def test_size_property(self, cache: GuidanceCache) -> None:
        """size 属性正确反映条目数"""
        assert cache.size == 0
        cache.put("A1", None, _make_result("A1"))
        assert cache.size == 1
        cache.put("A2", None, _make_result("A2"))
        assert cache.size == 2


# ---------------------------------------------------------------------------
# Test 2: mtime 失效
# ---------------------------------------------------------------------------


class TestMtimeInvalidation:
    """模板文件 mtime 变化时缓存自动失效"""

    def test_mtime_change_invalidates(self, cache: GuidanceCache) -> None:
        """文件 mtime 变化后 get 应返回 None"""
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(b"v1")
            tmp_path = Path(f.name)

        try:
            result = _make_result("D2-1")
            cache.put("D2-1", tmp_path, result)

            # 确认缓存命中
            assert cache.get("D2-1", tmp_path) is not None

            # 模拟文件修改（更新 mtime）
            time.sleep(0.05)
            tmp_path.write_bytes(b"v2")

            # mtime 变化后应失效
            got = cache.get("D2-1", tmp_path)
            assert got is None
        finally:
            os.unlink(tmp_path)

    def test_none_path_always_valid(self, cache: GuidanceCache) -> None:
        """template_path=None 时 mtime=0，缓存始终有效"""
        result = _make_result("FALLBACK")
        cache.put("FALLBACK", None, result)

        # 多次 get 均命中
        assert cache.get("FALLBACK", None) is not None
        assert cache.get("FALLBACK", None) is not None
        assert cache.hits == 2

    def test_nonexistent_path_uses_zero_mtime(self, cache: GuidanceCache) -> None:
        """不存在的路径 mtime=0，与 put 时一致则命中"""
        fake_path = Path("/nonexistent/template.xlsx")
        result = _make_result("X1")

        # put 时文件不存在 → mtime=0
        cache.put("X1", fake_path, result)

        # get 时文件仍不存在 → mtime=0 → 命中
        assert cache.get("X1", fake_path) is not None

    def test_file_deleted_after_put(self, cache: GuidanceCache) -> None:
        """文件在 put 后被删除 → mtime 从 >0 变为 0 → 失效"""
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(b"content")
            tmp_path = Path(f.name)

        result = _make_result("DEL")
        cache.put("DEL", tmp_path, result)

        # 删除文件
        os.unlink(tmp_path)

        # mtime 从实际值变为 0 → 失效
        got = cache.get("DEL", tmp_path)
        assert got is None


# ---------------------------------------------------------------------------
# Test 3: LRU 淘汰
# ---------------------------------------------------------------------------


class TestLRUEviction:
    """超过 maxsize 时淘汰最久未使用条目"""

    def test_eviction_at_capacity(self, small_cache: GuidanceCache) -> None:
        """maxsize=3 时，第 4 个 put 应淘汰第 1 个"""
        small_cache.put("A", None, _make_result("A"))
        small_cache.put("B", None, _make_result("B"))
        small_cache.put("C", None, _make_result("C"))

        assert small_cache.size == 3

        # 插入第 4 个，A 应被淘汰
        small_cache.put("D", None, _make_result("D"))

        assert small_cache.size == 3
        assert small_cache.get("A", None) is None  # 被淘汰
        assert small_cache.get("B", None) is not None
        assert small_cache.get("C", None) is not None
        assert small_cache.get("D", None) is not None

    def test_access_refreshes_lru_order(self, small_cache: GuidanceCache) -> None:
        """get 命中会刷新 LRU 顺序，被访问的不会被优先淘汰"""
        small_cache.put("A", None, _make_result("A"))
        small_cache.put("B", None, _make_result("B"))
        small_cache.put("C", None, _make_result("C"))

        # 访问 A → A 变为最近使用
        small_cache.get("A", None)

        # 插入 D → B 应被淘汰（最久未使用）
        small_cache.put("D", None, _make_result("D"))

        assert small_cache.get("A", None) is not None  # 刚访问过，保留
        assert small_cache.get("B", None) is None  # 被淘汰
        assert small_cache.get("C", None) is not None
        assert small_cache.get("D", None) is not None

    def test_put_existing_key_refreshes(self, small_cache: GuidanceCache) -> None:
        """重复 put 同一 key 不增加条目数，且刷新位置"""
        small_cache.put("A", None, _make_result("A"))
        small_cache.put("B", None, _make_result("B"))
        small_cache.put("C", None, _make_result("C"))

        # 更新 A（相当于刷新）
        small_cache.put("A", None, _make_result("A-updated"))

        assert small_cache.size == 3

        # 插入 D → B 应被淘汰
        small_cache.put("D", None, _make_result("D"))

        assert small_cache.get("A", None) is not None
        assert small_cache.get("B", None) is None
        assert small_cache.size == 3

    def test_never_exceeds_maxsize(self) -> None:
        """无论插入多少条，size 永不超过 maxsize"""
        cache = GuidanceCache(maxsize=5)
        for i in range(100):
            cache.put(f"wp_{i}", None, _make_result(f"wp_{i}"))
        assert cache.size <= 5


# ---------------------------------------------------------------------------
# Test 4: 线程安全
# ---------------------------------------------------------------------------


class TestThreadSafety:
    """并发 put/get 不崩溃且数据一致"""

    def test_concurrent_put_get(self) -> None:
        """多线程并发 put/get 不抛异常，最终 size ≤ maxsize"""
        cache = GuidanceCache(maxsize=50)
        errors: list[Exception] = []

        def writer(start: int) -> None:
            try:
                for i in range(start, start + 100):
                    cache.put(f"wp_{i}", None, _make_result(f"wp_{i}"))
            except Exception as e:
                errors.append(e)

        def reader(start: int) -> None:
            try:
                for i in range(start, start + 100):
                    cache.get(f"wp_{i}", None)
            except Exception as e:
                errors.append(e)

        threads = []
        for t_id in range(4):
            threads.append(threading.Thread(target=writer, args=(t_id * 100,)))
            threads.append(threading.Thread(target=reader, args=(t_id * 100,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"线程异常: {errors}"
        assert cache.size <= 50

    def test_concurrent_invalidate(self) -> None:
        """并发 invalidate 不崩溃"""
        cache = GuidanceCache(maxsize=100)
        for i in range(100):
            cache.put(f"wp_{i}", None, _make_result(f"wp_{i}"))

        errors: list[Exception] = []

        def invalidator(start: int) -> None:
            try:
                for i in range(start, start + 50):
                    cache.invalidate(f"wp_{i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=invalidator, args=(0,)),
            threading.Thread(target=invalidator, args=(50,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors
        assert cache.size == 0


# ---------------------------------------------------------------------------
# Test: invalidate 和 clear
# ---------------------------------------------------------------------------


class TestInvalidateAndClear:
    """手动失效和清空"""

    def test_invalidate_existing(self, cache: GuidanceCache) -> None:
        cache.put("A17", None, _make_result("A17"))
        assert cache.invalidate("A17") is True
        assert cache.get("A17", None) is None

    def test_invalidate_nonexistent(self, cache: GuidanceCache) -> None:
        assert cache.invalidate("NOPE") is False

    def test_clear(self, cache: GuidanceCache) -> None:
        cache.put("A", None, _make_result("A"))
        cache.put("B", None, _make_result("B"))
        cache.clear()
        assert cache.size == 0
        assert cache.hits == 0
        assert cache.misses == 0
