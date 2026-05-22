"""跨循环断裂清单路由

Requirements: 2.2, 2.4, 2.6

GET /api/projects/{project_id}/cross-cycle-breakage
返回跨循环断裂清单（items + summary）。
性能目标：≤ 1s（400 CWR 规模）。
注册到 router_registry 协作域 §98。
"""

from __future__ import annotations

import logging
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.services.cross_cycle_breakage_service import (
    BreakageListResponse,
    get_cross_cycle_breakage,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/cross-cycle-breakage",
    tags=["cross-cycle-breakage"],
)


@router.get("", response_model=BreakageListResponse)
async def get_breakage_list(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> BreakageListResponse:
    """获取跨循环断裂清单。

    运行时 JOIN working_paper + wp_index 判断 target 是否断裂：
    - target_missing：项目内无对应 wp_code
    - target_stale：wp_code 存在但 prefill_stale=true

    按 severity 降序排列（blocking > required > warning > recommended > info）。
    性能目标：≤ 1s（400 条 CWR 规模）。
    """
    start_time = time.time()

    try:
        result = await get_cross_cycle_breakage(db=db, project_id=project_id)
    except (FileNotFoundError, ValueError, OSError) as e:
        logger.error(
            "Cross-cycle breakage load failed: project=%s error=%s",
            project_id,
            e,
        )
        raise HTTPException(
            status_code=503,
            detail=f"CWR 数据加载失败：{e}",
        ) from e

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        "Cross-cycle breakage: project=%s user=%s items=%d elapsed=%.1fms",
        project_id,
        current_user.id,
        len(result.items),
        elapsed_ms,
    )

    return result
