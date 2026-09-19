"""Tests for ACNR generate_catalog.py pipeline.

验证：
- 6 类输入合并为 SheetCatalogEntry/CellCatalogEntry
- 确定性输出（同输入 → 字节一致）
- skip_reason 阻断整册 manifest
- 别名一对多冲突检测与阻断
- catalog_report.json 生成
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# 确保 backend 目录在 path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from scripts.acnr.generate_catalog import (
    _detect_alias_conflicts,
    _deterministic_json,
    generate_catalog,
)
from app.services.acnr.loaders.from_classification import SheetCatalogEntry
from app.services.acnr.loaders.from_address_seeds import CellCatalogEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_classification_records() -> list[dict]:
    """构建测试用 classification 记录。"""
    return [
        {
            "wp_code": "D2-1",
            "sheet_name": "审定表D2-1",
            "class_code": "F-审定表",
            "functional_type": "adjudication_table",
            "template_version_id": "tpl-001",
        },
        {
            "wp_code": "D2-2",
            "sheet_name": "明细表D2-2",
            "class_code": "F-明细表",
            "functional_type": "detail_table",
            "template_version_id": "tpl-002",
        },
        {
            "wp_code": "D3-1",
            "sheet_name": "审定表D3-1",
            "class_code": "F-审定表",
            "functional_type": "adjudication_table",
            "template_version_id": "tpl-003",
        },
        {
            "wp_code": "D3-2",
            "sheet_name": "预付款项明细表",
            "class_code": "F-明细表",
            "functional_type": "detail_table",
            "template_version_id": "tpl-004",
        },
    ]


def _make_classification_records_with_skip() -> list[dict]:
    """构建带 skip_reason 的 classification 记录（通过 overrides 注入）。"""
    records = _make_classification_records()
    # skip_reason 通过 overrides 注入
    return records


# ---------------------------------------------------------------------------
# Test: 别名冲突检测
# ---------------------------------------------------------------------------


class TestAliasConflictDetection:
    """别名一对多冲突检测（R3.3, R3.5）。"""

    def test_no_conflict(self):
        aliases = {
            "D2-2": ["明细表", "D2明细"],
            "D3-2": ["预付款"],
        }
        clean, conflicts = _detect_alias_conflicts(aliases)
        assert len(conflicts) == 0
        assert clean == aliases

    def test_one_to_many_conflict_blocked(self):
        """一个别名映射多个 sheet_code → 阻断该别名进入 catalog。"""
        aliases = {
            "D2-2": ["应收账款明细", "明细表"],
            "D3-2": ["应收账款明细", "预付款"],
        }
        clean, conflicts = _detect_alias_conflicts(aliases)

        # "应收账款明细" 映射了 D2-2 和 D3-2 → 冲突
        assert len(conflicts) == 1
        assert conflicts[0]["alias"] == "应收账款明细"
        assert set(conflicts[0]["sheet_codes"]) == {"D2-2", "D3-2"}
        assert conflicts[0]["action"] == "blocked"

        # 干净别名中不含冲突别名
        assert "应收账款明细" not in clean.get("D2-2", [])
        assert "应收账款明细" not in clean.get("D3-2", [])
        # 非冲突别名保留
        assert "明细表" in clean["D2-2"]
        assert "预付款" in clean["D3-2"]

    def test_blocking_priority_over_gap_marking(self):
        """阻断优先于缺口标记（R3.5）。"""
        aliases = {
            "D2-2": ["冲突别名"],
            "D3-2": ["冲突别名"],
        }
        clean, conflicts = _detect_alias_conflicts(aliases)

        # 所有别名都冲突 → clean 为空
        assert len(clean) == 0
        # 冲突记录已标 blocked
        assert all(c["action"] == "blocked" for c in conflicts)


# ---------------------------------------------------------------------------
# Test: 确定性输出
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    """确定性输出验证：同输入 → 字节一致。"""

    def test_same_input_produces_identical_bytes(self):
        data = {
            "z_field": "last",
            "a_field": "first",
            "nested": {"b": 2, "a": 1},
            "list": [3, 1, 2],
        }
        result1 = _deterministic_json(data)
        result2 = _deterministic_json(data)
        assert result1 == result2

    def test_sort_keys_applied(self):
        data = {"z": 1, "a": 2, "m": 3}
        result = _deterministic_json(data)
        parsed = json.loads(result)
        keys = list(parsed.keys())
        assert keys == sorted(keys)

    def test_chinese_preserved(self):
        data = {"name": "明细表D2-2"}
        result = _deterministic_json(data)
        assert "明细表D2-2" in result
        assert "\\u" not in result

    def test_trailing_newline(self):
        data = {"key": "value"}
        result = _deterministic_json(data)
        assert result.endswith("\n")


# ---------------------------------------------------------------------------
# Test: 管线合并（集成）
# ---------------------------------------------------------------------------


class TestGenerateCatalogPipeline:
    """生成器管线合并测试（需 mock loaders）。"""

    @patch("scripts.acnr.generate_catalog.load_render_registry_edges")
    @patch("scripts.acnr.generate_catalog.load_sheet_name_aliases")
    @patch("scripts.acnr.generate_catalog.load_cell_entries_from_seeds")
    @patch("scripts.acnr.generate_catalog.load_ie_manifest")
    @patch("scripts.acnr.generate_catalog._load_overrides")
    def test_basic_merge(
        self,
        mock_overrides,
        mock_ie,
        mock_cells,
        mock_aliases,
        mock_render,
    ):
        """基本合并：classification + IE + aliases + cells。"""
        from scripts.acnr.generate_catalog import generate_catalog
        from app.services.acnr.loaders.from_render_registry import RenderRegistryData

        # Mock render registry
        render_data = RenderRegistryData()
        render_data.component_types = {"D2-2": "d2-accounts-receivable"}
        render_data.render_types = {"D2-2": "html_procedure"}
        mock_render.return_value = render_data

        # Mock IE manifest
        mock_ie.return_value = {
            "D2-2": {
                "enabled": True,
                "api_prefix": "d2",
                "item_id": "D2-detail-rows",
                "storage_field": "remark",
                "import_order": 20,
                "depends_on_sheets": ["D2-1"],
            }
        }

        # Mock aliases
        mock_aliases.return_value = {
            "D2-2": ["明细表", "应收明细"],
        }

        # Mock cells
        mock_cells.return_value = [
            CellCatalogEntry(
                addr_id="D2/D2-2/E100",
                parent_addr_id="D2/D2-2",
                uri="wp://D2/明细表D2-2#E100",
                cell_address="E100",
                semantic_label="合计行-期末余额",
                formula_ref="WP('D2','明细表D2-2','合计行-期末余额')",
                registry_version="test",
            )
        ]

        # Mock overrides (empty)
        mock_overrides.return_value = {}

        records = _make_classification_records()
        catalog, report, blocked = generate_catalog(
            classification_records=records,
            cycle="d",
            registry_version="20260101000000",
        )

        # 验证 catalog 结构
        assert catalog["version"] == "1"
        assert catalog["registry_version"] == "20260101000000"
        assert len(catalog["sheets"]) == 4
        assert len(catalog["cells"]) == 1

        # 验证合并结果
        d2_2_sheet = next(
            s for s in catalog["sheets"] if s.get("sheet_code") == "D2-2"
        )
        assert d2_2_sheet["component_type"] == "d2-accounts-receivable"
        assert d2_2_sheet["import_export"]["api_prefix"] == "d2"
        assert "明细表" in d2_2_sheet["sheet_name_aliases"]
        assert "应收明细" in d2_2_sheet["sheet_name_aliases"]

        # 验证 cells
        cell = catalog["cells"][0]
        assert cell["addr_id"] == "D2/D2-2/E100"
        assert cell["parent_addr_id"] == "D2/D2-2"

        # manifest 未阻断
        assert blocked is False

    @patch("scripts.acnr.generate_catalog.load_render_registry_edges")
    @patch("scripts.acnr.generate_catalog.load_sheet_name_aliases")
    @patch("scripts.acnr.generate_catalog.load_cell_entries_from_seeds")
    @patch("scripts.acnr.generate_catalog.load_ie_manifest")
    @patch("scripts.acnr.generate_catalog._load_overrides")
    def test_skip_reason_blocks_manifest(
        self,
        mock_overrides,
        mock_ie,
        mock_cells,
        mock_aliases,
        mock_render,
    ):
        """skip_reason 非空 → 写入条目并阻止整册 manifest（R1.4）。"""
        from scripts.acnr.generate_catalog import generate_catalog
        from app.services.acnr.loaders.from_render_registry import RenderRegistryData

        mock_render.return_value = RenderRegistryData()
        mock_ie.return_value = {}
        mock_aliases.return_value = {}
        mock_cells.return_value = []

        # 通过 overrides 注入 skip_reason
        mock_overrides.return_value = {
            "D2/D2-1": {"skip_reason": "no_import_export"},
        }

        records = _make_classification_records()
        catalog, report, blocked = generate_catalog(
            classification_records=records,
            cycle="d",
            registry_version="test-ver",
        )

        # skip_reason 写入条目
        d2_1 = next(
            s for s in catalog["sheets"] if s.get("sheet_code") == "D2-1"
        )
        assert d2_1["skip_reason"] == "no_import_export"

        # 整册 manifest 被阻断
        assert blocked is True
        assert report["manifest_blocked"] is True

    @patch("scripts.acnr.generate_catalog.load_render_registry_edges")
    @patch("scripts.acnr.generate_catalog.load_sheet_name_aliases")
    @patch("scripts.acnr.generate_catalog.load_cell_entries_from_seeds")
    @patch("scripts.acnr.generate_catalog.load_ie_manifest")
    @patch("scripts.acnr.generate_catalog._load_overrides")
    def test_alias_conflict_in_report(
        self,
        mock_overrides,
        mock_ie,
        mock_cells,
        mock_aliases,
        mock_render,
    ):
        """别名冲突在 catalog_report.json 中标记。"""
        from scripts.acnr.generate_catalog import generate_catalog
        from app.services.acnr.loaders.from_render_registry import RenderRegistryData

        mock_render.return_value = RenderRegistryData()
        mock_ie.return_value = {}
        mock_cells.return_value = []
        mock_overrides.return_value = {}

        # 别名冲突：两个 sheet 共享同一别名
        mock_aliases.return_value = {
            "D2-2": ["共享别名", "独占别名A"],
            "D3-2": ["共享别名", "独占别名B"],
        }

        records = _make_classification_records()
        catalog, report, blocked = generate_catalog(
            classification_records=records,
            cycle="d",
            registry_version="test-ver",
        )

        # 冲突别名不在 catalog entries 中
        d2_2 = next(
            s for s in catalog["sheets"] if s.get("sheet_code") == "D2-2"
        )
        aliases = d2_2.get("sheet_name_aliases", [])
        assert "共享别名" not in aliases
        assert "独占别名A" in aliases

        # report 记录冲突
        assert len(report["alias_conflicts"]) == 1
        assert report["alias_conflicts"][0]["alias"] == "共享别名"
        assert report["summary"]["alias_conflict_count"] == 1

    @patch("scripts.acnr.generate_catalog.load_render_registry_edges")
    @patch("scripts.acnr.generate_catalog.load_sheet_name_aliases")
    @patch("scripts.acnr.generate_catalog.load_cell_entries_from_seeds")
    @patch("scripts.acnr.generate_catalog.load_ie_manifest")
    @patch("scripts.acnr.generate_catalog._load_overrides")
    def test_deterministic_catalog_output(
        self,
        mock_overrides,
        mock_ie,
        mock_cells,
        mock_aliases,
        mock_render,
    ):
        """同输入调用两次 → 字节一致。"""
        from scripts.acnr.generate_catalog import generate_catalog
        from app.services.acnr.loaders.from_render_registry import RenderRegistryData

        mock_render.return_value = RenderRegistryData()
        mock_ie.return_value = {}
        mock_aliases.return_value = {"D2-2": ["别名A"]}
        mock_cells.return_value = []
        mock_overrides.return_value = {}

        records = _make_classification_records()

        cat1, _, _ = generate_catalog(
            classification_records=records,
            cycle="d",
            registry_version="fixed-version",
        )
        cat2, _, _ = generate_catalog(
            classification_records=records,
            cycle="d",
            registry_version="fixed-version",
        )

        json1 = _deterministic_json(cat1)
        json2 = _deterministic_json(cat2)
        assert json1 == json2

    @patch("scripts.acnr.generate_catalog.load_render_registry_edges")
    @patch("scripts.acnr.generate_catalog.load_sheet_name_aliases")
    @patch("scripts.acnr.generate_catalog.load_cell_entries_from_seeds")
    @patch("scripts.acnr.generate_catalog.load_ie_manifest")
    @patch("scripts.acnr.generate_catalog._load_overrides")
    def test_overrides_highest_priority(
        self,
        mock_overrides,
        mock_ie,
        mock_cells,
        mock_aliases,
        mock_render,
    ):
        """Overrides 优先级最高。"""
        from scripts.acnr.generate_catalog import generate_catalog
        from app.services.acnr.loaders.from_render_registry import RenderRegistryData

        mock_render.return_value = RenderRegistryData()
        mock_ie.return_value = {}
        mock_aliases.return_value = {}
        mock_cells.return_value = []

        # Override 覆盖 sheet_name
        mock_overrides.return_value = {
            "D2/D2-2": {"sheet_name": "覆盖后名称"},
        }

        records = _make_classification_records()
        catalog, _, _ = generate_catalog(
            classification_records=records,
            cycle="d",
            registry_version="test",
        )

        d2_2 = next(
            s for s in catalog["sheets"] if s.get("sheet_code") == "D2-2"
        )
        assert d2_2["sheet_name"] == "覆盖后名称"

    @patch("scripts.acnr.generate_catalog.load_render_registry_edges")
    @patch("scripts.acnr.generate_catalog.load_sheet_name_aliases")
    @patch("scripts.acnr.generate_catalog.load_cell_entries_from_seeds")
    @patch("scripts.acnr.generate_catalog.load_ie_manifest")
    @patch("scripts.acnr.generate_catalog._load_overrides")
    def test_report_contains_required_sections(
        self,
        mock_overrides,
        mock_ie,
        mock_cells,
        mock_aliases,
        mock_render,
    ):
        """catalog_report.json 包含冲突/缺口/未登记别名。"""
        from scripts.acnr.generate_catalog import generate_catalog
        from app.services.acnr.loaders.from_render_registry import RenderRegistryData

        mock_render.return_value = RenderRegistryData()
        mock_ie.return_value = {}
        mock_aliases.return_value = {"UNKNOWN-SHEET": ["某别名"]}
        mock_cells.return_value = [
            CellCatalogEntry(
                addr_id="D2/D2-2/semantic-slug",
                parent_addr_id="D2/D2-2",
                uri="wp://D2/明细表D2-2",
                semantic_only=True,
                semantic_label="语义锚点",
                formula_ref="WP('D2','明细表D2-2','语义锚点')",
                registry_version="test",
            )
        ]
        mock_overrides.return_value = {}

        records = _make_classification_records()
        _, report, _ = generate_catalog(
            classification_records=records,
            cycle="d",
            registry_version="test",
        )

        # 报告包含必须的 section
        assert "alias_conflicts" in report
        assert "gaps" in report
        assert "unregistered_aliases" in report
        assert "summary" in report
        assert "manifest_blocked" in report

        # semantic_only → gap
        assert len(report["gaps"]) == 1
        assert report["gaps"][0]["type"] == "semantic_only_missing_a1"

        # 未注册 sheet 的别名
        assert len(report["unregistered_aliases"]) == 1
        assert report["unregistered_aliases"][0]["sheet_code"] == "UNKNOWN-SHEET"
