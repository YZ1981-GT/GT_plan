"""报表逐行计算与依赖缓存（spec formula-hub-integrity-closure 任务 16；需求 5.2、5.3、6.4、4.3 报表部分；ADR-FHIC-01 / 05）。

全量生成 ``ReportEngine._generate_report``、affected 重算 ``regenerate_affected``、stale 重算 ``recalculate_stale_rows``
三路共用本模块，逐行语义只此一处：

- :func:`compute_row`：外包 ``formula_warnings.collect()`` 调 ``parser.execute_with_status``；失败 ⇒ ``state != "ok"``、
  不给值；``ROW`` / ``SUM_ROW`` 引用了缓存里没有的本准则非无公式行 ⇒「引用行未就绪」（不求值）；结果为 0 而公式首个
  ``TB`` 科目本级有余额 ⇒ 只加 warning、不替换值；``ROW`` 直接引用无公式行 ⇒ warning「组成行 … 未定义公式」；
  ``TB`` 科目在试算表没有本级也没有下级 ⇒ 按 0（成功），trace 注明。算完同步缓存：成功写入、失败删除。
- :func:`build_row_cache`：库中行只有未标过期且计算版本为当前版本（``report_freshness.is_flag_stale`` 的反面）才作输入；
  :meth:`RowScope.start_cache` 再把无公式行按全量生成对它们写入的值（:data:`FORMULA_LESS_VALUE`）预置进去。
- :func:`write_row`：统一写库 —— 成功写值、计算版本、来源公式并清 ``calc_error`` 与过期；失败保留旧值（新行金额为 NULL）、
  标过期、写首条错误（≤500 字）。
- :class:`GenerateSummary`：全量生成逐行分类（值变化 / 成功未变 / 失败；金额规范化到分后比较）。
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.services.formula_grammar import ROW_PATTERN, SUM_ROW_PATTERN, SUM_TB_PATTERN, TB_PATTERN
from app.services.formula_warnings import collect as collect_formula_warnings, messages as formula_warning_messages
from app.services.report_freshness import CALC_VERSION, is_flag_stale

logger = logging.getLogger(__name__)

#: 全量生成对无公式行写入的值；三路求值前都按此预置进依赖缓存（ADR-FHIC-01）
FORMULA_LESS_VALUE = Decimal("0")
#: ``financial_report.calc_error`` 的长度上限（V229 varchar(500)）
CALC_ERROR_MAX = 500
_CENT = Decimal("0.01")


@dataclass
class RowOutcome:
    """一行的计算结果：``value`` 只在成功时有值；写库的 ``calc_error`` 取首条错误。"""

    value: Decimal | None = None
    state: str = "ok"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    inputs: list[Any] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.state == "ok"

    @property
    def calc_error(self) -> str | None:
        if self.ok:
            return None
        return (self.errors[0] if self.errors else "公式执行失败")[:CALC_ERROR_MAX]


@dataclass(frozen=True)
class RowScope:
    """本准则有效定义的行次全集、输入行、无公式行与循环引用成员。"""

    codes: frozenset[str]
    formula_less: frozenset[str]
    input_codes: frozenset[str] = frozenset()
    cycles: frozenset[str] = frozenset()

    @classmethod
    def of(cls, configs: Iterable[Any], *, cycles: Iterable[str] = ()) -> RowScope:
        configs = list(configs)
        formula_less = frozenset(c.row_code for c in configs if not (c.formula or "").strip())
        return cls(
            frozenset(c.row_code for c in configs),
            formula_less,
            frozenset(
                c.row_code for c in configs
                if c.row_code in formula_less and str(getattr(c, "formula_source", "") or "").strip().lower() == "input"
            ),
            frozenset(cycles),
        )

    def start_cache(self, rows: Iterable[Any] = ()) -> dict[str, Decimal]:
        """依赖缓存起点：库中本准则行里的就绪行（:func:`build_row_cache`）+ 无公式行预置为 :data:`FORMULA_LESS_VALUE`。"""
        cache = build_row_cache((r for r in rows if r.row_code in self.codes), current_version=CALC_VERSION)
        cache.update(dict.fromkeys(self.formula_less, FORMULA_LESS_VALUE))
        return cache


def build_row_cache(rows: Iterable[Any], *, current_version: int) -> dict[str, Decimal]:
    """库中行 → 依赖缓存：只收有值、未标过期且计算版本为 ``current_version`` 的行（过期、计算失败、旧版本的行不作输入）。"""
    return {
        row.row_code: row.current_period_amount
        for row in rows
        if row.current_period_amount is not None and not is_flag_stale(row, current_version)
    }


async def compute_row(
    parser: Any, config: Any, row_cache: dict[str, Decimal], *, mode: str, scope: RowScope,
) -> RowOutcome:
    """算一行（三路共用）并同步依赖缓存：成功写入 ``row_cache``，失败从中删除（引用它的行随后报「引用行未就绪」）。

    ``parser`` = ``ReportFormulaParser``（审定 / 未审模式由调用方设定）；``mode`` 只用于结果为 0 时的余额核对提示。
    """
    if config.row_code in scope.cycles:
        outcome = RowOutcome(
            state="cycle",
            errors=[f"循环引用：{config.row_code}（本套循环行：{'、'.join(sorted(scope.cycles))}）"],
        )
        row_cache.pop(config.row_code, None)
        return outcome

    from app.services.formula_inputs import collect as collect_formula_inputs

    with collect_formula_inputs() as inputs:
        outcome = await _evaluate(parser, config.formula, row_cache, mode=mode, scope=scope)
    outcome.inputs = list(inputs)
    if outcome.ok:
        row_cache[config.row_code] = outcome.value
    else:
        row_cache.pop(config.row_code, None)
    return outcome


async def _evaluate(
    parser: Any, formula: str | None, row_cache: dict[str, Decimal], *, mode: str, scope: RowScope,
) -> RowOutcome:
    if not (formula or "").strip():
        return RowOutcome(value=FORMULA_LESS_VALUE)
    refs = list(dict.fromkeys(ROW_PATTERN.findall(formula)))
    components = _formula_less_components(formula, refs, scope)
    manual = [code for code in components if code in scope.input_codes]
    undefined = [code for code in components if code not in scope.input_codes]
    warnings: list[str] = []
    if manual:
        warnings.append(
            f"组成行 {'、'.join(manual)} 为手工输入行；重新生成会清零，请确认手工金额后再生成"
        )
    if undefined:
        warnings.append(f"组成行 {'、'.join(undefined)} 未定义公式")
    waiting = _not_ready(formula, refs, row_cache, scope)
    if waiting:
        return RowOutcome(state="not_ready", errors=[f"引用行未就绪：{'、'.join(waiting)}（过期或计算失败）"],
                          warnings=warnings)
    try:
        with collect_formula_warnings() as fetched:
            result = await parser.execute_with_status(formula, row_cache)
    except Exception as exc:  # noqa: BLE001 —— 本行失败，不中断其余行（与改动前三路一致）
        logger.warning("报表行公式执行异常：%s", formula, exc_info=True)
        return RowOutcome(state="error", errors=[str(exc) or type(exc).__name__], warnings=warnings)
    warnings = _unique([*warnings, *result.warnings, *formula_warning_messages(fetched)])
    if not result.ok:
        errors = list(result.errors) or ["公式被拦截" if result.blocked else "公式执行失败"]
        return RowOutcome(state=result.state, errors=errors, warnings=warnings, trace=list(result.trace))
    if result.value is None:
        return RowOutcome(state="error", errors=["公式执行未返回数值"], warnings=warnings, trace=list(result.trace))
    trace = [*result.trace, *await _missing_account_notes(parser, formula)]
    value = result.value
    if value == 0:
        hint = await _tb_balance_hint(parser, formula, mode)
        if hint is not None:
            warnings.append(f"公式结果为 0，而试算表科目 {hint[0]} 本级有余额 {hint[1]}：按公式结果 0 写入（不替换），请核对公式")
    return RowOutcome(value=value, warnings=warnings, trace=trace)


def _formula_less_components(
    formula: str, refs: list[str], scope: RowScope,
) -> list[str]:
    """公式直接或区间引用到的无公式行，按首次出现顺序返回。"""
    wanted = [code for code in refs if code in scope.formula_less]
    for start, end in SUM_ROW_PATTERN.findall(formula):
        wanted.extend(sorted(code for code in scope.formula_less if start <= code <= end))
    return list(dict.fromkeys(wanted))


def _not_ready(formula: str, refs: list[str], row_cache: dict[str, Decimal], scope: RowScope) -> list[str]:
    """``ROW`` / ``SUM_ROW`` 引用的本准则行里，缓存中没有的非无公式行（过期、计算失败或尚未算到）。

    不在本准则的引用（悬空）不在此判，留给 L1 报「引用的行次不存在」。
    """
    wanted = [code for code in refs if code in scope.codes]
    for start, end in SUM_ROW_PATTERN.findall(formula):
        wanted.extend(sorted(code for code in scope.codes if start <= code <= end))
    return [code for code in dict.fromkeys(wanted) if code not in row_cache and code not in scope.formula_less]


async def _missing_account_notes(parser: Any, formula: str) -> list[str]:
    """缺科目（``TB`` 引用的科目在试算表没有本级也没有下级）按 0 取数、状态正常，trace 注明；注入了外部取数器时不判。"""
    if getattr(parser, "resolver", None) is not None:
        return []
    notes: list[str] = []
    for code in dict.fromkeys(m.group(1) for m in TB_PATTERN.finditer(SUM_TB_PATTERN.sub("", formula))):
        if not await parser._get_tb_rows_prefix(code):  # 已由取数缓存，不再查库
            notes.append(f"TB('{code}')：试算表没有该科目（含下级），按 0 计")
    return notes


async def _tb_balance_hint(parser: Any, formula: str, mode: str) -> tuple[str, Decimal] | None:
    """结果为 0 时的核对提示：公式首个 ``TB`` 科目本级在试算表有非零余额（未审模式取未审数，否则取审定数）。"""
    match = TB_PATTERN.search(formula)
    tb_row = await parser._get_tb_row(match.group(1)) if match else None
    if tb_row is None:
        return None
    amount = tb_row.unadjusted_amount if mode == "unadjusted" else tb_row.audited_amount
    return (match.group(1), amount) if amount else None


def write_row(
    row: Any, config: Any, outcome: RowOutcome, *, generated_at: Any, source_accounts: list[str] | None,
) -> None:
    """三路统一写库；有 S5 运行上下文时原子同步最终值来源。"""
    row.row_name, row.indent_level, row.is_total_row = config.row_name, config.indent_level, config.is_total_row
    context = _report_context()
    if not outcome.ok:
        row.is_stale, row.calc_error = True, outcome.calc_error
        if context is not None:
            attempt = _report_attempt(config, outcome, context, generated_at)
            prior_state = _prior_value_state(getattr(row, "provenance", None))
            row.provenance = _advance_report_provenance(
                getattr(row, "provenance", None), value_state=prior_state, attempt=attempt,
                calculation_applied=False,
            )
        return
    row.current_period_amount, row.formula_used = outcome.value, config.formula
    row.source_accounts, row.generated_at = source_accounts or None, generated_at
    row.calc_version, row.calc_error, row.is_stale = CALC_VERSION, None, False
    if context is not None:
        attempt = _report_attempt(config, outcome, context, generated_at)
        row.provenance = _advance_report_provenance(
            getattr(row, "provenance", None), value_state="auto", attempt=attempt,
            calculation_applied=True,
        )
        row.run_id = context.run_id


def _report_context() -> Any | None:
    from app.services.report_provenance import current_context

    return current_context()


def _report_attempt(config: Any, outcome: RowOutcome, context: Any, generated_at: Any) -> Any:
    from app.services.formula_provenance import build_attempt, report_definition_identity

    return build_attempt(
        domain="report",
        identity=report_definition_identity(config),
        run_id=context.run_id,
        computed_at=generated_at,
        computed_by=context.triggered_by,
        calc_version=context.calc_version,
        inputs=outcome.inputs,
        calculated_value=outcome.value if outcome.ok else None,
        calculation_status="succeeded" if outcome.ok else "failed",
        error_code=None if outcome.ok else f"REPORT_{outcome.state.upper()}",
    )


def _prior_value_state(raw: Any) -> str:
    if isinstance(raw, dict) and raw.get("value_state") in {"auto", "manual", "locked", "kept", "pending_confirm", "failed"}:
        return str(raw["value_state"])
    return "failed"


def _advance_report_provenance(
    raw: Any, *, value_state: str, attempt: Any, calculation_applied: bool,
) -> dict[str, Any]:
    from app.services.formula_provenance import FinalValueProvenanceV1, advance_final_value

    try:
        prior = FinalValueProvenanceV1.model_validate(raw) if isinstance(raw, dict) else None
    except Exception:  # 历史 / 损坏 JSON 不能让报表写入失败；成功重算自然覆盖，失败保留原文。
        if not calculation_applied:
            return raw if isinstance(raw, dict) else {}
        prior = None
    return advance_final_value(
        prior, value_slot="current", value_state=value_state,
        attempt=attempt, calculation_applied=calculation_applied,
    ).model_dump(mode="json")


def _cents(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)


def _unique(texts: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(text for text in texts if text))


@dataclass
class GenerateSummary:
    """全量生成逐行分类（``generate_all_reports(summary_out=…)`` 填写，返回 dict 不含它）。

    ``changed_rows``：成功且值变化（新行、或规范化到分后与生成前不同）；``recomputed_rows``：成功、值未变；
    ``failed_rows``：失败（``error`` / ``state``，保留旧值）。每项含 ``report_type`` / ``row_code``。
    """

    changed_rows: list[dict[str, Any]] = field(default_factory=list)
    recomputed_rows: list[dict[str, Any]] = field(default_factory=list)
    failed_rows: list[dict[str, Any]] = field(default_factory=list)

    def record(self, report_type: Any, row_code: str, before: Decimal | None, outcome: RowOutcome) -> None:
        item = {"report_type": getattr(report_type, "value", report_type), "row_code": row_code}
        if not outcome.ok:
            self.failed_rows.append({**item, "error": outcome.calc_error, "state": outcome.state})
        elif before is None or _cents(before) != _cents(outcome.value):
            self.changed_rows.append(item)
        else:
            self.recomputed_rows.append(item)
