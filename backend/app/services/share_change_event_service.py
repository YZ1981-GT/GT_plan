"""share_change_event_service — 动态股比变动事件 CRUD + G7 幂等归一。

spec: consol-node-key-isolation-and-shared-context 任务 9.1~9.2
设计: §十三（ADR-CNSC-009~010）

核心语义：
- list_events: 按 (effective_date, sequence, id) 排序返回
- create_event: 手动创建（source_type='manual'）
- upsert_from_g7: G7 来源幂等 upsert（按 source identity 去重）
- approve/revoke: 状态转换
- delete_event: 仅 draft 可删
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, and_, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.share_change_event_models import ShareChangeEvent

logger = logging.getLogger(__name__)


async def list_events(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    company_code: str | None = None,
) -> list[ShareChangeEvent]:
    """列出项目/年度的股比事件，按排序键 (effective_date, sequence, id) 排序。"""
    conditions = [
        ShareChangeEvent.project_id == project_id,
        ShareChangeEvent.year == year,
    ]
    if company_code:
        conditions.append(ShareChangeEvent.company_code == company_code)

    stmt = (
        select(ShareChangeEvent)
        .where(and_(*conditions))
        .order_by(
            ShareChangeEvent.company_code,
            ShareChangeEvent.effective_date.asc().nulls_last(),
            ShareChangeEvent.sequence.asc(),
            ShareChangeEvent.id.asc(),
        )
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_event(
    db: AsyncSession, event_id: UUID,
) -> ShareChangeEvent | None:
    """按 ID 获取单个事件。"""
    return await db.get(ShareChangeEvent, event_id)


async def create_event(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    company_code: str,
    node_key: str | None = None,
    effective_date: Any = None,
    sequence: int = 0,
    before_ratio: Decimal | None = None,
    after_ratio: Decimal | None = None,
    change_type: str | None = None,
    amount: Decimal | None = None,
    equity_adjustment: Decimal | None = None,
    source_type: str = "manual",
    source_row_id: str | None = None,
    source_sheet_key: str | None = None,
    detail: dict | None = None,
    created_by: UUID | None = None,
) -> ShareChangeEvent:
    """创建新的股比变动事件。"""
    ratio_delta = None
    if before_ratio is not None and after_ratio is not None:
        ratio_delta = after_ratio - before_ratio

    event = ShareChangeEvent(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        company_code=company_code,
        node_key=node_key,
        effective_date=effective_date,
        sequence=sequence,
        before_ratio=before_ratio,
        after_ratio=after_ratio,
        ratio_delta=ratio_delta,
        change_type=change_type,
        amount=amount,
        equity_adjustment=equity_adjustment,
        source_type=source_type,
        source_row_id=source_row_id,
        source_sheet_key=source_sheet_key,
        review_status="draft",
        calculation_version=0,
        detail=detail,
        created_by=created_by,
    )
    db.add(event)
    await db.flush()
    return event


async def upsert_from_g7(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    suggestions: list[dict[str, Any]],
    created_by: UUID | None = None,
) -> dict[str, int]:
    """将 G7-10 建议归一为事件并幂等 upsert。

    每条 suggestion 必须有 company_code + source_type + source_row_id（来源行 identity）。
    重复来源行更新已有事件而非追加。

    并发安全：INSERT 冲突唯一约束时在 SAVEPOINT 内回滚并转为 UPDATE（防 SELECT→INSERT 竞态）。

    返回 {"created": N, "updated": N, "skipped": N}。
    """
    created = 0
    updated = 0
    skipped = 0

    for suggestion in suggestions:
        company_code = suggestion.get("company_code", "")
        source_type = suggestion.get("source_type") or suggestion.get("type") or "g7"
        source_row_id = suggestion.get("source_row_id") or suggestion.get("id") or ""

        if not company_code or not source_row_id:
            skipped += 1
            continue

        before_ratio = _to_decimal(suggestion.get("before_ratio"))
        after_ratio = _to_decimal(suggestion.get("after_ratio"))
        ratio_delta = None
        if before_ratio is not None and after_ratio is not None:
            ratio_delta = after_ratio - before_ratio

        now = datetime.now(timezone.utc)

        # 先尝试 SELECT 已有事件
        lookup_stmt = select(ShareChangeEvent).where(
            and_(
                ShareChangeEvent.project_id == project_id,
                ShareChangeEvent.year == year,
                ShareChangeEvent.company_code == company_code,
                ShareChangeEvent.source_type == source_type,
                ShareChangeEvent.source_row_id == source_row_id,
            )
        )
        existing = (await db.execute(lookup_stmt)).scalar_one_or_none()

        if existing is not None:
            _update_event_fields(existing, suggestion, before_ratio, after_ratio, ratio_delta, now)
            updated += 1
        else:
            # 尝试 INSERT；并发时唯一约束冲突则回滚 SAVEPOINT 并转为 UPDATE
            try:
                async with db.begin_nested():
                    event = ShareChangeEvent(
                        id=uuid.uuid4(),
                        project_id=project_id,
                        year=year,
                        company_code=company_code,
                        node_key=suggestion.get("node_key"),
                        effective_date=None,
                        sequence=0,
                        before_ratio=before_ratio,
                        after_ratio=after_ratio,
                        ratio_delta=ratio_delta,
                        change_type=suggestion.get("change_type"),
                        amount=_to_decimal(suggestion.get("amount")),
                        equity_adjustment=_to_decimal(suggestion.get("equity_adjustment")),
                        source_type=source_type,
                        source_row_id=source_row_id,
                        source_sheet_key=suggestion.get("source_sheet", suggestion.get("source_sheet_key")),
                        review_status="draft",
                        calculation_version=0,
                        detail=_build_detail(suggestion),
                        created_by=created_by,
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(event)
                    await db.flush()
                created += 1
            except IntegrityError:
                # 并发 INSERT 冲突——另一个请求先创建了同来源事件，转为 UPDATE
                logger.info(
                    "upsert_from_g7 并发冲突，转为 UPDATE: company=%s source=%s/%s",
                    company_code, source_type, source_row_id,
                )
                existing = (await db.execute(lookup_stmt)).scalar_one_or_none()
                if existing is not None:
                    _update_event_fields(existing, suggestion, before_ratio, after_ratio, ratio_delta, now)
                    updated += 1
                else:
                    skipped += 1

    await db.flush()
    return {"created": created, "updated": updated, "skipped": skipped}


async def approve_event(
    db: AsyncSession, event_id: UUID,
) -> ShareChangeEvent | None:
    """将事件从 draft 转为 approved。"""
    event = await db.get(ShareChangeEvent, event_id)
    if event is None:
        return None
    if event.review_status != "draft":
        raise ValueError(f"只能审批 draft 状态的事件，当前状态: {event.review_status}")
    event.review_status = "approved"
    event.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return event


async def revoke_event(
    db: AsyncSession, event_id: UUID,
) -> ShareChangeEvent | None:
    """将事件从 approved 转为 revoked。"""
    event = await db.get(ShareChangeEvent, event_id)
    if event is None:
        return None
    if event.review_status != "approved":
        raise ValueError(f"只能撤回 approved 状态的事件，当前状态: {event.review_status}")
    event.review_status = "revoked"
    event.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return event


async def delete_event(
    db: AsyncSession, event_id: UUID,
) -> bool:
    """删除 draft 事件。非 draft 拒绝。"""
    event = await db.get(ShareChangeEvent, event_id)
    if event is None:
        return False
    if event.review_status != "draft":
        raise ValueError(f"只能删除 draft 状态的事件，当前状态: {event.review_status}")
    await db.delete(event)
    await db.flush()
    return True


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _update_event_fields(
    existing: ShareChangeEvent,
    suggestion: dict[str, Any],
    before_ratio: Decimal | None,
    after_ratio: Decimal | None,
    ratio_delta: Decimal | None,
    now: datetime,
) -> None:
    """更新已有事件的字段（保留 id 和 review_status）。"""
    existing.before_ratio = before_ratio
    existing.after_ratio = after_ratio
    existing.ratio_delta = ratio_delta
    existing.change_type = suggestion.get("change_type")
    existing.amount = _to_decimal(suggestion.get("amount"))
    existing.equity_adjustment = _to_decimal(suggestion.get("equity_adjustment"))
    existing.source_sheet_key = suggestion.get("source_sheet", suggestion.get("source_sheet_key"))
    existing.node_key = suggestion.get("node_key")
    existing.detail = _build_detail(suggestion)
    existing.updated_at = now


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        d = Decimal(str(value))
        return d if d.is_finite() else None
    except Exception:
        return None


def _build_detail(suggestion: dict[str, Any]) -> dict | None:
    """从 G7 suggestion 中提取扩展字段。"""
    detail: dict[str, Any] = {}
    for key in (
        "adj_capital_reserve", "adj_surplus_reserve", "adj_retained_earnings",
        "target_hint", "note", "company_name",
    ):
        val = suggestion.get(key)
        if val is not None:
            detail[key] = val
    return detail or None
