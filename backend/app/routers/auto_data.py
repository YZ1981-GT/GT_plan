"""通用 auto_data_source resolver API 端点.

GET /api/projects/{project_id}/auto-data/{source}
供前端直接调用注册的 resolver（如 a15_financial_ratios）。
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.auto_data_resolvers import resolve_auto_data_source

router = APIRouter(prefix="/api/projects/{project_id}/auto-data", tags=["auto-data"])

#: 路径/固定参数名——**不得**被当成 resolver 的行级参数透传（否则重复传参 TypeError）。
_RESERVED_QUERY_KEYS = frozenset({"project_id", "source", "year"})


def _row_level_kwargs(request: Request) -> dict[str, Any]:
    """把 query string 里的非保留参数收成 resolver 的 `**kwargs`（行级取数参数）。

    🔴 为什么需要它：`resolve_auto_data_source` 早就支持 `**kwargs`
    （`auto_data_resolvers/__init__.py` 的调度器直接 `await resolver(db, pid, year, **kwargs)`），
    但本端点原来一个都不传 ⇒ 任何**按行取数**的 resolver 经 HTTP 恒拿不到参数。
    D4 IPO 四表的 `d4_25_dealer_sales` / `d4_26_overseas_sales` /
    `d4_27_related_party_sales` / `d4_28_customer_balances` 都要 `customer_name`
    （或 `person_name`）才能查，缺参时它们按「宁缺勿造」返回全 None ——
    于是「表间提取」在 UI 上永远是空白。这一步把那条通道打开。

    安全面：值只作为 SQLAlchemy 绑定参数参与等值/LIKE 比较（resolver 内部），
    不拼 SQL；未知 kwargs 被 resolver 的 `**kwargs` 直接忽略，故对既有 resolver 是纯加法
    （现存调用方一个都没传额外 query 参数，行为零变化）。
    """
    return {
        key: value
        for key, value in request.query_params.items()
        if key not in _RESERVED_QUERY_KEYS
    }


@router.get("/{source}")
async def get_auto_data(
    project_id: UUID,
    source: str,
    request: Request,
    year: int = Query(..., description="审计年度"),
    db: AsyncSession = Depends(get_db),
):
    """调用注册的 auto_data_source resolver 返回结果。

    除 `year` 外的 query 参数按原名透传给 resolver 作行级取数参数
    （如 `?year=2025&customer_name=某某公司`）。
    """
    result = await resolve_auto_data_source(
        db, project_id, year, source, **_row_level_kwargs(request)
    )
    if result is None:
        return {"summary": f"未注册的数据源: {source}", "_error": True}
    return result
