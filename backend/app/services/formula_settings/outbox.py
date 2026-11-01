"""公式设置域的持久化 outbox 门面（S4 ADR-SDO-01/02/03）。

写入方在同一事务里调 ``record_changes`` 登记变化并就地标过期，路由 ``commit`` 后调
``publish_pending`` 交给后台投递。复用平台已有的 ``DurableEventOutboxService`` 与
``import_event_outbox`` 表，不建第二套事件表。

投递时直接调用 ``propagation.HANDLERS[domain](...)``，不经事件总线（总线会吞异常），
失败可重试、成功只一次。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_schemas import EventType
from app.services.workpaper_sync.outbox import (
    DurableEventOutboxService,
    PendingPublication,
    PublishReport,
)

logger = logging.getLogger(__name__)

#: 入队时用的 origin 标记，投递方按此区分旧路径和 outbox 路径
ORIGIN = "formula_settings_outbox"

#: Session.info 上的待发布清单键（与底稿同步域各自独立）
PENDING_SESSION_KEY = "formula_settings.outbox.pending"

#: 后台投递的并发信号量（进程内）
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    """惰性初始化：首次调用时创建。默认并发 4。"""
    global _semaphore
    if _semaphore is None:
        try:
            from app.core.config import settings
            concurrency = getattr(settings, "FORMULA_PROPAGATION_CONCURRENCY", 4) or 4
        except Exception:
            concurrency = 4
        _semaphore = asyncio.Semaphore(int(concurrency))
    return _semaphore


# ── 入队 ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FormulaChangeRecord:
    """一个项目在一个域里的公式变化记录。"""
    project_id: uuid.UUID
    domain: str
    slot_keys: list[str]
    source: str
    publish_id: str | None = None
    row_codes: list[str] | None = None  # report 域用


async def record_changes(
    db: AsyncSession,
    *,
    domain: str,
    events: Iterable[dict[str, Any]],
    source: str,
    publish_id: str | None = None,
) -> list[PendingPublication]:
    """在调用方事务内为每个有变化的项目入队一条耐久事件并就地标过期。

    ``events`` 格式与现有 ``publish_events`` 的参数一致：每个 dict 含
    ``project_id``, ``slot_keys``, 可选 ``domain``。

    只 flush 不 commit。返回待发布句柄列表。
    """
    from app.services.formula_settings.stale_marks import mark_in_txn

    publications: list[PendingPublication] = []
    events_list = list(events)
    if not events_list:
        return publications

    # 报表域：先失效反向索引（与 publish_events 同行为）
    effective_domain = domain
    if domain == "report" or any(ev.get("domain") == "report" for ev in events_list):
        try:
            from app.services.formula_reverse_index import invalidate_reverse_index
            invalidate_reverse_index()
        except Exception as exc:
            logger.warning("[formula_settings.outbox] 反向索引失效失败: %s", exc)

    for ev in events_list:
        slots = [s for s in (ev.get("slot_keys") or []) if s]
        if not slots:
            continue

        d = ev.get("domain") or domain
        project_id_raw = ev.get("project_id")
        if project_id_raw is None:
            continue
        project_id = uuid.UUID(str(project_id_raw))

        # 同事务标过期（ADR-SDO-03）
        await mark_in_txn(db, d, project_id, slots)

        # 构造 payload
        payload: dict[str, Any] = {
            "origin": ORIGIN,
            "domain": d,
            "slot_keys": slots[:200],  # 限制大小
            "source": source,
            "publish_token": publish_id or uuid.uuid4().hex,
        }
        if d == "report":
            payload["row_codes"] = sorted({s.partition(":")[2] for s in slots if ":" in s})

        # 入队（只 flush）
        pub = await DurableEventOutboxService.enqueue(
            db,
            event_type=EventType.FORMULA_CONFIG_CHANGED,
            project_id=project_id,
            year=None,  # year 由投递时现取
            payload=payload,
            remember=False,  # 我们用自己的 session key
        )
        publications.append(pub)

        # 挂到自己的 session 清单
        _remember(db, pub)

    return publications


def _remember(db: AsyncSession, pub: PendingPublication) -> None:
    """把句柄挂到 session.info 的公式域清单。"""
    info = getattr(db, "info", None)
    if not isinstance(info, dict):
        return
    bucket = info.setdefault(PENDING_SESSION_KEY, [])
    bucket.append(pub)


def _take_pending(db: AsyncSession) -> list[PendingPublication]:
    """取出并清空 session 上的公式域待发布清单。"""
    info = getattr(db, "info", None)
    if not isinstance(info, dict):
        return []
    bucket = info.pop(PENDING_SESSION_KEY, [])
    return list(bucket) if isinstance(bucket, list) else []


# ── 发布（路由 commit 之后调用）──────────────────────────────────────────────


async def publish_pending(db: AsyncSession) -> dict[str, Any]:
    """路由 commit 之后调用：取本会话登记的行，后台有界并发投递。

    立即返回已登记条数，不等投递完成。投递由 ``deliver`` 直接调用传播处理器，
    失败由 outbox_replay_worker 重放。
    """
    pending = _take_pending(db)
    if not pending:
        return {"queued": 0}

    sem = _get_semaphore()
    count = len(pending)

    async def _deliver_one(pub: PendingPublication) -> None:
        async with sem:
            try:
                from app.core.database import async_session
                async with async_session() as session:
                    await deliver(session, pub)
                    await session.commit()
            except Exception as exc:
                logger.warning(
                    "[formula_settings.outbox] 投递失败 outbox_id=%s, worker 将重放: %s",
                    pub.outbox_id, exc,
                )

    # 后台并发投递（不阻塞路由响应）
    for pub in pending:
        asyncio.ensure_future(_deliver_one(pub))

    return {"queued": count}


# ── 投递（直接调传播处理器，不经事件总线）──────────────────────────────────


async def deliver(db: AsyncSession, pub: PendingPublication) -> dict[str, Any]:
    """投递一条公式变更事件：直接调用传播处理器，不经事件总线。

    被 ``publish_pending`` 和 ``ImportEventOutboxService._deliver``（对
    FORMULA_CONFIG_CHANGED 事件类型分派）调用。

    成功经消费闸门只生效一次；失败让 outbox 行保持可重试。
    """
    from app.services.formula_settings.propagation import HANDLERS
    from app.services.import_event_outbox_service import ImportEventOutboxService

    # 读 outbox 行
    row = await ImportEventOutboxService.get(db, pub.outbox_id)
    if row is None:
        return {"skipped": "row_not_found"}

    payload = row.payload or {}
    domain = payload.get("domain", "")
    slot_keys = payload.get("slot_keys", [])
    project_id = row.project_id

    if not domain or not slot_keys:
        # 标为 published（空变更不重试）
        row.status = "published"
        await db.flush()
        return {"skipped": "empty_payload"}

    # 消费闸门
    claimed = await DurableEventOutboxService.begin_fanout(
        db,
        event_id=str(pub.outbox_id),
        project_id=project_id,
    )
    if not claimed:
        return {"skipped": "already_delivered"}

    # 取审计年度
    year = await _fetch_project_year(db, project_id)

    # 调传播处理器
    handler = HANDLERS.get(domain)
    result: dict[str, Any] = {}
    try:
        if handler:
            result = await handler(project_id, year, slot_keys)

        # stale_engine（反向索引失效 + 依赖图标下游过期）
        row_codes = payload.get("row_codes", [])
        if row_codes:
            await _stale_engine_for_formula_change(db, project_id, year, row_codes)

        # 标为 published
        row.status = "published"
        row.published_at = __import__("datetime").datetime.utcnow()
        await db.flush()

    except Exception:
        # 归还消费权，让 worker 重试
        await DurableEventOutboxService.abort_fanout(
            db, event_id=str(pub.outbox_id),
        )
        raise

    return {"delivered": True, "domain": domain, "handler_result": result}


async def _fetch_project_year(db: AsyncSession, project_id: uuid.UUID) -> int | None:
    """取项目审计年度（与 event_bus._backfill_year 同口径）。"""
    import sqlalchemy as sa
    from app.models.core import Project

    row = (await db.execute(
        sa.select(Project.audit_period_end).where(
            Project.id == project_id,
            Project.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()
    if row is None:
        return None
    try:
        return row.year
    except AttributeError:
        return None


async def _stale_engine_for_formula_change(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int | None,
    row_codes: list[str],
) -> None:
    """从 ``event_handlers._stale_engine_on_formula_config_changed`` 抽出的逻辑：
    反向索引失效 + 依赖图按报表行标下游过期。"""
    try:
        from app.services.formula_reverse_index import invalidate_reverse_index
        invalidate_reverse_index()
    except Exception:
        pass

    if not row_codes or year is None:
        return

    try:
        from app.services.stale_summary_aggregate import mark_downstream_stale
        await mark_downstream_stale(db, project_id=project_id, year=year, row_codes=row_codes)
    except Exception as exc:
        logger.warning(
            "[formula_settings.outbox] stale_engine 失败 project=%s: %s",
            project_id, exc,
        )
