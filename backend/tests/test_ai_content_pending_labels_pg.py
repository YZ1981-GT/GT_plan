"""真实 PostgreSQL：AI 待确认列表的目标标签按真实列名取到（spec ai-content-pending-target-label）。

原缺陷：底稿标签查 ``working_paper.wp_name``，PG 上必报 UndefinedColumn（列在 ``wp_index``），被保存点吞掉 ⇒ 标签全空。
SQLite 用例建表来自 ORM，看不出「原生 SQL 写的列名在真实库里不存在」；这里用真实迁移结果的列。

隔离：同一连接里建 ``LIKE public.x INCLUDING DEFAULTS`` 的临时表（临时 schema 在 search_path 最前，遮住正式表），
只往临时表写，整个事务回滚。带反向对照：原实现那条 SQL 在同样的临时表上确实失败 —— 对照不失败说明临时表列不对，
正向断言就是空转。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.pg_only


async def _scenario() -> dict:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.database import engine
    from app.models.v3_refinement_models import AiContentLog
    from app.routers import ai_content

    out: dict = {}
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            db = AsyncSession(bind=conn)
            for table in ("wp_index", "working_paper", "disclosure_notes"):
                await db.execute(sa.text(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING DEFAULTS)"))
            pid, other_pid = uuid.uuid4(), uuid.uuid4()
            wi_d2, wi_e1, wp_d2, note = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            await db.execute(
                sa.text(
                    "INSERT INTO wp_index (id, project_id, wp_code, wp_name) VALUES "
                    "(:a, :p, 'D2', '应收账款审定表'), (:b, :p, 'E1', '货币资金审定表')"
                ),
                {"a": wi_d2, "b": wi_e1, "p": pid},
            )
            await db.execute(
                sa.text(
                    "INSERT INTO working_paper (id, project_id, wp_index_id, file_path, source_type) "
                    "VALUES (:id, :p, :wi, '/t/d2.xlsx', 'manual')"
                ),
                {"id": wp_d2, "p": pid, "wi": wi_d2},
            )
            await db.execute(
                sa.text(
                    "INSERT INTO disclosure_notes (id, project_id, year, note_section, section_title) "
                    "VALUES (:id, :p, 2025, '八、1', '货币资金')"
                ),
                {"id": note, "p": pid},
            )
            cells = [f"workpaper:{wp_d2}:E5", f"workpaper:{wi_e1}", f"note:{note}:正文第一段"]
            items = [
                AiContentLog(id=uuid.uuid4(), project_id=pid, target_cell=cell, model="m",
                             generated_content="x", confirm_action="pending")
                for cell in cells
            ]
            got = await ai_content._enrich_target_labels(db, pid, items)
            out["labels"] = [(g["target_label"], g["target_position"]) for g in got]
            other = await ai_content._enrich_target_labels(db, other_pid, items)
            out["other"] = [g["target_label"] for g in other]
            out["after"] = (await db.execute(sa.text("SELECT 1"))).scalar_one()

            # 反向对照：原实现的底稿标签 SQL 在同样的临时表上确实失败
            try:
                async with db.begin_nested():
                    await db.execute(sa.text("SELECT id, wp_name FROM working_paper"))
                out["control"] = "原 SQL 居然成功了"
            except sa.exc.DBAPIError as exc:
                out["control"] = str(exc.orig if exc.orig is not None else exc)
        finally:
            await trans.rollback()
    # 共享引擎的连接池绑在本次 asyncio.run 的事件循环上：用完释放，否则同进程下一个 asyncio.run 拿到旧循环的连接
    await engine.dispose()
    return out


def test_labels_resolve_against_real_columns():
    out = asyncio.run(_scenario())
    assert "wp_name" in out["control"] and "does not exist" in out["control"], (
        f"反向对照没复现原缺陷（{out['control']}），临时表列不对，本用例判据空转"
    )
    assert out["labels"] == [
        ("D2 应收账款审定表", "E5"),
        ("E1 货币资金审定表", None),
        ("八、1 货币资金", "正文第一段"),
    ]
    assert out["other"] == [None, None, None], "按路径项目限定：别的项目看不到这些名称"
    assert out["after"] == 1
