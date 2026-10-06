"""合并附注节点级自动刷新编排测试。

覆盖 handler 的事件边界、节点去重、独立会话、逐节点事务、章节 SAVEPOINT、
Listed/SOE 传递，以及公式服务的 legacy copy-on-write / manual_cells 失败可观察性。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.core.database as database
import app.services.consol_note_formula_refresh_handler as refresh_handler
import app.services.consol_note_formula_service as formula_service
import app.services.consol_tree_service as tree_service
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.base import Base
from app.models.consol_note_data_models import ConsolNoteData
from app.services.event_bus import EventBus

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_PROJECT_ID = uuid4()
_YEAR = 2025
_SECTIONS = ("五-1-1", "五-2-1")


class _RecordingSession:
    """只实现 handler 编排所需的会话接口，记录节点级事务边界。"""

    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


class _SessionContext:
    def __init__(self, session: _RecordingSession) -> None:
        self.session = session

    async def __aenter__(self) -> _RecordingSession:
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def _node(key: str, *children: object, label: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        node_key=key,
        display_name=label or key,
        company_name=label or key,
        children=list(children),
    )


def _event(
    event_type: EventType = EventType.TRIAL_BALANCE_UPDATED,
    *,
    extra: dict | None = None,
    year: int | None = _YEAR,
) -> EventPayload:
    return EventPayload(
        event_type=event_type,
        project_id=_PROJECT_ID,
        year=year,
        extra=extra or {},
    )


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch):
    """安装可观测的 handler 运行时桩；数据库会话仍由真实 async context 管理。"""
    session = _RecordingSession()
    contexts: list[_SessionContext] = []

    def session_factory() -> _SessionContext:
        context = _SessionContext(session)
        contexts.append(context)
        return context

    monkeypatch.setattr(database, "async_session", session_factory)

    enabled = AsyncMock(return_value=True)
    resolve_template = AsyncMock(return_value="soe")
    build_tree = AsyncMock()
    fill_sections = AsyncMock()

    monkeypatch.setattr(
        "app.services.consol_note_gray_service.is_consol_note_v2_enabled", enabled,
    )
    monkeypatch.setattr(
        "app.services.consol_note_formula_service.resolve_note_template_type",
        resolve_template,
    )
    monkeypatch.setattr(
        "app.services.consol_note_formula_service.consol_note_tables",
        lambda template: [{"section_id": section} for section in _SECTIONS],
    )
    monkeypatch.setattr(tree_service, "build_tree", build_tree)
    monkeypatch.setattr(
        "app.services.consol_note_formula_service.fill_note_sections", fill_sections,
    )

    return SimpleNamespace(
        session=session,
        contexts=contexts,
        enabled=enabled,
        resolve_template=resolve_template,
        build_tree=build_tree,
        fill_sections=fill_sections,
    )


def _persisted_result(section_ids: list[str] | tuple[str, ...], *, prefix: str = "r") -> dict:
    return {
        "results": [
            {
                "section_id": section_id,
                "record_id": f"{prefix}-{index}",
                "status": "persisted",
                "kept_manual_count": 1 if index == 0 else 0,
            }
            for index, section_id in enumerate(section_ids)
        ],
        "failures": [],
    }


@pytest.mark.asyncio
async def test_refreshes_unique_nodes_once_in_a_new_session(runtime):
    """树内重复 node_key 只刷新一次，且每个成功节点独立提交。"""
    root = _node("G:consol", label="集团合并")
    child = _node("A:subsidiary", label="子公司 A")
    duplicate = _node("A:subsidiary", label="重复节点")
    root.children = [child, duplicate]
    runtime.build_tree.return_value = root
    runtime.fill_sections.side_effect = lambda *args, **kwargs: _persisted_result(
        args[3], prefix=kwargs["node_key"].split(":")[0],
    )

    result = await refresh_handler.handle_consol_note_formula_refresh(_event())

    assert result["status"] == "persisted"
    assert [call.kwargs["node_key"] for call in runtime.fill_sections.await_args_list] == [
        "G:consol", "A:subsidiary",
    ]
    assert all(call.args[0] is runtime.session for call in runtime.fill_sections.await_args_list)
    assert runtime.session.commit_count == 2
    assert runtime.session.rollback_count == 0
    assert len(result["nodes"]) == 2
    assert len(result["persisted"]) == 4
    assert {item["record_id"] for item in result["persisted"]} == {
        "G-0", "G-1", "A-0", "A-1",
    }


@pytest.mark.asyncio
async def test_node_failure_rolls_back_only_that_node_and_next_node_continues(runtime):
    """前节点提交后，当前节点失败不能撤销前节点，后续节点仍继续。"""
    root = _node("G:consol")
    failed = _node("A:consol")
    following = _node("B:subsidiary")
    root.children = [failed, following]
    runtime.build_tree.return_value = root

    async def fill(*args, **kwargs):
        if kwargs["node_key"] == "A:consol":
            raise RuntimeError("A 节点数据库写入失败")
        return _persisted_result(args[3], prefix=kwargs["node_key"].split(":")[0])

    runtime.fill_sections.side_effect = fill
    result = await refresh_handler.handle_consol_note_formula_refresh(_event())

    assert result["status"] == "partial"
    assert [call.kwargs["node_key"] for call in runtime.fill_sections.await_args_list] == [
        "G:consol", "A:consol", "B:subsidiary",
    ]
    assert runtime.session.commit_count == 2
    assert runtime.session.rollback_count == 1
    assert len(runtime.contexts) == 1
    assert {item["node_key"] for item in result["persisted"]} == {"G:consol", "B:subsidiary"}
    failed_items = [item for item in result["failed"] if item["node_key"] == "A:consol"]
    assert failed_items and all(item["retry"] is True for item in failed_items)
    assert result["nodes"][1]["status"] == "failed"
    assert result["nodes"][1]["failed"] == len(_SECTIONS)


@pytest.mark.asyncio
async def test_section_failure_is_reported_without_blocking_other_sections(runtime):
    """章节结果可部分成功；失败章节不能伪装成全量成功。"""
    runtime.build_tree.return_value = _node("G:consol")
    runtime.fill_sections.return_value = {
        "results": [
            {"section_id": _SECTIONS[0], "record_id": "r-1", "kept_manual_count": 0},
            {"section_id": _SECTIONS[1], "record_id": "r-3", "kept_manual_count": 2},
        ],
        "failures": [{"section_id": "五-1-2", "error": "manual_cells 损坏"}],
    }

    result = await refresh_handler.handle_consol_note_formula_refresh(_event())

    assert result["status"] == "partial"
    assert runtime.session.commit_count == 1
    assert runtime.session.rollback_count == 0
    assert result["persisted"][1]["manual_preserved_count"] == 2
    assert result["failed"] == [{
        "node_key": "G:consol",
        "section_id": "五-1-2",
        "template_type": "soe",
        "status": "failed",
        "error": "manual_cells 损坏",
        "retry": True,
    }]


@pytest.mark.asyncio
@pytest.mark.parametrize("template_type", ["soe", "listed"])
async def test_template_type_is_resolved_once_and_passed_to_each_node(runtime, template_type):
    """Listed/SOE 分流由项目解析结果决定，并传到共享写入内核。"""
    runtime.resolve_template.return_value = template_type
    runtime.build_tree.return_value = _node("G:consol")
    runtime.fill_sections.return_value = _persisted_result([_SECTIONS[0]])

    result = await refresh_handler.handle_consol_note_formula_refresh(_event())

    assert result["template_type"] == template_type
    assert runtime.fill_sections.await_args.kwargs["template_type"] == template_type
    assert runtime.resolve_template.await_count == 1


@pytest.mark.asyncio
async def test_workpaper_saved_requires_explicit_note_declaration(runtime):
    """普通底稿保存不能无条件重写合并附注。"""
    result = await refresh_handler.handle_consol_note_formula_refresh(
        _event(EventType.WORKPAPER_SAVED),
    )

    assert result["status"] == "skipped"
    assert "未声明影响合并附注" in result["skipped"][0]["reason"]
    runtime.enabled.assert_not_awaited()
    runtime.fill_sections.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_workpaper_saved_declaration_enters_refresh(runtime):
    runtime.build_tree.return_value = _node("G:consol")
    runtime.fill_sections.return_value = _persisted_result([_SECTIONS[0]])

    result = await refresh_handler.handle_consol_note_formula_refresh(_event(
        EventType.WORKPAPER_SAVED,
        extra={"consol_note_affected": True, "section_ids": [_SECTIONS[0]]},
    ))

    assert result["status"] == "persisted"
    assert runtime.fill_sections.await_args.args[3] == [_SECTIONS[0]]


@pytest.mark.asyncio
async def test_disabled_no_tree_and_no_section_are_observable_skips(runtime):
    runtime.enabled.return_value = False
    disabled = await refresh_handler.handle_consol_note_formula_refresh(_event())
    assert disabled["status"] == "skipped"
    assert "未启用" in disabled["skipped"][0]["reason"]

    runtime.enabled.return_value = True
    runtime.build_tree.return_value = None
    no_tree = await refresh_handler.handle_consol_note_formula_refresh(_event())
    assert no_tree["status"] == "skipped"
    assert "没有有效合并树" in no_tree["skipped"][0]["reason"]

    runtime.build_tree.reset_mock()
    runtime.fill_sections.reset_mock()
    runtime.build_tree.return_value = _node("G:consol")
    no_section = await refresh_handler.handle_consol_note_formula_refresh(_event(
        extra={"section_ids": ["不存在章节"]},
    ))
    assert no_section["status"] == "skipped"
    assert "章节不存在" in no_section["skipped"][0]["reason"]
    runtime.build_tree.assert_not_awaited()
    runtime.fill_sections.assert_not_awaited()


@pytest_asyncio.fixture
async def note_db():
    """给真实 handler/公式服务测试使用的独立 SQLite 持久化库。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection, tables=[ConsolNoteData.__table__],
            )
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Base.metadata.drop_all(
                    sync_connection, tables=[ConsolNoteData.__table__],
                )
            )
        await engine.dispose()


async def _note_rows(factory) -> list[ConsolNoteData]:
    async with factory() as session:
        return list((await session.execute(sa.select(ConsolNoteData))).scalars().all())


@pytest.mark.asyncio
async def test_real_session_commit_keeps_successful_nodes_after_a_later_failure(
    note_db, monkeypatch: pytest.MonkeyPatch,
):
    """真实 AsyncSession：前后节点独立提交，失败节点 flush 的行随 rollback 消失。"""
    monkeypatch.setattr(database, "async_session", note_db)
    monkeypatch.setattr(
        "app.services.consol_note_gray_service.is_consol_note_v2_enabled",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "app.services.consol_note_formula_service.resolve_note_template_type",
        AsyncMock(return_value="soe"),
    )
    monkeypatch.setattr(
        "app.services.consol_note_formula_service.consol_note_tables",
        lambda _template: [{"section_id": section} for section in _SECTIONS],
    )
    root = _node("G:consol")
    failed = _node("A:consol")
    following = _node("B:subsidiary")
    root.children = [failed, following]
    monkeypatch.setattr(tree_service, "build_tree", AsyncMock(return_value=root))

    async def write_and_fail_on_a(db, project_id, year, section_ids, **kwargs):
        node_key = kwargs["node_key"]
        for section_id in section_ids:
            db.add(ConsolNoteData(
                project_id=project_id,
                year=year,
                section_id=section_id,
                node_key=node_key,
                data={"node": node_key},
            ))
        await db.flush()
        if node_key == "A:consol":
            raise RuntimeError("A 节点 flush 后失败")
        return _persisted_result(section_ids, prefix=node_key.split(":")[0])

    monkeypatch.setattr(
        "app.services.consol_note_formula_service.fill_note_sections",
        write_and_fail_on_a,
    )

    result = await refresh_handler.handle_consol_note_formula_refresh(_event())

    assert result["status"] == "partial"
    assert {row.node_key for row in await _note_rows(note_db)} == {"G:consol", "B:subsidiary"}
    assert [item["node_key"] for item in result["failed"]] == ["A:consol"] * len(_SECTIONS)
    assert [item["section_id"] for item in result["failed"]] == list(_SECTIONS)
    assert all(item["retry"] is True for item in result["failed"])


@pytest.mark.asyncio
async def test_fill_note_sections_savepoint_rolls_back_bad_section_and_keeps_neighbors(
    note_db, monkeypatch: pytest.MonkeyPatch,
):
    """真实 SAVEPOINT：坏章节已 flush 的行回滚，前后章节仍可提交。"""
    async with note_db() as session:
        monkeypatch.setattr(
            formula_service, "resolve_note_template_type", AsyncMock(return_value="soe"),
        )

        async def fill_one(db, project_id, year, section_id, **kwargs):
            db.add(ConsolNoteData(
                project_id=project_id,
                year=year,
                section_id=section_id,
                node_key=kwargs["node_key"],
                data={"section": section_id},
            ))
            await db.flush()
            if section_id == "坏章节":
                raise RuntimeError("章节写入失败")
            return {"section_id": section_id, "record_id": section_id}

        monkeypatch.setattr(formula_service, "fill_by_formula", fill_one)
        result = await formula_service.fill_note_sections(
            session,
            _PROJECT_ID,
            _YEAR,
            ["前章节", "坏章节", "后章节"],
            node_key="G:consol",
            template_type="soe",
        )
        await session.commit()

    assert result["status"] == "failed"
    assert [item["section_id"] for item in result["results"]] == ["前章节", "后章节"]
    assert result["failures"] == [{
        "section_id": "坏章节",
        "status": "failed",
        "error": "章节写入失败",
    }]
    rows = await _note_rows(note_db)
    assert {row.section_id for row in rows} == {"前章节", "后章节"}


@pytest.mark.asyncio
async def test_root_legacy_copy_on_write_and_corrupt_manual_cells_are_observable(
    note_db, monkeypatch: pytest.MonkeyPatch,
):
    """根节点可读 legacy，但损坏的 manual_cells 失败时不能留下复制行。"""
    legacy_data = {
        "headers": ["项目", "期末"],
        "rows": [["货币资金", "旧值"]],
        "manual_cells": {"row": 0, "col": 1},
    }
    async with note_db() as session:
        session.add(ConsolNoteData(
            project_id=_PROJECT_ID,
            year=_YEAR,
            section_id=_SECTIONS[0],
            node_key=None,
            data=legacy_data,
        ))
        await session.commit()
        monkeypatch.setattr(
            formula_service, "resolve_note_template_type", AsyncMock(return_value="soe"),
        )
        monkeypatch.setattr(
            formula_service,
            "note_breakdown",
            AsyncMock(return_value={
                "template_type": "soe",
                "year": _YEAR,
                "section_id": _SECTIONS[0],
                "node_key": "G:consol",
                "_is_root_consol": True,
                "cells": [],
            }),
        )
        monkeypatch.setattr(
            formula_service,
            "find_table",
            lambda _template, _section: {"headers": ["项目", "期末"], "rows": [["货币资金", ""]]},
        )
        result = await formula_service.fill_note_sections(
            session,
            _PROJECT_ID,
            _YEAR,
            [_SECTIONS[0]],
            node_key="G:consol",
            template_type="soe",
        )
        await session.commit()

    assert result["status"] == "failed"
    assert result["failures"][0]["section_id"] == _SECTIONS[0]
    assert "manual_cells 必须是数组" in result["failures"][0]["error"]
    rows = await _note_rows(note_db)
    assert [(row.node_key, row.data) for row in rows] == [(None, legacy_data)]


@pytest.mark.asyncio
async def test_register_is_idempotent_and_does_not_subscribe_adjustment_approval():
    bus = EventBus(debounce_ms=0)

    refresh_handler.register_consol_note_formula_refresh_handler(bus)
    refresh_handler.register_consol_note_formula_refresh_handler(bus)

    assert bus._handlers[EventType.TRIAL_BALANCE_UPDATED] == [
        refresh_handler.handle_consol_note_formula_refresh,
    ]
    assert bus._handlers[EventType.WORKPAPER_SAVED] == [
        refresh_handler.handle_consol_note_formula_refresh,
    ]
    assert refresh_handler.handle_consol_note_formula_refresh not in (
        bus._handlers.get(EventType.ADJUSTMENT_APPROVED, [])
    )


@pytest.mark.asyncio
async def test_invalid_event_is_failed_without_opening_a_database_session(runtime):
    invalid = EventPayload(
        event_type=EventType.TRIAL_BALANCE_UPDATED,
        project_id=_PROJECT_ID,
        year=0,
    )

    result = await refresh_handler.handle_consol_note_formula_refresh(invalid)

    assert result["status"] == "failed"
    assert result["failed"][0]["retry"] is False
    assert runtime.contexts == []
