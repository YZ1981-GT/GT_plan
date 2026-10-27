"""advanced-query-linkage-closure 后端测试共用夹具（design §10；实施计划 §0.5、§0.13）。

- ``pg_only``：本目录用到真库夹具（``gold``、``pg_rollback_session``）的用例必须带 ``pytest.mark.pg_only``——
  不带就当场报错，不连库（``gold.require_pg_only``）。口径类断言在 SQLite 上表达不了 PG 枚举、缺表与多数据集，
  跳过即没测：跑真库时核对 skipped 为 0。
- ``gold``：金标准读取器（``gold.Gold``）。每条查询开独立连接、只读事务、结束回滚，不经被测代码、不与被测会话共享
  事务（被测代码出错使事务 aborted 时金标准照常可读）。SQL 片段见 ``gold.active_sql``。
- ``pg_rollback_session``：真库回滚事务会话。同一连接 ``begin()``，会话以 ``join_transaction_mode="create_savepoint"``
  加入——被测代码的 ``commit`` 只释放保存点；结束整体 rollback，不留任何写入。只许写名称带【测试】/【UAT】的项目。
- ``builder``：真库构建器客户端（``builder_client.BuilderClient``），请求经生产注册的 query_builder router，会话即上面的
  回滚事务会话。
- ``business``：真库业务视图客户端（``business_client.BusinessClient``，系统管理员），请求经生产注册的 custom_query
  router，会话同上。

连接串只取进程环境变量 ``DATABASE_URL``（与 ``tests.authz_world.pg_engine`` 同一入口），命令行里设置、跑完即删。
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from tests.advanced_query_linkage.builder_client import BuilderClient, builder_client
from tests.advanced_query_linkage.business_client import BusinessClient, business_client
from tests.advanced_query_linkage.gold import Gold, require_pg_only
from tests.authz_world import pg_engine


@pytest_asyncio.fixture
async def gold(request: pytest.FixtureRequest) -> AsyncIterator[Gold]:
    require_pg_only(request.node)
    engine = pg_engine()
    try:
        yield Gold(engine)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def pg_rollback_session(request: pytest.FixtureRequest) -> AsyncIterator[AsyncSession]:
    require_pg_only(request.node)
    engine = pg_engine()
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            try:
                async with AsyncSession(
                    bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint",
                ) as session:
                    yield session
            finally:
                await outer.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def builder(pg_rollback_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[BuilderClient]:
    """真库构建器客户端：生产注册的 query_builder router + 回滚事务会话（见 ``builder_client``）。"""
    async with builder_client(pg_rollback_session, monkeypatch) as client:
        yield client


@pytest_asyncio.fixture
async def business(pg_rollback_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[BusinessClient]:
    """真库业务视图客户端：生产注册的 custom_query router + 回滚事务会话（见 ``business_client``）。"""
    async with business_client(pg_rollback_session, monkeypatch) as client:
        yield client
