"""H0 固定资产循环函证 — 专属渲染策略.

覆盖新建 componentType：
- confirmation-alternative-h05 → H0-5 固定资产循环替代程序（4 区块宽表，复用 D0-5 壳层）

数据持久化在 working_paper.parsed_data.html_data[sheet]，
由前端 buildPayload → wp_html_save 写回。
"""
from __future__ import annotations

import logging

from ._context import RenderContext

logger = logging.getLogger(__name__)

_INITIAL_FORMAT: dict[str, str] = {
    "confirmation-alternative-h05": "alternative-h05-v1",
}


def _initial_data(component_type: str) -> dict:
    fmt = _INITIAL_FORMAT.get(component_type, "confirmation-v1")
    if component_type == "confirmation-alternative-h05":
        return {"_format": fmt, "companies": []}
    return {"_format": fmt, "rows": [], "conclusion": "", "audit_note": ""}


async def _render_confirmation(ctx: RenderContext, component_type: str) -> dict | None:
    existing = ctx.sheet_html_data
    fmt = _INITIAL_FORMAT.get(component_type)
    if isinstance(existing, dict) and existing.get("_format") == fmt:
        return existing
    return _initial_data(component_type)


async def render_h0_alternative(ctx: RenderContext) -> dict | None:
    """Render 策略: confirmation-alternative-h05（H0-5 固定资产循环替代程序）."""
    return await _render_confirmation(ctx, "confirmation-alternative-h05")
