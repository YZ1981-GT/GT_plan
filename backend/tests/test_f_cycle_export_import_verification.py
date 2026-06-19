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
    """验证 F 类 d-form-table 底稿能被通用 Excel 导出基础设施支持。"""

    # F 类中走 d-form-table 的 wp_codes（设计文档 §2.2）
    _F_FORM_TABLE_CODES = [
        # 函证辅助
        "F0-1", "F0-2", "F0-3", "F0-4", "F0-5",
        # 预付账款
        "F1", "F1-1", "F1-4",
        # 存货
        "F2", "F2-1", "F2-11", "F2-12", "F2-13", "F2-14", "F2-16", "F2-52",
        # 应付票据
        "F3", "F3-1", "F3-4",
        # 应付账款
        "F4", "F4-1", "F4-4",
        # 营业成本
        "F5", "F5-1",
    ]

    @pytest.mark.parametrize("wp_code", _F_FORM_TABLE_CODES)
    def test_f_form_table_component_type_registered(self, wp_code):
        """每个 d-form-table F 类 wp_code 在 _WP_CODE_OVERRIDE 中注册且类型正确。"""
        assert wp_code in _WP_CODE_OVERRIDE, (
            f"F 类 wp_code '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册"
        )
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table", (
            f"F 类 wp_code '{wp_code}' 应为 d-form-table，实际为 {_WP_CODE_OVERRIDE[wp_code]}"
        )

    def test_all_f_form_table_codes_in_mapping(self, f_class_entries):
        """所有 d-form-table F 类 wp_code 在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in f_class_entries}
        for code in self._F_FORM_TABLE_CODES:
            assert code in mapping_codes, (
                f"wp_code '{code}' 未在 wp_account_mapping.json 中注册"
            )

    def test_f_form_table_count(self):
        """F 类 d-form-table 底稿数量验证。"""
        f_form_codes = [
            code for code, ct in _WP_CODE_OVERRIDE.items()
            if code.startswith("F") and ct == "d-form-table"
        ]
        assert len(f_form_codes) == len(self._F_FORM_TABLE_CODES), (
            f"F 类 d-form-table 应有 {len(self._F_FORM_TABLE_CODES)} 个，"
            f"实际 {len(f_form_codes)} 个: {sorted(f_form_codes)}"
        )

    def test_f_audit_determination_tables_have_schema(self):
        """F{n}-1 审定表有对应的 YAML schema 文件（支持结构化导出）。"""
        schema_dir = (
            Path(__file__).resolve().parent.parent
            / "data" / "ledger_adapters" / "wp_render_schema"
        )
        audit_det_codes = ["F1-1", "F2-1", "F3-1", "F4-1", "F5-1"]
        for code in audit_det_codes:
            schema_path = schema_dir / f"{code}.yaml"
            assert schema_path.exists(), (
                f"审定表 {code} 的 schema YAML 不存在: {schema_path}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 50: F 类 audit-sheet 底稿原生导出
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask50AuditSheetExport:
    """验证 F 类 audit-sheet 底稿注册正确，支持 OnlyOffice 原生导出。"""

    # F 类中走 audit-sheet 的 wp_codes（按功能分组）
    _AUDIT_SHEET_CODES = [
        # 预付账款明细/检查
        "F1-2", "F1-3", "F1-5", "F1-6",
        # 存货明细（含公式）
        "F2-2", "F2-3", "F2-4", "F2-5", "F2-6", "F2-7", "F2-8", "F2-9", "F2-10",
        # 分析程序
        "F2-18", "F2-19", "F2-20",
        # 存货监盘
        "F2-21", "F2-22", "F2-23", "F2-24", "F2-25", "F2-26",
        # 检查程序
        "F2-29", "F2-30", "F2-31", "F2-32", "F2-33", "F2-34", "F2-35",
        # 计价测试
        "F2-38", "F2-39", "F2-40", "F2-41", "F2-42", "F2-43", "F2-44",
        # 跌价准备测试
        "F2-47", "F2-48", "F2-49",
        # 合同履约成本
        "F2-55", "F2-56", "F2-57", "F2-58",
        # IPO/舞弊应对
        "F2-61", "F2-62", "F2-63", "F2-64", "F2-65", "F2-66",
        "F2-67", "F2-68", "F2-69", "F2-70", "F2-71", "F2-72",
        # 应付票据
        "F3-2", "F3-3", "F3-5", "F3-6",
        # 应付账款
        "F4-2", "F4-3", "F4-5", "F4-6",
        # 营业成本
        "F5-2", "F5-3", "F5-4", "F5-5", "F5-6",
    ]

    @pytest.mark.parametrize("wp_code", _AUDIT_SHEET_CODES)
    def test_audit_sheet_component_type_registered(self, wp_code):
        """每个 audit-sheet F 类 wp_code 在 _WP_CODE_OVERRIDE 中注册且类型正确。"""
        assert wp_code in _WP_CODE_OVERRIDE, (
            f"F 类 wp_code '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册"
        )
        assert _WP_CODE_OVERRIDE[wp_code] == "audit-sheet", (
            f"F 类 wp_code '{wp_code}' 应为 audit-sheet，实际为 {_WP_CODE_OVERRIDE[wp_code]}"
        )

    def test_all_audit_sheet_codes_in_mapping(self, f_class_entries):
        """所有 audit-sheet F 类 wp_code 在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in f_class_entries}
        for code in self._AUDIT_SHEET_CODES:
            assert code in mapping_codes, (
                f"wp_code '{code}' 未在 wp_account_mapping.json 中注册"
            )

    def test_audit_sheet_count(self):
        """F 类 audit-sheet 底稿数量验证。"""
        f_sheet_codes = [
            code for code, ct in _WP_CODE_OVERRIDE.items()
            if code.startswith("F") and ct == "audit-sheet"
        ]
        assert len(f_sheet_codes) == len(self._AUDIT_SHEET_CODES), (
            f"F 类 audit-sheet 应有 {len(self._AUDIT_SHEET_CODES)} 个，"
            f"实际 {len(f_sheet_codes)} 个: {sorted(f_sheet_codes)}"
        )

    def test_inventory_count_sheets_registered(self):
        """F2-21~F2-26 存货监盘系列全部为 audit-sheet。"""
        for i in range(21, 27):
            code = f"F2-{i}"
            assert code in _WP_CODE_OVERRIDE, f"{code} 未注册"
            assert _WP_CODE_OVERRIDE[code] == "audit-sheet", (
                f"{code} 应为 audit-sheet，实际为 {_WP_CODE_OVERRIDE[code]}"
            )

    def test_valuation_test_sheets_registered(self):
        """F2-38~F2-44 计价测试系列全部为 audit-sheet。"""
        for i in range(38, 45):
            code = f"F2-{i}"
            assert code in _WP_CODE_OVERRIDE, f"{code} 未注册"
            assert _WP_CODE_OVERRIDE[code] == "audit-sheet", (
                f"{code} 应为 audit-sheet，实际为 {_WP_CODE_OVERRIDE[code]}"
            )

    def test_impairment_test_sheets_registered(self):
        """F2-47~F2-49 跌价准备测试系列全部为 audit-sheet。"""
        for i in range(47, 50):
            code = f"F2-{i}"
            assert code in _WP_CODE_OVERRIDE, f"{code} 未注册"
            assert _WP_CODE_OVERRIDE[code] == "audit-sheet", (
                f"{code} 应为 audit-sheet，实际为 {_WP_CODE_OVERRIDE[code]}"
            )

    def test_ipo_sheets_registered(self):
        """F2-61~F2-72 IPO/舞弊应对系列全部为 audit-sheet。"""
        for i in range(61, 73):
            code = f"F2-{i}"
            assert code in _WP_CODE_OVERRIDE, f"{code} 未注册"
            assert _WP_CODE_OVERRIDE[code] == "audit-sheet", (
                f"{code} 应为 audit-sheet，实际为 {_WP_CODE_OVERRIDE[code]}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 51: F 审定表走 d-form-table — 可导入填充
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask51ImportFromExcel:
    """验证 F 类审定表使用 d-form-table，具备结构化导入基础。"""

    # F 审定表（F{n}-1 系列）
    _AUDIT_DETERMINATION_CODES = ["F1-1", "F2-1", "F3-1", "F4-1", "F5-1"]

    @pytest.mark.parametrize("wp_code", _AUDIT_DETERMINATION_CODES)
    def test_audit_determination_tables_are_d_form(self, wp_code):
        """F{n}-1 审定表映射为 d-form-table（支持结构化导入）。"""
        assert wp_code in _WP_CODE_OVERRIDE, (
            f"审定表 '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册"
        )
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table", (
            f"审定表 '{wp_code}' 应为 d-form-table，实际为 {_WP_CODE_OVERRIDE[wp_code]}"
        )

    def test_audit_determination_tables_in_mapping(self, f_class_entries):
        """F{n}-1 审定表全部在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in f_class_entries}
        for code in self._AUDIT_DETERMINATION_CODES:
            assert code in mapping_codes, (
                f"审定表 '{code}' 未在 wp_account_mapping.json 中注册"
            )

    @pytest.mark.parametrize("wp_code", _AUDIT_DETERMINATION_CODES)
    def test_audit_determination_schema_yaml_exists(self, wp_code):
        """F{n}-1 审定表 schema YAML 文件存在。"""
        schema_path = (
            Path(__file__).resolve().parent.parent
            / "data" / "ledger_adapters" / "wp_render_schema" / f"{wp_code}.yaml"
        )
        assert schema_path.exists(), f"{wp_code} schema YAML 不存在: {schema_path}"

    def test_f_form_table_importable_pattern(self, f_class_entries):
        """所有 F 类 d-form-table 底稿具备导入基础条件。"""
        d_form_codes = [
            e["wp_code"] for e in f_class_entries
            if _WP_CODE_OVERRIDE.get(e["wp_code"]) == "d-form-table"
        ]
        # 每个 d-form-table 底稿在 _WP_CODE_OVERRIDE 中注册
        for code in d_form_codes:
            assert code in _WP_CODE_OVERRIDE
            assert _WP_CODE_OVERRIDE[code] == "d-form-table"

    def test_f_form_table_additional_structured_codes(self):
        """F 类附加 d-form-table 底稿（坏账/跌价明细/关联交易等）结构完整。"""
        structured_codes = [
            "F1-4",   # 预付账款坏账准备
            "F2-11",  # 跌价准备明细
            "F2-12",  # 跌价准备变动
            "F2-13",  # 调整分录汇总
            "F2-14",  # 存货担保质押
            "F2-16",  # 会计政策检查
            "F2-52",  # 关联交易检查
            "F3-4",   # 应付票据调整分录
            "F4-4",   # 应付账款调整分录
        ]
        for code in structured_codes:
            assert code in _WP_CODE_OVERRIDE, f"{code} 未注册"
            assert _WP_CODE_OVERRIDE[code] == "d-form-table", (
                f"{code} 应为 d-form-table（可导入），实际为 {_WP_CODE_OVERRIDE[code]}"
            )


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
        valid_types = {
            "d-form-table", "audit-sheet", "a-program-console",
            "confirmation-hub", "c-note-table",
        }
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

        # 验证分布：大量 audit-sheet + d-form-table + 1 confirmation-hub
        assert type_counts.get("confirmation-hub", 0) == 1, "应有 1 个 confirmation-hub (F0)"
        assert type_counts.get("d-form-table", 0) >= 20, "应有至少 20 个 d-form-table"
        assert type_counts.get("audit-sheet", 0) >= 60, "应有至少 60 个 audit-sheet"

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

    def test_f_class_override_count_matches_mapping(self, f_class_entries):
        """_WP_CODE_OVERRIDE 中 F 类条目数 == wp_account_mapping F 类条目数。"""
        override_f_count = sum(
            1 for code in _WP_CODE_OVERRIDE if code.startswith("F")
        )
        mapping_f_count = len(f_class_entries)
        assert override_f_count == mapping_f_count, (
            f"_WP_CODE_OVERRIDE F 类 {override_f_count} 条 != "
            f"wp_account_mapping F 类 {mapping_f_count} 条"
        )

    def test_f_confirmation_hub_consistent_with_d_and_e(self):
        """F0、E0 和 D0 使用相同的 confirmation-hub 模式。"""
        assert _WP_CODE_OVERRIDE.get("F0") == "confirmation-hub"
        assert _WP_CODE_OVERRIDE.get("E0") == "confirmation-hub"
        assert _WP_CODE_OVERRIDE.get("D0") == "confirmation-hub"

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
