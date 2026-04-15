"""通知服务 — NotificationService

提供通知的创建、查询、已读管理等能力：
- create_notification — 创建通知记录
- get_notifications — 分页+筛选查询
- mark_read / mark_all_read — 标记已读
- get_unread_count — 未读数量（Redis缓存，30秒TTL）
- 事件处理器方法（供 EventBus 调用）

Phase 3 事件→通知映射：
  REVIEW_SUBMITTED       → 复核待办通知（发复核人）
  REVIEW_COMPLETED       → 复核完成通知（发编制人）
  REVIEW_RESPONDED       → 复核回复通知（发复核人）
  MISSTATEMENT_THRESHOLD → 错报超限通知（发项目经理+合伙人）
  CONFIRMATION_OVERDUE   → 函证超期通知（发项目经理）
  SYNC_CONFLICT          → 同步冲突通知（发操作人）
  GOING_CONCERN_ALERT    → 持续经营预警（发合伙人）

Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.redis import redis_client
from app.models.core import Notification, Project, ProjectUser, User
from app.models.audit_platform_schemas import EventPayload, EventType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Notification type constants
# ---------------------------------------------------------------------------

NOTIF_TYPE_WORKPAPER_ASSIGNED = "workpaper_assigned"
NOTIF_TYPE_WORKPAPER_SIGNED = "workpaper_signed"
NOTIF_TYPE_WORKPAPER_REVIEW = "workpaper_review"
NOTIF_TYPE_REVIEW_PENDING = "review_pending"
NOTIF_TYPE_REVIEW_RESPONSE = "review_response"
NOTIF_TYPE_REVIEW_APPROVED = "review_approved"
NOTIF_TYPE_REVIEW_REJECTED = "review_rejected"
NOTIF_TYPE_OVERDUE_WARNING = "overdue_warning"
NOTIF_TYPE_MISSTATEMENT_ALERT = "misstatement_alert"
NOTIF_TYPE_SYNC_CONFLICT = "sync_conflict"
NOTIF_TYPE_AI_COMPLETE = "ai_complete"
NOTIF_TYPE_IMPORT_COMPLETE = "import_complete"
NOTIF_TYPE_CONFIRMATION_OVERDUE = "confirmation_overdue"
NOTIF_TYPE_REPORT_READY = "report_ready"
NOTIF_TYPE_ADJUSTMENT_APPROVED = "adjustment_approved"
NOTIF_TYPE_ADJUSTMENT_REJECTED = "adjustment_rejected"
NOTIF_TYPE_PBC_REMINDER = "pbc_reminder"
NOTIF_TYPE_CONFIRMATION_REPLY = "confirmation_reply"
NOTIF_TYPE_GOING_CONCERN_ALERT = "going_concern_alert"
NOTIF_TYPE_GENERAL = "general"

# Redis缓存键前缀与TTL
_UNREAD_COUNT_KEY_PREFIX = "notif:unread:"
_UNREAD_COUNT_TTL_SECONDS = 30


# ---------------------------------------------------------------------------
# NotificationService
# ---------------------------------------------------------------------------

class NotificationService:
    """通知服务"""

    @staticmethod
    def create_notification(
        db: Session,
        recipient_id: str,
        notification_type: str,
        title: str,
        message: Optional[str] = None,
        related_object_type: Optional[str] = None,
        related_object_id: Optional[str] = None,
        project_id: Optional[str] = None,
        priority: str = "normal",
    ) -> Notification:
        """
        创建通知记录并使缓存失效。

        Args:
            db: 数据库会话
            recipient_id: 通知接收人用户ID
            notification_type: 通知类型（见常量）
            title: 通知标题
            message: 通知内容
            related_object_type: 关联对象类型（workpaper/adjustment/review/...）
            related_object_id: 关联对象ID
            project_id: 关联项目ID
            priority: 优先级（low/normal/high）
        """
        notif = Notification(
            id=uuid.uuid4(),
            recipient_id=recipient_id,
            notification_type=notification_type,
            title=title,
            content=message,
            related_object_type=related_object_type,
            related_object_id=related_object_id,
            project_id=project_id,
            is_read=False,
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(notif)
        db.commit()
        db.refresh(notif)

        # 缓存失效
        NotificationService._invalidate_unread_cache(recipient_id)

        return notif

    @staticmethod
    def get_notifications(
        db: Session,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        unread_only: bool = False,
        type_filter: Optional[str] = None,
    ) -> tuple[list[Notification], int]:
        """
        分页查询用户通知。

        Args:
            db: 数据库会话
            user_id: 用户ID
            page: 页码（从1开始）
            page_size: 每页条数
            unread_only: 仅返回未读
            type_filter: 按通知类型筛选

        Returns:
            (通知列表, 总数)
        """
        query = db.query(Notification).filter(
            Notification.recipient_id == user_id,
            Notification.is_deleted == False,  # noqa: E712
        )

        if unread_only:
            query = query.filter(Notification.is_read == False)  # noqa: E712

        if type_filter:
            query = query.filter(Notification.notification_type == type_filter)

        total = query.count()

        offset = (page - 1) * page_size
        notifications = (
            query.order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

        return notifications, total

    @staticmethod
    def mark_read(
        db: Session,
        notification_id: str,
        user_id: str,
    ) -> Optional[Notification]:
        """
        标记单条通知为已读，需校验归属。

        Returns:
            更新后的通知对象；若不存在或不属于该用户则返回 None。
        """
        notif = (
            db.query(Notification)
            .filter(
                Notification.id == notification_id,
                Notification.recipient_id == user_id,
                Notification.is_deleted == False,  # noqa: E712
            )
            .first()
        )
        if not notif:
            return None

        if not notif.is_read:
            notif.is_read = True
            notif.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(notif)
            NotificationService._invalidate_unread_cache(user_id)

        return notif

    @staticmethod
    def mark_all_read(db: Session, user_id: str) -> int:
        """
        标记用户所有未读通知为已读。

        Returns:
            实际更新的记录数。
        """
        count = (
            db.query(Notification)
            .filter(
                Notification.recipient_id == user_id,
                Notification.is_read == False,  # noqa: E712
                Notification.is_deleted == False,  # noqa: E712
            )
            .update(
                {"is_read": True, "updated_at": datetime.now(timezone.utc)},
                synchronize_session=False,
            )
        )
        db.commit()

        NotificationService._invalidate_unread_cache(user_id)

        return count

    @staticmethod
    def get_unread_count(db: Session, user_id: str) -> int:
        """
        获取用户未读通知数量。

        使用 Redis 缓存（30秒TTL），缓存未命中时查库并写入缓存。
        """
        cache_key = f"{_UNREAD_COUNT_KEY_PREFIX}{user_id}"

        try:
            cached = redis_client.get(cache_key)
            if cached is not None:
                return int(cached)
        except Exception:
            logger.warning("Redis unavailable for unread count cache")

        # 缓存未命中，查库
        count = (
            db.query(func.count(Notification.id))
            .filter(
                Notification.recipient_id == user_id,
                Notification.is_read == False,  # noqa: E712
                Notification.is_deleted == False,  # noqa: E712
            )
            .scalar()
        ) or 0

        try:
            redis_client.setex(cache_key, _UNREAD_COUNT_TTL_SECONDS, count)
        except Exception:
            logger.warning("Redis unavailable for unread count write")

        return count

    # -------------------------------------------------------------------------
    # 缓存失效
    # -------------------------------------------------------------------------

    @staticmethod
    def _invalidate_unread_cache(user_id: str) -> None:
        """删除用户未读数缓存，使下次查询触发重新计算"""
        cache_key = f"{_UNREAD_COUNT_KEY_PREFIX}{user_id}"
        try:
            redis_client.delete(cache_key)
        except Exception:
            logger.warning("Redis unavailable for cache invalidation")

    # -------------------------------------------------------------------------
    # 事件处理器（供 EventBus 调用）
    # -------------------------------------------------------------------------

    async def on_review_submitted(self, payload: EventPayload) -> None:
        """
        底稿提交复核 → 通知复核人（review_pending）

        Payload extra 字段期望:
            reviewer_id: str — 指定复核人用户ID
            submitter_name: str — 提交人姓名
            workpaper_name: str — 底稿名称
            project_name: str — 项目名称
        """
        extra = payload.extra or {}
        reviewer_id = extra.get("reviewer_id")
        if not reviewer_id:
            logger.warning("on_review_submitted: no reviewer_id in payload")
            return

        self._notify(
            recipient_id=reviewer_id,
            notification_type=NOTIF_TYPE_REVIEW_PENDING,
            title="工作底稿待复核",
            message=(
                f"【{extra.get('project_name', '项目')}】"
                f"审计员 {extra.get('submitter_name', '未知')} "
                f"已提交「{extra.get('workpaper_name', '底稿')}」待您复核。"
            ),
            related_object_type="workpaper",
            related_object_id=payload.extra.get("workpaper_id"),
            project_id=str(payload.project_id),
        )

    async def on_review_completed(self, payload: EventPayload) -> None:
        """
        复核完成 → 通知编制人（review_approved / review_rejected）

        Payload extra 字段期望:
            submitter_id: str — 编制人用户ID
            reviewer_name: str — 复核人姓名
            result: "approved" | "rejected" — 复核结果
            workpaper_name: str — 底稿名称
            project_name: str — 项目名称
            opinion: str — 复核意见（可选）
        """
        extra = payload.extra or {}
        submitter_id = extra.get("submitter_id")
        if not submitter_id:
            logger.warning("on_review_completed: no submitter_id in payload")
            return

        result = extra.get("result", "approved")
        if result == "approved":
            notif_type = NOTIF_TYPE_REVIEW_APPROVED
            title = "复核已通过"
            message = (
                f"您编制的「{extra.get('workpaper_name', '底稿')}」"
                f"已通过 {extra.get('reviewer_name', '复核人')} 的复核。"
            )
        else:
            notif_type = NOTIF_TYPE_REVIEW_REJECTED
            title = "复核意见：需修改"
            opinion = extra.get("opinion", "")
            message = (
                f"您编制的「{extra.get('workpaper_name', '底稿')}」"
                f"被 {extra.get('reviewer_name', '复核人')} 退回，请查看复核意见。"
                + (f"\n意见：{opinion}" if opinion else "")
            )

        self._notify(
            recipient_id=submitter_id,
            notification_type=notif_type,
            title=title,
            message=message,
            related_object_type="workpaper",
            related_object_id=payload.extra.get("workpaper_id"),
            project_id=str(payload.project_id),
        )

    async def on_review_responded(self, payload: EventPayload) -> None:
        """
        编制人回复复核意见 → 通知复核人（review_response）

        Payload extra 字段期望:
            reviewer_id: str — 原复核人用户ID
            responder_name: str — 回复人姓名
            workpaper_name: str — 底稿名称
            project_name: str — 项目名称
        """
        extra = payload.extra or {}
        reviewer_id = extra.get("reviewer_id")
        if not reviewer_id:
            logger.warning("on_review_responded: no reviewer_id in payload")
            return

        self._notify(
            recipient_id=reviewer_id,
            notification_type=NOTIF_TYPE_REVIEW_RESPONSE,
            title="复核意见已回复",
            message=(
                f"【{extra.get('project_name', '项目')}】"
                f"{extra.get('responder_name', '编制人')} "
                f"已回复您对「{extra.get('workpaper_name', '底稿')}」的复核意见，请查看。"
            ),
            related_object_type="review",
            related_object_id=payload.extra.get("review_id"),
            project_id=str(payload.project_id),
        )

    async def on_misstatement_alert(self, payload: EventPayload) -> None:
        """
        未更正错报达到/超过重要性水平 → 通知项目经理和合伙人（misstatement_alert）

        Payload extra 字段期望:
            total_amount: float — 错报总金额
            materiality_level: float — 重要性水平
            project_name: str — 项目名称
        """
        extra = payload.extra or {}
        project_id = str(payload.project_id)

        # 查询项目成员：manager 和 partner
        db = self._get_sync_db()
        try:
            project_users = (
                db.query(ProjectUser)
                .filter(
                    ProjectUser.project_id == project_id,
                    ProjectUser.is_deleted == False,  # noqa: E712
                    ProjectUser.role.in_(["manager", "partner"]),
                )
                .all()
            )
        finally:
            db.close()

        for pu in project_users:
            self._notify(
                recipient_id=str(pu.user_id),
                notification_type=NOTIF_TYPE_MISSTATEMENT_ALERT,
                title="错报超限预警",
                message=(
                    f"【{extra.get('project_name', '项目')}】"
                    f"未更正错报总额（{extra.get('total_amount', 0):.2f}）"
                    f"已达到或超过重要性水平（{extra.get('materiality_level', 0):.2f}），"
                    f"请项目经理和合伙人关注。"
                ),
                related_object_type="misstatement",
                project_id=project_id,
            )

    async def on_confirmation_overdue(self, payload: EventPayload) -> None:
        """
        函证超30天未回函 → 通知项目经理（confirmation_overdue）

        Payload extra 字段期望:
            confirmation_id: str — 函证ID
            counterparty_name: str — 对方单位名称
            days_overdue: int — 超期天数
            project_name: str — 项目名称
            manager_id: str — 项目经理用户ID
        """
        extra = payload.extra or {}
        manager_id = extra.get("manager_id")
        if not manager_id:
            logger.warning("on_confirmation_overdue: no manager_id in payload")
            return

        self._notify(
            recipient_id=manager_id,
            notification_type=NOTIF_TYPE_CONFIRMATION_OVERDUE,
            title="函证超期未回函",
            message=(
                f"【{extra.get('project_name', '项目')}】"
                f"向「{extra.get('counterparty_name', '未知')}」发出的函证"
                f"已超期 {extra.get('days_overdue', 0)} 天仍未回函，请跟进。"
            ),
            related_object_type="confirmation",
            related_object_id=extra.get("confirmation_id"),
            project_id=str(payload.project_id),
        )

    async def on_sync_conflict(self, payload: EventPayload) -> None:
        """
        云同步检测到冲突 → 通知操作人（sync_conflict）

        Payload extra 字段期望:
            user_id: str — 触发冲突的用户ID
            conflict_type: str — 冲突类型
            project_name: str — 项目名称
        """
        extra = payload.extra or {}
        user_id = extra.get("user_id")
        if not user_id:
            logger.warning("on_sync_conflict: no user_id in payload")
            return

        self._notify(
            recipient_id=user_id,
            notification_type=NOTIF_TYPE_SYNC_CONFLICT,
            title="同步冲突",
            message=(
                f"【{extra.get('project_name', '项目')}】"
                f"同步时检测到{extra.get('conflict_type', '数据')}冲突，"
                f"请手动解决后再继续同步。"
            ),
            related_object_type="sync",
            project_id=str(payload.project_id),
        )

    async def on_going_concern_alert(self, payload: EventPayload) -> None:
        """
        持续经营评价发现重大问题 → 通知合伙人（going_concern_alert）

        Payload extra 字段期望:
            partner_id: str — 合伙人用户ID
            conclusion: str — 结论类型
            project_name: str — 项目名称
        """
        extra = payload.extra or {}
        partner_id = extra.get("partner_id")
        if not partner_id:
            logger.warning("on_going_concern_alert: no partner_id in payload")
            return

        conclusion = extra.get("conclusion", "")
        conclusion_msg = ""
        if conclusion == "material_uncertainty":
            conclusion_msg = "审计报告需增加「与持续经营相关的重大不确定性」段落。"
        elif conclusion == "going_concern_inappropriate":
            conclusion_msg = "建议考虑出具否定意见。"

        self._notify(
            recipient_id=partner_id,
            notification_type=NOTIF_TYPE_GOING_CONCERN_ALERT,
            title="持续经营预警",
            message=(
                f"【{extra.get('project_name', '项目')}】"
                f"持续经营评价已出具结论（{conclusion or '未知'}），"
                f"{conclusion_msg}"
            ),
            related_object_type="going_concern",
            related_object_id=extra.get("going_concern_id"),
            project_id=str(payload.project_id),
        )

    # -------------------------------------------------------------------------
    # 内部工具
    # -------------------------------------------------------------------------

    @staticmethod
    def _get_sync_db() -> Session:
        """
        获取同步数据库会话（用于事件处理器）。
        """
        from app.core.database import SyncSession

        return SyncSession()

    def _notify(self, **kwargs) -> None:
        """创建通知并自动关闭数据库会话，防止连接泄漏。"""
        db = self._get_sync_db()
        try:
            self.create_notification(db=db, **kwargs)
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 全局实例（供事件处理器引用）
# ---------------------------------------------------------------------------
notification_service = NotificationService()
