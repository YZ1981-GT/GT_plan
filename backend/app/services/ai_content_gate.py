"""AI 内容状态机与确认门控 (P0-5).

状态机:
    suggestion → draft → confirmed
    suggestion → rejected
    draft → rejected

P0-5.4: AI_CONTENT_CONFIRMATION_STRICT 开关
    - 环境变量 AI_CONTENT_CONFIRMATION_STRICT=true 时 blocking
    - 默认 false = warning only

P0-5.5:
    - strict=false: draft 放行但附带 warning
    - strict=true: 仅 confirmed 可通过，其余阻断
"""
from __future__ import annotations

import os
from enum import Enum
from typing import Optional


# ---------- P0-5.1: AI 内容状态定义 ----------

class AiContentStatus(str, Enum):
    """AI 内容生命周期状态。"""
    suggestion = "suggestion"
    draft = "draft"
    confirmed = "confirmed"
    rejected = "rejected"


# 合法状态列表
AI_CONTENT_STATES = tuple(s.value for s in AiContentStatus)

# 合法状态流转
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "suggestion": {"draft", "rejected"},
    "draft": {"confirmed", "rejected"},
    "confirmed": set(),  # 终态
    "rejected": set(),  # 终态
}


# ---------- P0-5.4: 模块级开关 ----------

def _read_strict_flag() -> bool:
    """从环境变量读取 strict 开关。"""
    val = os.environ.get("AI_CONTENT_CONFIRMATION_STRICT", "false")
    return val.lower() in ("true", "1", "yes")


AI_CONTENT_CONFIRMATION_STRICT: bool = _read_strict_flag()


# ---------- P0-5.1: 状态查询 ----------

def is_confirmed(status: str) -> bool:
    """判断 AI 内容是否已确认。"""
    return status == AiContentStatus.confirmed.value


def is_terminal(status: str) -> bool:
    """判断是否为终态（confirmed / rejected）。"""
    return status in (AiContentStatus.confirmed.value, AiContentStatus.rejected.value)


def can_transition(current: str, target: str) -> bool:
    """判断状态流转是否合法。"""
    allowed = _VALID_TRANSITIONS.get(current, set())
    return target in allowed


# ---------- P0-5.5: 门控函数 ----------

def can_enter_formal_output(
    status: str,
    strict: Optional[bool] = None,
) -> tuple[bool, str | None]:
    """判断 AI 内容能否进入报告/附注正式导出。

    Args:
        status: AI 内容当前状态
        strict: 是否 strict 模式。None 时使用模块级开关。

    Returns:
        (allowed, message)
        - strict=True: 仅 confirmed 可通过
        - strict=False: draft 放行但附带 warning
    """
    if strict is None:
        strict = AI_CONTENT_CONFIRMATION_STRICT

    if status == AiContentStatus.confirmed.value:
        return (True, None)

    if strict:
        return (False, "AI 内容未确认，strict 模式下阻断签发")

    # non-strict: draft 放行 + warning
    if status == AiContentStatus.draft.value:
        return (True, "warning: AI 内容待确认，建议在签发前完成人工审阅")

    # suggestion / rejected 均不可
    return (False, "AI 内容未确认")


# ---------- P0-5.3: AI 状态标记工具 ----------

def mark_ai_content_status(
    current_status: Optional[str],
    target_status: str,
) -> tuple[bool, str]:
    """尝试将 AI 内容标记为目标状态。

    Returns:
        (success, message)
    """
    if current_status is None:
        # 新内容首次标记
        if target_status in (AiContentStatus.suggestion.value, AiContentStatus.draft.value):
            return (True, f"标记为 {target_status}")
        return (False, f"新内容只能标记为 suggestion 或 draft，不可直接 {target_status}")

    if not can_transition(current_status, target_status):
        return (False, f"不允许从 {current_status} 流转到 {target_status}")

    return (True, f"从 {current_status} 流转到 {target_status}")


def get_strict_mode() -> bool:
    """获取当前 strict 模式设置（可被测试动态覆盖）。"""
    return AI_CONTENT_CONFIRMATION_STRICT


# ---------- P2-2.4: Stale 来源校验 ----------

def validate_citations_freshness(
    citations: list[dict],
) -> tuple[bool, str | None]:
    """校验 AI 引用来源是否全部新鲜（非 stale）。

    如果所有引用来源都是 stale（过期索引），则该 AI 内容不可被确认为 confirmed。
    至少需要一条 fresh（非 stale）来源才能确认。

    Args:
        citations: 引用来源列表，每条含 is_stale 字段

    Returns:
        (valid, message)
        - valid=True: 至少存在一条 fresh 来源，可确认
        - valid=False: 所有来源均 stale，不可确认
    """
    if not citations:
        # 无引用来源时不阻断（可能是纯 LLM 生成无 RAG）
        return (True, None)

    fresh_count = sum(1 for c in citations if not c.get("is_stale", False))

    if fresh_count == 0:
        return (
            False,
            "AI 内容的所有知识库引用来源均已过期（stale），"
            "请等待索引重建后再确认，或手动核实内容正确性",
        )

    return (True, None)
