"""高级查询阶段 0：退役写入口、存活项目、变换语义、查询保护与 DSL 边界。"""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException, Response
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import literal, select, text
from sqlalchemy.dialects import sqlite
from sqlalchemy.exc import SQLAlchemyError

from app.models.core import Project, ProjectStatus
from app.routers import custom_query, custom_query_writeback, query_builder
from app.services.custom_query.builder_dsl import QueryDSL, _build_select
from app.services.custom_query.builder_scope import BuilderScope, resolve_builder_scope, scope_signature
from app.services.custom_query.execution_guard import statement_timeout
from app.services.custom_query.ownership_guard import ownership_guard
from app.services.custom_query.query_orchestrator import (
    Agg,
    ColumnMeta,
    PivotConfig,
    QueryOrchestrator,
    QueryRequest,
)
from tests.authz_world import TARGET_PROJECT_ID, sqlite_world


_RETIRED = (
    (custom_query.router, "/api/custom-query/cell-writeback"),
    (custom_query_writeback.router, "/api/custom-query/writeback-preview"),
    (custom_query_writeback.router, "/api/custom-query/writeback-confirm"),
)


@pytest.mark.asyncio
async def test_retired_write_routes_are_dependency_free_410_stubs() -> None:
    app = FastAPI()
    for router, _ in _RETIRED:
        app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://aqs") as client:
        for _, path in _RETIRED:
            response = await client.post(path, json={"malformed": True})
            assert response.status_code == 410, (path, response.text)
            assert response.json()["detail"]["error_code"] == "ADVANCED_QUERY_WRITEBACK_RETIRED"

    routes = {route.path: route for route in app.routes if isinstance(route, APIRoute)}
    for _, path in _RETIRED:
        route = routes[path]
        assert route.dependant.dependencies == [], path
        assert route.body_field is None, path


@pytest.mark.asyncio
async def test_deleted_project_is_forbidden_for_member_and_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    async with sqlite_world(monkeypatch) as world:
        member = (await world.edit_member()).user
        admin = (await world.admin_non_member()).user
        project = await world.db.get(Project, TARGET_PROJECT_ID)
        assert project is not None
        project.is_deleted = True
        await world.db.flush()

        rls = AsyncMock()
        monkeypatch.setattr("app.services.custom_query.ownership_guard.set_rls_context", rls)
        monkeypatch.setattr(
            "app.services.custom_query.ownership_guard.audit_logger.log_action", AsyncMock(return_value={})
        )
        for user in (member, admin):
            with pytest.raises(HTTPException) as exc:
                await ownership_guard.assert_target_accessible(
                    user=user, project_id=TARGET_PROJECT_ID, db=world.db
                )
            assert exc.value.status_code == 403
            assert exc.value.detail["error_code"] == "FORBIDDEN_PROJECT"
        rls.assert_not_awaited()
        assert TARGET_PROJECT_ID not in (await ownership_guard.get_accessible_project_ids(member, world.db))

        fetched: list[bool] = []

        async def fetcher(*args, **kwargs):
            fetched.append(True)
            return [], []

        orchestrator = QueryOrchestrator(guard=ownership_guard, business_fetcher=fetcher)
        with pytest.raises(HTTPException):
            await orchestrator.execute(
                QueryRequest(entry="business", project_id=str(TARGET_PROJECT_ID), year=2025),
                user=admin, db=world.db,
            )
        assert fetched == [], "软删项目必须在领域取数前被拒绝"


def test_grouping_and_pivot_internal_errors_are_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.custom_query.grouping_engine import GroupingEngine
    from app.services.custom_query.pivot_engine import PivotEngine

    orchestrator = QueryOrchestrator()
    monkeypatch.setattr(GroupingEngine, "group", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("secret")))
    with pytest.raises(HTTPException) as group_exc:
        orchestrator._apply_grouping(
            QueryRequest(entry="business", project_id="p", group_by=["kind"], aggs=[Agg("amount")]),
            [{"kind": "x", "amount": 1}], [ColumnMeta("kind", "类别")], [],
        )
    assert group_exc.value.detail["error_code"] == "QUERY_TRANSFORM_FAILED"
    assert "secret" not in str(group_exc.value.detail)

    monkeypatch.setattr(PivotEngine, "pivot", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("secret")))
    with pytest.raises(HTTPException) as pivot_exc:
        orchestrator._apply_pivot(
            QueryRequest(entry="business", project_id="p", pivot=PivotConfig(["kind"], ["period"], "amount")),
            [{"kind": "x", "period": "本期", "amount": 1}], [ColumnMeta("kind", "类别")], [],
        )
    assert pivot_exc.value.detail["error_code"] == "QUERY_TRANSFORM_FAILED"


class _GuardSession:
    def __init__(self, dialect: str, *, fail_set: bool = False) -> None:
        self.dialect = dialect
        self.fail_set = fail_set
        self.statements: list[str] = []
        self.rolled_back = False

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name=self.dialect))

    def in_transaction(self) -> bool:
        return True

    async def execute(self, statement):
        self.statements.append(str(statement))
        if self.fail_set:
            raise RuntimeError("set failed")

    async def rollback(self):
        self.rolled_back = True


@pytest.mark.asyncio
async def test_statement_timeout_skips_known_sqlite_but_postgres_failure_is_503() -> None:
    sqlite = _GuardSession("sqlite")
    async with statement_timeout(sqlite):
        pass
    assert sqlite.statements == []

    postgres = _GuardSession("postgresql", fail_set=True)
    with pytest.raises(HTTPException) as exc:
        async with statement_timeout(postgres):
            pytest.fail("查询保护失败后不应进入查询体")
    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == "QUERY_GUARD_UNAVAILABLE"
    assert postgres.rolled_back is True


@pytest.mark.parametrize(
    "payload",
    [
        {"fields": ["id"] * 61},
        {"filters": [{"field": "id", "op": "eq", "value": 1}] * 21},
        {"order_by": [{"field": "id"}] * 6},
        {"joins": [{"table": "wp_index"}] * 4},
        {"aggregates": [{"func": "count", "field": "*"}] * 11},
        {"group_by": ["id"] * 6},
        {"offset": 100_001},
    ],
)
def test_query_dsl_resource_limits(payload: dict) -> None:
    with pytest.raises(ValidationError):
        QueryDSL(table="working_paper", **payload)


def test_query_dsl_rejects_extra_nested_keys_and_ambiguous_projection() -> None:
    with pytest.raises(ValidationError):
        QueryDSL(table="working_paper", joins=[{"table": "wp_index", "on": "1=1"}])
    with pytest.raises(ValidationError):
        QueryDSL(table="working_paper", aggregates=[{"func": "count", "field": "*", "sql": "raw"}])

    with pytest.raises(HTTPException) as missing_group:
        _build_select(QueryDSL(
            table="trial_balance", fields=["account_name"],
            aggregates=[{"func": "sum", "field": "audited_amount", "alias": "amount"}],
        ))
    assert missing_group.value.detail["error_code"] == "INVALID_QUERY_SHAPE"

    with pytest.raises(HTTPException) as duplicate:
        _build_select(QueryDSL(
            table="trial_balance", fields=["account_name"], group_by=["account_name"],
            aggregates=[{"func": "count", "field": "*", "alias": "account_name"}],
        ))
    assert duplicate.value.detail["error_code"] == "INVALID_QUERY_SHAPE"


@pytest.mark.asyncio
async def test_builder_database_error_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.query_cache as cache_module

    async def scope(*args, **kwargs):
        return BuilderScope(project_ids=None)

    async def no_targets(*args, **kwargs):
        return None

    async def cache_miss(*args, **kwargs):
        return None

    class Db:
        def get_bind(self):
            return SimpleNamespace(dialect=sqlite.dialect())

        async def execute(self, statement):
            raise SQLAlchemyError("driver secret: SELECT private_column")

        async def rollback(self):
            return None

    monkeypatch.setattr(query_builder, "_builder_scope", scope)
    monkeypatch.setattr(query_builder, "plan_builder_targets", no_targets)
    monkeypatch.setattr(cache_module, "get_cached_result", cache_miss)
    user = SimpleNamespace(id=uuid.uuid4(), role=SimpleNamespace(value="admin"))
    with pytest.raises(HTTPException) as exc:
        await query_builder.execute_query(
            QueryDSL(table="projects", fields=["id"]), Response(), Db(), user
        )
    detail = exc.value.detail
    assert detail["error_code"] == "QUERY_EXECUTION_FAILED"
    assert len(detail["correlation_id"]) == 32
    assert "secret" not in str(detail) and "SELECT" not in str(detail)


@pytest.mark.asyncio
async def test_builder_success_audit_contains_scope_not_business_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.core.redis as redis_module
    import app.services.custom_query.audit_helper as audit_module

    captured: list[dict] = []

    async def fake_redis():
        return object()

    async def record(**kwargs):
        captured.append(kwargs)
        return True

    class Db:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    monkeypatch.setattr(redis_module, "get_redis", fake_redis)
    monkeypatch.setattr(audit_module, "record_query_execution", record)
    body = QueryDSL(
        table="trial_balance", fields=["standard_account_code"],
        filters=[{"field": "standard_account_code", "op": "eq", "value": "1001"}],
        project_id=TARGET_PROJECT_ID,
    )
    user = SimpleNamespace(id=uuid.uuid4())
    await query_builder._audit_query_success(
        body, user=user, scope=BuilderScope(project_ids=frozenset({TARGET_PROJECT_ID})),
        total=12, cache_hit=False, db=Db(),
    )
    assert len(captured) == 1
    details = captured[0]["details"]
    assert details["table"] == "trial_balance" and details["row_count"] == 12
    assert details["condition_fields"] == ["standard_account_code"]
    assert "rows" not in details


@pytest.mark.asyncio
async def test_business_cache_scope_signature_changes_with_cycle_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    async def cycles(self, project_id):
        return list(self._user.cycles)

    monkeypatch.setattr(
        "app.services.custom_query.query_orchestrator.CycleScopeCache.cycles", cycles
    )
    request = QueryRequest(entry="business", project_id=str(TARGET_PROJECT_ID), year=2025)
    d_only = await QueryOrchestrator._scope_signature(
        SimpleNamespace(id="u1", cycles=("D",)), request, object()
    )
    e_only = await QueryOrchestrator._scope_signature(
        SimpleNamespace(id="u1", cycles=("E",)), request, object()
    )
    assert d_only != e_only
    assert d_only.endswith("cycles=D") and e_only.endswith("cycles=E")


@pytest.mark.asyncio
async def test_builder_execute_calls_success_audit_on_cache_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.query_cache as cache_module

    async def scope(*args, **kwargs):
        return BuilderScope(project_ids=None)

    async def no_targets(*args, **kwargs):
        return None

    async def cached(*args, **kwargs):
        return {"rows": [], "columns": ["id"], "total": 7, "table": "projects", "warnings": []}

    audits: list[dict] = []

    async def audit(*args, **kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(query_builder, "_builder_scope", scope)
    monkeypatch.setattr(query_builder, "plan_builder_targets", no_targets)
    monkeypatch.setattr(query_builder, "_audit_query_success", audit)
    monkeypatch.setattr(cache_module, "get_cached_result", cached)
    user = SimpleNamespace(id=uuid.uuid4(), role=SimpleNamespace(value="admin"))
    response = Response()
    result = await query_builder.execute_query(
        QueryDSL(table="projects", fields=["id"]), response, object(), user
    )
    assert result["total"] == 7 and response.headers["X-Cache"] == "HIT"
    assert len(audits) == 1 and audits[0]["total"] == 7 and audits[0]["cache_hit"] is True


@pytest.mark.asyncio
async def test_builder_export_database_error_is_sanitized() -> None:
    from app.services.custom_query.query_export import export_builder_query

    class Db:
        def get_bind(self):
            return SimpleNamespace(dialect=sqlite.dialect())

        async def execute(self, statement):
            raise SQLAlchemyError("driver secret: SELECT private_column")

        async def rollback(self):
            return None

    body = QueryDSL(table="projects", fields=["id"])
    user = SimpleNamespace(id=uuid.uuid4())
    with pytest.raises(HTTPException) as exc:
        await export_builder_query(
            body, stmt=select(literal(1)), column_names=["id"],
            scope=BuilderScope(project_ids=None), warnings=[], table_label="项目",
            user=user, db=Db(), batch=10,
        )
    detail = exc.value.detail
    assert detail["error_code"] == "QUERY_EXECUTION_FAILED"
    assert len(detail["correlation_id"]) == 32
    assert "secret" not in str(detail) and "SELECT" not in str(detail)


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_real_postgres_statement_timeout_is_enabled(pg_rollback_session) -> None:
    async with statement_timeout(pg_rollback_session, 4321):
        value = (await pg_rollback_session.execute(
            text("SELECT current_setting('statement_timeout')")
        )).scalar_one()
    assert value == "4321ms"


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_real_postgres_deleted_project_is_forbidden_to_admin(
    pg_rollback_session, monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted = Project(
        id=uuid.uuid4(), name="【测试】高级查询软删门", client_name="【测试】",
        status=ProjectStatus.execution, is_deleted=True,
    )
    pg_rollback_session.add(deleted)
    await pg_rollback_session.flush()
    monkeypatch.setattr(
        "app.services.custom_query.ownership_guard.audit_logger.log_action", AsyncMock(return_value={})
    )
    admin = SimpleNamespace(id=uuid.uuid4(), role=SimpleNamespace(value="admin"))
    with pytest.raises(HTTPException) as exc:
        await ownership_guard.assert_target_accessible(
            user=admin, project_id=deleted.id, db=pg_rollback_session
        )
    assert exc.value.status_code == 403
    assert exc.value.detail["error_code"] == "FORBIDDEN_PROJECT"


@pytest.mark.asyncio
async def test_all_project_scope_and_count_subject_change_when_project_is_deleted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.custom_query import count_token

    async with sqlite_world(monkeypatch) as world:
        admin = (await world.admin_non_member()).user
        before = await resolve_builder_scope(
            user=admin, dsl_tables=("projects",), db=world.db
        )
        project = await world.db.get(Project, TARGET_PROJECT_ID)
        assert project is not None
        project.is_deleted = True
        await world.db.flush()
        after = await resolve_builder_scope(
            user=admin, dsl_tables=("projects",), db=world.db
        )

    before_sig, after_sig = scope_signature(before), scope_signature(after)
    assert before_sig != after_sig
    from app.services.query_cache import compute_cache_key
    assert compute_cache_key("u", f"__query_builder__:{before_sig}", {"table": "projects"}) != compute_cache_key(
        "u", f"__query_builder__:{after_sig}", {"table": "projects"}
    )
    token = count_token.issue(digest="same-sql", total=1, subject=f"u:{before_sig}", now=100)
    assert count_token.reuse(token, digest="same-sql", subject=f"u:{after_sig}", now=101) is None


def test_grouped_query_projection_and_order_are_postgres_safe() -> None:
    stmt, columns = _build_select(QueryDSL(
        table="trial_balance", group_by=["account_category"],
        aggregates=[{"func": "count", "field": "*", "alias": "n"}],
    ))
    assert columns == ["account_category", "n"]
    assert "ORDER BY trial_balance.account_category ASC" in str(stmt)

    invalid = [
        QueryDSL(table="trial_balance", fields=["account_name"], group_by=["account_category"]),
        QueryDSL(table="trial_balance", fields=["account_category"], group_by=["account_category"],
                 order_by=[{"field": "account_name"}]),
        QueryDSL(table="trial_balance", aggregates=[{"func": "count", "field": "*", "alias": "n"}],
                 order_by=[{"field": "account_name"}]),
    ]
    for query in invalid:
        with pytest.raises(HTTPException) as exc:
            _build_select(query)
        assert exc.value.detail["error_code"] == "INVALID_QUERY_SHAPE"


@pytest.mark.asyncio
async def test_builder_success_audit_timeout_does_not_hold_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.redis as redis_module

    never = asyncio.Event()

    async def pending_redis():
        await never.wait()

    class Db:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    monkeypatch.setattr(redis_module, "get_redis", pending_redis)
    monkeypatch.setattr(query_builder, "SUCCESS_AUDIT_TIMEOUT_S", 0.01)
    await asyncio.wait_for(query_builder._audit_query_success(
        QueryDSL(table="projects", fields=["id"]),
        user=SimpleNamespace(id=uuid.uuid4()), scope=BuilderScope(project_ids=frozenset()),
        total=0, cache_hit=False, db=Db(),
    ), timeout=0.2)
