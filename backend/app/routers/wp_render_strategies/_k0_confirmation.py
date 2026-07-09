"""K0 管理循环函证 — 专属渲染策略.

覆盖新建 componentType：
- confirmation-alternative-k05 → K0-5 其他应收款替代程序（4 区块宽表）
- confirmation-alternative-k06 → K0-6 其他应付款替代程序（4 区块宽表）

数据持久化在 working_paper.parsed_data.html_data[sheet]，
由前端 buildPayload → wp_html_save 写回。
"""
from __future__ import annotations

import logging

from ._context import RenderContext

logger = logging.getLogger(__name__)

_INITIAL_FORMAT: dict[str, str] = {
    "confirmation-alternative-k05": "alternative-k05-v1",
    "confirmation-alternative-k06": "alternative-k06-v1",
}


def _initial_data(component_type: str) -> dict:
    fmt = _INITIAL_FORMAT.get(component_type, "confirmation-v1")
    return {"_format": fmt, "companies": []}


async def _render_confirmation(ctx: RenderContext, component_type: str) -> dict | None:
    existing = ctx.sheet_html_data
    fmt = _INITIAL_FORMAT.get(component_type)
    if isinstance(existing, dict) and existing.get("_format") == fmt:
        return existing
    return _initial_data(component_type)


async def render_k0_alternative_k05(ctx: RenderContext) -> dict | None:
    """Render 策略: confirmation-alternative-k05（K0-5 其他应收款替代程序）."""
    return await _render_confirmation(ctx, "confirmation-alternative-k05")


async def render_k0_alternative_k06(ctx: RenderContext) -> dict | None:
    """Render 策略: confirmation-alternative-k06（K0-6 其他应付款替代程序）."""
    return await _render_confirmation(ctx, "confirmation-alternative-k06")
