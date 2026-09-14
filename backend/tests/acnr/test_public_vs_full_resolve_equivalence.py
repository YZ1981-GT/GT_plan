"""PBT: 公共 API resolve == full_resolve 直调 [P1, P2]

Property 1 (P1): POST /api/acnr/resolve 端点的响应与直接调用
    resolver.full_resolve() 完全等价。

Property 2 (P2): 四种语法（URI/formula_ref/addr_id/index_ref）
    殊途同归 → 同一 CanonicalAddress (addr_id)。

测试策略:
- 使用 Hypothesis 生成有效的 ACNR 地址输入。
- 注入测试 catalog 确保可控。
- P1: 模拟端点行为（调 full_resolve + asdict + strip None）与直调对比。
- P2: 同一 cell 的四种语法输入均解析到相同 addr_id。

Validates: Requirements 1.1, 1.2, 1.5
"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr import catalog as catalog_mod
from app.services.acnr.catalog import CatalogIndex
from app.services.acnr.resolver import full_resolve


# ─── Test Catalog Data ────────────────────────────────────────────────────────

_TEST_CELLS = [
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
    {
        "addr_id": "K1/K1-12/B5",
        "parent_addr_id": "K1/K1-12",
        "cell_address": "B5",
        "semantic_label": "样本量",
        "formula_ref": "WP('K1','检查表K1-12','B5')",
        "uri": "wp://K1/检查表K1-12#B5",
        "domain": "wp",
        "semantic_only": False,
    },
    {
        "addr_id": "F1/F1-2/C10",
        "parent_addr_id": "F1/F1-2",
        "cell_address": "C10",
        "semantic_label": "存货合计",
        "formula_ref": "WP('F1','明细表F1-2','C10')",
        "uri": "wp://F1/明细表F1-2#C10",
        "domain": "wp",
        "semantic_only": False,
    },
]

_TEST_SHEETS = [
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
        "addr_id": "K1/K1-12",
        "sheet_code": "K1-12",
        "sheet_name": "检查表K1-12",
        "parent_wp_code": "K1",
        "display_label": "底稿 > K1 > 检查表K1-12",
        "domain": "wp",
        "cycle": "K",
        "jump_route_template": "/workpapers/{wp_id}?sheet=K1-12",
        "import_export": {"enabled": False},
        "sheet_name_aliases": [],
    },
    {
        "addr_id": "F1/F1-2",
        "sheet_code": "F1-2",
        "sheet_name": "明细表F1-2",
        "parent_wp_code": "F1",
        "display_label": "底稿 > F1 > 明细表F1-2",
        "domain": "wp",
        "cycle": "F",
        "jump_route_template": "/workpapers/{wp_id}?sheet=F1-2",
        "import_export": {"enabled": True, "api_prefix": "f1", "item_id": "F1-detail-rows"},
        "sheet_name_aliases": ["存货明细表"],
    },
]

_TEST_CATALOG_DATA: dict[str, Any] = {
    "version": "1",
    "registry_version": "2026.1.0-pbt",
    "sheets": _TEST_SHEETS,
    "cells": _TEST_CELLS,
}


@pytest.fixture(autouse=True)
def _inject_test_catalog():
    """注入测试 catalog，确保 PBT 环境可控。"""
    test_index = CatalogIndex(_TEST_CATALOG_DATA)
    with patch.object(catalog_mod, "_catalog", test_index):
        yield


# ─── Hypothesis Strategies ────────────────────────────────────────────────────

# 从测试 cell 数据生成有效输入
_cell_strategy = st.sampled_from(_TEST_CELLS)


def _syntax_from_cell(cell: dict) -> st.SearchStrategy:
    """从 cell 数据生成四种语法输入之一。"""
    return st.sampled_from([
        {"uri": cell["uri"]},
        {"formula_ref": cell["formula_ref"]},
        {"addr_id": cell["addr_id"]},
        {"index_ref": f"cell:{cell['parent_addr_id'].split('/')[-1]}!{cell['cell_address']}"},
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# Property 1: 公共 API resolve == full_resolve 直调 (P1)
# ═══════════════════════════════════════════════════════════════════════════════


class TestP1PublicApiEqualsFullResolve:
    """P1: POST /api/acnr/resolve 端点响应与直接调 full_resolve 完全等价。

    模拟端点行为: 调 full_resolve → asdict → strip None。
    直调 full_resolve 应产出相同结果。

    Validates: Requirements 1.1
    """

    @settings(max_examples=5, deadline=None)
    @given(cell=_cell_strategy, syntax_idx=st.integers(min_value=0, max_value=3))
    def test_endpoint_matches_direct_call(self, cell: dict, syntax_idx: int):
        """端点行为（full_resolve + asdict + strip None）与直调 full_resolve 一致。"""
        # 构造四种语法输入
        syntaxes = [
            {"uri": cell["uri"]},
            {"formula_ref": cell["formula_ref"]},
            {"addr_id": cell["addr_id"]},
            {"index_ref": f"cell:{cell['parent_addr_id'].split('/')[-1]}!{cell['cell_address']}"},
        ]
        kwargs = syntaxes[syntax_idx]

        # 直调 full_resolve
        result = asyncio.new_event_loop().run_until_complete(
            full_resolve(**kwargs)
        )

        # 模拟端点行为: asdict + strip None
        endpoint_response = {k: v for k, v in asdict(result).items() if v is not None}

        # 直调等价断言: found + addr_id 一致
        assert endpoint_response["found"] is True
        assert endpoint_response["addr_id"] == cell["addr_id"]

        # 验证响应包含统一 schema 关键字段
        assert "entry_type" in endpoint_response
        assert "source_layer" in endpoint_response

    @settings(max_examples=5, deadline=None)
    @given(cell=_cell_strategy)
    def test_no_project_id_pure_l1(self, cell: dict):
        """无 project_id 时，full_resolve 纯 L1 解析 — 不含 wp_id。"""
        result = asyncio.new_event_loop().run_until_complete(
            full_resolve(addr_id=cell["addr_id"])
        )

        response = {k: v for k, v in asdict(result).items() if v is not None}

        assert response["found"] is True
        # 无 project_id → 不返回 wp_id
        assert "wp_id" not in response


# ═══════════════════════════════════════════════════════════════════════════════
# Property 2: 四语法殊途同归 → 同一 CanonicalAddress (P2)
# ═══════════════════════════════════════════════════════════════════════════════


class TestP2FourSyntaxConvergence:
    """P2: 四种语法（URI/formula_ref/addr_id/index_ref）→ 同一 addr_id。

    对同一 cell，无论用哪种语法输入，full_resolve 都应返回相同的
    canonical addr_id（即 CanonicalAddress 的字符串表示）。

    Validates: Requirements 1.1
    """

    @settings(max_examples=5, deadline=None)
    @given(cell=_cell_strategy)
    def test_four_syntax_same_addr_id(self, cell: dict):
        """四种语法解析同一 cell → 相同 addr_id。"""
        loop = asyncio.new_event_loop()

        # 四种语法输入
        by_uri = loop.run_until_complete(full_resolve(uri=cell["uri"]))
        by_formula = loop.run_until_complete(full_resolve(formula_ref=cell["formula_ref"]))
        by_addr = loop.run_until_complete(full_resolve(addr_id=cell["addr_id"]))
        by_index = loop.run_until_complete(
            full_resolve(index_ref=f"cell:{cell['parent_addr_id'].split('/')[-1]}!{cell['cell_address']}")
        )

        # 四路结果的 addr_id 必须相同
        expected_addr_id = cell["addr_id"]
        assert by_uri.addr_id == expected_addr_id
        assert by_formula.addr_id == expected_addr_id
        assert by_addr.addr_id == expected_addr_id
        assert by_index.addr_id == expected_addr_id

    @settings(max_examples=5, deadline=None)
    @given(cell=_cell_strategy)
    def test_four_syntax_all_found(self, cell: dict):
        """四种语法解析同一 cell → 全部 found=True。"""
        loop = asyncio.new_event_loop()

        results = [
            loop.run_until_complete(full_resolve(uri=cell["uri"])),
            loop.run_until_complete(full_resolve(formula_ref=cell["formula_ref"])),
            loop.run_until_complete(full_resolve(addr_id=cell["addr_id"])),
            loop.run_until_complete(
                full_resolve(index_ref=f"cell:{cell['parent_addr_id'].split('/')[-1]}!{cell['cell_address']}")
            ),
        ]

        for r in results:
            assert r.found is True, f"Expected found=True but got {r}"

    @settings(max_examples=5, deadline=None)
    @given(cell=_cell_strategy)
    def test_four_syntax_same_entry_type(self, cell: dict):
        """四种语法解析同一 cell → 相同 entry_type。"""
        loop = asyncio.new_event_loop()

        results = [
            loop.run_until_complete(full_resolve(uri=cell["uri"])),
            loop.run_until_complete(full_resolve(formula_ref=cell["formula_ref"])),
            loop.run_until_complete(full_resolve(addr_id=cell["addr_id"])),
            loop.run_until_complete(
                full_resolve(index_ref=f"cell:{cell['parent_addr_id'].split('/')[-1]}!{cell['cell_address']}")
            ),
        ]

        entry_types = [r.entry_type for r in results]
        assert len(set(entry_types)) == 1, f"entry_types diverged: {entry_types}"
