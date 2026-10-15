"""真实 PostgreSQL 守卫：附注章节读取的「承载表格」判定（第 17 组真实写入验收，AC-2.3）。

═══ 为什么必须真库 ═══

SQL 侧判定按方言分两支（PG ``jsonb_typeof`` / SQLite ``json_type``），SQLite 端点测试只走后一支。
真库形态：``table_data`` 是未设 ``none_as_null`` 的 JSONB，ORM 写 ``None`` 存 JSON ``null`` —— 真库纯文字章节
475 行全是 JSON null、0 行 SQL NULL（2026-10-15）。首版 ``IS NOT NULL`` 在这种形态下恒真。

═══ 判据 ═══

1. 夹具形态对照：JSON null 行 ``IS NOT NULL`` 为真、``jsonb_typeof = 'null'``（与真库一致），否则测不到缺陷；
2. ``_table_payload_expr('postgresql')`` 与 Python 侧 ``has_table_payload`` 对每种取值逐值一致；
3. ``load_target_sections`` 真跑：空正文章行 = container、只有表格的父节点 = narrative；
4. 反向对照：表达式换回首版 ``IS NOT NULL``，同一夹具的章行必须变回 narrative —— 对照不变说明夹具没复现缺陷。

═══ 隔离 ═══

scratch schema（``tmp_ntbtgt_*``），projects / disclosure_notes 为去外键副本，结束 ``DROP SCHEMA CASCADE``。
``DATABASE_URL`` 非 PostgreSQL 时直接失败不 skip。
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
#: 逐值对拍的取值（含 SQL NULL）；键 = 样本章节号
_SAMPLES: dict[str, Any] = {
    "样本-json-null": None, "样本-sql-null": sa.null(), "样本-空对象": {}, "样本-空数组": [],
    "样本-数组": [{"label": "x"}], "样本-字符串": "text", "样本-数字": 0,
    "样本-空行表": {"rows": []}, "样本-单表": {"rows": [{"label": "合计", "values": [1]}]}, "样本-多表": {"_tables": [{}]},
}


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


def _generated_rows(pid: uuid.UUID) -> list[Any]:
    """真库生成形态：章行空正文、``table_data`` 显式 None（JSON null）。"""
    from app.models.report_models import DisclosureNote

    def note(code: str, title: str, order: int, **kw) -> DisclosureNote:
        kw.setdefault("table_data", None)
        return DisclosureNote(project_id=pid, year=YEAR, note_section=code, section_title=title, sort_order=order, **kw)

    return [
        note("一", "公司基本情况", 1, section_id="ch-01", level=1, text_content=""),
        note("一、1", "公司基本情况", 2, section_id="ch-01-1", parent_section_id="ch-01", text_content="<p>概况</p>"),
        note("二", "财务报表编制基础", 3, section_id="ch-02", level=1, text_content=""),
        note("二、1", "财务报表编制基础", 4, parent_section_id="ch-02", text_content="<p>持续经营</p>"),
        note("四、表格父节", "表格父节", 5, section_id="tp", text_content="",
             table_data={"rows": [{"label": "合计", "values": [1]}]}),
        note("四、表格父节、1", "表格子节", 6, parent_section_id="tp", text_content="<p>子节</p>"),
    ]


async def _kinds(Session, pid: uuid.UUID) -> dict[str, str]:
    from app.services.note_text_batch_service import load_target_sections

    async with Session() as s:
        return {t["note_section"]: t["section_kind"] for t in await load_target_sections(s, pid, YEAR, scope="all")}


async def _collect() -> dict[str, Any]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    import app.services.note_text_batch_service as svc
    from app.core.config import settings
    from app.models.core import Project
    from app.models.report_models import DisclosureNote
    from app.services.note_section_kind import has_table_payload

    snap: dict[str, Any] = {"harness_errors": [], "shape": {}, "agreement": {}, "kinds": {}, "control_kinds": {}}
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        snap["harness_errors"].append("本守卫的判据是 PostgreSQL JSONB 语义，必须真实 PostgreSQL")
        return snap
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    admin = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off))
    schema = f"tmp_ntbtgt_{uuid.uuid4().hex[:10]}"
    engine = None
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool,
                                     connect_args={**ssl_off, "server_settings": {"search_path": schema}})
        md = sa.MetaData()
        _fk_free_copy(Project.__table__, md)
        _fk_free_copy(DisclosureNote.__table__, md)
        async with engine.begin() as conn:
            for ddl in _enum_ddl(Project.__table__, DisclosureNote.__table__):
                await conn.exec_driver_sql(ddl)
            await conn.run_sync(md.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        pid, sample_pid = uuid.uuid4(), uuid.uuid4()
        async with Session() as s:
            s.add_all([Project(id=p, name=f"守卫{i}", client_name=f"守卫{i}公司", template_type="soe",
                               report_scope="standalone") for i, p in enumerate((pid, sample_pid))])
            await s.flush()
            s.add_all(_generated_rows(pid))
            s.add_all([DisclosureNote(project_id=sample_pid, year=YEAR, note_section=code, section_title=code,
                                      table_data=value) for code, value in _SAMPLES.items()])
            await s.commit()
        async with Session() as s:
            column = DisclosureNote.table_data
            for code, not_null, type_of in (await s.execute(
                    sa.select(DisclosureNote.note_section, column.is_not(None), sa.func.jsonb_typeof(column))
                    .where(DisclosureNote.project_id == pid, DisclosureNote.note_section.in_(["一", "二"])))).all():
                snap["shape"][code] = [bool(not_null), type_of]
            for code, value, in_sql in (await s.execute(
                    sa.select(DisclosureNote.note_section, column, svc._table_payload_expr("postgresql"))
                    .where(DisclosureNote.project_id == sample_pid))).all():
                snap["agreement"][code] = {"sql": bool(in_sql), "python": has_table_payload(value)}
        snap["kinds"] = await _kinds(Session, pid)
        original = svc._table_payload_expr
        svc._table_payload_expr = lambda _dialect: DisclosureNote.table_data.is_not(None)  # 首版判据，仅作反向对照
        try:
            snap["control_kinds"] = await _kinds(Session, pid)
        finally:
            svc._table_payload_expr = original
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
    assert set(snapshot["agreement"]) == set(_SAMPLES), "样本没有全部读回，逐值对拍空转"


def test_fixture_reproduces_real_db_shape(snapshot: dict[str, Any]) -> None:
    """对照：JSON null 行 ``IS NOT NULL`` 为真 —— 这正是首版判据在真库恒真的原因。"""
    assert snapshot["shape"] == {"一": [True, "null"], "二": [True, "null"]}


def test_sql_and_python_table_payload_agree(snapshot: dict[str, Any]) -> None:
    disagree = {k: v for k, v in snapshot["agreement"].items() if v["sql"] != v["python"]}
    assert disagree == {}
    assert {k for k, v in snapshot["agreement"].items() if v["sql"]} == {"样本-空行表", "样本-单表", "样本-多表"}


def test_empty_chapter_rows_are_containers_on_postgres(snapshot: dict[str, Any]) -> None:
    kinds = snapshot["kinds"]
    assert kinds["一"] == kinds["二"] == "container"
    assert kinds["四、表格父节"] == "narrative", "只有表格的父节点被误判为容器"
    assert kinds["一、1"] == kinds["二、1"] == "narrative"


def test_negative_control_first_version_predicate_misclassifies(snapshot: dict[str, Any]) -> None:
    """反向对照：首版 ``IS NOT NULL`` 下章行变回 narrative —— 证明夹具真的能区分两种判据。"""
    control = snapshot["control_kinds"]
    assert control["一"] == control["二"] == "narrative", "夹具没复现缺陷，正向断言空转"
