"""工时批量审批服务 — Round 2 需求 7

POST /api/workhours/batch-approve
- 幂等键头 Idempotency-Key + Redis 5 分钟防重
- 状态流转 confirmed→approved 或 confirmed→draft（退回附原因）
- SOD 守卫：审批人 ≠ 被审批人
- 发通知 workhour_approved / workhour_rejected
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.staff_models import StaffMember, WorkHour
from app.services.notification_service import NotificationService
from app.services.notification_types import WORKHOUR_APPROVED, WORKHOUR_REJECTED

logger = logging.getLogger(__name__)

# 幂等键 TTL（秒）
IDEMPOTENCY_TTL = 300  # 5 分钟


class WorkHourApproveService:
    """工时批量审批服务"""

    async def batch_approve(
        self,
        db: AsyncSession,
        hour_ids: list[uuid.UUID],
        action: Literal["approve", "reject"],
        approver_user_id: uuid.UUID,
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """批量审批/退回工时记录。

        Args:
            db: 数据库会话
            hour_ids: 工时记录 ID 列表
            action: 'approve' 批准 | 'reject' 退回
            approver_user_id: 审批人 user_id
            reason: 退回原因（reject 时必填）
            idempotency_key: 幂等键（可选）

        Returns:
            {approved_count, rejected_count, failed: [{id, reason}]}
        """
        # 1. 幂等检查
        if idempotency_key:
            cached_result = await self._check_idempotency(idempotency_key)
            if cached_result is not None:
                logger.info(
                    "[WORKHOUR_APPROVE] idempotency hit: key=%s", idempotency_key
                )
                return cached_result

        # 2. 获取审批人对应的 staff_id
        approver_staff_id = await self._get_staff_id(db, approver_user_id)

        # 3. 查询所有目标工时记录
        stmt = sa.select(WorkHour).where(
            WorkHour.id.in_(hour_ids),
            WorkHour.is_deleted == False,  # noqa: E712
        )
        result = await db.execute(stmt)
        records = list(result.scalars().all())

        # 建立 ID → 记录映射
        record_map = {r.id: r for r in records}

        approved_count = 0
        rejected_count = 0
        failed: list[dict] = []

        notif_service = NotificationService(db)

        for hour_id in hour_ids:
            wh = record_map.get(hour_id)

            # 记录不存在
            if wh is None:
                failed.append({"id": str(hour_id), "reason": "记录不存在"})
                continue

            # 状态不是 confirmed，不能审批
            if wh.status != "confirmed":
                failed.append({
                    "id": str(hour_id),
                    "reason": f"状态为 {wh.status}，仅 confirmed 状态可审批",
                })
                continue

            # SOD 守卫：审批人 ≠ 被审批人
            if approver_staff_id and wh.staff_id == approver_staff_id:
                failed.append({
                    "id": str(hour_id),
                    "reason": "审批人不能审批自己的工时（SOD 冲突）",
                })
                continue

            # 执行状态流转
            if action == "approve":
                wh.status = "approved"
                approved_count += 1

                # 发通知给员工
                staff_user_id = await self._get_user_id_by_staff(db, wh.staff_id)
                if staff_user_id:
                    await notif_service.send_notification(
                        user_id=staff_user_id,
                        notification_type=WORKHOUR_APPROVED,
                        title="工时已批准",
                        content=f"您 {wh.work_date} 提交的 {float(wh.hours)} 小时工时已被批准",
                        metadata={
                            "object_type": "work_hour",
                            "object_id": str(wh.id),
                            "date": str(wh.work_date),
                            "hours": str(float(wh.hours)),
                        },
                    )
            else:
                # reject → 退回到 draft
                wh.status = "draft"
                rejected_count += 1

                # 发通知给员工（附原因）
                staff_user_id = await self._get_user_id_by_staff(db, wh.staff_id)
                reject_reason = reason or "未提供原因"
                if staff_user_id:
                    await notif_service.send_notification(
                        user_id=staff_user_id,
                        notification_type=WORKHOUR_REJECTED,
                        title="工时已退回",
                        content=(
                            f"您 {wh.work_date} 提交的 {float(wh.hours)} 小时工时已被退回，"
                            f"原因：{reject_reason}"
                        ),
                        metadata={
                            "object_type": "work_hour",
                            "object_id": str(wh.id),
                            "date": str(wh.work_date),
                            "hours": str(float(wh.hours)),
                            "reason": reject_reason,
                        },
                    )

        await db.commit()

        result_data = {
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "failed": failed,
        }

        # 写入幂等缓存
        if idempotency_key:
            await self._set_idempotency(idempotency_key, result_data)

        return result_data

    async def _get_staff_id(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> uuid.UUID | None:
        """通过 user_id 查找对应的 staff_id。"""
        stmt = sa.select(StaffMember.id).where(
            StaffMember.user_id == user_id,
            StaffMember.is_deleted == False,  # noqa: E712
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_user_id_by_staff(
        self, db: AsyncSession, staff_id: uuid.UUID
    ) -> uuid.UUID | None:
        """通过 staff_id 查找对应的 user_id（用于发通知）。"""
        stmt = sa.select(StaffMember.user_id).where(
            StaffMember.id == staff_id,
            StaffMember.is_deleted == False,  # noqa: E712
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _check_idempotency(self, key: str) -> dict | None:
        """检查幂等键是否已存在（Redis）。

        Redis 不可用时降级跳过（允许重复执行）。
        """
        try:
            from app.core.redis import redis_client
            import json

            cached = await redis_client.get(f"idempotency:workhour_approve:{key}")
            if cached:
                return json.loads(cached)
            return None
        except Exception as exc:
            logger.warning(
                "[WORKHOUR_APPROVE] Redis unavailable for idempotency check: %s", exc
            )
            return None

    async def _set_idempotency(self, key: str, result: dict) -> None:
        """写入幂等缓存，TTL 5 分钟。"""
        try:
            from app.core.redis import redis_client
            import json

            await redis_client.setex(
                f"idempotency:workhour_approve:{key}",
                IDEMPOTENCY_TTL,
                json.dumps(result, ensure_ascii=False),
            )
        except Exception as exc:
            logger.warning(
                "[WORKHOUR_APPROVE] Redis unavailable for idempotency set: %s", exc
            )


workhour_approve_service = WorkHourApproveService()
