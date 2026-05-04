"""统一分页/排序参数 — FastAPI 依赖注入

用法:
    from app.core.pagination import PaginationParams, SortParams, paginate, sort_query, build_paginated_response

    @router.get("")
    async def list_items(
        pagination: PaginationParams = Depends(),
        sort: SortParams = Depends(),
        db: AsyncSession = Depends(get_db),
    ):
        stmt = select(MyModel)
        stmt = sort_query(stmt, sort, MyModel)
        return await build_paginated_response(db, stmt, pagination)
"""

from __future__ import annotations

import math
from typing import Any, Literal, Sequence, TypedDict

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class PaginationParams:
    """分页参数依赖 — page 从 1 开始，page_size 默认 20，最大 200"""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码（从 1 开始）"),
        page_size: int = Query(20, ge=1, le=200, description="每页条数（最大 200）"),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class SortParams:
    """排序参数依赖 — sort_by 可选列名，sort_order 默认 asc"""

    def __init__(
        self,
        sort_by: str | None = Query(None, description="排序字段名"),
        sort_order: Literal["asc", "desc"] = Query("asc", description="排序方向"),
    ):
        self.sort_by = sort_by
        self.sort_order = sort_order


class PaginatedResponse(TypedDict):
    """标准分页响应结构"""
    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


def paginate(stmt: Select, pagination: PaginationParams) -> Select:
    """对 SQLAlchemy Select 语句应用 OFFSET/LIMIT"""
    return stmt.offset(pagination.offset).limit(pagination.limit)


def sort_query(stmt: Select, sort: SortParams, model: Any) -> Select:
    """对 SQLAlchemy Select 语句应用 ORDER BY

    仅当 sort.sort_by 对应 model 上的有效列时才生效，
    防止任意列名注入。
    """
    if sort.sort_by is None:
        return stmt

    col = getattr(model, sort.sort_by, None)
    if col is None:
        return stmt

    if sort.sort_order == "desc":
        return stmt.order_by(col.desc())
    return stmt.order_by(col.asc())


async def build_paginated_response(
    db: AsyncSession,
    stmt: Select,
    pagination: PaginationParams,
    *,
    row_mapper: Any | None = None,
) -> PaginatedResponse:
    """执行查询并构建标准分页响应

    Parameters
    ----------
    db : AsyncSession
        数据库会话
    stmt : Select
        已应用过滤/排序的查询（不含 offset/limit）
    pagination : PaginationParams
        分页参数
    row_mapper : callable, optional
        将 ORM 对象转为 dict 的函数。默认直接放入 items。

    Returns
    -------
    PaginatedResponse
        包含 items, total, page, page_size, total_pages
    """
    # 计算总数
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total: int = (await db.execute(count_stmt)).scalar() or 0

    # 分页查询
    paged_stmt = paginate(stmt, pagination)
    result = await db.execute(paged_stmt)
    rows: Sequence = result.scalars().all()

    # 映射
    if row_mapper is not None:
        items = [row_mapper(r) for r in rows]
    else:
        items = list(rows)

    total_pages = math.ceil(total / pagination.page_size) if total > 0 else 0

    return {
        "items": items,
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
        "total_pages": total_pages,
    }
