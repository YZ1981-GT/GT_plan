"""用户管理路由 — 用户CRUD + 项目成员管理

Validates: Requirements 1.1, 1.2, 1.3
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.models.collaboration_schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    ProjectUserCreate,
    ProjectUserResponse,
)
from app.services import auth_service
from app.services.permission_service import Permission, check_project_permission

router = APIRouter(prefix="/users", tags=["用户管理"])


def _get_user_by_id(db: Session, user_id: str) -> User:
    user = db.query(User).filter(
        User.id == user_id,
        User.is_deleted == False  # noqa: E712
    ).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    return user


def _require_admin(user: User) -> None:
    role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    if role not in ("admin",):
        raise HTTPException(403, "需要 admin 权限")


@router.get("", response_model=list[UserResponse])
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取用户列表（admin 可查看所有，普通用户只能查看）"""
    q = db.query(User).filter(User.is_deleted == False)  # noqa: E712
    if role:
        q = q.filter(User.role == role)
    if is_active is not None:
        q = q.filter(User.is_active == is_active)
    users = q.offset(skip).limit(limit).all()
    return [_user_to_response(u) for u in users]


@router.post("", response_model=UserResponse)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建用户（仅 admin）"""
    _require_admin(user)

    # 检查用户名唯一性
    existing = db.query(User).filter(User.username == body.username).first()
    if existing:
        raise HTTPException(400, "用户名已存在")

    from app.models.base import UserRole
    role_enum = UserRole(body.role) if body.role else UserRole.auditor

    new_user = User(
        username=body.username,
        hashed_password=auth_service.hash_password(body.password),
        display_name=body.display_name,
        email=body.email,
        office_code=body.office_code,
        role=role_enum,
        is_active=True,
        is_deleted=False,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return _user_to_response(new_user)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取用户详情"""
    target = _get_user_by_id(db, user_id)
    return _user_to_response(target)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    body: UserUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """更新用户（admin 或本人）"""
    _require_admin(user)

    target = _get_user_by_id(db, user_id)
    if body.display_name is not None:
        target.display_name = body.display_name
    if body.email is not None:
        target.email = body.email
    if body.office_code is not None:
        target.office_code = body.office_code
    if body.is_active is not None:
        target.is_active = body.is_active
    if body.role is not None:
        from app.models.base import UserRole
        target.role = UserRole(body.role)
    db.commit()
    db.refresh(target)
    return _user_to_response(target)


@router.delete("/{user_id}")
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """软删除用户（仅 admin）"""
    _require_admin(user)

    target = _get_user_by_id(db, user_id)
    target.is_deleted = True
    target.is_active = False
    db.commit()
    return {"message": "用户已删除"}


# ---------------------------------------------------------------------------
# 项目成员管理
# ---------------------------------------------------------------------------

@router.get(
    "/projects/{project_id}/users",
    response_model=list[ProjectUserResponse],
)
def list_project_users(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取项目成员列表"""
    from app.models.core import ProjectUser
    members = db.query(ProjectUser).filter(
        ProjectUser.project_id == project_id,
        ProjectUser.is_deleted == False,  # noqa: E712
    ).all()
    return [_pu_to_response(pu) for pu in members]


@router.post(
    "/projects/{project_id}/users",
    response_model=ProjectUserResponse,
)
def add_project_user(
    project_id: str,
    body: ProjectUserCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """添加项目成员"""
    role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    if role not in ("admin", "partner", "manager"):
        raise HTTPException(403, "需要 manager 及以上权限")

    # 检查成员是否已存在
    existing = db.query(ProjectUser).filter(
        ProjectUser.project_id == project_id,
        ProjectUser.user_id == body.user_id,
        ProjectUser.is_deleted == False,  # noqa: E712
    ).first()
    if existing:
        raise HTTPException(400, "该用户已在项目中")

    from app.models.core import ProjectUser as PUModel
    from app.models.base import ProjectUserRole as PURole

    pu = PUModel(
        project_id=project_id,
        user_id=body.user_id,
        project_role=PURole(body.project_role),
        assigned_cycles=body.assigned_cycles,
        assigned_account_ranges=body.assigned_account_ranges,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        is_deleted=False,
    )
    db.add(pu)
    db.commit()
    db.refresh(pu)
    return _pu_to_response(pu)


@router.delete("/projects/{project_id}/users/{member_user_id}")
def remove_project_user(
    project_id: str,
    member_user_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """移除项目成员"""
    role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    if role not in ("admin", "partner", "manager"):
        raise HTTPException(403, "需要 manager 及以上权限")

    from app.models.core import ProjectUser
    pu = db.query(ProjectUser).filter(
        ProjectUser.project_id == project_id,
        ProjectUser.user_id == member_user_id,
        ProjectUser.is_deleted == False,  # noqa: E712
    ).first()
    if not pu:
        raise HTTPException(404, "项目成员不存在")
    pu.is_deleted = True
    db.commit()
    return {"message": "已移除项目成员"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_to_response(u: User) -> UserResponse:
    return UserResponse(
        id=str(u.id),
        username=u.username,
        display_name=getattr(u, 'display_name', None),
        role=u.role.value if hasattr(u.role, 'value') else str(u.role),
        office_code=getattr(u, 'office_code', None),
        email=getattr(u, 'email', None),
        is_active=getattr(u, 'is_active', True),
    )


def _pu_to_response(pu) -> ProjectUserResponse:
    return ProjectUserResponse(
        id=str(pu.id),
        project_id=str(pu.project_id),
        user_id=str(pu.user_id),
        project_role=pu.project_role.value if hasattr(pu.project_role, 'value') else str(pu.project_role),
        assigned_cycles=getattr(pu, 'assigned_cycles', None),
        assigned_account_ranges=getattr(pu, 'assigned_account_ranges', None),
        valid_from=getattr(pu, 'valid_from', None),
        valid_to=getattr(pu, 'valid_to', None),
    )
