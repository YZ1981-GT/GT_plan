"""K 类 address_registry seed 加载验证。

验证：
  26. k_address_registry_seed.json 结构完整性
  27. K1-2/K1-3 其他应收款明细+账龄坐标
  28. K3-2/K3-3 其他应付款明细+账龄坐标
  29. K5-4 预计负债最佳估计数坐标
  30. K8-2/K8-3/K9-2/K9-3 费用明细+分析坐标
  31. 验证 seed 加载 + custom_query 正确读取
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# Fixture: 加载 seed JSON
# ═══════════════════════════════════════════════════════════════════════════════

SEED_PATH = Path(__file__).parent.parent / "data" / "k_address_registry_seed.json"


@pytest.fixture(scope="module")
def seed_data() -> dict:
    """加载 K 类 address_registry seed 文件。"""
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
    assert seed_data["cycle"] == "K"
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
    "receivable_detail",
    "aging_analysis",
    "aging_total",
    "payable_detail",
    "best_estimate",
    "best_estimate_variance",
    "expense_detail",
    "expense_variance",
    "expense_trend",
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

REQUIRED_WP_CODES = {"K1-2", "K1-3", "K3-2", "K3-3", "K5-4", "K8-2", "K8-3", "K9-2", "K9-3"}


def test_seed_covers_required_wp_codes(seed_data: dict):
    """seed 必须包含 K1-2/K1-3/K3-2/K3-3/K5-4/K8-2/K8-3/K9-2/K9-3 九个底稿。"""
    registered_codes = {entry["wp_code"] for entry in seed_data["entries"]}
    missing = REQUIRED_WP_CODES - registered_codes
    assert not missing, f"缺少必要的 wp_code 注册: {missing}"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 8: custom_query 可正确读取坐标
# ═══════════════════════════════════════════════════════════════════════════════


def test_seed_custom_query_lookup(seed_data: dict):
    """模拟 custom_query 按 wp_code + purpose 查找坐标。"""
    registry: dict[str, dict[str, list]] = {}
    for entry in seed_data["entries"]:
        wp_code = entry["wp_code"]
        registry[wp_code] = {}
        for coord in entry["coordinates"]:
            purpose = coord["purpose"]
            if purpose not in registry[wp_code]:
                registry[wp_code][purpose] = []
            registry[wp_code][purpose].append(coord["cell_address"])

    # K1-2 其他应收款明细：4 cells
    assert "K1-2" in registry
    assert len(registry["K1-2"]["receivable_detail"]) == 4

    # K1-3 其他应收款账龄：aging_analysis (4) + aging_total (1)
    assert "K1-3" in registry
    assert len(registry["K1-3"]["aging_analysis"]) == 4
    assert len(registry["K1-3"]["aging_total"]) == 1

    # K3-2 其他应付款明细：4 cells
    assert "K3-2" in registry
    assert len(registry["K3-2"]["payable_detail"]) == 4

    # K3-3 其他应付款账龄：aging_analysis (4) + aging_total (1)
    assert "K3-3" in registry
    assert len(registry["K3-3"]["aging_analysis"]) == 4
    assert len(registry["K3-3"]["aging_total"]) == 1

    # K5-4 最佳估计数：best_estimate (4) + best_estimate_variance (1)
    assert "K5-4" in registry
    assert len(registry["K5-4"]["best_estimate"]) == 4
    assert len(registry["K5-4"]["best_estimate_variance"]) == 1

    # K8-2 销售费用明细：expense_detail (3) + expense_variance (1)
    assert "K8-2" in registry
    assert len(registry["K8-2"]["expense_detail"]) == 3
    assert len(registry["K8-2"]["expense_variance"]) == 1

    # K8-3 销售费用分析：expense_trend (4)
    assert "K8-3" in registry
    assert len(registry["K8-3"]["expense_trend"]) == 4

    # K9-2 管理费用明细：expense_detail (3) + expense_variance (1)
    assert "K9-2" in registry
    assert len(registry["K9-2"]["expense_detail"]) == 3
    assert len(registry["K9-2"]["expense_variance"]) == 1

    # K9-3 管理费用分析：expense_trend (4)
    assert "K9-3" in registry
    assert len(registry["K9-3"]["expense_trend"]) == 4
