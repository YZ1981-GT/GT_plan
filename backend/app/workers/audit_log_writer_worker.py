"""审计日志批量写入 Worker — 从 Redis 队列消费 + 哈希链落库

Refinement Round 1 — 需求 9：审计日志真实落库 + 不可篡改。

架构：
- 从 Redis List RPOP 批量取（最多 100 条/批）
- 按 project_id 分组，顺序计算 entry_hash（需要 prev_hash）
- 脱敏：写入前 payload 过 export_mask_service.mask_log_payload（若可用）
- 写失败进重试队列，3 次失败触发告警 AUDIT_LOG_WRITE_FAILED
- 降级模式：Redis 不可用时从 asyncio.Queue 消费
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_chain.canonical import (
    GENESIS_HASH,
    hash_v1 as _compute_entry_hash,
)
from app.services.audit_chain.worker import (
    QUARANTINE_PREFIX,
    quarantine_entries_by_chain,
    replay_quarantine,
    write_batch,
)

__all__ = [
    "AUDIT_LOG_QUEUE_KEY",
    "AUDIT_LOG_RETRY_QUEUE_KEY",
    "BATCH_SIZE",
    "GENESIS_HASH",
    "MAX_RETRIES",
    "QUARANTINE_PREFIX",
    "_compute_entry_hash",
    "_replay_quarantine",
    "_write_batch",
    "run",
]

logger = logging.getLogger("audit_log_writer")

INTERVAL_SECONDS = 2  # 每 2 秒检查一次队列
BATCH_SIZE = 100  # 每批最多处理 100 条
MAX_RETRIES = 3  # 最大重试次数

# Redis queue keys
AUDIT_LOG_QUEUE_KEY = "audit:log:queue"
AUDIT_LOG_RETRY_QUEUE_KEY = "audit:log:retry"

def _mask_payload(payload: dict) -> dict:
    """尝试脱敏 payload，mask_log_payload 不存在则跳过。"""
    try:
        from app.services.export_mask_service import export_mask_service
        # 使用 assistant 角色的脱敏规则（最严格）
        import copy
        masked = copy.deepcopy(payload)
        export_mask_service._apply_rules(masked, [
            "client_contact_phone",
            "client_contact_email",
            "bank_account_number",
            "client_id_number",
        ])
        return masked
    except Exception:
        return payload


async def _get_session_factory():
    """获取 async_session 工厂（便于测试 patch）。"""
    from app.core.database import async_session
    return async_session


async def _write_batch(entries: list[dict]) -> int:
    """逐链独立提交；失败链原样进入隔离区。"""
    if not entries:
        return 0
    session_factory = await _get_session_factory()
    from app.core.redis import redis_client

    return await write_batch(
        entries,
        session_factory=session_factory,
        redis_client=redis_client,
        mask_payload=_mask_payload,
    )


async def _replay_quarantine() -> int:
    """尝试重放每条隔离链，提交成功后才出列。"""
    session_factory = await _get_session_factory()
    from app.core.redis import redis_client

    return await replay_quarantine(
        session_factory=session_factory,
        redis_client=redis_client,
    )


async def _send_admin_notification(
    db: AsyncSession,
    title: str,
    content: str,
    metadata: dict | None = None,
) -> bool:
    """向所有管理员发送审计日志失败告警。

    Batch 2-12: _handle_write_failure 除 logger.critical 外，实际调用
    NotificationService.send_notification_to_admins 发送持久化通知。
    返回 True 表示至少发送了一条通知。兜底仍保持 logger.critical。

    Batch 3-8: 函数签名改为接收 session 参数，避免每次失败开新 session，
    短时高并发失败耗尽连接池。调用方负责 commit/rollback。

    Batch 3-2: notification_type 改为独立的 AUDIT_LOG_WRITE_FAILED（原误用
    GATE_ALERT 导致跳转到 gate-readiness 页找不到对应项目）。
    """
    try:
        from sqlalchemy import select
        from app.models.base import UserRole
        from app.models.core import User
        from app.services.notification_service import NotificationService
        from app.services.notification_types import AUDIT_LOG_WRITE_FAILED

        stmt = select(User.id).where(
            User.role == UserRole.admin,
            User.is_active == True,  # noqa: E712
            User.is_deleted == False,  # noqa: E712
        )
        admin_ids = [row[0] for row in (await db.execute(stmt)).all()]
        if not admin_ids:
            logger.warning(
                "[audit_log_writer] no admin users found for AUDIT_LOG_WRITE_FAILED notification"
            )
            return False

        svc = NotificationService(db)
        sent = await svc.send_notification_to_many(
            user_ids=admin_ids,
            notification_type=AUDIT_LOG_WRITE_FAILED,
            title=title,
            content=content,
            metadata=metadata,
        )
        logger.info(
            "[audit_log_writer] AUDIT_LOG_WRITE_FAILED admin notifications sent: recipients=%d sent=%d",
            len(admin_ids),
            sent,
        )
        return sent > 0
    except Exception as exc:
        logger.warning(
            "[audit_log_writer] send admin notification failed (falling back to log only): %s",
            exc,
        )
        return False


async def _fallback_preserve(entries: list[dict], retry_count: int) -> None:
    """Redis 不可用时把失败项放回进程队列，不静默丢弃。"""
    from app.services.audit_logger_enhanced import audit_logger

    queue = audit_logger._get_fallback_queue()
    for entry in entries:
        await queue.put({**entry, "_retry_count": retry_count})


async def _handle_write_failure(entries: list[dict], retry_count: int = 0):
    """非链类批量失败先重试，达到上限后转隔离区而非丢弃。"""
    terminal = retry_count >= MAX_RETRIES
    try:
        from app.core.redis import redis_client

        if terminal:
            await quarantine_entries_by_chain(redis_client, entries)
        else:
            for entry in entries:
                entry_with_retry = {**entry, "_retry_count": retry_count + 1}
                await redis_client.lpush(
                    AUDIT_LOG_RETRY_QUEUE_KEY,
                    json.dumps(entry_with_retry, ensure_ascii=False, default=str),
                )
            return
    except Exception as exc:
        logger.error(
            "[audit_log_writer] Redis unavailable; preserving %d entries in fallback queue: %s",
            len(entries),
            exc,
        )
        await _fallback_preserve(entries, retry_count)
        if not terminal:
            return

    logger.critical(
        "ALERT [AUDIT_LOG_WRITE_FAILED]: %d entries preserved after %d retries",
        len(entries),
        MAX_RETRIES,
    )
    try:
        from app.core.database import async_session

        async with async_session() as db:
            await _send_admin_notification(
                db,
                title="审计日志写入失败告警",
                content=(
                    f"审计日志 writer 连续 {MAX_RETRIES} 次写入失败，"
                    f"{len(entries)} 条日志已保留在隔离区或降级队列，请立即处理。"
                ),
                metadata={
                    "retry_count": MAX_RETRIES,
                    "quarantined_count": len(entries),
                    "alert_type": "AUDIT_LOG_WRITE_FAILED",
                },
            )
            await db.commit()
    except Exception as exc:
        logger.warning("[audit_log_writer] admin notification failed: %s", exc)


async def _consume_from_redis(redis_client) -> list[dict]:
    """从 Redis 队列批量取条目。"""
    entries = []
    for _ in range(BATCH_SIZE):
        raw = await redis_client.rpop(AUDIT_LOG_QUEUE_KEY)
        if raw is None:
            break
        try:
            entries.append(json.loads(raw))
        except json.JSONDecodeError:
            logger.warning("[audit_log_writer] invalid JSON in queue, skipping")
    return entries


async def _consume_retry_queue(redis_client) -> list[dict]:
    """从重试队列取条目。"""
    entries = []
    for _ in range(BATCH_SIZE // 2):  # 重试队列每次取一半
        raw = await redis_client.rpop(AUDIT_LOG_RETRY_QUEUE_KEY)
        if raw is None:
            break
        try:
            entries.append(json.loads(raw))
        except json.JSONDecodeError:
            pass
    return entries


async def _consume_from_fallback_queue() -> list[dict]:
    """从进程内降级队列取条目。"""
    entries = []
    try:
        from app.services.audit_logger_enhanced import audit_logger
        queue = audit_logger._fallback_queue
        if queue is None:
            return entries
        for _ in range(BATCH_SIZE):
            try:
                entry = queue.get_nowait()
                entries.append(entry)
            except asyncio.QueueEmpty:
                break
    except Exception:
        pass
    return entries


async def run(stop_event: asyncio.Event) -> None:
    """审计日志写入 Worker 主循环。

    - stop_event.set() 后退出循环
    - 异常不影响主应用，记录 warning 后继续下一周期
    """
    # Batch 3-5: 启动日志从 warning 降级为 info，附上 worker_id（host-pid），
    # 便于运维在日志聚合中看到同一 id 重复出现时立即识别出双实例 bug。
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    logger.info(
        "[audit_log_writer] worker started id=%s "
        "（单实例约束：同一 id 重复出现请检查部署，见 backend/app/workers/README.md）",
        worker_id,
    )

    rounds = 0
    while not stop_event.is_set():
        try:
            rounds += 1
            # 等待间隔或 stop_event
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=INTERVAL_SECONDS)
                break  # stop_event 被设置，退出
            except asyncio.TimeoutError:
                pass  # 正常到达间隔

            entries: list[dict] = []

            # 尝试从 Redis 消费
            try:
                from app.core.redis import redis_client
                await asyncio.wait_for(redis_client.ping(), timeout=0.3)

                # 主队列
                entries = await _consume_from_redis(redis_client)

                # 重试队列（如果主队列为空或有余量）
                if len(entries) < BATCH_SIZE:
                    retry_entries = await _consume_retry_queue(redis_client)
                    entries.extend(retry_entries)
            except Exception:
                # Redis 不可用，从降级队列消费
                entries = await _consume_from_fallback_queue()

            # 约每分钟尝试一次隔离区；没有主队列数据时也必须执行。
            if rounds % 30 == 0:
                replayed = await _replay_quarantine()
                if replayed:
                    logger.info(
                        "[audit_log_writer] replayed %d quarantined entries",
                        replayed,
                    )

            if not entries:
                continue

            # 分离重试计数
            retry_counts: dict[int, int] = {}
            clean_entries = []
            for i, entry in enumerate(entries):
                rc = entry.pop("_retry_count", 0)
                retry_counts[i] = rc
                clean_entries.append(entry)

            # 批量写入
            try:
                written = await _write_batch(clean_entries)
                if written > 0:
                    logger.debug("[audit_log_writer] wrote %d entries", written)
            except Exception as e:
                logger.warning("[audit_log_writer] write failed, queuing for retry: %s", e)
                # 按重试次数分组处理
                max_retry = max(retry_counts.values()) if retry_counts else 0
                await _handle_write_failure(clean_entries, max_retry)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("[audit_log_writer] loop error: %s", e)

    logger.info("[audit_log_writer] worker stopped")
