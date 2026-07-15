"""公共 Resolve 端点 API 契约基线测试 — Task 1 [Req-1, P1]

记录 GET /api/acnr/resolve 公共端点当前返回值 baseline（5 个金样例）：
  1. URI 语法输入
  2. formula_ref 语法输入
  3. addr_id 语法输入
  4. index_ref 语法输入
  5. 非 wp 域（tb/report/note/aux）

目的：Task 3 将端点改为调用 full_resolve 时，本文件的 baseline 断言应保持
一致（P1: 公共 API resolve == full_resolve 直调），若有差异则说明收敛成功。

当前行为：端点直接调用 catalog.resolve()（只走 L1），不支持 project_id/wp_id。

Validates: Requirements 1.1, 1.2, 1.5
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr import catalog as catalog_mod
from app.services.acnr.catalog import CatalogIndex, resolve


# ─── 测试用 catalog 数据 ─────────────────────────────────────────────────────

_TEST_CATALOG_DATA: dict[str, Any] = {
    "version": "1",
    "registry_version": "2026.1.0-baseline",
    "sheets": [
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
    ],
}


@pytest.fixture(autouse=True)
def _inject_test_catalog():
    """注入测试 catalog 数据，测试结束后恢复。"""
    test_index = CatalogIndex(_TEST_CATALOG_DATA)
    with patch.object(catalog_mod, "_catalog", test_index):
        yield


# ═══════════════════════════════════════════════════════════════════════════════
# 金样例 1: URI 语法
# ═══════════════════════════════════════════════════════════════════════════════


class TestGoldenUriSyntax:
    """金样例 1: 通过 URI 语法解析 — 记录当前 baseline。

    输入: uri="wp://D2/明细表D2-2#E100"
    期望: 当前端点返回 L1 cell 精确命中结果。

    Validates: Requirements 1.1
    """

    def test_uri_resolve_found(self):
        """URI 解析命中：found=True + addr_id + entry_type=cell。"""
        result = resolve(uri="wp://D2/明细表D2-2#E100")

        assert result["found"] is True
        assert result["addr_id"] == "D2/D2-2/E100"
        assert result["entry_type"] == "cell"

    def test_uri_resolve_baseline_fields(self):
        """URI 解析命中后返回完整字段集（cell 级别）。"""
        result = resolve(uri="wp://D2/明细表D2-2#E100")

        # Baseline: 当前 catalog.resolve 返回 cell 级别的字段
        assert result["cell_address"] == "E100"
        assert result["semantic_label"] == "合计行-期末余额"
        assert result["formula_ref"] == "WP('D2','明细表D2-2','E100')"
        assert result["uri"] == "wp://D2/明细表D2-2#E100"


# ═══════════════════════════════════════════════════════════════════════════════
# 金样例 2: formula_ref 语法
# ═══════════════════════════════════════════════════════════════════════════════


class TestGoldenFormulaRefSyntax:
    """金样例 2: 通过 WP() 公式引用解析 — 记录当前 baseline。

    输入: formula_ref="WP('D2','明细表D2-2','E100')"
    期望: 与 URI 语法殊途同归。

    Validates: Requirements 1.1
    """

    def test_formula_ref_resolve_found(self):
        """formula_ref 解析命中：found=True + addr_id。"""
        result = resolve(formula_ref="WP('D2','明细表D2-2','E100')")

        assert result["found"] is True
        assert result["addr_id"] == "D2/D2-2/E100"
        assert result["entry_type"] == "cell"

    def test_formula_ref_converges_with_uri(self):
        """formula_ref 与 uri 殊途同归（同一 addr_id）。"""
        by_formula = resolve(formula_ref="WP('D2','明细表D2-2','E100')")
        by_uri = resolve(uri="wp://D2/明细表D2-2#E100")

        assert by_formula["addr_id"] == by_uri["addr_id"]


# ═══════════════════════════════════════════════════════════════════════════════
# 金样例 3: addr_id 语法
# ═══════════════════════════════════════════════════════════════════════════════


class TestGoldenAddrIdSyntax:
    """金样例 3: 直接传 addr_id 解析 — 记录当前 baseline。

    输入: addr_id="D2/D2-2/E100"
    期望: 直接精确匹配 cell。

    Validates: Requirements 1.1
    """

    def test_addr_id_resolve_found(self):
        """addr_id 解析命中：found=True + 同一 addr_id。"""
        result = resolve(addr_id="D2/D2-2/E100")

        assert result["found"] is True
        assert result["addr_id"] == "D2/D2-2/E100"
        assert result["entry_type"] == "cell"

    def test_addr_id_converges_with_all(self):
        """addr_id / uri / formula_ref 三路殊途同归。"""
        by_addr = resolve(addr_id="D2/D2-2/E100")
        by_uri = resolve(uri="wp://D2/明细表D2-2#E100")
        by_formula = resolve(formula_ref="WP('D2','明细表D2-2','E100')")

        assert by_addr["addr_id"] == by_uri["addr_id"] == by_formula["addr_id"]


# ═══════════════════════════════════════════════════════════════════════════════
# 金样例 4: index_ref 语法
# ═══════════════════════════════════════════════════════════════════════════════


class TestGoldenIndexRefSyntax:
    """金样例 4: 通过索引语法 cell:D2-2!E100 解析 — 记录当前 baseline。

    输入: index_ref="cell:D2-2!E100"
    期望: 解析到同一 cell addr_id。

    Validates: Requirements 1.1
    """

    def test_index_ref_resolve_found(self):
        """index_ref 解析命中：found=True + addr_id。"""
        result = resolve(index_ref="cell:D2-2!E100")

        assert result["found"] is True
        assert result["addr_id"] == "D2/D2-2/E100"
        assert result["entry_type"] == "cell"

    def test_index_ref_four_syntax_convergence(self):
        """四种语法（URI/formula_ref/addr_id/index_ref）殊途同归。"""
        results = [
            resolve(uri="wp://D2/明细表D2-2#E100"),
            resolve(formula_ref="WP('D2','明细表D2-2','E100')"),
            resolve(addr_id="D2/D2-2/E100"),
            resolve(index_ref="cell:D2-2!E100"),
        ]
        addr_ids = [r["addr_id"] for r in results]
        assert all(aid == "D2/D2-2/E100" for aid in addr_ids)
        assert all(r["found"] is True for r in results)


# ═══════════════════════════════════════════════════════════════════════════════
# 金样例 5: 非 wp 域（tb/report/note/aux）
# ═══════════════════════════════════════════════════════════════════════════════


class TestGoldenNonWpDomain:
    """金样例 5: 非 wp 域输入 — 记录当前 baseline。

    当前行为（L1 only）：catalog.resolve 不含非 wp 域条目，
    输入非 wp 域语法时返回 found=False（miss）。

    Task 3 改为 full_resolve 后，非 wp 域将经 V1 委托返回 found=True。
    本 baseline 记录当前的 miss 行为，后续可对比收敛效果。

    Validates: Requirements 1.5
    """

    def test_non_wp_uri_tb_domain_miss(self):
        """非 wp 域 URI（tb://1001#审定数）→ 当前 catalog.resolve miss。"""
        result = resolve(uri="tb://1001#审定数")

        # Baseline: catalog 无 tb 域条目 → miss
        assert result["found"] is False

    def test_non_wp_formula_ref_report_domain_miss(self):
        """非 wp 域公式引用（ROW('BS-1')）→ 当前 catalog.resolve miss。"""
        result = resolve(formula_ref="ROW('BS-1')")

        # Baseline: catalog 无 report 域条目 → miss
        assert result["found"] is False

    def test_non_wp_index_ref_note_domain_miss(self):
        """非 wp 域索引语法（Note:五、3）→ 当前 catalog.resolve miss。"""
        result = resolve(index_ref="Note:五、3")

        # Baseline: catalog 无 note 域条目 → miss
        assert result["found"] is False

    def test_non_wp_miss_returns_candidates(self):
        """非 wp 域 miss 返回 candidates 列表（可能为空）。"""
        result = resolve(uri="tb://1001#审定数")

        assert "candidates" in result
        assert isinstance(result["candidates"], list)
        # candidates 最多 5 条
        assert len(result["candidates"]) <= 5
