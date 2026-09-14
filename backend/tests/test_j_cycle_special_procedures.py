"""J 类底稿（职工薪酬循环）特殊程序验证测试。

Phase 4 覆盖:
  Task 19: J1-3 工资测算 → audit-sheet（人数×平均工资×月份）
  Task 20: J2-3 精算假设评估 → d-form-table（折现率/工资增长率/离职率/死亡率）
  Task 21: J2-5 精算重新计算 → audit-sheet（DBO/计划资产/净负债）
  Task 22: J3-4 期权定价 → audit-sheet（Black-Scholes 参数+公式）
  Task 23: 验证 J 全系列底稿在前端正确打开（注册完整性+类型正确性）
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
_ADDR_REGISTRY_PATH = _DATA_DIR / "j_address_registry_seed.json"
_SCHEMA_DIR = _DATA_DIR / "ledger_adapters" / "wp_render_schema"


@pytest.fixture(scope="module")
def wp_mapping() -> list[dict]:
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mappings", data) if isinstance(data, dict) else data


@pytest.fixture(scope="module")
def j_class_entries(wp_mapping) -> list[dict]:
    return [e for e in wp_mapping if e.get("cycle") == "J"]


@pytest.fixture(scope="module")
def procedure_templates() -> dict:
    with open(_TEMPLATES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("templates", data) if isinstance(data, dict) else data


@pytest.fixture(scope="module")
def addr_registry() -> dict:
    with open(_ADDR_REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════════════════
# Task 19: J1-3 工资测算 → audit-sheet 确认
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask19WageCalculation:
    """Task 19: 确认 J1-3 工资测算 audit-sheet schema（人数×平均工资×月份）"""

    def test_j1_3_registered_as_audit_sheet(self):
        """J1-3 在 _WP_CODE_OVERRIDE 中映射为 audit-sheet。"""
        assert "J1-3" in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE["J1-3"] == "audit-sheet", (
            f"J1-3 应为 audit-sheet，实际为 '{_WP_CODE_OVERRIDE['J1-3']}'"
        )

    def test_j1_3_comment_describes_formula(self):
        """J1-3 的注释描述了工资测算公式逻辑（人数×平均工资×月份）。"""
        # 通过读取源代码验证注释中描述了公式
        import inspect
        import app.services.wp_classification_service as mod
        source = inspect.getsource(mod)
        # 确认 J1-3 附近有工资测算描述
        assert "J1-3" in source
        assert "工资测算" in source

    def test_j1_3_has_address_registry_coordinates(self, addr_registry):
        """J1-3 在 address_registry 中注册了工资测算坐标。"""
        j1_3_entries = [e for e in addr_registry["entries"] if e["wp_code"] == "J1-3"]
        assert len(j1_3_entries) == 1, "J1-3 应有 1 个 entry"
        entry = j1_3_entries[0]
        assert entry["sheet_name"] == "工资测算"
        # 验证有合计/人数/人均月工资/差异坐标
        purposes = {c["purpose"] for c in entry["coordinates"]}
        assert "wage_calculation" in purposes
        assert "wage_variance" in purposes

    def test_j1_3_no_yaml_schema_needed(self):
        """audit-sheet 类型不需要 YAML schema（OnlyOffice 直接渲染）。"""
        schema_path = _SCHEMA_DIR / "J1-3.yaml"
        # audit-sheet 不需要 YAML schema，如果存在也OK但不是必需
        # 这里确认的是：J1-3 是 audit-sheet 走 OnlyOffice 渲染路径
        assert _WP_CODE_OVERRIDE["J1-3"] == "audit-sheet"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 20: J2-3 精算假设评估 → d-form-table 确认 + YAML schema
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask20ActuarialAssumptions:
    """Task 20: 确认 J2-3 精算假设评估 d-form-table schema。"""

    def test_j2_3_registered_as_d_form_table(self):
        """J2-3 在 _WP_CODE_OVERRIDE 中映射为 d-form-table。"""
        assert "J2-3" in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE["J2-3"] == "d-form-table", (
            f"J2-3 应为 d-form-table，实际为 '{_WP_CODE_OVERRIDE['J2-3']}'"
        )

    def test_j2_3_yaml_schema_exists(self):
        """J2-3.yaml schema 文件存在。"""
        schema_path = _SCHEMA_DIR / "J2-3.yaml"
        assert schema_path.exists(), f"J2-3.yaml 不存在: {schema_path}"

    def test_j2_3_yaml_schema_structure(self):
        """J2-3.yaml 包含必要的顶层字段和正确的 componentType。"""
        schema_path = _SCHEMA_DIR / "J2-3.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)

        assert schema["wp_code"] == "J2-3"
        assert schema["component_type"] == "d-form-table"
        assert "sections" in schema
        assert len(schema["sections"]) >= 4  # 至少4个假设参数

    def test_j2_3_yaml_covers_all_assumptions(self):
        """J2-3.yaml sections 覆盖折现率/工资增长率/离职率/死亡率。"""
        schema_path = _SCHEMA_DIR / "J2-3.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)

        section_names = [s["name"] for s in schema["sections"]]
        required_assumptions = ["折现率", "工资增长率", "离职率", "死亡率"]
        for assumption in required_assumptions:
            assert assumption in section_names, (
                f"J2-3 schema 缺少假设参数: {assumption}"
            )

    def test_j2_3_yaml_fields_complete(self):
        """J2-3.yaml 每个 section 包含管理层假设/审计师评价/同行业对比/结论字段。"""
        schema_path = _SCHEMA_DIR / "J2-3.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)

        required_fields = {
            "management_assumption",
            "auditor_evaluation",
            "industry_benchmark",
            "conclusion",
        }

        for section in schema["sections"]:
            field_names = {f["field"] for f in section["fields"]}
            missing = required_fields - field_names
            assert not missing, (
                f"section '{section['name']}' 缺少字段: {missing}"
            )

    def test_j2_3_auditor_evaluation_is_select(self):
        """J2-3 审计师评价字段为 select 类型，选项为 合理/不合理。"""
        schema_path = _SCHEMA_DIR / "J2-3.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)

        first_section = schema["sections"][0]
        eval_field = next(
            (f for f in first_section["fields"] if f["field"] == "auditor_evaluation"),
            None,
        )
        assert eval_field is not None
        assert eval_field["type"] == "select"
        assert "合理" in eval_field["options"]
        assert "不合理" in eval_field["options"]


# ═══════════════════════════════════════════════════════════════════════════════
# Task 21: J2-5 精算重新计算 → audit-sheet 确认
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask21ActuarialRecalculation:
    """Task 21: 确认 J2-5 精算重新计算 audit-sheet schema（DBO/计划资产/净负债）。"""

    def test_j2_5_registered_as_audit_sheet(self):
        """J2-5 在 _WP_CODE_OVERRIDE 中映射为 audit-sheet。"""
        assert "J2-5" in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE["J2-5"] == "audit-sheet", (
            f"J2-5 应为 audit-sheet，实际为 '{_WP_CODE_OVERRIDE['J2-5']}'"
        )

    def test_j2_5_has_address_registry_coordinates(self, addr_registry):
        """J2-5 在 address_registry 中注册了精算重算坐标。"""
        j2_5_entries = [e for e in addr_registry["entries"] if e["wp_code"] == "J2-5"]
        assert len(j2_5_entries) == 1, "J2-5 应有 1 个 entry"
        entry = j2_5_entries[0]
        assert entry["sheet_name"] == "精算重新计算"
        purposes = {c["purpose"] for c in entry["coordinates"]}
        # 必须有 DBO + 净负债计算相关坐标
        assert "actuarial_calc" in purposes
        assert "actuarial_net_liability" in purposes

    def test_j2_5_coordinates_cover_dbo_and_plan_assets(self, addr_registry):
        """J2-5 坐标覆盖 DBO现值、计划资产公允价值、净负债。"""
        j2_5_entries = [e for e in addr_registry["entries"] if e["wp_code"] == "J2-5"]
        entry = j2_5_entries[0]
        descriptions = [c["description"] for c in entry["coordinates"]]
        # 关键项
        assert any("DBO" in d or "设定受益义务" in d for d in descriptions), (
            "J2-5 缺少 DBO 坐标"
        )
        assert any("计划资产" in d for d in descriptions), (
            "J2-5 缺少计划资产坐标"
        )
        assert any("净负债" in d for d in descriptions), (
            "J2-5 缺少净负债坐标"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 22: J3-4 期权定价 → audit-sheet 确认
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask22OptionPricing:
    """Task 22: 确认 J3-4 期权定价 audit-sheet schema（Black-Scholes 参数+公式）。"""

    def test_j3_4_registered_as_audit_sheet(self):
        """J3-4 在 _WP_CODE_OVERRIDE 中映射为 audit-sheet。"""
        assert "J3-4" in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE["J3-4"] == "audit-sheet", (
            f"J3-4 应为 audit-sheet，实际为 '{_WP_CODE_OVERRIDE['J3-4']}'"
        )

    def test_j3_4_has_address_registry_coordinates(self, addr_registry):
        """J3-4 在 address_registry 中注册了期权定价坐标。"""
        j3_4_entries = [e for e in addr_registry["entries"] if e["wp_code"] == "J3-4"]
        assert len(j3_4_entries) == 1, "J3-4 应有 1 个 entry"
        entry = j3_4_entries[0]
        assert entry["sheet_name"] == "期权公允价值测算"
        purposes = {c["purpose"] for c in entry["coordinates"]}
        assert "option_pricing" in purposes

    def test_j3_4_coordinates_cover_bs_parameters(self, addr_registry):
        """J3-4 坐标覆盖 Black-Scholes 模型关键参数。"""
        j3_4_entries = [e for e in addr_registry["entries"] if e["wp_code"] == "J3-4"]
        entry = j3_4_entries[0]
        descriptions = [c["description"] for c in entry["coordinates"]]
        # Black-Scholes 五要素
        assert any("公允价值" in d for d in descriptions), "缺少公允价值坐标"
        assert any("行权价格" in d for d in descriptions), "缺少行权价格坐标"
        assert any("标的股价" in d or "股价" in d for d in descriptions), "缺少股价坐标"
        assert any("波动率" in d for d in descriptions), "缺少波动率坐标"
        assert any("无风险利率" in d for d in descriptions), "缺少无风险利率坐标"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 23: 验证 J 全系列底稿在前端正确打开
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask23FullJCycleVerification:
    """Task 23: 验证 J 全系列底稿注册完整，能在前端正确打开。"""

    # J 类全部 wp_codes（不含程序表 J{n}A）
    _ALL_J_CODES = [
        # J1 应付职工薪酬
        "J1-1", "J1-2", "J1-3", "J1-4", "J1-5", "J1-6", "J1-7", "J1-8",
        # J2 设定受益计划
        "J2-1", "J2-2", "J2-3", "J2-4", "J2-5", "J2-6",
        # J3 股份支付
        "J3-1", "J3-2", "J3-3", "J3-4", "J3-5", "J3-6",
    ]

    # J 类程序表
    _PROGRAM_TABLES = ["J1A", "J2A", "J3A"]

    # 所有 J 类 wp_codes（含程序表）
    _ALL_J_WITH_PROGRAMS = _ALL_J_CODES + _PROGRAM_TABLES

    # ─── P0: 注册完整性 ──────────────────────────────────────────────────────

    def test_all_j_codes_in_override(self):
        """所有 J 类 wp_code 在 _WP_CODE_OVERRIDE 中注册。"""
        for code in self._ALL_J_WITH_PROGRAMS:
            assert code in _WP_CODE_OVERRIDE, (
                f"J 类 wp_code '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )

    def test_all_j_component_types_valid(self):
        """所有 J 类 componentType 在白名单中。"""
        for code in self._ALL_J_WITH_PROGRAMS:
            ct = _WP_CODE_OVERRIDE[code]
            assert ct in VALID_COMPONENT_TYPES, (
                f"J 类 wp_code '{code}' 的 componentType '{ct}' 不在白名单中"
            )

    def test_j_mapping_count(self, j_class_entries):
        """wp_account_mapping.json 中应有足够的 J 类条目。"""
        # J1~J3 约 23 条（含附注 J1/J2/J3）
        assert len(j_class_entries) >= 20, (
            f"J 类底稿应有 ≥20 条注册，实际 {len(j_class_entries)} 条"
        )

    # ─── P1: 程序表注册 ──────────────────────────────────────────────────────

    def test_j_program_tables_are_dedicated_components(self):
        """J1A~J3A 映射为对应专属组件（整册内分发程序表，对齐 H1A/L1A）。"""
        expected = {
            "J1A": "j1-employee-compensation",
            "J2A": "j2-defined-benefit-plan",
            "J3A": "j3-share-based-payment",
        }
        for code, ct in expected.items():
            assert _WP_CODE_OVERRIDE[code] == ct, (
                f"{code} 应为 {ct}，实际为 '{_WP_CODE_OVERRIDE[code]}'"
            )

    def test_j_program_tables_in_templates(self, procedure_templates):
        """J1A~J3A 在 procedure_table_templates.json 中有注册。"""
        if isinstance(procedure_templates, list):
            template_ids = {t.get("template_id", t.get("id", "")) for t in procedure_templates}
        else:
            template_ids = set(procedure_templates.keys())
        for code in self._PROGRAM_TABLES:
            assert code in template_ids, (
                f"程序表 {code} 未在 procedure_table_templates.json 中注册"
            )

    # ─── P2: 审定表验证 ──────────────────────────────────────────────────────

    def test_j_audit_determinations_are_dedicated_components(self):
        """J1-1/J2-1/J3-1 审定表映射为对应专属组件（整册内分发）。"""
        expected = {
            "J1-1": "j1-employee-compensation",
            "J2-1": "j2-defined-benefit-plan",
            "J3-1": "j3-share-based-payment",
        }
        for code, ct in expected.items():
            assert _WP_CODE_OVERRIDE[code] == ct, (
                f"{code} 审定表应为 {ct}，实际为 '{_WP_CODE_OVERRIDE[code]}'"
            )

    def test_j_audit_determination_schemas_exist(self):
        """J1-1/J2-1/J3-1 审定表 YAML schema 文件存在。"""
        for code in ["J1-1", "J2-1", "J3-1"]:
            schema_path = _SCHEMA_DIR / f"{code}.yaml"
            assert schema_path.exists(), f"{code}.yaml 不存在: {schema_path}"

    def test_j_audit_determination_match_handler_regex(self):
        """J1-1/J2-1/J3-1 匹配审定表回写正则 ^[D-N]\\d+-1$。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        for code in ["J1-1", "J2-1", "J3-1"]:
            assert pattern.match(code), (
                f"{code} 不匹配审定表回写正则 '^[D-N]\\d+-1$'"
            )

    # ─── P4: 特殊程序 componentType 正确性 ────────────────────────────────────

    def test_audit_sheet_types_correct(self):
        """含公式/测算的底稿正确映射为 audit-sheet。"""
        expected_audit_sheets = [
            "J1-2",  # 明细表
            "J1-3",  # 工资测算（人数×平均工资×月份）
            "J1-4",  # 社保测算
            "J1-5",  # 分析程序
            "J1-6",  # 检查
            "J1-7",  # 个税验证
            "J2-2",  # 设定受益计划明细
            "J2-5",  # 精算重新计算（DBO/计划资产/净负债）
            "J3-2",  # 股份支付明细
            "J3-4",  # 期权定价（Black-Scholes）
            "J3-5",  # 费用分摊
        ]
        for code in expected_audit_sheets:
            assert _WP_CODE_OVERRIDE[code] == "audit-sheet", (
                f"{code} 应为 audit-sheet，实际为 '{_WP_CODE_OVERRIDE[code]}'"
            )

    def test_d_form_table_types_correct(self):
        """结构化检查/调整分录底稿正确映射为 d-form-table。"""
        expected_d_form = [
            "J1-8",  # 调整分录
            "J2-3",  # 精算假设评估
            "J2-4",  # 精算师工作利用
            "J2-6",  # 调整分录
            "J3-3",  # 授予条件检查
            "J3-6",  # 调整分录
        ]
        for code in expected_d_form:
            assert _WP_CODE_OVERRIDE[code] == "d-form-table", (
                f"{code} 应为 d-form-table，实际为 '{_WP_CODE_OVERRIDE[code]}'"
            )

    # ─── 前端可打开验证（componentType 完整性） ───────────────────────────────

    def test_no_univer_fallback_for_j_codes(self):
        """J 类底稿不应有 univer fallback（全部有显式映射）。"""
        for code in self._ALL_J_WITH_PROGRAMS:
            ct = _WP_CODE_OVERRIDE.get(code)
            assert ct is not None, f"{code} 无 componentType 映射"
            assert ct != "univer", (
                f"{code} 映射为 'univer'（应有专用 componentType）"
            )

    def test_j_codes_have_consistent_naming(self, j_class_entries):
        """J 类 wp_code 命名符合 J{n}-{m} 模式。"""
        pattern = re.compile(r"^J\d+(-\d+)?$")
        for entry in j_class_entries:
            code = entry["wp_code"]
            # 跳过附注 sheet（J1/J2/J3 纯前缀）
            if code in ("J1", "J2", "J3"):
                continue
            # 跳过程序表
            if code.endswith("A"):
                continue
            assert pattern.match(code), (
                f"J 类 wp_code '{code}' 命名不符合 J{{n}}-{{m}} 模式"
            )
