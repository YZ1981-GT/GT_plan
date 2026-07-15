"""程序行一级复核服务（Task 13）

Feature: procedure-delegation-notification
需求：5.4-5.8（reviewer 回退与职责边界）、8.1-8.8（一级复核 / IssueTicket / 历史参与者访问）
Design：C9（ProcedureReviewService）、D6（程序行只做操作复核）、F5（ProcedureReviewPanel）
Properties：P17（reviewer fallback 决定性）、P18（一级复核不改变高阶复核）、
            P25（IssueTicket 关闭门槛）、P26（reviewer 转派历史可读、动作不可用）

职责边界（Design D6 / 需求 5.7-5.8）：
- 本服务 **仅** 处理程序行 Operation_Reviewer 的一级复核。任务 ``reviewed`` 只结束程序行一级
  复核，**绝不** 触碰底稿/项目层 partner / QC / EQCR 高阶复核状态或门槛（P18）。
- 状态机（submitted→changes_requested / submitted→reviewed）唯一入口仍是
  ``ProcedureTaskTransitionService``；本服务只做 reviewer 解析、ReviewConversation 关联、
  IssueTicket 生命周期、消息与只读视图。**不直接写** workflow_status/applicability_status
  （否则触发架构守卫 procedure-state-transition-bypass）。

对话与问题单（需求 8.1-8.4）：
- 用 ``ReviewConversation(related_object_type='procedure_row_task', related_object_id=task_id,
  cell_ref='proc:{sheet_key}:{definition_key}')`` 关联程序行讨论；**不** 把 task_id 塞入
  ``ReviewThread.wp_id``，**不** 创建缺 conversation_id 的 ReviewMessage。
- 每次 changes_requested 创建或复用
  ``IssueTicket(source='review_comment', source_ref_id=task_id, conversation_id=...)``
  作为正式未解决项；review 前该 task 关联的全部 review_comment IssueTicket 必须 closed（否则 409）。

reviewer fallback（需求 5.4-5.5 / P17）严格依次：
  1. 显式 ``reviewer_staff_id``；
  2. ``WorkingPaper.reviewer`` 或 ``WpIndex.reviewer``（users.id）映射到本项目 **唯一** active
     StaffMember；
  3. 本项目 **唯一** primary manager（active ProjectAssignment role=manager）；
  4. 否则 ``reviewer_missing``。
映射不存在/跨项目/inactive/重复不唯一 → 该层 fail-closed（不任取第一条），进入下一层。

约定：service 只 flush 不 commit；router 显式 commit。history/outbox 由 TransitionService 同事务写。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase10_models import ReviewConversation, ReviewMessage
from app.models.phase15_models import IssueTicket
from app.models.procedure_models import ProcedureRowTask
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import WorkingPaper, WpIndex

logger = logging.getLogger(__name__)

# ReviewConversation.related_object_type 常量（需求 8.1）。
CONVERSATION_OBJECT_TYPE = "procedure_row_task"
# IssueTicket.source 常量（需求 8.3；phase15 IssueTicket.source 枚举已含 review_comment）。
ISSUE_SOURCE_REVIEW_COMMENT = "review_comment"
# 只有 closed 视为"已关闭"（需求 8.4）。
ISSUE_STATUS_CLOSED = "closed"
# reviewer 缺失哨兵（需求 5.6）。
REVIEWER_MISSING = "reviewer_missing"

# 文本 trim 后长度约束（需求 8.8）。
_TEXT_MIN = 1
_TEXT_MAX = 5000


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProcedureReviewService:
    """程序行一级复核（reviewer 解析 / 对话 / IssueTicket / 消息 / 只读视图）。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================================================================
    # reviewer fallback（需求 5.4-5.5 / P17）
    # ==================================================================

    async def _map_user_to_project_staff(
        self, user_id: UUID | None, project_id: UUID
    ) -> UUID | None:
        """把 users.id 映射到本项目 **唯一** active StaffMember.id。

        - StaffMember active（未软删）且 user_id 匹配；
        - 且在本项目有 active ProjectAssignment；
        - 结果必须唯一，否则 fail-closed 返回 None（不任取第一条，需求 5.5）。
        """
        if user_id is None:
            return None
        rows = (
            await self.db.execute(
                sa.select(StaffMember.id)
                .join(ProjectAssignment, ProjectAssignment.staff_id == StaffMember.id)
                .where(
                    StaffMember.user_id == user_id,
                    StaffMember.is_deleted == sa.false(),
                    ProjectAssignment.project_id == project_id,
                    ProjectAssignment.is_deleted == sa.false(),
                )
                .distinct()
            )
        ).scalars().all()
        return rows[0] if len(rows) == 1 else None

    async def _unique_primary_manager_staff(self, project_id: UUID) -> UUID | None:
        """本项目 **唯一** primary manager（active ProjectAssignment role=manager）→ staff_id。

        0 或 >1 个 manager → None（fail-closed，不任取第一条）。要求对应 StaffMember active。
        """
        rows = (
            await self.db.execute(
                sa.select(StaffMember.id)
                .join(ProjectAssignment, ProjectAssignment.staff_id == StaffMember.id)
                .where(
                    ProjectAssignment.project_id == project_id,
                    ProjectAssignment.is_deleted == sa.false(),
                    sa.func.lower(ProjectAssignment.role) == "manager",
                    StaffMember.is_deleted == sa.false(),
                )
                .distinct()
            )
        ).scalars().all()
        return rows[0] if len(rows) == 1 else None

    async def resolve_reviewer(
        self, task: ProcedureRowTask
    ) -> tuple[UUID | None, str]:
        """决定性 reviewer 解析（返回 ``(staff_id, source)``）。

        source ∈ {explicit, wp_reviewer, wp_index_reviewer, primary_manager, reviewer_missing}。
        staff_id 为 None 当且仅当 source == reviewer_missing（需求 5.6）。纯读，无副作用。
        """
        # ① 显式 reviewer_staff_id（须仍 active）
        if task.reviewer_staff_id is not None:
            active = (
                await self.db.execute(
                    sa.select(StaffMember.id).where(
                        StaffMember.id == task.reviewer_staff_id,
                        StaffMember.is_deleted == sa.false(),
                    )
                )
            ).scalar_one_or_none()
            if active is not None:
                return task.reviewer_staff_id, "explicit"

        # ② WorkingPaper.reviewer → 本项目唯一 active staff
        if task.wp_id is not None:
            wp_reviewer = (
                await self.db.execute(
                    sa.select(WorkingPaper.reviewer).where(WorkingPaper.id == task.wp_id)
                )
            ).scalar_one_or_none()
            staff_id = await self._map_user_to_project_staff(wp_reviewer, task.project_id)
            if staff_id is not None:
                return staff_id, "wp_reviewer"

        # ③ WpIndex.reviewer → 本项目唯一 active staff
        wpi_reviewer = (
            await self.db.execute(
                sa.select(WpIndex.reviewer).where(WpIndex.id == task.wp_index_id)
            )
        ).scalar_one_or_none()
        staff_id = await self._map_user_to_project_staff(wpi_reviewer, task.project_id)
        if staff_id is not None:
            return staff_id, "wp_index_reviewer"

        # ④ 本项目唯一 primary manager
        mgr_staff = await self._unique_primary_manager_staff(task.project_id)
        if mgr_staff is not None:
            return mgr_staff, "primary_manager"

        # ⑤ reviewer_missing（需求 5.6：阻止 review，向 Delegator 产生通知意图）
        return None, REVIEWER_MISSING

    # ==================================================================
    # ReviewConversation 关联（需求 8.1-8.2）
    # ==================================================================

    def _cell_ref(self, task: ProcedureRowTask) -> str:
        return f"proc:{task.sheet_key}:{task.definition_key}"

    async def _staff_user_id(self, staff_id: UUID | None) -> UUID | None:
        if staff_id is None:
            return None
        return (
            await self.db.execute(
                sa.select(StaffMember.user_id).where(
                    StaffMember.id == staff_id,
                    StaffMember.is_deleted == sa.false(),
                    StaffMember.user_id.isnot(None),
                )
            )
        ).scalar_one_or_none()

    async def get_conversation(self, task_id: UUID) -> ReviewConversation | None:
        """反查该 task 的程序行 ReviewConversation（纯读，可能为 None）。"""
        return (
            await self.db.execute(
                sa.select(ReviewConversation)
                .where(
                    ReviewConversation.related_object_type == CONVERSATION_OBJECT_TYPE,
                    ReviewConversation.related_object_id == task_id,
                    ReviewConversation.is_deleted == sa.false(),
                )
                .order_by(ReviewConversation.created_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def ensure_conversation(
        self,
        task: ProcedureRowTask,
        *,
        actor_user_id: UUID | None,
    ) -> ReviewConversation:
        """获取或创建程序行 ReviewConversation（related_object_type=procedure_row_task）。

        initiator = 操作复核人 user（缺失回退 actor）；target = 执行人 user（缺失回退 actor）。
        绝不把 task_id 塞入 ReviewThread.wp_id。
        """
        conv = await self.get_conversation(task.id)
        if conv is not None:
            return conv

        reviewer_user = await self._staff_user_id(task.reviewer_staff_id)
        assignee_user = await self._staff_user_id(task.assignee_staff_id)
        initiator = reviewer_user or actor_user_id or assignee_user
        target = assignee_user or actor_user_id or reviewer_user
        if initiator is None or target is None:
            raise HTTPException(status_code=409, detail="无法建立复核对话：缺少有效参与者")

        conv = ReviewConversation(
            project_id=task.project_id,
            initiator_id=initiator,
            target_id=target,
            related_object_type=CONVERSATION_OBJECT_TYPE,
            related_object_id=task.id,
            cell_ref=self._cell_ref(task),
            title=f"程序行一级复核：{task.wp_code or ''} {task.program_no or ''}".strip(),
            status="open",
        )
        self.db.add(conv)
        await self.db.flush()
        return conv

    # ==================================================================
    # IssueTicket 生命周期（需求 8.3-8.4 / P25）
    # ==================================================================

    async def open_changes_requested_issue_count(self, task_id: UUID) -> int:
        """该 task 关联的、**未关闭** 的 review_comment IssueTicket 数（review 门槛，需求 8.4）。"""
        return (
            await self.db.execute(
                sa.select(sa.func.count()).select_from(IssueTicket).where(
                    IssueTicket.source == ISSUE_SOURCE_REVIEW_COMMENT,
                    IssueTicket.source_ref_id == task_id,
                    IssueTicket.status != ISSUE_STATUS_CLOSED,
                )
            )
        ).scalar() or 0

    async def list_task_issues(self, task_id: UUID) -> list[IssueTicket]:
        """列出该 task 的全部 review_comment IssueTicket（稳定排序，纯读）。"""
        return list(
            (
                await self.db.execute(
                    sa.select(IssueTicket)
                    .where(
                        IssueTicket.source == ISSUE_SOURCE_REVIEW_COMMENT,
                        IssueTicket.source_ref_id == task_id,
                    )
                    .order_by(IssueTicket.created_at.asc(), IssueTicket.id.asc())
                )
            ).scalars().all()
        )

    async def create_or_reuse_issue_ticket(
        self,
        task: ProcedureRowTask,
        *,
        actor_user_id: UUID | None,
        reason: str,
        conversation_id: UUID,
        request_id: str | None = None,
    ) -> IssueTicket:
        """changes_requested 创建/复用正式未解决项（需求 8.3）。

        复用规则：若该 task 已存在 **未关闭** 的 review_comment IssueTicket，则复用（同一返修轮内
        不重复开单）；否则新建。owner = 执行人 user（缺失回退 actor）。
        """
        r = (reason or "").strip()
        if not (_TEXT_MIN <= len(r) <= _TEXT_MAX):
            raise HTTPException(status_code=422, detail="退回原因长度须为 1–5000 字符")

        existing = (
            await self.db.execute(
                sa.select(IssueTicket)
                .where(
                    IssueTicket.source == ISSUE_SOURCE_REVIEW_COMMENT,
                    IssueTicket.source_ref_id == task.id,
                    IssueTicket.status != ISSUE_STATUS_CLOSED,
                )
                .order_by(IssueTicket.created_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        owner_user = await self._staff_user_id(task.assignee_staff_id) or actor_user_id
        if owner_user is None:
            raise HTTPException(status_code=409, detail="无法创建问题单：缺少责任人")

        ticket = IssueTicket(
            project_id=task.project_id,
            wp_id=task.wp_id,
            conversation_id=conversation_id,
            source=ISSUE_SOURCE_REVIEW_COMMENT,
            source_ref_id=task.id,
            severity="major",
            category="procedure_review",
            title=r[:200],
            description=r,
            owner_id=owner_user,
            status="open",
            reason_code="procedure_review_changes_requested",
            trace_id=(request_id or str(uuid.uuid4()))[:64],
        )
        self.db.add(ticket)
        await self.db.flush()
        return ticket

    async def close_issue(
        self,
        task_id: UUID,
        issue_id: UUID,
        *,
        actor_user_id: UUID | None,
    ) -> IssueTicket:
        """关闭该 task 关联的 review_comment IssueTicket（需求 8.4 门槛的解除动作）。"""
        ticket = (
            await self.db.execute(
                sa.select(IssueTicket).where(
                    IssueTicket.id == issue_id,
                    IssueTicket.source == ISSUE_SOURCE_REVIEW_COMMENT,
                    IssueTicket.source_ref_id == task_id,
                )
            )
        ).scalar_one_or_none()
        if ticket is None:
            raise HTTPException(status_code=404, detail="问题单不存在或不属于该任务")
        if ticket.status != ISSUE_STATUS_CLOSED:
            ticket.status = ISSUE_STATUS_CLOSED
            ticket.closed_at = _utcnow()
            ticket.updated_at = _utcnow()
            await self.db.flush()
        return ticket

    # ==================================================================
    # 消息（需求 8.7-8.8）
    # ==================================================================

    async def add_message(
        self,
        task: ProcedureRowTask,
        *,
        sender_user_id: UUID,
        content: str,
        actor_user_id: UUID | None = None,
    ) -> dict:
        """在程序行对话追加消息（须绑定 conversation_id；不创建孤立 ReviewMessage）。

        文本 trim 后 1–5000 字符（需求 8.8）。发送后向当前相关参与者产生通知意图（SSE + 站内），
        历史只读参与者不因历史访问自动扩大收件范围（需求 8.7）。
        """
        text = (content or "").strip()
        if not (_TEXT_MIN <= len(text) <= _TEXT_MAX):
            raise HTTPException(status_code=422, detail="消息内容 trim 后须为 1–5000 字符")

        conv = await self.ensure_conversation(task, actor_user_id=actor_user_id or sender_user_id)
        msg = ReviewMessage(
            conversation_id=conv.id,
            sender_id=sender_user_id,
            content=text,
            message_type="text",
        )
        self.db.add(msg)
        await self.db.flush()

        await self._notify_current_participants(task, conv, sender_user_id, text)
        return self._msg_to_dict(msg)

    async def _notify_current_participants(
        self,
        task: ProcedureRowTask,
        conv: ReviewConversation,
        sender_user_id: UUID,
        preview: str,
    ) -> None:
        """通知当前相关参与者（assignee/reviewer 的归一 user，排除发送者）。

        历史只读参与者不在此自动收件（需求 8.7）。SSE 用 broadcast_raw；站内通知按参与者写。
        """
        recipients: set[UUID] = set()
        for sid in (task.assignee_staff_id, task.reviewer_staff_id):
            uid = await self._staff_user_id(sid)
            if uid is not None and uid != sender_user_id:
                recipients.add(uid)

        # 站内通知（metadata 驱动跳转，不从中文 content 解析路由）
        from app.models.core import Notification

        for uid in recipients:
            self.db.add(
                Notification(
                    recipient_id=uid,
                    recipient_user_id=uid,
                    message_type="procedure_review_message",
                    title="程序行复核有新消息",
                    content=preview[:200],
                    related_object_type=CONVERSATION_OBJECT_TYPE,
                    related_object_id=task.id,
                    notification_metadata={
                        "task_id": str(task.id),
                        "project_id": str(task.project_id),
                        "conversation_id": str(conv.id),
                        "sheet_key": task.sheet_key,
                        "definition_key": task.definition_key,
                    },
                )
            )
        if recipients:
            await self.db.flush()

        try:
            from app.services.event_bus import event_bus

            event_bus.broadcast_raw(
                "PROCEDURE_REVIEW_MESSAGE",
                {
                    "project_id": str(task.project_id),
                    "task_id": str(task.id),
                    "conversation_id": str(conv.id),
                    "sender_id": str(sender_user_id),
                    "preview": preview[:100],
                },
            )
        except Exception:  # SSE 失败不影响领域写
            pass

    # ==================================================================
    # reviewer_missing 通知意图（需求 5.6 / Task 11）
    # ==================================================================

    async def notify_reviewer_missing(
        self, task: ProcedureRowTask, *, actor_user_id: UUID | None = None
    ) -> int:
        """任务提交后若复核人不可解析，向有权限的 Delegator 产生可靠通知意图（Req 5.6）。

        - 仅当 ``resolve_reviewer`` 结果为 ``reviewer_missing`` 时产生（否则 no-op）。
        - 收件人 = 本项目全部 Delegator（partner/signing_partner/manager）归一化 user。
        - metadata 驱动跳转（不解析中文 content）；按 ``reviewer_missing:{task}:{assignment_version}``
          + recipient 去重（同一 assignment 重复提交不重复通知）。
        - 只 flush 不 commit；SSE 走 broadcast_raw（失败不影响领域写）。返回新增通知条数。
        """
        resolved, source = await self.resolve_reviewer(task)
        if resolved is not None or source != REVIEWER_MISSING:
            return 0

        from app.services.procedure_authorization import (
            list_project_delegator_user_ids,
        )

        try:
            recipients = await list_project_delegator_user_ids(self.db, task.project_id)
        except Exception:  # 解析异常不阻断领域写
            logger.warning("reviewer_missing 收件人解析失败 task=%s", task.id, exc_info=True)
            return 0
        if not recipients:
            return 0

        from app.models.core import Notification
        from app.services.notification_types import PROCEDURE_TASK_REVIEWER_MISSING

        event_id = f"reviewer_missing:{task.id}:{task.assignment_version}"
        metadata = {
            "kind": "reviewer_missing",
            "event_id": event_id,
            "task_id": str(task.id),
            "project_id": str(task.project_id),
            "wp_index_id": str(task.wp_index_id),
            "wp_id": str(task.wp_id) if task.wp_id else None,
            "sheet_key": task.sheet_key,
            "definition_key": task.definition_key,
        }
        added = 0
        for uid in recipients:
            # 幂等：同 (event_id, recipient) 已存在则跳过（与 uq_notifications_event_recipient 一致）
            exists = (
                await self.db.execute(
                    sa.select(Notification.id).where(
                        Notification.event_id == event_id,
                        Notification.recipient_user_id == uid,
                    )
                )
            ).first()
            if exists:
                continue
            self.db.add(
                Notification(
                    recipient_id=uid,
                    recipient_user_id=uid,
                    message_type=PROCEDURE_TASK_REVIEWER_MISSING,
                    title="程序任务缺少操作复核人",
                    content=None,
                    related_object_type=CONVERSATION_OBJECT_TYPE,
                    related_object_id=task.id,
                    event_id=event_id,
                    dedup_key=f"{event_id}:{uid}",
                    notification_metadata=metadata,
                )
            )
            added += 1
        if added:
            await self.db.flush()
            try:
                from app.services.event_bus import event_bus

                event_bus.broadcast_raw(
                    "procedure_task.event",
                    {
                        "project_id": str(task.project_id),
                        "event_id": event_id,
                        "event_type": "reviewer_missing",
                        "task_id": str(task.id),
                    },
                )
            except Exception:  # SSE 失败不影响领域写
                pass
        return added

    # ==================================================================
    # 只读视图（需求 8.8：消息/历史按 created_at,id 稳定排序）
    # ==================================================================

    async def get_conversation_view(self, task: ProcedureRowTask) -> dict:
        """程序行复核只读视图：对话 + 消息（稳定排序）+ 未解决问题单数 + 问题单列表。"""
        conv = await self.get_conversation(task.id)
        messages: list[dict] = []
        conv_dict = None
        if conv is not None:
            conv_dict = self._conv_to_dict(conv)
            rows = (
                await self.db.execute(
                    sa.select(ReviewMessage)
                    .where(ReviewMessage.conversation_id == conv.id)
                    .order_by(ReviewMessage.created_at.asc(), ReviewMessage.id.asc())
                )
            ).scalars().all()
            messages = [self._msg_to_dict(m) for m in rows]

        issues = await self.list_task_issues(task.id)
        open_count = sum(1 for i in issues if i.status != ISSUE_STATUS_CLOSED)
        return {
            "task_id": str(task.id),
            "cell_ref": self._cell_ref(task),
            "conversation": conv_dict,
            "messages": messages,
            "open_issue_count": open_count,
            "issues": [self._issue_to_dict(i) for i in issues],
        }

    # -- dict helpers ---------------------------------------------------

    def _conv_to_dict(self, c: ReviewConversation) -> dict:
        return {
            "id": str(c.id),
            "project_id": str(c.project_id),
            "initiator_id": str(c.initiator_id),
            "target_id": str(c.target_id),
            "related_object_type": c.related_object_type,
            "related_object_id": str(c.related_object_id) if c.related_object_id else None,
            "cell_ref": c.cell_ref,
            "status": c.status,
            "title": c.title,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }

    def _msg_to_dict(self, m: ReviewMessage) -> dict:
        return {
            "id": str(m.id),
            "conversation_id": str(m.conversation_id),
            "sender_id": str(m.sender_id),
            "content": m.content,
            "message_type": m.message_type,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }

    def _issue_to_dict(self, i: IssueTicket) -> dict:
        return {
            "id": str(i.id),
            "source": i.source,
            "source_ref_id": str(i.source_ref_id) if i.source_ref_id else None,
            "conversation_id": str(i.conversation_id) if i.conversation_id else None,
            "severity": i.severity,
            "category": i.category,
            "title": i.title,
            "status": i.status,
            "owner_id": str(i.owner_id) if i.owner_id else None,
            "created_at": i.created_at.isoformat() if i.created_at else None,
            "closed_at": i.closed_at.isoformat() if i.closed_at else None,
        }
