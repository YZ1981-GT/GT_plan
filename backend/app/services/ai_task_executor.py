"""声明式 AI 任务执行入口。

它统一任务边界、Prompt 版本和 typed LLM 结果；业务事实和写回仍由各领域服务负责。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any, Iterable

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
    #: ADR-LLM-018 可复现 envelope：只含哈希与参数，不含正文
    envelope: dict[str, Any] | None = None

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
            "estimated_cost": _estimated_cost(self.result),
            "envelope": self.envelope,
            "envelope_hash": _canonical_hash(self.envelope) if self.envelope else None,
        }


def _sha256(text: str | None) -> str | None:
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def actor_role(user: Any) -> str | None:
    """调用者的平台角色字符串（``UserRole`` 枚举取 value）；取不到时为 None，由执行器拒绝。"""
    role = getattr(user, "role", None)
    if role is None:
        return None
    value = getattr(role, "value", role)
    return str(value) if value else None


def _estimated_cost(result: LLMInvocationResult) -> float:
    """按部署位置的配置单价估算成本（需求 8.3）；未配置单价时为 0。"""
    from app.services.ai_chat.metrics import estimate_task_cost

    return estimate_task_cost(result.deployment, result.prompt_tokens, result.completion_tokens)


def _app_version() -> dict[str, Any]:
    try:
        from app.core.build_version import get_build_version

        build = get_build_version() or {}
    except Exception:  # pragma: no cover - 构建信息缺失不影响生成
        build = {}
    return {k: build.get(k) for k in sorted(build) if isinstance(build.get(k), (str, int))}


def build_reproducibility_envelope(
    spec: AiTaskSpec,
    *,
    prompt_version: str,
    prompt_hash: str,
    result: LLMInvocationResult,
    verifier: AiVerifierOutcome | None,
    user_prompt: str,
    system_addendum: str | None,
    context_documents: Iterable[str],
    temperature: float,
    action: str | None,
) -> dict[str, Any]:
    """ADR-LLM-018：记录能重放一次生成所需的全部标识与哈希，不保存任何正文。"""
    docs = [str(doc) for doc in context_documents]
    return {
        "schema": "ai_task_envelope/v1",
        "task_code": spec.task_code,
        "action": action,
        "risk_class": spec.risk_class.value,
        "prompt": {"id": spec.prompt_id, "version": prompt_version, "sha256": prompt_hash},
        "model": {
            "id": str(result.model_id) if result.model_id else None,
            "name": result.model_name,
            "deployment": result.deployment,
            "fallback_used": result.fallback_used,
            "attempts": list(result.attempts),
        },
        "parameters": {
            "temperature": temperature,
            "max_output_tokens": spec.max_output_tokens,
            "timeout_seconds": spec.timeout_seconds,
            "mask_policy": spec.mask_policy,
            "effective_mask_policy": result.effective_mask_policy,
            "context_recipe": spec.context_recipe,
            "output_schema": spec.output_schema,
            "writeback_policy": spec.writeback_policy,
        },
        "app_version": _app_version(),
        "context": {
            "user_prompt_sha256": _sha256(user_prompt),
            "system_addendum_sha256": _sha256(system_addendum),
            "document_sha256": [_sha256(doc) for doc in docs],
        },
        "output_sha256": verifier.output_hash if verifier else None,
        "status": result.status.value,
        "error_code": result.error_code,
        "verifier": {
            "id": spec.verifier_id,
            "status": verifier.status if verifier else "not_run",
            "reason_code": verifier.reason_code if verifier else None,
        },
    }


async def invoke_ai_task(
    task_code: str,
    *,
    user_prompt: str,
    context_documents: list[str] | None = None,
    role: str | None = None,
    system_addendum: str | None = None,
    temperature: float = 0.2,
    action: str | None = None,
    verifier_facts: Iterable[str] | None = None,
) -> AiTaskInvocation:
    """执行登记任务；未登记、角色越界或禁止任务均在调用模型前 fail-closed。"""
    spec = get_ai_task_spec(task_code)
    prompt = get_prompt(spec.prompt_id, spec.prompt_version)
    docs = list(context_documents or [])

    def _done(result: LLMInvocationResult, verifier: AiVerifierOutcome | None = None) -> AiTaskInvocation:
        envelope = build_reproducibility_envelope(
            spec, prompt_version=prompt.version, prompt_hash=prompt.sha256,
            result=result, verifier=verifier, user_prompt=user_prompt,
            system_addendum=system_addendum, context_documents=docs,
            temperature=temperature, action=action,
        )
        return AiTaskInvocation(spec, prompt.version, prompt.sha256, result, verifier, envelope)

    if spec.risk_class is AiTaskRisk.prohibited:
        result = LLMInvocationResult(
            status=LLMInvocationStatus.rejected,
            error_code="professional_judgment_required",
            error_message="此事项需要审计师专业判断，AI 只提供数据和判断因素",
        )
        return _done(result)
    if not role:
        # 角色缺失不等于放行：调用方漏传角色时角色门禁形同虚设（ADR-LLM-008）。
        result = LLMInvocationResult(
            status=LLMInvocationStatus.rejected,
            error_code="ai_role_missing",
            error_message="未识别调用者角色，不能执行 AI 任务",
        )
        return _done(result)
    if role not in spec.allowed_roles:
        result = LLMInvocationResult(
            status=LLMInvocationStatus.rejected,
            error_code="ai_role_denied",
            error_message="当前角色不能执行该 AI 任务",
        )
        return _done(result)
    if action is None or action not in spec.allowed_actions:
        result = LLMInvocationResult(
            status=LLMInvocationStatus.rejected,
            error_code="ai_action_denied",
            error_message="该 AI 任务不支持当前动作",
        )
        return _done(result)

    system = prompt.content
    if system_addendum:
        system = f"{system}\n\n{system_addendum.strip()}"
    try:
        result = await asyncio.wait_for(
            chat_completion_result(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=spec.max_output_tokens,
                context_documents=docs or None,
                allowed_trust_zones=frozenset(zone.value for zone in spec.allowed_trust_zones),
                client_data=True,
                task_mask_policy=spec.mask_policy,
                actor_role=role,
            ),
            timeout=spec.timeout_seconds,
        )
    except asyncio.TimeoutError:
        result = LLMInvocationResult(
            status=LLMInvocationStatus.timeout,
            error_code="task_timeout",
            error_message=f"AI 任务超过 {spec.timeout_seconds} 秒未完成，本次未生成内容",
        )
    verifier: AiVerifierOutcome | None = None
    if result.succeeded:
        verifier = verify_ai_output(
            spec,
            result.text or "",
            user_prompt=user_prompt,
            system_addendum=system_addendum,
            context_documents=docs,
            allowed_facts=list(verifier_facts or ()),
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
    return _done(result, verifier)
