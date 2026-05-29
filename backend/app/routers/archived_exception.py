"""归档项目例外通道 — V3 收官 Req 1.2 + 1.3

提供 POST /api/projects/{pid}/archived-exception/{action} 端点：
- 仅 admin / partner / qc 角色可访问
- 不经过 require_project_access 守卫（归档项目会被拦截）
- 强制 reason 字段（非空）
- 写入 audit_log (event_type=archived_exception_access)

提供 POST /api/projects/{pid}/unarchive 端点：
- 仅 admin / partner 角色可访问（比例外通道更严格，不含 qc）
- 需要 reason（非空）+ project_code 二次确认
- 校验 project_code 匹配项目名称（二次确认机制）
- 项目必须处于 archived 状态
- 成功后 project.status → execution（恢复活跃状态）
- 写入 audit_log (event_type=archive_unarchive)

Validates: Requirements 1.2, AC 1.5, AC 1.7
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import ProjectStatus
from app.models.core import Project, User
from app.services.audit_log_helper import append_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/archived-exception",
    tags=["归档例外通道"],
)

unarchive_router = APIRouter(
    prefix="/api/projects/{project_id}",
    tags=["归档例外通道"],
)

# 允许的角色
ALLOWED_ROLES = {"admin", "partner", "qc"}
# 解除归档允许的角色（更严格，不含 qc）
UNARCHIVE_ALLOWED_ROLES = {"admin", "partner"}


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------


class ArchivedExceptionRequest(BaseModel):
    reason: str
    password_confirm: str = ""

    @field_validator("reason")
    @classmethod
    def reason_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("reason 不能为空")
        return v.strip()


class UnarchiveRequest(BaseModel):
    """解除归档请求体。

    project_code 用于二次确认：用户必须输入项目名称/编码以确认操作。
    """

    reason: str
    password_confirm: str = ""
    project_code: str

    @field_validator("reason")
    @classmethod
    def reason_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("reason 不能为空")
        return v.strip()

    @field_validator("project_code")
    @classmethod
    def project_code_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("project_code 不能为空")
        return v.strip()


# ---------------------------------------------------------------------------
# POST /api/projects/{pid}/archived-exception/{action}
# ---------------------------------------------------------------------------


@router.post("/{action}")
async def archived_exception_access(
    project_id: uuid.UUID,
    action: str,
    body: ArchivedExceptionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """归档项目例外通道。

    允许 admin/partner/qc 角色在归档项目上执行特定操作，
    绕过正常的归档只读守卫，但强制记录审计日志。
    """
    # 角色校验
    if current_user.role.value not in ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="权限不足，仅管理员/合伙人/质控可使用例外通道")

    # 写入审计日志
    await append_audit_log(db, {
        "user_id": current_user.id,
        "project_id": project_id,
        "action": "archived_exception_access",
        "resource_type": "project",
        "resource_id": str(project_id),
        "details": {
            "event_type": "archived_exception_access",
            "reason": body.reason,
            "approver_id": str(current_user.id),
            "endpoint": f"/api/projects/{project_id}/archived-exception/{action}",
            "original_status": "archived",
        },
    })

    await db.commit()

    return {
        "success": True,
        "message": f"例外通道操作 '{action}' 已授权",
        "project_id": str(project_id),
        "action": action,
    }


# ---------------------------------------------------------------------------
# POST /api/projects/{pid}/unarchive — 解除归档 + 二次确认
# ---------------------------------------------------------------------------


@unarchive_router.post("/unarchive")
async def unarchive_project(
    project_id: uuid.UUID,
    body: UnarchiveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """解除归档端点。

    仅 admin/partner 角色可操作（比例外通道更严格）。
    需要 project_code 二次确认（用户输入项目名称匹配）。
    成功后将 project.status 从 archived → execution。
    """
    # 角色校验（仅 admin / partner）
    if current_user.role.value not in UNARCHIVE_ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail="权限不足，仅管理员/合伙人可解除归档",
        )

    # 加载项目
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 校验项目当前状态必须为 archived
    if project.status != ProjectStatus.archived:
        raise HTTPException(
            status_code=400,
            detail="项目当前未处于归档状态，无需解除归档",
        )

    # 二次确认：project_code 必须匹配项目名称
    if body.project_code != project.name:
        raise HTTPException(
            status_code=400,
            detail="项目编码校验失败，请输入正确的项目名称以确认解除归档",
        )

    # 记录原始状态
    previous_status = project.status.value

    # 更新项目状态 → execution（恢复活跃状态）
    project.status = ProjectStatus.execution

    # 写入审计日志
    await append_audit_log(db, {
        "user_id": current_user.id,
        "project_id": project_id,
        "action": "archive_unarchive",
        "resource_type": "project",
        "resource_id": str(project_id),
        "details": {
            "event_type": "archive_unarchive",
            "reason": body.reason,
            "previous_status": previous_status,
        },
    })

    await db.commit()

    return {
        "success": True,
        "message": "项目已成功解除归档",
        "project_id": str(project_id),
        "new_status": project.status.value,
    }
