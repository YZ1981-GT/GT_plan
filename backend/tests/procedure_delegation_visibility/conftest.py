# Feature: procedure-delegation-visibility-isolation — shared test fixtures
"""事务隔离 PG session fixture（用例结束回滚，不污染 dev 库）。

Task 14：在收集本目录时幂等注册 smoke/correctness/fast Hypothesis profile（隔离运行时兜底，
backend/tests/conftest.py 亦注册），并在 session 结束时把每 property 有效样例计数 + P1–P20
覆盖矩阵报告落地到 ``evidence/artifacts/task14/valid_example_counts.json``。
"""
from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings

from . import _pbt_profiles as _pbt

# 幂等注册双 profile（backend conftest 先注册；此处兜底隔离收集场景）。
_pbt.register_profiles()

_IS_PG = app_settings.DATABASE_URL.startswith("postgresql")

# spec 目录内相对路径（供 evidence manifest 使用 spec-relative artifact）。
_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPORT_ABS = (
    _REPO_ROOT
    / ".kiro" / "specs" / "procedure-delegation-visibility-isolation"
    / "evidence" / "artifacts" / "task14" / "valid_example_counts.json"
)


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """落地 Task 14 有效样例计数报告（若本次 session 跑到任一 property 测试）。"""
    try:
        if _pbt.VALID_EXAMPLE_COUNTS:
            _pbt.write_report(_REPORT_ABS)
    except Exception:  # noqa: BLE001 — 报告落地失败不影响测试结论
        pass


@pytest_asyncio.fixture
async def session():
    if not _IS_PG:
        pytest.skip("need PostgreSQL (visibility role/mapping)")
    engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True)
    try:
        conn = await engine.connect()
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")
    trans = await conn.begin()
    s = AsyncSession(bind=conn)
    try:
        yield s
    finally:
        await s.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()
