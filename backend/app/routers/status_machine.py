"""可解释状态机 router — V3 收官增强 Req 10.2

提供状态机查询端点：

- GET /api/{module}/{instance_id}/allowed-actions

注册位置：backend/app/router_registry/system.py §125

Validates: Requirements 10.2
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services import allowed_actions_service as svc

router = APIRouter(tags=["可解释状态机"])

_VALID_MODULES = {"workpaper", "adjustment", "misstatement", "report", "disclosure"}


@router.get("/api/{module}/{instance_id}/allowed-actions")
async def get_allowed_actions(
    module: str,
    instance_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """获取指定业务实例的允许/禁止操作列表。

    Parameters
    ----------
    module : str
        业务模块类型（workpaper / adjustment / misstatement / report / disclosure）
    instance_id : UUID
        实例 ID
    """
    if module not in _VALID_MODULES:
        raise HTTPException(
            status_code=422,
            detail={"message": f"不支持的模块类型: {module}，支持: {', '.join(sorted(_VALID_MODULES))}"},
        )

    # 获取实例当前状态（简化：从 DB 查询或使用默认值）
    current_status, project_id, is_archived = await _load_instance_status(
        db, module, instance_id
    )

    user_role = getattr(user, "role", "editor")

    result = await svc.compute_allowed_actions(
        db,
        module=module,
        instance_id=instance_id,
        current_status=current_status,
        user_role=user_role,
        project_id=project_id,
        is_archived=is_archived,
    )

    return result


async def _load_instance_status(
    db: AsyncSession, module: str, instance_id: UUID
) -> tuple[str, UUID, bool]:
    """加载实例当前状态、项目 ID、是否归档。

    根据 module 类型查询对应表。
    """
    from sqlalchemy import text

    # 模块 → 表名 + 状态字段映射
    table_map = {
        "workpaper": ("working_papers", "status"),
        "adjustment": ("adjustments", "status"),
        "misstatement": ("misstatements", "status"),
        "report": ("reports", "status"),
        "disclosure": ("disclosure_notes", "status"),
    }

    table_name, status_col = table_map.get(module, ("working_papers", "status"))

    try:
        # 查询实例状态和项目 ID
        stmt = text(f"""
            SELECT {status_col}, project_id
            FROM {table_name}
            WHERE id = :instance_id
            LIMIT 1
        """)
        result = await db.execute(stmt, {"instance_id": instance_id})
        row = result.first()

        if not row:
            raise HTTPException(
                status_code=404,
                detail={"message": f"未找到 {module} 实例: {instance_id}"},
            )

        status = row[0] or "draft"
        project_id = row[1]

        # 查询项目是否归档
        proj_stmt = text("SELECT status FROM projects WHERE id = :pid LIMIT 1")
        proj_result = await db.execute(proj_stmt, {"pid": project_id})
        proj_row = proj_result.first()
        is_archived = (proj_row[0] == "archived") if proj_row else False

        return status, project_id, is_archived

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"message": f"查询实例状态失败: {exc}"},
        )
