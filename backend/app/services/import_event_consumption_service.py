"""Import event consumption maintenance service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset_models import ImportEventConsumption


class ImportEventConsumptionService:
    @staticmethod
    async def cleanup_older_than_days(
        db: AsyncSession,
        *,
        retention_days: int = 180,
        batch_size: int = 5000,
    ) -> dict[str, int]:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(1, retention_days))
        ids = list(
            (
                await db.execute(
                    sa.select(ImportEventConsumption.id)
                    .where(ImportEventConsumption.consumed_at < cutoff)
                    .order_by(ImportEventConsumption.consumed_at.asc())
                    .limit(max(1, batch_size))
                )
            )
            .scalars()
            .all()
        )
        if not ids:
            return {"deleted_count": 0}

        await db.execute(
            sa.delete(ImportEventConsumption).where(ImportEventConsumption.id.in_(ids))
        )
        await db.flush()
        return {"deleted_count": len(ids)}
