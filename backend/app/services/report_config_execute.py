"""报表配置「公式试算」两个执行端点（spec formula-hub-integrity-closure 需求 2.5、2.7、12.3，ADR-FHIC-19，N6）。

``POST /api/report-config/execute-formula`` / ``/execute-formulas-batch`` 的路由只做鉴权，随即转发到 :func:`execute_one` /
:func:`execute_batch`：

- 请求体是 pydantic 模型，``year`` 必填（缺失 ⇒ 422；原实现 ``body.get("year", 2024)`` 静默按 2024 年取数）；
- 有项目时走报表路径（``report_engine.evaluate_formula_result`` + ``TrialBalanceResolver``，严格上下文）**一次**求值，
  ``value`` 与 ``trace`` 出自同一次：报表路径把 ``TB`` / ``SUM_TB`` 预替换成数值，:class:`_TracingResolver` 把取到的每个值
  按 L1 同一写法（``TB('1001','期末余额') = 100``）记进 trace，后接 L1 trace（原实现 value 走报表路径、trace 另跑一次
  空上下文的 L1，trace 里的 TB 全是 0）；L1 失败 ⇒ ``value=None``、``error`` 写原因（原实现照样返回 0 且不报错）；
- batch 按行次依赖拓扑序在同一会话上串行 ``for``（原 ``asyncio.gather`` 在同一 ``AsyncSession`` 上并发）；依赖认
  ``ROW('X')`` / ``REPORT('X')`` / ``SUM_ROW('A','B')`` 函数写法与裸行次 / ``SUM(A:B)``，只等本批里有的行次（原实现
  只认裸写法，而报表配置公式的行次引用全是函数写法 ⇒ 合计行先于明细行求值）；
- 执行预算 ``formula_budget.run_with_deadline``：单条每请求 ``FORMULA_EXECUTE_TIMEOUT``、batch 整批
  ``FORMULA_BATCH_TIMEOUT``；batch 超过 :data:`BATCH_LIMIT` 条 ⇒ 422（上限依据见 spec 任务 13 实施记录）。
无项目时只按请求的 ``row_values`` / 本批已算出的行次做 L1 纯求值，不读库、不进预算。
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import User
from app.services.formula_arity import dataclass_children
from app.services.formula_budget import batch_seconds, execute_seconds, require_batch_size, run_with_deadline
from app.services.formula_engine import (
    ASTFuncCall,
    ASTRangeSum,
    ASTRowRef,
    ASTString,
    FormulaContext,
    FormulaResult,
    execute,
    parse_to_ast,
)
from app.services.formula_management.function_support_matrix import (
    Executor,
    FormulaSupportViolation,
    require_expression_support,
)

logger = logging.getLogger(__name__)

#: ``execute-formulas-batch`` 单次上限。2026-10-27 快照（85 个活项目）现算最大批量：表间审核（内置 7 + 用户规则 0）× 2
#: = 14；报表试算单个节点最多 129 行（国企单体资产负债表），一个准则全部报表类型合计 352 行（spec 任务 13 实施记录）
BATCH_LIMIT = 1000
UNSUPPORTED_ERROR_CODE = "FORMULA_FUNCTION_UNSUPPORTED"

Evaluator = Callable[[str, dict[str, Decimal]], Awaitable[dict[str, Any]]]


class ExecuteFormulaBody(BaseModel):
    """``POST /api/report-config/execute-formula`` 请求体。"""

    project_id: str | None = None
    year: int
    formula: str = ""
    #: 行次引用值（如 ``{"BS-002": 50000}``），供 ``ROW`` / ``SUM_ROW`` / 裸行次
    row_values: dict[str, Decimal] | None = None


class BatchFormula(BaseModel):
    row_code: str = ""
    formula: str = ""


class ExecuteFormulasBatchBody(BaseModel):
    """``POST /api/report-config/execute-formulas-batch`` 请求体。"""

    project_id: str | None = None
    year: int
    formulas: list[BatchFormula] = Field(default_factory=list)


def parse_project_id(raw: str | None) -> uuid.UUID | None:
    """请求体里的项目：空 ⇒ ``None``（无项目纯求值）；格式无效 ⇒ 400 ``PROJECT_ID_INVALID``。"""
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail={"error_code": "PROJECT_ID_INVALID", "message": "project_id 格式无效"}) from exc


class _TracingResolver:
    """包一层报表取数源：报表路径预替换取到的每个值按 L1 trace 写法记下来（与求值是同一次取数）。"""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.trace: list[str] = []

    def __getattr__(self, name: str) -> Any:  # db / project_id / year：报表路径据此预载 WP / NOTE
        return getattr(self._inner, name)

    async def resolve_tb(self, account_code: str, column_name: str) -> Decimal:
        value = await self._inner.resolve_tb(account_code, column_name)
        self.trace.append(f"TB('{account_code}','{column_name}') = {value}")
        return value

    async def resolve_sum(self, code_range: str, column_name: str) -> Decimal:
        value = await self._inner.resolve_sum(code_range, column_name)
        self.trace.append(f"SUM_TB('{code_range}','{column_name}') = {value}")
        return value


def _payload(result: FormulaResult, trace: list[str]) -> dict[str, Any]:
    """一次求值的返回：``ok=False`` ⇒ ``value=None``、``errors`` 非空、``error`` = 原因以「；」连接。"""
    ok = result.ok
    errors = list(result.errors) or ([] if ok else [f"求值失败（{result.state}）"])
    return {"value": float(result.value) if ok else None, "ok": ok, "state": result.state, "trace": trace,
            "errors": errors, "warnings": list(result.warnings), "error": None if ok else "；".join(errors)}


def _failed(message: str) -> dict[str, Any]:
    """没能求值的一行（解析失败、取数异常、循环依赖），形状同 :func:`_payload`。"""
    return {"value": None, "ok": False, "state": "error", "trace": [], "errors": [message], "warnings": [],
            "error": message}


async def _evaluate(db: AsyncSession, project_id: uuid.UUID, year: int, formula: str,
                    row_values: dict[str, Decimal]) -> dict[str, Any]:
    """报表路径一次求值（严格上下文）：value 与 trace 同源。"""
    from app.services.amount_resolver import TrialBalanceResolver
    from app.services.report_engine import evaluate_formula_result

    resolver = _TracingResolver(TrialBalanceResolver(db, project_id, year))
    result = await evaluate_formula_result(formula, resolver=resolver, row_cache=row_values, strict_context=True)
    return _payload(result, [*resolver.trace, *result.trace])


async def _pure(formula: str, row_values: dict[str, Decimal]) -> dict[str, Any]:
    """无项目：只按行次值做 L1 纯求值（不读库）。"""
    result = execute(formula, FormulaContext(tb_data={}, row_cache=dict(row_values)))
    return _payload(result, list(result.trace))


def _unsupported(detail: dict[str, Any]) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                         detail={"error_code": UNSUPPORTED_ERROR_CODE, **detail})


async def execute_one(db: AsyncSession, project_id: uuid.UUID | None, body: ExecuteFormulaBody) -> dict[str, Any]:
    """单条试算（路由已按 ``project_id`` 鉴权）。"""
    formula = body.formula
    if not formula:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"error_code": "FORMULA_EMPTY", "message": "公式不能为空"})
    try:
        require_expression_support(formula, Executor.REPORT_PATH)
    except FormulaSupportViolation as exc:
        raise _unsupported({"executor": exc.executor.value, "issues": exc.issues}) from exc
    row_values = dict(body.row_values or {})
    if project_id is None:
        return await _pure(formula, row_values)

    async def _run() -> dict[str, Any]:
        try:
            return await _evaluate(db, project_id, body.year, formula, row_values)
        except Exception as exc:  # noqa: BLE001 —— 上下文取不到（附注 / 底稿缺数等）⇒ 422，原因原样带回
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
                "error_code": "FORMULA_CONTEXT_UNAVAILABLE", "message": f"公式执行失败: {exc}"}) from exc

    return await run_with_deadline(db, _run, seconds=execute_seconds())


# ─── batch ────────────────────────────────────────────────────────────────────


def _row_refs(root: Any) -> tuple[set[str], list[tuple[str, str]]]:
    """公式引用的行次（``ROW('X')`` / ``REPORT('X')`` / 裸行次）与行次区间（``SUM_ROW('A','B')`` / ``SUM(A:B)``）。"""
    rows: set[str] = set()
    ranges: list[tuple[str, str]] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, ASTRowRef):
            rows.add(node.row_code)
        elif isinstance(node, ASTRangeSum):
            ranges.append((node.start_code, node.end_code))
        elif isinstance(node, ASTFuncCall) and node.name in ("ROW", "REPORT", "SUM_ROW"):
            args = [arg.value for arg in node.args if isinstance(arg, ASTString)]
            if node.name == "SUM_ROW" and len(args) >= 2:
                ranges.append((args[0], args[1]))
            elif node.name != "SUM_ROW" and args:
                rows.add(args[0])
        stack.extend(dataclass_children(node))
    return rows, ranges


def _waiting_for(code: str, rows: set[str], ranges: list[tuple[str, str]], batch_codes: set[str]) -> set[str]:
    """要先算完的本批行次（不在本批的引用不等，由求值按缺行 / 取到多少算多少处理）。"""
    waiting = {r for r in rows if r in batch_codes}
    waiting |= {c for c in batch_codes if any(lo <= c <= hi for lo, hi in ranges)}
    waiting.discard(code)
    return waiting


async def _run_batch(items: list[BatchFormula], evaluate: Evaluator) -> tuple[list[dict[str, Any]], dict[str, Decimal]]:
    """按依赖拓扑序逐条串行求值；解析失败 / 循环依赖的行如实报错，算出的值供后续行引用。"""
    results: list[dict[str, Any]] = []
    parsed: list[tuple[str, str, set[str], list[tuple[str, str]]]] = []
    for item in items:
        if not item.formula:
            continue
        try:
            rows, ranges = _row_refs(parse_to_ast(item.formula))
        except Exception as exc:  # noqa: BLE001 —— 解析失败如实记为该行失败
            results.append({"row_code": item.row_code, **_failed(str(exc))})
            continue
        parsed.append((item.row_code, item.formula, rows, ranges))
    batch_codes = {code for code, *_ in parsed}
    pending = [(code, formula, _waiting_for(code, rows, ranges, batch_codes)) for code, formula, rows, ranges in parsed]
    row_values: dict[str, Decimal] = {}
    done: set[str] = set()
    progressed = True
    while progressed:
        progressed = False
        for code, formula, waiting in pending:
            if code in done or not waiting <= done:
                continue
            try:
                outcome = await evaluate(formula, row_values)
            except Exception as exc:  # noqa: BLE001 —— 单条取数失败如实记为该行失败
                outcome = _failed(f"执行错误: {exc}")
            if outcome["value"] is not None:
                row_values[code] = Decimal(str(outcome["value"]))
            results.append({"row_code": code, **outcome})
            done.add(code)
            progressed = True
    for code, _formula, waiting in pending:
        if code not in done:
            results.append({"row_code": code, **_failed(f"循环依赖: {sorted(waiting - done)}")})
    return results, row_values


async def _audit(db: AsyncSession, user: User, project_id: uuid.UUID | None, items: list[BatchFormula],
                 results: list[dict[str, Any]], *, year: int | None = None) -> None:
    """试算结果记审计日志（统一走哈希链 ``append_audit_log``）：best_effort（ADR-ALC-07，spec audit-log-chain-integrity
    批 B 的调用点裁决，登记在 ``services/audit_chain/call_sites.py``）—— 每行一个 ``begin_nested`` 保存点，写失败只回滚
    该行并记日志，不影响返回；函数内不 commit / rollback（与批 B 在搬迁前位置 ``routers/report_config.py`` 的写法一致）。
    生产 ``get_db`` 不提交 ⇒ 这批留痕随请求会话关闭回滚（已知，交接该 spec，
    ``tests/formula_hub/test_report_trial_batch_audit_persistence.py`` 以 xfail(strict) 钉住）。

    ``year`` = 本次试算的年度，写进载荷供历史页按年度查询（需求 11.1）。
    """
    from app.services.audit_log_helper import append_audit_log

    formulas: dict[str, str] = {}
    for item in items:
        formulas.setdefault(item.row_code, item.formula)
    for r in results:
        if r.get("value") is None:
            continue
        details: dict[str, Any] = {
            "event_type": "formula_changed", "module": "report", "row_code": r["row_code"],
            "action": "execute", "old_formula": "", "new_formula": formulas.get(r["row_code"], ""),
            "result_value": str(r["value"]), "trace": r.get("trace", [])}
        if year is not None:
            details["year"] = str(year)
        try:
            async with db.begin_nested():
                await append_audit_log(db, {
                    "user_id": user.id, "project_id": project_id, "action": "formula.changed",
                    "resource_type": "report_config", "resource_id": r["row_code"],
                    "details": details,
                })
        except Exception:  # noqa: BLE001 —— best_effort：审计失败不影响主流程（保存点已回滚该行）
            logger.warning("报表配置公式试算：审计日志写入失败（不影响结果）", exc_info=True)


async def execute_batch(db: AsyncSession, user: User, project_id: uuid.UUID | None,
                        body: ExecuteFormulasBatchBody) -> dict[str, Any]:
    """批量试算（路由已按 ``project_id`` 鉴权）：超上限 422、预检全部通过才求值、整批一个时限。"""
    items = body.formulas
    require_batch_size(len(items), BATCH_LIMIT)
    issues = []
    for index, item in enumerate(items):
        try:
            require_expression_support(item.formula, Executor.REPORT_PATH)
        except FormulaSupportViolation as exc:
            issues.append({"index": index, "row_code": item.row_code, "issues": exc.issues})
    if issues:
        raise _unsupported({"executor": Executor.REPORT_PATH.value, "items": issues})
    if project_id is None:
        results, row_values = await _run_batch(items, _pure)
    else:
        async def _one(formula: str, rows: dict[str, Decimal]) -> dict[str, Any]:
            return await _evaluate(db, project_id, body.year, formula, rows)

        results, row_values = await run_with_deadline(db, lambda: _run_batch(items, _one), seconds=batch_seconds())
    await _audit(db, user, project_id, items, results, year=body.year)
    return {"results": results, "row_values": {k: float(v) for k, v in row_values.items()}}
