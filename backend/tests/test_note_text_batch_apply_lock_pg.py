"""真实 PostgreSQL 守卫：附注批量 apply 的目标行锁（Task 28 / 33，AC-4.3）。

═══ 为什么必须真库 ═══

SQLite 忽略 ``FOR UPDATE`` ⇒ 在 SQLite 上「加没加锁」都绿。判据是 PostgreSQL 行锁语义：
会话 A 用 ``lock_target_notes`` 锁住目标后，会话 B 的同一调用必须**阻塞到 A 提交**，且 B 拿到锁后
读到的是 **A 已提交的正文**（READ COMMITTED 下加锁读取最新版本）⇒ B 的逐章 before_hash 复核判 stale。

反向对照：同一查询去掉 ``FOR UPDATE``，B 不阻塞且读到旧正文。对照不红，说明夹具没复现并发，
正向断言就是空转。

═══ 隔离 ═══

scratch schema（``tmp_ntblock_*``），``search_path`` 只含自己；``disclosure_notes`` 由 ORM metadata
派生（去外键）。结束 ``DROP SCHEMA CASCADE``。``DATABASE_URL`` 非 PostgreSQL 时直接失败不 skip。
"""
from __future__ import annotations

import asyncio
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

YEAR = 2025
OLD, NEW = "<p>旧正文</p>", "<p>A 写入</p>"
#: A 持锁期间给 B 的时间；B 在此期间完成 ⇒ 没有被阻塞
_HOLD_SECONDS = 1.0


def _fk_free_copy(table: sa.Table) -> sa.Table:
    from sqlalchemy.dialects import postgresql

    def _type(column: sa.Column):
        t = column.type
        if isinstance(t, sa.Enum) and t.name:
            return postgresql.ENUM(*t.enums, name=t.name, create_type=False)
        return t

    return sa.Table(table.name, sa.MetaData(), *[
        sa.Column(c.name, _type(c), primary_key=c.primary_key, nullable=c.nullable, server_default=c.server_default)
        for c in table.columns
    ])


def _enum_ddl(table: sa.Table) -> list[str]:
    seen = {c.type.name: list(c.type.enums) for c in table.columns if isinstance(c.type, sa.Enum) and c.type.name}
    return [f"CREATE TYPE {name} AS ENUM ({', '.join(repr(v) for v in labels)})" for name, labels in sorted(seen.items())]


async def _unlocked(db, project_id, year, note_ids):
    """反向对照：与 ``lock_target_notes`` 同一查询，只是不加 ``FOR UPDATE``。"""
    from app.models.report_models import DisclosureNote

    rows = await db.execute(sa.select(DisclosureNote).where(
        DisclosureNote.id.in_(list(note_ids)), DisclosureNote.project_id == project_id,
        DisclosureNote.year == year, DisclosureNote.is_deleted == sa.false()))
    return {n.id: n for n in rows.scalars().all()}


async def _scenario(Session, lock_fn, project_id: uuid.UUID, note_id: uuid.UUID) -> dict[str, Any]:
    from app.models.report_models import DisclosureNote

    async with Session() as a:
        locked_a = await lock_fn(a, project_id, YEAR, [note_id])

        async def _second() -> str | None:
            async with Session() as b:
                locked_b = await lock_fn(b, project_id, YEAR, [note_id])
                text = locked_b[note_id].text_content
                await b.rollback()
                return text

        task = asyncio.create_task(_second())
        await asyncio.sleep(_HOLD_SECONDS)
        finished_early = task.done()
        locked_a[note_id].text_content = NEW
        await a.commit()
    seen = await asyncio.wait_for(task, timeout=15)
    async with Session() as s:  # 复原，供下一个场景使用
        (await s.get(DisclosureNote, note_id)).text_content = OLD
        await s.commit()
    return {"b_finished_while_a_held_lock": finished_early, "b_saw": seen}


async def _collect() -> dict[str, Any]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.models.report_models import DisclosureNote
    from app.services.note_text_batch_apply import lock_target_notes

    snap: dict[str, Any] = {"harness_errors": [], "scenarios": {}}
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        snap["harness_errors"].append("本守卫的判据是 PostgreSQL 行锁语义，必须真实 PostgreSQL")
        return snap
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    admin = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off))
    schema = f"tmp_ntblock_{uuid.uuid4().hex[:10]}"
    engine = None
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool,
                                     connect_args={**ssl_off, "server_settings": {"search_path": schema}})
        async with engine.begin() as conn:
            for ddl in _enum_ddl(DisclosureNote.__table__):
                await conn.exec_driver_sql(ddl)
            await conn.run_sync(_fk_free_copy(DisclosureNote.__table__).create)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        project_id, note_id = uuid.uuid4(), uuid.uuid4()
        async with Session() as s:
            s.add(DisclosureNote(id=note_id, project_id=project_id, year=YEAR, note_section="一、1",
                                 section_title="公司基本情况", text_content=OLD, sort_index=1))
            await s.commit()
        snap["scenarios"]["locked"] = await _scenario(Session, lock_target_notes, project_id, note_id)
        snap["scenarios"]["unlocked_control"] = await _scenario(Session, _unlocked, project_id, note_id)
    except Exception as exc:  # noqa: BLE001 - 采集失败必须让守卫红
        snap["harness_errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        except Exception as exc:  # noqa: BLE001
            snap["harness_errors"].append(f"cleanup: {type(exc).__name__}: {exc}")
        await admin.dispose()
    return snap


@pytest.fixture(scope="module")
def snapshot() -> dict[str, Any]:
    return asyncio.run(_collect())


def test_harness_ran_without_errors(snapshot: dict[str, Any]) -> None:
    assert snapshot["harness_errors"] == []
    assert set(snapshot["scenarios"]) == {"locked", "unlocked_control"}


def test_negative_control_without_for_update_does_not_block(snapshot: dict[str, Any]) -> None:
    """反向对照：不加锁时 B 立即读到旧正文 —— 证明夹具真的制造了并发窗口。"""
    s = snapshot["scenarios"]["unlocked_control"]
    assert s == {"b_finished_while_a_held_lock": True, "b_saw": OLD}, "夹具未复现并发窗口，正向断言会空转"


def test_second_apply_waits_for_lock_and_sees_committed_text(snapshot: dict[str, Any]) -> None:
    s = snapshot["scenarios"]["locked"]
    assert s["b_finished_while_a_held_lock"] is False, "A 持锁期间 B 已拿到目标行：lock_target_notes 没有加行锁"
    assert s["b_saw"] == NEW, "B 拿到锁后读到的不是 A 已提交的正文：before_hash 复核会放过覆盖写"
