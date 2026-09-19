"""统一字段覆盖存储 set/get 往返 PBT

Property: 对任意合法 scope+item_key+field+value 组合，
set 后 get 返回相同值，get_batch 包含该条目。

max_examples=5（项目铁律）。
"""

from __future__ import annotations

import asyncio
import uuid

from hypothesis import given, settings, assume
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base, UserRole
from app.models.core import User
from app.models.workpaper_field_override_models import WorkpaperFieldOverride
from app.services.field_override_service import FieldOverrideService

# SQLite JSONB 兼容
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_TABLES = [
    User.__table__,
    WorkpaperFieldOverride.__table__,
]


# Strategies
scope_st = st.from_regex(r"[a-z_]{2,10}:[A-Z][0-9\-]{0,8}", fullmatch=True).filter(
    lambda s: len(s) <= 50
)
item_key_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
    min_size=1,
    max_size=30,
)
field_st = st.from_regex(r"[a-z_]{2,20}", fullmatch=True).filter(
    lambda s: len(s) <= 50
)
value_st = st.one_of(
    st.none(),
    st.text(min_size=0, max_size=50),
    st.integers(min_value=-999999, max_value=999999),
    st.booleans(),
    st.dictionaries(st.text(min_size=1, max_size=10), st.integers(), max_size=3),
)


def _run_in_isolated_db(coro_factory):
    """单个 hypothesis 样例用独立内存库。"""

    async def _runner():
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                # Seed user
                user_id = uuid.uuid4()
                session.add(
                    User(
                        id=user_id,
                        username=f"pbt_{user_id.hex[:8]}",
                        email=f"pbt_{user_id.hex[:8]}@test.com",
                        hashed_password="x",
                        role=UserRole.admin,
                    )
                )
                await session.flush()
                return await coro_factory(session, user_id)
        finally:
            await engine.dispose()

    return asyncio.run(_runner())


@given(
    scope=scope_st,
    item_key=item_key_st,
    field=field_st,
    value=value_st,
)
@settings(max_examples=5, deadline=None)
def test_set_get_roundtrip(scope, item_key, field, value):
    """Property: set(v) → get() == v，get_batch 包含该条目。"""

    async def _body(session: AsyncSession, user_id: uuid.UUID):
        project_id = uuid.uuid4()
        year = 2025
        svc = FieldOverrideService(session)

        # set
        override = await svc.set(project_id, year, scope, item_key, field, value, user_id)
        assert override.id is not None

        # get 往返
        got = await svc.get(project_id, year, scope, item_key, field)
        assert got == value

        # get_batch 包含
        batch = await svc.get_batch(project_id, year, scope)
        assert item_key in batch
        assert field in batch[item_key]
        assert batch[item_key][field] == value

    _run_in_isolated_db(_body)


@given(
    scope=scope_st,
    item_key=item_key_st,
    field=field_st,
    v1=value_st,
    v2=value_st,
)
@settings(max_examples=5, deadline=None)
def test_set_overwrite(scope, item_key, field, v1, v2):
    """Property: 二次 set 覆盖第一次值，get 返回最后一次 set 的值。"""

    async def _body(session: AsyncSession, user_id: uuid.UUID):
        project_id = uuid.uuid4()
        year = 2025
        svc = FieldOverrideService(session)

        await svc.set(project_id, year, scope, item_key, field, v1, user_id)
        await svc.set(project_id, year, scope, item_key, field, v2, user_id)

        got = await svc.get(project_id, year, scope, item_key, field)
        assert got == v2

    _run_in_isolated_db(_body)


def test_merge_override_priority():
    """merge 静态测试：覆盖值非 None 时替换自动值。"""
    auto = {"applicable": True, "executor": "系统", "summary": "自动生成"}
    overrides = {"executor": "张三", "summary": None}
    merged = FieldOverrideService.merge(auto, overrides)
    assert merged["applicable"] is True  # 无覆盖保留
    assert merged["executor"] == "张三"  # 覆盖生效
    assert merged["summary"] == "自动生成"  # None 覆盖不替换
