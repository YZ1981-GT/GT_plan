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
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.schemas.consol_context import ConsolContext

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
    load_calc_basis_pair,
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


MEASURE_WITH_DRAFTS = "consolidated_with_drafts"
_BALANCE_TOLERANCE = Decimal("0.01")


def account_balance(basis: CalcBasis, amounts: Mapping[str, Decimal]) -> dict:
    """科目金额按自然方向分借方性质 / 贷方性质求和判平衡（R8.5；与 ``account_sign`` 同源）。"""
    debit = credit = ZERO
    for account, amount in amounts.items():
        if basis.signs.get(account, ONE) < ZERO:
            credit += amount
        else:
            debit += amount
    diff = to_cents(debit - credit)
    return {"debit_total": str(to_cents(debit)), "credit_total": str(to_cents(credit)),
            "difference": str(diff), "balanced": abs(diff) < _BALANCE_TOLERANCE}


async def trial_view(
    basis: CalcBasis, rows: list[ReportRow], *, report_type: str, node_key: str | None = None,
    draft_basis: CalcBasis | None = None,
) -> dict:
    """某节点按报表行次的五列净额（design §五）。全部报表类型一起求值（跨表 ROW），只返回所请求的类型。

    ``node_kind / node_role`` 供前端按节点类型说明列口径；``balance`` = 该节点合并数按科目自然方向的
    借贷平衡检查；给了 ``draft_basis`` 时每行加「含草稿预览」列（已审批 + 草稿 + 待审批分录的合并数），
    ``draft_pending_entries`` = 本节点子树内计入预览的未审批分录笔数。
    """
    node = find_node(basis.tree, node_key)
    measures = node_measures(basis)[node.node_key]
    report = await node_report(rows, measures, categories=basis.categories)
    drafts: dict[str, RowValue] | None = None
    pending = 0
    if draft_basis is not None:
        draft_ms = node_measures(draft_basis).get(node.node_key, {})
        drafts = await report_values(rows, draft_ms.get(MEASURE_CONSOLIDATED, {}), categories=draft_basis.categories)
        elims = {n.node_key for n in iter_nodes(node) if n.kind == KIND_ELIM}
        pending = sum(1 for eid, key in draft_basis.attributed.items() if key in elims and eid not in basis.attributed)
    out_rows = []
    for row in _rows_of_type(rows, report_type):
        cells = {m: report[m][row.row_code] for m, _label in TRIAL_COLUMNS}
        reasons = list(dict.fromkeys(v.reason for v in cells.values() if v.reason))
        extra = {MEASURE_WITH_DRAFTS: _amount(drafts[row.row_code])} if drafts is not None else {}
        out_rows.append({
            **_row_meta(row),
            **{m: _amount(v) for m, v in cells.items()},
            **extra,
            "linear": cells[MEASURE_CONSOLIDATED].linear,
            "note": "；".join(reasons) or None,
        })
    columns = [{"key": m, "label": label} for m, label in TRIAL_COLUMNS]
    if drafts is not None:
        columns.append({"key": MEASURE_WITH_DRAFTS, "label": "含草稿预览"})
    return {
        "node_key": node.node_key,
        "node_label": node.display_name or node.company_name,
        "node_kind": node.kind,
        "node_role": node.role,
        "report_type": report_type,
        "columns": columns,
        "rows": out_rows,
        "balance": account_balance(basis, measures.get(MEASURE_CONSOLIDATED, {})),
        "draft_pending_entries": pending if draft_basis is not None else None,
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
    from app.services.consol_elimination_sheet_service import ENTRY_TYPE_LABELS

    node = find_node(basis.tree, node_key)
    by_code = {r.row_code: r for r in rows}
    if row_code not in by_code:
        raise ViewError(f"报表行 {row_code} 不存在")
    subtree = {n.node_key for n in iter_nodes(node) if n.kind == KIND_ELIM}
    terms_by_row = row_account_terms(rows)
    terms = terms_by_row.get(row_code)
    labels = {n.node_key: n.display_name or n.company_name for n in iter_nodes(basis.tree)}
    entries = list(entries)
    descriptions = {e.id: getattr(e, "description", None) for e in entries}
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
                "entry_type_label": ENTRY_TYPE_LABELS.get(ln.entry_type, ln.entry_type),
                "description": descriptions.get(ln.entry_id),
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
    """审定汇总列穿透：各数据叶子对该行的求值（``values_by_leaf`` 由调用方按叶子求好）。

    ``parent_label`` = 该叶子在企业树上的直接上级（汇总节点）名称，供明细标明所属。
    """
    labels = {n.node_key: (n.display_name or n.company_name, n.project_id) for n in iter_nodes(basis.tree)}
    parent_of = {c.node_key: n for n in iter_nodes(basis.tree) for c in n.children}
    out = []
    for key, value in values_by_leaf.items():
        label, project_id = labels.get(key, (key, None))
        if value.amount is None and value.reason is None:
            continue
        parent = parent_of.get(key)
        out.append({
            "node_key": key,
            "node_label": label,
            "parent_label": (parent.display_name or parent.company_name) if parent else None,
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
    # 「含草稿预览」口径（已审批 + 草稿 + 待审批，不含已驳回；同一树与试算表）；只在 include_drafts 时装载
    draft_basis: CalcBasis | None = None


async def load_view_context(
    db: AsyncSession,
    project_id: UUID,
    year: int | None = None,
    *,
    context: "ConsolContext | None" = None,
    tree: TreeNode | None = None,
    include_drafts: bool = False,
) -> ViewContext | None:
    """合并项目的计算口径 + 报表配置（按项目口径）；项目不存在或不是合并项目返回 None。

    级联/批量入口传入 ``tree`` 时直接复用该树，避免同一轮计算重新推导企业范围。
    ``context`` 只负责身份边界校验，``ViewContext`` 继续承载计算 basis、报表行、准则和年度。
    ``include_drafts`` ⇒ 另装载 ``draft_basis``（只供试算页「含草稿预览」列与分录汇总表；合并数仍只认已审批）。
    """
    from app.services.consol_context_service import validate_context
    from app.services.consol_group_tree import ROLE_CONSOL, build_group_tree

    resolved_tree = tree
    resolved_year = year
    if resolved_tree is None:
        result = await build_group_tree(db, project_id)
        if result is None or result.root is None or result.root.role != ROLE_CONSOL:
            return None
        resolved_tree = result.root
        if resolved_year is None:
            resolved_year = result.year
    elif getattr(resolved_tree, "role", None) != ROLE_CONSOL:
        return None

    if resolved_year is None:
        return None
    validate_context(context, project_id, resolved_year, tree=resolved_tree)
    draft_basis = None
    if include_drafts:
        basis, draft_basis = await load_calc_basis_pair(db, project_id, resolved_year, tree=resolved_tree)
    else:
        basis = await load_calc_basis(db, project_id, resolved_year, tree=resolved_tree)
    if basis is None:
        return None
    standard = await resolve_consol_standard(db, project_id)
    return ViewContext(
        basis=basis,
        rows=await load_report_rows(db, standard),
        standard=standard,
        year=resolved_year,
        draft_basis=draft_basis,
    )


async def prior_node_values(
    db: AsyncSession, project_id: UUID, year: int, node_key: str, report_type: str,
    *, standard: str | None = None,
) -> tuple[dict[str, RowValue] | None, str | None]:
    """合并报表「上期」：上年同企业合并项目同一节点的合并数（spec consol-autotree-linkage-closure R8.1）。

    上年项目与报表上期、PREV 共用 ``prior_year_context.find_prior_project``（同企业代码、审计年度 − 1、
    同为合并口径，唯一才认）。取不到返回 ``(None, 原因)``，调用方留空并把原因给用户，不代入 0。
    ``standard`` 是本年报表口径：上年口径不同则行次对不上，留空并说明（不按行次硬套）。
    🔴 旧实现拿本项目算 ``year − 1``：本项目的企业树是本年度的，年度边界拒绝后被吞 ⇒ 上期恒空。
    """
    from fastapi import HTTPException

    from app.services.prior_year_context import find_prior_project

    found = await find_prior_project(db, project_id, year)
    if found.project_id is None:
        return None, f"合并上期留空：{found.reason}"
    try:
        prior_ctx = await load_view_context(db, found.project_id, year - 1)
    except HTTPException as exc:
        detail = exc.detail.get("message") if isinstance(exc.detail, dict) else exc.detail
        return None, f"合并上期留空：上年合并项目无法计算（{detail}）"
    if prior_ctx is None:
        return None, "合并上期留空：上年项目不是合并项目，或无法确定其审计年度"
    if standard is not None and prior_ctx.standard != standard:
        return None, f"合并上期留空：上年合并项目报表口径（{prior_ctx.standard}）与本年（{standard}）不同"
    node_ms = node_measures(prior_ctx.basis).get(node_key)
    if node_ms is None:
        return None, f"合并上期留空：上年企业树没有节点「{node_key}」"
    prior_rows = _rows_of_type(prior_ctx.rows, report_type)
    if not prior_rows:
        return None, "合并上期留空：上年合并项目没有该报表的配置行"
    values = await report_values(
        prior_rows, node_ms.get(MEASURE_CONSOLIDATED, {}),
        categories=prior_ctx.basis.categories, require_linear=False,
    )
    return values, None


async def load_entry_drill(
    db: AsyncSession, ctx: ViewContext, *, row_code: str, measure: str, node_key: str | None,
) -> dict:
    """分录穿透；合并审定数列另给完整构成（R10.3）：``individual_total``（审定汇总）+ 分录贡献 = ``consolidated_total``。"""
    entries = await load_tree_entries(db, ctx.basis.tree, ctx.year)
    result = entry_drill_rows(ctx.basis, entries, ctx.rows, row_code=row_code, measure=measure, node_key=node_key)
    if measure == MEASURE_CONSOLIDATED:
        node = find_node(ctx.basis.tree, node_key)
        report = await node_report(ctx.rows, node_measures(ctx.basis)[node.node_key], categories=ctx.basis.categories)
        result["individual_total"] = _amount(report[MEASURE_INDIVIDUAL][row_code])
        result["consolidated_total"] = _amount(report[MEASURE_CONSOLIDATED][row_code])
    return result


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
