"""表间审核用户规则（cross_check 域）：旧接口形状 ↔ 公式位，以及在报表勾稽 run 内执行（R10.2）。

公式位 ``{树节点 key}#{规则编号}``；定义 = 左侧 / 运算符 / 右侧 / 容差（执行字段）+ 名称 / 说明。
全局层按适用准则，回退 ``*``。旧数据（``projects.wizard_state.cross_check_user_rules``）由 V199 迁入本项目层。

执行（与原前端比较口径一致）：左右两侧经报表路径求值（``evaluate_formula_result``，严格上下文），
``=`` 为 |差| < 容差，``<=`` 为 差 <= 容差，``>=`` 为 差 >= -容差，容差缺省 0.01；
取不到数（不支持的函数 / 上下文缺失 / 求值出错）记为不通过并写明原因，不冒充通过。
"""
from __future__ import annotations

import logging
import secrets
import time
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_settings.errors import FormulaSettingError
from app.services.formula_settings.setting_sets import live_slots, replace_set, version_token

logger = logging.getLogger(__name__)
import hashlib

DOMAIN = "cross_check"
RULE_FIELDS = ("label", "left_ref", "operator", "right_ref", "description", "tolerance")
OPERATORS = ("=", "<=", ">=")
DEFAULT_TOLERANCE = Decimal("0.01")
FORMULA_ID_PREFIX = "user:"


def new_rule_id() -> str:
    """毫秒时间戳在前 ⇒ 按公式位排序即按新增先后。"""
    return f"{int(time.time() * 1000):011x}{secrets.token_hex(2)}"


def result_rule_id(slot_key: str) -> str:
    """落库用的稳定 rule_id（``cross_check_results.rule_id`` 限 30 字符）。

    🔴 必须按**整个公式位**（节点 # 规则号）取，不能只用规则号：迁入的旧数据规则号在不同节点
    会重复（V199 按节点各自从 ``0NNNN`` 编号），只用规则号 ⇒ ``user:00000`` 撞号，
    落库先删后插会少一条、issue 还会配错左右金额。``user:`` + sha1 前 16 位 = 21 字符，稳定且唯一。
    """
    return f"{FORMULA_ID_PREFIX}{hashlib.sha1(slot_key.encode('utf-8')).hexdigest()[:16]}"


def split_slot(slot_key: str) -> tuple[str, str]:
    node, _, rid = slot_key.partition("#")
    return node, rid


def _definition(rule: Mapping[str, Any]) -> dict[str, Any]:
    d = {f: rule.get(f) for f in RULE_FIELDS}
    d["operator"] = d["operator"] if d["operator"] in OPERATORS else "="
    return d


async def load(db: AsyncSession, project_id: uuid.UUID) -> dict[str, Any]:
    rules: dict[str, list[dict[str, Any]]] = {}
    loaded: dict[str, str] = {}
    pending: list[str] = []
    layers: dict[str, str] = {}
    for slot, e in sorted((await live_slots(db, DOMAIN, project_id)).items()):
        node, rid = split_slot(slot)
        d = e.definition or {}
        token = version_token(e)
        rules.setdefault(node, []).append({
            "rule_id": rid, "slot_key": slot, "label": d.get("label") or "", "left_ref": d.get("left_ref") or "",
            # 与执行口径一致：不认识的比较符按「=」（迁入的旧数据可能带别的值）
            "operator": d.get("operator") if d.get("operator") in OPERATORS else "=",
            "right_ref": d.get("right_ref") or "",
            "description": d.get("description") or "", "tolerance": d.get("tolerance"),
            "layer": e.layer, "pending": e.pending, "version_token": token,
        })
        layers[slot] = e.layer
        if e.pending:
            pending.append(slot)
        if token:
            loaded[slot] = token
    return {"rules": rules, "loaded": loaded, "layers": layers, "pending": pending}


async def save(db: AsyncSession, project_id: uuid.UUID, *, rules: Mapping[str, list[Mapping[str, Any]]],
               loaded: Mapping[str, str] | None, user_id: uuid.UUID | None) -> dict[str, Any]:
    desired: dict[str, dict[str, Any]] = {}
    for node, node_rules in rules.items():
        node = str(node).strip()
        if not node or "#" in node:
            raise FormulaSettingError(f"规则分组标识不正确：{node}")
        for rule in node_rules:
            rid = str(rule.get("rule_id") or "").strip() or new_rule_id()
            slot = f"{node}#{rid}"
            if slot in desired:
                raise FormulaSettingError(f"规则编号重复：{rid}")
            desired[slot] = {"definition": _definition(rule), "label": rule.get("label") or rid}
    return await replace_set(db, domain=DOMAIN, project_id=project_id, desired=desired, loaded=loaded,
                             user_id=user_id, source="cross_check_edit")


# ── 执行 ──────────────────────────────────────────────────────────────────────


def _tolerance(raw: Any) -> Decimal:
    try:
        tol = Decimal(str(raw)) if raw not in (None, "") else DEFAULT_TOLERANCE
    except (InvalidOperation, ValueError):
        return DEFAULT_TOLERANCE
    return abs(tol)


def compare(left: Decimal, right: Decimal, operator: str, tolerance: Decimal) -> bool:
    diff = left - right
    if operator == "<=":
        return diff <= tolerance
    if operator == ">=":
        return diff >= -tolerance
    return abs(diff) < tolerance


async def _evaluate(expression: str, resolver: Any, row_cache: dict[str, Decimal]) -> tuple[Decimal | None, str]:
    from app.services.formula_management.function_support_matrix import (
        Executor,
        FormulaSupportViolation,
        require_expression_support,
    )
    from app.services.report_engine import evaluate_formula_result

    text = (expression or "").strip()
    if not text:
        return None, "未填写"
    try:
        require_expression_support(text, Executor.REPORT_PATH)
    except FormulaSupportViolation:
        return None, "含报表路径不支持的函数"
    try:
        result = await evaluate_formula_result(text, resolver=resolver, row_cache=row_cache, strict_context=True)
    except Exception as exc:  # noqa: BLE001 —— 取不到数如实记为不通过
        return None, str(exc)[:200]
    if not result.ok:
        return None, "；".join(result.errors)[:200] or "公式被拦截"
    return result.value, ""


async def _report_rows(db: AsyncSession, project_id: uuid.UUID, year: int) -> list[Any]:
    import sqlalchemy as sa

    from app.models.report_models import FinancialReport

    return list((await db.execute(sa.select(FinancialReport).where(
        FinancialReport.project_id == project_id, FinancialReport.year == year,
        FinancialReport.is_deleted == sa.false()))).scalars().all())


async def run_user_rules(db: AsyncSession, *, project_id: uuid.UUID, year: int,
                         report_rows: Iterable[Any] | None = None) -> tuple[list[Any], list[Any]]:
    """执行本项目生效的全部用户规则（全局 + 本项目），返回 ``(outcomes, issues)``。

    ``ROW('行次')`` / ``REPORT(...)`` 取本项目本年度已生成的全部报表行（六类报表）。
    """
    from app.services.amount_resolver import TrialBalanceResolver
    from app.services.formula_management.engine import IssueItem
    from app.services.formula_management.logic_check import CrossCheckOutcome

    rules = sorted((await live_slots(db, DOMAIN, project_id)).items())
    if not rules:
        return [], []
    rows = list(report_rows) if report_rows is not None else await _report_rows(db, project_id, year)
    row_cache = {r.row_code: Decimal(str(r.current_period_amount or 0)) for r in rows
                 if getattr(r, "row_code", None)}
    resolver = TrialBalanceResolver(db, project_id, year)
    outcomes, issues = [], []
    for slot, e in rules:
        d = e.definition or {}
        _node, rid = split_slot(slot)
        fid = result_rule_id(slot)  # 按整个公式位取，避免不同节点同规则号撞 rule_id
        op = d.get("operator") if d.get("operator") in OPERATORS else "="
        label = d.get("label") or rid
        expression = f"{d.get('left_ref') or ''} {op} {d.get('right_ref') or ''}".strip()
        left, left_err = await _evaluate(d.get("left_ref") or "", resolver, row_cache)
        right, right_err = await _evaluate(d.get("right_ref") or "", resolver, row_cache)
        if left is None or right is None:
            passed = False
            reason = "；".join(x for x in (f"左侧{left_err}" if left is None else "",
                                          f"右侧{right_err}" if right is None else "") if x)
            message = f"{label}：无法取数（{reason}）"
        else:
            passed = compare(left, right, op, _tolerance(d.get("tolerance")))
            message = f"{label}：左侧 {left} {op} 右侧 {right} 不成立"
        outcomes.append(CrossCheckOutcome(formula_id=fid, description=label, expression=expression, passed=passed))
        if not passed:
            issues.append(IssueItem(formula_id=fid, addr_id=None, description=message, left_value=left,
                                    right_value=right))
    return outcomes, issues
