"""合并附注 stale 原因 / 时间的纯状态契约测试。"""
from __future__ import annotations

import hashlib
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

import tests.conftest  # noqa: F401  确保 SQLite 方言补丁与全量模型注册已生效
from app.models.base import Base
from app.models.consol_note_data_models import ConsolNoteData
from app.models.consol_note_mapping_models import (
    ConsolNoteDetailTemplate,
    ConsolNoteDetailTemplateVersion,
    ConsolNoteMappingBinding,
    ConsolNoteMappingRule,
    ConsolNoteTemplateBinding,
)
from app.services.consol_note_stale_state import (
    ConsolNoteStaleSource,
    clear_stale,
    clear_values,
    inherit_values,
    label_of,
    mark_stale,
    stale_values,
)


def test_mark_stale_records_reason_and_time_and_clear_removes_both():
    now = datetime(2026, 11, 12, 8, 30, tzinfo=timezone.utc)
    record = SimpleNamespace(is_stale=False, stale_reason=None, stale_at=None)

    mark_stale(record, ConsolNoteStaleSource.CONSOL_PUSH, now=now)
    assert record.is_stale is True
    assert record.stale_reason == "consol_push"
    assert record.stale_at == now

    clear_stale(record)
    assert vars(record) == {"is_stale": False, "stale_reason": None, "stale_at": None}


def test_stale_values_are_batch_update_values():
    now = datetime(2026, 11, 12, 8, 31, tzinfo=timezone.utc)
    assert stale_values(ConsolNoteStaleSource.FORMULA_SETTINGS, now) == {
        "is_stale": True,
        "stale_reason": "formula_settings",
        "stale_at": now,
    }
    assert clear_values() == {"is_stale": False, "stale_reason": None, "stale_at": None}


def test_inherit_values_preserves_stale_metadata_only_when_source_is_stale():
    stale_at = datetime(2026, 11, 12, 8, 32, tzinfo=timezone.utc)
    source = SimpleNamespace(is_stale=True, stale_reason="node_created", stale_at=stale_at)
    assert inherit_values(source) == {
        "is_stale": True,
        "stale_reason": "node_created",
        "stale_at": stale_at,
    }

    fresh = SimpleNamespace(is_stale=False, stale_reason="legacy", stale_at=stale_at)
    assert inherit_values(fresh) == {
        "is_stale": False,
        "stale_reason": None,
        "stale_at": None,
    }


def test_unknown_reason_falls_back_to_history_label():
    assert label_of("not-a-real-reason") == "历史标记"
    assert label_of("legacy") == "历史标记，未记录原因"
    assert label_of(None) == "历史标记"


def test_consol_note_stale_sse_includes_reason(monkeypatch):
    from app.services import consol_note_stale_handler as handler

    class _Bus:
        def __init__(self):
            self.calls = []

        def broadcast_raw(self, event_type, extra):
            self.calls.append((event_type, extra))

    bus = _Bus()
    monkeypatch.setattr("app.services.event_bus.event_bus", bus)
    handler._emit_consol_note_stale(
        __import__("uuid").uuid4(), 2025, "五、1", 2, "formula_settings"
    )
    assert bus.calls[0][0] == "consol.note_stale"
    assert bus.calls[0][1]["reason"] == "formula_settings"


YEAR = 2025
SECTION = "五、1"


@pytest_asyncio.fixture
async def stale_db():
    """真实 SQLAlchemy ORM 会话：写入方测试不靠 Mock 观察 update 参数。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()


def _note(
    project_id: UUID,
    *,
    section_id: str = SECTION,
    year: int = YEAR,
    node_key: str | None = None,
    data: dict | None = None,
    is_stale: bool = False,
    stale_reason: str | None = None,
    stale_at: datetime | None = None,
    last_formula_value: dict | None = None,
) -> ConsolNoteData:
    return ConsolNoteData(
        id=uuid4(),
        project_id=project_id,
        year=year,
        section_id=section_id,
        node_key=node_key,
        data=data or {},
        is_stale=is_stale,
        stale_reason=stale_reason,
        stale_at=stale_at,
        last_formula_value=last_formula_value,
        locked_cells=[],
    )


async def _read_notes(factory, project_id: UUID, *, section_id: str | None = SECTION):
    async with factory() as db:
        statement = sa.select(ConsolNoteData).where(ConsolNoteData.project_id == project_id)
        if section_id is not None:
            statement = statement.where(ConsolNoteData.section_id == section_id)
        return list(
            (await db.execute(statement.order_by(ConsolNoteData.node_key))).scalars().all()
        )


@pytest.mark.asyncio
async def test_push_writer_persists_reason_and_time_only_for_project_year(stale_db):
    """推送批量置位走真实 UPDATE，并不污染其他项目/年度。"""
    from app.services.consol_push_notes import _mark_notes_stale

    project_id = uuid4()
    other_project = uuid4()
    async with stale_db() as db:
        db.add_all([
            _note(project_id, stale_reason="legacy", stale_at=None),
            _note(project_id, year=2024),
            _note(other_project),
        ])
        await db.commit()
        before = datetime.now(timezone.utc)
        count = await _mark_notes_stale(db, project_id, YEAR)
        await db.commit()
        after = datetime.now(timezone.utc)

    assert count == 1
    rows = await _read_notes(stale_db, project_id)
    assert len(rows) == 2
    current = next(row for row in rows if row.year == YEAR)
    assert current.is_stale is True
    assert current.stale_reason == ConsolNoteStaleSource.CONSOL_PUSH.value
    assert current.stale_at is not None
    assert before.replace(tzinfo=None) <= current.stale_at <= after.replace(tzinfo=None)
    old_year = next(row for row in rows if row.year == 2024)
    assert old_year.is_stale is False and old_year.stale_reason is None and old_year.stale_at is None
    other = await _read_notes(stale_db, other_project)
    assert other[0].is_stale is False and other[0].stale_reason is None


@pytest.mark.asyncio
async def test_formula_settings_writer_persists_reason_and_time(stale_db, monkeypatch):
    """公式设置传播的合并附注分支执行真实批量 UPDATE。"""
    from app.services.formula_settings import propagation

    project_id = uuid4()
    async with stale_db() as db:
        db.add_all([
            _note(project_id, section_id=SECTION),
            _note(project_id, section_id="五、2"),
            _note(project_id, year=2024),
        ])
        await db.commit()
        async def _not_frozen(_db, _project_id):
            return False
        monkeypatch.setattr(propagation, "_is_frozen", _not_frozen)
        result = await propagation.mark_in_year(
            db, "consol_note", project_id, YEAR, [f"{SECTION}|cell:1"]
        )
        await db.commit()

    assert result == {"domain": "consol_note", "marked": 1}
    rows = await _read_notes(stale_db, project_id)
    current = next(row for row in rows if row.section_id == SECTION and row.year == YEAR)
    assert current.is_stale is True
    assert current.stale_reason == ConsolNoteStaleSource.FORMULA_SETTINGS.value
    assert current.stale_at is not None
    untouched = [row for row in rows if row.section_id != SECTION or row.year != YEAR]
    assert all(not row.is_stale and row.stale_reason is None and row.stale_at is None for row in untouched)


@pytest.mark.asyncio
async def test_standalone_note_saved_marks_all_bound_nodes(stale_db):
    """子企业单体附注保存会经绑定查询，逐条写入 stale 原因和时间。"""
    from app.services.consol_note_value_change_service import on_note_section_saved

    entity_project_id = uuid4()
    consol_project_id = uuid4()
    async with stale_db() as db:
        db.add(
            ConsolNoteMappingBinding(
                id=uuid4(), project_id=consol_project_id, section_id=SECTION,
                entity_node_key="A:subsidiary", entity_project_id=entity_project_id,
                rule_id=uuid4(), bound_source_hash="a" * 64, status="confirmed",
            )
        )
        db.add_all([
            _note(consol_project_id, node_key=None),
            _note(consol_project_id, node_key="A:subsidiary"),
            _note(consol_project_id, section_id="五、2"),
        ])
        await db.commit()
        result = await on_note_section_saved(
            db,
            entity_project_id=entity_project_id,
            section_id=SECTION,
            year=YEAR,
        )
        await db.commit()

    assert result == {
        "affected_projects": [{
            "consol_project_id": str(consol_project_id),
            "section_id": SECTION,
            "entity_node_key": "A:subsidiary",
            "entity_project_id": str(entity_project_id),
        }]
    }
    rows = await _read_notes(stale_db, consol_project_id, section_id=None)
    affected = [row for row in rows if row.section_id == SECTION]
    assert len(affected) == 2
    assert all(
        row.is_stale
        and row.stale_reason == ConsolNoteStaleSource.STANDALONE_NOTE_SAVED.value
        and row.stale_at is not None
        for row in affected
    )
    untouched = next(row for row in rows if row.section_id == "五、2")
    assert untouched.is_stale is False and untouched.stale_reason is None and untouched.stale_at is None


@pytest.mark.asyncio
async def test_formula_value_change_writer_marks_pulled_row(stale_db, monkeypatch):
    """后台公式刷新对已拉数行只更新快照，公式值变化才置 stale。"""
    from app.services import consol_note_formula_service as formula
    from app.services.consol_calc_basis import MEASURE_CONSOLIDATED

    project_id = uuid4()
    old_snapshot = {
        "cells": [{"row_index": 0, "col_index": 1, "value": "100"}],
        "computed_at": "2026-01-01T00:00:00+00:00",
    }
    async with stale_db() as db:
        db.add(_note(
            project_id,
            data={"rows": [["项目", "80"]], "_last_write_source": "detail_mapping"},
            last_formula_value=old_snapshot,
        ))
        await db.commit()

        async def _breakdown(*_args, **_kwargs):
            return {
                "template_type": "soe", "year": YEAR, "node_key": None,
                "_is_root_consol": False,
                "cells": [{"row_index": 0, "col_index": 1, MEASURE_CONSOLIDATED: "200"}],
            }

        monkeypatch.setattr(formula, "note_breakdown", _breakdown)
        monkeypatch.setattr(
            formula, "find_table", lambda _template, _section: {"headers": ["项目", "本期"]},
        )
        result = await formula.fill_by_formula(
            db, project_id, YEAR, SECTION, template_type="soe", preserve_pulled=True,
        )
        await db.commit()

    assert result["status"] == "kept_pulled"
    assert result["stale_marked"] is True
    row = (await _read_notes(stale_db, project_id))[0]
    assert row.is_stale is True
    assert row.stale_reason == ConsolNoteStaleSource.FORMULA_VALUE_CHANGED.value
    assert row.stale_at is not None
    assert row.last_formula_value["cells"] == [{"row_index": 0, "col_index": 1, "value": "200"}]


@pytest.mark.asyncio
async def test_formula_writer_clears_stale_reason_and_time(stale_db, monkeypatch):
    """普通「按公式填入」实际写入后同时清除 stale 三元组。"""
    from app.services import consol_note_formula_service as formula
    from app.services.consol_calc_basis import MEASURE_CONSOLIDATED

    project_id = uuid4()
    async with stale_db() as db:
        db.add(_note(
            project_id,
            data={
                "headers": ["项目", "本期"],
                "rows": [["项目", "80"]],
                "_last_write_source": "detail_mapping",
            },
            is_stale=True,
            stale_reason=ConsolNoteStaleSource.CONSOL_PUSH.value,
            stale_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        ))
        await db.commit()

        async def _breakdown(*_args, **_kwargs):
            return {
                "template_type": "soe", "year": YEAR, "node_key": None,
                "_is_root_consol": False,
                "cells": [{"row_index": 0, "col_index": 1, MEASURE_CONSOLIDATED: "200"}],
            }

        monkeypatch.setattr(formula, "note_breakdown", _breakdown)
        monkeypatch.setattr(
            formula, "find_table",
            lambda _template, _section: {
                "headers": ["项目", "本期"], "rows": [["项目", ""]],
            },
        )
        result = await formula.fill_by_formula(
            db, project_id, YEAR, SECTION, template_type="soe",
        )
        await db.commit()

    assert result["status"] == "persisted"
    row = (await _read_notes(stale_db, project_id))[0]
    assert row.data["rows"] == [["项目", "200"]]
    assert row.is_stale is False and row.stale_reason is None and row.stale_at is None


@pytest.mark.asyncio
async def test_detail_apply_writer_clears_stale_reason_and_time(stale_db, monkeypatch):
    """明细映射写入方走真实绑定/规则/来源流程，并清除 stale 元数据。"""
    from app.services import consol_note_detail_apply_service as detail
    from app.services import consol_note_detail_source_service as source
    from app.services import consol_note_formula_service as formula

    project_id = uuid4()
    entity_project_id = uuid4()
    template_id, version_id, rule_id = uuid4(), uuid4(), uuid4()
    async with stale_db() as db:
        db.add(ConsolNoteDetailTemplate(
            id=template_id, template_type="soe", section_id=SECTION,
            name="测试明细模板", visibility="project", is_deleted=False,
        ))
        db.add(ConsolNoteDetailTemplateVersion(
            id=version_id, template_id=template_id, version_number=1,
            rows=[{"target_row_id": "target-1", "canonical_name": "项目", "row_type": "data"}],
        ))
        db.add(ConsolNoteTemplateBinding(
            id=uuid4(), project_id=project_id, section_id=SECTION,
            template_version_id=version_id,
        ))
        db.add(ConsolNoteMappingRule(
            id=rule_id, project_id=project_id, section_id=SECTION,
            template_version_id=version_id, source_structure_hash="a" * 64,
            mappings=[{"source_label": "项目", "target_row_id": "target-1", "mapping_action": "map"}],
        ))
        db.add(ConsolNoteMappingBinding(
            id=uuid4(), project_id=project_id, section_id=SECTION,
            entity_node_key="A:subsidiary", entity_project_id=entity_project_id,
            rule_id=rule_id, bound_source_hash="a" * 64, status="confirmed",
        ))
        db.add(_note(
            project_id,
            data={"headers": ["项目", "本期", "上期"], "rows": [["项目", "80", "70"]]},
            is_stale=True, stale_reason=ConsolNoteStaleSource.CONSOL_PUSH.value,
            stale_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        ))
        await db.commit()

        async def _sources(*_args, **_kwargs):
            return {entity_project_id: SimpleNamespace(
                rows=[{"label": "项目", "values": ["200", "180"]}],
                usable=True, reason=None,
            )}

        monkeypatch.setattr(source, "load_source_tables", _sources)
        monkeypatch.setattr(source, "compute_source_structure_hash", lambda *_args: "a" * 64)
        monkeypatch.setattr(formula, "find_table", lambda *_args: {
            "headers": ["项目", "本期", "上期"], "rows": [],
        })
        result = await detail.apply_detail_refresh(
            db, project_id=project_id, section_id=SECTION, year=YEAR,
            template_type="soe",
            scope_leaves=[SimpleNamespace(
                node_key="A:subsidiary", project_id=entity_project_id, company_name="子公司",
            )],
        )
        await db.commit()

    assert result["status"] == "applied"
    assert result["applied_entity_count"] == 1
    row = (await _read_notes(stale_db, project_id))[0]
    assert row.data["rows"][0][1:] == ["200.00", "180.00"]
    assert row.is_stale is False and row.stale_reason is None and row.stale_at is None


@pytest.mark.asyncio
async def test_subtree_aggregate_writer_inherits_then_clears_stale_metadata(stale_db, monkeypatch):
    """子树汇总真实汇总一个下级：复制 legacy 行继承后，写入完成再清除 stale。"""
    from app.services import consol_note_subtree_reaggregate as subtree
    from app.services.consol_group_tree import KIND_AGGREGATE
    from app.services.consol_tree_service import TreeNode

    project_id = uuid4()
    root = TreeNode(
        project_id=project_id, company_code="G", company_name="集团",
        parent_company_code=None, ultimate_company_code="G", consol_level=0,
        node_key="G:consol", role="consol", kind=KIND_AGGREGATE,
    )
    child = TreeNode(
        project_id=uuid4(), company_code="A", company_name="子公司",
        parent_company_code="G", ultimate_company_code="G", consol_level=1,
        node_key="A:subsidiary", role="subsidiary", kind="data",
    )
    root.children = [child]
    async with stale_db() as db:
        legacy = _note(
            project_id,
            data={"rows": [["项目", "1"]]},
            is_stale=True,
            stale_reason=ConsolNoteStaleSource.STANDALONE_NOTE_SAVED.value,
            stale_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
        )
        leaf = _note(
            project_id,
            node_key=child.node_key,
            data={"rows": [["项目", "200"]], "_last_write_source": "detail_mapping"},
        )
        db.add_all([legacy, leaf])
        await db.commit()

        run = subtree._Run(db, project_id, YEAR, root, root, "soe", [SECTION])
        run.skeletons[SECTION] = [("项目", "data")]
        run.records = {(SECTION, None): legacy, (SECTION, child.node_key): leaf}
        monkeypatch.setattr(subtree, "section_topn_limit", lambda *_args: None)
        monkeypatch.setattr(subtree, "find_table", lambda *_args: {"headers": ["项目", "本期"]})
        outcome = await run._aggregate(SECTION, root)
        await db.commit()

    assert outcome.status == subtree._PERSISTED
    rows = await _read_notes(stale_db, project_id)
    target = next(row for row in rows if row.node_key == root.node_key)
    assert target.data["rows"] == [["项目", "200.00"]]
    assert target.data["_last_write_source"] == subtree.WRITE_SOURCE
    assert target.is_stale is False and target.stale_reason is None and target.stale_at is None


@pytest.mark.asyncio
async def test_subtree_writable_record_inherits_stale_metadata_before_refresh(stale_db):
    """子树汇总的节点专属复制函数本身完整继承原因与时间。"""
    from app.services import consol_note_subtree_reaggregate as subtree
    from app.services.consol_group_tree import KIND_AGGREGATE
    from app.services.consol_tree_service import TreeNode

    project_id = uuid4()
    root = TreeNode(
        project_id=project_id, company_code="G", company_name="集团",
        parent_company_code=None, ultimate_company_code="G", consol_level=0,
        node_key="G:consol", role="consol", kind=KIND_AGGREGATE,
    )
    async with stale_db() as db:
        source = _note(
            project_id,
            data={"rows": [["项目", "1"]]},
            is_stale=True,
            stale_reason=ConsolNoteStaleSource.FORMULA_SETTINGS.value,
            stale_at=datetime(2026, 11, 3, tzinfo=timezone.utc),
        )
        db.add(source)
        await db.flush()
        run = subtree._Run(db, project_id, YEAR, root, root, "soe", [SECTION])
        target = await run._writable_record(SECTION, root, source)
        assert target.is_stale is True
        assert target.stale_reason == ConsolNoteStaleSource.FORMULA_SETTINGS.value
        assert target.stale_at == source.stale_at


@pytest.mark.asyncio
async def test_topn_writer_clears_stale_reason_and_time():
    """前 N 名写入方复用真实 write_topn，清除全部 stale 字段。"""
    from app.services.consol_note_topn import TopNColumns, TopNResult, write_topn

    record = ConsolNoteData(
        id=uuid4(), project_id=uuid4(), year=YEAR, section_id=SECTION,
        data={"headers": ["单位", "金额"], "rows": [["旧单位", "100"]]},
        is_stale=True, stale_reason=ConsolNoteStaleSource.CONSOL_PUSH.value,
        stale_at=datetime(2026, 11, 4, tzinfo=timezone.utc), locked_cells=[],
    )
    result = TopNResult(
        rows=[["新单位", "200"], ["合  计", "200"]], names=["新单位"],
        columns=TopNColumns(balance=1, amounts=(1,), ratio=(), text=()),
    )
    summary = write_topn(
        record, headers=["单位", "金额"], result=result, limit=5, approximate=False,
        denominator=None, denominator_note="测试",
    )

    assert summary["units"] == ["新单位"]
    assert record.is_stale is False and record.stale_reason is None and record.stale_at is None


@pytest.mark.asyncio
async def test_node_scope_new_record_gets_node_created_reason(stale_db):
    """无 legacy 基线的新节点保存实际落库为 node_created，且带调用时刻。"""
    from app.services.consol_node_scope import NodeScope, save_scoped_note_record

    project_id = uuid4()
    now = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)
    async with stale_db() as db:
        record = await save_scoped_note_record(
            db,
            NodeScope(project_id, YEAR, SECTION, node_key="A:subsidiary"),
            {"rows": [["项目", "1"]]},
            now=now,
        )
        await db.commit()

    assert record.is_stale is True
    assert record.stale_reason == ConsolNoteStaleSource.NODE_CREATED.value
    assert record.stale_at == now
    stored = (await _read_notes(stale_db, project_id))[0]
    assert stored.node_key == "A:subsidiary"
    assert stored.stale_reason == ConsolNoteStaleSource.NODE_CREATED.value


@pytest.mark.asyncio
async def test_node_scope_copy_inherits_legacy_reason_and_time(stale_db):
    """根合并节点从 legacy 行建专属行时，真实保存路径完整继承原因与时间。"""
    from app.services.consol_group_tree import ROLE_CONSOL
    from app.services.consol_node_scope import NodeScope, save_scoped_note_record
    from app.services.consol_tree_service import TreeNode

    project_id = uuid4()
    legacy_at = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)
    root = TreeNode(
        project_id=project_id, company_code="G", company_name="集团",
        parent_company_code=None, ultimate_company_code="G", consol_level=0,
        node_key="G:consol", role=ROLE_CONSOL, kind="aggregate",
    )
    async with stale_db() as db:
        db.add(_note(
            project_id, data={"rows": [["项目", "10"]]}, node_key=None,
            is_stale=True, stale_reason=ConsolNoteStaleSource.CONSOL_PUSH.value,
            stale_at=legacy_at,
        ))
        await db.commit()
        record = await save_scoped_note_record(
            db,
            NodeScope(project_id, YEAR, SECTION, node_key=root.node_key, tree=root, node=root),
            {"rows": [["项目", "20"]]},
            now=datetime(2026, 11, 6, 10, 0, tzinfo=timezone.utc),
        )
        await db.commit()

    assert record.node_key == root.node_key
    assert record.is_stale is True
    assert record.stale_reason == ConsolNoteStaleSource.CONSOL_PUSH.value
    assert record.stale_at.replace(tzinfo=timezone.utc) == legacy_at
    rows = await _read_notes(stale_db, project_id)
    assert {row.node_key for row in rows} == {None, root.node_key}


@pytest.mark.asyncio
async def test_formula_copy_writer_inherits_stale_metadata(stale_db):
    """公式服务的 legacy→节点复制函数完整继承 stale 元数据。"""
    from app.services.consol_note_formula_service import _copy_note_data_record

    project_id = uuid4()
    legacy_at = datetime(2026, 11, 7, 9, 0, tzinfo=timezone.utc)
    async with stale_db() as db:
        source = _note(
            project_id, data={"rows": [["项目", "10"]]},
            is_stale=True, stale_reason=ConsolNoteStaleSource.FORMULA_SETTINGS.value,
            stale_at=legacy_at,
        )
        db.add(source)
        await db.flush()
        copied = await _copy_note_data_record(
            db, source, project_id=project_id, year=YEAR,
            section_id=SECTION, node_key="G:consol",
        )

    assert copied.is_stale is True
    assert copied.stale_reason == ConsolNoteStaleSource.FORMULA_SETTINGS.value
    assert copied.stale_at == legacy_at
    assert copied.data == source.data


# ── V/R 迁移：只在 PostgreSQL 的一次性 schema 中执行，不触碰 public 表 ─────────

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
_STALE_MIGRATION_SUFFIX = "__consol_note_stale_semantics.sql"
_STALE_ROLLBACK_SUFFIX = "__rollback_consol_note_stale_semantics.sql"


def _locate_stale_migrations() -> tuple[str, Path, Path]:
    found: dict[str, list[tuple[str, Path]]] = {"V": [], "R": []}
    for path in _MIGRATIONS_DIR.iterdir():
        if not path.is_file():
            continue
        for kind, suffix in (("V", _STALE_MIGRATION_SUFFIX), ("R", _STALE_ROLLBACK_SUFFIX)):
            match = re.fullmatch(rf"{kind}(\d+){re.escape(suffix)}", path.name, re.IGNORECASE)
            if match:
                found[kind].append((match.group(1), path))
    assert len(found["V"]) == 1 and len(found["R"]) == 1, found
    v, forward = found["V"][0]
    r, rollback = found["R"][0]
    assert v == r, f"V/R 版本不一致：{forward.name} / {rollback.name}"
    return v, forward, rollback


@asynccontextmanager
async def _stale_migration_schema():
    """创建独立 schema；每条连接的 search_path 只含该 schema。"""
    from app.core.config import settings

    database_url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in database_url:
        raise RuntimeError("V/R 迁移验收需要环境变量 DATABASE_URL 指向 PostgreSQL")
    connect_args = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    admin = create_async_engine(database_url, poolclass=NullPool, connect_args=connect_args)
    schema = f"tmp_consol_stale_{uuid4().hex[:12]}"
    scoped = None
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        scoped = create_async_engine(
            database_url,
            poolclass=NullPool,
            connect_args={**connect_args, "server_settings": {"search_path": schema}},
        )
        async with scoped.begin() as conn:
            # 只建 V270 的 legacy 前置表，确保 ADD COLUMN 真正被执行。
            await conn.exec_driver_sql(
                "CREATE TABLE consol_note_data ("
                "id UUID PRIMARY KEY, "
                "is_stale BOOLEAN NOT NULL DEFAULT FALSE)"
            )
            # 预置执行器追踪表的完整列，避免 runner 查询 public 同名表时误判缺列。
            await conn.exec_driver_sql(
                "CREATE TABLE schema_version ("
                "id SERIAL PRIMARY KEY, version VARCHAR(20) NOT NULL UNIQUE, "
                "filename VARCHAR(255) NOT NULL, applied_at TIMESTAMP NOT NULL DEFAULT NOW(), "
                "checksum VARCHAR(64) NOT NULL, operator VARCHAR(100), rollback_note TEXT)"
            )
            true_id, false_id = uuid4(), uuid4()
            await conn.execute(
                sa.text("INSERT INTO consol_note_data (id, is_stale) VALUES (:true_id, TRUE), (:false_id, FALSE)"),
                {"true_id": true_id, "false_id": false_id},
            )
        yield schema, scoped, true_id, false_id
    finally:
        if scoped is not None:
            await scoped.dispose()
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            left = await conn.scalar(
                sa.text("SELECT count(*) FROM pg_namespace WHERE nspname = :schema"),
                {"schema": schema},
            )
        await admin.dispose()
        assert left == 0, f"临时迁移 schema 未清理：{schema}"


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_stale_migration_forward_backfill_and_rollback(tmp_path):
    """真实 MigrationRunner：V 加列并回填 legacy，R 删除列；全程只在临时 schema。"""
    from app.core.migration_runner import MigrationRunner

    version, forward, rollback = _locate_stale_migrations()
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / forward.name).write_bytes(forward.read_bytes())
    (migration_dir / rollback.name).write_bytes(rollback.read_bytes())
    assert hashlib.sha256((migration_dir / forward.name).read_bytes()).digest() == hashlib.sha256(
        forward.read_bytes()
    ).digest()

    async with _stale_migration_schema() as (schema, engine, true_id, false_id):
        runner = MigrationRunner(engine=engine, migrations_dir=migration_dir)
        pending = await runner.run_pending()
        assert pending.executed == [version]
        assert pending.failed == []

        async with engine.connect() as conn:
            columns = {
                row[0]
                for row in (
                    await conn.execute(
                        sa.text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = :schema AND table_name = 'consol_note_data'"
                        ),
                        {"schema": schema},
                    )
                ).all()
            }
            assert {"stale_reason", "stale_at"} <= columns
            values = {
                str(row[0]): (row[1], row[2], row[3])
                for row in (
                    await conn.execute(
                        sa.text(
                            "SELECT id, is_stale, stale_reason, stale_at "
                            "FROM consol_note_data ORDER BY id"
                        )
                    )
                ).all()
            }
            # 通过 id 定位，避免 UUID 排序把两个样例的顺序写死。
            legacy = values[str(true_id)]
            fresh = values[str(false_id)]
            assert legacy[0] is True and legacy[1] == "legacy" and legacy[2] is None
            assert fresh[0] is False and fresh[1] is None and fresh[2] is None
            registered = await conn.execute(
                sa.text("SELECT version, filename FROM schema_version WHERE version = :version"),
                {"version": version},
            )
            assert registered.one() == (version, forward.name)

        backup_calls: list[tuple[str, str]] = []
        runner._run_backup = lambda from_version, to_version: (
            backup_calls.append((from_version, to_version)) or Path("不落盘的测试替身")
        )
        rolled_back = await runner.rollback_to(str(int(version) - 1))
        assert rolled_back == [version]
        assert backup_calls == [(version, str(int(version) - 1))]

        async with engine.connect() as conn:
            columns_after = {
                row[0]
                for row in (
                    await conn.execute(
                        sa.text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = :schema AND table_name = 'consol_note_data'"
                        ),
                        {"schema": schema},
                    )
                ).all()
            }
            assert "stale_reason" not in columns_after and "stale_at" not in columns_after
            assert await conn.scalar(
                sa.text("SELECT count(*) FROM schema_version WHERE version = :version"),
                {"version": version},
            ) == 0
            # 回滚只删新列，不碰原有 stale 数据行。
            assert await conn.scalar(sa.text("SELECT count(*) FROM consol_note_data")) == 2
