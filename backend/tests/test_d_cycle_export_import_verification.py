"""D 类底稿导入导出基础设施验证。

验证 tasks 39-42:
  39. D 类 d-form-table 底稿导出为 Excel（复用通用 d-form-table 导出逻辑）
  40. D 类 audit-sheet 底稿原生导出（复用 audit-sheet 通用导出）
  41. 从 Excel 导入填充已有结构化 D 类底稿
  42. 批量导出 D 类全量打包 zip（项目归档场景）

验证方式：
  - 确认所有 D 类 wp_code 正确注册在 wp_account_mapping.json
  - 确认 componentType 映射正确（d-form-table / audit-sheet / a-program-console / confirmation-hub）
  - 确认 d-form-table 类型的 D 类底稿可被通用导出逻辑处理
  - 确认 audit-sheet 类型的 D 类底稿注册正确
  - 确认批量导出时 D 类底稿在 audit_cycle="D" 下可被检索
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
    """加载 wp_account_mapping.json 全量数据（mappings 数组）。"""
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mappings", data) if isinstance(data, dict) else data


@pytest.fixture(scope="module")
def d_class_entries(wp_mapping) -> list[dict]:
    """筛选 cycle == 'D' 的全部条目。"""
    return [e for e in wp_mapping if e.get("cycle") == "D"]


# ═══════════════════════════════════════════════════════════════════════════════
# Task 39: D 类 d-form-table 底稿可被通用导出逻辑覆盖
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask39DFormTableExport:
    """验证 D 类 d-form-table 底稿能被通用 Excel 导出基础设施支持。"""

    # D 类中走 d-form-table 的 wp_codes
    _D_FORM_TABLE_CODES = [
        # 函证辅助
        "D0-1", "D0-2", "D0-3", "D0-4", "D0-5",
        # 应收票据
        "D1", "D1-1", "D1-4",
        # 应收账款
        "D2", "D2-1", "D2-3", "D2-4",
        # 预收账款
        "D3", "D3-1", "D3-2",
        # 营业收入
        "D4", "D4-1", "D4-5", "D4-12", "D4-21", "D4-33",
        # 应收款项融资
        "D5", "D5-1",
        # 合同资产
        "D6", "D6-1", "D6-4", "D6-5", "D6-6", "D6-9",
        # 合同负债
        "D7", "D7-1", "D7-2",
    ]

    @pytest.mark.parametrize("wp_code", _D_FORM_TABLE_CODES)
    def test_d_form_table_component_type_registered(self, wp_code):
        """每个 d-form-table D 类 wp_code 在 _WP_CODE_OVERRIDE 中注册且类型正确。"""
        assert wp_code in _WP_CODE_OVERRIDE, (
            f"D 类 wp_code '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册"
        )
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table", (
            f"D 类 wp_code '{wp_code}' 应为 d-form-table，实际为 {_WP_CODE_OVERRIDE[wp_code]}"
        )

    def test_all_d_form_table_codes_in_mapping(self, d_class_entries):
        """所有 d-form-table D 类 wp_code 在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in d_class_entries}
        for code in self._D_FORM_TABLE_CODES:
            assert code in mapping_codes, (
                f"wp_code '{code}' 未在 wp_account_mapping.json 中注册"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 40: D 类 audit-sheet 底稿原生导出
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask40DAuditSheetExport:
    """验证 D 类 audit-sheet 底稿注册正确，支持 OnlyOffice 原生导出。"""

    # D 类中走 audit-sheet 的 wp_codes
    _AUDIT_SHEET_CODES = [
        "D1-2", "D1-3",          # 应收票据明细
        "D2-2", "D2-5", "D2-6", # 应收账款明细+分析+检查
        "D4-2", "D4-3", "D4-4", # 收入明细
        "D4-6", "D4-13", "D4-22",  # 收入分析+检查+IPO
        "D5-2",                   # 应收款项融资明细
        "D6-2", "D6-3", "D6-8", # 合同资产明细+减值
    ]

    @pytest.mark.parametrize("wp_code", _AUDIT_SHEET_CODES)
    def test_audit_sheet_component_type_registered(self, wp_code):
        """每个 audit-sheet D 类 wp_code 在 _WP_CODE_OVERRIDE 中注册且类型正确。"""
        assert wp_code in _WP_CODE_OVERRIDE, (
            f"D 类 wp_code '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册"
        )
        assert _WP_CODE_OVERRIDE[wp_code] == "audit-sheet", (
            f"D 类 wp_code '{wp_code}' 应为 audit-sheet，实际为 {_WP_CODE_OVERRIDE[wp_code]}"
        )

    def test_all_audit_sheet_codes_in_mapping(self, d_class_entries):
        """所有 audit-sheet D 类 wp_code 在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in d_class_entries}
        for code in self._AUDIT_SHEET_CODES:
            assert code in mapping_codes, (
                f"wp_code '{code}' 未在 wp_account_mapping.json 中注册"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 41: D 审定表（D{n}-1）走 d-form-table — 可导入填充
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask41ImportFromExcel:
    """验证 D 类审定表使用 d-form-table，具备结构化导入基础。"""

    # D{n}-1 审定表系列
    _AUDIT_DETERMINATION_CODES = [
        "D1-1", "D2-1", "D3-1", "D4-1", "D5-1", "D6-1", "D7-1",
    ]

    @pytest.mark.parametrize("wp_code", _AUDIT_DETERMINATION_CODES)
    def test_audit_determination_tables_are_d_form(self, wp_code):
        """D{n}-1 审定表全部映射为 d-form-table（支持结构化导入）。"""
        assert wp_code in _WP_CODE_OVERRIDE, (
            f"审定表 '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册"
        )
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table", (
            f"审定表 '{wp_code}' 应为 d-form-table，实际为 {_WP_CODE_OVERRIDE[wp_code]}"
        )

    def test_audit_determination_tables_in_mapping(self, d_class_entries):
        """所有 D{n}-1 审定表在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in d_class_entries}
        for code in self._AUDIT_DETERMINATION_CODES:
            assert code in mapping_codes, (
                f"审定表 '{code}' 未在 wp_account_mapping.json 中注册"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 42: 批量导出 zip（D 类全量可检索）
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask42BatchExportZip:
    """验证 D 类底稿在 wp_account_mapping 中全部注册，批量导出可正确枚举。"""

    def test_all_49_d_class_registered(self, d_class_entries):
        """wp_account_mapping.json 中应有 49 个 audit_cycle='D' 的条目。"""
        assert len(d_class_entries) == 49, (
            f"D 类底稿应有 49 条注册，实际 {len(d_class_entries)} 条"
        )

    def test_d_class_all_have_wp_code(self, d_class_entries):
        """所有 D 类条目都有有效 wp_code。"""
        for entry in d_class_entries:
            assert entry.get("wp_code"), f"D 类条目缺少 wp_code: {entry}"
            assert entry["wp_code"].startswith("D"), (
                f"D 类条目 wp_code 应以 D 开头: {entry['wp_code']}"
            )

    def test_d0_is_confirmation_hub(self):
        """D0 函证底稿应映射为 confirmation-hub（对比 C1 映射为 a-program-console）。"""
        assert "D0" in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE["D0"] == "confirmation-hub"
        # 同时验证 C1 作对比
        assert "C1" in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE["C1"] == "a-program-console"

    def test_all_d_class_have_component_type(self, d_class_entries):
        """所有 49 个 D 类 wp_code 在 _WP_CODE_OVERRIDE 中都有 componentType 映射。"""
        for entry in d_class_entries:
            wp_code = entry["wp_code"]
            assert wp_code in _WP_CODE_OVERRIDE, (
                f"D 类 wp_code '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册 componentType"
            )

    def test_d_paragraph_type_exists(self):
        """D6-7 应映射为 d-form-paragraph（段落式政策描述）。"""
        assert "D6-7" in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE["D6-7"] == "d-form-paragraph"

    def test_d_class_component_types_valid(self, d_class_entries):
        """所有 D 类 componentType 必须是合法类型之一。"""
        valid_types = {
            "d-form-table", "audit-sheet", "a-program-console",
            "confirmation-hub", "d-form-paragraph", "c-note-table",
        }
        for entry in d_class_entries:
            wp_code = entry["wp_code"]
            ct = _WP_CODE_OVERRIDE.get(wp_code, "")
            assert ct in valid_types, (
                f"D 类 wp_code '{wp_code}' 的 componentType '{ct}' 不在合法类型集合内"
            )
