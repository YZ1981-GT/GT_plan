"""自定义底稿公式依赖联动（custom-workpaper-formula-binding 14.3）。

当某 WP 单元格（wp_code + sheet + cell）取值变更时：
1. 扫描同项目 ``wp_formula`` 表达式中的 ``WP('code','cell')`` 引用，标记引用方底稿 ``prefill_stale``；
2. 调用 ``StalePropagationEngine.on_change`` 走静态 ``unified_dependency_graph.json`` BFS（标准底稿链路）。
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session as async_session_factory
from app.models.workpaper_models import WorkingPaper, WpFormula

logger = logging.getLogger(__name__)

# WP('D11','B5') / WP("D11","审定数")
_WP_REF_RE = re.compile(
    r"WP\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)",
    re.IGNORECASE,
)


def extract_wp_refs(expression: str) -> list[tuple[str, str]]:
    """从表达式提取 (wp_code, second_arg) 列表。"""
    if not expression:
        return []
    return [(m.group(1).strip(), m.group(2).strip()) for m in _WP_REF_RE.finditer(expression)]


def expression_references_cell(
    expression: str,
    wp_code: str,
    cell_or_col: str,
) -> bool:
    """表达式是否引用指定底稿单元格/列。"""
    target_cell = (cell_or_col or "").strip().upper()
    code = (wp_code or "").strip()
    for ref_code, ref_arg in extract_wp_refs(expression):
        if ref_code == code and ref_arg.strip().upper() == target_cell:
            return True
    return False


async def find_dependent_wp_ids(
    db: AsyncSession,
    project_id: uuid.UUID,
    wp_code: str,
    cell_or_col: str,
) -> list[uuid.UUID]:
    """查找引用了指定 WP 单元格/列的其它底稿 working_paper.id 列表。"""
    rows = (
        await db.execute(
            sa.select(WpFormula.wp_id, WpFormula.expression).where(
                WpFormula.project_id == project_id,
            )
        )
    ).all()
    dependents: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for wp_id, expression in rows:
        if not expression or not expression_references_cell(expression, wp_code, cell_or_col):
            continue
        if wp_id not in seen:
            seen.add(wp_id)
            dependents.append(wp_id)
    return dependents


async def mark_working_papers_stale(
    project_id: uuid.UUID,
    wp_ids: list[uuid.UUID],
    *,
    db: AsyncSession | None = None,
) -> int:
    """将指定 working_paper 行标记 prefill_stale=true。"""
    if not wp_ids:
        return 0

    async def _run(session: AsyncSession) -> int:
        result = await session.execute(
            sa.update(WorkingPaper)
            .where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.id.in_(wp_ids),
                WorkingPaper.is_deleted == False,  # noqa: E712
            )
            .values(prefill_stale=True)
        )
        return int(result.rowcount or 0)

    if db is not None:
        count = await _run(db)
        return count

    async with async_session_factory() as session:
        count = await _run(session)
        await session.commit()
        return count


async def propagate_custom_wp_cell_change(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    year: int,
    wp_code: str,
    sheet_name: str,
    cell_ref: str,
) -> dict[str, Any]:
    """单元格变更后的依赖联动（动态 wp_formula + 静态依赖图）。"""
    cell_up = (cell_ref or "").strip().upper()
    source_uri = f"WP:{wp_code}:{sheet_name}:{cell_up}"

    dependent_wp_ids = await find_dependent_wp_ids(db, project_id, wp_code, cell_up)
    dynamic_marked = await mark_working_papers_stale(
        project_id, dependent_wp_ids, db=db
    )

    graph_result: dict[str, Any] = {"affected": [], "total": 0, "degraded": False}
    try:
        from app.services.stale_propagation_engine import stale_engine

        graph_result = await stale_engine.on_change(source_uri, project_id, year)
    except Exception as e:
        logger.warning(
            "stale_engine.on_change failed source=%s: %s", source_uri, e
        )
        graph_result = {"error": str(e), "degraded": True}

    return {
        "source_uri": source_uri,
        "dynamic_dependents": [str(i) for i in dependent_wp_ids],
        "dynamic_marked": dynamic_marked,
        "graph": graph_result,
    }
