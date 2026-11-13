"""合并 readiness 七域五态只读路由（批 5）。"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/consolidation/readiness",
    tags=["合并就绪度"],
)


@router.get("/{project_id}/{year}")
async def get_consol_readiness(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    """七域五态 readiness：事实与阻断分离，不执行重算。

    批 6.4 起同时返回 ``evidence``（壳底稿证据充分性四态，复用统一真源）与
    ``review``（壳复核状态，批 6.2 状态机）摘要。
    """
    from app.services.consol_readiness_service import load_consol_readiness

    try:
        return await load_consol_readiness(db, project_id, year)
    except Exception as exc:
        logger.warning("readiness 装载失败：%s", exc)
        raise HTTPException(status_code=400, detail=f"合并就绪度读取失败：{exc}") from exc


@router.get("/{project_id}/{year}/role-views")
async def get_consol_role_views(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    """角色视图：编制 / 审批 / 重大判断 / 质控四桶待办（批 6.4 / ADR-CRW-006 R8）。

    待办事实全部来自服务端 readiness + 证据充分性 + 壳复核状态，前端不再拼装事实。
    角色→级别经 ``assignment_service.ROLE_MAP``（编制/审批/重大判断=edit，质控=review）。
    只读鉴权：任何项目成员可看四桶；写操作仍由各自端点的 edit/review 门控制。
    """
    from app.services.consol_readiness_service import load_consol_role_views

    try:
        return await load_consol_role_views(db, project_id, year)
    except Exception as exc:
        logger.warning("角色视图装载失败：%s", exc)
        raise HTTPException(status_code=400, detail=f"合并角色视图读取失败：{exc}") from exc
