"""AI 任务注册表、Prompt 版本和执行边界。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.ai_task_executor import invoke_ai_task
from app.services.ai_task_registry import (
    AI_TASK_SPECS,
    PROMPT_VERSIONS,
    AiTaskNotRegistered,
    get_ai_task_spec,
    get_prompt,
    validate_registry,
)
from app.services.llm_client import LLMInvocationResult, LLMInvocationStatus


def test_every_task_resolves_exact_prompt_version() -> None:
    validate_registry()
    for spec in AI_TASK_SPECS.values():
        prompt = get_prompt(spec.prompt_id, spec.prompt_version)
        assert prompt.version == spec.prompt_version
        assert len(prompt.sha256) == 64


def test_prompt_versions_are_unique_and_append_ordered() -> None:
    for prompt_id, versions in PROMPT_VERSIONS.items():
        assert versions
        assert all(v.prompt_id == prompt_id for v in versions)
        names = [v.version for v in versions]
        assert len(names) == len(set(names))


def test_unregistered_task_fails_closed() -> None:
    with pytest.raises(AiTaskNotRegistered):
        get_ai_task_spec("unknown.task")


@pytest.mark.asyncio
async def test_role_denied_before_model_call() -> None:
    with patch(
        "app.services.ai_task_executor.chat_completion_result", new=AsyncMock()
    ) as model:
        invocation = await invoke_ai_task(
            "note.policy_draft", user_prompt="测试", role="qc"
        )
    assert invocation.result.status is LLMInvocationStatus.rejected
    assert invocation.result.error_code == "ai_role_denied"
    model.assert_not_awaited()


@pytest.mark.asyncio
async def test_execution_uses_registered_prompt_and_exposes_audit_envelope() -> None:
    success = LLMInvocationResult(
        status=LLMInvocationStatus.success,
        text="草稿",
        model_name="served-model",
        deployment="local",
        total_tokens=12,
    )
    with patch(
        "app.services.ai_task_executor.chat_completion_result",
        new=AsyncMock(return_value=success),
    ) as model:
        invocation = await invoke_ai_task(
            "note.policy_draft", user_prompt="用户事实", role="auditor"
        )
    sent = model.await_args.args[0]
    assert sent[0]["content"] == get_prompt("note.policy_draft").content
    assert sent[1]["content"] == "用户事实"
    envelope = invocation.audit_metadata()
    assert envelope["task_code"] == "note.policy_draft"
    assert envelope["model_name"] == "served-model"
    assert envelope["prompt_hash"] == get_prompt("note.policy_draft").sha256


@pytest.mark.asyncio
async def test_note_fact_verifier_rejects_invented_number() -> None:
    success = LLMInvocationResult(
        status=LLMInvocationStatus.success,
        text="本期余额为 999999 元。",
        model_name="fake",
        deployment="local",
    )
    with patch(
        "app.services.ai_task_executor.chat_completion_result",
        new=AsyncMock(return_value=success),
    ):
        invocation = await invoke_ai_task(
            "note.change_analysis",
            user_prompt="本期余额为 100000 元。",
            role="auditor",
        )
    assert invocation.result.status is LLMInvocationStatus.invalid_output
    assert invocation.result.text is None
    assert invocation.result.error_code == "unverified_fact_token"
    assert invocation.verifier is not None and invocation.verifier.status == "failed"


@pytest.mark.asyncio
async def test_professional_boundary_rejects_final_audit_opinion() -> None:
    success = LLMInvocationResult(
        status=LLMInvocationStatus.success,
        text="据此确定出具无保留审计意见。",
        model_name="fake",
        deployment="local",
    )
    with patch(
        "app.services.ai_task_executor.chat_completion_result",
        new=AsyncMock(return_value=success),
    ):
        invocation = await invoke_ai_task(
            "workpaper.subject_conclusion_advice",
            user_prompt="请给出科目结论措辞建议。",
            role="auditor",
        )
    assert invocation.result.status is LLMInvocationStatus.invalid_output
    assert invocation.result.error_code == "final_opinion_prohibited"


@pytest.mark.asyncio
async def test_citation_required_task_without_context_is_not_a_draft() -> None:
    success = LLMInvocationResult(
        status=LLMInvocationStatus.success,
        text="建议核实披露事项。",
        model_name="fake",
        deployment="local",
    )
    with patch(
        "app.services.ai_task_executor.chat_completion_result",
        new=AsyncMock(return_value=success),
    ):
        invocation = await invoke_ai_task(
            "note.completeness_review",
            user_prompt="检查完整性",
            role="auditor",
            context_documents=[],
        )
    assert invocation.result.status is LLMInvocationStatus.invalid_output
    assert invocation.result.error_code == "citation_context_missing"
    assert invocation.audit_metadata()["verifier_status"] == "failed"
