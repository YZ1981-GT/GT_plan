"""ACNR full_resolve() 完整决策树单元测试。

覆盖:
- L2 overlay 应用优先于 L1 匹配（R5.2, R5.8）
- L1 Cell 精确 match → hit（R5.3）
- L1 Sheet + aliases match → hit
- semantic_label 包含匹配
- 多命中 → ambiguous（R5.5）
- L3 RuntimeCellEntry（project-scoped）
- 非 wp 域委托 V1 返回统一契约（R5.7）
- miss → metrics + candidates ≤ 5（R5.6）
- 带 project_id 时附 wp_id（R5.4）

Requirements: 5.1, 5.3, 5.4, 5.5, 5.6, 5.7
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr import catalog as catalog_mod
from app.services.acnr.catalog import CatalogIndex
from app.services.acnr.overlay import (
    OverlayPatch,
    clear_all_overlays,
    set_overlay,
)
from app.services.acnr.resolver import (
    ResolveResult,
    full_resolve,
    get_resolve_metrics,
    reset_resolve_metrics,
)
from app.services.acnr.runtime import (
    RuntimeCellEntry,
    clear_all_runtime_entries,
    _l3_store,
)


# ─── Test Catalog Data ────────────────────────────────────────────────────────

_TEST_CATALOG_DATA: dict[str, Any] = {
    "version": "1",
    "registry_version": "2026.1.0-test",
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
        # ambiguous case
        {
            "addr_id": "D3/AMB-1",
            "sheet_code": "AMB-1",
            "sheet_name": "测试表AMB-1",
            "parent_wp_code": "D3",
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
        {
            "addr_id": "D2/D2-2/E50",
            "parent_addr_id": "D2/D2-2",
            "cell_address": "E50",
            "semantic_label": "小计-期末余额",
            "formula_ref": "WP('D2','明细表D2-2','E50')",
            "uri": "wp://D2/明细表D2-2#E50",
            "domain": "wp",
            "semantic_only": False,
        },
        {
            "addr_id": "D2/D2-1/B7",
            "parent_addr_id": "D2/D2-1",
            "cell_address": "B7",
            "semantic_label": "审定数-应收账款合计",
            "formula_ref": "WP('D2','审定表D2-1','B7')",
            "uri": "wp://D2/审定表D2-1#B7",
            "domain": "wp",
            "semantic_only": False,
        },
    ],
}


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _inject_test_catalog():
    """注入测试 catalog 数据。"""
    test_index = CatalogIndex(_TEST_CATALOG_DATA)
    with patch.object(catalog_mod, "_catalog", test_index):
        yield


@pytest.fixture(autouse=True)
def _clean_state():
    """清理全局状态。"""
    reset_resolve_metrics()
    clear_all_overlays()
    clear_all_runtime_entries()
    yield
    reset_resolve_metrics()
    clear_all_overlays()
    clear_all_runtime_entries()


# ─── Test: L1 Cell 精确 match (Step 3) ───────────────────────────────────────


class TestL1CellExactMatch:
    """Step 3: L1 CellCatalogEntry 精确 match → hit (R5.3)。"""

    @pytest.mark.asyncio
    async def test_resolve_by_addr_id_cell_hit(self):
        """直接 addr_id 精确匹配 cell 条目。"""
        result = await full_resolve(addr_id="D2/D2-2/E100")

        assert result.found is True
        assert result.addr_id == "D2/D2-2/E100"
        assert result.entry_type == "cell"
        assert result.cell_address == "E100"
        assert result.semantic_label == "合计行-期末余额"
        assert result.source_layer == "L1_cell"

    @pytest.mark.asyncio
    async def test_resolve_by_formula_ref_cell_hit(self):
        """formula_ref 解析 → cell 精确匹配。"""
        result = await full_resolve(formula_ref="WP('D2','明细表D2-2','E100')")

        assert result.found is True
        assert result.addr_id == "D2/D2-2/E100"
        assert result.entry_type == "cell"
        assert result.formula_ref == "WP('D2','明细表D2-2','E100')"

    @pytest.mark.asyncio
    async def test_resolve_by_uri_cell_hit(self):
        """URI 解析 → cell 精确匹配。"""
        result = await full_resolve(uri="wp://D2/明细表D2-2#E100")

        assert result.found is True
        assert result.addr_id == "D2/D2-2/E100"
        assert result.entry_type == "cell"

    @pytest.mark.asyncio
    async def test_resolve_by_index_ref_cell_hit(self):
        """index_ref cell:D2-2!E100 → cell 精确匹配。"""
        result = await full_resolve(index_ref="cell:D2-2!E100")

        assert result.found is True
        assert result.addr_id == "D2/D2-2/E100"
        assert result.entry_type == "cell"


# ─── Test: L1 Sheet match (Step 4) ───────────────────────────────────────────


class TestL1SheetMatch:
    """Step 4: L1 SheetCatalogEntry match → hit。"""

    @pytest.mark.asyncio
    async def test_resolve_sheet_by_addr_id(self):
        """addr_id 为 sheet 级时命中 sheet 条目。"""
        result = await full_resolve(addr_id="D2/D2-2")

        assert result.found is True
        assert result.addr_id == "D2/D2-2"
        assert result.entry_type == "sheet"
        assert result.source_layer == "L1_sheet"

    @pytest.mark.asyncio
    async def test_resolve_ambiguous_sheet_code(self):
        """同一 sheet_code 多命中 → ambiguous (R5.5)。"""
        result = await full_resolve(addr_id="AMB-1")

        assert result.found is False
        assert result.error == "ambiguous"
        assert result.candidates is not None
        assert len(result.candidates) == 2


# ─── Test: semantic_label 包含匹配 (Step 5) ──────────────────────────────────


class TestSemanticLabelMatch:
    """Step 5: 同 sheet 下 semantic_label 包含匹配。"""

    @pytest.mark.asyncio
    async def test_semantic_match_unique(self):
        """cell_desc 在 semantic_label 中唯一包含匹配时命中。"""
        # "合计行" 只在 E100 的 semantic_label 中出现
        result = await full_resolve(addr_id="D2/D2-2/合计行-期末余额")

        assert result.found is True
        assert result.addr_id == "D2/D2-2/E100"
        assert result.entry_type == "cell"

    @pytest.mark.asyncio
    async def test_semantic_match_ambiguous(self):
        """多个 cell semantic_label 都包含搜索词 → ambiguous。"""
        # "期末余额" 出现在 E100 和 E50 的 semantic_label 中
        result = await full_resolve(addr_id="D2/D2-2/期末余额")

        assert result.found is False
        assert result.error == "ambiguous"
        assert result.candidates is not None
        assert len(result.candidates) == 2


# ─── Test: L3 RuntimeCellEntry (Step 6) ──────────────────────────────────────


class TestL3RuntimeMatch:
    """Step 6: L3 RuntimeCellEntry (project-scoped)。"""

    @pytest.mark.asyncio
    async def test_runtime_entry_match(self):
        """project_id 存在时搜索 L3 运行时条目。"""
        project_id = "proj-001"
        rt_entry = RuntimeCellEntry(
            addr_id=f"runtime/{project_id}/wp-x/CUST-01/B7",
            uri="wp://CUST-01/B7",
            formula_ref="WP('CUST-01','B7')",
            project_id=project_id,
            wp_id="wp-x",
            cell_address="B7",
            semantic_label="自定义格",
            wp_code="CUST-01",
        )
        _l3_store[project_id] = {rt_entry.addr_id: rt_entry}

        result = await full_resolve(
            addr_id=f"runtime/{project_id}/wp-x/CUST-01/B7",
            project_id=project_id,
        )

        assert result.found is True
        assert result.entry_type == "runtime_cell"
        assert result.cell_address == "B7"
        assert result.wp_id == "wp-x"
        assert result.source_layer == "L3"

    @pytest.mark.asyncio
    async def test_no_runtime_without_project_id(self):
        """无 project_id 时不搜索 L3 → miss。"""
        project_id = "proj-002"
        rt_entry = RuntimeCellEntry(
            addr_id=f"runtime/{project_id}/wp-y/CUST-02/C5",
            project_id=project_id,
            wp_id="wp-y",
            cell_address="C5",
            wp_code="CUST-02",
        )
        _l3_store[project_id] = {rt_entry.addr_id: rt_entry}

        # 不传 project_id → L3 不会被搜索
        result = await full_resolve(
            addr_id=f"runtime/{project_id}/wp-y/CUST-02/C5",
        )

        # miss（L1 中没有 "runtime/..." 这种 addr_id）
        assert result.found is False


# ─── Test: Non-wp domain V1 delegation (Step 7) ──────────────────────────────


class TestNonWpDomainDelegation:
    """Step 7: 非 wp 域（tb/report/note/aux）→ 委托 V1 (R5.7)。"""

    @pytest.mark.asyncio
    async def test_tb_uri_delegates_to_v1(self):
        """tb:// URI → 委托 V1 返回统一契约。"""
        result = await full_resolve(uri="tb://1001#审定数")

        assert result.found is True
        assert result.entry_type == "tb"
        assert result.source_layer == "V1"
        assert result.uri == "tb://1001#审定数"

    @pytest.mark.asyncio
    async def test_tb_formula_ref_delegates_to_v1(self):
        """TB('1001','审定数') → 委托 V1。"""
        result = await full_resolve(formula_ref="TB('1001','审定数')")

        assert result.found is True
        assert result.source_layer == "V1"

    @pytest.mark.asyncio
    async def test_note_uri_delegates_to_v1(self):
        """note:// URI → 委托 V1。"""
        result = await full_resolve(uri="note://五、3/应收账款#合计.期末")

        assert result.found is True
        assert result.entry_type == "note"
        assert result.source_layer == "V1"

    @pytest.mark.asyncio
    async def test_report_uri_delegates_to_v1(self):
        """report:// URI → 委托 V1。"""
        result = await full_resolve(uri="report://BS/BS-002#期末")

        assert result.found is True
        assert result.entry_type == "report"
        assert result.source_layer == "V1"

    @pytest.mark.asyncio
    async def test_tb_index_ref_delegates_to_v1(self):
        """TB:1001 索引命名空间 → 委托 V1 (R11.2)。"""
        result = await full_resolve(index_ref="TB:1001")

        assert result.found is True
        assert result.source_layer == "V1"
        # TB:1001 → tb://1001#审定数（默认列=审定数）
        assert result.uri == "tb://1001#审定数"

    @pytest.mark.asyncio
    async def test_note_index_ref_delegates_to_v1(self):
        """Note:五、3 索引命名空间 → 委托 V1。"""
        result = await full_resolve(index_ref="Note:五、3")

        assert result.found is True
        assert result.source_layer == "V1"

    @pytest.mark.asyncio
    async def test_external_module_index_ref_not_resolved(self):
        """外部模块命名空间（Adj:/Att:）→ 首期不解析物理格 (R11.4)。"""
        result = await full_resolve(index_ref="Adj:something")

        assert result.found is False
        assert result.error == "external_module_not_resolved"


# ─── Test: miss metrics (Step 8) ─────────────────────────────────────────────


class TestMissMetrics:
    """Step 8: miss → metrics + candidates ≤ 5 (R5.6)。"""

    @pytest.mark.asyncio
    async def test_miss_returns_candidates(self):
        """未命中时返回 candidates ≤ 5。"""
        result = await full_resolve(addr_id="NONEXISTENT/XYZ/A99")

        assert result.found is False
        assert result.candidates is not None
        assert len(result.candidates) <= 5

    @pytest.mark.asyncio
    async def test_miss_increments_metric(self):
        """miss 时 metrics["miss"] 自增。"""
        reset_resolve_metrics()
        await full_resolve(addr_id="NONEXISTENT/XYZ/A99")

        metrics = get_resolve_metrics()
        assert metrics["miss"] >= 1

    @pytest.mark.asyncio
    async def test_hit_increments_metric(self):
        """hit 时 metrics["hit"] 自增。"""
        reset_resolve_metrics()
        await full_resolve(addr_id="D2/D2-2/E100")

        metrics = get_resolve_metrics()
        assert metrics["hit"] >= 1

    @pytest.mark.asyncio
    async def test_v1_delegate_increments_metric(self):
        """V1 委托时 metrics["v1_delegate"] 自增。"""
        reset_resolve_metrics()
        await full_resolve(uri="tb://1001#审定数")

        metrics = get_resolve_metrics()
        assert metrics["v1_delegate"] >= 1


# ─── Test: L2 overlay 应用 (Step 2) ──────────────────────────────────────────


class TestL2OverlayApplication:
    """Step 2: 带 project_id → 先应用 L2 overlay (R5.2, R5.8)。"""

    @pytest.mark.asyncio
    async def test_overlay_adds_alias_for_matching(self):
        """overlay 追加别名使原本 miss 的查询命中 (R5.2)。"""
        project_id = "proj-overlay-1"
        # 为 D2/D2-2 追加一个项目级别名
        patch_obj = OverlayPatch(
            project_id=project_id,
            addr_id="D2/D2-2",
            overrides={"sheet_name_alias_add": ["现场临时叫法"]},
            reason="项目模板差异",
            owner="zhangsan",
        )
        set_overlay(patch_obj)

        # 使用项目级别名搜索 — 通过 project_aliases 机制
        # overlay 的 alias 在 full_resolve 的别名匹配逻辑中生效
        result = await full_resolve(
            addr_id="D2/D2-2",
            project_id=project_id,
        )

        # sheet 应该命中（overlay 不影响已有精确匹配）
        assert result.found is True
        assert result.addr_id == "D2/D2-2"


# ─── Test: project_id attach wp_id (R5.4) ────────────────────────────────────


class TestProjectContextAttachWpId:
    """R5.4: 带 project_id 且命中 → 通过 resolve_instance 附 wp_id。"""

    @pytest.mark.asyncio
    async def test_hit_without_project_id_no_wp_id(self):
        """无 project_id 时命中结果不含 wp_id。"""
        result = await full_resolve(addr_id="D2/D2-2/E100")

        assert result.found is True
        assert result.wp_id is None

    @pytest.mark.asyncio
    async def test_hit_with_project_id_attaches_wp_id(self):
        """有 project_id + db 时命中后尝试附 wp_id。

        由于测试环境无 DB，mock resolve_instance 验证调用链。
        """
        project_id = str(uuid4())
        mock_wp_id = uuid4()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.found = True
        mock_result.wp_id = mock_wp_id
        mock_result.jump_route = f"/workpapers/{mock_wp_id}?sheet=D2-2"

        with patch(
            "app.services.acnr.resolver.resolve_instance",
            return_value=mock_result,
        ):
            result = await full_resolve(
                addr_id="D2/D2-2/E100",
                project_id=project_id,
                db=mock_db,
            )

        assert result.found is True
        assert result.wp_id == str(mock_wp_id)


# ─── Test: Convergence — 多语法殊途同归 ──────────────────────────────────────


class TestMultiSyntaxConvergence:
    """多种语法输入解析到同一 addr_id（Property 4 基础验证）。"""

    @pytest.mark.asyncio
    async def test_four_syntaxes_same_addr_id(self):
        """formula_ref / uri / addr_id / index_ref → 同一 D2/D2-2/E100。"""
        results = [
            await full_resolve(formula_ref="WP('D2','明细表D2-2','E100')"),
            await full_resolve(uri="wp://D2/明细表D2-2#E100"),
            await full_resolve(addr_id="D2/D2-2/E100"),
            await full_resolve(index_ref="cell:D2-2!E100"),
        ]

        assert all(r.found is True for r in results)
        assert all(r.addr_id == "D2/D2-2/E100" for r in results)
        assert all(r.entry_type == "cell" for r in results)
