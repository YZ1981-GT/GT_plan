"""P1.3：真实 S20 → D4 营业收入审定数端到端验证。

只读使用当前 PostgreSQL 中已存在的 S20 底稿，不创建或修改项目/TB 数据。
成功路径调用真实 S20 render strategy 和真实 auto-data resolver；异常路径只在
真实 PG 会话的第二条查询注入一个不存在表名，验证局部 SAVEPOINT 回滚后仍能
继续执行查询，并把诊断留在渲染载荷中。
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.routers.wp_render_strategies._context import RenderContext
from app.routers.wp_render_strategies._s20_revenue_deduction import render as render_s20
from app.services.auto_data_resolvers import resolve_auto_data_source


_S20_CANDIDATE_SQL = text(
    """
    SELECT wp.id AS wp_id,
           wp.project_id,
           p.name,
           p.audit_year,
           p.business_category,
           wi.wp_code,
           wi.wp_name
    FROM working_paper wp
    JOIN projects p ON p.id = wp.project_id
    JOIN wp_index wi ON wi.id = wp.wp_index_id
    WHERE p.is_deleted = false
      AND wp.is_deleted = false
      AND wi.is_deleted = false
      AND wi.wp_code = 'S20'
      AND p.audit_year IS NOT NULL
      AND EXISTS (
          SELECT 1
          FROM trial_balance tb
          WHERE tb.project_id = p.id
            AND tb.year = p.audit_year
            AND (tb.is_deleted = false OR tb.is_deleted IS NULL)
            AND (tb.standard_account_code LIKE '6001%'
                 OR tb.standard_account_code LIKE '6051%')
            AND tb.audited_amount IS NOT NULL
            AND tb.audited_amount <> 0
      )
    ORDER BY p.name
    LIMIT 1
    """
)


class _FailOnSecondExecute:
    """真实 AsyncSession 的故障注入适配器，不替换被测生产函数。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.execute_count = 0
        self.savepoint_count = 0

    def begin_nested(self):
        self.savepoint_count += 1
        return self.session.begin_nested()

    async def execute(self, statement, params=None, *args, **kwargs):
        self.execute_count += 1
        if self.execute_count == 2:
            # 该语句由真实 PG 执行并失败，确认 SAVEPOINT 而非 Python 异常吞掉了
            # 数据库错误；之后必须还能在同一外层事务中 SELECT 1。
            return await self.session.execute(
                text("SELECT * FROM p13_s20_intentionally_missing_table")
            )
        return await self.session.execute(statement, params, *args, **kwargs)


def _pg_url() -> str:
    url = str(settings.DATABASE_URL or "")
    if "postgresql" not in url:
        pytest.skip("P1.3 需要真实 PostgreSQL；当前 DATABASE_URL 非 PostgreSQL")
    return url


async def _open_readonly_pg():
    engine = create_async_engine(_pg_url(), poolclass=NullPool)
    conn = await engine.connect()
    outer = await conn.begin()
    session = AsyncSession(
        bind=conn,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    return engine, conn, outer, session


def _context(*, db, project_id: UUID, wp_id: UUID, year: int) -> RenderContext:
    return RenderContext(
        db=db,
        project_id=project_id,
        wp_id=wp_id,
        wp_code="S20",
        working_paper=None,
        classification=SimpleNamespace(sheet_name="营业收入扣除情况核查"),
        component_type="s20-revenue-deduction",
        sheet_html_data=None,
        sheet_schema=None,
        template_file_path=None,
        year=year,
        business_category="C",
    )


@pytest.mark.asyncio
async def test_s20_render_payload_contains_real_d4_audited_revenue():
    """真实 S20 strategy 载荷必须携带非零 D4 营收审定数。"""
    engine, conn, outer, db = await _open_readonly_pg()
    try:
        row = (await db.execute(_S20_CANDIDATE_SQL)).mappings().first()
        if row is None:
            pytest.skip("真实 PG 中没有带非零 6001/6051 审定数的 S20 底稿")

        expected = await resolve_auto_data_source(
            db,
            row["project_id"],
            int(row["audit_year"]),
            "revenue_audited_for_s20",
        )
        assert expected is not None
        assert expected.get("_error") is not True
        raw_total = (
            await db.execute(
                text(
                    """
                    SELECT COALESCE(SUM(audited_amount), 0)
                    FROM trial_balance
                    WHERE project_id = :project_id
                      AND year = :year
                      AND (is_deleted = false OR is_deleted IS NULL)
                      AND (standard_account_code LIKE '6001%'
                           OR standard_account_code LIKE '6051%')
                    """
                ),
                {"project_id": str(row["project_id"]), "year": int(row["audit_year"])},
            )
        ).scalar_one()

        payload = await render_s20(
            _context(
                db=db,
                project_id=row["project_id"],
                wp_id=row["wp_id"],
                year=int(row["audit_year"]),
            )
        )

        assert payload is not None
        assert payload["component_type"] == "s20-revenue-deduction"
        assert payload["auto_data_source"] == "revenue_audited_for_s20"
        auto_data = payload["auto_data"]
        assert auto_data.get("_error") is not True
        assert isinstance(auto_data["main_revenue"], (int, float))
        assert isinstance(auto_data["other_revenue"], (int, float))
        assert isinstance(auto_data["total_revenue"], (int, float))
        assert auto_data["main_revenue"] == expected["main_revenue"]
        assert auto_data["other_revenue"] == expected["other_revenue"]
        assert auto_data["total_revenue"] == pytest.approx(float(raw_total))
        assert auto_data["total_revenue"] == expected["total_revenue"]
        assert auto_data["total_revenue"] != 0
        assert "主营业务收入" in auto_data["summary"]
    finally:
        await db.close()
        await outer.rollback()
        await conn.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_s20_render_error_isolated_by_savepoint_and_keeps_diagnostic():
    """真实 PG 查询失败后，S20 返回诊断且同一外层事务仍可继续读取。"""
    engine, conn, outer, db = await _open_readonly_pg()
    try:
        faulty_db = _FailOnSecondExecute(db)
        payload = await render_s20(
            _context(
                db=faulty_db,
                project_id=uuid4(),
                wp_id=uuid4(),
                year=2025,
            )
        )

        assert faulty_db.savepoint_count >= 1
        assert faulty_db.execute_count >= 2
        assert payload is not None
        auto_data = payload["auto_data"]
        assert auto_data["_error"] is True
        assert auto_data["_error_source"] == "revenue_audited_for_s20"
        assert auto_data["_error_detail"]
        assert "p13_s20_intentionally_missing_table" in auto_data["_error_detail"]

        # 若没有回滚 SAVEPOINT，PG 会把外层事务留在 aborted 状态，这条查询会失败。
        assert (await db.execute(text("SELECT 1"))).scalar_one() == 1
    finally:
        await db.close()
        await outer.rollback()
        await conn.close()
        await engine.dispose()
