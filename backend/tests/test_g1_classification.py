"""Unit tests for G-F11 金融资产分类辅助 (CAS 22 / IFRS 9)
— 3 种分类结果 × 写回 × RBAC × is_llm_stub config-driven.

Decision tree:
- (hold_to_collect, SPPI pass)  → amortized_cost
- (hold_and_sell, SPPI pass)    → fvoci
- (other, *)  OR  (*, SPPI fail) → fvtpl

对应 spec: workpaper-g-investment-cycle G-F11
对应 task: Sprint 3 Task 3.3 + 3.4
"""

from __future__ import annotations

import sys

sys.path.insert(0, "backend")

import asyncio
import inspect

import pytest
from fastapi import HTTPException

from app.routers.wp_g_classification import (
    ClassificationCheckRequest,
    ClassificationCheckResponse,
    _build_reasoning,
    _classify,
    _maybe_apply_classification_to_workpaper,
    g1_classification_check,
    router,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CLASSIFY — 决策树正确性（3 种结果 + boundary）
# ═══════════════════════════════════════════════════════════════════════════════


class TestClassifyDecisionTree:
    """3 种分类结果（CAS 22 / IFRS 9 决策树）"""

    def test_amortized_cost_path(self):
        """hold_to_collect + SPPI pass → 摊余成本"""
        suggestion, label = _classify("hold_to_collect", "pass")
        assert suggestion == "amortized_cost"
        assert "摊余成本" in label

    def test_fvoci_path(self):
        """hold_and_sell + SPPI pass → FVOCI"""
        suggestion, label = _classify("hold_and_sell", "pass")
        assert suggestion == "fvoci"
        assert "其他综合收益" in label
        assert "FVOCI" in label

    def test_fvtpl_via_sppi_fail(self):
        """SPPI fail → FVTPL（无论 business_model）"""
        for bm in ("hold_to_collect", "hold_and_sell", "other"):
            suggestion, label = _classify(bm, "fail")
            assert suggestion == "fvtpl", f"business_model={bm} + SPPI fail 应为 fvtpl"
            assert "当期损益" in label
            assert "FVTPL" in label

    def test_fvtpl_via_other_business_model(self):
        """business_model=other → FVTPL（无论 SPPI）"""
        for sppi in ("pass", "fail"):
            suggestion, label = _classify("other", sppi)
            assert suggestion == "fvtpl"

    def test_six_combinations_complete(self):
        """3 × 2 = 6 种组合全部命中明确分类"""
        results = {}
        for bm in ("hold_to_collect", "hold_and_sell", "other"):
            for sppi in ("pass", "fail"):
                suggestion, _ = _classify(bm, sppi)
                results[(bm, sppi)] = suggestion
        # Verify expected mapping
        assert results[("hold_to_collect", "pass")] == "amortized_cost"
        assert results[("hold_to_collect", "fail")] == "fvtpl"
        assert results[("hold_and_sell", "pass")] == "fvoci"
        assert results[("hold_and_sell", "fail")] == "fvtpl"
        assert results[("other", "pass")] == "fvtpl"
        assert results[("other", "fail")] == "fvtpl"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. ENDPOINT — 完整响应 + 3 种分类结果验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestClassificationEndpoint:
    """endpoint 返回完整字段 + 3 种分类结果"""

    def test_amortized_cost_response(self):
        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = ClassificationCheckRequest(
                business_model="hold_to_collect",
                sppi_result="pass",
                instrument_name="国债 2025-1 期",
            )
            return await g1_classification_check(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        assert isinstance(resp, ClassificationCheckResponse)
        assert resp.classification_suggestion == "amortized_cost"
        assert "摊余成本" in resp.classification_label_zh
        assert "国债 2025-1 期" in resp.reasoning
        assert resp.applied_to_sheet is None

    def test_fvoci_response(self):
        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = ClassificationCheckRequest(
                business_model="hold_and_sell",
                sppi_result="pass",
                instrument_name="可流通债券 A",
            )
            return await g1_classification_check(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        assert resp.classification_suggestion == "fvoci"
        assert "FVOCI" in resp.classification_label_zh

    def test_fvtpl_response_via_sppi_fail(self):
        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = ClassificationCheckRequest(
                business_model="hold_to_collect",
                sppi_result="fail",  # SPPI 不通过
                instrument_name="复杂金融产品",
            )
            return await g1_classification_check(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        assert resp.classification_suggestion == "fvtpl"
        assert "FVTPL" in resp.classification_label_zh

    def test_fvtpl_response_via_other_business_model(self):
        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = ClassificationCheckRequest(
                business_model="other",
                sppi_result="pass",
                instrument_name="交易性持有股票",
            )
            return await g1_classification_check(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        assert resp.classification_suggestion == "fvtpl"

    def test_endpoint_invalid_project_id_returns_400(self):
        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = ClassificationCheckRequest(
                business_model="hold_to_collect",
                sppi_result="pass",
            )
            return await g1_classification_check(
                project_id="not-a-valid-uuid",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(_run())
        assert exc_info.value.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# 3. PYDANTIC VALIDATION — 枚举值非法 → ValidationError
# ═══════════════════════════════════════════════════════════════════════════════


class TestPydanticValidation:
    def test_invalid_business_model_raises(self):
        with pytest.raises(Exception):
            ClassificationCheckRequest(
                business_model="invalid_model",  # type: ignore[arg-type]
                sppi_result="pass",
            )

    def test_invalid_sppi_result_raises(self):
        with pytest.raises(Exception):
            ClassificationCheckRequest(
                business_model="hold_to_collect",
                sppi_result="maybe",  # type: ignore[arg-type]
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. WRITE-BACK — apply_to_sheet 写回 parsed_data.classification_checks[sheet]
# ═══════════════════════════════════════════════════════════════════════════════


class TestWriteBack:
    def test_writeback_helper_exists_and_callable(self):
        assert callable(_maybe_apply_classification_to_workpaper)

    def test_writeback_helper_is_async(self):
        assert inspect.iscoroutinefunction(_maybe_apply_classification_to_workpaper)

    def test_writeback_returns_none_when_apply_to_sheet_none(self):
        async def _run():
            payload = ClassificationCheckRequest(
                business_model="hold_to_collect",
                sppi_result="pass",
                apply_to_sheet=None,
            )
            return await _maybe_apply_classification_to_workpaper(
                db=None,  # type: ignore[arg-type]
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                suggestion="amortized_cost",
                label_zh="以摊余成本计量",
                reasoning="...",
                is_llm_stub=False,
            )

        assert asyncio.run(_run()) is None

    def test_writeback_returns_none_when_invalid_wp_id(self):
        async def _run():
            payload = ClassificationCheckRequest(
                business_model="hold_to_collect",
                sppi_result="pass",
                apply_to_sheet="业务模式分析G1-8",
            )
            return await _maybe_apply_classification_to_workpaper(
                db=None,  # type: ignore[arg-type]
                wp_id="not-a-uuid",
                payload=payload,
                suggestion="amortized_cost",
                label_zh="...",
                reasoning="...",
                is_llm_stub=False,
            )

        assert asyncio.run(_run()) is None

    def test_writeback_populates_parsed_data_structure(self):
        wp = _FakeWorkpaper(parsed_data=None)
        mock_db = _FakeAsyncSession(workpaper=wp)
        sheet_name = "业务模式分析G1-8"

        async def _run():
            payload = ClassificationCheckRequest(
                business_model="hold_and_sell",
                sppi_result="pass",
                instrument_name="债券A",
                apply_to_sheet=sheet_name,
            )
            return await _maybe_apply_classification_to_workpaper(
                db=mock_db,
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                suggestion="fvoci",
                label_zh="以公允价值计量且其变动计入其他综合收益",
                reasoning="决策路径: ...",
                is_llm_stub=False,
            )

        applied = asyncio.run(_run())
        assert applied == sheet_name
        assert wp.parsed_data is not None
        assert "classification_checks" in wp.parsed_data
        record = wp.parsed_data["classification_checks"][sheet_name]
        assert record["business_model"] == "hold_and_sell"
        assert record["sppi_result"] == "pass"
        assert record["classification_suggestion"] == "fvoci"
        assert record["instrument_name"] == "债券A"
        assert record["is_llm_stub"] is False
        assert "applied_at" in record
        assert mock_db.flush_called
        assert mock_db.commit_called

    def test_writeback_endpoint_e2e(self):
        wp = _FakeWorkpaper(parsed_data={"existing": "data"})
        mock_db = _FakeAsyncSession(workpaper=wp)
        sheet_name = "合同现金流量特征分析G1-10"

        async def _run():
            payload = ClassificationCheckRequest(
                business_model="hold_to_collect",
                sppi_result="fail",
                instrument_name="复合金融工具",
                apply_to_sheet=sheet_name,
            )
            return await g1_classification_check(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        assert resp.applied_to_sheet == sheet_name
        assert resp.classification_suggestion == "fvtpl"
        # 既有数据保留
        assert wp.parsed_data["existing"] == "data"
        assert wp.parsed_data["classification_checks"][sheet_name]["classification_suggestion"] == "fvtpl"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. RBAC — require_project_access("edit") 强制校验
# ═══════════════════════════════════════════════════════════════════════════════


class TestRBAC:
    def test_route_uses_require_project_access_edit(self):
        import app.routers.wp_g_classification as mod
        src = inspect.getsource(mod)
        assert 'require_project_access("edit")' in src, (
            "wp_g_classification 必须用 require_project_access('edit')"
        )

    def test_endpoint_function_has_user_dependency(self):
        sig = inspect.signature(g1_classification_check)
        assert "_user" in sig.parameters

    def test_router_prefix_contains_project_id_and_wp_id(self):
        assert "{project_id}" in router.prefix
        assert "{wp_id}" in router.prefix
        assert "/g1" in router.prefix

    def test_endpoint_is_async(self):
        assert inspect.iscoroutinefunction(g1_classification_check)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. is_llm_stub — config-driven (与 G-F4 同模式)
# ═══════════════════════════════════════════════════════════════════════════════


class TestStubFlagConfigDriven:
    """is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动"""

    def test_is_llm_stub_true_when_ai_disabled(self, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "WP_AI_SERVICE_ENABLED", False)

        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = ClassificationCheckRequest(
                business_model="hold_to_collect",
                sppi_result="pass",
            )
            return await g1_classification_check(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        assert resp.is_llm_stub is True
        assert "wp_ai_service" in resp.reasoning

    def test_is_llm_stub_false_when_ai_enabled(self, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "WP_AI_SERVICE_ENABLED", True)

        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = ClassificationCheckRequest(
                business_model="hold_to_collect",
                sppi_result="pass",
            )
            return await g1_classification_check(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        assert resp.is_llm_stub is False
        assert "wp_ai_service" not in resp.reasoning


# ═══════════════════════════════════════════════════════════════════════════════
# 7. REASONING TEXT — 含 6 个变量插值（避免文案空洞）
# ═══════════════════════════════════════════════════════════════════════════════


class TestReasoningText:
    """reasoning 文案应含 instrument_name + business_model + sppi + 决策路径"""

    def test_reasoning_includes_instrument_name(self):
        text = _build_reasoning(
            business_model="hold_to_collect",
            sppi_result="pass",
            suggestion="amortized_cost",
            instrument_name="特定债券",
            is_llm_stub=False,
        )
        assert "特定债券" in text

    def test_reasoning_default_instrument_when_none(self):
        text = _build_reasoning(
            business_model="hold_to_collect",
            sppi_result="pass",
            suggestion="amortized_cost",
            instrument_name=None,
            is_llm_stub=False,
        )
        assert "该金融资产" in text

    def test_reasoning_includes_business_model_zh(self):
        text = _build_reasoning(
            business_model="hold_to_collect",
            sppi_result="pass",
            suggestion="amortized_cost",
            instrument_name=None,
            is_llm_stub=False,
        )
        assert "持有以收取" in text

    def test_reasoning_includes_decision_path(self):
        for sg in ("amortized_cost", "fvoci", "fvtpl"):
            text = _build_reasoning(
                business_model="hold_to_collect",
                sppi_result="pass",
                suggestion=sg,
                instrument_name=None,
                is_llm_stub=False,
            )
            assert "决策路径" in text


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers — fake DB / fake workpaper for write-back testing
# ═══════════════════════════════════════════════════════════════════════════════


class _FakeWorkpaper:
    def __init__(self, parsed_data: dict | None = None):
        self.parsed_data = parsed_data


class _FakeScalarResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _FakeAsyncSession:
    def __init__(self, workpaper=None):
        self._workpaper = workpaper
        self.flush_called = False
        self.commit_called = False

    async def execute(self, _stmt):
        return _FakeScalarResult(self._workpaper)

    async def flush(self):
        self.flush_called = True

    async def commit(self):
        self.commit_called = True


def _make_mock_db_no_writeback():
    return _FakeAsyncSession(workpaper=None)
