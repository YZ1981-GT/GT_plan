"""合并推送下游入队失败的可见留痕。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.models.consol_push_models import ConsolPushRun

logger = logging.getLogger(__name__)


async def record_consol_push_failure(
    project_id: UUID,
    year: int,
    *,
    trigger: str,
    reason: str,
    source_id: str | None = None,
) -> UUID | None:
    """用独立会话记录失败运行并广播 ``consol.push_failed``。

    审批事件处理器可能正处于异常事务中，因此这里不能复用处理器的 session。
    记录失败不再向上抛，审批本身已经提交，后续由合并推送页手动重试。
    """
    run_id = uuid4()
    now = datetime.now(timezone.utc)
    warning = str(reason or "合并重算事件投递失败")[:1000]
    try:
        from app.core.database import async_session

        async with async_session() as db:
            db.add(ConsolPushRun(
                id=run_id,
                project_id=project_id,
                year=int(year),
                trigger_source=trigger,
                status="failed",
                steps=[],
                warnings=[warning],
                started_at=now,
                finished_at=now,
            ))
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.error("记录合并推送失败运行也失败 project=%s year=%s: %s", project_id, year, exc)
        return None

    try:
        from app.services.consol_push_service import SSE_FAILED
        from app.services.event_bus import event_bus

        event_bus.broadcast_raw(SSE_FAILED, {
            "project_id": str(project_id),
            "year": int(year),
            "run_id": str(run_id),
            "trigger": trigger,
            "source_id": source_id,
            "warnings": [warning],
        })
    except Exception as exc:  # noqa: BLE001
        logger.warning("广播合并推送失败事件失败 run=%s: %s", run_id, exc)
    return run_id


__all__ = ["record_consol_push_failure"]
