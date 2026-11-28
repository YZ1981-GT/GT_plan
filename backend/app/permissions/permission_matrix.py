"""
Permission Matrix — 5角色权限判定单一真源（后端安全边界）

Feature: platform-global-hardening

本模块是后端权限判定的**权威来源**。前端 usePermissionMatrix composable
镜像同一份定义用于 UX 优化，但不构成安全边界。

5 审计角色（映射到系统角色）：
- 审计助理 (assistant)  → system_role: auditor
- 现场经理 (manager)    → system_role: manager
- 业务合伙人 (partner)  → system_role: partner
- 质量控制复核合伙人 (qc_partner) → system_role: qc
- EQCR 技术复核人 (eqcr) → system_role: eqcr

前后端共享同一组 operation codes（与 permission_matrix_service.py 一致）。
本模块在其基础上提供面向审计 5 角色的 `can()` 函数，作为统一入口。
"""

from __future__ import annotations

from typing import Any

from app.services.permission_matrix_service import (
    OPERATION_CODES,
    ROLE_ALIAS_MAP,
    can as _matrix_can,
    get_allowed_operations,
    normalize_role,
)

# ─── 5 审计角色常量 ──────────────────────────────────────────────────────────
AUDIT_ROLES = ("assistant", "manager", "partner", "qc_partner", "eqcr")

# ─── 角色别名→系统角色映射（归一化） ──────────────────────────────────────────
#
# 🔴 **定义已下沉到 `app/services/permission_matrix_service.py`**，
#    这里只是**重导出**（`ROLE_ALIAS_MAP` / `normalize_role` 均从上方 import 而来，
#    是**同一个对象**、不是 copy）⇒ `from app.permissions.permission_matrix import
#    ROLE_ALIAS_MAP` 这个既有路径行为不变。
#
#    下沉的原因：别名需要在 **6 个查表处**生效（明细见 service 层 `normalize_role`
#    的 docstring），其中 `wp_cell_lock_service.py` 与 service 层本身都是
#    **零 app 依赖的叶子模块**，而本模块**不能被它们 import**。
#
#    ⚠️ 本模块的 `can()` / `get_operations_for_role()` 仍照旧先归一化再委托；
#       区别只在于**下层现在也归一化了**（原先只有上层归一化，是那 6 处缺陷的根因）。

# ─── 资源→操作前缀映射 ────────────────────────────────────────────────────────
RESOURCE_ACTION_MAP: dict[str, dict[str, str]] = {
    "workpaper": {
        "edit": "wp:edit",
        "review": "wp:review",
        "read": "project:view",
    },
    "report": {
        "edit": "report:edit",
        "sign": "report:sign",
        "read": "project:view",
    },
    "note": {
        "edit": "note:edit",
        "read": "project:view",
    },
    "project": {
        "view": "project:view",
        "read": "project:view",
    },
    "archive": {
        "manage": "archive:manage",
    },
}

# ─── 锁定底稿限制 ────────────────────────────────────────────────────────────
# 底稿锁定后，只有 partner/admin 可以解锁/编辑
LOCKED_OVERRIDE_ROLES = {"admin", "partner"}

# ─── 复核后限制 ───────────────────────────────────────────────────────────────
# 已复核底稿，编辑操作降级为只读（除非是 partner/admin 重新打开）
POST_REVIEW_EDIT_ROLES = {"admin", "partner", "manager"}


def can(
    role: str,
    action: str,
    resource: str,
    context: dict[str, Any] | None = None,
) -> bool:
    """统一权限判定入口 — 镜像前端 usePermissionMatrix.can()。

    后端安全边界：此函数的判定结果为最终权威。前端同名函数仅用于 UX。

    Args:
        role: 审计角色名（5角色别名或系统角色名均可）
        action: 操作动作（如 "edit", "review", "sign", "read"）
        resource: 资源类型（如 "workpaper", "report", "note", "project"）
        context: 可选上下文（支持 locked/reviewed/project_role 等）

    Returns:
        True 表示允许，False 表示拒绝

    Examples:
        >>> can("assistant", "edit", "workpaper")
        True
        >>> can("eqcr", "edit", "workpaper")
        False
        >>> can("assistant", "edit", "workpaper", {"locked": True})
        False
    """
    ctx = context or {}
    system_role = normalize_role(role)
    project_role = ctx.get("project_role")

    # ─── 直接用 operation code（兼容已有端点直接传 operation） ─────────
    if ":" in action and resource == "":
        operation = action
    else:
        # ─── 从 resource + action 解析 operation code ─────────────────
        resource_map = RESOURCE_ACTION_MAP.get(resource, {})
        operation = resource_map.get(action)
        if operation is None:
            # 未映射的 action:resource 组合 → 拒绝（安全侧）
            return False

    # ─── 基础权限判定（委托 permission_matrix_service） ────────────────
    if not _matrix_can(system_role, project_role, operation):
        return False

    # ─── 上下文约束：锁定底稿 ─────────────────────────────────────────
    if ctx.get("locked") and action == "edit":
        if system_role not in LOCKED_OVERRIDE_ROLES:
            return False

    # ─── 上下文约束：已复核底稿 ───────────────────────────────────────
    if ctx.get("reviewed") and action == "edit":
        if system_role not in POST_REVIEW_EDIT_ROLES:
            return False

    return True


def get_operations_for_role(
    role: str,
    project_role: str | None = None,
) -> set[str]:
    """返回指定角色的允许操作集合。

    Args:
        role: 审计角色名
        project_role: 可选项目职责

    Returns:
        允许的 operation code 集合
    """
    system_role = normalize_role(role)
    return get_allowed_operations(system_role, project_role)


def get_all_operation_codes() -> list[str]:
    """返回全部已定义的 operation codes。"""
    return list(OPERATION_CODES)
