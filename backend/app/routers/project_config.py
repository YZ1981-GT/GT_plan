"""项目级配置中心路由

Requirements: 31.1-31.4 / platform-global-display-settings-closure R4

端点:
  GET  /api/projects/{pid}/config  — 获取项目配置（项目成员 readonly）
  PUT  /api/projects/{pid}/config  — 更新项目配置（project:edit）

读写全部委托 :class:`ProjectConfigService`；路由只负责鉴权与事务边界，
不再保留第二份 schema / 内联写逻辑。
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access, require_project_permission
from app.schemas.project_config import (
    ProjectConfigResponse,
    ProjectConfigUpdate,
    ProjectConfigUpdateResponse,
)
from app.services.project_config_service import ProjectConfigService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/config",
    tags=["project-config"],
)


@router.get("", response_model=ProjectConfigResponse)
async def get_project_config(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_project_access("readonly")),
) -> ProjectConfigResponse:
    """获取项目配置（项目成员只读）。

    Requirements: 31.1；platform-global-display-settings-closure AC-05。
    """
    return await ProjectConfigService(db).get_config(project_id)


@router.put("", response_model=ProjectConfigUpdateResponse)
async def update_project_config(
    project_id: UUID,
    body: ProjectConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_project_permission("project:edit")),
) -> ProjectConfigUpdateResponse:
    """更新项目配置。

    服务层只 flush（企业树重算、过期标记与本次写入同事务），
    提交 / 回滚由本路由独占。
    Requirements: 31.1-31.4；platform-global-display-settings-closure AC-05/AC-06。
    """
    try:
        result = await ProjectConfigService(db).update_config(project_id, body)
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception("project config update failed project=%s", project_id)
        raise
    await db.commit()
    return result