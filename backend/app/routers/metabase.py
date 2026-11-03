"""Metabase 数据可视化 API 路由

- GET /api/metabase/dashboards           — 预置仪表板列表
- GET /api/metabase/embed-url            — 获取嵌入URL
- GET /api/metabase/sql-templates        — SQL查询模板
- DELETE /api/metabase/cache/{project_id} — 清除缓存

Validates: Requirements 13.1-13.6
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.deps import assert_project_permission, get_current_user, require_project_access
from app.models.core import User
from app.services.metabase_service import MetabaseService

router = APIRouter(prefix="/api/metabase", tags=["metabase"])


def _svc(redis=None) -> MetabaseService:
    return MetabaseService(
        metabase_url=settings.METABASE_URL,
        embedding_secret=settings.METABASE_EMBEDDING_SECRET,
        redis=redis,
    )


@router.get("/dashboards")
async def list_dashboards():
    """预置仪表板列表"""
    return _svc().get_dashboard_configs()


@router.get("/embed-url")
async def get_embed_url(
    resource_type: str = Query("dashboard"),
    resource_id: int = Query(1),
    project_id: UUID | None = None,
    year: int | None = None,
    account_code: str | None = None,
    company_code: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取 Metabase 嵌入 URL。项目资源要求只读权限，全局资源仅管理员可签发。"""
    params: dict = {}
    if project_id is not None:
        await assert_project_permission(db, current_user, project_id, "readonly")
        params["project_id"] = str(project_id)
    else:
        role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
        if role != "admin":
            raise HTTPException(status_code=403, detail="仅管理员可签发全局 Metabase 嵌入地址")
    if year:
        params["year"] = year
    if account_code:
        params["account_code"] = account_code
    if company_code:
        params["company_code"] = company_code

    url = _svc().get_embed_url(resource_type, resource_id, params)
    return {"embed_url": url}


@router.get("/sql-templates")
async def list_sql_templates():
    """SQL 查询模板"""
    return _svc().get_sql_templates()


@router.delete("/cache/{project_id}")
async def clear_cache(
    project_id: UUID,
    current_user: User = Depends(require_project_access("edit")),
    redis=Depends(get_redis),
):
    """清除项目仪表板缓存。"""
    svc = _svc(redis)
    count = await svc.invalidate_dashboard_cache(project_id)
    return {"cleared": count}


# ── 下钻（Task 14.5） ──

@router.get("/drilldown-config")
async def get_drilldown_config():
    """获取下钻路径配置"""
    return _svc().get_drilldown_config()


@router.get("/drilldown-url")
async def build_drilldown_url(
    project_id: UUID = Query(...),
    year: int = Query(...),
    target_level: str = Query(..., description="ledger/voucher/aux_balance/aux_ledger"),
    account_code: str | None = None,
    voucher_no: str | None = None,
    voucher_date: str | None = None,
    aux_code: str | None = None,
    aux_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """构建下钻目标 URL。"""
    await assert_project_permission(db, current_user, project_id, "readonly")

    params: dict = {}
    if account_code:
        params["account_code"] = account_code
    if voucher_no:
        params["voucher_no"] = voucher_no
    if voucher_date:
        params["voucher_date"] = voucher_date
    if aux_code:
        params["aux_code"] = aux_code
    if aux_type:
        params["aux_type"] = aux_type

    url = _svc().build_drilldown_url(str(project_id), year, target_level, params)
    return {"drilldown_url": url, "target_level": target_level, "params": params}
