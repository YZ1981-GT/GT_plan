"""底稿渲染策略模块

按 componentType 分发的渲染策略函数集合。
主入口 wp_render_config.get_render_config 通过 RENDERER_DISPATCH 调度。
"""

from __future__ import annotations

from typing import Callable

from ._a_program import render as render_a_program
from ._a112_dual import render as render_a112_dual
from ._a115_disclosure import render as render_a115_disclosure
from ._analytical_review import render as render_analytical_review
from ._audit_sheet import render as render_audit_sheet
from ._b_index import render as render_b_index
from ._c_note import render as render_c_note
from ._checklist import render as render_checklist
from ._review_checklist import render as render_review_checklist
from ._univer_grid import render as render_univer_grid

# 策略函数签名: async def render(ctx: RenderContext) -> dict | None
# 各策略文件在后续 task 中逐一实现后注册到此 dict
RENDERER_DISPATCH: dict[str, Callable] = {
    "b-index": render_b_index,
    "a-program-console": render_a_program,
    "a1-dashboard": render_a_program,
    "a1-12-dual-checklist": render_a112_dual,
    "a1-15-disclosure-checklist": render_a115_disclosure,
    "a2-adjustment-console": render_a_program,
    "a3-consolidation-console": render_a_program,
    "audit-sheet": render_audit_sheet,
    "checklist-table": render_checklist,
    "review-checklist": render_review_checklist,
    "analytical-review": render_analytical_review,
    "c-note-table": render_c_note,
    "univer": render_univer_grid,
}
