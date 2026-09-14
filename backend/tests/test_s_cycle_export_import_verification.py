"""S 类底稿（专项循环）完整验证测试。

覆盖 P0-P6 综合验证：
  1. wp_account_mapping 注册完整性（90 个 wp_code）
  2. _WP_CODE_OVERRIDE componentType 映射（90 条）
  3. applicable_when 评估逻辑（S32/S33/S34/S35）
  4. 程序表模板注册（S1/S2/S3/S8/S10/S11/S13）
  5. address_registry 坐标注册（S15/S17）
  6. docx 配置（S12A/S33-REV/S34-1-1）
  7. 联动 resolver 注册
  8. 导入导出基础设施
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
_ADDR_REGISTRY_PATH = _DATA_DIR / "s_address_registry_seed.json"


@pytest.fixture(scope="module")
def wp_mapping() -> list[dict]:
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mappings", data) if isinstance(data, dict) else data


@pytest.fixture(scope="module")
def s_class_entries(wp_mapping) -> list[dict]:
    return [e for e in wp_mapping if e.get("cycle") == "S"]


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
    if not _ADDR_REGISTRY_PATH.exists():
        pytest.skip("s_address_registry_seed.json not yet created")
    with open(_ADDR_REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════════════════
# P0: 注册完整性
# ═══════════════════════════════════════════════════════════════════════════════


class TestP0Registration:
    """P0: wp_account_mapping + _WP_CODE_OVERRIDE 完整性。"""

    # All 90 S-cycle wp_codes
    _ALL_S_CODES = (
        # S1~S17 + S12A (18)
        ["S1", "S2", "S3", "S4", "S5", "S6", "S8", "S9", "S10", "S11",
         "S12", "S12A", "S13", "S14", "S15", "S16", "S17"]
        # S20~S21 (2)
        + ["S20", "S21"]
        # S32-1~S32-13 (13)
        + [f"S32-{i}" for i in range(1, 14)]
        # S33-1~S33-9 + S33-REV (10)
        + [f"S33-{i}" for i in range(1, 10)] + ["S33-REV"]
        # S34-0~S34-41 + S34-1-1 (43)
        + [f"S34-{i}" for i in range(0, 42)] + ["S34-1-1"]
        # S35-1~S35-5 (5)
        + [f"S35-{i}" for i in range(1, 6)]
    )

    _PROGRAM_CODES = ["S1", "S2", "S3", "S8", "S10", "S11", "S13"]
    _D_FORM_TABLE_CODES = (
        ["S4", "S5", "S6", "S9", "S12", "S14", "S16", "S20", "S21"]
        + [f"S32-{i}" for i in range(1, 14)]
        + [f"S33-{i}" for i in range(1, 10)]
        + [f"S34-{i}" for i in range(0, 42)]
        + [f"S35-{i}" for i in range(1, 6)]
    )
    _AUDIT_SHEET_CODES = ["S15", "S17"]
    _WORD_TEMPLATE_CODES = ["S12A", "S33-REV", "S34-1-1"]

    def test_s_class_count(self, s_class_entries):
        """wp_account_mapping.json 中应有 90 个 cycle='S' 的条目。"""
        assert len(s_class_entries) == 90, (
            f"S 类底稿应有 90 条注册，实际 {len(s_class_entries)} 条"
        )

    def test_all_s_codes_in_mapping(self, s_class_entries):
        """所有 90 个 S 类 wp_code 在 wp_account_mapping 中注册。"""
        mapping_codes = {e["wp_code"] for e in s_class_entries}
        expected = set(self._ALL_S_CODES)
        missing = expected - mapping_codes
        assert not missing, f"缺少 S 类 wp_code: {sorted(missing)}"

    def test_all_s_codes_have_override(self):
        """所有 90 个 S 类 wp_code 在 _WP_CODE_OVERRIDE 中有映射。"""
        for code in self._ALL_S_CODES:
            assert code in _WP_CODE_OVERRIDE, (
                f"S 类 wp_code '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )

    def test_all_component_types_valid(self):
        """所有 S 类 componentType 必须是合法类型。"""
        for code in self._ALL_S_CODES:
            ct = _WP_CODE_OVERRIDE.get(code, "")
            assert ct in VALID_COMPONENT_TYPES, (
                f"S 类 '{code}' componentType '{ct}' 不合法"
            )

    @pytest.mark.parametrize("wp_code", _PROGRAM_CODES)
    def test_program_tables_are_a_program_console(self, wp_code):
        """S 类程序表式底稿映射为 a-program-console。"""
        assert _WP_CODE_OVERRIDE[wp_code] == "a-program-console"

    @pytest.mark.parametrize("wp_code", _AUDIT_SHEET_CODES)
    def test_audit_sheets_are_audit_sheet(self, wp_code):
        """S 类计算表底稿映射为 audit-sheet。"""
        assert _WP_CODE_OVERRIDE[wp_code] == "audit-sheet"

    @pytest.mark.parametrize("wp_code", _WORD_TEMPLATE_CODES)
    def test_word_templates_are_word_template(self, wp_code):
        """S 类 docx 底稿映射为 word-template。"""
        assert _WP_CODE_OVERRIDE[wp_code] == "word-template"

    def test_no_confirmation_hub(self):
        """S 类无函证（无 S0），不应有 confirmation-hub 映射。"""
        s_codes = {code: ct for code, ct in _WP_CODE_OVERRIDE.items() if code.startswith("S")}
        for code, ct in s_codes.items():
            assert ct != "confirmation-hub", f"S 类 '{code}' 不应映射 confirmation-hub"

    def test_type_distribution(self):
        """S 类 componentType 分布：7 程序表 + 78 检查表 + 2 计算表 + 3 文档 = 90。"""
        s_codes = {code: ct for code, ct in _WP_CODE_OVERRIDE.items() if code.startswith("S")}
        type_counts: dict[str, int] = {}
        for ct in s_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1
        assert type_counts.get("a-program-console", 0) == 7
        assert type_counts.get("d-form-table", 0) == 78
        assert type_counts.get("audit-sheet", 0) == 2
        assert type_counts.get("word-template", 0) == 3

    def test_s_class_no_account_codes(self, s_class_entries):
        """S 类底稿不对应 GL 科目（account_codes 为空数组）。"""
        for entry in s_class_entries:
            assert entry.get("account_codes") == [] or entry.get("account_codes") is None, (
                f"S 类 '{entry['wp_code']}' 不应有 account_codes"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# P0 续: applicable_when 评估
# ═══════════════════════════════════════════════════════════════════════════════


class TestP0ApplicableWhen:
    """P0: S32~S35 applicable_when 字段验证。"""

    def test_s32_applicable_when(self, s_class_entries):
        """S32 系列 applicable_when = ipo/listed/neeq。"""
        for entry in s_class_entries:
            if entry["wp_code"].startswith("S32-"):
                aw = entry.get("applicable_when", {})
                cats = aw.get("business_category", [])
                assert set(cats) == {"ipo", "listed", "neeq"}, (
                    f"{entry['wp_code']} applicable_when 不正确: {cats}"
                )

    def test_s33_applicable_when(self, s_class_entries):
        """S33 系列 applicable_when = ipo/listed/neeq。"""
        for entry in s_class_entries:
            if entry["wp_code"].startswith("S33"):
                aw = entry.get("applicable_when", {})
                cats = aw.get("business_category", [])
                assert set(cats) == {"ipo", "listed", "neeq"}, (
                    f"{entry['wp_code']} applicable_when 不正确: {cats}"
                )

    def test_s34_applicable_when(self, s_class_entries):
        """S34 系列 applicable_when = ipo/listed/neeq/refinancing。"""
        for entry in s_class_entries:
            if entry["wp_code"].startswith("S34"):
                aw = entry.get("applicable_when", {})
                cats = aw.get("business_category", [])
                assert set(cats) == {"ipo", "listed", "neeq", "refinancing"}, (
                    f"{entry['wp_code']} applicable_when 不正确: {cats}"
                )

    def test_s35_applicable_when(self, s_class_entries):
        """S35 系列 applicable_when = refinancing。"""
        for entry in s_class_entries:
            if entry["wp_code"].startswith("S35-"):
                aw = entry.get("applicable_when", {})
                cats = aw.get("business_category", [])
                assert set(cats) == {"refinancing"}, (
                    f"{entry['wp_code']} applicable_when 不正确: {cats}"
                )

    def test_s1_to_s21_no_applicable_when(self, s_class_entries):
        """S1~S21 无 applicable_when 限制（所有项目适用）。"""
        general_codes = {"S1", "S2", "S3", "S4", "S5", "S6", "S8", "S9",
                         "S10", "S11", "S12", "S12A", "S13", "S14", "S15",
                         "S16", "S17", "S20", "S21"}
        for entry in s_class_entries:
            if entry["wp_code"] in general_codes:
                aw = entry.get("applicable_when")
                assert not aw, (
                    f"{entry['wp_code']} 不应有 applicable_when: {aw}"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# P1: 程序表模板
# ═══════════════════════════════════════════════════════════════════════════════


class TestP1ProcedureTables:
    """P1: S 类程序表模板注册验证。"""

    _EXPECTED_TABLES = ["S1", "S2", "S3", "S8", "S10", "S11", "S13"]

    def test_all_7_procedure_tables_registered(self, procedure_templates):
        """S1/S2/S3/S8/S10/S11/S13 共 7 个程序表全部注册。"""
        for table_id in self._EXPECTED_TABLES:
            assert table_id in procedure_templates, (
                f"程序表 '{table_id}' 未注册到 procedure_table_templates.json"
            )

    @pytest.mark.parametrize("table_id", ["S1", "S2", "S3", "S8", "S10", "S11", "S13"])
    def test_procedure_table_has_items(self, procedure_templates, table_id):
        """每个 S 类程序表有 items 且步骤数 >= 3。"""
        table = procedure_templates[table_id]
        assert "items" in table, f"{table_id} 缺少 items"
        assert len(table["items"]) >= 3, (
            f"{table_id} 步骤数 {len(table['items'])} < 3"
        )

    def test_s_procedure_tables_no_risk_for_cycle(self, procedure_templates):
        """S 类程序表不引用 risk_for_cycle（S 无独立风险评估）。"""
        for table_id in self._EXPECTED_TABLES:
            if table_id not in procedure_templates:
                continue
            items = procedure_templates[table_id]["items"]
            for item in items:
                assert item.get("auto_data_source") != "risk_for_cycle", (
                    f"{table_id} 不应引用 risk_for_cycle（S 类无独立风险评估）"
                )

    def test_s_procedure_tables_no_control_test(self, procedure_templates):
        """S 类程序表不引用 control_test_result_for_cycle（S 无控制测试）。"""
        for table_id in self._EXPECTED_TABLES:
            if table_id not in procedure_templates:
                continue
            items = procedure_templates[table_id]["items"]
            for item in items:
                assert item.get("auto_data_source") != "control_test_result_for_cycle", (
                    f"{table_id} 不应引用 control_test_result_for_cycle（S 类无控制测试）"
                )

    def test_s_procedure_table_names_use_wp_code_directly(self, procedure_templates):
        """S 类程序表 key 使用 wp_code 直接（S1 而非 S1A）。"""
        for table_id in self._EXPECTED_TABLES:
            assert table_id in procedure_templates
            # 不应有 S1A, S2A 等 pattern
            assert f"{table_id}A" not in procedure_templates, (
                f"S 类不应使用 {table_id}A 模式"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# P3: address_registry 坐标
# ═══════════════════════════════════════════════════════════════════════════════


class TestP3AddressRegistry:
    """P3: S 类 address_registry 坐标注册。"""

    def test_seed_file_exists(self):
        """s_address_registry_seed.json 存在。"""
        assert _ADDR_REGISTRY_PATH.exists()

    def test_seed_has_entries(self, addr_registry):
        """seed 有 entries 数组且 >= 2 条（S15 + S17）。"""
        assert "entries" in addr_registry
        assert len(addr_registry["entries"]) >= 2

    def test_seed_cycle_is_s(self, addr_registry):
        """seed cycle 标识为 S。"""
        assert addr_registry.get("cycle") == "S"

    def test_s15_coordinates(self, addr_registry):
        """S15 每股收益坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "S15" in codes

    def test_s17_coordinates(self, addr_registry):
        """S17 非经常性损益坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "S17" in codes

    def test_s15_has_eps_coords(self, addr_registry):
        """S15 有每股收益/稀释EPS/ROE 坐标。"""
        s15 = next((e for e in addr_registry["entries"] if e["wp_code"] == "S15"), None)
        assert s15 is not None
        purposes = {c["purpose"] for c in s15["coordinates"]}
        assert "basic_eps" in purposes
        assert "diluted_eps" in purposes
        assert "weighted_avg_roe" in purposes

    def test_s17_has_non_recurring_coords(self, addr_registry):
        """S17 有非经常性损益合计/扣非净利润坐标。"""
        s17 = next((e for e in addr_registry["entries"] if e["wp_code"] == "S17"), None)
        assert s17 is not None
        purposes = {c["purpose"] for c in s17["coordinates"]}
        assert "non_recurring_total" in purposes
        assert "adjusted_net_profit" in purposes


# ═══════════════════════════════════════════════════════════════════════════════
# P4: docx 配置
# ═══════════════════════════════════════════════════════════════════════════════


class TestP4DocxConfig:
    """P4: S 类 word-template 底稿配置验证。"""

    def test_s12a_is_word_template(self):
        """S12A 映射为 word-template。"""
        assert _WP_CODE_OVERRIDE.get("S12A") == "word-template"

    def test_s33_rev_is_word_template(self):
        """S33-REV 映射为 word-template。"""
        assert _WP_CODE_OVERRIDE.get("S33-REV") == "word-template"

    def test_s34_1_1_is_word_template(self):
        """S34-1-1 映射为 word-template。"""
        assert _WP_CODE_OVERRIDE.get("S34-1-1") == "word-template"


# ═══════════════════════════════════════════════════════════════════════════════
# P5: 联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestP5Linkage:
    """P5: S 类联动 resolver 验证。"""

    def test_revenue_audited_for_s20_resolver_registered(self):
        """revenue_audited_for_s20 resolver 已注册。"""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        assert "revenue_audited_for_s20" in sources

    def test_eps_data_from_tb_resolver_registered(self):
        """eps_data_from_tb resolver 已注册。"""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        assert "eps_data_from_tb" in sources

    def test_non_recurring_items_from_tb_resolver_registered(self):
        """non_recurring_items_from_tb resolver 已注册。"""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        assert "non_recurring_items_from_tb" in sources

    def test_cycle_audited_amounts_resolver_registered(self):
        """cycle_audited_amounts resolver 已注册。"""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        assert "cycle_audited_amounts" in sources


# ═══════════════════════════════════════════════════════════════════════════════
# P6: 导入导出
# ═══════════════════════════════════════════════════════════════════════════════


class TestP6ExportImport:
    """P6: 导入导出基础设施验证。"""

    _S_D_FORM_TABLE_SAMPLE = [
        "S4", "S5", "S6", "S9", "S12", "S14", "S16", "S20", "S21",
        "S32-1", "S32-5", "S32-13",
        "S33-1", "S33-9",
        "S34-0", "S34-1", "S34-20", "S34-41",
        "S35-1", "S35-5",
    ]

    @pytest.mark.parametrize("wp_code", _S_D_FORM_TABLE_SAMPLE)
    def test_s_form_table_registered(self, wp_code):
        """S 类 d-form-table 底稿在 _WP_CODE_OVERRIDE 中注册正确。"""
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table"

    def test_all_s_codes_in_mapping(self, s_class_entries):
        """所有 S 类 wp_code 在 wp_account_mapping 注册（批量导出可枚举）。"""
        mapping_codes = {e["wp_code"] for e in s_class_entries}
        assert len(mapping_codes) == 90

    def test_s_class_all_have_wp_code(self, s_class_entries):
        """所有 S 类条目有有效 wp_code。"""
        for entry in s_class_entries:
            assert entry.get("wp_code"), f"缺少 wp_code: {entry}"
            assert entry["wp_code"].startswith("S")

    def test_batch_export_type_distribution(self):
        """S 类 componentType 分布合理（90 = 7+78+2+3）。"""
        s_codes = {code: ct for code, ct in _WP_CODE_OVERRIDE.items() if code.startswith("S")}
        assert len(s_codes) == 90
        type_counts: dict[str, int] = {}
        for ct in s_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1
        assert type_counts["a-program-console"] == 7
        assert type_counts["d-form-table"] == 78
        assert type_counts["audit-sheet"] == 2
        assert type_counts["word-template"] == 3
