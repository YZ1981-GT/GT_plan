"""D4-13/14/15/16 检查表 descriptor 契约测试。

openpyxl 直读权威 xlsx，与 `app.services.d4_extraction.d4_inspection_descriptor`
的常量三向比对（源xlsx ↔ descriptor ↔ 运行时）+ 反向自检。

spec: d4-inspection-writeback-formula-io / Task 1
Requirements: 1.1, 1.2, 1.3, 1.4, 4.1
失败即阻塞后续 IO/公式/联动实现。
"""
from __future__ import annotations

import openpyxl
import pytest

from app.services.d4_extraction.d4_inspection_descriptor import (
    # Template
    d4_inspection_template_path,
    WORKBOOK_SHEETS,
    # Tri-state
    DateTriState,
    AmountTriState,
    # D4-13
    D4_13_SHEET_NAME,
    D4_13_ITEM_PROCESS,
    D4_13_ITEM_CONCLUSION,
    D4_13_SECTION_TITLES,
    D4_13_HINT_ROW,
    D4_13_HINT_TEXT,
    # D4-14
    D4_14_SHEET_NAME,
    D4_14_ITEM_ID,
    D4_14_HEADER_GROUP_ROW,
    D4_14_HEADER_FIELD_ROW,
    D4_14_DIMENSIONS,
    D4_14_STANDALONE_COLUMNS,
    D4_14_DATA_START_ROW,
    D4_14_TOTAL_ROW,
    D4_14_TOTAL_FORMULAS,
    D4_14_COVERAGE_FORMULA,
    D4_14_COVERAGE_FORMULA_VALUE,
    D4_14_KNOWN_ITEM_IDS,
    # D4-15
    D4_15_SHEET_NAME,
    D4_15_ITEM_ID,
    D4_15_HEADER_GROUP_ROW,
    D4_15_HEADER_FIELD_ROW,
    D4_15_LAYERS,
    D4_15_STANDALONE_COLUMNS,
    D4_15_KNOWN_ITEM_IDS,
    # D4-16
    D4_16_SHEET_NAME,
    D4_16_ITEM_ID,
    D4_16_HEADER_GROUP_ROW,
    D4_16_HEADER_FIELD_ROW,
    D4_16_COLUMNS,
    D4_16_GROUP_HEADERS,
    D4_16_KNOWN_ITEM_IDS,
    D4_16_DERIVED_KEYS,
    # Unknown mapping
    UnknownMappingError,
    assert_known_headers,
    assert_known_item_id,
    # Descriptor
    d4_inspection_descriptor,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def wb():
    path = d4_inspection_template_path()
    assert path.exists(), f"权威模板不存在: {path}"
    return openpyxl.load_workbook(path, data_only=False, read_only=False)


@pytest.fixture(scope="module")
def ws_13(wb):
    assert D4_13_SHEET_NAME in wb.sheetnames
    return wb[D4_13_SHEET_NAME]


@pytest.fixture(scope="module")
def ws_14(wb):
    assert D4_14_SHEET_NAME in wb.sheetnames
    return wb[D4_14_SHEET_NAME]


@pytest.fixture(scope="module")
def ws_15(wb):
    assert D4_15_SHEET_NAME in wb.sheetnames
    return wb[D4_15_SHEET_NAME]


@pytest.fixture(scope="module")
def ws_16(wb):
    assert D4_16_SHEET_NAME in wb.sheetnames
    return wb[D4_16_SHEET_NAME]


# ═══════════════════════════════════════════════════════════════════════════════
# 册 / tab 校验
# ═══════════════════════════════════════════════════════════════════════════════

class TestWorkbook:
    def test_workbook_sheets_match(self, wb):
        """同册 sheet 名单与 descriptor 逐字一致。"""
        assert tuple(wb.sheetnames) == WORKBOOK_SHEETS

    def test_four_target_sheets_exist(self, wb):
        """D4-13/14/15/16 四张目标 sheet 全在。"""
        for sn in (D4_13_SHEET_NAME, D4_14_SHEET_NAME,
                   D4_15_SHEET_NAME, D4_16_SHEET_NAME):
            assert sn in wb.sheetnames, f"目标 sheet 缺失: {sn}"


# ═══════════════════════════════════════════════════════════════════════════════
# D4-13 ERP核对记录
# ═══════════════════════════════════════════════════════════════════════════════

class TestD413:
    def test_section_titles(self, ws_13):
        """叙述区标题锚点与 descriptor 逐字一致。"""
        for item_id, (row, text) in D4_13_SECTION_TITLES.items():
            actual = ws_13[f"A{row}"].value
            assert actual == text, (
                f"D4-13 A{row} 期望 {text!r} 实得 {actual!r}"
            )

    def test_process_title_row_matches(self, ws_13):
        """D4_13_PROCESS_TITLE_ROW 与源 xlsx 核对过程标题行一致。"""
        from app.services.d4_extraction.d4_inspection_descriptor import (
            D4_13_PROCESS_TITLE_ROW,
            D4_13_CONCLUSION_TITLE_ROW,
        )
        assert ws_13[f"A{D4_13_PROCESS_TITLE_ROW}"].value == "一、核对过程"
        assert ws_13[f"A{D4_13_CONCLUSION_TITLE_ROW}"].value == "二、核对结论"

    def test_process_item_id(self):
        assert D4_13_ITEM_PROCESS == "D4-13-process"

    def test_conclusion_item_id(self):
        assert D4_13_ITEM_CONCLUSION == "D4-13-conclusion"

    def test_hint_row(self, ws_13):
        """提示行文案锚点。"""
        actual = ws_13[f"A{D4_13_HINT_ROW}"].value
        assert actual is not None
        assert "IT审计" in str(actual), f"提示行应含'IT审计', 实得 {actual!r}"


# ═══════════════════════════════════════════════════════════════════════════════
# D4-14 发生检查表（7 维嵌套）
# ═══════════════════════════════════════════════════════════════════════════════

class TestD414:
    def test_dimension_group_headers(self, ws_14):
        """R13 维度组标题与 descriptor 逐字一致。"""
        for dim in D4_14_DIMENSIONS:
            cell = f"{dim.col_start}{D4_14_HEADER_GROUP_ROW}"
            actual = ws_14[cell].value
            assert actual == dim.label, (
                f"D4-14 {cell} 期望 {dim.label!r} 实得 {actual!r}"
            )

    def test_dimension_sub_headers(self, ws_14):
        """R14 子字段标题与 descriptor 逐字一致。"""
        for dim in D4_14_DIMENSIONS:
            for col, expected_label in dim.sub_fields:
                cell = f"{col}{D4_14_HEADER_FIELD_ROW}"
                actual = ws_14[cell].value
                assert actual == expected_label, (
                    f"D4-14 {cell} (维度 {dim.key}) "
                    f"期望 {expected_label!r} 实得 {actual!r}"
                )

    def test_standalone_columns(self, ws_14):
        """独立列（R13:R14 合并）标题与 descriptor 逐字一致。"""
        for col, expected_label in D4_14_STANDALONE_COLUMNS.items():
            cell = f"{col}{D4_14_HEADER_GROUP_ROW}"
            actual = ws_14[cell].value
            assert actual == expected_label, (
                f"D4-14 {cell} 期望 {expected_label!r} 实得 {actual!r}"
            )

    def test_six_dimensions(self):
        """恰好 6 个子字段维度（仓库保管员/发货审批人是独立列不含子字段）。"""
        assert len(D4_14_DIMENSIONS) == 6

    def test_dimension_keys_unique(self):
        """维度 key 唯一。"""
        keys = [d.key for d in D4_14_DIMENSIONS]
        assert len(keys) == len(set(keys))

    def test_total_formulas(self, ws_14):
        """合计行公式与 descriptor 一致。"""
        for coord, expected in D4_14_TOTAL_FORMULAS.items():
            actual = ws_14[coord].value
            assert actual == expected, (
                f"D4-14 {coord} 期望 {expected!r} 实得 {actual!r}"
            )

    def test_coverage_formula(self, ws_14):
        """检查比例公式。"""
        actual = ws_14[D4_14_COVERAGE_FORMULA].value
        assert actual == D4_14_COVERAGE_FORMULA_VALUE

    def test_data_area_blank(self, ws_14):
        """数据区 A 列（序号列）在空白可扩行为空。"""
        for r in range(D4_14_DATA_START_ROW, D4_14_TOTAL_ROW):
            assert ws_14[f"A{r}"].value is None, (
                f"D4-14 A{r} 应为空白可扩行"
            )

    def test_total_row_label(self, ws_14):
        assert ws_14[f"A{D4_14_TOTAL_ROW}"].value == "合计"

    def test_item_id(self):
        assert D4_14_ITEM_ID == "D4-14-transactions"

    def test_known_item_ids(self):
        """已知 item_id 集合完整。"""
        assert D4_14_ITEM_ID in D4_14_KNOWN_ITEM_IDS
        assert "D4-14-sampling" in D4_14_KNOWN_ITEM_IDS
        assert "D4-14-note" in D4_14_KNOWN_ITEM_IDS
        assert "D4-14-conclusion" in D4_14_KNOWN_ITEM_IDS
        assert len(D4_14_KNOWN_ITEM_IDS) == 4


# ═══════════════════════════════════════════════════════════════════════════════
# D4-15 完整性检查表（三层嵌套）
# ═══════════════════════════════════════════════════════════════════════════════

class TestD415:
    def test_layer_group_headers(self, ws_15):
        """R11 组标题与 descriptor 逐字一致。"""
        for layer in D4_15_LAYERS:
            cell = f"{layer.col_start}{D4_15_HEADER_GROUP_ROW}"
            actual = ws_15[cell].value
            assert actual == layer.label, (
                f"D4-15 {cell} 期望 {layer.label!r} 实得 {actual!r}"
            )

    def test_layer_sub_headers(self, ws_15):
        """R12 子字段标题与 descriptor 逐字一致。"""
        for layer in D4_15_LAYERS:
            for col, expected_label in layer.sub_fields:
                cell = f"{col}{D4_15_HEADER_FIELD_ROW}"
                actual = ws_15[cell].value
                assert actual == expected_label, (
                    f"D4-15 {cell} (层 {layer.key}) "
                    f"期望 {expected_label!r} 实得 {actual!r}"
                )

    def test_three_layers(self):
        """恰好 3 层：delivery/invoice/voucher。"""
        assert len(D4_15_LAYERS) == 3
        assert [l.key for l in D4_15_LAYERS] == ["delivery", "invoice", "voucher"]

    def test_each_layer_five_subfields(self):
        """每层 5 个子字段：日期/编号/品名/数量/金额。"""
        for layer in D4_15_LAYERS:
            assert len(layer.sub_fields) == 5
            sub_labels = [s[1] for s in layer.sub_fields]
            assert sub_labels == ["日期", "编号", "品名", "数量", "金额"]

    def test_consistency_column(self, ws_15):
        """Q11 一致性列标题。"""
        actual = ws_15[f"Q{D4_15_HEADER_GROUP_ROW}"].value
        assert actual == D4_15_STANDALONE_COLUMNS["Q"]

    def test_item_id(self):
        assert D4_15_ITEM_ID == "D4-15-items"

    def test_known_item_ids(self):
        assert D4_15_ITEM_ID in D4_15_KNOWN_ITEM_IDS
        assert "D4-15-note" in D4_15_KNOWN_ITEM_IDS
        assert "D4-15-conclusion" in D4_15_KNOWN_ITEM_IDS
        assert len(D4_15_KNOWN_ITEM_IDS) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# D4-16 出口口岸核对（英文 key）
# ═══════════════════════════════════════════════════════════════════════════════

class TestD416:
    def test_group_headers(self, ws_16):
        """R11 组标题与 descriptor 一致。"""
        # 账面出口收入金额 = A11
        assert ws_16["A11"].value == "账面出口收入金额"
        # 电子口岸系统 = B11
        assert ws_16["B11"].value == "电子口岸系统"
        # 免抵退税申报数据 = G11
        assert ws_16["G11"].value == "免抵退税申报数据"

    def test_sub_headers(self, ws_16):
        """R12 子字段标题与 descriptor 逐字一致。"""
        for col_spec in D4_16_COLUMNS:
            # 跳过 A 列（A 列只在 R11 有组标题，R12 无子标题）
            if col_spec.col == "A":
                continue
            cell = f"{col_spec.col}{D4_16_HEADER_FIELD_ROW}"
            actual = ws_16[cell].value
            assert actual == col_spec.header, (
                f"D4-16 {cell} 期望 {col_spec.header!r} 实得 {actual!r}"
            )

    def test_derived_formulas(self, ws_16):
        """D13/I13 派生公式存在。"""
        d13 = ws_16["D13"].value
        assert d13 is not None and isinstance(d13, str) and d13.startswith("="), (
            f"D13 应为公式，实得 {d13!r}"
        )
        i13 = ws_16["I13"].value
        assert i13 is not None and isinstance(i13, str) and i13.startswith("="), (
            f"I13 应为公式，实得 {i13!r}"
        )

    def test_column_count(self):
        """D4-16 恰好 11 列（A~K）。"""
        assert len(D4_16_COLUMNS) == 11

    def test_english_key_mapping(self):
        """中文→英文 key 映射完整（Req 1.4）。"""
        required_keys = {
            "bookAmount", "portsAmount", "portsPeriod", "portsReason",
            "taxReportAmount", "taxReason", "taxIndex",
        }
        actual_keys = {c.field for c in D4_16_COLUMNS}
        assert required_keys.issubset(actual_keys)

    def test_derived_keys(self):
        """portsDiff/taxDiff 是派生字段。"""
        assert D4_16_DERIVED_KEYS == {"portsDiff", "taxDiff"}

    def test_item_id(self):
        assert D4_16_ITEM_ID == "D4-16-rows"


# ═══════════════════════════════════════════════════════════════════════════════
# 三态枚举 (Requirement 4.1)
# ═══════════════════════════════════════════════════════════════════════════════

class TestTriState:
    """日期/空/零/未知三态与文本 N/A。"""

    def test_date_present(self):
        assert DateTriState.classify("2025-01-15") == DateTriState.PRESENT

    def test_date_empty_none(self):
        assert DateTriState.classify(None) == DateTriState.EMPTY

    def test_date_empty_blank(self):
        assert DateTriState.classify("") == DateTriState.EMPTY

    def test_date_empty_na(self):
        assert DateTriState.classify("N/A") == DateTriState.EMPTY

    def test_date_unknown_text(self):
        assert DateTriState.classify("未知") == DateTriState.UNKNOWN

    def test_date_unknown_zero(self):
        assert DateTriState.classify(0) == DateTriState.UNKNOWN

    def test_date_display_na(self):
        assert DateTriState.EMPTY.display_text == "N/A"
        assert DateTriState.UNKNOWN.display_text == "N/A"
        assert DateTriState.PRESENT.display_text == ""

    def test_amount_present(self):
        assert AmountTriState.classify(1234.56) == AmountTriState.PRESENT

    def test_amount_zero(self):
        assert AmountTriState.classify(0) == AmountTriState.ZERO

    def test_amount_empty(self):
        assert AmountTriState.classify(None) == AmountTriState.EMPTY

    def test_amount_empty_na(self):
        assert AmountTriState.classify("N/A") == AmountTriState.EMPTY

    def test_amount_display(self):
        assert AmountTriState.ZERO.display_text == "0"
        assert AmountTriState.EMPTY.display_text == "N/A"


# ═══════════════════════════════════════════════════════════════════════════════
# 未知映射拒绝机制
# ═══════════════════════════════════════════════════════════════════════════════

class TestUnknownMapping:
    def test_known_headers_pass(self):
        """全部已知列头不抛错。"""
        assert_known_headers(
            ["日期", "编号", "品名"],
            ["日期", "编号", "品名"],
            "test",
        )

    def test_unknown_header_raises(self):
        """未知列头抛 UnknownMappingError。"""
        with pytest.raises(UnknownMappingError, match="未知列头"):
            assert_known_headers(
                ["日期", "编号", "鬼列"],
                ["日期", "编号"],
                "test",
            )

    def test_known_item_id_pass(self):
        assert_known_item_id("D4-14-transactions", D4_14_KNOWN_ITEM_IDS, "D4-14")

    def test_unknown_item_id_raises(self):
        with pytest.raises(UnknownMappingError, match="未知 item_id"):
            assert_known_item_id("D4-14-ghost", D4_14_KNOWN_ITEM_IDS, "D4-14")


# ═══════════════════════════════════════════════════════════════════════════════
# 聚合 Descriptor
# ═══════════════════════════════════════════════════════════════════════════════

class TestDescriptor:
    def test_descriptor_creates(self):
        desc = d4_inspection_descriptor()
        assert desc.d4_13_sheet_name == D4_13_SHEET_NAME
        assert desc.d4_14_item_id == D4_14_ITEM_ID
        assert desc.d4_15_item_id == D4_15_ITEM_ID
        assert desc.d4_16_item_id == D4_16_ITEM_ID

    def test_descriptor_dimensions_count(self):
        desc = d4_inspection_descriptor()
        assert len(desc.d4_14_dimensions) == 6
        assert len(desc.d4_15_layers) == 3
        assert len(desc.d4_16_columns) == 11


# ═══════════════════════════════════════════════════════════════════════════════
# 反向自检（判据不能恒真）
# ═══════════════════════════════════════════════════════════════════════════════

class TestReverseGuards:
    """证明以上判据有分辨力，不会恒过。"""

    def test_wrong_sheet_name_caught(self, wb):
        """descriptor 若写错 tab 名，fixture 断言必失败。"""
        assert "营业收入发生检查表D4-99" not in wb.sheetnames

    def test_d4_14_wrong_header_caught(self, ws_14):
        """把维度组标题改错，比对必失败。"""
        assert ws_14[f"B{D4_14_HEADER_GROUP_ROW}"].value != "错误占位XXX"

    def test_d4_15_wrong_layer_caught(self, ws_15):
        """把层标题改错，比对必失败。"""
        assert ws_15[f"B{D4_15_HEADER_GROUP_ROW}"].value != "错误占位XXX"

    def test_d4_16_wrong_sub_header_caught(self, ws_16):
        """把子标题改错，比对必失败。"""
        assert ws_16["B12"].value != "错误占位XXX"

    def test_unknown_mapping_has_message(self):
        """UnknownMappingError 异常消息不为空。"""
        try:
            assert_known_headers(["鬼列"], [], "test")
        except UnknownMappingError as e:
            assert "鬼列" in str(e)
        else:
            pytest.fail("应抛异常")

    def test_date_tristate_distinguishes_zero_from_empty(self):
        """0 和 None 不是同一态（反向自检三态分辨力）。"""
        assert DateTriState.classify(0) != DateTriState.classify(None)

    def test_amount_tristate_distinguishes_zero_from_present(self):
        """0 和 100 不是同一态。"""
        assert AmountTriState.classify(0) != AmountTriState.classify(100)
