"""真实 PostgreSQL 守卫：附注对齐的备份 / 恢复（spec disclosure-note-template-word-realignment Task 13「先实测恢复路径」）。

scratch schema（``tmp_realign_*``，search_path 只含自己）：四张表按 ORM 建去外键副本 + 生产同款唯一索引，章节锁表按
V046 原文建。数据 = **真实项目「测试集团甲」2025 年附注原样拷贝**（真实形态：纯文字章节 ``table_data`` 是 JSON null）
+ 几行专门构造的边界值（SQL NULL 与 JSON null 并存、``1.10`` 与 20 位有效数字、推送「推送过空值」）。

流程：备份 → 改名 / 改表 / JSON null 改 SQL NULL / 删行 / 新增行 → 恢复 → 再导出须与备份逐字相等，且边界值逐项原样。
public 只读（拷贝源前后行数一致）；结束 ``DROP SCHEMA CASCADE`` 并复查。``DATABASE_URL`` 非 PostgreSQL 时直接失败不 skip。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

SOURCE_PROJECT = uuid.UUID("94a40b23-21a2-4d7a-a38d-9fd059d57717")  # 【测试】附注批量甲
YEAR = 2025
_LOCKS_DDL = """CREATE TABLE note_section_locks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), project_id UUID NOT NULL, year INT NOT NULL,
    section_code VARCHAR(100) NOT NULL, locked_by UUID, locked_by_name VARCHAR(150),
    acquired_at TIMESTAMPTZ DEFAULT now(), heartbeat_at TIMESTAMPTZ DEFAULT now(), released_at TIMESTAMPTZ)"""
_UNIQUE = ("CREATE UNIQUE INDEX uq_dn ON disclosure_notes (project_id, year, note_section)",
           "CREATE UNIQUE INDEX uq_fps ON formula_push_state (project_id, year, addr_id)")


def _tables():
    from app.models.formula_push_models import FormulaPushState
    from app.models.note_trim_models import NoteSectionInstance
    from app.models.report_models import DisclosureNote

    return DisclosureNote.__table__, FormulaPushState.__table__, NoteSectionInstance.__table__


def _copy(table: sa.Table, md: sa.MetaData) -> sa.Table:
    from sqlalchemy.dialects import postgresql

    def _type(c: sa.Column):
        t = c.type
        return postgresql.ENUM(*t.enums, name=t.name, create_type=False) if isinstance(t, sa.Enum) and t.name else t

    return sa.Table(table.name, md, *[sa.Column(c.name, _type(c), primary_key=c.primary_key, nullable=c.nullable,
                                                server_default=c.server_default) for c in table.columns])


def _enum_ddl(*tables: sa.Table) -> list[str]:
    seen = {c.type.name: list(c.type.enums) for t in tables for c in t.columns
            if isinstance(c.type, sa.Enum) and c.type.name}
    return [f"CREATE TYPE {n} AS ENUM ({', '.join(repr(v) for v in labels)})" for n, labels in sorted(seen.items())]


async def _seed(conn, schema: str, dn: sa.Table) -> dict[str, Any]:
    cols = ", ".join(c.name for c in dn.columns)
    # 枚举列要转到 scratch 自己的同名类型（search_path 只含 scratch，不带 schema 的类型名解析到它）
    picks = ", ".join(f"{c.name}::text::{c.type.name}" if isinstance(c.type, sa.Enum) and c.type.name else c.name
                      for c in dn.columns)
    copied = (await conn.execute(sa.text(
        f'INSERT INTO "{schema}".disclosure_notes ({cols}) SELECT {picks} FROM public.disclosure_notes '
        "WHERE project_id = :p AND year = :y"), {"p": SOURCE_PROJECT, "y": YEAR})).rowcount
    edge = {k: uuid.uuid4() for k in ("sql_null", "precise", "fps_json_null", "fps_sql_null", "inst", "lock")}
    await conn.execute(sa.text(
        "INSERT INTO disclosure_notes (id, project_id, year, note_section, section_title, table_data, status) VALUES "
        "(:a, :p, :y, '边界、SQL NULL', 'SQL NULL', NULL, 'draft'), "
        "(:b, :p, :y, '边界、精度', '精度', CAST(:j AS jsonb), 'draft')"),
        {"a": edge["sql_null"], "b": edge["precise"], "p": SOURCE_PROJECT, "y": YEAR,
         "j": '{"v": 1.10, "big": 123456789012345678.12, "rows": [{"label": "甲", "values": [0.1, null]}]}'})
    await conn.execute(sa.text(
        "INSERT INTO formula_push_state (id, project_id, year, addr_id, rule_id, domain, note_section, "
        "last_pushed_value, state) VALUES "
        "(:a, :p, :y, 'note://八、1/货币资金/合计.end', 'r1', 'note', '八、1', 'null'::jsonb, 'auto'), "
        "(:b, :p, :y, 'note://八、1/货币资金/合计.prior', 'r1', 'note', '八、1', NULL, 'manual')"),
        {"a": edge["fps_json_null"], "b": edge["fps_sql_null"], "p": SOURCE_PROJECT, "y": YEAR})
    await conn.execute(sa.text(
        "INSERT INTO note_section_instances (id, project_id, template_type, section_number, section_title, status, "
        "sort_order, is_deleted) VALUES (:i, :p, 'soe', '七、母公司直接或通过其他子公司间接拥有被投资单位半数以上的表决权"
        "但未能对其形成控制的', '长编号', 'retain', 0, false)"), {"i": edge["inst"], "p": SOURCE_PROJECT})
    await conn.execute(sa.text("INSERT INTO note_section_locks (id, project_id, year, section_code, locked_by_name) "
                               "VALUES (:i, :p, :y, '八、1', '经理甲')"), {"i": edge["lock"], "p": SOURCE_PROJECT, "y": YEAR})
    return {"copied": copied, "edge": edge}


async def _mutate(conn, edge: dict[str, uuid.UUID]) -> None:
    """模拟一次对齐写坏：改编号、改表格、JSON null 改成 SQL NULL、删行、新增行、改推送 / 实例 / 锁。"""
    await conn.execute(sa.text("UPDATE disclosure_notes SET note_section = note_section || '·改', table_data = "
                               "'{\"x\": 1}'::jsonb WHERE project_id = :p AND note_section LIKE '八、%'"),
                       {"p": SOURCE_PROJECT})
    await conn.execute(sa.text("UPDATE disclosure_notes SET table_data = NULL WHERE jsonb_typeof(table_data) = 'null'"))
    await conn.execute(sa.text("UPDATE disclosure_notes SET table_data = '{\"v\": 1.1}'::jsonb WHERE id = :i"),
                       {"i": edge["precise"]})
    await conn.execute(sa.text("DELETE FROM disclosure_notes WHERE note_section LIKE '十%'"))
    await conn.execute(sa.text("INSERT INTO disclosure_notes (id, project_id, year, note_section, section_title, "
                               "status) VALUES (:i, :p, :y, '新增、1', '新增', 'draft')"),
                       {"i": uuid.uuid4(), "p": SOURCE_PROJECT, "y": YEAR})
    await conn.execute(sa.text("UPDATE formula_push_state SET last_pushed_value = NULL, addr_id = addr_id || 'x'"))
    await conn.execute(sa.text("DELETE FROM note_section_instances"))
    await conn.execute(sa.text("UPDATE note_section_locks SET section_code = '八、2'"))


async def _probe(conn, edge: dict[str, uuid.UUID]) -> dict[str, Any]:
    q = lambda sql, **kw: conn.scalar(sa.text(sql), kw)  # noqa: E731
    return {
        "json_null_notes": int(await q("SELECT count(*) FROM disclosure_notes WHERE jsonb_typeof(table_data) = 'null'")),
        "sql_null_notes": int(await q("SELECT count(*) FROM disclosure_notes WHERE table_data IS NULL")),
        "precise": await q("SELECT table_data::text FROM disclosure_notes WHERE id = :i", i=edge["precise"]),
        "fps": sorted((await conn.execute(sa.text(
            "SELECT addr_id, coalesce(jsonb_typeof(last_pushed_value), 'SQL NULL') FROM formula_push_state"))).all()),
        "inst": await q("SELECT section_number FROM note_section_instances WHERE id = :i", i=edge["inst"]),
        "lock": await q("SELECT section_code FROM note_section_locks WHERE id = :i", i=edge["lock"]),
        "notes": int(await q("SELECT count(*) FROM disclosure_notes")),
    }


async def _collect() -> dict[str, Any]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.services.note_project_realign_apply import export_rows, restore_backup, write_backup

    snap: dict[str, Any] = {"errors": []}
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        snap["errors"].append("备份 / 恢复用 row_to_json / json_populate_recordset，必须真实 PostgreSQL")
        return snap
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    admin = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off))
    schema, engine = f"tmp_realign_{uuid.uuid4().hex[:10]}", None
    backup = Path(tempfile.mkdtemp()) / "note_realign_backup.json"
    count_src = "SELECT count(*) FROM public.disclosure_notes WHERE project_id = :p"
    try:
        async with admin.connect() as conn:
            snap["public_before"] = int(await conn.scalar(sa.text(count_src), {"p": SOURCE_PROJECT}))
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool,
                                     connect_args={**ssl_off, "server_settings": {"search_path": schema}})
        dn, fps, nsi = _tables()
        md = sa.MetaData()
        for t in (dn, fps, nsi):
            _copy(t, md)
        async with engine.begin() as conn:
            for ddl in _enum_ddl(dn):
                await conn.exec_driver_sql(ddl)
            await conn.run_sync(md.create_all)
            for ddl in (_LOCKS_DDL, *_UNIQUE):
                await conn.exec_driver_sql(ddl)
            seeded = await _seed(conn, schema, dn)
        snap["copied"], edge = seeded["copied"], seeded["edge"]
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.connect() as conn:
            snap["before"] = await _probe(conn, edge)
        async with Session() as db:
            snap["backup"] = await write_backup(db, SOURCE_PROJECT, YEAR, backup)
            await db.rollback()
        snap["backup_rows_are_raw_text"] = all(
            isinstance(e["row"], str) for es in json.loads(backup.read_text("utf-8"))["tables"].values() for e in es)
        async with engine.begin() as conn:
            await _mutate(conn, edge)
            snap["mutated"] = await _probe(conn, edge)
        async with Session() as db:
            snap["restore"] = await restore_backup(db, backup)
            await db.commit()
        async with engine.connect() as conn:
            snap["after"] = await _probe(conn, edge)
        async with Session() as db:
            snap["export_equal"] = await export_rows(db, SOURCE_PROJECT, YEAR) == json.loads(
                backup.read_text("utf-8"))["tables"]
        async with admin.connect() as conn:
            snap["public_after"] = int(await conn.scalar(sa.text(count_src), {"p": SOURCE_PROJECT}))
    except Exception as exc:  # noqa: BLE001 - 采集失败必须让守卫红
        snap["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        if engine is not None:
            await engine.dispose()
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        async with admin.connect() as conn:
            snap["schema_left"] = int(await conn.scalar(
                sa.text("SELECT count(*) FROM pg_namespace WHERE nspname = :s"), {"s": schema}))
        await admin.dispose()
        backup.unlink(missing_ok=True)
    return snap


@pytest.fixture(scope="module")
def snapshot() -> dict[str, Any]:
    return asyncio.run(_collect())


def test_harness_ran_on_real_rows(snapshot: dict[str, Any]) -> None:
    assert snapshot["errors"] == []
    assert snapshot["copied"] >= 100, "真实项目拷贝行数过少：判据空转"
    assert snapshot["before"]["json_null_notes"] > 0 and snapshot["before"]["sql_null_notes"] >= 1
    assert snapshot["backup_rows_are_raw_text"] is True
    assert snapshot["public_after"] == snapshot["public_before"] and snapshot["schema_left"] == 0


def test_mutation_really_changed_every_probe(snapshot: dict[str, Any]) -> None:
    """反向断言：写坏那一步确实动到了每一项（否则「恢复后相等」不证明任何事）。"""
    before, mutated = snapshot["before"], snapshot["mutated"]
    assert all(before[k] != mutated[k] for k in before), {k: (before[k], mutated[k]) for k in before}


def test_restore_is_exact(snapshot: dict[str, Any]) -> None:
    assert snapshot["after"] == snapshot["before"]
    assert snapshot["export_equal"] is True
    assert snapshot["restore"]["counts"] == snapshot["backup"]["counts"]


def test_edge_values_survive_round_trip(snapshot: dict[str, Any]) -> None:
    after = snapshot["after"]
    precise = json.loads(after["precise"], parse_float=str)
    assert precise["v"] == "1.10" and precise["big"] == "123456789012345678.12"
    assert after["fps"] == [("note://八、1/货币资金/合计.end", "null"), ("note://八、1/货币资金/合计.prior", "SQL NULL")]
    assert after["inst"].startswith("七、母公司直接") and len(after["inst"]) > 20
