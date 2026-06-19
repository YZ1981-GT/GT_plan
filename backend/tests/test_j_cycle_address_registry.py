"""J 类 address_registry seed 加载验证。

验证：
  1. j_address_registry_seed.json 结构完整性
  2. 所有 wp_code 在 _WP_CODE_OVERRIDE 中有对应 audit-sheet 映射
  3. coordinates 字段格式正确
  4. 覆盖 J1-3/J1-4/J2-5/J3-4/J3-5 五个底稿坐标注册
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# Fixture: 加载 seed JSON
# ═══════════════════════════════════════════════════════════════════════════════

SEED_PATH = Path(__file__).parent.parent / "data" / "j_address_registry_seed.json"


@pytest.fixture(scope="module")
def seed_data() -> dict:
    """加载 J 类 address_registry seed 文件。"""
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
    assert seed_data["cycle"] == "J"
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
    # J1-3 工资测算
    "wage_calculation",
    "wage_variance",
    # J1-4 社保测算
    "social_insurance_calc",
    "social_insurance_variance",
    # J2-5 精算重算
    "actuarial_calc",
    "actuarial_net_liability",
    # J3-4 期权定价
    "option_pricing",
    # J3-5 等待期费用分摊
    "vesting_expense",
    "vesting_expense_calc",
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
# Test 7: 覆盖所有必需底稿
# ═══════════════════════════════════════════════════════════════════════════════

REQUIRED_WP_CODES = {"J1-3", "J1-4", "J2-5", "J3-4", "J3-5"}


def test_seed_covers_required_wp_codes(seed_data: dict):
    """seed 必须包含 J1-3/J1-4/J2-5/J3-4/J3-5 五个底稿。"""
    registered_codes = {entry["wp_code"] for entry in seed_data["entries"]}
    missing = REQUIRED_WP_CODES - registered_codes
    assert not missing, f"缺少必要的 wp_code 注册: {missing}"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 8: custom_query 可正确读取坐标
# ═══════════════════════════════════════════════════════════════════════════════


def test_seed_custom_query_lookup(seed_data: dict):
    """模拟 custom_query 按 wp_code + purpose 查找坐标。"""
    # 构建 lookup 索引（模拟 address_registry 加载后的内存结构）
    registry: dict[str, dict[str, list]] = {}
    for entry in seed_data["entries"]:
        wp_code = entry["wp_code"]
        registry[wp_code] = {}
        for coord in entry["coordinates"]:
            purpose = coord["purpose"]
            if purpose not in registry[wp_code]:
                registry[wp_code][purpose] = []
            registry[wp_code][purpose].append(coord["cell_address"])

    # J1-3 工资测算：应有 wage_calculation (3 cells) + wage_variance (1 cell)
    assert "J1-3" in registry
    assert len(registry["J1-3"]["wage_calculation"]) == 3
    assert len(registry["J1-3"]["wage_variance"]) == 1

    # J1-4 社保测算：应有 social_insurance_calc (3 cells) + variance (1 cell)
    assert "J1-4" in registry
    assert len(registry["J1-4"]["social_insurance_calc"]) == 3
    assert len(registry["J1-4"]["social_insurance_variance"]) == 1

    # J2-5 精算重算：actuarial_calc (4 cells) + net_liability (1 cell)
    assert "J2-5" in registry
    assert len(registry["J2-5"]["actuarial_calc"]) == 4
    assert len(registry["J2-5"]["actuarial_net_liability"]) == 1

    # J3-4 期权定价：option_pricing (6 cells)
    assert "J3-4" in registry
    assert len(registry["J3-4"]["option_pricing"]) == 6

    # J3-5 等待期费用分摊：vesting_expense (3) + vesting_expense_calc (1)
    assert "J3-5" in registry
    assert len(registry["J3-5"]["vesting_expense"]) == 3
    assert len(registry["J3-5"]["vesting_expense_calc"]) == 1
