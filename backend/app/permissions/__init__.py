"""
Permission enforcement package — 后端安全边界（单一真源）

Feature: platform-global-hardening

设计原则（Req 7.4/7.5）：
- 后端 deps 层 = 安全边界（authoritative），强制校验
- 前端 permission 判定 = 体验优化（UX-only），不保证安全
- 不一致时后端生效（前端说 allowed 但后端拒绝 → 403）

本包提供：
- permission_matrix.can(role, action, resource, context) — 5角色权限判定
- require_permission(action, resource) — FastAPI 依赖注入 helper
- AUDIT_ROLES — 5 审计角色常量

使用示例::

    from app.permissions import require_permission

    @router.put("/{wp_id}/data")
    async def update_data(
        wp_id: UUID,
        current_user: User = Depends(require_permission("wp:edit", "workpaper")),
    ):
        ...
"""

from app.permissions.permission_matrix import (
    AUDIT_ROLES,
    ROLE_ALIAS_MAP,
    can,
)
from app.permissions.enforcement import require_permission

__all__ = [
    "AUDIT_ROLES",
    "ROLE_ALIAS_MAP",
    "can",
    "require_permission",
]
