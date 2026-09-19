# Feature: acnr, Property 8: 未命中响应契约与 ambiguous
"""Property-based test: 未命中响应契约与 ambiguous（含 resolve_instance 多实例）。

**Validates: Requirements 2.3, 2.4, 5.5, 5.6**

验证规则:
- R2.3: sheet_code 不存在时返回 found=False 并附带最多 5 条 candidates
        （含 addr_id、display_label、score）
- R2.4: 同一 sheet_code 命中多个条目时返回 found=False、error="ambiguous"
        且在 candidates 中返回全部命中条目
- R5.5: 解析在同一 sheet 下命中多个候选 → found=False + error="ambiguous" + candidates
- R5.6: 未命中 → found=False + 最多 5 条相近项 candidates 并记 miss 指标

核心属性:
1. Miss 响应: found=False + candidates 列表 (≤5 items)
2. 每个 candidate 包含 addr_id、display_label、score
3. Ambiguous 响应: found=False + error="ambiguous" + candidates 列表
4. Ambiguous candidates 包含全部命中条目（不截断）
5. 随机不存在引用的 miss 契约验证

Testing framework: hypothesis
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

# 确保 backend 目录在 path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))


# ---------------------------------------------------------------------------
# Test catalog injection utilities
# ---------------------------------------------------------------------------


def _inject_catalog(catalog_data: dict):
    """注入自定义 catalog 数据到全局单例（测试用）。"""
    import app.services.acnr.catalog as cat_mod
    cat_mod._catalog = cat_mod.CatalogIndex(catalog_data)


def _reset_catalog():
    """重置 catalog 单例，恢复正常加载逻辑。"""
    import app.services.acnr.catalog as cat_mod
    cat_mod._catalog = None


# ---------------------------------------------------------------------------
# Strategies for generating non-existent refs
# ---------------------------------------------------------------------------

# 不存在的 wp_code 前缀（Z 不在 A-S 标准范围，且拼接数字确保无命中）
_nonexistent_wp_code_st = st.from_regex(r"Z[0-9]{2,3}", fullmatch=True)

# 不存在的 sheet_code 后缀
_nonexistent_sheet_st = st.from_regex(r"Z[0-9]{1,2}-[0-9]{1,2}", fullmatch=True)

# 不存在的 cell 地址
_nonexistent_cell_st = st.from_regex(r"[W-Z]{2}[0-9]{4}", fullmatch=True)

# 不存在的 addr_id = "Z99/Z99-9/ZZ9999"
_nonexistent_addr_id_st = st.builds(
    lambda wp, sheet, cell: f"{wp}/{sheet}/{cell}",
    _nonexistent_wp_code_st,
    _nonexistent_sheet_st,
    _nonexistent_cell_st,
)

# 不存在的 URI
_nonexistent_uri_st = st.builds(
    lambda wp, sheet, cell: f"wp://{wp}/不存在的Sheet{sheet}#{cell}",
    _nonexistent_wp_code_st,
    _nonexistent_sheet_st,
    _nonexistent_cell_st,
)

# 不存在的 formula_ref
_nonexistent_formula_ref_st = st.builds(
    lambda wp, sheet, cell: f"WP('{wp}','不存在Sheet{sheet}','{cell}')",
    _nonexistent_wp_code_st,
    _nonexistent_sheet_st,
    _nonexistent_cell_st,
)

# 不存在的 index_ref
_nonexistent_index_ref_st = st.builds(
    lambda sheet, cell: f"cell:{sheet}!{cell}",
    _nonexistent_sheet_st,
    _nonexistent_cell_st,
)


# ---------------------------------------------------------------------------
# Ambiguous catalog builder: 构造含多个同 sheet_code 的 catalog
# ---------------------------------------------------------------------------

# 产生 2~4 个同 sheet_code 条目的条数
_ambiguous_count_st = st.integers(min_value=2, max_value=4)


def _build_ambiguous_catalog(
    parent: str,
    sheet_code: str,
    count: int,
) -> dict:
    """构造一个含 count 个同 sheet_code 条目的 catalog（用于触发 ambiguous）。

    每个 sheet 有相同 sheet_code 但不同的 addr_id（通过不同 parent 实现）。
    """
    sheets = []
    cells = []
    for i in range(count):
        # 不同 parent 使得 addr_id 唯一，但 sheet_code 重复
        p = f"{parent}{i}"
        addr_id = f"{p}/{sheet_code}"
        sheets.append({
            "addr_id": addr_id,
            "domain": "wp",
            "origin": "standard",
            "cycle": "D",
            "parent_wp_code": p,
            "sheet_code": sheet_code,
            "sheet_name": f"测试Sheet{i}",
            "sheet_name_aliases": [],
            "component_type": "test-component",
            "class_code": "F-明细表",
            "display_label": f"底稿 > {p} > 测试Sheet{i}",
            "jump_route_template": f"/workpapers/{{wp_id}}?sheet={sheet_code}",
            "registry_version": "test-v1",
        })
    return {
        "version": "1",
        "registry_version": "test-v1",
        "sheets": sheets,
        "cells": cells,
    }


def _build_ambiguous_cell_catalog(
    parent: str,
    sheet_code: str,
    cell_desc: str,
    count: int,
) -> dict:
    """构造同一 sheet 下多个同 cell_address 条目的 catalog（用于 cell 级 ambiguous）。"""
    sheet_addr_id = f"{parent}/{sheet_code}"
    sheets = [{
        "addr_id": sheet_addr_id,
        "domain": "wp",
        "origin": "standard",
        "cycle": "D",
        "parent_wp_code": parent,
        "sheet_code": sheet_code,
        "sheet_name": f"测试Sheet",
        "sheet_name_aliases": [],
        "component_type": "test-component",
        "class_code": "F-明细表",
        "display_label": f"底稿 > {parent} > 测试Sheet",
        "jump_route_template": f"/workpapers/{{wp_id}}?sheet={sheet_code}",
        "registry_version": "test-v1",
    }]
    cells = []
    for i in range(count):
        cells.append({
            "addr_id": f"{parent}/{sheet_code}/{cell_desc}-{i}",
            "parent_addr_id": sheet_addr_id,
            "domain": "wp",
            "cell_address": cell_desc,
            "semantic_label": f"语义标签{i}",
            "formula_ref": f"WP('{parent}','{sheet_code}','{cell_desc}-{i}')",
            "uri": f"wp://{parent}/测试Sheet#{cell_desc}-{i}",
            "registry_version": "test-v1",
        })
    return {
        "version": "1",
        "registry_version": "test-v1",
        "sheets": sheets,
        "cells": cells,
    }


# ---------------------------------------------------------------------------
# Helper: 运行 async full_resolve
# ---------------------------------------------------------------------------


def _run_resolve(**kwargs):
    """同步包装 async full_resolve。"""
    from app.services.acnr.resolver import full_resolve
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(full_resolve(**kwargs))
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _restore_catalog():
    """每个测试后恢复 catalog 到默认状态。"""
    yield
    _reset_catalog()


# ---------------------------------------------------------------------------
# Property Test 1: Miss 响应契约 — found=False + candidates ≤ 5
# ---------------------------------------------------------------------------


class TestMissResponseContract:
    """Property 8a: 未命中响应必须满足 found=False + candidates ≤ 5 + 每项含必要字段。"""

    @given(addr_id=_nonexistent_addr_id_st)
    @settings(max_examples=10)
    def test_miss_by_addr_id_contract(self, addr_id: str):
        """R5.6: 随机不存在 addr_id resolve → found=False + candidates ≤ 5。

        每个 candidate 包含 addr_id、display_label、score 三个字段。

        **Validates: Requirements 2.3, 5.6**
        """
        result = _run_resolve(addr_id=addr_id)

        # 未命中必须 found=False
        assert result.found is False, (
            f"不存在的 addr_id 不应命中: {addr_id}, got found=True"
        )

        # candidates 存在且为列表
        assert result.candidates is not None, (
            f"miss 响应必须有 candidates 字段: addr_id={addr_id}"
        )
        assert isinstance(result.candidates, list)

        # candidates ≤ 5 条（R2.3, R5.6）
        assert len(result.candidates) <= 5, (
            f"candidates 超过 5 条限制: len={len(result.candidates)}, "
            f"addr_id={addr_id}"
        )

        # 每个 candidate 包含必要字段（R2.3）
        for i, cand in enumerate(result.candidates):
            assert "addr_id" in cand, (
                f"candidate[{i}] 缺少 addr_id: {cand}"
            )
            assert "display_label" in cand, (
                f"candidate[{i}] 缺少 display_label: {cand}"
            )
            assert "score" in cand, (
                f"candidate[{i}] 缺少 score: {cand}"
            )

    @given(uri=_nonexistent_uri_st)
    @settings(max_examples=10)
    def test_miss_by_uri_contract(self, uri: str):
        """R5.6: 随机不存在 URI resolve → 满足 miss 契约。

        **Validates: Requirements 2.3, 5.6**
        """
        result = _run_resolve(uri=uri)

        assert result.found is False, (
            f"不存在的 URI 不应命中: {uri}"
        )
        assert result.candidates is not None
        assert isinstance(result.candidates, list)
        assert len(result.candidates) <= 5

        for cand in result.candidates:
            assert "addr_id" in cand
            assert "display_label" in cand
            assert "score" in cand

    @given(formula_ref=_nonexistent_formula_ref_st)
    @settings(max_examples=10)
    def test_miss_by_formula_ref_contract(self, formula_ref: str):
        """R5.6: 随机不存在 formula_ref resolve → 满足 miss 契约。

        **Validates: Requirements 2.3, 5.6**
        """
        result = _run_resolve(formula_ref=formula_ref)

        assert result.found is False, (
            f"不存在的 formula_ref 不应命中: {formula_ref}"
        )
        assert result.candidates is not None
        assert isinstance(result.candidates, list)
        assert len(result.candidates) <= 5

        for cand in result.candidates:
            assert "addr_id" in cand
            assert "display_label" in cand
            assert "score" in cand

    @given(index_ref=_nonexistent_index_ref_st)
    @settings(max_examples=10)
    def test_miss_by_index_ref_contract(self, index_ref: str):
        """R5.6: 随机不存在 index_ref resolve → 满足 miss 契约。

        **Validates: Requirements 2.3, 5.6**
        """
        result = _run_resolve(index_ref=index_ref)

        assert result.found is False, (
            f"不存在的 index_ref 不应命中: {index_ref}"
        )
        assert result.candidates is not None
        assert isinstance(result.candidates, list)
        assert len(result.candidates) <= 5

        for cand in result.candidates:
            assert "addr_id" in cand
            assert "display_label" in cand
            assert "score" in cand


# ---------------------------------------------------------------------------
# Property Test 2: Ambiguous 响应契约 — found=False + error="ambiguous" + candidates
# ---------------------------------------------------------------------------


class TestAmbiguousResponseContract:
    """Property 8b: ambiguous 响应必须满足 found=False + error="ambiguous" + 全部命中条目。"""

    @given(count=_ambiguous_count_st)
    @settings(max_examples=10)
    def test_ambiguous_sheet_code_returns_all_candidates(self, count: int):
        """R2.4, R5.5: 同 sheet_code 多条目 → ambiguous 且 candidates 包含全部。

        注入含 count 个同 sheet_code 条目的 catalog，验证:
        - found=False
        - error="ambiguous"
        - candidates 数量 == count（不截断）
        - 每个 candidate 含 addr_id、display_label、score

        **Validates: Requirements 2.4, 5.5**
        """
        parent = "T1"
        sheet_code = "T1-99"

        catalog_data = _build_ambiguous_catalog(parent, sheet_code, count)
        _inject_catalog(catalog_data)

        # 用裸 sheet_code 解析（单段 → sheets_by_code 匹配多条）
        result = _run_resolve(addr_id=sheet_code)

        assert result.found is False, (
            f"ambiguous 场景不应返回 found=True: count={count}"
        )
        assert result.error == "ambiguous", (
            f"ambiguous 场景 error 应为 'ambiguous': got={result.error}"
        )
        assert result.candidates is not None, (
            "ambiguous 响应必须有 candidates"
        )
        assert isinstance(result.candidates, list)

        # candidates 数量 = 全部命中条目（不截断, R2.4）
        assert len(result.candidates) == count, (
            f"ambiguous candidates 应包含全部 {count} 条: "
            f"got={len(result.candidates)}"
        )

        # 每个 candidate 字段完整
        for i, cand in enumerate(result.candidates):
            assert "addr_id" in cand, (
                f"ambiguous candidate[{i}] 缺少 addr_id"
            )
            assert "display_label" in cand, (
                f"ambiguous candidate[{i}] 缺少 display_label"
            )
            assert "score" in cand, (
                f"ambiguous candidate[{i}] 缺少 score"
            )

    @given(count=_ambiguous_count_st)
    @settings(max_examples=10)
    def test_ambiguous_cell_returns_all_candidates(self, count: int):
        """R5.5: 同 sheet 下多个同 cell_address 候选 → ambiguous 不截断。

        注入含 count 个同 cell_address 条目的 catalog，验证 ambiguous 契约。

        **Validates: Requirements 5.5, 5.6**
        """
        parent = "T2"
        sheet_code = "T2-88"
        cell_desc = "E100"

        catalog_data = _build_ambiguous_cell_catalog(
            parent, sheet_code, cell_desc, count
        )
        _inject_catalog(catalog_data)

        # resolve addr_id = "T2/T2-88/E100" → 该 sheet 下有多个 E100
        addr_id = f"{parent}/{sheet_code}/{cell_desc}"
        result = _run_resolve(addr_id=addr_id)

        assert result.found is False, (
            f"cell ambiguous 场景不应返回 found=True: count={count}"
        )
        assert result.error == "ambiguous", (
            f"cell ambiguous 场景 error 应为 'ambiguous': got={result.error}"
        )
        assert result.candidates is not None
        assert isinstance(result.candidates, list)

        # 全部命中（不截断）
        assert len(result.candidates) == count, (
            f"cell ambiguous candidates 应包含全部 {count} 条: "
            f"got={len(result.candidates)}"
        )

        for cand in result.candidates:
            assert "addr_id" in cand
            assert "display_label" in cand
            assert "score" in cand


# ---------------------------------------------------------------------------
# Property Test 3: resolve_instance 多实例 disambiguation（R6.3）
# ---------------------------------------------------------------------------


def _make_wp_index(
    project_id: uuid.UUID,
    wp_code: str,
    wp_name: str,
    idx_id: uuid.UUID | None = None,
) -> MagicMock:
    """Create a mock WpIndex row."""
    idx = MagicMock()
    idx.id = idx_id or uuid.uuid4()
    idx.project_id = project_id
    idx.wp_code = wp_code
    idx.wp_name = wp_name
    idx.is_deleted = False
    return idx


def _make_db_multi_instances(
    project_id: uuid.UUID,
    wp_code: str,
    count: int,
) -> AsyncMock:
    """构造返回 count 条 WpIndex 的 mock DB（多实例场景）。"""
    db = AsyncMock()
    indices = [
        _make_wp_index(project_id, wp_code, f"实例{i}")
        for i in range(count)
    ]

    async def mock_execute(stmt):
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = indices
        result_mock.scalars.return_value = scalars_mock
        return result_mock

    db.execute = mock_execute
    return db


class TestResolveInstanceDisambiguation:
    """Property 8c: resolve_instance 多实例返回 disambiguation + 全部候选。"""

    @given(count=st.integers(min_value=2, max_value=4))
    @settings(max_examples=10)
    def test_multi_instance_disambiguation(self, count: int):
        """R6.3: resolve_instance 同项目多实例 → disambiguation + candidates 包含全部。

        验证:
        - found=False
        - error="disambiguation"
        - candidates 数量 == count（全部实例）

        **Validates: Requirements 2.4, 5.5**
        """
        from app.services.acnr.resolver import resolve_instance

        project_id = uuid.uuid4()
        parent_wp_code = "D2"
        sheet_code = "D2-2"

        db = _make_db_multi_instances(project_id, sheet_code, count)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                resolve_instance(
                    db=db,
                    project_id=project_id,
                    parent_wp_code=parent_wp_code,
                    sheet_code=sheet_code,
                )
            )
        finally:
            loop.close()

        assert result.found is False, (
            f"多实例不应返回 found=True: count={count}"
        )
        assert result.error == "disambiguation", (
            f"多实例 error 应为 'disambiguation': got={result.error}"
        )
        assert result.candidates is not None
        assert isinstance(result.candidates, list)

        # candidates 包含全部实例（不截断）
        assert len(result.candidates) == count, (
            f"disambiguation candidates 应包含全部 {count} 条: "
            f"got={len(result.candidates)}"
        )
