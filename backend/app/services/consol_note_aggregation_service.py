"""合并附注汇总前的层级链校验（CI-16）.

「🔄 重新汇总」（``consol_notes.reaggregate``）与「按公式应用」（``consol_note_sections``）在写入前
调 ``validate_lineage_dag``：沿 ``projects.parent_project_id`` 向上走，出现环即拒绝汇总。

合并附注的个别数从各子企业单体附注按已确认映射拉取（``consol_note_subtree_reaggregate``）。
原 Sprint B.0 的「从子公司单体附注汇总」五种聚合方式只给 V2 汇总器与 ``consol_aggregation``
取数源用，已随 V2 于 2026-10-22 下线（spec consol-note-header-library-and-node-reaggregate R6.1）。

Validates: Requirements CI-16
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


async def validate_lineage_dag(project_id: UUID, db: Any = None) -> bool:
    """校验多层合并 lineage 链无环（CI-16）."""
    visited: set[UUID] = set()
    current = project_id
    while current is not None:
        if current in visited:
            logger.error("Cycle detected in lineage chain at project %s", current)
            return False
        visited.add(current)
        current = await _get_parent_project_id(current, db)
    return True


async def _get_parent_project_id(project_id: UUID, db: Any = None) -> UUID | None:
    """获取项目的 parent_project_id."""
    if db is None:
        return None
    try:
        from sqlalchemy import text
        row = await db.execute(
            text("SELECT parent_project_id FROM projects WHERE id = :pid AND is_deleted = false"),
            {"pid": str(project_id)},
        )
        record = row.first()
        if record and record[0]:
            return UUID(str(record[0])) if isinstance(record[0], str) else record[0]
    except Exception:
        pass
    return None
