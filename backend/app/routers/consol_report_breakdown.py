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

from fastapi import APIRouter, Depends
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
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    """获取某合并报表科目的子公司贡献明细（报表级穿透）.

    数据来自 consol_trial.consolidation_breakdown（Phase 0 B1 汇总时写入）。
    无明细时返回空 by_company + has_breakdown=false + 中文友好提示"请先刷新合并数"
    （HTTP 200，不 404/500），见错误场景 EH5。复用 Phase 0 provenance，不重算。
    """
    return await get_report_consol_breakdown(db, project_id, year, account_code)
