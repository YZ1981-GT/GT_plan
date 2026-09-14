"""G0 投资循环函证 — 专属渲染策略.

覆盖 2 个新建 confirmation componentType（同 F0 pattern，F0 复用 D0 共享组件，
无独立后端策略；G0 因证券差异核对/投资替代程序为投资循环特有，需独立策略）：

- confirmation-diff-securities     → G0-3(证券) 证券投资差异核对（持仓/公允价值/市值三维）
- confirmation-diff-nonsecurities  → G0-4(非证券) 非证券投资差异核对（持股比例/投资金额/投资条款三维）
- confirmation-alternative-g06     → G0-6 投资循环替代程序（4区块29列宽表）

这两个 componentType 是纯前端渲染组件（Vue: GtConfirmationDiffSecurities /
GtConfirmationAlternativeG06）。数据持久化在 working_paper.parsed_data.html_data[sheet]，
由前端 buildPayload → wp_html_save 写回。

render 策略的关键作用：
1. 让 component_type 命中 RENDERER_DISPATCH，避免多 sheet dispatch 循环把 G0 各 sheet
   误判为非白名单而重写成 onlyoffice-sheet（否则专属组件被吞掉）。
2. seed 回读：优先返回已持久化的 html_data（sheet_html_data）；首次打开无数据时
   返回空的新格式初始数据（_format 标记让前端识别为可编辑新表）。
"""
from __future__ import annotations

import logging

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 各 componentType 首次打开的空初始格式（与 wp_render_config._CONFIRMATION_FORMAT_MAP 对齐）
_INITIAL_FORMAT: dict[str, str] = {
    "confirmation-diff-securities": "diff-securities-v1",
    "confirmation-diff-nonsecurities": "diff-nonsecurities-v1",
    "confirmation-alternative-g06": "alternative-g06-v1",
}


def _initial_data(component_type: str) -> dict:
    """生成空的新格式初始数据。

    前端组件检测 `_format` → 识别为新格式 → 显示可编辑空表。
    diff-securities 用 rows；alternative-g06 用 companies。
    """
    fmt = _INITIAL_FORMAT.get(component_type, "confirmation-v1")
    if component_type == "confirmation-alternative-g06":
        return {"_format": fmt, "companies": []}
    return {"_format": fmt, "rows": [], "conclusion": "", "audit_note": ""}


async def _render_confirmation(ctx: RenderContext, component_type: str) -> dict | None:
    """seed 回读：已有持久化数据（且格式匹配）优先，否则返回空初始格式。"""
    existing = ctx.sheet_html_data
    fmt = _INITIAL_FORMAT.get(component_type)
    if isinstance(existing, dict) and existing.get("_format") == fmt:
        # 已持久化的新格式数据 → 原样回读作为 seed
        return existing
    # 首次打开或旧格式 → 返回空的新格式初始数据
    return _initial_data(component_type)


async def render_g0_diff_securities(ctx: RenderContext) -> dict | None:
    """Render 策略: confirmation-diff-securities（G0-3 证券差异核对）."""
    return await _render_confirmation(ctx, "confirmation-diff-securities")


async def render_g0_diff_nonsecurities(ctx: RenderContext) -> dict | None:
    """Render 策略: confirmation-diff-nonsecurities（G0-4 非证券差异核对，三维）.

    seed 回读特例（Property 7）：既有项目可能把非证券差异录在共享 diff-reconcile-v1
    （G0-4 早先指向 confirmation-diff-reconcile）。此时原样回读旧数据作为 seed，
    由前端 useG0DiffNonSecurities 按投资金额维 hydrate（不静默丢弃）。
    """
    existing = ctx.sheet_html_data
    if isinstance(existing, dict) and existing.get("_format") in (
        "diff-nonsecurities-v1",
        "diff-reconcile-v1",
    ):
        return existing
    return _initial_data("confirmation-diff-nonsecurities")


async def render_g0_alternative(ctx: RenderContext) -> dict | None:
    """Render 策略: confirmation-alternative-g06（G0-6 投资替代程序）."""
    return await _render_confirmation(ctx, "confirmation-alternative-g06")
