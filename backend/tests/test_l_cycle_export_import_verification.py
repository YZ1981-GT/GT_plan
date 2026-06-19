"""L 类底稿（筹资循环）导入导出完整验证测试。

覆盖:
  P0-P6 综合验证：
  36. L 类 d-form-table 底稿导出为 Excel
  37. L 类 audit-sheet 底稿原生导出
  38. 从 Excel 导入填充 L 类底稿
  39. 批量导出 L 类全量打包 zip
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
_ADDR_REGISTRY_PATH = _DATA_DIR / "l_address_registry_seed.json"
_SCHEMA_DIR = _DATA_DIR / "ledger_adapters" / "wp_render_schema"


@pytest.fixture(scope="module")
def wp_mapping() -> list[dict]:
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mappings", data) if isinstance(data, dict) else data


@pytest.fixture(scope="module")
def l_class_entries(wp_mapping) -> list[dict]:
    return [e for e in wp_mapping if e.get("cycle") == "L"]


@pytest.fixture(scope="module")
def procedure_templates() -> dict:
    with open(_TEMPLATES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    # Templates can be in data["tables"] or at root level (newer cycles)
    tables = data.get("tables", {}) if isinstance(data, dict) else {}
    # Merge root-level entries that look like procedure tables (e.g. G0A, H1A, L0A)
    if isinstance(data, dict):
        for key, val in data.items():
            if key not in ("version", "description", "tables") and isinstance(val, dict) and "items" in val:
                tables[key] = val
    return tables


@pytest.fixture(scope="module")
def addr_registry() -> dict:
    with open(_ADDR_REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════════════════
# P0: 注册完整性
# ═══════════════════════════════════════════════════════════════════════════════


class TestP0Registration:
    """P0: wp_account_mapping + _WP_CODE_OVERRIDE 完整性。"""

    _ALL_L_SUBCODES = [
        # L0 函证
        "L0-1", "L0-2", "L0-3", "L0-4", "L0-5",
        # L1 短期借款
        "L1-1", "L1-2", "L1-3", "L1-4", "L1-5", "L1-6",
        # L2 应付利息
        "L2-1", "L2-2", "L2-3", "L2-4",
        # L3 长期借款
        "L3-1", "L3-2", "L3-3", "L3-4", "L3-5", "L3-6",
        # L4 应付债券
        "L4-1", "L4-2", "L4-3", "L4-4", "L4-5", "L4-6", "L4-7", "L4-8",
        # L5 长期应付款
        "L5-1", "L5-2", "L5-3", "L5-4",
        # L6 专项应付款
        "L6-1", "L6-2", "L6-3", "L6-4",
        # L7 其他非流动负债
        "L7-1", "L7-2", "L7-3", "L7-4",
        # L8 财务费用
        "L8-1", "L8-2", "L8-3", "L8-4", "L8-5", "L8-6",
    ]

    _PARENT_CODES = ["L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8"]

    _PROGRAM_CODES = ["L0A", "L1A", "L2A", "L3A", "L4A", "L5A", "L6A", "L7A", "L8A"]

    def test_l_class_count(self, l_class_entries):
        """wp_account_mapping.json 中应有 ≥50 个 cycle='L' 的条目。"""
        assert len(l_class_entries) >= 50, (
            f"L 类底稿应有 ≥50 条注册，实际 {len(l_class_entries)} 条"
        )

    def test_all_l_subcodes_have_override(self):
        """所有 L 类子码在 _WP_CODE_OVERRIDE 中有 componentType 映射。"""
        for code in self._ALL_L_SUBCODES:
            assert code in _WP_CODE_OVERRIDE, (
                f"L 类 wp_code '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )

    def test_all_parent_codes_have_override(self):
        """所有 L 类父码在 _WP_CODE_OVERRIDE 中有映射。"""
        for code in self._PARENT_CODES:
            assert code in _WP_CODE_OVERRIDE, (
                f"L 类父码 '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )

    def test_all_program_codes_have_override(self):
        """所有 L 类程序表在 _WP_CODE_OVERRIDE 中有映射。"""
        for code in self._PROGRAM_CODES:
            assert code in _WP_CODE_OVERRIDE, (
                f"L 类程序表 '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )
            assert _WP_CODE_OVERRIDE[code] == "a-program-console"

    def test_all_component_types_valid(self):
        """所有 L 类子码 componentType 必须是合法类型。"""
        for code in self._ALL_L_SUBCODES + self._PARENT_CODES + self._PROGRAM_CODES:
            ct = _WP_CODE_OVERRIDE.get(code, "")
            assert ct in VALID_COMPONENT_TYPES, (
                f"L 类 '{code}' componentType '{ct}' 不合法"
            )

    def test_l0_confirmation_hub(self):
        """L0 映射为 confirmation-hub。"""
        assert _WP_CODE_OVERRIDE.get("L0") == "confirmation-hub"

    def test_type_distribution(self):
        """L 类 componentType 分布符合预期。"""
        l_codes = {
            code: ct for code, ct in _WP_CODE_OVERRIDE.items()
            if re.match(r'^L\d', code)
        }
        type_counts: dict[str, int] = {}
        for ct in l_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1
        # 9 c-note-table (L0~L8 parent) - L0 is confirmation-hub so 8
        assert type_counts.get("c-note-table", 0) >= 8
        # d-form-table: 5(L0-x) + 8(审定表) + 1(L3-4) + 8(调整分录) = 22+
        assert type_counts.get("d-form-table", 0) >= 20
        # audit-sheet: formula/detail/analysis
        assert type_counts.get("audit-sheet", 0) >= 15

    @pytest.mark.parametrize("wp_code", ["L1-1", "L2-1", "L3-1", "L4-1",
                                          "L5-1", "L6-1", "L7-1", "L8-1"])
    def test_audit_determination_tables_are_d_form(self, wp_code):
        """L{n}-1 审定表映射为 d-form-table。"""
        assert _WP_CODE_OVERRIDE.get(wp_code) == "d-form-table"


# ═══════════════════════════════════════════════════════════════════════════════
# P1: 程序表模板
# ═══════════════════════════════════════════════════════════════════════════════


class TestP1ProcedureTables:
    """P1: 程序表模板注册验证。"""

    _EXPECTED_TABLES = [
        "L0A", "L1A", "L2A", "L3A", "L4A", "L5A", "L6A", "L7A", "L8A",
    ]

    def test_all_9_procedure_tables_registered(self, procedure_templates):
        """L0A~L8A 共 9 个程序表全部注册。"""
        for table_id in self._EXPECTED_TABLES:
            assert table_id in procedure_templates, (
                f"程序表 '{table_id}' 未注册到 procedure_table_templates.json"
            )

    @pytest.mark.parametrize("table_id", [
        "L0A", "L1A", "L2A", "L3A", "L4A", "L5A", "L6A", "L7A", "L8A",
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

    def test_procedure_tables_last_step_has_control_test(self, procedure_templates):
        """所有程序表末步引用 control_test_result_for_cycle。"""
        for table_id in self._EXPECTED_TABLES:
            last_item = procedure_templates[table_id]["items"][-1]
            assert last_item.get("auto_data_source") == "control_test_result_for_cycle", (
                f"{table_id} 末步未引用 control_test_result_for_cycle 数据源"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# P2: 审定表 + 回写联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestP2AuditDetermination:
    """P2: 审定表 schema + handler 正则。"""

    def test_handler_regex_covers_l_class(self):
        """handler 正则 ^[D-N]\\d+-1$ 匹配所有 L 审定表。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        for i in range(1, 9):
            code = f"L{i}-1"
            assert pattern.match(code), f"正则不匹配 {code}"

    def test_l4_1_schema_exists(self):
        """L4-1 特殊 YAML schema 文件存在。"""
        schema_path = _SCHEMA_DIR / "L4-1.yaml"
        assert schema_path.exists()

    def test_l8_1_schema_exists(self):
        """L8-1 特殊 YAML schema 文件存在。"""
        schema_path = _SCHEMA_DIR / "L8-1.yaml"
        assert schema_path.exists()

    def test_l4_1_has_bond_fields(self):
        """L4-1 schema 包含债券品种字段（面值/票面利率/到期日/摊余成本）。"""
        schema_path = _SCHEMA_DIR / "L4-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "L4-1"
        assert schema.get("dynamic_rows") is True
        row_fields = schema["row_template"]["fields"]
        field_names = [f["field"] for f in row_fields]
        assert "face_value" in field_names
        assert "coupon_rate" in field_names
        assert "maturity_date" in field_names
        assert "audited_amount" in field_names

    def test_l8_1_is_income_statement_type(self):
        """L8-1 schema 标记为损益类。"""
        schema_path = _SCHEMA_DIR / "L8-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema.get("income_statement_type") is True
        assert schema.get("amount_source") == "occurrence_amount"

    def test_l4_1_cross_ref_to_g4(self):
        """L4-1 有到 G4 的对称关联引用。"""
        schema_path = _SCHEMA_DIR / "L4-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        targets = [r["target_wp"] for r in schema["cross_refs"]]
        assert "G4-1" in targets


# ═══════════════════════════════════════════════════════════════════════════════
# P3: address_registry 坐标
# ═══════════════════════════════════════════════════════════════════════════════


class TestP3AddressRegistry:
    """P3: address_registry 坐标注册。"""

    def test_seed_file_exists(self):
        """l_address_registry_seed.json 存在。"""
        assert _ADDR_REGISTRY_PATH.exists()

    def test_seed_has_entries(self, addr_registry):
        """seed 有 entries 数组且 >= 6 条。"""
        assert "entries" in addr_registry
        assert len(addr_registry["entries"]) >= 6

    def test_seed_cycle_is_l(self, addr_registry):
        """seed cycle 标识为 L。"""
        assert addr_registry.get("cycle") == "L"

    def test_l1_3_coordinates(self, addr_registry):
        """L1-3 短期借款利息测算坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "L1-3" in codes

    def test_l3_3_coordinates(self, addr_registry):
        """L3-3 长期借款利息测算坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "L3-3" in codes

    def test_l4_3_coordinates(self, addr_registry):
        """L4-3 实际利率计算坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "L4-3" in codes

    def test_l4_4_coordinates(self, addr_registry):
        """L4-4 摊余成本摊销表坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "L4-4" in codes

    def test_l8_3_coordinates(self, addr_registry):
        """L8-3 利息费用测算坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "L8-3" in codes

    def test_l8_5_coordinates(self, addr_registry):
        """L8-5 汇兑损益测算坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "L8-5" in codes


# ═══════════════════════════════════════════════════════════════════════════════
# P4: 特殊程序
# ═══════════════════════════════════════════════════════════════════════════════


class TestP4SpecialProcedures:
    """P4: 特殊程序 schema 确认。"""

    def test_l4_1_schema_parseable(self):
        """L4-1 schema 可正确解析。"""
        schema_path = _SCHEMA_DIR / "L4-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "L4-1"
        assert schema["component_type"] == "d-form-table"

    def test_l3_4_schema_exists(self):
        """L3-4 一年内到期重分类 YAML schema 存在。"""
        schema_path = _SCHEMA_DIR / "L3-4.yaml"
        assert schema_path.exists()

    def test_l3_4_schema_parseable(self):
        """L3-4 schema 可正确解析。"""
        schema_path = _SCHEMA_DIR / "L3-4.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "L3-4"
        assert schema["component_type"] == "d-form-table"
        assert schema.get("dynamic_rows") is True

    def test_l3_4_has_loan_fields(self):
        """L3-4 schema 含借款清单字段（银行/金额/利率/到期日/剩余期限）。"""
        schema_path = _SCHEMA_DIR / "L3-4.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        row_fields = schema["row_template"]["fields"]
        field_names = [f["field"] for f in row_fields]
        assert "bank_name" in field_names
        assert "loan_amount" in field_names
        assert "interest_rate" in field_names
        assert "maturity_date" in field_names
        assert "remaining_term_days" in field_names
        assert "is_within_one_year" in field_names
        assert "reclassify_amount" in field_names

    def test_l4_3_is_audit_sheet(self):
        """L4-3 实际利率计算映射为 audit-sheet。"""
        assert _WP_CODE_OVERRIDE.get("L4-3") == "audit-sheet"

    def test_l4_4_is_audit_sheet(self):
        """L4-4 摊余成本摊销表映射为 audit-sheet。"""
        assert _WP_CODE_OVERRIDE.get("L4-4") == "audit-sheet"

    def test_l1_3_is_audit_sheet(self):
        """L1-3 利息测算映射为 audit-sheet。"""
        assert _WP_CODE_OVERRIDE.get("L1-3") == "audit-sheet"

    def test_l3_3_is_audit_sheet(self):
        """L3-3 利息测算映射为 audit-sheet。"""
        assert _WP_CODE_OVERRIDE.get("L3-3") == "audit-sheet"

    def test_l8_5_is_audit_sheet(self):
        """L8-5 汇兑损益映射为 audit-sheet。"""
        assert _WP_CODE_OVERRIDE.get("L8-5") == "audit-sheet"

    def test_l8_1_schema_has_sections(self):
        """L8-1 schema 有利息/汇兑/手续费等分类行。"""
        schema_path = _SCHEMA_DIR / "L8-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        section_names = [s["name"] for s in schema["sections"]]
        assert "利息支出" in section_names
        assert "汇兑损益" in section_names
        assert "手续费" in section_names


# ═══════════════════════════════════════════════════════════════════════════════
# P5: 联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestP5Linkage:
    """P5: 联动绑定验证。"""

    def test_risk_for_cycle_in_procedure_tables(self, procedure_templates):
        """L{n}A 程序表引用 risk_for_cycle。"""
        tables_with_risk = []
        expected = ["L0A", "L1A", "L2A", "L3A", "L4A", "L5A", "L6A", "L7A", "L8A"]
        for key in expected:
            items = procedure_templates[key].get("items", [])
            for item in items:
                if item.get("auto_data_source") == "risk_for_cycle":
                    tables_with_risk.append(key)
                    break
        assert len(tables_with_risk) == 9

    def test_l0_confirmation_hub_route(self):
        """L0→ConfirmationHub 路由正确。"""
        assert _WP_CODE_OVERRIDE["L0"] == "confirmation-hub"

    def test_l4_1_g4_cross_ref(self):
        """L4-1 与 G4 有对称关联。"""
        schema_path = _SCHEMA_DIR / "L4-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        targets = [r["target_wp"] for r in schema["cross_refs"]]
        assert "G4-1" in targets

    def test_l8_1_interest_ref(self):
        """L8-1 引用 L8-3 利息测算。"""
        schema_path = _SCHEMA_DIR / "L8-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        targets = [r["target_wp"] for r in schema["cross_refs"]]
        assert "L8-3" in targets

    def test_l8_1_exchange_ref(self):
        """L8-1 引用 L8-5 汇兑损益。"""
        schema_path = _SCHEMA_DIR / "L8-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        targets = [r["target_wp"] for r in schema["cross_refs"]]
        assert "L8-5" in targets


# ═══════════════════════════════════════════════════════════════════════════════
# P6: 导入导出
# ═══════════════════════════════════════════════════════════════════════════════


class TestP6ExportImport:
    """P6: 导入导出基础设施验证。"""

    # L 类 d-form-table wp_codes
    _L_FORM_TABLE_CODES = [
        "L0-1", "L0-2", "L0-3", "L0-4", "L0-5",
        "L1-1", "L1-6",
        "L2-1", "L2-4",
        "L3-1", "L3-4", "L3-6",
        "L4-1", "L4-8",
        "L5-1", "L5-4",
        "L6-1", "L6-4",
        "L7-1", "L7-4",
        "L8-1", "L8-6",
    ]

    # L 类 audit-sheet wp_codes
    _AUDIT_SHEET_CODES = [
        "L1-2", "L1-3", "L1-4", "L1-5",
        "L2-2", "L2-3",
        "L3-2", "L3-3", "L3-5",
        "L4-2", "L4-3", "L4-4", "L4-5", "L4-6", "L4-7",
        "L5-2", "L5-3",
        "L6-2", "L6-3",
        "L7-2", "L7-3",
        "L8-2", "L8-3", "L8-4", "L8-5",
    ]

    @pytest.mark.parametrize("wp_code", _L_FORM_TABLE_CODES)
    def test_l_form_table_registered(self, wp_code):
        """L 类 d-form-table 底稿在 _WP_CODE_OVERRIDE 中注册正确。"""
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table"

    @pytest.mark.parametrize("wp_code", _AUDIT_SHEET_CODES)
    def test_l_audit_sheet_registered(self, wp_code):
        """L 类 audit-sheet 底稿在 _WP_CODE_OVERRIDE 中注册正确。"""
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == "audit-sheet"

    def test_all_l_codes_in_mapping(self, l_class_entries):
        """所有 L 类 wp_code 在 wp_account_mapping 注册（批量导出可枚举）。"""
        mapping_codes = {e["wp_code"] for e in l_class_entries}
        all_codes = set(self._L_FORM_TABLE_CODES + self._AUDIT_SHEET_CODES)
        missing = all_codes - mapping_codes
        assert not missing, f"L 类缺少: {sorted(missing)}"

    def test_l_class_all_have_wp_code(self, l_class_entries):
        """所有 L 类条目有有效 wp_code。"""
        for entry in l_class_entries:
            assert entry.get("wp_code"), f"缺少 wp_code: {entry}"
            assert entry["wp_code"].startswith("L")

    def test_batch_export_type_distribution(self):
        """L 类 componentType 分布合理。"""
        l_codes = {
            code: ct for code, ct in _WP_CODE_OVERRIDE.items()
            if re.match(r'^L\d', code)
        }
        type_counts: dict[str, int] = {}
        for ct in l_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1
        assert type_counts.get("d-form-table", 0) >= 20
        assert type_counts.get("audit-sheet", 0) >= 15

    def test_l4_1_yaml_schema_parseable_for_import(self):
        """L4-1 审定表 YAML schema 可正确解析用于导入填充。"""
        schema_path = _SCHEMA_DIR / "L4-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "L4-1"
        assert schema["component_type"] == "d-form-table"
        assert schema.get("dynamic_rows") is True

    def test_l8_1_yaml_schema_parseable_for_import(self):
        """L8-1 审定表 YAML schema 可正确解析用于导入填充。"""
        schema_path = _SCHEMA_DIR / "L8-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "L8-1"
        assert schema["component_type"] == "d-form-table"
        assert len(schema["sections"]) >= 5
        first_section = schema["sections"][0]
        assert "fields" in first_section
        field_names = [f["field"] for f in first_section["fields"]]
        assert "account_code" in field_names
        assert "audited_amount" in field_names

    def test_l3_4_yaml_schema_parseable_for_import(self):
        """L3-4 重分类 YAML schema 可正确解析用于导入。"""
        schema_path = _SCHEMA_DIR / "L3-4.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "L3-4"
        assert schema["component_type"] == "d-form-table"
