"""用户路由 — 用户列表 / 创建 / 修改（启用停用、重置密码）/ 当前用户信息

Validates: Requirements 3.12, 3.13；spec procedure-chain-followup-closure R1
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.core import User
from app.schemas.auth import UserCreate, UserResponse, UserUpdate
from app.services import auth_service
from app.services.project_creation_grant_service import (
    audit_grant_change,
    grant_many,
    list_grants,
    revoke_grant,
)
from app.services.staff_account_binding_service import (
    audit_binding_change,
    bind_staff_to_user,
    list_bindings,
    unbind_staff_from_user,
)

router = APIRouter(tags=["用户"])


class StaffBindingRequest(BaseModel):
    staff_id: UUID


class ProjectCreationGrantBatchRequest(BaseModel):
    company_codes: list[str] = Field(min_length=1, max_length=500)
    valid_until: datetime | None = None
    reason: str = Field(min_length=3, max_length=500)


class ProjectCreationGrantRevokeRequest(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


@router.get("/")
async def list_users(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """获取用户列表（用于底稿分配、复核人选择等下拉框；须登录，原先不鉴权）。

    带 ``is_active``：用户管理页显示状态、下拉框可据此排除停用账号。
    """
    from sqlalchemy import select
    result = await db.execute(
        select(User).where(User.is_deleted == False).order_by(User.username)  # noqa: E712
    )
    users = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "username": u.username,
            "full_name": u.username,
            "email": u.email,
            "role": u.role.value if hasattr(u.role, "value") else u.role,
            "is_active": bool(u.is_active),
        }
        for u in users
    ]


@router.get("/project-creation-grants")
async def get_project_creation_grants(
    manager_user_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin"])),
) -> list[dict]:
    """列出经理精确 USCC 建项授权（仅 admin）。"""
    return await list_grants(db, manager_user_id=manager_user_id)


@router.post("/project-creation-grants/{manager_user_id}")
async def create_project_creation_grants(
    manager_user_id: UUID,
    body: ProjectCreationGrantBatchRequest,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """批量授予经理精确企业代码建项权（仅 admin，重复请求幂等）。"""
    grants = await grant_many(
        db,
        manager_user_id=manager_user_id,
        company_codes=body.company_codes,
        valid_until=body.valid_until,
        reason=body.reason,
        actor=current_user,
    )
    await db.commit()
    await audit_grant_change(
        current_user,
        action="project.creation_grant.granted",
        codes=[grant.company_code for grant in grants],
        manager_user_id=manager_user_id,
        reason=body.reason,
    )
    return await list_grants(db, manager_user_id=manager_user_id)


@router.post("/project-creation-grants/{grant_id}/revoke")
async def revoke_project_creation_grant(
    grant_id: UUID,
    body: ProjectCreationGrantRevokeRequest,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """撤销一条经理建项授权（仅 admin）。"""
    grant = await revoke_grant(
        db, grant_id=grant_id, expected_version=body.expected_version,
        reason=body.reason, actor=current_user,
    )
    await db.commit()
    await audit_grant_change(
        current_user,
        action="project.creation_grant.revoked",
        codes=[grant.company_code],
        manager_user_id=grant.grantee_user_id,
        reason=body.reason,
    )
    return {"id": str(grant.id), "revoked": True}


@router.get("/staff-bindings")
async def get_staff_bindings(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin"])),
) -> list[dict]:
    """列出人员档案与登录账号的绑定（仅 admin）。"""
    return await list_bindings(db)


@router.post("/{user_id}/staff-binding")
async def bind_user_staff(
    user_id: UUID,
    body: StaffBindingRequest,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """把人员档案绑定到账号（仅 admin）：一对一，绑定后该人员的有效委派对账号生效。"""
    result = await bind_staff_to_user(
        db, user_id=user_id, staff_id=body.staff_id, actor_user_id=current_user.id,
    )
    await db.commit()
    if result["changed"]:
        await audit_binding_change(
            current_user.id, action="user.staff_binding.bound",
            staff_id=result["staff_id"], user_id=result["user_id"],
            project_count=result["project_count"],
        )
    return result


@router.post("/{user_id}/staff-binding/unbind")
async def unbind_user_staff(
    user_id: UUID,
    body: StaffBindingRequest,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """解除账号与人员档案的绑定（仅 admin）；人员仍在项目团队中时拒绝。"""
    result = await unbind_staff_from_user(
        db, user_id=user_id, staff_id=body.staff_id, actor_user_id=current_user.id,
    )
    await db.commit()
    await audit_binding_change(
        current_user.id, action="user.staff_binding.unbound",
        staff_id=result["staff_id"], user_id=result["user_id"],
    )
    return result


@router.post("/", response_model=UserResponse)
async def create_user(
    body: UserCreate,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """创建用户（仅 admin 角色）。

    Validates: Requirements 3.12
    """
    return await auth_service.create_user(user_data=body, db=db)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """修改用户（仅 admin）：邮箱 / 角色 / 启用状态 / 重置密码。不能停用或降级自己；至少保留一个启用的管理员。"""
    updated = await auth_service.update_user(db, actor_id=current_user.id, user_id=user_id, data=body)
    await db.commit()
    return updated


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """获取当前用户信息（含角色权限列表，供前端权限检查使用）。

    Validates: Requirements 3.13
    """
    profile = await auth_service.get_current_user_profile(
        user_id=str(current_user.id),
        db=db,
    )
    # 注入权限列表（从后端权限矩阵派生，防止前后端权限表不同步）
    from app.services.permission_service import ROLE_PERMISSION_MATRIX
    role_str = current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)
    perms = ROLE_PERMISSION_MATRIX.get(role_str, set())
    profile.permissions = [p.value if hasattr(p, 'value') else str(p) for p in perms]
    return profile
