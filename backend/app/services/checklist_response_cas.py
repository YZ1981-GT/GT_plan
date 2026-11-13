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


def checklist_response_version(value: object) -> str | None:
    """checklist 行的 CAS 版本令牌：``updated_at.isoformat()``。

    与 ``GET /checklist-responses`` 回执的 ``version``、``lock_and_check_versions`` 预检算出的服务端版本
    同一写法 —— 三处一致，render 快照带出去的版本才能原样当 ``if_match`` 用。
    驱动没把列解析成 datetime 时（SQLite 文本列）原样返回字符串。
    """
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return str(value) or None


def checklist_snapshot_entry(row: object) -> dict[str, object]:
    """render 快照里的一条 checklist 回显：``conclusion`` / ``remark``，库里有这一行时再带 ``version``。

    K1~K13 与 D2 的宿主只用 render 快照建编辑基线（快照非空就不再 GET），保存走严格 CAS
    （``require_if_match``）；快照不带版本 ⇒ 前端没有 ``if_match`` ⇒ 已有行一保存就 428。
    调用方的查询必须同时选出 ``updated_at``。
    """
    entry: dict[str, object] = {
        "conclusion": getattr(row, "conclusion", None) or "",
        "remark": getattr(row, "remark", None) or "",
    }
    version = checklist_response_version(getattr(row, "updated_at", None))
    if version:
        entry["version"] = version
    return entry


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
    """按稳定顺序取得 checklist 逻辑键和现存行锁，供 HTTP CAS 与 OO mirror 共用。

    往返次数：advisory lock 逐 item 一条 + 现存行锁合并成一条（D4 有 46 个 store item，
    合并前是 92 次往返，且这段跑在 `_commit_once` 的 per-wp 临界区内）。

    🔴 advisory lock **不能**合并成单条语句。死锁安全完全依赖「两条路径都按 item_id 升序
    逐个取锁」：单条语句里对集合求值的顺序 PG 不保证（`ORDER BY` 只约束输出顺序，不约束
    函数求值顺序），一旦两个并发事务的求值顺序相反就会互等成死锁 —— 把 92 次往返换成一次
    偶发死锁不是优化。

    🔴 `FOR UPDATE` **可以**合并：走到这一步时本事务已持有全部 item 的 advisory lock，
    任何同样经过本 helper 的写者都还阻塞在 advisory 阶段，不可能在这些行上与我交错；
    不走本 helper 的旧 LWW 写者不取 advisory lock、也不会等我，故不构成环。
    """
    normalized = tuple(sorted(set(item_ids)))
    if any(not isinstance(item_id, str) or not item_id.strip() for item_id in normalized):
        raise ValueError("checklist item_id 必须是非空字符串")
    if not _uses_postgresql(db):
        # SQLite/轻量桩没有 PG advisory lock；并发保证只由真实 PG 测试声明。
        return normalized
    if not normalized:
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
            "WHERE wp_id = :wp_id AND item_id = ANY(:item_ids) "
            "ORDER BY item_id FOR UPDATE"
        ),
        {"wp_id": str(wp_id), "item_ids": list(normalized)},
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
