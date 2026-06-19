"""C 类底稿导入导出基础设施验证。

验证 tasks 34-37:
  34. C 类 d-form-table 底稿导出为 Excel（复用通用 d-form-table 导出逻辑）
  35. C22 OnlyOffice 原生导出（复用 audit-sheet 通用导出）
  36. 从 Excel 导入填充已有结构化 C 类底稿
  37. 批量导出 C 类全量打包 zip（项目归档场景）

验证方式：
  - 确认所有 C 类 wp_code 正确注册在 wp_account_mapping.json
  - 确认 componentType 映射正确（d-form-table / audit-sheet / a-program-console）
  - 确认 d-form-table 类型的 C 类底稿可被通用导出逻辑处理
  - 确认 C22 audit-sheet 类型注册正确
  - 确认批量导出时 C 类底稿在 audit_cycle="C" 下可被检索
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.wp_classification_service import (
    _WP_CODE_OVERRIDE,
    derive_component_type,
)

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
def c_class_entries(wp_mapping) -> list[dict]:
    """筛选 cycle == 'C' 的全部条目。"""
    return [e for e in wp_mapping if e.get("cycle") == "C"]


# ═══════════════════════════════════════════════════════════════════════════════
# Task 34: C 类 d-form-table 底稿可被通用导出逻辑覆盖
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask34DFormTableExport:
    """验证 C 类 d-form-table 底稿能被通用 Excel 导出基础设施支持。"""

    # C 类中走 d-form-table 的 wp_codes
    _D_FORM_TABLE_CODES = [
        "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9",
        "C10", "C11", "C12", "C13", "C14", "C15",
        "C2-2", "C3-2", "C4-2", "C5-2", "C6-2", "C7-2", "C8-2", "C9-2",
        "C10-2", "C11-2", "C12-2", "C13-2", "C14-2", "C15-2",
        "C21", "C21-1", "C23", "C24", "C25", "C26",
    ]

    @pytest.mark.parametrize("wp_code", _D_FORM_TABLE_CODES)
    def test_d_form_table_component_type_registered(self, wp_code):
        """每个 d-form-table C 类 wp_code 在 _WP_CODE_OVERRIDE 中注册且类型正确。"""
        assert wp_code in _WP_CODE_OVERRIDE, (
            f"C 类 wp_code '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册"
        )
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table", (
            f"C 类 wp_code '{wp_code}' 应为 d-form-table，实际为 {_WP_CODE_OVERRIDE[wp_code]}"
        )

    def test_all_d_form_table_codes_in_mapping(self, c_class_entries):
        """所有 d-form-table C 类 wp_code 在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in c_class_entries}
        for code in self._D_FORM_TABLE_CODES:
            assert code in mapping_codes, (
                f"wp_code '{code}' 未在 wp_account_mapping.json 中注册"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 35: C22 OnlyOffice 原生导出
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask35C22AuditSheetExport:
    """验证 C22 使用 audit-sheet componentType，支持 OnlyOffice 原生导出。"""

    def test_c22_is_audit_sheet(self):
        """C22 应注册为 audit-sheet componentType。"""
        assert "C22" in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE["C22"] == "audit-sheet"

    def test_c22_in_mapping_with_correct_cycle(self, c_class_entries):
        """C22 在 wp_account_mapping.json 中注册且 cycle='C'。"""
        c22 = next((e for e in c_class_entries if e["wp_code"] == "C22"), None)
        assert c22 is not None, "C22 未在 wp_account_mapping.json 中注册"
        assert c22["cycle"] == "C"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 36: 从 Excel 导入填充（结构验证）
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask36ImportFromExcel:
    """验证 C 类底稿的 YAML schema 存在，支持结构化导入。"""

    def test_c_generic_yaml_exists(self):
        """C-generic.yaml 存在，d-form-table 导入基础设施可用。"""
        schema_dir = (
            Path(__file__).resolve().parent.parent
            / "data" / "ledger_adapters" / "wp_render_schema"
        )
        generic_path = schema_dir / "C-generic.yaml"
        assert generic_path.exists(), "C-generic.yaml 不存在"

    def test_c_deviation_generic_yaml_exists(self):
        """C-deviation-generic.yaml 存在，偏差评价导入基础设施可用。"""
        schema_dir = (
            Path(__file__).resolve().parent.parent
            / "data" / "ledger_adapters" / "wp_render_schema"
        )
        deviation_path = schema_dir / "C-deviation-generic.yaml"
        assert deviation_path.exists(), "C-deviation-generic.yaml 不存在"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 37: 批量导出 zip（C 类全量可检索）
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask37BatchExportZip:
    """验证 C 类底稿在 wp_account_mapping 中全部注册，批量导出可正确枚举。"""

    def test_all_36_c_class_registered(self, c_class_entries):
        """wp_account_mapping.json 中应有 36 个 audit_cycle='C' 的条目。"""
        assert len(c_class_entries) == 36, (
            f"C 类底稿应有 36 条注册，实际 {len(c_class_entries)} 条"
        )

    def test_c_class_all_have_wp_code(self, c_class_entries):
        """所有 C 类条目都有有效 wp_code。"""
        for entry in c_class_entries:
            assert entry.get("wp_code"), f"C 类条目缺少 wp_code: {entry}"
            assert entry["wp_code"].startswith("C"), (
                f"C 类条目 wp_code 应以 C 开头: {entry['wp_code']}"
            )

    def test_c1_is_program_console(self):
        """C1 企业层面控制测试应为 a-program-console。"""
        assert "C1" in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE["C1"] == "a-program-console"

    def test_all_c_class_have_component_type(self, c_class_entries):
        """所有 C 类 wp_code 在 _WP_CODE_OVERRIDE 中都有 componentType 映射。"""
        for entry in c_class_entries:
            wp_code = entry["wp_code"]
            assert wp_code in _WP_CODE_OVERRIDE, (
                f"C 类 wp_code '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册 componentType"
            )
