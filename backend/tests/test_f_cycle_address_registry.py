"""F 类 address_registry seed 加载验证。

验证：
  1. f_address_registry_seed.json 结构完整性
  2. 所有 wp_code 在 _WP_CODE_OVERRIDE 中有对应 audit-sheet 映射
  3. coordinates 字段格式正确
  4. 无重复 wp_code
  5. purpose 值在预定义范围内
  6. 覆盖设计文档要求的全部 wp_code 范围
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# Fixture: 加载 seed JSON
# ═══════════════════════════════════════════════════════════════════════════════

SEED_PATH = Path(__file__).parent.parent / "data" / "f_address_registry_seed.json"


@pytest.fixture(scope="module")
def seed_data() -> dict:
    """加载 F 类 address_registry seed 文件。"""
    assert SEED_PATH.exists(), f"Seed 文件不存在: {SEED_PATH}"
    with open(SEED_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data


# ═══════════════════════════════════════════════════════════════════════════════
# Test 1: 顶层结构
# ═══════════════════════════════════════════════════════════════════════════════


def test_seed_top_level_structure(seed_data: dict):
    """seed JSON 包含必要的顶层字段。"""
    assert "version" in seed_data
    assert "entries" in seed_data
    assert "description" in seed_data
    assert "cycle" in seed_data
    assert seed_data["cycle"] == "F"
    assert isinstance(seed_data["entries"], list)
    assert len(seed_data["entries"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Test 2: 每个 entry 结构完整
# ═══════════════════════════════════════════════════════════════════════════════


def test_seed_entries_have_required_fields(seed_data: dict):
    """每个 entry 包含 wp_code, sheet_name, coordinates 必要字段。"""
    for entry in seed_data["entries"]:
        assert "wp_code" in entry, f"entry 缺少 wp_code: {entry}"
        assert "sheet_name" in entry, f"entry 缺少 sheet_name: {entry}"
        assert "coordinates" in entry, f"entry 缺少 coordinates: {entry}"
        assert isinstance(entry["coordinates"], list), (
            f"{entry['wp_code']} coordinates 不是列表"
        )
        assert len(entry["coordinates"]) > 0, (
            f"{entry['wp_code']} coordinates 为空"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 3: coordinates 字段格式
# ═══════════════════════════════════════════════════════════════════════════════


def test_seed_coordinates_format(seed_data: dict):
    """每个 coordinate 包含 cell_address, description, purpose。"""
    for entry in seed_data["entries"]:
        for coord in entry["coordinates"]:
            assert "cell_address" in coord, (
                f"{entry['wp_code']} coordinate 缺少 cell_address"
            )
            assert "description" in coord, (
                f"{entry['wp_code']} coordinate 缺少 description"
            )
            assert "purpose" in coord, (
                f"{entry['wp_code']} coordinate 缺少 purpose"
            )
            # cell_address 格式：字母+数字 (如 A1, F99, AA100)
            addr = coord["cell_address"]
            assert len(addr) >= 2, f"cell_address 太短: {addr}"
            assert addr[0].isalpha(), f"cell_address 应以字母开头: {addr}"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 4: wp_code 匹配 _WP_CODE_OVERRIDE 中的 audit-sheet 类型
# ═══════════════════════════════════════════════════════════════════════════════


def test_seed_wp_codes_are_audit_sheet_type(seed_data: dict):
    """所有 seed 中的 wp_code 在 _WP_CODE_OVERRIDE 中映射为 audit-sheet。"""
    from app.services.wp_classification_service import _WP_CODE_OVERRIDE

    for entry in seed_data["entries"]:
        wp_code = entry["wp_code"]
        assert wp_code in _WP_CODE_OVERRIDE, (
            f"wp_code '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册"
        )
        component_type = _WP_CODE_OVERRIDE[wp_code]
        assert component_type == "audit-sheet", (
            f"wp_code '{wp_code}' componentType 应为 'audit-sheet'，"
            f"实际为 '{component_type}'"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 5: 无重复 wp_code
# ═══════════════════════════════════════════════════════════════════════════════


def test_seed_no_duplicate_wp_codes(seed_data: dict):
    """seed 中不应有重复的 wp_code。"""
    codes = [entry["wp_code"] for entry in seed_data["entries"]]
    duplicates = [c for c in codes if codes.count(c) > 1]
    assert not duplicates, f"发现重复 wp_code: {set(duplicates)}"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 6: purpose 值在预定义范围内
# ═══════════════════════════════════════════════════════════════════════════════

VALID_PURPOSES = {
    "balance_verification",
    "conclusion",
    "ratio_analysis",
    "reconciliation_result",
    "interest_calculation",
    "interest_difference",
    "impairment_calc",
    "assumption",
    "aging_analysis",
    "inventory_count",
    "valuation_test",
}


def test_seed_coordinate_purposes_valid(seed_data: dict):
    """每个 coordinate 的 purpose 属于预定义有效值集合。"""
    for entry in seed_data["entries"]:
        for coord in entry["coordinates"]:
            purpose = coord["purpose"]
            assert purpose in VALID_PURPOSES, (
                f"{entry['wp_code']} coordinate purpose '{purpose}' "
                f"不在有效集合中: {VALID_PURPOSES}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 7: 覆盖设计文档中的关键 wp_code 范围
# ═══════════════════════════════════════════════════════════════════════════════

REQUIRED_WP_CODES = {
    # F1 预付账款明细
    "F1-2", "F1-3",
    # F2 存货各类明细
    "F2-2", "F2-3", "F2-4", "F2-5", "F2-6", "F2-7", "F2-8", "F2-9", "F2-10",
    # F2 分析程序
    "F2-18", "F2-19", "F2-20",
    # F2 存货监盘
    "F2-21", "F2-22", "F2-23", "F2-24", "F2-25", "F2-26",
    # F2 检查程序
    "F2-29", "F2-30", "F2-31", "F2-32", "F2-33", "F2-34", "F2-35",
    # F2 计价测试
    "F2-38", "F2-39", "F2-40", "F2-41", "F2-42", "F2-43", "F2-44",
    # F2 跌价准备测试
    "F2-47", "F2-48", "F2-49",
    # F2 合同履约成本
    "F2-55", "F2-56", "F2-57", "F2-58",
    # F2 IPO 底稿
    "F2-61", "F2-62", "F2-63", "F2-64", "F2-65", "F2-66",
    "F2-67", "F2-68", "F2-69", "F2-70", "F2-71", "F2-72",
    # F3 应付票据
    "F3-2", "F3-5", "F3-6",
    # F4 应付账款
    "F4-2", "F4-3",
    # F5 营业成本
    "F5-2", "F5-3", "F5-4",
}


def test_seed_covers_required_wp_codes(seed_data: dict):
    """seed 覆盖设计文档要求的全部 wp_code。"""
    registered_codes = {entry["wp_code"] for entry in seed_data["entries"]}
    missing = REQUIRED_WP_CODES - registered_codes
    assert not missing, (
        f"seed 缺少以下设计文档要求的 wp_code: {sorted(missing)}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 8: wp_code 均以 F 开头
# ═══════════════════════════════════════════════════════════════════════════════


def test_seed_all_wp_codes_start_with_f(seed_data: dict):
    """所有 wp_code 必须以 F 开头（F 循环）。"""
    for entry in seed_data["entries"]:
        assert entry["wp_code"].startswith("F"), (
            f"wp_code '{entry['wp_code']}' 不以 F 开头"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 9: sheet_name 非空且合理
# ═══════════════════════════════════════════════════════════════════════════════


def test_seed_sheet_names_non_empty(seed_data: dict):
    """每个 entry 的 sheet_name 非空且长度合理。"""
    for entry in seed_data["entries"]:
        name = entry["sheet_name"]
        assert isinstance(name, str) and len(name) >= 2, (
            f"{entry['wp_code']} sheet_name 过短或为空: '{name}'"
        )
