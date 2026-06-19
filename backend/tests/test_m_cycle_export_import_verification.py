"""M 类底稿（股东权益循环）完整验证测试。

覆盖 P0-P6 综合验证：
  1. wp_account_mapping 注册完整性
  2. _WP_CODE_OVERRIDE componentType 映射
  3. 程序表模板注册
  4. 审定表 schema + handler 正则
  5. address_registry 坐标注册
  6. 特殊程序（M6-2勾稽/income_statement_total/M9-3 OCI分类/M10-3永续债）
  7. 联动绑定
  8. 导入导出基础设施
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
_ADDR_REGISTRY_PATH = _DATA_DIR / "m_address_registry_seed.json"
_SCHEMA_DIR = _DATA_DIR / "ledger_adapters" / "wp_render_schema"


@pytest.fixture(scope="module")
def wp_mapping() -> list[dict]:
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mappings", data) if isinstance(data, dict) else data


@pytest.fixture(scope="module")
def m_class_entries(wp_mapping) -> list[dict]:
    return [e for e in wp_mapping if e.get("cycle") == "M"]


@pytest.fixture(scope="module")
def procedure_templates() -> dict:
    with open(_TEMPLATES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    tables = data.get("tables", {}) if isinstance(data, dict) else {}
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

    _ALL_M_SUBCODES = [
        # M1 应付股利
        "M1-1", "M1-2", "M1-3", "M1-4",
        # M2 实收资本
        "M2-1", "M2-2", "M2-3", "M2-4", "M2-5", "M2-6",
        # M3 库存股
        "M3-1", "M3-2", "M3-3", "M3-4",
        # M4 资本公积
        "M4-1", "M4-2", "M4-3", "M4-4", "M4-5", "M4-6",
        # M5 盈余公积
        "M5-1", "M5-2", "M5-3", "M5-4",
        # M6 未分配利润
        "M6-1", "M6-2", "M6-3", "M6-4", "M6-5", "M6-6",
        # M7 专项储备
        "M7-1", "M7-2", "M7-3", "M7-4",
        # M8 一般风险准备
        "M8-1", "M8-2", "M8-3", "M8-4",
        # M9 其他综合收益
        "M9-1", "M9-2", "M9-3", "M9-4", "M9-5", "M9-6",
        # M10 其他权益工具
        "M10-1", "M10-2", "M10-3", "M10-4",
    ]

    _PARENT_CODES = ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9", "M10"]

    _PROGRAM_CODES = ["M1A", "M2A", "M3A", "M4A", "M5A", "M6A", "M7A", "M8A", "M9A", "M10A"]

    def test_m_class_count(self, m_class_entries):
        """wp_account_mapping.json 中应有 ≥55 个 cycle='M' 的条目。"""
        assert len(m_class_entries) >= 55, (
            f"M 类底稿应有 ≥55 条注册，实际 {len(m_class_entries)} 条"
        )

    def test_all_m_subcodes_have_override(self):
        """所有 M 类子码在 _WP_CODE_OVERRIDE 中有 componentType 映射。"""
        for code in self._ALL_M_SUBCODES:
            assert code in _WP_CODE_OVERRIDE, (
                f"M 类 wp_code '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )

    def test_all_parent_codes_have_override(self):
        """所有 M 类父码在 _WP_CODE_OVERRIDE 中有映射。"""
        for code in self._PARENT_CODES:
            assert code in _WP_CODE_OVERRIDE, (
                f"M 类父码 '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )

    def test_all_program_codes_have_override(self):
        """所有 M 类程序表在 _WP_CODE_OVERRIDE 中有映射。"""
        for code in self._PROGRAM_CODES:
            assert code in _WP_CODE_OVERRIDE, (
                f"M 类程序表 '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )
            assert _WP_CODE_OVERRIDE[code] == "a-program-console"

    def test_all_component_types_valid(self):
        """所有 M 类子码 componentType 必须是合法类型。"""
        for code in self._ALL_M_SUBCODES + self._PARENT_CODES + self._PROGRAM_CODES:
            ct = _WP_CODE_OVERRIDE.get(code, "")
            assert ct in VALID_COMPONENT_TYPES, (
                f"M 类 '{code}' componentType '{ct}' 不合法"
            )

    def test_no_confirmation_hub(self):
        """M 类无函证（无 M0），不应有 confirmation-hub 映射。"""
        m_codes = {code: ct for code, ct in _WP_CODE_OVERRIDE.items() if re.match(r'^M\d', code)}
        for code, ct in m_codes.items():
            assert ct != "confirmation-hub", f"M 类 '{code}' 不应映射 confirmation-hub"

    def test_type_distribution(self):
        """M 类 componentType 分布符合预期。"""
        m_codes = {code: ct for code, ct in _WP_CODE_OVERRIDE.items() if re.match(r'^M\d', code)}
        type_counts: dict[str, int] = {}
        for ct in m_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1
        # 10 c-note-table (M1~M10 parent)
        assert type_counts.get("c-note-table", 0) == 10
        # 10 a-program-console (M1A~M10A)
        assert type_counts.get("a-program-console", 0) == 10
        # d-form-table: 审定表 + 调整分录 + 结构化检查
        assert type_counts.get("d-form-table", 0) >= 25
        # audit-sheet: 明细/变动/勾稽/损益联动
        assert type_counts.get("audit-sheet", 0) >= 14

    @pytest.mark.parametrize("wp_code", ["M1-1", "M2-1", "M3-1", "M4-1", "M5-1",
                                          "M6-1", "M7-1", "M8-1", "M9-1", "M10-1"])
    def test_audit_determination_tables_are_d_form(self, wp_code):
        """M{n}-1 审定表映射为 d-form-table。"""
        assert _WP_CODE_OVERRIDE.get(wp_code) == "d-form-table"

    def test_m8_applicable_when(self, m_class_entries):
        """M8 系列有 applicable_when: industry IN 金融类。"""
        m8_entries = [e for e in m_class_entries if e["wp_code"].startswith("M8")]
        for entry in m8_entries:
            aw = entry.get("applicable_when", {})
            assert "industry" in aw, f"{entry['wp_code']} 缺少 applicable_when.industry"
            assert "banking" in aw["industry"]


# ═══════════════════════════════════════════════════════════════════════════════
# P1: 程序表模板
# ═══════════════════════════════════════════════════════════════════════════════


class TestP1ProcedureTables:
    """P1: 程序表模板注册验证。"""

    _EXPECTED_TABLES = [
        "M1A", "M2A", "M3A", "M4A", "M5A", "M6A", "M7A", "M8A", "M9A", "M10A",
    ]

    def test_all_10_procedure_tables_registered(self, procedure_templates):
        """M1A~M10A 共 10 个程序表全部注册。"""
        for table_id in self._EXPECTED_TABLES:
            assert table_id in procedure_templates, (
                f"程序表 '{table_id}' 未注册到 procedure_table_templates.json"
            )

    @pytest.mark.parametrize("table_id", [
        "M1A", "M2A", "M3A", "M4A", "M5A", "M6A", "M7A", "M8A", "M9A", "M10A",
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

    def test_m6a_has_income_statement_total(self, procedure_templates):
        """M6A 程序表中有步骤引用 income_statement_total。"""
        items = procedure_templates["M6A"]["items"]
        sources = [it.get("auto_data_source") for it in items]
        assert "income_statement_total" in sources, (
            "M6A 缺少 income_statement_total 数据源引用"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# P2: 审定表 + 回写联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestP2AuditDetermination:
    """P2: 审定表 schema + handler 正则。"""

    def test_handler_regex_covers_m_class(self):
        """handler 正则 ^[D-N]\\d+-1$ 匹配所有 M 审定表。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        for i in range(1, 11):
            code = f"M{i}-1"
            assert pattern.match(code), f"正则不匹配 {code}"

    def test_m2_1_schema_exists(self):
        """M2-1 实收资本审定表 YAML schema 文件存在。"""
        schema_path = _SCHEMA_DIR / "M2-1.yaml"
        assert schema_path.exists()

    def test_m6_1_schema_exists(self):
        """M6-1 未分配利润审定表 YAML schema 文件存在。"""
        schema_path = _SCHEMA_DIR / "M6-1.yaml"
        assert schema_path.exists()

    def test_m2_1_has_shareholder_fields(self):
        """M2-1 schema 包含股东字段（股东名称/持股比例/出资方式/认缴/实缴）。"""
        schema_path = _SCHEMA_DIR / "M2-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "M2-1"
        assert schema.get("dynamic_rows") is True
        row_fields = schema["row_template"]["fields"]
        field_names = [f["field"] for f in row_fields]
        assert "shareholder_name" in field_names
        assert "shareholding_ratio" in field_names
        assert "contribution_type" in field_names
        assert "subscribed_amount" in field_names
        assert "paid_in_amount" in field_names
        assert "audited_amount" in field_names

    def test_m6_1_has_formula_fields(self):
        """M6-1 schema 包含公式字段（期初+净利润-提取-分配=期末）。"""
        schema_path = _SCHEMA_DIR / "M6-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "M6-1"
        assert schema.get("dynamic_rows") is False
        fields = schema["sections"][0]["fields"]
        field_names = [f["field"] for f in fields]
        assert "opening_retained_earnings" in field_names
        assert "net_income" in field_names
        assert "statutory_surplus_reserve" in field_names
        assert "dividend_distribution" in field_names
        assert "closing_retained_earnings" in field_names

    def test_m6_1_closing_formula(self):
        """M6-1 期末公式正确。"""
        schema_path = _SCHEMA_DIR / "M6-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        fields = schema["sections"][0]["fields"]
        closing = next(f for f in fields if f["field"] == "closing_retained_earnings")
        formula = closing.get("formula", "")
        assert "opening_retained_earnings" in formula
        assert "net_income" in formula
        assert "statutory_surplus_reserve" in formula
        assert "dividend_distribution" in formula


# ═══════════════════════════════════════════════════════════════════════════════
# P3: address_registry 坐标
# ═══════════════════════════════════════════════════════════════════════════════


class TestP3AddressRegistry:
    """P3: address_registry 坐标注册。"""

    def test_seed_file_exists(self):
        """m_address_registry_seed.json 存在。"""
        assert _ADDR_REGISTRY_PATH.exists()

    def test_seed_has_entries(self, addr_registry):
        """seed 有 entries 数组且 >= 4 条。"""
        assert "entries" in addr_registry
        assert len(addr_registry["entries"]) >= 4

    def test_seed_cycle_is_m(self, addr_registry):
        """seed cycle 标识为 M。"""
        assert addr_registry.get("cycle") == "M"

    def test_m6_2_coordinates(self, addr_registry):
        """M6-2 未分配利润勾稽表坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "M6-2" in codes

    def test_m6_5_coordinates(self, addr_registry):
        """M6-5 损益联动验证坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "M6-5" in codes

    def test_m2_2_coordinates(self, addr_registry):
        """M2-2 实收资本明细坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "M2-2" in codes

    def test_m9_2_coordinates(self, addr_registry):
        """M9-2 其他综合收益明细坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "M9-2" in codes

    def test_m6_2_has_reconciliation_coords(self, addr_registry):
        """M6-2 勾稽表有期初/净利润/分配/期末坐标。"""
        m6_2 = next(e for e in addr_registry["entries"] if e["wp_code"] == "M6-2")
        purposes = {c["purpose"] for c in m6_2["coordinates"]}
        assert "reconciliation_opening" in purposes
        assert "reconciliation_net_income" in purposes
        assert "reconciliation_closing" in purposes


# ═══════════════════════════════════════════════════════════════════════════════
# P4: 特殊程序
# ═══════════════════════════════════════════════════════════════════════════════


class TestP4SpecialProcedures:
    """P4: 特殊程序验证。"""

    def test_m6_2_is_audit_sheet(self):
        """M6-2 勾稽表映射为 audit-sheet。"""
        assert _WP_CODE_OVERRIDE.get("M6-2") == "audit-sheet"

    def test_m6_5_is_audit_sheet(self):
        """M6-5 损益联动验证映射为 audit-sheet。"""
        assert _WP_CODE_OVERRIDE.get("M6-5") == "audit-sheet"

    def test_m2_3_is_d_form_table(self):
        """M2-3 验资报告核实映射为 d-form-table。"""
        assert _WP_CODE_OVERRIDE.get("M2-3") == "d-form-table"

    def test_m2_4_is_d_form_table(self):
        """M2-4 工商变更核实映射为 d-form-table。"""
        assert _WP_CODE_OVERRIDE.get("M2-4") == "d-form-table"

    def test_m9_3_is_d_form_table(self):
        """M9-3 OCI分类检查映射为 d-form-table。"""
        assert _WP_CODE_OVERRIDE.get("M9-3") == "d-form-table"

    def test_m10_3_is_d_form_table(self):
        """M10-3 权益/负债分类检查映射为 d-form-table。"""
        assert _WP_CODE_OVERRIDE.get("M10-3") == "d-form-table"

    def test_m4_5_is_d_form_table(self):
        """M4-5 股份支付联动映射为 d-form-table。"""
        assert _WP_CODE_OVERRIDE.get("M4-5") == "d-form-table"

    def test_income_statement_total_resolver_registered(self):
        """income_statement_total resolver 已注册。"""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        assert "income_statement_total" in sources

    def test_m8_applicable_when_industry(self):
        """M8 系列 applicable_when 指定金融行业。"""
        # 通过 wp_account_mapping 验证
        with open(_MAPPING_PATH, encoding="utf-8") as f:
            data = json.load(f)
        mappings = data.get("mappings", data) if isinstance(data, dict) else data
        m8_primary = next(e for e in mappings if e["wp_code"] == "M8")
        aw = m8_primary.get("applicable_when", {})
        assert "industry" in aw
        industries = aw["industry"]
        assert "banking" in industries
        assert "insurance" in industries
        assert "securities" in industries


# ═══════════════════════════════════════════════════════════════════════════════
# P5: 联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestP5Linkage:
    """P5: 联动绑定验证。"""

    def test_risk_for_cycle_in_procedure_tables(self, procedure_templates):
        """M{n}A 程序表引用 risk_for_cycle。"""
        expected = ["M1A", "M2A", "M3A", "M4A", "M5A", "M6A", "M7A", "M8A", "M9A", "M10A"]
        tables_with_risk = []
        for key in expected:
            items = procedure_templates[key].get("items", [])
            for item in items:
                if item.get("auto_data_source") == "risk_for_cycle":
                    tables_with_risk.append(key)
                    break
        assert len(tables_with_risk) == 10

    def test_control_test_result_in_procedure_tables(self, procedure_templates):
        """M{n}A 程序表末步引用 control_test_result_for_cycle（C1 企业层面控制）。"""
        expected = ["M1A", "M2A", "M3A", "M4A", "M5A", "M6A", "M7A", "M8A", "M9A", "M10A"]
        tables_with_control = []
        for key in expected:
            items = procedure_templates[key].get("items", [])
            last = items[-1] if items else {}
            if last.get("auto_data_source") == "control_test_result_for_cycle":
                tables_with_control.append(key)
        assert len(tables_with_control) == 10

    def test_m4_5_ref_index_to_j3(self, procedure_templates):
        """M4A 程序表有步骤引用 M4-5（股份支付联动→J3）。"""
        items = procedure_templates["M4A"]["items"]
        refs = [it.get("ref_index") for it in items if it.get("ref_index")]
        assert "M4-5" in refs

    def test_m9_ref_to_g8(self, procedure_templates):
        """M9A 程序表有步骤引用 M9-4（OCI来源→G8关联）。"""
        items = procedure_templates["M9A"]["items"]
        refs = [it.get("ref_index") for it in items if it.get("ref_index")]
        assert "M9-4" in refs

    def test_m6_ref_to_m6_2(self, procedure_templates):
        """M6A 程序表有步骤引用 M6-2（勾稽表）。"""
        items = procedure_templates["M6A"]["items"]
        refs = [it.get("ref_index") for it in items if it.get("ref_index")]
        assert "M6-2" in refs

    def test_m6_ref_to_m6_5(self, procedure_templates):
        """M6A 程序表有步骤引用 M6-5（损益联动验证）。"""
        items = procedure_templates["M6A"]["items"]
        refs = [it.get("ref_index") for it in items if it.get("ref_index")]
        assert "M6-5" in refs


# ═══════════════════════════════════════════════════════════════════════════════
# P6: 导入导出
# ═══════════════════════════════════════════════════════════════════════════════


class TestP6ExportImport:
    """P6: 导入导出基础设施验证。"""

    _M_FORM_TABLE_CODES = [
        "M1-1", "M1-3", "M1-4",
        "M2-1", "M2-3", "M2-4", "M2-5", "M2-6",
        "M3-1", "M3-3", "M3-4",
        "M4-1", "M4-4", "M4-5", "M4-6",
        "M5-1", "M5-3", "M5-4",
        "M6-1", "M6-3", "M6-4", "M6-6",
        "M7-1", "M7-3", "M7-4",
        "M8-1", "M8-3", "M8-4",
        "M9-1", "M9-3", "M9-6",
        "M10-1", "M10-3", "M10-4",
    ]

    _AUDIT_SHEET_CODES = [
        "M1-2",
        "M2-2",
        "M3-2",
        "M4-2", "M4-3",
        "M5-2",
        "M6-2", "M6-5",
        "M7-2",
        "M8-2",
        "M9-2", "M9-4", "M9-5",
        "M10-2",
    ]

    @pytest.mark.parametrize("wp_code", _M_FORM_TABLE_CODES)
    def test_m_form_table_registered(self, wp_code):
        """M 类 d-form-table 底稿在 _WP_CODE_OVERRIDE 中注册正确。"""
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table"

    @pytest.mark.parametrize("wp_code", _AUDIT_SHEET_CODES)
    def test_m_audit_sheet_registered(self, wp_code):
        """M 类 audit-sheet 底稿在 _WP_CODE_OVERRIDE 中注册正确。"""
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == "audit-sheet"

    def test_all_m_codes_in_mapping(self, m_class_entries):
        """所有 M 类 wp_code 在 wp_account_mapping 注册（批量导出可枚举）。"""
        mapping_codes = {e["wp_code"] for e in m_class_entries}
        all_codes = set(self._M_FORM_TABLE_CODES + self._AUDIT_SHEET_CODES)
        missing = all_codes - mapping_codes
        assert not missing, f"M 类缺少: {sorted(missing)}"

    def test_m_class_all_have_wp_code(self, m_class_entries):
        """所有 M 类条目有有效 wp_code。"""
        for entry in m_class_entries:
            assert entry.get("wp_code"), f"缺少 wp_code: {entry}"
            assert entry["wp_code"].startswith("M")

    def test_m2_1_yaml_schema_parseable_for_import(self):
        """M2-1 审定表 YAML schema 可正确解析用于导入填充。"""
        schema_path = _SCHEMA_DIR / "M2-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "M2-1"
        assert schema["component_type"] == "d-form-table"
        assert schema.get("dynamic_rows") is True

    def test_m6_1_yaml_schema_parseable_for_import(self):
        """M6-1 审定表 YAML schema 可正确解析用于导入填充。"""
        schema_path = _SCHEMA_DIR / "M6-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "M6-1"
        assert schema["component_type"] == "d-form-table"
        assert schema.get("dynamic_rows") is False

    def test_batch_export_type_distribution(self):
        """M 类 componentType 分布合理。"""
        m_codes = {code: ct for code, ct in _WP_CODE_OVERRIDE.items() if re.match(r'^M\d', code)}
        type_counts: dict[str, int] = {}
        for ct in m_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1
        assert type_counts.get("d-form-table", 0) >= 25
        assert type_counts.get("audit-sheet", 0) >= 14
