"""全局一键刷新统一入口（合伙人专属，Global_Refresh）.

公式管理库（formula-management-library）Task 5.5 / 设计 Components §1 与 §13。

分层门禁（Req 1 / Req 20）：
- **全局一键刷新**（本模块 ``POST /api/workpapers/draft-refresh``）走**合伙人门禁**
  （``require_role(["partner", "signing_partner"])``），一次从四表库未审数生成
  未审报表 + 底稿 + 附注初稿。
- **模块/循环级局部刷新**（``wp_render_config.py`` 的 ``audit-sheet-refresh``）走
  **编辑权门禁**（``require_wp_edit_permission``），不锁死为合伙人。

门禁复用 ``deps.py`` 的 ``require_role``（不新增并行角色判断，Req 1.3）。
编排：``DraftRefreshService.precheck``（precheck 阻断 422，先于编排）+
``DraftRefreshOrchestrator.generate``（按勾选 scopes 分派生成器产 RefreshUnit + page_keys，
经 ``refresh_with_presets`` 治理：套预设 + 幂等 + Draft 标记 + 覆盖排除 + 审计留痕，Req 21）；
service 只 flush，router 层 commit（工程铁律）。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_role
from app.models.core import User
from app.services.draft_refresh_service import DraftRefreshService
from app.services.formula_management.draft_refresh_orchestrator import (
    DraftRefreshOrchestrator,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers",
    tags=["draft-refresh"],
)

# 合伙人角色（全局一键刷新专属门禁，Req 1.1）。复用 deps.require_role，不新增并行角色判断。
PARTNER_ROLES = ["partner", "signing_partner"]


class OneClickRefreshRequest(BaseModel):
    """全局一键刷新（``/draft-refresh``）请求体（公式管理库 Req 1/19）。

    - ``scopes``：合伙人在全局刷新勾选弹窗（Req 19）选定的刷新范围键，如
      ``["report", "note", "workpaper:D"]``；为空时默认覆盖 报表/底稿/附注三域。
    - ``confirm_overwrite``：是否确认覆盖团队人工编辑单元（Req 4.4）；``False`` 时
      仅刷新未被人工编辑的单元。
    """

    project_id: UUID
    year: int
    scopes: list[str] = Field(default_factory=list)
    confirm_overwrite: bool = False


@router.post("/draft-refresh")
async def one_click_draft_refresh(
    body: OneClickRefreshRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(PARTNER_ROLES)),
):
    """全局一键刷新统一入口（合伙人专属，Global_Refresh，公式管理库 Req 1）。

    一次从四表库未审数生成未审报表 + 底稿 + 附注初稿。门禁复用 ``deps.py`` 的
    ``require_role(["partner", "signing_partner"])``（不新增并行角色判断，Req 1.3）——
    非合伙人一律 403 且不执行任何数据写入（Req 1.2）。合伙人门禁**仅**施加于本全局入口；
    模块/循环级 ``audit-sheet-refresh`` 走编辑权门禁不受此限（Req 1.5 / Req 20）。

    编排（Req 1.4 / Req 21）：``DraftRefreshService.precheck``（四表库完整度前置校验）→
    ``DraftRefreshOrchestrator.generate``（按勾选 ``scopes`` 分派各上游生成器产出
    ``RefreshUnit`` + ``page_keys``，交治理层 ``refresh_with_presets`` 统一编排：套预设 +
    幂等 + Draft 标记 + 覆盖排除 + 快照 + 审计留痕，``affected_count = len(refreshed_units)``
    不再恒为 0）。前置校验阻断时返回 422 缺失清单，不执行写入（Req 2.2）——precheck 显式在
    orchestrator 之前，阻断不进 orchestrator。service 只 flush，router 层 commit。

    响应返回 ``affected_count``（在 ``result.to_dict()`` 内）+ ``preset_application``
    （``PresetApplication.to_dict()``）+ ``precheck_warnings``。本次实际执行的勾选范围清单由
    ``orchestrator.generate`` 内部写入 ``draft_refresh_audit.detail.scopes``（Req 21.6，router
    无需重复）。
    """
    service = DraftRefreshService()

    # 前置校验：四表库完整度不足则阻断，不执行任何写入（Req 2.2）——阻断不进 orchestrator
    precheck = await service.precheck(db, project_id=body.project_id, year=body.year)
    if not precheck.can_refresh:
        raise HTTPException(
            status_code=422,
            detail={"message": "四表库数据不完整，无法一键刷新", **precheck.to_dict()},
        )

    # 勾选范围为空时默认覆盖 报表/底稿/附注三域（Req 1.4 / Req 19 默认）
    scopes = body.scopes or ["report", "workpaper", "note"]

    # 生成编排层（Req 21）：按勾选 scopes 分派生成器产 RefreshUnit + page_keys，
    # 交治理层 refresh_with_presets 统一编排（幂等 / Draft / 覆盖 / 快照 / 审计）
    orchestrator = DraftRefreshOrchestrator(db)
    result, preset_application = await orchestrator.generate(
        project_id=body.project_id,
        year=body.year,
        operator=_user,
        scopes=scopes,
        confirm_overwrite=body.confirm_overwrite,
    )

    # service 只 flush，router 层 commit（工程铁律）
    await db.commit()

    return {
        **result.to_dict(),
        "preset_application": preset_application.to_dict(),
        "precheck_warnings": [w.to_dict() for w in precheck.warnings],
    }
