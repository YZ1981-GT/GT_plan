"""C2/C3：同一套合并附注子树断言在真实 PostgreSQL 上逐值对拍。

执行前必须设置：
- ``DATABASE_URL=postgresql+asyncpg://.../gt_consol_reaggregate``（一次性库）
- ``GT_CONSOL_REAGGREGATE_PG=1``
- ``GT_REQUIRE_PG=1``

fixture 在提交型临时 schema 里运行，结束后 DROP SCHEMA，不写 public。
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import tests.conftest  # noqa: F401
from app.core.config import settings
from app.models.base import Base

from tests.services import test_consol_note_subtree_reaggregate as _fixtures
from app.services.consol_note_subtree_reaggregate import reaggregate_subtree

#: 复用既有夹具：pytest 按名字解析 fixture，直接 import 名字会被 ruff 判成
#: 未使用 / 重定义；这里显式重导出，语义与 import 等价。
_SECTION = _fixtures._SECTION
_YEAR = _fixtures._YEAR
_rec = _fixtures._rec
_rows = _fixtures._rows
_setup = _fixtures._setup
user = _fixtures.user
group = _fixtures.group

pytestmark = [
    pytest.mark.pg_only,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.environ.get("GT_CONSOL_REAGGREGATE_PG", "").strip() not in ("1", "true", "yes"),
        reason="需要 GT_CONSOL_REAGGREGATE_PG=1 显式启用一次性 PG 合并附注对拍",
    ),
]


@pytest_asyncio.fixture
async def factory():
    url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in url or "audit_platform" in url.lower():
        pytest.skip("PG 模式需要 DATABASE_URL 指向非共享一次性库")
    schema = f"consol_reagg_{uuid.uuid4().hex[:12]}"
    ssl_args = {"ssl": False} if settings.DB_DISABLE_SSL else {}
    admin = create_async_engine(url, poolclass=NullPool, connect_args=ssl_args)
    world = None
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", public')
            await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn))
        connect_args = {**ssl_args, "server_settings": {"search_path": f"{schema},public"}}
        world = create_async_engine(url, poolclass=NullPool, connect_args=connect_args)
        yield async_sessionmaker(world, class_=AsyncSession, expire_on_commit=False)
    finally:
        if world is not None:
            await world.dispose()
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin.dispose()


@pytest_asyncio.fixture
async def db(factory):
    async with factory() as session:
        yield session


async def test_pg_full_subtree_reaggregate_matches_sqlite_value_contract(db, user, group):
    """PG 真实写入后，叶子 / 差额 / 中间汇总 / 根汇总逐值等于既有业务契约。"""
    await _setup(db, user, group)
    result = await reaggregate_subtree(
        db, group["G"].id, _YEAR, node_key="G:consol", section_ids=[_SECTION]
    )
    assert result["status"] == "persisted", result["failures"]
    assert result["sections_updated"] == 1

    # 叶子：来源必须来自单体附注，不是试算表
    a1 = await _rec(db, group, "A1:subsidiary")
    assert _rows(a1)["库存现金"] == (Decimal("100.00"), Decimal("50.00"))
    assert _rows(a1)["合计"] == (Decimal("2600.00"), Decimal("1050.00"))

    # 差额：抵销分录 + 公式值，且来源是 formula
    elim = await _rec(db, group, "A:consol_elim")
    assert elim.data["_last_write_source"] == "formula"
    assert _rows(elim)["银行存款"][0] == Decimal("-100")

    # 中间汇总：A 本部 + A1 + A 差额
    middle = _rows(await _rec(db, group, "A:consol"))
    assert middle["库存现金"] == (Decimal("476.73"), Decimal("336.73"))
    assert middle["银行存款"] == (Decimal("1001900.00"), Decimal("801000.00"))
    assert middle["合计"] == (Decimal("1002876.73"), Decimal("801336.73"))

    # 根汇总：A 合并 + B，差额节点不计入子企业计数；公式快照保留试算表口径
    root = await _rec(db, group, "G:consol")
    rows = _rows(root)
    assert rows["库存现金"] == (Decimal("1476.73"), Decimal("1336.73"))
    assert rows["银行存款"] == (Decimal("1001900.00"), Decimal("801000.00"))
    assert rows["合计"] == (Decimal("1003876.73"), Decimal("802336.73"))
    assert root.data["_last_write_source"] == "subtree_aggregate"
    assert root.data["_subtree_child_count"] == 2
    assert root.is_stale is False
    assert root.data["_subtree_provenance"]["children"]


async def test_pg_manual_cells_are_preserved_and_included(db, user, group):
    """PG 逐值对拍：手工格保留，自动合计仍纳入手工值。"""
    from tests.services.test_consol_note_subtree_reaggregate import (
        TestProtectionAndSkips,
    )

    await TestProtectionAndSkips.test_manual_cell_kept_and_counted_in_total(
        object(), db, user, group
    )


async def test_pg_invalid_protection_rolls_back_whole_section(db, user, group):
    """PG 逐值对拍：坏保护元数据触发章节 SAVEPOINT 回滚，不留下前序节点写入。"""
    from tests.services.test_consol_note_subtree_reaggregate import (
        TestProtectionAndSkips,
    )

    await TestProtectionAndSkips.test_invalid_protection_metadata_rolls_back_whole_section(
        object(), db, user, group
    )
