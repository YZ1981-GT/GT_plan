"""科目余额表 / 序时账人工修改接口（spec citar-table-manual-edit R3~R5）。

前缀 ``/api/projects/{project_id}/ledger``（与穿透查询同前缀，只加写端点）；读只读权限、写编辑权限，合并锁定期间禁止写；
写端点另需账号开通「允许修改」（``manual_edit_permission``，spec citar-manual-edit-permission）。

- ``PUT balance-rows/{row_id}``：改末级科目余额行（上级同步），随即重算试算表
- ``PUT entries/{row_id}``：改序时账分录（不回写余额表）
- ``POST {table}/{row_id}/restore``：恢复导入原值（table = balance / ledger）
- ``GET manual-edits?table=``：当前数据集里改过的行；``GET manual-edits/summary``：两张表改过的行数
"""

from __future__ import annotations

import logging
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.deps import check_consol_lock, require_project_access
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.core import User
from app.models.ledger_edit_models import TABLE_BALANCE, TABLE_LEDGER
from app.services import ledger_edit_service as svc
from app.services.event_bus import event_bus
from app.services.manual_edit_permission import assert_manual_edit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/projects/{project_id}/ledger", tags=["查账与试算"])

YearQuery = Query(..., ge=1990, le=2100)


class EditBody(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = Field(None, max_length=500)


async def _clear_ledger_cache(redis, project_id: UUID, year: int) -> None:
    """穿透查询缓存（余额 5 分钟）：与导入完成后同一清法。"""
    if not redis:
        return
    try:
        keys = [k async for k in redis.scan_iter(match=f"ledger:*:{project_id}:{year}:*")]
        if keys:
            await redis.delete(*keys)
    except Exception:  # 缓存清不掉不影响修改本身（最多 5 分钟后过期）
        logger.warning("清除穿透查询缓存失败 project=%s year=%s", project_id, year, exc_info=True)


async def _after_balance_change(db: AsyncSession, redis, project_id: UUID, year: int) -> None:
    """余额表变了：试算表未审数按新值重算（与「重算试算表」同一链路），清缓存、发事件。"""
    from app.services.cache_service import CacheService
    from app.services.trial_balance_service import TrialBalanceService

    await TrialBalanceService(db).full_recalc(project_id, year)
    await db.commit()
    await _clear_ledger_cache(redis, project_id, year)
    try:
        await CacheService(redis).invalidate_tb_cache(project_id, year)
    except Exception:
        logger.warning("清除试算表缓存失败 project=%s year=%s", project_id, year, exc_info=True)
    await event_bus.publish_immediate(EventPayload(event_type=EventType.TRIAL_BALANCE_UPDATED, project_id=project_id, year=year))


@router.put("/balance-rows/{row_id}")
async def edit_balance_row(
    project_id: UUID, row_id: UUID, body: EditBody, year: int = YearQuery,
    db: AsyncSession = Depends(get_db), redis=Depends(get_redis),
    _lock=Depends(check_consol_lock),
    current_user: User = Depends(require_project_access("edit")),
):
    """``values``：opening / closing（借正贷负）、debit / credit（发生额），不传的不改。"""
    assert_manual_edit(current_user)
    await svc.edit_balance(db, project_id, year, row_id, body.values, current_user.id, body.reason)
    await _after_balance_change(db, redis, project_id, year)
    return {"ok": True}


@router.put("/entries/{row_id}")
async def edit_ledger_entry(
    project_id: UUID, row_id: UUID, body: EditBody, year: int = YearQuery,
    db: AsyncSession = Depends(get_db), redis=Depends(get_redis),
    _lock=Depends(check_consol_lock),
    current_user: User = Depends(require_project_access("edit")),
):
    assert_manual_edit(current_user)
    await svc.edit_ledger(db, project_id, year, row_id, body.values, current_user.id, body.reason)
    await db.commit()
    await _clear_ledger_cache(redis, project_id, year)
    return {"ok": True}


@router.post("/{table}/{row_id}/restore")
async def restore_row(
    project_id: UUID, table: Literal["balance", "ledger"], row_id: UUID, year: int = YearQuery,
    db: AsyncSession = Depends(get_db), redis=Depends(get_redis),
    _lock=Depends(check_consol_lock),
    current_user: User = Depends(require_project_access("edit")),
):
    assert_manual_edit(current_user)
    await svc.restore(db, project_id, year, table, row_id, current_user.id)
    if table == TABLE_BALANCE:
        await _after_balance_change(db, redis, project_id, year)
    else:
        await db.commit()
        await _clear_ledger_cache(redis, project_id, year)
    return {"ok": True}


@router.get("/manual-edits/summary")
async def manual_edits_summary(
    project_id: UUID, year: int = YearQuery, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    return await svc.summary(db, project_id, year)


@router.get("/manual-edits")
async def manual_edits(
    project_id: UUID, table: Literal["balance", "ledger"] = Query(...), year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    return await svc.list_edits(db, project_id, year, TABLE_BALANCE if table == "balance" else TABLE_LEDGER)
