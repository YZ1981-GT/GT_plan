"""合并附注节点作用域的真实 ORM/SQLite 回归。

覆盖任务 2 的节点年度、四元组隔离、根 legacy 兼容复制以及 SAVEPOINT 冲突恢复。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.consol_note_data_models import ConsolNoteData
from app.models.core import Project
from app.services.consol_node_scope import (
    NodeScope,
    NodeScopeError,
    load_scoped_note_record,
    resolve_node_scope,
    save_scoped_note_record,
)

# SQLite 测试库沿用 PG JSONB 的 ORM 映射；StaticPool 让内存库在独立会话间可复读。
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]

_ENGINE = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    echo=False,
    poolclass=StaticPool,
)
_SESSION_FACTORY = async_sessionmaker(_ENGINE, class_=AsyncSession, expire_on_commit=False)
_TABLES = [Project.__table__, ConsolNoteData.__table__]
_YEAR = 2025
_SECTION = "五-1-1"
_ROOT_KEY = "G:consol"
_CHILD_KEY = "A:subsidiary"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with _ENGINE.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.drop_all(sync_conn, tables=_TABLES))
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=_TABLES))
    async with _SESSION_FACTORY() as session:
        yield session
        await session.rollback()


async def _seed_projects(session: AsyncSession) -> tuple[Project, Project, Project]:
    root = Project(
        id=uuid4(),
        name="集团_2025",
        client_name="集团",
        company_code="G",
        ultimate_company_code="G",
        report_scope="consolidated",
        audit_year=_YEAR,
        audit_period_end=date(_YEAR, 12, 31),
    )
    child = Project(
        id=uuid4(),
        name="子公司A_2025",
        client_name="子公司A",
        company_code="A",
        parent_company_code="G",
        ultimate_company_code="G",
        relation_to_parent="subsidiary",
        report_scope="standalone",
        audit_year=_YEAR,
        audit_period_end=date(_YEAR, 12, 31),
    )
    other = Project(
        id=uuid4(),
        name="其他项目_2025",
        client_name="其他项目",
        company_code="O",
        ultimate_company_code="O",
        report_scope="consolidated",
        audit_year=_YEAR,
        audit_period_end=date(_YEAR, 12, 31),
    )
    session.add_all([root, child, other])
    await session.commit()
    return root, child, other


async def _root_scope(session: AsyncSession, root: Project, section: str = _SECTION) -> NodeScope:
    scope = await resolve_node_scope(session, root.id, _YEAR, _ROOT_KEY, section)
    assert scope.node is not None and scope.node.node_key == _ROOT_KEY
    assert scope.is_root_consol
    return scope


async def _child_scope(session: AsyncSession, root: Project, section: str = _SECTION) -> NodeScope:
    scope = await resolve_node_scope(session, root.id, _YEAR, _CHILD_KEY, section)
    assert scope.node is not None and scope.node.node_key == _CHILD_KEY
    assert not scope.is_root_consol
    return scope


async def _get_record(
    session: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    section_id: str,
    node_key: str | None,
) -> ConsolNoteData | None:
    target = ConsolNoteData.node_key.is_(None) if node_key is None else ConsolNoteData.node_key == node_key
    return (
        await session.execute(
            sa.select(ConsolNoteData).where(
                ConsolNoteData.project_id == project_id,
                ConsolNoteData.year == year,
                ConsolNoteData.section_id == section_id,
                target,
            )
        )
    ).scalar_one_or_none()


@pytest.mark.asyncio
async def test_resolve_uses_effective_year_and_rejects_invalid_node(db_session: AsyncSession):
    root, _child, _other = await _seed_projects(db_session)

    scope = await _root_scope(db_session, root)
    assert scope.year == _YEAR

    with pytest.raises(NodeScopeError, match="请求年度 2024 与项目有效审计年度 2025 不一致") as exc_info:
        await resolve_node_scope(db_session, root.id, 2024, _ROOT_KEY, _SECTION)
    assert exc_info.value.status == 400

    with pytest.raises(NodeScopeError, match="不在当前企业树中") as exc_info:
        await resolve_node_scope(db_session, root.id, _YEAR, "G:unknown", _SECTION)
    assert exc_info.value.status == 404


@pytest.mark.asyncio
async def test_exact_scope_isolated_by_project_year_and_section(db_session: AsyncSession):
    root, _child, other = await _seed_projects(db_session)
    scope = await _root_scope(db_session, root)
    target_data = {"rows": [{"label": "目标", "cells": [{"value": 10}]}]}
    db_session.add_all([
        ConsolNoteData(project_id=root.id, year=_YEAR, section_id=_SECTION, node_key=_ROOT_KEY, data=target_data),
        ConsolNoteData(project_id=root.id, year=2024, section_id=_SECTION, node_key=_ROOT_KEY, data={"rows": [{"label": "旧年度"}]}),
        ConsolNoteData(project_id=root.id, year=_YEAR, section_id="五-2-1", node_key=_ROOT_KEY, data={"rows": [{"label": "其他章节"}]}),
        ConsolNoteData(project_id=other.id, year=_YEAR, section_id=_SECTION, node_key=_ROOT_KEY, data={"rows": [{"label": "其他项目"}]}),
    ])
    await db_session.commit()

    record = await load_scoped_note_record(db_session, scope, allow_root_legacy_fallback=False)
    assert record is not None
    assert record.data == target_data


@pytest.mark.asyncio
async def test_root_get_fallback_and_first_save_copy_leave_legacy_unchanged(db_session: AsyncSession):
    root, _child, _other = await _seed_projects(db_session)
    legacy_data = {
        "headers": ["项目", "期末"],
        "rows": [{"label": "legacy", "cells": [{"value": 100, "meta": {"source": "old"}}]}],
        "nested": {"values": [1, {"deep": True}]},
    }
    legacy_time = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    legacy = ConsolNoteData(
        id=uuid4(),
        project_id=root.id,
        year=_YEAR,
        section_id=_SECTION,
        node_key=None,
        data=legacy_data,
        updated_at=legacy_time,
        is_stale=True,
    )
    db_session.add(legacy)
    await db_session.commit()

    scope = await _root_scope(db_session, root)
    fallback = await load_scoped_note_record(db_session, scope)
    assert fallback is not None and fallback.id == legacy.id
    legacy_before = (
        legacy.id,
        legacy.node_key,
        deepcopy(legacy.data),
        legacy.updated_at.replace(tzinfo=None),
        legacy.is_stale,
    )

    payload = {"headers": ["项目", "期末"], "rows": [{"label": "new", "cells": [{"value": 200}]}]}
    saved_time = datetime(2025, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
    saved = await save_scoped_note_record(db_session, scope, payload, now=saved_time)
    assert saved.node_key == _ROOT_KEY
    assert saved.updated_at == saved_time
    assert saved.is_stale is True  # 继承 legacy 的过期状态
    assert saved.data == payload
    assert saved.data is not payload
    assert saved.data["rows"] is not payload["rows"]

    # 调用方后续修改原 payload 不得改变待提交的 ORM 快照。
    payload["rows"][0]["cells"][0]["value"] = 999
    await db_session.commit()

    async with _SESSION_FACTORY() as check:
        stored_legacy = await _get_record(
            check, project_id=root.id, year=_YEAR, section_id=_SECTION, node_key=None,
        )
        stored_root = await _get_record(
            check, project_id=root.id, year=_YEAR, section_id=_SECTION, node_key=_ROOT_KEY,
        )
        assert stored_legacy is not None and stored_root is not None
        assert (stored_legacy.id, stored_legacy.node_key, stored_legacy.data, stored_legacy.updated_at, stored_legacy.is_stale) == legacy_before
        assert stored_root.data["rows"][0]["cells"][0]["value"] == 200
        assert stored_root.updated_at == saved_time.replace(tzinfo=None)
        assert stored_root.is_stale is True


@pytest.mark.asyncio
async def test_existing_node_save_updates_only_node_and_preserves_stale(db_session: AsyncSession):
    root, _child, _other = await _seed_projects(db_session)
    legacy = ConsolNoteData(
        project_id=root.id, year=_YEAR, section_id=_SECTION, node_key=None,
        data={"rows": [{"label": "legacy", "value": 1}]}, is_stale=False,
    )
    node = ConsolNoteData(
        project_id=root.id, year=_YEAR, section_id=_SECTION, node_key=_ROOT_KEY,
        data={"rows": [{"label": "root", "value": 2}]}, is_stale=True,
    )
    db_session.add_all([legacy, node])
    await db_session.commit()
    scope = await _root_scope(db_session, root)
    saved_time = datetime(2025, 3, 4, tzinfo=timezone.utc)

    saved = await save_scoped_note_record(
        db_session, scope, {"rows": [{"label": "updated", "value": 3}]}, now=saved_time,
    )
    await db_session.commit()

    async with _SESSION_FACTORY() as check:
        stored_legacy = await _get_record(check, project_id=root.id, year=_YEAR, section_id=_SECTION, node_key=None)
        stored_node = await _get_record(check, project_id=root.id, year=_YEAR, section_id=_SECTION, node_key=_ROOT_KEY)
        assert stored_legacy is not None and stored_node is not None
        assert stored_legacy.data["rows"][0]["value"] == 1
        assert stored_node.data["rows"][0]["value"] == 3
        assert stored_node.is_stale is True
        assert stored_node.updated_at == saved_time.replace(tzinfo=None)
        assert saved.id == stored_node.id


@pytest.mark.asyncio
async def test_non_root_never_falls_back_and_nodes_do_not_mix(db_session: AsyncSession):
    root, _child, _other = await _seed_projects(db_session)
    db_session.add_all([
        ConsolNoteData(
            project_id=root.id, year=_YEAR, section_id=_SECTION, node_key=None,
            data={"rows": [{"label": "legacy", "value": 1}]},
        ),
    ])
    await db_session.commit()

    child_scope = await _child_scope(db_session, root)
    assert await load_scoped_note_record(db_session, child_scope) is None

    child_saved = await save_scoped_note_record(
        db_session, child_scope, {"rows": [{"label": "child", "value": 2}]},
    )
    legacy_scope = NodeScope(project_id=root.id, year=_YEAR, section_id=_SECTION)
    legacy = await load_scoped_note_record(db_session, legacy_scope)
    assert child_saved.node_key == _CHILD_KEY
    assert legacy is not None and legacy.data["rows"][0]["value"] == 1

    root_scope = await _root_scope(db_session, root)
    root_record = await load_scoped_note_record(db_session, root_scope)
    assert root_record is not None and root_record.node_key is None


@pytest.mark.asyncio
async def test_legacy_scope_only_reads_and_writes_null_row(db_session: AsyncSession):
    root, _child, _other = await _seed_projects(db_session)
    legacy_scope = NodeScope(project_id=root.id, year=_YEAR, section_id=_SECTION)
    saved = await save_scoped_note_record(
        db_session, legacy_scope, {"rows": [{"label": "legacy", "value": 10}]},
    )
    assert saved.node_key is None
    await db_session.commit()

    root_scope = await _root_scope(db_session, root)
    root_record = await load_scoped_note_record(db_session, root_scope)
    assert root_record is not None and root_record.node_key is None

    await save_scoped_note_record(
        db_session, legacy_scope, {"rows": [{"label": "legacy updated", "value": 11}]},
    )
    await db_session.commit()
    rows = list((await db_session.execute(sa.select(ConsolNoteData))).scalars().all())
    assert len(rows) == 1
    assert rows[0].node_key is None
    assert rows[0].data["rows"][0]["value"] == 11


@pytest.mark.asyncio
async def test_root_without_legacy_uses_normal_new_node_stale_semantics(db_session: AsyncSession):
    root, _child, _other = await _seed_projects(db_session)
    scope = await _root_scope(db_session, root)
    saved = await save_scoped_note_record(
        db_session, scope, {"rows": [{"label": "new root", "value": 7}]},
    )
    await db_session.commit()
    assert saved.node_key == _ROOT_KEY
    assert saved.is_stale is True
    assert await _get_record(
        db_session, project_id=root.id, year=_YEAR, section_id=_SECTION, node_key=None,
    ) is None


@pytest.mark.asyncio
async def test_unique_conflict_reloads_winner_and_outer_transaction_survives(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    """真实 SQLite 唯一索引冲突后，SAVEPOINT 回滚且外层事务仍可继续。"""
    root, _child, _other = await _seed_projects(db_session)
    legacy = ConsolNoteData(
        project_id=root.id, year=_YEAR, section_id=_SECTION, node_key=None,
        data={"rows": [{"label": "legacy", "value": 1}]},
    )
    db_session.add(legacy)
    await db_session.commit()
    scope = await _root_scope(db_session, root)

    import app.services.consol_node_scope as node_scope_module

    original_loader = node_scope_module._load_exact_note_record
    calls = 0
    injected_winner: ConsolNoteData | None = None

    async def load_and_inject(*args, **kwargs):
        nonlocal calls, injected_winner
        result = await original_loader(*args, **kwargs)
        calls += 1
        # 第一次是精确目标查询；第二次是读取 legacy 基线。在生产插入前
        # 先在当前外层事务制造真实唯一键赢家，让候选行触发 SAVEPOINT 回滚。
        if calls == 2 and args[1].node_key is None:
            injected_winner = ConsolNoteData(
                project_id=root.id,
                year=_YEAR,
                section_id=_SECTION,
                node_key=_ROOT_KEY,
                data={"rows": [{"label": "winner before candidate", "value": 20}]},
                is_stale=False,
            )
            db_session.add(injected_winner)
            await db_session.flush()
        return result

    monkeypatch.setattr(node_scope_module, "_load_exact_note_record", load_and_inject)
    saved_time = datetime(2025, 4, 5, tzinfo=timezone.utc)
    saved = await save_scoped_note_record(
        db_session, scope, {"rows": [{"label": "last writer", "value": 30}]}, now=saved_time,
    )
    assert injected_winner is not None
    assert saved.id == injected_winner.id
    assert saved.data["rows"][0]["value"] == 30
    assert db_session.in_transaction()

    # 外层事务仍能写入另一个合法范围；若把 IntegrityError 留在外层，下面的
    # flush/commit 会抛 PendingRollbackError，这正是该回归要钉住的行为。
    other_section = ConsolNoteData(
        project_id=root.id,
        year=_YEAR,
        section_id="五-9-9",
        node_key=None,
        data={"rows": [{"label": "after conflict", "value": 99}]},
    )
    db_session.add(other_section)
    await db_session.flush()
    await db_session.commit()

    async with _SESSION_FACTORY() as check:
        rows = list(
            (
                await check.execute(
                    sa.select(ConsolNoteData).order_by(ConsolNoteData.section_id)
                )
            ).scalars().all()
        )
        assert len(rows) == 3
        stored_legacy = next(row for row in rows if row.section_id == _SECTION and row.node_key is None)
        stored_winner = next(row for row in rows if row.section_id == _SECTION and row.node_key == _ROOT_KEY)
        stored_other = next(row for row in rows if row.section_id == "五-9-9")
        assert stored_legacy.data["rows"][0]["value"] == 1
        assert stored_winner.id == injected_winner.id
        assert stored_winner.data["rows"][0]["value"] == 30
        assert stored_winner.updated_at == saved_time.replace(tzinfo=None)
        assert stored_other.data["rows"][0]["value"] == 99
