"""公式中枢 spec 的真 PG 测试基座（ADR-FHIC-25 第 3 点）：收集钩子 + ``pg_tx`` / ``committed_project`` 夹具。

实现在 ``tests/formula_hub/_pg_harness.py``；根 conftest 的 pg_only 跳过逻辑不改。
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from tests.formula_hub._pg_harness import committed_project_scope, pg_tx_session, require_pg_usage_error


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    """``GT_REQUIRE_PG=1`` 而 ``DATABASE_URL`` 不是 PostgreSQL ⇒ 整轮 UsageError（不出现 skip）。"""
    message = require_pg_usage_error()
    if message:
        raise pytest.UsageError(message)


@pytest_asyncio.fixture
async def pg_tx():
    """独立连接 + 外层事务 + ``create_savepoint`` 会话；用例结束一律回滚。"""
    async with pg_tx_session() as session:
        yield session


@pytest_asyncio.fixture
async def committed_project():
    """只供多会话并发用例：快照库内真提交的【测试】项目，结束按主键删净（库名非 fh_snap_ 开头即失败）。"""
    async with committed_project_scope() as handle:
        yield handle
