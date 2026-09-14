"""DraftRefreshService.preview_overwrites 团队人工编辑覆盖清单测试.

Task 5.2（formula-management-library）：验证 preview_overwrites 从 draft_marker
（state='human_edited'）返回将被一键刷新覆盖的人工编辑单元清单，并支持按 scope
前缀过滤（Req 4.3）。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.workpaper_models import DraftMarker
from app.services.draft_refresh_service import (
    DraftRefreshService,
    OverwriteItem,
    _parse_unit_scope,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

PROJECT_ID = uuid.uuid4()
OTHER_PROJECT_ID = uuid.uuid4()
YEAR = 2025

_TEST_TABLES = [DraftMarker.__table__]


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: MetaData().create_all(sync_conn, tables=_TEST_TABLES)
        )
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: MetaData().drop_all(sync_conn, tables=_TEST_TABLES)
        )


def _marker(unit_scope: str, state: str = "human_edited", **kw) -> DraftMarker:
    base = dict(
        project_id=PROJECT_ID, year=YEAR, unit_scope=unit_scope, state=state,
    )
    base.update(kw)
    return DraftMarker(**base)


# ── _parse_unit_scope 单元测试 ──────────────────────────────────────


def test_parse_unit_scope_audit_sheet():
    domain, wp, cell = _parse_unit_scope("audit_sheet:WP123:B12")
    assert domain == "audit_sheet"
    assert wp == "WP123"
    assert cell == "B12"


def test_parse_unit_scope_report_row():
    domain, wp, cell = _parse_unit_scope("report:BS-1")
    assert domain == "report"
    assert wp is None
    assert cell == "BS-1"


def test_parse_unit_scope_bare_domain():
    domain, wp, cell = _parse_unit_scope("note")
    assert domain == "note"
    assert wp is None
    assert cell is None


def test_parse_unit_scope_cell_with_colon_preserved():
    # 单元段本身含冒号（如某些复合坐标）应完整保留
    domain, wp, cell = _parse_unit_scope("audit_sheet:WP1:sheet:A1")
    assert domain == "audit_sheet"
    assert wp == "WP1"
    assert cell == "sheet:A1"


# ── preview_overwrites 行为测试 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_preview_only_human_edited(db_session: AsyncSession):
    """只返回 state='human_edited'，draft 单元不入清单。"""
    db_session.add_all([
        _marker("audit_sheet:WP1:A1", state="human_edited"),
        _marker("audit_sheet:WP1:A2", state="draft"),
        _marker("report:BS-1", state="human_edited"),
    ])
    await db_session.commit()

    items = await DraftRefreshService().preview_overwrites(
        db_session, project_id=PROJECT_ID, year=YEAR
    )

    scopes = {i.unit_scope for i in items}
    assert scopes == {"audit_sheet:WP1:A1", "report:BS-1"}
    assert all(isinstance(i, OverwriteItem) for i in items)


@pytest.mark.asyncio
async def test_preview_empty_when_no_human_edits(db_session: AsyncSession):
    """无人工编辑单元 → 空清单。"""
    db_session.add(_marker("audit_sheet:WP1:A1", state="draft"))
    await db_session.commit()

    items = await DraftRefreshService().preview_overwrites(
        db_session, project_id=PROJECT_ID, year=YEAR
    )
    assert items == []


@pytest.mark.asyncio
async def test_preview_scoped_by_project_and_year(db_session: AsyncSession):
    """跨项目/跨年度的人工编辑不串入本项目清单。"""
    db_session.add_all([
        _marker("report:BS-1"),
        _marker("report:BS-2", project_id=OTHER_PROJECT_ID),
        _marker("report:BS-3", year=YEAR - 1),
    ])
    await db_session.commit()

    items = await DraftRefreshService().preview_overwrites(
        db_session, project_id=PROJECT_ID, year=YEAR
    )
    assert {i.unit_scope for i in items} == {"report:BS-1"}


@pytest.mark.asyncio
async def test_preview_scope_prefix_filter_string(db_session: AsyncSession):
    """scope 为字符串 → 前缀匹配 unit_scope。"""
    db_session.add_all([
        _marker("audit_sheet:WP1:A1"),
        _marker("report:BS-1"),
        _marker("note:section-3"),
    ])
    await db_session.commit()

    items = await DraftRefreshService().preview_overwrites(
        db_session, project_id=PROJECT_ID, year=YEAR, scope="report"
    )
    assert {i.unit_scope for i in items} == {"report:BS-1"}


@pytest.mark.asyncio
async def test_preview_scope_prefix_filter_workpaper_specific(db_session: AsyncSession):
    """scope 可细到具体底稿前缀。"""
    db_session.add_all([
        _marker("audit_sheet:WP1:A1"),
        _marker("audit_sheet:WP2:A1"),
    ])
    await db_session.commit()

    items = await DraftRefreshService().preview_overwrites(
        db_session, project_id=PROJECT_ID, year=YEAR, scope="audit_sheet:WP1"
    )
    assert {i.unit_scope for i in items} == {"audit_sheet:WP1:A1"}


@pytest.mark.asyncio
async def test_preview_scope_list_matches_any(db_session: AsyncSession):
    """scope 为列表 → 命中任一前缀即返回（多勾选范围）。"""
    db_session.add_all([
        _marker("audit_sheet:WP1:A1"),
        _marker("report:BS-1"),
        _marker("note:section-3"),
    ])
    await db_session.commit()

    items = await DraftRefreshService().preview_overwrites(
        db_session, project_id=PROJECT_ID, year=YEAR, scope=["report", "note"]
    )
    assert {i.unit_scope for i in items} == {"report:BS-1", "note:section-3"}


@pytest.mark.asyncio
async def test_preview_empty_scope_list_returns_all(db_session: AsyncSession):
    """scope 为全空列表 → 视为不过滤，返回全部人工编辑。"""
    db_session.add_all([_marker("report:BS-1"), _marker("note:section-3")])
    await db_session.commit()

    items = await DraftRefreshService().preview_overwrites(
        db_session, project_id=PROJECT_ID, year=YEAR, scope=[""]
    )
    assert {i.unit_scope for i in items} == {"report:BS-1", "note:section-3"}


@pytest.mark.asyncio
async def test_preview_items_sorted_and_parsed(db_session: AsyncSession):
    """清单按 unit_scope 升序，且解析出 domain/workpaper/cell。"""
    db_session.add_all([
        _marker("report:BS-2"),
        _marker("audit_sheet:WP1:A1"),
        _marker("report:BS-1"),
    ])
    await db_session.commit()

    items = await DraftRefreshService().preview_overwrites(
        db_session, project_id=PROJECT_ID, year=YEAR
    )

    assert [i.unit_scope for i in items] == [
        "audit_sheet:WP1:A1", "report:BS-1", "report:BS-2",
    ]
    first = items[0]
    assert first.domain == "audit_sheet"
    assert first.workpaper == "WP1"
    assert first.cell == "A1"
    assert first.editor_id is None
    assert first.marker_id is not None


@pytest.mark.asyncio
async def test_preview_item_to_dict_shape(db_session: AsyncSession):
    """OverwriteItem.to_dict 输出稳定结构，供 API 序列化。"""
    db_session.add(_marker("audit_sheet:WP1:A1"))
    await db_session.commit()

    items = await DraftRefreshService().preview_overwrites(
        db_session, project_id=PROJECT_ID, year=YEAR
    )
    payload = items[0].to_dict()
    assert set(payload.keys()) == {
        "unit_scope", "domain", "workpaper", "cell", "editor_id", "marker_id",
    }
    assert payload["editor_id"] is None
    assert isinstance(payload["marker_id"], str)
