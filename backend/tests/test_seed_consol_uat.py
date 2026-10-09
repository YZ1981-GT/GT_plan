"""合并 UAT seed 的数据库契约测试。

验证 seed 写入的项目年度/企业关系是合并树的可消费输入，并验证重复运行与
历史缺字段修复不会制造重复项目或覆盖业务年度。
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import database
from app.models.audit_platform_models import TrialBalance
from app.models.base import Base, UserRole
from app.models.consolidation_models import EliminationEntry, InternalTrade
from app.models.core import Project, User
from app.services.consol_group_tree import (
    MODE_SUBSIDIARY,
    ROLE_CONSOL,
    ROLE_CONSOL_ELIM,
    ROLE_PARENT,
    ROLE_SUBSIDIARY,
)
from app.services.consol_tree_service import build_tree, iter_nodes

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

_REPO = Path(__file__).resolve().parents[2]
_SEED_PATH = _REPO / "backend" / "scripts" / "seed" / "seed_consol_uat.py"
_SPEC = importlib.util.spec_from_file_location("test_seed_consol_uat_script", _SEED_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_seed = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _seed
_SPEC.loader.exec_module(_seed)

_ENGINE = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_ENGINE, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
def seed_session(monkeypatch):
    factory = async_sessionmaker(_ENGINE, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(database, "async_session", factory)
    return factory


async def _count(db: AsyncSession, model: type) -> int:
    return int((await db.execute(select(func.count()).select_from(model))).scalar_one())


@pytest.mark.asyncio
async def test_seed_is_idempotent_and_tree_consumable(db, seed_session):
    plan = _seed.build_plan(2025)

    first = await _seed.seed(plan)
    second = await _seed.seed(plan)

    assert first["year"] == 2025
    assert second["parent_id"] == first["parent_id"]
    assert len(first["stats"]["created"]) == 15
    assert first["stats"]["updated"] == []
    assert second["stats"]["created"] == []
    assert second["stats"]["updated"] == []
    assert len(second["stats"]["skipped"]) == 15

    assert await _count(db, User) == 1
    assert await _count(db, Project) == 3
    assert await _count(db, TrialBalance) == 8
    assert await _count(db, EliminationEntry) == 2
    assert await _count(db, InternalTrade) == 1

    parent_id = uuid.UUID(first["parent_id"])
    projects = (
        await db.execute(
            select(Project).where(
                Project.client_name.in_([_seed.PARENT_NAME, _seed.CHILD_A_NAME, _seed.CHILD_B_NAME])
            )
        )
    ).scalars().all()
    assert {project.audit_year for project in projects} == {2025}
    assert {project.relation_to_parent for project in projects if project.id != parent_id} == {"subsidiary"}

    tree = await build_tree(db, parent_id)
    assert tree is not None
    assert tree.mode == MODE_SUBSIDIARY
    assert [node.role for node in iter_nodes(tree)] == [
        ROLE_CONSOL,
        ROLE_CONSOL_ELIM,
        ROLE_PARENT,
        ROLE_SUBSIDIARY,
        ROLE_SUBSIDIARY,
    ]
    assert tree.children[0].host_project_id == parent_id
    assert tree.children[0].project_id is None
    assert tree.children[1].project_id is None
    assert "standalone_missing" in tree.children[1].flags
    assert [node.project_id is not None for node in tree.children[2:]] == [True, True]


@pytest.mark.asyncio
async def test_seed_repairs_missing_metadata_without_replacing_ids(db, seed_session):
    user = User(
        id=uuid.uuid4(),
        username="uat_consol_seed",
        email="uat_consol_seed@uat.local",
        hashed_password="!uat-seed-not-loginable!",
        role=UserRole.admin,
    )
    parent_id = uuid.uuid4()
    child_id = uuid.uuid4()
    parent = Project(
        id=parent_id,
        name=_seed.PARENT_NAME,
        client_name=_seed.PARENT_NAME,
        company_code=_seed.PARENT_CODE,
        ultimate_company_code=_seed.PARENT_CODE,
        report_scope="consolidated",
        manager_id=user.id,
        audit_year=None,
    )
    child = Project(
        id=child_id,
        name=_seed.CHILD_A_NAME,
        client_name=_seed.CHILD_A_NAME,
        company_code=_seed.CHILD_A_CODE,
        parent_company_code=_seed.PARENT_CODE,
        ultimate_company_code=_seed.PARENT_CODE,
        report_scope="standalone",
        manager_id=user.id,
        audit_year=None,
        relation_to_parent=None,
    )
    db.add_all([user, parent, child])
    await db.commit()

    result = await _seed.seed(_seed.build_plan(2025))

    assert result["parent_id"] == str(parent_id)
    assert set(result["stats"]["updated"]) == {
        f"parent_project:{_seed.PARENT_NAME}/audit_year",
        f"child_project:{_seed.CHILD_A_NAME}/audit_year",
        f"child_project:{_seed.CHILD_A_NAME}/relation_to_parent",
        f"child_project:{_seed.CHILD_A_NAME}/parent_project_id",
    }
    await db.refresh(parent)
    await db.refresh(child)
    assert parent.audit_year == 2025
    assert child.audit_year == 2025
    assert child.relation_to_parent == "subsidiary"
    assert child.parent_project_id == parent_id
    assert await _count(db, Project) == 3


@pytest.mark.asyncio
async def test_seed_rejects_existing_project_from_other_year(db, seed_session):
    user = User(
        id=uuid.uuid4(),
        username="uat_consol_seed",
        email="uat_consol_seed@uat.local",
        hashed_password="!uat-seed-not-loginable!",
        role=UserRole.admin,
    )
    parent = Project(
        id=uuid.uuid4(),
        name=_seed.PARENT_NAME,
        client_name=_seed.PARENT_NAME,
        company_code=_seed.PARENT_CODE,
        ultimate_company_code=_seed.PARENT_CODE,
        report_scope="consolidated",
        audit_year=2024,
        manager_id=user.id,
    )
    db.add_all([user, parent])
    await db.commit()

    with pytest.raises(ValueError, match="已有 audit_year=2024"):
        await _seed.seed(_seed.build_plan(2025))

    await db.refresh(parent)
    assert parent.audit_year == 2024
    assert await _count(db, Project) == 1


@pytest.mark.asyncio
async def test_seed_rejects_non_subsidiary_child_relation(db, seed_session):
    user = User(
        id=uuid.uuid4(),
        username="uat_consol_seed",
        email="uat_consol_seed@uat.local",
        hashed_password="!uat-seed-not-loginable!",
        role=UserRole.admin,
    )
    parent = Project(
        id=uuid.uuid4(),
        name=_seed.PARENT_NAME,
        client_name=_seed.PARENT_NAME,
        company_code=_seed.PARENT_CODE,
        ultimate_company_code=_seed.PARENT_CODE,
        report_scope="consolidated",
        audit_year=2025,
        manager_id=user.id,
    )
    child = Project(
        id=uuid.uuid4(),
        name=_seed.CHILD_A_NAME,
        client_name=_seed.CHILD_A_NAME,
        company_code=_seed.CHILD_A_CODE,
        parent_company_code=_seed.PARENT_CODE,
        ultimate_company_code=_seed.PARENT_CODE,
        report_scope="standalone",
        audit_year=2025,
        relation_to_parent="branch",
        manager_id=user.id,
    )
    db.add_all([user, parent, child])
    await db.commit()

    with pytest.raises(ValueError, match="relation_to_parent='branch'"):
        await _seed.seed(_seed.build_plan(2025))

    await db.refresh(child)
    assert child.relation_to_parent == "branch"
    assert await _count(db, Project) == 2
