"""全局刷新范围动态发现端点（合伙人专属，Global_Refresh）.

公式管理库（formula-management-library）Task 17.1 / 设计 §19（Req 20）。

``GET /api/workpapers/refresh-scopes?project_id=&year=`` → ``{items: [RefreshScopeItem]}``。

供全局刷新勾选弹窗（Req 19，前端 ``GtRefreshScopeDialog``）渲染可勾选项、后端编排
（Req 21，``DraftRefreshOrchestrator``）校验勾选范围合法性，**共用同一发现口径**
（Req 20.5 / 20.6，避免前后端清单漂移）。

门禁复用 ``deps.py`` 的 ``require_role(["partner", "signing_partner"])``——与
``/draft-refresh`` 同一合伙人门禁（不新增并行角色判断，Req 1.3）；非合伙人 403。
本端点只读，不写任何数据。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_role
from app.models.core import User
from app.services.formula_management.refresh_scope_discovery import (
    RefreshScopeDiscovery,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers",
    tags=["refresh-scopes"],
)

# 合伙人角色（与 /draft-refresh 同一门禁，Req 1.1 / 20.5）。
PARTNER_ROLES = ["partner", "signing_partner"]


@router.get("/refresh-scopes")
async def list_refresh_scopes(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(PARTNER_ROLES)),
):
    """列出全局刷新可勾选范围项（合伙人专属，Req 20）。

    从三来源动态发现（模块注册固定顶层域 + 后端注册循环常量 + ``wp_index`` 循环前缀），
    按 key 去重。非合伙人在依赖解析阶段即被 ``require_role`` 拦截返回 403。
    """
    items = await RefreshScopeDiscovery(db).discover(project_id=project_id, year=year)
    return {"items": [item.to_dict() for item in items]}
