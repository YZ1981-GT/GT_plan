"""真实 PostgreSQL 守卫：两处按 ``table_data`` 读附注的原生 SQL（第 26 组）。

第 17 组修章节读取时触类旁通登记了另外 4 处 ``table_data IS NOT NULL``：附注生成的上年缓存（读回后按对象过滤）与
数据校验（另有表格形状条件）判据成立不改；本文件守的是要改的两处。

═══ 为什么必须真库 ═══

两处都是原生 SQL：高级查询附注取数用 ``source_template::text`` / ``jsonb_typeof``（PostgreSQL 专有）；报表行附注引用
按 ``str(project_id)`` 绑定 UUID（SQLite 存 32 位十六进制，永远匹配不上）⇒ SQLite 测不到。
真库形态：生成链把 None 存成 JSON null（``IS NOT NULL`` 为真，2026-10-15 纯文字章节 475 行全是这种）；
SQL NULL 来自不经 ORM 赋值的写入方（不赋该列）。

═══ 判据 ═══

1. 夹具形态对照：JSON null 行 ``IS NOT NULL`` 为真、SQL NULL 行为假；
2. 高级查询附注取数（``_query_disclosure``，不带章节）：LIMIT 名额只给有表章节 —— 排在前面的纯文字章节、空对象、
   非对象不占名额；``limit=None``（唯一调用方的口径）照旧返回全部表格行；
3. 报表行附注引用的第 3 级（勾稽预设，只认「本项目存在的章节」）：SQL NULL 与 JSON null 两种没有表的章节都算存在；
4. 反向对照：两条首版 SQL 在同一夹具上分别「名额被纯文字章节占掉」「SQL NULL 章节丢失」—— 对照不成立说明夹具没复现缺陷。

═══ 隔离 ═══

scratch schema（``tmp_ntpr_*``），projects / disclosure_notes / consol_note_data 为去外键副本，结束 ``DROP SCHEMA CASCADE``。
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

from tests.test_note_text_batch_targets_pg import _enum_ddl, _fk_free_copy  # noqa: E402

YEAR = 2025
_TABLE = {"headers": ["项目", "期末余额"], "rows": [{"label": "库存现金", "values": [1]}, {"label": "合计", "values": [1]}]}
#: (章节号, 标题, table_data)；sort_order 按顺序。没有表的章节都排在有表章节前面，LIMIT 1 才能区分两种判据
_ROWS: list[tuple[str, str, Any]] = [
    ("一、1", "公司基本情况", None),          # JSON null（生成链纯文字章节）
    ("五、1", "货币资金", sa.null()),         # SQL NULL；勾稽预设 BS-002 指向它
    ("五、2", "交易性金融资产", None),        # JSON null；勾稽预设 BS-005 指向它
    ("五、3", "空表", {}),                    # 空对象：Word 导出也不出表
    ("五、4", "数组", []),                    # 非对象
    ("五、7", "有表章节", _TABLE),
]
#: 首版 SQL（只作反向对照）
_OLD_QUERY_SQL = (
    "SELECT note_section FROM disclosure_notes WHERE project_id = :pid AND year = :y "
    "AND is_deleted = false AND table_data IS NOT NULL ORDER BY sort_order NULLS LAST, note_section LIMIT 1"
)
_OLD_REFS_SQL = (
    "SELECT note_section FROM disclosure_notes WHERE project_id = :pid AND year = :y "
    "AND is_deleted = false AND table_data IS NOT NULL"
)


async def _collect() -> dict[str, Any]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.models.consol_note_data_models import ConsolNoteData
    from app.models.core import Project
    from app.models.report_models import DisclosureNote
    from app.routers.custom_query import _query_disclosure
    from app.routers.report_note_references import get_note_references_for_row

    snap: dict[str, Any] = {"harness_errors": []}
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        snap["harness_errors"].append("本守卫的判据是 PostgreSQL JSONB 语义，必须真实 PostgreSQL")
        return snap
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    admin = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off))
    schema = f"tmp_ntpr_{uuid.uuid4().hex[:10]}"
    engine = None
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool,
                                     connect_args={**ssl_off, "server_settings": {"search_path": schema}})
        md = sa.MetaData()
        for table in (Project.__table__, DisclosureNote.__table__, ConsolNoteData.__table__):
            _fk_free_copy(table, md)
        async with engine.begin() as conn:
            for ddl in _enum_ddl(Project.__table__, DisclosureNote.__table__):
                await conn.exec_driver_sql(ddl)
            await conn.run_sync(md.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        pid = uuid.uuid4()
        async with Session() as s:
            s.add(Project(id=pid, name="守卫_2025", client_name="守卫公司", template_type="soe",
                          report_scope="standalone"))
            await s.flush()
            s.add_all([DisclosureNote(project_id=pid, year=YEAR, note_section=code, section_title=title,
                                      sort_order=order, table_data=value)
                       for order, (code, title, value) in enumerate(_ROWS, start=1)])
            await s.commit()
        params = {"pid": str(pid), "y": YEAR}
        async with Session() as s:
            snap["shape"] = {code: bool(not_null) for code, not_null in (await s.execute(sa.text(
                "SELECT note_section, table_data IS NOT NULL FROM disclosure_notes WHERE project_id = :pid"),
                params)).all() if code in ("五、1", "五、2")}
        async with Session() as s:
            snap["query_limit_1"] = await _query_disclosure(s, str(pid), YEAR, {}, 1)
        async with Session() as s:
            snap["query_unlimited"] = await _query_disclosure(s, str(pid), YEAR, {}, None)
        for row_code in ("BS-002", "BS-005"):
            async with Session() as s:
                resp = await get_note_references_for_row(pid, YEAR, row_code, db=s, current_user=None)
            snap[f"refs_{row_code}"] = [[n.note_section, n.section_title, n.origin] for n in resp.notes]
        async with Session() as s:
            snap["old_query_first"] = (await s.execute(sa.text(_OLD_QUERY_SQL), params)).scalar()
            snap["old_refs_sections"] = sorted(r[0] for r in (await s.execute(sa.text(_OLD_REFS_SQL), params)).all())
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


def test_fixture_reproduces_both_null_shapes(snapshot: dict[str, Any]) -> None:
    assert snapshot["shape"] == {"五、1": False, "五、2": True}


def test_custom_query_limit_goes_to_sections_with_tables(snapshot: dict[str, Any]) -> None:
    got = snapshot["query_limit_1"]
    assert [r["note_section"] for r in got["rows"]] == ["五、7"], got
    assert got["total"] == 2, "LIMIT 1 取到的是唯一有表章节，展平两行"
    assert got["columns"][:3] == ["note_section", "section_title", "table_name"]


def test_custom_query_unlimited_returns_every_table_row(snapshot: dict[str, Any]) -> None:
    got = snapshot["query_unlimited"]
    assert [(r["note_section"], r["项目"]) for r in got["rows"]] == [("五、7", "库存现金"), ("五、7", "合计")]


@pytest.mark.parametrize("row_code,section,title", [("BS-002", "五、1", "货币资金"), ("BS-005", "五、2", "交易性金融资产")])
def test_cross_check_sees_sections_without_tables(snapshot: dict[str, Any], row_code: str, section: str, title: str):
    from app.routers.report_note_references import find_cross_check_sections_for_row

    assert section in find_cross_check_sections_for_row(row_code), "预设库前提变了，判据空转"
    assert [section, title, "cross_check"] in snapshot[f"refs_{row_code}"]


def test_negative_control_first_version_sql(snapshot: dict[str, Any]) -> None:
    """反向对照：首版 SQL 在同一夹具上 LIMIT 1 被纯文字章节占掉、SQL NULL 章节不在标题登记里。"""
    assert snapshot["old_query_first"] == "一、1", "夹具没复现「纯文字章节占 LIMIT 名额」"
    assert "五、1" not in snapshot["old_refs_sections"], "夹具没复现「SQL NULL 章节丢失」"
    assert "五、2" in snapshot["old_refs_sections"], "JSON null 行首版也读到（碰巧不漏的那一半）"
