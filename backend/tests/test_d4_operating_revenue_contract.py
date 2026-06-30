"""D4 营业收入注册契约测试 — 验证 componentType 注册与 wp_code_overrides 映射

验证:
  1. 'd4-operating-revenue' 在 VALID_COMPONENT_TYPES 中注册
  2. wp_code_overrides.json 将 D4/D4-1~D4-36 映射为 'd4-operating-revenue'
  3. D4A 映射为 'a-program-console'（程序表复用）
  4. 所有映射值均为合法 componentType

Validates: Requirements 1.6, 1.7, 1.8
"""

import json
from pathlib import Path

import pytest

from app.services.wp_classification_service import (
    VALID_COMPONENT_TYPES,
    _WP_CODE_OVERRIDE,
)


class TestD4ValidComponentTypes:
    """VALID_COMPONENT_TYPES 契约验证"""

    def test_d4_operating_revenue_in_valid_types(self):
        """'d4-operating-revenue' 已注册于 VALID_COMPONENT_TYPES 白名单。"""
        assert "d4-operating-revenue" in VALID_COMPONENT_TYPES

    def test_a_program_console_in_valid_types(self):
        """'a-program-console' 已注册（D4A 程序表复用）。"""
        assert "a-program-console" in VALID_COMPONENT_TYPES


class TestD4WpCodeOverrides:
    """wp_code_overrides.json 契约验证 D4/D4-1~D4-36 映射"""

    @pytest.fixture()
    def overrides_data(self) -> dict[str, str]:
        """从 JSON 文件加载 overrides 数据。"""
        p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
        return json.loads(p.read_text(encoding="utf-8"))

    def test_d4_maps_to_operating_revenue(self, overrides_data):
        """D4 顶层编码映射为 'd4-operating-revenue'。"""
        assert overrides_data.get("D4") == "d4-operating-revenue"

    @pytest.mark.parametrize("code", [
        "D4-1", "D4-2", "D4-3", "D4-4", "D4-5", "D4-6", "D4-7", "D4-8",
        "D4-9", "D4-10", "D4-11", "D4-12", "D4-13", "D4-14", "D4-15",
        "D4-16", "D4-17", "D4-18", "D4-19", "D4-20", "D4-21", "D4-22",
        "D4-22A", "D4-23", "D4-24", "D4-25", "D4-26", "D4-27", "D4-28",
        "D4-29", "D4-30", "D4-31", "D4-32", "D4-33", "D4-34", "D4-35",
        "D4-36",
    ])
    def test_d4_sub_codes_map_to_operating_revenue(self, overrides_data, code: str):
        """D4-1~D4-36 + D4-22A 均映射为 'd4-operating-revenue'。"""
        assert overrides_data.get(code) == "d4-operating-revenue", (
            f"wp_code '{code}' 应映射为 'd4-operating-revenue'，"
            f"实际为 {overrides_data.get(code)!r}"
        )

    def test_d4a_maps_to_program_console(self, overrides_data):
        """D4A 程序表映射为 'a-program-console'（复用通用程序表组件）。"""
        assert overrides_data.get("D4A") == "a-program-console"

    def test_all_d4_overrides_are_valid_types(self, overrides_data):
        """D4 系列所有映射值均在 VALID_COMPONENT_TYPES 白名单内。"""
        d4_entries = {k: v for k, v in overrides_data.items() if k.startswith("D4")}
        assert len(d4_entries) > 0, "wp_code_overrides.json 中无 D4 系列条目"
        invalid = {k: v for k, v in d4_entries.items() if v not in VALID_COMPONENT_TYPES}
        assert not invalid, (
            f"D4 系列 wp_code 映射到非法 componentType:\n"
            + "\n".join(f"  {code!r} -> {ctype!r}" for code, ctype in sorted(invalid.items()))
        )

    def test_d4_override_count(self, overrides_data):
        """D4 系列条目数量 >= 38（D4 + D4-1~D4-36 + D4-22A + D4A）。"""
        d4_entries = {k: v for k, v in overrides_data.items() if k.startswith("D4")}
        assert len(d4_entries) >= 38, (
            f"D4 系列条目数量不足：期望 >= 38，实际 {len(d4_entries)}"
        )

    def test_runtime_override_consistency(self, overrides_data):
        """运行时 _WP_CODE_OVERRIDE 与 JSON 文件中 D4 条目一致。"""
        d4_json = {k: v for k, v in overrides_data.items() if k.startswith("D4")}
        d4_runtime = {k: v for k, v in _WP_CODE_OVERRIDE.items() if k.startswith("D4")}
        assert d4_json == d4_runtime, (
            "运行时 _WP_CODE_OVERRIDE 的 D4 条目与 JSON 文件不一致"
        )
