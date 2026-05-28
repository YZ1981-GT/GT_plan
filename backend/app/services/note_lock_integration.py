"""Sprint A.6.1 — 附注章节锁集成 helper.

提供 context manager 和装饰器，让 4 个入口（动态行/列编辑、集团基线 apply、
auto_trim、国企↔上市切换）在操作前自动获锁、操作后自动释放。

用法::

    async with note_section_lock(db, project_id, year, section_id, user_id):
        # 编辑逻辑
        ...

或在 router 层::

    @router.post("/dynamic-rows")
    async def add_dynamic_row(...):
        async with note_section_lock(db, project_id, year, section_id, user_id):
            ...

设计原则：
- 锁粒度 = 章节级（section_id）
- 超时 = 300s（5 分钟无心跳自动释放，与 NoteSectionLockService 对齐）
- 锁冲突 → 抛 HTTPException 409（前端弹冲突弹窗）
- 批量操作（auto_trim / 切换）→ 对所有受影响章节逐一获锁

CI-13: 锁释放必触发（context manager __aexit__ 保证）
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 默认锁超时（秒）
DEFAULT_LOCK_TIMEOUT = 300


@asynccontextmanager
async def note_section_lock(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    section_id: str,
    user_id: UUID,
    *,
    timeout: int = DEFAULT_LOCK_TIMEOUT,
) -> AsyncGenerator[None, None]:
    """章节级锁 context manager（CI-13: 退出时必释放）.

    Args:
        db: AsyncSession
        project_id: 项目 ID
        year: 年度
        section_id: 章节 section_id（锁粒度）
        user_id: 当前用户 ID
        timeout: 锁超时秒数（默认 300s）

    Raises:
        HTTPException(409): 锁冲突（其他用户持有）

    Usage::

        async with note_section_lock(db, pid, year, sid, uid):
            # 安全编辑
            ...
    """
    from app.services.note_section_lock_service import NoteSectionLockService

    lock_service = NoteSectionLockService(db)
    acquired = await lock_service.acquire_lock(
        project_id=project_id,
        year=year,
        section_id=section_id,
        user_id=user_id,
        timeout_seconds=timeout,
    )

    if not acquired:
        # 查谁持有
        active = await lock_service.get_active_locks(project_id, year)
        holder = next(
            (lk for lk in active if lk.get("section_id") == section_id),
            None,
        )
        holder_name = holder.get("user_name", "其他用户") if holder else "其他用户"
        raise HTTPException(
            status_code=409,
            detail=f"章节 {section_id} 正被 {holder_name} 编辑中，请稍后重试或联系对方释放",
        )

    try:
        yield
    finally:
        # CI-13: 锁释放必触发
        try:
            await lock_service.release_lock(
                project_id=project_id,
                year=year,
                section_id=section_id,
                user_id=user_id,
            )
        except Exception as exc:
            logger.warning(
                "note_section_lock release failed for %s/%s: %s",
                project_id, section_id, exc,
            )


@asynccontextmanager
async def note_batch_lock(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    section_ids: list[str],
    user_id: UUID,
    *,
    timeout: int = DEFAULT_LOCK_TIMEOUT,
) -> AsyncGenerator[None, None]:
    """批量章节锁（auto_trim / 切换等批量操作用）.

    逐一获锁；任一失败 → 释放已获取的锁 + 抛 409。
    退出时释放所有已获取的锁（CI-13）。
    """
    from app.services.note_section_lock_service import NoteSectionLockService

    lock_service = NoteSectionLockService(db)
    acquired_ids: list[str] = []

    try:
        for sid in section_ids:
            ok = await lock_service.acquire_lock(
                project_id=project_id,
                year=year,
                section_id=sid,
                user_id=user_id,
                timeout_seconds=timeout,
            )
            if not ok:
                raise HTTPException(
                    status_code=409,
                    detail=f"批量锁定失败：章节 {sid} 被其他用户占用",
                )
            acquired_ids.append(sid)
        yield
    finally:
        for sid in acquired_ids:
            try:
                await lock_service.release_lock(
                    project_id=project_id,
                    year=year,
                    section_id=sid,
                    user_id=user_id,
                )
            except Exception as exc:
                logger.warning("batch lock release %s failed: %s", sid, exc)
