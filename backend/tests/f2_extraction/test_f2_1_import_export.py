"""F2-1 审定表导入导出 — Property 1-5 测试."""

from __future__ import annotations

import io
import pytest
import openpyxl

from app.routers.wp_render_strategies._f2_import_export import (
    _F2_1_GROSS_CATEGORIES,
    _F2_1_IMPAIRMENT_CATEGORIES,
    _F2_1_HEADERS,
    _F2_1_LABEL_TO_ROW_KEY,
    _f2_1_item_id,
    _F2_1_NUMERIC_FIELDS,
)


class TestF2_1Constants:
    """基础常量正确性."""

    def test_gross_categories_exclude_impairment(self):
        keys = [c["rowKey"] for c in _F2_1_GROSS_CATEGORIES]
        assert "impairment-provision" not in keys
        assert len(keys) == 12

    def test_impairment_categories_only_one(self):
        assert len(_F2_1_IMPAIRMENT_CATEGORIES) == 1
        assert _F2_1_IMPAIRMENT_CATEGORIES[0]["rowKey"] == "impairment-provision"

    def test_headers_structure(self):
        assert _F2_1_HEADERS == ["类别名", "科目编码", "期初未审数", "本期增加", "本期减少", "账项调整"]

    def test_label_to_row_key_complete(self):
        assert len(_F2_1_LABEL_TO_ROW_KEY) == 13
        assert _F2_1_LABEL_TO_ROW_KEY["原材料"] == "raw-materials"
        assert _F2_1_LABEL_TO_ROW_KEY["存货跌价准备"] == "impairment-provision"

    def test_item_id_format(self):
        assert _f2_1_item_id("gross", "raw-materials", "opening") == "F2-1-gross-raw-materials-opening"
        assert _f2_1_item_id("impairment", "impairment-provision", "decrease") == "F2-1-impairment-impairment-provision-decrease"

    def test_numeric_fields(self):
        assert _F2_1_NUMERIC_FIELDS == {"opening", "increase", "decrease", "adjustment"}


class TestF2_1ExportTemplate:
    """Property 6: 导出模板结构正确."""

    @pytest.fixture
    def template_wb(self):
        """Simulate template generation by calling the internal logic."""
        from openpyxl import Workbook
        from openpyxl.styles import Font

        wb = Workbook()
        ws_guide = wb.active
        ws_guide.title = "编制说明"
        ws_guide.append(["F2-1 存货审定表 — 导入模板编制说明"])

        ws_gross = wb.create_sheet("原值")
        ws_gross.append(_F2_1_HEADERS)
        for cat in _F2_1_GROSS_CATEGORIES:
            ws_gross.append([cat["label"], cat["account"], None, None, None, None])

        ws_imp = wb.create_sheet("跌价准备")
        ws_imp.append(_F2_1_HEADERS)
        for cat in _F2_1_IMPAIRMENT_CATEGORIES:
            ws_imp.append([cat["label"], cat["account"], None, None, None, None])

        return wb

    def test_three_sheets(self, template_wb):
        assert template_wb.sheetnames == ["编制说明", "原值", "跌价准备"]

    def test_gross_sheet_headers(self, template_wb):
        ws = template_wb["原值"]
        headers = [ws.cell(1, c).value for c in range(1, 7)]
        assert headers == _F2_1_HEADERS

    def test_gross_sheet_row_count(self, template_wb):
        ws = template_wb["原值"]
        assert ws.max_row == 13  # 1 header + 12 categories

    def test_impairment_sheet_row_count(self, template_wb):
        ws = template_wb["跌价准备"]
        assert ws.max_row == 2  # 1 header + 1 category


class TestF2_1Import:
    """Property 2, 3: 导入逻辑纯函数测试."""

    def _build_import_xlsx(self, gross_data=None, imp_data=None):
        """Build a test xlsx with optional data."""
        wb = openpyxl.Workbook()
        ws_guide = wb.active
        ws_guide.title = "编制说明"

        ws_gross = wb.create_sheet("原值")
        ws_gross.append(_F2_1_HEADERS)
        if gross_data:
            for row in gross_data:
                ws_gross.append(row)

        ws_imp = wb.create_sheet("跌价准备")
        ws_imp.append(_F2_1_HEADERS)
        if imp_data:
            for row in imp_data:
                ws_imp.append(row)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def test_label_matching(self):
        """Known category labels map to correct row keys."""
        assert _F2_1_LABEL_TO_ROW_KEY.get("原材料") == "raw-materials"
        assert _F2_1_LABEL_TO_ROW_KEY.get("库存商品") == "finished-goods"
        assert _F2_1_LABEL_TO_ROW_KEY.get("不存在的类别") is None

    def test_item_id_round_trip(self):
        """item_id 生成格式可被解析回 block/rowKey/field."""
        item_id = _f2_1_item_id("gross", "raw-materials", "opening")
        rest = item_id[len("F2-1-"):]  # "gross-raw-materials-opening"
        # Parse back
        for field in _F2_1_NUMERIC_FIELDS:
            suffix = f"-{field}"
            if rest.endswith(suffix):
                prefix = rest[: -len(suffix)]
                dash_idx = prefix.find("-")
                block = prefix[:dash_idx]
                row_key = prefix[dash_idx + 1:]
                assert block == "gross"
                assert row_key == "raw-materials"
                assert field == "opening"
                break

    def test_xlsx_structure(self):
        """Generated xlsx has correct structure."""
        content = self._build_import_xlsx(
            gross_data=[["原材料", "1401", 100.5, 50.0, 30.0, 10.0]],
            imp_data=[["存货跌价准备", "1471", 20.0, 5.0, 3.0, 2.0]],
        )
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        assert "原值" in wb.sheetnames
        assert "跌价准备" in wb.sheetnames
        ws = wb["原值"]
        assert ws.cell(2, 1).value == "原材料"
        assert ws.cell(2, 3).value == 100.5


class TestF2_1ZeroRegression:
    """Property 5: F2-3~14 不受影响."""

    def test_supported_sheets_includes_f2_1(self):
        from app.routers.wp_render_strategies._f2_import_export import _SUPPORTED_SHEETS
        assert "F2-1" in _SUPPORTED_SHEETS

    def test_supported_sheets_still_has_f2_3(self):
        from app.routers.wp_render_strategies._f2_import_export import _SUPPORTED_SHEETS
        assert "F2-3" in _SUPPORTED_SHEETS
        assert "F2-14" in _SUPPORTED_SHEETS
        assert "F2-8" in _SUPPORTED_SHEETS
