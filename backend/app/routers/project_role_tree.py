"""用户 → 项目 → 角色 三层树 只读 API（project-data-permission-isolation Task 4.1）

prefix=`/api/system/user-project-role-tree`，全部端点 `require_role(["admin"])`。

🔴 **只读**：本模块只有 `@router.get`，无任何 POST/PUT/PATCH/DELETE（Req 6.1/6.4）。
   要变更项目角色分配走既有的 `project_users` 分配 API —— 本 spec 不新建与它
   并行的写路径（Req 6.3），否则同一份数据会有两个写真源。

🔴 **主体是"被查看的账号"而非"当前管理员"**：故不注入
   `Depends(get_visible_project_ids)`（那会算成管理员自己的可见集）。
   详见 `project_role_tree_service` 模块头的说明。

Validates: Requirements 1.1~1.5, 2.1~2.5, 3.1~3.3, 5.1~5.4, 6.1, 6.4
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_role
from app.models.core import User
from app.schemas.project_role_tree import UserNodePage, UserSubtree
from app.services.project_role_tree_service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    TreeAssemblyService,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/system/user-project-role-tree",
    tags=["系统管理-用户项目角色树"],
)


@router.get("/users", response_model=UserNodePage)
async def list_user_nodes(
    search: str | None = Query(
        default=None, description="用户名或邮箱关键字（模糊匹配）"
    ),
    page: int = Query(default=1, ge=1, description="页码，从 1 起"),
    page_size: int = Query(
        default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="单页条数"
    ),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
) -> UserNodePage:
    """树的**根层**：未删除账号分页列表（Req 1.1~1.5）。

    `has_children` 由一次聚合查询批量算出，前端据此决定节点是否可展开
    —— 无项目的账号仍会返回（`has_children=false`），不被过滤掉（Req 1.3）。
    """
    items, total = await TreeAssemblyService.list_user_nodes(
        db, search=search, page=page, page_size=page_size
    )
    return UserNodePage(items=items, total=total)


@router.get("/users/{user_id}/subtree", response_model=UserSubtree)
async def get_user_subtree(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
) -> UserSubtree:
    """树的**第 2/3 层**：某账号的项目层 + 角色层 + 数据权限视角（Req 2.1~2.5, 5.1~5.4）。

    懒加载的第二段 —— 前端展开某个 User_Node 时才请求本端点。

    ⚠️ 账号不存在或已软删返回 **404**「账号不存在」（Req 2.5）。
       service 层抛的是 `ValueError`（它不依赖 FastAPI，便于脱离 web 框架测试），
       在这里转成 HTTPException。
    """
    try:
        return await TreeAssemblyService.get_user_project_role_subtree(db, user_id)
    except ValueError as e:
        # ⚠️ 只把 ValueError 当 404 —— 其他异常（DB 故障等）必须原样上抛成 500。
        #    若在这里 `except Exception` 一律转 404，会把"服务挂了"伪装成
        #    "账号不存在"，排查时完全找不到方向。
        raise HTTPException(status_code=404, detail=str(e) or "账号不存在") from e
