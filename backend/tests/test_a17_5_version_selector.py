"""Tests for A17-5 version selector service."""

from __future__ import annotations

import pytest

from app.services.a17_5_version_selector import _determine_applicability


class TestDetermineApplicability:
    """纯逻辑测试：无需 DB"""

    def test_a1_listed_company(self):
        """A1 上市公司：5-1 必做, 5-2 适用(整合审计), 5-5 推荐"""
        results = _determine_applicability("A1", "normal")
        by_code = {r["wp_code"]: r for r in results}

        # 5-1 必做
        assert by_code["A17-5-1"]["applicable"] is True
        assert by_code["A17-5-1"]["mandatory"] is True
        # 5-2 整合审计适用
        assert by_code["A17-5-2"]["applicable"] is True
        # 5-3 IPO 不适用
        assert by_code["A17-5-3"]["applicable"] is False
        # 5-4 新三板不适用
        assert by_code["A17-5-4"]["applicable"] is False
        # 5-5 推荐
        assert by_code["A17-5-5"]["applicable"] is True
        assert by_code["A17-5-5"]["mandatory"] is False

    def test_a2_ipo(self):
        """A2 IPO：5-1 必做, 5-3 必做"""
        results = _determine_applicability("A2", "ipo")
        by_code = {r["wp_code"]: r for r in results}

        assert by_code["A17-5-1"]["applicable"] is True
        assert by_code["A17-5-1"]["mandatory"] is True
        assert by_code["A17-5-3"]["applicable"] is True
        assert by_code["A17-5-3"]["mandatory"] is True
        # 5-2 不适用 (IPO 非整合)
        assert by_code["A17-5-2"]["applicable"] is False

    def test_b1_neeq(self):
        """B1 新三板：5-1 适用(非必做), 5-4 必做, 5-5 推荐"""
        results = _determine_applicability("B1", "normal")
        by_code = {r["wp_code"]: r for r in results}

        # 5-1 适用但非必做 (B 类)
        assert by_code["A17-5-1"]["applicable"] is True
        assert by_code["A17-5-1"]["mandatory"] is False
        # 5-4 新三板必做
        assert by_code["A17-5-4"]["applicable"] is True
        assert by_code["A17-5-4"]["mandatory"] is True
        # 5-5 推荐
        assert by_code["A17-5-5"]["applicable"] is True

    def test_c_class_general(self):
        """C 类一般审计：所有版本不适用"""
        results = _determine_applicability("C", "normal")
        by_code = {r["wp_code"]: r for r in results}

        for code, item in by_code.items():
            assert item["applicable"] is False, f"{code} should not be applicable for C class"
            assert item["mandatory"] is False

    def test_none_category_safe_defaults(self):
        """无分类信息：返回安全默认（C 类行为）"""
        results = _determine_applicability(None, None)
        by_code = {r["wp_code"]: r for r in results}

        # 无分类 → get_category_prefix 返回 "C" → 全部不适用
        for code, item in by_code.items():
            assert item["applicable"] is False

    def test_a5_soe(self):
        """A5 央企：5-1 必做, 5-2 整合适用, 5-5 推荐"""
        results = _determine_applicability("A5", "normal")
        by_code = {r["wp_code"]: r for r in results}

        assert by_code["A17-5-1"]["mandatory"] is True
        assert by_code["A17-5-2"]["applicable"] is True
        assert by_code["A17-5-5"]["applicable"] is True
        assert by_code["A17-5-3"]["applicable"] is False
        assert by_code["A17-5-4"]["applicable"] is False

    def test_scenario_ipo_overrides(self):
        """scenario='ipo' 使 5-3 适用（即使 business_category 不是 A2）"""
        results = _determine_applicability("A1", "ipo")
        by_code = {r["wp_code"]: r for r in results}

        assert by_code["A17-5-3"]["applicable"] is True
        assert by_code["A17-5-3"]["mandatory"] is True

    def test_returns_five_versions(self):
        """始终返回 5 个版本"""
        results = _determine_applicability("A1", "normal")
        assert len(results) == 5
        codes = [r["wp_code"] for r in results]
        assert codes == ["A17-5-1", "A17-5-2", "A17-5-3", "A17-5-4", "A17-5-5"]

    def test_all_have_required_fields(self):
        """每个结果包含必要字段"""
        results = _determine_applicability("A3", "normal")
        for item in results:
            assert "wp_code" in item
            assert "title" in item
            assert "description" in item
            assert "applicable" in item
            assert "mandatory" in item
            assert isinstance(item["applicable"], bool)
            assert isinstance(item["mandatory"], bool)

    def test_b_class_general(self):
        """B 类（非新三板）：5-1 适用非必做, 5-5 推荐"""
        results = _determine_applicability("B3", "normal")
        by_code = {r["wp_code"]: r for r in results}

        assert by_code["A17-5-1"]["applicable"] is True
        assert by_code["A17-5-1"]["mandatory"] is False
        assert by_code["A17-5-4"]["applicable"] is False
        assert by_code["A17-5-5"]["applicable"] is True
