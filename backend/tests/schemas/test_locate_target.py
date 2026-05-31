"""Tests for locate_target schema and trace_item_to_locate_target conversion.

Requirements: 1.2
"""

import pytest

from app.schemas.locate_target import (
    LocateTarget,
    trace_item_to_locate_target,
)
from app.services.wp_trace_service import TraceItem


class TestTraceItemToLocateTarget:
    """TraceItem → LocateTarget 转换函数测试。"""

    def test_full_fields_mapping(self):
        """所有字段都有值时正确映射。"""
        item = TraceItem(
            wp_code="D2-1",
            sheet="审定表D2-1",
            cell="K15",
            value=42772704.06,
            label="应收账款期末余额",
        )
        target = trace_item_to_locate_target(item)

        assert isinstance(target, LocateTarget)
        assert target.wp_code == "D2-1"
        assert target.sheet_name == "审定表D2-1"
        assert target.cell_ref == "K15"
        assert target.value == "42772704.06"
        assert target.label == "应收账款期末余额"
        assert target.wp_id is None
        assert target.component_type is None

    def test_minimal_fields(self):
        """仅 wp_code 时其余字段为 None。"""
        item = TraceItem(wp_code="E1")
        target = trace_item_to_locate_target(item)

        assert target.wp_code == "E1"
        assert target.sheet_name is None
        assert target.cell_ref is None
        assert target.value is None
        assert target.label is None

    def test_value_converted_to_str(self):
        """value 非 None 时转为 str。"""
        item = TraceItem(wp_code="F2", value=100)
        target = trace_item_to_locate_target(item)
        assert target.value == "100"

        item2 = TraceItem(wp_code="F2", value=[1, 2, 3])
        target2 = trace_item_to_locate_target(item2)
        assert target2.value == "[1, 2, 3]"

    def test_value_none_stays_none(self):
        """value=None 保持 None 不转为 'None' 字符串。"""
        item = TraceItem(wp_code="G1", value=None)
        target = trace_item_to_locate_target(item)
        assert target.value is None

    def test_sheet_level_locate(self):
        """有 sheet 无 cell 时为 sheet 级定位（满足需求 1.4）。"""
        item = TraceItem(wp_code="D4", sheet="主表", cell=None)
        target = trace_item_to_locate_target(item)

        assert target.sheet_name == "主表"
        assert target.cell_ref is None

    def test_target_type_fields_not_mapped(self):
        """TraceItem 的 target_type/target_identifier 不影响 LocateTarget。"""
        item = TraceItem(
            wp_code="A1",
            target_type="report",
            target_identifier="BS-007",
            label="报表行",
        )
        target = trace_item_to_locate_target(item)

        assert target.wp_code == "A1"
        assert target.label == "报表行"
        # target_type/target_identifier 不在 LocateTarget 中
        assert not hasattr(target, "target_type")
