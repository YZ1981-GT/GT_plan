"""审定报表 / 报表分析的单元格来源（spec citar-cell-source-hover R5，design §6）。

- 内存里按报表生成同一顺序（``evaluation_order``）、同一取数器（``ReportFormulaParser``，加记录）重算资产负债表与利润表，不写库；
  审定口径读手工值，生效值进 ROW 缓存（与生成一致）。
- 公式拆项：原公式经 L1 内核 ``parse_to_ast``，按加减与常数倍算系数；TB / SUM_TB 再拆到各标准科目（含按前缀并入的下级）。
  含 IF / MIN / ABS / ROUND / 比较 / 两个引用相乘除的公式只列引用、不做合计核对。
- 上期 / 期初：写明来源（本年试算表期初 / 本项目上年试算表 / 上年项目报表同行 / 上年项目试算表 / 无来源）；
  前两种用带记录的取数器同样拆项。
- 库里的报表值与重算值不一致 ⇒ 「报表已过期，请重新生成」（未审口径不落库，不比）。
cell_key：``{row_code}:{current|prior}``。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.report_models import FinancialReport, FinancialReportType
from app.services.cell_source.schema import item, link, money, source
from app.services.formula_engine import (
    ASTBinOp, ASTCompare, ASTFuncCall, ASTNumber, ASTRangeSum, ASTRowRef, ASTString, ASTUnary, FormulaParseError,
    parse_to_ast,
)
from app.services.report_engine import ReportEngine, ReportFormulaParser
from app.services.report_manual_values import effective, load_manual, manual_value
from app.services.report_row_order import evaluation_order
from app.services.user_display_names import resolve_user_display_names

_ZERO = Decimal(0)
_CENT = Decimal("0.005")
#: 本轮接卡片的报表（其余页签隐藏，R5.7）
REPORT_TYPES = (FinancialReportType.balance_sheet, FinancialReportType.income_statement)
_ZERO_FUNCS = {"PREV": "上年数（报表生成时按 0）", "AUX": "辅助核算（报表生成时按 0）"}


class RecordingParser(ReportFormulaParser):
    """记下每次 TB / SUM_TB / PL_UNCLOSED 取数用到的试算表行与金额；求值结果与父类逐值相同（同一个 ``_row_amount``）。"""

    def __init__(self, *args: Any, **kw: Any) -> None:
        super().__init__(*args, **kw)
        #: (fn, 编码或区间, 列名) → [(标准码, 名称, 金额)]
        self.records: dict[tuple[str, str, str], list[tuple[str, str, Decimal]]] = {}
        self.pl_value: Decimal | None = None

    def _record(self, fn: str, arg: str, column: str, rows: list) -> None:
        out = []
        for r in rows:
            amount = self._row_amount(r, column)
            if amount is not None:
                out.append((r.standard_account_code, r.account_name or "", amount))
        self.records[(fn, arg, column)] = out

    async def _resolve_tb(self, account_code: str, column_name: str) -> Decimal:
        value = await super()._resolve_tb(account_code, column_name)
        if "~" not in account_code:  # TB 正则会误匹配 SUM_TB 的后半段，跳过
            self._record("TB", account_code, column_name, await self._get_tb_rows_prefix(account_code))
        return value

    async def _resolve_sum_tb(self, code_range: str, column_name: str) -> Decimal:
        value = await super()._resolve_sum_tb(code_range, column_name)
        self._record("SUM_TB", code_range, column_name, await self._sum_tb_rows(code_range) or [])
        return value

    async def resolve_pl_unclosed(self) -> Decimal | None:
        self.pl_value = await super().resolve_pl_unclosed()
        return self.pl_value


def _str_arg(node: Any) -> str:
    if isinstance(node, ASTString):
        return node.value
    if isinstance(node, ASTNumber):
        return str(node.value)
    if isinstance(node, ASTRowRef):
        return node.row_code
    return ""


def linear_leaves(node: Any) -> list[tuple[tuple, Decimal]] | None:
    """AST → [(叶子, 系数)]；常数叶子 ("NUM", 值)。非线性返回 None。"""
    if isinstance(node, ASTNumber):
        return [(("NUM", node.value), Decimal(1))]
    if isinstance(node, ASTString):
        return [(("NUM", Decimal(node.value)), Decimal(1))] if node.value.replace(".", "", 1).lstrip("-").isdigit() else []
    if isinstance(node, ASTRowRef):
        return [(("ROW", node.row_code), Decimal(1))]
    if isinstance(node, ASTRangeSum):
        return [(("SUM_ROW", node.start_code, node.end_code), Decimal(1))]
    if isinstance(node, ASTUnary):
        sub = linear_leaves(node.operand)
        return None if sub is None else [(k, -c) for k, c in sub]
    if isinstance(node, ASTBinOp):
        left, right = linear_leaves(node.left), linear_leaves(node.right)
        if left is None or right is None:
            return None
        if node.op in ("+", "-"):
            k = Decimal(1) if node.op == "+" else Decimal(-1)
            return left + [(leaf, c * k) for leaf, c in right]
        const_l, const_r = _const(left), _const(right)
        if node.op == "*":
            if const_l is not None:
                return [(leaf, c * const_l) for leaf, c in right]
            return [(leaf, c * const_r) for leaf, c in left] if const_r is not None else None
        if node.op == "/" and const_r:
            return [(leaf, c / const_r) for leaf, c in left]
        return None
    if isinstance(node, ASTFuncCall):
        args = [_str_arg(a) for a in node.args]
        if node.name in ("TB", "SUM_TB", "ADJ", "NOTE", "WP") + tuple(_ZERO_FUNCS):
            return [((node.name, *args), Decimal(1))]
        if node.name == "PL_UNCLOSED":
            return [(("PL_UNCLOSED",), Decimal(1))]
        if node.name in ("ROW", "REPORT"):
            return [(("ROW", args[0] if args else ""), Decimal(1))]
        if node.name == "SUM_ROW":
            return [(("SUM_ROW", *(args + ["", ""])[:2]), Decimal(1))]
    return None


def _const(terms: list[tuple[tuple, Decimal]]) -> Decimal | None:
    """全是常数时返回其值。"""
    if not all(leaf[0] == "NUM" for leaf, _ in terms):
        return None
    return sum((leaf[1] * c for leaf, c in terms), _ZERO)


def all_leaves(node: Any) -> list[tuple]:
    """非线性公式：只收集引用叶子（不算系数）。"""
    if isinstance(node, (ASTNumber, ASTString)):
        return []
    if isinstance(node, (ASTRowRef, ASTRangeSum)) or (isinstance(node, ASTFuncCall) and node.name not in
                                                      ("ABS", "ROUND", "MAX", "MIN", "IF")):
        terms = linear_leaves(node)
        return [leaf for leaf, _ in terms or []]
    children = []
    if isinstance(node, (ASTBinOp, ASTCompare)):
        children = [node.left, node.right]
    elif isinstance(node, ASTUnary):
        children = [node.operand]
    elif isinstance(node, ASTFuncCall):
        children = list(node.args)
    return [leaf for ch in children for leaf in all_leaves(ch)]


def _recording(parser: ReportFormulaParser, project_id: UUID, year: int) -> RecordingParser:
    rec = RecordingParser(parser.db, project_id, year)
    rec._use_unadjusted = parser._use_unadjusted
    rec._use_opening = parser._use_opening
    return rec


def _column_text(parser: ReportFormulaParser, column: str) -> str:
    if parser._use_opening:
        return f"{column}（按年初）"
    return f"{column}（未审口径）" if parser._use_unadjusted else f"{column}（审定口径）"


async def _prior_kind(resolver: Any, report_type: FinancialReportType) -> str | None:
    """上期金额实际来自哪一路（与 ``PriorPeriodResolver.prior_amount`` 同一判定顺序，读它已缓存的判定结果）。"""
    from app.services.report_prior_period import _BALANCE_TYPES

    if report_type in _BALANCE_TYPES:
        return "opening" if await resolver._opening_available() else None
    if await resolver._same_project_has_prior_tb():
        return "same_prior"
    pid = await resolver._find_prior_project()
    if pid is None:
        return None
    cache = resolver._prior_rows.get(report_type)
    if cache is not None and not cache["empty"]:
        return "prior_report"
    return "prior_tb" if await resolver._prior_project_has_tb(pid) else None


class _Rows:
    """一次重算的结果：每行本期 / 上期值、手工值、拆项用的取数器与 ROW 缓存快照。"""

    def __init__(self) -> None:
        self.row_name: dict[str, tuple[FinancialReportType, str]] = {}
        self.computed: dict[str, dict] = {}


async def _items(leaves: list[tuple[tuple, Decimal]], parser: RecordingParser, row_cache: dict[str, Decimal],
                 rows: _Rows, linear: bool) -> tuple[list[dict], bool]:
    """叶子 → 构成项；遇到取不到值的叶子（NOTE / WP）返回 linear=False。"""
    out: list[dict] = []
    for leaf, coef in leaves:
        kind = leaf[0]
        sign = coef if linear else Decimal(1)
        if kind == "NUM":
            if leaf[1]:
                out.append(item("常数", leaf[1], sign=sign))
        elif kind in ("TB", "SUM_TB"):
            arg = leaf[1] if len(leaf) > 1 else ""
            column = leaf[2] if len(leaf) > 2 else "期末余额"
            recs = parser.records.get((kind, arg, column))
            if recs is None:
                out.append(item(f"{kind}('{arg}')", None, sign=sign, detail="未取到"))
                linear = False
                continue
            if not recs:
                out.append(item(f"{arg} 试算表没有该科目", 0, sign=sign, detail=_column_text(parser, column)))
            nonzero = sorted((r for r in recs if r[2]), key=lambda r: r[0])
            for code, name, amount in nonzero or sorted(recs, key=lambda r: r[0])[:1]:
                out.append(item(f"{code} {name}".strip(), amount, sign=sign, detail=_column_text(parser, column),
                                link_to=link("trial_balance", code=code)))
            zeros = len(recs) - max(len(nonzero), 1)
            if zeros > 0:
                out.append(item(f"另有 {zeros} 个科目（含下级）金额为 0", None, sign=sign))
        elif kind == "PL_UNCLOSED":
            out.append(item("未结转损益（损益类科目未结平的余额，利润为正）", parser.pl_value or 0, sign=sign,
                            link_to=link("trial_balance")))
        elif kind == "ROW":
            rt, name = rows.row_name.get(leaf[1], (None, leaf[1]))
            out.append(item(f"{leaf[1]} {name}", row_cache.get(leaf[1], _ZERO), sign=sign,
                            link_to=link("reports", report_type=rt.value, code=leaf[1]) if rt else None))
        elif kind == "SUM_ROW":
            start, end = leaf[1], leaf[2]
            for code in sorted(c for c in row_cache if start <= c <= end):
                rt, name = rows.row_name.get(code, (None, code))
                out.append(item(f"{code} {name}", row_cache[code], sign=sign,
                                link_to=link("reports", report_type=rt.value, code=code) if rt else None))
        elif kind == "ADJ":
            from app.services.adjustment_amount_source import normalize_adj_type

            data = {} if parser._use_opening else await parser._get_adj_data()
            try:
                key = f"{normalize_adj_type(leaf[2] if len(leaf) > 2 else '')}_net"
            except ValueError:
                key = ""
            out.append(item(f"调整分录净额 {leaf[1] if len(leaf) > 1 else ''}", data.get(leaf[1], {}).get(key, _ZERO),
                            sign=sign, link_to=link("adjustments")))
        elif kind in _ZERO_FUNCS:
            out.append(item(_ZERO_FUNCS[kind], 0, sign=sign))
        else:  # NOTE / WP：取自附注 / 底稿，值在求值内部预载，这里不重取
            out.append(item(f"{kind}({', '.join(leaf[1:])})", None, sign=sign, detail="取自附注 / 底稿"))
            linear = False
    return out, linear


async def _decompose(formula: str | None, parser: RecordingParser, row_cache: dict[str, Decimal], rows: _Rows
                     ) -> tuple[list[dict], bool]:
    if not formula or not formula.strip():
        return [], True
    try:
        ast = parse_to_ast(formula)
    except FormulaParseError:
        return [], False
    leaves = linear_leaves(ast)
    if leaves is None:
        items, _ = await _items([(leaf, Decimal(1)) for leaf in all_leaves(ast)], parser, row_cache, rows, False)
        return items, False
    return await _items(leaves, parser, row_cache, rows, True)


_PRIOR_TITLES = {
    "opening": "期初余额：本年试算表期初数，按同一公式计算",
    "same_prior": "上期金额：本项目上年试算表，按同一公式计算",
    "prior_tb": "上期金额：上年项目「{name}」的试算表，按同一公式计算",
    "prior_report": "上期金额：上年项目「{name}」{year} 年报表同一行",
}


async def report_sources(db: AsyncSession, project_id: UUID, year: int, report_type: FinancialReportType,
                         mode: str = "audited") -> dict:
    """``{year, report_type, mode, cells: {"{行次}:{current|prior}": CellSource}, notices}``。"""
    from app.services.report_config_service import ReportConfigService
    from app.services.report_prior_period import PriorPeriodResolver

    unadjusted = mode == "unadjusted"
    engine = ReportEngine(db)
    standard = await ReportConfigService.resolve_applicable_standard(db, project_id)
    configs = await engine._load_report_configs(standard, project_id=project_id)
    cur = RecordingParser(db, project_id, year)
    cur._use_unadjusted = unadjusted
    prior = PriorPeriodResolver(db, project_id, year, unadjusted=unadjusted)
    prior._opening_parser = _recording(prior._opening_parser, project_id, year)
    prior._same_prior_parser = _recording(prior._same_prior_parser, project_id, year - 1)
    prior_pid = await prior._find_prior_project()
    if prior_pid is not None:
        prior._prior_tb_parser = RecordingParser(db, prior_pid, year - 1)
    prior_name = (await db.get(Project, prior_pid)).name if prior_pid else ""

    rows = _Rows()
    for rt in REPORT_TYPES:
        for c in configs.get(rt, []):
            rows.row_name[c.row_code] = (rt, (c.row_name or "").strip())
    row_cache: dict[str, Decimal] = {}
    manual_rows: dict[str, dict] = {}
    for rt in REPORT_TYPES:
        manual = await load_manual(db, project_id, year, rt) if not unadjusted else {}
        manual_rows.update(manual)
        for cfg in evaluation_order(configs.get(rt, [])):
            auto = await cur.execute(cfg.formula, row_cache) if cfg.formula else _ZERO
            m = manual.get(cfg.row_code)
            row_cache[cfg.row_code] = effective(m, "current", auto) or _ZERO
            try:
                p_auto = await prior.prior_amount(rt, cfg)
                p_kind = await _prior_kind(prior, rt)
            except Exception:  # noqa: BLE001 —— 与报表生成同：上期取不到留空
                p_auto, p_kind = None, None
            if manual_value(m, "prior")[0]:
                prior.override(cfg.row_code, effective(m, "prior", p_auto))
            rows.computed[cfg.row_code] = {
                "cfg": cfg, "rt": rt, "auto": auto, "p_auto": p_auto, "p_kind": p_kind, "manual": m,
                # SUM_ROW 按区间取 ROW 缓存：存下求值当时的快照（之后的行会继续写进缓存）
                "cache": dict(row_cache),
                "p_cache": dict(prior._opening_cache if rt == FinancialReportType.balance_sheet else
                                prior._same_prior_cache if p_kind == "same_prior" else prior._prior_tb_cache),
            }

    stored = {} if unadjusted else {
        r.row_code: (r.current_period_amount, r.prior_period_amount)
        for r in (await db.execute(sa.select(FinancialReport).where(
            FinancialReport.project_id == project_id, FinancialReport.year == year,
            FinancialReport.report_type == report_type, FinancialReport.is_deleted == sa.false(),
        ))).scalars().all()
    }
    editors = await resolve_user_display_names(db, [m.get("by") for m in manual_rows.values() if m])
    p_parser = {"opening": prior._opening_parser, "same_prior": prior._same_prior_parser, "prior_tb": prior._prior_tb_parser}
    basis = "未审口径：试算表未审数，不含调整分录" if unadjusted else "审定口径：试算表审定数（未审数 + 已批准调整）"

    cells: dict[str, dict] = {}
    for code, c in rows.computed.items():
        if c["rt"] != report_type:
            continue
        cfg, m = c["cfg"], c["manual"]
        formula = (cfg.formula or "").strip()
        for col in ("current", "prior"):
            is_manual, mv = manual_value(m, col)
            auto = c["auto"] if col == "current" else c["p_auto"]
            notes: list[str] = []
            if col == "current":
                items, linear = await _decompose(formula, cur, c["cache"], rows)
                title = f"公式：{formula}" if formula else "本行没有公式，按 0"
                notes.append(basis)
            elif c["p_kind"] is None:
                items, linear = [], False
                title = "上期 / 期初金额无来源（本年试算表没有期初数，或找不到上年项目 / 上年试算表），留空"
            elif c["p_kind"] == "prior_report":
                items, linear = [item(f"上年项目「{prior_name}」{year - 1} 年报表", auto)], True
                title = _PRIOR_TITLES["prior_report"].format(name=prior_name, year=year - 1)
            else:
                items, linear = await _decompose(formula, p_parser[c["p_kind"]], c["p_cache"], rows)
                title = _PRIOR_TITLES[c["p_kind"]].format(name=prior_name) + (f"：{formula}" if formula else "")
            shown = mv if is_manual else auto
            issue = None
            if code in stored:
                db_value = stored[code][0 if col == "current" else 1]
                if (db_value is None) != (shown is None) or (
                        db_value is not None and shown is not None and abs(Decimal(db_value) - shown) >= _CENT):
                    issue = "报表已过期：按当前试算表重算的值与报表里的不一致，请重新生成报表"
            manual = None
            if is_manual:
                manual = {"value": money(mv), "auto": money(auto),
                          "by_name": editors.get(str(m.get("by"))) if m.get("by") else None, "at": m.get("at")}
            cells[f"{code}:{col}"] = source("manual" if is_manual else "formula", title, auto, items,
                                            linear=linear and auto is not None, notes=notes, issue=issue, manual=manual)
    return {"year": year, "report_type": report_type.value, "mode": mode, "cells": cells, "notices": []}
