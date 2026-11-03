"""V224/R224（原 V216/R216，2026-10-30 同步改号）在随机 PostgreSQL schema 中的真实迁移契约测试。

测试只在临时 schema 中创建最小父表，并以 MigrationRunner 的生产拆句逻辑
执行迁移；无论成功或失败都在 finally 中强制删除该 schema。
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))

_MIGRATIONS = _BACKEND / "migrations"
_V216 = _MIGRATIONS / "V224__workpaper_generation_operations.sql"
_R216 = _MIGRATIONS / "R224__rollback_workpaper_generation_operations.sql"
_TARGET_TABLES = {
    "workpaper_generation_operations",
    "workpaper_generation_items",
}
_PARENT_TABLES = {"projects", "users", "wp_template_set"}
_ACTIVE_STATUSES = {"prepared", "materializing", "materialized", "finalizing"}
_EXPECTED_INDEXES = {
    "ix_wp_generation_operations_project_status": (False, ("project_id", "status", "created_at")),
    "ix_wp_generation_operations_lease": (False, ("status", "lease_expires_at")),
    "uq_wp_generation_items_operation_code": (True, ("operation_id", "wp_code")),
    "uq_wp_generation_items_operation_ordinal": (True, ("operation_id", "ordinal")),
    "ix_wp_generation_items_operation_status": (False, ("operation_id", "status", "ordinal")),
}

pytestmark = pytest.mark.asyncio

_EXPECTED_CONSTRAINTS = {
    "workpaper_generation_operations": {
        "workpaper_generation_operations_pkey",
        "workpaper_generation_operations_project_id_fkey",
        "workpaper_generation_operations_actor_user_id_fkey",
        "workpaper_generation_operations_template_set_id_fkey",
        "ck_wp_generation_operations_kind",
        "ck_wp_generation_operations_failure_policy",
        "ck_wp_generation_operations_status",
        "ck_wp_generation_operations_kind_policy",
        "ck_wp_generation_operations_progress",
        "ck_wp_generation_operations_lease_pair",
    },
    "workpaper_generation_items": {
        "workpaper_generation_items_pkey",
        "workpaper_generation_items_operation_id_fkey",
        "ck_wp_generation_items_status",
        "ck_wp_generation_items_ordinal",
    },
}

_OPERATION_INSERT = sa.text("""
    INSERT INTO workpaper_generation_operations (
        id, project_id, year, actor_user_id, kind, failure_policy,
        request_hash, scope_revision, status, lease_token, lease_expires_at,
        attempt, progress_total, progress_done
    ) VALUES (
        :id, :project_id, 2026, :actor_user_id, :kind, :failure_policy,
        :request_hash, :scope_revision, :status, :lease_token, :lease_expires_at,
        :attempt, :progress_total, :progress_done
    )
""")
_ITEM_INSERT = sa.text("""
    INSERT INTO workpaper_generation_items (
        id, operation_id, ordinal, wp_code, wp_name, wp_index_id, wp_id, status
    ) VALUES (
        :id, :operation_id, :ordinal, :wp_code, :wp_name, :wp_index_id, :wp_id, :status
    )
""")


async def _run_sql_file(conn, path: Path) -> int:
    from app.core.migration_runner import MigrationRunner

    statements = MigrationRunner._split_sql_statements(path.read_text(encoding="utf-8"))
    for statement in statements:
        await conn.exec_driver_sql(statement)
    return len(statements)


async def _table_names(conn) -> set[str]:
    rows = await conn.execute(sa.text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'"
    ))
    return {row[0] for row in rows}


async def _constraint_names(conn, table: str) -> set[str]:
    rows = await conn.execute(sa.text("""
        SELECT constraint_def.conname
        FROM pg_constraint AS constraint_def
        JOIN pg_class AS table_class ON table_class.oid = constraint_def.conrelid
        JOIN pg_namespace AS ns ON ns.oid = table_class.relnamespace
        WHERE ns.nspname = current_schema()
          AND table_class.relname = :table
          AND constraint_def.contype IN ('p', 'f', 'c')
    """), {"table": table})
    return {row[0] for row in rows}


async def _index_catalog(conn) -> dict[str, tuple[bool, str, str | None]]:
    rows = await conn.execute(sa.text("""
        SELECT index_class.relname,
               idx.indisunique,
               pg_get_indexdef(idx.indexrelid),
               pg_get_expr(idx.indpred, idx.indrelid)
        FROM pg_index AS idx
        JOIN pg_class AS index_class ON index_class.oid = idx.indexrelid
        JOIN pg_class AS table_class ON table_class.oid = idx.indrelid
        JOIN pg_namespace AS ns ON ns.oid = table_class.relnamespace
        WHERE ns.nspname = current_schema()
          AND table_class.relname IN (
              'workpaper_generation_operations', 'workpaper_generation_items'
          )
    """))
    return {row[0]: (row[1], row[2], row[3]) for row in rows}


def _operation_params(project_id: uuid.UUID, user_id: uuid.UUID, **overrides):
    params = {
        "id": uuid.uuid4(),
        "project_id": project_id,
        "actor_user_id": user_id,
        "kind": "from_codes",
        "failure_policy": "per_item",
        "request_hash": "a" * 64,
        "scope_revision": "b" * 64,
        "status": "prepared",
        "lease_token": None,
        "lease_expires_at": None,
        "attempt": 0,
        "progress_total": 1,
        "progress_done": 0,
    }
    params.update(overrides)
    return params


def _item_params(operation_id: uuid.UUID, **overrides):
    params = {
        "id": uuid.uuid4(),
        "operation_id": operation_id,
        "ordinal": 0,
        "wp_code": "D1",
        "wp_name": "应收票据",
        "wp_index_id": uuid.uuid4(),
        "wp_id": uuid.uuid4(),
        "status": "prepared",
    }
    params.update(overrides)
    return params


def _sqlstate(exc: sa.exc.IntegrityError) -> str | None:
    candidates = (exc.orig, getattr(exc.orig, "__cause__", None))
    for candidate in candidates:
        state = getattr(candidate, "sqlstate", None) or getattr(candidate, "pgcode", None)
        if state:
            return str(state)
    return None


async def _expect_integrity_error(
    conn,
    statement,
    params: dict,
    *,
    sqlstate: str,
    label: str,
) -> None:
    savepoint = await conn.begin_nested()
    try:
        await conn.execute(statement, params)
    except sa.exc.IntegrityError as exc:
        await savepoint.rollback()
        assert _sqlstate(exc) == sqlstate, f"{label} 返回了错误 SQLSTATE: {_sqlstate(exc)}"
    except BaseException:
        await savepoint.rollback()
        raise
    else:
        await savepoint.rollback()
        pytest.fail(f"{label} 未被数据库约束拒绝")


def _assert_indexes(indexes: dict[str, tuple[bool, str, str | None]]) -> None:
    explicit = {name: value for name, value in indexes.items() if not name.endswith("_pkey")}
    assert set(explicit) == set(_EXPECTED_INDEXES), f"显式索引不一致: {set(explicit)}"
    for name, (expected_unique, expected_columns) in _EXPECTED_INDEXES.items():
        is_unique, definition, predicate = explicit[name]
        assert is_unique is expected_unique
        assert f"({', '.join(expected_columns)})" in definition
        if name != "ix_wp_generation_operations_lease":
            assert predicate is None

    lease_predicate = explicit["ix_wp_generation_operations_lease"][2]
    assert lease_predicate is not None
    assert "status" in lease_predicate
    for status in _ACTIVE_STATUSES:
        assert f"'{status}'" in lease_predicate
    for status in {"succeeded", "partial_failed", "failed", "stale"}:
        assert f"'{status}'" not in lease_predicate


async def test_v216_r216_in_isolated_postgres_schema() -> None:
    from app.core.config import settings as app_settings

    if make_url(app_settings.DATABASE_URL).get_backend_name() != "postgresql":
        pytest.skip("V224/R224 真实约束测试需要 PostgreSQL")

    connect_args = {"ssl": False} if app_settings.DB_DISABLE_SSL else {}
    admin_engine = create_async_engine(
        app_settings.DATABASE_URL,
        poolclass=NullPool,
        connect_args=connect_args,
    )
    schema = f"tmp_v216_{uuid.uuid4().hex[:12]}"
    scoped_engine = None

    try:
        async with admin_engine.begin() as admin:
            await admin.exec_driver_sql(f'CREATE SCHEMA "{schema}"')

        scoped_engine = create_async_engine(
            app_settings.DATABASE_URL,
            poolclass=NullPool,
            connect_args={
                **connect_args,
                "server_settings": {"search_path": schema},
            },
        )
        async with scoped_engine.begin() as conn:
            assert await conn.scalar(sa.text("SELECT current_schema()")) == schema
            await conn.exec_driver_sql("CREATE TABLE projects (id UUID PRIMARY KEY)")
            await conn.exec_driver_sql("CREATE TABLE users (id UUID PRIMARY KEY)")
            await conn.exec_driver_sql("CREATE TABLE wp_template_set (id UUID PRIMARY KEY)")
            assert await _table_names(conn) == _PARENT_TABLES

            v216_statements = await _run_sql_file(conn, _V216)
            assert v216_statements > 0
            assert await _table_names(conn) == _PARENT_TABLES | _TARGET_TABLES
            for table, expected in _EXPECTED_CONSTRAINTS.items():
                assert await _constraint_names(conn, table) == expected

            indexes = await _index_catalog(conn)
            assert set(indexes) == set(_EXPECTED_INDEXES) | {
                "workpaper_generation_operations_pkey",
                "workpaper_generation_items_pkey",
            }
            _assert_indexes(indexes)

            project_id, user_id, template_set_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            await conn.execute(
                sa.text("INSERT INTO projects (id) VALUES (:id)"),
                {"id": project_id},
            )
            await conn.execute(
                sa.text("INSERT INTO users (id) VALUES (:id)"),
                {"id": user_id},
            )
            await conn.execute(
                sa.text("INSERT INTO wp_template_set (id) VALUES (:id)"),
                {"id": template_set_id},
            )

            operation_id = uuid.uuid4()
            await conn.execute(sa.text("""
                INSERT INTO workpaper_generation_operations (
                    id, project_id, year, actor_user_id, kind, failure_policy,
                    request_hash, scope_revision
                ) VALUES (
                    :id, :project_id, 2026, :actor_user_id, 'from_codes', 'per_item',
                    :request_hash, :scope_revision
                )
            """), {
                "id": operation_id,
                "project_id": project_id,
                "actor_user_id": user_id,
                "request_hash": "c" * 64,
                "scope_revision": "d" * 64,
            })
            item = _item_params(operation_id)
            await conn.execute(_ITEM_INSERT, item)

            legal = (await conn.execute(sa.text("""
                SELECT op.status, op.request_payload, op.attempt,
                       op.progress_total, op.progress_done,
                       item.status, item.from_template
                FROM workpaper_generation_operations AS op
                JOIN workpaper_generation_items AS item ON item.operation_id = op.id
                WHERE op.id = :operation_id
            """), {"operation_id": operation_id})).one()
            assert tuple(legal) == ("prepared", {}, 0, 0, 0, "prepared", False)

            invalid_operations = [
                ("非法 status", {"status": "queued"}),
                ("非法 kind-policy", {"kind": "template_set", "failure_policy": "per_item"}),
                ("非法 progress", {"progress_total": 1, "progress_done": 2}),
                ("负数 progress", {"attempt": -1}),
                (
                    "缺 lease_expires_at",
                    {"lease_token": uuid.uuid4(), "lease_expires_at": None},
                ),
                (
                    "缺 lease_token",
                    {
                        "lease_token": None,
                        "lease_expires_at": datetime(2099, 1, 1, tzinfo=timezone.utc),
                    },
                ),
            ]
            for label, overrides in invalid_operations:
                await _expect_integrity_error(
                    conn,
                    _OPERATION_INSERT,
                    _operation_params(project_id, user_id, **overrides),
                    sqlstate="23514",
                    label=label,
                )

            await _expect_integrity_error(
                conn,
                _ITEM_INSERT,
                _item_params(operation_id, ordinal=1, wp_code="BAD", status="queued"),
                sqlstate="23514",
                label="非法 item status",
            )
            await _expect_integrity_error(
                conn,
                _ITEM_INSERT,
                _item_params(operation_id, ordinal=-1, wp_code="NEG"),
                sqlstate="23514",
                label="非法 item ordinal",
            )
            await _expect_integrity_error(
                conn,
                _ITEM_INSERT,
                _item_params(operation_id, ordinal=1, wp_code=item["wp_code"]),
                sqlstate="23505",
                label="同 operation 的 item code 重复",
            )
            await _expect_integrity_error(
                conn,
                _ITEM_INSERT,
                _item_params(operation_id, ordinal=item["ordinal"], wp_code="D2"),
                sqlstate="23505",
                label="同 operation 的 item ordinal 重复",
            )

            assert await conn.scalar(sa.text(
                "SELECT count(*) FROM workpaper_generation_items "
                "WHERE operation_id = :operation_id"
            ), {"operation_id": operation_id}) == 1
            await conn.execute(sa.text(
                "DELETE FROM workpaper_generation_operations WHERE id = :operation_id"
            ), {"operation_id": operation_id})
            assert await conn.scalar(sa.text(
                "SELECT count(*) FROM workpaper_generation_items "
                "WHERE operation_id = :operation_id"
            ), {"operation_id": operation_id}) == 0

            r216_statements_1 = await _run_sql_file(conn, _R216)
            assert r216_statements_1 > 0
            assert await _table_names(conn) == _PARENT_TABLES
            assert not (set(await _index_catalog(conn)) & set(_EXPECTED_INDEXES))

            r216_statements_2 = await _run_sql_file(conn, _R216)
            assert r216_statements_2 == r216_statements_1
            assert await _table_names(conn) == _PARENT_TABLES
            parent_rows = {
                table: await conn.scalar(sa.text(f'SELECT count(*) FROM "{table}"'))
                for table in _PARENT_TABLES
            }
            assert parent_rows == {table: 1 for table in _PARENT_TABLES}
    finally:
        if scoped_engine is not None:
            await scoped_engine.dispose()
        try:
            async with admin_engine.begin() as admin:
                await admin.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                schema_left = await admin.scalar(
                    sa.text("SELECT count(*) FROM pg_namespace WHERE nspname = :schema"),
                    {"schema": schema},
                )
                assert schema_left == 0
        finally:
            await admin_engine.dispose()
