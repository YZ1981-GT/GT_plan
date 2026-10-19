"""B5 业务约定书版本推荐端点

GET /api/projects/{project_id}/b5/recommended-version
根据项目 business_category + 项目特征自动推荐适用的约定书版本（B5-1~B5-9）。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access

logger = logging.getLogger(__name__)

# 项目级读鉴权：按项目推荐 B5 版本（Phase 8 Task 8 补）
router = APIRouter(
    prefix="/api/projects/{project_id}/b5",
    tags=["b5-version"],
    dependencies=[Depends(require_project_access("readonly"))],
)


@router.get("/recommended-version")
async def get_b5_recommended_version(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """推荐 B5 约定书主版本（基于项目 business_category + signals）"""
    from app.services.b5_version_service import recommend_b5_version

    result = await recommend_b5_version(db, project_id)
    return result
