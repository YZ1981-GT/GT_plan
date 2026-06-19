"""I 类底稿（无形资产循环）完整验证测试。

覆盖:
  P0: 注册完整性（wp_account_mapping + _WP_CODE_OVERRIDE）
  P1: 程序表模板注册（I1A~I6A 共 6 个）
  P2: 审定表 schema（I1-1 YAML）+ handler 正则
  P3: address_registry 坐标注册
  P4: 特殊程序 schema 确认（DCF/摊销/资本化条件/加计扣除）
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
_ADDR_REGISTRY_PATH = _DATA_DIR / "i_address_registry_seed.json"
_SCHEMA_DIR = _DATA_DIR / "ledger_adapters" / "wp_render_schema"


@pytest.fixture(scope="module")
def wp_mapping() -> list[dict]:
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mappings", data) if isinstance(data, dict) else data


@pytest.fixture(scope="module")
def i_class_entries(wp_mapping) -> list[dict]:
    return [e for e in wp_mapping if e.get("cycle") == "I"]


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

    # I 类全部 wp_codes（42 个，不含程序表 I{n}A）
    _ALL_I_CODES = [
        # I1 无形资产
        "I1", "I1-1", "I1-2", "I1-3", "I1-4", "I1-5", "I1-6", "I1-7", "I1-8",
        # I2 开发支出
        "I2", "I2-1", "I2-2", "I2-3", "I2-4", "I2-5", "I2-6",
        # I3 商誉
        "I3", "I3-1", "I3-2", "I3-3", "I3-4", "I3-5", "I3-6",
        # I4 长期待摊费用
        "I4", "I4-1", "I4-2", "I4-3", "I4-4",
        # I5 其他非流动资产
        "I5", "I5-1", "I5-2", "I5-3", "I5-4",
        # I6 研发费用
        "I6", "I6-1", "I6-2", "I6-3", "I6-4", "I6-5", "I6-6", "I6-7", "I6-8",
    ]

    def test_i_class_count(self, i_class_entries):
        """wp_account_mapping.json 中应有 42 个 cycle='I' 的条目。"""
        assert len(i_class_entries) == 42, (
            f"I 类底稿应有 42 条注册，实际 {len(i_class_entries)} 条"
        )

    def test_all_i_codes_in_mapping(self, i_class_entries):
        """所有 I 类 wp_code 在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in i_class_entries}
        missing = set(self._ALL_I_CODES) - mapping_codes
        assert not missing, f"I 类缺少 wp_code: {sorted(missing)}"

    def test_all_i_codes_have_override(self):
        """所有 42 个 I 类 wp_code 在 _WP_CODE_OVERRIDE 中有 componentType 映射。"""
        for code in self._ALL_I_CODES:
            assert code in _WP_CODE_OVERRIDE, (
                f"I 类 wp_code '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )

    def test_override_count_matches_mapping(self, i_class_entries):
        """_WP_CODE_OVERRIDE 中 I 类条目数 == wp_account_mapping I 类条目数。"""
        override_i_count = sum(1 for code in _WP_CODE_OVERRIDE if re.match(r'^I\d', code))
        assert override_i_count == len(i_class_entries), (
            f"_WP_CODE_OVERRIDE I 类 {override_i_count} 条 != "
            f"wp_account_mapping I 类 {len(i_class_entries)} 条"
        )

    def test_no_i0_confirmation_hub(self):
        """I 类无函证组（无 I0 ConfirmationHub）。"""
        assert "I0" not in _WP_CODE_OVERRIDE

    def test_all_component_types_valid(self, i_class_entries):
        """所有 I 类 componentType 必须是合法类型。"""
        valid_types = {"d-form-table", "audit-sheet"}
        for entry in i_class_entries:
            wp_code = entry["wp_code"]
            ct = _WP_CODE_OVERRIDE.get(wp_code, "")
            assert ct in valid_types, (
                f"I 类 '{wp_code}' componentType '{ct}' 不合法"
            )

    def test_type_distribution(self):
        """I 类 componentType 分布符合预期。"""
        i_codes = {
            code: ct for code, ct in _WP_CODE_OVERRIDE.items()
            if re.match(r'^I\d', code)
        }
        type_counts: dict[str, int] = {}
        for ct in i_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1
        # I 类无 confirmation-hub
        assert type_counts.get("confirmation-hub", 0) == 0
        assert type_counts.get("d-form-table", 0) >= 18
        assert type_counts.get("audit-sheet", 0) >= 18

    @pytest.mark.parametrize("wp_code", [
        "I1-1", "I2-1", "I3-1", "I4-1", "I5-1", "I6-1",
    ])
    def test_audit_determination_tables_are_d_form(self, wp_code):
        """I{n}-1 审定表映射为 d-form-table。"""
        assert _WP_CODE_OVERRIDE.get(wp_code) == "d-form-table"

    def test_i1_is_primary(self, i_class_entries):
        """I1 无形资产标记 is_primary。"""
        i1 = next((e for e in i_class_entries if e["wp_code"] == "I1"), None)
        assert i1 is not None
        assert i1.get("is_primary") is True

    def test_i6_is_primary(self, i_class_entries):
        """I6 研发费用标记 is_primary。"""
        i6 = next((e for e in i_class_entries if e["wp_code"] == "I6"), None)
        assert i6 is not None
        assert i6.get("is_primary") is True


# ═══════════════════════════════════════════════════════════════════════════════
# P1: 程序表模板
# ═══════════════════════════════════════════════════════════════════════════════


class TestP1ProcedureTables:
    """P1 Tasks 5-12: 程序表模板注册验证。"""

    _EXPECTED_TABLES = ["I1A", "I2A", "I3A", "I4A", "I5A", "I6A"]

    def test_all_6_procedure_tables_registered(self, procedure_templates):
        """I1A~I6A 共 6 个程序表全部注册。"""
        for table_id in self._EXPECTED_TABLES:
            assert table_id in procedure_templates, (
                f"程序表 '{table_id}' 未注册到 procedure_table_templates.json"
            )

    @pytest.mark.parametrize("table_id", ["I1A", "I2A", "I3A", "I4A", "I5A", "I6A"])
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

    def test_i3a_has_dcf_steps(self, procedure_templates):
        """I3A 商誉程序表包含 DCF/敏感性分析步骤。"""
        items = procedure_templates["I3A"]["items"]
        contents = " ".join(item["content"] for item in items)
        assert "DCF" in contents or "现金流折现" in contents
        assert "敏感性" in contents

    def test_i6a_has_super_deduction_step(self, procedure_templates):
        """I6A 研发费用程序表包含加计扣除步骤。"""
        items = procedure_templates["I6A"]["items"]
        contents = " ".join(item["content"] for item in items)
        assert "加计扣除" in contents


# ═══════════════════════════════════════════════════════════════════════════════
# P2: 审定表 + 回写联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestP2AuditDetermination:
    """P2 Tasks 13-16: 审定表 schema + handler 正则。"""

    _AUDIT_DET_CODES = ["I1-1", "I2-1", "I3-1", "I4-1", "I5-1", "I6-1"]

    def test_handler_regex_covers_i_class(self):
        """handler 正则 ^[D-N]\\d+-1$ 匹配所有 I 审定表。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        for code in self._AUDIT_DET_CODES:
            assert pattern.match(code), f"正则不匹配 {code}"

    def test_i1_1_schema_exists(self):
        """I1-1 特殊 YAML schema 文件存在。"""
        schema_path = _SCHEMA_DIR / "I1-1.yaml"
        assert schema_path.exists(), f"I1-1 schema 不存在: {schema_path}"

    def test_i1_1_schema_has_category_sections(self):
        """I1-1 schema 包含无形资产类别分组。"""
        import yaml
        schema_path = _SCHEMA_DIR / "I1-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        section_names = [s["name"] for s in schema["sections"]]
        assert "土地使用权" in section_names
        assert "软件" in section_names
        assert "专利权" in section_names
        assert "特许经营权" in section_names

    def test_i1_1_has_deduction_rows(self):
        """I1-1 schema 包含累计摊销+减值准备扣减行+净额行。"""
        import yaml
        schema_path = _SCHEMA_DIR / "I1-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        section_names = [s["name"] for s in schema["sections"]]
        assert "减：累计摊销" in section_names
        assert "减：无形资产减值准备" in section_names
        assert "无形资产净额" in section_names

    def test_i1_1_has_writeback_config(self):
        """I1-1 schema 包含 writeback 配置。"""
        import yaml
        schema_path = _SCHEMA_DIR / "I1-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert "writeback" in schema
        assert schema["writeback"]["target"] == "trial_balance.audited_amount"

    @pytest.mark.parametrize("wp_code", _AUDIT_DET_CODES)
    def test_audit_det_component_type(self, wp_code):
        """所有 6 个审定表为 d-form-table。"""
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table"


# ═══════════════════════════════════════════════════════════════════════════════
# P3: address_registry 坐标
# ═══════════════════════════════════════════════════════════════════════════════


class TestP3AddressRegistry:
    """P3 Tasks 17-21: address_registry 坐标注册。"""

    def test_seed_file_exists(self):
        """i_address_registry_seed.json 存在。"""
        assert _ADDR_REGISTRY_PATH.exists()

    def test_seed_has_entries(self, addr_registry):
        """seed 有 entries 数组。"""
        assert "entries" in addr_registry
        assert len(addr_registry["entries"]) >= 8

    def test_seed_cycle_is_i(self, addr_registry):
        """seed cycle 标识为 I。"""
        assert addr_registry.get("cycle") == "I"

    def test_i1_3_amortization_coordinates(self, addr_registry):
        """I1-3 摊销测算坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "I1-3" in codes

    def test_i3_4_dcf_coordinates(self, addr_registry):
        """I3-4 DCF计算坐标已注册（含WACC/NPV）。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "I3-4" in codes
        # 验证 DCF 坐标含关键项
        i3_4 = next(e for e in addr_registry["entries"] if e["wp_code"] == "I3-4")
        purposes = {c["purpose"] for c in i3_4["coordinates"]}
        assert "wacc" in purposes
        assert "npv_enterprise_value" in purposes
        assert "recoverable_amount" in purposes

    def test_i3_5_sensitivity_coordinates(self, addr_registry):
        """I3-5 敏感性分析坐标已注册（含矩阵）。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "I3-5" in codes
        i3_5 = next(e for e in addr_registry["entries"] if e["wp_code"] == "I3-5")
        purposes = {c["purpose"] for c in i3_5["coordinates"]}
        assert "base_discount_rate" in purposes
        assert "matrix_center" in purposes

    def test_i6_7_super_deduction_coordinates(self, addr_registry):
        """I6-7 研发加计扣除坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "I6-7" in codes
        i6_7 = next(e for e in addr_registry["entries"] if e["wp_code"] == "I6-7")
        purposes = {c["purpose"] for c in i6_7["coordinates"]}
        assert "super_deduction_amount" in purposes
        assert "qualifying_rd_expense" in purposes

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
    """P4 Tasks 22-28: 特殊程序 schema 确认。"""

    def test_i1_3_amortization_is_audit_sheet(self):
        """I1-3 摊销测算走 audit-sheet（直线法/产量法含公式）。"""
        assert _WP_CODE_OVERRIDE["I1-3"] == "audit-sheet"

    def test_i3_4_dcf_is_audit_sheet(self):
        """I3-4 DCF计算走 audit-sheet（WACC/CAPM/FCF/TV/NPV复杂公式）。"""
        assert _WP_CODE_OVERRIDE["I3-4"] == "audit-sheet"

    def test_i3_5_sensitivity_is_audit_sheet(self):
        """I3-5 敏感性分析走 audit-sheet（折现率/增长率矩阵含公式）。"""
        assert _WP_CODE_OVERRIDE["I3-5"] == "audit-sheet"

    def test_i2_3_capitalization_is_d_form_table(self):
        """I2-3 资本化条件检查走 d-form-table（CAS6五条件结构化检查）。"""
        assert _WP_CODE_OVERRIDE["I2-3"] == "d-form-table"

    def test_i6_3_classification_is_d_form_table(self):
        """I6-3 资本化/费用化分类走 d-form-table（结构化判断）。"""
        assert _WP_CODE_OVERRIDE["I6-3"] == "d-form-table"

    def test_i6_7_super_deduction_is_audit_sheet(self):
        """I6-7 加计扣除测算走 audit-sheet（税法公式含公式）。"""
        assert _WP_CODE_OVERRIDE["I6-7"] == "audit-sheet"

    def test_i3_3_impairment_summary_is_d_form_table(self):
        """I3-3 减值测试概要走 d-form-table（概要结构化表）。"""
        assert _WP_CODE_OVERRIDE["I3-3"] == "d-form-table"

    def test_i1_4_impairment_is_audit_sheet(self):
        """I1-4 无形资产减值测试走 audit-sheet。"""
        assert _WP_CODE_OVERRIDE["I1-4"] == "audit-sheet"

    def test_i4_3_amortization_check_is_audit_sheet(self):
        """I4-3 长期待摊费用摊销检查走 audit-sheet。"""
        assert _WP_CODE_OVERRIDE["I4-3"] == "audit-sheet"

    def test_all_i_class_routes_no_missing(self):
        """I 全系列在 _WP_CODE_OVERRIDE 中无遗漏（componentType 路由无 404）。"""
        i_codes = [code for code in _WP_CODE_OVERRIDE if re.match(r'^I\d', code)]
        assert len(i_codes) == 42, f"应有 42 个 I 类映射，实际 {len(i_codes)}"


# ═══════════════════════════════════════════════════════════════════════════════
# P5: 联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestP5Linkage:
    """P5 Tasks 29-31: 联动绑定验证。"""

    def test_risk_for_cycle_in_procedure_tables(self, procedure_templates):
        """I{n}A 程序表引用 risk_for_cycle。"""
        tables_with_risk = []
        for key in procedure_templates:
            if key.startswith("I") and key.endswith("A"):
                items = procedure_templates[key].get("items", [])
                for item in items:
                    if item.get("auto_data_source") == "risk_for_cycle":
                        tables_with_risk.append(key)
                        break
        # 所有 6 个程序表引用 risk
        assert len(tables_with_risk) == 6

    def test_control_test_in_procedure_tables(self, procedure_templates):
        """部分程序表引用 control_test_result_for_cycle。"""
        tables_with_control = []
        for key in procedure_templates:
            if key.startswith("I") and key.endswith("A"):
                items = procedure_templates[key].get("items", [])
                for item in items:
                    if item.get("auto_data_source") == "control_test_result_for_cycle":
                        tables_with_control.append(key)
                        break
        assert len(tables_with_control) >= 5

    def test_i3_4_dcf_ref_in_procedure(self, procedure_templates):
        """I3A 程序表引用 I3-4（DCF计算联动）。"""
        items = procedure_templates["I3A"]["items"]
        refs = " ".join(item.get("ref_index", "") or "" for item in items)
        assert "I3-4" in refs, "I3A 应有 I3-4 引用（DCF计算）"

    def test_i6_7_ref_in_procedure(self, procedure_templates):
        """I6A 程序表引用 I6-7（加计扣除联动）。"""
        items = procedure_templates["I6A"]["items"]
        refs = " ".join(item.get("ref_index", "") or "" for item in items)
        assert "I6-7" in refs, "I6A 应有 I6-7 引用（加计扣除）"

    def test_i2a_i1_cross_ref(self, procedure_templates):
        """I2A 程序表引用 I1（开发支出→无形资产联动）。"""
        items = procedure_templates["I2A"]["items"]
        refs = " ".join(item.get("ref_index", "") or "" for item in items)
        assert "I1" in refs, "I2A 应有 I1 引用（转入无形资产联动）"


# ═══════════════════════════════════════════════════════════════════════════════
# P6: 导入导出
# ═══════════════════════════════════════════════════════════════════════════════


class TestP6ExportImport:
    """P6 Tasks 32-35: 导入导出基础设施验证。"""

    # I 类 d-form-table wp_codes
    _I_FORM_TABLE_CODES = [
        "I1", "I1-1", "I1-8",
        "I2", "I2-1", "I2-3", "I2-6",
        "I3", "I3-1", "I3-3", "I3-6",
        "I4", "I4-1", "I4-4",
        "I5", "I5-1", "I5-4",
        "I6", "I6-1", "I6-3", "I6-8",
    ]

    # I 类 audit-sheet wp_codes
    _AUDIT_SHEET_CODES = [
        "I1-2", "I1-3", "I1-4", "I1-5", "I1-6", "I1-7",
        "I2-2", "I2-4", "I2-5",
        "I3-2", "I3-4", "I3-5",
        "I4-2", "I4-3",
        "I5-2", "I5-3",
        "I6-2", "I6-4", "I6-5", "I6-6", "I6-7",
    ]

    @pytest.mark.parametrize("wp_code", _I_FORM_TABLE_CODES)
    def test_i_form_table_registered(self, wp_code):
        """I 类 d-form-table 底稿在 _WP_CODE_OVERRIDE 中注册正确。"""
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table"

    @pytest.mark.parametrize("wp_code", _AUDIT_SHEET_CODES)
    def test_i_audit_sheet_registered(self, wp_code):
        """I 类 audit-sheet 底稿在 _WP_CODE_OVERRIDE 中注册正确。"""
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == "audit-sheet"

    def test_all_i_codes_in_mapping(self, i_class_entries):
        """所有 I 类 wp_code 在 wp_account_mapping 注册（批量导出可枚举）。"""
        mapping_codes = {e["wp_code"] for e in i_class_entries}
        all_codes = set(self._I_FORM_TABLE_CODES + self._AUDIT_SHEET_CODES)
        missing = all_codes - mapping_codes
        assert not missing, f"I 类缺少: {sorted(missing)}"

    def test_i_class_all_have_wp_code(self, i_class_entries):
        """所有 I 类条目有有效 wp_code。"""
        for entry in i_class_entries:
            assert entry.get("wp_code"), f"缺少 wp_code: {entry}"
            assert entry["wp_code"].startswith("I")

    def test_batch_export_type_distribution(self):
        """I 类 componentType 分布合理（无 confirmation-hub）。"""
        i_codes = {
            code: ct for code, ct in _WP_CODE_OVERRIDE.items()
            if re.match(r'^I\d', code)
        }
        type_counts: dict[str, int] = {}
        for ct in i_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1
        assert type_counts.get("confirmation-hub", 0) == 0
        assert type_counts.get("d-form-table", 0) >= 18
        assert type_counts.get("audit-sheet", 0) >= 18
