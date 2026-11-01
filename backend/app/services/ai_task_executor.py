"""声明式 AI 任务执行入口。

它统一任务边界、Prompt 版本和 typed LLM 结果；业务事实和写回仍由各领域服务负责。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from app.services.ai_task_registry import (
    AiTaskRisk,
    AiTaskSpec,
    get_ai_task_spec,
    get_prompt,
)
from app.services.ai_task_verifier import AiVerifierOutcome, verify_ai_output
from app.services.llm_client import (
    LLMInvocationResult,
    LLMInvocationStatus,
    chat_completion_result,
)


@dataclass(frozen=True)
class AiTaskInvocation:
    spec: AiTaskSpec
    prompt_version: str
    prompt_hash: str
    result: LLMInvocationResult
    verifier: AiVerifierOutcome | None = None

    def audit_metadata(self) -> dict[str, Any]:
        return {
            "task_code": self.spec.task_code,
            "risk_class": self.spec.risk_class.value,
            "prompt_id": self.spec.prompt_id,
            "prompt_version": self.prompt_version,
            "prompt_hash": self.prompt_hash,
            "model_id": str(self.result.model_id) if self.result.model_id else None,
            "model_name": self.result.model_name,
            "deployment": self.result.deployment,
            "fallback_used": self.result.fallback_used,
            "attempts": list(self.result.attempts),
            "total_tokens": self.result.total_tokens,
            "prompt_tokens": self.result.prompt_tokens,
            "completion_tokens": self.result.completion_tokens,
            "ttft_ms": self.result.ttft_ms,
            "tokens_per_second": self.result.tokens_per_second,
            "latency_ms": self.result.latency_ms,
            "effective_mask_policy": self.result.effective_mask_policy,
            "masked_value_count": self.result.masked_value_count,
            "status": self.result.status.value,
            "error_code": self.result.error_code,
            "verifier_id": self.spec.verifier_id,
            "verifier_status": self.verifier.status if self.verifier else "not_run",
            "verifier_reason_code": self.verifier.reason_code if self.verifier else None,
            "output_hash": self.verifier.output_hash if self.verifier else None,
        }


async def invoke_ai_task(
    task_code: str,
    *,
    user_prompt: str,
    context_documents: list[str] | None = None,
    role: str | None = None,
    system_addendum: str | None = None,
    temperature: float = 0.2,
) -> AiTaskInvocation:
    """执行登记任务；未登记、角色越界或禁止任务均在调用模型前 fail-closed。"""
    spec = get_ai_task_spec(task_code)
    prompt = get_prompt(spec.prompt_id, spec.prompt_version)
    if spec.risk_class is AiTaskRisk.prohibited:
        result = LLMInvocationResult(
            status=LLMInvocationStatus.rejected,
            error_code="professional_judgment_required",
            error_message="此事项需要审计师专业判断，AI 只提供数据和判断因素",
        )
        return AiTaskInvocation(spec, prompt.version, prompt.sha256, result)
    if role is not None and role not in spec.allowed_roles:
        result = LLMInvocationResult(
            status=LLMInvocationStatus.rejected,
            error_code="ai_role_denied",
            error_message="当前角色不能执行该 AI 任务",
        )
        return AiTaskInvocation(spec, prompt.version, prompt.sha256, result)

    system = prompt.content
    if system_addendum:
        system = f"{system}\n\n{system_addendum.strip()}"
    result = await chat_completion_result(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=spec.max_output_tokens,
        context_documents=context_documents,
        allowed_trust_zones=frozenset(zone.value for zone in spec.allowed_trust_zones),
        client_data=True,
        task_mask_policy=spec.mask_policy,
        actor_role=role,
    )
    verifier: AiVerifierOutcome | None = None
    if result.succeeded:
        verifier = verify_ai_output(
            spec,
            result.text or "",
            user_prompt=user_prompt,
            system_addendum=system_addendum,
            context_documents=context_documents or [],
        )
        if verifier.status != "passed":
            result = replace(
                result,
                status=LLMInvocationStatus.invalid_output,
                text=None,
                error_code=verifier.reason_code or "verifier_failed",
                error_message=verifier.message or "AI 输出未通过任务验证",
            )
    from app.services.ai_chat.metrics import record_ai_task_metric
    from app.services.llm_metrics import llm_metrics

    verifier_status = verifier.status if verifier else "not_run"
    llm_metrics.record_call(
        duration_ms=result.latency_ms,
        tokens_used=result.total_tokens or 0,
        success=result.succeeded,
        model=result.model_name or "route",
        error=result.error_code,
        task_code=spec.task_code,
        deployment=result.deployment,
        fallback_used=result.fallback_used,
        error_code=result.error_code,
        verifier_status=verifier_status,
        ttft_ms=result.ttft_ms,
        tokens_per_second=result.tokens_per_second,
    )
    record_ai_task_metric(
        task_code=spec.task_code,
        status=result.status.value,
        deployment=result.deployment,
        fallback_used=result.fallback_used,
        verifier_status=verifier_status,
        latency_ms=result.latency_ms,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
    )
    return AiTaskInvocation(spec, prompt.version, prompt.sha256, result, verifier)
