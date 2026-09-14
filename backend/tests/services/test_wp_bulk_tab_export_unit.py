"""单测 — 底稿批量 Tab 导入导出服务（wp_bulk_tab_export）

Spec: acnr-consumer-wiring — Task 5.6
Requirements: 6.1–6.6, 7.1–7.5

覆盖（example-based）：
- wp_id=None 的未解析实例被跳过，并 log warning（list_export_sheets + list_import_sheets）
- _topological_sort 对具体依赖图输出顺序正确（依赖先于被依赖，import_order 作 tiebreaker）
- 存活 entry 携带 api_prefix + item_id（导入额外携带 storage_field），
  供调用方按 api_prefix/item_id 构造/路由端点

manifest.list_import_export 在函数内部惰性 import，故 monkeypatch 模块级符号
`app.services.acnr.manifest.list_import_export`（AsyncMock 返回固定 entries）。
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.wp_bulk_tab_export import (
    _topological_sort,
    list_export_sheets,
    list_import_sheets,
)

PROJECT_ID = "11111111-1111-1111-1111-111111111111"
CYCLE = "D"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entry(
    sheet_code: str,
    *,
    wp_id: str | None = "wp-" ,
    api_prefix: str | None = None,
    item_id: Any = None,
    storage_field: str = "remark",
    import_order: int = 999,
    depends_on_sheets: list[str] | None = None,
) -> dict[str, Any]:
    """构造一条 manifest entry（字段与 manifest.list_import_export 输出对齐）。"""
    prefix = api_prefix if api_prefix is not None else sheet_code.split("-")[0].lower()
    return {
        "sheet_code": sheet_code,
        "api_prefix": prefix,
        "item_id": item_id if item_id is not None else f"{sheet_code}-item",
        "storage_field": storage_field,
        "import_order": import_order,
        "depends_on_sheets": depends_on_sheets or [],
        "wp_id": (f"{wp_id}{sheet_code}" if wp_id == "wp-" else wp_id),
        "jump_route": None,
        "parent_wp_code": sheet_code.split("-")[0],
        "addr_id": f"{sheet_code}/root/A1",
    }


def _patch_manifest(monkeypatch, entries: list[dict[str, Any]]) -> AsyncMock:
    """Monkeypatch manifest.list_import_export 返回固定 entries。"""
    mock = AsyncMock(return_value=entries)
    monkeypatch.setattr("app.services.acnr.manifest.list_import_export", mock)
    return mock


def _db() -> MagicMock:
    """轻量 db mock — 仅透传给被 monkeypatch 的 list_import_export，不会真实使用。"""
    return MagicMock()


# ---------------------------------------------------------------------------
# Test: wp_id=None 跳过 + warning 日志
# ---------------------------------------------------------------------------


class TestSkipUnresolvedInstances:
    """wp_id=None 的条目应被剔除并记录 warning（Req 6.3）"""

    @pytest.mark.asyncio
    async def test_export_skips_wp_id_none_and_logs_warning(self, monkeypatch, caplog):
        entries = [
            _entry("D2-1", import_order=1),
            _entry("D2-2", wp_id=None, import_order=2),  # 未解析实例
            _entry("D2-3", import_order=3),
        ]
        _patch_manifest(monkeypatch, entries)

        with caplog.at_level(logging.WARNING, logger="app.services.wp_bulk_tab_export"):
            result = await list_export_sheets(_db(), PROJECT_ID, CYCLE)

        codes = [e["sheet_code"] for e in result]
        assert codes == ["D2-1", "D2-3"]
        assert all(e["wp_id"] is not None for e in result)

        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert any("D2-2" in m for m in warnings)
        assert any("Bulk export" in m and "skipping" in m for m in warnings)

    @pytest.mark.asyncio
    async def test_import_skips_wp_id_none_and_logs_warning(self, monkeypatch, caplog):
        entries = [
            _entry("D2-1", import_order=1),
            _entry("D2-2", wp_id=None, import_order=2),
            _entry("D2-3", import_order=3),
        ]
        _patch_manifest(monkeypatch, entries)

        with caplog.at_level(logging.WARNING, logger="app.services.wp_bulk_tab_export"):
            result = await list_import_sheets(_db(), PROJECT_ID, CYCLE)

        codes = [e["sheet_code"] for e in result]
        assert codes == ["D2-1", "D2-3"]
        assert all(e["wp_id"] is not None for e in result)

        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert any("D2-2" in m for m in warnings)
        assert any("Bulk import" in m and "skipping" in m for m in warnings)

    @pytest.mark.asyncio
    async def test_all_resolved_no_warning(self, monkeypatch, caplog):
        """全部已解析时不产生 skip warning。"""
        entries = [_entry("D2-1", import_order=1), _entry("D2-2", import_order=2)]
        _patch_manifest(monkeypatch, entries)

        with caplog.at_level(logging.WARNING, logger="app.services.wp_bulk_tab_export"):
            result = await list_export_sheets(_db(), PROJECT_ID, CYCLE)

        assert len(result) == 2
        assert not [r for r in caplog.records if "skipping" in r.getMessage()]


# ---------------------------------------------------------------------------
# Test: 拓扑排序输出顺序正确
# ---------------------------------------------------------------------------


class TestTopologicalSort:
    """_topological_sort 依赖顺序 + import_order tiebreaker（Req 7.1–7.4）"""

    def test_linear_chain_orders_dependencies_first(self):
        # C 依赖 B，B 依赖 A → 顺序必须 A, B, C
        entries = [
            _entry("C", import_order=3, depends_on_sheets=["B"]),
            _entry("A", import_order=1, depends_on_sheets=[]),
            _entry("B", import_order=2, depends_on_sheets=["A"]),
        ]
        result = _topological_sort(entries)
        assert [e["sheet_code"] for e in result] == ["A", "B", "C"]

    def test_import_order_tiebreaker_among_roots(self):
        # 两个无依赖根节点 → 按 import_order 排序
        entries = [
            _entry("X", import_order=5, depends_on_sheets=[]),
            _entry("Y", import_order=2, depends_on_sheets=[]),
        ]
        result = _topological_sort(entries)
        assert [e["sheet_code"] for e in result] == ["Y", "X"]

    def test_diamond_dependency_respects_all_edges(self):
        # 菱形：A → B, A → C, B → D, C → D
        # A 必在首，D 必在末，B/C 在中间（import_order 决定 B 先于 C）
        entries = [
            _entry("D", import_order=4, depends_on_sheets=["B", "C"]),
            _entry("C", import_order=3, depends_on_sheets=["A"]),
            _entry("B", import_order=2, depends_on_sheets=["A"]),
            _entry("A", import_order=1, depends_on_sheets=[]),
        ]
        result = _topological_sort(entries)
        codes = [e["sheet_code"] for e in result]
        assert codes[0] == "A"
        assert codes[-1] == "D"
        # 每个节点都排在其依赖之后
        pos = {c: i for i, c in enumerate(codes)}
        assert pos["B"] > pos["A"]
        assert pos["C"] > pos["A"]
        assert pos["D"] > pos["B"] and pos["D"] > pos["C"]
        # 同级 tiebreaker：B(2) 先于 C(3)
        assert pos["B"] < pos["C"]

    def test_cycle_falls_back_to_import_order(self):
        # 循环依赖 A↔B → 回退到 import_order 排序，不丢条目
        entries = [
            _entry("B", import_order=1, depends_on_sheets=["A"]),
            _entry("A", import_order=2, depends_on_sheets=["B"]),
        ]
        result = _topological_sort(entries)
        assert len(result) == 2
        assert [e["sheet_code"] for e in result] == ["B", "A"]

    @pytest.mark.asyncio
    async def test_export_result_is_topologically_sorted(self, monkeypatch):
        """list_export_sheets 端到端返回拓扑序（含依赖）。"""
        entries = [
            _entry("D2-3", import_order=3, depends_on_sheets=["D2-1"]),
            _entry("D2-1", import_order=1, depends_on_sheets=[]),
        ]
        _patch_manifest(monkeypatch, entries)
        result = await list_export_sheets(_db(), PROJECT_ID, CYCLE)
        codes = [e["sheet_code"] for e in result]
        assert codes.index("D2-1") < codes.index("D2-3")


# ---------------------------------------------------------------------------
# Test: api_prefix / item_id / storage_field 端点构造字段
# ---------------------------------------------------------------------------


class TestEndpointConstructionFields:
    """存活 entry 携带路由端点所需字段（Req 6.5, 6.6, 7.5）"""

    @pytest.mark.asyncio
    async def test_export_entries_carry_api_prefix_and_item_id(self, monkeypatch):
        entries = [
            _entry("D2-1", api_prefix="d2", item_id="D2-1-detail", import_order=1),
            _entry("D2-2", api_prefix="d2", item_id=["a", "b"], import_order=2),
        ]
        _patch_manifest(monkeypatch, entries)
        result = await list_export_sheets(_db(), PROJECT_ID, CYCLE)

        by_code = {e["sheet_code"]: e for e in result}
        assert by_code["D2-1"]["api_prefix"] == "d2"
        assert by_code["D2-1"]["item_id"] == "D2-1-detail"
        # item_id 可为 list（多 item 存储）
        assert by_code["D2-2"]["item_id"] == ["a", "b"]
        # 每条都能构造端点：/{api_prefix}/... 且 tab 名 == sheet_code
        for e in result:
            assert e["api_prefix"]
            assert e["item_id"]
            assert e["sheet_code"]

    @pytest.mark.asyncio
    async def test_import_entries_carry_storage_field(self, monkeypatch):
        entries = [
            _entry("D2-1", api_prefix="d2", item_id="D2-1-detail",
                   storage_field="parsed_data", import_order=1),
            _entry("D2-2", api_prefix="d2", item_id="D2-2-detail",
                   storage_field="remark", import_order=2),
        ]
        _patch_manifest(monkeypatch, entries)
        result = await list_import_sheets(_db(), PROJECT_ID, CYCLE)

        by_code = {e["sheet_code"]: e for e in result}
        assert by_code["D2-1"]["storage_field"] == "parsed_data"
        assert by_code["D2-2"]["storage_field"] == "remark"
        # 导入路由三要素齐备：api_prefix + item_id + storage_field
        for e in result:
            assert e["api_prefix"]
            assert e["item_id"]
            assert e["storage_field"]

    @pytest.mark.asyncio
    async def test_manifest_called_with_passthrough_args(self, monkeypatch):
        """db / project_id / cycle 应原样透传给 manifest.list_import_export。"""
        mock = _patch_manifest(monkeypatch, [_entry("D2-1", import_order=1)])
        db = _db()
        await list_export_sheets(db, PROJECT_ID, CYCLE)
        mock.assert_awaited_once_with(db, PROJECT_ID, CYCLE)

    @pytest.mark.asyncio
    async def test_empty_manifest_returns_empty(self, monkeypatch):
        _patch_manifest(monkeypatch, [])
        assert await list_export_sheets(_db(), PROJECT_ID, CYCLE) == []
        assert await list_import_sheets(_db(), PROJECT_ID, CYCLE) == []
