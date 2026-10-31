"""NOTE 取数只有一个实现（spec formula-fetch-followup-defect-closure 7.2 浏览器实测发现）。

原状（逐条可打红）：
* 报表求值 ``report_engine.evaluate_formula_result``（报表生成 + 报表审核 / 表间审核 / 公式试算三个严格入口）与旧公式
  执行接口 ``FormulaEngine.execute`` 经 ``NOTEExecutor`` 取附注：它引用了 ``formula_engine`` 从未导入的 ``sa`` ⇒
  NameError 被自身 ``except`` 吞掉，**任何** NOTE 都恒为 0，严格入口也不报错（真库安徽
  ``NOTE('八、1','合计','期末余额')`` 应为 9,182,572.99，公式试算接口返回 0）；而且忽略行和列、一律取合计行第一列。
* 统一预载层 ``formula_preloader._load_note``（公式调试 / 预填）只读披露表同步数据、把第二参当字段键 ⇒ 标准写法恒取
  不到、静默为 0，公式调试不给任何提示。
* L1 ``_handle_note`` 只按第二参存取 ⇒ 同章节同一行的期末 / 期初撞成一个值。

SQLite 真库 + 真 ORM 行；期望按附注表格写死，不由被测函数推出。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.core import Project
from app.models.report_models import DisclosureNote, FinancialReport, FinancialReportType

YEAR = 2025
P = uuid.UUID("5c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e4f")
# 货币资金：主表三行，期末 / 期初两列 + 一张其余表格（只有它有「其他货币资金明细」行）
MAIN = {"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"],
        "rows": [{"label": "库存现金", "values": [1, 2]}, {"label": "银行存款", "values": [10, 20]},
                 {"label": "合计", "values": [11, 22], "is_total": True}]}
OTHER = {"name": "受限资金", "headers": ["项目", "期末余额"], "rows": [{"label": "保证金", "values": [7]}]}


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [Project.__table__, TrialBalance.__table__, DisclosureNote.__table__, FinancialReport.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: MetaData().create_all(c, tables=tables))
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        session.add(Project(id=P, name="附注取数_2025", client_name="附注取数", template_type="soe",
                            report_scope="standalone", audit_year=YEAR))
        session.add(TrialBalance(project_id=P, year=YEAR, company_code="001", standard_account_code="1001",
                                 account_name="库存现金", account_category=AccountCategory.asset,
                                 audited_amount=Decimal("1"), opening_balance=Decimal("0")))
        session.add(DisclosureNote(project_id=P, year=YEAR, note_section="五、1", section_title="货币资金",
                                   table_data={**MAIN, "_tables": [MAIN, OTHER]}))
        session.add(DisclosureNote(project_id=P, year=YEAR, note_section="五、2", section_title="已删除",
                                   table_data=MAIN, is_deleted=True))
        session.add(FinancialReport(project_id=P, year=YEAR, report_type=FinancialReportType.balance_sheet,
                                    row_code="BS-002", row_name="货币资金",
                                    current_period_amount=Decimal("11"), prior_period_amount=Decimal("22")))
        await session.flush()
        yield session
    await engine.dispose()


def _resolver(db):
    from app.services.amount_resolver import TrialBalanceResolver

    return TrialBalanceResolver(db, P, YEAR)


# ── 1. 唯一实现：按章节 / 行 / 列取，取不到写明原因 ─────────────────────────────────


@pytest.mark.asyncio
async def test_load_note_values_by_section_row_and_column(db):
    from app.services.formula_engine import note_value_key
    from app.services.formula_ref_preload import load_note_values

    refs = [("五、1", "合计", "期末余额"), ("五、1", "银行存款", "期初"), ("五、1", "合计", ""),
            ("五、1", "保证金", "期末"), ("货币资金", "合计", "期末"), ("", "合计", "期末"), ("五、2", "合计", "")]
    values, missing = await load_note_values(db, P, YEAR, refs)
    assert values == {"五、1": {note_value_key("合计", "期末余额"): Decimal("11"),
                                note_value_key("银行存款", "期初"): Decimal("20"),
                                note_value_key("合计", ""): Decimal("11"),
                                note_value_key("保证金", "期末"): Decimal("7")}}
    assert "附注没有章节 货币资金" in missing[("货币资金", "合计", "期末")]
    assert "章节编号" in missing[("货币资金", "合计", "期末")], "第一参写成标题时要提示写章节编号"
    assert "为空" in missing[("", "合计", "期末")]
    assert "附注没有章节 五、2" in missing[("五、2", "合计", "")], "已删除的章节不算"
    assert "不是标题" not in missing[("五、2", "合计", "")], "写的就是章节编号时不提示写法"


@pytest.mark.asyncio
async def test_ref_check_and_value_loading_give_the_same_missing_section_reason(db):
    """保存前的引用校验（附注公式保存 / 地址库校验）与取数同一文案：标题写法两边都提示写章节编号。

    原状：取数说「（第一参须是章节编号…）」，引用校验只说「附注没有章节 货币资金」—— 用户在保存提示里看不出错在写法。
    """
    from app.services.formula_ref_check import FormulaRefChecker
    from app.services.formula_ref_preload import load_note_values

    refs = [("货币资金", "合计", "期末"), ("五、9", "合计", "期末余额")]
    _values, missing = await load_note_values(db, P, YEAR, refs)
    checker = FormulaRefChecker(db, P, YEAR, "soe")
    for section, label, column in refs:
        verdict = await checker.check(f"NOTE('{section}','{label}','{column}')")
        assert verdict is not None and not verdict.exists
        assert verdict.reason == missing[(section, label, column)], (verdict.reason, missing)
    assert (await checker.check_note_section("货币资金")).reason == missing[("货币资金", "合计", "期末")]
    assert "不是标题" in missing[("货币资金", "合计", "期末")] and "不是标题" not in missing[("五、9", "合计", "期末余额")]

    # 本年度附注未生成（按模板判定）：标题写法同样提示，编号写法不提示
    blank = FormulaRefChecker(db, uuid.uuid4(), YEAR, "soe")
    by_title = (await blank.check("NOTE('货币资金','合计','期末')")).reason
    by_code = (await blank.check("NOTE('五、999','合计','期末')")).reason
    assert "尚未生成" in by_title and "不是标题" in by_title, by_title
    assert "尚未生成" in by_code and "不是标题" not in by_code, by_code


# ── 2. 报表求值：严格报原因、非严格按 0；能取到时取到真值（原先恒 0） ─────────────────


@pytest.mark.asyncio
async def test_report_engine_strict_entry_takes_real_value_and_reports_reason(db):
    from app.services.report_engine import evaluate_formula_result

    ok = await evaluate_formula_result("NOTE('五、1','银行存款','期初') + 1", resolver=_resolver(db),
                                       strict_context=True)
    assert ok.ok and ok.value == Decimal("21"), ok
    with pytest.raises(ValueError) as exc:
        await evaluate_formula_result("NOTE('货币资金','合计','期末')", resolver=_resolver(db), strict_context=True)
    assert "NOTE('货币资金','合计','期末')" in str(exc.value) and "附注没有章节 货币资金" in str(exc.value)


@pytest.mark.asyncio
async def test_report_engine_lenient_path_zeroes_only_what_is_missing(db):
    from app.services.report_engine import evaluate_formula_result

    res = await evaluate_formula_result("NOTE('五、1','合计','期末余额') + NOTE('货币资金','合计','期末')",
                                        resolver=_resolver(db))
    assert res.ok and res.value == Decimal("11"), res


@pytest.mark.asyncio
async def test_same_row_two_columns_do_not_collide(db):
    from app.services.report_engine import evaluate_formula_result

    res = await evaluate_formula_result("NOTE('五、1','合计','期末余额') - NOTE('五、1','合计','期初余额')",
                                        resolver=_resolver(db), strict_context=True)
    assert res.value == Decimal("-11"), "同章节同一行的期末 / 期初撞成一个值"


@pytest.mark.asyncio
async def test_cross_check_rule_reports_reason_instead_of_comparing_zero(db):
    from app.services.formula_settings.cross_check_rules import _evaluate

    value, reason = await _evaluate("NOTE('货币资金','合计','期末')", _resolver(db), {})
    assert value is None and "附注没有章节 货币资金" in reason, (value, reason)
    value, reason = await _evaluate("NOTE('五、1','合计','期末余额')", _resolver(db), {})
    assert value == Decimal("11") and reason == "", (value, reason)


# ── 3. 统一预载层（公式调试 / 预填）与旧执行接口 ───────────────────────────────────


@pytest.mark.asyncio
async def test_formula_debug_context_takes_value_and_reports_gap(db):
    from app.routers.formula_debug import _build_context
    from app.services.formula_engine import execute

    formula = "NOTE('五、1','合计','期末余额') + NOTE('货币资金','合计','期末')"
    gaps: list[str] = []
    ctx = await _build_context(db, P, YEAR, "report", None, formula=formula, gaps=gaps)
    assert execute(formula, ctx).value == Decimal("11")
    assert any("NOTE('货币资金','合计','期末')" in g and "附注没有章节 货币资金" in g for g in gaps), gaps


@pytest.mark.asyncio
async def test_legacy_execute_endpoint_takes_value_and_reports_missing(db):
    """旧执行接口（``FormulaEngine.execute`` 薄转发到中央执行合同，spec formula-hub-integrity-closure ADR-FHIC-19）：
    取得到的 NOTE 是真值；有一个取不到 ⇒ ``ok=false``、``value=None``、``state=missing``，原因进 ``errors`` 与 ``error``。

    任务 12 改写（原名 ``test_legacy_execute_endpoint_takes_value_and_warns``）：原断言 ``value == 10.0`` 且原因只在
    ``warnings`` —— 即取不到的 NOTE 按 0 参与求值、结果照常当成功返回，只看 ``value`` 的调用方会把 10 当作
    ``NOTE('五、1',…) + NOTE('五、9',…)`` 的真值。这正是中央合同要消除的「缺数按 0 冒充正常值」，旧断言固化了该缺陷。
    """
    from app.services.formula_engine import FormulaEngine

    engine = FormulaEngine()
    found = await engine.execute(db, P, YEAR, "custom", {"formula": "NOTE('五、1','银行存款','期末')"})
    assert (found["ok"], found["value"], found["state"], found["errors"], found["error"]) == (
        True, 10.0, "ok", [], None), found
    out = await engine.execute(db, P, YEAR, "custom",
                               {"formula": "NOTE('五、1','银行存款','期末') + NOTE('五、9','合计')"})
    assert (out["ok"], out["value"], out["state"]) == (False, None, "missing"), out
    assert any("NOTE('五、9','合计')" in e and "附注没有章节 五、9" in e for e in out["errors"]), out
    assert "附注没有章节 五、9" in (out["error"] or ""), out


@pytest.mark.asyncio
async def test_legacy_executors_return_real_values_or_none(db):
    """两个旧执行器不再因 NameError 恒 0：取到真值，取不到 ``None``。"""
    from app.services.formula_engine import NOTEExecutor, REPORTExecutor

    assert await NOTEExecutor.execute(db, P, YEAR, "五、1", "银行存款", "期初") == Decimal("20")
    assert await NOTEExecutor.execute(db, P, YEAR, "五、1") == Decimal("11")
    assert await NOTEExecutor.execute(db, P, YEAR, "货币资金") is None
    assert await REPORTExecutor.execute(db, P, YEAR, "BS", "BS-002") == Decimal("11")
    assert await REPORTExecutor.execute(db, P, YEAR, "BS", "BS-999") is None


# ── 4. L1：先取行 + 列键，没有时退回旧口径（第二参键） ────────────────────────────────


def test_l1_handler_reads_row_column_key_then_legacy_key():
    from app.services.formula_engine import FormulaContext, execute, note_value_key

    ctx = FormulaContext(note_data={"五、1": {note_value_key("合计", "期初余额"): Decimal("22"),
                                              note_value_key("合计", "期末余额"): Decimal("11"),
                                              "银行存款": Decimal("99")}})
    assert execute("NOTE('五、1','合计','期初余额')", ctx).value == Decimal("22")
    assert execute("NOTE('五、1','合计','期末余额')", ctx).value == Decimal("11")
    assert execute("NOTE('五、1','银行存款')", ctx).value == Decimal("99"), "旧口径（第二参键）不能丢"
