"""数据信任度 router — V3 收官增强 Req 9.2

提供信任度聚合查询端点：

- GET /api/projects/{project_id}/trust-score?context=...

底层调用 trust_score_service.aggregate_trust_score（9.1 已就位）。
Redis 60s TTL 缓存由 service 层内部管理（9.3）。

注册位置：backend/app/router_registry/system.py §124

Validates: Requirements 9.2
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.deps import get_current_user
from app.models.core import User
from app.services import trust_score_service as svc

router = APIRouter(tags=["数据信任度"])


@router.get("/api/projects/{project_id}/trust-score")
async def get_trust_score(
    project_id: UUID,
    context: str = Query(..., description="上下文标识，如 workpaper:D2-1|cells.B5"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """获取指定上下文的数据信任度聚合信息。

    context 格式：
    - workpaper:{wp_code}|{cell}
    - report:{report_type}|{cell}
    - tb:{account_code}|{cell}
    - note:{section_id}|{cell}
    - adj:{adjustment_type}|{cell}
    """
    if not context or not context.strip():
        raise HTTPException(status_code=422, detail={"message": "context 参数不能为空"})

    # 获取 Redis（可能为 None，service 层会降级跳过缓存）
    redis = await get_redis()

    payload = await svc.aggregate_trust_score(
        db,
        project_id=project_id,
        context=context.strip(),
        redis=redis,
    )

    return {
        "project_id": str(project_id),
        "context": context,
        "data": payload,
    }
