"""E 类 address_registry seed 加载验证。

验证：
  1. e_address_registry_seed.json 结构完整性
  2. 所有 wp_code 在 _WP_CODE_OVERRIDE 中有对应 audit-sheet 映射
  3. coordinates 字段格式正确
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# Fixture: 加载 seed JSON
# ═══════════════════════════════════════════════════════════════════════════════

SEED_PATH = Path(__file__).parent.parent / "data" / "e_address_registry_seed.json"


@pytest.fixture(scope="module")
def seed_data() -> dict:
    """加载 E 类 address_registry seed 文件。"""
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
