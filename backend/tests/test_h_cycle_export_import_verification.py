"""H 类底稿（固定资产循环）完整验证测试。

覆盖:
  P0: 注册完整性（wp_account_mapping + _WP_CODE_OVERRIDE + confirmation-hub）
  P1: 程序表模板注册（H0A~H10A 共 11 个）
  P2: 审定表 schema（H1-1 YAML）+ handler 正则
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
_ADDR_REGISTRY_PATH = _DATA_DIR / "h_address_registry_seed.json"
_SCHEMA_DIR = _DATA_DIR / "ledger_adapters" / "wp_render_schema"


@pytest.fixture(scope="module")
def wp_mapping() -> list[dict]:
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mappings", data) if isinstance(data, dict) else data


@pytest.fixture(scope="module")
def h_class_entries(wp_mapping) -> list[dict]:
    return [e for e in wp_mapping if e.get("cycle") == "H"]


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
    """P0 Tasks 1-5: wp_account_mapping + _WP_CODE_OVERRIDE 完整性。"""

    # H 类全部 wp_codes（68 个，不含程序表 H{n}A）
    _ALL_H_CODES = [
        # H0 函证
        "H0", "H0-1", "H0-2", "H0-3", "H0-4", "H0-5",
        # H1 固定资产
        "H1", "H1-1", "H1-2", "H1-3", "H1-4", "H1-5", "H1-6", "H1-7", "H1-8",
        # H2 在建工程
        "H2", "H2-1", "H2-2", "H2-3", "H2-4", "H2-5", "H2-6",
        # H3 投资性房地产
        "H3", "H3-1", "H3-2", "H3-3", "H3-4", "H3-5", "H3-6",
        # H4 工程物资
        "H4", "H4-1", "H4-2", "H4-3", "H4-4",
        # H5 油气资产
        "H5", "H5-1", "H5-2", "H5-3", "H5-4",
        # H6 固定资产清理
        "H6", "H6-1", "H6-2", "H6-3", "H6-4",
        # H7 生产性生物资产
        "H7", "H7-1", "H7-2", "H7-3", "H7-4",
        # H8 使用权资产
        "H8", "H8-1", "H8-2", "H8-3", "H8-4", "H8-5", "H8-6",
        # H9 租赁负债
        "H9", "H9-1", "H9-2", "H9-3", "H9-4", "H9-5", "H9-6",
        # H10 资产处置损益
        "H10", "H10-1", "H10-2", "H10-3", "H10-4",
    ]

    def test_h_class_count(self, h_class_entries):
        """wp_account_mapping.json 中应有 68 个 cycle='H' 的条目。"""
        assert len(h_class_entries) == 68, (
            f"H 类底稿应有 68 条注册，实际 {len(h_class_entries)} 条"
        )

    def test_all_h_codes_in_mapping(self, h_class_entries):
        """所有 H 类 wp_code 在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in h_class_entries}
        missing = set(self._ALL_H_CODES) - mapping_codes
        assert not missing, f"H 类缺少 wp_code: {sorted(missing)}"

    def test_all_h_codes_have_override(self):
        """所有 68 个 H 类 wp_code 在 _WP_CODE_OVERRIDE 中有 componentType 映射。"""
        for code in self._ALL_H_CODES:
            assert code in _WP_CODE_OVERRIDE, (
                f"H 类 wp_code '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )

    def test_override_count_matches_mapping(self, h_class_entries):
        """_WP_CODE_OVERRIDE 中 H 类条目数 == wp_account_mapping H 类条目数。"""
        override_h_count = sum(1 for code in _WP_CODE_OVERRIDE if code.startswith("H"))
        assert override_h_count == len(h_class_entries), (
            f"_WP_CODE_OVERRIDE H 类 {override_h_count} 条 != "
            f"wp_account_mapping H 类 {len(h_class_entries)} 条"
        )

    def test_h0_is_confirmation_hub(self):
        """H0 函证底稿映射为 confirmation-hub。"""
        assert _WP_CODE_OVERRIDE.get("H0") == "confirmation-hub"

    def test_h0_consistent_with_d0_e0_f0_g0(self):
        """H0/G0/D0/E0/F0 使用相同 confirmation-hub 模式。"""
        for code in ["H0", "G0", "D0", "E0", "F0"]:
            assert _WP_CODE_OVERRIDE.get(code) == "confirmation-hub"

    def test_confirmation_hub_valid_type(self):
        """confirmation-hub 是合法的 componentType。"""
        assert "confirmation-hub" in VALID_COMPONENT_TYPES

    def test_all_component_types_valid(self, h_class_entries):
        """所有 H 类 componentType 必须是合法类型。"""
        valid_types = {
            "d-form-table", "audit-sheet", "a-program-console",
            "confirmation-hub", "c-note-table",
            # 已迁移为专属组件的 H 类
            "h1-fixed-assets", "h2-construction-in-progress",
            "h3-investment-property", "h4-engineering-materials",
            "h10-asset-disposal-income",
            # 函证组件
            "confirmation-summary", "confirmation-entity-verify",
            "confirmation-followup", "confirmation-diff-reconcile",
            "confirmation-alternative-h05", "confirmation-diff-checklist",
            "confirmation-fraud-risk", "confirmation-reliability",
        }
        for entry in h_class_entries:
            wp_code = entry["wp_code"]
            ct = _WP_CODE_OVERRIDE.get(wp_code, "")
            assert ct in valid_types, (
                f"H 类 '{wp_code}' componentType '{ct}' 不合法"
            )

    def test_type_distribution(self):
        """H 类 componentType 分布符合预期。"""
        h_codes = {
            code: ct for code, ct in _WP_CODE_OVERRIDE.items()
            if code.startswith("H")
        }
        type_counts: dict[str, int] = {}
        for ct in h_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1
        assert type_counts.get("confirmation-hub", 0) == 1
        assert type_counts.get("d-form-table", 0) >= 25
        assert type_counts.get("audit-sheet", 0) >= 30

    @pytest.mark.parametrize("wp_code", [
        "H1-1", "H2-1", "H3-1", "H4-1", "H5-1", "H6-1", "H7-1",
        "H8-1", "H9-1", "H10-1",
    ])
    def test_audit_determination_tables_are_d_form(self, wp_code):
        """H{n}-1 审定表映射为 d-form-table 或已迁移到专属组件。"""
        # 已迁移为专属组件的底稿不再走 d-form-table
        _MIGRATED_TO_DEDICATED = {
            "H1-1": "h1-fixed-assets",
            "H2-1": "h2-construction-in-progress",
            "H3-1": "h3-investment-property",
            "H10-1": "h10-asset-disposal-income",
        }
        if wp_code in _MIGRATED_TO_DEDICATED:
            assert _WP_CODE_OVERRIDE.get(wp_code) == _MIGRATED_TO_DEDICATED[wp_code]
        else:
            assert _WP_CODE_OVERRIDE.get(wp_code) == "d-form-table"

    def test_h5_applicable_when(self, h_class_entries):
        """H5 油气资产带 applicable_when 行业限制。"""
        h5_entries = [e for e in h_class_entries if e["wp_code"].startswith("H5")]
        for entry in h5_entries:
            assert "applicable_when" in entry, (
                f"{entry['wp_code']} 缺少 applicable_when"
            )
            assert "oil_gas" in entry["applicable_when"]["industry"]

    def test_h7_applicable_when(self, h_class_entries):
        """H7 生产性生物资产带 applicable_when 行业限制。"""
        h7_entries = [e for e in h_class_entries if e["wp_code"].startswith("H7")]
        for entry in h7_entries:
            assert "applicable_when" in entry, (
                f"{entry['wp_code']} 缺少 applicable_when"
            )
            assert "agriculture" in entry["applicable_when"]["industry"]


# ═══════════════════════════════════════════════════════════════════════════════
# P1: 程序表模板
# ═══════════════════════════════════════════════════════════════════════════════


class TestP1ProcedureTables:
    """P1 Tasks 6-18: 程序表模板注册验证。"""

    _EXPECTED_TABLES = [
        "H0A", "H1A", "H2A", "H3A", "H4A", "H5A", "H6A", "H7A",
        "H8A", "H9A", "H10A",
    ]

    def test_all_11_procedure_tables_registered(self, procedure_templates):
        """H0A~H10A 共 11 个程序表全部注册。"""
        for table_id in self._EXPECTED_TABLES:
            assert table_id in procedure_templates, (
                f"程序表 '{table_id}' 未注册到 procedure_table_templates.json"
            )

    @pytest.mark.parametrize("table_id", [
        "H0A", "H1A", "H2A", "H3A", "H4A", "H5A", "H6A", "H7A",
        "H8A", "H9A", "H10A",
    ])
    def test_procedure_table_has_items(self, procedure_templates, table_id):
        """每个程序表有 items 且步骤数 >= 4。"""
        table = procedure_templates[table_id]
        assert "items" in table, f"{table_id} 缺少 items"
        assert len(table["items"]) >= 4, (
            f"{table_id} 步骤数 {len(table['items'])} < 4"
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

    def test_h0a_has_confirmation_auto_source(self, procedure_templates):
        """H0A 函证程序表应有 confirmation_summary_for_cycle 数据源。"""
        items = procedure_templates["H0A"]["items"]
        sources = [item.get("auto_data_source") for item in items]
        assert "confirmation_summary_for_cycle" in sources

    def test_procedure_tables_have_risk_source(self, procedure_templates):
        """所有程序表 seq1 应引用 risk_for_cycle 或 confirmation_summary。"""
        for table_id in self._EXPECTED_TABLES:
            first_item = procedure_templates[table_id]["items"][0]
            assert first_item.get("auto_data_source") in (
                "risk_for_cycle", "confirmation_summary_for_cycle"
            ), f"{table_id} seq1 未引用 risk/confirmation 数据源"


# ═══════════════════════════════════════════════════════════════════════════════
# P2: 审定表 + 回写联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestP2AuditDetermination:
    """P2 Tasks 19-22: 审定表 schema + handler 正则。"""

    _AUDIT_DET_CODES = [
        "H1-1", "H2-1", "H3-1", "H4-1", "H5-1", "H6-1", "H7-1",
        "H8-1", "H9-1", "H10-1",
    ]

    def test_handler_regex_covers_h_class(self):
        """handler 正则 ^[D-N]\\d+-1$ 匹配所有 H 审定表。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        for code in self._AUDIT_DET_CODES:
            assert pattern.match(code), f"正则不匹配 {code}"

    def test_h1_1_schema_exists(self):
        """H1-1 特殊 YAML schema 文件存在。"""
        schema_path = _SCHEMA_DIR / "H1-1.yaml"
        assert schema_path.exists(), f"H1-1 schema 不存在: {schema_path}"

    def test_h1_1_schema_has_category_sections(self):
        """H1-1 schema 包含资产类别分组。"""
        import yaml
        schema_path = _SCHEMA_DIR / "H1-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        section_names = [s["name"] for s in schema["sections"]]
        assert "房屋及建筑物" in section_names
        assert "机器设备" in section_names
        assert "运输工具" in section_names
        assert "电子设备" in section_names

    def test_h1_1_has_deduction_rows(self):
        """H1-1 schema 包含累计折旧+减值准备扣减行+净额行。"""
        import yaml
        schema_path = _SCHEMA_DIR / "H1-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        section_names = [s["name"] for s in schema["sections"]]
        assert "减：累计折旧" in section_names
        assert "减：固定资产减值准备" in section_names
        assert "固定资产净额" in section_names

    def test_h1_1_has_writeback_config(self):
        """H1-1 schema 包含 writeback 配置。"""
        import yaml
        schema_path = _SCHEMA_DIR / "H1-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert "writeback" in schema
        assert schema["writeback"]["target"] == "trial_balance.audited_amount"

    @pytest.mark.parametrize("wp_code", _AUDIT_DET_CODES)
    def test_audit_det_component_type(self, wp_code):
        """所有 10 个审定表为 d-form-table 或已迁移到专属组件。"""
        _MIGRATED_TO_DEDICATED = {
            "H1-1": "h1-fixed-assets",
            "H2-1": "h2-construction-in-progress",
            "H3-1": "h3-investment-property",
            "H10-1": "h10-asset-disposal-income",
        }
        if wp_code in _MIGRATED_TO_DEDICATED:
            assert _WP_CODE_OVERRIDE[wp_code] == _MIGRATED_TO_DEDICATED[wp_code]
        else:
            assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table"


# ═══════════════════════════════════════════════════════════════════════════════
# P3: address_registry 坐标
# ═══════════════════════════════════════════════════════════════════════════════


class TestP3AddressRegistry:
    """P3 Tasks 23-28: address_registry 坐标注册。"""

    def test_seed_file_exists(self):
        """h_address_registry_seed.json 存在。"""
        assert _ADDR_REGISTRY_PATH.exists()

    def test_seed_has_entries(self, addr_registry):
        """seed 有 entries 数组。"""
        assert "entries" in addr_registry
        assert len(addr_registry["entries"]) >= 10

    def test_seed_cycle_is_h(self, addr_registry):
        """seed cycle 标识为 H。"""
        assert addr_registry.get("cycle") == "H"

    def test_h1_3_depreciation_coordinates(self, addr_registry):
        """H1-3 折旧测算坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "H1-3" in codes

    def test_h2_3_interest_capitalization_coordinates(self, addr_registry):
        """H2-3 利息资本化坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "H2-3" in codes

    def test_h8_h9_cas21_coordinates(self, addr_registry):
        """H8-4/H9-3/H9-4 CAS21 租赁相关坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "H8-4" in codes
        assert "H9-3" in codes
        assert "H9-4" in codes

    def test_h3_3_fair_value_coordinates(self, addr_registry):
        """H3-3 投资性房地产公允价值坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "H3-3" in codes

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
    """P4 Tasks 29-34: 特殊程序 schema 确认。"""

    def test_h1_3_depreciation_is_audit_sheet(self):
        """H1-3 折旧测算走 h1-fixed-assets 专属组件（已从 audit-sheet 迁移）。"""
        assert _WP_CODE_OVERRIDE["H1-3"] == "h1-fixed-assets"

    def test_h1_5_impairment_is_audit_sheet(self):
        """H1-5 减值测试走 h1-fixed-assets 专属组件（已从 audit-sheet 迁移）。"""
        assert _WP_CODE_OVERRIDE["H1-5"] == "h1-fixed-assets"

    def test_h2_3_interest_capitalization_is_audit_sheet(self):
        """H2-3 利息资本化测算走 h2-construction-in-progress 专属组件（已从 audit-sheet 迁移）。"""
        assert _WP_CODE_OVERRIDE["H2-3"] == "h2-construction-in-progress"

    def test_h3_3_fair_value_is_audit_sheet(self):
        """H3-3 公允价值测试走 h3-investment-property 专属组件（已从 audit-sheet 迁移）。"""
        assert _WP_CODE_OVERRIDE["H3-3"] == "h3-investment-property"

    def test_h8_cas21_sheets_are_audit_sheet(self):
        """H8-3/H8-4/H8-5 使用权资产 CAS21 相关全部走 audit-sheet。"""
        cas21_h8_codes = ["H8-3", "H8-4", "H8-5"]
        for code in cas21_h8_codes:
            assert _WP_CODE_OVERRIDE[code] == "audit-sheet", (
                f"{code} 应为 audit-sheet，实际为 {_WP_CODE_OVERRIDE[code]}"
            )

    def test_h9_cas21_sheets_are_audit_sheet(self):
        """H9-3/H9-4 租赁负债 CAS21 相关全部走 audit-sheet。"""
        cas21_h9_codes = ["H9-3", "H9-4"]
        for code in cas21_h9_codes:
            assert _WP_CODE_OVERRIDE[code] == "audit-sheet", (
                f"{code} 应为 audit-sheet，实际为 {_WP_CODE_OVERRIDE[code]}"
            )

    def test_h5_h7_industry_specific_components(self):
        """H5/H7 行业特殊科目的 componentType 正确。"""
        assert _WP_CODE_OVERRIDE["H5"] == "d-form-table"
        assert _WP_CODE_OVERRIDE["H5-3"] == "audit-sheet"
        assert _WP_CODE_OVERRIDE["H7"] == "d-form-table"
        assert _WP_CODE_OVERRIDE["H7-3"] == "audit-sheet"

    def test_all_h_class_routes_no_missing(self):
        """H 全系列在 _WP_CODE_OVERRIDE 中无遗漏（componentType 路由无 404）。"""
        h_codes = [code for code in _WP_CODE_OVERRIDE if code.startswith("H") and not code.startswith("H-")]
        # 过滤掉 h-static-doc 的 "H-" 前缀
        h_codes = [c for c in h_codes if re.match(r'^H\d', c)]
        assert len(h_codes) == 68, f"应有 68 个 H 类映射，实际 {len(h_codes)}"


# ═══════════════════════════════════════════════════════════════════════════════
# P5: 联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestP5Linkage:
    """P5 Tasks 35-38: 联动绑定验证。"""

    def test_risk_for_cycle_in_procedure_tables(self, procedure_templates):
        """H{n}A 程序表引用 risk_for_cycle。"""
        tables_with_risk = []
        for key in procedure_templates:
            if key.startswith("H") and key.endswith("A"):
                items = procedure_templates[key].get("items", [])
                for item in items:
                    if item.get("auto_data_source") == "risk_for_cycle":
                        tables_with_risk.append(key)
                        break
        # 所有 11 个程序表中至少 10 个（H0A 用 confirmation_summary）引用 risk
        assert len(tables_with_risk) >= 10

    def test_control_test_in_procedure_tables(self, procedure_templates):
        """部分程序表引用 control_test_result_for_cycle。"""
        tables_with_control = []
        for key in procedure_templates:
            if key.startswith("H") and key.endswith("A"):
                items = procedure_templates[key].get("items", [])
                for item in items:
                    if item.get("auto_data_source") == "control_test_result_for_cycle":
                        tables_with_control.append(key)
                        break
        assert len(tables_with_control) >= 5

    def test_h0_confirmation_hub_route(self):
        """H0 → ConfirmationHub 路由已配置。"""
        assert _WP_CODE_OVERRIDE["H0"] == "confirmation-hub"

    def test_h8_h9_cross_ref_in_procedure(self, procedure_templates):
        """H8A 程序表引用 H9（使用权资产↔租赁负债 CAS21 联动）。"""
        items = procedure_templates["H8A"]["items"]
        refs = " ".join(item.get("ref_index", "") or "" for item in items)
        assert "H9" in refs, "H8A 应有 H9 引用（CAS21 租赁联动）"

    def test_h10_h6_cross_ref_in_procedure(self, procedure_templates):
        """H10A 程序表引用 H6（资产处置损益↔固定资产清理联动）。"""
        items = procedure_templates["H10A"]["items"]
        refs = " ".join(item.get("ref_index", "") or "" for item in items)
        assert "H6" in refs, "H10A 应有 H6 引用（处置损益联动清理）"


# ═══════════════════════════════════════════════════════════════════════════════
# P6: 导入导出
# ═══════════════════════════════════════════════════════════════════════════════


class TestP6ExportImport:
    """P6 Tasks 39-46: 导入导出基础设施验证。"""

    # H 类 d-form-table wp_codes（排除已迁移到专属组件的：H1/H2/H3/H10，排除H0函证）
    _H_FORM_TABLE_CODES = [
        "H4", "H4-1", "H4-4",
        "H5", "H5-1", "H5-4",
        "H6", "H6-1", "H6-4",
        "H7", "H7-1", "H7-4",
        "H8", "H8-1", "H8-6",
        "H9", "H9-1", "H9-6",
    ]

    # H 类 audit-sheet wp_codes（排除已迁移到专属组件的：H1/H2/H3/H10）
    _AUDIT_SHEET_CODES = [
        "H4-2", "H4-3",
        "H5-2", "H5-3",
        "H6-2", "H6-3",
        "H7-2", "H7-3",
        "H8-2", "H8-3", "H8-4", "H8-5",
        "H9-2", "H9-3", "H9-4", "H9-5",
    ]

    # 已迁移到专属组件的 H 类 codes
    _H_DEDICATED_CODES = {
        "H1": "h1-fixed-assets", "H1-1": "h1-fixed-assets", "H1-8": "h1-fixed-assets",
        "H1-2": "h1-fixed-assets", "H1-3": "h1-fixed-assets", "H1-4": "h1-fixed-assets",
        "H1-5": "h1-fixed-assets", "H1-6": "h1-fixed-assets", "H1-7": "h1-fixed-assets",
        "H2": "h2-construction-in-progress", "H2-1": "h2-construction-in-progress",
        "H2-6": "h2-construction-in-progress",
        "H2-2": "h2-construction-in-progress", "H2-3": "h2-construction-in-progress",
        "H2-4": "h2-construction-in-progress", "H2-5": "h2-construction-in-progress",
        "H3": "h3-investment-property", "H3-1": "h3-investment-property",
        "H3-6": "h3-investment-property",
        "H3-2": "h3-investment-property", "H3-3": "h3-investment-property",
        "H3-4": "h3-investment-property", "H3-5": "h3-investment-property",
        "H10": "h10-asset-disposal-income", "H10-1": "h10-asset-disposal-income",
        "H10-4": "h10-asset-disposal-income",
        "H10-2": "h10-asset-disposal-income", "H10-3": "h10-asset-disposal-income",
    }

    @pytest.mark.parametrize("wp_code", _H_FORM_TABLE_CODES)
    def test_h_form_table_registered(self, wp_code):
        """H 类 d-form-table 底稿在 _WP_CODE_OVERRIDE 中注册正确。"""
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table"

    @pytest.mark.parametrize("wp_code", _AUDIT_SHEET_CODES)
    def test_h_audit_sheet_registered(self, wp_code):
        """H 类 audit-sheet 底稿在 _WP_CODE_OVERRIDE 中注册正确。"""
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == "audit-sheet"

    @pytest.mark.parametrize("wp_code,expected_ct", list(_H_DEDICATED_CODES.items()))
    def test_h_dedicated_registered(self, wp_code, expected_ct):
        """已迁移到专属组件的 H 类底稿在 _WP_CODE_OVERRIDE 中注册正确。"""
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == expected_ct

    def test_all_h_codes_in_mapping(self, h_class_entries):
        """所有 H 类 wp_code 在 wp_account_mapping 注册（批量导出可枚举）。"""
        mapping_codes = {e["wp_code"] for e in h_class_entries}
        all_codes = set(
            self._H_FORM_TABLE_CODES
            + self._AUDIT_SHEET_CODES
            + list(self._H_DEDICATED_CODES.keys())
            + ["H0"]
        )
        missing = all_codes - mapping_codes
        assert not missing, f"H 类缺少: {sorted(missing)}"

    def test_h_class_all_have_wp_code(self, h_class_entries):
        """所有 H 类条目有有效 wp_code。"""
        for entry in h_class_entries:
            assert entry.get("wp_code"), f"缺少 wp_code: {entry}"
            assert entry["wp_code"].startswith("H")

    def test_batch_export_type_distribution(self):
        """H 类 componentType 分布合理。"""
        h_codes = {
            code: ct for code, ct in _WP_CODE_OVERRIDE.items()
            if re.match(r'^H\d', code)
        }
        type_counts: dict[str, int] = {}
        for ct in h_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1
        assert type_counts.get("confirmation-hub") == 1
        assert type_counts.get("d-form-table", 0) >= 25
        assert type_counts.get("audit-sheet", 0) >= 30
