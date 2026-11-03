"""公式全局设置权限判定（ADR-CNS-02）。

公式设置中心与合并附注旧端点共用同一个 admin 判断函数，
避免两处各写一份角色名单导致口径漂移。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.core import User


def can_edit_global(user: "User") -> bool:
    """当前用户是否有全局公式写权限（= admin）。"""
    role = getattr(user, "role", None)
    return getattr(role, "value", role) == "admin"
