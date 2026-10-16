"""真实 PostgreSQL 守卫：V188 放宽 note_section_instances.section_number（disclosure-note-template-word-realignment Phase 3）。

SQLite 不校验 VARCHAR 长度 ⇒ 「裁剪页初始化写不进 42 字编号」只在 PostgreSQL 上出现。这里在 scratch schema
（``tmp_v188_*``，search_path 只含自己）里建一张 **V188 之前**（VARCHAR(20)）的表副本，用真服务
``NoteTrimService._init_from_sections`` 写国企合并口径全部种子章节：

- V188 之前 ⇒ 22001（value too long），且一行都没写进去；
- V188 原文（MigrationRunner 同一分句器）跑两遍 ⇒ 不限长、第二遍无副作用；之后同一批章节整批写入；
- R188 遇到超长行 ⇒ 报错拒绝回滚、列宽不变；删掉超长行后 R188 恢复 VARCHAR(20)，再跑 V188 又放宽。

public **只读**：只查本列的列宽与 schema_version 是否已记 188（开发服务器热重载不跑迁移，漏跑时这里红）。
结束 ``DROP SCHEMA CASCADE`` 并复查。``DATABASE_URL`` 非 PostgreSQL 时直接失败不 skip。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

MIGRATIONS = _BACKEND / "migrations"
V188 = MIGRATIONS / "V188__note_section_instances_section_number_unbounded.sql"
R188 = MIGRATIONS / "R188__note_section_instances_section_number_unbounded.sql"
_WIDTH_SQL = ("SELECT character_maximum_length FROM information_schema.columns WHERE table_schema = :s "
              "AND table_name = 'note_section_instances' AND column_name = 'section_number'")


def _sqlstate(exc: BaseException) -> str:
    for e in (getattr(getattr(exc, "orig", None), "__cause__", None), getattr(exc, "orig", None), exc.__cause__):
        code = getattr(e, "sqlstate", None) or getattr(e, "pgcode", None)
        if code:
            return str(code)
    return type(exc).__name__


def _sections() -> list[dict[str, Any]]:
    from app.services.note_section_catalog import filter_template_sections

    data = json.loads((_BACKEND / "data" / "note_template_soe.json").read_text(encoding="utf-8-sig"))
    return filter_template_sections(data.get("sections", []), "consolidated")


def _pre_v188_table(md: sa.MetaData) -> sa.Table:
    """去外键副本，section_number 按 V188 之前的真库现状建成 VARCHAR(20)。"""
    from app.models.note_trim_models import NoteSectionInstance

    return sa.Table(NoteSectionInstance.__table__.name, md, *[
        sa.Column(c.name, sa.String(20) if c.name == "section_number" else c.type, primary_key=c.primary_key,
                  nullable=c.nullable, server_default=c.server_default)
        for c in NoteSectionInstance.__table__.columns
    ])


async def _run_script(engine, path: Path) -> str:
    from app.core.migration_runner import MigrationRunner

    try:
        async with engine.begin() as conn:
            for stmt in MigrationRunner._split_sql_statements(path.read_text(encoding="utf-8")):
                await conn.exec_driver_sql(stmt)
        return "ok"
    except sa.exc.DBAPIError as exc:
        return _sqlstate(exc)


async def _init_sections(Session, project_id: uuid.UUID, sections: list[dict[str, Any]]) -> str:
    from app.services.note_trim_service import NoteTrimService

    async with Session() as db:
        try:
            await NoteTrimService(db)._init_from_sections(project_id, "soe", sections)
            await db.commit()
            return "ok"
        except sa.exc.DBAPIError as exc:
            await db.rollback()
            return _sqlstate(exc)


async def _state(engine, schema: str, project_id: uuid.UUID) -> dict[str, Any]:
    async with engine.connect() as conn:
        width = await conn.scalar(sa.text(_WIDTH_SQL), {"s": schema})
        row = (await conn.execute(sa.text(
            "SELECT count(*), coalesce(max(length(section_number)), 0) FROM note_section_instances "
            "WHERE project_id = :p"), {"p": project_id})).one()
    return {"width": width, "rows": int(row[0]), "longest": int(row[1])}


async def _collect() -> dict[str, Any]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    snap: dict[str, Any] = {"harness_errors": [], "steps": {}}
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        snap["harness_errors"].append("本守卫的判据是 PostgreSQL 的 VARCHAR 长度校验，必须真实 PostgreSQL")
        return snap
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    admin = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off))
    schema = f"tmp_v188_{uuid.uuid4().hex[:10]}"
    project_id = uuid.uuid4()
    sections = _sections()
    snap["sections"] = len(sections)
    snap["longest_seed"] = max(len(s.get("section_number", "")) for s in sections)
    engine = None
    steps = snap["steps"]
    try:
        async with admin.connect() as conn:
            snap["public_width"] = await conn.scalar(sa.text(_WIDTH_SQL), {"s": "public"})
            snap["public_v188_applied"] = int(await conn.scalar(sa.text(
                "SELECT count(*) FROM schema_version WHERE version = '188'")))
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool,
                                     connect_args={**ssl_off, "server_settings": {"search_path": schema}})
        md = sa.MetaData()
        _pre_v188_table(md)
        async with engine.begin() as conn:
            await conn.run_sync(md.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)

        steps["before_v188"] = {"init": await _init_sections(Session, project_id, sections),
                                **await _state(engine, schema, project_id)}
        steps["v188_first"] = {"run": await _run_script(engine, V188), **await _state(engine, schema, project_id)}
        steps["v188_again"] = {"run": await _run_script(engine, V188), **await _state(engine, schema, project_id)}
        steps["after_v188"] = {"init": await _init_sections(Session, project_id, sections),
                               **await _state(engine, schema, project_id)}
        steps["r188_with_long_rows"] = {"run": await _run_script(engine, R188),
                                        **await _state(engine, schema, project_id)}
        async with engine.begin() as conn:
            await conn.execute(sa.text("DELETE FROM note_section_instances WHERE length(section_number) > 20"))
        steps["r188_after_cleanup"] = {"run": await _run_script(engine, R188),
                                       **await _state(engine, schema, project_id)}
        steps["v188_reapplied"] = {"run": await _run_script(engine, V188), **await _state(engine, schema, project_id)}
    except Exception as exc:  # noqa: BLE001 - 采集失败必须让守卫红
        snap["harness_errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            async with admin.connect() as conn:
                snap["schema_left"] = int(await conn.scalar(
                    sa.text("SELECT count(*) FROM pg_namespace WHERE nspname = :s"), {"s": schema}))
        except Exception as exc:  # noqa: BLE001
            snap["harness_errors"].append(f"cleanup: {type(exc).__name__}: {exc}")
        await admin.dispose()
    return snap


@pytest.fixture(scope="module")
def snapshot() -> dict[str, Any]:
    return asyncio.run(_collect())


def test_harness_ran_and_cleaned_up(snapshot: dict[str, Any]) -> None:
    assert snapshot["harness_errors"] == []
    assert snapshot["schema_left"] == 0
    assert snapshot["longest_seed"] > 20, "样本里没有超过 20 字的编号：判据空转"


def test_before_v188_init_fails_with_value_too_long_and_writes_nothing(snapshot: dict[str, Any]) -> None:
    """复现真库现状：VARCHAR(20) 上写国企合并口径全部种子章节 ⇒ 22001，整批回滚（真库本表一直 0 行）。"""
    assert snapshot["steps"]["before_v188"] == {"init": "22001", "width": 20, "rows": 0, "longest": 0}


def test_v188_widens_idempotently_then_whole_batch_is_written(snapshot: dict[str, Any]) -> None:
    steps, n, longest = snapshot["steps"], snapshot["sections"], snapshot["longest_seed"]
    assert steps["v188_first"] == {"run": "ok", "width": None, "rows": 0, "longest": 0}
    assert steps["v188_again"] == {"run": "ok", "width": None, "rows": 0, "longest": 0}
    assert steps["after_v188"] == {"init": "ok", "width": None, "rows": n, "longest": longest}


def test_r188_refuses_to_truncate_then_restores_and_v188_reapplies(snapshot: dict[str, Any]) -> None:
    """R188 有超长行时 RAISE EXCEPTION（P0001）且列宽不变；清掉超长行才恢复 VARCHAR(20)；之后 V188 可再次放宽。"""
    steps, n = snapshot["steps"], snapshot["sections"]
    assert steps["r188_with_long_rows"] == {"run": "P0001", "width": None, "rows": n,
                                            "longest": snapshot["longest_seed"]}
    restored = steps["r188_after_cleanup"]
    assert (restored["run"], restored["width"]) == ("ok", 20) and 0 < restored["rows"] < n
    assert restored["longest"] <= 20
    assert steps["v188_reapplied"]["run"] == "ok" and steps["v188_reapplied"]["width"] is None


def test_local_database_has_v188_applied(snapshot: dict[str, Any]) -> None:
    """开发服务器热重载不跑迁移：本地库必须真的应用过 V188（列已放宽 + schema_version 有记录）。"""
    assert snapshot["public_width"] is None
    assert snapshot["public_v188_applied"] == 1
