"""K 类底稿（管理循环）联动完善验证测试。

Phase 5 覆盖:
  Task 38: K{n}A 程序表 risk_for_cycle + control_test_result_for_cycle 绑定
  Task 39: K0→ConfirmationHub 路由确认
  Task 40: K5→A5-3 ref_index 跳转（K5-3 YAML cross_refs）
  Task 41: K7↔K10 cross_refs 联动
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from app.services.wp_classification_service import _WP_CODE_OVERRIDE

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
    return data.get("tables", data.get("templates", data)) if isinstance(data, dict) else data


# ═══════════════════════════════════════════════════════════════════════════════
# Task 38: K{n}A 程序表 risk_for_cycle + control_test_result_for_cycle 绑定
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask38ProcedureTableBindings:
    """Task 38: K{n}A 程序表引用 risk_for_cycle + control_test_result_for_cycle。"""

    _K_PROGRAM_TABLES = [
        "K0A", "K1A", "K2A", "K3A", "K4A", "K5A", "K6A",
        "K7A", "K8A", "K9A", "K10A", "K11A", "K12A", "K13A",
    ]

    def test_all_k_program_tables_registered(self, procedure_templates):
        """K0A~K13A 共 14 个程序表全部注册。"""
        for table_id in self._K_PROGRAM_TABLES:
            assert table_id in procedure_templates, (
                f"程序表 '{table_id}' 未注册"
            )

    def test_risk_for_cycle_in_k_procedure_tables(self, procedure_templates):
        """所有 K 程序表引用 risk_for_cycle。"""
        tables_with_risk = []
        for key in self._K_PROGRAM_TABLES:
            if key in procedure_templates:
                items = procedure_templates[key].get("items", [])
                for item in items:
                    if item.get("auto_data_source") == "risk_for_cycle":
                        tables_with_risk.append(key)
                        break
        assert len(tables_with_risk) == 14, (
            f"应有 14 个程序表引用 risk_for_cycle，实际 {len(tables_with_risk)}: "
            f"缺少 {set(self._K_PROGRAM_TABLES) - set(tables_with_risk)}"
        )

    def test_control_test_in_k_procedure_tables(self, procedure_templates):
        """至少部分 K 程序表引用 control_test_result_for_cycle。"""
        tables_with_control = []
        for key in self._K_PROGRAM_TABLES:
            if key in procedure_templates:
                items = procedure_templates[key].get("items", [])
                for item in items:
                    if item.get("auto_data_source") == "control_test_result_for_cycle":
                        tables_with_control.append(key)
                        break
        assert len(tables_with_control) >= 10, (
            f"应有 ≥10 个程序表引用 control_test，实际 {len(tables_with_control)}"
        )

    def test_k_procedure_tables_have_items(self, procedure_templates):
        """每个 K 程序表有 items 且步骤数 >= 5。"""
        for table_id in self._K_PROGRAM_TABLES:
            table = procedure_templates[table_id]
            assert "items" in table, f"{table_id} 缺少 items"
            assert len(table["items"]) >= 5, (
                f"{table_id} 步骤数 {len(table['items'])} < 5"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 39: K0→ConfirmationHub 路由确认
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask39ConfirmationHub:
    """Task 39: K0→ConfirmationHub 路由确认。"""

    def test_k0_is_confirmation_hub(self):
        """K0 在 _WP_CODE_OVERRIDE 中映射为 confirmation-hub。"""
        assert _WP_CODE_OVERRIDE.get("K0") == "confirmation-hub"

    def test_k0_in_confirmation_hub_whitelist(self):
        """K0 在 confirmation-hub 白名单中。"""
        from app.services.wp_classification_service import _WP_CODE_OVERRIDE
        # K0 映射为 confirmation-hub 即表示在白名单中
        assert _WP_CODE_OVERRIDE["K0"] == "confirmation-hub"

    def test_k0_sub_codes_are_d_form_table(self):
        """K0-1~K0-5 函证辅助表映射为 d-form-table。"""
        for i in range(1, 6):
            code = f"K0-{i}"
            assert _WP_CODE_OVERRIDE[code] == "d-form-table", (
                f"{code} 应为 d-form-table，实际为 '{_WP_CODE_OVERRIDE[code]}'"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 40: K5→A5-3 ref_index 跳转
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask40K5ToA5CrossRef:
    """Task 40: K5-3 YAML 中 cross_refs 包含 A5-3 跨循环引用。"""

    def test_k5_3_schema_has_a5_3_ref(self):
        """K5-3 YAML cross_refs 中有到 A5-3 的引用。"""
        schema_path = _SCHEMA_DIR / "K5-3.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert "cross_refs" in schema
        targets = [ref["target_wp"] for ref in schema["cross_refs"]]
        assert "A5-3" in targets, "K5-3 缺少到 A5-3 的跨循环引用"

    def test_k5_3_a5_3_ref_direction(self):
        """K5-3→A5-3 引用方向为 outbound。"""
        schema_path = _SCHEMA_DIR / "K5-3.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        a5_ref = next(
            (r for r in schema["cross_refs"] if r["target_wp"] == "A5-3"), None
        )
        assert a5_ref is not None
        assert a5_ref["direction"] == "outbound"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 41: K7↔K10 cross_refs 联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask41K7K10CrossRef:
    """Task 41: K7-1 和 K10-1 YAML cross_refs 双向联动。"""

    def test_k7_1_has_k10_1_ref(self):
        """K7-1 YAML cross_refs 中有到 K10-1 的引用。"""
        schema_path = _SCHEMA_DIR / "K7-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert "cross_refs" in schema
        targets = [ref["target_wp"] for ref in schema["cross_refs"]]
        assert "K10-1" in targets, "K7-1 缺少到 K10-1 的联动引用"

    def test_k10_1_has_k7_1_ref(self):
        """K10-1 YAML cross_refs 中有到 K7-1 的引用。"""
        schema_path = _SCHEMA_DIR / "K10-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert "cross_refs" in schema
        targets = [ref["target_wp"] for ref in schema["cross_refs"]]
        assert "K7-1" in targets, "K10-1 缺少到 K7-1 的联动引用"

    def test_k7_k10_ref_is_bidirectional(self):
        """K7-1↔K10-1 引用标记为 bidirectional。"""
        schema_path = _SCHEMA_DIR / "K7-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        k10_ref = next(
            (r for r in schema["cross_refs"] if r["target_wp"] == "K10-1"), None
        )
        assert k10_ref is not None
        assert k10_ref["direction"] == "bidirectional"
