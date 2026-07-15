"""程序行任务：项目级授权、staff/user 归一化与 SOD 唯一守卫（Task 7）

Feature: procedure-delegation-notification
需求：5.1-5.3（staff/user 边界与 SOD）、8.5-8.6（历史参与者只读）、11.1-11.6（fail-closed 项目授权）
Design：D5（staff 与 user 边界唯一）、C5（ProcedureProjectAuthorization）
Properties：P16（staff/user 归一化 SOD）、P32（项目授权 fail-closed）

本模块是本 feature **唯一** 的项目级授权入口，供裁剪（粗裁/细裁）、reconcile apply、
scheme apply、materialize、delegation preview/apply、转派、cancel/reopen 与 dead-letter
replay 复用同一 guard。所有敏感 mutation router 必须挂 `require_project_delegator`
（或直接调用 `ensure_project_delegator`）。

核心不变量（fail-closed）：
- 仅认证 admin 全局放行；partner/signing_partner/manager 必须持当前项目 **唯一** active
  ProjectAssignment，且该 assignment 经 **唯一** active `StaffMember.user_id → staff_id`
  链路与当前 user 绑定。
- 任意缺失、无 user_id、inactive、重复映射、跨项目或查询异常一律 fail-closed 403，
  不 500 泄露内部错误。
- assignee/reviewer 外键均指向 staff；actor/recipient 使用 user；所有 SOD **先归一到 user**
  再比较，禁止用 staff id 推断是否同人。无 active user_id 的 staff 不得被委派或设为 reviewer。
- 同一归一化 user 不得同时成为同一任务的 assignee 与 reviewer。

纯读、无写副作用；service 约定只 flush 不 commit（本模块不写库）。
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from uuid import UUID

import sqlalchemy as sa
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.procedure_models import ProcedureRowTask, ProcedureRowTaskHistory
from app.models.staff_models import ProjectAssignment, StaffMember

logger = logging.getLogger(__name__)

# 允许作为程序行委派人（Delegator）的项目委派角色（Design C5、需求 11.1/11.3）。
# ProjectAssignment.role 为自由文本列；此处以规范化小写字面量集合判定，不依赖系统 role。
DELEGATOR_ASSIGNMENT_ROLES: frozenset[str] = frozenset(
    {"partner", "signing_partner", "manager"}
)


# ---------------------------------------------------------------------------
# 结果模型
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DelegatorContext:
    """通过 `require_project_delegator` 后的授权上下文（供审计/后续 mutation 使用）。"""

    user: User
    project_id: UUID
    is_admin: bool
    # 非 admin 时才有：归一链路的 staff / assignment 角色
    staff_id: UUID | None = None
    assignment_role: str | None = None


class ParticipantAccess(str, enum.Enum):
    """任务参与者访问级别（动作授权用归一化 user 比较，而非 staff id）。"""

    delegator = "delegator"          # 项目 Delegator：可执行 cancel/reopen/reassign 等
    assignee = "assignee"            # 当前执行人：ack/start/submit
    reviewer = "reviewer"            # 当前操作复核人：request_changes/review
    history_readonly = "history"     # 历史参与者：仅只读其参与期间记录
    none = "none"                    # 无任何访问


@dataclass
class TaskBinding:
    """从 task 反查的服务端项目绑定（不信任客户端 project_id，需求 11.6）。"""

    task_id: UUID
    project_id: UUID
    wp_index_id: UUID
    wp_id: UUID | None
    assignee_staff_id: UUID | None
    reviewer_staff_id: UUID | None


@dataclass
class ParticipantResolution:
    """任务参与者解析结果：当前访问级别 + 归一化只读参与者 user 集合。"""

    access: ParticipantAccess
    binding: TaskBinding
    normalized_user_id: UUID | None = None
    readonly_user_ids: set[UUID] = field(default_factory=set)


# ---------------------------------------------------------------------------
# staff → user 归一化（D5 / P16）
# ---------------------------------------------------------------------------


async def resolve_user_active_staff_id(db: AsyncSession, user_id: UUID) -> UUID:
    """当前 user → **唯一** active StaffMember.id。

    缺失/重复映射均 fail-closed 抛 403（P32）。查询异常由上层 `ensure_project_delegator`
    的 try/except 统一转 403。
    """
    rows = (
        await db.execute(
            sa.select(StaffMember.id).where(
                StaffMember.user_id == user_id,
                StaffMember.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().all()
    if len(rows) != 1:
        # 0 = 缺失；>1 = 重复映射：均拒绝
        raise HTTPException(status_code=403, detail="项目授权失败：用户未唯一绑定人员")
    return rows[0]


async def normalize_staff_to_user(db: AsyncSession, staff_id: UUID | None) -> UUID | None:
    """staff → active 归一化 user_id；staff 缺失/inactive/无 user_id 返回 None。

    只读且不抛错，供参与者集合构建与宽松归一使用。
    """
    if staff_id is None:
        return None
    return (
        await db.execute(
            sa.select(StaffMember.user_id).where(
                StaffMember.id == staff_id,
                StaffMember.is_deleted == False,  # noqa: E712
                StaffMember.user_id.isnot(None),
            )
        )
    ).scalar_one_or_none()


async def list_project_delegator_user_ids(
    db: AsyncSession, project_id: UUID
) -> set[UUID]:
    """本项目全部 Delegator 的归一化 user 集合（partner/signing_partner/manager，Req 5.6）。

    经 active ``ProjectAssignment.staff_id → StaffMember.user_id`` 唯一链路解析；用于
    reviewer_missing 时向有权限的 Delegator 产生可靠通知意图。只读、无副作用；查询异常
    上层可容错降级（reviewer_missing 通知不阻断领域写）。
    """
    rows = (
        await db.execute(
            sa.select(StaffMember.user_id)
            .join(ProjectAssignment, ProjectAssignment.staff_id == StaffMember.id)
            .where(
                ProjectAssignment.project_id == project_id,
                ProjectAssignment.is_deleted == False,  # noqa: E712
                sa.func.lower(sa.func.trim(ProjectAssignment.role)).in_(
                    DELEGATOR_ASSIGNMENT_ROLES
                ),
                StaffMember.is_deleted == False,  # noqa: E712
                StaffMember.user_id.isnot(None),
            )
        )
    ).scalars().all()
    return {u for u in rows if u is not None}


async def require_staff_active_user(db: AsyncSession, staff_id: UUID) -> UUID:
    """委派/设为 reviewer 前置：staff 必须 active 且有 user_id，否则 422。

    需求 5.2：无 user_id 的 StaffMember 禁止被委派或设为 reviewer。
    """
    user_id = await normalize_staff_to_user(db, staff_id)
    if user_id is None:
        raise HTTPException(
            status_code=422,
            detail="人员无有效账号绑定（缺 active user_id），不能被委派或设为复核人",
        )
    return user_id


async def assert_sod_distinct(
    db: AsyncSession,
    assignee_staff_id: UUID | None,
    reviewer_staff_id: UUID | None,
) -> None:
    """SOD 唯一守卫（P16 / 需求 5.2-5.3）。

    - assignee 与 reviewer 若设置，各自 staff 必须 active 且有 user_id（否则 422）。
    - 两者 **归一到 user** 后不得相同（否则 409 自我复核）。
    - 仅当两者都设置时才比较归一化 user；单独设置只校验 user_id 有效性。
    - **禁止** 直接比较 staff id 推断是否同人（两个不同 staff 可能归一到同一 user）。
    """
    assignee_user = (
        await require_staff_active_user(db, assignee_staff_id)
        if assignee_staff_id is not None
        else None
    )
    reviewer_user = (
        await require_staff_active_user(db, reviewer_staff_id)
        if reviewer_staff_id is not None
        else None
    )
    if assignee_user is not None and reviewer_user is not None and assignee_user == reviewer_user:
        raise HTTPException(
            status_code=409,
            detail="职责分离冲突：同一人员不能同时是该任务的执行人与操作复核人",
        )


# ---------------------------------------------------------------------------
# 项目级 Delegator 授权（C5 / P32）
# ---------------------------------------------------------------------------


async def ensure_project_delegator(
    db: AsyncSession,
    current_user: User,
    project_id: UUID,
) -> DelegatorContext:
    """项目级 Delegator 授权核心函数（fail-closed）。

    规则（Design C5）：
      1. 认证 admin：全局通过。
      2. 其余 user：唯一 active StaffMember(user_id) → 唯一 active ProjectAssignment(project_id, staff_id)。
      3. assignment role ∈ {partner, signing_partner, manager}。
      4. 任何缺失/重复/inactive/跨项目/查询异常 → 403（不 500 泄露）。

    供 materialize、reconcile、trim、scheme、delegation、cancel/reopen、dead-letter replay
    复用；router 可直接 `await ensure_project_delegator(...)`，或用 `require_project_delegator`
    依赖。
    """
    # ① 认证 admin 全局放行
    try:
        if current_user.role.value == "admin":
            return DelegatorContext(
                user=current_user, project_id=project_id, is_admin=True
            )
    except Exception:  # role 缺失/异常同样 fail-closed
        raise HTTPException(status_code=403, detail="项目授权失败")

    try:
        # ② 唯一 active StaffMember(user_id)
        staff_id = await resolve_user_active_staff_id(db, current_user.id)

        # ③ 唯一 active ProjectAssignment(project_id, staff_id)
        assignments = (
            await db.execute(
                sa.select(ProjectAssignment.role).where(
                    ProjectAssignment.project_id == project_id,
                    ProjectAssignment.staff_id == staff_id,
                    ProjectAssignment.is_deleted == False,  # noqa: E712
                )
            )
        ).scalars().all()
    except HTTPException:
        raise
    except Exception as exc:  # 查询异常 fail-closed，不 500 泄露
        logger.warning("项目授权查询异常 (project=%s user=%s): %s", project_id, current_user.id, exc)
        raise HTTPException(status_code=403, detail="项目授权失败")

    if len(assignments) != 1:
        # 0 = 无当前项目 active assignment（跨项目/缺失）；>1 = 重复映射
        raise HTTPException(status_code=403, detail="项目授权失败：无当前项目唯一有效委派")

    role = (assignments[0] or "").strip().lower()
    if role not in DELEGATOR_ASSIGNMENT_ROLES:
        raise HTTPException(status_code=403, detail="项目授权失败：委派角色不足")

    return DelegatorContext(
        user=current_user,
        project_id=project_id,
        is_admin=False,
        staff_id=staff_id,
        assignment_role=role,
    )


def require_project_delegator(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FastAPI 依赖：项目级 Delegator 守卫（路径参数名 `project_id`）。

    用于 `/api/projects/{project_id}/...` 形态路由。对使用 `{pid}` 的路由，
    见 `require_project_delegator_pid`。二者共享 `ensure_project_delegator` 核心逻辑。
    """
    return ensure_project_delegator(db, current_user, project_id)


async def require_project_delegator_pid(
    pid: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DelegatorContext:
    """FastAPI 依赖：项目级 Delegator 守卫（路径参数名 `pid`）。

    本 feature 的 API 设计统一使用 `/api/projects/{pid}/...`，故 materialize、
    reconcile、trim、scheme、delegation、transition、dead-letter replay 等 router
    应挂本依赖。
    """
    return await ensure_project_delegator(db, current_user, pid)


# ---------------------------------------------------------------------------
# 任务绑定反查与参与者/历史只读 guard（需求 11.5-11.6 / 8.5-8.6）
# ---------------------------------------------------------------------------


async def resolve_task_binding(db: AsyncSession, task_id: UUID) -> TaskBinding:
    """从 task 反查服务端项目绑定（不信任客户端 project_id）。

    任务不存在/软删除 → 404 且不泄露程序文本。
    """
    row = (
        await db.execute(
            sa.select(
                ProcedureRowTask.id,
                ProcedureRowTask.project_id,
                ProcedureRowTask.wp_index_id,
                ProcedureRowTask.wp_id,
                ProcedureRowTask.assignee_staff_id,
                ProcedureRowTask.reviewer_staff_id,
            ).where(
                ProcedureRowTask.id == task_id,
                ProcedureRowTask.is_deleted == False,  # noqa: E712
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return TaskBinding(
        task_id=row[0],
        project_id=row[1],
        wp_index_id=row[2],
        wp_id=row[3],
        assignee_staff_id=row[4],
        reviewer_staff_id=row[5],
    )


async def assert_task_in_project(
    db: AsyncSession, task_id: UUID, project_id: UUID
) -> TaskBinding:
    """校验 task→project 绑定；跨项目返回 404（不泄露），需求 9.8/11.6。"""
    binding = await resolve_task_binding(db, task_id)
    if binding.project_id != project_id:
        # 跨项目：按“不存在”处理，不泄露程序文本/metadata
        raise HTTPException(status_code=404, detail="任务不存在")
    return binding


async def build_history_readonly_user_ids(
    db: AsyncSession, task_id: UUID
) -> set[UUID]:
    """构建历史参与者只读 user 集合（需求 8.5）。

    从 append-only history 的 old/new assignee/reviewer staff 归一到 user。
    历史参与者仅拥有其参与期间的只读访问，不获得当前动作权限。
    conversation/issue 参与关系由 Task 13 在此基础上并集扩展。
    """
    staff_rows = (
        await db.execute(
            sa.select(
                ProcedureRowTaskHistory.old_assignee_staff_id,
                ProcedureRowTaskHistory.new_assignee_staff_id,
                ProcedureRowTaskHistory.old_reviewer_staff_id,
                ProcedureRowTaskHistory.new_reviewer_staff_id,
            ).where(ProcedureRowTaskHistory.task_id == task_id)
        )
    ).all()
    staff_ids: set[UUID] = set()
    for row in staff_rows:
        for sid in row:
            if sid is not None:
                staff_ids.add(sid)
    if not staff_ids:
        return set()
    user_rows = (
        await db.execute(
            sa.select(StaffMember.user_id).where(
                StaffMember.id.in_(staff_ids),
                StaffMember.is_deleted == False,  # noqa: E712
                StaffMember.user_id.isnot(None),
            )
        )
    ).scalars().all()
    return {u for u in user_rows if u is not None}


async def build_task_issue_participant_user_ids(
    db: AsyncSession, task_id: UUID
) -> set[UUID]:
    """该 task 关联 review_comment IssueTicket 的参与者 user 集合（需求 8.6）。

    IssueTicket.owner_id 已是 users.id（责任人）。用于把 issue 参与关系纳入对话授权并集。
    只读；导入置于函数内避免模块级循环依赖。
    """
    from app.models.phase15_models import IssueTicket

    rows = (
        await db.execute(
            sa.select(IssueTicket.owner_id).where(
                IssueTicket.source == "review_comment",
                IssueTicket.source_ref_id == task_id,
                IssueTicket.owner_id.isnot(None),
            )
        )
    ).scalars().all()
    return {u for u in rows if u is not None}


async def build_conversation_participant_user_ids(
    db: AsyncSession, task_id: UUID
) -> set[UUID]:
    """该 task 程序行 ReviewConversation 的参与者 user 集合（需求 8.6）。

    并集来源：conversation initiator/target 以及全部 ReviewMessage.sender。授权 **不** 只依赖
    conversation initiator/target 单点，故这里连同消息发送者一并纳入。只读。
    """
    from app.models.phase10_models import ReviewConversation, ReviewMessage

    conv_rows = (
        await db.execute(
            sa.select(
                ReviewConversation.id,
                ReviewConversation.initiator_id,
                ReviewConversation.target_id,
            ).where(
                ReviewConversation.related_object_type == "procedure_row_task",
                ReviewConversation.related_object_id == task_id,
                ReviewConversation.is_deleted == False,  # noqa: E712
            )
        )
    ).all()
    users: set[UUID] = set()
    conv_ids: list[UUID] = []
    for cid, initiator, target in conv_rows:
        conv_ids.append(cid)
        if initiator is not None:
            users.add(initiator)
        if target is not None:
            users.add(target)
    if conv_ids:
        senders = (
            await db.execute(
                sa.select(ReviewMessage.sender_id).where(
                    ReviewMessage.conversation_id.in_(conv_ids)
                )
            )
        ).scalars().all()
        users.update(s for s in senders if s is not None)
    return users


async def build_conversation_readonly_user_ids(
    db: AsyncSession, task_id: UUID
) -> set[UUID]:
    """对话授权的历史/参与者只读并集（需求 8.6）。

    = 任务历史参与者（history）∪ IssueTicket 参与者 ∪ ReviewConversation 参与者。
    历史只读参与者仅拥有只读范围，不获得当前动作权限（需求 8.5）。
    """
    history = await build_history_readonly_user_ids(db, task_id)
    issue_users = await build_task_issue_participant_user_ids(db, task_id)
    conv_users = await build_conversation_participant_user_ids(db, task_id)
    return history | issue_users | conv_users


async def resolve_conversation_access(
    db: AsyncSession,
    task_id: UUID,
    current_user: User,
) -> ParticipantResolution:
    """解析当前 user 对程序行 **对话** 的访问级别（需求 8.5-8.6）。

    在 `resolve_task_participant_access`（delegator/assignee/reviewer/history）基础上，把
    IssueTicket 参与者与 ReviewConversation 参与者（含消息发送者）纳入 **只读** 并集：
    - delegator/assignee/reviewer → 保留其访问级别（可发消息 / 处理 issue）。
    - 命中并集但非当前参与者 → history_readonly（只读，无当前动作权限）。
    - 都不命中 → none。

    授权不只依赖 conversation initiator/target 单点（P26）。
    """
    resolution = await resolve_task_participant_access(db, task_id, current_user)
    if resolution.access in (
        ParticipantAccess.delegator,
        ParticipantAccess.assignee,
        ParticipantAccess.reviewer,
    ):
        return resolution

    readonly = await build_conversation_readonly_user_ids(db, task_id)
    resolution.readonly_user_ids = readonly
    if resolution.access == ParticipantAccess.history_readonly:
        return resolution
    if current_user.id in readonly:
        resolution.access = ParticipantAccess.history_readonly
        resolution.normalized_user_id = current_user.id
    return resolution


async def resolve_task_participant_access(
    db: AsyncSession,
    task_id: UUID,
    current_user: User,
) -> ParticipantResolution:
    """解析当前 user 对任务的访问级别（动作授权用归一化 user 比较）。

    优先级：delegator > assignee > reviewer > history_readonly > none。
    - 从 task 反查 project 后判定项目 Delegator（admin/项目委派人）。
    - assignee/reviewer 按 **归一化 user** 比较（而非 staff id）。
    - 否则查历史只读集合；命中则 history_readonly（只读，无当前动作权限）。
    - 都不命中 → none（router 应据此 403）。
    """
    binding = await resolve_task_binding(db, task_id)

    # 当前 user 归一化（admin 可能无 staff，容错为 None）
    try:
        normalized_user_id: UUID | None = current_user.id
    except Exception:
        normalized_user_id = None

    # ① Delegator（含 admin）
    try:
        await ensure_project_delegator(db, current_user, binding.project_id)
        return ParticipantResolution(
            access=ParticipantAccess.delegator,
            binding=binding,
            normalized_user_id=normalized_user_id,
        )
    except HTTPException:
        pass

    # ② assignee / reviewer（归一化 user 比较）
    assignee_user = await normalize_staff_to_user(db, binding.assignee_staff_id)
    if assignee_user is not None and assignee_user == current_user.id:
        return ParticipantResolution(
            access=ParticipantAccess.assignee,
            binding=binding,
            normalized_user_id=current_user.id,
        )
    reviewer_user = await normalize_staff_to_user(db, binding.reviewer_staff_id)
    if reviewer_user is not None and reviewer_user == current_user.id:
        return ParticipantResolution(
            access=ParticipantAccess.reviewer,
            binding=binding,
            normalized_user_id=current_user.id,
        )

    # ③ 历史只读参与者
    readonly = await build_history_readonly_user_ids(db, task_id)
    if current_user.id in readonly:
        return ParticipantResolution(
            access=ParticipantAccess.history_readonly,
            binding=binding,
            normalized_user_id=current_user.id,
            readonly_user_ids=readonly,
        )

    # ④ 无访问
    return ParticipantResolution(
        access=ParticipantAccess.none,
        binding=binding,
        normalized_user_id=normalized_user_id,
        readonly_user_ids=readonly,
    )
