"""单体财务报表的单元格来源（spec citar-cell-source-hover R5.6，design §7）。

- 企业会计制度格式：格值取 ``financial_statements.build`` 的结果（页面同一份），构成按行配置展开 ——
  取数行按科目项拆到各标准科目（``fs_rows.account_terms``，与求值同一口径）、合计行按引用行、现金流量表行按平台现金流量表行名、
  跨表行指到被引用的格；手工值写手工值与自动值。
- 企业会计准则格式：即平台审定报表，转调 ``cell_source.report``（键换成本页的表 / 行号）。
cell_key：``{表key}:{行号 r}:{current|prior}``。
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import FinancialReportType
from app.models.tax_workpaper_models import FS_SHEET_CODE
from app.services import tax_workpaper_service as tws
from app.services.cell_source import report as report_src
from app.services.cell_source.schema import item, link, money, source, to_decimal
from app.services.prior_year_context import resolve_prior_source
from app.services.standard_balance_view_service import build_standard_balance_view
from app.services.tax_assurance import financial_statements as fs
from app.services.tax_assurance.fs_rows import _SUM_RE, _TERM_RE, PL_CLOSE, account_terms, load_config, normalize_name
from app.services.user_display_names import resolve_user_display_names

_ZERO = Decimal(0)
COLS = ("current", "prior")


def _value(row: dict, col: str) -> Decimal | None:
    v = row.get(col)
    return to_decimal(v.get("n")) if isinstance(v, dict) and "n" in v else None


async def _cas_sources(db: AsyncSession, project_id: UUID, year: int, body: dict) -> dict[str, dict]:
    cells: dict[str, dict] = {}
    for stmt in body["statements"]:
        try:
            rt = FinancialReportType(stmt["key"])
        except ValueError:
            continue
        if rt not in report_src.REPORT_TYPES:
            continue
        src = (await report_src.report_sources(db, project_id, year, rt))["cells"]
        for row in stmt["rows"]:
            for col in COLS:
                hit = src.get(f"{row.get('row_code')}:{col}")
                if hit:
                    cells[f"{stmt['key']}:{row['r']}:{col}"] = hit
    return cells


def _account_items(row: dict, balances: dict[str, Decimal], pl_close: Decimal, flip: Decimal, std_names: dict[str, str]
                   ) -> list[dict]:
    sign = flip * (Decimal(-1) if row.get("negate") else Decimal(1))
    out = []
    for term in row["accounts"]:
        for code, amount in account_terms(balances, term, pl_close):
            if code == PL_CLOSE:
                out.append(item("未结转损益（损益类科目期末未结平的余额）", amount, sign=sign, link_to=link("trial_balance")))
            elif amount:
                out.append(item(f"{code} {std_names.get(code, '')}".strip(), amount, sign=sign,
                                detail=f"科目项 {term}" if "!" in term else None, link_to=link("trial_balance", code=code)))
    return out


async def fs_sources(db: AsyncSession, project_id: UUID, year: int, scope_codes: set[str] | None = None) -> dict:
    """``{year, format, cells: {"{表}:{行}:{列}": CellSource}, notices}``。"""
    body = await fs.build(db, project_id, year, scope_codes, diagnose=False)
    if body["format"] == fs.FORMAT_CAS:
        return {"year": year, "format": body["format"], "cells": await _cas_sources(db, project_id, year, body),
                "notices": []}
    if body["format"] != fs.FORMAT_SYSTEM:
        return {"year": year, "format": body["format"], "cells": {}, "notices": []}

    view = await build_standard_balance_view(db, project_id, year)
    if scope_codes is not None:
        view = [r for r in view if r["standard_account_code"] in scope_codes]
    closing, opening, pl_close = fs.balances_of(view)
    std_names = {r["standard_account_code"]: r["account_name"] for r in view}
    prior_src = await resolve_prior_source(db, project_id, year)
    prior_closing = None
    if prior_src.project_id is not None:
        prior_view = await build_standard_balance_view(db, prior_src.project_id, prior_src.year)
        prior_closing = fs.balances_of(prior_view)[0] if prior_view else None
    cf_cur, cf_prior, cf_generated = await fs._cf_values(db, project_id, year)
    own = (await tws._rows(db, project_id, year)).get(FS_SHEET_CODE)
    saved_by, saved_at = (own.updated_by, own.updated_at.isoformat() if own.updated_at else None) if own else (None, None)
    names = await resolve_user_display_names(db, [saved_by]) if saved_by else {}

    stmts = {s["key"]: s for s in load_config()["statements"]}
    shown: dict[tuple[str, int, str], Decimal | None] = {}
    rows_out: dict[tuple[str, int], dict] = {}
    for s in body["statements"]:
        for r in s["rows"]:
            rows_out[(s["key"], r["r"])] = r
            for col in COLS:
                shown[(s["key"], r["r"], col)] = _value(r, col)
    labels = {(k, r["r"]): r["label"].strip() for k, st in stmts.items() for r in st["rows"]}

    cells: dict[str, dict] = {}
    for key, stmt in stmts.items():
        flip = Decimal(-1) if stmt["side"] == "credit" else Decimal(1)
        for row in stmt["rows"]:
            if row.get("heading") or row.get("note"):
                continue
            r = row["r"]
            out_row = rows_out.get((key, r), {})
            for col in COLS:
                manual_cell = (out_row.get("manual") or {}).get(col)
                auto = to_decimal((manual_cell.get("auto") or {}).get("n")) if manual_cell else shown.get((key, r, col))
                manual = None
                if manual_cell:
                    manual = {"value": money(shown.get((key, r, col))), "auto": money(auto),
                              "by_name": names.get(str(saved_by)) if saved_by else None, "at": saved_at,
                              "note": "手工值整份保存，修改人 / 时间为本页最近一次保存"}
                cells[f"{key}:{r}:{col}"] = _row_source(
                    key, stmt, row, col, auto, manual, flip, closing, opening, pl_close, prior_closing, prior_src,
                    cf_cur, cf_prior, cf_generated, std_names, shown, labels)
    return {"year": year, "format": body["format"], "cells": cells, "notices": []}


def _row_source(key, stmt, row, col, auto, manual, flip, closing, opening, pl_close, prior_closing, prior_src,
                cf_cur, cf_prior, cf_generated, std_names, shown, labels) -> dict:
    """企业会计制度格式一格的来源（构成按自动值拆；手工值另写）。"""
    title_col = stmt["columns"][COLS.index(col)] if len(stmt.get("columns") or []) > COLS.index(col) else ""
    notes: list[str] = []
    items: list[dict] = []
    linear = False
    if "accounts" in row:
        if stmt["period"] == "date":
            balances, pl = (closing, pl_close) if col == "current" else (opening, _ZERO)
            basis = "试算表审定数（期末）" if col == "current" else "本年试算表期初数（上年年末），损益类未结转余额按 0"
        else:
            balances, pl = (closing, _ZERO) if col == "current" else (prior_closing, _ZERO)
            basis = "试算表审定数（本期发生额）" if col == "current" else (
                f"上年项目试算表审定数（{prior_src.year} 年）" if prior_closing is not None else "")
        if balances is None:
            return source("none", f"{title_col}无来源：{prior_src.reason or '上年试算表没有数据'}", auto, manual=manual)
        items = _account_items(row, balances, pl, flip, std_names)
        linear = True
        title = f"取数：{'、'.join(row['accounts'])}" + ("，取反" if row.get("negate") else "") + f"；{basis}"
        if flip < 0:
            notes.append("贷方报表：试算表借正贷负，乘 −1 后列示")
    elif "formula" in row:
        title = f"合计：{row['formula']}"
        for sign, term in _TERM_RE.findall(row["formula"].replace(" ", "")):
            k = Decimal(-1) if sign == "-" else Decimal(1)
            m = _SUM_RE.fullmatch(term)
            lines = range(int(m.group(1)), int(m.group(2)) + 1) if m else [int(term)]
            for line in lines:
                if (key, line) not in labels:
                    continue
                items.append(item(f"{line} {labels[(key, line)]}", shown.get((key, line, col)) or _ZERO, sign=k,
                                  link_to=link("statement", sheet=key, row=line, column=col)))
        linear = manual is None
        if manual:
            notes.append("本格改过手工值：合计不再按下列各行重算")
    elif "cf" in row:
        values = cf_cur if col == "current" else cf_prior
        if not cf_generated:
            title = "取自平台现金流量表：尚未生成"
        else:
            title = f"取自平台现金流量表：{'、'.join(row['cf'])}"
            for name in row["cf"]:
                n = normalize_name(name)
                if n in values:
                    items.append(item(name, values[n], link_to=link("reports", report_type="cash_flow_statement")))
            linear = auto is not None
    elif "from" in row:
        src_key, line = row["from"].split(":")
        line = int(line)
        title = f"取自{src_key}第 {line} 行"
        items = [item(f"{line} {labels.get((src_key, line), '')}".strip(), shown.get((src_key, line, col)),
                      link_to=link("statement", sheet=src_key, row=line, column=col))]
        linear = auto is not None and manual is None
    else:
        title = "本行不取数"
    return source("manual" if manual else ("import" if "accounts" in row else "formula"), title, auto, items,
                  linear=linear and auto is not None, notes=notes, manual=manual)
