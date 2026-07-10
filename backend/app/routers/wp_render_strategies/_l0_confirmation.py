"""L0 债务循环函证 — 专属渲染策略.

覆盖新建 componentType：
- confirmation-alternative-l05 → L0-5 长期应付款/借款替代程序（4 区块宽表）

数据持久化在 working_paper.parsed_data.html_data[sheet]，
由前端 buildPayload → wp_html_save 写回。
"""
from __future__ import annotations

import logging

from ._context import RenderContext

logger = logging.getLogger(__name__)

_INITIAL_FORMAT = "alternative-l05-v1"


def _initial_data() -> dict:
    return {"_format": _INITIAL_FORMAT, "companies": []}


async def _render_confirmation(ctx: RenderContext) -> dict | None:
    existing = ctx.sheet_html_data
    if isinstance(existing, dict) and existing.get("_format") == _INITIAL_FORMAT:
        return existing
    return _initial_data()


async def render_l0_alternative(ctx: RenderContext) -> dict | None:
    """Render 策略: confirmation-alternative-l05（L0-5 债务循环替代程序）."""
    return await _render_confirmation(ctx)
