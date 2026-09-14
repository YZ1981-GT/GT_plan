"""调整分录协作接力服务 — AdjustmentCollaborationService

spec: adjustment-collaboration-and-propagation

以集中登记分录组 entry_group_id 为锚点的多人协作工作流：
  转派(assign) → 知晓(acknowledge) → 补充明细行(contribute) → 确认(confirm)
  旁支：退回(reject)；多轮：confirmed/rejected 后可再派（round 递增）。

协作是受控多人编辑通道：
  - contribute 直接重建分录组明细行（借贷平衡校验），append-only 事件记快照。
  - origin='workpaper' 分录组活跃协作期间由 sync 端锁定 re-sync 防覆盖（见
    AdjustmentSyncService + has_active_collaboration）。
  - 状态机白名单转换，非法转换 raise CollaborationError('INVALID_TRANSITION')。
  - 各节点经 NotificationService 推送（旁路失败仅 warning，不阻断状态转换）。
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    Adjustment,
    AdjustmentCollaboration,
    AdjustmentCollaborationEvent,
    AdjustmentEntry,
    AdjustmentType,
    ReviewStatus,
)
from app.models.audit_platform_schemas import (
    AdjustmentCollaborationResponse,
    AdjustmentSyncLineItem,
)
from app.services import notification_types as nt
from app.services.adjustment_service import AdjustmentService
from app.services.adjustment_sync_service import AdjustmentSyncService
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

# 活跃状态（协作锁生效 + 可继续推进）
ACTIVE_STATUSES: frozenset[str] = frozenset({"pending", "acknowledged", "contributed"})

# 状态机合法转换白名单：目标状态 → 允许的来源状态集合
_LEGAL_FROM: dict[str, frozenset[str]] = {
    "acknowledged": frozenset({"pending"}),
    "contributed": frozenset({"pending", "acknowledged", "contributed"}),
    "confirmed": frozenset({"contributed"}),
    "rejected": frozenset({"pending", "acknowledged", "contributed"}),
    "closed": frozenset({"pending", "acknowledged", "contributed", "confirmed", "rejected"}),
}


class CollaborationError(ValueError):
    """协作业务错误（携错误码供 router 转 4xx）。"""

    def __init__(self, code: str, message: str, detail: object | None = None):
        super().__init__(message)
        self.code = code
        self.detail = detail


async def has_active_collaboration(
    db: AsyncSession, project_id: UUID, entry_group_id: UUID
) -> bool:
    """供 sync 端调用：分录组是否存在活跃协作（协作锁判定）。"""
    q = sa.select(sa.func.count(AdjustmentCollaboration.id)).where(
        AdjustmentCollaboration.project_id == project_id,
        AdjustmentCollaboration.entry_group_id == entry_group_id,
        AdjustmentCollaboration.status.in_(list(ACTIVE_STATUSES)),
        AdjustmentCollaboration.is_deleted == sa.false(),
    )
    return bool((await db.execute(q)).scalar() or 0)


class AdjustmentCollaborationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._adj = AdjustmentService(db)
        self._notif = NotificationService(db)

    # ------------------------------------------------------------------
    # 转派 / 重派 / 新轮
    # ------------------------------------------------------------------
    async def assign(
        self,
        project_id: UUID,
        *,
        entry_group_id: UUID,
        assignee_id: UUID,
        initiator_id: UUID,
        year: int,
        note: str | None = None,
    ) -> AdjustmentCollaborationResponse:
        # 1. 分录组存在 + 非 approved + 取 source_ref
        group = await self._adj._get_group_rows(project_id, entry_group_id)
        if not group:
            raise CollaborationError("GROUP_NOT_FOUND", "分录组不存在或不属于该项目")
        head = group[0]
        if head.review_status == ReviewStatus.approved:
            raise CollaborationError(
                "APPROVED_LOCKED", "该分录组已复核通过，不可发起协作补充"
            )
        source_ref = head.source_ref

        # 2. 解析 assignee（前端 picker 传 staff_id 或 user_id）→ user_id，并校验项目成员
        assignee_id = await self._resolve_user_id(assignee_id)
        if not await self._is_project_member(project_id, assignee_id):
            raise CollaborationError(
                "NOT_PROJECT_MEMBER", "转派对象必须为该项目成员"
            )

        # 3. 活跃协作存在 → 重派；否则新建（round = 历史 max + 1）
        active = await self._get_active(project_id, entry_group_id)
        if active is not None:
            active.assignee_id = assignee_id
            active.initiator_id = initiator_id
            active.status = "pending"
            active.note = note
            active.rejection_reason = None
            collab = active
            event_type = "reassigned"
        else:
            next_round = await self._next_round(project_id, entry_group_id)
            collab = AdjustmentCollaboration(
                project_id=project_id,
                year=year,
                entry_group_id=entry_group_id,
                source_ref=source_ref,
                initiator_id=initiator_id,
                assignee_id=assignee_id,
                status="pending",
                round=next_round,
                note=note,
                created_by=initiator_id,
            )
            self.db.add(collab)
            event_type = "assigned"
        await self.db.flush()

        await self._add_event(collab.id, initiator_id, event_type, {"note": note, "round": collab.round})
        await self._notify(
            assignee_id, nt.ADJ_COLLAB_ASSIGNED,
            "调整分录协作转派",
            f"分录组 {head.adjustment_no or ''} 已转派给您补充，请知晓并补充明细后确认",
            entry_group_id, project_id,
        )
        return AdjustmentCollaborationResponse.model_validate(collab)

    # ------------------------------------------------------------------
    # 知晓
    # ------------------------------------------------------------------
    async def acknowledge(
        self, project_id: UUID, collaboration_id: UUID, actor_id: UUID
    ) -> AdjustmentCollaborationResponse:
        collab = await self._require(project_id, collaboration_id)
        self._require_assignee(collab, actor_id)
        self._guard_transition(collab.status, "acknowledged")
        collab.status = "acknowledged"
        await self.db.flush()
        await self._add_event(collab.id, actor_id, "acknowledged", None)
        return AdjustmentCollaborationResponse.model_validate(collab)

    # ------------------------------------------------------------------
    # 补充明细行（重建分录组）
    # ------------------------------------------------------------------
    async def contribute(
        self,
        project_id: UUID,
        collaboration_id: UUID,
        actor_id: UUID,
        line_items: list[AdjustmentSyncLineItem],
        note: str | None = None,
    ) -> AdjustmentCollaborationResponse:
        collab = await self._require(project_id, collaboration_id)
        self._require_assignee(collab, actor_id)
        self._guard_transition(collab.status, "contributed")

        # 借贷平衡校验
        total_debit = sum((li.debit_amount or Decimal("0")) for li in line_items)
        total_credit = sum((li.credit_amount or Decimal("0")) for li in line_items)
        if total_debit != total_credit:
            raise CollaborationError(
                "UNBALANCED",
                f"借贷不平衡：借方合计 {total_debit}，贷方合计 {total_credit}，"
                f"差额 {total_debit - total_credit}",
            )

        # 科目解析（复用 sync 服务）
        sync = AdjustmentSyncService(self.db)
        resolved, unresolved = await sync._resolve_account_codes(project_id, line_items)
        if unresolved:
            raise CollaborationError(
                "UNRESOLVED_ACCOUNTS",
                "以下明细行无法解析标准科目，请补全科目编码：" + "、".join(unresolved),
                detail={"unresolved": unresolved},
            )

        # 重建分录组明细行（保留组元数据：entry_group_id/adjustment_no/type/origin/source_ref/review_status）
        group = await self._adj._get_group_rows(project_id, collab.entry_group_id)
        if not group:
            raise CollaborationError("GROUP_NOT_FOUND", "分录组不存在")
        head = group[0]
        for row in group:
            row.soft_delete()
        for e in await self._adj._get_entry_rows(collab.entry_group_id):
            e.soft_delete()
        await self.db.flush()

        snapshot: list[dict] = []
        for idx, (li, code) in enumerate(zip(line_items, resolved), start=1):
            adj = Adjustment(
                project_id=project_id,
                year=head.year,
                company_code=head.company_code,
                adjustment_no=head.adjustment_no,
                adjustment_type=head.adjustment_type,
                description=head.description,
                account_code=code,
                account_name=li.account_name,
                debit_amount=li.debit_amount,
                credit_amount=li.credit_amount,
                entry_group_id=collab.entry_group_id,
                review_status=head.review_status,
                origin=getattr(head, "origin", "manual") or "manual",
                source_ref=head.source_ref,
                created_by=actor_id,
            )
            self.db.add(adj)
            await self.db.flush()
            self.db.add(AdjustmentEntry(
                adjustment_id=adj.id,
                entry_group_id=collab.entry_group_id,
                line_no=idx,
                standard_account_code=code,
                account_name=li.account_name,
                report_line_code=li.report_line_code,
                debit_amount=li.debit_amount or Decimal("0"),
                credit_amount=li.credit_amount or Decimal("0"),
            ))
            snapshot.append({
                "line_no": idx, "account_code": code, "account_name": li.account_name,
                "debit": str(li.debit_amount or 0), "credit": str(li.credit_amount or 0),
            })

        collab.status = "contributed"
        await self.db.flush()
        await self._add_event(
            collab.id, actor_id, "contributed",
            {"note": note, "lines": snapshot, "round": collab.round},
        )
        await self._notify(
            collab.initiator_id, nt.ADJ_COLLAB_CONTRIBUTED,
            "协作补充已提交",
            f"分录组 {head.adjustment_no or ''} 的协作补充已提交，共 {len(snapshot)} 行",
            collab.entry_group_id, project_id,
        )
        return AdjustmentCollaborationResponse.model_validate(collab)

    # ------------------------------------------------------------------
    # 确认
    # ------------------------------------------------------------------
    async def confirm(
        self, project_id: UUID, collaboration_id: UUID, actor_id: UUID, note: str | None = None
    ) -> AdjustmentCollaborationResponse:
        collab = await self._require(project_id, collaboration_id)
        self._require_assignee(collab, actor_id)
        self._guard_transition(collab.status, "confirmed")
        collab.status = "confirmed"
        await self.db.flush()
        await self._add_event(collab.id, actor_id, "confirmed", {"note": note})
        await self._notify(
            collab.initiator_id, nt.ADJ_COLLAB_CONFIRMED,
            "协作已确认",
            "分录组协作补充已确认完成",
            collab.entry_group_id, project_id,
        )
        return AdjustmentCollaborationResponse.model_validate(collab)

    # ------------------------------------------------------------------
    # 退回
    # ------------------------------------------------------------------
    async def reject(
        self, project_id: UUID, collaboration_id: UUID, actor_id: UUID, reason: str
    ) -> AdjustmentCollaborationResponse:
        collab = await self._require(project_id, collaboration_id)
        if actor_id not in (collab.initiator_id, collab.assignee_id):
            raise CollaborationError("NOT_PARTICIPANT", "只有发起人或被指派人可退回协作")
        self._guard_transition(collab.status, "rejected")
        collab.status = "rejected"
        collab.rejection_reason = reason
        await self.db.flush()
        await self._add_event(collab.id, actor_id, "rejected", {"reason": reason})
        # 通知对方：actor 是 assignee → 通知 initiator；否则通知 assignee
        target = collab.initiator_id if actor_id == collab.assignee_id else collab.assignee_id
        await self._notify(
            target, nt.ADJ_COLLAB_REJECTED,
            "协作已退回",
            f"分录组协作被退回，原因：{reason}",
            collab.entry_group_id, project_id,
        )
        return AdjustmentCollaborationResponse.model_validate(collab)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    async def get_active_by_group(
        self, project_id: UUID, entry_group_id: UUID
    ) -> AdjustmentCollaborationResponse | None:
        collab = await self._get_active(project_id, entry_group_id)
        return AdjustmentCollaborationResponse.model_validate(collab) if collab else None

    async def get_latest_by_group(
        self, project_id: UUID, entry_group_id: UUID
    ) -> AdjustmentCollaboration | None:
        q = (
            sa.select(AdjustmentCollaboration)
            .where(
                AdjustmentCollaboration.project_id == project_id,
                AdjustmentCollaboration.entry_group_id == entry_group_id,
                AdjustmentCollaboration.is_deleted == sa.false(),
            )
            .order_by(AdjustmentCollaboration.round.desc(), AdjustmentCollaboration.created_at.desc())
        )
        return (await self.db.execute(q)).scalars().first()

    async def get_timeline(
        self, collaboration_id: UUID
    ) -> list[AdjustmentCollaborationEvent]:
        q = (
            sa.select(AdjustmentCollaborationEvent)
            .where(AdjustmentCollaborationEvent.collaboration_id == collaboration_id)
            .order_by(AdjustmentCollaborationEvent.created_at)
        )
        return list((await self.db.execute(q)).scalars().all())

    async def list_inbox(
        self, project_id: UUID, assignee_id: UUID
    ) -> list[AdjustmentCollaboration]:
        q = (
            sa.select(AdjustmentCollaboration)
            .where(
                AdjustmentCollaboration.project_id == project_id,
                AdjustmentCollaboration.assignee_id == assignee_id,
                AdjustmentCollaboration.status.in_(list(ACTIVE_STATUSES)),
                AdjustmentCollaboration.is_deleted == sa.false(),
            )
            .order_by(AdjustmentCollaboration.updated_at.desc())
        )
        return list((await self.db.execute(q)).scalars().all())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _require_assignee(self, collab: AdjustmentCollaboration, actor_id: UUID) -> None:
        if actor_id != collab.assignee_id:
            raise CollaborationError(
                "NOT_ASSIGNEE", "只有被指派人可执行该协作操作（知晓/补充/确认）"
            )

    def _guard_transition(self, current: str, target: str) -> None:
        allowed = _LEGAL_FROM.get(target, frozenset())
        if current not in allowed:
            raise CollaborationError(
                "INVALID_TRANSITION",
                f"非法状态转换：{current} → {target}",
            )

    async def _require(
        self, project_id: UUID, collaboration_id: UUID
    ) -> AdjustmentCollaboration:
        q = sa.select(AdjustmentCollaboration).where(
            AdjustmentCollaboration.id == collaboration_id,
            AdjustmentCollaboration.project_id == project_id,
            AdjustmentCollaboration.is_deleted == sa.false(),
        )
        collab = (await self.db.execute(q)).scalar_one_or_none()
        if collab is None:
            raise CollaborationError("COLLAB_NOT_FOUND", "协作记录不存在")
        return collab

    async def _get_active(
        self, project_id: UUID, entry_group_id: UUID
    ) -> AdjustmentCollaboration | None:
        q = (
            sa.select(AdjustmentCollaboration)
            .where(
                AdjustmentCollaboration.project_id == project_id,
                AdjustmentCollaboration.entry_group_id == entry_group_id,
                AdjustmentCollaboration.status.in_(list(ACTIVE_STATUSES)),
                AdjustmentCollaboration.is_deleted == sa.false(),
            )
            .order_by(AdjustmentCollaboration.round.desc(), AdjustmentCollaboration.created_at.desc())
        )
        return (await self.db.execute(q)).scalars().first()

    async def _next_round(self, project_id: UUID, entry_group_id: UUID) -> int:
        q = sa.select(sa.func.max(AdjustmentCollaboration.round)).where(
            AdjustmentCollaboration.project_id == project_id,
            AdjustmentCollaboration.entry_group_id == entry_group_id,
            AdjustmentCollaboration.is_deleted == sa.false(),
        )
        cur = (await self.db.execute(q)).scalar()
        return (cur or 0) + 1

    async def _resolve_user_id(self, candidate_id: UUID) -> UUID:
        """picker 可能传 staff_id 或 user_id → 归一为 user_id。

        若 candidate_id 命中 StaffMember.id 则取其 user_id；否则原样视为 user_id。
        """
        from app.models.staff_models import StaffMember

        staff_user_id = (await self.db.execute(
            sa.select(StaffMember.user_id).where(
                StaffMember.id == candidate_id,
                StaffMember.is_deleted == sa.false(),
            )
        )).scalar_one_or_none()
        return staff_user_id or candidate_id

    async def _is_project_member(self, project_id: UUID, user_id: UUID) -> bool:
        from app.models.core import User, UserRole
        from app.models.staff_models import ProjectAssignment, StaffMember

        # admin 全局可协作
        role = (await self.db.execute(
            sa.select(User.role).where(User.id == user_id)
        )).scalar_one_or_none()
        if role in (UserRole.admin, "admin", getattr(UserRole, "admin", None)):
            return True
        # StaffMember → ProjectAssignment（role 不限，只要是项目成员）
        staff_id = (await self.db.execute(
            sa.select(StaffMember.id).where(
                StaffMember.user_id == user_id,
                StaffMember.is_deleted == sa.false(),
            )
        )).scalar_one_or_none()
        if not staff_id:
            return False
        pa = (await self.db.execute(
            sa.select(ProjectAssignment.id).where(
                ProjectAssignment.staff_id == staff_id,
                ProjectAssignment.project_id == project_id,
                ProjectAssignment.is_deleted == sa.false(),
            )
        )).scalar_one_or_none()
        return pa is not None

    async def _add_event(
        self, collaboration_id: UUID, actor_id: UUID, event_type: str, payload: dict | None
    ) -> None:
        self.db.add(AdjustmentCollaborationEvent(
            collaboration_id=collaboration_id,
            actor_id=actor_id,
            event_type=event_type,
            payload=payload,
        ))
        await self.db.flush()

    async def _notify(
        self, user_id: UUID, notif_type: str, title: str, content: str,
        entry_group_id: UUID, project_id: UUID | None = None,
    ) -> None:
        """旁路通知（失败仅 warning，不阻断状态转换）。"""
        try:
            metadata = {
                "object_type": "adjustment_collaboration",
                "object_id": str(entry_group_id),
            }
            if project_id is not None:
                # 前端 getNotificationJumpRoute 据此构造 /projects/{pid}/adjustments?group={id}
                metadata["project_id"] = str(project_id)
            await self._notif.send_notification(
                user_id=user_id,
                notification_type=notif_type,
                title=title,
                content=content,
                metadata=metadata,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ADJ_COLLAB] notify failed (non-blocking): %s", exc)
