"""J 类底稿（职工薪酬循环）联动完善验证测试。

Phase 5 覆盖:
  Task 24: J{n}A 程序表 risk_for_cycle + control_test_result_for_cycle 绑定
  Task 25: J2→B51 accounting_estimate_b51 精算假设联动
  Task 26: J3→M4 资本公积 ref_index 跳转
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

# ═══════════════════════════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════════════════════════

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_TEMPLATES_PATH = _DATA_DIR / "procedure_table_templates.json"
_SCHEMA_DIR = _DATA_DIR / "ledger_adapters" / "wp_render_schema"


@pytest.fixture(scope="module")
def procedure_templates() -> dict:
    with open(_TEMPLATES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    # Templates may be inside "tables" key or at top level (G~J cycles are top-level)
    tables = dict(data.get("tables", {}))
    # Merge any top-level template entries (keys that look like cycle codes)
    for key, value in data.items():
        if key not in ("version", "description", "tables") and isinstance(value, dict) and "items" in value:
            tables[key] = value
    return tables


@pytest.fixture(scope="module")
def j2_3_schema() -> dict:
    schema_path = _SCHEMA_DIR / "J2-3.yaml"
    with open(schema_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def j3_1_schema() -> dict:
    schema_path = _SCHEMA_DIR / "J3-1.yaml"
    with open(schema_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ═══════════════════════════════════════════════════════════════════════════════
# Task 24: J{n}A 程序表 risk_for_cycle + control_test_result_for_cycle 绑定
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask24ProcedureTableRiskControlBinding:
    """验证 J1A/J2A/J3A 程序表首步绑定 risk_for_cycle，
    末步绑定 control_test_result_for_cycle。"""

    @pytest.mark.parametrize("template_key", ["J1A", "J2A", "J3A"])
    def test_first_step_has_risk_for_cycle(self, procedure_templates, template_key):
        """程序表第一步 auto_data_source 应为 risk_for_cycle。"""
        template = procedure_templates[template_key]
        items = template["items"]
        first_item = items[0]
        assert first_item["auto_data_source"] == "risk_for_cycle", (
            f"{template_key} seq1 auto_data_source 应为 risk_for_cycle，"
            f"实际为 {first_item.get('auto_data_source')}"
        )

    @pytest.mark.parametrize("template_key", ["J1A", "J2A", "J3A"])
    def test_last_step_has_control_test_result_for_cycle(self, procedure_templates, template_key):
        """程序表最后一步 auto_data_source 应为 control_test_result_for_cycle。"""
        template = procedure_templates[template_key]
        items = template["items"]
        last_item = items[-1]
        assert last_item["auto_data_source"] == "control_test_result_for_cycle", (
            f"{template_key} 最后一步 auto_data_source 应为 control_test_result_for_cycle，"
            f"实际为 {last_item.get('auto_data_source')}"
        )

    @pytest.mark.parametrize("template_key", ["J1A", "J2A", "J3A"])
    def test_template_exists_and_has_items(self, procedure_templates, template_key):
        """程序表存在且至少有 2 个步骤（首末可区分）。"""
        assert template_key in procedure_templates, f"{template_key} 未在 procedure_table_templates.json 中注册"
        template = procedure_templates[template_key]
        items = template["items"]
        assert len(items) >= 2, f"{template_key} 步骤数不足 2"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 25: J2→B51 accounting_estimate_b51 精算假设联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask25J2B51AccountingEstimateLinkage:
    """验证 J2-3.yaml 已配置 accounting_estimate_b51 auto_data_source，
    实现精算假设→B51 会计估计风险联动。"""

    def test_j2_3_has_auto_data_source_section(self, j2_3_schema):
        """J2-3.yaml 应有 auto_data_source 配置。"""
        assert "auto_data_source" in j2_3_schema, (
            "J2-3.yaml 缺少 auto_data_source 配置"
        )

    def test_j2_3_references_accounting_estimate_b51(self, j2_3_schema):
        """J2-3 auto_data_source 应引用 accounting_estimate_b51。"""
        auto_sources = j2_3_schema["auto_data_source"]
        # auto_data_source 可能是列表或字典
        if isinstance(auto_sources, list):
            source_names = [s.get("source") for s in auto_sources]
        elif isinstance(auto_sources, dict):
            source_names = [auto_sources.get("source")]
        else:
            source_names = [str(auto_sources)]

        assert "accounting_estimate_b51" in source_names, (
            f"J2-3 auto_data_source 应包含 accounting_estimate_b51，"
            f"实际为 {source_names}"
        )

    def test_j2_3_cross_ref_mentions_b51(self, j2_3_schema):
        """J2-3 cross_refs 应包含到 B51 的引用。"""
        cross_refs = j2_3_schema.get("cross_refs", [])
        b51_refs = [r for r in cross_refs if r.get("target_wp") == "B51"]
        assert len(b51_refs) >= 1, (
            "J2-3.yaml cross_refs 中应至少有一条引用 B51 的条目"
        )

    def test_j2_3_b51_cross_ref_describes_accounting_estimate(self, j2_3_schema):
        """J2-3→B51 cross_ref 描述应包含会计估计相关信息。"""
        cross_refs = j2_3_schema.get("cross_refs", [])
        b51_refs = [r for r in cross_refs if r.get("target_wp") == "B51"]
        assert len(b51_refs) >= 1
        ref = b51_refs[0]
        description = ref.get("description", "")
        assert "会计估计" in description or "估计" in description or "精算" in description, (
            f"B51 cross_ref 描述应提及会计估计，实际描述: {description}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 26: J3→M4 资本公积 ref_index 跳转
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask26J3M4CapitalReserveRef:
    """验证 J3-1.yaml 包含到 M4（资本公积）的 cross_ref 跳转配置。"""

    def test_j3_1_has_cross_refs(self, j3_1_schema):
        """J3-1.yaml 应有 cross_refs 配置。"""
        assert "cross_refs" in j3_1_schema, (
            "J3-1.yaml 缺少 cross_refs 配置"
        )

    def test_j3_1_cross_ref_includes_m4(self, j3_1_schema):
        """J3-1 cross_refs 应包含到 M4 的引用。"""
        cross_refs = j3_1_schema.get("cross_refs", [])
        m4_refs = [r for r in cross_refs if r.get("target_wp") == "M4"]
        assert len(m4_refs) >= 1, (
            "J3-1.yaml cross_refs 中应至少有一条引用 M4（资本公积）的条目"
        )

    def test_j3_1_m4_ref_is_outbound(self, j3_1_schema):
        """J3→M4 应为 outbound 方向（股份支付流向资本公积）。"""
        cross_refs = j3_1_schema.get("cross_refs", [])
        m4_refs = [r for r in cross_refs if r.get("target_wp") == "M4"]
        assert len(m4_refs) >= 1
        ref = m4_refs[0]
        assert ref.get("direction") == "outbound", (
            f"J3→M4 应为 outbound 方向，实际为 {ref.get('direction')}"
        )

    def test_j3_1_m4_ref_mentions_capital_reserve(self, j3_1_schema):
        """J3→M4 cross_ref 描述应提及资本公积。"""
        cross_refs = j3_1_schema.get("cross_refs", [])
        m4_refs = [r for r in cross_refs if r.get("target_wp") == "M4"]
        assert len(m4_refs) >= 1
        ref = m4_refs[0]
        desc = ref.get("description", "") + ref.get("target_field", "")
        assert "资本公积" in desc, (
            f"M4 cross_ref 应提及资本公积，实际: description={ref.get('description')}, "
            f"target_field={ref.get('target_field')}"
        )
