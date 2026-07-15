"""Formula Runtime Outbox — 事务内写入 + 幂等发布 + 失败重试。

核心契约（design §8 / P9）：
- write_outbox_event() 在同一事务内写入 outbox 记录（不 commit）
- publish_pending_events() 在事务提交后幂等发布未交付事件
- 重试逻辑：递增 attempts，记录 last_error，delivered_at 标记已交付

event_key 唯一约束保证：
1. 同一 run 同一事件不重复写入
2. 发布侧幂等——event_key 相同的消息只交付一次
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import FormulaRuntimeOutbox

logger = logging.getLogger(__name__)

# ─── 最大重试次数 ───────────────────────────────────────────────────────────

MAX_DELIVERY_ATTEMPTS = 5


# ─── 事务内写入（同事务，不 commit）─────────────────────────────────────────


async def write_outbox_event(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    event_type: str,
    event_key: str,
    payload: dict[str, Any] | None = None,
) -> FormulaRuntimeOutbox:
    """在当前事务中写入一条 outbox 事件（不 commit）。

    使用 INSERT ... ON CONFLICT (event_key) DO NOTHING 实现幂等：
    - 若 event_key 已存在，不重复写入（事务安全）
    - 调用方可在 apply_many 同事务内多次调用，保证原子性

    Returns:
        写入或已存在的 FormulaRuntimeOutbox 实例。
    """
    if payload is None:
        payload = {}

    # 幂等 INSERT: ON CONFLICT DO NOTHING
    stmt = (
        pg_insert(FormulaRuntimeOutbox)
        .values(
            id=uuid.uuid4(),
            event_key=event_key,
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            attempts=0,
            delivered_at=None,
            last_error=None,
        )
        .on_conflict_do_nothing(index_elements=["event_key"])
    )
    await session.execute(stmt)
    await session.flush()

    # 返回该 event_key 对应的记录（无论新插入还是已存在）
    result = await session.execute(
        select(FormulaRuntimeOutbox).where(
            FormulaRuntimeOutbox.event_key == event_key
        )
    )
    return result.scalar_one()


# ─── 提交后幂等发布 ─────────────────────────────────────────────────────────


async def publish_pending_events(
    session: AsyncSession,
    *,
    run_id: uuid.UUID | None = None,
    publisher: Any | None = None,
    batch_size: int = 50,
) -> int:
    """发布未交付的 outbox 事件（幂等、可重试）。

    Args:
        session: 独立的 session（非业务事务），publisher 发布后标记 delivered_at。
        run_id: 可选，限定只发布某个 run 的事件。
        publisher: 可选的发布回调 — async callable(event_type, payload) -> None。
                   若为 None，则仅标记 delivered（适用于测试或无下游消费者场景）。
        batch_size: 每批处理上限。

    Returns:
        本次成功发布（或已超最大重试）的事件数量。
    """
    # 查询待发布事件
    stmt = (
        select(FormulaRuntimeOutbox)
        .where(
            FormulaRuntimeOutbox.delivered_at.is_(None),
            FormulaRuntimeOutbox.attempts < MAX_DELIVERY_ATTEMPTS,
        )
        .order_by(FormulaRuntimeOutbox.created_at)
        .limit(batch_size)
    )
    if run_id is not None:
        stmt = stmt.where(FormulaRuntimeOutbox.run_id == run_id)

    result = await session.execute(stmt)
    events = list(result.scalars().all())

    delivered_count = 0
    for event in events:
        try:
            if publisher is not None:
                await publisher(event.event_type, event.payload)

            # 标记已交付
            event.delivered_at = datetime.now(timezone.utc)
            event.attempts += 1
            delivered_count += 1

        except Exception as exc:
            # 递增 attempts，记录 last_error
            event.attempts += 1
            event.last_error = str(exc)[:500]
            logger.warning(
                "Outbox delivery failed for event_key=%s (attempt %d): %s",
                event.event_key,
                event.attempts,
                str(exc)[:200],
            )

    await session.flush()
    return delivered_count


# ─── 查询 helpers ─────────────────────────────────────────────────────────


async def get_events_by_run(
    session: AsyncSession,
    run_id: uuid.UUID,
) -> list[FormulaRuntimeOutbox]:
    """获取某个 run 的所有 outbox 事件。"""
    result = await session.execute(
        select(FormulaRuntimeOutbox)
        .where(FormulaRuntimeOutbox.run_id == run_id)
        .order_by(FormulaRuntimeOutbox.created_at)
    )
    return list(result.scalars().all())


async def count_undelivered(
    session: AsyncSession,
    run_id: uuid.UUID | None = None,
) -> int:
    """统计未交付事件数量。"""
    from sqlalchemy import func as sa_func

    stmt = select(sa_func.count(FormulaRuntimeOutbox.id)).where(
        FormulaRuntimeOutbox.delivered_at.is_(None)
    )
    if run_id is not None:
        stmt = stmt.where(FormulaRuntimeOutbox.run_id == run_id)

    result = await session.execute(stmt)
    return result.scalar_one()
