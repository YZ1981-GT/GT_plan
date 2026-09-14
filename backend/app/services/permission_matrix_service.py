"""
Permission Matrix Service (P0-4)

系统角色 × 项目职责 → 操作权限集合。
纯 Python 实现，不依赖 DB，作为权限判断的单一真源。

Operation Codes (首批 7 个):
- project:view   — 查看项目基本信息
- wp:edit        — 编辑底稿
- wp:review      — 复核底稿
- report:edit    — 编辑报表
- report:sign    — 签发报表
- note:edit      — 编辑附注
- archive:manage — 管理归档
"""

from __future__ import annotations

# ─── 首批 7 个 Operation Codes ───────────────────────────────────────────────
OPERATION_CODES: list[str] = [
    "project:view",
    "wp:edit",
    "wp:review",
    "report:edit",
    "report:sign",
    "note:edit",
    "archive:manage",
]

# ─── 系统角色 → 允许操作映射 ─────────────────────────────────────────────────
# 角色继承: admin > partner > manager > auditor
#           admin > partner > qc > auditor
#           eqcr 独立（只读 + 特定复核权限）
ROLE_OPERATIONS: dict[str, set[str]] = {
    "admin": set(OPERATION_CODES),  # admin 拥有全部操作
    "partner": {
        "project:view",
        "wp:edit",
        "wp:review",
        "report:edit",
        "report:sign",
        "note:edit",
        "archive:manage",
    },
    "manager": {
        "project:view",
        "wp:edit",
        "wp:review",
        "report:edit",
        "note:edit",
    },
    "auditor": {
        "project:view",
        "wp:edit",
        "note:edit",
    },
    "qc": {
        "project:view",
        "wp:review",
        "report:edit",
    },
    "eqcr": {
        "project:view",
        "wp:review",
    },
}

# ─── P0-4.3: 项目职责 → 额外操作映射 ────────────────────────────────────────
PROJECT_ROLE_OPERATIONS: dict[str, set[str]] = {
    "preparer": {
        "project:view",
        "wp:edit",
        "note:edit",
    },
    "reviewer": {
        "project:view",
        "wp:review",
        "report:edit",
    },
    "manager": {
        "project:view",
        "wp:edit",
        "wp:review",
        "report:edit",
        "note:edit",
    },
    "partner": {
        "project:view",
        "wp:edit",
        "wp:review",
        "report:edit",
        "report:sign",
        "note:edit",
        "archive:manage",
    },
    "eqcr": {
        "project:view",
        "wp:review",
    },
}


def get_allowed_operations(
    system_role: str,
    project_role: str | None = None,
) -> set[str]:
    """
    根据系统角色和可选的项目职责，返回允许的操作集合。

    P0-4.3: 将系统角色 + 项目职责解析为 operation set（并集）。

    Args:
        system_role: 系统级角色 (admin/partner/manager/auditor/qc/eqcr)
        project_role: 项目级职责 (preparer/reviewer/manager/partner/eqcr)

    Returns:
        允许的操作 code 集合
    """
    role = system_role.lower().strip()
    base_ops = ROLE_OPERATIONS.get(role, set())

    # P0-4.3: project_role 叠加额外权限
    if project_role:
        pr = project_role.lower().strip()
        project_ops = PROJECT_ROLE_OPERATIONS.get(pr, set())
        return base_ops | project_ops

    return set(base_ops)  # 返回副本，避免外部修改


def can(
    system_role: str,
    project_role: str | None,
    operation: str,
) -> bool:
    """
    判断指定角色组合是否允许执行某操作。
    """
    allowed = get_allowed_operations(system_role, project_role)
    return operation in allowed


def why_cannot(
    system_role: str,
    project_role: str | None,
    operation: str,
) -> str | None:
    """
    返回不能执行操作的原因，如果可以执行则返回 None。
    """
    if can(system_role, project_role, operation):
        return None

    role_desc = system_role
    if project_role:
        role_desc = f"{system_role}(项目职责: {project_role})"

    return f"角色 {role_desc} 无 {operation} 权限"


def get_permission_matrix(
    system_role: str,
    project_role: str | None = None,
) -> dict:
    """
    P0-4.4: 返回完整的权限矩阵响应（供 API 端点使用）。
    """
    allowed = get_allowed_operations(system_role, project_role)
    denied = set(OPERATION_CODES) - allowed
    return {
        "operations": sorted(allowed),
        "denied_operations": sorted(denied),
        "system_role": system_role,
        "project_role": project_role,
        "all_operation_codes": OPERATION_CODES,
    }
