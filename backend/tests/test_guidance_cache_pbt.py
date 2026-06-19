# Feature: workpaper-editing-guidance, Property 3: 缓存一致性（mtime 失效）
"""Property 3: 缓存一致性（mtime 失效）

For any wp_code + mtime pair, cache.put then cache.get with same mtime returns result;
get with different mtime returns None. Size never exceeds maxsize.

**Validates: Requirements 2.6, 8.1, 8.2, 8.3**
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.guidance_cache import GuidanceCache
from app.services.guidance_extractor import GuidanceResult, GuidanceSection


def _make_result(wp_code: str) -> GuidanceResult:
    """构造 GuidanceResult"""
    return GuidanceResult(
        wp_code=wp_code,
        source="template_sheet",
        sections=[GuidanceSection(heading="测试", content="内容", order=0)],
        raw_text=f"{wp_code} 编制说明",
    )


# wp_code 策略：2-10 字符字母数字连字符
_wp_code_st = st.text(
    alphabet=st.sampled_from("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"),
    min_size=2,
    max_size=10,
)

# mtime 策略：正浮点数
_mtime_st = st.floats(min_value=1.0, max_value=2000000000.0, allow_nan=False, allow_infinity=False)


@given(wp_code=_wp_code_st, mtime=_mtime_st)
@settings(max_examples=5)
def test_cache_put_get_same_mtime_returns_result(wp_code: str, mtime: float):
    """put 后以相同 mtime get，必须返回缓存结果。"""
    cache = GuidanceCache(maxsize=128)
    result = _make_result(wp_code)

    # Mock _get_mtime 返回固定值
    with patch.object(GuidanceCache, "_get_mtime", return_value=mtime):
        cache.put(wp_code, None, result)
        got = cache.get(wp_code, None)

    assert got is not None, f"wp_code={wp_code}, mtime={mtime} 应命中缓存"
    assert got.wp_code == wp_code
    assert got.raw_text == result.raw_text


@given(wp_code=_wp_code_st, mtime1=_mtime_st, mtime2=_mtime_st)
@settings(max_examples=5)
def test_cache_get_different_mtime_returns_none(wp_code: str, mtime1: float, mtime2: float):
    """put 时 mtime=mtime1，get 时 mtime=mtime2（不同），必须返回 None。"""
    assume(abs(mtime1 - mtime2) > 0.001)  # 确保两个 mtime 不同

    cache = GuidanceCache(maxsize=128)
    result = _make_result(wp_code)

    # put 时使用 mtime1
    with patch.object(GuidanceCache, "_get_mtime", return_value=mtime1):
        cache.put(wp_code, None, result)

    # get 时使用不同的 mtime2
    with patch.object(GuidanceCache, "_get_mtime", return_value=mtime2):
        got = cache.get(wp_code, None)

    assert got is None, f"mtime 变化后应返回 None（mtime1={mtime1}, mtime2={mtime2}）"


@given(
    num_entries=st.integers(min_value=5, max_value=20),
    maxsize=st.integers(min_value=3, max_value=10),
)
@settings(max_examples=5)
def test_cache_size_never_exceeds_maxsize(num_entries: int, maxsize: int):
    """无论插入多少条目，缓存 size 永不超过 maxsize。"""
    cache = GuidanceCache(maxsize=maxsize)

    for i in range(num_entries):
        wp_code = f"WP-{i}"
        cache.put(wp_code, None, _make_result(wp_code))

    assert cache.size <= maxsize, (
        f"缓存 size={cache.size} 超过 maxsize={maxsize}（插入了 {num_entries} 条）"
    )
