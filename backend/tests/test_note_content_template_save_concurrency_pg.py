"""真实 PostgreSQL 守卫：附注内容模板并发保存（R-13 / Task 42，AC-7.4）。

═══ 缺陷 ═══

首版 ``_find_or_create_template`` 与 ``max(version_no)+1`` 都不加锁：并发首建同名模板时后到者撞部分唯一索引，
并发续版时两边算出同一个 version_no 撞 ``ux_nctv_template_version`` —— 都是未捕获的 IntegrityError（500）。

═══ 判据 ═══

A 保存后持有事务不提交，B 并发保存同名模板（不同来源 ⇒ 不同内容）：B 必须等 A，A 提交后 B 也成功，
版本号连续不重复。反向对照：换回首版无锁实现，同一场景 B 必须失败 —— 对照不红说明夹具没制造出竞态。

═══ 隔离 ═══

scratch schema（``tmp_nctsave_*``）。两张模板表由 ORM ``to_metadata`` 复制，**保留**自身外键、部分唯一索引与
不可延迟的 ``current_version_id`` 外键（与 V187 同口径）；projects / disclosure_notes 为去外键副本，users 只建主键。
结束 ``DROP SCHEMA CASCADE``。``DATABASE_URL`` 非 PostgreSQL 时直接失败不 skip。
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

YEAR = 2025
_HOLD_SECONDS = 1.0


def _fk_free_copy(table: sa.Table, metadata: sa.MetaData) -> sa.Table:
    from sqlalchemy.dialects import postgresql

    def _type(column: sa.Column):
        t = column.type
        if isinstance(t, sa.Enum) and t.name:
            return postgresql.ENUM(*t.enums, name=t.name, create_type=False)
        return t

    return sa.Table(table.name, metadata, *[
        sa.Column(c.name, _type(c), primary_key=c.primary_key, nullable=c.nullable, server_default=c.server_default)
        for c in table.columns
    ])


def _enum_ddl(*tables: sa.Table) -> list[str]:
    seen = {c.type.name: list(c.type.enums) for t in tables for c in t.columns
            if isinstance(c.type, sa.Enum) and c.type.name}
    return [f"CREATE TYPE {name} AS ENUM ({', '.join(repr(v) for v in labels)})" for name, labels in sorted(seen.items())]


async def _legacy_find_or_create(db, *, name, description, owner_scope, owner_user_id, owner_group_project_id,
                                 user_id):
    """首版实现（无行锁、无首建竞态处理）—— 仅作反向对照。"""
    from app.models.note_content_template_models import NoteContentTemplate
    from app.services.note_content_template_snapshot import _template_filters

    existing = await db.scalar(sa.select(NoteContentTemplate).where(
        *_template_filters(name, owner_scope, owner_user_id, owner_group_project_id)))
    if existing:
        return existing
    template = NoteContentTemplate(id=uuid.uuid4(), name=name, description=description, owner_scope=owner_scope,
                                   owner_user_id=owner_user_id, owner_group_project_id=owner_group_project_id,
                                   created_by=user_id)
    db.add(template)
    await db.flush()
    return template


async def _save(db, project_id: uuid.UUID, user, name: str) -> dict[str, Any]:
    from app.services.note_content_template_snapshot import save_snapshot, snapshot_preview

    digest = (await snapshot_preview(db, project_id, YEAR, user=user))["snapshot_digest"]
    return await save_snapshot(db, project_id=project_id, year=YEAR, name=name, description=None,
                               owner_scope="personal", snapshot_digest=digest, user=user)


async def _race(Session, user, first: uuid.UUID, second: uuid.UUID, name: str) -> dict[str, Any]:
    async with Session() as a:
        first_result = await _save(a, first, user, name)

        async def _other() -> dict[str, Any]:
            async with Session() as b:
                try:
                    result = await _save(b, second, user, name)
                    await b.commit()
                    return {"ok": True, "version_no": result["version_no"], "template_id": result["template_id"]}
                except Exception as exc:  # noqa: BLE001 - 失败形态本身就是观测值
                    await b.rollback()
                    return {"ok": False, "error": type(exc).__name__}

        task = asyncio.create_task(_other())
        await asyncio.sleep(_HOLD_SECONDS)
        waited = not task.done()
        await a.commit()
    other = await asyncio.wait_for(task, timeout=20)
    return {"first": {"version_no": first_result["version_no"], "template_id": first_result["template_id"]},
            "second": other, "second_waited": waited}


async def _collect() -> dict[str, Any]:  # noqa: C901 - 单次采集覆盖全部场景
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    import app.services.note_content_template_snapshot as snap_module
    from app.core.config import settings
    from app.models.core import Project
    from app.models.note_content_template_models import NoteContentTemplate, NoteContentTemplateVersion
    from app.models.report_models import DisclosureNote

    snap: dict[str, Any] = {"harness_errors": [], "scenarios": {}, "versions": {}}
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        snap["harness_errors"].append("本守卫的判据是 PostgreSQL 锁与唯一索引语义，必须真实 PostgreSQL")
        return snap
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    admin = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off))
    schema = f"tmp_nctsave_{uuid.uuid4().hex[:10]}"
    engine = None
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool,
                                     connect_args={**ssl_off, "server_settings": {"search_path": schema}})
        md = sa.MetaData()
        sa.Table("users", md, sa.Column("id", PG_UUID(as_uuid=True), primary_key=True))
        _fk_free_copy(Project.__table__, md)
        _fk_free_copy(DisclosureNote.__table__, md)
        NoteContentTemplate.__table__.to_metadata(md)
        NoteContentTemplateVersion.__table__.to_metadata(md)
        async with engine.begin() as conn:
            for ddl in _enum_ddl(Project.__table__, DisclosureNote.__table__):
                await conn.exec_driver_sql(ddl)
            await conn.run_sync(md.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        user = SimpleNamespace(id=uuid.uuid4(), role="auditor")
        sources = {key: uuid.uuid4() for key in ("x", "y", "z")}
        async with Session() as s:
            await s.execute(sa.text("INSERT INTO users (id) VALUES (:id)"), {"id": user.id})
            for key, pid in sources.items():
                s.add(Project(id=pid, name=f"来源{key}", client_name=f"{key}公司", template_type="soe",
                              report_scope="standalone"))
            await s.flush()
            for key, pid in sources.items():  # 不同来源 ⇒ 不同内容 hash，迫使并发双方都要新建版本
                s.add(DisclosureNote(project_id=pid, year=YEAR, note_section="一、1", section_title="公司基本情况",
                                     text_content=f"<p>{key}公司正文</p>", sort_index=1))
            await s.commit()

        async def _seed_v1(name: str) -> None:
            async with Session() as s:
                await _save(s, sources["x"], user, name)
                await s.commit()

        snap["scenarios"]["create"] = await _race(Session, user, sources["x"], sources["y"], "并发首建")
        await _seed_v1("并发续版")
        snap["scenarios"]["append"] = await _race(Session, user, sources["y"], sources["z"], "并发续版")
        original = snap_module._lock_or_create_template
        snap_module._lock_or_create_template = _legacy_find_or_create
        try:
            snap["scenarios"]["legacy_create"] = await _race(Session, user, sources["x"], sources["y"], "对照首建")
            await _seed_v1("对照续版")
            snap["scenarios"]["legacy_append"] = await _race(Session, user, sources["y"], sources["z"], "对照续版")
        finally:
            snap_module._lock_or_create_template = original
        async with Session() as s:
            rows = (await s.execute(sa.text(
                "SELECT t.name, v.version_no, (t.current_version_id = v.id) AS is_current "
                "FROM note_content_template_versions v JOIN note_content_templates t ON t.id = v.template_id "
                "ORDER BY 1, 2"))).all()
        for name, version_no, is_current in rows:
            snap["versions"].setdefault(name, []).append([version_no, bool(is_current)])
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
    assert set(snapshot["scenarios"]) == {"create", "append", "legacy_create", "legacy_append"}


@pytest.mark.parametrize("scenario", ["legacy_create", "legacy_append"])
def test_negative_control_unlocked_save_fails_under_race(snapshot: dict[str, Any], scenario: str) -> None:
    """反向对照：首版无锁实现在同一竞态下后到者必失败 —— 证明夹具真的制造了并发。"""
    s = snapshot["scenarios"][scenario]
    assert s["second_waited"] is True and s["second"] == {"ok": False, "error": "IntegrityError"}, s


def test_concurrent_first_create_serializes_into_one_template(snapshot: dict[str, Any]) -> None:
    s = snapshot["scenarios"]["create"]
    assert s["second"]["ok"] is True, s
    assert s["second"]["template_id"] == s["first"]["template_id"]
    assert (s["first"]["version_no"], s["second"]["version_no"]) == (1, 2)
    assert snapshot["versions"]["并发首建"] == [[1, False], [2, True]]


def test_concurrent_new_versions_get_consecutive_numbers(snapshot: dict[str, Any]) -> None:
    s = snapshot["scenarios"]["append"]
    assert s["second_waited"] is True, "B 未等待 A：目录行锁没有生效"
    assert s["second"]["ok"] is True, s
    assert (s["first"]["version_no"], s["second"]["version_no"]) == (2, 3)
    assert snapshot["versions"]["并发续版"] == [[1, False], [2, False], [3, True]]
