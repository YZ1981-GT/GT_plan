"""V225/R225（原 V217/R217，2026-10-30 同步改号；ProcedureInstance 规范化身份）在随机 PostgreSQL schema 中的真实迁移测试。

测试只创建迁移所需的最小父表（``tests.pg_temp_schema.V217_PARENT_DDL``），所有迁移 SQL 都通过
``MigrationRunner._split_sql_statements`` 拆分执行，并在 finally 中删除临时 schema。
共享库 public 已有同名约束时本测试仍须在临时 schema 里建出约束（V225 按本表判断约束是否存在）。
粗裁确认投影（V218）见 ``test_procedure_trim_confirmation_pg.py``。
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))

from tests.pg_temp_schema import (  # noqa: E402
    MIGRATIONS as _MIGRATIONS,
    V217_PARENT_TABLES,
    constraint_names as _constraint_names,
    create_v217_parents,
    run_sql_file as _run_sql_file,
    sqlstate as _sqlstate,
    table_names as _table_names,
    temporary_schema as _temporary_schema,
)

_V217 = _MIGRATIONS / "V225__procedure_identity_and_trim_confirmation.sql"
_R217 = _MIGRATIONS / "R225__rollback_procedure_identity_and_trim_confirmation.sql"
_INDEX = "uq_procedure_instances_active_identity_norm"
_CHECKS = {
    "ck_procedure_instances_audit_cycle_canonical",
    "ck_procedure_instances_code_canonical",
    "ck_procedure_instances_wp_code_canonical",
}

pytestmark = [pytest.mark.asyncio, pytest.mark.pg_only]

_INSERT = sa.text("""
INSERT INTO procedure_instances (
    id, project_id, audit_cycle, procedure_code, wp_code, is_deleted
) VALUES (
    :id, :project_id, :audit_cycle, :procedure_code, :wp_code, :is_deleted
)
""")


async def _index_catalog(
    conn: AsyncConnection,
) -> dict[str, tuple[bool, str, str | None]]:
    rows = await conn.execute(sa.text("""
        SELECT index_class.relname,
               index_def.indisunique,
               pg_get_indexdef(index_def.indexrelid),
               pg_get_expr(index_def.indpred, index_def.indrelid)
        FROM pg_index AS index_def
        JOIN pg_class AS index_class ON index_class.oid = index_def.indexrelid
        JOIN pg_class AS table_class ON table_class.oid = index_def.indrelid
        JOIN pg_namespace AS ns ON ns.oid = table_class.relnamespace
        WHERE ns.nspname = current_schema()
          AND table_class.relname = 'procedure_instances'
    """))
    return {row[0]: (row[1], row[2], row[3]) for row in rows}


async def _expect_integrity_error(
    conn: AsyncConnection,
    params: dict,
    *,
    sqlstate: str,
    label: str,
) -> None:
    savepoint = await conn.begin_nested()
    try:
        await conn.execute(_INSERT, params)
    except sa.exc.IntegrityError as exc:
        await savepoint.rollback()
        assert _sqlstate(exc) == sqlstate, (
            f"{label} 返回了错误 SQLSTATE: {_sqlstate(exc)}"
        )
    except BaseException:
        await savepoint.rollback()
        raise
    else:
        await savepoint.rollback()
        pytest.fail(f"{label} 未被数据库约束拒绝")


def _row(
    project_id: uuid.UUID,
    *,
    audit_cycle: str,
    procedure_code: str,
    wp_code: str | None,
    is_deleted: bool = False,
    row_id: uuid.UUID | None = None,
) -> dict:
    return {
        "id": row_id or uuid.uuid4(),
        "project_id": project_id,
        "audit_cycle": audit_cycle,
        "procedure_code": procedure_code,
        "wp_code": wp_code,
        "is_deleted": is_deleted,
    }


async def _identity_rows(
    conn: AsyncConnection,
) -> dict[uuid.UUID, tuple[str, str, str | None, bool]]:
    rows = await conn.execute(sa.text("""
        SELECT id, audit_cycle, procedure_code, wp_code, is_deleted
        FROM procedure_instances
    """))
    return {row[0]: (row[1], row[2], row[3], row[4]) for row in rows}


async def _assert_expression_index_rejects_equivalent_active_row(
    conn: AsyncConnection,
    project_id: uuid.UUID,
) -> None:
    """在 SAVEPOINT 内撤下 CHECK，单独证明表达式索引的等价语义。"""
    savepoint = await conn.begin_nested()
    caught: sa.exc.IntegrityError | None = None
    try:
        for constraint in _CHECKS:
            await conn.exec_driver_sql(
                f'ALTER TABLE procedure_instances DROP CONSTRAINT "{constraint}"'
            )
        try:
            await conn.execute(
                _INSERT,
                _row(
                    project_id,
                    audit_cycle=" d ",
                    procedure_code=" d2-1 ",
                    wp_code="IGNORED-BY-IDENTITY",
                ),
            )
        except sa.exc.IntegrityError as exc:
            caught = exc
    finally:
        await savepoint.rollback()

    assert caught is not None, "表达式唯一索引未拒绝大小写/空白等价的 active 行"
    assert _sqlstate(caught) == "23505"
    assert _CHECKS <= await _constraint_names(conn, "procedure_instances")


async def test_v217_normalizes_enforces_identity_and_r217_restores_safely() -> None:
    async with _temporary_schema("tmp_v217_ok") as (engine, _schema):
        project_id = uuid.uuid4()
        canonical = _row(
            project_id,
            audit_cycle="D",
            procedure_code="D2-1",
            wp_code="D2-1",
        )
        restored = _row(
            project_id,
            audit_cycle=" e ",
            procedure_code=" e1 ",
            wp_code=" e1 ",
        )
        manually_changed = _row(
            project_id,
            audit_cycle=" f ",
            procedure_code=" f1 ",
            wp_code=" f1 ",
        )
        deleted_duplicate = _row(
            project_id,
            audit_cycle=" d ",
            procedure_code=" d2-1 ",
            wp_code=" d2-1 ",
            is_deleted=True,
        )

        async with engine.begin() as conn:
            await create_v217_parents(conn)
            await conn.execute(
                _INSERT,
                [canonical, restored, manually_changed, deleted_duplicate],
            )

            assert await _run_sql_file(conn, _V217) > 0
            identities = await _identity_rows(conn)
            assert identities[canonical["id"]] == ("D", "D2-1", "D2-1", False)
            assert identities[restored["id"]] == ("E", "E1", "E1", False)
            assert identities[manually_changed["id"]] == ("F", "F1", "F1", False)
            assert identities[deleted_duplicate["id"]] == (
                "D", "D2-1", "D2-1", True,
            )

            backup_rows = await conn.execute(sa.text("""
                SELECT instance_id, old_audit_cycle, old_procedure_code, old_wp_code
                FROM procedure_instance_identity_v217_backup
            """))
            backups = {
                row[0]: (row[1], row[2], row[3])
                for row in backup_rows
            }
            assert backups == {
                restored["id"]: (" e ", " e1 ", " e1 "),
                manually_changed["id"]: (" f ", " f1 ", " f1 "),
                deleted_duplicate["id"]: (" d ", " d2-1 ", " d2-1 "),
            }

            constraints = await _constraint_names(conn, "procedure_instances")
            assert _CHECKS <= constraints
            indexes = await _index_catalog(conn)
            assert _INDEX in indexes
            is_unique, definition, predicate = indexes[_INDEX]
            assert is_unique is True
            normalized_definition = definition.lower().replace("::text", "")
            assert "upper(btrim((audit_cycle)))" in normalized_definition
            assert "upper(btrim((procedure_code)))" in normalized_definition
            assert predicate is not None and "not is_deleted" in predicate.lower()

            invalid_values = [
                ("audit_cycle 小写", "d", "A-LOWER", "A-LOWER"),
                ("audit_cycle 带空白", " D ", "A-SPACED", "A-SPACED"),
                ("audit_cycle 空码", "", "A-EMPTY", "A-EMPTY"),
                ("procedure_code 小写", "G", "g-lower", "G-LOWER"),
                ("procedure_code 带空白", "G", " G-SPACED ", "G-SPACED"),
                ("procedure_code 空码", "G", "", "G-EMPTY"),
                ("wp_code 小写", "H", "H-LOWER", "h-lower"),
                ("wp_code 带空白", "H", "H-SPACED", " H-SPACED "),
                ("wp_code 空码", "H", "H-EMPTY", ""),
            ]
            for label, audit_cycle, procedure_code, wp_code in invalid_values:
                await _expect_integrity_error(
                    conn,
                    _row(
                        project_id,
                        audit_cycle=audit_cycle,
                        procedure_code=procedure_code,
                        wp_code=wp_code,
                    ),
                    sqlstate="23514",
                    label=label,
                )

            post_migration_soft_delete = _row(
                project_id,
                audit_cycle="D",
                procedure_code="D2-1",
                wp_code="D2-1",
                is_deleted=True,
            )
            await conn.execute(_INSERT, post_migration_soft_delete)
            same_code_count = await conn.scalar(sa.text("""
                SELECT count(*)
                FROM procedure_instances
                WHERE project_id = :project_id
                  AND audit_cycle = 'D'
                  AND procedure_code = 'D2-1'
            """), {"project_id": project_id})
            assert same_code_count == 3

            await _assert_expression_index_rejects_equivalent_active_row(
                conn,
                project_id,
            )

            manual_target = ("F2", "F2-MANUAL", "F2-MANUAL")
            await conn.execute(sa.text("""
                UPDATE procedure_instances
                SET audit_cycle = :audit_cycle,
                    procedure_code = :procedure_code,
                    wp_code = :wp_code
                WHERE id = :id
            """), {
                "id": manually_changed["id"],
                "audit_cycle": manual_target[0],
                "procedure_code": manual_target[1],
                "wp_code": manual_target[2],
            })

            assert await _run_sql_file(conn, _R217) > 0
            after_rollback = await _identity_rows(conn)
            assert after_rollback[restored["id"]] == (" e ", " e1 ", " e1 ", False)
            assert after_rollback[manually_changed["id"]] == (*manual_target, False)
            assert after_rollback[canonical["id"]] == ("D", "D2-1", "D2-1", False)
            assert after_rollback[deleted_duplicate["id"]] == (
                " d ", " d2-1 ", " d2-1 ", True,
            )
            assert len(after_rollback) == 5

            assert await _table_names(conn) == V217_PARENT_TABLES
            assert not (_CHECKS & await _constraint_names(conn, "procedure_instances"))
            assert _INDEX not in await _index_catalog(conn)


async def test_v217_normalization_conflict_is_atomic_and_fail_closed() -> None:
    async with _temporary_schema("tmp_v217_conflict") as (engine, _schema):
        project_id = uuid.uuid4()
        first = _row(
            project_id,
            audit_cycle=" d ",
            procedure_code="d2-1",
            wp_code=" first ",
        )
        second = _row(
            project_id,
            audit_cycle="D",
            procedure_code=" D2-1 ",
            wp_code="SECOND",
        )

        async with engine.begin() as conn:
            await create_v217_parents(conn)
            await conn.execute(_INSERT, [first, second])

        with pytest.raises(sa.exc.DBAPIError) as exc_info:
            async with engine.begin() as conn:
                await _run_sql_file(conn, _V217)

        assert "active normalized procedure identity conflicts" in str(exc_info.value)

        async with engine.connect() as conn:
            assert await conn.scalar(sa.text("SELECT current_schema()")) == _schema
            identities = await _identity_rows(conn)
            assert identities == {
                first["id"]: (" d ", "d2-1", " first ", False),
                second["id"]: ("D", " D2-1 ", "SECOND", False),
            }
            assert await _table_names(conn) == V217_PARENT_TABLES
            assert not (_CHECKS & await _constraint_names(conn, "procedure_instances"))
            indexes = await _index_catalog(conn)
            assert _INDEX not in indexes
            assert {name for name in indexes if not name.endswith("_pkey")} == set()


async def test_v217_unique_index_serializes_concurrent_active_identity() -> None:
    async with _temporary_schema("tmp_v217_race") as (engine, _schema):
        async with engine.begin() as setup:
            await create_v217_parents(setup)
            await _run_sql_file(setup, _V217)

        project_id = uuid.uuid4()
        first_row = _row(project_id, audit_cycle="D", procedure_code="D2-1", wp_code="D2-1")
        second_row = _row(project_id, audit_cycle="D", procedure_code="D2-1", wp_code="D2-1")
        async with engine.connect() as first, engine.connect() as second:
            tx1, tx2 = await first.begin(), await second.begin()
            await first.execute(_INSERT, first_row)
            pending = asyncio.create_task(second.execute(_INSERT, second_row))
            await asyncio.sleep(0.1)
            assert not pending.done(), "第二事务应等待第一事务的唯一身份判定"
            await tx1.commit()
            with pytest.raises(sa.exc.IntegrityError) as exc_info:
                await pending
            assert _sqlstate(exc_info.value) == "23505"
            await tx2.rollback()

        async with engine.connect() as verify:
            count = await verify.scalar(sa.text(
                "SELECT count(*) FROM procedure_instances WHERE project_id = :project_id AND NOT is_deleted"
            ), {"project_id": project_id})
            assert count == 1
