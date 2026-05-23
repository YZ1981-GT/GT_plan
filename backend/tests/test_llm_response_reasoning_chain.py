"""Tests for K-4 解释链字段（reasoning/references/data_sources/confidence）

验证：
1. LLMResponse 新字段默认值（向后兼容）
2. LLMResponse 新字段可正确赋值与读取
3. K8 ExpenseAnalysisResponse 含 4 个新字段且默认值合理
4. K11 ImpairmentSummaryResponse 含 4 个新字段且默认值合理
5. K8 _build_reasoning_chain 函数返回值正确（is_llm_stub vs LLM 启用）
6. K11 endpoint 真实端点 mock 调用：返回响应含完整 4 字段

对应 spec：proposal-remaining-18 task 4.2 / design.md ADR-6
"""

from __future__ import annotations

import pytest

from app.services.llm_service import LLMResponse


# ─── 1. LLMResponse dataclass 新字段 ────────────────────────────────────────


class TestLlmResponseReasoningChain:
    """LLMResponse 新增 K-4 解释链字段"""

    def test_defaults_backward_compatible(self):
        """新字段全部有默认值 → 现有调用代码（仅传 content/tokens_used）不破坏"""
        resp = LLMResponse(content="hi", tokens_used=42)
        # 现有字段不动
        assert resp.content == "hi"
        assert resp.tokens_used == 42
        assert resp.is_stub is False
        # 新字段默认值
        assert resp.reasoning is None
        assert resp.references == []
        assert resp.data_sources == []
        assert resp.confidence == 0.0

    def test_full_assignment(self):
        """4 字段可一次性赋值"""
        resp = LLMResponse(
            content="ok",
            reasoning="基于 CAS 8 减值测试",
            references=[
                {"type": "CAS", "code": "CAS 8", "section": "减值测试"},
                {"type": "ISA", "code": "ISA 540", "section": "估计与披露"},
            ],
            data_sources=["TB:1601:期末余额", "WP:H1:折旧分配分析表"],
            confidence=0.82,
        )
        assert resp.reasoning == "基于 CAS 8 减值测试"
        assert len(resp.references) == 2
        assert resp.references[0]["code"] == "CAS 8"
        assert resp.data_sources == ["TB:1601:期末余额", "WP:H1:折旧分配分析表"]
        assert resp.confidence == 0.82

    def test_independent_default_lists(self):
        """references / data_sources 默认 list 必须独立（dataclass field 默认工厂）"""
        a = LLMResponse()
        b = LLMResponse()
        a.references.append({"type": "CAS", "code": "X"})
        a.data_sources.append("WP:Y")
        # b 不能被 a 的修改污染
        assert b.references == []
        assert b.data_sources == []


# ─── 2. K8 ExpenseAnalysisResponse schema ──────────────────────────────────


class TestExpenseAnalysisResponseSchema:
    """ExpenseAnalysisResponse 含 4 个新字段"""

    def test_schema_has_reasoning_chain_fields(self):
        from app.routers.wp_k_expense_analysis import ExpenseAnalysisResponse

        fields = ExpenseAnalysisResponse.model_fields
        assert "reasoning" in fields
        assert "references" in fields
        assert "data_sources" in fields
        assert "confidence" in fields

    def test_schema_minimal_construct(self):
        """无新字段时也能构造（向后兼容）"""
        from app.routers.wp_k_expense_analysis import ExpenseAnalysisResponse

        resp = ExpenseAnalysisResponse(
            yoy_changes={},
            budget_variances=None,
            industry_comparison=None,
            anomaly_flags=[],
            summary="ok",
            is_llm_stub=True,
        )
        # 默认值存在
        assert resp.reasoning is None
        assert resp.references == []
        assert resp.data_sources == []
        assert resp.confidence == 0.0

    def test_schema_full_construct(self):
        from app.routers.wp_k_expense_analysis import ExpenseAnalysisResponse

        resp = ExpenseAnalysisResponse(
            yoy_changes={},
            budget_variances=None,
            industry_comparison=None,
            anomaly_flags=[],
            summary="ok",
            is_llm_stub=False,
            reasoning="规则引擎判断",
            references=[{"type": "CAS", "code": "CAS 28", "section": "复核"}],
            data_sources=["WP:K8:本年费用"],
            confidence=0.75,
        )
        assert resp.reasoning == "规则引擎判断"
        assert resp.references[0]["code"] == "CAS 28"
        assert resp.data_sources == ["WP:K8:本年费用"]
        assert resp.confidence == 0.75


# ─── 3. K8 _build_reasoning_chain 函数 ──────────────────────────────────────


class TestBuildReasoningChainK8:
    def _make_yoy(self):
        return {
            "职工薪酬": {"amount_change": 5000, "rate_change": 0.05, "flag": "normal"},
            "广告费": {"amount_change": 100000, "rate_change": 0.50, "flag": "increase_anomaly"},
        }

    def test_stub_mode_confidence_zero(self):
        """LLM stub 时 confidence=0.0"""
        from app.routers.wp_k_expense_analysis import _build_reasoning_chain

        reasoning, refs, sources, conf = _build_reasoning_chain(
            "K8", self._make_yoy(), None, None, ["yoy_increase_anomaly_广告费"], is_llm_stub=True
        )
        assert reasoning is not None
        assert "2 个费用类别" in reasoning
        assert "1 项异常" in reasoning
        assert "降级" in reasoning  # stub 时含降级提示
        assert isinstance(refs, list) and len(refs) >= 1
        assert any(r.get("type") == "CAS" for r in refs)
        assert isinstance(sources, list) and len(sources) >= 1
        assert all(s.startswith("WP:K8:") for s in sources)
        assert conf == 0.0

    def test_non_stub_mode_confidence_positive(self):
        """LLM 启用时 confidence > 0"""
        from app.routers.wp_k_expense_analysis import _build_reasoning_chain

        _, _, _, conf = _build_reasoning_chain(
            "K8", self._make_yoy(), None, None, [], is_llm_stub=False
        )
        assert conf > 0
        assert conf <= 1.0

    def test_data_sources_include_budget_industry_when_provided(self):
        """提供了 budget/industry 维度时 data_sources 应包含对应项"""
        from app.routers.wp_k_expense_analysis import _build_reasoning_chain

        budget = {"职工薪酬": {"variance_amount": 100, "variance_rate": 0.01, "flag": "normal"}}
        industry = {
            "职工薪酬": {"project_rate": 0.05, "industry_avg_rate": 0.04, "deviation": 0.01, "flag": "normal"}
        }
        _, _, sources, _ = _build_reasoning_chain(
            "K9", self._make_yoy(), budget, industry, [], is_llm_stub=True
        )
        joined = "|".join(sources)
        assert "WP:K9:本年费用" in joined
        assert "预算" in joined
        assert "行业" in joined
        assert "上年" in joined  # yoy 中有 rate_change != 0 → 包含上年


# ─── 4. K11 ImpairmentSummaryResponse schema ──────────────────────────────


class TestImpairmentSummaryResponseSchema:
    def test_schema_has_reasoning_chain_fields(self):
        from app.routers.wp_k_impairment_summary import ImpairmentSummaryResponse

        fields = ImpairmentSummaryResponse.model_fields
        assert "reasoning" in fields
        assert "references" in fields
        assert "data_sources" in fields
        assert "confidence" in fields

    def test_schema_minimal_construct(self):
        from app.routers.wp_k_impairment_summary import ImpairmentSummaryResponse

        resp = ImpairmentSummaryResponse(
            impairment_by_type=[],
            total_impairment=0.0,
            sources_found=[],
            sources_missing=[],
            summary="ok",
            is_llm_stub=True,
        )
        assert resp.reasoning is None
        assert resp.references == []
        assert resp.data_sources == []
        assert resp.confidence == 0.0


# ─── 5. K11 _build_impairment_reasoning ────────────────────────────────────


class TestBuildImpairmentReasoning:
    def test_stub_mode_includes_degradation_marker(self):
        from app.routers.wp_k_impairment_summary import _build_impairment_reasoning

        text = _build_impairment_reasoning(
            total=1_500_000.50,
            sources_found=["H1.减值测算表H1-14", "F2.存货跌价准备F2-47"],
            sources_missing=["I3 商誉减值（未提供）"],
            is_llm_stub=True,
        )
        assert "1,500,000.50" in text
        assert "2 个来源底稿" in text
        assert "1 个来源待补充" in text
        assert "降级" in text

    def test_non_stub_mode(self):
        from app.routers.wp_k_impairment_summary import _build_impairment_reasoning

        text = _build_impairment_reasoning(
            total=0.0,
            sources_found=[],
            sources_missing=["全部 4 个来源未提供"],
            is_llm_stub=False,
        )
        assert "暂无来源底稿" in text
        assert "结合 LLM" in text


# ─── 6. K11 endpoint 集成（仅响应字段存在性） ──────────────────────────────


class TestK11EndpointResponseShape:
    """通过响应模型层验证 endpoint 返回新字段（不调用 DB）"""

    def test_response_model_dump_includes_reasoning_chain(self):
        from app.routers.wp_k_impairment_summary import (
            ImpairmentByType,
            ImpairmentSummaryResponse,
        )

        resp = ImpairmentSummaryResponse(
            impairment_by_type=[
                ImpairmentByType(
                    asset_type="固定资产减值", amount=100000.0, source_wp="H1", source_sheet="减值测算表H1-14"
                )
            ],
            total_impairment=100000.0,
            sources_found=["H1.减值测算表H1-14"],
            sources_missing=["I3 商誉减值"],
            summary="K11 资产减值汇总",
            is_llm_stub=False,
            reasoning="基于 4 类资产减值规则汇总",
            references=[
                {"type": "CAS", "code": "CAS 8", "section": "资产减值"},
            ],
            data_sources=["WP:H1:固定资产减值"],
            confidence=0.85,
        )
        body = resp.model_dump()
        assert "reasoning" in body
        assert "references" in body
        assert "data_sources" in body
        assert "confidence" in body
        assert body["reasoning"] == "基于 4 类资产减值规则汇总"
        assert body["confidence"] == 0.85


# ─── 7. build_reasoning_chain 公共构造器 ───────────────────────────────────


class TestBuildReasoningChainHelper:
    """app.services.llm_service.build_reasoning_chain — 跨引擎复用的统一入口"""

    def test_stub_mode_zero_confidence(self):
        from app.services.llm_service import build_reasoning_chain

        reasoning, refs, sources, conf = build_reasoning_chain(
            reasoning="r",
            references=[{"type": "CAS", "code": "X"}],
            data_sources=["WP:Y"],
            is_llm_stub=True,
            base_confidence=0.85,
        )
        assert reasoning == "r"
        assert refs == [{"type": "CAS", "code": "X"}]
        assert sources == ["WP:Y"]
        assert conf == 0.0

    def test_non_stub_uses_base_confidence(self):
        from app.services.llm_service import build_reasoning_chain

        _, _, _, conf = build_reasoning_chain(
            reasoning="r", is_llm_stub=False, base_confidence=0.7
        )
        assert conf == 0.7

    def test_confidence_clamped(self):
        from app.services.llm_service import build_reasoning_chain

        _, _, _, hi = build_reasoning_chain(
            reasoning=None, is_llm_stub=False, base_confidence=2.5
        )
        _, _, _, lo = build_reasoning_chain(
            reasoning=None, is_llm_stub=False, base_confidence=-1.0
        )
        assert hi == 1.0
        assert lo == 0.0

    def test_none_collections_become_empty(self):
        from app.services.llm_service import build_reasoning_chain

        _, refs, sources, _ = build_reasoning_chain(
            reasoning=None, references=None, data_sources=None, is_llm_stub=True
        )
        assert refs == []
        assert sources == []


# ─── 8. 5 个 LLM stub endpoint schema 含解释链字段 ──────────────────────────


class TestStubEndpointSchemasIncludeReasoningChain:
    """H/I/G/J/N stub endpoint 响应 schema 必须含 K-4 解释链 4 字段"""

    def test_h_impairment_schema_has_fields(self):
        from app.routers.wp_h_impairment import ImpairmentAnalysisResponse

        f = ImpairmentAnalysisResponse.model_fields
        for name in ("reasoning", "references", "data_sources", "confidence"):
            assert name in f, f"H1 ImpairmentAnalysisResponse 缺少字段 {name}"

    def test_i_goodwill_schema_has_fields(self):
        from app.routers.wp_i_goodwill import GoodwillImpairmentResponse

        f = GoodwillImpairmentResponse.model_fields
        for name in ("reasoning", "references", "data_sources", "confidence"):
            assert name in f, f"I3 GoodwillImpairmentResponse 缺少字段 {name}"

    def test_g_fair_value_schema_has_fields(self):
        from app.routers.wp_g_fair_value import FairValueTestResponse

        f = FairValueTestResponse.model_fields
        for name in ("reasoning", "references", "data_sources", "confidence"):
            assert name in f, f"G FairValueTestResponse 缺少字段 {name}"

    def test_j_share_payment_schema_has_fields(self):
        from app.routers.wp_j_share_payment import SharePaymentCalcResponse

        f = SharePaymentCalcResponse.model_fields
        for name in ("reasoning", "references", "data_sources", "confidence"):
            assert name in f, f"J3 SharePaymentCalcResponse 缺少字段 {name}"

    def test_n_income_tax_schema_has_fields(self):
        from app.routers.wp_n_income_tax_calc import IncomeTaxCalcResponse

        f = IncomeTaxCalcResponse.model_fields
        for name in ("reasoning", "references", "data_sources", "confidence"):
            assert name in f, f"N5 IncomeTaxCalcResponse 缺少字段 {name}"


# ─── 9. 5 个 endpoint 内部 reasoning builder 行为 ──────────────────────────


class TestEndpointReasoningBuilders:
    """各 endpoint 内部 reasoning builder 行为：stub→0 / non-stub→正值"""

    def test_h_impairment_reasoning_via_endpoint_response_model(self):
        """直接构造响应模型即可验证默认值是合法的（向后兼容契约）"""
        from app.routers.wp_h_impairment import ImpairmentAnalysisResponse

        resp = ImpairmentAnalysisResponse(
            asset_group_id="CGU-001",
            book_value="1000000",
            present_value_of_cash_flows="900000",
            fair_value_less_costs=None,
            recoverable_amount="900000",
            impairment_loss="100000",
            is_impaired=True,
            dcf_details=[],
            summary="",
        )
        # 默认值可用
        assert resp.reasoning is None
        assert resp.references == []
        assert resp.data_sources == []
        assert resp.confidence == 0.0

    def test_i_goodwill_reasoning_helper_stub(self):
        from decimal import Decimal

        from app.routers.wp_i_goodwill import (
            GoodwillImpairmentRequest,
            _build_i3_reasoning,
        )

        payload = GoodwillImpairmentRequest(
            cgu_id="CGU-G-001",
            goodwill_book_value=Decimal("1000000"),
            other_assets_book_value=Decimal("3000000"),
            cash_flows=[Decimal("500000"), Decimal("520000")],
            discount_rate=Decimal("0.10"),
            terminal_growth_rate=Decimal("0.03"),
        )
        out = _build_i3_reasoning(
            payload,
            pv_cash_flows=Decimal("4000000"),
            recoverable_amount=Decimal("4000000"),
            impairment_loss=Decimal("0"),
            goodwill_writedown=Decimal("0"),
            other_assets_writedown=Decimal("0"),
            asset_allocations=[],
            is_llm_stub=True,
        )
        assert "DCF" in out["reasoning"]
        assert "Gordon" in out["reasoning"]
        assert any(r["type"] == "IFRS" for r in out["references"])
        assert out["confidence"] == 0.0

    def test_i_goodwill_reasoning_helper_non_stub(self):
        from decimal import Decimal

        from app.routers.wp_i_goodwill import (
            GoodwillImpairmentRequest,
            _build_i3_reasoning,
        )

        payload = GoodwillImpairmentRequest(
            cgu_id="CGU-G-001",
            goodwill_book_value=Decimal("1000000"),
            other_assets_book_value=Decimal("3000000"),
            cash_flows=[Decimal("500000")],
            discount_rate=Decimal("0.10"),
            terminal_growth_rate=Decimal("0"),
        )
        out = _build_i3_reasoning(
            payload,
            pv_cash_flows=Decimal("4000000"),
            recoverable_amount=Decimal("4000000"),
            impairment_loss=Decimal("0"),
            goodwill_writedown=Decimal("0"),
            other_assets_writedown=Decimal("0"),
            asset_allocations=[],
            is_llm_stub=False,
        )
        assert out["confidence"] > 0.5

    def test_g_fair_value_reasoning_level_3_stub(self):
        from decimal import Decimal

        from app.routers.wp_g_fair_value import (
            FairValueTestRequest,
            _build_g_fair_value_reasoning,
        )

        payload = FairValueTestRequest(
            level=3,
            instrument_type="债权投资",
            face_value=Decimal("1000000"),
            cash_flow_projections=[Decimal("200000"), Decimal("210000")],
            discount_rate=Decimal("0.10"),
            terminal_value=Decimal("0"),
        )
        reasoning, refs, sources, conf = _build_g_fair_value_reasoning(
            payload, fair_value=Decimal("950000"),
            valuation_method="Level 3（DCF）：discount_rate=0.10",
            is_llm_stub=True,
        )
        assert "Level 3" in reasoning
        assert any(r["code"] == "ISA 540" for r in refs)
        assert conf == 0.0

    def test_j_share_payment_reasoning_helper(self):
        from app.routers.wp_j_share_payment import (
            SharePaymentCalcRequest,
            _build_j3_reasoning,
        )

        payload = SharePaymentCalcRequest(
            stock_price=20,
            exercise_price=18,
            risk_free_rate=0.03,
            volatility=0.35,
            time_to_maturity=3,
            dividend_yield=0.01,
            grant_quantity=1000000,
            vesting_period=4,
        )
        result = {
            "option_value": 5.1234,
            "total_fair_value": 5123400.0,
            "annual_expense_schedule": [],
        }
        out = _build_j3_reasoning(payload, result, is_llm_stub=True)
        assert "Black-Scholes" in out["reasoning"]
        assert any(r["code"] == "IFRS 2" for r in out["references"])
        assert out["confidence"] == 0.0

    def test_n_income_tax_reasoning_helper(self):
        from app.routers.wp_n_income_tax_calc import (
            IncomeTaxCalcRequest,
            _build_n5_reasoning,
        )

        payload = IncomeTaxCalcRequest(
            profit_before_tax=10_000_000,
            statutory_rate=0.25,
            permanent_differences={"业务招待费超标": 50000},
            temporary_differences={"折旧差异": 30000},
            deferred_tax_asset_change=10000,
            deferred_tax_liability_change=5000,
        )
        result = {
            "current_income_tax": 2_520_000.0,
            "deferred_income_tax": -5000.0,
            "total_income_tax": 2_515_000.0,
            "effective_rate": 0.2515,
            "reconciliation_items": [],
        }
        out = _build_n5_reasoning(payload, result, is_llm_stub=False)
        assert "税率调节" in out["reasoning"]
        assert any(r["code"] == "CAS 18" for r in out["references"])
        assert out["confidence"] >= 0.85
