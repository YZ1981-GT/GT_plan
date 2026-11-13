"""余额表右键「跳转到底稿」：科目 → 底稿（审定表优先）的解析。

- 纯映射：子科目归到映射表里最长的前缀科目；层级边界；审定表 → 主底稿 → 其他的排序；无映射返回空；
- 落库解析：审定表 sheet（E1-1）归到本项目已生成的所在底稿（E1），未生成返回 wp_id=None，已删除的底稿不算。
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus
from app.services.ledger_account_workpapers import (
    candidate_entries,
    classify,
    match_mapped_account,
    resolve_account_workpapers,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

USER, PROJECT = uuid.uuid4(), uuid.uuid4()


def test_child_account_matches_longest_mapped_prefix_on_level_boundary():
    mapped = {"1002", "1012", "10", "1122"}
    assert match_mapped_account("1002", mapped) == "1002"
    assert match_mapped_account("1002.01", mapped) == "1002"
    assert match_mapped_account("1122.01.03", mapped) == "1122"
    # 前缀必须落在层级边界上：10021 不是 1002 的子科目，也不是 10 的子科目
    assert match_mapped_account("10021", mapped) is None
    assert match_mapped_account("10021", {"1002"}) is None
    assert match_mapped_account("", mapped) is None
    assert match_mapped_account("9999", {"1002"}) is None


def test_audit_determination_first_then_primary_then_other():
    matched, entries = candidate_entries("1002.01")
    assert matched == "1002"
    kinds = [classify(e) for e in entries]
    assert kinds == sorted(kinds, key={"audit_determination": 0, "primary": 1, "other": 2}.get)
    assert entries[0]["wp_code"] == "E1-1" and "审定表" in entries[0]["wp_name"]
    assert any(classify(e) == "primary" and e["wp_code"] == "E1" for e in entries)


def test_explicit_sheet_audit_entry_sorts_before_bare_workbook_code():
    # 应收账款：D2（册）与 D2-1（审定表 sheet）名称都含「审定表」，带 sheet 编码的排前，深链能落到具体 sheet
    _, entries = candidate_entries("1122.01")
    audit = [e["wp_code"] for e in entries if classify(e) == "audit_determination"]
    assert audit[0] == "D2-1" and "D2" in audit


def test_unmapped_account_returns_nothing():
    assert candidate_entries("9999") == (None, [])
    assert candidate_entries("") == (None, [])


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(User(id=USER, username="u", email="u@t.com", hashed_password="x", role="auditor"))
        session.add(Project(id=PROJECT, name="底稿定位", client_name="测试", project_type=ProjectType.annual,
                            status=ProjectStatus.execution, created_by=USER, audit_period_end=date(2025, 12, 31)))
        yield session
    await engine.dispose()


def _add_wp(session, code: str, *, deleted: bool = False) -> uuid.UUID:
    wp_id = uuid.uuid4()
    wi = WpIndex(id=uuid.uuid4(), project_id=PROJECT, wp_code=code, wp_name=f"{code} 名称", audit_cycle=code[0],
                 status=WpStatus.not_started)
    session.add(wi)
    session.add(WorkingPaper(id=wp_id, project_id=PROJECT, wp_index_id=wi.id, file_path="x.xlsx",
                             source_type=WpSourceType.template, file_version=1, is_deleted=deleted))
    return wp_id


@pytest.mark.asyncio
async def test_audit_sheet_resolves_to_generated_host_workbook(db):
    e1 = _add_wp(db, "E1")
    await db.flush()
    matched, items = await resolve_account_workpapers(db, PROJECT, "1002.01")
    assert matched == "1002"
    first = items[0]
    assert (first.wp_code, first.kind, first.host_wp_code, first.wp_id) == ("E1-1", "audit_determination", "E1", str(e1))
    # 同账套里没生成的底稿（E0 函证等）wp_id 为空，不会被误指向别的底稿
    e0 = next(i for i in items if i.wp_code == "E0")
    assert e0.wp_id is None and e0.host_wp_code is None


@pytest.mark.asyncio
async def test_not_generated_and_deleted_workpapers_have_no_id(db):
    _add_wp(db, "E1", deleted=True)           # 已删除的不算
    await db.flush()
    _, items = await resolve_account_workpapers(db, PROJECT, "1002")
    assert items and all(i.wp_id is None for i in items)


@pytest.mark.asyncio
async def test_other_project_workpapers_are_not_used(db):
    other = uuid.uuid4()
    db.add(Project(id=other, name="别的项目", client_name="测试", project_type=ProjectType.annual,
                   status=ProjectStatus.execution, created_by=USER))
    wi = WpIndex(id=uuid.uuid4(), project_id=other, wp_code="E1", wp_name="E1", audit_cycle="E", status=WpStatus.not_started)
    db.add(wi)
    db.add(WorkingPaper(id=uuid.uuid4(), project_id=other, wp_index_id=wi.id, file_path="x.xlsx",
                        source_type=WpSourceType.template, file_version=1, is_deleted=False))
    await db.flush()
    _, items = await resolve_account_workpapers(db, PROJECT, "1002")
    assert all(i.wp_id is None for i in items)
