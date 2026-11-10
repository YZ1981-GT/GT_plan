"""公式耐久传播状态：先按来源和精确条件筛选，再取窗口；派发与业务回执分开。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_schemas import EventType
from app.models.dataset_models import EventOutboxDLQ, ImportEventOutbox, OutboxStatus
from app.services.formula_settings.outbox import ORIGIN, RECEIPT_KEY

#: 只看最近这么多条公式变更事件（足够覆盖一次全局发布 + 若干次项目保存）
WINDOW = 200
#: 失败明细最多返回条数
MAX_FAILURES = 20

_DOMAIN_LABELS = {
    "report": "报表", "tb_detail": "试算表明细", "cross_check": "表间审核", "wp": "底稿",
    "note": "附注", "consol_note": "合并附注", "push": "推送规则",
}
_OPERATION_STATUSES = {"queued", "running", "succeeded", "partial", "failed", "stale", "cancelled"}
_ACTION_STATUSES = _OPERATION_STATUSES | {"unknown", "skipped", "no_consumer", "marked_stale", "check_failed"}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _status_value(status: Any) -> str:
    return status.value if isinstance(status, OutboxStatus) else str(status or "")


def _filters(model, project_id, *, year, domain, publish_token, outbox_id):
    """JSON 下标由 SQLAlchemy 按 PG / SQLite 方言编译，不在 Python 窗口内过滤。"""
    filters = [model.project_id == project_id,
               model.event_type == EventType.FORMULA_CONFIG_CHANGED.value,
               model.payload["origin"].as_string() == ORIGIN]
    if year is not None:
        filters.append(model.year == year)
    if domain is not None:
        filters.append(model.payload["domain"].as_string() == domain)
    if publish_token is not None:
        filters.append(model.payload["publish_token"].as_string() == publish_token)
    if outbox_id is not None:
        column = model.original_event_id if model is EventOutboxDLQ else model.id
        filters.append(column == outbox_id)
    return filters


def _receipt_of(row) -> dict[str, Any]:
    payload = row.payload if isinstance(row.payload, dict) else {}
    stored = payload.get(RECEIPT_KEY)
    stored = stored if isinstance(stored, dict) and stored.get("schema_version") == 1 else {}
    # 旧行只知道派发状态，没有业务证据，不能补造成功。
    valid = (stored.get("outbox_id") == str(row.id) and stored.get("year") == row.year
             and stored.get("domain") == payload.get("domain")
             and stored.get("publish_token") == payload.get("publish_token"))
    if not valid:
        stored = {}
    delivery_status = _status_value(row.status)
    action = stored.get("action_status")
    action_status = action if isinstance(action, str) and action in _ACTION_STATUSES else "unknown"
    if stored and delivery_status == OutboxStatus.failed.value:
        action_status = "failed"
    return {
        "outbox_id": str(row.id), "domain": payload.get("domain") or "", "year": row.year,
        "publish_token": payload.get("publish_token"), "delivery_status": delivery_status,
        "action_status": action_status,
        "handler_result": stored.get("handler_result") if isinstance(stored.get("handler_result"), dict) else {},
        "operation_id": stored.get("operation_id"), "operation_status": None,
        "last_error": row.last_error or stored.get("last_error"),
    }


async def _attach_operations(db: AsyncSession, project_id: uuid.UUID, receipts: list[dict]) -> None:
    wanted: set[tuple[uuid.UUID, int]] = set()
    linked: list[tuple[dict, tuple[uuid.UUID, int]]] = []
    for receipt in receipts:
        if receipt["domain"] != "consol_note":
            continue
        published = receipt["delivery_status"] == OutboxStatus.published.value
        if not receipt["operation_id"]:
            if published and receipt["action_status"] in _OPERATION_STATUSES:
                receipt["action_status"] = "unknown"
            continue
        # 先撤下旧的任务状态；缺年度、坏 UUID 或查无任务都不能保留 queued/succeeded。
        if published:
            receipt["action_status"] = "unknown"
        try:
            operation_id = uuid.UUID(str(receipt["operation_id"]))
        except (TypeError, ValueError):
            continue
        if receipt["year"] is not None:
            key = (operation_id, receipt["year"])
            wanted.add(key)
            linked.append((receipt, key))
    if not wanted:
        return
    from app.models.consol_operation_models import ConsolOperation

    operations = (await db.execute(sa.select(ConsolOperation).where(
        ConsolOperation.project_id == project_id,
        sa.or_(*(sa.and_(ConsolOperation.id == oid, ConsolOperation.year == year) for oid, year in wanted)),
    ))).scalars().all()
    by_id = {(op.id, op.year): op for op in operations}
    for receipt, key in linked:
        operation = by_id.get(key)
        status = operation.status if operation is not None else None
        receipt["operation_status"] = status
        # outbox 若失败，业务仍保留 failed；任务状态单独可见。published 才由真实终态更新业务状态。
        if receipt["delivery_status"] == OutboxStatus.published.value:
            receipt["action_status"] = status if status in _OPERATION_STATUSES else "unknown"
        if operation is not None:
            receipt["operation_errors"] = operation.errors


async def propagation_status(db: AsyncSession, project_id: uuid.UUID, *,
                             max_attempts: int | None = None, year: int | None = None,
                             domain: str | None = None, publish_token: str | None = None,
                             outbox_id: uuid.UUID | None = None) -> dict[str, Any]:
    """兼容既有字段；可按年度、域、发布 token 或 outbox 主键精确查看。"""
    if max_attempts is None:
        from app.core.config import settings

        max_attempts = int(getattr(settings, "LEDGER_IMPORT_OUTBOX_MAX_RETRY_ATTEMPTS", 0) or 0)
    filters = dict(year=year, domain=domain, publish_token=publish_token, outbox_id=outbox_id)
    mine = (await db.execute(sa.select(ImportEventOutbox).where(
        *_filters(ImportEventOutbox, project_id, **filters),
    ).order_by(ImportEventOutbox.created_at.desc(), ImportEventOutbox.id.desc()).limit(WINDOW))).scalars().all()

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
            payload = row.payload or {}
            row_domain = str(payload.get("domain") or "")
            failures.append({
                "outbox_id": str(row.id), "domain": row_domain,
                "domain_label": _DOMAIN_LABELS.get(row_domain, row_domain),
                "source": payload.get("source") or "", "slot_count": len(payload.get("slot_keys") or []),
                "attempt_count": int(row.attempt_count or 0), "gave_up": gave_up,
                "last_error": row.last_error or "", "created_at": _iso(row.created_at),
            })
    dead_letter = int(await db.scalar(sa.select(sa.func.count()).select_from(EventOutboxDLQ).where(
        *_filters(EventOutboxDLQ, project_id, **filters), EventOutboxDLQ.resolved_at.is_(None),
    )) or 0)
    receipts = [_receipt_of(row) for row in mine]
    await _attach_operations(db, project_id, receipts)
    action_counts: dict[str, int] = {}
    for receipt in receipts:
        action = receipt["action_status"]
        action_counts[action] = action_counts.get(action, 0) + 1
    business_pending = sum(1 for receipt in receipts if receipt["action_status"] in {"queued", "running"})
    state = "failed" if counts["failed"] else "running" if counts["pending"] or business_pending else "idle"
    return {
        "project_id": str(project_id), "window": WINDOW, "state": state, "counts": counts,
        "retrying": counts["failed"] - exhausted, "gave_up": exhausted, "dead_letter": dead_letter,
        "max_attempts": max_attempts or None, "last_published_at": _iso(last_published),
        "recent_failures": failures, "receipts": receipts, "action_counts": action_counts,
        "business_pending": business_pending,
        "has_pending_actions": bool(counts["pending"] or counts["failed"] - exhausted or business_pending),
    }
