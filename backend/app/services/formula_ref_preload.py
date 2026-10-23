"""取数引用按值代入（spec formula-governance-coverage-closure R7a / R6）。

表间审核、报表「审核」里配置的公式与底稿可编辑公式要**严格取数**：取不到数就写明原因，不能代入 0 后接着算
（另一侧恰好是 0 时，「取不到」会被当成「相等、通过」；底稿单元格会显示一个假的 0）。L1 内核的
PREV / AUX / ROW / REPORT / NOTE 在上下文缺数时都返回 0，所以严格路径在求值前先用本模块把这些引用换成真实数值，
缺数即记原因。

口径：

* ``PREV('科目','列')`` / ``PREV(TB('科目','列'))``：上年（年度 − 1）试算表，科目按前缀聚合（与 TB 同口径）；上年数据
  来源是同项目上年 → 上年项目（``prior_year_context``）。都没有上年试算表 ⇒ 缺数；有数据但没有该科目 ⇒ 0（合法的 0）。
* ``PREV('底稿','表','字段')`` 三参：上年同底稿取数 —— 本底稿该字段的现行取数定义在上年数据上求值（``prev_wp_field``）；
  没有定义、定义不能在上年数据上重算、上年数据取不到 ⇒ 缺数并写明原因。
* ``AUX('科目','辅助类型','辅助项','列')``：辅助核算余额表的当前数据集（``get_active_filter``），科目按前缀，
  辅助项按名称或编码匹配。该科目本年没有辅助核算余额、或找不到这个辅助项 ⇒ 缺数。
* ``AUX('科目','类型或辅助项','列')`` / ``AUX('科目','类型或辅助项')``（列缺省期末余额）：第二参先按辅助类型
  匹配（该类型全部辅助项合计）；不是辅助类型时按辅助项名称或编码匹配（地址选择器生成的就是这种写法）。
  同一辅助项出现在多个辅助类型下 ⇒ 缺数（请用四参写法指明类型），不跨类型相加。
* ``ROW('行次')`` / ``SUM_ROW('起','止')`` / ``REPORT('行次','期间')``：本年度已生成的报表（``financial_report``）。
  ROW / SUM_ROW 取本期金额；REPORT 的期间含 期初 / 上期 / 上年 / 年初 取上期金额，含 期末 / 本期 / 本年 / 年末
  取本期金额，其余写法 ⇒ 缺数。本年度报表没有任何行、行次不存在、金额为空 ⇒ 缺数。
* ``NOTE('章节','行','列')`` / ``NOTE('章节','行')``（列缺省第一个数据列）：本年度附注（``disclosure_notes``）。
  先在主表找，主表没有该行再到其余表格里找（多张表都有 ⇒ 缺数）；行「合计」找不到同名行时取主表最后一个合计行；
  列名先精确匹配表头；只写期间（期末 / 期初 / 本期 …）时按期间语义匹配唯一一列（多列同期间 ⇒ 缺数，请写完整列名）。
  章节没有、行或列找不到、表头与数据列数不一致、单元格为空 ⇒ 缺数。
* 列名不认识、写法识别不了（例如少参数）⇒ 缺数 —— 不让它落进求值器被静默求 0。

``strict=False`` 时缺数代入 0（供非严格调用方保持置 0 行为）。
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

_Q = r"\s*'([^']*)'\s*"
#: 前面不能紧挨标识符字符：``TB_AUX(…)`` 里的 ``AUX(`` 不是 AUX 引用，``SUM_ROW(`` 里的 ``ROW(`` 不是 ROW
_START = r"(?<![A-Za-z0-9_])"
PREV_TB_RE = re.compile(_START + r"PREV\(\s*TB\(" + _Q + "," + _Q + r"\)\s*\)")
PREV_RE = re.compile(_START + r"PREV\(" + _Q + "," + _Q + r"\)")
PREV3_RE = re.compile(_START + r"PREV\(" + _Q + "," + _Q + "," + _Q + r"\)")
AUX4_RE = re.compile(_START + r"AUX\(" + _Q + "," + _Q + "," + _Q + "," + _Q + r"\)")
AUX3_RE = re.compile(_START + r"AUX\(" + _Q + "," + _Q + "," + _Q + r"\)")
AUX2_RE = re.compile(_START + r"AUX\(" + _Q + "," + _Q + r"\)")
ROW_RE = re.compile(_START + r"ROW\(" + _Q + r"\)")
SUM_ROW_RE = re.compile(_START + r"SUM_ROW\(" + _Q + "," + _Q + r"\)")
REPORT_RE = re.compile(_START + r"REPORT\(" + _Q + r"(?:," + _Q + r")?\)")
NOTE_RE = re.compile(_START + r"NOTE\(" + _Q + "," + _Q + r"(?:," + _Q + r")?\)")
_LEFTOVER_RE = re.compile(_START + r"(PREV|AUX)\s*\(")
_LEFTOVER_REPORT_NOTE_RE = re.compile(_START + r"(ROW|SUM_ROW|REPORT|NOTE)\s*\(")

#: 辅助核算余额表的列（中文列名 → ORM 字段）；期末 / 期初 是地址选择器生成的写法
AUX_COLUMNS = {
    "期末余额": "closing_balance", "期末": "closing_balance",
    "期初余额": "opening_balance", "年初余额": "opening_balance", "期初": "opening_balance",
    "借方发生额": "debit_amount", "本期借方": "debit_amount", "本期借方发生额": "debit_amount",
    "贷方发生额": "credit_amount", "本期贷方": "credit_amount", "本期贷方发生额": "credit_amount",
}
_DEFAULT_AUX_COLUMN = "期末余额"

#: 期间关键词：先认上期（「上年年末余额」是上期），再认本期
_PRIOR_PERIOD_WORDS = ("期初", "上期", "上年", "年初", "prior")
_CURRENT_PERIOD_WORDS = ("期末", "本期", "本年", "年末", "current")
_PERIOD_SHORTHAND = frozenset(_PRIOR_PERIOD_WORDS + _CURRENT_PERIOD_WORDS)


def has_prev_or_aux(expression: str) -> bool:
    return bool(_LEFTOVER_RE.search(expression or ""))


def has_report_or_note(expression: str) -> bool:
    return bool(_LEFTOVER_REPORT_NOTE_RE.search(expression or ""))


def period_kind(period: str | None) -> str | None:
    """期间写法 → ``"current"`` / ``"prior"``；空串按本期；认不出 ⇒ ``None``。"""
    text = (period or "").strip()
    if not text:
        return "current"
    if any(word in text for word in _PRIOR_PERIOD_WORDS):
        return "prior"
    if any(word in text for word in _CURRENT_PERIOD_WORDS):
        return "current"
    return None


@dataclass
class Substitution:
    """代入结果：``expression`` 里的引用已换成数值；``missing`` 是取不到数的原因（严格时非空即不可求值）。"""

    expression: str
    missing: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AuxRef:
    """一处 AUX 引用：``args`` 是科目之后的参数（原样，不去空白），``aux_ref_key(args)`` 即 L1 取值键。"""

    token: str
    account: str
    args: tuple[str, ...]


def _literal(value: Decimal) -> str:
    return f"({value})"


def _to_decimal(raw: Any) -> Decimal | None:
    """单元格 / 金额 → Decimal；空值或非数值 ⇒ ``None``。"""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float, Decimal)):
        return Decimal(str(raw))
    if isinstance(raw, str):
        text = raw.strip().replace(",", "")
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None
    return None


async def _aux_rows(db: AsyncSession, project_id: uuid.UUID, year: int, account: str) -> list[Any]:
    from app.models.audit_platform_models import TbAuxBalance
    from app.services.dataset_query import get_active_filter

    active = await get_active_filter(db, TbAuxBalance.__table__, project_id, year, strict=True)
    return list((await db.execute(sa.select(
        TbAuxBalance.aux_type, TbAuxBalance.aux_code, TbAuxBalance.aux_name,
        TbAuxBalance.closing_balance, TbAuxBalance.opening_balance,
        TbAuxBalance.debit_amount, TbAuxBalance.credit_amount,
    ).where(active, TbAuxBalance.account_code.like(f"{account}%")))).all())


def _sum(rows: list[Any], column: str) -> Decimal:
    return sum((Decimal(str(getattr(r, column) or 0)) for r in rows), Decimal("0"))


def parse_aux_refs(expression: str) -> list[AuxRef]:
    """按出现顺序列出 AUX 引用（四参 / 三参 / 两参三种写法互斥，各自以右括号收尾）。"""
    text = expression or ""
    found: list[tuple[int, AuxRef]] = []
    for regex in (AUX4_RE, AUX3_RE, AUX2_RE):
        for m in regex.finditer(text):
            found.append((m.start(), AuxRef(m.group(0), m.group(1), tuple(m.groups()[1:]))))
    return [ref for _, ref in sorted(found, key=lambda item: item[0])]


def _pick_aux_rows(rows: list[Any], args: tuple[str, ...]) -> tuple[list[Any] | None, str, str]:
    """按写法挑出参与合计的辅助余额行 → ``(行, 列名, 缺数原因)``。"""
    if len(args) == 3:
        aux_type, item, column = args
        hit = [r for r in rows if (r.aux_type or "") == aux_type and item in ((r.aux_name or ""), (r.aux_code or ""))]
        return (hit, column, "") if hit else (None, column, f"没有「{aux_type}」辅助项「{item}」")
    what = args[0]
    column = args[1] if len(args) > 1 else _DEFAULT_AUX_COLUMN
    typed = [r for r in rows if (r.aux_type or "") == what]
    if typed:
        return typed, column, ""
    items = [r for r in rows if what in ((r.aux_name or ""), (r.aux_code or ""))]
    if not items:
        return None, column, f"没有「{what}」辅助核算余额（既不是辅助类型，也不是辅助项）"
    kinds = sorted({r.aux_type or "" for r in items})
    if len(kinds) > 1:
        return None, column, f"辅助项「{what}」出现在多个辅助类型（{'、'.join(kinds)}）下，请用四参写法指明辅助类型"
    return items, column, ""


async def resolve_aux_refs(db: AsyncSession, project_id: uuid.UUID, year: int,
                           refs: list[AuxRef]) -> dict[str, tuple[Decimal | None, str]]:
    """逐个 AUX 引用取数 → ``{引用原文: (金额 | None, 缺数原因)}``。调用方负责保存点。"""
    out: dict[str, tuple[Decimal | None, str]] = {}
    cache: dict[str, list[Any]] = {}
    for ref in refs:
        if ref.token in out:
            continue
        if ref.account not in cache:
            cache[ref.account] = await _aux_rows(db, project_id, year, ref.account)
        rows = cache[ref.account]
        if not rows:
            out[ref.token] = (None, f"科目 {ref.account} 本年无辅助核算余额")
            continue
        hit, column, reason = _pick_aux_rows(rows, ref.args)
        attr = AUX_COLUMNS.get(column.strip())
        if attr is None:
            out[ref.token] = (None, f"列名「{column}」无法识别")
        elif hit is None:
            out[ref.token] = (None, f"科目 {ref.account} {reason}")
        else:
            out[ref.token] = (_sum(hit, attr), "")
    return out


async def substitute_prev_aux(expression: str, *, db: AsyncSession, project_id: uuid.UUID, year: int,
                              strict: bool = True) -> Substitution:
    """把 ``expression`` 里的 PREV / AUX 换成数值。读库包在保存点里：失败不会让调用方的事务停在中止状态。"""
    from app.services.formula_engine import COLUMN_ALIASES

    text = expression or ""
    if not has_prev_or_aux(text):
        return Substitution(text)
    out = Substitution(text)

    def put(token: str, value: Decimal | None, reason: str = "") -> None:
        if value is None:
            out.missing.append(f"{token}：{reason}")
            value = Decimal("0")
        out.expression = out.expression.replace(token, _literal(value), 1)

    async with db.begin_nested():
        prev3 = list(PREV3_RE.finditer(text))
        prev_hits = [(m.group(0), m.group(1), m.group(2)) for m in (*PREV_TB_RE.finditer(text), *PREV_RE.finditer(text))]
        if prev3 or prev_hits:
            from app.services.formula_preloader import _load_tb
            from app.services.prev_wp_field import PriorWpFieldResolver

            resolver = PriorWpFieldResolver(db, project_id, year)
            for m in prev3:
                hit = await resolver.resolve(m.group(1), m.group(2), m.group(3))
                put(m.group(0), hit.value, hit.reason)
            if prev_hits:
                source = await resolver.source()
                occurrence = any(COLUMN_ALIASES.get(column.strip()) in ("本期借方", "本期贷方")
                                 for _, _, column in prev_hits)
                prior = None if source.project_id is None else await _load_tb(
                    db, source.project_id, source.year, {code for _, code, _ in prev_hits},
                    with_occurrence=occurrence)
                for token, code, column in prev_hits:
                    std = COLUMN_ALIASES.get(column.strip())
                    if std is None:
                        put(token, None, f"列名「{column}」无法识别")
                    elif prior is None:
                        put(token, None, source.reason)
                    else:
                        put(token, Decimal(str((prior.get(code) or {}).get(std, Decimal("0")))))

        refs = parse_aux_refs(text)
        if refs:
            resolved = await resolve_aux_refs(db, project_id, year, refs)
            for ref in refs:
                value, reason = resolved[ref.token]
                put(ref.token, value, reason)

    for m in _LEFTOVER_RE.finditer(out.expression):
        out.missing.append(f"{m.group(1)} 写法无法识别（PREV 需「科目, 列」或「底稿, 表, 字段」，"
                           "AUX 需「科目, 辅助类型[, 辅助项], 列」）")
        break
    if not strict:
        out.missing = []
    return out


# ── 报表行 / 附注 ───────────────────────────────────────────────────────────────


async def load_report_rows(db: AsyncSession, project_id: uuid.UUID,
                           year: int) -> dict[str, tuple[Decimal | None, Decimal | None]]:
    """本年度已生成报表 → ``{行次: (本期金额, 上期金额)}``；空字典 = 本年度报表未生成。"""
    from app.models.report_models import FinancialReport

    rows = (await db.execute(sa.select(
        FinancialReport.row_code, FinancialReport.current_period_amount, FinancialReport.prior_period_amount,
    ).where(FinancialReport.project_id == project_id, FinancialReport.year == year,
            FinancialReport.is_deleted == sa.false()))).all()
    return {r.row_code: (r.current_period_amount, r.prior_period_amount) for r in rows if r.row_code}


async def _note_table_data(db: AsyncSession, project_id: uuid.UUID, year: int, section: str) -> tuple[bool, Any]:
    """``(章节是否存在, table_data)``。"""
    from app.models.report_models import DisclosureNote

    row = (await db.execute(sa.select(DisclosureNote.table_data).where(
        DisclosureNote.project_id == project_id, DisclosureNote.year == year,
        DisclosureNote.note_section == section, DisclosureNote.is_deleted == sa.false()))).first()
    return (row is not None), (row[0] if row is not None else None)


def _note_tables(table_data: Any) -> tuple[dict | None, list[dict]]:
    """``(主表, 其余表格)``。``_tables`` 第一张通常就是主表的副本（行相同），不算「其余表格」。"""
    if not isinstance(table_data, dict):
        return None, []
    main = {"name": table_data.get("name") or "", "headers": table_data.get("headers"),
            "rows": table_data.get("rows")}
    if not isinstance(main["rows"], list):
        main = None
    others = [t for t in table_data.get("_tables") or []
              if isinstance(t, dict) and isinstance(t.get("rows"), list)
              and not (main is not None and t.get("rows") == main["rows"])]
    return main, others


def _note_rows(table: dict, label: str) -> list[dict]:
    rows = [r for r in table["rows"] if isinstance(r, dict)]
    wanted = label.strip()
    exact = [r for r in rows if str(r.get("label") or "").strip() == wanted]
    if exact or wanted not in ("合计", "*", ""):
        return exact
    totals = [r for r in rows if r.get("is_total")]
    return totals[-1:]


def _note_column(headers: list, column: str) -> tuple[int | None, str]:
    """列名 → 数据列下标（``values`` 与 ``headers[1:]`` 对齐）。"""
    data_headers = [str(h or "").strip() for h in headers[1:]]
    wanted = column.strip()
    if not wanted:
        return (0, "") if data_headers else (None, "表格没有数据列")
    exact = [i for i, h in enumerate(data_headers) if h == wanted]
    if len(exact) == 1:
        return exact[0], ""
    if len(exact) > 1:
        return None, f"列「{wanted}」出现多次"
    # 只有单写期间（期末 / 期初 / 本期 …）才按期间语义找列；「本期发生额」这类完整列名不做模糊匹配
    kind = period_kind(wanted) if wanted in _PERIOD_SHORTHAND else None
    if kind is not None:
        same = [i for i, h in enumerate(data_headers) if h and period_kind(h) == kind]
        if len(same) == 1:
            return same[0], ""
        if len(same) > 1:
            return None, f"列「{wanted}」对应多列（{'、'.join(data_headers[i] for i in same)}），请写完整列名"
    return None, f"没有「{wanted}」列（表头：{'、'.join(h for h in data_headers if h) or '无'}）"


def _note_cell(table_data: Any, section: str, label: str, column: str) -> tuple[Decimal | None, str]:
    main, others = _note_tables(table_data)
    if main is None and not others:
        return None, f"附注 {section} 没有表格"
    main_rows = _note_rows(main, label) if main is not None else []
    if main_rows:
        hits = [(main, main_rows)]
    else:
        hits = [(t, rows) for t in others if (rows := _note_rows(t, label))]
        if len(hits) > 1:
            names = "、".join(str(t.get("name") or "未命名") for t, _ in hits)
            return None, f"附注 {section} 有多张表格都有「{label}」行（{names}）"
    if not hits:
        return None, f"附注 {section} 没有「{label}」行"
    table, rows = hits[0]
    if len(rows) > 1:
        return None, f"附注 {section}「{label}」行出现多次"
    headers = table.get("headers") if isinstance(table.get("headers"), list) else []
    values = rows[0].get("values")
    if not isinstance(values, list) or not headers or len(values) != len(headers) - 1:
        return None, f"附注 {section} 表头与数据列数不一致，无法按列名定位"
    idx, reason = _note_column(headers, column)
    if idx is None:
        return None, f"附注 {section} {reason}"
    value = _to_decimal(values[idx])
    if value is None:
        return None, f"附注 {section}「{label}」行「{headers[idx + 1]}」列为空或不是数值"
    return value, ""


async def substitute_report_note_refs(expression: str, *, db: AsyncSession, project_id: uuid.UUID, year: int,
                                      strict: bool = True) -> Substitution:
    """把 ``expression`` 里的 ROW / SUM_ROW / REPORT / NOTE 换成数值（本年度报表 / 附注）。读库包在保存点里。"""
    text = expression or ""
    if not has_report_or_note(text):
        return Substitution(text)
    out = Substitution(text)

    def put(token: str, value: Decimal | None, reason: str = "") -> None:
        if value is None:
            out.missing.append(f"{token}：{reason}")
            value = Decimal("0")
        out.expression = out.expression.replace(token, _literal(value), 1)

    async with db.begin_nested():
        report_hits = [*SUM_ROW_RE.finditer(text), *ROW_RE.finditer(text), *REPORT_RE.finditer(text)]
        if report_hits:
            rows = await load_report_rows(db, project_id, year)
            not_generated = f"本年度（{year}）报表未生成"
            for m in SUM_ROW_RE.finditer(text):
                start, end = m.group(1).strip(), m.group(2).strip()
                codes = sorted(code for code in rows if start <= code <= end)
                if not rows:
                    put(m.group(0), None, not_generated)
                elif not codes:
                    put(m.group(0), None, f"报表行区间 {start}~{end} 无数据")
                elif empty := [code for code in codes if rows[code][0] is None]:
                    put(m.group(0), None, f"报表行 {'、'.join(empty)} 本期金额为空")
                else:
                    put(m.group(0), sum((Decimal(str(rows[code][0])) for code in codes), Decimal("0")))
            for m, code, kind in [*((m, m.group(1).strip(), "current") for m in ROW_RE.finditer(text)),
                                  *((m, m.group(1).strip(), period_kind(m.group(2))) for m in REPORT_RE.finditer(text))]:
                if kind is None:
                    put(m.group(0), None, f"期间「{m.group(2)}」无法识别（本期写 期末 / 本期 / 本年，上期写 期初 / 上期 / 上年）")
                elif not rows:
                    put(m.group(0), None, not_generated)
                elif code not in rows:
                    put(m.group(0), None, f"报表行 {code} 不存在")
                else:
                    amount = rows[code][0 if kind == "current" else 1]
                    label = "本期" if kind == "current" else "上期"
                    put(m.group(0), None if amount is None else Decimal(str(amount)), f"报表行 {code} {label}金额为空")

        note_cache: dict[str, tuple[bool, Any]] = {}
        for m in NOTE_RE.finditer(text):
            section, label, column = m.group(1).strip(), m.group(2), m.group(3) or ""
            if section not in note_cache:
                note_cache[section] = await _note_table_data(db, project_id, year, section)
            exists, table_data = note_cache[section]
            if not exists:
                put(m.group(0), None, f"本年度（{year}）附注没有章节 {section}")
                continue
            value, reason = _note_cell(table_data, section, label, column)
            put(m.group(0), value, reason)

    for m in _LEFTOVER_REPORT_NOTE_RE.finditer(out.expression):
        out.missing.append(f"{m.group(1)} 写法无法识别（ROW 需「行次」，SUM_ROW 需「起, 止」，"
                           "REPORT 需「行次, 期间」，NOTE 需「章节, 行[, 列]」）")
        break
    if not strict:
        out.missing = []
    return out


async def substitute_value_refs(expression: str, *, db: AsyncSession, project_id: uuid.UUID, year: int,
                                strict: bool = True) -> Substitution:
    """PREV / AUX / ROW / SUM_ROW / REPORT / NOTE 全部按值代入（底稿可编辑公式用）。"""
    first = await substitute_prev_aux(expression, db=db, project_id=project_id, year=year, strict=strict)
    second = await substitute_report_note_refs(first.expression, db=db, project_id=project_id, year=year,
                                               strict=strict)
    return Substitution(second.expression, [*first.missing, *second.missing])
