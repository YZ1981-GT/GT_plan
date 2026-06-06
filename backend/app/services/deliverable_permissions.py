"""交付物操作权限矩阵 — 角色 × 操作 × 状态"""

from __future__ import annotations

from enum import Enum

AUDITOR_PLUS = frozenset({"auditor", "qc", "manager", "partner", "admin"})
MANAGER_PLUS = frozenset({"manager", "partner", "admin"})
APPROVE_ROLES = frozenset({"manager", "partner", "admin"})
LOCKED_EDIT_STATUSES = frozenset({"confirmed", "signed", "archived"})


class DeliverableAction(str, Enum):
    list = "list"
    preview = "preview"
    download = "download"
    export = "export"
    edit = "edit"
    confirm = "confirm"
    sign = "sign"
    approve = "approve"
    archive = "archive"
    unarchive = "unarchive"


READ_ACTIONS = frozenset({
    DeliverableAction.list,
    DeliverableAction.preview,
    DeliverableAction.download,
})

WRITE_ACTIONS = frozenset({
    DeliverableAction.export,
    DeliverableAction.edit,
    DeliverableAction.confirm,
    DeliverableAction.sign,
    DeliverableAction.approve,
    DeliverableAction.archive,
    DeliverableAction.unarchive,
})


def can_deliverable(
    user_role: str,
    action: DeliverableAction | str,
    *,
    task_status: str | None = None,
    is_eqcr_assignment: bool = False,
) -> bool:
    """按权限矩阵判定是否允许操作"""
    if isinstance(action, str):
        action = DeliverableAction(action)

    if is_eqcr_assignment:
        return action in READ_ACTIONS

    if action in READ_ACTIONS:
        return True

    if action == DeliverableAction.export:
        return user_role in AUDITOR_PLUS

    if action == DeliverableAction.edit:
        return (
            user_role in AUDITOR_PLUS
            and (task_status is None or task_status not in LOCKED_EDIT_STATUSES)
        )

    if action == DeliverableAction.confirm:
        return user_role in AUDITOR_PLUS

    if action == DeliverableAction.sign:
        return user_role in MANAGER_PLUS

    if action == DeliverableAction.approve:
        return user_role in APPROVE_ROLES

    if action == DeliverableAction.archive:
        return user_role in MANAGER_PLUS

    if action == DeliverableAction.unarchive:
        return user_role == "admin"

    return False
