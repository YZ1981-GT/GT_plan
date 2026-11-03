"""附件溯源用例共用的夹具写入与读取（spec formula-hub-integrity-closure 任务 3；不被 pytest 收集）。

``attachment_lineage`` 一律用原生 SQL 写读：用例要在列被删掉的状态下写入（模拟迁移前 / 旧代码），而 ORM 模型
（任务 4 起）映射了 ``project_id``，列不存在时 ORM 写读必报错。项目名带「【测试】」，全部写入都在调用方的事务里。
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.core.migration_runner import MigrationRunner
from app.models.attachment_models import Attachment
from app.models.core import Project
from tests.formula_hub._pg_harness import (
    DISPOSABLE_DB_ENV,
    SNAPSHOT_PREFIX,
    TEST_PROJECT_PREFIX,
    database_name,
    database_url,
    is_disposable_database,
)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
V227 = MIGRATIONS_DIR / "V227__attachment_lineage_project_id.sql"
R227 = MIGRATIONS_DIR / "R227__rollback_attachment_lineage_project_id.sql"
INDEX_NAME = "idx_attachment_lineage_project_target"


def assert_ddl_allowed() -> None:
    """回滚事务里的 DDL（R227 删列、重放 V227）只在快照库上做：共享库上 ALTER 的排他锁会挡住开发服（ADR-FHIC-25）。"""
    name = database_name(database_url())
    if not is_disposable_database(name):
        pytest.fail(f"含 DDL 的用例只连快照库（库名以 {SNAPSHOT_PREFIX} 开头，或由 {DISPOSABLE_DB_ENV} 点名的一次性库），"
                    f"当前库名 {name or '未知'}", pytrace=False)


async def make_project(session, label: str) -> uuid.UUID:
    tag = uuid.uuid4().hex[:10]
    project = Project(name=f"{TEST_PROJECT_PREFIX}fh_{label}_{tag}", client_name=f"{TEST_PROJECT_PREFIX}附件溯源")
    session.add(project)
    await session.flush()
    return project.id


async def make_attachment(session, project_id: uuid.UUID) -> uuid.UUID:
    attachment = Attachment(project_id=project_id, file_name=f"fh_{uuid.uuid4().hex[:8]}.pdf",
                            file_path=f"/tmp/fh_{uuid.uuid4().hex[:8]}.pdf", file_type="pdf", file_size=1024)
    session.add(attachment)
    await session.flush()
    return attachment.id


async def insert_lineage(session, *, attachment_id: uuid.UUID, target_ref: str, target_type: str = "wp_cell",
                         project_id: uuid.UUID | None = None, project_column: bool = True) -> uuid.UUID:
    """插入一行关联；``project_column=False`` 表示列已被删掉（迁移前 / 旧代码的写法）。"""
    lineage_id = uuid.uuid4()
    params: dict[str, Any] = {"id": lineage_id, "aid": attachment_id, "t": target_type, "ref": target_ref}
    if project_column:
        params["pid"] = project_id
        sql = ("INSERT INTO attachment_lineage (id, attachment_id, target_type, target_ref, project_id) "
               "VALUES (:id, :aid, :t, :ref, :pid)")
    else:
        sql = ("INSERT INTO attachment_lineage (id, attachment_id, target_type, target_ref) "
               "VALUES (:id, :aid, :t, :ref)")
    await session.execute(text(sql), params)
    return lineage_id


async def lineage_state(session, ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
    """这些关联行的整行原文（``row_to_json``），已不存在的行不出现在结果里。"""
    rows = (await session.execute(
        text("SELECT al.id, row_to_json(al)::text AS original FROM attachment_lineage al WHERE al.id = ANY(:ids)"),
        {"ids": ids})).all()
    return {row.id: json.loads(row.original) for row in rows}


async def project_column(session) -> tuple[str, str] | None:
    """``attachment_lineage.project_id`` 的（类型, 可空）；列不存在 ⇒ None。"""
    row = (await session.execute(text(
        "SELECT data_type, is_nullable FROM information_schema.columns WHERE table_schema = current_schema() "
        "AND table_name = 'attachment_lineage' AND column_name = 'project_id'"))).first()
    return (row[0], row[1]) if row else None


async def index_columns(session) -> list[str] | None:
    """索引 ``idx_attachment_lineage_project_target`` 的列（按索引定义里的顺序）；索引不存在 ⇒ None。"""
    rows = (await session.execute(text(
        "SELECT indexdef FROM pg_indexes WHERE schemaname = current_schema() "
        "AND tablename = 'attachment_lineage' AND indexname = :name"), {"name": INDEX_NAME})).scalars().all()
    if not rows:
        return None
    (definition,) = rows
    match = re.search(r"\(([^()]*)\)\s*$", definition)
    assert match, definition
    return [column.strip() for column in match.group(1).split(",")]


async def replay(session, path: Path) -> int:
    """按 MigrationRunner 的分句与执行方式（``exec_driver_sql``）在会话的事务里重放一个迁移文件，返回语句数。"""
    assert_ddl_allowed()
    statements = MigrationRunner._split_sql_statements(path.read_text(encoding="utf-8"))
    conn = await session.connection()
    for statement in statements:
        await conn.exec_driver_sql(statement)
    return len(statements)
