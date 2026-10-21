"""团队委派服务

Phase 9 Task 1.4: 项目团队委派 CRUD + 通知推送
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import NamedTuple
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import PermissionLevel, ProjectUserRole
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.core import Notification, Project, ProjectUser
from app.services.notification_types import ASSIGNMENT_CREATED

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ROLE_MAP — 委派角色 → (ProjectUserRole, PermissionLevel) 的单一真源
# ---------------------------------------------------------------------------
# R5 任务 2：将字典抽到模块级，满足跨轮约束 2 的"权限四点同步"显式验证脚本：
#
#     from app.services.assignment_service import ROLE_MAP
#     assert 'eqcr' in ROLE_MAP
#
# ``_sync_project_users`` 经 :func:`resolve_member_mapping` 读取本常量，不再本地重复定义。
# ``ProjectUserRole`` 不新增 ``eqcr`` 枚举（与 design.md "架构决策一览"
# "EQCR 角色挂载复用 ProjectAssignment.role='eqcr'" 对齐），
# 因此 eqcr 在 project_users 层面映射为 partner+review；
# 独立性仍由 ``project_assignments.role='eqcr'`` 在业务层区分。
# partner-manager-edit-permission：合伙人（含签字合伙人）与经理为 edit 级，质控与 EQCR 保持 review。
ROLE_MAP: dict[str, tuple[ProjectUserRole, PermissionLevel]] = {
    "signing_partner": (ProjectUserRole.partner, PermissionLevel.edit),
    "partner": (ProjectUserRole.partner, PermissionLevel.edit),
    "合伙人": (ProjectUserRole.partner, PermissionLevel.edit),
    "manager": (ProjectUserRole.manager, PermissionLevel.edit),
    "项目经理": (ProjectUserRole.manager, PermissionLevel.edit),
    "qc": (ProjectUserRole.qc, PermissionLevel.review),
    "质控": (ProjectUserRole.qc, PermissionLevel.review),
    "auditor": (ProjectUserRole.auditor, PermissionLevel.edit),
    "审计员": (ProjectUserRole.auditor, PermissionLevel.edit),
    "assistant": (ProjectUserRole.auditor, PermissionLevel.edit),
    "助理": (ProjectUserRole.auditor, PermissionLevel.edit),
    # R5 任务 2：EQCR 独立复核合伙人
    "eqcr": (ProjectUserRole.partner, PermissionLevel.review),
    "独立复核合伙人": (ProjectUserRole.partner, PermissionLevel.review),
}

UNMAPPED_ROLE: tuple[ProjectUserRole, PermissionLevel] = (ProjectUserRole.readonly, PermissionLevel.readonly)
# 两个别名集合都由 ROLE_MAP 推导，不另写别名字面量副本（需求 7.2）。
EQCR_ROLE_ALIASES: frozenset[str] = frozenset(
    k for k, v in ROLE_MAP.items() if v == (ProjectUserRole.partner, PermissionLevel.review))
PARTNER_MANAGER_ROLE_ALIASES: frozenset[str] = frozenset(
    k for k, (r, lv) in ROLE_MAP.items()
    if r in (ProjectUserRole.partner, ProjectUserRole.manager) and lv == PermissionLevel.edit)
# 同一级别有多个项目角色候选时按此先后取第一个（需求 3.8）；须覆盖 ROLE_MAP 与 UNMAPPED_ROLE 写得出的全部项目角色。
_ROLE_TIEBREAK: tuple[ProjectUserRole, ...] = (
    ProjectUserRole.partner, ProjectUserRole.manager, ProjectUserRole.qc,
    ProjectUserRole.auditor, ProjectUserRole.readonly)
_LEVEL_RANK: dict[PermissionLevel, int] = {
    PermissionLevel.readonly: 0, PermissionLevel.review: 1, PermissionLevel.edit: 2}


def map_assignment_role(role: str) -> tuple[ProjectUserRole, PermissionLevel]:
    """单个委派角色 →（项目角色，项目级别）：精确匹配，未登记取 UNMAPPED_ROLE（需求 2.2）。"""
    return ROLE_MAP.get(role, UNMAPPED_ROLE)


def resolve_member_mapping(roles: Iterable[str]) -> tuple[ProjectUserRole, PermissionLevel]:
    """同一用户在同一项目的一组委派角色 → 一组成员行取值，与先后顺序无关（需求 3.3、3.8）。"""
    if isinstance(roles, str):  # 单个字符串会被逐字拆开、静默落到未登记 ⇒ 按误用拒绝
        raise TypeError("resolve_member_mapping 需要委派角色序列，不接受单个字符串")
    roles = list(roles)
    if not roles:
        raise ValueError("resolve_member_mapping 需要至少一个委派角色")
    if any(r in EQCR_ROLE_ALIASES for r in roles):  # EQCR 优先，强制 (partner, review)
        return ROLE_MAP["eqcr"]
    mapped = [map_assignment_role(r) for r in roles]
    best = max((lv for _, lv in mapped), key=_LEVEL_RANK.__getitem__)  # 最高级别
    candidates = {r for r, lv in mapped if lv == best}
    return next(r for r in _ROLE_TIEBREAK if r in candidates), best  # 项目角色按固定先后取第一个


class MemberChange(NamedTuple):
    """委派同步对一名用户在本项目成员行的改动（只用于 info 日志与测试断言）；``before`` 为 None 表示新建。"""

    user_id: UUID
    before: tuple[ProjectUserRole, PermissionLevel] | None
    after: tuple[ProjectUserRole, PermissionLevel]

    def describe(self) -> str:
        before = "新建" if self.before is None else f"{self.before[0].value}/{self.before[1].value}"
        return f"{self.user_id}: {before} → {self.after[0].value}/{self.after[1].value}"


class AssignmentService:
    """项目团队委派服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_assignments(self, project_id: UUID) -> list[dict]:
        """获取项目的团队委派列表"""
        q = (
            sa.select(
                ProjectAssignment,
                StaffMember.name.label("staff_name"),
                StaffMember.title.label("staff_title"),
                StaffMember.employee_no,
            )
            .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
            .where(
                ProjectAssignment.project_id == project_id,
                ProjectAssignment.is_deleted == False,  # noqa
            )
            .order_by(ProjectAssignment.assigned_at)
        )
        rows = (await self.db.execute(q)).all()
        results = []
        for row in rows:
            pa = row[0]
            results.append({
                "id": str(pa.id),
                "project_id": str(pa.project_id),
                "staff_id": str(pa.staff_id),
                "role": pa.role,
                "assigned_cycles": pa.assigned_cycles,
                "assigned_at": str(pa.assigned_at) if pa.assigned_at else None,
                "staff_name": row.staff_name,
                "staff_title": row.staff_title,
                "employee_no": row.employee_no,
            })
        return results

    async def save_assignments(
        self,
        project_id: UUID,
        assignments: list[dict],
        assigned_by: UUID | None = None,
    ) -> list[ProjectAssignment]:
        """批量保存委派（先软删除旧的，再插入新的）

        R5 任务 2：在落库前对每一条委派执行 SOD 校验（EQCR 独立性规则），
        任一条冲突则整批拒绝，避免部分落库的一致性问题。
        随后由 :meth:`_sync_project_users` 按角色映射精确写入成员行（可升可降）。
        本方法只 flush、不 commit，由 router 统一提交。
        """
        now = datetime.now(timezone.utc)

        # ---- R5: SOD 前置校验（EQCR 独立性） ----
        # 同批次中 staff_id+role 的组合用来模拟"本次将形成的终态"，
        # 避免先删后插的瞬时窗口让规则误判。
        from app.services.sod_guard_service import (
            EqcrIndependenceRule,
            SodViolation,
        )

        rule = EqcrIndependenceRule()
        proposed_roles: list[tuple[UUID, str]] = [
            (a["staff_id"], a["role"]) for a in assignments
        ]
        for staff_id, role in proposed_roles:
            try:
                await rule.check(
                    self.db,
                    project_id=project_id,
                    staff_id=staff_id,
                    new_role=role,
                    proposed_roles=proposed_roles,
                )
            except SodViolation as exc:
                # 冒泡给 router 层转成 403/409
                raise exc

        # 软删除现有委派
        await self.db.execute(
            sa.update(ProjectAssignment)
            .where(
                ProjectAssignment.project_id == project_id,
                ProjectAssignment.is_deleted == False,  # noqa
            )
            .values(is_deleted=True, deleted_at=now)
        )

        # 插入新委派
        created = []
        for a in assignments:
            pa = ProjectAssignment(
                project_id=project_id,
                staff_id=a["staff_id"],
                role=a["role"],
                assigned_cycles=a.get("assigned_cycles"),
                assigned_at=now,
                assigned_by=assigned_by,
            )
            self.db.add(pa)
            created.append(pa)

        await self.db.flush()

        # 自动同步 project_users 表（解决委派与权限脱节问题）：按角色映射精确写入，可升可降
        changes = await self._sync_project_users(project_id, created)
        if changes:
            logger.info(
                "save_assignments: project=%s, member rows changed (%d): %s",
                project_id, len(changes), "; ".join(c.describe() for c in changes),
            )

        # procedure-delegation-visibility-isolation Task 7 / Req 14.20：
        # 项目成员/角色变更必须在同一事务内持久递增 policy epoch 并写 invalidation outbox
        # （不能提交后 best-effort 才失效）；随 router 单次 commit 原子生效。
        from app.services.wp_visibility.delegation_transaction import (
            DelegationTransactionService,
        )

        await DelegationTransactionService(self.db).bump_policy_epoch(
            project_id,
            "membership",
            actor_user_id=assigned_by,
            detail={"kind": "assignment", "count": len(created)},
        )

        # 发送通知给被委派人员
        await self._send_assignment_notifications(project_id, created)

        # 发布 SSE 通知前端（纯广播，不触发任何 handler）。
        # 🔴 修复前这里复用 EventType.DATA_IMPORTED（year=None）冒充「数据导入」：
        #    DATA_IMPORTED 有 7 个订阅者，其中 5 个不看 year 直接按项目全量执行 ——
        #    全项目底稿 prefill_stale=True、地址库/报表 Redis/程序表缓存全清；
        #    且发布在 router commit 之前（debounce 窗口内若 commit 失败则是幽灵事件）。
        #    委派只改人员与权限，不改任何账表数据，不应触碰数据链。
        #    前端只需「委派已变」这一信号，走 broadcast_raw（不入 handler 链）。
        try:
            from app.services.event_bus import event_bus
            event_bus.broadcast_raw(
                "workpaper.assigned",
                {"project_id": str(project_id), "kind": "assignment", "count": len(created)},
            )
        except Exception:
            pass  # SSE 推送失败不阻断主流程

        return created

    async def _send_assignment_notifications(
        self, project_id: UUID, assignments: list[ProjectAssignment]
    ) -> None:
        """给被委派人员发送通知"""
        # 获取项目名称
        proj = (await self.db.execute(
            sa.select(Project.name).where(Project.id == project_id)
        )).scalar_one_or_none()
        project_name = proj or "未知项目"

        for pa in assignments:
            # 查找人员关联的 user_id
            staff = (await self.db.execute(
                sa.select(StaffMember.user_id, StaffMember.name)
                .where(StaffMember.id == pa.staff_id)
            )).one_or_none()

            if staff and staff.user_id:
                role_map = {
                    "signing_partner": "签字合伙人",
                    "manager": "项目经理",
                    "auditor": "审计员",
                    "qc": "质控人员",
                    "eqcr": "独立复核合伙人",  # R5 任务 2
                }
                role_cn = role_map.get(pa.role, pa.role)
                cycles = ", ".join(pa.assigned_cycles) if pa.assigned_cycles else "全部"

                notif = Notification(
                    recipient_id=staff.user_id,
                    message_type=ASSIGNMENT_CREATED,
                    title=f"您已被委派到项目「{project_name}」",
                    content=f"角色：{role_cn}，负责循环：{cycles}。点击前往填报工时：/work-hours",
                    related_object_type="project",
                    related_object_id=project_id,
                )
                self.db.add(notif)

    async def _sync_project_users(
        self, project_id: UUID, assignments: list[ProjectAssignment]
    ) -> list[MemberChange]:
        """委派同步：把本批委派涉及的用户在本项目的成员行写成角色映射给出的值（design §4.3）。

        - 人员库记录已删除或未关联登录用户的委派跳过（D4、需求 3.9），委派本身照常保存。
        - 同一用户经多份人员库记录出现的委派合并后经 :func:`resolve_member_mapping` 得一组取值
          （EQCR 别名强制 (partner, review)，否则取最高级别、项目角色按固定先后），与委派先后顺序无关（需求 3.3、3.8）。
        - 没有未删除成员行则新建（已删除的行不查不改，需求 3.1）；有则改写项目角色与级别，可升可降，
          全局角色不影响；循环范围、科目范围、有效期不动（需求 3.2）。
        - 只查批次内用户在本项目的未删除成员行：批次外用户与其他项目的成员行不查不改（需求 3.4）。
        - 不读写任何 ``perm:*`` 键（权限缓存已移除，design D3 / D12）；只 flush、不 commit。

        返回 :class:`MemberChange` 列表（新建与取值有变的行），只用于 info 日志与测试断言。
        """
        # 调用方传入的 staff_id 可能是 UUID 或其字符串形式，统一成 UUID 再与库里的人员库记录比对
        pairs = [(UUID(str(pa.staff_id)), pa.role) for pa in assignments]
        if not pairs:
            return []
        linked: dict[UUID, UUID] = dict((await self.db.execute(
            sa.select(StaffMember.id, StaffMember.user_id).where(
                StaffMember.id.in_(sorted({staff_id for staff_id, _ in pairs}, key=str)),
                StaffMember.is_deleted == False,  # noqa: E712
                StaffMember.user_id.is_not(None),
            )
        )).all())
        roles_by_user: dict[UUID, list[str]] = defaultdict(list)
        for staff_id, role in pairs:
            user_id = linked.get(staff_id)
            if user_id is not None:  # 多份人员库记录关联同一用户 ⇒ 合并（需求 3.8）
                roles_by_user[user_id].append(role)

        changes: list[MemberChange] = []
        for user_id in sorted(roles_by_user, key=str):  # 处理顺序与委派先后无关
            role, level = resolve_member_mapping(roles_by_user[user_id])
            row = (await self.db.execute(
                sa.select(ProjectUser).where(
                    ProjectUser.project_id == project_id,
                    ProjectUser.user_id == user_id,
                    ProjectUser.is_deleted == False,  # noqa: E712
                )
            )).scalar_one_or_none()
            if row is None:
                self.db.add(ProjectUser(
                    project_id=project_id, user_id=user_id, role=role, permission_level=level,
                ))
                changes.append(MemberChange(user_id, None, (role, level)))
            elif (row.role, row.permission_level) != (role, level):
                changes.append(MemberChange(user_id, (row.role, row.permission_level), (role, level)))
                row.role, row.permission_level = role, level

        await self.db.flush()
        return changes

    async def get_my_assignments(self, user_id: UUID) -> list[dict]:
        """获取当前用户被委派的项目列表"""
        q = (
            sa.select(
                ProjectAssignment,
                Project.name.label("project_name"),
                Project.client_name,
                Project.status.label("project_status"),
            )
            .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
            .join(Project, ProjectAssignment.project_id == Project.id)
            .where(
                StaffMember.user_id == user_id,
                ProjectAssignment.is_deleted == False,  # noqa
                Project.is_deleted == False,  # noqa
            )
            .order_by(ProjectAssignment.assigned_at.desc())
        )
        rows = (await self.db.execute(q)).all()
        return [
            {
                "project_id": str(row[0].project_id),
                "project_name": row.project_name,
                "client_name": row.client_name,
                "project_status": row.project_status,
                "role": row[0].role,
                "assigned_cycles": row[0].assigned_cycles,
                "assigned_at": str(row[0].assigned_at) if row[0].assigned_at else None,
            }
            for row in rows
        ]
