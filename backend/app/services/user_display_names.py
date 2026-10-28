"""用户显示名：user_id → 人员档案姓名（优先）/ 用户名 —— 批量、只读。

原先只在底稿看板（``wp_batch_router``）里有一份；底稿列表的「编制人」恒「—」（列表接口只回 id，前端读不存在的
``assignee_name``），回收站「删除人」恒空 —— 都改用这一份（spec procedure-chain-followup-closure R3.1 / R3.2）。

fail-open：任一查询异常返回已解析部分，不阻断主体。
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


def _as_uuid(value) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


async def resolve_user_display_names(db: AsyncSession, user_ids: Iterable) -> dict[str, str]:
    """``{str(user_id): 显示名}``；人员档案（未删除）姓名优先，回退 ``users.username``。"""
    from app.models.core import User
    from app.models.staff_models import StaffMember

    ids = sorted({u for u in (_as_uuid(v) for v in user_ids if v) if u})
    names: dict[str, str] = {}
    if not ids:
        return names
    # 两条查询各自 fail-open，互不影响；SAVEPOINT 隔离：PG 上失败的语句不能把调用方事务拖成 aborted
    try:
        async with db.begin_nested():
            rows = (await db.execute(sa.select(StaffMember.user_id, StaffMember.name).where(
                StaffMember.user_id.in_(ids), StaffMember.is_deleted == sa.false(),
            ).order_by(StaffMember.created_at, StaffMember.id))).all()  # 一人多条档案时取最早建的那条
        for uid, name in rows:
            if uid and name:
                names.setdefault(str(uid), name)
    except Exception:  # noqa: BLE001 — 人员档案解析失败不影响主体
        pass
    try:
        async with db.begin_nested():
            rows = (await db.execute(sa.select(User.id, User.username).where(User.id.in_(ids)))).all()
        for uid, username in rows:
            if username:
                names.setdefault(str(uid), username)
    except Exception:  # noqa: BLE001
        pass
    return names
