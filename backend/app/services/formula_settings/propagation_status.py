"""公式变更传播状态（spec formula-management-repair-closure R1.3）。

数据源就是公式域 outbox 行（``import_event_outbox``，``event_type = formula_config.changed``、
``payload.origin = formula_settings_outbox``）与死信表 ``event_outbox_dlq``，不另建作业表。
origin 在 Python 里过滤（不依赖 PG JSON 操作符，SQLite 测试同一份代码）。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_schemas import EventType
from app.models.dataset_models import EventOutboxDLQ, ImportEventOutbox, OutboxStatus
from app.services.formula_settings.outbox import ORIGIN

#: 只看最近这么多条公式变更事件（足够覆盖一次全局发布 + 若干次项目保存）
WINDOW = 200
#: 失败明细最多返回条数
MAX_FAILURES = 20

_DOMAIN_LABELS = {
    "report": "报表", "tb_detail": "试算表明细", "cross_check": "表间审核", "wp": "底稿",
    "note": "附注", "consol_note": "合并附注", "push": "推送规则",
}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _status_value(status: Any) -> str:
    return status.value if isinstance(status, OutboxStatus) else str(status or "")


async def propagation_status(db: AsyncSession, project_id: uuid.UUID, *,
                             max_attempts: int | None = None) -> dict[str, Any]:
    """本项目最近公式变更的传播结果：计数、失败明细、未处理死信数、总体状态。"""
    if max_attempts is None:
        from app.core.config import settings

        max_attempts = int(getattr(settings, "LEDGER_IMPORT_OUTBOX_MAX_RETRY_ATTEMPTS", 0) or 0)
    rows = (await db.execute(
        sa.select(ImportEventOutbox)
        .where(ImportEventOutbox.project_id == project_id,
               ImportEventOutbox.event_type == EventType.FORMULA_CONFIG_CHANGED.value)
        .order_by(ImportEventOutbox.created_at.desc())
        .limit(WINDOW)
    )).scalars().all()
    mine = [r for r in rows if isinstance(r.payload, dict) and r.payload.get("origin") == ORIGIN]

    counts = {"pending": 0, "failed": 0, "published": 0}
    exhausted = 0
    failures: list[dict[str, Any]] = []
    last_published: datetime | None = None
    for row in mine:
        status = _status_value(row.status)
        counts[status] = counts.get(status, 0) + 1
        if status == OutboxStatus.published.value and row.published_at is not None:
            last_published = max(last_published, row.published_at) if last_published else row.published_at
        if status != OutboxStatus.failed.value:
            continue
        gave_up = bool(max_attempts) and int(row.attempt_count or 0) >= max_attempts
        exhausted += int(gave_up)
        if len(failures) < MAX_FAILURES:
            domain = str((row.payload or {}).get("domain") or "")
            failures.append({
                "outbox_id": str(row.id), "domain": domain, "domain_label": _DOMAIN_LABELS.get(domain, domain),
                "source": (row.payload or {}).get("source") or "",
                "slot_count": len((row.payload or {}).get("slot_keys") or []),
                "attempt_count": int(row.attempt_count or 0), "gave_up": gave_up,
                "last_error": row.last_error or "", "created_at": _iso(row.created_at),
            })

    dlq_rows = (await db.execute(
        sa.select(EventOutboxDLQ.payload)
        .where(EventOutboxDLQ.project_id == project_id,
               EventOutboxDLQ.event_type == EventType.FORMULA_CONFIG_CHANGED.value,
               EventOutboxDLQ.resolved_at.is_(None))
    )).scalars().all()
    dead_letter = sum(1 for p in dlq_rows if isinstance(p, dict) and p.get("origin") == ORIGIN)

    if counts["failed"]:
        state = "failed"
    elif counts["pending"]:
        state = "running"
    else:
        state = "idle"
    return {
        "project_id": str(project_id), "window": WINDOW, "state": state, "counts": counts,
        "retrying": counts["failed"] - exhausted, "gave_up": exhausted, "dead_letter": dead_letter,
        "max_attempts": max_attempts or None, "last_published_at": _iso(last_published),
        "recent_failures": failures,
    }
