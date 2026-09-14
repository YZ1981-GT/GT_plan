# Feature: audit-report-deliverable-center, Property 34: 权限矩阵授权一致性
"""Property 34: 权限矩阵授权一致性 — 全 (角色, 操作, 状态) 三元组授权判定。

Validates: Requirements 14.4, 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7

授权规则（需求 17.1-17.7 + 14.4）：
- 17.1 审计师及以上 → export/create
- 17.2 项目成员（含 EQCR 只读） → preview/download/list
- 17.3 审计师及以上 且状态 ∉ {confirmed,signed,archived} → 在线编辑 edit
- 17.4 项目经理/合伙人（+admin） → 审批 approve
- 17.5 项目经理及以上 → 归档 archive
- 17.6 admin → 解除归档 unarchive
- 17.7 / 14.4 EQCR 复核角色 → 全程仅只读（所有写操作拒绝，仅读允许）
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.base import UserRole
from app.services.deliverable_permissions import (
    READ_ACTIONS,
    WRITE_ACTIONS,
    DeliverableAction,
    can_deliverable,
)

# 系统全部角色（来自 UserRole 枚举），不与实现共用集合，独立列举
ALL_ROLES = [r.value for r in UserRole]  # admin/partner/manager/auditor/qc/readonly

# 审计师及以上：auditor 及职级更高的角色（含 qc 质控）
AUDITOR_OR_ABOVE = {"auditor", "qc", "manager", "partner", "admin"}
# 项目经理及以上
MANAGER_OR_ABOVE = {"manager", "partner", "admin"}
# 审批角色：项目经理/合伙人（+admin）
APPROVER_ROLES = {"manager", "partner", "admin"}
# 编辑锁定状态
LOCKED_EDIT_STATUSES = {"confirmed", "signed", "archived"}

ALL_STATUSES = [
    None,
    "draft",
    "generating",
    "generated",
    "editing",
    "pending_approval",
    "confirmed",
    "signed",
    "archived",
]

ALL_ACTIONS = list(DeliverableAction)


def _oracle(role: str, action: DeliverableAction, status: str | None, is_eqcr: bool) -> bool:
    """独立编码需求 17.1-17.7 的预期授权结果（授权矩阵真值表 oracle）。"""
    # 17.7 / 14.4 EQCR 复核角色全程仅只读
    if is_eqcr:
        return action in READ_ACTIONS

    # 17.2 项目成员（任何角色）可预览/下载/列表
    if action in READ_ACTIONS:
        return True

    # 写操作
    if action == DeliverableAction.export:  # 17.1 审计师及以上
        return role in AUDITOR_OR_ABOVE
    if action == DeliverableAction.edit:  # 17.3 审计师及以上且非锁定态
        return role in AUDITOR_OR_ABOVE and status not in LOCKED_EDIT_STATUSES
    if action == DeliverableAction.confirm:  # 审计师及以上（进入 confirmed 由 EQCR 守卫另控）
        return role in AUDITOR_OR_ABOVE
    if action == DeliverableAction.approve:  # 17.4 经理/合伙人
        return role in APPROVER_ROLES
    if action == DeliverableAction.sign:  # 签章：经理及以上
        return role in MANAGER_OR_ABOVE
    if action == DeliverableAction.archive:  # 17.5 经理及以上
        return role in MANAGER_OR_ABOVE
    if action == DeliverableAction.unarchive:  # 17.6 仅 admin
        return role == "admin"
    return False


@given(
    role=st.sampled_from(ALL_ROLES),
    action=st.sampled_from(ALL_ACTIONS),
    status=st.sampled_from(ALL_STATUSES),
    is_eqcr=st.booleans(),
)
@settings(max_examples=5)
def test_permission_matrix_authorization_consistency(role, action, status, is_eqcr):
    """Property 34: 任意 (角色, 操作, 状态, EQCR标志) 的授权判定与权限矩阵一致。"""
    actual = can_deliverable(
        role, action, task_status=status, is_eqcr_assignment=is_eqcr
    )
    expected = _oracle(role, action, status, is_eqcr)
    assert actual == expected, (
        f"role={role} action={action.value} status={status} is_eqcr={is_eqcr}: "
        f"期望 {expected}，实际 {actual}"
    )


@given(
    role=st.sampled_from(ALL_ROLES),
    action=st.sampled_from(list(WRITE_ACTIONS)),
    status=st.sampled_from(ALL_STATUSES),
)
@settings(max_examples=5)
def test_eqcr_reviewer_read_only(role, action, status):
    """Property 34 (17.7/14.4): EQCR 复核角色对所有写操作被拒。"""
    assert (
        can_deliverable(role, action, task_status=status, is_eqcr_assignment=True)
        is False
    )


@given(
    role=st.sampled_from(ALL_ROLES),
    action=st.sampled_from(list(READ_ACTIONS)),
    status=st.sampled_from(ALL_STATUSES),
    is_eqcr=st.booleans(),
)
@settings(max_examples=5)
def test_read_actions_always_allowed_for_members(role, action, status, is_eqcr):
    """Property 34 (17.2/17.7): 任何项目成员（含 EQCR）均可执行只读操作。"""
    assert (
        can_deliverable(role, action, task_status=status, is_eqcr_assignment=is_eqcr)
        is True
    )
