"""合并 push/refresh 的 CalcBasis 单次装载与父链单查询守卫。"""

from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.schemas.consol_context import ConsolContext
from app.services.consol_calc_basis import (
    CalcBasis,
    CalcBasisBoundaryError,
    validate_calc_basis,
)
from app.services.consol_context_service import context_from_tree
from app.services.consol_tree_service import TreeNode

YEAR = 2025


def _tree(project_id: uuid.UUID, code: str, *, children: list[TreeNode] | None = None) -> TreeNode:
    return TreeNode(
        project_id=project_id,
        company_code=code,
        company_name=code,
        parent_company_code=None,
        ultimate_company_code=code,
        consol_level=1,
        children=children or [],
        report_scope="consolidated",
        node_key=f"{code}:consol",
        role="consol",
        kind="aggregate",
        display_name=f"{code}（合并）",
        mode="subsidiary",
    )


def _basis(tree: TreeNode, *, year: int = YEAR) -> CalcBasis:
    return CalcBasis(
        tree=tree,
        year=year,
        accounts=[],
        names={},
        categories={},
        signs={},
        leaf_amounts={},
        elim_totals={},
    )


def test_basis_is_keyword_only_on_all_compatible_entrypoints() -> None:
    from app.services.consol_push_service import _refresh_notes, refresh_notes_exclusive
    from app.services.consol_report_service import ConsolReportService, generate_consol_reports_sync
    from app.services.consol_trial_service import recalculate_trial
    from app.services.consol_worksheet_engine import recalc_full

    entries = (
        recalc_full,
        recalculate_trial,
        ConsolReportService.generate_consol_reports,
        generate_consol_reports_sync,
        _refresh_notes,
        refresh_notes_exclusive,
    )
    for entry in entries:
        parameter = inspect.signature(entry).parameters["basis"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, entry
        assert parameter.default is None, entry


def test_injected_basis_rejects_year_project_and_tree_mismatch() -> None:
    project_id = uuid.uuid4()
    other_project_id = uuid.uuid4()
    tree = _tree(project_id, "ROOT")
    basis = _basis(tree)

    validate_calc_basis(basis, project_id, YEAR, tree=tree)
    with pytest.raises(CalcBasisBoundaryError, match="年度"):
        validate_calc_basis(basis, project_id, YEAR + 1, tree=tree)
    with pytest.raises(CalcBasisBoundaryError, match="项目"):
        validate_calc_basis(basis, other_project_id, YEAR, tree=tree)

    changed_tree = _tree(project_id, "ROOT", children=[_tree(uuid.uuid4(), "SUB")])
    with pytest.raises(CalcBasisBoundaryError, match="树指纹"):
        validate_calc_basis(basis, project_id, YEAR, tree=changed_tree)


@pytest.mark.asyncio
async def test_push_loads_one_distinct_basis_per_target_and_reuses_it_in_all_steps(monkeypatch) -> None:
    from app.services import consol_calc_basis, consol_context_service, consol_push_service, consol_tree_service
    from app.services import consol_report_service, consol_trial_service, consol_worksheet_engine

    source_id, parent_id = uuid.uuid4(), uuid.uuid4()
    targets = (source_id, parent_id)
    trees = {pid: _tree(pid, f"P{i}") for i, pid in enumerate(targets)}
    contexts: dict[uuid.UUID, ConsolContext] = {
        pid: context_from_tree(pid, YEAR, trees[pid]) for pid in targets
    }
    bases = {pid: _basis(trees[pid]) for pid in targets}

    build_tree = AsyncMock(side_effect=lambda _db, pid: trees[pid])
    build_source_context = AsyncMock(side_effect=lambda _db, pid, _year, **_kw: contexts[pid])
    build_target_context = AsyncMock(side_effect=lambda _db, _seed, pid, _year, **_kw: contexts[pid])
    load_basis = AsyncMock(side_effect=lambda _db, pid, _year, **_kw: bases[pid])
    worksheet = AsyncMock(return_value={"node_count": 1, "account_count": 0, "orphan_entries": []})
    trial = AsyncMock(return_value=[])
    report = AsyncMock(return_value={})
    notes = AsyncMock(return_value={
        "stale_marked": 0,
        "distinct_section_count": 1,
        "node_count": 1,
        "refreshed_count": 1,
        "failed_count": 0,
        "skipped_count": 0,
        "note_status": "persisted",
    })
    record_tree = AsyncMock(return_value="")

    monkeypatch.setattr(consol_push_service, "push_targets", AsyncMock(return_value=list(targets)))
    monkeypatch.setattr(consol_push_service, "_project_name", AsyncMock(side_effect=lambda _db, pid: str(pid)))
    monkeypatch.setattr(consol_push_service, "_record_tree_version", record_tree)
    monkeypatch.setattr(consol_push_service, "_advisory_lock", AsyncMock())
    monkeypatch.setattr(consol_push_service, "_refresh_notes", notes)
    monkeypatch.setattr(consol_push_service, "_finish_run", AsyncMock())
    monkeypatch.setattr(consol_push_service, "_broadcast", MagicMock())
    monkeypatch.setattr(consol_tree_service, "build_tree", build_tree)
    monkeypatch.setattr(consol_context_service, "build_consol_context", build_source_context)
    monkeypatch.setattr(consol_context_service, "build_target_consol_context", build_target_context)
    monkeypatch.setattr(consol_calc_basis, "load_calc_basis", load_basis)
    monkeypatch.setattr(consol_worksheet_engine, "recalc_full", worksheet)
    monkeypatch.setattr(consol_trial_service, "recalculate_trial", trial)
    monkeypatch.setattr(consol_report_service.ConsolReportService, "generate_consol_reports", report)

    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    result = await consol_push_service.push(db, source_id, YEAR)

    assert result.status == "succeeded"
    assert result.pushed_projects == [str(source_id), str(parent_id)]
    assert build_tree.await_count == 2
    assert build_source_context.await_count == 1
    assert build_target_context.await_count == 1
    assert load_basis.await_count == 2
    assert [call.args[1] for call in load_basis.await_args_list] == list(targets)
    assert bases[source_id] is not bases[parent_id]

    for index, target in enumerate(targets):
        for stage in (worksheet, trial, report, notes):
            call = stage.await_args_list[index]
            assert call.kwargs["tree"] is trees[target]
            assert call.kwargs["context"] is contexts[target]
            assert call.kwargs["basis"] is bases[target]
        assert record_tree.await_args_list[index].kwargs["tree"] is trees[target]


@pytest_asyncio.fixture
async def topology_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.exec_driver_sql(
            "CREATE TABLE projects ("
            "id CHAR(32) PRIMARY KEY, "
            "parent_project_id CHAR(32), "
            "report_scope VARCHAR(20), "
            "is_deleted BOOLEAN NOT NULL DEFAULT 0)"
        )
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session, engine
    await engine.dispose()


async def _insert_topology(
    db: AsyncSession,
    rows: list[tuple[uuid.UUID, uuid.UUID | None, str, bool]],
) -> None:
    statement = sa.text(
        "INSERT INTO projects (id, parent_project_id, report_scope, is_deleted) "
        "VALUES (:id, :parent_id, :scope, :deleted)"
    )
    for project_id, parent_id, scope, deleted in rows:
        await db.execute(statement, {
            "id": project_id.hex,
            "parent_id": parent_id.hex if parent_id else None,
            "scope": scope,
            "deleted": deleted,
        })
    await db.commit()


async def _targets_and_sql_count(db: AsyncSession, engine, project_id: uuid.UUID):
    from app.services.consol_push_service import push_targets

    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        targets = await push_targets(db, project_id)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
    return targets, statements


@pytest.mark.asyncio
async def test_push_targets_one_recursive_query_crosses_non_consolidated_and_stops_at_deleted_or_cycle(
    topology_db,
) -> None:
    db, engine = topology_db
    source, middle, upper, deleted, hidden = [uuid.uuid4() for _ in range(5)]
    ring_source, ring_middle, ring_upper = [uuid.uuid4() for _ in range(3)]
    await _insert_topology(db, [
        (source, middle, "standalone", False),
        (middle, upper, "standalone", False),
        (upper, deleted, " consolidated ", False),
        (deleted, hidden, "consolidated", True),
        (hidden, None, "consolidated", False),
        (ring_source, ring_middle, "consolidated", False),
        (ring_middle, ring_upper, "standalone", False),
        (ring_upper, ring_source, "consolidated", False),
    ])

    targets, statements = await _targets_and_sql_count(db, engine, source)
    assert targets == [source, upper]
    assert len(statements) == 1
    assert "WITH RECURSIVE" in statements[0].upper()

    ring_targets, ring_statements = await _targets_and_sql_count(db, engine, ring_source)
    assert ring_targets == [ring_source, ring_upper]
    assert len(ring_statements) == 1


@pytest.mark.asyncio
async def test_push_targets_query_count_is_constant_and_depth_is_capped_at_32(topology_db) -> None:
    db, engine = topology_db
    chain = [uuid.uuid4() for _ in range(35)]
    await _insert_topology(db, [
        (project_id, chain[index + 1] if index + 1 < len(chain) else None, "consolidated", False)
        for index, project_id in enumerate(chain)
    ])

    deep_targets, deep_statements = await _targets_and_sql_count(db, engine, chain[0])
    shallow_targets, shallow_statements = await _targets_and_sql_count(db, engine, chain[-1])

    assert deep_targets == chain[:33], "depth=0 的 self 加最多 32 层父项目"
    assert shallow_targets == [chain[-1]]
    assert len(deep_statements) == len(shallow_statements) == 1


@pytest.mark.asyncio
async def test_push_targets_statement_compiles_for_postgresql_without_connecting() -> None:
    from app.services.consol_push_service import push_targets

    captured: dict[str, object] = {}

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return []

    class _Db:
        async def execute(self, statement, parameters):
            captured["statement"] = statement
            captured["parameters"] = parameters
            return _Result()

    project_id = uuid.uuid4()
    assert await push_targets(_Db(), project_id) == []
    compiled = str(captured["statement"].compile(dialect=postgresql.dialect()))
    assert "WITH RECURSIVE" in compiled.upper()
    assert captured["parameters"] == {"root_project_id": project_id}


@pytest.mark.asyncio
async def test_calculation_entrypoints_use_injected_basis_without_reloading(monkeypatch) -> None:
    from app.services import consol_calc_basis, consol_report_service, consol_report_values
    from app.services import consol_report_view_service, consol_trial_service, consol_worksheet_engine

    project_id = uuid.uuid4()
    tree = _tree(project_id, "ROOT")
    basis = _basis(tree)
    context = context_from_tree(project_id, YEAR, tree)
    forbidden_load = AsyncMock(side_effect=AssertionError("传入 basis 后不得重新装载"))

    # worksheet
    monkeypatch.setattr(consol_worksheet_engine, "load_calc_basis", forbidden_load)
    monkeypatch.setattr(consol_worksheet_engine, "worksheet_rows", MagicMock(return_value=[]))
    monkeypatch.setattr(consol_worksheet_engine, "_write_rows", AsyncMock(return_value=(0, 0)))
    worksheet_db = MagicMock(commit=AsyncMock())
    await consol_worksheet_engine.recalc_full(
        worksheet_db, project_id, YEAR, context=context, tree=tree, basis=basis,
    )

    # trial（函数内按调用时从 consol_calc_basis 导入 loader）
    monkeypatch.setattr(consol_calc_basis, "load_calc_basis", forbidden_load)
    monkeypatch.setattr(consol_calc_basis, "trial_amounts", MagicMock(return_value={}))
    monkeypatch.setattr(consol_trial_service, "sync_trial_rows", AsyncMock(return_value=[]))
    monkeypatch.setattr(consol_trial_service, "get_trial_balance", AsyncMock(return_value=[]))
    await consol_trial_service.recalculate_trial(
        MagicMock(), project_id, YEAR, context=context, tree=tree, basis=basis,
    )

    # report
    monkeypatch.setattr(
        consol_calc_basis,
        "node_measures",
        MagicMock(return_value={tree.node_key: {"consolidated": {}}}),
    )
    monkeypatch.setattr(consol_report_values, "resolve_consol_standard", AsyncMock(return_value="soe_consolidated"))
    monkeypatch.setattr(consol_report_values, "load_report_rows", AsyncMock(return_value=[]))
    monkeypatch.setattr(consol_report_values, "report_values", AsyncMock(return_value={}))
    report_rows = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
    report_db = MagicMock(execute=AsyncMock(return_value=report_rows), flush=AsyncMock())
    report_service = consol_report_service.ConsolReportService(report_db)
    monkeypatch.setattr(report_service, "_prior_year_amounts", AsyncMock(return_value={}))
    await report_service.generate_consol_reports(
        project_id, YEAR, context=context, tree=tree, basis=basis,
    )

    # notes 的计算入口是 ViewContext；传入口径后只再读取准则和报表配置。
    view_loader = AsyncMock(side_effect=AssertionError("附注 ViewContext 不得重新装载 basis"))
    monkeypatch.setattr(consol_report_view_service, "load_calc_basis", view_loader)
    monkeypatch.setattr(consol_report_view_service, "resolve_consol_standard", AsyncMock(return_value="soe_consolidated"))
    monkeypatch.setattr(consol_report_view_service, "load_report_rows", AsyncMock(return_value=[]))
    view = await consol_report_view_service.load_view_context(
        MagicMock(), project_id, YEAR, context=context, tree=tree, basis=basis,
    )
    assert view is not None and view.basis is basis
    forbidden_load.assert_not_awaited()
    view_loader.assert_not_awaited()


@pytest.mark.asyncio
async def test_scope_version_state_reuses_prebuilt_tree(monkeypatch) -> None:
    from app.services import consol_scope_confirmation_service as scope

    project_id = uuid.uuid4()
    tree = _tree(project_id, "ROOT")
    project = SimpleNamespace(
        id=project_id,
        report_scope="consolidated",
        audit_year=YEAR,
        audit_period_end=None,
        consol_lock=False,
    )

    class _ScalarResult:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[
        _ScalarResult(project),
        _ScalarResult(None),
        _ScalarResult(None),
    ])
    rebuild = AsyncMock(side_effect=AssertionError("预构建树不得再次推导"))
    monkeypatch.setattr(scope, "build_group_tree", rebuild)

    state = await scope._load_state(db, project_id, tree=tree)

    assert state["result"].root is tree
    assert state["result"].year == YEAR
    rebuild.assert_not_awaited()
