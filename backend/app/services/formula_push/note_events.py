"""公式推送提交后的附注领域事件。"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from uuid import UUID

logger = logging.getLogger(__name__)


async def publish_note_sections(
    project_id: UUID,
    year: int,
    sections: Iterable[str],
    run_id: UUID | None,
) -> None:
    """发布逐章节保存事件；业务已经提交，通知失败只能记录告警。"""
    unique_sections = tuple(dict.fromkeys(sections))
    if not unique_sections:
        return
    try:
        from app.models.audit_platform_schemas import EventPayload, EventType
        from app.services.event_bus import event_bus

        for section in unique_sections:
            await event_bus.publish(EventPayload(
                event_type=EventType.NOTE_SECTION_SAVED,
                project_id=project_id,
                year=year,
                extra={
                    "section_code": section,
                    "action": "formula_push",
                    "formula_push_run_id": str(run_id) if run_id else None,
                },
            ))
    except Exception:  # noqa: BLE001 — 业务已提交，领域通知只能 fail-open
        logger.warning(
            "formula_push: NOTE_SECTION_SAVED 发布失败 project=%s sections=%s",
            project_id, unique_sections, exc_info=True,
        )
