"""底稿催办服务 — Round 2 需求 4

POST /api/projects/{project_id}/workpapers/{wp_id}/remind
- 创建 IssueTicket(source='reminder') + Notification(type='workpaper_reminder')
- 消息模板用"已创建 X 天尚未完成"措辞（不用"逾期"）
- 7 天内 3 次限流（Redis remind:{wp_id}:{day} 计数，按自然日）
- 超限返回 429 + 提示消息
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase15_enums import IssueSource, IssueStatus
from app.models.phase15_models import IssueTicket
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.notification_service import NotificationService
from app.services.notification_types import WORKPAPER_REMINDER
from app.services.trace_event_service import generate_trace_id

logger = logging.getLogger(__name__)

# 7 天内最多催办次数
MAX_REMIND_COUNT = 3
# 限流窗口天数
REMIND_WINDOW_DAYS = 7


class WorkpaperRemindService:
    """底稿催办服务"""

    async def remind(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        operator_id: uuid.UUID,
        message: Optional[str] = None,
    ) -> dict:
        """对指定底稿发起催办。

        Args:
            db: 数据库会话
            project_id: 项目 ID
            wp_id: 底稿 ID（WorkingPaper.id）
            operator_id: 操作人 ID（项目经理）
            message: 自定义催办消息（可选）

        Returns:
            {ticket_id, notification_id, remind_count, allowed_next}

        Raises:
            HTTPException 404: 底稿不存在
            HTTPException 429: 7 天内已催办 3 次
        """
        # 1. 查询底稿及其索引信息
        stmt = (
            select(WorkingPaper, WpIndex)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WorkingPaper.id == wp_id,
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == False,  # noqa: E712
            )
        )
        result = await db.execute(stmt)
        row = result.one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="WORKPAPER_NOT_FOUND")

        wp: WorkingPaper = row[0]
        wp_index: WpIndex = row[1]

        # 2. 确定催办对象（assigned_to）
        assigned_to = wp.assigned_to or wp_index.assigned_to
        if assigned_to is None:
            raise HTTPException(
                status_code=400,
                detail="底稿尚未分配编制人，无法催办",
            )

        # 3. 限流检查：7 天内最多 3 次
        remind_count = await self._get_remind_count(wp_id)
        if remind_count >= MAX_REMIND_COUNT:
            raise HTTPException(
                status_code=429,
                detail={
                    "error_code": "REMIND_LIMIT_EXCEEDED",
                    "message": "已连续催办 3 次，请考虑重新分配",
                    "remind_count": remind_count,
                },
            )

        # 4. 计算"已创建天数"
        created_at = wp.created_at or wp_index.created_at
        days_since_created = (date.today() - created_at.date()).days if created_at else 0

        # 5. 构建催办消息
        wp_code = wp_index.wp_code
        wp_name = wp_index.wp_name
        if message:
            remind_message = message
        else:
            remind_message = (
                f"您编制的底稿 {wp_code} {wp_name} "
                f"已创建 {days_since_created} 天尚未完成，请尽快推进。"
            )

        # 6. 创建 IssueTicket(source='reminder')
        trace_id = generate_trace_id()
        ticket = IssueTicket(
            id=uuid.uuid4(),
            project_id=project_id,
            wp_id=wp_id,
            source=IssueSource.reminder.value,
            severity="minor",
            category="procedure_incomplete",
            title=f"催办：{wp_code} {wp_name}",
            description=remind_message,
            owner_id=operator_id,
            status=IssueStatus.open,
            trace_id=trace_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(ticket)
        await db.flush()

        # 7. 发送 Notification(type='workpaper_reminder')
        notif_service = NotificationService(db)
        notif_result = await notif_service.send_notification(
            user_id=assigned_to,
            notification_type=WORKPAPER_REMINDER,
            title=f"底稿催办提醒 — {wp_code}",
            content=remind_message,
            metadata={
                "object_type": "working_paper",
                "object_id": str(wp_id),
                "project_id": str(project_id),
                "wp_code": wp_code,
                "wp_name": wp_name,
                "days": str(days_since_created),
            },
        )

        notification_id = notif_result["id"] if notif_result else None

        # Batch 1 Fix 1.5: commit 先于 Redis INCR，避免 commit 失败但计数已递增
        await db.commit()

        # 8. 递增 Redis 计数（commit 成功后才计入）
        new_count = await self._increment_remind_count(wp_id)

        # 9. 计算下次允许催办时间
        allowed_next = self._compute_allowed_next(new_count)

        return {
            "ticket_id": str(ticket.id),
            "notification_id": notification_id,
            "remind_count": new_count,
            "allowed_next": allowed_next,
        }

    async def _get_remind_count(self, wp_id: uuid.UUID) -> int:
        """获取 7 天内催办次数（Redis pipeline 原子读取）。

        Batch 1 Fix 1.4: 使用 pipeline MGET 替代逐个 GET，减少 race window。
        Redis 不可用时降级返回 0（允许催办）。
        """
        try:
            from app.core.redis import redis_client

            today = date.today()
            keys = [
                f"remind:{wp_id}:{(today - timedelta(days=i)).strftime('%Y%m%d')}"
                for i in range(REMIND_WINDOW_DAYS)
            ]
            # pipeline 原子批量读取
            pipe = redis_client.pipeline(transaction=False)
            for k in keys:
                pipe.get(k)
            values = await pipe.execute()
            return sum(int(v) for v in values if v)
        except Exception as exc:
            logger.warning(
                "[REMIND] Redis unavailable for rate limit check, allowing: %s", exc
            )
            return 0

    async def _increment_remind_count(self, wp_id: uuid.UUID) -> int:
        """递增今日催办计数，返回 7 天内总计数。

        Batch 1 Fix 1.4: 使用 pipeline INCR + MGET 原子操作，避免并发 race。
        Redis key TTL = 7 天（确保过期自动清理）。
        """
        try:
            from app.core.redis import redis_client

            today = date.today()
            today_key = f"remind:{wp_id}:{today.strftime('%Y%m%d')}"
            keys = [
                f"remind:{wp_id}:{(today - timedelta(days=i)).strftime('%Y%m%d')}"
                for i in range(REMIND_WINDOW_DAYS)
            ]

            # pipeline: INCR today + EXPIRE + MGET all 7 days
            pipe = redis_client.pipeline(transaction=True)
            pipe.incr(today_key)
            pipe.expire(today_key, REMIND_WINDOW_DAYS * 86400)
            for k in keys:
                pipe.get(k)
            results = await pipe.execute()

            # results[0] = INCR result (today's new count)
            # results[1] = EXPIRE result (True/False)
            # results[2:] = MGET results for 7 days
            mget_values = results[2:]
            # 用 INCR 后的值替代 today 的 GET（因为 GET 可能拿到 INCR 前的值）
            total = int(results[0])  # today's count from INCR
            for i, v in enumerate(mget_values):
                if i == 0:
                    continue  # skip today, already counted from INCR
                if v:
                    total += int(v)
            return total
        except Exception as exc:
            logger.warning(
                "[REMIND] Redis unavailable for increment, returning 1: %s", exc
            )
            return 1

    def _compute_allowed_next(self, current_count: int) -> str | None:
        """计算下次允许催办的时间提示。

        如果已达上限返回 None（不允许），否则返回"立即可用"。
        """
        if current_count >= MAX_REMIND_COUNT:
            return None
        return "now"


workpaper_remind_service = WorkpaperRemindService()
