"""中央执行合同（spec formula-hub-integrity-closure ADR-FHIC-19；需求 2.1、2.2、2.4、4.3）。

``POST /api/formula/execute`` / ``/batch-execute``（经 ``FormulaEngine.execute`` / ``batch_execute`` 薄转发）的唯一求值实现，
``/api/formula/debug`` 共用同一预检。:func:`execute_central` 四步：

1. 预检 :func:`precheck`：表达式里**全部**函数调用名（``function_support_matrix.called_function_names``）逐个分类 ——
   矩阵登记的取数函数查 ``central_batch`` 列；L1 内置纯函数（``formula_arity.BUILTIN_FUNCTION_NAMES``）与已注册自定义
   函数放行；其余一律 :class:`FormulaSupportViolation`（路由转 422 ``FORMULA_FUNCTION_UNSUPPORTED``，不求值、不取数）。
2. 统一预载层 ``formula_preloader.preload``（试算表叶子口径、调整额、辅助核算、报表行、附注、上年、序时账），取数缺口
   记进 ``gaps``；调整额不排除底稿来源（口径矩阵第 2 行，与原实现、底稿 ``ADJ()`` 同口径）。
3. 缺科目：公式引用的试算表科目码（``TB`` / ``SUM_TB`` 首参，含区间；``PREV(TB(…))`` 取上年、不算）对本项目年度
   ``trial_balance`` 判有无匹配行（前缀 / 区间，与预载同口径）：预载已读的码直接用预载读到的行（``tb_presence``），
   预载没读的码才另做一次 ``EXISTS``；零命中记「{年度} 年度试算表无科目 {码}」。
4. L1 ``execute``；预载与求值包在 ``formula_warnings.collect()`` 里，父子不符等取数告警并入 ``warnings``。

返回 ``{value, ok, state, errors, warnings, formula, error}``：``ok = L1 ok 且无取数缺口且无缺科目``；``ok=False`` 时
``value=None``、``errors`` 非空、``error`` = 各条原因以「；」连接。``state``：L1 求值失败照 L1（``blocked`` 拦截 /
``damaged`` 解析失败 / ``error`` 除零、ROW 缺行、未注册列名、参数个数不符等）；L1 成功但缺科目或有取数缺口 ⇒ ``missing``；
否则 ``ok``。空公式与 L1 同口径（0、``ok``），不读库。
"""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.services import formula_warnings
from app.services.formula_arity import BUILTIN_FUNCTION_NAMES, dataclass_children
from app.services.formula_engine import _REGISTRY, ASTFuncCall, ASTString, execute, parse_to_ast
from app.services.formula_management.function_support_matrix import (
    FUNCTIONS,
    Executor,
    FormulaSupportViolation,
    called_function_names,
    require_function_support,
)
from app.services.formula_preloader import preload
from app.services.tb_leaf_codes import scope_for_year

EXECUTOR = Executor.CENTRAL_BATCH
UNSUPPORTED_ERROR_CODE = "FORMULA_FUNCTION_UNSUPPORTED"
_UNKNOWN_REASON = "未注册的函数（不是平台取数函数、内置函数或已注册的自定义函数）"


# ─── ① 预检 ───────────────────────────────────────────────────────────────────


def precheck_issues(formula: str | None) -> list[dict[str, str]]:
    """逐个函数调用名分类，返回不放行的（空列表 = 放行）。"""
    custom = {name.upper() for name in _REGISTRY.known_function_names()} - BUILTIN_FUNCTION_NAMES
    issues: list[dict[str, str]] = []
    for name in called_function_names(formula):
        if name in FUNCTIONS:
            try:
                require_function_support(name, EXECUTOR)
            except FormulaSupportViolation as exc:
                issues.extend(exc.issues)
        elif name not in BUILTIN_FUNCTION_NAMES and name not in custom:
            issues.append({"function": name, "executor": EXECUTOR.value, "reason": _UNKNOWN_REASON})
    return issues


def precheck(formula: str | None) -> None:
    """预检不放行 ⇒ :class:`FormulaSupportViolation`（路由转 422）。"""
    if issues := precheck_issues(formula):
        raise FormulaSupportViolation(EXECUTOR, issues)


def issues_message(issues: list[dict[str, str]]) -> str:
    return "公式含当前执行器不支持的函数：" + "；".join(f"{i['function']}()：{i['reason']}" for i in issues)


def unsupported_detail(exc: FormulaSupportViolation) -> dict[str, Any]:
    """单条公式预检不放行的 422 detail（``message`` 供前端直接显示）。"""
    return {"error_code": UNSUPPORTED_ERROR_CODE, "executor": exc.executor.value, "issues": exc.issues,
            "message": issues_message(exc.issues)}


# ─── ③ 缺科目 ─────────────────────────────────────────────────────────────────


def referenced_tb_codes(formula: str | None) -> list[str]:
    """本年度试算表取数码：``TB`` / ``SUM_TB`` 的字面量首参（按出现顺序去重；``PREV(...)`` 子树取上年，跳过）。

    解析失败返回空（L1 求值同样失败，由 L1 报错）。
    """
    if not formula or not formula.strip():
        return []
    try:
        root = parse_to_ast(formula)
    except Exception:
        return []
    codes: list[str] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, ASTFuncCall):
            if node.name == "PREV":
                continue
            if node.name in ("TB", "SUM_TB") and node.args and isinstance(node.args[0], ASTString):
                if node.args[0].value and node.args[0].value not in codes:
                    codes.append(node.args[0].value)
        stack.extend(reversed(list(dataclass_children(node))))
    return codes


def _code_clause(column: Any, code: str) -> Any:
    """与预载 ``_load_tb`` 同口径：``'起~止'`` 按码头部落在区间内，否则按前缀。"""
    if code.count("~") == 1:
        start, end = (part.strip() for part in code.split("~", 1))
        if not start:
            return sa.false()
        head = sa.func.substr(column, 1, len(start))
        return sa.and_(head >= start, head <= end)
    return column.startswith(code, autoescape=True)


async def missing_account_codes(db: AsyncSession, project_id: uuid.UUID, year: int, formula: str | None,
                                known: Mapping[str, bool] | None = None) -> list[str]:
    """公式引用、而本项目年度试算表（未删行）一行都匹配不到的取数码。

    ``known`` = 预载已读过的码（``preload(tb_presence=…)``，同一批行、同一判据）直接用；其余的码一条语句、每码一个 ``EXISTS``。
    """
    codes = referenced_tb_codes(formula)
    known = known or {}
    unknown = [code for code in codes if code not in known]
    hits: dict[str, bool] = {}
    if unknown:
        tb = TrialBalance.__table__
        scope = (tb.c.project_id == project_id, tb.c.year == year, tb.c.is_deleted == sa.false())
        probes = [sa.exists().where(*scope, _code_clause(tb.c.standard_account_code, code)).label(f"c{i}")
                  for i, code in enumerate(unknown)]
        hits = dict(zip(unknown, (await db.execute(sa.select(*probes))).one()))
    return [code for code in codes if not (known[code] if code in known else hits[code])]


# ─── 主入口 ───────────────────────────────────────────────────────────────────


def _unique(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


async def execute_central(db: AsyncSession, project_id: uuid.UUID, year: int, formula: str | None) -> dict[str, Any]:
    """中央执行合同（见模块 docstring）。预检不放行抛 :class:`FormulaSupportViolation`。"""
    text = "" if formula is None else str(formula)
    precheck(text)
    if not text.strip():
        return {"value": 0.0, "ok": True, "state": "ok", "errors": [], "warnings": [], "formula": text, "error": None}
    gaps: list[str] = []
    with formula_warnings.collect() as collected:
        presence: dict[str, bool] = {}
        ctx = await preload(db, project_id, year, [text], adj_exclude_origins=frozenset(), gaps=gaps,
                            tb_presence=presence)
        missing = await missing_account_codes(db, project_id, year, text, known=presence)
        result = execute(text, ctx)
    absent = [f"{scope_for_year(year)}无科目 {code}" for code in missing]
    ok = result.ok and not gaps and not absent
    errors = [] if ok else _unique([*result.errors, *absent, *gaps]) or [f"求值失败（{result.state}）"]
    state = result.state if not result.ok else ("ok" if ok else "missing")
    return {
        "value": float(result.value) if ok else None,
        "ok": ok,
        "state": state,
        "errors": errors,
        "warnings": formula_warnings.merge_into(_unique(list(result.warnings)), collected),
        "formula": text,
        "error": "；".join(errors) or None,
    }
