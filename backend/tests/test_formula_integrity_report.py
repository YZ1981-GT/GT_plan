"""报表入口的实际来源与条件短路；数据库取数另用隔离 SQLite 验证。"""
from decimal import Decimal

import pytest

from app.services import formula_engine as kernel
from app.services.formula_inputs import collect
from app.services.report_engine import evaluate_formula_result


class Resolver:
    db = None
    project_id = None
    year = None

    def __init__(self):
        self.calls = []

    async def resolve_tb(self, code, column):
        self.calls.append(("TB", code, column))
        return Decimal(4)

    async def resolve_sum(self, code, column):
        self.calls.append(("SUM_TB", code, column))
        return Decimal(4)


@pytest.mark.parametrize("mode", ("ast", "regex", "parallel"))
@pytest.mark.parametrize("formula", (
    "IF(1,7,ROW('absent'))", "IF(0,SUM_ROW('X1','X3'),7)",
    'IF(1,7,WP ("E1", "审定数"))', "IF(0,NOTE('五、1','合计'),7)",
    "IF(1,7,TB('1001','审定数'))"))
async def test_report_preloads_only_selected_branch(monkeypatch, mode, formula):
    monkeypatch.setattr(kernel, "_PARSE_MODE", mode)
    resolver = Resolver()
    with collect() as inputs:
        result = await evaluate_formula_result(formula, resolver=resolver)
    assert result.ok, result.errors
    assert result.value == Decimal(7)
    assert resolver.calls == []
    assert inputs == []


@pytest.mark.parametrize("formula", ("REPORT(BS001,'本期')", 'REPORT (BS001,"本期")',
                                     "REPORT('BS001','本期')"))
async def test_address_argument_is_not_an_independent_row_reference(formula):
    with collect() as inputs:
        result = await evaluate_formula_result(formula, resolver=Resolver(), row_cache={"BS001": Decimal(5)})
    assert result.ok, result.errors
    assert result.value == Decimal(5)
    assert len(inputs) == 1
    assert inputs[0].kind == "REPORT"
    assert inputs[0].key == "BS001|本期"
