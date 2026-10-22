"""表间审核 / 报表审核的严格取数：PREV / AUX 按值代入（spec formula-governance-coverage-closure R7a）。

修复前 PREV / AUX 在表间审核里取不到数就代入 0：另一侧恰好也是 0 时，「取不到」会被判成「相等、通过」。
"""
from __future__ import annotations

import re
import uuid
from decimal import Decimal

import pytest

from app.models.audit_platform_models import AccountCategory, TbAuxBalance, TrialBalance
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.models.report_models import FinancialReport
from app.services import formula_ref_preload as frp
from app.services.formula_settings import cross_check_rules

from ._env import BS, add_project, make_db

EXTRA = (TrialBalance, TbAuxBalance, LedgerDataset)


def _tb(pid, year, code, audited, opening=None):
    return TrialBalance(project_id=pid, year=year, company_code="001", standard_account_code=code,
                        account_name=code, account_category=AccountCategory.asset,
                        audited_amount=Decimal(audited), opening_balance=Decimal(opening or "0"))


def _aux(pid, code, aux_type, name, closing, *, aux_code=None, opening="0", dataset_id=None, year=2025):
    return TbAuxBalance(project_id=pid, year=year, company_code="001", account_code=code, aux_type=aux_type,
                        aux_code=aux_code, aux_name=name, closing_balance=Decimal(closing),
                        opening_balance=Decimal(opening), dataset_id=dataset_id)


async def _sub(db, pid, expr, **kw):
    return await frp.substitute_prev_aux(expr, db=db, project_id=pid, year=2025, **kw)


def _values(expr: str) -> list[Decimal]:
    """代入后的数值（按出现顺序；数据库数值带两位小数，按值比较）。"""
    return [Decimal(v) for v in re.findall(r"\((-?[\d.]+)\)", expr)]


def _rule(label, left, right):
    return {"rule_id": None, "label": label, "left_ref": left, "operator": "=", "right_ref": right,
            "description": "", "tolerance": None, "_editing": True}


async def _run_rules(db, pid, rules):
    await cross_check_rules.save(db, pid, loaded=None, user_id=None, rules={"cross_report_wp": rules})
    await db.commit()
    outcomes, issues = await cross_check_rules.run_user_rules(db, project_id=pid, year=2025)
    return {o.description: o.passed for o in outcomes}, {i.description for i in issues}


async def test_aux_missing_is_not_passed_even_when_other_side_is_zero():
    """核心回归：AUX 取不到数、另一侧恰好是 0 ⇒ 仍是「无法取数、不通过」，不能被当成 0 = 0。"""
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "AUX 缺数")
        db.add(FinancialReport(project_id=pid, year=2025, report_type=BS, row_code="BS-ZERO", row_name="零",
                               current_period_amount=Decimal("0")))
        await db.commit()
        passed, msgs = await _run_rules(db, pid, [_rule("缺数", "AUX('1122','客户','甲公司','期末余额')",
                                                        "ROW('BS-ZERO')")])
        assert passed == {"缺数": False}
        assert any("无法取数" in m and "1122" in m and "无辅助核算余额" in m for m in msgs), msgs


async def test_prev_without_prior_year_tb_is_not_passed():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "PREV 无上年")
        db.add(_tb(pid, 2025, "1001", "50"))  # 只有本年
        db.add(FinancialReport(project_id=pid, year=2025, report_type=BS, row_code="BS-ZERO", row_name="零",
                               current_period_amount=Decimal("0")))
        await db.commit()
        passed, msgs = await _run_rules(db, pid, [_rule("上年", "PREV('1001','期末余额')", "ROW('BS-ZERO')")])
        assert passed == {"上年": False}
        assert any("上年（2024）试算表无数据" in m for m in msgs), msgs


async def test_prev_reads_prior_year_by_prefix_and_absent_account_is_zero():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "PREV 有上年")
        db.add_all([_tb(pid, 2024, "100201", "30", opening="5"), _tb(pid, 2024, "100202", "12")])
        await db.commit()
        sub = await _sub(db, pid, "PREV('1002','期末余额') + PREV(TB('1002','年初余额')) + PREV('9999','期末余额')")
        assert sub.missing == []
        assert "PREV" not in sub.expression
        assert _values(sub.expression) == [Decimal("42"), Decimal("5"), Decimal("0")]  # 9999 上年不存在 ⇒ 合法的 0


async def test_aux_four_args_matches_item_by_name_or_code_within_active_dataset():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "AUX 取数")
        active, old = uuid.uuid4(), uuid.uuid4()
        db.add_all([LedgerDataset(id=active, project_id=pid, year=2025, status=DatasetStatus.active),
                    LedgerDataset(id=old, project_id=pid, year=2025, status=DatasetStatus.superseded)])
        db.add_all([
            _aux(pid, "112201", "客户", "甲公司", "100", aux_code="C01", opening="7", dataset_id=active),
            _aux(pid, "112202", "客户", "甲公司", "20", aux_code="C01", dataset_id=active),
            _aux(pid, "112201", "客户", "乙公司", "300", aux_code="C02", dataset_id=active),
            _aux(pid, "112201", "客户", "甲公司", "999", aux_code="C01", dataset_id=old),  # 旧版本不算
        ])
        await db.commit()
        sub = await _sub(db, pid, "AUX('1122','客户','甲公司','期末余额') - AUX('1122','客户','C02','期初余额')"
                                  " + AUX('1122','客户','期末余额')")
        assert sub.missing == []
        assert "AUX" not in sub.expression
        assert _values(sub.expression) == [Decimal("120"), Decimal("0"), Decimal("420")]


async def test_aux_unknown_item_type_or_column_are_each_reported():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "AUX 报因")
        db.add(_aux(pid, "1122", "客户", "甲公司", "100"))
        await db.commit()
        sub = await _sub(db, pid, "AUX('1122','客户','丙公司','期末余额') + AUX('1122','供应商','期末余额')"
                                  " + AUX('1122','客户','甲公司','余额')")
        assert len(sub.missing) == 3, sub.missing
        joined = "\n".join(sub.missing)
        for reason in ("没有「客户」辅助项「丙公司」", "没有「供应商」辅助核算余额", "列名「余额」无法识别"):
            assert reason in joined, joined


async def test_unrecognized_form_is_reported_and_tb_aux_is_not_mistaken_for_aux():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "写法")
        await db.commit()
        assert not frp.has_prev_or_aux("TB_AUX('1121','客户','期末余额') + TB('1001','期末余额')")
        sub = await _sub(db, pid, "PREV('1001') + TB_AUX('1121','客户','期末余额')")
        assert sub.missing and "写法无法识别" in sub.missing[0]
        assert "TB_AUX('1121','客户','期末余额')" in sub.expression  # TB_AUX 原样保留


async def test_non_strict_substitutes_zero_and_reports_nothing():
    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "非严格")
        await db.commit()
        sub = await _sub(db, pid, "AUX('1122','客户','甲公司','期末余额') + PREV('1001','期末余额')", strict=False)
        assert sub.missing == []
        assert _values(sub.expression) == [Decimal("0"), Decimal("0")] and "AUX" not in sub.expression


async def test_strict_evaluate_returns_value_when_data_exists():
    """严格入口取到数时照常求值（与 ROW 等其他函数混用）。"""
    from app.services.amount_resolver import TrialBalanceResolver

    async with make_db(extra_models=EXTRA) as factory, factory() as db:
        pid = await add_project(db, "求值")
        db.add_all([_tb(pid, 2024, "1001", "80"), _aux(pid, "1122", "客户", "甲公司", "100")])
        await db.commit()
        value, err = await cross_check_rules.evaluate_strict(
            "PREV('1001','期末余额') + AUX('1122','客户','甲公司','期末余额') - ROW('BS-001')",
            TrialBalanceResolver(db, pid, 2025), {"BS-001": Decimal("30")})
        assert (value, err) == (Decimal("150"), "")


@pytest.mark.parametrize("expr", ["PREV('1001','期末余额')", "AUX('1122','客户','甲公司','期末余额')"])
async def test_resolver_without_project_context_is_reported(expr):
    value, err = await cross_check_rules.evaluate_strict(expr, object(), {})
    assert value is None and "不可用" in err
