"""工作底稿可编辑公式补齐函数（spec formula-governance-coverage-closure R6）。

修复前底稿求值器只真实实现 TB / SUM_TB / WP，其余函数在空上下文里交给 L1 内核 —— 保存端点按函数支持矩阵
422 拒绝；而读取 / 渲染时求值预设（不经保存端点）会静默得 0。现在 ROW / SUM_ROW / REPORT / NOTE / PREV / AUX
严格按值代入、ADJ 走统一预载层（底稿口径），取不到数写进错误清单；序时账等仍拒绝且不求值。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.audit_platform_models import (
    AccountCategory,
    Adjustment,
    AdjustmentEntry,
    AdjustmentType,
    ReviewStatus,
    TbAuxBalance,
    TrialBalance,
)
from app.models.dataset_models import LedgerDataset
from app.models.report_models import DisclosureNote, FinancialReport, FinancialReportType
from app.services.formula_engine import execute
from app.services.formula_preloader import preload
from app.services.wp_formula_eval_service import evaluate_wp_formula_expression

from ._env import BS, add_project, make_db

IS = FinancialReportType.income_statement
EXTRA = (TrialBalance, TbAuxBalance, LedgerDataset, DisclosureNote, Adjustment, AdjustmentEntry)
YEAR = 2025


def _tb(pid, year, code, audited, opening="0"):
    return TrialBalance(project_id=pid, year=year, company_code="001", standard_account_code=code,
                        account_name=code, account_category=AccountCategory.asset,
                        audited_amount=Decimal(audited), opening_balance=Decimal(opening))


def _aux(pid, code, aux_type, name, closing, *, aux_code=None, opening="0"):
    return TbAuxBalance(project_id=pid, year=YEAR, company_code="001", account_code=code, aux_type=aux_type,
                        aux_code=aux_code, aux_name=name, closing_balance=Decimal(closing),
                        opening_balance=Decimal(opening))


def _row(pid, code, current, prior=None, report_type=BS):
    return FinancialReport(project_id=pid, year=YEAR, report_type=report_type, row_code=code, row_name=code,
                           current_period_amount=None if current is None else Decimal(current),
                           prior_period_amount=None if prior is None else Decimal(prior))


_CASH = {
    "name": "货币资金",
    "headers": ["项目", "期末余额", "期初余额"],
    "rows": [
        {"label": "库存现金", "values": [376.73, 286.73], "is_total": False},
        {"label": "银行存款", "values": ["4,703,056.26", 22944619.45], "is_total": False},
        {"label": "合计", "values": [4703432.99, 22944906.18], "is_total": True},
    ],
    "_tables": [
        {"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"], "rows": "<主表副本，见下>"},
        {"name": "受限制的货币资金明细", "headers": ["项目", "期末余额", "期初余额"], "rows": [
            {"label": "履约保证金", "values": [100, None], "is_total": False},
            {"label": "合计", "values": [100, 0], "is_total": True},
        ]},
    ],
}
_CASH["_tables"][0]["rows"] = _CASH["rows"]


def _note(pid, section="八、1", table_data=None):
    return DisclosureNote(project_id=pid, year=YEAR, note_section=section, section_title="货币资金",
                          table_data=_CASH if table_data is None else table_data)


def _adj(pid, user_id, code, debit, *, origin="manual", status=ReviewStatus.approved, kind=AdjustmentType.aje):
    group = uuid.uuid4()
    head = Adjustment(id=uuid.uuid4(), project_id=pid, year=YEAR, company_code="001", adjustment_no=str(group)[:8],
                      adjustment_type=kind, account_code=code, entry_group_id=group, review_status=status,
                      origin=origin, created_by=user_id)
    line = AdjustmentEntry(adjustment_id=head.id, entry_group_id=group, line_no=1, standard_account_code=code,
                           account_name="应收账款", debit_amount=Decimal(debit), credit_amount=Decimal("0"))
    return [head, line]


async def _eval(db, pid, expr, year=YEAR):
    return await evaluate_wp_formula_expression(db, project_id=pid, year=year, expression=expr)


# ── ROW / SUM_ROW / REPORT ──────────────────────────────────────────────────────


async def test_row_sum_row_and_report_periods_read_generated_report():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "报表行")
        db.add_all([_row(pid, "BS-002", "100", "80"), _row(pid, "BS-003", "20", "5"),
                    _row(pid, "IS-001", "900", "700", IS)])
        await db.commit()
        assert await _eval(db, pid, "ROW('BS-002') + SUM_ROW('BS-002','BS-003')") == (Decimal("220"), [])
        value, errs = await _eval(db, pid, "REPORT('BS-002','期初') + REPORT('BS-002','期末') + REPORT('IS-001','上期')")
        assert (value, errs) == (Decimal("880"), [])


async def test_report_gaps_are_reported_not_zero():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "报表缺口")
        empty = await add_project(db, "报表未生成")
        db.add_all([_row(pid, "BS-002", "100", None)])
        await db.commit()
        _, errs = await _eval(db, empty, "ROW('BS-002')")
        assert any("本年度（2025）报表未生成" in e for e in errs), errs
        _, errs = await _eval(db, pid, "ROW('BS-404') + REPORT('BS-002','期初') + REPORT('BS-002','某期') "
                                       "+ SUM_ROW('CF-001','CF-009')")
        joined = "\n".join(errs)
        for reason in ("报表行 BS-404 不存在", "报表行 BS-002 上期金额为空", "期间「某期」无法识别",
                       "报表行区间 CF-001~CF-009 无数据"):
            assert reason in joined, joined


# ── NOTE ───────────────────────────────────────────────────────────────────────


async def test_note_reads_main_table_then_other_tables_with_column_shorthand():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "附注")
        db.add(_note(pid))
        await db.commit()
        value, errs = await _eval(db, pid, "NOTE('八、1','合计','期末余额') - NOTE('八、1','银行存款','期末') "
                                           "+ NOTE('八、1','履约保证金','期末余额') + NOTE('八、1','库存现金')")
        assert errs == []
        # 合计取主表（不是受限制明细表的合计）；「期末」唯一对应「期末余额」；两参取第一个数据列
        assert value == Decimal("4703432.99") - Decimal("4703056.26") + Decimal("100") + Decimal("376.73")


async def test_note_gaps_are_reported():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "附注缺口")
        wide = {"headers": ["项目", "期末账面余额", "期末坏账准备"],
                "rows": [{"label": "合计", "values": [10, 2], "is_total": True}]}
        db.add_all([_note(pid), _note(pid, "八、5", wide)])
        await db.commit()
        _, errs = await _eval(db, pid, "NOTE('八、99','合计','期末余额') + NOTE('八、1','不存在行','期末余额')"
                                       " + NOTE('八、1','合计','本期发生额') + NOTE('八、1','履约保证金','期初余额')"
                                       " + NOTE('八、5','合计','期末')")
        joined = "\n".join(errs)
        for reason in ("附注没有章节 八、99", "没有「不存在行」行", "没有「本期发生额」列",
                       "「履约保证金」行「期初余额」列为空", "列「期末」对应多列（期末账面余额、期末坏账准备）"):
            assert reason in joined, joined


# ── PREV / AUX ─────────────────────────────────────────────────────────────────


async def test_prev_reads_prior_year_and_prev_tb_nesting_is_not_broken_by_tb_substitution():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "上年")
        db.add_all([_tb(pid, 2024, "1001", "80", opening="10"), _tb(pid, 2025, "1001", "50")])
        await db.commit()
        value, errs = await _eval(db, pid, "PREV(TB('1001','年初余额')) + PREV('1001','期末余额') + TB('1001','期末余额')")
        assert (value, errs) == (Decimal("140"), [])
        _, errs = await _eval(db, pid, "PREV('1001','期末余额')", year=2024)
        # 上年来源同项目上年 → 上年项目（prior_year_context，R2.4）：本项目无 2023 年试算表、也没有可认的上年项目
        assert any("本项目没有 2023 年试算表" in e for e in errs), errs


async def test_aux_four_three_and_two_arg_forms():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "辅助")
        db.add_all([_aux(pid, "112201", "客户", "甲公司", "100", aux_code="C01", opening="7"),
                    _aux(pid, "112201", "客户", "乙公司", "300", aux_code="C02"),
                    _aux(pid, "112201", "部门", "销售部", "400")])
        await db.commit()
        value, errs = await _eval(db, pid, "AUX('1122','客户','甲公司','期末余额') + AUX('1122','乙公司','期末')"
                                           " + AUX('1122','客户','期末余额') + AUX('1122','C01','期初')")
        # 四参按类型 + 辅助项；三参第二参不是类型时按辅助项（地址选择器写法）；类型合计；期初 = 期初余额
        assert (value, errs) == (Decimal("100") + Decimal("300") + Decimal("400") + Decimal("7"), [])


async def test_aux_gaps_and_ambiguous_item_are_reported():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "辅助缺口")
        db.add_all([_aux(pid, "1122", "客户", "华东公司", "10"), _aux(pid, "1122", "供应商", "华东公司", "20")])
        await db.commit()
        _, errs = await _eval(db, pid, "AUX('1122','华东公司','期末余额') + AUX('2202','供应商','期末余额')"
                                       " + AUX('1122','客户','丙公司','期末余额')")
        joined = "\n".join(errs)
        for reason in ("出现在多个辅助类型（供应商、客户）下", "科目 2202 本年无辅助核算余额", "没有「客户」辅助项「丙公司」"):
            assert reason in joined, joined


# ── ADJ（底稿口径） ─────────────────────────────────────────────────────────────


async def test_adj_uses_workpaper_scope_and_only_approved_entries():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "调整")
        user = uuid.uuid4()
        for objs in (_adj(pid, user, "1122", "100"), _adj(pid, user, "1122", "30", origin="workpaper"),
                     _adj(pid, user, "1122", "999", status=ReviewStatus.draft)):
            db.add_all(objs)
        await db.commit()
        # 底稿口径含底稿来源分录（130）；报表口径排除底稿来源（100）—— 同一数据两种口径，证明不是巧合
        assert await _eval(db, pid, "ADJ('1122','aje_net') + ADJ('9999','aje_net')") == (Decimal("130"), [])
        report_ctx = await preload(db, pid, YEAR, ["ADJ('1122','aje_net')"], adj_exclude_origins=frozenset({"workpaper"}))
        assert execute("ADJ('1122','aje_net')", report_ctx).value == Decimal("100")


# ── 混合 / 不支持 / 写法 ─────────────────────────────────────────────────────────


async def test_mixed_formula_and_whitespace_tolerant_tb():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "混合")
        db.add_all([_tb(pid, 2025, "1001", "50"), _tb(pid, 2024, "1001", "8"), _row(pid, "BS-002", "100"),
                    _aux(pid, "1122", "客户", "甲公司", "11"), _note(pid)])
        await db.commit()
        value, errs = await _eval(db, pid, "=TB('1001', '期末余额') + ROW('BS-002') - PREV('1001','期末余额')"
                                           " + AUX('1122','客户','甲公司','期末余额') + ROUND(NOTE('八、1','库存现金','期末余额'), 0)")
        assert (value, errs) == (Decimal("50") + Decimal("100") - Decimal("8") + Decimal("11") + Decimal("377"), [])


@pytest.mark.parametrize(("expr", "fn"), [
    ("LEDGER('6001','借','全年')", "LEDGER"),
    ("COUNT_LEDGER('6001','借','全年')", "COUNT_LEDGER"),
    ("TB_AUX('1121','客户','期末余额') + 1", "TB_AUX"),
    # PREV 三参自 spec formula-fetch-and-wp-generation-defect-closure R2 起支持（上年同底稿取数），
    # 见 test_prev_prior_wp_field.py
])
async def test_unsupported_functions_are_not_evaluated_to_zero(expr, fn):
    class _NoDb:  # 不支持就不该碰数据库
        def __getattr__(self, name):
            raise AssertionError(f"不支持的函数不应取数：{name}")

    value, errs = await evaluate_wp_formula_expression(_NoDb(), project_id=uuid.uuid4(), year=YEAR, expression=expr)
    assert value == Decimal("0") and errs and errs[0].startswith(f"{fn}："), errs


async def test_unrecognized_call_form_is_reported_not_silently_zero():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "写法")
        await db.commit()
        for expr in ('TB("1001","期末余额")', "ROW(BS-002)", "NOTE('八、1')"):
            value, errs = await _eval(db, pid, expr)
            assert value == Decimal("0") and any("写法无法识别" in e for e in errs), (expr, errs)


# ── 统一预载层（R6.5，预填充同一入口） ──────────────────────────────────────────


async def test_preload_aux_and_report_rows_reach_l1_and_record_gaps():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "预载")
        db.add_all([_aux(pid, "1122", "客户", "甲公司", "100"), _aux(pid, "1122", "客户", "乙公司", "300"),
                    _row(pid, "IS-019", "55")])
        await db.commit()
        formulas = ["AUX('1122','客户','甲公司','期末余额')", "AUX('1122','客户','期末余额')", "ROW('IS-019')",
                    "AUX('1122','客户','丙公司','期末余额')"]
        gaps: list[str] = []
        ctx = await preload(db, pid, YEAR, formulas, adj_exclude_origins=frozenset(), gaps=gaps)
        # 四参取单个辅助项（不是该类型合计）；三参类型合计；报表行由预载层自带（调用方没给 row_cache）
        assert [execute(f, ctx).value for f in formulas[:3]] == [Decimal("100"), Decimal("400"), Decimal("55")]
        assert any("丙公司" in g for g in gaps), gaps
        ctx2 = await preload(db, pid, YEAR, ["ROW('IS-019')"], row_cache={"IS-019": Decimal("1")})
        assert execute("ROW('IS-019')", ctx2).value == Decimal("1")  # 调用方给了 row_cache 就用调用方的


async def test_preload_without_gaps_keeps_lenient_behaviour():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "非严格")
        await db.commit()
        ctx = await preload(db, pid, YEAR, ["AUX('1122','客户','甲公司','期末余额') + ROW('BS-001')"])
        assert execute("AUX('1122','客户','甲公司','期末余额') + ROW('BS-001')", ctx).value == Decimal("0")
