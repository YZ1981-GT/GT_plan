"""底稿 AI 高风险入口的 typed 失败语义。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm_client import LLMInvocationResult, LLMInvocationStatus
from app.services.wp_ai_service import WpAIService


def _invocation(result):
    return SimpleNamespace(
        result=result,
        spec=SimpleNamespace(task_code="workpaper.subject_conclusion_advice"),
        prompt_version="1.0.0",
        prompt_hash="b" * 64,
    )


@pytest.mark.asyncio
async def test_scenario_failure_has_no_fallback_conclusion() -> None:
    failed = LLMInvocationResult(
        status=LLMInvocationStatus.unavailable,
        error_code="provider_unreachable",
        error_message="不可达",
    )
    with patch(
        "app.services.ai_task_executor.invoke_ai_task",
        new=AsyncMock(return_value=_invocation(failed)),
    ), patch(
        "app.services.export_mask_service.export_mask_service.mask_text",
        return_value=("已脱敏", {}),
    ):
        result = await WpAIService(MagicMock())._execute_llm_with_mask(
            "系统提示", "业务数据", "audit_conclusion"
        )

    assert result["type"] == "ai_error"
    assert result["content"] is None
    assert result["confidence"] is None
    assert result["error_code"] == "provider_unreachable"


@pytest.mark.asyncio
async def test_scenario_success_uses_actual_model_without_fake_confidence() -> None:
    success = LLMInvocationResult(
        status=LLMInvocationStatus.success,
        text="待人工复核的措辞",
        model_name="served-model",
        deployment="server",
        fallback_used=True,
    )
    with patch(
        "app.services.ai_task_executor.invoke_ai_task",
        new=AsyncMock(return_value=_invocation(success)),
    ), patch(
        "app.services.export_mask_service.export_mask_service.mask_text",
        return_value=("已脱敏", {}),
    ):
        result = await WpAIService(MagicMock())._execute_llm_with_mask(
            "系统提示", "业务数据", "audit_conclusion"
        )

    assert result["content"] == "待人工复核的措辞"
    assert result["source_model"] == "served-model"
    assert result["confidence"] is None


@pytest.mark.asyncio
async def test_field_suggestion_failure_never_returns_generic_clean_opinion() -> None:
    failed = LLMInvocationResult(
        status=LLMInvocationStatus.timeout,
        error_code="provider_timeout",
        error_message="超时",
    )
    with patch(
        "app.services.ai_task_executor.invoke_ai_task",
        new=AsyncMock(return_value=_invocation(failed)),
    ), patch(
        "app.core.config.settings.WP_AI_SERVICE_ENABLED", True
    ):
        result = await WpAIService(MagicMock()).suggest_field_content(
            MagicMock(), "审定表", "审计结论"
        )

    assert result["text"] == ""
    assert result["confidence"] is None
    assert result["error_code"] == "provider_timeout"


@pytest.mark.asyncio
async def test_missing_prompt_is_error_not_placeholder_draft() -> None:
    service = WpAIService(MagicMock())
    service._load_llm_prompt = AsyncMock(return_value=None)
    result = await service.generate_audit_conclusion(
        MagicMock(), "E1", 2025,
    )
    assert result["type"] == "ai_error"
    assert result["content"] is None
    assert result["confidence"] is None
    assert result["error_code"] == "prompt_not_configured"
