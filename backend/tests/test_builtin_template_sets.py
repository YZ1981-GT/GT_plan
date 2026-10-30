"""内置模板集初始化（spec trim-followup-residual-findings-closure R2）。

原状（可打红）：生成弹窗每次打开先 ``POST /api/template-sets/seed``（只读账号也写、任何登录用户都能改写内置集）；
种子一键加载的 template_sets 分支 import 不存在的 ``app.services.wp_template_service``，ImportError 被吞成
「已加载、0 条」。现：启动任务 ``seed_builtin_template_sets``（singleton、best_effort）幂等初始化，手动端点
（admin / partner）与一键加载走同一函数；每个内置集一个保存点，并发撞唯一键只回滚自己。
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.workpaper_models import WpTemplateSet
from app.services import builtin_template_sets as bts
from app.services.template_engine import BUILTIN_TEMPLATE_SETS

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with _factory() as session:
        yield session


async def _rows(session: AsyncSession) -> list[WpTemplateSet]:
    return list((await session.execute(sa.select(WpTemplateSet))).scalars())


@pytest.mark.asyncio
async def test_first_seed_inserts_then_second_is_noop(db):
    first = await bts.seed_builtin_template_sets_safely(db)
    await db.commit()
    assert first.as_dict() == {"inserted": len(BUILTIN_TEMPLATE_SETS), "updated": 0, "unchanged": 0}
    second = await bts.seed_builtin_template_sets_safely(db)
    await db.commit()
    assert second.changed == [] and second.as_dict() == {"inserted": 0, "updated": 0, "unchanged": len(BUILTIN_TEMPLATE_SETS)}
    assert [r.set_name for r in await _rows(db)] == [d["set_name"] for d in BUILTIN_TEMPLATE_SETS]


@pytest.mark.asyncio
async def test_changed_codes_are_updated(db):
    name = BUILTIN_TEMPLATE_SETS[0]["set_name"]
    db.add(WpTemplateSet(set_name=name, template_codes=["A1"], applicable_audit_type="annual", description="旧说明"))
    await db.commit()
    result = await bts.seed_builtin_template_sets_safely(db)
    await db.commit()
    assert result.as_dict()["updated"] == 1
    (row,) = await _rows(db)
    assert row.template_codes == BUILTIN_TEMPLATE_SETS[0]["template_codes"]
    assert row.description == BUILTIN_TEMPLATE_SETS[0]["description"]


@pytest.mark.asyncio
async def test_concurrent_insert_rolls_back_only_its_savepoint(db, monkeypatch):
    """别的进程刚插入同名内置集：查询时还没看到、flush 撞 set_name 唯一键 ⇒ 只回滚这一个保存点，会话照常可提交。"""
    name = BUILTIN_TEMPLATE_SETS[0]["set_name"]
    db.add(WpTemplateSet(set_name=name, template_codes=["X1"], applicable_audit_type="annual", description="别的进程"))
    await db.commit()

    real_execute = db.execute
    hidden = {"done": False}

    async def racing_execute(stmt, *args, **kwargs):
        if not hidden["done"] and "wp_template_set" in str(stmt) and str(stmt).lstrip().upper().startswith("SELECT"):
            hidden["done"] = True
            res = MagicMock()
            res.scalar_one_or_none.return_value = None  # 还没看到对方的插入
            return res
        return await real_execute(stmt, *args, **kwargs)

    monkeypatch.setattr(db, "execute", racing_execute)
    result = await bts.seed_builtin_template_sets_safely(db)
    monkeypatch.setattr(db, "execute", real_execute)
    await db.commit()

    assert hidden["done"]
    assert result.as_dict() == {"inserted": 0, "updated": 0, "unchanged": 1}
    (row,) = await _rows(db)
    assert row.template_codes == ["X1"]  # 对方的行原样


@pytest.mark.asyncio
async def test_ensure_opens_own_session_and_commits(db, monkeypatch):
    from app.core import database

    monkeypatch.setattr(database, "async_session", _factory)
    result = await bts.ensure_builtin_template_sets()
    assert result.inserted == len(BUILTIN_TEMPLATE_SETS)
    async with _factory() as other:
        assert len(await _rows(other)) == len(BUILTIN_TEMPLATE_SETS)  # 已提交


def test_startup_task_registered_as_singleton_best_effort():
    from app.core import startup_registry as sr

    names = [t.name for t in sr.STARTUP_TASKS]
    spec = next(t for t in sr.STARTUP_TASKS if t.name == "seed_builtin_template_sets")
    assert (spec.phase, spec.criticality, spec.singleton) == ("seeds", "best_effort", True)
    # 迁移与 schema 校验之后、预热渲染缓存之前
    assert names.index("run_migrations") < names.index("run_schema_drift_check") < names.index(spec.name)
    assert names.index(spec.name) == names.index("warm_render_caches") - 1


@pytest.mark.asyncio
async def test_startup_task_runs_ensure(monkeypatch):
    from app.core import startup_registry as sr

    ensure = AsyncMock(return_value=bts.BuiltinSeedResult())
    monkeypatch.setattr(bts, "ensure_builtin_template_sets", ensure)
    spec = next(t for t in sr.STARTUP_TASKS if t.name == "seed_builtin_template_sets")
    await spec.run(sr.StartupContext())
    ensure.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_seed_all_template_sets_branch_really_seeds(db):
    """原先 import 不存在的模块、ImportError 被吞 ⇒ 报「已加载」但 0 条。"""
    from app.routers.template_library_mgmt import _exec_seed

    out = await _exec_seed("template_sets", db, types.SimpleNamespace(id=None))
    await db.commit()
    assert out["status"] == "loaded"
    assert out["inserted"] == len(BUILTIN_TEMPLATE_SETS)
    assert out["record_count"] == len(BUILTIN_TEMPLATE_SETS)
    assert len(await _rows(db)) == len(BUILTIN_TEMPLATE_SETS)
