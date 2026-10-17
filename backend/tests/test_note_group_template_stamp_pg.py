"""集团附注模板下发（裸 SQL）的盖章与层级（spec disclosure-note-template-word-realignment Task 16，design §5）。

``NoteGroupTemplateService._upsert_section`` 是裸 SQL：SQLite 下 ``str(uuid)`` 与 ORM 存的 32 位 hex 互不命中，SQLite
也不拒绝把字母写进整数列 ⇒ 只能在真 PostgreSQL 上验。scratch schema（``tmp_grptpl_*``，search_path 只含自己），
两张表 ``LIKE public.* INCLUDING DEFAULTS``（列类型与真库一致、无外键）；结束 ``DROP SCHEMA CASCADE`` 并复查。

覆盖：①覆盖分支以下发人盖章、写内容；②模板 ``layer`` 是字母（下发策略层）或空值时 ``level`` 保留原值（原来
字母直接报错、整个项目下发失败，空值把层级清成 NULL），是 1~5 的整数才写；③只改结构的分支不盖章。
``DATABASE_URL`` 非 PostgreSQL 时直接失败不 skip。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

OLD = datetime(2020, 1, 1, tzinfo=timezone.utc)
PREV = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
YEAR = 2025
_SECTIONS = [  # 模板章节（键名即保存模板时的别名：section_code / title / layer / content）
    {"section_code": "sid-A", "title": "新标题", "layer": "A", "content": "<p>新正文</p>", "sort_order": 9},
    {"section_code": "sid-B", "layer": 3, "sort_order": 7},
    {"section_code": "sid-C", "layer": None, "sort_order": 8},
]
_SEED = (("sid-A", "八、1", 2, 1), ("sid-B", "八、2", 2, 2), ("sid-C", "八、3", 4, 3))


async def _rows(conn) -> dict[str, dict[str, Any]]:
    result = await conn.execute(sa.text(
        "SELECT section_id, section_title, text_content, level, sort_order, updated_at, updated_by "
        "FROM disclosure_notes ORDER BY section_id"))
    return {r.section_id: dict(r._mapping) for r in result}


async def _collect() -> dict[str, Any]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.services.note_group_template_service import NoteGroupTemplateService

    snap: dict[str, Any] = {"errors": []}
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        snap["errors"].append("裸 SQL 的类型校验只有真实 PostgreSQL 才会报，必须真库")
        return snap
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    admin = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off))
    schema, engine = f"tmp_grptpl_{uuid.uuid4().hex[:10]}", None
    pid, uid, tid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            for table in ("disclosure_notes", "group_note_templates"):
                await conn.exec_driver_sql(
                    f'CREATE TABLE "{schema}".{table} (LIKE public.{table} INCLUDING DEFAULTS)')
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool,
                                     connect_args={**ssl_off, "server_settings": {"search_path": schema}})
        async with engine.begin() as conn:
            for sid, code, level, order in _SEED:
                await conn.execute(sa.text(
                    "INSERT INTO disclosure_notes (id, project_id, year, note_section, section_title, section_id, "
                    "text_content, level, sort_order, updated_at, updated_by) VALUES "
                    "(:i, :p, :y, :c, '旧标题', :s, '<p>旧正文</p>', :l, :o, :t, :u)"),
                    {"i": uuid.uuid4(), "p": pid, "y": YEAR, "c": code, "s": sid, "l": level, "o": order,
                     "t": OLD, "u": PREV})
            await conn.execute(sa.text(
                "INSERT INTO group_note_templates (id, name, template_data) VALUES (:i, '集团模板', CAST(:d AS jsonb))"),
                {"i": tid, "d": json.dumps({"sections": _SECTIONS}, ensure_ascii=False)})
        async with engine.connect() as conn:  # 自检：真库确实拒绝把字母写进层级列（SQLite 不拒绝）
            try:
                await conn.execute(sa.text("UPDATE disclosure_notes SET level = :l"), {"l": "A"})
                snap["letter_rejected"] = False
            except Exception as exc:  # noqa: BLE001
                snap["letter_rejected"] = type(exc).__name__
        snap["since"] = datetime.now(timezone.utc) - timedelta(seconds=1)
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            snap["result"] = await NoteGroupTemplateService(db).distribute_template(
                template_id=tid, target_project_ids=[pid], strategy="a_overwrite", user_id=uid)
            await db.commit()
        async with engine.connect() as conn:
            snap["rows"] = await _rows(conn)
        snap["uid"] = uid
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
    return snap


@pytest.fixture(scope="module")
def snapshot() -> dict[str, Any]:
    return asyncio.run(_collect())


def test_harness_ran_on_real_postgres(snapshot: dict[str, Any]) -> None:
    assert snapshot["errors"] == [] and snapshot["schema_left"] == 0
    assert snapshot["letter_rejected"], "真库居然接受把字母写进 SMALLINT —— 本文件的判据空转"
    assert snapshot["result"]["success"] == 1 and snapshot["result"]["failed"] == [], snapshot["result"]


def test_overwrite_branch_stamps_distributor_and_keeps_level_for_letter_layer(snapshot: dict[str, Any]) -> None:
    row = snapshot["rows"]["sid-A"]
    assert (row["section_title"], row["text_content"], row["sort_order"]) == ("新标题", "<p>新正文</p>", 9)
    assert row["level"] == 2, "模板层级是策略字母 A：不是树层级，保留原值"
    assert row["updated_by"] == snapshot["uid"] and row["updated_at"] >= snapshot["since"]


def test_structure_only_branch_writes_numeric_level_and_does_not_stamp(snapshot: dict[str, Any]) -> None:
    b, c = snapshot["rows"]["sid-B"], snapshot["rows"]["sid-C"]
    assert (b["level"], b["sort_order"], b["section_title"]) == (3, 7, "旧标题")
    assert (c["level"], c["sort_order"]) == (4, 8), "模板层级为空时把原层级清成了 NULL"
    for row in (b, c):
        assert (row["updated_by"], row["updated_at"]) == (PREV, OLD), "只改排序 / 层级不算内容编辑"
