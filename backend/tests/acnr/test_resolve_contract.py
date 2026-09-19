"""ACNR lookup/resolve 响应契约单元测试（表驱动 RC-01..RC-12 只读 M0 子集）。

覆盖：
- RC-01: lookup 正向命中（sheet_code → found:true + addr_id + entry_type）
- RC-02: 别名反查命中（alias → 唯一 sheet_code）
- RC-03: resolve by formula_ref（WP 3 参）
- RC-04: resolve by uri
- RC-05: resolve by addr_id
- RC-09: miss（unknown ref → found:false + candidates）
- RC-11: resolve by index_ref（cell:D2-2!E100）

测试方法：
- 注入 fixture catalog 匹配 resolve_cases.json 的期望数据
- pytest parametrize 表驱动
- 断言响应满足契约（found, addr_id, entry_type）

Requirements: 2.1, 2.2, 2.3, 2.4
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# 确保 backend 在 path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr import catalog as catalog_mod
from app.services.acnr.catalog import (
    CatalogIndex,
    lookup,
    reload_catalog,
    resolve,
)


# ─── Fixture: 与 resolve_cases.json 对齐的测试 catalog 数据 ─────────────────

_TEST_CATALOG_DATA: dict[str, Any] = {
    "version": "1",
    "registry_version": "2026.1.0-test",
    "sheets": [
        {
            "addr_id": "D2/D2-1",
            "sheet_code": "D2-1",
            "sheet_name": "审定表D2-1",
            "parent_wp_code": "D2",
            "display_label": "底稿 > D2 > 审定表D2-1",
            "domain": "wp",
            "cycle": "D",
            "jump_route_template": "/workpapers/{wp_id}?sheet=D2-1",
            "import_export": {"enabled": True, "api_prefix": "d2", "item_id": "D2-adjudication"},
            "sheet_name_aliases": [],
        },
        {
            "addr_id": "D2/D2-2",
            "sheet_code": "D2-2",
            "sheet_name": "明细表D2-2",
            "parent_wp_code": "D2",
            "display_label": "底稿 > D2 > 明细表D2-2",
            "domain": "wp",
            "cycle": "D",
            "jump_route_template": "/workpapers/{wp_id}?sheet=D2-2",
            "import_export": {"enabled": True, "api_prefix": "d2", "item_id": "D2-detail-rows"},
            "sheet_name_aliases": ["应收账款明细表"],
        },
        {
            "addr_id": "D2/D2-3",
            "sheet_code": "D2-3",
            "sheet_name": "检查表D2-3",
            "parent_wp_code": "D2",
            "display_label": "底稿 > D2 > 检查表D2-3",
            "domain": "wp",
            "cycle": "D",
            "jump_route_template": "/workpapers/{wp_id}?sheet=D2-3",
            "import_export": {"enabled": False},
            "sheet_name_aliases": [],
        },
        # RC-10 ambiguous: 同一 sheet_code 在多个 parent 下
        {
            "addr_id": "D3/AMB-1",
            "sheet_code": "AMB-1",
            "sheet_name": "测试表AMB-1",
            "parent_wp_code": "D3",
            "display_label": "底稿 > D3 > 测试表AMB-1",
            "domain": "wp",
            "cycle": "D",
            "jump_route_template": "/workpapers/{wp_id}?sheet=AMB-1",
            "sheet_name_aliases": [],
        },
        {
            "addr_id": "F2/AMB-1",
            "sheet_code": "AMB-1",
            "sheet_name": "分析表AMB-1",
            "parent_wp_code": "F2",
            "display_label": "底稿 > F2 > 分析表AMB-1",
            "domain": "wp",
            "cycle": "F",
            "jump_route_template": "/workpapers/{wp_id}?sheet=AMB-1",
            "sheet_name_aliases": [],
        },
    ],
    "cells": [
        {
            "addr_id": "D2/D2-2/E100",
            "parent_addr_id": "D2/D2-2",
            "cell_address": "E100",
            "semantic_label": "合计行-期末余额",
            "formula_ref": "WP('D2','明细表D2-2','E100')",
            "uri": "wp://D2/明细表D2-2#E100",
            "domain": "wp",
            "semantic_only": False,
        },
    ],
}


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _inject_test_catalog():
    """注入测试 catalog 数据，测试结束后恢复。"""
    test_index = CatalogIndex(_TEST_CATALOG_DATA)
    with patch.object(catalog_mod, "_catalog", test_index):
        yield


# ─── 加载 resolve_cases.json ──────────────────────────────────────────────────

_FIXTURES_PATH = Path(__file__).resolve().parents[3] / "docs" / "acnr" / "fixtures" / "resolve_cases.json"


def _load_resolve_cases() -> dict[str, dict]:
    """加载 RC cases 为 {id: case} dict。"""
    with open(_FIXTURES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {c["id"]: c for c in data["cases"]}


_RC = _load_resolve_cases()


# ─── RC-01: lookup 正向命中 ──────────────────────────────────────────────────


class TestRC01LookupHit:
    """RC-01: sheet_code → found:true + addr_id + entry_type + import_export。

    Validates: Requirements 2.1, 2.2
    """

    def test_lookup_by_sheet_code_found(self):
        """lookup(sheet='D2-2') → found=True, addr_id=D2/D2-2, entry_type=sheet。"""
        case = _RC["RC-01"]
        result = lookup(sheet=case["input"]["sheet_code"])

        assert result["found"] is True
        assert result["addr_id"] == case["expected_output"]["addr_id"]
        assert result["entry_type"] == case["expected_output"]["entry_type"]

    def test_lookup_returns_sheet_name(self):
        """命中时返回 sheet_name。"""
        result = lookup(sheet="D2-2")
        assert result["sheet_name"] == "明细表D2-2"

    def test_lookup_returns_parent_wp_code(self):
        """命中时返回 parent_wp_code。"""
        result = lookup(sheet="D2-2")
        assert result["parent_wp_code"] == "D2"

    def test_lookup_returns_import_export(self):
        """命中时返回 import_export 段（含 api_prefix + item_id）。"""
        case = _RC["RC-01"]
        result = lookup(sheet=case["input"]["sheet_code"])

        assert "import_export" in result
        ie = result["import_export"]
        expected_ie = case["expected_output"]["import_export"]
        assert ie["enabled"] is expected_ie["enabled"]
        assert ie["api_prefix"] == expected_ie["api_prefix"]
        assert ie["item_id"] == expected_ie["item_id"]


# ─── RC-02: 别名反查命中 ─────────────────────────────────────────────────────


class TestRC02AliasLookup:
    """RC-02: alias '应收账款明细表' → 唯一 sheet_code D2-2。

    Validates: Requirement 3.1 (别名反查)
    """

    def test_alias_reverse_lookup_hit(self):
        """lookup(sheet='应收账款明细表') → D2/D2-2。"""
        case = _RC["RC-02"]
        # lookup API 通过 sheet 参数接受别名
        result = lookup(sheet=case["input"]["alias"])

        assert result["found"] is True
        assert result["addr_id"] == case["expected_output"]["addr_id"]
        assert result["entry_type"] == case["expected_output"]["entry_type"]
        assert result["sheet_code"] == case["expected_output"]["sheet_code"]


# ─── RC-03: resolve by formula_ref (WP 三参) ────────────────────────────────


class TestRC03ResolveFormulaRef:
    """RC-03: WP('D2','明细表D2-2','E100') → addr_id=D2/D2-2/E100。

    Validates: Requirements 5.1, 5.3
    """

    def test_resolve_formula_ref_hit(self):
        """resolve(formula_ref=WP('D2','明细表D2-2','E100')) → cell 命中。"""
        case = _RC["RC-03"]
        result = resolve(formula_ref=case["input"]["formula_ref"])

        assert result["found"] is True
        assert result["addr_id"] == case["expected_output"]["addr_id"]
        assert result["entry_type"] == case["expected_output"]["entry_type"]

    def test_resolve_formula_ref_returns_cell_fields(self):
        """命中 cell 时返回 cell_address + semantic_label + formula_ref + uri。"""
        case = _RC["RC-03"]
        result = resolve(formula_ref=case["input"]["formula_ref"])

        expected = case["expected_output"]
        assert result["cell_address"] == expected["cell_address"]
        assert result["semantic_label"] == expected["semantic_label"]
        assert result["formula_ref"] == expected["formula_ref"]
        assert result["uri"] == expected["uri"]


# ─── RC-04: resolve by uri ───────────────────────────────────────────────────


class TestRC04ResolveUri:
    """RC-04: wp://D2/明细表D2-2#E100 → same addr_id as RC-03。

    Validates: Requirements 5.1, 5.3 (殊途同归 Property 4)
    """

    def test_resolve_uri_hit(self):
        """resolve(uri=wp://D2/明细表D2-2#E100) → D2/D2-2/E100。"""
        case = _RC["RC-04"]
        result = resolve(uri=case["input"]["uri"])

        assert result["found"] is True
        assert result["addr_id"] == case["expected_output"]["addr_id"]
        assert result["entry_type"] == case["expected_output"]["entry_type"]

    def test_resolve_uri_convergence_with_formula_ref(self):
        """RC-03 和 RC-04 解析到相同 addr_id（殊途同归）。"""
        rc03 = resolve(formula_ref=_RC["RC-03"]["input"]["formula_ref"])
        rc04 = resolve(uri=_RC["RC-04"]["input"]["uri"])

        assert rc03["addr_id"] == rc04["addr_id"]


# ─── RC-05: resolve by addr_id ───────────────────────────────────────────────


class TestRC05ResolveAddrId:
    """RC-05: 直接传 addr_id D2/D2-2/E100 → same result。

    Validates: Requirements 5.1, 5.3
    """

    def test_resolve_addr_id_hit(self):
        """resolve(addr_id='D2/D2-2/E100') → cell 命中。"""
        case = _RC["RC-05"]
        result = resolve(addr_id=case["input"]["addr_id"])

        assert result["found"] is True
        assert result["addr_id"] == case["expected_output"]["addr_id"]
        assert result["entry_type"] == case["expected_output"]["entry_type"]

    def test_resolve_addr_id_convergence(self):
        """RC-03/04/05 三种语法解析到同一 addr_id（殊途同归）。"""
        rc03 = resolve(formula_ref=_RC["RC-03"]["input"]["formula_ref"])
        rc04 = resolve(uri=_RC["RC-04"]["input"]["uri"])
        rc05 = resolve(addr_id=_RC["RC-05"]["input"]["addr_id"])

        assert rc03["addr_id"] == rc04["addr_id"] == rc05["addr_id"]


# ─── RC-09: miss + candidates ────────────────────────────────────────────────


class TestRC09Miss:
    """RC-09: 未知 ref → found:false + candidates ≤ 5。

    Validates: Requirements 2.3, 5.6
    """

    def test_resolve_unknown_ref_miss(self):
        """resolve(formula_ref=WP('D2','不存在的表','X999')) → found=False。"""
        case = _RC["RC-09"]
        result = resolve(formula_ref=case["input"]["formula_ref"])

        assert result["found"] is False

    def test_miss_has_candidates(self):
        """miss 返回 candidates 列表（非空）。"""
        case = _RC["RC-09"]
        result = resolve(formula_ref=case["input"]["formula_ref"])

        assert "candidates" in result
        assert isinstance(result["candidates"], list)

    def test_candidates_max_5(self):
        """candidates 最多 5 条。"""
        case = _RC["RC-09"]
        result = resolve(formula_ref=case["input"]["formula_ref"])

        assert len(result["candidates"]) <= 5

    def test_candidate_structure(self):
        """每条 candidate 含 addr_id + display_label + score。"""
        case = _RC["RC-09"]
        result = resolve(formula_ref=case["input"]["formula_ref"])

        for cand in result["candidates"]:
            assert "addr_id" in cand
            assert "display_label" in cand
            assert "score" in cand


# ─── RC-10: ambiguous ────────────────────────────────────────────────────────


class TestRC10Ambiguous:
    """RC-10: 同一 sheet_code 多命中 → found:false + error:ambiguous + candidates。

    Validates: Requirements 2.4, 5.5
    """

    def test_ambiguous_lookup(self):
        """lookup(sheet='AMB-1') → found=False, error='ambiguous'。"""
        case = _RC["RC-10"]
        result = lookup(sheet=case["input"]["sheet_code"])

        assert result["found"] is False
        assert result.get("error") == "ambiguous"

    def test_ambiguous_candidates_complete(self):
        """ambiguous 候选列表包含全部命中项。"""
        case = _RC["RC-10"]
        result = lookup(sheet=case["input"]["sheet_code"])

        expected_candidates = case["expected_output"]["candidates"]
        assert len(result["candidates"]) == len(expected_candidates)

        result_addr_ids = {c["addr_id"] for c in result["candidates"]}
        expected_addr_ids = {c["addr_id"] for c in expected_candidates}
        assert result_addr_ids == expected_addr_ids


# ─── RC-11: resolve by index_ref (cell:D2-2!E100) ───────────────────────────


class TestRC11ResolveIndexRef:
    """RC-11: cell:D2-2!E100 → same addr_id as RC-03/04/05。

    Validates: Requirements 11.3, 5.3
    """

    def test_resolve_index_ref_cell_hit(self):
        """resolve(index_ref='cell:D2-2!E100') → D2/D2-2/E100。"""
        case = _RC["RC-11"]
        result = resolve(index_ref=case["input"]["index_ref"])

        assert result["found"] is True
        assert result["addr_id"] == case["expected_output"]["addr_id"]
        assert result["entry_type"] == case["expected_output"]["entry_type"]

    def test_index_ref_convergence_with_all(self):
        """RC-03/04/05/11 四种语法解析到同一 addr_id（殊途同归 Property 4）。"""
        rc03 = resolve(formula_ref=_RC["RC-03"]["input"]["formula_ref"])
        rc04 = resolve(uri=_RC["RC-04"]["input"]["uri"])
        rc05 = resolve(addr_id=_RC["RC-05"]["input"]["addr_id"])
        rc11 = resolve(index_ref=_RC["RC-11"]["input"]["index_ref"])

        assert rc03["addr_id"] == rc04["addr_id"] == rc05["addr_id"] == rc11["addr_id"]
        assert rc03["addr_id"] == "D2/D2-2/E100"


# ─── 殊途同归收敛断言 ────────────────────────────────────────────────────────


class TestConvergenceD2E100:
    """convergence_group D2-2-E100: 四种语法同一目标。

    对应 resolve_cases.json 中 convergence_assertions[0]。
    """

    def test_all_resolve_to_same_addr_id(self):
        """RC-03/04/05/11 全部 resolve 到 canonical addr_id 'D2/D2-2/E100'。"""
        results = [
            resolve(formula_ref="WP('D2','明细表D2-2','E100')"),
            resolve(uri="wp://D2/明细表D2-2#E100"),
            resolve(addr_id="D2/D2-2/E100"),
            resolve(index_ref="cell:D2-2!E100"),
        ]
        addr_ids = [r["addr_id"] for r in results]
        # 所有结果一致
        assert all(aid == "D2/D2-2/E100" for aid in addr_ids)
        # 所有都命中
        assert all(r["found"] is True for r in results)
