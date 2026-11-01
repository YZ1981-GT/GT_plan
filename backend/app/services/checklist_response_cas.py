# -*- coding: utf-8 -*-
"""Checklist 批量保存的行锁与渐进式 If-Match 预检。"""
from __future__ import annotations

import uuid
from typing import Protocol, Sequence

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ChecklistVersionItem(Protocol):
    item_id: str
    if_match: str | None


def _uses_postgresql(db: AsyncSession) -> bool:
    """真实 PG 才使用 advisory lock；SQLite 与轻量测试桩显式降级为行锁路径。"""
    get_bind = getattr(db, "get_bind", None)
    bind = get_bind() if callable(get_bind) else None
    return getattr(getattr(bind, "dialect", None), "name", None) == "postgresql"


async def acquire_checklist_response_write_locks(
    db: AsyncSession,
    wp_id: uuid.UUID | str,
    item_ids: Sequence[str],
) -> tuple[str, ...]:
    """按稳定顺序取得 checklist 逻辑键和现存行锁，供 HTTP CAS 与 OO mirror 共用。"""
    normalized = tuple(sorted(set(item_ids)))
    if any(not isinstance(item_id, str) or not item_id.strip() for item_id in normalized):
        raise ValueError("checklist item_id 必须是非空字符串")
    if not _uses_postgresql(db):
        # SQLite/轻量桩没有 PG advisory lock；并发保证只由真实 PG 测试声明。
        return normalized
    for item_id in normalized:
        lock_key = f"checklist_response:{wp_id}:{len(item_id)}:{item_id}"
        await db.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended(CAST(:lock_key AS text), 1129595219))"
            ),
            {"lock_key": lock_key},
        )
        await db.execute(
            text(
                "SELECT item_id FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id = :item_id FOR UPDATE"
            ),
            {"wp_id": str(wp_id), "item_id": item_id},
        )
    return normalized


async def lock_and_check_versions(
    db: AsyncSession,
    wp_id: uuid.UUID,
    items: Sequence[ChecklistVersionItem],
    *,
    require_if_match: bool = False,
) -> dict[str, str]:
    """稳定排序锁定逻辑键和现存行，并在任何写入前完成整批版本预检。"""
    existing: dict[str, str] = {}
    item_ids = await acquire_checklist_response_write_locks(
        db, wp_id, [item.item_id for item in items]
    )
    for item_id in item_ids:
        row = (
            await db.execute(
                text(
                    "SELECT updated_at FROM checklist_responses "
                    "WHERE wp_id = :wp_id AND item_id = :item_id"
                ),
                {"wp_id": str(wp_id), "item_id": item_id},
            )
        ).fetchone()
        if row and row.updated_at:
            existing[item_id] = row.updated_at.isoformat()

    for item in items:
        server_version = existing.get(item.item_id)
        if item.if_match is None:
            if require_if_match and server_version is not None:
                raise HTTPException(
                    status_code=428,
                    detail={
                        "code": "version_required",
                        "item_id": item.item_id,
                        "server_version": server_version,
                        "message": "底稿条目已有更新版本，请刷新后再保存",
                        "atomic": True,
                    },
                )
            continue
        if item.if_match != server_version:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "version_conflict",
                    "item_id": item.item_id,
                    "client_version": item.if_match,
                    "server_version": server_version,
                    "message": "底稿条目已被其他客户端修改",
                    "atomic": True,
                },
            )
    return existing
