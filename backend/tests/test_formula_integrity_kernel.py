"""公式完整性：仅运行纯内核，不连接应用数据库。"""
from decimal import Decimal

import pytest

from app.services import formula_engine as engine


MODES = ("ast", "regex", "parallel")
BAD_VALUES = (None, "", "  ", "不是金额", True, False,
              Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"))
ROW_FORMULAS = ("ROW('BS001')", "REPORT('BS001','本期')",
                "SUM_ROW('BS001','BS003')")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("formula", ROW_FORMULAS)
@pytest.mark.parametrize("value", BAD_VALUES, ids=str)
def test_referenced_invalid_row_never_becomes_zero(monkeypatch, mode, formula, value):
    monkeypatch.setattr(engine, "_PARSE_MODE", mode)
    ctx = engine.FormulaContext.from_simple_map({}, {"BS001": value})
    result = engine.execute(formula, ctx)
    assert not result.ok, (mode, formula, value, result)
    assert result.value is None
    assert result.errors


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("formula", ROW_FORMULAS)
def test_missing_row_and_empty_range_fail(monkeypatch, mode, formula):
    monkeypatch.setattr(engine, "_PARSE_MODE", mode)
    result = engine.execute(formula, engine.FormulaContext())
    assert not result.ok
    assert result.value is None
    assert result.errors


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("formula", ROW_FORMULAS)
def test_real_zero_source_succeeds(monkeypatch, mode, formula):
    monkeypatch.setattr(engine, "_PARSE_MODE", mode)
    result = engine.execute(formula, engine.FormulaContext(row_cache={"BS001": Decimal(0)}))
    assert result.ok, result.errors
    assert result.value == Decimal(0)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("value", (None, Decimal(0), Decimal("27.50")), ids=str)
def test_ast_range_sum_uses_actual_sources(monkeypatch, mode, value):
    monkeypatch.setattr(engine, "_PARSE_MODE", mode)
    result = engine.execute("BS001:BS003", engine.FormulaContext(row_cache={"BS002": value}))
    if value is None:
        assert not result.ok
        assert result.value is None
    else:
        assert result.ok, result.errors
        assert result.value == value


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("formula", ("IF(1,7,ROW('absent'))", "IF(0,ROW('absent'),7)",
                                     "IF(1,7,SUM_ROW('X1','X3'))"))
def test_if_does_not_evaluate_unselected_source(monkeypatch, mode, formula):
    monkeypatch.setattr(engine, "_PARSE_MODE", mode)
    result = engine.execute(formula, engine.FormulaContext())
    assert result.ok, result.errors
    assert result.value == Decimal(7)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("formula", ("WP('E1','明细','D6')", 'WP ("E1", "明细", "D6")',
                                     "NOTE('五、1','合计','期初')", 'NOTE ("五、1", "合计", "期初")'))
def test_three_argument_reference_consumes_full_key(monkeypatch, mode, formula):
    monkeypatch.setattr(engine, "_PARSE_MODE", mode)
    ctx = engine.FormulaContext(wp_data={"E1": {"明细!D6": Decimal(23), "明细": Decimal(91)}},
        note_data={"五、1": {engine.note_value_key("合计", "期初"): Decimal(23), "合计": Decimal(91)}})
    result = engine.execute(formula, ctx)
    assert result.ok, result.errors
    assert result.value == Decimal(23)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("formula,expected", (
    ("IF(ROW('BS001')>0,IF(0,ROW('absent'),ROUND(ABS(-2.345),2)),ROW('absent'))", "2.35"),
    ("MAX(IF(0,ROW('absent'),MIN(3,4)),2)", "3"),
    ("IF(0,1/0,IF(1,7,ROW('absent')))", "7"),
    ("ROUND((ROW('BS001')+REPORT('BS002','本期'))/3,2)", "2.00"),
    ("ROUND(0.000000125+2500,8)", "2500.00000013"),
))
def test_formula_integrity_nested_condition_and_math_compatibility(monkeypatch, mode, formula, expected):
    monkeypatch.setattr(engine, "_PARSE_MODE", mode)
    result = engine.execute(formula, engine.FormulaContext(row_cache={"BS001": Decimal(2), "BS002": Decimal(4)}))
    assert result.ok, result.errors
    assert result.value == Decimal(expected)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("formula", ("IF(1/0,7,9)", "IF(ROW('absent'),7,9)",
    "IF(ROW('BS001'),7,9)", "IF(1,7)", "IF(1,7,9,11)"))
def test_formula_integrity_condition_failure_returns_status(monkeypatch, mode, formula):
    monkeypatch.setattr(engine, "_PARSE_MODE", mode)
    result = engine.execute(formula, engine.FormulaContext(row_cache={"BS001": None}))
    assert not result.ok
    assert result.value is None
    assert result.errors


@pytest.mark.parametrize("mode", MODES)
def test_formula_integrity_cached_ast_is_unchanged_across_contexts(monkeypatch, mode):
    from copy import deepcopy

    monkeypatch.setattr(engine, "_PARSE_MODE", mode)
    formula = "IF(ROW('BS001'),WP('E1','明细','D6'),NOTE('五、1','合计','期初'))"
    cached = engine.parse_to_ast(formula)
    snapshot = deepcopy(cached)
    for flag, wp, note, expected in ((1, 23, 7, 23), (0, 91, 2, 2), (1, 5, 8, 5)):
        ctx = engine.FormulaContext(row_cache={"BS001": Decimal(flag)},
            wp_data={"E1": {"明细!D6": Decimal(wp)}},
            note_data={"五、1": {engine.note_value_key("合计", "期初"): Decimal(note)}})
        result = engine.execute(formula, ctx)
        assert result.ok, result.errors
        assert result.value == Decimal(expected)
        assert engine.parse_to_ast(formula) is cached
        assert cached == snapshot
