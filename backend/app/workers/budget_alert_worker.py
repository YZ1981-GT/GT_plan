"""预算预警 Worker — 每日凌晨扫描项目工时，80%/100% 触发通知

需求 9.4：
- 实际工时 > 预算 80% → budget_alert_80 通知给 PM 与 signing_partner
- 实际工时 > 预算 100% → budget_overrun 通知给 PM 与 signing_partner
- 幂等键 budget_alert:{project_id}:{threshold}:{YYYYMMDD}，一天内同阈值不重复发

Worker 模式：async def run(stop_event: asyncio.Event)
使用 asyncio.wait_for(stop_event.wait(), timeout=interval) 实现可中断 sleep。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

logger = logging.getLogger("budget_alert")

# 每日检查一次（86400 秒 = 24 小时）
INTERVAL_SECONDS = 86400


async def run(stop_event: asyncio.Event) -> None:
    """预算预警主循环。

    - stop_event.set() 后退出循环
    - 异常不影响主应用，记录 warning 后继续下一周期
    """
    import os
    worker_id = f"{os.uname().nodename if hasattr(os, 'uname') else 'win'}-{os.getpid()}"
    logger.info("[BUDGET_ALERT] started, worker_id=%s, interval=%ds", worker_id, INTERVAL_SECONDS)

    while not stop_event.is_set():
        try:
            # 等待 INTERVAL_SECONDS 或 stop_event
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=INTERVAL_SECONDS)
                break  # stop_event 被设置，退出
            except asyncio.TimeoutError:
                pass  # 正常到达间隔，继续执行检查

            await _check_all_projects()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("[BUDGET_ALERT] check loop error: %s", e)


async def _check_all_projects() -> None:
    """扫描所有有预算的项目，检查是否需要发预警。"""
    from app.core.database import async_session
    from app.core.redis import redis_client
    from app.models.core import Project
    from app.models.staff_models import ProjectAssignment, WorkHour
    from app.services.notification_service import NotificationService

    async with async_session() as db:
        # 查询所有有 budget_hours 且未归档的项目
        stmt = select(Project.id, Project.budget_hours, Project.name).where(
            Project.budget_hours.isnot(None),
            Project.is_deleted == False,  # noqa: E712
            Project.archived_at.is_(None),
        )
        result = await db.execute(stmt)
        projects = result.all()

        if not projects:
            return

        today_str = date.today().strftime("%Y%m%d")
        notification_service = NotificationService(db)
        alerts_sent = 0

        for project_row in projects:
            project_id = project_row.id
            budget_hours = project_row.budget_hours
            project_name = project_row.name or str(project_id)

            # 计算已批准工时总量
            hours_stmt = select(func.sum(WorkHour.hours)).where(
                WorkHour.project_id == project_id,
                WorkHour.status == "approved",
                WorkHour.is_deleted == False,  # noqa: E712
            )
            hours_result = await db.execute(hours_stmt)
            actual_hours = hours_result.scalar() or Decimal("0")
            actual_hours_float = float(actual_hours)

            if budget_hours <= 0:
                continue

            utilization = actual_hours_float / budget_hours

            # 确定需要发送的阈值
            thresholds_to_check: list[tuple[float, str, str]] = []
            if utilization >= 1.0:
                thresholds_to_check.append(
                    (1.0, "100", "budget_overrun")
                )
            if utilization >= 0.8:
                thresholds_to_check.append(
                    (0.8, "80", "budget_alert_80")
                )

            if not thresholds_to_check:
                continue

            # 获取 PM 和 signing_partner 的 user_id
            recipients = await _get_pm_and_partner_user_ids(db, project_id)
            if not recipients:
                continue

            for _threshold_val, threshold_label, notification_type in thresholds_to_check:
                idempotency_key = (
                    f"budget_alert:{project_id}:{threshold_label}:{today_str}"
                )

                # Redis 幂等检查：一天内同阈值不重复发
                try:
                    already_sent = await redis_client.get(idempotency_key)
                    if already_sent:
                        continue
                except Exception:
                    # Redis 不可用时跳过幂等检查，允许重复发送
                    pass

                # 发送通知
                title = (
                    f"项目预算预警（{threshold_label}%）"
                    if threshold_label == "80"
                    else "项目预算超支"
                )
                content = (
                    f"项目「{project_name}」已使用工时 "
                    f"{actual_hours_float:.1f} / {budget_hours} 小时"
                    f"（{utilization * 100:.0f}%），请关注。"
                )

                for user_id in recipients:
                    await notification_service.send_notification(
                        user_id=user_id,
                        notification_type=notification_type,
                        title=title,
                        content=content,
                        metadata={
                            "object_type": "project",
                            "object_id": str(project_id),
                            "project_id": str(project_id),
                            "project_name": project_name,
                            "threshold": threshold_label,
                            "utilization_pct": f"{utilization * 100:.0f}",
                        },
                    )

                # 标记幂等键（24 小时过期）
                try:
                    await redis_client.set(
                        idempotency_key, "1", ex=86400
                    )
                except Exception:
                    pass

                alerts_sent += 1

        if alerts_sent > 0:
            await db.commit()
            logger.info("[BUDGET_ALERT] sent %d alert(s)", alerts_sent)


async def _get_pm_and_partner_user_ids(
    db, project_id
) -> list:
    """获取项目的 manager 和 signing_partner 对应的 user_id 列表。"""
    from app.models.staff_models import ProjectAssignment, StaffMember

    stmt = (
        select(StaffMember.user_id)
        .join(ProjectAssignment, ProjectAssignment.staff_id == StaffMember.id)
        .where(
            ProjectAssignment.project_id == project_id,
            ProjectAssignment.role.in_(["manager", "signing_partner"]),
            ProjectAssignment.is_deleted == False,  # noqa: E712
        )
    )
    result = await db.execute(stmt)
    user_ids = [row[0] for row in result.all() if row[0] is not None]
    return user_ids
