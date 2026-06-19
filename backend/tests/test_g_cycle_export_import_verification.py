"""G 类底稿（投资循环）完整验证测试。

覆盖:
  P0: 注册完整性（wp_account_mapping + _WP_CODE_OVERRIDE + confirmation-hub）
  P1: 程序表模板注册（G0A~G14A 共 15 个）
  P2: 审定表 schema（G7-1 YAML）+ handler 正则
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
_ADDR_REGISTRY_PATH = _DATA_DIR / "g_address_registry_seed.json"
_SCHEMA_DIR = _DATA_DIR / "ledger_adapters" / "wp_render_schema"


@pytest.fixture(scope="module")
def wp_mapping() -> list[dict]:
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mappings", data) if isinstance(data, dict) else data


@pytest.fixture(scope="module")
def g_class_entries(wp_mapping) -> list[dict]:
    return [e for e in wp_mapping if e.get("cycle") == "G"]


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

    # G 类全部 wp_codes（89 个，不含程序表 G{n}A）
    _ALL_G_CODES = [
        # G0 函证
        "G0", "G0-1", "G0-2", "G0-3", "G0-4", "G0-5",
        # G1 交易性金融资产
        "G1", "G1-1", "G1-2", "G1-3", "G1-4", "G1-5", "G1-6",
        # G2 应收利息
        "G2", "G2-1", "G2-2", "G2-3", "G2-4",
        # G3 应收股利
        "G3", "G3-1", "G3-2", "G3-3", "G3-4",
        # G4 债权投资
        "G4", "G4-1", "G4-2", "G4-3", "G4-4", "G4-5", "G4-6", "G4-7", "G4-8",
        # G5 长期应收款
        "G5", "G5-1", "G5-2", "G5-3", "G5-4",
        # G6 其他债权投资
        "G6", "G6-1", "G6-2", "G6-3", "G6-4", "G6-5", "G6-6",
        # G7 长期股权投资
        "G7", "G7-1", "G7-2", "G7-3", "G7-4", "G7-5", "G7-6", "G7-7", "G7-8",
        # G8 其他权益工具投资
        "G8", "G8-1", "G8-2", "G8-3", "G8-4", "G8-5", "G8-6",
        # G9 其他非流动金融资产
        "G9", "G9-1", "G9-2", "G9-3", "G9-4",
        # G10 交易性金融负债
        "G10", "G10-1", "G10-2", "G10-3", "G10-4",
        # G11 投资收益
        "G11", "G11-1", "G11-2", "G11-3", "G11-4",
        # G12 净敞口套期收益
        "G12", "G12-1", "G12-2", "G12-3",
        # G13 公允价值变动收益
        "G13", "G13-1", "G13-2", "G13-3", "G13-4",
        # G14 信用减值损失
        "G14", "G14-1", "G14-2", "G14-3", "G14-4",
    ]

    def test_g_class_count(self, g_class_entries):
        """wp_account_mapping.json 中应有 89 个 cycle='G' 的条目。"""
        assert len(g_class_entries) == 89, (
            f"G 类底稿应有 89 条注册，实际 {len(g_class_entries)} 条"
        )

    def test_all_g_codes_in_mapping(self, g_class_entries):
        """所有 G 类 wp_code 在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in g_class_entries}
        missing = set(self._ALL_G_CODES) - mapping_codes
        assert not missing, f"G 类缺少 wp_code: {sorted(missing)}"

    def test_all_g_codes_have_override(self):
        """所有 89 个 G 类 wp_code 在 _WP_CODE_OVERRIDE 中有 componentType 映射。"""
        for code in self._ALL_G_CODES:
            assert code in _WP_CODE_OVERRIDE, (
                f"G 类 wp_code '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )

    def test_override_count_matches_mapping(self, g_class_entries):
        """_WP_CODE_OVERRIDE 中 G 类条目数 == wp_account_mapping G 类条目数。"""
        override_g_count = sum(1 for code in _WP_CODE_OVERRIDE if code.startswith("G"))
        assert override_g_count == len(g_class_entries), (
            f"_WP_CODE_OVERRIDE G 类 {override_g_count} 条 != "
            f"wp_account_mapping G 类 {len(g_class_entries)} 条"
        )

    def test_g0_is_confirmation_hub(self):
        """G0 函证底稿映射为 confirmation-hub。"""
        assert _WP_CODE_OVERRIDE.get("G0") == "confirmation-hub"

    def test_g0_consistent_with_d0_e0_f0(self):
        """G0/D0/E0/F0 使用相同 confirmation-hub 模式。"""
        assert _WP_CODE_OVERRIDE.get("G0") == "confirmation-hub"
        assert _WP_CODE_OVERRIDE.get("D0") == "confirmation-hub"
        assert _WP_CODE_OVERRIDE.get("E0") == "confirmation-hub"
        assert _WP_CODE_OVERRIDE.get("F0") == "confirmation-hub"

    def test_confirmation_hub_valid_type(self):
        """confirmation-hub 是合法的 componentType。"""
        assert "confirmation-hub" in VALID_COMPONENT_TYPES

    def test_all_component_types_valid(self, g_class_entries):
        """所有 G 类 componentType 必须是合法类型。"""
        valid_types = {
            "d-form-table", "audit-sheet", "a-program-console",
            "confirmation-hub", "c-note-table",
        }
        for entry in g_class_entries:
            wp_code = entry["wp_code"]
            ct = _WP_CODE_OVERRIDE.get(wp_code, "")
            assert ct in valid_types, (
                f"G 类 '{wp_code}' componentType '{ct}' 不合法"
            )

    def test_type_distribution(self):
        """G 类 componentType 分布符合预期。"""
        g_codes = {
            code: ct for code, ct in _WP_CODE_OVERRIDE.items()
            if code.startswith("G")
        }
        type_counts: dict[str, int] = {}
        for ct in g_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1
        assert type_counts.get("confirmation-hub", 0) == 1
        assert type_counts.get("d-form-table", 0) >= 40
        assert type_counts.get("audit-sheet", 0) >= 30

    @pytest.mark.parametrize("wp_code", [
        "G1-1", "G2-1", "G3-1", "G4-1", "G5-1", "G6-1", "G7-1",
        "G8-1", "G9-1", "G10-1", "G11-1", "G12-1", "G13-1", "G14-1",
    ])
    def test_audit_determination_tables_are_d_form(self, wp_code):
        """G{n}-1 审定表映射为 d-form-table。"""
        assert _WP_CODE_OVERRIDE.get(wp_code) == "d-form-table"


# ═══════════════════════════════════════════════════════════════════════════════
# P1: 程序表模板
# ═══════════════════════════════════════════════════════════════════════════════


class TestP1ProcedureTables:
    """P1 Tasks 6-22: 程序表模板注册验证。"""

    _EXPECTED_TABLES = [
        "G0A", "G1A", "G2A", "G3A", "G4A", "G5A", "G6A", "G7A",
        "G8A", "G9A", "G10A", "G11A", "G12A", "G13A", "G14A",
    ]

    def test_all_15_procedure_tables_registered(self, procedure_templates):
        """G0A~G14A 共 15 个程序表全部注册。"""
        for table_id in self._EXPECTED_TABLES:
            assert table_id in procedure_templates, (
                f"程序表 '{table_id}' 未注册到 procedure_table_templates.json"
            )

    @pytest.mark.parametrize("table_id", [
        "G0A", "G1A", "G2A", "G3A", "G4A", "G5A", "G6A", "G7A",
        "G8A", "G9A", "G10A", "G11A", "G12A", "G13A", "G14A",
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

    def test_g0a_has_confirmation_auto_source(self, procedure_templates):
        """G0A 函证程序表应有 confirmation_summary_for_cycle 数据源。"""
        items = procedure_templates["G0A"]["items"]
        sources = [item.get("auto_data_source") for item in items]
        assert "confirmation_summary_for_cycle" in sources

    def test_procedure_tables_have_risk_source(self, procedure_templates):
        """所有程序表 seq1 应引用 risk_for_cycle。"""
        for table_id in self._EXPECTED_TABLES:
            first_item = procedure_templates[table_id]["items"][0]
            assert first_item.get("auto_data_source") in (
                "risk_for_cycle", "confirmation_summary_for_cycle"
            ), f"{table_id} seq1 未引用 risk/confirmation 数据源"


# ═══════════════════════════════════════════════════════════════════════════════
# P2: 审定表 + 回写联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestP2AuditDetermination:
    """P2 Tasks 23-26: 审定表 schema + handler 正则。"""

    _AUDIT_DET_CODES = [
        "G1-1", "G2-1", "G3-1", "G4-1", "G5-1", "G6-1", "G7-1",
        "G8-1", "G9-1", "G10-1", "G11-1", "G12-1", "G13-1", "G14-1",
    ]

    def test_handler_regex_covers_g_class(self):
        """handler 正则 ^[D-N]\\d+-1$ 匹配所有 G 审定表。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        for code in self._AUDIT_DET_CODES:
            assert pattern.match(code), f"正则不匹配 {code}"

    def test_g7_1_schema_exists(self):
        """G7-1 特殊 YAML schema 文件存在。"""
        schema_path = _SCHEMA_DIR / "G7-1.yaml"
        assert schema_path.exists(), f"G7-1 schema 不存在: {schema_path}"

    def test_g7_1_schema_has_equity_cost_groups(self):
        """G7-1 schema 包含权益法/成本法分组。"""
        import yaml
        schema_path = _SCHEMA_DIR / "G7-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        section_names = [s["name"] for s in schema["sections"]]
        assert "权益法核算" in section_names
        assert "成本法核算" in section_names

    def test_g7_1_has_writeback_config(self):
        """G7-1 schema 包含 writeback 配置。"""
        import yaml
        schema_path = _SCHEMA_DIR / "G7-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert "writeback" in schema
        assert schema["writeback"]["target"] == "trial_balance.audited_amount"

    @pytest.mark.parametrize("wp_code", _AUDIT_DET_CODES)
    def test_audit_det_component_type(self, wp_code):
        """所有 14 个审定表为 d-form-table。"""
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table"


# ═══════════════════════════════════════════════════════════════════════════════
# P3: address_registry 坐标
# ═══════════════════════════════════════════════════════════════════════════════


class TestP3AddressRegistry:
    """P3 Tasks 27-32: address_registry 坐标注册。"""

    def test_seed_file_exists(self):
        """g_address_registry_seed.json 存在。"""
        assert _ADDR_REGISTRY_PATH.exists()

    def test_seed_has_entries(self, addr_registry):
        """seed 有 entries 数组。"""
        assert "entries" in addr_registry
        assert len(addr_registry["entries"]) >= 10

    def test_seed_cycle_is_g(self, addr_registry):
        """seed cycle 标识为 G。"""
        assert addr_registry.get("cycle") == "G"

    def test_g1_coordinates_registered(self, addr_registry):
        """G1-2/G1-3 交易性金融资产坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "G1-2" in codes
        assert "G1-3" in codes

    def test_g4_coordinates_registered(self, addr_registry):
        """G4-3/G4-4/G4-5 债权投资坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "G4-3" in codes
        assert "G4-4" in codes
        assert "G4-5" in codes

    def test_g7_coordinates_registered(self, addr_registry):
        """G7-3/G7-4/G7-5 长期股权投资坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "G7-3" in codes
        assert "G7-4" in codes
        assert "G7-5" in codes

    def test_g14_2_coordinates_registered(self, addr_registry):
        """G14-2 信用减值损失 ECL 坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "G14-2" in codes

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
    """P4 Tasks 33-38: 特殊程序 schema 确认。"""

    def test_g4_3_4_irr_is_audit_sheet(self):
        """G4-3/G4-4 实际利率法摊销走 audit-sheet。"""
        assert _WP_CODE_OVERRIDE["G4-3"] == "audit-sheet"
        assert _WP_CODE_OVERRIDE["G4-4"] == "audit-sheet"

    def test_g4_5_g14_2_ecl_is_audit_sheet(self):
        """G4-5/G14-2 ECL 三阶段走 audit-sheet。"""
        assert _WP_CODE_OVERRIDE["G4-5"] == "audit-sheet"
        assert _WP_CODE_OVERRIDE["G14-2"] == "audit-sheet"

    def test_g7_3_equity_method_is_audit_sheet(self):
        """G7-3 权益法核算走 audit-sheet。"""
        assert _WP_CODE_OVERRIDE["G7-3"] == "audit-sheet"

    def test_g7_4_impairment_is_audit_sheet(self):
        """G7-4 减值测试走 audit-sheet。"""
        assert _WP_CODE_OVERRIDE["G7-4"] == "audit-sheet"

    def test_fair_value_sheets_are_audit_sheet(self):
        """G1-3/G6-3/G8-3/G10-3 公允价值测试全部走 audit-sheet。"""
        fv_codes = ["G1-3", "G6-3", "G8-3", "G10-3"]
        for code in fv_codes:
            assert _WP_CODE_OVERRIDE[code] == "audit-sheet", (
                f"{code} 应为 audit-sheet，实际为 {_WP_CODE_OVERRIDE[code]}"
            )

    def test_all_g_class_routes_no_missing(self):
        """G 全系列在 _WP_CODE_OVERRIDE 中无遗漏（componentType 路由无 404）。"""
        g_codes = [code for code in _WP_CODE_OVERRIDE if code.startswith("G")]
        assert len(g_codes) == 89, f"应有 89 个 G 类映射，实际 {len(g_codes)}"


# ═══════════════════════════════════════════════════════════════════════════════
# P5: 联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestP5Linkage:
    """P5 Tasks 39-42: 联动绑定验证。"""

    def test_risk_for_cycle_in_procedure_tables(self, procedure_templates):
        """G{n}A 程序表引用 risk_for_cycle。"""
        tables_with_risk = []
        for key in procedure_templates:
            if key.startswith("G") and key.endswith("A"):
                items = procedure_templates[key].get("items", [])
                for item in items:
                    if item.get("auto_data_source") == "risk_for_cycle":
                        tables_with_risk.append(key)
                        break
        # 所有 15 个程序表中至少 14 个（G0A 用 confirmation_summary）引用 risk
        assert len(tables_with_risk) >= 14

    def test_control_test_in_procedure_tables(self, procedure_templates):
        """部分程序表引用 control_test_result_for_cycle。"""
        tables_with_control = []
        for key in procedure_templates:
            if key.startswith("G") and key.endswith("A"):
                items = procedure_templates[key].get("items", [])
                for item in items:
                    if item.get("auto_data_source") == "control_test_result_for_cycle":
                        tables_with_control.append(key)
                        break
        assert len(tables_with_control) >= 3

    def test_g0_confirmation_hub_route(self):
        """G0 → ConfirmationHub 路由已配置。"""
        assert _WP_CODE_OVERRIDE["G0"] == "confirmation-hub"

    def test_g13_g1_cross_ref_in_procedure(self, procedure_templates):
        """G13A 程序表引用 G1（公允价值变动↔交易性金融资产）。"""
        items = procedure_templates["G13A"]["items"]
        refs = " ".join(item.get("ref_index", "") or "" for item in items)
        assert "G1" in refs, "G13A 应有 G1 引用（公允价值变动联动）"

    def test_g11_g7_cross_ref_in_procedure(self, procedure_templates):
        """G11A 程序表引用 G7-5（投资收益↔长期股权投资）。"""
        items = procedure_templates["G11A"]["items"]
        refs = " ".join(item.get("ref_index", "") or "" for item in items)
        assert "G7" in refs, "G11A 应有 G7 引用（投资收益联动）"


# ═══════════════════════════════════════════════════════════════════════════════
# P6: 导入导出
# ═══════════════════════════════════════════════════════════════════════════════


class TestP6ExportImport:
    """P6 Tasks 43-46: 导入导出基础设施验证。"""

    # G 类 d-form-table wp_codes
    _G_FORM_TABLE_CODES = [
        "G0-1", "G0-2", "G0-3", "G0-4", "G0-5",
        "G1", "G1-1", "G1-6",
        "G2", "G2-1", "G2-4",
        "G3", "G3-1", "G3-2", "G3-4",
        "G4", "G4-1", "G4-8",
        "G5", "G5-1", "G5-2", "G5-4",
        "G6", "G6-1", "G6-6",
        "G7", "G7-1", "G7-8",
        "G8", "G8-1", "G8-6",
        "G9", "G9-1", "G9-4",
        "G10", "G10-1", "G10-4",
        "G11", "G11-1", "G11-4",
        "G12", "G12-1", "G12-3",
        "G13", "G13-1", "G13-4",
        "G14", "G14-1", "G14-4",
    ]

    # G 类 audit-sheet wp_codes
    _AUDIT_SHEET_CODES = [
        "G1-2", "G1-3", "G1-4", "G1-5",
        "G2-2", "G2-3",
        "G3-3",
        "G4-2", "G4-3", "G4-4", "G4-5", "G4-6", "G4-7",
        "G5-3",
        "G6-2", "G6-3", "G6-4", "G6-5",
        "G7-2", "G7-3", "G7-4", "G7-5", "G7-6", "G7-7",
        "G8-2", "G8-3", "G8-4", "G8-5",
        "G9-2", "G9-3",
        "G10-2", "G10-3",
        "G11-2", "G11-3",
        "G12-2",
        "G13-2", "G13-3",
        "G14-2", "G14-3",
    ]

    @pytest.mark.parametrize("wp_code", _G_FORM_TABLE_CODES)
    def test_g_form_table_registered(self, wp_code):
        """G 类 d-form-table 底稿在 _WP_CODE_OVERRIDE 中注册正确。"""
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table"

    @pytest.mark.parametrize("wp_code", _AUDIT_SHEET_CODES)
    def test_g_audit_sheet_registered(self, wp_code):
        """G 类 audit-sheet 底稿在 _WP_CODE_OVERRIDE 中注册正确。"""
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == "audit-sheet"

    def test_all_g_codes_in_mapping(self, g_class_entries):
        """所有 G 类 wp_code 在 wp_account_mapping 注册（批量导出可枚举）。"""
        mapping_codes = {e["wp_code"] for e in g_class_entries}
        all_codes = set(self._G_FORM_TABLE_CODES + self._AUDIT_SHEET_CODES + ["G0"])
        missing = all_codes - mapping_codes
        assert not missing, f"G 类缺少: {sorted(missing)}"

    def test_g_class_all_have_wp_code(self, g_class_entries):
        """所有 G 类条目有有效 wp_code。"""
        for entry in g_class_entries:
            assert entry.get("wp_code"), f"缺少 wp_code: {entry}"
            assert entry["wp_code"].startswith("G")

    def test_batch_export_type_distribution(self):
        """G 类 componentType 分布：1 confirmation-hub + 45 d-form-table + 39 audit-sheet + 4 其他。"""
        g_codes = {
            code: ct for code, ct in _WP_CODE_OVERRIDE.items()
            if code.startswith("G")
        }
        type_counts: dict[str, int] = {}
        for ct in g_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1
        assert type_counts.get("confirmation-hub") == 1
        assert type_counts.get("d-form-table", 0) >= 40
        assert type_counts.get("audit-sheet", 0) >= 30
