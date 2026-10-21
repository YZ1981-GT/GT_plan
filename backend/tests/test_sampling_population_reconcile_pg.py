"""总体完整性核对 — PostgreSQL 保存点隔离守卫

spec: voucher-sampling-reconcile-balance-source

抽凭端点在同一事务里先做总体完整性核对，后面还要补往来单位、对方科目、跨底稿重复检测。
PG 上任何一条语句失败都会让**整个事务**进入 aborted 状态，后续查询全部报错；
核对取数因此包在 ``begin_nested()`` 保存点里，失败只回滚保存点。

本守卫在保存点内制造**真实的库端错误**（表不存在），断言：
1. 核对返回「不可用 + 取数失败」，不抛出；
2. 外层事务仍可执行查询（未 aborted）；
3. 外层事务里先前设置的事务级变量还在（未被整体回滚 —— 若有人在 except 里写
   ``await db.rollback()``，这一条会打红）。

故障注入点是被测函数读取的**表对象**（下一层），被测函数本身不替换。
全程只读，结束回滚。
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.services.sampling_population_reconcile as reconcile_module
from app.core.config import settings

pytestmark = pytest.mark.pg_only


@pytest.fixture
async def pg_session():
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        pytest.skip("需要真实 PostgreSQL")
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
    await engine.dispose()


def _missing_table() -> type:
    table = sa.table(
        "tb_balance_reconcile_guard_missing",
        sa.column("project_id"), sa.column("year"), sa.column("is_deleted"),
        sa.column("dataset_id"), sa.column("account_code"),
        sa.column("debit_amount"), sa.column("credit_amount"),
    )

    class _Missing:
        __table__ = table

    return _Missing


@pytest.mark.asyncio
async def test_sql_error_inside_savepoint_keeps_outer_transaction(pg_session, monkeypatch):
    await pg_session.execute(
        sa.text("SELECT set_config('gt.reconcile_guard', 'kept', true)")
    )
    monkeypatch.setattr(reconcile_module, "TbBalance", _missing_table())

    facts = await reconcile_module.resolve_population_reconcile(
        pg_session, uuid.uuid4(), 2025, ["1122"], None
    )

    assert facts.available is False
    assert facts.unavailable_reason == "总体完整性核对取数失败，请检查数据完整性后重试"
    # 外层事务未 aborted，且未被整体回滚（事务级变量仍在）
    kept = (
        await pg_session.execute(sa.text("SELECT current_setting('gt.reconcile_guard', true)"))
    ).scalar()
    assert kept == "kept"
