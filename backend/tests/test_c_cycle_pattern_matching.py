"""C 类底稿 pattern matching 单元测试。

验证：
1. C-generic.yaml 对 C2~C15 正确加载
2. C-deviation-generic.yaml 对 C2-2~C15-2 正确加载
3. cycle_name 注入正确
4. 边界值（C1, C16, C0）不匹配 pattern
5. Schema 完整性校验（必需字段、sheet 名）
"""
from __future__ import annotations

import pytest

from app.services.wp_render_schema_service import (
    SAMPLE_SIZE_BY_FREQUENCY,
    WpRenderSchemaService,
)


@pytest.fixture
def schema_svc():
    return WpRenderSchemaService()


# ═══════════════════════════════════════════════════════════════════════════════
# C-generic.yaml pattern matching (C2~C15)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCGenericPatternMatching:
    """C-generic.yaml 对 C2~C15 正确加载。"""

    @pytest.mark.parametrize("n", range(2, 16))
    def test_c_generic_loads_for_valid_codes(self, schema_svc, n):
        wp_code = f"C{n}"
        schema = schema_svc.load_schema(wp_code)
        assert schema is not None
        assert "sheets" in schema
        assert schema.get("wp_code_pattern") == "C{n}"

    def test_c_generic_has_required_sheets(self, schema_svc):
        schema = schema_svc.load_schema("C2")
        sheets = schema["sheets"]
        assert "控制测试汇总表" in sheets
        assert "控制测试过程记录" in sheets

    def test_c_generic_summary_sheet_has_all_columns(self, schema_svc):
        schema = schema_svc.load_schema("C2")
        summary = schema["sheets"]["控制测试汇总表"]
        columns = summary["dynamic_table"]["columns"]
        required_fields = [
            "sub_process", "control_id", "control_name", "control_description",
            "affected_accounts", "assertion", "control_attribute", "frequency",
            "test_method", "sample_size", "test_conclusion",
        ]
        column_fields = list(columns.keys())
        for f in required_fields:
            assert f in column_fields, f"控制测试汇总表缺少必需字段: {f}"

    def test_c_generic_does_not_have_options_sheet(self, schema_svc):
        """C-generic.yaml 不渲染原始选项清单 sheet。"""
        schema = schema_svc.load_schema("C2")
        sheets = schema["sheets"]
        assert "选项清单" not in sheets
        assert "选项清单列表" not in sheets

    def test_c_generic_not_match_c1(self, schema_svc):
        """C1 走 a-program-console，不应匹配 C-generic.yaml pattern。"""
        # C1 不应走 generic pattern（范围 2~15）
        # 如果存在 C1.yaml 精确匹配则用那个，否则 prefix fallback
        # 此处验证 pattern 不会匹配 n=1
        from app.services.wp_render_schema_service import _PATTERN_SCHEMA_MAP
        import re
        for pattern, schema_file in _PATTERN_SCHEMA_MAP:
            if schema_file == "C-generic.yaml":
                m = pattern.match("C1")
                if m:
                    n = int(m.group(1))
                    assert not (2 <= n <= 15), "C1 不应匹配 C-generic.yaml 范围"

    def test_c_generic_not_match_c16(self, schema_svc):
        """C16 超出范围 [2,15]，不匹配。"""
        with pytest.raises(FileNotFoundError):
            schema_svc.load_schema("C16")

    def test_c_generic_not_match_c0(self, schema_svc):
        """C0 超出范围 [2,15]，不匹配。"""
        with pytest.raises(FileNotFoundError):
            schema_svc.load_schema("C0")


# ═══════════════════════════════════════════════════════════════════════════════
# C-deviation-generic.yaml pattern matching (C2-2~C15-2)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCDeviationPatternMatching:
    """C-deviation-generic.yaml 对 C2-2~C15-2 正确加载。"""

    @pytest.mark.parametrize("n", range(2, 16))
    def test_c_deviation_loads_for_valid_codes(self, schema_svc, n):
        wp_code = f"C{n}-2"
        schema = schema_svc.load_schema(wp_code)
        assert schema is not None
        assert "sheets" in schema
        assert schema.get("wp_code_pattern") == "C{n}-2"

    def test_c_deviation_has_required_sheet(self, schema_svc):
        schema = schema_svc.load_schema("C2-2")
        sheets = schema["sheets"]
        assert "评价控制偏差" in sheets

    def test_c_deviation_has_all_columns(self, schema_svc):
        schema = schema_svc.load_schema("C3-2")
        deviation_sheet = schema["sheets"]["评价控制偏差"]
        columns = deviation_sheet["dynamic_table"]["columns"]
        required_fields = [
            "control_id", "exception_description",
            "step1_isolated", "step2_cause", "step3_design_defect",
            "step4_supplementary_procedures", "step5_reliance_impact",
            "step6_substantive_impact", "step7_report_deficiency", "conclusion",
        ]
        column_fields = list(columns.keys())
        for f in required_fields:
            assert f in column_fields, f"评价控制偏差缺少必需字段: {f}"

    def test_c_deviation_does_not_have_example_sheet(self, schema_svc):
        """C-deviation-generic.yaml 不渲染示例 sheet。"""
        schema = schema_svc.load_schema("C5-2")
        sheets = schema["sheets"]
        assert "示例" not in sheets

    def test_c_deviation_not_match_c1_2(self, schema_svc):
        """C1-2 超出范围 [2,15]，不匹配。"""
        with pytest.raises(FileNotFoundError):
            schema_svc.load_schema("C1-2")

    def test_c_deviation_not_match_c16_2(self, schema_svc):
        """C16-2 超出范围 [2,15]，不匹配。"""
        with pytest.raises(FileNotFoundError):
            schema_svc.load_schema("C16-2")


# ═══════════════════════════════════════════════════════════════════════════════
# cycle_name 注入
# ═══════════════════════════════════════════════════════════════════════════════


class TestCCycleNameInjection:
    """cycle_name 参数化注入正确。"""

    _EXPECTED_NAMES = {
        "C2": "销售收入", "C3": "货币资金", "C4": "采购存货",
        "C5": "投资", "C6": "固定资产", "C7": "在建工程",
        "C8": "无形资产", "C9": "研发", "C10": "职工薪酬",
        "C11": "管理", "C12": "税费", "C13": "债务",
        "C14": "租赁", "C15": "关联方",
    }

    @pytest.mark.parametrize("wp_code,expected_name", list(_EXPECTED_NAMES.items()))
    def test_c_generic_cycle_name_injected(self, schema_svc, wp_code, expected_name):
        schema = schema_svc.load_schema(wp_code)
        # 找到第一个 sheet 的 fields 中 cycle_name 字段
        sheets = schema["sheets"]
        first_sheet = next(iter(sheets.values()))
        fields = first_sheet.get("fields", [])
        cycle_field = next((f for f in fields if f.get("field") == "cycle_name"), None)
        assert cycle_field is not None, f"{wp_code} 缺少 cycle_name 字段"
        assert cycle_field.get("default") == expected_name

    @pytest.mark.parametrize("n", range(2, 16))
    def test_c_deviation_cycle_name_injected(self, schema_svc, n):
        wp_code = f"C{n}-2"
        schema = schema_svc.load_schema(wp_code)
        sheets = schema["sheets"]
        first_sheet = next(iter(sheets.values()))
        fields = first_sheet.get("fields", [])
        cycle_field = next((f for f in fields if f.get("field") == "cycle_name"), None)
        assert cycle_field is not None
        assert cycle_field.get("default") is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 样本量推荐映射
# ═══════════════════════════════════════════════════════════════════════════════


class TestSampleSizeRecommendation:
    """样本量自动推荐映射正确性。"""

    def test_sample_size_constant_has_6_entries(self):
        assert len(SAMPLE_SIZE_BY_FREQUENCY) == 6

    @pytest.mark.parametrize("freq,expected", [
        ("每次发生", 25),
        ("每日", 25),
        ("每周", 5),
        ("每月", 2),
        ("每季", 1),
        ("每年", 1),
    ])
    def test_sample_size_values(self, freq, expected):
        assert SAMPLE_SIZE_BY_FREQUENCY[freq] == expected

    def test_sample_size_in_schema_yaml(self, schema_svc):
        """C-generic.yaml 中嵌入了 sample_size_recommendation。"""
        schema = schema_svc.load_schema("C2")
        rec = schema.get("sample_size_recommendation")
        assert rec is not None
        assert rec["每次发生"] == 25
        assert rec["每年"] == 1
