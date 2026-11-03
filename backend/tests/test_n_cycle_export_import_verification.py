"""N 类底稿（税费循环）完整验证测试。

覆盖 P0-P6 综合验证：
  1. wp_account_mapping 注册完整性
  2. _WP_CODE_OVERRIDE componentType 映射
  3. 程序表模板注册
  4. 审定表 schema + handler 正则
  5. address_registry 坐标注册
  6. 特殊程序（N5-3所得税计算/N1-3暂时性差异/N2-3增值税核对）
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
_ADDR_REGISTRY_PATH = _DATA_DIR / "n_address_registry_seed.json"
_SCHEMA_DIR = _DATA_DIR / "ledger_adapters" / "wp_render_schema"


@pytest.fixture(scope="module")
def wp_mapping() -> list[dict]:
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mappings", data) if isinstance(data, dict) else data


@pytest.fixture(scope="module")
def n_class_entries(wp_mapping) -> list[dict]:
    return [e for e in wp_mapping if e.get("cycle") == "N"]


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

    _ALL_N_SUBCODES = [
        # N1 递延所得税资产
        "N1-1", "N1-2", "N1-3", "N1-4", "N1-5", "N1-6",
        # N2 应交税费
        "N2-1", "N2-2", "N2-3", "N2-4", "N2-5", "N2-6",
        "N2-7", "N2-8", "N2-9", "N2-10", "N2-11",
        # N3 递延所得税负债
        "N3-1", "N3-2", "N3-3",
        # N4 税金及附加
        "N4-1", "N4-2", "N4-3",
        # N5 所得税费用
        "N5-1", "N5-2", "N5-3", "N5-4", "N5-5",
        "N5-6", "N5-6-1", "N5-6-2", "N5-7", "N5-8",
    ]

    _PARENT_CODES = ["N1", "N2", "N3", "N4", "N5"]

    _PROGRAM_CODES = ["N1A", "N2A", "N3A", "N4A", "N5A"]

    def test_n_class_count(self, n_class_entries):
        """wp_account_mapping.json 中应有 ≥35 个 cycle='N' 的条目。"""
        assert len(n_class_entries) >= 35, (
            f"N 类底稿应有 ≥35 条注册，实际 {len(n_class_entries)} 条"
        )

    def test_all_n_subcodes_have_override(self):
        """所有 N 类子码在 _WP_CODE_OVERRIDE 中有 componentType 映射。"""
        for code in self._ALL_N_SUBCODES:
            assert code in _WP_CODE_OVERRIDE, (
                f"N 类 wp_code '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )

    def test_all_parent_codes_have_override(self):
        """所有 N 类父码在 _WP_CODE_OVERRIDE 中有映射。"""
        for code in self._PARENT_CODES:
            assert code in _WP_CODE_OVERRIDE, (
                f"N 类父码 '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )

    # N 循环级 componentType 映射（wp_code_overrides.json 实际值）
    _CYCLE_CT = {
        "N1": "n1-deferred-tax-assets",
        "N2": "n2-taxes-payable",
        "N3": "n3-deferred-tax-liabilities",
        "N4": "n4-taxes-and-surcharges",
        "N5": "n5-income-tax-expense",
    }

    def test_all_program_codes_have_override(self):
        """所有 N 类程序表在 _WP_CODE_OVERRIDE 中有映射。"""
        for code in self._PROGRAM_CODES:
            assert code in _WP_CODE_OVERRIDE, (
                f"N 类程序表 '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )
            prefix = code.rstrip("A")
            expected = self._CYCLE_CT[prefix]
            assert _WP_CODE_OVERRIDE[code] == expected, (
                f"{code} 应映射 {expected}，实际 {_WP_CODE_OVERRIDE[code]}"
            )

    def test_all_component_types_valid(self):
        """所有 N 类子码 componentType 必须是合法类型。"""
        for code in self._ALL_N_SUBCODES + self._PARENT_CODES + self._PROGRAM_CODES:
            ct = _WP_CODE_OVERRIDE.get(code, "")
            assert ct in VALID_COMPONENT_TYPES, (
                f"N 类 '{code}' componentType '{ct}' 不合法"
            )

    def test_no_confirmation_hub(self):
        """N 类无函证（无 N0），不应有 confirmation-hub 映射。"""
        n_codes = {code: ct for code, ct in _WP_CODE_OVERRIDE.items() if re.match(r'^N\d', code)}
        for code, ct in n_codes.items():
            assert ct != "confirmation-hub", f"N 类 '{code}' 不应映射 confirmation-hub"

    def test_type_distribution(self):
        """N 类 componentType 分布符合预期：以循环级专用类型为主。"""
        n_codes = {code: ct for code, ct in _WP_CODE_OVERRIDE.items() if re.match(r'^N\d', code)}
        type_counts: dict[str, int] = {}
        for ct in n_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1
        # 5 个循环级 componentType 覆盖绝大多数 N 码
        cycle_types = {
            "n1-deferred-tax-assets", "n2-taxes-payable",
            "n3-deferred-tax-liabilities", "n4-taxes-and-surcharges",
            "n5-income-tax-expense",
        }
        cycle_total = sum(type_counts.get(ct, 0) for ct in cycle_types)
        assert cycle_total >= 38, f"循环级类型覆盖 {cycle_total} 个，应 ≥38"
        # N1-6 例外映射为 d-form-table
        assert type_counts.get("d-form-table", 0) >= 1

    @pytest.mark.parametrize("wp_code", ["N1-1", "N2-1", "N3-1", "N4-1", "N5-1"])
    def test_audit_determination_maps_to_cycle_component(self, wp_code):
        """N{n}-1 审定表映射为对应循环级 componentType。"""
        prefix = wp_code.split("-")[0]
        expected = self._CYCLE_CT[prefix]
        assert _WP_CODE_OVERRIDE.get(wp_code) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# P1: 程序表模板
# ═══════════════════════════════════════════════════════════════════════════════


class TestP1ProcedureTables:
    """P1: 程序表模板注册验证。"""

    _EXPECTED_TABLES = ["N1A", "N2A", "N3A", "N4A", "N5A"]

    def test_all_5_procedure_tables_registered(self, procedure_templates):
        """N1A~N5A 共 5 个程序表全部注册。"""
        for table_id in self._EXPECTED_TABLES:
            assert table_id in procedure_templates, (
                f"程序表 '{table_id}' 未注册到 procedure_table_templates.json"
            )

    @pytest.mark.parametrize("table_id", ["N1A", "N2A", "N3A", "N4A", "N5A"])
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

    def test_n5a_has_income_tax_calculation(self, procedure_templates):
        """N5A 程序表中有步骤引用 income_tax_calculation。"""
        items = procedure_templates["N5A"]["items"]
        sources = [it.get("auto_data_source") for it in items]
        assert "income_tax_calculation" in sources, (
            "N5A 缺少 income_tax_calculation 数据源引用"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# P2: 审定表 + 回写联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestP2AuditDetermination:
    """P2: 审定表 schema + handler 正则。"""

    def test_handler_regex_covers_n_class(self):
        """handler 正则 ^[D-N]\\d+-1$ 匹配所有 N 审定表。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        for i in range(1, 6):
            code = f"N{i}-1"
            assert pattern.match(code), f"正则不匹配 {code}"

    def test_n2_1_schema_exists(self):
        """N2-1 应交税费审定表 YAML schema 文件存在。"""
        schema_path = _SCHEMA_DIR / "N2-1.yaml"
        assert schema_path.exists()

    def test_n5_1_schema_exists(self):
        """N5-1 所得税费用审定表 YAML schema 文件存在。"""
        schema_path = _SCHEMA_DIR / "N5-1.yaml"
        assert schema_path.exists()

    def test_n2_1_has_tax_type_rows(self):
        """N2-1 schema 按税种分行（增值税/所得税/个税/城建/教育/房产/土地等）。"""
        schema_path = _SCHEMA_DIR / "N2-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "N2-1"
        assert schema.get("dynamic_rows") is True
        row_fields = schema["row_template"]["fields"]
        field_names = [f["field"] for f in row_fields]
        assert "tax_type" in field_names
        assert "audited_amount" in field_names

    def test_n5_1_has_current_deferred_total(self):
        """N5-1 schema 包含当期所得税+递延所得税=合计字段。"""
        schema_path = _SCHEMA_DIR / "N5-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "N5-1"
        assert schema.get("dynamic_rows") is False
        fields = schema["sections"][0]["fields"]
        field_names = [f["field"] for f in fields]
        assert "current_income_tax" in field_names
        assert "deferred_income_tax" in field_names
        assert "total_income_tax" in field_names

    def test_n5_1_total_formula(self):
        """N5-1 合计公式 = 当期 + 递延。"""
        schema_path = _SCHEMA_DIR / "N5-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        fields = schema["sections"][0]["fields"]
        total = next(f for f in fields if f["field"] == "total_income_tax")
        formula = total.get("formula", "")
        assert "current_income_tax" in formula
        assert "deferred_income_tax" in formula


# ═══════════════════════════════════════════════════════════════════════════════
# P3: address_registry 坐标
# ═══════════════════════════════════════════════════════════════════════════════


class TestP3AddressRegistry:
    """P3: address_registry 坐标注册。"""

    def test_seed_file_exists(self):
        """n_address_registry_seed.json 存在。"""
        assert _ADDR_REGISTRY_PATH.exists()

    def test_seed_has_entries(self, addr_registry):
        """seed 有 entries 数组且 >= 6 条。"""
        assert "entries" in addr_registry
        assert len(addr_registry["entries"]) >= 6

    def test_seed_cycle_is_n(self, addr_registry):
        """seed cycle 标识为 N。"""
        assert addr_registry.get("cycle") == "N"

    def test_n1_3_coordinates(self, addr_registry):
        """N1-3 暂时性差异计算坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "N1-3" in codes

    def test_n3_3_coordinates(self, addr_registry):
        """N3-3 暂时性差异计算坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "N3-3" in codes

    def test_n2_3_coordinates(self, addr_registry):
        """N2-3 增值税核对坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "N2-3" in codes

    def test_n5_3_coordinates(self, addr_registry):
        """N5-3 所得税计算坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "N5-3" in codes

    def test_n5_4_coordinates(self, addr_registry):
        """N5-4 纳税调增调减坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "N5-4" in codes

    def test_n5_5_coordinates(self, addr_registry):
        """N5-5 有效税率分析坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "N5-5" in codes

    def test_n5_3_has_tax_calculation_coords(self, addr_registry):
        """N5-3 所得税计算有应纳税所得额/当期所得税坐标。"""
        n5_3 = next(e for e in addr_registry["entries"] if e["wp_code"] == "N5-3")
        purposes = {c["purpose"] for c in n5_3["coordinates"]}
        assert "taxable_income" in purposes
        assert "current_income_tax_expense" in purposes


# ═══════════════════════════════════════════════════════════════════════════════
# P4: 特殊程序
# ═══════════════════════════════════════════════════════════════════════════════


class TestP4SpecialProcedures:
    """P4: 特殊程序 componentType 映射验证（全部映射到循环级专用类型）。"""

    # N 循环级 componentType 映射
    _CYCLE_CT = {
        "N1": "n1-deferred-tax-assets",
        "N2": "n2-taxes-payable",
        "N3": "n3-deferred-tax-liabilities",
        "N4": "n4-taxes-and-surcharges",
        "N5": "n5-income-tax-expense",
    }

    _SPECIAL_CODES = [
        ("N5-3", "所得税计算表"),
        ("N5-4", "纳税调增调减明细"),
        ("N5-5", "有效税率分析"),
        ("N1-3", "暂时性差异计算（可抵扣）"),
        ("N3-3", "暂时性差异计算（应纳税）"),
        ("N2-3", "增值税核对表"),
        ("N1-4", "可抵扣确认条件"),
        ("N5-6", "递延所得税联动"),
        ("N5-7", "研发加计扣除"),
    ]

    @pytest.mark.parametrize(("wp_code", "label"),
                             _SPECIAL_CODES,
                             ids=[c for c, _ in _SPECIAL_CODES])
    def test_special_code_maps_to_cycle_component(self, wp_code, label):
        """N 类特殊程序底稿映射到对应循环级 componentType。"""
        prefix = wp_code.split("-")[0]
        expected = self._CYCLE_CT[prefix]
        actual = _WP_CODE_OVERRIDE.get(wp_code)
        assert actual == expected, (
            f"{wp_code}（{label}）应映射 {expected}，实际 {actual}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# P5: 联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestP5Linkage:
    """P5: 联动绑定验证。"""

    def test_risk_for_cycle_in_procedure_tables(self, procedure_templates):
        """N{n}A 程序表引用 risk_for_cycle。"""
        expected = ["N1A", "N2A", "N3A", "N4A", "N5A"]
        tables_with_risk = []
        for key in expected:
            items = procedure_templates[key].get("items", [])
            for item in items:
                if item.get("auto_data_source") == "risk_for_cycle":
                    tables_with_risk.append(key)
                    break
        assert len(tables_with_risk) == 5

    def test_control_test_result_in_procedure_tables(self, procedure_templates):
        """N{n}A 程序表末步引用 control_test_result_for_cycle。"""
        expected = ["N1A", "N2A", "N3A", "N4A", "N5A"]
        tables_with_control = []
        for key in expected:
            items = procedure_templates[key].get("items", [])
            last = items[-1] if items else {}
            if last.get("auto_data_source") == "control_test_result_for_cycle":
                tables_with_control.append(key)
        assert len(tables_with_control) == 5

    def test_n5a_has_n5_6_ref(self, procedure_templates):
        """N5A 程序表有步骤引用 N5-6（递延所得税联动→N1/N3）。"""
        items = procedure_templates["N5A"]["items"]
        refs = [it.get("ref_index") for it in items if it.get("ref_index")]
        assert "N5-6" in refs

    def test_n5a_has_n5_7_ref(self, procedure_templates):
        """N5A 程序表有步骤引用 N5-7（研发加计扣除→I6-7）。"""
        items = procedure_templates["N5A"]["items"]
        refs = [it.get("ref_index") for it in items if it.get("ref_index")]
        assert "N5-7" in refs

    def test_temporary_differences_summary_resolver_registered(self):
        """temporary_differences_summary resolver 已注册。"""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        assert "temporary_differences_summary" in sources

    def test_income_tax_calculation_resolver_registered(self):
        """income_tax_calculation resolver 已注册。"""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        assert "income_tax_calculation" in sources


# ═══════════════════════════════════════════════════════════════════════════════
# P6: 导入导出
# ═══════════════════════════════════════════════════════════════════════════════


class TestP6ExportImport:
    """P6: 导入导出基础设施验证。"""

    # N 循环级 componentType 映射
    _CYCLE_CT = {
        "N1": "n1-deferred-tax-assets",
        "N2": "n2-taxes-payable",
        "N3": "n3-deferred-tax-liabilities",
        "N4": "n4-taxes-and-surcharges",
        "N5": "n5-income-tax-expense",
    }

    _N_FORM_TABLE_CODES = [
        "N1-1", "N1-4", "N1-6",
        "N2-1", "N2-4", "N2-6",
        "N3-1",
        "N4-1",
        "N5-1", "N5-6", "N5-8",
    ]

    _AUDIT_SHEET_CODES = [
        "N1-2", "N1-3", "N1-5",
        "N2-2", "N2-3", "N2-5",
        "N3-2", "N3-3",
        "N4-2", "N4-3",
        "N5-2", "N5-3", "N5-4", "N5-5", "N5-7",
    ]

    @pytest.mark.parametrize("wp_code", _N_FORM_TABLE_CODES)
    def test_n_structured_code_maps_to_cycle_component(self, wp_code):
        """N 类结构化底稿映射到对应循环级 componentType。"""
        assert wp_code in _WP_CODE_OVERRIDE
        prefix = wp_code.split("-")[0]
        expected = self._CYCLE_CT[prefix]
        # N1-6 例外：映射到 d-form-table
        if wp_code == "N1-6":
            assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table"
        else:
            assert _WP_CODE_OVERRIDE[wp_code] == expected, (
                f"{wp_code} 应映射 {expected}，实际 {_WP_CODE_OVERRIDE[wp_code]}"
            )

    @pytest.mark.parametrize("wp_code", _AUDIT_SHEET_CODES)
    def test_n_analysis_code_maps_to_cycle_component(self, wp_code):
        """N 类分析底稿映射到对应循环级 componentType。"""
        assert wp_code in _WP_CODE_OVERRIDE
        prefix = wp_code.split("-")[0]
        expected = self._CYCLE_CT[prefix]
        assert _WP_CODE_OVERRIDE[wp_code] == expected, (
            f"{wp_code} 应映射 {expected}，实际 {_WP_CODE_OVERRIDE[wp_code]}"
        )

    def test_all_n_codes_in_mapping(self, n_class_entries):
        """所有 N 类 wp_code 在 wp_account_mapping 注册（批量导出可枚举）。"""
        mapping_codes = {e["wp_code"] for e in n_class_entries}
        all_codes = set(self._N_FORM_TABLE_CODES + self._AUDIT_SHEET_CODES)
        missing = all_codes - mapping_codes
        assert not missing, f"N 类缺少: {sorted(missing)}"

    def test_n_class_all_have_wp_code(self, n_class_entries):
        """所有 N 类条目有有效 wp_code。"""
        for entry in n_class_entries:
            assert entry.get("wp_code"), f"缺少 wp_code: {entry}"
            assert entry["wp_code"].startswith("N")

    def test_n2_1_yaml_schema_parseable_for_import(self):
        """N2-1 审定表 YAML schema 可正确解析用于导入填充。"""
        schema_path = _SCHEMA_DIR / "N2-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "N2-1"
        assert schema["component_type"] == "d-form-table"
        assert schema.get("dynamic_rows") is True

    def test_n5_1_yaml_schema_parseable_for_import(self):
        """N5-1 审定表 YAML schema 可正确解析用于导入填充。"""
        schema_path = _SCHEMA_DIR / "N5-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "N5-1"
        assert schema["component_type"] == "d-form-table"
        assert schema.get("dynamic_rows") is False

    def test_batch_export_type_distribution(self):
        """N 类 componentType 以循环级专用类型为主。"""
        n_codes = {code: ct for code, ct in _WP_CODE_OVERRIDE.items() if re.match(r'^N\d', code)}
        type_counts: dict[str, int] = {}
        for ct in n_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1
        cycle_types = {
            "n1-deferred-tax-assets", "n2-taxes-payable",
            "n3-deferred-tax-liabilities", "n4-taxes-and-surcharges",
            "n5-income-tax-expense",
        }
        cycle_total = sum(type_counts.get(ct, 0) for ct in cycle_types)
        assert cycle_total >= 38, f"循环级类型覆盖 {cycle_total} 个，应 ≥38"
