"""真实 PostgreSQL 守卫：附注对齐的备份 / 恢复（spec disclosure-note-template-word-realignment Task 13「先实测恢复路径」）。

scratch schema（``tmp_realign_*``，search_path 只含自己）：四张表按 ORM 建去外键副本 + 生产同款唯一索引，章节锁表按
V046 原文建，底稿条目表按 public 现表结构建（推送前备份 ``include_workpapers`` 用）。数据 = **真实项目「测试集团甲」2025 年附注原样拷贝**（真实形态：纯文字章节 ``table_data`` 是 JSON null）
+ 几行专门构造的边界值（SQL NULL 与 JSON null 并存、``1.10`` 与 20 位有效数字、推送「推送过空值」）。

流程：备份 → 改名 / 改表 / JSON null 改 SQL NULL / 删行 / 新增行 → 补记后像 → 恢复 → 再导出须与备份逐字相等，且边界值逐项原样。
后像围栏：现状与后像一致才放行，不一致时一行不写地拒绝、``force`` 才继续；REPEATABLE READ 下操作取快照后别人提交的改动
进不了后像，恢复预演据此点名该行。
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
#: 底稿条目表无 ORM 模型：按 public 现表结构建（不带外键），推送前备份（include_workpapers）用
_CHECKLIST_DDL = ("CREATE TABLE checklist_responses (LIKE public.checklist_responses "
                  "INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES)")


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
    wp = uuid.uuid4()
    await conn.execute(sa.text(
        "INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, remark, content_version) VALUES "
        "(:a, :p, :w, 'E1-cash-detail-total-unaudited', NULL, '476.73', 3), (:b, :p, :w, 'E1-note', '结论', NULL, 1)"),
        {"a": uuid.uuid4(), "b": uuid.uuid4(), "p": SOURCE_PROJECT, "w": wp})
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
    await conn.execute(sa.text("UPDATE checklist_responses SET remark = '0', content_version = content_version + 1"))
    await conn.execute(sa.text("DELETE FROM checklist_responses WHERE item_id = 'E1-note'"))


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
        "checklist": sorted((await conn.execute(sa.text(
            "SELECT item_id, conclusion, remark, content_version, updated_at::text FROM checklist_responses"))).all()),
    }


async def _collect() -> dict[str, Any]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.services.note_project_realign_apply import (
        RealignError, begin_snapshot, export_rows, plan_restore, record_postimage, restore_backup, write_backup,
    )

    snap: dict[str, Any] = {"errors": []}
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        snap["errors"].append("备份 / 恢复用 row_to_json / json_populate_recordset，必须真实 PostgreSQL")
        return snap
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    admin = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off))
    schema, engine = f"tmp_realign_{uuid.uuid4().hex[:10]}", None
    backup = Path(tempfile.mkdtemp()) / "note_realign_backup.json"
    backup_wp = backup.with_name("note_push_backup.json")
    backup_rr = backup.with_name("note_rr_backup.json")
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
            for ddl in (_LOCKS_DDL, *_UNIQUE, _CHECKLIST_DDL):
                await conn.exec_driver_sql(ddl)
            seeded = await _seed(conn, schema, dn)
        snap["copied"], edge = seeded["copied"], seeded["edge"]
        snap["edge_ids"] = {k: str(v) for k, v in edge.items()}
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.connect() as conn:
            snap["before"] = await _probe(conn, edge)
        async with Session() as db:
            snap["backup"] = await write_backup(db, SOURCE_PROJECT, YEAR, backup)
            snap["backup_wp"] = await write_backup(db, SOURCE_PROJECT, YEAR, backup_wp, include_workpapers=True)
            await db.rollback()
        snap["backup_rows_are_raw_text"] = all(
            isinstance(e["row"], str) for es in json.loads(backup.read_text("utf-8"))["tables"].values() for e in es)
        async with engine.begin() as conn:
            await _mutate(conn, edge)
            snap["mutated"] = await _probe(conn, edge)
        async with Session() as db:  # 模拟操作提交前补记后像（真实流程与执行同一事务，见 realign_project_notes）
            await record_postimage(db, backup)
            await record_postimage(db, backup_wp)
            await db.rollback()
        async with Session() as db:
            snap["plan_base"] = await plan_restore(db, backup)
            await db.rollback()
        async with Session() as db:  # 默认备份不含底稿条目：恢复只回附注四张表，底稿条目保持写坏后的样子
            await begin_snapshot(db)
            snap["restore_base"] = await restore_backup(db, backup)
            await db.commit()
        async with engine.connect() as conn:
            snap["after_base"] = await _probe(conn, edge)
        async with Session() as db:  # 上一步恢复改了附注四张表 ⇒ 对 backup_wp 的后像来说是「操作后有改动」
            snap["plan_wp"] = await plan_restore(db, backup_wp)
            await db.rollback()
        async with Session() as db:
            try:
                await restore_backup(db, backup_wp)
                snap["refused"] = None
            except RealignError as err:
                snap["refused"] = str(err)
            await db.rollback()
        async with engine.connect() as conn:
            snap["after_refusal"] = await _probe(conn, edge)
        async with Session() as db:
            await begin_snapshot(db)
            snap["restore"] = await restore_backup(db, backup_wp, force=True)
            await db.commit()
        async with engine.connect() as conn:
            snap["after"] = await _probe(conn, edge)
        async with Session() as db:
            snap["export_equal"] = await export_rows(db, SOURCE_PROJECT, YEAR, include_workpapers=True) == json.loads(
                backup_wp.read_text("utf-8"))["tables"]
            snap["plan_again"] = await plan_restore(db, backup_wp)
            await db.rollback()
        # REPEATABLE READ：备份之后、提交之前别人提交的改动不进后像 ⇒ 恢复围栏点名它。读已提交时它会进后像却
        # 不在备份里，围栏放行、按备份恢复就把别人的改动一起抹掉（这条用例在读已提交下必红）
        async with Session() as db:
            await begin_snapshot(db)
            snap["isolation"] = await db.scalar(sa.text("SELECT current_setting('transaction_isolation')"))
            await write_backup(db, SOURCE_PROJECT, YEAR, backup_rr)
            async with engine.begin() as other:
                await other.execute(sa.text("UPDATE disclosure_notes SET section_title = section_title || '·他人' "
                                            "WHERE id = :i"), {"i": edge["sql_null"]})
            await db.execute(sa.text("UPDATE disclosure_notes SET section_title = section_title || '·操作' "
                                     "WHERE id = :i"), {"i": edge["precise"]})
            await record_postimage(db, backup_rr)
            await db.commit()
        async with Session() as db:
            snap["plan_rr"] = await plan_restore(db, backup_rr)
            await db.rollback()
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
        for path in (backup, backup_wp, backup_rr):
            path.unlink(missing_ok=True)
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
    assert snapshot["restore"]["counts"] == snapshot["backup_wp"]["counts"]
    assert snapshot["backup_wp"]["counts"]["checklist_responses"] == 2


def test_default_backup_leaves_workpaper_entries_alone(snapshot: dict[str, Any]) -> None:
    """对齐 / 重建的备份不含底稿条目（它们不改底稿）；推送前的备份才带上，两种备份各自只恢复自己那几张表。"""
    assert "checklist_responses" not in snapshot["backup"]["counts"]
    assert snapshot["restore_base"]["counts"] == snapshot["backup"]["counts"]
    base = {k: v for k, v in snapshot["after_base"].items() if k != "checklist"}
    assert base == {k: v for k, v in snapshot["before"].items() if k != "checklist"}
    assert snapshot["after_base"]["checklist"] == snapshot["mutated"]["checklist"]


def test_restore_fence_refuses_until_forced(snapshot: dict[str, Any]) -> None:
    """后像围栏：现状与操作后像一致才放行；不一致时在任何写入之前拒绝，``force`` 才继续；恢复完再预演 = 无需恢复。"""
    assert snapshot["plan_base"]["fence"] == "ok"
    assert snapshot["plan_base"]["delta"]["disclosure_notes"]["change"] > 0
    plan_wp = snapshot["plan_wp"]
    assert plan_wp["fence"] == "mismatch" and plan_wp["drift"].get("disclosure_notes")
    assert "checklist_responses" not in plan_wp["drift"]  # 底稿条目在后像之后没人动过
    assert snapshot["refused"] and "后像围栏不放行" in snapshot["refused"]
    assert snapshot["after_refusal"] == snapshot["after_base"]  # 拒绝时一行没写
    assert snapshot["restore"]["restored"] is True and snapshot["restore"]["forced"] is True
    assert snapshot["plan_again"]["fence"] == "already_restored"


def test_repeatable_read_keeps_concurrent_edit_out_of_postimage(snapshot: dict[str, Any]) -> None:
    """操作事务取快照后别人提交的改动：后像里没有它 ⇒ 恢复围栏点名这一行（读已提交会把它记成操作结果而放行恢复）。"""
    plan = snapshot["plan_rr"]
    assert plan["fence"] == "mismatch"
    assert plan["drift"] == {"disclosure_notes": [snapshot["edge_ids"]["sql_null"]]}
    assert snapshot["isolation"] == "repeatable read"


def test_edge_values_survive_round_trip(snapshot: dict[str, Any]) -> None:
    after = snapshot["after"]
    precise = json.loads(after["precise"], parse_float=str)
    assert precise["v"] == "1.10" and precise["big"] == "123456789012345678.12"
    assert after["fps"] == [("note://八、1/货币资金/合计.end", "null"), ("note://八、1/货币资金/合计.prior", "SQL NULL")]
    assert after["inst"].startswith("七、母公司直接") and len(after["inst"]) > 20
