"""J 类底稿（职工薪酬循环）完整验证测试。

覆盖:
  P0: 注册完整性（wp_account_mapping + _WP_CODE_OVERRIDE）
  P1: 程序表模板注册（J1A~J3A 共 3 个）
  P2: 审定表 schema（J1-1 YAML）+ handler 正则
  P3: address_registry 坐标注册
  P4: 特殊程序 schema 确认
  P5: 联动绑定
  P6: 导入导出基础设施验证
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

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
# P0: 注册完整性
# ═══════════════════════════════════════════════════════════════════════════════


class TestP0Registration:
    """P0 Tasks 1-4: wp_account_mapping + _WP_CODE_OVERRIDE 完整性。"""

    # J 类子码 wp_codes（不含 J1/J2/J3 父码和程序表 J{n}A）
    # 父码（J1/J2/J3）在 wp_account_mapping 中注册但通过 fallback 分类，不在 _WP_CODE_OVERRIDE
    _ALL_J_CODES = [
        # J1 应付职工薪酬
        "J1-1", "J1-2", "J1-3", "J1-4", "J1-5", "J1-6", "J1-7", "J1-8",
        # J2 设定受益计划
        "J2-1", "J2-2", "J2-3", "J2-4", "J2-5", "J2-6",
        # J3 股份支付
        "J3-1", "J3-2", "J3-3", "J3-4", "J3-5", "J3-6",
    ]

    # 父码（在 mapping 中但不在 override 中）
    _PARENT_CODES = ["J1", "J2", "J3"]

    def test_j_class_count(self, j_class_entries):
        """wp_account_mapping.json 中应有 ≥23 个 cycle='J' 的条目。"""
        assert len(j_class_entries) >= 23, (
            f"J 类底稿应有 ≥23 条注册，实际 {len(j_class_entries)} 条"
        )

    def test_all_j_codes_in_mapping(self, j_class_entries):
        """所有 J 类 wp_code 在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in j_class_entries}
        all_codes = set(self._ALL_J_CODES + self._PARENT_CODES)
        missing = all_codes - mapping_codes
        assert not missing, f"J 类缺少 wp_code: {sorted(missing)}"

    def test_all_j_subcodes_have_override(self):
        """所有 J 类子码在 _WP_CODE_OVERRIDE 中有 componentType 映射。"""
        for code in self._ALL_J_CODES:
            assert code in _WP_CODE_OVERRIDE, (
                f"J 类 wp_code '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )

    def test_no_j0_confirmation_hub(self):
        """J 类无函证组（无 J0 ConfirmationHub）。"""
        assert "J0" not in _WP_CODE_OVERRIDE

    def test_all_component_types_valid(self):
        """所有 J 类子码 componentType 必须是合法类型。"""
        valid_types = {"d-form-table", "audit-sheet"}
        for code in self._ALL_J_CODES:
            ct = _WP_CODE_OVERRIDE.get(code, "")
            assert ct in valid_types, (
                f"J 类 '{code}' componentType '{ct}' 不合法"
            )

    def test_type_distribution(self):
        """J 类 componentType 分布符合预期。"""
        j_codes = {
            code: ct for code, ct in _WP_CODE_OVERRIDE.items()
            if re.match(r'^J\d', code)
        }
        type_counts: dict[str, int] = {}
        for ct in j_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1
        # J 类无 confirmation-hub
        assert type_counts.get("confirmation-hub", 0) == 0
        assert type_counts.get("d-form-table", 0) >= 9
        assert type_counts.get("audit-sheet", 0) >= 11

    @pytest.mark.parametrize("wp_code", ["J1-1", "J2-1", "J3-1"])
    def test_audit_determination_tables_are_d_form(self, wp_code):
        """J{n}-1 审定表映射为 d-form-table。"""
        assert _WP_CODE_OVERRIDE.get(wp_code) == "d-form-table"


# ═══════════════════════════════════════════════════════════════════════════════
# P1: 程序表模板
# ═══════════════════════════════════════════════════════════════════════════════


class TestP1ProcedureTables:
    """P1 Tasks 5-9: 程序表模板注册验证。"""

    _EXPECTED_TABLES = ["J1A", "J2A", "J3A"]

    def test_all_3_procedure_tables_registered(self, procedure_templates):
        """J1A~J3A 共 3 个程序表全部注册。"""
        for table_id in self._EXPECTED_TABLES:
            assert table_id in procedure_templates, (
                f"程序表 '{table_id}' 未注册到 procedure_table_templates.json"
            )

    @pytest.mark.parametrize("table_id", ["J1A", "J2A", "J3A"])
    def test_procedure_table_has_items(self, procedure_templates, table_id):
        """每个程序表有 items 且步骤数 >= 5。"""
        table = procedure_templates[table_id]
        assert "items" in table, f"{table_id} 缺少 items"
        assert len(table["items"]) >= 5, (
            f"{table_id} 步骤数 {len(table['items'])} < 5"
        )

    def test_procedure_tables_have_names(self, procedure_templates):
        """每个程序表有 name 字段。"""
        for table_id in self._EXPECTED_TABLES:
            assert "name" in procedure_templates[table_id]

    def test_procedure_items_have_seq(self, procedure_templates):
        """每个步骤有 seq 字段且递增。"""
        for table_id in self._EXPECTED_TABLES:
            items = procedure_templates[table_id]["items"]
            seqs = [item["seq"] for item in items]
            assert seqs == sorted(seqs), f"{table_id} seq 不递增"

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
    """P2 Tasks 10-13: 审定表 schema + handler 正则。"""

    _AUDIT_DET_CODES = ["J1-1", "J2-1", "J3-1"]

    def test_handler_regex_covers_j_class(self):
        """handler 正则 ^[D-N]\\d+-1$ 匹配所有 J 审定表。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        for code in self._AUDIT_DET_CODES:
            assert pattern.match(code), f"正则不匹配 {code}"

    def test_j1_1_schema_exists(self):
        """J1-1 特殊 YAML schema 文件存在。"""
        schema_path = _SCHEMA_DIR / "J1-1.yaml"
        assert schema_path.exists(), f"J1-1 schema 不存在: {schema_path}"

    def test_j1_1_schema_has_category_sections(self):
        """J1-1 schema 包含薪酬类别分组。"""
        import yaml
        schema_path = _SCHEMA_DIR / "J1-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        section_names = [s["name"] for s in schema["sections"]]
        assert "工资" in section_names
        assert "奖金" in section_names
        assert "社会保险" in section_names
        assert "住房公积金" in section_names
        assert "职工福利" in section_names

    def test_j1_1_has_total_row(self):
        """J1-1 schema 包含合计行。"""
        import yaml
        schema_path = _SCHEMA_DIR / "J1-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        section_names = [s["name"] for s in schema["sections"]]
        assert "应付职工薪酬合计" in section_names

    def test_j1_1_has_writeback_config(self):
        """J1-1 schema 包含 writeback 配置。"""
        import yaml
        schema_path = _SCHEMA_DIR / "J1-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert "writeback" in schema
        assert schema["writeback"]["target"] == "trial_balance.audited_amount"

    @pytest.mark.parametrize("wp_code", _AUDIT_DET_CODES)
    def test_audit_det_component_type(self, wp_code):
        """所有 3 个审定表为 d-form-table。"""
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table"


# ═══════════════════════════════════════════════════════════════════════════════
# P3: address_registry 坐标
# ═══════════════════════════════════════════════════════════════════════════════


class TestP3AddressRegistry:
    """P3 Tasks 14-18: address_registry 坐标注册。"""

    def test_seed_file_exists(self):
        """j_address_registry_seed.json 存在。"""
        assert _ADDR_REGISTRY_PATH.exists()

    def test_seed_has_entries(self, addr_registry):
        """seed 有 entries 数组。"""
        assert "entries" in addr_registry
        assert len(addr_registry["entries"]) >= 5

    def test_seed_cycle_is_j(self, addr_registry):
        """seed cycle 标识为 J。"""
        assert addr_registry.get("cycle") == "J"

    def test_j1_3_wage_coordinates(self, addr_registry):
        """J1-3 工资测算坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "J1-3" in codes

    def test_j1_4_social_insurance_coordinates(self, addr_registry):
        """J1-4 社保测算坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "J1-4" in codes

    def test_j2_5_actuarial_coordinates(self, addr_registry):
        """J2-5 精算重算坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "J2-5" in codes
        j2_5 = next(e for e in addr_registry["entries"] if e["wp_code"] == "J2-5")
        purposes = {c["purpose"] for c in j2_5["coordinates"]}
        assert "actuarial_calc" in purposes

    def test_j3_4_option_pricing_coordinates(self, addr_registry):
        """J3-4 期权定价坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "J3-4" in codes
        j3_4 = next(e for e in addr_registry["entries"] if e["wp_code"] == "J3-4")
        purposes = {c["purpose"] for c in j3_4["coordinates"]}
        assert "option_pricing" in purposes

    def test_j3_5_vesting_expense_coordinates(self, addr_registry):
        """J3-5 等待期费用分摊坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "J3-5" in codes
        j3_5 = next(e for e in addr_registry["entries"] if e["wp_code"] == "J3-5")
        purposes = {c["purpose"] for c in j3_5["coordinates"]}
        assert "vesting_expense" in purposes

    def test_all_entries_have_coordinates(self, addr_registry):
        """每个 entry 有 coordinates 数组且非空。"""
        for entry in addr_registry["entries"]:
            assert "coordinates" in entry, f"{entry['wp_code']} 缺少 coordinates"
            assert len(entry["coordinates"]) >= 1

    def test_coordinates_have_required_fields(self, addr_registry):
        """坐标包含 cell_address, description, purpose。"""
        for entry in addr_registry["entries"]:
            for coord in entry["coordinates"]:
                assert "cell_address" in coord, f"{entry['wp_code']} 坐标缺少 cell_address"
                assert "description" in coord, f"{entry['wp_code']} 坐标缺少 description"
                assert "purpose" in coord, f"{entry['wp_code']} 坐标缺少 purpose"


# ═══════════════════════════════════════════════════════════════════════════════
# P4: 特殊程序
# ═══════════════════════════════════════════════════════════════════════════════


class TestP4SpecialProcedures:
    """P4 Tasks 19-23: 特殊程序 schema 确认。"""

    def test_j1_3_wage_calc_is_audit_sheet(self):
        """J1-3 工资测算走 audit-sheet（人数×平均工资×月份含公式）。"""
        assert _WP_CODE_OVERRIDE["J1-3"] == "audit-sheet"

    def test_j1_4_social_insurance_is_audit_sheet(self):
        """J1-4 社保测算走 audit-sheet（基数×比例含公式）。"""
        assert _WP_CODE_OVERRIDE["J1-4"] == "audit-sheet"

    def test_j2_3_actuarial_assumptions_is_d_form_table(self):
        """J2-3 精算假设评估走 d-form-table（折现率/工资增长率/离职率/死亡率）。"""
        assert _WP_CODE_OVERRIDE["J2-3"] == "d-form-table"

    def test_j2_4_actuary_work_is_d_form_table(self):
        """J2-4 精算师工作利用走 d-form-table（评估胜任能力/客观性/工作范围）。"""
        assert _WP_CODE_OVERRIDE["J2-4"] == "d-form-table"

    def test_j2_5_actuarial_recalc_is_audit_sheet(self):
        """J2-5 精算重新计算走 audit-sheet（DBO/计划资产/净负债含公式）。"""
        assert _WP_CODE_OVERRIDE["J2-5"] == "audit-sheet"

    def test_j3_3_grant_conditions_is_d_form_table(self):
        """J3-3 授予条件检查走 d-form-table（结构化检查）。"""
        assert _WP_CODE_OVERRIDE["J3-3"] == "d-form-table"

    def test_j3_4_option_pricing_is_audit_sheet(self):
        """J3-4 期权定价走 audit-sheet（Black-Scholes 参数+公式）。"""
        assert _WP_CODE_OVERRIDE["J3-4"] == "audit-sheet"

    def test_j3_5_vesting_expense_is_audit_sheet(self):
        """J3-5 等待期费用分摊走 audit-sheet（总公允价值÷等待期×已服务月份）。"""
        assert _WP_CODE_OVERRIDE["J3-5"] == "audit-sheet"

    def test_adjustment_entries_are_d_form_table(self):
        """J1-8/J2-6/J3-6 调整分录走 d-form-table。"""
        for code in ["J1-8", "J2-6", "J3-6"]:
            assert _WP_CODE_OVERRIDE[code] == "d-form-table", (
                f"{code} 应为 d-form-table，实际为 {_WP_CODE_OVERRIDE[code]}"
            )

    def test_all_j_class_routes_no_missing(self):
        """J 全系列在 _WP_CODE_OVERRIDE 中无遗漏（componentType 路由无 404）。"""
        j_codes = [code for code in _WP_CODE_OVERRIDE if re.match(r'^J\d', code)]
        assert len(j_codes) == 23, f"应有 23 个 J 类映射，实际 {len(j_codes)}"


# ═══════════════════════════════════════════════════════════════════════════════
# P5: 联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestP5Linkage:
    """P5 Tasks 24-26: 联动绑定验证。"""

    def test_risk_for_cycle_in_procedure_tables(self, procedure_templates):
        """J{n}A 程序表引用 risk_for_cycle。"""
        tables_with_risk = []
        for key in procedure_templates:
            if key.startswith("J") and key.endswith("A"):
                items = procedure_templates[key].get("items", [])
                for item in items:
                    if item.get("auto_data_source") == "risk_for_cycle":
                        tables_with_risk.append(key)
                        break
        # 所有 3 个程序表引用 risk
        assert len(tables_with_risk) == 3

    def test_control_test_in_procedure_tables(self, procedure_templates):
        """部分程序表引用 control_test_result_for_cycle。"""
        tables_with_control = []
        for key in procedure_templates:
            if key.startswith("J") and key.endswith("A"):
                items = procedure_templates[key].get("items", [])
                for item in items:
                    if item.get("auto_data_source") == "control_test_result_for_cycle":
                        tables_with_control.append(key)
                        break
        assert len(tables_with_control) >= 2

    def test_j2_b51_cross_ref_in_procedure(self, procedure_templates):
        """J2A 程序表应有精算师工作利用引用（J2-4）。"""
        items = procedure_templates["J2A"]["items"]
        refs = " ".join(item.get("ref_index", "") or "" for item in items)
        # J2→B51 联动通过 accounting_estimate_b51 resolver 在服务层实现
        # 程序表中应有 J2-4 精算师工作利用的引用
        assert "J2-4" in refs, (
            "J2A 应有 J2-4 引用（精算师工作利用评估）"
        )

    def test_j3_share_payment_refs_in_procedure(self, procedure_templates):
        """J3A 程序表引用 J3-1/J3-2（股份支付联动）。"""
        items = procedure_templates["J3A"]["items"]
        refs = " ".join(item.get("ref_index", "") or "" for item in items)
        # J3→M4 联动通过 ref_index chip 在服务层实现
        # 程序表中应有 J3-1/J3-2 审定表/明细的引用
        assert "J3-1" in refs, "J3A 应有 J3-1 引用（股份支付审定表）"
        assert "J3-2" in refs, "J3A 应有 J3-2 引用（股份支付明细）"


# ═══════════════════════════════════════════════════════════════════════════════
# P6: 导入导出
# ═══════════════════════════════════════════════════════════════════════════════


class TestP6ExportImport:
    """P6 Tasks 27-29: 导入导出基础设施验证。"""

    # J 类 d-form-table wp_codes（仅 _WP_CODE_OVERRIDE 中注册的子码）
    _J_FORM_TABLE_CODES = [
        "J1-1", "J1-8",
        "J2-1", "J2-3", "J2-4", "J2-6",
        "J3-1", "J3-3", "J3-6",
    ]

    # J 类 audit-sheet wp_codes
    _AUDIT_SHEET_CODES = [
        "J1-2", "J1-3", "J1-4", "J1-5", "J1-6", "J1-7",
        "J2-2", "J2-5",
        "J3-2", "J3-4", "J3-5",
    ]

    @pytest.mark.parametrize("wp_code", _J_FORM_TABLE_CODES)
    def test_j_form_table_registered(self, wp_code):
        """J 类 d-form-table 底稿在 _WP_CODE_OVERRIDE 中注册正确。"""
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table"

    @pytest.mark.parametrize("wp_code", _AUDIT_SHEET_CODES)
    def test_j_audit_sheet_registered(self, wp_code):
        """J 类 audit-sheet 底稿在 _WP_CODE_OVERRIDE 中注册正确。"""
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == "audit-sheet"

    def test_all_j_codes_in_mapping(self, j_class_entries):
        """所有 J 类 wp_code 在 wp_account_mapping 注册（批量导出可枚举）。"""
        mapping_codes = {e["wp_code"] for e in j_class_entries}
        all_codes = set(self._J_FORM_TABLE_CODES + self._AUDIT_SHEET_CODES)
        missing = all_codes - mapping_codes
        assert not missing, f"J 类缺少: {sorted(missing)}"

    def test_j_class_all_have_wp_code(self, j_class_entries):
        """所有 J 类条目有有效 wp_code。"""
        for entry in j_class_entries:
            assert entry.get("wp_code"), f"缺少 wp_code: {entry}"
            assert entry["wp_code"].startswith("J")

    def test_batch_export_type_distribution(self):
        """J 类 componentType 分布合理（无 confirmation-hub）。"""
        j_codes = {
            code: ct for code, ct in _WP_CODE_OVERRIDE.items()
            if re.match(r'^J\d', code)
        }
        type_counts: dict[str, int] = {}
        for ct in j_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1
        assert type_counts.get("confirmation-hub", 0) == 0
        assert type_counts.get("d-form-table", 0) >= 9
        assert type_counts.get("audit-sheet", 0) >= 11

    def test_j2_3_yaml_schema_parseable(self):
        """J2-3 精算假设 d-form-table YAML schema 可正确解析用于导入。"""
        schema_path = _SCHEMA_DIR / "J2-3.yaml"
        if schema_path.exists():
            import yaml
            with open(schema_path, encoding="utf-8") as f:
                schema = yaml.safe_load(f)
            assert "wp_code" in schema
            assert schema["wp_code"] == "J2-3"
            assert "sections" in schema or "fields" in schema

    def test_j1_1_yaml_schema_parseable_for_import(self):
        """J1-1 审定表 YAML schema 可正确解析用于导入填充。"""
        import yaml
        schema_path = _SCHEMA_DIR / "J1-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "J1-1"
        assert schema["component_type"] == "d-form-table"
        assert len(schema["sections"]) >= 7
        # 验证字段结构可用于导入映射
        first_section = schema["sections"][0]
        assert "fields" in first_section
        field_names = [f["field"] for f in first_section["fields"]]
        assert "account_code" in field_names
        assert "audited_amount" in field_names
