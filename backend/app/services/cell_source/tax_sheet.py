"""税审底稿 / 汇算申报表的单元格来源（spec citar-cell-source-hover design §4）。

与 ``tax_workpaper_service.compute_sheet`` 同一次求值（``evaluate_keys``，同 seeds），不另跑取数：
- 取数格：命中的客户科目逐个按同一口径算金额（``AccountBook.measure`` / ``month`` 逐节点可加，Σ = 格值）
- 公式格：公式原文 + 引用格逐个列出；只含加减、常数倍、SUM 的公式算出每格系数做合计核对
- 手工值格：手工值 + 原值（构成仍按原值拆，核对的是原值）
只返回取数格、公式格与有手工值的格；样表预置值、空的填写格由前端按 sheet 定义自己写。
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import AccountChart, AccountSource
from app.services import tax_workpaper_service as tws
from app.services.cell_source.schema import item, link, money, source, to_decimal
from app.services.standard_balance_view_service import approved_adjustment_lines
from app.services.tax_formula_engine import iter_refs
from app.services.tax_workbook import Key, load_workbook, to_a1
from app.services.tax_workpaper_rule_runner import RuleResult
from app.services.user_display_names import resolve_user_display_names

MEASURE_LABEL = {
    "debit": "本期借方发生额",
    "credit": "本期贷方发生额",
    "closing": "期末余额",
    "opening": "期初余额",
    "closing_debit": "期末借方余额",
    "closing_credit": "期末贷方余额",
    "paid_opening": "本年支付以前年度金额（年初余额与本年借方取小）",
}
STATUS_LABEL = {"auto": "照取", "confirm": "照取，待确认", "manual": "需人工判断后填写"}
#: 区域引用最多展开的格数（卡片只显示 20 项，其余计入合计）
MAX_REF_CELLS = 500
_NOT_ADJUSTED = "以下已批准调整分录涉及本格科目，未计入本格（税审取数读导入的科目余额表，不含审计调整）"
#: 行次 / 序号（「1」「2.1」「（三）」不算），不当作行名
_LINE_NO = re.compile(r"[\d.\s]+")


def linear_terms(node: tuple) -> tuple[dict[tuple, Decimal], Decimal] | None:
    """公式 AST → ({引用节点: 系数}, 常数)；含 IF / MIN / 比较 / 两个引用相乘除等非线性运算时 None。"""
    kind = node[0]
    if kind == "num":
        return {}, node[1]
    if kind == "empty":
        return {}, Decimal(0)
    if kind == "ref":
        return {node: Decimal(1)}, Decimal(0)
    if kind in ("neg", "pct"):
        sub = linear_terms(node[1])
        return None if sub is None else _scale(sub, Decimal(-1) if kind == "neg" else Decimal("0.01"))
    if kind == "bin":
        op, left, right = node[1], linear_terms(node[2]), linear_terms(node[3])
        if left is None or right is None:
            return None
        if op in ("+", "-"):
            return _add(left, _scale(right, Decimal(1) if op == "+" else Decimal(-1)))
        if op == "*":
            if not left[0]:
                return _scale(right, left[1])
            return _scale(left, right[1]) if not right[0] else None
        if op == "/" and not right[0] and right[1] != 0:
            return _scale(left, 1 / right[1])
        return None
    if kind == "call" and node[1] == "SUM":
        acc: tuple[dict[tuple, Decimal], Decimal] = ({}, Decimal(0))
        for arg in node[2]:
            sub = linear_terms(arg)
            if sub is None:
                return None
            acc = _add(acc, sub)
        return acc
    return None


def _scale(t: tuple[dict, Decimal], k: Decimal) -> tuple[dict, Decimal]:
    return {r: c * k for r, c in t[0].items()}, t[1] * k


def _add(a: tuple[dict, Decimal], b: tuple[dict, Decimal]) -> tuple[dict, Decimal]:
    out = dict(a[0])
    for r, c in b[0].items():
        out[r] = out.get(r, Decimal(0)) + c
    return out, a[1] + b[1]


def ref_cells(ref: tuple) -> list[Key]:
    _, sheet, r1, c1, r2, c2 = ref
    return [(sheet, r, c) for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)]


class _Builder:
    """一次请求内的上下文：求值结果、编号反查、行名缓存、标准科目名、已批准调整。"""

    def __init__(self, ev: tws.Evaluation, std_names: dict[str, str], adj_lines: list[dict],
                 manual_info: dict[str, Any]) -> None:
        self.ev = ev
        self.wb = ev.wb
        self.std_names = std_names
        self.adj_lines = adj_lines
        self.manual_info = manual_info
        self.sheet_code = {s: c for c, sheets in self.wb.codes.items() for s in sheets}
        self.params_sheet = self.wb.model["params_sheet"]
        self._row_labels: dict[str, dict[int, list[tuple[int, str]]]] = {}

    # ── 标注 ──
    def row_label(self, sheet: str, row: int, col: int | None = None) -> str:
        """行名：同行 ``col`` 左侧最近的文字常量（项目名称），没有时取本行第一个；纯数字的文字（申报表的行次「1」「2.1」）跳过。

        合并的类别列（申报表「利润总额计算」纵跨多行，只出现在首行）会比项目名更靠左，取「第一个」会把它当行名。
        """
        if sheet not in self._row_labels:
            texts: dict[int, list[tuple[int, str]]] = {}
            for (s, r, c), v in self.wb.consts.items():
                if s != sheet or not isinstance(v, str):
                    continue
                text = v.strip()
                if text and not _LINE_NO.fullmatch(text):
                    texts.setdefault(r, []).append((c, text))
            self._row_labels[sheet] = {r: sorted(cs) for r, cs in texts.items()}
        cs = self._row_labels[sheet].get(row) or []
        if not cs:
            return ""
        if col is not None:
            left = [t for c, t in cs if c < col]
            if left:
                return left[-1]
        return cs[0][1]

    def cell_label(self, key: Key) -> str:
        sheet, row, col = key
        if sheet == self.params_sheet:
            return f"填写参数 {to_a1(row, col)}"
        code = self.sheet_code.get(sheet, sheet)
        name = self.row_label(sheet, row, col)
        return f"{code} {to_a1(row, col)}" + (f" {name}" if name else "")

    def cell_link(self, key: Key) -> dict | None:
        sheet, row, col = key
        code = self.sheet_code.get(sheet)
        if code is None or sheet == self.params_sheet:
            return None
        page = "tax_return" if tws.code_domain(self.wb, code) == "tax_return" else "workpaper"
        return link(page, code=code, sheet=sheet, ref=to_a1(row, col))

    def manual(self, key: Key, auto: Any) -> dict | None:
        if key not in self.ev.inputs:
            return None
        return {"value": money(self.ev.inputs[key]), "auto": money(auto), **self.manual_info,
                "note": "手工值不按格记人，修改人 / 时间为本表最近一次保存"}

    # ── 取数格 ──
    def rule_source(self, key: Key, meta: RuleResult) -> dict:
        rule = self.wb.rules[key]
        book = self.ev.book
        op = rule["op"]
        manual = self.manual(key, meta.value)
        if meta.status == "manual":
            return source("manual" if manual else "rule", "需人工判断后填写（不取数）", meta.value, manual=manual,
                          rule_text=meta.rule)
        if op == "list_name":
            title = "明细科目名称（取自科目余额表，按余额 / 发生额列出）"
            items = [item(f"{n.code} {n.label}", detail=self._std_detail(n.standard)) for n in meta.nodes]
            return source("manual" if manual else "rule", title, meta.value, items, manual=manual,
                          issue=meta.issue, rule_text=meta.rule)
        measure = rule.get("measure") or (self._group_measure(rule) if op == "classify" else None)
        if op == "month":
            col = f"{rule['month']} 月{'借方' if measure == 'debit' else '贷方'}发生额（序时账）"
        else:
            col = MEASURE_LABEL.get(measure or "", measure or "")
        items = []
        for n in meta.nodes:
            amount = (book.month([n], measure, rule["month"]) if op == "month" else book.measure([n], measure)) if book else None
            items.append(item(f"{n.code} {n.label}", amount, detail=self._std_detail(n.standard),
                              link_to=link("balance", code=n.code)))
        notes = [f"取数状态：{STATUS_LABEL.get(meta.status, meta.status)}"]
        path = rule.get("path")
        fallback = book.fallback_top(list(path)) if book and path and op in ("amount", "month") else None
        if fallback:
            notes.append(f"「{path[0]}」下没有「{path[1]}」，按「{fallback}」取数")
        adj = self._unadjusted(meta.nodes)
        if adj:
            notes.append(_NOT_ADJUSTED)
            items.extend(adj)
        return source("manual" if manual else "rule", f"科目余额表（导入数，不含审计调整）· {col}", meta.value, items,
                      linear=bool(meta.nodes) and meta.value is not None, notes=notes, issue=meta.issue,
                      manual=manual, rule_text=meta.rule)

    def _group_measure(self, rule: dict) -> str | None:
        return (self.wb.model.get("classify_groups") or {}).get(rule.get("group"), {}).get("measure")

    def _std_detail(self, code: str | None) -> str:
        return f"映射到 {code} {self.std_names.get(code, '')}".rstrip() if code else "未映射到标准科目"

    def _unadjusted(self, nodes: list) -> list[dict]:
        codes = {n.standard for n in nodes if n.standard}
        if not codes or not self.adj_lines:
            return []
        groups: dict[str, dict] = {}
        for line in self.adj_lines:
            if not any(line["code"] == c or line["code"].startswith(c) for c in codes):
                continue
            g = groups.setdefault(line["group"], {"no": line["no"], "desc": line["description"], "net": Decimal(0)})
            g["net"] += line["debit"] - line["credit"]
        return [item(f"调整分录 {g['no']}", g["net"], sign=0, detail=g["desc"] or None,
                     link_to=link("adjustments", group=gid)) for gid, g in groups.items()]

    # ── 公式格 ──
    def calc(self, key: Key) -> Any:
        """参与计算的值（与 ``TaxWorkbook.evaluate`` 的取值顺序一致：公式结果含手工覆盖、手工值、取数值、常量）。"""
        if key in self.wb.formulas:
            return self.ev.computed.get(key)
        if key in self.ev.inputs:
            return self.ev.inputs[key]
        if key in self.ev.rule_values:
            return self.ev.rule_values[key]
        return self.wb.consts.get(key)

    def formula_source(self, key: Key) -> dict:
        ev, wb = self.ev, self.wb
        is_manual = key in ev.inputs
        auto = getattr(ev.computed, "auto", {}).get(key) if is_manual else None
        value = auto if is_manual else wb.cell_value(key, ev.inputs, ev.rule_values, ev.computed)
        ast = wb.formulas[key]
        terms = linear_terms(ast)
        items: list[dict] = []
        refs = [r for r in iter_refs(ast)]
        targets: list[tuple[Key, Decimal]] = []
        if terms is not None:
            for ref, coef in terms[0].items():
                targets.extend((cell, coef) for cell in ref_cells(ref)[:MAX_REF_CELLS])
        else:
            for ref in refs:
                targets.extend((cell, Decimal(1)) for cell in ref_cells(ref)[:MAX_REF_CELLS])
        seen: dict[Key, Decimal] = {}
        for cell, coef in targets:
            seen[cell] = seen.get(cell, Decimal(0)) + coef
        multi = len(seen) > 1
        cancelled: list[str] = []
        for cell, coef in seen.items():
            if terms is not None and coef == 0:
                cancelled.append(self.cell_label(cell))  # 区域里含、又单独减掉（加减相抵）
                continue
            v = self.calc(cell)
            amount = to_decimal(v)
            if multi and v in (None, ""):
                continue  # 区域里的空格不列
            detail = None if amount is not None or v is None else str(v)
            items.append(item(self.cell_label(cell), amount, sign=coef, detail=detail, link_to=self.cell_link(cell)))
        notes = []
        if cancelled:
            notes.append(f"{'、'.join(cancelled[:5])}{' 等' if len(cancelled) > 5 else ''}在公式中加减相抵，不计入")
        if terms is not None and terms[1]:
            items.append(item("常数", terms[1]))
        if terms is None:
            notes.append("非线性公式（含 IF / MIN / MAX / ROUND 等），只列引用，不做合计核对")
        issue = "公式循环引用" if key in wb.cyclic else None
        kind = "param" if refs and all(r[1] == self.params_sheet for r in refs) else "formula"
        if kind == "param":
            notes.append("取自填写参数（未填时为项目信息）")
        # 文字 / 错误值（客户名称、#DIV/0!）没有金额合计可核对
        numeric = value is None or (isinstance(value, Decimal) and not isinstance(value, bool))
        return source("manual" if is_manual else kind, f"公式计算：{wb.formula_text[key]}", value, items,
                      linear=terms is not None and numeric, notes=notes, issue=issue, manual=self.manual(key, auto))

    # ── 手工填写 / 改过的样表预置值 ──
    def input_source(self, key: Key) -> dict:
        preset = self.wb.consts.get(key)
        title = "已修改样表预置值" if preset is not None else "手工填写"
        return source("manual", title, self.ev.inputs[key], manual=self.manual(key, preset))


async def _std_names(db: AsyncSession, project_id: UUID) -> dict[str, str]:
    rows = (await db.execute(
        sa.select(AccountChart.account_code, AccountChart.account_name).where(
            AccountChart.project_id == project_id,
            AccountChart.source == AccountSource.standard,
            AccountChart.is_deleted == sa.false(),
        )
    )).all()
    return {c: n for c, n in rows if c}


async def sheet_sources(db: AsyncSession, project_id: UUID, year: int, code: str,
                        domain: str = tws.WORKPAPER_DOMAIN) -> dict:
    """``{code, year, cells: {"{sheet}!{A1}": CellSource}, notices}``；编号不属于该域时 404（同 ``compute_sheet``）。"""
    wb = load_workbook()
    sheets = tws._sheets_in_domain(wb, code, domain)
    await tws._project(db, project_id)
    rows = await tws._rows(db, project_id, year)
    own = rows.get(code)
    # 取成普通值：之后的取数查询失败时 get_active_filter 会 rollback，ORM 对象过期
    saved_by = own.updated_by if own else None
    saved_at = own.updated_at.isoformat() if own and own.updated_at else None
    ev = await tws.evaluate_keys(db, project_id, year, [k for s in sheets for k in wb.print_keys(s)], rows)
    has_nodes = any(m.nodes for m in ev.results_meta.values())
    adj = await approved_adjustment_lines(db, project_id, year) if has_nodes else []
    std = await _std_names(db, project_id) if has_nodes else {}
    names = await resolve_user_display_names(db, [saved_by]) if saved_by else {}
    b = _Builder(ev, std, adj, {"by_name": names.get(str(saved_by)) if saved_by else None, "at": saved_at})

    cells: dict[str, dict] = {}
    for sheet in sheets:
        for key in wb.print_keys(sheet):
            k = f"{sheet}!{to_a1(key[1], key[2])}"
            if key in wb.formulas:
                cells[k] = b.formula_source(key)
            elif key in ev.results_meta:
                cells[k] = b.rule_source(key, ev.results_meta[key])
        for key in ev.inputs:
            if key[0] == sheet and key not in wb.formulas and key not in wb.rules:
                cells[f"{sheet}!{to_a1(key[1], key[2])}"] = b.input_source(key)
    return {"code": code, "year": year, "cells": cells, "notices": list(ev.notices)}
