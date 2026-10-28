"""回收站列表排序与分页（真实 PG，回滚事务）。

spec procedure-chain-followup-closure R3.2 浏览器实测撞上的缺陷（2026-10-25）：删除项目起开始记 ``deleted_at``，
而列表每张表按 ``deleted_at`` 倒序取一页 —— PG 倒序把空值排最前，旧记录 ``deleted_at`` 全空 ⇒ 刚删的项目排到所有
旧记录之后、被每表一页的截断丢掉，回收站里看不到；每表只取一页还让单类型第 2 页起恒空。
SQLite 倒序空值排最后，测不出第一条，所以放真实 PG。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.core.pagination import PaginationParams
from app.models.base import ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.routers import recycle_bin

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def world():
    if not settings.DATABASE_URL.startswith("postgresql"):
        pytest.skip("need PostgreSQL")
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    conn = await engine.connect()
    trans = await conn.begin()
    db = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        tag = uuid.uuid4().hex[:8]
        user = User(username=f"rb_order_{tag}", email=f"rb_order_{tag}@example.com", hashed_password="x",
                    role=UserRole.manager, is_active=True)
        db.add(user)
        await db.flush()
        now = datetime.now(timezone.utc)
        legacy = []
        for i in range(3):  # 旧记录：删除时没记 deleted_at（updated_at 是当时的时间）
            p = Project(name=f"【测试】回收站旧项目{i}_{tag}", client_name="【测试】回收站排序", is_deleted=True,
                        updated_at=now - timedelta(days=3 - i))
            legacy.append(p)
        fresh = Project(name=f"【测试】回收站刚删的项目_{tag}", client_name="【测试】回收站排序", is_deleted=True,
                        deleted_at=now, updated_at=now, updated_by=user.id)
        db.add_all([*legacy, fresh])
        await db.flush()
        for p in (*legacy, fresh):
            db.add(ProjectUser(project_id=p.id, user_id=user.id, role=ProjectUserRole.manager))
        await db.flush()
        yield {"db": db, "user": user, "fresh": fresh, "legacy": legacy}
    finally:
        await db.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()


async def _page(world, page: int, page_size: int) -> dict:
    return await recycle_bin.list_recycle_bin(
        item_type="project", pagination=PaginationParams(page=page, page_size=page_size),
        db=world["db"], user=world["user"])


async def test_just_deleted_project_lists_first_with_its_deleter(world):
    res = await _page(world, 1, 2)
    assert res["total"] == 4
    first = res["items"][0]
    assert first["id"] == str(world["fresh"].id), [i["name"] for i in res["items"]]
    assert first["deleted_by"] == str(world["user"].id)
    assert first["deleted_by_name"] == world["user"].username
    # 旧记录按当时的时间（updated_at）排在后面，删除人不知道就空着
    assert res["items"][1]["id"] == str(world["legacy"][2].id) and res["items"][1]["deleted_by"] is None


async def test_second_page_is_not_empty(world):
    page1 = await _page(world, 1, 2)
    page2 = await _page(world, 2, 2)
    ids = [i["id"] for i in page1["items"] + page2["items"]]
    assert len(page2["items"]) == 2, "每表只取一页 ⇒ 第 2 页恒空"
    assert len(set(ids)) == 4 and ids[-1] == str(world["legacy"][0].id)
