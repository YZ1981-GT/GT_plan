"""底稿审定数同步发布服务。

TB 核心写、幂等 ack 与 durable outbox 在同一事务；router commit 后只负责投递。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Iterable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import Adjustment, ReviewStatus, TbPublishAck
from app.models.audit_platform_schemas import EventPayload, EventType
from app.services.tb_audited_writer import PublishRowsResult, publish_rows
from app.services.workpaper_sync.outbox import DurableEventOutboxService


class TbPublishError(ValueError):
    def __init__(self, code: str, message: str, detail: Any = None):
        super().__init__(message)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class TbPublishResult:
    report: PublishRowsResult
    duplicate: bool
    related_adjustment_groups: tuple[str, ...]


async def validate_workpaper_adjustments_approved(
    db: AsyncSession,
    *,
    project_id: UUID,
    wp_id: UUID,
    account_codes: list[str],
) -> tuple[str, ...]:
    """相关底稿来源分录必须全部批准，方可发布审定数。"""
    rows = (await db.execute(sa.select(
        Adjustment.entry_group_id,
        Adjustment.adjustment_no,
        Adjustment.review_status,
        Adjustment.content_revision,
    ).where(
        Adjustment.project_id == project_id,
        Adjustment.origin == "workpaper",
        Adjustment.source_ref.like(f"{wp_id}:%"),
        Adjustment.account_code.in_(sorted(set(account_codes))),
        Adjustment.is_deleted == sa.false(),
    ))).all()
    groups: dict[UUID, dict[str, Any]] = {}
    for group_id, number, status, revision in rows:
        group = groups.setdefault(group_id, {
            "entry_group_id": str(group_id), "adjustment_no": number,
            "statuses": set(), "revisions": set(),
        })
        group["statuses"].add(getattr(status, "value", status))
        group["revisions"].add(int(revision or 1))
    blocked = []
    for group in groups.values():
        if group["statuses"] != {ReviewStatus.approved.value} or len(group["revisions"]) != 1:
            blocked.append({
                "entry_group_id": group["entry_group_id"],
                "adjustment_no": group["adjustment_no"],
                "statuses": sorted(group["statuses"]),
                "revisions": sorted(group["revisions"]),
            })
    if blocked:
        raise TbPublishError(
            "WORKPAPER_ADJUSTMENTS_NOT_APPROVED",
            "来源底稿存在尚未完成集中复核的调整分录，请先在调整分录大厅提交并批准",
            {"groups": blocked},
        )
    return tuple(sorted(str(group_id) for group_id in groups))


async def publish_workpaper_rows(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    wp_id: UUID,
    wp_code: str,
    rows: Iterable[dict[str, Any] | Any],
    publish_token: str,
    confirmed_by: UUID,
    amount_kinds: dict[str, str] | None = None,
) -> TbPublishResult:
    normalized_rows = list(rows)
    account_codes = [
        str((row.get("account_code") if isinstance(row, dict) else getattr(row, "account_code", "")) or "")
        for row in normalized_rows
    ]
    account_codes = [code for code in account_codes if code]
    groups = await validate_workpaper_adjustments_approved(
        db, project_id=project_id, wp_id=wp_id, account_codes=account_codes,
    )

    existing = (await db.execute(sa.select(TbPublishAck).where(
        TbPublishAck.publish_token == publish_token,
    ))).scalar_one_or_none()
    if existing is not None:
        if existing.project_id != project_id or existing.year != year or existing.wp_code != wp_code:
            raise TbPublishError("PUBLISH_TOKEN_CONFLICT", "发布令牌已被其他发布请求使用")
        duplicate = PublishRowsResult()
        duplicate.updated_account_codes.extend(account_codes[: int(existing.accounts_updated or 0)])
        return TbPublishResult(duplicate, True, groups)

    ack = TbPublishAck(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        wp_code=wp_code,
        publish_token=publish_token,
        confirmed_by=confirmed_by,
        accounts_updated=0,
    )
    db.add(ack)
    await db.flush()

    report = await publish_rows(
        db,
        project_id,
        year,
        normalized_rows,
        source=f"audit_determination:{wp_code}",
    )
    if report.skipped:
        raise TbPublishError(
            "TB_PUBLISH_INCOMPLETE",
            "审定数未完整写入试算表，已取消本次发布",
            {"skipped": [
                {"account_code": item.account_code, "reason": item.reason,
                 "company_codes": list(item.company_codes)}
                for item in report.skipped
            ]},
        )
    ack.accounts_updated = report.updated_count

    event_extra = {
        "wp_id": str(wp_id),
        "wp_code": wp_code,
        "trigger": "audit_determination_publish",
        "publish_confirmed": True,
        "publish_token": publish_token,
        "confirmed_by": str(confirmed_by),
        "tb_write_committed": True,
        "related_adjustment_groups": list(groups),
        **({"amount_kinds": dict(amount_kinds)} if amount_kinds else {}),
    }
    await DurableEventOutboxService.enqueue_event(db, EventPayload(
        event_type=EventType.WORKPAPER_SAVED,
        project_id=project_id,
        year=year,
        account_codes=report.updated_account_codes,
        extra=event_extra,
    ))
    await DurableEventOutboxService.enqueue_event(db, EventPayload(
        event_type=EventType.TRIAL_BALANCE_UPDATED,
        project_id=project_id,
        year=year,
        account_codes=report.updated_account_codes,
        extra={**event_extra, "source": f"audit_determination:{wp_code}"},
    ))
    await db.flush()
    return TbPublishResult(report, False, groups)
