"""联动全景图聚合端点。

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9

提供 GET /api/projects/{project_id}/linkage-panorama/graph-data 端点，
聚合 cross_wp_references.json 和 working_paper.prefill_stale 后返回全量图数据。
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.schemas.linkage_panorama import GraphDataResponse, GraphStatistics
from app.services.linkage_panorama_aggregator import (
    aggregate_graph_from_cwr,
    compute_statistics,
    overlay_stale_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/linkage-panorama",
    tags=["linkage-panorama"],
)

# CWR 数据文件路径（相对仓库根，部署时可通过环境变量覆盖）
_CWR_FILE_DEFAULT = Path(__file__).resolve().parents[2] / "data" / "cross_wp_references.json"


def _resolve_cwr_path() -> Path:
    """返回 cross_wp_references.json 文件路径。

    覆盖优先级：
    1. 环境变量 LINKAGE_PANORAMA_CWR_PATH
    2. backend/data/cross_wp_references.json (默认)
    """
    import os

    env_path = os.environ.get("LINKAGE_PANORAMA_CWR_PATH")
    if env_path:
        return Path(env_path)
    return _CWR_FILE_DEFAULT


def _load_cwr_references() -> list[dict]:
    """加载 cross_wp_references.json 的 references 数组。

    加载失败时抛 HTTPException 503。
    """
    path = _resolve_cwr_path()
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        refs = data.get("references")
        if not isinstance(refs, list):
            raise ValueError("references field missing or not a list")
        return refs
    except FileNotFoundError as e:
        logger.error("CWR file not found: %s", path)
        raise HTTPException(status_code=503, detail="CWR 数据加载失败：文件不存在") from e
    except (json.JSONDecodeError, ValueError, OSError) as e:
        logger.error("CWR file load failed: %s — %s", path, e)
        raise HTTPException(status_code=503, detail=f"CWR 数据加载失败：{e}") from e


async def _load_stale_wp_codes(db: AsyncSession, project_id: UUID) -> set[str]:
    """查询当前项目所有 prefill_stale=True 的底稿 wp_code 集合。

    底稿 wp_code 在 WpIndex 上，需 join WorkingPaper.wp_index_id。
    """
    stmt = (
        select(WpIndex.wp_code)
        .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted.is_(False),
            WorkingPaper.prefill_stale.is_(True),
        )
    )
    result = await db.execute(stmt)
    return {row[0] for row in result.all() if row[0]}


@router.get("/graph-data", response_model=GraphDataResponse)
async def get_graph_data(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> GraphDataResponse:
    """聚合全量 CWR 图数据 + 当前项目 stale 状态。

    流程：
    1. 加载 cross_wp_references.json
    2. 聚合节点+边
    3. 查询 DB stale wp_codes
    4. 叠加 stale 状态
    5. 计算 statistics
    """
    start_time = time.time()

    references = _load_cwr_references()
    nodes, edges = aggregate_graph_from_cwr(references)
    stale_wp_codes = await _load_stale_wp_codes(db, project_id)
    nodes, edges = overlay_stale_status(nodes, edges, stale_wp_codes)
    stats = compute_statistics(nodes, edges)

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        "Linkage panorama graph-data: project=%s user=%s nodes=%d edges=%d "
        "stale_nodes=%d stale_edges=%d elapsed=%.1fms",
        project_id,
        current_user.id,
        stats["node_count"],
        stats["edge_count"],
        stats["stale_node_count"],
        stats["stale_edge_count"],
        elapsed_ms,
    )

    return GraphDataResponse(
        nodes=nodes,
        edges=edges,
        statistics=GraphStatistics(**stats),
    )
