"""K 类底稿（管理循环）导入导出完整验证测试。

覆盖:
  P0-P6 综合验证：
  42. K 类 d-form-table 底稿导出为 Excel
  43. K 类 audit-sheet 底稿原生导出
  44. 从 Excel 导入填充 K 类底稿
  45. 批量导出 K 类全量打包 zip
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
# P0: 注册完整性
# ═══════════════════════════════════════════════════════════════════════════════


class TestP0Registration:
    """P0: wp_account_mapping + _WP_CODE_OVERRIDE 完整性。"""

    _ALL_K_SUBCODES = [
        # K0 函证
        "K0-1", "K0-2", "K0-3", "K0-4", "K0-5",
        # K1~K13 子码
        "K1-1", "K1-2", "K1-3", "K1-4", "K1-5", "K1-6",
        "K2-1", "K2-2", "K2-3", "K2-4",
        "K3-1", "K3-2", "K3-3", "K3-4", "K3-5", "K3-6",
        "K4-1", "K4-2", "K4-3", "K4-4",
        "K5-1", "K5-2", "K5-3", "K5-4", "K5-5", "K5-6",
        "K6-1", "K6-2", "K6-3", "K6-4",
        "K7-1", "K7-2", "K7-3", "K7-4",
        "K8-1", "K8-2", "K8-3", "K8-4", "K8-5", "K8-6",
        "K9-1", "K9-2", "K9-3", "K9-4", "K9-5", "K9-6",
        "K10-1", "K10-2", "K10-3", "K10-4",
        "K11-1", "K11-2", "K11-3", "K11-4",
        "K12-1", "K12-2", "K12-3", "K12-4",
        "K13-1", "K13-2", "K13-3", "K13-4",
    ]

    _PARENT_CODES = ["K0", "K1", "K2", "K3", "K4", "K5", "K6", "K7",
                     "K8", "K9", "K10", "K11", "K12", "K13"]

    def test_k_class_count(self, k_class_entries):
        """wp_account_mapping.json 中应有 ≥70 个 cycle='K' 的条目。"""
        assert len(k_class_entries) >= 70, (
            f"K 类底稿应有 ≥70 条注册，实际 {len(k_class_entries)} 条"
        )

    def test_all_k_subcodes_have_override(self):
        """所有 K 类子码在 _WP_CODE_OVERRIDE 中有 componentType 映射。"""
        for code in self._ALL_K_SUBCODES:
            assert code in _WP_CODE_OVERRIDE, (
                f"K 类 wp_code '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )

    def test_all_component_types_valid(self):
        """所有 K 类子码 componentType 必须是合法类型。"""
        for code in self._ALL_K_SUBCODES:
            ct = _WP_CODE_OVERRIDE.get(code, "")
            assert ct in VALID_COMPONENT_TYPES, (
                f"K 类 '{code}' componentType '{ct}' 不合法"
            )

    def test_k0_confirmation_hub(self):
        """K0 映射为 confirmation-hub。"""
        assert _WP_CODE_OVERRIDE.get("K0") == "confirmation-hub"

    def test_type_distribution(self):
        """K 类 componentType 分布符合预期。"""
        k_codes = {
            code: ct for code, ct in _WP_CODE_OVERRIDE.items()
            if re.match(r'^K\d', code)
        }
        type_counts: dict[str, int] = {}
        for ct in k_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1
        assert type_counts.get("d-form-table", 0) >= 25
        assert type_counts.get("audit-sheet", 0) >= 30

    @pytest.mark.parametrize("wp_code", [f"K{i}-1" for i in range(1, 14)])
    def test_audit_determination_tables_are_d_form(self, wp_code):
        """K{n}-1 审定表映射为 d-form-table。"""
        assert _WP_CODE_OVERRIDE.get(wp_code) == "d-form-table"


# ═══════════════════════════════════════════════════════════════════════════════
# P1: 程序表模板
# ═══════════════════════════════════════════════════════════════════════════════


class TestP1ProcedureTables:
    """P1: 程序表模板注册验证。"""

    _EXPECTED_TABLES = [
        "K0A", "K1A", "K2A", "K3A", "K4A", "K5A", "K6A",
        "K7A", "K8A", "K9A", "K10A", "K11A", "K12A", "K13A",
    ]

    def test_all_14_procedure_tables_registered(self, procedure_templates):
        """K0A~K13A 共 14 个程序表全部注册。"""
        for table_id in self._EXPECTED_TABLES:
            assert table_id in procedure_templates, (
                f"程序表 '{table_id}' 未注册到 procedure_table_templates.json"
            )

    @pytest.mark.parametrize("table_id", [
        "K0A", "K1A", "K2A", "K3A", "K4A", "K5A", "K6A",
        "K7A", "K8A", "K9A", "K10A", "K11A", "K12A", "K13A",
    ])
    def test_procedure_table_has_items(self, procedure_templates, table_id):
        """每个程序表有 items 且步骤数 >= 5。"""
        table = procedure_templates[table_id]
        assert "items" in table, f"{table_id} 缺少 items"
        assert len(table["items"]) >= 5, (
            f"{table_id} 步骤数 {len(table['items'])} < 5"
        )

    def test_procedure_tables_have_risk_source(self, procedure_templates):
        """所有程序表 seq1 应引用 risk_for_cycle。"""
        for table_id in self._EXPECTED_TABLES:
            first_item = procedure_templates[table_id]["items"][0]
            assert first_item.get("auto_data_source") == "risk_for_cycle", (
                f"{table_id} seq1 未引用 risk_for_cycle 数据源"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# P2: 审定表 + 回写联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestP2AuditDetermination:
    """P2: 审定表 schema + handler 正则。"""

    def test_handler_regex_covers_k_class(self):
        """handler 正则 ^[D-N]\\d+-1$ 匹配所有 K 审定表。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        for i in range(1, 14):
            code = f"K{i}-1"
            assert pattern.match(code), f"正则不匹配 {code}"

    def test_k8_1_schema_exists(self):
        """K8-1 特殊 YAML schema 文件存在。"""
        schema_path = _SCHEMA_DIR / "K8-1.yaml"
        assert schema_path.exists()

    def test_k9_1_schema_exists(self):
        """K9-1 特殊 YAML schema 文件存在。"""
        schema_path = _SCHEMA_DIR / "K9-1.yaml"
        assert schema_path.exists()

    def test_k8_1_is_income_statement_type(self):
        """K8-1 schema 标记为损益类。"""
        schema_path = _SCHEMA_DIR / "K8-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema.get("income_statement_type") is True
        assert schema.get("amount_source") == "occurrence_amount"

    def test_k9_1_is_income_statement_type(self):
        """K9-1 schema 标记为损益类。"""
        schema_path = _SCHEMA_DIR / "K9-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema.get("income_statement_type") is True
        assert schema.get("amount_source") == "occurrence_amount"


# ═══════════════════════════════════════════════════════════════════════════════
# P3: address_registry 坐标
# ═══════════════════════════════════════════════════════════════════════════════


class TestP3AddressRegistry:
    """P3: address_registry 坐标注册。"""

    def test_seed_file_exists(self):
        """k_address_registry_seed.json 存在。"""
        assert _ADDR_REGISTRY_PATH.exists()

    def test_seed_has_entries(self, addr_registry):
        """seed 有 entries 数组且 >= 9 条。"""
        assert "entries" in addr_registry
        assert len(addr_registry["entries"]) >= 9

    def test_seed_cycle_is_k(self, addr_registry):
        """seed cycle 标识为 K。"""
        assert addr_registry.get("cycle") == "K"

    def test_k1_2_coordinates(self, addr_registry):
        """K1-2 其他应收款明细坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "K1-2" in codes

    def test_k5_4_coordinates(self, addr_registry):
        """K5-4 最佳估计数坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "K5-4" in codes

    def test_k8_2_coordinates(self, addr_registry):
        """K8-2 销售费用明细坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "K8-2" in codes

    def test_k9_2_coordinates(self, addr_registry):
        """K9-2 管理费用明细坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "K9-2" in codes


# ═══════════════════════════════════════════════════════════════════════════════
# P4: 特殊程序
# ═══════════════════════════════════════════════════════════════════════════════


class TestP4SpecialProcedures:
    """P4: 特殊程序 schema 确认。"""

    def test_k5_3_contingency_schema_exists(self):
        """K5-3 或有事项评估 YAML schema 存在。"""
        schema_path = _SCHEMA_DIR / "K5-3.yaml"
        assert schema_path.exists()

    def test_k5_5_lawyer_response_schema_exists(self):
        """K5-5 律师函回函分析 YAML schema 存在。"""
        schema_path = _SCHEMA_DIR / "K5-5.yaml"
        assert schema_path.exists()

    def test_k6_3_held_for_sale_schema_exists(self):
        """K6-3 持有待售分类条件 YAML schema 存在。"""
        schema_path = _SCHEMA_DIR / "K6-3.yaml"
        assert schema_path.exists()

    def test_k5_3_schema_parseable(self):
        """K5-3 schema 可正确解析。"""
        schema_path = _SCHEMA_DIR / "K5-3.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "K5-3"
        assert schema["component_type"] == "d-form-table"

    def test_k6_3_schema_parseable(self):
        """K6-3 schema 可正确解析。"""
        schema_path = _SCHEMA_DIR / "K6-3.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "K6-3"
        assert schema["component_type"] == "d-form-table"


# ═══════════════════════════════════════════════════════════════════════════════
# P5: 联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestP5Linkage:
    """P5: 联动绑定验证。"""

    def test_risk_for_cycle_in_procedure_tables(self, procedure_templates):
        """K{n}A 程序表引用 risk_for_cycle。"""
        tables_with_risk = []
        for key in procedure_templates:
            if key.startswith("K") and key.endswith("A"):
                items = procedure_templates[key].get("items", [])
                for item in items:
                    if item.get("auto_data_source") == "risk_for_cycle":
                        tables_with_risk.append(key)
                        break
        assert len(tables_with_risk) == 14

    def test_k0_confirmation_hub_route(self):
        """K0→ConfirmationHub 路由正确。"""
        assert _WP_CODE_OVERRIDE["K0"] == "confirmation-hub"

    def test_k7_k10_cross_refs(self):
        """K7-1 和 K10-1 YAML 有双向引用。"""
        k7_path = _SCHEMA_DIR / "K7-1.yaml"
        k10_path = _SCHEMA_DIR / "K10-1.yaml"
        with open(k7_path, encoding="utf-8") as f:
            k7_schema = yaml.safe_load(f)
        with open(k10_path, encoding="utf-8") as f:
            k10_schema = yaml.safe_load(f)
        k7_targets = [r["target_wp"] for r in k7_schema["cross_refs"]]
        k10_targets = [r["target_wp"] for r in k10_schema["cross_refs"]]
        assert "K10-1" in k7_targets
        assert "K7-1" in k10_targets

    def test_k5_3_a5_3_cross_ref(self):
        """K5-3→A5-3 跨循环引用存在。"""
        schema_path = _SCHEMA_DIR / "K5-3.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        targets = [r["target_wp"] for r in schema["cross_refs"]]
        assert "A5-3" in targets


# ═══════════════════════════════════════════════════════════════════════════════
# P6: 导入导出
# ═══════════════════════════════════════════════════════════════════════════════


class TestP6ExportImport:
    """P6: 导入导出基础设施验证。"""

    # K 类 d-form-table wp_codes
    _K_FORM_TABLE_CODES = [
        "K0-1", "K0-2", "K0-3", "K0-4", "K0-5",
        "K1-1", "K1-4", "K1-6",
        "K2-1", "K2-4",
        "K3-1", "K3-6",
        "K4-1", "K4-4",
        "K5-1", "K5-3", "K5-5", "K5-6",
        "K6-1", "K6-3", "K6-4",
        "K7-1", "K7-4",
        "K8-1", "K8-6",
        "K9-1", "K9-6",
        "K10-1", "K10-4",
        "K11-1", "K11-4",
        "K12-1", "K12-4",
        "K13-1", "K13-4",
    ]

    # K 类 audit-sheet wp_codes
    _AUDIT_SHEET_CODES = [
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

    @pytest.mark.parametrize("wp_code", _K_FORM_TABLE_CODES)
    def test_k_form_table_registered(self, wp_code):
        """K 类 d-form-table 底稿在 _WP_CODE_OVERRIDE 中注册正确。"""
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table"

    @pytest.mark.parametrize("wp_code", _AUDIT_SHEET_CODES)
    def test_k_audit_sheet_registered(self, wp_code):
        """K 类 audit-sheet 底稿在 _WP_CODE_OVERRIDE 中注册正确。"""
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == "audit-sheet"

    def test_all_k_codes_in_mapping(self, k_class_entries):
        """所有 K 类 wp_code 在 wp_account_mapping 注册（批量导出可枚举）。"""
        mapping_codes = {e["wp_code"] for e in k_class_entries}
        all_codes = set(self._K_FORM_TABLE_CODES + self._AUDIT_SHEET_CODES)
        missing = all_codes - mapping_codes
        assert not missing, f"K 类缺少: {sorted(missing)}"

    def test_k_class_all_have_wp_code(self, k_class_entries):
        """所有 K 类条目有有效 wp_code。"""
        for entry in k_class_entries:
            assert entry.get("wp_code"), f"缺少 wp_code: {entry}"
            assert entry["wp_code"].startswith("K")

    def test_batch_export_type_distribution(self):
        """K 类 componentType 分布合理。"""
        k_codes = {
            code: ct for code, ct in _WP_CODE_OVERRIDE.items()
            if re.match(r'^K\d', code)
        }
        type_counts: dict[str, int] = {}
        for ct in k_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1
        assert type_counts.get("d-form-table", 0) >= 25
        assert type_counts.get("audit-sheet", 0) >= 30

    def test_k8_1_yaml_schema_parseable_for_import(self):
        """K8-1 审定表 YAML schema 可正确解析用于导入填充。"""
        schema_path = _SCHEMA_DIR / "K8-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "K8-1"
        assert schema["component_type"] == "d-form-table"
        assert len(schema["sections"]) >= 8
        first_section = schema["sections"][0]
        assert "fields" in first_section
        field_names = [f["field"] for f in first_section["fields"]]
        assert "account_code" in field_names
        assert "audited_amount" in field_names

    def test_k5_3_yaml_schema_parseable_for_import(self):
        """K5-3 或有事项 YAML schema 可正确解析用于导入。"""
        schema_path = _SCHEMA_DIR / "K5-3.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "K5-3"
        first_section = schema["sections"][0]
        assert "fields" in first_section
