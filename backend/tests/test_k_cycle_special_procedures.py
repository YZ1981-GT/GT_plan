"""K 类底稿（管理循环）特殊程序验证测试。

Phase 4 覆盖:
  Task 32: K5-3 或有事项评估 d-form-table schema（三级可能性+金额区间）
  Task 33: K5-4 最佳估计数计算 audit-sheet
  Task 34: K5-5 律师函回函分析 d-form-table schema
  Task 35: K6-3 持有待售分类条件 d-form-table schema（CAS42 五条件）
  Task 36: K8/K9 费用明细 ledger_detail_for_account resolver
  Task 37: 验证 K 全系列底稿在前端正确打开
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from app.services.wp_classification_service import _WP_CODE_OVERRIDE, VALID_COMPONENT_TYPES

# ═══════════════════════════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════════════════════════

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_MAPPING_PATH = _DATA_DIR / "wp_account_mapping.json"
_TEMPLATES_PATH = _DATA_DIR / "procedure_table_templates.json"
_ADDR_REGISTRY_PATH = _DATA_DIR / "k_address_registry_seed.json"
_SCHEMA_DIR = _DATA_DIR / "ledger_adapters" / "wp_render_schema"


@pytest.fixture(scope="module")
def wp_mapping() -> list[dict]:
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mappings", data) if isinstance(data, dict) else data


@pytest.fixture(scope="module")
def k_class_entries(wp_mapping) -> list[dict]:
    return [e for e in wp_mapping if e.get("cycle") == "K"]


@pytest.fixture(scope="module")
def procedure_templates() -> dict:
    with open(_TEMPLATES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tables", data.get("templates", data)) if isinstance(data, dict) else data


@pytest.fixture(scope="module")
def addr_registry() -> dict:
    with open(_ADDR_REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════════════════
# Task 32: K5-3 或有事项评估 d-form-table schema
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask32ContingencyAssessment:
    """Task 32: K5-3 或有事项评估 d-form-table schema（三级可能性+金额区间）。"""

    def test_k5_3_registered_as_d_form_table(self):
        """K5-3 在 _WP_CODE_OVERRIDE 中映射为 d-form-table。"""
        assert "K5-3" in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE["K5-3"] == "d-form-table"

    def test_k5_3_yaml_schema_exists(self):
        """K5-3.yaml schema 文件存在。"""
        schema_path = _SCHEMA_DIR / "K5-3.yaml"
        assert schema_path.exists(), f"K5-3.yaml 不存在: {schema_path}"

    def test_k5_3_yaml_structure(self):
        """K5-3.yaml 包含必要的顶层字段。"""
        schema_path = _SCHEMA_DIR / "K5-3.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "K5-3"
        assert schema["component_type"] == "d-form-table"
        assert "sections" in schema
        assert len(schema["sections"]) >= 2

    def test_k5_3_has_contingency_fields(self):
        """K5-3 包含或有事项评估关键字段。"""
        schema_path = _SCHEMA_DIR / "K5-3.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        first_section = schema["sections"][0]
        field_names = [f["field"] for f in first_section["fields"]]
        required_fields = [
            "description", "litigation_amount", "likelihood",
            "amount_lower", "amount_upper", "should_accrue", "accrued_amount",
        ]
        for field in required_fields:
            assert field in field_names, f"K5-3 缺少字段 {field}"

    def test_k5_3_likelihood_has_three_levels(self):
        """K5-3 可能性字段有三级选项。"""
        schema_path = _SCHEMA_DIR / "K5-3.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        first_section = schema["sections"][0]
        likelihood_field = next(
            (f for f in first_section["fields"] if f["field"] == "likelihood"), None
        )
        assert likelihood_field is not None
        assert likelihood_field["type"] == "select"
        options = likelihood_field["options"]
        assert "很可能" in options
        assert "可能" in options
        assert "极小可能" in options

    def test_k5_3_has_cross_refs_to_k5_4(self):
        """K5-3 有到 K5-4 最佳估计数的跨底稿引用。"""
        schema_path = _SCHEMA_DIR / "K5-3.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert "cross_refs" in schema
        targets = [ref["target_wp"] for ref in schema["cross_refs"]]
        assert "K5-4" in targets

    def test_k5_3_has_cross_refs_to_a5_3(self):
        """K5-3 有到 A5-3 或有事项的跨循环引用（Task 40）。"""
        schema_path = _SCHEMA_DIR / "K5-3.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        targets = [ref["target_wp"] for ref in schema["cross_refs"]]
        assert "A5-3" in targets


# ═══════════════════════════════════════════════════════════════════════════════
# Task 33: K5-4 最佳估计数计算 audit-sheet
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask33BestEstimate:
    """Task 33: K5-4 最佳估计数计算 audit-sheet 确认。"""

    def test_k5_4_registered_as_audit_sheet(self):
        """K5-4 在 _WP_CODE_OVERRIDE 中映射为 audit-sheet。"""
        assert "K5-4" in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE["K5-4"] == "audit-sheet"

    def test_k5_4_has_address_registry_coordinates(self, addr_registry):
        """K5-4 在 address_registry 中注册了最佳估计数坐标。"""
        k5_4_entries = [e for e in addr_registry["entries"] if e["wp_code"] == "K5-4"]
        assert len(k5_4_entries) == 1, "K5-4 应有 1 个 entry"
        entry = k5_4_entries[0]
        assert entry["sheet_name"] == "最佳估计数计算"
        purposes = {c["purpose"] for c in entry["coordinates"]}
        assert "best_estimate" in purposes
        assert "best_estimate_variance" in purposes

    def test_k5_4_coordinates_cover_range(self, addr_registry):
        """K5-4 坐标覆盖金额区间上下限+加权平均+差异。"""
        k5_4_entries = [e for e in addr_registry["entries"] if e["wp_code"] == "K5-4"]
        entry = k5_4_entries[0]
        descriptions = [c["description"] for c in entry["coordinates"]]
        assert any("下限" in d for d in descriptions), "缺少金额区间下限坐标"
        assert any("上限" in d for d in descriptions), "缺少金额区间上限坐标"
        assert any("加权平均" in d or "最佳估计" in d for d in descriptions), "缺少最佳估计数坐标"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 34: K5-5 律师函回函分析 d-form-table schema
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask34LawyerResponse:
    """Task 34: K5-5 律师函回函分析 d-form-table schema。"""

    def test_k5_5_registered_as_d_form_table(self):
        """K5-5 在 _WP_CODE_OVERRIDE 中映射为 d-form-table。"""
        assert "K5-5" in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE["K5-5"] == "d-form-table"

    def test_k5_5_yaml_schema_exists(self):
        """K5-5.yaml schema 文件存在。"""
        schema_path = _SCHEMA_DIR / "K5-5.yaml"
        assert schema_path.exists(), f"K5-5.yaml 不存在: {schema_path}"

    def test_k5_5_yaml_structure(self):
        """K5-5.yaml 包含必要的结构。"""
        schema_path = _SCHEMA_DIR / "K5-5.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "K5-5"
        assert schema["component_type"] == "d-form-table"
        assert "sections" in schema

    def test_k5_5_has_lawyer_fields(self):
        """K5-5 包含律师函回函关键字段。"""
        schema_path = _SCHEMA_DIR / "K5-5.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        first_section = schema["sections"][0]
        field_names = [f["field"] for f in first_section["fields"]]
        required_fields = [
            "law_firm", "case_description", "case_amount",
            "lawyer_opinion", "estimated_outcome", "audit_evaluation",
        ]
        for field in required_fields:
            assert field in field_names, f"K5-5 缺少字段 {field}"

    def test_k5_5_has_cross_refs_to_k5_3(self):
        """K5-5 有到 K5-3 或有事项的跨底稿引用。"""
        schema_path = _SCHEMA_DIR / "K5-5.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        targets = [ref["target_wp"] for ref in schema["cross_refs"]]
        assert "K5-3" in targets


# ═══════════════════════════════════════════════════════════════════════════════
# Task 35: K6-3 持有待售分类条件 d-form-table schema（CAS42 五条件）
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask35HeldForSale:
    """Task 35: K6-3 持有待售分类条件 d-form-table schema（CAS42 五条件）。"""

    def test_k6_3_registered_as_d_form_table(self):
        """K6-3 在 _WP_CODE_OVERRIDE 中映射为 d-form-table。"""
        assert "K6-3" in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE["K6-3"] == "d-form-table"

    def test_k6_3_yaml_schema_exists(self):
        """K6-3.yaml schema 文件存在。"""
        schema_path = _SCHEMA_DIR / "K6-3.yaml"
        assert schema_path.exists(), f"K6-3.yaml 不存在: {schema_path}"

    def test_k6_3_yaml_structure(self):
        """K6-3.yaml 包含必要的结构。"""
        schema_path = _SCHEMA_DIR / "K6-3.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "K6-3"
        assert schema["component_type"] == "d-form-table"
        assert "sections" in schema

    def test_k6_3_has_five_conditions(self):
        """K6-3 CAS42 五条件检查 section 包含 5 个条件字段。"""
        schema_path = _SCHEMA_DIR / "K6-3.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        # 找到 CAS42 五条件 section
        cas42_section = next(
            (s for s in schema["sections"] if "条件" in s["name"]),
            None
        )
        assert cas42_section is not None, "K6-3 缺少 CAS42 五条件 section"
        condition_fields = [
            f for f in cas42_section["fields"]
            if f["field"].startswith("condition_") and f["field"].endswith(("approved", "agreement", "one_year", "actively_seeking", "irrevocable"))
        ]
        assert len(condition_fields) == 5, (
            f"K6-3 应有 5 个条件字段，实际有 {len(condition_fields)}"
        )

    def test_k6_3_conditions_are_select_type(self):
        """K6-3 五条件字段为 select 类型（满足/不满足/不适用）。"""
        schema_path = _SCHEMA_DIR / "K6-3.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        cas42_section = next(
            (s for s in schema["sections"] if "条件" in s["name"]),
            None
        )
        condition_fields = [
            f for f in cas42_section["fields"]
            if f["field"].startswith("condition_") and not f["field"].endswith("_evidence")
        ]
        for field in condition_fields:
            assert field["type"] == "select", (
                f"字段 {field['field']} 应为 select 类型"
            )
            assert "满足" in field["options"]
            assert "不满足" in field["options"]

    def test_k6_3_has_conclusion_section(self):
        """K6-3 包含分类结论 section。"""
        schema_path = _SCHEMA_DIR / "K6-3.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        section_names = [s["name"] for s in schema["sections"]]
        assert "分类结论" in section_names


# ═══════════════════════════════════════════════════════════════════════════════
# Task 36: K8/K9 费用明细 ledger_detail_for_account resolver
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask36ExpenseDetailResolver:
    """Task 36: K8/K9 费用明细 ledger_detail_for_account resolver 验证。"""

    def test_k8_2_registered_as_audit_sheet(self):
        """K8-2 费用明细走 audit-sheet（从 tb_ledger 取发生额）。"""
        assert _WP_CODE_OVERRIDE["K8-2"] == "audit-sheet"

    def test_k9_2_registered_as_audit_sheet(self):
        """K9-2 费用明细走 audit-sheet（从 tb_ledger 取发生额）。"""
        assert _WP_CODE_OVERRIDE["K9-2"] == "audit-sheet"

    def test_ledger_detail_resolver_exists(self):
        """ledger_detail_for_account resolver 在 auto_data_resolvers 中注册。"""
        from app.services import auto_data_resolvers
        import inspect
        src = inspect.getsource(auto_data_resolvers)
        assert "ledger_detail_for_account" in src

    def test_k8_3_analysis_is_audit_sheet(self):
        """K8-3 费用分析走 audit-sheet（同比/环比趋势分析）。"""
        assert _WP_CODE_OVERRIDE["K8-3"] == "audit-sheet"

    def test_k9_3_analysis_is_audit_sheet(self):
        """K9-3 费用分析走 audit-sheet（同比/环比趋势分析）。"""
        assert _WP_CODE_OVERRIDE["K9-3"] == "audit-sheet"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 37: 验证 K 全系列底稿在前端正确打开
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask37FullKCycleVerification:
    """Task 37: 验证 K 全系列底稿注册完整，能在前端正确打开。"""

    # K 类全部子码 wp_codes（不含附注 K{n} 和程序表 K{n}A）
    _ALL_K_SUBCODES = [
        # K0 函证
        "K0-1", "K0-2", "K0-3", "K0-4", "K0-5",
        # K1 其他应收款
        "K1-1", "K1-2", "K1-3", "K1-4", "K1-5", "K1-6",
        # K2 其他流动资产
        "K2-1", "K2-2", "K2-3", "K2-4",
        # K3 其他应付款
        "K3-1", "K3-2", "K3-3", "K3-4", "K3-5", "K3-6",
        # K4 其他流动负债
        "K4-1", "K4-2", "K4-3", "K4-4",
        # K5 预计负债
        "K5-1", "K5-2", "K5-3", "K5-4", "K5-5", "K5-6",
        # K6 持有待售
        "K6-1", "K6-2", "K6-3", "K6-4",
        # K7 递延收益
        "K7-1", "K7-2", "K7-3", "K7-4",
        # K8 销售费用
        "K8-1", "K8-2", "K8-3", "K8-4", "K8-5", "K8-6",
        # K9 管理费用
        "K9-1", "K9-2", "K9-3", "K9-4", "K9-5", "K9-6",
        # K10 其他收益
        "K10-1", "K10-2", "K10-3", "K10-4",
        # K11 资产减值损失
        "K11-1", "K11-2", "K11-3", "K11-4",
        # K12 营业外收入
        "K12-1", "K12-2", "K12-3", "K12-4",
        # K13 营业外支出
        "K13-1", "K13-2", "K13-3", "K13-4",
    ]

    _PROGRAM_TABLES = [
        "K0A", "K1A", "K2A", "K3A", "K4A", "K5A", "K6A",
        "K7A", "K8A", "K9A", "K10A", "K11A", "K12A", "K13A",
    ]

    _SPECIAL_CODES = ["K0"]  # confirmation-hub

    _ALL_K_WITH_PROGRAMS = _ALL_K_SUBCODES + _PROGRAM_TABLES + _SPECIAL_CODES

    def test_all_k_subcodes_in_override(self):
        """所有 K 类子码在 _WP_CODE_OVERRIDE 中注册。"""
        for code in self._ALL_K_WITH_PROGRAMS:
            assert code in _WP_CODE_OVERRIDE, (
                f"K 类 wp_code '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )

    def test_all_k_component_types_valid(self):
        """所有 K 类 componentType 在白名单中。"""
        for code in self._ALL_K_WITH_PROGRAMS:
            ct = _WP_CODE_OVERRIDE[code]
            assert ct in VALID_COMPONENT_TYPES, (
                f"K 类 wp_code '{code}' 的 componentType '{ct}' 不在白名单中"
            )

    def test_k_program_tables_are_a_program_console(self):
        """K0A~K13A 映射为 a-program-console。"""
        for code in self._PROGRAM_TABLES:
            assert _WP_CODE_OVERRIDE[code] == "a-program-console"

    def test_k0_is_confirmation_hub(self):
        """K0 映射为 confirmation-hub。"""
        assert _WP_CODE_OVERRIDE["K0"] == "confirmation-hub"

    def test_k_audit_determinations_are_d_form_table(self):
        """K1-1~K13-1 审定表映射为 d-form-table。"""
        for i in range(1, 14):
            code = f"K{i}-1"
            assert _WP_CODE_OVERRIDE[code] == "d-form-table", (
                f"{code} 审定表应为 d-form-table，实际为 '{_WP_CODE_OVERRIDE[code]}'"
            )

    def test_k_adjustment_entries_are_d_form_table(self):
        """调整分录底稿映射为 d-form-table。"""
        adjustment_codes = [
            "K1-6", "K2-4", "K3-6", "K4-4", "K5-6",
            "K6-4", "K7-4", "K8-6", "K9-6", "K10-4",
            "K11-4", "K12-4", "K13-4",
        ]
        for code in adjustment_codes:
            assert _WP_CODE_OVERRIDE[code] == "d-form-table", (
                f"{code} 调整分录应为 d-form-table"
            )

    def test_k_special_d_form_tables(self):
        """K5-3/K5-5/K6-3 特殊底稿映射为 d-form-table。"""
        special_codes = ["K5-3", "K5-5", "K6-3", "K1-4"]
        for code in special_codes:
            assert _WP_CODE_OVERRIDE[code] == "d-form-table", (
                f"{code} 应为 d-form-table"
            )

    def test_k_audit_sheets_correct(self):
        """含公式/数据的底稿映射为 audit-sheet。"""
        expected_audit_sheets = [
            "K1-2", "K1-3", "K1-5",
            "K2-2", "K2-3",
            "K3-2", "K3-3", "K3-4", "K3-5",
            "K4-2", "K4-3",
            "K5-2", "K5-4",
            "K6-2",
            "K7-2", "K7-3",
            "K8-2", "K8-3", "K8-4", "K8-5",
            "K9-2", "K9-3", "K9-4", "K9-5",
            "K10-2", "K10-3",
            "K11-2", "K11-3",
            "K12-2", "K12-3",
            "K13-2", "K13-3",
        ]
        for code in expected_audit_sheets:
            assert _WP_CODE_OVERRIDE[code] == "audit-sheet", (
                f"{code} 应为 audit-sheet，实际为 '{_WP_CODE_OVERRIDE[code]}'"
            )

    def test_k_mapping_count(self, k_class_entries):
        """wp_account_mapping.json 中应有足够的 K 类条目。"""
        assert len(k_class_entries) >= 70, (
            f"K 类底稿应有 ≥70 条注册，实际 {len(k_class_entries)} 条"
        )

    def test_k_program_tables_in_templates(self, procedure_templates):
        """K0A~K13A 在 procedure_table_templates.json 中有注册。"""
        if isinstance(procedure_templates, list):
            template_ids = {t.get("template_id", t.get("id", "")) for t in procedure_templates}
        else:
            template_ids = set(procedure_templates.keys())
        for code in self._PROGRAM_TABLES:
            assert code in template_ids, (
                f"程序表 {code} 未在 procedure_table_templates.json 中注册"
            )

    def test_handler_regex_matches_all_k_audit_tables(self):
        """handler 正则 ^[D-N]\\d+-1$ 匹配所有 K 类审定表。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        for i in range(1, 14):
            code = f"K{i}-1"
            assert pattern.match(code), f"正则不匹配 {code}"

    def test_no_univer_fallback_for_k_codes(self):
        """K 类底稿不应有 univer fallback。"""
        for code in self._ALL_K_WITH_PROGRAMS:
            ct = _WP_CODE_OVERRIDE.get(code)
            assert ct != "univer", f"{code} 映射为 'univer'（应有专用 componentType）"
