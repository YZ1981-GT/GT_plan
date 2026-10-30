"""子企业单体附注章节保存 → 用到它的合并附注章节标「待更新」（is_stale）。

原属 spec consol-note-mapping-reuse-and-reference-push（V202）：另有值指纹、值确认降级与 stale 汇总端点。规则模板库 / 值确认 /
结构锁整体退役后（spec note-pull-followup-closure R16，V208 删表）只留在用的这一段：按明细映射绑定找到把该子企业作为
来源的合并项目章节，标 ``ConsolNoteData.is_stale``，回报受影响的合并项目（调用方 ``consol_note_stale_handler`` 提交并推
``consol.note_stale`` SSE）。

Service 只 flush 不 commit。
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = ["on_note_section_saved"]


async def on_note_section_saved(
    db: AsyncSession,
    *,
    entity_project_id: UUID,
    section_id: str,
    year: int,
    consol_project_ids: list[UUID] | None = None,
) -> dict[str, Any] | None:
    """子企业保存了与合并章节 ``section_id`` 对应的单体附注 → 绑定了它的合并项目该章节全部节点标 is_stale。

    只看已确认 / 结构已变化的绑定（``consol_note_mapping_binding``）；``consol_project_ids`` 给定时只处理这些合并项目。
    返回 ``{"affected_projects": [{consol_project_id, section_id, entity_node_key, entity_project_id}]}``；没有绑定返回 None。
    """
    from app.models.consol_note_data_models import ConsolNoteData
    from app.models.consol_note_mapping_models import ConsolNoteMappingBinding

    query = sa.select(ConsolNoteMappingBinding).where(
        ConsolNoteMappingBinding.entity_project_id == entity_project_id,
        ConsolNoteMappingBinding.section_id == section_id,
        ConsolNoteMappingBinding.status.in_(["confirmed", "stale"]),
    )
    if consol_project_ids is not None:
        query = query.where(ConsolNoteMappingBinding.project_id.in_(consol_project_ids))
    bindings = (await db.execute(query)).scalars().all()
    if not bindings:
        return None

    results: list[dict[str, Any]] = []
    for binding in bindings:
        for record in (await db.execute(sa.select(ConsolNoteData).where(
            ConsolNoteData.project_id == binding.project_id,
            ConsolNoteData.year == year,
            ConsolNoteData.section_id == section_id,
        ))).scalars().all():
            record.is_stale = True
        results.append({
            "consol_project_id": str(binding.project_id),
            "section_id": section_id,
            "entity_node_key": binding.entity_node_key,
            "entity_project_id": str(entity_project_id),
        })
    await db.flush()
    return {"affected_projects": results}
