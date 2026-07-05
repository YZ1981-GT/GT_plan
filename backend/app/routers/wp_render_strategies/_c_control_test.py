"""C2~C15 业务循环控制测试 — 专属渲染策略.

component_type = "c-control-test"

C2~C15 前端组件 GtCControlTest 为自加载组件（按 sheetName v-if 分发到
目录/汇总表/控制测试子页/偏差评价各视图），通过 GET checklist-responses
拉取 C{n}- 前缀数据还原状态。本渲染策略返回轻量 html_data（project_context +
cycle_info + responses_snapshot），确保 RENDERER_DISPATCH 命中，避免多 sheet
dispatch 循环把 C{n} 误判为 onlyoffice-sheet。

数据持久化在 checklist_responses 表，item_id 前缀为 "C{n}-"（n=2~15）。
"""

from __future__ import annotations

import logging
import re

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


# ─── 14 循环名称映射 ─────────────────────────────────────────────────────
CYCLE_NAMES: dict[int, str] = {
    2: "销售与收款循环",
    3: "货币资金循环",
    4: "采购与付款循环",
    5: "存货与仓储循环",
    6: "投资循环",
    7: "筹资循环",
    8: "人力资源与工薪循环",
    9: "固定资产循环",
    10: "无形资产循环",
    11: "税项循环",
    12: "关联方交易循环",
    13: "或有事项循环",
    14: "持续经营循环",
    15: "期后事项循环",
}


def _extract_cycle_number(wp_code: str) -> int:
    """从 wp_code (如 C2, C10, C15) 提取循环编号."""
    m = re.match(r"C(\d+)", wp_code or "")
    return int(m.group(1)) if m else 0


async def render(ctx: RenderContext) -> dict | None:
    """C2~C15 控制测试渲染策略 — 返回轻量 html_data.

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtCControlTest，而非 grid 兜底或 OnlyOffice。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # 提取循环编号
    wp_code = ctx.classification.wp_code if ctx.classification else ""
    cycle_n = _extract_cycle_number(wp_code)
    prefix = f"C{cycle_n}-" if cycle_n else "C-"

    # ─── 从 checklist_responses 加载 C{n}-* 数据快照 ──────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE :prefix "
                "LIMIT 2000"
            ),
            {"wp_id": str(wp_id), "prefix": f"{prefix}%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "c-control-test render: checklist_responses 查询失败 wp_id=%s: %s",
            wp_id, e,
        )

    # ─── 项目上下文 ──────────────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
    }
    try:
        proj_row = (
            await db.execute(
                sa.text(
                    "SELECT client_name, audit_year "
                    "FROM projects WHERE id = :pid"
                ),
                {"pid": str(ctx.project_id)},
            )
        ).fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
    except Exception as e:  # noqa: BLE001
        logger.warning("c-control-test render: project context 查询失败: %s", e)

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "cycle_number": cycle_n,
        "cycle_name": CYCLE_NAMES.get(cycle_n, f"循环{cycle_n}"),
        "wp_code": wp_code,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
    }
