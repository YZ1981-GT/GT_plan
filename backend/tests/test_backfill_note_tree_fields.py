"""Task 10 回填工具：与生成链同口径、只补空不覆盖、按项目自己的模板类型、不制造重复、可重复执行。"""

from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.models.base import Base
from app.models.core import Project, User
from app.models.report_models import DisclosureNote
from app.services.note_section_catalog import DATA_DIR

_SPEC = importlib.util.spec_from_file_location(
    "backfill_note_tree_fields", Path(__file__).resolve().parents[1] / "scripts/migrate/backfill_note_tree_fields.py")
tool = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tool)


def _sid(tt: str, code: str) -> str:
    secs = json.loads((DATA_DIR / f"note_template_{tt}.json").read_text(encoding="utf-8-sig"))["sections"]
    return next(s["section_id"] for s in secs if s["section_number"] == code)


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(
            c, tables=[User.__table__, Project.__table__, DisclosureNote.__table__]))
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _seed(factory) -> dict:
    ids = {k: uuid.uuid4() for k in ("soe", "listed")}
    period_sid = _sid("soe", "四、会计期间")
    async with factory() as s:
        s.add_all([Project(id=ids["soe"], name="国企甲", client_name="甲", template_type="soe", report_scope="standalone"),
                   Project(id=ids["listed"], name="上市乙", client_name="乙", template_type="listed",
                           report_scope="standalone")])
        await s.flush()
        for code, sid, order in (("一、1", None, 100), ("四、会计期间", None, 400), ("二、1", "converted", 200),
                                 ("九、自定义章", None, 900), ("十、旧自定义", period_sid, 950)):
            s.add(DisclosureNote(project_id=ids["soe"], year=2025, note_section=code, section_title=code,
                                 section_id=sid, sort_order=order))
        s.add(DisclosureNote(project_id=ids["listed"], year=2025, note_section="二、1", section_title="财务报表的编制基础",
                             sort_order=200))
        await s.commit()
    return ids


@pytest.mark.asyncio
async def test_plan_fills_only_blank_template_rows_without_duplicates(factory):
    ids = await _seed(factory)
    async with factory() as db:
        plan = await tool.plan_backfill(db, ids["soe"])
    assert (plan["rows"], plan["already"], plan["no_template"], plan["conflict"]) == (5, 2, 1, 1)
    assert [(r["note_section"], r["section_id"]) for r in plan["fill"]] == [("一、1", _sid("soe", "一、1"))]


@pytest.mark.asyncio
async def test_listed_project_uses_listed_template_ids(factory):
    """旧脚本把两套模板合成一个按编号的索引且国企优先 ⇒ 两套模板同编号而 ID 不同的 14 个章节（如「二、1」
    「八、1」——上市版八、1 是政府补助、国企版是货币资金），上市项目会拿到国企的 ID。"""
    ids = await _seed(factory)
    assert _sid("listed", "二、1") != _sid("soe", "二、1")
    async with factory() as db:
        plan = await tool.plan_backfill(db, ids["listed"])
    assert [r["section_id"] for r in plan["fill"]] == [_sid("listed", "二、1")]


@pytest.mark.asyncio
async def test_apply_is_idempotent_and_never_overwrites(factory):
    ids = await _seed(factory)
    async with factory() as db:
        first = await tool.plan_backfill(db, ids["soe"])
        assert await tool.apply_backfill(db, first) == 1
        await db.commit()
    async with factory() as db:
        # 过期计划（期间已被生成链 / 上一次回填写过）再执行也不覆盖：UPDATE 带 section_id IS NULL
        assert await tool.apply_backfill(db, first) == 0
        again = await tool.plan_backfill(db, ids["soe"])
        assert again["fill"] == [] and await tool.apply_backfill(db, again) == 0
        rows = dict((await db.execute(sa.select(DisclosureNote.note_section, DisclosureNote.section_id)
                                      .where(DisclosureNote.project_id == ids["soe"]))).all())
    assert rows["二、1"] == "converted" and rows["九、自定义章"] is None and rows["四、会计期间"] is None
    assert rows["一、1"] == _sid("soe", "一、1")
