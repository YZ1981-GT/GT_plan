"""统一批量操作工具 — 校验 + 事务 + 部分失败处理

用法:
    from app.core.bulk_operations import BulkRequest, BulkResult, bulk_execute, bulk_soft_delete, bulk_hard_delete

    @router.post("/batch-delete")
    async def batch_delete(
        body: BulkRequest,
        db: AsyncSession = Depends(get_db),
    ):
        result = await bulk_soft_delete(db, MyModel, body.ids)
        return result

Validates: Requirements R7.4
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable, TypedDict
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request / Response 模型
# ---------------------------------------------------------------------------


class BulkRequest(BaseModel):
    """批量操作请求体 — 传入待操作的 ID 列表"""
    ids: list[UUID] = Field(..., min_length=1, max_length=200, description="待操作的 ID 列表（1~200）")


class FailedItem(TypedDict):
    """单条失败记录"""
    id: str
    error: str


class BulkResult(TypedDict):
    """批量操作结果"""
    succeeded: list[str]
    failed: list[FailedItem]
    total: int
    success_count: int
    fail_count: int


# ---------------------------------------------------------------------------
# 通用批量执行器
# ---------------------------------------------------------------------------


async def bulk_execute(
    db: AsyncSession,
    model: Any,
    ids: list[UUID],
    action_fn: Callable[[AsyncSession, Any], Awaitable[None]],
    *,
    filter_deleted: bool = False,
) -> BulkResult:
    """通用批量操作执行器

    Parameters
    ----------
    db : AsyncSession
        数据库会话
    model : SQLAlchemy ORM Model
        目标模型类
    ids : list[UUID]
        待操作的 ID 列表
    action_fn : async (db, row) -> None
        对每条记录执行的操作函数，抛异常视为该条失败
    filter_deleted : bool
        True 时只查询 is_deleted=True 的记录（用于回收站永久删除）

    Returns
    -------
    BulkResult
        包含 succeeded / failed / total / success_count / fail_count
    """
    # 1. 查询所有目标记录
    stmt = select(model).where(model.id.in_(ids))
    if filter_deleted and hasattr(model, "is_deleted"):
        stmt = stmt.where(model.is_deleted == True)  # noqa: E712

    result = await db.execute(stmt)
    rows = {row.id: row for row in result.scalars().all()}

    succeeded: list[str] = []
    failed: list[FailedItem] = []

    # 2. 标记不存在的 ID
    for uid in ids:
        if uid not in rows:
            failed.append({"id": str(uid), "error": "记录不存在"})

    # 3. 逐条执行 action_fn，每条用 savepoint 隔离，捕获单条失败
    for uid, row in rows.items():
        try:
            async with db.begin_nested() as sp:  # savepoint 隔离
                await action_fn(db, row)
            succeeded.append(str(uid))
        except Exception as exc:
            # savepoint 已在 async with 退出时自动 rollback，此处仅记录
            logger.warning("bulk_execute 单条失败: id=%s error=%s", uid, exc)
            failed.append({"id": str(uid), "error": str(exc)})

    return BulkResult(
        succeeded=succeeded,
        failed=failed,
        total=len(ids),
        success_count=len(succeeded),
        fail_count=len(failed),
    )


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


async def bulk_soft_delete(
    db: AsyncSession,
    model: Any,
    ids: list[UUID],
) -> BulkResult:
    """批量软删除 — 要求模型有 soft_delete() 方法（SoftDeleteMixin）"""

    async def _soft_delete(_db: AsyncSession, row: Any) -> None:
        if getattr(row, "is_deleted", False):
            raise ValueError("记录已被删除")
        row.soft_delete()

    return await bulk_execute(db, model, ids, _soft_delete)


async def bulk_hard_delete(
    db: AsyncSession,
    model: Any,
    ids: list[UUID],
    *,
    filter_deleted: bool = True,
) -> BulkResult:
    """批量永久删除 — 从数据库物理删除记录

    Parameters
    ----------
    filter_deleted : bool
        默认 True，只删除 is_deleted=True 的记录（回收站场景）。
        设为 False 可删除任意记录。
    """

    async def _hard_delete(_db: AsyncSession, row: Any) -> None:
        await _db.delete(row)

    return await bulk_execute(
        db, model, ids, _hard_delete, filter_deleted=filter_deleted,
    )
