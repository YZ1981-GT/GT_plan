"""Tests for report_trace_to_locate_targets conversion function.

Task 1.3: report_trace_service 升级到 cell 级
- 利用 cell_provenance 返回精确 LocateTarget（而非整个 parsed_data）
- 无 cell_provenance 时降级到 sheet 级（cell_ref=None）

Requirements: 1.3, 1.4
"""

import pytest

from app.schemas.locate_target import LocateTarget
from app.services.report_trace_service import report_trace_to_locate_targets


class TestReportTraceToLocateTargets:
    """report_trace_to_locate_targets 转换函数测试。"""

    def _make_trace_result(
        self,
        wp_code: str = "D2-1",
        note_title: str = "应收账款",
        workpaper_data: dict | None = None,
    ) -> dict:
        """构造 trace_section 返回的 dict。"""
        return {
            "section_number": "6.3",
            "note_data": {
                "wp_code": wp_code,
                "account_codes": ["1122"],
                "note_title": note_title,
            },
            "workpaper_data": workpaper_data,
            "trial_balance_data": None,
            "top_ledger_entries": [],
        }

    # ─── 有 cell_provenance 时：精确 cell 级定位 ─────────────────────────

    def test_with_cell_provenance_single_entry(self):
        """单条 provenance → 单个精确 LocateTarget。"""
        trace = self._make_trace_result()
        provenance = {
            "0:col_ending": {
                "source": "wp_data",
                "value": 42772704.06,
                "source_detail": {
                    "wp_code": "D2-1",
                    "sheet": "审定表D2-1",
                    "cell_ref": "K15",
                },
            }
        }

        targets = report_trace_to_locate_targets(trace, provenance)

        assert len(targets) == 1
        t = targets[0]
        assert isinstance(t, LocateTarget)
        assert t.wp_code == "D2-1"
        assert t.sheet_name == "审定表D2-1"
        assert t.cell_ref == "K15"
        assert t.value == "42772704.06"
        assert t.label == "应收账款"
        assert t.wp_id is None
        assert t.component_type is None

    def test_with_cell_provenance_multiple_entries(self):
        """多条 provenance → 多个 LocateTarget（去重）。"""
        trace = self._make_trace_result()
        provenance = {
            "0:col_ending": {
                "source": "wp_data",
                "value": 100.0,
                "source_detail": {
                    "wp_code": "D2-1",
                    "sheet": "审定表D2-1",
                    "cell_ref": "K15",
                },
            },
            "1:col_opening": {
                "source": "wp_data",
                "value": 200.0,
                "source_detail": {
                    "wp_code": "D2-1",
                    "sheet": "审定表D2-1",
                    "cell_ref": "L15",
                },
            },
            "2:col_ending": {
                "source": "tb",
                "value": 300.0,
                "source_detail": {
                    "wp_code": "D2-2",
                    "sheet": "明细表",
                    "cell_ref": "F3",
                },
            },
        }

        targets = report_trace_to_locate_targets(trace, provenance)

        assert len(targets) == 3
        assert targets[0].cell_ref == "K15"
        assert targets[1].cell_ref == "L15"
        assert targets[2].wp_code == "D2-2"
        assert targets[2].sheet_name == "明细表"
        assert targets[2].cell_ref == "F3"

    def test_with_cell_provenance_deduplication(self):
        """相同 (wp_code, sheet, cell_ref) 去重。"""
        trace = self._make_trace_result()
        provenance = {
            "0:col_ending": {
                "source": "wp_data",
                "value": 100.0,
                "source_detail": {
                    "wp_code": "D2-1",
                    "sheet": "审定表D2-1",
                    "cell_ref": "K15",
                },
            },
            "1:col_ending": {
                "source": "wp_data",
                "value": 100.0,
                "source_detail": {
                    "wp_code": "D2-1",
                    "sheet": "审定表D2-1",
                    "cell_ref": "K15",
                },
            },
        }

        targets = report_trace_to_locate_targets(trace, provenance)
        assert len(targets) == 1

    def test_provenance_uses_base_wp_code_when_missing(self):
        """provenance source_detail 无 wp_code 时用 trace 的 base wp_code。"""
        trace = self._make_trace_result(wp_code="D4")
        provenance = {
            "0:col_ending": {
                "source": "tb",
                "value": 500.0,
                "source_detail": {
                    "sheet": "主表",
                    "cell_ref": "B3",
                },
            },
        }

        targets = report_trace_to_locate_targets(trace, provenance)

        assert len(targets) == 1
        assert targets[0].wp_code == "D4"
        assert targets[0].sheet_name == "主表"
        assert targets[0].cell_ref == "B3"

    def test_provenance_without_cell_ref_gives_sheet_level(self):
        """provenance 有 sheet 无 cell_ref → cell_ref=None（sheet 级）。"""
        trace = self._make_trace_result()
        provenance = {
            "0:col_ending": {
                "source": "wp_data",
                "value": 100.0,
                "source_detail": {
                    "wp_code": "D2-1",
                    "sheet": "审定表D2-1",
                    # 无 cell_ref
                },
            },
        }

        targets = report_trace_to_locate_targets(trace, provenance)

        assert len(targets) == 1
        assert targets[0].sheet_name == "审定表D2-1"
        assert targets[0].cell_ref is None

    # ─── 无 cell_provenance 时：降级到 sheet 级（Requirement 1.4）────────

    def test_no_provenance_fallback_to_sheet_level(self):
        """无 provenance → 降级到 sheet 级定位。"""
        trace = self._make_trace_result(
            workpaper_data={"html_data": {"审定表D2-1": {}, "明细表": {}}}
        )

        targets = report_trace_to_locate_targets(trace, None)

        assert len(targets) == 1
        t = targets[0]
        assert t.wp_code == "D2-1"
        assert t.sheet_name == "审定表D2-1"  # 取第一个 sheet
        assert t.cell_ref is None
        assert t.label == "应收账款"

    def test_empty_provenance_fallback_to_sheet_level(self):
        """空 provenance dict → 降级到 sheet 级。"""
        trace = self._make_trace_result(
            workpaper_data={"html_data": {"主表": {}}}
        )

        targets = report_trace_to_locate_targets(trace, {})

        assert len(targets) == 1
        assert targets[0].sheet_name == "主表"
        assert targets[0].cell_ref is None

    def test_no_workpaper_data_fallback_no_sheet(self):
        """无 workpaper_data → sheet_name=None 的最低级降级。"""
        trace = self._make_trace_result(workpaper_data=None)

        targets = report_trace_to_locate_targets(trace, None)

        assert len(targets) == 1
        assert targets[0].wp_code == "D2-1"
        assert targets[0].sheet_name is None
        assert targets[0].cell_ref is None

    def test_workpaper_data_sheets_list_format(self):
        """workpaper_data 使用 sheets 列表格式时也能提取 sheet_name。"""
        trace = self._make_trace_result(
            workpaper_data={"sheets": [{"name": "Sheet1"}, {"name": "Sheet2"}]}
        )

        targets = report_trace_to_locate_targets(trace, None)

        assert len(targets) == 1
        assert targets[0].sheet_name == "Sheet1"

    # ─── 边界情况 ─────────────────────────────────────────────────────────

    def test_no_note_data_returns_empty(self):
        """trace_result 无 note_data → 空列表。"""
        trace = {"section_number": "1.1", "note_data": None}
        targets = report_trace_to_locate_targets(trace, None)
        assert targets == []

    def test_no_wp_code_returns_empty(self):
        """note_data 无 wp_code → 空列表。"""
        trace = {
            "section_number": "1.1",
            "note_data": {"wp_code": None, "note_title": "test"},
        }
        targets = report_trace_to_locate_targets(trace, None)
        assert targets == []

    def test_provenance_value_none_stays_none(self):
        """provenance value=None 保持 None 不转为字符串。"""
        trace = self._make_trace_result()
        provenance = {
            "0:col_ending": {
                "source": "wp_data",
                "value": None,
                "source_detail": {
                    "wp_code": "D2-1",
                    "sheet": "审定表D2-1",
                    "cell_ref": "K15",
                },
            },
        }

        targets = report_trace_to_locate_targets(trace, provenance)
        assert targets[0].value is None

    def test_provenance_empty_source_detail(self):
        """provenance source_detail 为空 → 用 base wp_code，sheet/cell 为 None。"""
        trace = self._make_trace_result(wp_code="E1")
        provenance = {
            "0:col_ending": {
                "source": "fallback",
                "value": 0,
                "source_detail": {},
            },
        }

        targets = report_trace_to_locate_targets(trace, provenance)

        assert len(targets) == 1
        assert targets[0].wp_code == "E1"
        assert targets[0].sheet_name is None
        assert targets[0].cell_ref is None
