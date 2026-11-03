"""LLM 出站正文的统一脱敏策略。

同一次调用可能从本机切到服务器候选，因此发送前按“任务最低策略 + 全部可尝试
候选最低策略”取最严格值。映射原文只存在于本函数栈，不进入日志或指标。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.ai_chat.mcp_token import McpMaskLevel, resolve_mask_policy
from app.services.export_mask_service import export_mask_service
from app.services.llm_runtime import RouteCandidate

_POLICY_RANK = {"none": 0, "role_based": 1, "strict": 2}


@dataclass(frozen=True)
class SanitizedPayload:
    messages: list[dict[str, Any]]
    effective_policy: str
    masked_value_count: int
    restore_mapping: dict[str, str]


def _normalized(value: str | None) -> str:
    if value == "none":
        return "none"
    if value in {"role_based", "standard", "partial"}:
        return "role_based"
    return "strict"


def effective_mask_policy(
    *,
    task_policy: str,
    actor_role: str | None,
    route: list[RouteCandidate],
) -> str:
    policies = [_normalized(task_policy)]
    policies.extend(
        _normalized(candidate.config.mask_policy)
        for candidate in route
        if candidate.config is not None
    )
    policy = max(policies, key=lambda value: _POLICY_RANK[value])
    if policy == "role_based":
        role_policy = resolve_mask_policy(actor_role)
        if role_policy in {McpMaskLevel.NONE}:
            return "none"
        # 未知角色不得把策略放宽；严格遮蔽比把客户正文原样发出更安全。
        return "strict" if role_policy in {McpMaskLevel.STRICT, McpMaskLevel.REJECTED} else "role_based"
    return policy


def sanitize_messages(
    messages: list[dict[str, Any]],
    *,
    task_policy: str,
    actor_role: str | None,
    route: list[RouteCandidate],
) -> SanitizedPayload:
    policy = effective_mask_policy(
        task_policy=task_policy,
        actor_role=actor_role,
        route=route,
    )
    if policy == "none":
        return SanitizedPayload([dict(message) for message in messages], policy, 0, {})

    masked_count = 0
    restore_mapping: dict[str, str] = {}
    sanitized: list[dict[str, Any]] = []
    for message_index, message in enumerate(messages):
        copy = dict(message)
        content = copy.get("content")
        if isinstance(content, str):
            masked, mapping = export_mask_service.mask_text(content)
            for placeholder, original in mapping.items():
                scoped = f"[gt_m{message_index}_{placeholder.strip('[]')}]"
                masked = masked.replace(placeholder, scoped)
                restore_mapping[scoped] = original
            copy["content"] = masked
            masked_count += len(mapping)
        sanitized.append(copy)
    return SanitizedPayload(sanitized, policy, masked_count, restore_mapping)


def restore_masked_values(text: str, mapping: dict[str, str]) -> str:
    """只恢复本次请求签发的精确占位符，不解析或执行模型生成的其他文本。"""
    restored = text
    for placeholder, original in mapping.items():
        restored = restored.replace(placeholder, original)
    return restored
