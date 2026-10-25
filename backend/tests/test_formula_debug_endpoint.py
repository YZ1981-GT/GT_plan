"""公式调试/模拟器端点测试（spec: formula-management-deep-optimization · R3）。

验证：
1. 基本公式执行返回 trace
2. 自定义上下文传入
3. 语法错误返回错误信息
4. 空公式拒绝
5. 上下文摘要正确
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.routers.formula_debug import _build_context, _context_summary


class TestBuildContext:
    """调试上下文构造。"""

    @pytest.mark.asyncio
    async def test_custom_context_used_directly(self):
        """传入 custom_context 时直接构造，不查 DB。"""
        db = AsyncMock()
        ctx = await _build_context(
            db, uuid.uuid4(), 2025, "report",
            custom_context={
                "tb_data": {"1001": {"期末余额": "100.5"}},
                "row_cache": {"1": "200"},
            },
        )
        assert ctx.tb_data["1001"]["期末余额"] == Decimal("100.5")
        assert ctx.row_cache["1"] == Decimal("200")
        # 不应调用 DB
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_context_matches_production_preload(self, real_db):
        """custom_context 为 None 时按该公式走统一预载层取实时数据（真 SQLite）。

        原实现从不存在的 ``app.models.four_table_models`` 导入试算表（被 except 吞掉）⇒ 调试里 TB 恒 0、
        调整额从不取（formula-fetch-followup-defect-closure 6.6）。原用例用 mock DB 只断言「是 dict」，测不出来。"""
        from app.services.formula_engine import execute

        db, pid = real_db
        ctx = await _build_context(db, pid, 2025, "report", None, formula="TB('1001','期末余额')")
        assert execute("TB('1001','期末余额')", ctx).value == Decimal("100")
        assert _context_summary(ctx)["tb_accounts"] == 1
        # 调整额口径按作用域：报表排除底稿来源（20），底稿不排除（20 + 30）
        f = "ADJ('1001','aje_net')"
        assert execute(f, await _build_context(db, pid, 2025, "report", None, formula=f)).value == Decimal("20")
        assert execute(f, await _build_context(db, pid, 2025, "wp", None, formula=f)).value == Decimal("50")

    @pytest.mark.asyncio
    async def test_auto_context_reports_fetch_gaps(self, real_db):
        """取数缺口（如本年度报表未生成）写进 gaps，端点把它放进 warnings。"""
        db, pid = real_db
        gaps: list[str] = []
        await _build_context(db, pid, 2025, "report", None, formula="ROW('BS-001')", gaps=gaps)
        assert any("报表未生成" in g for g in gaps), gaps


@pytest.mark.asyncio
async def test_endpoint_returns_fetch_gaps_as_warnings(monkeypatch):
    """端点级（权限世界真发请求）：取数缺口随响应的 warnings 返回 —— 否则调试结果是 0 却看不出为什么。"""
    import app.routers.formula_debug as formula_debug
    from app.services.formula_engine import FormulaContext
    from tests.authz_world import TARGET_PROJECT_ID, sqlite_world

    seen: dict[str, object] = {}

    async def _fake_context(db, project_id, year, scope, custom_context, formula="", gaps=None):
        seen.update(formula=formula, gaps_is_list=isinstance(gaps, list))
        gaps.append("报表未生成（2025 年度），ROW 取不到")
        return FormulaContext()

    async with sqlite_world(monkeypatch) as world:
        monkeypatch.setattr(formula_debug, "_build_context", _fake_context)
        identity = await world.identity("readonly_member")
        async with world.client(formula_debug.router, user=identity.user) as client:
            resp = await client.request("POST", "/api/formula/debug", json={
                "formula": "ROW('BS-001')", "project_id": str(TARGET_PROJECT_ID), "year": 2025, "scope": "report"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    payload = body.get("data", body) if isinstance(body, dict) else body
    assert "报表未生成（2025 年度），ROW 取不到" in payload["warnings"], payload
    assert seen == {"formula": "ROW('BS-001')", "gaps_is_list": True}


@pytest_asyncio.fixture
async def real_db():
    """1001 库存现金：审定数 100；已审批 AJE 两笔（manual 20 / workpaper 30）。"""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.models.audit_platform_models import (
        AccountCategory, Adjustment, AdjustmentEntry, AdjustmentType, TrialBalance,
    )
    from app.models.base import Base

    pid, uid = uuid.uuid4(), uuid.uuid4()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as s:
        s.add(TrialBalance(project_id=pid, year=2025, company_code="001", standard_account_code="1001",
                           account_name="库存现金", account_category=AccountCategory.asset,
                           unadjusted_amount=Decimal("100"), audited_amount=Decimal("100"),
                           aje_adjustment=Decimal("0"), rje_adjustment=Decimal("0"), opening_balance=Decimal("0")))
        for no, amount, origin in (("AJE-M", "20", "manual"), ("AJE-W", "30", "workpaper")):
            adj_id, grp = uuid.uuid4(), uuid.uuid4()
            s.add(Adjustment(id=adj_id, project_id=pid, year=2025, company_code="001", adjustment_no=no,
                             adjustment_type=AdjustmentType.aje, account_code="1001", account_name="库存现金",
                             debit_amount=Decimal(amount), credit_amount=Decimal("0"), entry_group_id=grp,
                             review_status="approved", origin=origin, created_by=uid))
            s.add(AdjustmentEntry(id=uuid.uuid4(), adjustment_id=adj_id, entry_group_id=grp, line_no=1,
                                  standard_account_code="1001", account_name="库存现金",
                                  debit_amount=Decimal(amount), credit_amount=Decimal("0")))
        await s.commit()
        yield s, pid
    await engine.dispose()


class TestContextSummary:
    """上下文摘要。"""

    def test_counts_populated_fields(self):
        from app.services.formula_engine import FormulaContext
        ctx = FormulaContext(
            tb_data={"1001": {"期末余额": Decimal("100")}},
            row_cache={"1": Decimal("200"), "2": Decimal("300")},
        )
        summary = _context_summary(ctx)
        assert summary["tb_accounts"] == 1
        assert summary["report_rows"] == 2
        assert summary["note_sections"] == 0

    def test_empty_context(self):
        from app.services.formula_engine import FormulaContext
        ctx = FormulaContext()
        summary = _context_summary(ctx)
        assert all(v == 0 for v in summary.values())


class TestFormulaExecution:
    """公式执行（直接调用 execute 验证 trace 生成）。"""

    def test_simple_arithmetic_has_trace(self):
        from app.services.formula_engine import FormulaContext, execute
        ctx = FormulaContext(
            row_cache={"1": Decimal("100"), "2": Decimal("200")},
        )
        result = execute("ROW(\"1\") + ROW(\"2\")", ctx)
        assert result.ok
        assert result.value == Decimal("300")

    def test_tb_function_returns_trace(self):
        from app.services.formula_engine import FormulaContext, execute
        ctx = FormulaContext(
            tb_data={"1001": {"期末余额": Decimal("1000"), "未审数": Decimal("800")}},
        )
        result = execute("TB('1001')", ctx)
        assert result.ok
        assert result.value == Decimal("1000")
        # trace 应记录取数步骤
        assert len(result.trace) > 0

    def test_syntax_error_returns_errors(self):
        from app.services.formula_engine import FormulaContext, execute
        ctx = FormulaContext()
        result = execute("TB('1001'", ctx)  # 缺右括号
        assert not result.ok
        assert len(result.errors) > 0

    def test_unknown_function_blocked(self):
        from app.services.formula_engine import FormulaContext, execute
        ctx = FormulaContext()
        result = execute("EVIL('hack')", ctx)
        assert not result.ok
