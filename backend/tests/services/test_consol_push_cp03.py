"""CP03 合并推送运行状态、附注叶结果和事务边界验证。"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import tests.conftest  # noqa: F401  注册全部模型及 SQLite 方言补丁
from app.models.base import Base, ProjectStatus
from app.models.consol_note_data_models import ConsolNoteData
from app.models.core import Project

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

YEAR = 2025
PROJECT_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[Project.__table__, ConsolNoteData.__table__],
            )
        )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield session_factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db(factory) -> AsyncSession:
    async with factory() as session:
        yield session


def _project() -> Project:
    return Project(
        id=PROJECT_ID,
        name="CP03 测试集团",
        client_name="CP03 测试集团",
        company_code="CP03",
        report_scope="consolidated",
        audit_year=YEAR,
        status=ProjectStatus.execution,
    )


def _tree(*node_keys: str):
    nodes = [SimpleNamespace(node_key=key, children=[]) for key in node_keys]
    root = nodes[0]
    root.children = nodes[1:]
    return root


async def _note_rows(factory) -> list[ConsolNoteData]:
    async with factory() as session:
        return list((await session.execute(sa.select(ConsolNoteData))).scalars().all())


@pytest.mark.asyncio
async def test_refresh_notes_commits_stale_before_template_failure(db, factory, monkeypatch):
    """模板解析失败只能阻止刷新，不能回滚已经提交的 stale 标记。"""
    db.add(_project())
    db.add_all([
        ConsolNoteData(
            project_id=PROJECT_ID,
            year=YEAR,
            section_id="section-a",
            data={"rows": []},
            is_stale=False,
        ),
        ConsolNoteData(
            project_id=PROJECT_ID,
            year=YEAR,
            section_id="section-b",
            data={"rows": []},
            is_stale=False,
        ),
    ])
    await db.commit()

    async def fail_template(*_args, **_kwargs):
        raise RuntimeError("模板目录暂不可用")

    monkeypatch.setattr(
        "app.services.consol_note_formula_service.resolve_note_template_type",
        fail_template,
    )

    from app.services.consol_push_service import _refresh_notes

    result = await _refresh_notes(db, PROJECT_ID, YEAR, tree=_tree("CP03:consol"), context=object())

    assert result["note_status"] == "failed"
    assert result["stale_marked"] == 2
    assert result["missing_reasons"][0]["code"] == "missing_template"
    rows = await _note_rows(factory)
    assert {row.section_id for row in rows} == {"section-a", "section-b"}
    assert all(row.is_stale is True for row in rows)


@pytest.mark.asyncio
async def test_refresh_notes_classifies_leaves_and_keeps_previous_node_after_later_rollback(
    db, factory, monkeypatch,
):
    """真实 SQLite：叶结果分类准确，成功节点提交后不受后续节点异常回滚影响。"""
    db.add(_project())
    sections = ["refreshed", "locked", "manual", "blank", "failed"]
    db.add_all([
        ConsolNoteData(
            project_id=PROJECT_ID,
            year=YEAR,
            section_id=section,
            data={"rows": []},
            is_stale=False,
        )
        for section in sections
    ])
    await db.commit()

    async def fill_sections(session, project_id, year, section_ids, **kwargs):
        node_key = kwargs["node_key"]
        for section_id in section_ids:
            session.add(ConsolNoteData(
                project_id=project_id,
                year=year,
                section_id=section_id,
                node_key=node_key,
                data={"node": node_key},
            ))
        await session.flush()
        if node_key == "A:consol":
            raise RuntimeError("A 节点写入后失败")
        return {
            "results": [
                {
                    "section_id": "refreshed",
                    "status": "persisted",
                    "filled": [{"row_index": 1}],
                    "kept_manual": [],
                    "blank": [],
                },
                {
                    "section_id": "locked",
                    "status": "skipped_locked",
                    "reason": "整节被锁定",
                    "filled": [],
                    "kept_manual": [],
                    "blank": [],
                },
                {
                    "section_id": "manual",
                    "status": "persisted",
                    "filled": [],
                    "kept_manual": [{"row_index": 2}],
                    "blank": [],
                },
                {
                    "section_id": "blank",
                    "status": "persisted",
                    "filled": [],
                    "kept_manual": [],
                    "blank": [{"row_index": 3, "reason": "取不到数"}],
                },
            ],
            "failures": [{
                "section_id": "failed",
                "status": "failed",
                "error": "章节写入失败",
            }],
        }

    monkeypatch.setattr(
        "app.services.consol_note_formula_service.resolve_note_template_type",
        AsyncMock(return_value="soe"),
    )
    monkeypatch.setattr(
        "app.services.consol_note_formula_service.consol_note_tables",
        lambda _template: [{"section_id": section} for section in sections],
    )
    monkeypatch.setattr(
        "app.services.consol_report_view_service.load_view_context",
        AsyncMock(return_value=SimpleNamespace()),
    )
    monkeypatch.setattr(
        "app.services.consol_note_formula_service.fill_note_sections",
        fill_sections,
    )

    from app.services.consol_push_service import _refresh_notes

    result = await _refresh_notes(
        db,
        PROJECT_ID,
        YEAR,
        tree=_tree("G:consol", "A:consol"),
        context=object(),
    )

    by_section = {
        item["section_id"]: item["classification"]
        for item in result["leaf_results"]
        if item["node_key"] == "G:consol"
    }
    assert by_section == {
        "refreshed": "refreshed",
        "locked": "skipped_locked",
        "manual": "skipped_manual",
        "blank": "skipped_missing",
        "failed": "failed",
    }
    assert result["expected_leaf_count"] == 10
    assert result["processed_leaf_count"] == 10
    assert result["refreshed_count"] == 1
    assert result["skipped_count"] == 3
    assert result["protected_count"] == 2
    assert result["missing_count"] == 1
    assert result["failed_count"] == 6
    assert result["note_status"] == "partial"

    rows = await _note_rows(factory)
    node_rows = {(row.node_key, row.section_id) for row in rows if row.node_key}
    assert {("G:consol", section) for section in sections} <= node_rows
    assert not any(row.node_key == "A:consol" for row in rows)
    assert all(row.is_stale is True for row in rows if row.node_key is None)


@pytest.mark.asyncio
async def test_push_one_propagates_partial_note_status_to_step(db, monkeypatch):
    """前面三步成功、附注 partial 时，notes step 和返回值都保留 partial。"""
    project = _project()
    db.add(project)
    await db.commit()

    note_stats = {
        "note_status": "partial",
        "stale_marked": 2,
        "distinct_section_count": 2,
        "node_count": 1,
        "expected_leaf_count": 2,
        "processed_leaf_count": 2,
        "refreshed_count": 1,
        "failed_count": 1,
        "skipped_count": 0,
        "protected_count": 0,
        "missing_count": 0,
        "leaf_results": [],
        "failure_details": [{"error": "章节写入失败"}],
        "skip_reasons": [],
        "missing_reasons": [],
        "warnings": ["章节写入失败"],
    }
    monkeypatch.setattr(
        "app.services.consol_worksheet_engine.recalc_full",
        AsyncMock(return_value={"node_count": 1, "account_count": 1}),
    )
    monkeypatch.setattr(
        "app.services.consol_trial_service.recalculate_trial",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.consol_report_service.ConsolReportService.generate_consol_reports",
        AsyncMock(return_value={"balance_sheet": []}),
    )
    monkeypatch.setattr(
        "app.services.consol_push_service._refresh_notes",
        AsyncMock(return_value=note_stats),
    )

    from app.services.consol_push_service import _push_one

    steps: list[dict] = []
    warnings: list[str] = []
    result = await _push_one(db, PROJECT_ID, YEAR, steps, warnings)

    assert result is False
    assert [step["status"] for step in steps] == [
        "succeeded", "succeeded", "succeeded", "partial",
    ]
    notes_step = steps[-1]
    assert notes_step["metadata"] is note_stats
    assert "附注状态=partial" in notes_step["detail"]
    assert any("附注：章节写入失败" in warning for warning in warnings)
