"""Health evidence for ledger import activation/rollback events."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.dataset_models import ActivationRecord, ActivationType, DatasetStatus, LedgerDataset
from app.models.audit_platform_schemas import EventType
from app.services.event_bus import event_bus
from app.services.import_event_outbox_service import ImportEventOutboxService


class ImportEventReliabilityService:
    """Build an operator-facing consistency report for import events."""

    @staticmethod
    async def get_health(db: AsyncSession, *, project_id=None, year: int | None = None) -> dict:
        filters = []
        if project_id is not None:
            filters.append(ActivationRecord.project_id == project_id)
        if year is not None:
            filters.append(ActivationRecord.year == year)

        record_stmt = sa.select(ActivationRecord).where(*filters).order_by(
            ActivationRecord.performed_at.desc()
        ).limit(50)
        records = list((await db.execute(record_stmt)).scalars().all())

        active_filters = [LedgerDataset.status == DatasetStatus.active]
        if project_id is not None:
            active_filters.append(LedgerDataset.project_id == project_id)
        if year is not None:
            active_filters.append(LedgerDataset.year == year)
        active_count = int((await db.execute(
            sa.select(sa.func.count()).select_from(LedgerDataset).where(*active_filters)
        )).scalar_one() or 0)

        missing_events: list[dict] = []
        event_map = {
            ActivationType.activate: EventType.LEDGER_DATASET_ACTIVATED.value,
            ActivationType.rollback: EventType.LEDGER_DATASET_ROLLED_BACK.value,
        }
        for record in records:
            event_name = event_map.get(record.action)
            if not event_name:
                continue
            missing_events.append({
                "activation_record_id": str(record.id),
                "project_id": str(record.project_id),
                "year": record.year,
                "expected_event": event_name,
                "evidence": "activation record present; verify consumer via replay report and downstream freshness",
            })

        replay_report = event_bus.get_replay_report()
        max_attempts = int(settings.LEDGER_IMPORT_OUTBOX_MAX_RETRY_ATTEMPTS or 0)
        outbox_summary = await ImportEventOutboxService.summary(
            db,
            project_id=project_id,
            year=year,
            max_attempts=max_attempts if max_attempts > 0 else None,
        )
        exhausted_failed_count = int(outbox_summary.get("exhausted_failed_count") or 0)

        degradation_reasons: list[str] = []
        if replay_report.get("last_error"):
            degradation_reasons.append("REDIS_REPLAY_ERROR")
        if outbox_summary["pending_count"] > 0:
            degradation_reasons.append("OUTBOX_PENDING_BACKLOG")
        if outbox_summary["failed_count"] > 0:
            degradation_reasons.append("OUTBOX_FAILED_BACKLOG")
        if exhausted_failed_count > 0:
            degradation_reasons.append("OUTBOX_FAILED_EXHAUSTED")
        return {
            "status": "healthy" if not degradation_reasons else "degraded",
            "active_dataset_count": active_count,
            "recent_activation_records": len(records),
            "expected_event_evidence": missing_events,
            "replay_report": replay_report,
            "outbox_summary": outbox_summary,
            "checks": {
                "redis_replay_available": replay_report.get("redis_available"),
                "last_replay_error": replay_report.get("last_error"),
                "acked_count": replay_report.get("acked_count", 0),
                "outbox_pending_count": outbox_summary["pending_count"],
                "outbox_failed_count": outbox_summary["failed_count"],
                "outbox_exhausted_failed_count": exhausted_failed_count,
                "outbox_max_retry_attempts": outbox_summary.get("max_attempts"),
                "degradation_reasons": degradation_reasons,
            },
        }
