"""AI Chat 可选上下文能力的生产 adapter 登记。"""

from __future__ import annotations

CONTEXT_CAPABILITY_ADAPTERS: dict[str, str] = {
    "attachments": "AttachmentService.validate_for_run",
    "review_mode": "resolve_review_mode",
    "mentions": "load_mention_context",
}


def context_capability_enabled(name: str) -> bool:
    return name in CONTEXT_CAPABILITY_ADAPTERS
