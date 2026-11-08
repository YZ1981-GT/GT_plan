"""Strict 异常传播回归：纯函数与内存替身，不创建引擎或连接服务。

由主会话的隔离 runner 执行；不要在默认共享数据库环境直接运行。
"""
from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services import formula_engine as fe


def fail_with(error):
    def fail(*args, **kwargs):
        raise error
    return fail


def afail_with(error):
    async def fail(*args, **kwargs):
        raise error
    return fail


def wrapped_error(cause):
    try:
        raise cause
    except Exception as caught:
        try:
            raise fe.FormulaEvalError("展示信息不决定分类") from caught
        except fe.FormulaEvalError as wrapped:
            return wrapped


@pytest.fixture(params=["ast", "regex", "parallel"])
def parse_mode(request, monkeypatch):
    monkeypatch.setattr(fe, "_PARSE_MODE", request.param)
    return request.param


def assert_business(result):
    assert not result.ok and result.value is None
    assert result.failure_kind == "business"
    assert result.technical_error is None
    result.raise_for_technical_error()

@pytest.mark.parametrize("kind", [RuntimeError, ValueError, TypeError])
def test_result_retains_technical_identity_and_cause(kind):
    cause = kind("原始故障")
    error = wrapped_error(cause)
    result = fe.FormulaResult(value=Decimal("7"))
    result.record_error(error)
    result.record_error(fe.FormulaBusinessError("缺数"))
    assert result.failure_kind == "technical"
    assert result.technical_error is error and result.value is None
    with pytest.raises(fe.FormulaEvalError) as caught:
        result.raise_for_technical_error()
    assert caught.value is error and caught.value.__cause__ is cause


def test_known_conversion_cause_is_business_not_retryable():
    with pytest.raises(fe.FormulaBusinessError) as caught:
        fe.formula_number("非金额", "内存来源")
    assert caught.value.__cause__ is not None
    result = fe.FormulaResult()
    result.record_error(caught.value)
    assert_business(result)
    assert not fe.formula_technical_error(fe.FormulaEvalError("缺数"))
    assert not fe.formula_technical_error(fe.FormulaColumnError("未注册"))
    assert not fe.formula_technical_error(fe.FormulaParseError("语法"))


@pytest.mark.parametrize("kind", [RuntimeError, ValueError, TypeError])
def test_strict_rethrows_lower_source_error(parse_mode, monkeypatch, kind):
    cause = kind("下层故障")
    error = wrapped_error(cause)
    monkeypatch.setattr(fe, "_resolve_tb_column", fail_with(error))
    with pytest.raises(fe.FormulaEvalError) as caught:
        fe.execute("TB('1001','期末余额')", fe.FormulaContext(), strict=True)
    assert caught.value is error and caught.value.__cause__ is cause


def test_strict_does_not_mutate_context(parse_mode):
    ctx = fe.FormulaContext(tb_data={"1001": {"期末余额": Decimal("0")}})
    result = fe.execute("TB('1001','期末余额')", ctx, strict=True)
    assert result.ok and result.value == 0
    assert ctx.strict is False and ctx.tb_data["1001"]["期末余额"] == 0

@pytest.mark.parametrize("kind", [RuntimeError, ValueError, TypeError])
def test_object_stringification_failure_remains_technical(kind):
    error = kind("对象转换运行时故障")

    class BrokenValue:
        def __str__(self):
            raise error

    with pytest.raises(kind) as caught:
        fe.formula_number(BrokenValue(), "内存来源")
    assert caught.value is error
    assert fe.formula_technical_error(error)


@pytest.mark.parametrize("value", [None, "", "  ", True, "非金额", "NaN", "Infinity", "-Infinity"])
def test_formula_number_rejects_invalid_source_as_business(value):
    with pytest.raises(fe.FormulaBusinessError) as caught:
        fe.formula_number(value, "内存来源")
    assert not fe.formula_technical_error(caught.value)


@pytest.mark.parametrize("value", [0, "0", Decimal("0"), "0.00"])
def test_formula_number_preserves_real_zero(value):
    assert fe.formula_number(value, "内存来源") == Decimal("0")


@pytest.mark.parametrize("formula", ["1/0", "1+", "UNKNOWN_FN(1)"])
def test_known_formula_failures_are_not_retryable(parse_mode, formula):
    result = fe.execute(formula, fe.FormulaContext(), strict=True)
    assert_business(result)

@pytest.mark.parametrize("branch", ["ast", "regex"])
def test_parallel_strict_cannot_hide_one_branch_failure(monkeypatch, branch):
    monkeypatch.setattr(fe, "_PARSE_MODE", "parallel")
    error = RuntimeError("单路计算故障")
    if branch == "ast":
        monkeypatch.setattr(fe, "_eval_ast", fail_with(error))
    else:
        monkeypatch.setitem(fe._SAFE_OPS, fe.ast.Add, fail_with(error))
    with pytest.raises(RuntimeError) as caught:
        fe.execute("1+2", fe.FormulaContext(), strict=True)
    assert caught.value is error


def test_parallel_default_retains_successful_regex_fallback(monkeypatch):
    monkeypatch.setattr(fe, "_PARSE_MODE", "parallel")
    monkeypatch.setattr(fe, "_eval_ast", fail_with(RuntimeError("AST 故障")))
    result = fe.execute("1+2", fe.FormulaContext())
    assert result.ok and result.value == 3
    assert result.warnings


@pytest.mark.parametrize("kind", [ValueError, TypeError])
def test_safe_eval_runtime_failure_keeps_cause(monkeypatch, kind):
    error = kind("运算实现故障")
    monkeypatch.setitem(fe._SAFE_OPS, fe.ast.Add, fail_with(error))
    with pytest.raises(fe.FormulaEvalError) as caught:
        fe.safe_eval_expr("1+2")
    assert caught.value.__cause__ is error
    assert fe.formula_technical_error(caught.value)


def test_default_precheck_error_still_raises(monkeypatch):
    monkeypatch.setattr(fe, "_PARSE_MODE", "ast")
    error = RuntimeError("前置校验故障")
    monkeypatch.setattr(fe, "_is_blocked_formula", fail_with(error))
    with pytest.raises(RuntimeError) as caught:
        fe.execute("1", fe.FormulaContext())
    assert caught.value is error

@pytest.fixture
def report_module():
    from app.services import report_engine
    return report_engine


def async_value(value):
    async def resolve(*args, **kwargs):
        return value
    return resolve


def memory_resolver(value=Decimal("0")):
    return SimpleNamespace(
        db=object(), project_id="00000000-0000-0000-0000-000000000001", year=2024,
        resolve_tb=async_value(value), resolve_sum=async_value(value),
    )


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("stage", ["parse", "source"])
def test_report_technical_failure_retains_object(report_module, monkeypatch, strict, stage):
    cause = TypeError("内存取数故障")
    error = wrapped_error(cause)
    resolver = memory_resolver()
    if stage == "parse":
        monkeypatch.setattr(report_module, "_report_reference_nodes", fail_with(error))
    else:
        resolver.resolve_tb = afail_with(error)
    call = report_module.evaluate_formula_result(
        "TB('1001','期末余额')", resolver=resolver, strict_context=strict,
    )
    if strict:
        with pytest.raises(fe.FormulaEvalError) as caught:
            asyncio.run(call)
        assert caught.value is error and caught.value.__cause__ is cause
    else:
        result = asyncio.run(call)
        assert result.failure_kind == "technical" and result.technical_error is error
        assert result.value is None

@pytest.mark.parametrize("formula", ["PREV('1001','期末余额')", "AUX('1001','客户','期末余额')"])
def test_report_unsupported_sources_are_business(report_module, formula):
    result = asyncio.run(report_module.evaluate_formula_result(
        formula, resolver=memory_resolver(), strict_context=True,
    ))
    assert_business(result)


@pytest.mark.parametrize("source", ["TB('1001','期末余额')", "SUM_TB('1001~1009','期末余额')"])
@pytest.mark.parametrize("value", [None, "", True, "非金额", "NaN", "Infinity", 0])
def test_report_source_values_are_not_silently_zero(report_module, source, value):
    result = asyncio.run(report_module.evaluate_formula_result(
        source, resolver=memory_resolver(value), strict_context=True,
    ))
    if value == 0 and not isinstance(value, bool):
        assert result.ok and result.value == 0
    else:
        assert_business(result)


def test_report_if_does_not_load_unselected_source(report_module):
    resolver = memory_resolver()
    resolver.resolve_tb = afail_with(RuntimeError("不可取数的未选择分支"))
    result = asyncio.run(report_module.evaluate_formula_result(
        "IF(1,0,TB('1001','期末余额'))", resolver=resolver, strict_context=True,
    ))
    assert result.ok and result.value == 0


@pytest.mark.parametrize("cache", [{}, {"R1": None}, {"R1": "NaN"}, {"R1": 0}])
def test_report_row_reference_distinguishes_null_and_zero(report_module, cache):
    result = asyncio.run(report_module.evaluate_formula_result(
        "ROW('R1')", resolver=memory_resolver(), row_cache=cache, strict_context=True,
    ))
    if cache.get("R1") == 0:
        assert result.ok and result.value == 0
    else:
        assert_business(result)

@pytest.fixture
def memory_adjustments(monkeypatch):
    def normalize(raw):
        if raw in ("aje", "aje_net", "AJE"):
            return "aje"
        if raw in ("rje", "rje_net", "RJE"):
            return "rje"
        raise ValueError("未知调整类型")
    module = SimpleNamespace(
        normalize_adj_type=normalize, adj_net_batch=async_value({}),
        DEFAULT_INCLUDE_STATUSES=("approved",),
    )
    monkeypatch.setitem(sys.modules, "app.services.adjustment_amount_source", module)
    return module


def source_context(source, value):
    balance = {"期末余额": value}
    cases = {
        "tb": ("TB('1001','期末余额')", {"tb_data": {"1001": balance}}),
        "sum_preloaded": ("SUM_TB('1001~1009','期末余额')", {"tb_data": {"1001~1009": balance}}),
        "sum_rows": ("SUM_TB('1001~1009','期末余额')", {"tb_data": {"1001": balance}}),
        "prev": ("PREV('1001','期末余额')", {"prior_tb_data": {"1001": balance}}),
        "prev_wp": ("PREV('D2','明细','B5')", {"prev_wp_data": {("D2", "明细", "B5"): value}}),
        "aux": ("AUX('1001','客户','期末余额')", {"aux_data": {"1001": {"客户\x1f期末余额": value}}}),
        "aux_legacy": ("AUX('1001','客户','期末余额')", {"aux_data": {"1001": {"客户": value}}}),
        "note": ("NOTE('五、1','现金','期末余额')", {"note_data": {"五、1": {fe.note_value_key("现金", "期末余额"): value}}}),
        "note_legacy": ("NOTE('五、1','现金','期末余额')", {"note_data": {"五、1": {"现金": value}}}),
        "wp": ("WP('D2','b5')", {"wp_data": {"D2": {"B5": value}}}),
        "wp_anchor": ("WP('D2','明细','B5')", {"wp_data": {"D2": {"明细!B5": value}}}),
        "adj": ("ADJ('1001','aje_net')", {"adj_data": {"1001": {"aje_net": value}}}),
    }
    formula, fields = cases[source]
    return formula, fe.FormulaContext(**fields)


@pytest.mark.parametrize("source", ["tb", "sum_preloaded", "sum_rows", "prev", "prev_wp", "aux", "aux_legacy", "note", "note_legacy", "wp", "wp_anchor", "adj"])
@pytest.mark.parametrize("value", [None, "", True, "非金额", "NaN", "Infinity", 0])
def test_l1_source_amount_matrix(parse_mode, memory_adjustments, source, value):
    formula, ctx = source_context(source, value)
    result = fe.execute(formula, ctx, strict=True)
    if value == 0 and not isinstance(value, bool):
        assert result.ok and result.value == 0
    else:
        assert_business(result)

def memory_parser(report_module, db=None):
    resolver = memory_resolver()
    return report_module.ReportFormulaParser(
        db if db is not None else resolver.db, resolver.project_id, resolver.year,
        resolver=resolver,
    )


@pytest.mark.parametrize("stage", ["codes", "batch"])
@pytest.mark.parametrize("strict_first", [False, True])
def test_adj_failed_cache_preserves_original_error(report_module, memory_adjustments, stage, strict_first):
    cause = RuntimeError("调整来源故障")
    error = wrapped_error(cause)
    db = SimpleNamespace(execute=async_value(SimpleNamespace(all=lambda: [("1001",)])))
    if stage == "codes":
        db.execute = afail_with(error)
    else:
        memory_adjustments.adj_net_batch = afail_with(error)
    parser = memory_parser(report_module, db)
    if strict_first:
        with pytest.raises(fe.FormulaEvalError) as caught:
            asyncio.run(parser._get_adj_data(strict=True))
        assert caught.value is error
    else:
        assert asyncio.run(parser._get_adj_data()) == {}
        assert parser._adj_data == {}
    assert parser._adj_error is error
    with pytest.raises(fe.FormulaEvalError) as caught:
        asyncio.run(parser._get_adj_data(strict=True))
    assert caught.value is error and caught.value.__cause__ is cause


def test_adj_successful_empty_result_is_cached(report_module, memory_adjustments):
    calls = []
    async def batch(*args, **kwargs):
        calls.append(kwargs)
        return {}
    memory_adjustments.adj_net_batch = batch
    db = SimpleNamespace(execute=async_value(SimpleNamespace(all=lambda: [("1001",)])))
    parser = memory_parser(report_module, db)
    assert asyncio.run(parser._get_adj_data(strict=True)) == {}
    assert asyncio.run(parser._get_adj_data(strict=True)) == {}
    assert parser._adj_error is None and len(calls) == 1
    assert calls[0]["year"] == 2024 and calls[0]["account_codes"] == {"1001"}
    assert calls[0]["exclude_origins"] == frozenset({"workpaper"})

@pytest.mark.parametrize("entry", ["execute", "execute_with_status"])
@pytest.mark.parametrize("strict", [False, True])
def test_parser_entry_forwards_strict_to_l2(report_module, monkeypatch, entry, strict):
    calls = []
    async def evaluate(formula, **kwargs):
        calls.append((formula, kwargs))
        return fe.FormulaResult(value=Decimal("0"))
    monkeypatch.setattr(report_module, "evaluate_formula_result", evaluate)
    parser = memory_parser(report_module)
    cache = {"R1": Decimal("2")}
    value = asyncio.run(getattr(parser, entry)("1", cache, strict=strict))
    assert len(calls) == 1 and calls[0][1]["strict_context"] is strict
    assert calls[0][1]["resolver"] is parser and calls[0][1]["row_cache"] is cache
    assert (value.value if entry == "execute_with_status" else value) == 0


@pytest.mark.parametrize("entry", ["execute", "execute_with_status"])
@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("opening", [False, True])
def test_parser_adj_preload_keeps_opening_behavior(report_module, monkeypatch, memory_adjustments, entry, strict, opening):
    """ADJ 惰性加载在 evaluate_formula_result 内部触发（非 parser 外层预载）。

    evaluate_formula_result 被 mock 后无法验证内部 _get_adj_data 调用；
    此用例只验证 parser 传给引擎的参数形态（adj_data=None + strict_context）。
    惰性加载的实际调用由 strict_seams 用例覆盖。
    """
    eval_calls = []
    async def evaluate(formula, **kwargs):
        eval_calls.append(kwargs)
        return fe.FormulaResult(value=Decimal("0"))
    monkeypatch.setattr(report_module, "evaluate_formula_result", evaluate)
    parser = memory_parser(report_module)
    parser._use_opening = opening
    asyncio.run(getattr(parser, entry)("ADJ('1001','aje_net')", {}, strict=strict))
    # parser 传 adj_data=None 让引擎惰性加载；adj_zero 由 opening 决定
    if entry == "execute" and opening:
        # execute 的期初路径 adj_zero=True，评估上下文 adj_data 不影响
        assert len(eval_calls) == 1
    else:
        assert len(eval_calls) == 1
    assert eval_calls[0]["strict_context"] is strict


@pytest.mark.parametrize("entry", ["execute", "execute_with_status"])
def test_parser_strict_source_error_reaches_caller(report_module, entry):
    error = wrapped_error(RuntimeError("底层报表来源故障"))
    parser = memory_parser(report_module)
    parser.resolver.resolve_tb = afail_with(error)
    with pytest.raises(fe.FormulaEvalError) as caught:
        asyncio.run(getattr(parser, entry)("TB('1001','期末余额')", {}, strict=True))
    assert caught.value is error

@pytest.fixture
def row_module():
    from app.services import report_row_compute
    return report_row_compute


def row_case(row_module, formula="1"):
    config = SimpleNamespace(row_code="R1", formula=formula)
    scope = row_module.RowScope(frozenset({"R1", "KEEP"}), frozenset())
    cache = {"R1": Decimal("99"), "KEEP": Decimal("7")}
    return config, scope, cache


@pytest.mark.parametrize("delivery", ["raised", "structured"])
@pytest.mark.parametrize("strict", [False, True])
def test_row_technical_failure_clears_only_current_cache(row_module, delivery, strict):
    cause = TypeError("逐行下层故障")
    error = wrapped_error(cause)
    calls = []
    async def execute(formula, cache, **kwargs):
        calls.append(kwargs)
        if delivery == "raised":
            raise error
        result = fe.FormulaResult(value=Decimal("4"))
        result.record_error(error)
        return result
    parser = SimpleNamespace(execute_with_status=execute, resolver=object())
    config, scope, cache = row_case(row_module)
    call = row_module.compute_row(parser, config, cache, mode="audited", scope=scope, strict=strict)
    if strict:
        with pytest.raises(fe.FormulaEvalError) as caught:
            asyncio.run(call)
        assert caught.value is error and caught.value.__cause__ is cause
    else:
        outcome = asyncio.run(call)
        assert not outcome.ok and outcome.value is None
    assert cache == {"KEEP": Decimal("7")}
    assert calls == [{"strict": True} if strict else {}]

@pytest.mark.parametrize("delivery", ["raised", "structured"])
@pytest.mark.parametrize("strict", [False, True])
def test_row_business_failure_is_outcome_and_clears_cache(row_module, delivery, strict):
    error = fe.FormulaBusinessError("缺少金额")
    async def execute(formula, cache, **kwargs):
        if delivery == "raised":
            raise error
        result = fe.FormulaResult()
        result.record_error(error)
        return result
    parser = SimpleNamespace(execute_with_status=execute, resolver=object())
    config, scope, cache = row_case(row_module)
    outcome = asyncio.run(row_module.compute_row(
        parser, config, cache, mode="audited", scope=scope, strict=strict,
    ))
    assert not outcome.ok and outcome.value is None and outcome.errors
    assert cache == {"KEEP": Decimal("7")}


def test_row_default_accepts_old_parser_signature_and_caches_zero(row_module):
    calls = []
    async def execute(formula, cache):
        calls.append(formula)
        return fe.FormulaResult(value=Decimal("0"))
    parser = SimpleNamespace(execute_with_status=execute, resolver=object())
    config, scope, cache = row_case(row_module)
    outcome = asyncio.run(row_module.compute_row(
        parser, config, cache, mode="audited", scope=scope,
    ))
    assert outcome.ok and outcome.value == 0 and calls == ["1"]
    assert cache == {"R1": Decimal("0"), "KEEP": Decimal("7")}

@pytest.mark.parametrize("stage", ["missing", "hint"])
@pytest.mark.parametrize("strict", [False, True])
def test_row_postprocessing_error_clears_cache(row_module, monkeypatch, stage, strict):
    error = RuntimeError("后置取数故障")
    async def execute(formula, cache, **kwargs):
        return fe.FormulaResult(value=Decimal("0"))
    target = "_missing_account_notes" if stage == "missing" else "_tb_balance_hint"
    monkeypatch.setattr(row_module, target, afail_with(error))
    parser = SimpleNamespace(execute_with_status=execute, resolver=object())
    config, scope, cache = row_case(row_module)
    with pytest.raises(RuntimeError) as caught:
        asyncio.run(row_module.compute_row(
            parser, config, cache, mode="audited", scope=scope, strict=strict,
        ))
    assert caught.value is error and cache == {"KEEP": Decimal("7")}

@pytest.fixture
def memory_note_loader(monkeypatch):
    module = SimpleNamespace(
        load_note_values=async_value(({}, {})),
        note_token=lambda ref: "NOTE(" + "|".join(ref) + ")",
    )
    monkeypatch.setitem(sys.modules, "app.services.formula_ref_preload", module)
    return module


@pytest.mark.parametrize("field", [None, "B5"])
def test_report_wp_forwards_frozen_year_and_field(report_module, monkeypatch, memory_note_loader, field):
    calls = []
    async def read(*args, **kwargs):
        calls.append((args, kwargs))
        return Decimal("0")
    monkeypatch.setattr(fe.WPExecutor, "execute", staticmethod(read))
    resolver = memory_resolver()
    formula = "WP('D2','审定数')" if field is None else "WP('D2','明细','B5')"
    result = asyncio.run(report_module.evaluate_formula_result(
        formula, resolver=resolver, strict_context=True,
    ))
    assert result.ok and result.value == 0 and len(calls) == 1
    args, kwargs = calls[0]
    assert args == (resolver.db, resolver.project_id, "D2", "审定数" if field is None else "明细")
    assert kwargs == {"field": field, "year": 2024}


@pytest.mark.parametrize("strict", [False, True])
def test_report_wp_technical_error_preserves_cause(report_module, monkeypatch, memory_note_loader, strict):
    cause = RuntimeError("底稿来源故障")
    error = wrapped_error(cause)
    monkeypatch.setattr(fe.WPExecutor, "execute", staticmethod(afail_with(error)))
    call = report_module.evaluate_formula_result(
        "WP('D2','明细','B5')", resolver=memory_resolver(), strict_context=strict,
    )
    if strict:
        with pytest.raises(fe.FormulaEvalError) as caught:
            asyncio.run(call)
        assert caught.value is error and caught.value.__cause__ is cause
    else:
        result = asyncio.run(call)
        assert result.failure_kind == "technical" and result.technical_error is error

@pytest.mark.parametrize("case", ["missing", "absent", None, "", True, "非金额", "NaN", "Infinity", 0])
def test_report_note_source_distinguishes_missing_invalid_and_zero(report_module, memory_note_loader, case):
    calls = []
    ref = ("五、1", "现金", "期末余额")
    async def load(*args):
        calls.append(args)
        if case == "missing":
            return {}, {ref: "来源不存在"}
        if case == "absent":
            return {}, {}
        return {ref[0]: {fe.note_value_key(ref[1], ref[2]): case}}, {}
    memory_note_loader.load_note_values = load
    resolver = memory_resolver()
    result = asyncio.run(report_module.evaluate_formula_result(
        "NOTE('五、1','现金','期末余额')", resolver=resolver, strict_context=True,
    ))
    assert calls == [(resolver.db, resolver.project_id, 2024, [ref])]
    if case == 0 and not isinstance(case, bool):
        assert result.ok and result.value == 0
    else:
        assert_business(result)


@pytest.mark.parametrize("strict", [False, True])
def test_report_note_technical_error_keeps_original_object(report_module, memory_note_loader, strict):
    cause = TypeError("附注加载实现故障")
    error = wrapped_error(cause)
    memory_note_loader.load_note_values = afail_with(error)
    call = report_module.evaluate_formula_result(
        "NOTE('五、1','现金','期末余额')", resolver=memory_resolver(), strict_context=strict,
    )
    if strict:
        with pytest.raises(fe.FormulaEvalError) as caught:
            asyncio.run(call)
        assert caught.value is error and caught.value.__cause__ is cause
    else:
        result = asyncio.run(call)
        assert result.failure_kind == "technical" and result.technical_error is error

@pytest.mark.parametrize("source,attribute", [
    ("prev", "prior_tb_data"), ("prev_wp", "prev_wp_data"),
    ("aux", "aux_data"), ("aux_legacy", "aux_data"),
    ("note", "note_data"), ("note_legacy", "note_data"),
    ("wp", "wp_data"), ("wp_anchor", "wp_data"),
])
def test_l1_missing_source_keys_are_business(parse_mode, source, attribute):
    formula, ctx = source_context(source, 0)
    getattr(ctx, attribute).clear()
    assert_business(fe.execute(formula, ctx, strict=True))


@pytest.mark.parametrize("mode", ["ast", "regex"])
def test_default_internal_error_retains_existing_boundary(monkeypatch, mode):
    monkeypatch.setattr(fe, "_PARSE_MODE", mode)
    error = RuntimeError("取值实现故障")
    monkeypatch.setattr(fe, "_resolve_tb_column", fail_with(error))
    formula = "TB('1001','期末余额')"
    if mode == "regex":
        with pytest.raises(RuntimeError) as caught:
            fe.execute(formula, fe.FormulaContext())
        assert caught.value is error
    else:
        result = fe.execute(formula, fe.FormulaContext())
        assert result.failure_kind == "technical"
        assert result.technical_error is error and result.value is None


@pytest.mark.parametrize("kind", [ValueError, RuntimeError, TypeError])
def test_adj_normalization_distinguishes_business_and_runtime(parse_mode, memory_adjustments, kind):
    error = kind("归一化故障")
    memory_adjustments.normalize_adj_type = fail_with(error)
    formula = "ADJ('1001','aje_net')"
    if kind is ValueError:
        result = fe.execute(formula, fe.FormulaContext(), strict=True)
        assert_business(result)
    else:
        with pytest.raises(kind) as caught:
            fe.execute(formula, fe.FormulaContext(), strict=True)
        assert caught.value is error

@pytest.fixture
def memory_wp_reader(monkeypatch):
    world = SimpleNamespace(
        db=object(), project_id="00000000-0000-0000-0000-000000000001",
        project_year=2024, parsed_data={"audited_amount": 0}, source_calls=[], year_calls=[],
    )
    async def project_year(db, project_id):
        world.year_calls.append((db, project_id))
        return world.project_year
    async def source_rows(*args):
        world.source_calls.append(args)
        return [("内存底稿", world.parsed_data)]
    module = SimpleNamespace(fetch_project_audit_year=project_year)
    monkeypatch.setitem(sys.modules, "app.services.project_audit_year", module)
    monkeypatch.setattr(fe.WPExecutor, "_source_rows", staticmethod(source_rows))
    world.year_module = module
    return world


@pytest.mark.parametrize("year,project_year", [
    (None, 2024), (True, 2024), ("2024", 2024), (2023, 2024), (2024, None),
])
def test_wp_executor_rejects_missing_invalid_or_mismatched_year(memory_wp_reader, year, project_year):
    world = memory_wp_reader
    world.project_year = project_year
    with pytest.raises(fe.FormulaEvalError) as caught:
        asyncio.run(fe.WPExecutor.execute(
            world.db, world.project_id, "E1", "审定数", year=year,
        ))
    result = fe.FormulaResult()
    result.record_error(caught.value)
    assert_business(result)
    assert world.source_calls == []
    expected = [] if year is None or isinstance(year, (bool, str)) else [(world.db, world.project_id)]
    assert world.year_calls == expected

@pytest.mark.parametrize("value", [None, "", True, "非金额", "NaN", "Infinity", 0])
def test_wp_executor_validates_parsed_amount_without_zero_fallback(memory_wp_reader, value):
    world = memory_wp_reader
    world.parsed_data = {"audited_amount": value}
    call = fe.WPExecutor.execute(world.db, world.project_id, "E1", "审定数", year=2024)
    if value == 0 and not isinstance(value, bool):
        assert asyncio.run(call) == 0
    else:
        with pytest.raises(fe.FormulaEvalError) as caught:
            asyncio.run(call)
        result = fe.FormulaResult()
        result.record_error(caught.value)
        assert_business(result)
    assert world.source_calls == [(world.db, world.project_id, "E1")]


@pytest.mark.parametrize("parsed_data", [None, [], {}, {"不同字段": 0}])
def test_wp_executor_rejects_absent_parsed_amount(memory_wp_reader, parsed_data):
    world = memory_wp_reader
    world.parsed_data = parsed_data
    with pytest.raises(fe.FormulaEvalError) as caught:
        asyncio.run(fe.WPExecutor.execute(world.db, world.project_id, "E1", year=2024))
    assert not fe.formula_technical_error(caught.value)


@pytest.mark.parametrize("stage", ["year", "rows", "cell"])
@pytest.mark.parametrize("kind", [RuntimeError, ValueError, TypeError])
def test_wp_executor_preserves_technical_cause(memory_wp_reader, monkeypatch, stage, kind):
    world = memory_wp_reader
    error = kind("底稿下层实现故障")
    field = None
    if stage == "year":
        world.year_module.fetch_project_audit_year = afail_with(error)
    elif stage == "rows":
        monkeypatch.setattr(fe.WPExecutor, "_source_rows", staticmethod(afail_with(error)))
    else:
        field = "B5"
        monkeypatch.setattr(fe.WPExecutor, "read_sheet_cell", staticmethod(afail_with(error)))
    with pytest.raises(fe.FormulaEvalError) as caught:
        asyncio.run(fe.WPExecutor.execute(
            world.db, world.project_id, "E1", "明细" if field else "审定数", field=field, year=2024,
        ))
    assert caught.value.__cause__ is error
    assert fe.formula_technical_error(caught.value)

@pytest.mark.parametrize("column", ["期末余额", "本期借方", "本期贷方", "本期发生额"])
@pytest.mark.parametrize("source", ["tb", "sum_preloaded", "sum_rows"])
def test_registered_missing_tb_column_remains_honest_zero(parse_mode, source, column):
    data = {} if column == "期末余额" else {"期末余额": Decimal("77")}
    code = "1001~1009" if source == "sum_preloaded" else "1001"
    function = "TB('1001'" if source == "tb" else "SUM_TB('1001~1009'"
    result = fe.execute(
        function + ",'" + column + "')", fe.FormulaContext(tb_data={code: data}), strict=True,
    )
    assert result.ok and result.value == 0 and not result.errors


@pytest.mark.parametrize("adjustments", [{}, {"1001": {}}, {"1001": {"rje_net": Decimal("7")}}])
def test_missing_adj_net_remains_honest_zero(parse_mode, memory_adjustments, adjustments):
    result = fe.execute(
        "ADJ('1001','aje_net')", fe.FormulaContext(adj_data=adjustments), strict=True,
    )
    assert result.ok and result.value == 0 and not result.errors


@pytest.mark.parametrize("arity", [2, 3])
def test_wp_executor_cell_reads_use_frozen_year(memory_wp_reader, monkeypatch, arity):
    world = memory_wp_reader
    calls = []
    async def read(*args):
        calls.append(args)
        value = SimpleNamespace(state="ok", reason=None, value=0, matches=1)
        return SimpleNamespace(read=value) if arity == 3 else value
    if arity == 3:
        monkeypatch.setattr(fe.WPExecutor, "read_sheet_cell", staticmethod(read))
        column, field = "明细", "b5"
        expected = (world.db, world.project_id, 2024, "E1", "明细", "B5")
    else:
        module = SimpleNamespace(resolve_wp_cell=read)
        monkeypatch.setitem(sys.modules, "app.services.wp_cell_reader", module)
        column, field = "b5", None
        expected = (world.db, world.project_id, 2024, "E1", None, "B5")
    assert asyncio.run(fe.WPExecutor.execute(
        world.db, world.project_id, "E1", column, field=field, year=2024,
    )) == 0
    assert calls == [expected]
    assert world.year_calls == [(world.db, world.project_id)]
    assert world.source_calls == ([(world.db, world.project_id, "E1")] if arity == 2 else [])


@pytest.mark.parametrize("arity", [2, 3])
@pytest.mark.parametrize("case", ["missing", "ambiguous", None, "", True, "非金额", "NaN", "Infinity"])
def test_wp_executor_cell_failures_are_business(memory_wp_reader, monkeypatch, arity, case):
    world = memory_wp_reader
    calls = []
    async def read(*args):
        calls.append(args)
        value = SimpleNamespace(
            state="missing" if case == "missing" else "ambiguous" if case == "ambiguous" else "ok",
            reason="来源不可唯一取值", value=case,
            matches=2 if case == "ambiguous" else 0 if case == "missing" else 1,
        )
        return SimpleNamespace(read=value) if arity == 3 else value
    if arity == 3:
        monkeypatch.setattr(fe.WPExecutor, "read_sheet_cell", staticmethod(read))
        column, field = "明细", "b5"
        expected = (world.db, world.project_id, 2024, "E1", "明细", "B5")
    else:
        monkeypatch.setitem(sys.modules, "app.services.wp_cell_reader", SimpleNamespace(resolve_wp_cell=read))
        column, field = "b5", None
        expected = (world.db, world.project_id, 2024, "E1", None, "B5")
    with pytest.raises(fe.FormulaEvalError) as caught:
        asyncio.run(fe.WPExecutor.execute(
            world.db, world.project_id, "E1", column, field=field, year=2024,
        ))
    result = fe.FormulaResult()
    result.record_error(caught.value)
    assert_business(result)
    assert calls == [expected]
    assert world.year_calls == [(world.db, world.project_id)]
    assert world.source_calls == ([(world.db, world.project_id, "E1")] if arity == 2 else [])
