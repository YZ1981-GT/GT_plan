"""PBT: 增量失效不影响无关 wp — P7

**Validates: Requirements 5.2**

Property: 两个 wp 各注册条目 → invalidate wp_A → wp_B 仍可 resolve

使用 Hypothesis 验证增量失效的隔离性。
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ─── Import SUT ──────────────────────────────────────────────────────────────

from app.services.acnr.runtime import (
    RuntimeCellEntry,
    clear_all_runtime_entries,
    clear_runtime_entries_for_wp,
    get_runtime_entries,
    register_custom,
    resolve_l3,
)
from app.services.acnr.events import invalidate


# ─── Strategies ──────────────────────────────────────────────────────────────

_wp_code_st = st.from_regex(r"[A-N][1-9][0-9]?", fullmatch=True)
_cell_st = st.from_regex(r"[A-Z][1-9][0-9]?", fullmatch=True)
_uuid_st = st.uuids().map(str)


@st.composite
def two_distinct_wps(draw):
    """生成两个不同的 (wp_id, wp_code, cells) 对。"""
    wp_id_a = draw(_uuid_st)
    wp_id_b = draw(_uuid_st.filter(lambda x: x != wp_id_a))
    wp_code_a = draw(_wp_code_st)
    wp_code_b = draw(_wp_code_st)
    cell_a = draw(_cell_st)
    cell_b = draw(_cell_st)
    return (wp_id_a, wp_code_a, cell_a), (wp_id_b, wp_code_b, cell_b)


# ─── Helper ──────────────────────────────────────────────────────────────────

def _make_mock_db():
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=AsyncMock(
        scalar_one_or_none=lambda: 1
    ))
    return mock_db


# ─── Tests ───────────────────────────────────────────────────────────────────


@settings(max_examples=5, deadline=None)
@given(data=two_distinct_wps())
def test_incremental_invalidation_preserves_other_wp(data):
    """P7: invalidate wp_A 后, wp_B 的 L3 条目仍存在。"""
    (wp_id_a, wp_code_a, cell_a), (wp_id_b, wp_code_b, cell_b) = data
    project_id = "test-project-p7"

    # 清空全局状态
    clear_all_runtime_entries()

    async def _run():
        mock_db = _make_mock_db()

        # 注册 wp_A 的条目
        cells_a = [{"cell_address": cell_a, "wp_code": wp_code_a}]
        await register_custom(mock_db, project_id, wp_id_a, cells_a)

        # 注册 wp_B 的条目
        cells_b = [{"cell_address": cell_b, "wp_code": wp_code_b}]
        await register_custom(mock_db, project_id, wp_id_b, cells_b)

        # 验证两个都已注册
        entries = get_runtime_entries(project_id)
        a_entries = [e for e in entries.values() if e.wp_id == wp_id_a]
        b_entries = [e for e in entries.values() if e.wp_id == wp_id_b]
        assert len(a_entries) > 0, "wp_A 条目应已注册"
        assert len(b_entries) > 0, "wp_B 条目应已注册"

        # 增量失效 wp_A
        removed = clear_runtime_entries_for_wp(project_id, wp_id_a)

        # 验证 wp_A 已清除
        entries_after = get_runtime_entries(project_id)
        a_after = [e for e in entries_after.values() if e.wp_id == wp_id_a]
        assert len(a_after) == 0, "wp_A 条目应已被清除"

        # 验证 wp_B 仍存在
        b_after = [e for e in entries_after.values() if e.wp_id == wp_id_b]
        assert len(b_after) > 0, "wp_B 条目不应受影响"

    asyncio.run(_run())


@settings(max_examples=5, deadline=None)
@given(data=two_distinct_wps())
def test_events_invalidate_with_wp_id_preserves_other(data):
    """P7 集成: events.invalidate(wp_id=A) 后 wp_B 仍可 resolve。"""
    (wp_id_a, wp_code_a, cell_a), (wp_id_b, wp_code_b, cell_b) = data
    project_id = "test-project-p7-events"

    clear_all_runtime_entries()

    async def _run():
        mock_db = _make_mock_db()

        # 注册两个 wp
        await register_custom(
            mock_db, project_id, wp_id_a,
            [{"cell_address": cell_a, "wp_code": wp_code_a}],
        )
        await register_custom(
            mock_db, project_id, wp_id_b,
            [{"cell_address": cell_b, "wp_code": wp_code_b}],
        )

        # 通过 events.invalidate 仅失效 wp_A
        with patch("app.services.acnr.overlay.clear_project_overlays"):
            with patch("app.services.formula_reverse_index.invalidate_reverse_index"):
                with patch("app.services.address_registry.address_registry") as mock_reg:
                    mock_reg.invalidate_async = AsyncMock()
                    await invalidate(project_id, wp_id=wp_id_a, trigger="test")

        # wp_B 仍可找到
        entries_after = get_runtime_entries(project_id)
        b_after = [e for e in entries_after.values() if e.wp_id == wp_id_b]
        assert len(b_after) > 0, "wp_B 条目不应受 invalidate(wp_id=A) 影响"

        # wp_A 应已清除
        a_after = [e for e in entries_after.values() if e.wp_id == wp_id_a]
        assert len(a_after) == 0, "wp_A 条目应已被清除"

    asyncio.run(_run())


@settings(max_examples=5, deadline=None)
@given(
    wp_code=_wp_code_st,
    cell=_cell_st,
)
def test_resolve_l3_exact_match(wp_code, cell):
    """resolve_l3 精确匹配返回 found。"""
    project_id = "test-resolve-l3-exact"
    clear_all_runtime_entries()

    async def _run():
        mock_db = _make_mock_db()
        wp_id = "wp-exact-test"

        await register_custom(
            mock_db, project_id, wp_id,
            [{"cell_address": cell, "wp_code": wp_code}],
        )

        entries = get_runtime_entries(project_id)
        # 取第一个 addr_id 做精确查找
        if entries:
            first_addr_id = next(iter(entries.keys()))
            status, result = resolve_l3(project_id, first_addr_id)
            assert status == "found"
            assert result is not None
            assert result.addr_id == first_addr_id

    asyncio.run(_run())


@settings(max_examples=5, deadline=None)
@given(
    wp_code=_wp_code_st,
    cell=_cell_st,
)
def test_resolve_l3_prefix_no_false_positive(wp_code, cell):
    """resolve_l3 不会错误匹配相似前缀（如 D2 不匹配 D20）。"""
    project_id = "test-resolve-l3-prefix"
    clear_all_runtime_entries()

    async def _run():
        mock_db = _make_mock_db()
        wp_id = "wp-prefix-test"

        # 注册 wp_code/wp_code/cell (custom_flat)
        await register_custom(
            mock_db, project_id, wp_id,
            [{"cell_address": cell, "wp_code": wp_code}],
            addr_profile="custom_flat",
        )

        # 用一个不相关但相似前缀查询（加个字符）
        fake_target = wp_code + "0"  # e.g., "D20" when wp_code="D2"
        status, result = resolve_l3(project_id, fake_target)
        # 不应匹配（精确不中，且 "D20/" 前缀也不中 "D2/D2/A1"）
        assert status == "miss", (
            f"target={fake_target} 不应匹配 wp_code={wp_code} 的条目"
        )

    asyncio.run(_run())


@settings(max_examples=5, deadline=None)
@given(
    wp_code=_wp_code_st,
    cell_a=_cell_st,
    cell_b=st.from_regex(r"[A-Z][1-9][0-9]?", fullmatch=True),
)
def test_resolve_l3_ambiguous_multi_candidate(wp_code, cell_a, cell_b):
    """resolve_l3 多候选匹配同一前缀时返回 ambiguous。"""
    project_id = "test-resolve-l3-ambiguous"
    clear_all_runtime_entries()

    # 确保两个 cell 不同
    if cell_a == cell_b:
        return  # skip trivial case

    async def _run():
        mock_db = _make_mock_db()
        wp_id = "wp-ambiguous-test"

        # 注册两个不同 cell 到同一 wp_code（custom_flat 会产生相同前缀）
        await register_custom(
            mock_db, project_id, wp_id,
            [
                {"cell_address": cell_a, "wp_code": wp_code},
                {"cell_address": cell_b, "wp_code": wp_code},
            ],
            addr_profile="custom_flat",
        )

        # 用 wp_code 作为前缀查询 → 应该匹配多个
        # custom_flat addr_id = "wp_code/wp_code/cell"
        # target = wp_code, prefix = wp_code + "/" → 匹配 "wp_code/..."
        status, result = resolve_l3(project_id, wp_code)
        assert status == "ambiguous", (
            f"两个候选 ({cell_a}, {cell_b}) 应返回 ambiguous, got {status}"
        )
        assert isinstance(result, list)
        assert len(result) >= 2

    asyncio.run(_run())
