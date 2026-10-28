"""合并报表穿透 API 路由（consol-phase2-orchestration / Phase 2 衔接4 / 需求 5）.

覆盖:
- GET /api/consolidation/report/{project_id}/{year}/{account_code}/consol-breakdown
      报表级穿透：某合并报表科目 → 各子公司金额 + 抵销 + 占比 + 合并数

路径设计（防 router_registry 必查铁律 + 路径冲突核对）：
- 本 router prefix = `/api/consolidation/report`（单数 report），与既有
  `consol_report.py` 的 `/api/consolidation/reports`（复数 reports）+
  `consol_notes.py` 的 `/api/consolidation/notes` 均不冲突（前缀第三段不同）。
- 单独建 router 文件保持单数 report 路径干净，在 router_registry §6 登记。

Validates: Phase 2 Requirements 5.1, 5.2, 5.3, 5.4; Properties S5; Error scenarios EH5.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.services.consol_report_breakdown_service import get_report_consol_breakdown

router = APIRouter(
    prefix="/api/consolidation/report",
    tags=["合并报表穿透"],
)


@router.get("/{project_id}/{year}/{account_code}/consol-breakdown")
async def get_report_breakdown(
    project_id: UUID,
    year: int,
    account_code: str,
    node_key: str | None = Query(default=None, description="汇总节点；省略 = 根合并节点（只对报表行次生效）"),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    """获取某合并报表行次 / 科目的下级构成（报表级穿透）.

    报表行次（如 ``BS-006``，报表页右键传的就是行次）：读时计算所选汇总节点各直接下级的合并数
    （与报表差额表同一求值，``basis = "read_time"``），合并数取后端合计。
    纯数字科目码：读 consol_trial.consolidation_breakdown（推送汇总时写入）；无明细时空 by_company +
    has_breakdown=false + 中文提示（HTTP 200）。
    """
    from app.services.consol_report_view_service import ViewError

    try:
        return await get_report_consol_breakdown(db, project_id, year, account_code, node_key=node_key)
    except ViewError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
