"""AI 内容状态映射与确认门控 (MVP).

状态机: suggestion -> draft -> confirmed
         suggestion -> rejected
         draft -> rejected
"""
from __future__ import annotations

# 模块级开关：strict=True 时 blocking，strict=False 时 warning only
AI_CONTENT_CONFIRMATION_STRICT: bool = False

# 合法 AI 内容状态
AI_CONTENT_STATES = ("suggestion", "draft", "confirmed", "rejected")


def is_confirmed(status: str) -> bool:
    """判断 AI 内容是否已确认。"""
    return status == "confirmed"


def can_enter_formal_output(
    status: str, strict: bool = False
) -> tuple[bool, str | None]:
    """判断 AI 内容能否进入报告/附注正式导出。

    Returns:
        (allowed, message)
        - strict=True: 仅 confirmed 可通过
        - strict=False: draft 放行但附带 warning
    """
    if status == "confirmed":
        return (True, None)

    if strict:
        return (False, "AI 内容未确认")

    # non-strict: draft 放行 + warning
    if status == "draft":
        return (True, "warning: AI 内容待确认")

    # suggestion / rejected 均不可
    return (False, "AI 内容未确认")
