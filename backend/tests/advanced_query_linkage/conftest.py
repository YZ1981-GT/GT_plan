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
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbBalance
from app.models.dataset_models import LedgerDataset
from tests.advanced_query_linkage.builder_client import BuilderClient, builder_client
from tests.advanced_query_linkage.business_client import BusinessClient, business_client
from tests.advanced_query_linkage.gold import Gold, require_pg_only
from tests.advanced_query_linkage.project_picks import Pick, PickResolver
from tests.advanced_query_linkage.writable_projects import insert_test_project
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
async def picks(request: pytest.FixtureRequest) -> AsyncIterator[PickResolver]:
    """按数据能力动态解析真库项目（见 ``project_picks``）。

    取代 ``gold.py`` 里写死的 9 个项目 UUID —— 那 9 个 2026-11-01 现算在 ``projects``
    表里全都查不到行，用例会拿 403 / 空集跟空金标准互相印证而假绿。
    """
    require_pg_only(request.node)
    engine = pg_engine()
    try:
        yield PickResolver(engine)
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
async def no_active_dataset_project(request: pytest.FixtureRequest, pg_rollback_session: AsyncSession) -> Pick:
    """回滚事务里自建「该年度没有 active 数据集」的【测试】项目（带几行余额表）。

    为什么不从真库里挑：现算共享库里**没有任何活项目的审计年度是「没有 active 数据集」的**
    （8 个有余额表行的项目全都有 active 数据集，见 `closure.md` §16.7）。
    若退而求其次挑一个「生效口径恰好等于只按未删」的项目，断言照样绿，但走的是
    「所有行都属于生效数据集」那条路 —— **分支覆盖会静默丢失**。

    这是结构分支而非数据分布判据，自建夹具不会削弱它：行数与数据集归属由用例自己定，
    比依赖共享库里恰好存在某种项目更确定。
    """
    require_pg_only(request.node)
    session = pg_rollback_session
    year = 2025
    # 🔴 不能用 `session.add(Project(...))`：ORM 已声明共享库还没有的 `amount_unit`（V250 未落库），
    #    ORM 的 INSERT 会带上它而当场 UndefinedColumnError。见 `writable_projects` 模块说明。
    pid, name = await insert_test_project(session, name_suffix="无生效数据集", audit_year=year)
    for index, code in enumerate(("1001", "1002", "1122")):
        session.add(
            TbBalance(
                project_id=pid,
                year=year,
                company_code="AQL0",
                account_code=code,
                account_name=f"【测试】科目 {code}",
                dataset_id=None,
                is_deleted=False,
            )
        )
        # 再放一行软删的，验「只按未删」这一半也真的在过滤
        session.add(
            TbBalance(
                project_id=pid,
                year=year,
                company_code="AQL0",
                account_code=f"{code}-deleted-{index}",
                account_name="【测试】软删行",
                dataset_id=None,
                is_deleted=True,
            )
        )
    await session.flush()
    assert not (
        await session.execute(
            sa.select(sa.func.count())
            .select_from(LedgerDataset.__table__)
            .where(LedgerDataset.project_id == pid)
        )
    ).scalar_one(), "自建项目不应有任何数据集行（否则这条分支没被走到）"
    return Pick(
        id=pid,
        name=name,
        audit_year=year,
        report_scope="standalone",
        template_type=None,
        capability="selfbuilt:no_active_dataset",
        metric=3,
    )


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
