"""附注 AI 端点不得把模型故障包装成正文。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.routers import note_ai
from app.services.llm_client import LLMInvocationResult, LLMInvocationStatus
from app.services.note_ai_fact_pack import NoteFactPackUnavailable


_FAILED = LLMInvocationResult(
    status=LLMInvocationStatus.unavailable,
    error_code="provider_unreachable",
    error_message="不可达",
)


def _invocation(result=_FAILED, task_code="note.policy_draft"):
    return SimpleNamespace(
        result=result,
        spec=SimpleNamespace(task_code=task_code, prompt_id=task_code),
        prompt_version="1.0.0",
        prompt_hash="a" * 64,
    )


@pytest.mark.asyncio
async def test_generate_policy_failure_has_no_generated_text() -> None:
    with patch.object(note_ai, "require_project_audit_year", new=AsyncMock(return_value=2025)), patch(
        "app.services.reference_doc_service.ReferenceDocService.load_context",
        new=AsyncMock(return_value=[]),
    ), patch.object(note_ai, "invoke_ai_task", new=AsyncMock(return_value=_invocation())):
        result = await note_ai.generate_policy(
            uuid4(), note_ai.PolicyGenerateRequest(section_number="五、1"), MagicMock(), SimpleNamespace(role="auditor")
        )

    assert result["generated_text"] is None
    assert result["error_code"] == "provider_unreachable"
    assert "暂不可用" not in str(result.get("generated_text"))


@pytest.mark.asyncio
async def test_generate_analysis_missing_facts_never_calls_model() -> None:
    with patch.object(note_ai, "require_project_audit_year", new=AsyncMock(return_value=2025)), patch(
        "app.services.note_ai_fact_pack.build_note_fact_pack",
        new=AsyncMock(side_effect=NoteFactPackUnavailable("current_data_missing", "没有本期数据")),
    ), patch.object(note_ai, "invoke_ai_task", new=AsyncMock()) as invoke:
        result = await note_ai.generate_analysis(
            uuid4(), note_ai.AnalysisGenerateRequest(section_number="五、1"), MagicMock(), SimpleNamespace(role="auditor")
        )

    assert result["generated_text"] is None
    assert result["error_code"] == "current_data_missing"
    invoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_rewrite_failure_does_not_echo_original_as_generated_result() -> None:
    user = SimpleNamespace(id=uuid4(), role="auditor")
    with patch.object(note_ai, "require_project_audit_year", new=AsyncMock(return_value=2025)), patch.object(
        note_ai, "_saved_note_text", new=AsyncMock(return_value="已保存：原文。")
    ), patch.object(
        note_ai, "_load_selected_knowledge", new=AsyncMock(return_value=[])
    ), patch(
        "app.services.reference_doc_service.ReferenceDocService.load_context",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.services.export_mask_service.export_mask_service.mask_text",
        return_value=("原文", {}),
    ), patch.object(
        note_ai,
        "invoke_ai_task",
        new=AsyncMock(return_value=_invocation(task_code="note.rewrite")),
    ):
        result = await note_ai.ai_rewrite(
            uuid4(), note_ai.RewriteRequest(text="原文"), MagicMock(), user
        )

    assert result["rewritten"] is None
    assert result["original"] == "原文"
    assert result["error_code"] == "provider_unreachable"
