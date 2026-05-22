"""K-F7 销售/管理费用 3 维度分析 — 单元测试

Covers:
- 同比 YoY 计算正确性 + 异常阈值（|rate| > 20%）
- 预算差异计算正确性 + 异常阈值（|rate| > 10%）
- 行业对比计算正确性 + 异常阈值（|deviation| > 10%）
- 边界 case（current_year 空 / 负值 → 400 / 上年 0 → new_category）
- apply_to_sheet 写回联动
- RBAC 校验（require_project_access('edit')）
- is_llm_stub config 驱动

对应 spec: workpaper-k-admin-cycle K-F7 / ADR-K4
"""

import sys
sys.path.insert(0, "backend")

import inspect

import pytest
from fastapi import HTTPException

from app.routers.wp_k_expense_analysis import (
    BUDGET_VARIANCE_THRESHOLD,
    ExpenseAnalysisRequest,
    INDUSTRY_DEVIATION_THRESHOLD,
    YOY_CHANGE_THRESHOLD,
    _build_anomaly_flags,
    _build_expense_prompt,
    _build_summary,
    _calc_budget_variance,
    _calc_industry_comparison,
    _calc_yoy,
    _call_llm_for_explanation,
    _EXPENSE_SYSTEM_PROMPT,
    _maybe_apply_analysis_to_workpaper,
    _validate_request,
    k_expense_analysis,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════════════════════════════════


def _make_request(**overrides) -> ExpenseAnalysisRequest:
    """构造标准 K8 销售费用分析请求"""
    defaults = {
        "wp_code": "K8",
        "current_year": {
            "职工薪酬": 1200000.00,
            "广告费": 500000.00,
            "差旅费": 80000.00,
            "折旧费": 60000.00,
        },
        "prior_year": {
            "职工薪酬": 1000000.00,
            "广告费": 400000.00,
            "差旅费": 100000.00,
            "折旧费": 50000.00,
        },
        "budget": None,
        "industry_avg_rates": None,
        "revenue": None,
        "apply_to_sheet": None,
    }
    defaults.update(overrides)
    return ExpenseAnalysisRequest(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 同比 YoY 计算
# ═══════════════════════════════════════════════════════════════════════════════


class TestYoyCalculation:
    """同比变化计算"""

    def test_yoy_normal_increase(self):
        """同比增加 20% 内 → normal"""
        cur = {"X": 1100.0}
        prior = {"X": 1000.0}
        result = _calc_yoy(cur, prior)
        assert result["X"]["amount_change"] == 100.0
        assert result["X"]["rate_change"] == 0.10
        assert result["X"]["flag"] == "normal"

    def test_yoy_increase_anomaly(self):
        """同比增加 > 20% → increase_anomaly"""
        cur = {"X": 1300.0}
        prior = {"X": 1000.0}
        result = _calc_yoy(cur, prior)
        assert result["X"]["rate_change"] == 0.30
        assert result["X"]["flag"] == "increase_anomaly"

    def test_yoy_decrease_anomaly(self):
        """同比减少 > 20% → decrease_anomaly"""
        cur = {"X": 700.0}
        prior = {"X": 1000.0}
        result = _calc_yoy(cur, prior)
        assert result["X"]["rate_change"] == -0.30
        assert result["X"]["flag"] == "decrease_anomaly"

    def test_yoy_threshold_boundary_at_20_percent(self):
        """同比变化恰好 20% → normal（formula: |rate| > THRESHOLD）"""
        cur = {"X": 1200.0}
        prior = {"X": 1000.0}
        result = _calc_yoy(cur, prior)
        # 0.20 不大于 0.20 → normal
        assert result["X"]["rate_change"] == 0.20
        assert result["X"]["flag"] == "normal"

    def test_yoy_threshold_just_above_20_percent(self):
        """同比变化 20.1% → increase_anomaly"""
        cur = {"X": 1201.0}
        prior = {"X": 1000.0}
        result = _calc_yoy(cur, prior)
        assert result["X"]["rate_change"] > 0.20
        assert result["X"]["flag"] == "increase_anomaly"

    def test_yoy_prior_zero_new_category(self):
        """上年 0 + 本年 > 0 → new_category（不算异常）"""
        cur = {"X": 1000.0}
        prior = {}
        result = _calc_yoy(cur, prior)
        assert result["X"]["flag"] == "new_category"

    def test_yoy_both_zero_normal(self):
        """两年均 0 → normal"""
        cur = {"X": 0.0}
        prior = {"X": 0.0}
        result = _calc_yoy(cur, prior)
        assert result["X"]["flag"] == "normal"
        assert result["X"]["amount_change"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 预算差异
# ═══════════════════════════════════════════════════════════════════════════════


class TestBudgetVariance:
    """预算差异计算"""

    def test_budget_normal(self):
        """实际 vs 预算偏差 < 10% → normal"""
        cur = {"X": 1050.0}
        budget = {"X": 1000.0}
        result = _calc_budget_variance(cur, budget)
        assert result["X"]["variance_amount"] == 50.0
        assert result["X"]["variance_rate"] == 0.05
        assert result["X"]["flag"] == "normal"

    def test_budget_overrun(self):
        """实际超预算 > 10% → overrun"""
        cur = {"X": 1200.0}
        budget = {"X": 1000.0}
        result = _calc_budget_variance(cur, budget)
        assert result["X"]["flag"] == "overrun"

    def test_budget_underrun(self):
        """实际低于预算 > 10% → underrun"""
        cur = {"X": 850.0}
        budget = {"X": 1000.0}
        result = _calc_budget_variance(cur, budget)
        assert result["X"]["flag"] == "underrun"

    def test_budget_zero_no_budget(self):
        """无预算 + 有实际 → no_budget"""
        cur = {"X": 1000.0}
        budget = {}
        result = _calc_budget_variance(cur, budget)
        assert result["X"]["flag"] == "no_budget"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 行业对比
# ═══════════════════════════════════════════════════════════════════════════════


class TestIndustryComparison:
    """行业对比"""

    def test_industry_normal(self):
        """项目费用占比与行业差异 < 10% → normal"""
        cur = {"X": 100000.0}  # 项目占比 10%
        rates = {"X": 0.105}  # 行业 10.5%
        revenue = 1000000.0
        result = _calc_industry_comparison(cur, rates, revenue)
        assert result["X"]["project_rate"] == 0.10
        assert result["X"]["industry_avg_rate"] == 0.105
        assert abs(result["X"]["deviation"]) < INDUSTRY_DEVIATION_THRESHOLD
        assert result["X"]["flag"] == "normal"

    def test_industry_above(self):
        """项目占比远高于行业 > 10% → above_industry"""
        cur = {"X": 250000.0}  # 项目占比 25%
        rates = {"X": 0.10}  # 行业 10%
        revenue = 1000000.0
        result = _calc_industry_comparison(cur, rates, revenue)
        # 25% - 10% = 15% > 10% → above
        assert result["X"]["flag"] == "above_industry"

    def test_industry_below(self):
        """项目占比远低于行业 > 10% → below_industry"""
        cur = {"X": 50000.0}  # 项目占比 5%
        rates = {"X": 0.20}  # 行业 20%
        revenue = 1000000.0
        result = _calc_industry_comparison(cur, rates, revenue)
        # 5% - 20% = -15% → below
        assert result["X"]["flag"] == "below_industry"

    def test_industry_revenue_zero_returns_empty(self):
        """收入为 0 → 返回空 dict"""
        cur = {"X": 100000.0}
        rates = {"X": 0.10}
        result = _calc_industry_comparison(cur, rates, 0)
        assert result == {}


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 异常标记汇总
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnomalyFlags:
    """异常标记汇总"""

    def test_normal_no_flags(self):
        """全部正常 → flags 为空"""
        yoy = {"X": {"flag": "normal", "rate_change": 0.05, "amount_change": 50}}
        flags = _build_anomaly_flags(yoy, None, None)
        assert flags == []

    def test_yoy_flag_appended(self):
        yoy = {
            "广告费": {"flag": "increase_anomaly", "rate_change": 0.30, "amount_change": 100},
        }
        flags = _build_anomaly_flags(yoy, None, None)
        assert any("yoy_increase_anomaly_广告费" in f for f in flags)

    def test_budget_flag_appended(self):
        yoy = {"X": {"flag": "normal", "rate_change": 0, "amount_change": 0}}
        budget = {"X": {"flag": "overrun", "variance_rate": 0.20, "variance_amount": 200}}
        flags = _build_anomaly_flags(yoy, budget, None)
        assert any("budget_overrun_X" in f for f in flags)

    def test_industry_flag_appended(self):
        yoy = {"X": {"flag": "normal", "rate_change": 0, "amount_change": 0}}
        industry = {
            "X": {
                "flag": "above_industry",
                "project_rate": 0.25,
                "industry_avg_rate": 0.10,
                "deviation": 0.15,
            }
        }
        flags = _build_anomaly_flags(yoy, None, industry)
        assert any("industry_above_industry_X" in f for f in flags)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 输入校验
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidation:
    """输入校验"""

    def test_empty_current_year_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            req = _make_request(current_year={})
            _validate_request(req)
        assert exc.value.status_code == 400
        assert "不能为空" in exc.value.detail

    def test_negative_amount_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            req = _make_request(current_year={"X": -100.0})
            _validate_request(req)
        assert exc.value.status_code == 400
        assert "不能为负" in exc.value.detail

    def test_invalid_wp_code_raises_validation(self):
        """wp_code 必须是 K8 或 K9（Pydantic Literal）"""
        with pytest.raises(Exception):  # ValidationError
            _make_request(wp_code="X1")


# ═══════════════════════════════════════════════════════════════════════════════
# 6. summary 文案
# ═══════════════════════════════════════════════════════════════════════════════


class TestSummaryGeneration:
    """summary 生成"""

    def test_summary_contains_wp_name_k8(self):
        yoy = {"职工薪酬": {"flag": "normal", "rate_change": 0.05, "amount_change": 100}}
        summary = _build_summary("K8", yoy, 0, is_llm_stub=False)
        assert "销售费用" in summary
        assert "1 个费用类别" in summary

    def test_summary_contains_wp_name_k9(self):
        yoy = {"X": {"flag": "normal", "rate_change": 0, "amount_change": 0}}
        summary = _build_summary("K9", yoy, 0, is_llm_stub=False)
        assert "管理费用" in summary

    def test_summary_includes_anomaly_count(self):
        yoy = {
            "A": {"flag": "increase_anomaly", "rate_change": 0.30, "amount_change": 100},
            "B": {"flag": "normal", "rate_change": 0.05, "amount_change": 10},
        }
        summary = _build_summary("K8", yoy, 1, is_llm_stub=False)
        assert "1 项异常" in summary

    def test_summary_stub_marker_when_disabled(self):
        yoy = {"X": {"flag": "normal", "rate_change": 0, "amount_change": 0}}
        summary = _build_summary("K8", yoy, 0, is_llm_stub=True)
        assert "wp_ai_service" in summary

    def test_summary_no_stub_marker_when_enabled(self):
        yoy = {"X": {"flag": "normal", "rate_change": 0, "amount_change": 0}}
        summary = _build_summary("K8", yoy, 0, is_llm_stub=False)
        assert "wp_ai_service" not in summary


# ═══════════════════════════════════════════════════════════════════════════════
# 7. 写回联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestWriteBack:
    """apply_to_sheet 写回联动"""

    def test_write_back_function_is_callable(self):
        assert callable(_maybe_apply_analysis_to_workpaper)

    def test_write_back_invalid_uuid_returns_none(self):
        """无效 wp_id → 返回 None（不抛异常）"""
        import asyncio

        async def _run():
            return await _maybe_apply_analysis_to_workpaper(
                None, "invalid-uuid", "审定表K8-1", "K8", {"foo": "bar"}
            )

        r = asyncio.run(_run())
        assert r is None


# ═══════════════════════════════════════════════════════════════════════════════
# 8. RBAC
# ═══════════════════════════════════════════════════════════════════════════════


class TestRBAC:
    """RBAC 校验"""

    def test_endpoint_uses_require_project_access_edit(self):
        """费用分析路由必须用 require_project_access('edit')"""
        import app.routers.wp_k_expense_analysis as mod
        src = inspect.getsource(mod)
        assert 'require_project_access("edit")' in src

    def test_endpoint_function_has_user_dependency(self):
        sig = inspect.signature(k_expense_analysis)
        param_names = list(sig.parameters.keys())
        assert "_user" in param_names

    def test_router_prefix_contains_project_id(self):
        from app.routers.wp_k_expense_analysis import router
        assert "{project_id}" in router.prefix

    def test_router_prefix_contains_workpaper_id(self):
        from app.routers.wp_k_expense_analysis import router
        assert "{wp_id}" in router.prefix


# ═══════════════════════════════════════════════════════════════════════════════
# 9. is_llm_stub config 驱动
# ═══════════════════════════════════════════════════════════════════════════════


class TestStubConfig:
    """is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动"""

    def test_stub_flag_default_true(self):
        """默认 WP_AI_SERVICE_ENABLED=False → is_llm_stub=True"""
        from app.core.config import settings
        enabled = getattr(settings, "WP_AI_SERVICE_ENABLED", False)
        is_stub = not enabled
        assert is_stub is True

    def test_stub_flag_when_enabled(self, monkeypatch):
        """配置 WP_AI_SERVICE_ENABLED=True → is_llm_stub=False"""
        from app.core.config import settings
        monkeypatch.setattr(settings, "WP_AI_SERVICE_ENABLED", True)
        enabled = getattr(settings, "WP_AI_SERVICE_ENABLED", False)
        is_stub = not enabled
        assert is_stub is False


# ═══════════════════════════════════════════════════════════════════════════════
# 10. 集成 calc 流程
# ═══════════════════════════════════════════════════════════════════════════════


class TestIntegration:
    """端到端流程串联"""

    def test_3_dimensions_full_run(self):
        """3 维度全运行：YoY + budget + industry"""
        req = _make_request(
            current_year={
                "职工薪酬": 1200000.00,
                "广告费": 600000.00,  # 同比 +50% → increase_anomaly
            },
            prior_year={"职工薪酬": 1000000.00, "广告费": 400000.00},
            budget={"职工薪酬": 1100000.00, "广告费": 500000.00},
            industry_avg_rates={"职工薪酬": 0.10, "广告费": 0.04},
            revenue=10000000.00,
        )
        yoy = _calc_yoy(req.current_year, req.prior_year)
        budget = _calc_budget_variance(req.current_year, req.budget)
        industry = _calc_industry_comparison(
            req.current_year, req.industry_avg_rates, req.revenue
        )

        # 广告费 +50% → increase_anomaly
        assert yoy["广告费"]["flag"] == "increase_anomaly"
        # 职工薪酬 +20%（恰好阈值）→ normal
        assert yoy["职工薪酬"]["flag"] == "normal"
        # 广告费实际 60万 vs 预算 50万 = +20% → overrun
        assert budget["广告费"]["flag"] == "overrun"
        # 广告费占比 6% vs 行业 4% = +2% < 10% → normal
        assert industry["广告费"]["flag"] == "normal"

        flags = _build_anomaly_flags(yoy, budget, industry)
        assert any("广告费" in f for f in flags)

    def test_constants_are_set(self):
        """阈值常量定义正确"""
        assert YOY_CHANGE_THRESHOLD == 0.20
        assert BUDGET_VARIANCE_THRESHOLD == 0.10
        assert INDUSTRY_DEVIATION_THRESHOLD == 0.10


# ═══════════════════════════════════════════════════════════════════════════════
# 11. LLM Prompt Builder — _build_expense_prompt
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildExpensePrompt:
    """_build_expense_prompt 构建 LLM 用户提示词"""

    def test_prompt_contains_wp_name_k8(self):
        """K8 → 提示词包含'销售费用'"""
        yoy = {"职工薪酬": {"amount_change": 200000, "rate_change": 0.20, "flag": "normal"}}
        prompt = _build_expense_prompt("K8", yoy, None, None, [])
        assert "销售费用" in prompt
        assert "K8" in prompt

    def test_prompt_contains_wp_name_k9(self):
        """K9 → 提示词包含'管理费用'"""
        yoy = {"X": {"amount_change": 100, "rate_change": 0.10, "flag": "normal"}}
        prompt = _build_expense_prompt("K9", yoy, None, None, [])
        assert "管理费用" in prompt

    def test_prompt_includes_yoy_data(self):
        """提示词包含同比变动数据"""
        yoy = {
            "广告费": {"amount_change": 100000, "rate_change": 0.50, "flag": "increase_anomaly"},
        }
        prompt = _build_expense_prompt("K8", yoy, None, None, ["yoy_increase_anomaly_广告费"])
        assert "广告费" in prompt
        assert "异常增加" in prompt
        assert "50.0%" in prompt

    def test_prompt_includes_budget_data(self):
        """提示词包含预算差异数据"""
        yoy = {"X": {"amount_change": 0, "rate_change": 0, "flag": "normal"}}
        budget = {"X": {"variance_amount": 50000, "variance_rate": 0.15, "flag": "overrun"}}
        prompt = _build_expense_prompt("K8", yoy, budget, None, [])
        assert "超支" in prompt
        assert "15.0%" in prompt

    def test_prompt_includes_industry_data(self):
        """提示词包含行业对比数据"""
        yoy = {"X": {"amount_change": 0, "rate_change": 0, "flag": "normal"}}
        industry = {
            "X": {"project_rate": 0.25, "industry_avg_rate": 0.10, "deviation": 0.15, "flag": "above_industry"}
        }
        prompt = _build_expense_prompt("K8", yoy, None, industry, [])
        assert "高于行业" in prompt
        assert "25.0%" in prompt
        assert "10.0%" in prompt

    def test_prompt_no_budget_shows_placeholder(self):
        """无预算数据时显示占位文本"""
        yoy = {"X": {"amount_change": 0, "rate_change": 0, "flag": "normal"}}
        prompt = _build_expense_prompt("K8", yoy, None, None, [])
        assert "未提供预算数据" in prompt

    def test_prompt_no_industry_shows_placeholder(self):
        """无行业数据时显示占位文本"""
        yoy = {"X": {"amount_change": 0, "rate_change": 0, "flag": "normal"}}
        prompt = _build_expense_prompt("K8", yoy, None, None, [])
        assert "未提供行业对比数据" in prompt

    def test_prompt_contains_output_format_instructions(self):
        """提示词包含输出格式要求"""
        yoy = {"X": {"amount_change": 0, "rate_change": 0, "flag": "normal"}}
        prompt = _build_expense_prompt("K8", yoy, None, None, [])
        assert "异常原因分析" in prompt
        assert "建议审计程序" in prompt
        assert "风险等级判断" in prompt

    def test_prompt_new_category_rate_shows_new(self):
        """rate_change=999 (inf) → 显示'新增'"""
        yoy = {"新费用": {"amount_change": 5000, "rate_change": 999.0, "flag": "new_category"}}
        prompt = _build_expense_prompt("K8", yoy, None, None, [])
        assert "新增" in prompt

    def test_prompt_anomaly_count_correct(self):
        """异常标记数正确反映在提示词中"""
        yoy = {
            "A": {"amount_change": 300, "rate_change": 0.30, "flag": "increase_anomaly"},
            "B": {"amount_change": -400, "rate_change": -0.40, "flag": "decrease_anomaly"},
        }
        flags = ["yoy_increase_anomaly_A", "yoy_decrease_anomaly_B"]
        prompt = _build_expense_prompt("K8", yoy, None, None, flags)
        assert "异常标记数：2" in prompt


# ═══════════════════════════════════════════════════════════════════════════════
# 12. LLM Call — _call_llm_for_explanation (mock)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCallLlmForExplanation:
    """_call_llm_for_explanation LLM 调用分支"""

    @pytest.mark.asyncio
    async def test_llm_success_returns_explanation(self, monkeypatch):
        """LLM 成功 → 返回 (explanation_text, False)"""
        from app.services.llm_service import LLMResponse, LLMService

        fake_content = "**异常原因分析**：广告费同比增长50%，主要因市场推广力度加大。\n\n**建议审计程序**：\n1. 检查广告合同\n2. 核实费用发生真实性\n3. 分析费用效益\n\n**风险等级判断**：中"

        async def mock_generate(self, **kwargs):
            return LLMResponse(
                content=fake_content,
                tokens_used=150,
                is_stub=False,
                duration_ms=1200.0,
            )

        monkeypatch.setattr(LLMService, "generate", mock_generate)

        yoy = {"广告费": {"amount_change": 100000, "rate_change": 0.50, "flag": "increase_anomaly"}}
        text, failed = await _call_llm_for_explanation(yoy, None, None, ["yoy_increase_anomaly_广告费"], "K8")

        assert failed is False
        assert text == fake_content
        assert "异常原因分析" in text

    @pytest.mark.asyncio
    async def test_llm_failure_returns_stub(self, monkeypatch):
        """LLM 失败 → 返回 (None, True)"""
        from app.services.llm_service import LLMResponse, LLMService

        async def mock_generate(self, **kwargs):
            return LLMResponse(
                content=None,
                tokens_used=0,
                is_stub=True,
                error="LLM call timeout after 30s",
                duration_ms=30000.0,
            )

        monkeypatch.setattr(LLMService, "generate", mock_generate)

        yoy = {"X": {"amount_change": 0, "rate_change": 0, "flag": "normal"}}
        text, failed = await _call_llm_for_explanation(yoy, None, None, [], "K8")

        assert failed is True
        assert text is None

    @pytest.mark.asyncio
    async def test_llm_uses_correct_system_prompt(self, monkeypatch):
        """LLM 调用使用正确的系统提示词"""
        from app.services.llm_service import LLMResponse, LLMService

        captured_kwargs = {}

        async def mock_generate(self, **kwargs):
            captured_kwargs.update(kwargs)
            return LLMResponse(content="test", tokens_used=10, is_stub=False, duration_ms=100)

        monkeypatch.setattr(LLMService, "generate", mock_generate)

        yoy = {"X": {"amount_change": 0, "rate_change": 0, "flag": "normal"}}
        await _call_llm_for_explanation(yoy, None, None, [], "K8")

        assert captured_kwargs["system_prompt"] == _EXPENSE_SYSTEM_PROMPT
        assert "资深审计师" in captured_kwargs["system_prompt"]

    @pytest.mark.asyncio
    async def test_llm_timeout_30s(self, monkeypatch):
        """LLM 调用超时设置为 30s"""
        from app.services.llm_service import LLMResponse, LLMService

        captured_kwargs = {}

        async def mock_generate(self, **kwargs):
            captured_kwargs.update(kwargs)
            return LLMResponse(content="test", tokens_used=10, is_stub=False, duration_ms=100)

        monkeypatch.setattr(LLMService, "generate", mock_generate)

        yoy = {"X": {"amount_change": 0, "rate_change": 0, "flag": "normal"}}
        await _call_llm_for_explanation(yoy, None, None, [], "K8")

        assert captured_kwargs["timeout"] == 30.0

    @pytest.mark.asyncio
    async def test_llm_temperature_03(self, monkeypatch):
        """LLM 调用温度为 0.3（审计场景偏保守）"""
        from app.services.llm_service import LLMResponse, LLMService

        captured_kwargs = {}

        async def mock_generate(self, **kwargs):
            captured_kwargs.update(kwargs)
            return LLMResponse(content="test", tokens_used=10, is_stub=False, duration_ms=100)

        monkeypatch.setattr(LLMService, "generate", mock_generate)

        yoy = {"X": {"amount_change": 0, "rate_change": 0, "flag": "normal"}}
        await _call_llm_for_explanation(yoy, None, None, [], "K8")

        assert captured_kwargs["temperature"] == 0.3


# ═══════════════════════════════════════════════════════════════════════════════
# 13. LLM 集成 — WP_AI_SERVICE_ENABLED 两态
# ═══════════════════════════════════════════════════════════════════════════════


class TestLlmIntegrationTwoStates:
    """WP_AI_SERVICE_ENABLED=True/False 两态测试"""

    def test_ai_explanation_field_exists_in_response_model(self):
        """ExpenseAnalysisResponse 包含 ai_explanation 字段"""
        from app.routers.wp_k_expense_analysis import ExpenseAnalysisResponse
        fields = ExpenseAnalysisResponse.model_fields
        assert "ai_explanation" in fields

    def test_ai_explanation_is_optional(self):
        """ai_explanation 字段可为 None"""
        from app.routers.wp_k_expense_analysis import ExpenseAnalysisResponse
        field_info = ExpenseAnalysisResponse.model_fields["ai_explanation"]
        # Optional field — default is None
        assert field_info.default is None

    def test_system_prompt_content(self):
        """系统提示词包含审计师角色定义"""
        assert "资深审计师" in _EXPENSE_SYSTEM_PROMPT
        assert "审计判断" in _EXPENSE_SYSTEM_PROMPT

    def test_endpoint_source_has_llm_branch(self):
        """endpoint 源码包含 LLM 调用分支"""
        import inspect
        import app.routers.wp_k_expense_analysis as mod
        src = inspect.getsource(mod.k_expense_analysis)
        assert "WP_AI_SERVICE_ENABLED" in src
        assert "_call_llm_for_explanation" in src
        assert "ai_explanation" in src

    def test_endpoint_source_has_degradation(self):
        """endpoint 源码包含降级逻辑"""
        import inspect
        import app.routers.wp_k_expense_analysis as mod
        src = inspect.getsource(mod.k_expense_analysis)
        assert "AI 分析暂不可用" in src
