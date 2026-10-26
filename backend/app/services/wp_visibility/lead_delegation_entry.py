"""旁路委派入口统一走底稿主编委派事务（spec procedure-trim-generation-delegation-chain 需求 4.3 / 任务 12）。

原先 5 条旁路直写 ``working_paper.assigned_to``：批量分配（不限项目）、增强批量分配、复核页指派、人员交接、
wp_mapping 按姓名分配 —— 不看裁剪、不校验可见范围、不记委派历史、不递增可见性策略版本、投影与展示镜像不同步。
现统一：入参（本项目人员 id 或其用户 id）解析为本项目唯一有效人员 → ``DelegationTransactionService.delegate_lead``
（裁剪 / 回收站拦截 + 有效循环范围 + 两层 + 历史 + 策略版本；缺循环整批处理完一次报全，调用方回滚）。
复核人不属委派层，仍直写 ``reviewer``，但必须是本项目成员。只 flush 不 commit。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import ProjectUser
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.wp_visibility.delegation_guard import DelegationError, DelegationRejectReason

NOT_MEMBER_MESSAGE = "被委派人不是本项目成员（或人员记录不唯一），不能委派；请先在团队分配中加入"


async def resolve_project_staff(db: AsyncSession, project_id: UUID, person_id: UUID | None) -> UUID | None:
    """本项目人员 id 或其用户 id ⇒ 本项目唯一有效人员 id（有未删除的团队分配）；不在项目 / 不唯一 ⇒ None。"""
    if person_id is None:
        return None
    in_project = sa.select(ProjectAssignment.staff_id).where(
        ProjectAssignment.project_id == project_id, ProjectAssignment.is_deleted == sa.false()
    )
    ids = set((await db.execute(
        sa.select(StaffMember.id).where(
            StaffMember.is_deleted == sa.false(),
            sa.or_(StaffMember.id == person_id, StaffMember.user_id == person_id),
            StaffMember.id.in_(in_project),
        )
    )).scalars().all())
    return next(iter(ids)) if len(ids) == 1 else None


async def resolve_project_member_user(db: AsyncSession, project_id: UUID, person_id: UUID | None) -> UUID | None:
    """复核人：本项目人员 id ⇒ 其用户 id；用户 id 且有本项目成员行或团队分配 ⇒ 原值；否则 None。"""
    staff_id = await resolve_project_staff(db, project_id, person_id)
    if staff_id is not None:
        user_id = (await db.execute(sa.select(StaffMember.user_id).where(StaffMember.id == staff_id))).scalar()
        if user_id is not None:
            return user_id
    if person_id is None:
        return None
    member = (await db.execute(
        sa.select(sa.func.count()).select_from(ProjectUser).where(
            ProjectUser.project_id == project_id,
            ProjectUser.user_id == person_id,
            ProjectUser.is_deleted == sa.false(),
        )
    )).scalar_one()
    return person_id if member else None


@dataclass
class LeadBatchOutcome:
    updated: list[UUID] = field(default_factory=list)          # 已设主编的底稿
    missing: list[UUID] = field(default_factory=list)          # 不在本项目 / 已删除（跳过）
    skipped_trimmed: list[UUID] = field(default_factory=list)  # 已裁 / 在回收站（仅 skip_trimmed=True 时跳过）
    assignee_users: dict[UUID, UUID] = field(default_factory=dict)  # 底稿 id → 主编用户 id


async def delegate_workpaper_leads(
    db: AsyncSession,
    project_id: UUID,
    items,
    *,
    actor_user_id: UUID,
    expand_scope: bool = False,
    scope_reason: str | None = None,
    skip_trimmed: bool = False,
) -> LeadBatchOutcome:
    """逐张底稿设主编；``items`` = ``[(wp_id, person_id), ...]``。

    - 底稿不在本项目 / 已删除 ⇒ 跳过（记 ``missing``，不跨项目改别人的底稿）。
    - 被委派人解析不到本项目唯一人员 ⇒ ``DelegationError(mapping_invalid)``。
    - 已裁 / 在回收站 ⇒ ``DelegationError``（``skip_trimmed=True`` 时跳过，人员交接用）。
    - 缺循环先收集、处理完一次报全（``out_of_scope``，带全部缺少的循环）；带理由扩权 ⇒ 同事务扩大。
    """
    from app.services.wp_visibility.delegation_transaction import (
        DelegationTransactionService,
        LeadDelegationRequest,
    )

    wp_ids = sorted({wp_id for wp_id, _ in items}, key=str)
    codes: dict[UUID, str] = {}
    for i in range(0, len(wp_ids), 500):
        rows = await db.execute(
            sa.select(WorkingPaper.id, WpIndex.wp_code)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.id.in_(wp_ids[i:i + 500]),
                WorkingPaper.is_deleted == sa.false(),
                WpIndex.is_deleted == sa.false(),
            )
        )
        codes.update({r[0]: r[1] for r in rows.all()})

    deleg = DelegationTransactionService(db)
    deleg.defer_scope_gaps()
    staff_of: dict[UUID, UUID | None] = {}
    outcome = LeadBatchOutcome()
    for wp_id, person_id in items:
        if wp_id not in codes:
            outcome.missing.append(wp_id)
            continue
        if person_id not in staff_of:
            staff_of[person_id] = await resolve_project_staff(db, project_id, person_id)
        staff_id = staff_of[person_id]
        if staff_id is None:
            raise DelegationError(DelegationRejectReason.mapping_invalid, NOT_MEMBER_MESSAGE)
        try:
            result = await deleg.delegate_lead(LeadDelegationRequest(
                project_id=project_id, actor_user_id=actor_user_id, staff_id=staff_id,
                wp_id=wp_id, wp_code=codes[wp_id], expand_scope=expand_scope, scope_reason=scope_reason,
            ))
        except DelegationError as exc:
            if skip_trimmed and exc.reason in (DelegationRejectReason.trimmed, DelegationRejectReason.recycled):
                outcome.skipped_trimmed.append(wp_id)
                continue
            raise
        outcome.updated.append(wp_id)
        if result.user_id is not None:
            outcome.assignee_users[wp_id] = result.user_id
    deleg.raise_deferred_scope_gaps()
    return outcome
