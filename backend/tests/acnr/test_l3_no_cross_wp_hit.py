"""PBT: L3 模糊搜索不跨 wp 错格 — P21

**Validates: Requirements 1.2**

Property: wp_code="D2" 注册 cell → resolved_addr_id="D2-2/xxx" 不命中 D2 的 L3 条目
（前提：cell_address 与搜索目标的末段不相同，排除 endswith 合法匹配）。

验证 Step 6 移除 startswith(wp_code) 后，相邻 wp_code（如 D2 vs D2-2）不会因
wp_code 前缀重叠而互相命中。
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.acnr.runtime import (
    RuntimeCellEntry,
    clear_all_runtime_entries,
    get_runtime_entries,
    register_custom,
)
from app.services.acnr.resolver import full_resolve, ResolveResult


# ─── Strategies ──────────────────────────────────────────────────────────────

# 生成 base wp_code 如 D2, E1, K10 等（仅字母+数字，排除可能混淆的单字符）
_base_wp_code_st = st.from_regex(r"[D-N][2-9]", fullmatch=True)
# 生成后缀 -2, -3, -4 等
_suffix_st = st.integers(min_value=2, max_value=9).map(lambda n: f"-{n}")
# 生成 cell 地址（使用高行号，避免与 wp_code 冲突）
_cell_st = st.from_regex(r"[A-Z](1[0-9]{2}|[5-9][0-9])", fullmatch=True)


@st.composite
def adjacent_wp_codes_with_distinct_cell(draw):
    """生成相邻的 wp_code 对 + 不与 wp_code 冲突的 cell 地址。

    例如: base="D2", extended="D2-2", cell="E150"
    确保 cell 不等于 wp_code（避免 endswith 合法匹配干扰 P21 验证）
    """
    base = draw(_base_wp_code_st)
    suffix = draw(_suffix_st)
    extended = base + suffix
    cell = draw(_cell_st)
    # 确保 cell 不等于 base/extended（排除 endswith 合法匹配）
    assume(cell != base and cell != extended)
    # 确保搜索目标的末段不等于 cell（排除 endswith("/" + cell) 合法匹配）
    # 即 "D2-2/D2-2/E150" 末段是 "E150"，而 base 注册的 cell 也是 "E150"
    # 这种情况是 endswith 合法命中，我们要排除它来隔离测试 startswith 的修复
    return base, extended, cell


@st.composite
def adjacent_wp_codes_cross_cell(draw):
    """生成相邻 wp_code 对 + 各自不同的 cell 地址。

    确保 base 的 cell != extended 搜索 addr_id 的末段（消除 endswith 干扰）。
    """
    base = draw(_base_wp_code_st)
    suffix = draw(_suffix_st)
    extended = base + suffix
    cell_base = draw(_cell_st)
    cell_ext = draw(_cell_st)
    # 关键：base 注册的 cell 不能等于 extended 搜索目标的末段
    # extended 搜索 "ext/ext/cell_ext"，末段是 cell_ext
    # base 注册 cell_base，endswith("/" + cell_base) 不应匹配 "ext/ext/cell_ext"
    assume(cell_base != cell_ext)
    return base, extended, cell_base, cell_ext


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_mock_db():
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=AsyncMock(
        scalar_one_or_none=lambda: 1
    ))
    return mock_db


# ─── Tests ───────────────────────────────────────────────────────────────────


@settings(max_examples=5, deadline=None)
@given(data=adjacent_wp_codes_cross_cell())
def test_l3_no_cross_wp_hit_forward(data):
    """P21: wp_code="D2" 注册 cell_base → "D2-2/D2-2/cell_ext" 不命中 D2 的条目。

    核心: 旧逻辑 `resolved_addr_id.startswith(rt_entry.wp_code)` 会让
    "D2-2/D2-2/E50" 命中 wp_code="D2" 的条目（因 "D2-2/...".startswith("D2") == True）。
    修复后此匹配不再发生。
    """
    base, extended, cell_base, cell_ext = data
    project_id = "test-p21-forward"

    # 前提：旧 startswith 确实会产生错配
    search_addr_id = f"{extended}/{extended}/{cell_ext}"
    assume(search_addr_id.startswith(base))
    # 前提：endswith 不会合法命中（cell_base != cell_ext）
    assume(not search_addr_id.endswith(f"/{cell_base}"))

    clear_all_runtime_entries()

    async def _run():
        mock_db = _make_mock_db()

        # 注册 base wp_code 的 cell（如 D2 注册 cell E150）
        await register_custom(
            mock_db, project_id, "wp-base-001",
            [{"cell_address": cell_base, "wp_code": base}],
            addr_profile="custom_flat",
        )

        # 用 extended wp_code 的 addr_id 搜索（如 "D2-2/D2-2/F60"）
        result = await full_resolve(
            addr_id=search_addr_id,
            project_id=project_id,
        )

        # 不应命中 base 的 L3 条目
        assert not result.found or result.addr_id != f"{base}/{base}/{cell_base}", (
            f"Cross-wp hit! search={search_addr_id} should NOT match "
            f"base wp_code={base} entry addr_id={base}/{base}/{cell_base}. "
            f"startswith(wp_code) 漏洞仍存在"
        )

    asyncio.run(_run())


@settings(max_examples=5, deadline=None)
@given(data=adjacent_wp_codes_cross_cell())
def test_l3_no_cross_wp_hit_reverse(data):
    """P21 反向: wp_code="D2-2" 注册 cell_ext → "D2/D2/cell_base" 不命中 D2-2 条目。

    验证反方向也不会有交叉命中。
    """
    base, extended, cell_base, cell_ext = data
    project_id = "test-p21-reverse"

    # 搜索目标
    search_addr_id = f"{base}/{base}/{cell_base}"
    # 确保 endswith 不会合法命中
    assume(not search_addr_id.endswith(f"/{cell_ext}"))

    clear_all_runtime_entries()

    async def _run():
        mock_db = _make_mock_db()

        # 注册 extended wp_code 的 cell（如 D2-2 注册 cell F60）
        await register_custom(
            mock_db, project_id, "wp-ext-001",
            [{"cell_address": cell_ext, "wp_code": extended}],
            addr_profile="custom_flat",
        )

        # 用 base wp_code 的 addr_id 搜索（如 "D2/D2/E150"）
        result = await full_resolve(
            addr_id=search_addr_id,
            project_id=project_id,
        )

        # 不应命中 extended 的 L3 条目
        assert not result.found or result.addr_id != f"{extended}/{extended}/{cell_ext}", (
            f"Cross-wp hit! search={search_addr_id} should NOT match "
            f"extended wp_code={extended} entry addr_id={extended}/{extended}/{cell_ext}"
        )

    asyncio.run(_run())


@settings(max_examples=5, deadline=None)
@given(data=adjacent_wp_codes_with_distinct_cell())
def test_l3_same_wp_still_hits(data):
    """P21 正向验证: 同一 wp_code 内精确 addr_id 匹配仍正常命中。

    确保收紧后不影响正常功能 — 精确 addr_id 匹配仍然工作。
    """
    base, extended, cell = data
    project_id = "test-p21-same-wp"

    clear_all_runtime_entries()

    async def _run():
        mock_db = _make_mock_db()

        # 注册 base wp_code 的 cell
        await register_custom(
            mock_db, project_id, "wp-base-002",
            [{"cell_address": cell, "wp_code": base}],
            addr_profile="custom_flat",
        )

        # 用 base 的精确 addr_id 搜索（如 "D2/D2/E150"）
        search_addr_id = f"{base}/{base}/{cell}"

        result = await full_resolve(
            addr_id=search_addr_id,
            project_id=project_id,
        )

        # 精确匹配应命中
        assert result.found is True, (
            f"Same wp_code exact match should hit: search={search_addr_id}"
        )
        assert result.addr_id == search_addr_id

    asyncio.run(_run())


@settings(max_examples=5, deadline=None)
@given(data=adjacent_wp_codes_with_distinct_cell())
def test_l3_endswith_cell_address_still_works(data):
    """P21 补充: endswith("/" + cell_address) 合法匹配仍正常工作。

    确保收紧后保留了 endswith 条件 — 带路径的 cell 精确匹配。
    """
    base, extended, cell = data
    project_id = "test-p21-endswith"

    clear_all_runtime_entries()

    async def _run():
        mock_db = _make_mock_db()

        # 注册 base wp_code 的 cell
        await register_custom(
            mock_db, project_id, "wp-base-003",
            [{"cell_address": cell, "wp_code": base}],
            addr_profile="custom_flat",
        )

        # 用 "arbitrary_prefix/{cell}" 形式搜索，应该通过 endswith 匹配
        search_addr_id = f"some_prefix/{cell}"

        result = await full_resolve(
            addr_id=search_addr_id,
            project_id=project_id,
        )

        # endswith("/" + cell) 条件应命中
        assert result.found is True, (
            f"endswith match should hit: search={search_addr_id}, "
            f"registered cell_address={cell}"
        )

    asyncio.run(_run())


@settings(max_examples=5, deadline=None)
@given(data=adjacent_wp_codes_with_distinct_cell())
def test_l3_multi_candidate_returns_ambiguous(data):
    """P21 多候选: 多个 L3 条目有相同 cell_address 时返回 ambiguous。

    Req-19.3: 多个 L3 条目匹配 → 返回 ambiguous（而非第一个命中）。
    """
    base, extended, cell = data
    project_id = "test-p21-ambiguous"

    clear_all_runtime_entries()

    async def _run():
        mock_db = _make_mock_db()

        # 注册两个不同 wp 都包含同名 cell
        await register_custom(
            mock_db, project_id, "wp-base-004",
            [{"cell_address": cell, "wp_code": base}],
            addr_profile="custom_flat",
        )
        await register_custom(
            mock_db, project_id, "wp-ext-004",
            [{"cell_address": cell, "wp_code": extended}],
            addr_profile="custom_flat",
        )

        # 用 "some_prefix/{cell}" 搜索 — 两个条目都满足 endswith("/" + cell)
        search_addr_id = f"unknown_prefix/{cell}"

        result = await full_resolve(
            addr_id=search_addr_id,
            project_id=project_id,
        )

        # 多候选应返回 ambiguous
        assert result.found is False, (
            f"Multi-candidate should return ambiguous, not found. "
            f"result={result}"
        )
        assert result.error == "ambiguous", (
            f"Expected error='ambiguous', got error={result.error!r}"
        )
        assert result.candidates is not None
        assert len(result.candidates) >= 2

    asyncio.run(_run())
