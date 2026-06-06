"""
Permission Matrix Service (MVP)

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


def get_allowed_operations(
    system_role: str,
    project_role: str | None = None,
) -> set[str]:
    """
    根据系统角色和可选的项目职责，返回允许的操作集合。

    Args:
        system_role: 系统级角色 (admin/partner/manager/auditor/qc/eqcr)
        project_role: 项目级职责 (可选, MVP 阶段暂不使用)

    Returns:
        允许的操作 code 集合
    """
    role = system_role.lower().strip()
    base_ops = ROLE_OPERATIONS.get(role, set())

    # MVP: project_role 预留接口，后续 P0 阶段实现项目职责叠加
    # 当 project_role 提供时可以叠加额外权限
    if project_role:
        project_ops = ROLE_OPERATIONS.get(project_role.lower().strip(), set())
        return base_ops | project_ops

    return set(base_ops)  # 返回副本，避免外部修改


def can(
    system_role: str,
    project_role: str | None,
    operation: str,
) -> bool:
    """
    判断指定角色组合是否允许执行某操作。

    Args:
        system_role: 系统级角色
        project_role: 项目级职责 (可选)
        operation: 操作 code

    Returns:
        True 如果允许，否则 False
    """
    allowed = get_allowed_operations(system_role, project_role)
    return operation in allowed
