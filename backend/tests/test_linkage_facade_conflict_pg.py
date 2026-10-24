"""真实 PostgreSQL 守卫：溯源附加的「待调解冲突」查询不得中止调用方事务（spec deliverable-trio-generation-accuracy 16b 追加）。

═══ 回归背景（2026-10-17 Playwright 实测）═══

交付件在线编辑器「查看溯源」选任一章节，``GET …/deliverables/{id}/trace`` 恒 500：
``LinkageFacadeService._enrich_conflict_stale`` 查 ``cross_module_conflicts.target_type``，而表的目标列是
``target_module``。异常被 try/except 吞掉，但 PG 事务已 aborted ⇒ 路由随后读章节状态报
``InFailedSQLTransactionError``。溯源失败时面板不显示刷新按钮 ⇒ 章节增量刷新在真实环境里根本点不到。

═══ 为什么必须真库 ═══

「语句失败 → 事务 aborted → 后续语句全失败」是 PostgreSQL 事务语义，SQLite / mock 不会进入 aborted 状态
（mock 用例还会照单返回任意列，列名写错照样绿）。本文件带反向对照：同一条失败语句不包 SAVEPOINT 时，
后续语句确实失败 —— 对照不红，说明夹具没复现出缺陷，正向断言就是空转。

═══ 隔离 ═══

同一连接里建临时表 ``cross_module_conflicts``（``LIKE public.cross_module_conflicts``：列取自真实库的迁移结果，
不手抄；临时 schema 在 search_path 最前，遮住正式表），只往临时表写，整个事务回滚。
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
    from app.schemas.linkage_contract import TargetType
    from app.services.linkage_facade_service import LinkageFacadeService

    out: dict = {}
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            db = AsyncSession(bind=conn)
            await db.execute(sa.text(
                "CREATE TEMP TABLE cross_module_conflicts (LIKE public.cross_module_conflicts INCLUDING DEFAULTS)"))
            project_id, note_id, conflict_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            await db.execute(sa.text(
                "INSERT INTO cross_module_conflicts (id, project_id, source_module, source_id, target_module, target_id,"
                " target_field, status) VALUES (:id, :pid, 'workpaper', :sid, 'disclosure', :tid, 'text_content', 'pending')"),
                {"id": conflict_id, "pid": project_id, "sid": uuid.uuid4(), "tid": note_id})
            facade = LinkageFacadeService(db)

            # 1) 列名按真实表：附注冲突（target_module=disclosure）对上附注契约（契约里是枚举成员）
            contracts = [{"target_type": TargetType.note, "target_id": str(note_id), "status": "current"}]
            enriched = await facade._enrich_conflict_stale(project_id, contracts)
            out["status"], out["conflict_id"] = enriched[0]["status"], enriched[0].get("conflict_id")
            out["expected_conflict_id"] = str(conflict_id)

            # 2) 查询失败（复现原缺陷：目标列不存在）只回滚 SAVEPOINT，调用方事务照常可用
            await db.execute(sa.text("ALTER TABLE cross_module_conflicts RENAME COLUMN target_module TO target_kind"))
            await facade._enrich_conflict_stale(project_id, [{"target_type": "note", "target_id": "x"}])
            out["after_failure"] = (await db.execute(sa.text("SELECT 1"))).scalar_one()

            # 3) 反向对照：同一条失败语句不包 SAVEPOINT ⇒ 事务 aborted，后续语句失败
            try:
                await db.execute(sa.text("SELECT id, target_module FROM cross_module_conflicts"))
                out["control"] = "失败语句居然成功了"
            except sa.exc.DBAPIError:
                try:
                    await db.execute(sa.text("SELECT 1"))
                    out["control"] = "事务没有 aborted"
                except sa.exc.DBAPIError as exc:
                    out["control"] = type(exc.orig).__name__ if exc.orig is not None else "DBAPIError"
        finally:
            await trans.rollback()
    # 共享引擎的连接池绑在本次 asyncio.run 的事件循环上：用完释放，否则同一进程里下一个 asyncio.run 的真库用例
    # 从池里拿到旧循环的连接，报「Event loop is closed」
    await engine.dispose()
    return out


def test_conflict_query_uses_real_columns_and_never_aborts_caller_transaction():
    out = asyncio.run(_scenario())
    assert out["control"] != "失败语句居然成功了" and out["control"] != "事务没有 aborted", (
        f"反向对照没复现 PG 事务中止（{out['control']}），本用例判据空转")
    assert out["status"] == "conflict" and out["conflict_id"] == out["expected_conflict_id"], out
    assert out["after_failure"] == 1
