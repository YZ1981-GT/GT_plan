"""GuidanceService 扩展测试 — 复杂度分类 + 推荐问题 + 完整响应结构

验证 Task 3.1/3.2 的核心逻辑：
1. classify_complexity 返回正确等级
2. get_recommended_questions 返回非空列表
3. GuidanceService.get_guidance 返回正确结构
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# 1. classify_complexity 测试
# ---------------------------------------------------------------------------


class TestClassifyComplexity:
    """复杂度分类单元测试"""

    def _get_service(self):
        from app.services.wp_guidance_service import GuidanceService
        return GuidanceService()

    def test_high_complexity_exact_match(self):
        """精确匹配高复杂度底稿"""
        svc = self._get_service()
        assert svc.classify_complexity("A17") == "high"
        assert svc.classify_complexity("B60") == "high"
        assert svc.classify_complexity("B50") == "high"
        assert svc.classify_complexity("B51") == "high"

    def test_high_complexity_determination_pattern(self):
        """通配符 *-1 匹配审定表"""
        svc = self._get_service()
        assert svc.classify_complexity("D2-1") == "high"
        assert svc.classify_complexity("E1-1") == "high"
        assert svc.classify_complexity("F1-1") == "high"
        assert svc.classify_complexity("N2-1") == "high"

    def test_high_complexity_program_pattern(self):
        """通配符 *A 匹配程序表"""
        svc = self._get_service()
        assert svc.classify_complexity("D0A") == "high"
        assert svc.classify_complexity("E1A") == "high"
        assert svc.classify_complexity("F0A") == "high"

    def test_medium_complexity(self):
        """中复杂度底稿匹配"""
        svc = self._get_service()
        assert svc.classify_complexity("A1-15") == "medium"
        assert svc.classify_complexity("A1-16") == "medium"
        assert svc.classify_complexity("A1-13") == "medium"
        assert svc.classify_complexity("A1-14") == "medium"
        assert svc.classify_complexity("A5") == "medium"

    def test_medium_complexity_s_pattern(self):
        """S* 通配符匹配专项底稿"""
        svc = self._get_service()
        assert svc.classify_complexity("S1") == "medium"
        assert svc.classify_complexity("S32") == "medium"

    def test_low_complexity_default(self):
        """默认为低复杂度"""
        svc = self._get_service()
        assert svc.classify_complexity("A2") == "low"
        assert svc.classify_complexity("A3") == "low"
        assert svc.classify_complexity("X99") == "low"

    def test_deterministic(self):
        """相同输入多次调用结果一致"""
        svc = self._get_service()
        results = [svc.classify_complexity("D2-1") for _ in range(5)]
        assert all(r == "high" for r in results)

    def test_return_valid_literal(self):
        """返回值永远是 high/medium/low 之一"""
        svc = self._get_service()
        codes = ["A17", "B60", "D2-1", "E1A", "A1-15", "S1", "A2", "X99", ""]
        valid = {"high", "medium", "low"}
        for code in codes:
            assert svc.classify_complexity(code) in valid


# ---------------------------------------------------------------------------
# 2. get_recommended_questions 测试
# ---------------------------------------------------------------------------


class TestRecommendedQuestions:
    """推荐问题映射测试"""

    def _get_service(self):
        from app.services.wp_guidance_service import GuidanceService
        return GuidanceService()

    def test_program_table_questions(self):
        """程序表(以A结尾)返回程序表问题"""
        svc = self._get_service()
        questions = svc.get_recommended_questions("D0A")
        assert len(questions) > 0
        # 程序表问题应包含"步骤"相关
        assert any("步骤" in q for q in questions)

    def test_determination_table_questions(self):
        """审定表(以-1结尾)返回审定表问题"""
        svc = self._get_service()
        questions = svc.get_recommended_questions("D2-1")
        assert len(questions) > 0
        # 审定表问题应包含"金额"或"取数"相关
        assert any("金额" in q or "取数" in q for q in questions)

    def test_default_questions(self):
        """通用底稿返回默认问题"""
        svc = self._get_service()
        questions = svc.get_recommended_questions("A2")
        assert len(questions) > 0

    def test_known_codes_non_empty(self):
        """已知底稿编码返回非空问题列表"""
        svc = self._get_service()
        for code in ["D0A", "E1A", "D2-1", "F1-1", "A3", "B60"]:
            questions = svc.get_recommended_questions(code)
            assert isinstance(questions, list)
            assert len(questions) > 0, f"{code} 应有推荐问题"


# ---------------------------------------------------------------------------
# 3. GuidanceService.get_guidance 完整结构测试
# ---------------------------------------------------------------------------


class TestGetGuidance:
    """GuidanceService.get_guidance 响应结构验证"""

    @pytest.mark.asyncio
    async def test_response_structure(self):
        """验证响应包含所有必需字段"""
        from app.services.wp_guidance_service import GuidanceService

        svc = GuidanceService()
        response = await svc.get_guidance(
            wp_code="A17",
            wp_name="重大事项概要",
            template_path=None,
        )

        # 必须字段
        assert "wp_code" in response
        assert "wp_name" in response
        assert "source" in response
        assert "complexity" in response
        assert "guidance" in response
        assert "recommended_questions" in response

        # guidance 子结构
        assert "sections" in response["guidance"]
        assert "raw_text" in response["guidance"]

    @pytest.mark.asyncio
    async def test_source_is_valid_enum(self):
        """source 字段值合法"""
        from app.services.wp_guidance_service import GuidanceService

        svc = GuidanceService()
        response = await svc.get_guidance(wp_code="A17", template_path=None)

        valid_sources = {
            "template_sheet", "template_header", "docx_instructions",
            "static_json", "typed_fallback", "fallback"
        }
        assert response["source"] in valid_sources

    @pytest.mark.asyncio
    async def test_never_empty_raw_text(self):
        """raw_text 永不为空字符串"""
        from app.services.wp_guidance_service import GuidanceService

        svc = GuidanceService()
        # 即使完全未知的 wp_code，fallback 也应提供内容
        response = await svc.get_guidance(wp_code="ZZZZZ_UNKNOWN", template_path=None)
        assert response["guidance"]["raw_text"] != ""

    @pytest.mark.asyncio
    async def test_complexity_matches_code(self):
        """响应中的 complexity 与 classify_complexity 一致"""
        from app.services.wp_guidance_service import GuidanceService

        svc = GuidanceService()
        response = await svc.get_guidance(wp_code="D2-1", template_path=None)
        assert response["complexity"] == "high"

        response2 = await svc.get_guidance(wp_code="A2", template_path=None)
        assert response2["complexity"] == "low"

    @pytest.mark.asyncio
    async def test_static_json_source(self):
        """有静态 JSON 文件的底稿返回 static_json 来源"""
        from app.services.wp_guidance_service import GuidanceService

        svc = GuidanceService()
        response = await svc.get_guidance(wp_code="A17", template_path=None)
        assert response["source"] == "static_json"
        assert len(response["guidance"]["sections"]) > 0
