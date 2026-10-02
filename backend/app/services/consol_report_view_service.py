"""合并报表读时计算视图（spec consol-elimination-single-source-push §五 / §六，ADR-CSP-002）。

三个只读视图共用同一份计算口径（``consol_calc_basis``）与同一个行求值函数（``consol_report_values``），
合并报表落库（``consol_report_service.generate_consol_reports``）也调同一个 ``report_values``：

- ``trial_view``：合并试算平衡表页 —— 某汇总节点按报表行次的五列净额
  （审定汇总 / 权益抵销 / 往来交易抵销 / 报表调整 / 合并审定数）；
- ``breakdown_view``：报表差额表 —— 某汇总节点的直接子节点各一列 + 合计列（P4：线性行列和 = 合计）；
- ``entry_drill_rows``：行 → 分录明细穿透 —— 已审批、已归属到该节点子树的明细行，
  按行公式展开的取数项取系数，贡献之和恒等于该行的度量值。

纯函数层不连库，``load_*`` 是薄装载（企业树 + 计算口径 + 报表配置）。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.consol_calc_basis import (
    ADJUSTMENT_ENTRY_TYPE,
    EQUITY_ENTRY_TYPE,
    MEASURE_ADJUSTMENT,
    MEASURE_CONSOLIDATED,
    MEASURE_ELIM_EQUITY,
    MEASURE_ELIM_TRADE,
    MEASURE_INDIVIDUAL,
    ONE,
    ZERO,
    CalcBasis,
    load_calc_basis,
    node_measures,
    records_from_entries,
    load_tree_entries,
    to_cents,
)
from app.services.consol_group_tree import KIND_AGGREGATE, KIND_DATA, KIND_ELIM
from app.services.consol_report_values import (
    REPORT_TYPE_ORDER,
    ReportRow,
    RowValue,
    load_report_rows,
    node_report,
    report_values,
    resolve_consol_standard,
    row_account_terms,
    term_matches,
)
from app.services.consol_tree_service import TreeNode, iter_nodes

# 试算平衡表页的列（design §五）：净额，一列一值；顺序即展示顺序
TRIAL_COLUMNS: tuple[tuple[str, str], ...] = (
    (MEASURE_INDIVIDUAL, "审定汇总"),
    (MEASURE_ELIM_EQUITY, "权益抵销"),
    (MEASURE_ELIM_TRADE, "往来交易抵销"),
    (MEASURE_ADJUSTMENT, "报表调整"),
    (MEASURE_CONSOLIDATED, "合并审定数"),
)
DRILL_MEASURES = frozenset({MEASURE_ELIM_EQUITY, MEASURE_ELIM_TRADE, MEASURE_ADJUSTMENT, MEASURE_CONSOLIDATED})


class ViewError(LookupError):
    """视图参数与企业树不匹配（节点不存在 / 不是汇总节点 / 行次不存在）；路由转 404 / 400。"""

    def __init__(self, message: str, *, status: int = 404):
        super().__init__(message)
        self.status = status


def _amount(value: RowValue) -> str | None:
    return None if value.amount is None else str(value.amount)


def find_node(tree: TreeNode, node_key: str | None) -> TreeNode:
    if not node_key:
        return tree
    node = next((n for n in iter_nodes(tree) if n.node_key == node_key), None)
    if node is None:
        raise ViewError(f"企业树中没有节点 {node_key}")
    return node


def _rows_of_type(rows: Iterable[ReportRow], report_type: str) -> list[ReportRow]:
    if report_type not in REPORT_TYPE_ORDER:
        raise ViewError(f"不支持的报表类型：{report_type}", status=400)
    return [r for r in rows if r.report_type == report_type]


def _row_meta(row: ReportRow) -> dict:
    return {
        "row_code": row.row_code,
        "row_name": row.row_name,
        "row_number": row.row_number,
        "indent_level": row.indent_level,
        "is_total_row": row.is_total_row,
        "has_formula": bool((row.formula or "").strip()),
    }


# ─────────────────────────────── 试算平衡表页 ───────────────────────────────


async def trial_view(
    basis: CalcBasis, rows: list[ReportRow], *, report_type: str, node_key: str | None = None,
) -> dict:
    """某节点按报表行次的五列净额（design §五）。全部报表类型一起求值（跨表 ROW），只返回所请求的类型。"""
    node = find_node(basis.tree, node_key)
    measures = node_measures(basis)[node.node_key]
    report = await node_report(rows, measures, categories=basis.categories)
    out_rows = []
    for row in _rows_of_type(rows, report_type):
        cells = {m: report[m][row.row_code] for m, _label in TRIAL_COLUMNS}
        reasons = list(dict.fromkeys(v.reason for v in cells.values() if v.reason))
        out_rows.append({
            **_row_meta(row),
            **{m: _amount(v) for m, v in cells.items()},
            "linear": cells[MEASURE_CONSOLIDATED].linear,
            "note": "；".join(reasons) or None,
        })
    return {
        "node_key": node.node_key,
        "node_label": node.display_name or node.company_name,
        "report_type": report_type,
        "columns": [{"key": m, "label": label} for m, label in TRIAL_COLUMNS],
        "rows": out_rows,
    }


# ─────────────────────────────── 报表差额表 ───────────────────────────────


def _column_kind(node: TreeNode) -> str:
    if node.kind == KIND_ELIM:
        return "elim"
    if node.kind == KIND_DATA:
        return "data"
    return "aggregate"


async def breakdown_view(
    basis: CalcBasis, rows: list[ReportRow], *, report_type: str, node_key: str | None = None,
) -> dict:
    """报表差额表（design §六）：列 = 汇总节点的直接子节点（树序），合计 = 该节点合并数求值。

    每列对子节点的合并数度量求值；线性行 Σ 列 = 合计（到分精确，报表公式系数全为整数时）；
    非线性行只给合计并注明不能分解。
    """
    node = find_node(basis.tree, node_key)
    if node.kind != KIND_AGGREGATE:
        raise ViewError(f"「{node.display_name or node.company_name}」不是汇总节点，没有差额表", status=400)
    measures = node_measures(basis)
    cats = basis.categories
    total = await report_values(rows, measures[node.node_key][MEASURE_CONSOLIDATED], categories=cats)
    per_child = [
        (child, await report_values(rows, measures[child.node_key][MEASURE_CONSOLIDATED],
                                    categories=cats, require_linear=True))
        for child in node.children
    ]
    columns = [
        {
            "node_key": child.node_key,
            "label": child.display_name or child.company_name,
            "kind": _column_kind(child),
            "role": child.role,
            "company_code": child.company_code,
        }
        for child, _values in per_child
    ]
    out_rows = []
    for row in _rows_of_type(rows, report_type):
        tot = total[row.row_code]
        cells = {child.node_key: _amount(values[row.row_code]) for child, values in per_child}
        note = tot.reason
        if tot.amount is not None and not tot.linear:
            note = "公式非线性，只给合计，不按子节点分解"
        out_rows.append({
            **_row_meta(row),
            "cells": cells,
            "total": _amount(tot),
            "linear": tot.linear,
            "note": note,
        })
    return {
        "node_key": node.node_key,
        "node_label": node.display_name or node.company_name,
        "report_type": report_type,
        "columns": columns,
        "rows": out_rows,
    }


def aggregate_nodes(tree: TreeNode) -> list[dict]:
    """可选的差额表节点（汇总节点，树序）。"""
    return [
        {"node_key": n.node_key, "label": n.display_name or n.company_name, "role": n.role}
        for n in iter_nodes(tree) if n.kind == KIND_AGGREGATE
    ]


# ─────────────────────────────── 行 → 分录明细穿透 ───────────────────────────────


def _measure_of(entry_type: str) -> str:
    if entry_type == ADJUSTMENT_ENTRY_TYPE:
        return MEASURE_ADJUSTMENT
    if entry_type == EQUITY_ENTRY_TYPE:
        return MEASURE_ELIM_EQUITY
    return MEASURE_ELIM_TRADE


@dataclass(frozen=True)
class DrillLine:
    entry_id: UUID
    entry_no: str
    entry_type: str
    node_key: str
    account_code: str
    account_name: str | None
    debit: Decimal
    credit: Decimal
    contribution: Decimal


def entry_drill_rows(
    basis: CalcBasis,
    entries: Iterable[Any],
    rows: list[ReportRow],
    *,
    row_code: str,
    measure: str,
    node_key: str | None = None,
) -> dict:
    """某报表行某度量由哪些分录明细行构成（design §五 穿透）。

    只计已审批且已归属到 ``node_key`` 子树内差额节点的分录（与计算口径同一归属结果 ``basis.attributed``）；
    每条明细行贡献 = Σ(取到该科目的取数项系数) × 按科目自然方向归一的（借 − 贷）。
    行能线性展开到取数项时 ``Σ 贡献 = 该行该度量值``（``reconciles`` 为真）；不能展开时不给贡献只说明原因。
    """
    if measure not in DRILL_MEASURES:
        raise ViewError(f"度量 {measure} 不能穿透到分录（个别数请看各数据节点）", status=400)
    node = find_node(basis.tree, node_key)
    by_code = {r.row_code: r for r in rows}
    if row_code not in by_code:
        raise ViewError(f"报表行 {row_code} 不存在")
    subtree = {n.node_key for n in iter_nodes(node) if n.kind == KIND_ELIM}
    terms_by_row = row_account_terms(rows)
    terms = terms_by_row.get(row_code)
    labels = {n.node_key: n.display_name or n.company_name for n in iter_nodes(basis.tree)}
    records, _invalid = records_from_entries(entries)
    lines: list[DrillLine] = []
    for entry in sorted(records, key=lambda e: (e.entry_no, str(e.id))):
        key = basis.attributed.get(entry.id)
        if key is None or key not in subtree:
            continue
        if measure != MEASURE_CONSOLIDATED and _measure_of(entry.entry_type) != measure:
            continue
        for line in entry.lines:
            if terms is None:
                coef = ZERO
            else:
                coef = sum((c for t, c in terms.items() if term_matches(t, line.account_code)), ZERO)
            if terms is not None and coef == 0:
                continue
            sign = basis.signs.get(line.account_code, ONE)
            lines.append(DrillLine(
                entry.id, entry.entry_no, entry.entry_type, key, line.account_code,
                line.account_name or basis.names.get(line.account_code), line.debit, line.credit,
                to_cents(coef * sign * (line.debit - line.credit)),
            ))
    total = sum((ln.contribution for ln in lines), ZERO)
    return {
        "node_key": node.node_key,
        "row_code": row_code,
        "row_name": by_code[row_code].row_name,
        "measure": measure,
        "decomposable": terms is not None,
        "note": None if terms is not None else "该行公式不能展开到科目（非线性或引用了不能展开的行），只列出相关分录，不计贡献",
        "total": str(total) if terms is not None else None,
        "lines": [
            {
                "entry_id": str(ln.entry_id),
                "entry_no": ln.entry_no,
                "entry_type": ln.entry_type,
                "node_key": ln.node_key,
                "node_label": labels.get(ln.node_key, ln.node_key),
                "account_code": ln.account_code,
                "account_name": ln.account_name,
                "debit": str(ln.debit),
                "credit": str(ln.credit),
                "contribution": str(ln.contribution) if terms is not None else None,
            }
            for ln in lines
        ],
    }


def individual_drill_rows(
    basis: CalcBasis, rows: list[ReportRow], values_by_leaf: Mapping[str, RowValue], *, row_code: str,
) -> list[dict]:
    """审定汇总列穿透：各数据叶子对该行的求值（``values_by_leaf`` 由调用方按叶子求好）。"""
    labels = {n.node_key: (n.display_name or n.company_name, n.project_id) for n in iter_nodes(basis.tree)}
    out = []
    for key, value in values_by_leaf.items():
        label, project_id = labels.get(key, (key, None))
        if value.amount is None and value.reason is None:
            continue
        out.append({
            "node_key": key,
            "node_label": label,
            "project_id": str(project_id) if project_id else None,
            "amount": _amount(value),
            "reason": value.reason,
        })
    return out


# ─────────────────────────────── 薄装载 ───────────────────────────────


@dataclass
class ViewContext:
    basis: CalcBasis
    rows: list[ReportRow]
    standard: str
    year: int


async def load_view_context(db: AsyncSession, project_id: UUID, year: int | None = None) -> ViewContext | None:
    """合并项目的计算口径 + 报表配置（按项目口径）；项目不存在或不是合并项目返回 None。"""
    from app.services.consol_group_tree import ROLE_CONSOL, build_group_tree

    result = await build_group_tree(db, project_id)
    if result is None or result.root is None or result.root.role != ROLE_CONSOL:
        return None
    effective_year = year if year is not None else result.year
    if effective_year is None:
        return None
    basis = await load_calc_basis(db, project_id, effective_year, tree=result.root)
    assert basis is not None
    standard = await resolve_consol_standard(db, project_id)
    return ViewContext(basis=basis, rows=await load_report_rows(db, standard), standard=standard, year=effective_year)


async def load_entry_drill(
    db: AsyncSession, ctx: ViewContext, *, row_code: str, measure: str, node_key: str | None,
) -> dict:
    entries = await load_tree_entries(db, ctx.basis.tree, ctx.year)
    return entry_drill_rows(ctx.basis, entries, ctx.rows, row_code=row_code, measure=measure, node_key=node_key)


async def load_individual_drill(ctx: ViewContext, *, row_code: str, node_key: str | None) -> list[dict]:
    """审定汇总穿透：节点子树内每个数据叶子对该行求值（全表求值，跨表 ROW 同一口径）。"""
    node = find_node(ctx.basis.tree, node_key)
    if row_code not in {r.row_code for r in ctx.rows}:
        raise ViewError(f"报表行 {row_code} 不存在")
    measures = node_measures(ctx.basis)
    values: dict[str, RowValue] = {}
    for leaf in iter_nodes(node):
        if leaf.kind != KIND_DATA or leaf.children:
            continue
        leaf_values = await report_values(
            ctx.rows, measures[leaf.node_key][MEASURE_INDIVIDUAL],
            categories=ctx.basis.categories, require_linear=True,
        )
        values[leaf.node_key] = leaf_values[row_code]
    return individual_drill_rows(ctx.basis, ctx.rows, values, row_code=row_code)


_SOURCE_BY_KIND = {KIND_DATA: "个别数", KIND_ELIM: "抵销与调整", KIND_AGGREGATE: "下级汇总"}


async def child_contributions(
    basis: CalcBasis, rows: list[ReportRow], *, report_type: str, row_code: str, node_key: str | None = None,
) -> dict:
    """报表某行在企业树上的构成（合并附注 / 报表「汇总穿透」，需求 9.3）：

    - ``rows``：所选汇总节点的直接子节点各自对该行的合并数求值（与报表差额表同一口径）；
    - ``leaf_rows``：子树内全部末级节点（数据叶子 + 差额节点）各自的值；
    线性行两层之和都 = 该节点合并数；非线性行只给合计并说明。不按持股比例估算。
    """
    node = find_node(basis.tree, node_key)
    if node.kind != KIND_AGGREGATE:
        raise ViewError(f"「{node.display_name or node.company_name}」不是汇总节点，没有下级构成", status=400)
    if row_code not in {r.row_code for r in _rows_of_type(rows, report_type)}:
        raise ViewError(f"报表行 {row_code} 不存在")
    measures = node_measures(basis)
    cats = basis.categories
    total = (await report_values(rows, measures[node.node_key][MEASURE_CONSOLIDATED], categories=cats))[row_code]
    parent_of: dict[str, TreeNode] = {}
    for n in iter_nodes(node):
        for c in n.children:
            parent_of[c.node_key] = n
    leaves = [n for n in iter_nodes(node) if not n.children and n is not node]

    async def entry(n: TreeNode) -> dict:
        value = (await report_values(rows, measures[n.node_key][MEASURE_CONSOLIDATED], categories=cats,
                                     require_linear=True))[row_code]
        parent = parent_of.get(n.node_key)
        amount = value.amount
        pct = None
        if amount is not None and total.amount:
            pct = str(to_cents(amount / total.amount * 100))
        return {
            "node_key": n.node_key,
            "company_code": n.company_code,
            "company_name": n.display_name or n.company_name,
            "kind": _column_kind(n),
            "source": _SOURCE_BY_KIND.get(n.kind, n.kind),
            "parent_name": (parent.display_name or parent.company_name) if parent else None,
            "project_id": str(n.project_id) if n.project_id else None,
            "amount": _amount(value),
            "pct": pct,
            "reason": value.reason,
        }

    direct = [await entry(c) for c in node.children]
    leaf_rows = [await entry(n) for n in leaves]
    note = total.reason
    if total.amount is not None and not total.linear:
        note = "公式非线性，只给合计，不按企业分解"
    return {
        "node_key": node.node_key,
        "node_label": node.display_name or node.company_name,
        "report_type": report_type,
        "row_code": row_code,
        "total": _amount(total),
        "linear": total.linear,
        "note": note,
        "rows": direct,
        "leaf_rows": leaf_rows,
    }


__all__ = [
    "DRILL_MEASURES",
    "TRIAL_COLUMNS",
    "ViewContext",
    "ViewError",
    "aggregate_nodes",
    "breakdown_view",
    "child_contributions",
    "entry_drill_rows",
    "find_node",
    "individual_drill_rows",
    "load_entry_drill",
    "load_individual_drill",
    "load_view_context",
    "trial_view",
]
