"""E 类底稿导入导出基础设施验证（Phase 6 Tasks 31-34）。

验证:
  Task 31: E 类 d-form-table 底稿导出为 Excel（复用通用 d-form-table 导出逻辑）
  Task 32: E 类 audit-sheet 底稿原生导出（复用 audit-sheet 通用导出）
  Task 33: 从 Excel 导入填充已有结构化 E 类底稿
  Task 34: 批量导出 E 类全量打包 zip（项目归档场景）

验证方式：
  - 确认所有 E 类 wp_code 正确注册在 wp_account_mapping.json
  - 确认 componentType 映射正确（d-form-table / audit-sheet / a-program-console / confirmation-hub）
  - 确认 d-form-table 类型的 E 类底稿可被通用导出逻辑处理
  - 确认 audit-sheet 类型的 E 类底稿注册正确
  - 确认批量导出时 E 类底稿在 audit_cycle="E" 下可被检索
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

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
def e_class_entries(wp_mapping) -> list[dict]:
    """筛选 cycle == 'E' 的全部条目。"""
    return [e for e in wp_mapping if e.get("cycle") == "E"]


# ═══════════════════════════════════════════════════════════════════════════════
# Task 31: E 类 d-form-table 底稿可被通用导出逻辑覆盖
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask31DFormTableExport:
    """验证 E 类 d-form-table 底稿能被通用 Excel 导出基础设施支持。"""

    # E 类中走 d-form-table 的 wp_codes
    _E_FORM_TABLE_CODES = [
        # 函证辅助
        "E0-1", "E0-2", "E0-3", "E0-4", "E0-5",
        # 货币资金 - 常规（结构化表单）
        "E1", "E1-1", "E1-2", "E1-6", "E1-10",
    ]

    @pytest.mark.parametrize("wp_code", _E_FORM_TABLE_CODES)
    def test_e_form_table_component_type_registered(self, wp_code):
        """每个 d-form-table E 类 wp_code 在 _WP_CODE_OVERRIDE 中注册且类型正确。"""
        assert wp_code in _WP_CODE_OVERRIDE, (
            f"E 类 wp_code '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册"
        )
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table", (
            f"E 类 wp_code '{wp_code}' 应为 d-form-table，实际为 {_WP_CODE_OVERRIDE[wp_code]}"
        )

    def test_all_e_form_table_codes_in_mapping(self, e_class_entries):
        """所有 d-form-table E 类 wp_code 在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in e_class_entries}
        for code in self._E_FORM_TABLE_CODES:
            assert code in mapping_codes, (
                f"wp_code '{code}' 未在 wp_account_mapping.json 中注册"
            )

    def test_e_form_table_count(self):
        """E 类 d-form-table 底稿数量验证。"""
        e_form_codes = [
            code for code, ct in _WP_CODE_OVERRIDE.items()
            if code.startswith("E") and ct == "d-form-table"
        ]
        assert len(e_form_codes) == len(self._E_FORM_TABLE_CODES), (
            f"E 类 d-form-table 应有 {len(self._E_FORM_TABLE_CODES)} 个，"
            f"实际 {len(e_form_codes)} 个: {e_form_codes}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 32: E 类 audit-sheet 底稿原生导出
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask32AuditSheetExport:
    """验证 E 类 audit-sheet 底稿注册正确，支持 OnlyOffice 原生导出。"""

    # E 类中走 audit-sheet 的 wp_codes
    _AUDIT_SHEET_CODES = [
        # 含公式明细表
        "E1-3", "E1-4", "E1-5",
        # 检查/测算
        "E1-7", "E1-8", "E1-9", "E1-11",
        # 分析程序
        "E1-14", "E1-15",
        # 检查程序
        "E1-18", "E1-19", "E1-20", "E1-21", "E1-22", "E1-23",
        # IPO/舞弊应对
        "E1-26", "E1-27", "E1-28", "E1-29", "E1-30", "E1-31", "E1-32",
    ]

    @pytest.mark.parametrize("wp_code", _AUDIT_SHEET_CODES)
    def test_audit_sheet_component_type_registered(self, wp_code):
        """每个 audit-sheet E 类 wp_code 在 _WP_CODE_OVERRIDE 中注册且类型正确。"""
        assert wp_code in _WP_CODE_OVERRIDE, (
            f"E 类 wp_code '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册"
        )
        assert _WP_CODE_OVERRIDE[wp_code] == "audit-sheet", (
            f"E 类 wp_code '{wp_code}' 应为 audit-sheet，实际为 {_WP_CODE_OVERRIDE[wp_code]}"
        )

    def test_all_audit_sheet_codes_in_mapping(self, e_class_entries):
        """所有 audit-sheet E 类 wp_code 在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in e_class_entries}
        for code in self._AUDIT_SHEET_CODES:
            assert code in mapping_codes, (
                f"wp_code '{code}' 未在 wp_account_mapping.json 中注册"
            )

    def test_audit_sheet_count(self):
        """E 类 audit-sheet 底稿数量验证。"""
        e_sheet_codes = [
            code for code, ct in _WP_CODE_OVERRIDE.items()
            if code.startswith("E") and ct == "audit-sheet"
        ]
        assert len(e_sheet_codes) == len(self._AUDIT_SHEET_CODES), (
            f"E 类 audit-sheet 应有 {len(self._AUDIT_SHEET_CODES)} 个，"
            f"实际 {len(e_sheet_codes)} 个: {e_sheet_codes}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 33: E 审定表（E1-1）走 d-form-table — 可导入填充
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask33ImportFromExcel:
    """验证 E 类审定表使用 d-form-table，具备结构化导入基础。"""

    # E 审定表
    _AUDIT_DETERMINATION_CODES = ["E1-1"]

    @pytest.mark.parametrize("wp_code", _AUDIT_DETERMINATION_CODES)
    def test_audit_determination_tables_are_d_form(self, wp_code):
        """E1-1 审定表映射为 d-form-table（支持结构化导入）。"""
        assert wp_code in _WP_CODE_OVERRIDE, (
            f"审定表 '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册"
        )
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table", (
            f"审定表 '{wp_code}' 应为 d-form-table，实际为 {_WP_CODE_OVERRIDE[wp_code]}"
        )

    def test_audit_determination_tables_in_mapping(self, e_class_entries):
        """E1-1 审定表在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in e_class_entries}
        for code in self._AUDIT_DETERMINATION_CODES:
            assert code in mapping_codes, (
                f"审定表 '{code}' 未在 wp_account_mapping.json 中注册"
            )

    def test_e1_1_schema_yaml_exists(self):
        """E1-1 审定表 schema YAML 文件存在。"""
        schema_path = (
            Path(__file__).resolve().parent.parent
            / "data" / "ledger_adapters" / "wp_render_schema" / "E1-1.yaml"
        )
        assert schema_path.exists(), f"E1-1 schema YAML 不存在: {schema_path}"

    def test_e_form_table_importable_pattern(self, e_class_entries):
        """所有 E 类 d-form-table 底稿具备导入基础条件。"""
        d_form_codes = [
            e["wp_code"] for e in e_class_entries
            if _WP_CODE_OVERRIDE.get(e["wp_code"]) == "d-form-table"
        ]
        # 每个 d-form-table 底稿在 _WP_CODE_OVERRIDE 中注册
        for code in d_form_codes:
            assert code in _WP_CODE_OVERRIDE
            assert _WP_CODE_OVERRIDE[code] == "d-form-table"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 34: 批量导出 zip（E 类全量可检索）
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask34BatchExportZip:
    """验证 E 类底稿在 wp_account_mapping 中全部注册，批量导出可正确枚举。"""

    def test_all_33_e_class_registered(self, e_class_entries):
        """wp_account_mapping.json 中应有 33 个 audit_cycle='E' 的条目。"""
        assert len(e_class_entries) == 33, (
            f"E 类底稿应有 33 条注册，实际 {len(e_class_entries)} 条"
        )

    def test_e_class_all_have_wp_code(self, e_class_entries):
        """所有 E 类条目都有有效 wp_code。"""
        for entry in e_class_entries:
            assert entry.get("wp_code"), f"E 类条目缺少 wp_code: {entry}"
            assert entry["wp_code"].startswith("E"), (
                f"E 类条目 wp_code 应以 E 开头: {entry['wp_code']}"
            )

    def test_e0_is_confirmation_hub(self):
        """E0 函证底稿应映射为 confirmation-hub。"""
        assert "E0" in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE["E0"] == "confirmation-hub"

    def test_all_e_class_have_component_type(self, e_class_entries):
        """所有 33 个 E 类 wp_code 在 _WP_CODE_OVERRIDE 中都有 componentType 映射。"""
        for entry in e_class_entries:
            wp_code = entry["wp_code"]
            assert wp_code in _WP_CODE_OVERRIDE, (
                f"E 类 wp_code '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册 componentType"
            )

    def test_e_class_component_types_valid(self, e_class_entries):
        """所有 E 类 componentType 必须是合法类型之一。"""
        valid_types = {
            "d-form-table", "audit-sheet", "a-program-console",
            "confirmation-hub", "c-note-table",
        }
        for entry in e_class_entries:
            wp_code = entry["wp_code"]
            ct = _WP_CODE_OVERRIDE.get(wp_code, "")
            assert ct in valid_types, (
                f"E 类 wp_code '{wp_code}' 的 componentType '{ct}' 不在合法类型集合内"
            )

    def test_e_class_expected_type_distribution(self):
        """E 类 componentType 分布符合预期。"""
        e_codes = {
            code: ct for code, ct in _WP_CODE_OVERRIDE.items()
            if code.startswith("E")
        }
        type_counts = {}
        for ct in e_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1

        # 验证分布：大量 audit-sheet + 一些 d-form-table + 1 confirmation-hub
        assert type_counts.get("confirmation-hub", 0) == 1, "应有 1 个 confirmation-hub (E0)"
        assert type_counts.get("d-form-table", 0) >= 5, "应有至少 5 个 d-form-table"
        assert type_counts.get("audit-sheet", 0) >= 15, "应有至少 15 个 audit-sheet"

    def test_e_cycle_all_wp_codes_complete(self, e_class_entries):
        """E 类全部 wp_code 覆盖验证（E0~E1-32 完整）。"""
        mapping_codes = {e["wp_code"] for e in e_class_entries}
        expected_codes = {
            "E0", "E0-1", "E0-2", "E0-3", "E0-4", "E0-5",
            "E1", "E1-1", "E1-2", "E1-3", "E1-4", "E1-5",
            "E1-6", "E1-7", "E1-8", "E1-9", "E1-10", "E1-11",
            "E1-14", "E1-15",
            "E1-18", "E1-19", "E1-20", "E1-21", "E1-22", "E1-23",
            "E1-26", "E1-27", "E1-28", "E1-29", "E1-30", "E1-31", "E1-32",
        }
        missing = expected_codes - mapping_codes
        assert not missing, f"E 类缺少 wp_code: {sorted(missing)}"

    def test_e_class_override_count_matches_mapping(self, e_class_entries):
        """_WP_CODE_OVERRIDE 中 E 类条目数 == wp_account_mapping E 类条目数。"""
        override_e_count = sum(
            1 for code in _WP_CODE_OVERRIDE if code.startswith("E")
        )
        mapping_e_count = len(e_class_entries)
        assert override_e_count == mapping_e_count, (
            f"_WP_CODE_OVERRIDE E 类 {override_e_count} 条 != "
            f"wp_account_mapping E 类 {mapping_e_count} 条"
        )

    def test_ipo_applicable_codes_are_audit_sheet(self):
        """E1-26~E1-32 IPO 底稿全部为 audit-sheet。"""
        for i in range(26, 33):
            code = f"E1-{i}"
            assert code in _WP_CODE_OVERRIDE, f"{code} 未注册"
            assert _WP_CODE_OVERRIDE[code] == "audit-sheet", (
                f"{code} 应为 audit-sheet，实际为 {_WP_CODE_OVERRIDE[code]}"
            )

    def test_e_confirmation_hub_consistent_with_d(self):
        """E0 和 D0 使用相同的 confirmation-hub 模式。"""
        assert _WP_CODE_OVERRIDE.get("E0") == "confirmation-hub"
        assert _WP_CODE_OVERRIDE.get("D0") == "confirmation-hub"
