"""认证中间件 — JWT 验证 + 用户提取 + 权限校验

Validates: Requirements 1.3, 1.6
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.core import User
from app.services.auth_service import is_token_blacklisted
from app.services.permission_service import Permission, check_permission

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """从 Authorization header 解析 JWT，验证并返回当前用户

    验证流程：
    1. 检查 token 是否在黑名单中
    2. 解码 JWT，检查 type=access
    3. 查询用户，验证 is_active 和 is_deleted
    """
    token = credentials.credentials

    # 检查黑名单
    if await is_token_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 已被吊销"
        )

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的 token 类型"
            )
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法验证凭据"
        )

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭据"
        )

    user = db.query(User).filter(
        User.id == user_id,
        User.is_deleted == False  # noqa: E712
    ).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在"
        )

    return user


def require_permission(permission: Permission):
    """权限校验依赖工厂：要求用户拥有指定权限"""
    def dependency(user: User = Depends(get_current_user)):
        role = user.role.value if hasattr(user.role, 'value') else str(user.role)
        if not check_permission(role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足"
            )
        return user
    return dependency


def require_any_permission(*permissions: Permission):
    """权限校验依赖工厂：要求用户拥有任一指定权限"""
    def dependency(user: User = Depends(get_current_user)):
        role = user.role.value if hasattr(user.role, 'value') else str(user.role)
        for p in permissions:
            if check_permission(role, p):
                return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    return dependency
