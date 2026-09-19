"""F 类底稿导入导出基础设施验证（Phase 6 Tasks 49-52）。

验证:
  Task 49: F 类 d-form-table 底稿导出为 Excel（复用通用 d-form-table 导出逻辑）
  Task 50: F 类 audit-sheet 底稿原生导出（复用 audit-sheet 通用导出）
  Task 51: 从 Excel 导入填充已有结构化 F 类底稿
  Task 52: 批量导出 F 类全量打包 zip（项目归档场景）

验证方式：
  - 确认所有 F 类 wp_code 正确注册在 wp_account_mapping.json
  - 确认 componentType 映射正确（d-form-table / audit-sheet / confirmation-hub）
  - 确认 d-form-table 类型的 F 类底稿可被通用导出逻辑处理
  - 确认 audit-sheet 类型的 F 类底稿注册正确
  - 确认批量导出时 F 类底稿在 audit_cycle="F" 下可被检索
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.f_cycle_f2_html_contract import (
    F2_HTML_MIGRATED,
    F2_MAIN,
    F2_SPE,
    F2_STOCKTAKE,
    F2_VAL,
    F1_PREPAYMENT,
    F3_NOTES,
    F4_PAYABLE,
    F5_COST,
    F_CYCLE_HTML_TYPES,
)
from app.services.wp_classification_service import _WP_CODE_OVERRIDE

# ═══════════════════════════════════════════════════════════════════════════════
# wp_account_mapping.json 加载
# ═══════════════════════════════════════════════════════════════════════════════

_MAPPING_PATH = Path(__file__).resolve().parent.parent / "data" / "wp_account_mapping.json"


@pytest.fixture(scope="module")
def wp_mapping() -> list[dict]:
    """加载 wp_account_mapping.json 全量数据。"""
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mappings", data) if isinstance(data, dict) else data


@pytest.fixture(scope="module")
def f_class_entries(wp_mapping) -> list[dict]:
    """筛选 cycle == 'F' 的全部条目。"""
    return [e for e in wp_mapping if e.get("cycle") == "F"]


# ═══════════════════════════════════════════════════════════════════════════════
# Task 49: F 类 d-form-table 底稿可被通用导出逻辑覆盖
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask49DFormTableExport:
    """验证 F 类 cycle HTML 底稿（F1~F5）注册正确，具备专用导入导出。"""

    _F_CYCLE_AUDIT_DETERMINATION = {
        "F1-1": F1_PREPAYMENT,
        "F2-1": F2_MAIN,
        "F3-1": F3_NOTES,
        "F4-1": F4_PAYABLE,
        "F5-1": F5_COST,
    }

    @pytest.mark.parametrize("wp_code,expected", list(_F_CYCLE_AUDIT_DETERMINATION.items()))
    def test_f_cycle_audit_determination_registered(self, wp_code, expected):
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == expected

    def test_f_class_no_legacy_d_form_table(self):
        """F 类已全部 HTML 化，不应残留 d-form-table。"""
        legacy = [
            code for code, ct in _WP_CODE_OVERRIDE.items()
            if code.startswith("F") and ct == "d-form-table"
        ]
        assert legacy == [], f"F 类仍使用 d-form-table: {legacy}"


class TestTask49F2HtmlInventoryExport:
    """F2 存货 HTML 化底稿 componentType 与导入导出前缀契约。"""

    @pytest.mark.parametrize("wp_code,expected", list(F2_HTML_MIGRATED.items()))
    def test_f2_html_component_type(self, wp_code, expected):
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == expected


# ═══════════════════════════════════════════════════════════════════════════════
# Task 50: F 类 audit-sheet 底稿原生导出
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask50AuditSheetExport:
    """验证 F 类已无 audit-sheet，F2 监盘/计价/特殊程序走 HTML bundle。"""

    def test_f_class_no_audit_sheet(self):
        legacy = [
            code for code, ct in _WP_CODE_OVERRIDE.items()
            if code.startswith("F") and ct == "audit-sheet"
        ]
        assert legacy == [], f"F 类仍使用 audit-sheet: {legacy}"

    def test_f1_cycle_html_registered(self):
        for code in ("F1", "F1-2", "F1-3", "F1-5", "F1-6"):
            assert _WP_CODE_OVERRIDE.get(code) == F1_PREPAYMENT

    def test_f3_cycle_html_registered(self):
        for code in ("F3-2", "F3-3", "F3-5", "F3-6"):
            assert _WP_CODE_OVERRIDE.get(code) == F3_NOTES

    def test_f4_cycle_html_registered(self):
        for code in ("F4-2", "F4-3", "F4-5", "F4-6"):
            assert _WP_CODE_OVERRIDE.get(code) == F4_PAYABLE

    def test_f5_cycle_html_registered(self):
        for code in ("F5-2", "F5-3", "F5-4", "F5-5", "F5-6"):
            assert _WP_CODE_OVERRIDE.get(code) == F5_COST

    def test_inventory_count_sheets_registered(self):
        """F2-21~F2-26 存货监盘系列全部为 f2-stocktake-bundle。"""
        for i in range(21, 27):
            code = f"F2-{i}"
            assert code in _WP_CODE_OVERRIDE, f"{code} 未注册"
            assert _WP_CODE_OVERRIDE[code] == F2_STOCKTAKE, (
                f"{code} 应为 {F2_STOCKTAKE}，实际为 {_WP_CODE_OVERRIDE[code]}"
            )

    def test_valuation_test_sheets_registered(self):
        """F2-38~F2-44 计价测试系列全部为 f2-inventory-valuation-impairment。"""
        for i in range(38, 45):
            code = f"F2-{i}"
            assert code in _WP_CODE_OVERRIDE, f"{code} 未注册"
            assert _WP_CODE_OVERRIDE[code] == F2_VAL, (
                f"{code} 应为 {F2_VAL}，实际为 {_WP_CODE_OVERRIDE[code]}"
            )

    def test_impairment_test_sheets_registered(self):
        """F2-47~F2-49 跌价准备测试系列全部为 f2-inventory-valuation-impairment。"""
        for i in range(47, 50):
            code = f"F2-{i}"
            assert code in _WP_CODE_OVERRIDE, f"{code} 未注册"
            assert _WP_CODE_OVERRIDE[code] == F2_VAL, (
                f"{code} 应为 {F2_VAL}，实际为 {_WP_CODE_OVERRIDE[code]}"
            )

    def test_ipo_sheets_registered(self):
        """F2-61~F2-72 IPO/舞弊应对系列全部为 f2-inventory-special。"""
        for i in range(61, 73):
            code = f"F2-{i}"
            assert code in _WP_CODE_OVERRIDE, f"{code} 未注册"
            assert _WP_CODE_OVERRIDE[code] == F2_SPE, (
                f"{code} 应为 {F2_SPE}，实际为 {_WP_CODE_OVERRIDE[code]}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 51: F 审定表走 d-form-table — 可导入填充
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask51ImportFromExcel:
    """验证 F 类审定表 / F2 HTML 底稿具备结构化导入基础。"""

    _AUDIT_DETERMINATION = {
        "F1-1": F1_PREPAYMENT,
        "F2-1": F2_MAIN,
        "F3-1": F3_NOTES,
        "F4-1": F4_PAYABLE,
        "F5-1": F5_COST,
    }

    @pytest.mark.parametrize("wp_code,expected", list(_AUDIT_DETERMINATION.items()))
    def test_audit_determination_tables_are_cycle_html(self, wp_code, expected):
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == expected

    def test_audit_determination_tables_in_mapping(self, f_class_entries):
        """F{n}-1 审定表全部在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in f_class_entries}
        for code in self._AUDIT_DETERMINATION:
            assert code in mapping_codes, (
                f"审定表 '{code}' 未在 wp_account_mapping.json 中注册"
            )

    @pytest.mark.parametrize("wp_code", ["F1-1", "F3-1", "F4-1", "F5-1"])
    def test_legacy_audit_determination_schema_yaml_exists(self, wp_code):
        """F{n}-1 审定表 schema YAML 文件存在。"""
        schema_path = (
            Path(__file__).resolve().parent.parent
            / "data" / "ledger_adapters" / "wp_render_schema" / f"{wp_code}.yaml"
        )
        assert schema_path.exists(), f"{wp_code} schema YAML 不存在: {schema_path}"

    def test_f_form_table_importable_pattern(self, f_class_entries):
        """F 类底稿 componentType 均在 cycle HTML 白名单内。"""
        for entry in f_class_entries:
            wp_code = entry["wp_code"]
            ct = _WP_CODE_OVERRIDE.get(wp_code, "")
            assert ct in F_CYCLE_HTML_TYPES, (
                f"{wp_code} 的 componentType '{ct}' 不在 F cycle HTML 白名单"
            )

    def test_f_form_table_additional_structured_codes(self):
        """原结构化 F2 底稿已 HTML 化。"""
        for code in ("F2-11", "F2-16", "F2-52", "F2-47", "F2-55", "F2-70"):
            assert code in F2_HTML_MIGRATED
            assert _WP_CODE_OVERRIDE.get(code) == F2_HTML_MIGRATED[code]


# ═══════════════════════════════════════════════════════════════════════════════
# Task 52: 批量导出 zip（F 类全量可检索）
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask52BatchExportZip:
    """验证 F 类底稿在 wp_account_mapping 中全部注册，批量导出可正确枚举。"""

    def test_all_93_f_class_registered(self, f_class_entries):
        """wp_account_mapping.json 中应有 93 个 audit_cycle='F' 的条目。"""
        assert len(f_class_entries) == 93, (
            f"F 类底稿应有 93 条注册，实际 {len(f_class_entries)} 条"
        )

    def test_f_class_all_have_wp_code(self, f_class_entries):
        """所有 F 类条目都有有效 wp_code。"""
        for entry in f_class_entries:
            assert entry.get("wp_code"), f"F 类条目缺少 wp_code: {entry}"
            assert entry["wp_code"].startswith("F"), (
                f"F 类条目 wp_code 应以 F 开头: {entry['wp_code']}"
            )

    def test_f0_is_confirmation_hub(self):
        """F0 函证底稿应映射为 confirmation-hub。"""
        assert "F0" in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE["F0"] == "confirmation-hub"

    def test_all_f_class_have_component_type(self, f_class_entries):
        """所有 93 个 F 类 wp_code 在 _WP_CODE_OVERRIDE 中都有 componentType 映射。"""
        for entry in f_class_entries:
            wp_code = entry["wp_code"]
            assert wp_code in _WP_CODE_OVERRIDE, (
                f"F 类 wp_code '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册 componentType"
            )

    def test_f_class_component_types_valid(self, f_class_entries):
        """所有 F 类 componentType 必须是合法类型之一。"""
        valid_types = set(F_CYCLE_HTML_TYPES)
        for entry in f_class_entries:
            wp_code = entry["wp_code"]
            ct = _WP_CODE_OVERRIDE.get(wp_code, "")
            assert ct in valid_types, (
                f"F 类 wp_code '{wp_code}' 的 componentType '{ct}' 不在合法类型集合内"
            )

    def test_f_class_expected_type_distribution(self):
        """F 类 componentType 分布符合预期。"""
        f_codes = {
            code: ct for code, ct in _WP_CODE_OVERRIDE.items()
            if code.startswith("F")
        }
        type_counts: dict[str, int] = {}
        for ct in f_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1

        # 验证分布：F2 HTML 四入口 + d-form-table + confirmation-hub
        assert type_counts.get("confirmation-hub", 0) == 1, "应有 1 个 confirmation-hub (F0)"
        assert type_counts.get(F2_MAIN, 0) >= 20, f"应有至少 20 个 {F2_MAIN}"
        assert type_counts.get(F1_PREPAYMENT, 0) >= 7, f"应有至少 7 个 {F1_PREPAYMENT}"
        assert type_counts.get("audit-sheet", 0) == 0, "F 类不应使用 audit-sheet"
        assert type_counts.get("d-form-table", 0) == 0, "F 类不应使用 d-form-table"

    def test_f_cycle_all_wp_codes_complete(self, f_class_entries):
        """F 类全部 wp_code 覆盖验证（关键编码完整性）。"""
        mapping_codes = {e["wp_code"] for e in f_class_entries}
        # 全部必须存在的关键编码
        expected_codes = {
            # 函证
            "F0", "F0-1", "F0-2", "F0-3", "F0-4", "F0-5",
            # 预付账款
            "F1", "F1-1", "F1-2", "F1-3", "F1-4",
            # 存货核心
            "F2", "F2-1", "F2-2", "F2-3", "F2-11", "F2-12", "F2-13", "F2-14",
            "F2-16", "F2-52",
            # 存货分析/监盘/检查/计价/跌价
            "F2-18", "F2-19", "F2-20",
            "F2-21", "F2-22", "F2-23", "F2-24", "F2-25", "F2-26",
            "F2-29", "F2-30", "F2-31", "F2-32", "F2-33", "F2-34", "F2-35",
            "F2-38", "F2-39", "F2-40", "F2-41", "F2-42", "F2-43", "F2-44",
            "F2-47", "F2-48", "F2-49",
            # 合同履约成本
            "F2-55", "F2-56", "F2-57", "F2-58",
            # IPO
            "F2-61", "F2-62", "F2-63", "F2-64", "F2-65", "F2-66",
            "F2-67", "F2-68", "F2-69", "F2-70", "F2-71", "F2-72",
            # 应付票据
            "F3", "F3-1", "F3-2", "F3-3", "F3-4", "F3-5", "F3-6",
            # 应付账款
            "F4", "F4-1", "F4-2", "F4-3", "F4-4", "F4-5", "F4-6",
            # 营业成本
            "F5", "F5-1", "F5-2", "F5-3", "F5-4", "F5-5", "F5-6",
        }
        missing = expected_codes - mapping_codes
        assert not missing, f"F 类缺少 wp_code: {sorted(missing)}"

    def test_f_class_override_covers_mapping(self, f_class_entries):
        """_WP_CODE_OVERRIDE 覆盖 wp_account_mapping 全部 F 类 wp_code。"""
        mapping_codes = {e["wp_code"] for e in f_class_entries}
        missing = mapping_codes - set(_WP_CODE_OVERRIDE.keys())
        assert not missing, f"F 类 mapping 未注册 override: {sorted(missing)}"

    def test_f_confirmation_hub_consistent_with_d_and_e(self):
        """F0 使用 confirmation-hub（与 D0/E0 同模式，若已注册）。"""
        assert _WP_CODE_OVERRIDE.get("F0") == "confirmation-hub"
        for code in ("D0", "E0"):
            if code in _WP_CODE_OVERRIDE:
                assert _WP_CODE_OVERRIDE[code] == "confirmation-hub"

    def test_f_class_g2_inventory_complete(self, f_class_entries):
        """G2 存货组（最复杂）关键子码齐全。"""
        mapping_codes = {e["wp_code"] for e in f_class_entries}
        # F2 明细（F2-4~F2-10 各类存货）
        for i in range(4, 11):
            code = f"F2-{i}"
            assert code in mapping_codes, f"存货明细 {code} 未注册"
        # F2 监盘（21~26）
        for i in range(21, 27):
            assert f"F2-{i}" in mapping_codes
        # F2 检查（29~35）
        for i in range(29, 36):
            assert f"F2-{i}" in mapping_codes
        # F2 计价（38~44）
        for i in range(38, 45):
            assert f"F2-{i}" in mapping_codes
        # F2 跌价（47~49）
        for i in range(47, 50):
            assert f"F2-{i}" in mapping_codes
        # F2 IPO（61~72）
        for i in range(61, 73):
            assert f"F2-{i}" in mapping_codes
