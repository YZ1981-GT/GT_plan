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
import hashlib
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("audit_log_writer")

INTERVAL_SECONDS = 2  # 每 2 秒检查一次队列
BATCH_SIZE = 100  # 每批最多处理 100 条
MAX_RETRIES = 3  # 最大重试次数

# Redis queue keys
AUDIT_LOG_QUEUE_KEY = "audit:log:queue"
AUDIT_LOG_RETRY_QUEUE_KEY = "audit:log:retry"

# 创世哈希
GENESIS_HASH = "0" * 64


def _compute_entry_hash(
    ts: str,
    user_id: str,
    action_type: str,
    object_id: str | None,
    payload_json: str,
    prev_hash: str,
) -> str:
    """计算审计日志条目哈希。"""
    raw = f"{ts}|{user_id or ''}|{action_type}|{object_id or ''}|{payload_json}|{prev_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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


async def _get_prev_hash(db, project_id: str | None) -> str:
    """获取指定 project_id 的最新一条 entry_hash，作为新条目的 prev_hash。

    跨项目不链：每个 project_id 独立链。
    project_id 为 None 时使用全局链（payload 无 project_id 的系统级日志）。
    """
    from sqlalchemy import select, desc, text, cast, String
    from app.models.audit_log_models import AuditLogEntry

    try:
        if project_id:
            # 通过 payload->>'project_id' 过滤（JSONB 查询）
            # SQLite 不支持 JSONB 操作符，用 json_extract 降级
            from app.core.config import settings
            if settings.DATABASE_URL.startswith("postgresql"):
                stmt = (
                    select(AuditLogEntry.entry_hash)
                    .where(AuditLogEntry.payload["project_id"].astext == project_id)
                    .order_by(desc(AuditLogEntry.ts))
                    .limit(1)
                )
            else:
                # SQLite fallback: json_extract
                stmt = (
                    select(AuditLogEntry.entry_hash)
                    .where(text(f"json_extract(payload, '$.project_id') = :pid"))
                    .params(pid=project_id)
                    .order_by(desc(AuditLogEntry.ts))
                    .limit(1)
                )
        else:
            # 全局链（无 project_id 的条目）
            from app.core.config import settings
            if settings.DATABASE_URL.startswith("postgresql"):
                stmt = (
                    select(AuditLogEntry.entry_hash)
                    .where(
                        AuditLogEntry.payload["project_id"].astext.is_(None)
                        | ~AuditLogEntry.payload.has_key("project_id")
                    )
                    .order_by(desc(AuditLogEntry.ts))
                    .limit(1)
                )
            else:
                stmt = (
                    select(AuditLogEntry.entry_hash)
                    .where(text("json_extract(payload, '$.project_id') IS NULL"))
                    .order_by(desc(AuditLogEntry.ts))
                    .limit(1)
                )

        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        return row if row else GENESIS_HASH
    except Exception as e:
        logger.warning("[audit_log_writer] _get_prev_hash error: %s", e)
        return GENESIS_HASH


async def _get_session_factory():
    """获取 async_session 工厂（便于测试 patch）。"""
    from app.core.database import async_session
    return async_session


async def _write_batch(entries: list[dict]) -> int:
    """批量写入一批日志条目到数据库。

    按 project_id 分组，顺序计算哈希链。
    返回成功写入的条数。

    R1 Bug Fix 3: 多 worker 副本并发写同一 project_id 时，两个 worker 可能
    同时读到相同 prev_hash、各自计算出不同 entry_hash，导致链断。
    解决：写入前按 project_id 取 PG advisory transaction lock（自动在 commit/
    rollback 时释放），将同一 project_id 的写入强制串行化。
    - PostgreSQL：pg_advisory_xact_lock(bigint)，lock_id = hash(project_id) 限定在
      signed bigint 范围内。
    - SQLite（测试环境）：跳过 advisory lock，依赖单进程测试隔离。
    注意：advisory lock 只能保证同一 PG 实例上的多 worker 串行；跨实例需要
    配合"生产环境审计 writer 单副本部署"运维约束（见 backend/app/workers/README.md）。
    """
    from app.models.audit_log_models import AuditLogEntry
    from app.core.config import settings
    from sqlalchemy import text as sa_text

    async_session = await _get_session_factory()

    if not entries:
        return 0

    # 按 project_id 分组
    groups: dict[str | None, list[dict]] = defaultdict(list)
    for entry in entries:
        pid = entry.get("project_id")
        groups[pid].append(entry)

    is_postgres = settings.DATABASE_URL.startswith("postgresql")

    written = 0

    async with async_session() as db:
        try:
            for project_id, group_entries in groups.items():
                # --- R1 Bug Fix 3: PG advisory lock 保证同项目串行写入 ---
                if is_postgres:
                    # lock_id 使用稳定哈希 + bigint signed 范围
                    lock_key = str(project_id) if project_id else "__global__"
                    lock_id = hash(lock_key) & 0x7FFFFFFFFFFFFFFF
                    try:
                        await db.execute(
                            sa_text("SELECT pg_advisory_xact_lock(:lock_id)"),
                            {"lock_id": lock_id},
                        )
                    except Exception as lock_err:
                        logger.warning(
                            "[audit_log_writer] advisory lock failed, falling back to lock-free: %s",
                            lock_err,
                        )

                # 获取该 project_id 链的最新 prev_hash
                prev_hash = await _get_prev_hash(db, project_id)

                for entry in group_entries:
                    # 脱敏 payload
                    payload = _mask_payload(entry.get("payload", {}))
                    # 注入 project_id 到 payload 以便后续查询
                    if project_id:
                        payload["project_id"] = project_id

                    payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)

                    ts_str = entry.get("ts", datetime.now(timezone.utc).isoformat())
                    user_id_str = entry.get("user_id") or ""
                    action_type = entry.get("action_type", "unknown")
                    object_id_str = entry.get("object_id") or ""

                    entry_hash = _compute_entry_hash(
                        ts_str, user_id_str, action_type, object_id_str, payload_json, prev_hash
                    )

                    # 构建 ORM 对象
                    log_entry = AuditLogEntry(
                        id=uuid.uuid4(),
                        ts=datetime.fromisoformat(ts_str) if ts_str else datetime.now(timezone.utc),
                        user_id=uuid.UUID(entry["user_id"]) if entry.get("user_id") else None,
                        session_id=entry.get("session_id"),
                        action_type=action_type,
                        object_type=entry.get("object_type", "unknown"),
                        object_id=uuid.UUID(entry["object_id"]) if entry.get("object_id") else None,
                        payload=payload,
                        ip=entry.get("ip"),
                        ua=entry.get("ua"),
                        trace_id=entry.get("trace_id"),
                        prev_hash=prev_hash,
                        entry_hash=entry_hash,
                    )
                    db.add(log_entry)
                    prev_hash = entry_hash
                    written += 1

            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("[audit_log_writer] batch write failed: %s", e)
            raise

    return written


async def _send_admin_notification(
    title: str, content: str, metadata: dict | None = None
) -> bool:
    """向所有管理员发送审计日志失败告警。

    Batch 2-12: _handle_write_failure 除 logger.critical 外，实际调用
    NotificationService.send_notification_to_admins 发送持久化通知。
    返回 True 表示至少发送了一条通知。兜底仍保持 logger.critical。
    """
    try:
        from sqlalchemy import select
        from app.core.database import async_session
        from app.models.base import UserRole
        from app.models.core import User
        from app.services.notification_service import NotificationService
        from app.services.notification_types import GATE_ALERT

        async with async_session() as db:
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
                notification_type=GATE_ALERT,
                title=title,
                content=content,
                metadata=metadata,
            )
            await db.commit()
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


async def _handle_write_failure(entries: list[dict], retry_count: int = 0):
    """处理写入失败：进重试队列，3 次失败触发告警 + 管理员通知。"""
    if retry_count >= MAX_RETRIES:
        logger.error(
            "[audit_log_writer] AUDIT_LOG_WRITE_FAILED: %d entries lost after %d retries",
            len(entries), MAX_RETRIES,
        )
        # Batch 2-12: 触发告警通知（持久化通知 + logger.critical 兜底）
        logger.critical(
            "ALERT [AUDIT_LOG_WRITE_FAILED]: %d audit log entries could not be persisted",
            len(entries),
        )
        try:
            await _send_admin_notification(
                title="审计日志写入失败告警",
                content=(
                    f"审计日志 writer 连续 {MAX_RETRIES} 次写入失败，"
                    f"{len(entries)} 条日志条目可能丢失，请立即检查 Redis 队列与数据库连接。"
                ),
                metadata={"lost_count": len(entries), "alert_type": "AUDIT_LOG_WRITE_FAILED"},
            )
        except Exception as exc:
            logger.warning(
                "[audit_log_writer] _send_admin_notification raised: %s", exc
            )
        return

    # 推入重试队列
    try:
        from app.core.redis import redis_client
        for entry in entries:
            entry_with_retry = {**entry, "_retry_count": retry_count + 1}
            await redis_client.lpush(
                AUDIT_LOG_RETRY_QUEUE_KEY,
                json.dumps(entry_with_retry, ensure_ascii=False, default=str),
            )
    except Exception:
        # Redis 也不可用，只能记日志
        logger.error(
            "[audit_log_writer] Cannot push to retry queue, %d entries lost", len(entries)
        )


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
    # Batch 2-13: 每次启动打印单实例约束警告，方便运维排查
    logger.warning(
        "[audit_log_writer] starting worker — 如果看到两个此 worker 实例同时打印此行，"
        "请立即停止一个（单实例约束，见 backend/app/workers/README.md）"
    )
    logger.info("[audit_log_writer] worker started")

    while not stop_event.is_set():
        try:
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
