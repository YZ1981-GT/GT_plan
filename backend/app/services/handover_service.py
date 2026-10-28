"""人员交接服务 — Round 2 需求 10

handover_service.execute 同事务：
1. ProjectAssignment 软删除 from_staff + 新增 to_staff
2. 底稿：编制人逐张走底稿主编委派事务（已裁 / 在回收站跳过，带交接理由扩大接收人可见范围），复核人直写
3. IssueTicket.owner_id 批量 UPDATE
4. 写 HandoverRecord 汇总
5. 调 audit_logger_enhanced.log_action(action_type='staff_handover')

resignation 时同步标记 IndependenceDeclaration.status='superseded_by_handover'

底稿编制人 / 复核人、工单负责人、独立性声明人、通知收件人都存 **用户 id**，按人员 → 用户换算后匹配与写入
（spec procedure-trim-generation-delegation-chain 任务 12；原实现直接用人员 id，真实数据从未命中）。

风险缓解：分批执行（每批 100 条），失败重试从上次断点续跑。
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.handover_models import HandoverRecord, HandoverReasonCode, HandoverScope
from app.models.independence_models import IndependenceDeclaration
from app.models.phase15_models import IssueTicket
from app.models.staff_models import ProjectAssignment
from app.models.workpaper_models import WorkingPaper
from app.services.audit_logger_enhanced import audit_logger
from app.services.notification_service import NotificationService
from app.services.notification_types import NOTIFICATION_META

logger = logging.getLogger(__name__)

# 分批大小
BATCH_SIZE = 100

# 交接通知类型
HANDOVER_RECEIVED = "handover_received"

# 交接时随人走的未关闭工单状态
_OPEN_ISSUE_STATUSES = ("open", "in_fix", "pending_recheck")
_NO_TARGET_USER = "接收人没有关联可登录的用户账号，不能接收底稿或工单"


class HandoverService:
    """人员交接执行器"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.notification_service = NotificationService(db)

    async def execute(
        self,
        from_staff_id: uuid.UUID,
        to_staff_id: uuid.UUID,
        scope: str,
        project_ids: list[uuid.UUID] | None,
        reason_code: str,
        reason_detail: str | None,
        effective_date: date,
        executed_by: uuid.UUID,
    ) -> dict[str, Any]:
        """执行交接 — 同事务批量迁移底稿/工单/委派。

        Returns:
            交接结果摘要 dict
        """
        # 验证 scope
        if scope == "by_project" and not project_ids:
            raise ValueError("scope='by_project' 时必须提供 project_ids")

        # 构建项目过滤条件
        project_filter = self._build_project_filter(scope, project_ids, from_staff_id)

        # 交接人 / 接收人的用户账号：底稿编制人与复核人、工单负责人、独立性声明人、通知收件人存的都是用户 id
        # （外键 users）。原实现直接拿人员 id 匹配与写入 —— 真实数据里人员 id ≠ 用户 id，从未命中，写入还会撞外键
        # （spec procedure-trim-generation-delegation-chain 任务 12；测试夹具里两者恰好相同，所以一直是绿的）
        from_user = await self._staff_user(from_staff_id)
        to_user = await self._staff_user(to_staff_id)

        # 1. ProjectAssignment 软删除 from_staff + 新增 to_staff（先于底稿：底稿主编委派要求接收人
        #    在该项目有团队分配）
        assignments_moved = await self._transfer_assignments(
            from_staff_id, to_staff_id, project_filter
        )

        # 2. 底稿：编制人走底稿主编委派事务，复核人直写
        wp_moved = await self._transfer_workpapers(
            from_user, to_user, to_staff_id, project_filter,
            actor_user_id=executed_by,
            reason=f"人员交接（{reason_code}）{('：' + reason_detail) if reason_detail else ''}",
        )

        # 3. 批量更新 IssueTicket.owner_id
        issues_moved = await self._transfer_issues(from_user, to_user, project_filter)

        # 4. 写 HandoverRecord 汇总
        record = HandoverRecord(
            id=uuid.uuid4(),
            from_staff_id=from_staff_id,
            to_staff_id=to_staff_id,
            scope=scope,
            project_ids=[str(pid) for pid in project_ids] if project_ids else None,
            reason_code=reason_code,
            reason_detail=reason_detail,
            effective_date=effective_date,
            workpapers_moved=wp_moved,
            issues_moved=issues_moved,
            assignments_moved=assignments_moved,
            executed_by=executed_by,
            executed_at=datetime.now(timezone.utc),
        )
        self.db.add(record)

        # 5. 调 audit_logger_enhanced.log_action(action_type='staff_handover')
        await audit_logger.log_action(
            user_id=executed_by,
            action="staff_handover",
            object_type="handover_record",
            object_id=record.id,
            project_id=None,
            details={
                "from_staff_id": str(from_staff_id),
                "to_staff_id": str(to_staff_id),
                "scope": scope,
                "project_ids": [str(pid) for pid in project_ids] if project_ids else None,
                "reason_code": reason_code,
                "reason_detail": reason_detail,
                "effective_date": str(effective_date),
                "workpapers_moved": wp_moved,
                "issues_moved": issues_moved,
                "assignments_moved": assignments_moved,
            },
        )

        # 6. resignation 时标记 IndependenceDeclaration.status='superseded_by_handover'
        independence_updated = 0
        if reason_code == HandoverReasonCode.resignation.value and from_user is not None:
            independence_updated = await self._supersede_independence_declarations(from_user)

        # 7. 发通知给新负责人（没有用户账号就无从通知）
        if to_user is not None:
            await self._send_handover_notification(
                to_user_id=to_user,
                from_staff_id=from_staff_id,
                record=record,
            )

        await self.db.flush()

        return {
            "handover_record_id": str(record.id),
            "workpapers_moved": wp_moved,
            "issues_moved": issues_moved,
            "assignments_moved": assignments_moved,
            "independence_superseded": independence_updated,
        }

    def _build_project_filter(
        self,
        scope: str,
        project_ids: list[uuid.UUID] | None,
        from_staff_id: uuid.UUID,
    ) -> list[uuid.UUID] | None:
        """构建项目 ID 过滤列表。

        scope='all' 返回 None（不限项目）
        scope='by_project' 返回指定的 project_ids
        """
        if scope == HandoverScope.by_project.value and project_ids:
            return project_ids
        return None

    async def _staff_user(self, staff_id: uuid.UUID) -> uuid.UUID | None:
        from app.models.staff_models import StaffMember

        return (await self.db.execute(
            sa.select(StaffMember.user_id).where(StaffMember.id == staff_id)
        )).scalar_one_or_none()

    async def _transfer_workpapers(
        self,
        from_user: uuid.UUID | None,
        to_user: uuid.UUID | None,
        to_staff_id: uuid.UUID,
        project_ids: list[uuid.UUID] | None,
        *,
        actor_user_id: uuid.UUID,
        reason: str,
    ) -> int:
        """转移底稿编制人与复核人（两列存用户 id），返回「编制人转移数 + 复核人转移数」。

        编制人逐张走底稿主编委派事务（交接即授权：带交接理由扩大接收人可见范围；已裁 / 在回收站的跳过；
        接收人不是项目成员 ⇒ ``DelegationError``，整次交接回滚）；复核人仍直写。
        """
        from app.services.wp_visibility.lead_delegation_entry import delegate_workpaper_leads

        if from_user is None:
            return 0  # 交接人没有用户账号 ⇒ 名下不会有底稿
        conds = [
            WorkingPaper.is_deleted == False,  # noqa: E712
            sa.or_(WorkingPaper.assigned_to == from_user, WorkingPaper.reviewer == from_user),
        ]
        if project_ids:
            conds.append(WorkingPaper.project_id.in_(project_ids))
        rows = (await self.db.execute(
            sa.select(WorkingPaper.id, WorkingPaper.project_id, WorkingPaper.assigned_to, WorkingPaper.reviewer)
            .where(*conds)
        )).all()
        if rows and to_user is None:
            raise ValueError(_NO_TARGET_USER)

        by_project: dict[uuid.UUID, list[uuid.UUID]] = {}
        for r in rows:
            if r.assigned_to == from_user:
                by_project.setdefault(r.project_id, []).append(r.id)
        leads_moved = 0
        for pid, wp_ids in by_project.items():
            outcome = await delegate_workpaper_leads(
                self.db, pid, [(w, to_staff_id) for w in wp_ids], actor_user_id=actor_user_id,
                expand_scope=True, scope_reason=reason, skip_trimmed=True,
            )
            leads_moved += len(outcome.updated)

        reviewer_ids = [r.id for r in rows if r.reviewer == from_user]
        if reviewer_ids:
            await self.db.execute(
                sa.update(WorkingPaper).where(WorkingPaper.id.in_(reviewer_ids)).values(reviewer=to_user)
            )

        logger.info(
            "[HANDOVER] workpapers transferred: leads=%d reviewers=%d (from=%s to=%s)",
            leads_moved, len(reviewer_ids), from_user, to_user,
        )
        return leads_moved + len(reviewer_ids)

    async def _transfer_issues(
        self,
        from_user: uuid.UUID | None,
        to_user: uuid.UUID | None,
        project_ids: list[uuid.UUID] | None,
    ) -> int:
        """批量转移未关闭工单的 owner_id（存用户 id）。"""
        if from_user is None:
            return 0
        issue_filter = sa.and_(
            IssueTicket.owner_id == from_user,
            IssueTicket.status.in_(_OPEN_ISSUE_STATUSES),
        )
        if project_ids:
            issue_filter = sa.and_(
                issue_filter,
                IssueTicket.project_id.in_(project_ids),
            )
        if to_user is None:
            pending = (await self.db.execute(
                sa.select(sa.func.count()).select_from(IssueTicket).where(issue_filter)
            )).scalar() or 0
            if pending:
                raise ValueError(_NO_TARGET_USER)
            return 0

        result = await self.db.execute(
            sa.update(IssueTicket)
            .where(issue_filter)
            .values(owner_id=to_user)
        )
        moved = result.rowcount

        logger.info(
            "[HANDOVER] issues transferred: %d (from=%s to=%s)",
            moved, from_user, to_user,
        )
        return moved

    async def _transfer_assignments(
        self,
        from_staff_id: uuid.UUID,
        to_staff_id: uuid.UUID,
        project_ids: list[uuid.UUID] | None,
    ) -> int:
        """转移项目委派：软删除 from_staff 的委派 + 新增 to_staff 的委派。"""
        # 查找 from_staff 的活跃委派
        assignment_filter = sa.and_(
            ProjectAssignment.staff_id == from_staff_id,
            ProjectAssignment.is_deleted == False,
        )
        if project_ids:
            assignment_filter = sa.and_(
                assignment_filter,
                ProjectAssignment.project_id.in_(project_ids),
            )

        result = await self.db.execute(
            sa.select(ProjectAssignment).where(assignment_filter)
        )
        old_assignments = result.scalars().all()

        moved = 0
        for old_assign in old_assignments:
            # 软删除旧委派
            old_assign.soft_delete()

            # 检查 to_staff 是否已有该项目的委派
            existing = await self.db.execute(
                sa.select(ProjectAssignment).where(
                    ProjectAssignment.project_id == old_assign.project_id,
                    ProjectAssignment.staff_id == to_staff_id,
                    ProjectAssignment.is_deleted == False,
                )
            )
            existing_assign = existing.scalar_one_or_none()

            if not existing_assign:
                # 新增 to_staff 的委派
                new_assign = ProjectAssignment(
                    id=uuid.uuid4(),
                    project_id=old_assign.project_id,
                    staff_id=to_staff_id,
                    role=old_assign.role,
                    assigned_cycles=old_assign.assigned_cycles,
                    assigned_at=datetime.now(timezone.utc),
                    assigned_by=old_assign.assigned_by,
                )
                self.db.add(new_assign)

            moved += 1

        logger.info(
            "[HANDOVER] assignments transferred: %d (from=%s to=%s)",
            moved, from_staff_id, to_staff_id,
        )
        return moved

    async def _supersede_independence_declarations(
        self,
        from_user: uuid.UUID,
    ) -> int:
        """resignation 时标记未完成的独立性声明为 superseded_by_handover（声明人列存用户 id）。"""
        # 只标记非终态的声明
        active_statuses = ["draft", "submitted", "pending_conflict_review"]

        result = await self.db.execute(
            sa.update(IndependenceDeclaration)
            .where(
                IndependenceDeclaration.declarant_id == from_user,
                IndependenceDeclaration.status.in_(active_statuses),
            )
            .values(status="superseded_by_handover")
        )
        updated = result.rowcount

        if updated > 0:
            logger.info(
                "[HANDOVER] independence declarations superseded: %d (user=%s)",
                updated, from_user,
            )
        return updated

    async def _send_handover_notification(
        self,
        to_user_id: uuid.UUID,
        from_staff_id: uuid.UUID,
        record: HandoverRecord,
    ) -> None:
        """发送交接通知给新负责人。"""
        title = "工作交接通知"
        content = (
            f"有 {record.workpapers_moved} 张底稿、"
            f"{record.issues_moved} 张工单、"
            f"{record.assignments_moved} 个项目委派已转交给您，"
            f"请及时查看。"
        )

        await self.notification_service.send_notification(
            user_id=to_user_id,
            notification_type=HANDOVER_RECEIVED,
            title=title,
            content=content,
            metadata={
                "object_type": "handover_record",
                "object_id": str(record.id),
                "from_staff_id": str(from_staff_id),
                "workpapers_moved": record.workpapers_moved,
                "issues_moved": record.issues_moved,
                "assignments_moved": record.assignments_moved,
            },
        )

    async def get_handover_preview(
        self,
        from_staff_id: uuid.UUID,
        scope: str,
        project_ids: list[uuid.UUID] | None,
    ) -> dict[str, int]:
        """预览交接将影响的数据量（不执行实际变更）。"""
        project_filter = self._build_project_filter(scope, project_ids, from_staff_id)

        # 统计底稿（编制人 / 复核人列存用户 id，与执行同口径按人员 → 用户换算；无关联用户 ⇒ 0，
        # 不能拿 None 比较 —— SQLAlchemy 会渲染成 IS NULL，把全部未分配底稿算进来）
        from_user = await self._staff_user(from_staff_id)
        wp_count = 0
        if from_user is not None:
            wp_filter = sa.and_(
                WorkingPaper.is_deleted == False,
                sa.or_(
                    WorkingPaper.assigned_to == from_user,
                    WorkingPaper.reviewer == from_user,
                ),
            )
            if project_filter:
                wp_filter = sa.and_(wp_filter, WorkingPaper.project_id.in_(project_filter))
            wp_count = (await self.db.execute(
                sa.select(sa.func.count()).select_from(WorkingPaper).where(wp_filter)
            )).scalar() or 0

        # 统计工单（负责人列存用户 id）
        issue_count = 0
        if from_user is not None:
            issue_filter = sa.and_(
                IssueTicket.owner_id == from_user,
                IssueTicket.status.in_(_OPEN_ISSUE_STATUSES),
            )
            if project_filter:
                issue_filter = sa.and_(
                    issue_filter, IssueTicket.project_id.in_(project_filter)
                )
            issue_count = (await self.db.execute(
                sa.select(sa.func.count()).select_from(IssueTicket).where(issue_filter)
            )).scalar() or 0

        # 统计委派
        assign_filter = sa.and_(
            ProjectAssignment.staff_id == from_staff_id,
            ProjectAssignment.is_deleted == False,
        )
        if project_filter:
            assign_filter = sa.and_(
                assign_filter, ProjectAssignment.project_id.in_(project_filter)
            )

        assign_result = await self.db.execute(
            sa.select(sa.func.count())
            .select_from(ProjectAssignment)
            .where(assign_filter)
        )
        assign_count = assign_result.scalar() or 0

        return {
            "workpapers": wp_count,
            "issues": issue_count,
            "assignments": assign_count,
        }
