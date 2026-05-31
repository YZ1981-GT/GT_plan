"""增量 stale 传播服务 — wp-traceability-panel Task 6.2

按 account_code/wp_code 精确传播 stale 标记（增量，非全量）。
封装 stale_propagation_engine.on_change 的精确调用模式。

Requirements: 5.2
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


async def propagate_stale_by_account(
    project_id: UUID | str,
    year: int,
    account_code: str,
) -> dict[str, Any]:
    """按科目编码精确传播 stale 标记。

    构造 source_uri = "TB:{account_code}::" 触发 BFS 精确传播，
    仅影响依赖该科目的底稿/报表/附注。
    """
    from app.services.stale_propagation_engine import stale_engine

    source_uri = f"TB:{account_code}::"
    return await stale_engine.on_change(source_uri, project_id, year)


async def propagate_stale_by_wp_code(
    project_id: UUID | str,
    year: int,
    wp_code: str,
    sheet_name: str | None = None,
    cell_ref: str | None = None,
) -> dict[str, Any]:
    """按底稿编码精确传播 stale 标记。

    构造 source_uri = "WP:{wp_code}:{sheet}:{cell}" 触发 BFS 精确传播，
    仅影响依赖该底稿的下游对象。
    """
    from app.services.stale_propagation_engine import stale_engine

    source_uri = f"WP:{wp_code}:{sheet_name or ''}:{cell_ref or ''}"
    return await stale_engine.on_change(source_uri, project_id, year)


async def propagate_stale_by_adjustment(
    project_id: UUID | str,
    year: int,
    account_code: str,
    adjustment_id: str | None = None,
) -> dict[str, Any]:
    """调整分录变更时精确传播 stale 标记。

    从调整分录涉及的科目出发，精确传播到依赖该科目的底稿/报表/附注。
    """
    from app.services.stale_propagation_engine import stale_engine

    source_uri = f"ADJ:{account_code}:{adjustment_id or ''}:"
    return await stale_engine.on_change(source_uri, project_id, year)
