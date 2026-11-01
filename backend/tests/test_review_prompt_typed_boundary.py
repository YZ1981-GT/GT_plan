"""单页 AI 复核失败/空发现不得变成业务通过。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.routers import review_prompt
from app.services.llm_client import LLMInvocationResult, LLMInvocationStatus


async def _invoke(invocation: LLMInvocationResult):
    wp_id = uuid4()
    with patch.object(review_prompt, "authorize_wp_read", new=AsyncMock(return_value=uuid4())), patch.object(
        review_prompt, "assert_project_permission", new=AsyncMock()
    ), patch.object(review_prompt, "_get_wp_code", new=AsyncMock(return_value="E1")), patch.object(
        review_prompt, "_get_workpaper_content", new=AsyncMock(return_value="底稿正文")
    ), patch(
        "app.services.cycle_review_context.build_review_reconciliation_context",
        new=AsyncMock(return_value=""),
    ), patch.object(review_prompt, "_call_llm", new=AsyncMock(return_value=invocation)), patch.object(
        review_prompt, "_get_project_id", new=AsyncMock(return_value=None)
    ):
        return await review_prompt.review_workpaper(
            wp_id,
            review_prompt.ReviewRequest(sheet_name="货币资金审定表"),
            MagicMock(),
            SimpleNamespace(id=uuid4()),
        )


@pytest.mark.asyncio
async def test_model_failure_is_manual_not_pass() -> None:
    response = await _invoke(
        LLMInvocationResult(
            status=LLMInvocationStatus.unavailable,
            error_code="provider_unreachable",
            error_message="模型不可达",
        )
    )
    assert response.overall_pass is False
    assert response.review_status == "manual_review_required"


@pytest.mark.asyncio
async def test_valid_empty_findings_is_advisory_not_pass() -> None:
    response = await _invoke(
        LLMInvocationResult(
            status=LLMInvocationStatus.success,
            text='{"findings": []}',
            model_name="test-model",
        )
    )
    assert response.overall_pass is False
    assert response.review_status == "ai_no_new_findings"
    assert response.findings == []
