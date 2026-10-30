"""V224（原 V216，2026-10-30 同步改号）底稿生成 operation/item 的 ORM 与 SQL 文本契约。

SQLite 部分只验证 ORM 字段、默认值和普通 CHECK/UNIQUE 行为；PostgreSQL 的
JSONB、TIMESTAMPTZ、ON DELETE 与部分索引谓词仅做 ORM/迁移文本对拍，本文件不声称
在 SQLite 上执行或验证了这些 PostgreSQL 能力，也不连接共享数据库。
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.wp_generation_models import (
    ACTIVE_OPERATION_STATUSES,
    FAILURE_POLICIES,
    ITEM_STATUSES,
    OPERATION_KINDS,
    OPERATION_STATUSES,
    WorkpaperGenerationItem,
    WorkpaperGenerationOperation,
)

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
V216 = MIGRATIONS / "V224__workpaper_generation_operations.sql"
R216 = MIGRATIONS / "R224__rollback_workpaper_generation_operations.sql"

_OPERATION_COLUMNS = {
    "id", "project_id", "year", "actor_user_id", "kind", "template_set_id",
    "failure_policy", "request_payload", "request_hash", "scope_revision", "status",
    "lease_token", "lease_expires_at", "attempt", "progress_total", "progress_done",
    "receipt", "public_error", "created_at", "updated_at", "started_at", "finished_at",
}
_ITEM_COLUMNS = {
    "id", "operation_id", "ordinal", "wp_code", "wp_name", "audit_cycle",
    "wp_index_id", "wp_id", "template_source", "template_fingerprint", "staging_path",
    "final_path", "file_sha256", "from_template", "header_prepared", "header_issue",
    "status", "error",
}
_CONSTRAINT_HEADS = {"constraint", "primary", "unique", "foreign", "check", "exclude", "key"}


def _without_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _create_body(table: str) -> str:
    sql = _without_comments(V216.read_text(encoding="utf-8"))
    match = re.search(
        rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{table}\s*\(",
        sql,
        re.IGNORECASE,
    )
    assert match, f"V224 未找到 CREATE TABLE IF NOT EXISTS {table}"
    start = match.end() - 1
    depth = 0
    for index in range(start, len(sql)):
        if sql[index] == "(":
            depth += 1
        elif sql[index] == ")":
            depth -= 1
            if depth == 0:
                return sql[start + 1:index]
    raise AssertionError(f"{table} 建表括号未闭合")


def _segments(body: str) -> list[str]:
    segments: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(body):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            segments.append(body[start:index].strip())
            start = index + 1
    segments.append(body[start:].strip())
    return [segment for segment in segments if segment]


def _ddl_columns(table: str) -> dict[str, bool]:
    columns: dict[str, bool] = {}
    for segment in _segments(_create_body(table)):
        head = re.match(r'"?([A-Za-z_][A-Za-z0-9_]*)"?', segment)
        if not head or head.group(1).lower() in _CONSTRAINT_HEADS:
            continue
        upper = segment.upper()
        columns[head.group(1)] = "NOT NULL" in upper or "PRIMARY KEY" in upper
    return columns


def _ddl_check_values(table: str, column: str) -> set[str]:
    match = re.search(
        rf"CHECK\s*\(\s*{column}\s+IN\s*\((.*?)\)\s*\)",
        _create_body(table),
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"V224 缺 {table}.{column} 的 CHECK IN"
    return set(re.findall(r"'([^']*)'", match.group(1)))


def _orm_check_values(model: type, name: str) -> set[str]:
    for constraint in model.__table__.constraints:
        if isinstance(constraint, sa.CheckConstraint) and constraint.name == name:
            return set(re.findall(r"'([^']*)'", str(constraint.sqltext)))
    raise AssertionError(f"ORM {model.__name__} 缺 CHECK {name}")


def _index_statement(name: str) -> str:
    sql = _without_comments(V216.read_text(encoding="utf-8"))
    match = re.search(
        rf"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+{name}\b.*?;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"V224 缺索引 {name}"
    return re.sub(r"\s+", " ", match.group(0)).strip()


def _foreign_key(model: type, column: str) -> tuple[str, str | None]:
    keys = list(model.__table__.c[column].foreign_keys)
    assert len(keys) == 1, f"{model.__name__}.{column} 应恰有一个外键"
    return keys[0].target_fullname, keys[0].ondelete


def test_v216_r216_pair_version_and_rollback_order() -> None:
    assert V216.is_file() and R216.is_file()
    same_version = sorted(
        path.name for path in MIGRATIONS.glob("V*.sql")
        if re.match(r"^V0*224__", path.name)
    )
    assert same_version == [V216.name], f"V224 版本号撞号: {same_version}"
    rollback = _without_comments(R216.read_text(encoding="utf-8"))
    drops = re.findall(r"DROP\s+TABLE\s+IF\s+EXISTS\s+(\w+)", rollback, re.IGNORECASE)
    assert drops == ["workpaper_generation_items", "workpaper_generation_operations"]


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        (WorkpaperGenerationOperation, _OPERATION_COLUMNS),
        (WorkpaperGenerationItem, _ITEM_COLUMNS),
    ],
    ids=["operations", "items"],
)
def test_orm_columns_and_nullability_match_v216(model: type, expected: set[str]) -> None:
    ddl = _ddl_columns(model.__tablename__)
    orm = {column.name: not column.nullable for column in model.__table__.columns}
    assert set(ddl) == set(orm) == expected
    mismatches = {name: (ddl[name], orm[name]) for name in ddl if ddl[name] != orm[name]}
    assert not mismatches, f"DDL/ORM 可空性不一致: {mismatches}"
    assert not (_CONSTRAINT_HEADS & {name.lower() for name in ddl})


def test_uuid_jsonb_text_types_and_metadata_registration() -> None:
    operation = WorkpaperGenerationOperation.__table__.c
    item = WorkpaperGenerationItem.__table__.c
    for column in (
        operation.id, operation.project_id, operation.actor_user_id,
        operation.template_set_id, operation.lease_token,
        item.id, item.operation_id, item.wp_index_id, item.wp_id,
    ):
        assert isinstance(column.type, PG_UUID), column.name
    for column in (operation.request_payload, operation.receipt, item.template_source):
        assert isinstance(column.type, JSONB), column.name
    for column in (
        operation.public_error, item.wp_name, item.staging_path,
        item.final_path, item.error,
    ):
        assert isinstance(column.type, sa.Text), column.name
    assert isinstance(operation.request_hash.type, sa.CHAR)
    assert isinstance(operation.scope_revision.type, sa.CHAR)
    assert isinstance(item.template_fingerprint.type, sa.CHAR)
    assert isinstance(item.file_sha256.type, sa.CHAR)
    assert (
        Base.metadata.tables[WorkpaperGenerationOperation.__tablename__]
        is WorkpaperGenerationOperation.__table__
    )
    assert (
        Base.metadata.tables[WorkpaperGenerationItem.__tablename__]
        is WorkpaperGenerationItem.__table__
    )


def test_status_kind_and_failure_policy_checks_match_all_layers() -> None:
    assert "materialized" in OPERATION_STATUSES
    assert _ddl_check_values("workpaper_generation_operations", "status") == set(OPERATION_STATUSES)
    assert _orm_check_values(WorkpaperGenerationOperation, "ck_wp_generation_operations_status") == set(OPERATION_STATUSES)
    assert _ddl_check_values("workpaper_generation_operations", "kind") == set(OPERATION_KINDS)
    assert _orm_check_values(WorkpaperGenerationOperation, "ck_wp_generation_operations_kind") == set(OPERATION_KINDS)
    assert _ddl_check_values("workpaper_generation_operations", "failure_policy") == set(FAILURE_POLICIES)
    assert _orm_check_values(
        WorkpaperGenerationOperation,
        "ck_wp_generation_operations_failure_policy",
    ) == set(FAILURE_POLICIES)
    assert _ddl_check_values("workpaper_generation_items", "status") == set(ITEM_STATUSES)
    assert _orm_check_values(WorkpaperGenerationItem, "ck_wp_generation_items_status") == set(ITEM_STATUSES)


def test_foreign_keys_match_v216_contract() -> None:
    assert _foreign_key(WorkpaperGenerationOperation, "project_id") == (
        "projects.id", "CASCADE",
    )
    assert _foreign_key(WorkpaperGenerationOperation, "actor_user_id") == (
        "users.id", "RESTRICT",
    )
    assert _foreign_key(WorkpaperGenerationOperation, "template_set_id") == (
        "wp_template_set.id", "SET NULL",
    )
    assert _foreign_key(WorkpaperGenerationItem, "operation_id") == (
        "workpaper_generation_operations.id", "CASCADE",
    )
    assert not WorkpaperGenerationItem.__table__.c.wp_index_id.foreign_keys
    assert not WorkpaperGenerationItem.__table__.c.wp_id.foreign_keys

    sql = re.sub(r"\s+", " ", _without_comments(V216.read_text(encoding="utf-8")))
    expected = (
        r"project_id UUID NOT NULL REFERENCES projects\(id\) ON DELETE CASCADE",
        r"actor_user_id UUID NOT NULL REFERENCES users\(id\) ON DELETE RESTRICT",
        r"template_set_id UUID REFERENCES wp_template_set\(id\) ON DELETE SET NULL",
        r"operation_id UUID NOT NULL REFERENCES workpaper_generation_operations\(id\) ON DELETE CASCADE",
    )
    for pattern in expected:
        assert re.search(pattern, sql, re.IGNORECASE), pattern


def test_unique_and_query_indexes_match_orm_and_v216() -> None:
    expected = {
        "ix_wp_generation_operations_project_status": (False, ("project_id", "status", "created_at")),
        "ix_wp_generation_operations_lease": (False, ("status", "lease_expires_at")),
        "uq_wp_generation_items_operation_code": (True, ("operation_id", "wp_code")),
        "uq_wp_generation_items_operation_ordinal": (True, ("operation_id", "ordinal")),
        "ix_wp_generation_items_operation_status": (False, ("operation_id", "status", "ordinal")),
    }
    indexes = {
        index.name: (bool(index.unique), tuple(column.name for column in index.columns))
        for model in (WorkpaperGenerationOperation, WorkpaperGenerationItem)
        for index in model.__table__.indexes
    }
    assert indexes == expected
    for name, (unique, columns) in expected.items():
        statement = _index_statement(name)
        assert ("CREATE UNIQUE INDEX" in statement.upper()) is unique
        column_pattern = r"\(\s*" + r"\s*,\s*".join(columns) + r"\s*\)"
        assert re.search(column_pattern, statement, re.IGNORECASE)

    lease_index = next(
        index for index in WorkpaperGenerationOperation.__table__.indexes
        if index.name == "ix_wp_generation_operations_lease"
    )
    orm_predicate = str(lease_index.dialect_options["postgresql"]["where"])
    assert set(re.findall(r"'([^']*)'", orm_predicate)) == set(ACTIVE_OPERATION_STATUSES)
    ddl_predicate = _index_statement("ix_wp_generation_operations_lease")
    assert set(re.findall(r"'([^']*)'", ddl_predicate)) == set(ACTIVE_OPERATION_STATUSES)
    assert " WHERE status IN " in ddl_predicate


def test_v216_defaults_and_idempotent_ddl_text() -> None:
    sql = _without_comments(V216.read_text(encoding="utf-8"))
    assert len(re.findall(r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS", sql, re.IGNORECASE)) == 2
    assert len(re.findall(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS", sql, re.IGNORECASE)) == 5
    normalized = re.sub(r"\s+", " ", sql)
    for fragment in (
        "request_payload JSONB NOT NULL DEFAULT '{}'::jsonb",
        "status VARCHAR(32) NOT NULL DEFAULT 'prepared'",
        "attempt INTEGER NOT NULL DEFAULT 0",
        "progress_total INTEGER NOT NULL DEFAULT 0",
        "progress_done INTEGER NOT NULL DEFAULT 0",
        "from_template BOOLEAN NOT NULL DEFAULT false",
        "header_prepared BOOLEAN NOT NULL DEFAULT false",
    ):
        assert fragment in normalized

    operation = WorkpaperGenerationOperation.__table__.c
    item = WorkpaperGenerationItem.__table__.c
    assert str(operation.status.server_default.arg) == "'prepared'"
    assert str(item.status.server_default.arg) == "'prepared'"
    assert str(operation.request_payload.server_default.arg) == "'{}'"
    assert str(operation.attempt.server_default.arg) == "0"
    assert str(operation.progress_total.server_default.arg) == "0"
    assert str(operation.progress_done.server_default.arg) == "0"
    assert str(item.from_template.server_default.arg).lower() == "false"
    assert str(item.header_prepared.server_default.arg).lower() == "false"


@pytest.fixture
def sqlite_engine():
    """只建本任务两张 ORM 表；SQLite 默认不启用外键，外键语义由文本契约验证。"""
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            WorkpaperGenerationOperation.__table__,
            WorkpaperGenerationItem.__table__,
        ],
    )
    try:
        yield engine
    finally:
        engine.dispose()


def _operation(**overrides: object) -> WorkpaperGenerationOperation:
    values: dict[str, object] = {
        "project_id": uuid.uuid4(),
        "year": 2025,
        "actor_user_id": uuid.uuid4(),
        "kind": "from_codes",
        "failure_policy": "per_item",
        "request_hash": "a" * 64,
        "scope_revision": "b" * 64,
    }
    values.update(overrides)
    return WorkpaperGenerationOperation(**values)


def _item(operation_id: uuid.UUID, **overrides: object) -> WorkpaperGenerationItem:
    values: dict[str, object] = {
        "operation_id": operation_id,
        "ordinal": 0,
        "wp_code": "D2-1",
        "wp_name": "应收账款审定表",
        "audit_cycle": "D",
        "wp_index_id": uuid.uuid4(),
        "wp_id": uuid.uuid4(),
    }
    values.update(overrides)
    return WorkpaperGenerationItem(**values)


def test_sqlite_orm_defaults_and_field_roundtrip(sqlite_engine) -> None:
    with Session(sqlite_engine) as session:
        operation = _operation()
        session.add(operation)
        session.flush()
        item = _item(operation.id)
        session.add(item)
        session.commit()
        session.refresh(operation)
        session.refresh(item)

        assert isinstance(operation.id, uuid.UUID)
        assert operation.status == "prepared"
        assert operation.request_payload == {}
        assert (operation.attempt, operation.progress_total, operation.progress_done) == (0, 0, 0)
        assert operation.created_at is not None and operation.updated_at is not None
        assert isinstance(item.id, uuid.UUID)
        assert item.status == "prepared"
        assert item.from_template is False
        assert item.header_prepared is False
        assert item.header_issue is None
        assert item.wp_code == "D2-1"
        assert item.wp_name == "应收账款审定表"
        assert item.audit_cycle == "D"


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "unknown"},
        {"failure_policy": "best_effort"},
        {"status": "unknown"},
        {"kind": "template_set", "failure_policy": "per_item"},
        {"attempt": -1},
        {"progress_total": 0, "progress_done": 1},
        {"lease_token": uuid.uuid4()},
    ],
)
def test_sqlite_operation_checks_reject_invalid_rows(sqlite_engine, overrides: dict[str, object]) -> None:
    with Session(sqlite_engine) as session:
        session.add(_operation(**overrides))
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "unknown"},
        {"ordinal": -1},
    ],
)
def test_sqlite_item_checks_reject_invalid_rows(sqlite_engine, overrides: dict[str, object]) -> None:
    with Session(sqlite_engine) as session:
        operation = _operation()
        session.add(operation)
        session.flush()
        session.add(_item(operation.id, **overrides))
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize(
    "second_overrides",
    [
        {"ordinal": 1, "wp_code": "D2-1"},
        {"ordinal": 0, "wp_code": "D2-2"},
    ],
)
def test_sqlite_item_unique_indexes_reject_duplicates(
    sqlite_engine,
    second_overrides: dict[str, object],
) -> None:
    with Session(sqlite_engine) as session:
        operation = _operation()
        session.add(operation)
        session.flush()
        session.add(_item(operation.id))
        session.commit()

        session.add(_item(operation.id, **second_overrides))
        with pytest.raises(IntegrityError):
            session.commit()
