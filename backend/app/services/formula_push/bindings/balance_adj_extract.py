"""审定表族「审定合计（原值）/ 净值」的真实来源（逐底稿声明）。

spec formula-fetch-followup-defect-closure R6.3：原先 26 个动态行规格一律读 ``{X}-1-rows`` 的 rowId 清单 +
扁平 ``{X}-1-{rowId}-unadj/-aje/-rje`` 键，前端只有 K2 真是这种存法；其余底稿全部读空，真库 G / H / I 的
``{X}-1-audited-receivable/net`` 全是 ``'0'``，H1 / I1 附注 builder 再拿这个 0 写进附注主表。

本模块逐底稿声明前端**实际**持久化的东西（每条注释写明前端出处，均现读确认），备抵按减项；
读不到 ⇒ ``None``，派生目标写空（``policy='derived'`` 的空值语义），不写假的 0。

四种来源：

* :class:`Rows` —— JSON 行清单（``remark`` 存数组）。原值清单 ``sign=+1``、备抵清单 ``sign=-1``；合计 / 小计行跳过。
  主清单（第一张 ``sign=+1`` 的）缺失、不是数组或是空数组 ⇒ 读不到；备抵清单缺失按 0（与前端缺省空行一致）。
* :class:`Key` —— 前端已持久化的合计键（数值字符串）；``column='conclusion'`` 从结论列读（G 族发布的审定数）。
* :class:`ByMode` —— 按模式键选来源（H3 成本 / 公允价值模式）。
* :class:`Unavailable` —— 前端没有可读的审定合计，写明原因。
"""
from __future__ import annotations

import json
import math
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Union

from app.services.formula_push.bindings.balance_adj_calc import _round2

#: 行清单里不计入的行名（前端持久化时一般已剔除合计 / 小计行；这里再挡一次，防旧数据双计）
_SKIP_NAMES = frozenset({"合计", "小计", "TB数据", "差异"})
_NAME_FIELDS = ("name", "category", "projectName", "investee")
_SKIP_FLAGS = ("isSubtotal", "isTotal")
#: 行金额字段组
U_AJE_RJE = ("unadjusted", "aje", "rje")
END_UNADJ_ADJ = ("endUnadjusted", "endAdjustment")


@dataclass(frozen=True)
class RowList:
    """一张 JSON 行清单。``sign`` +1 计入 / −1 减项（备抵）。"""

    item_id: str
    sign: int = 1
    #: 只取 ``row[section_field]``（缺省按 ``section_default``）等于 ``section`` 的行（H4 一个数组放原值 / 减值两段）
    section: str | None = None
    section_field: str = "section"
    section_default: str | None = None
    #: 主键读不到时依次尝试的历史键（与前端加载候选同序）
    alternates: tuple[str, ...] = ()


@dataclass(frozen=True)
class Rows:
    lists: tuple[RowList, ...]
    #: 行金额字段组，依次尝试：行里出现该组任一字段就按该组求和（新旧两种行结构并存）
    amount_fields: tuple[tuple[str, ...], ...] = (U_AJE_RJE,)


@dataclass(frozen=True)
class Key:
    """前端已持久化的合计键。"""

    item_id: str
    column: str = "remark"


@dataclass(frozen=True)
class Unavailable:
    reason: str


@dataclass(frozen=True)
class ByMode:
    mode_key: str
    cases: tuple[tuple[str, "Source"], ...]
    default: "Source"


Source = Union[Rows, Key, Unavailable, ByMode]


@dataclass(frozen=True)
class AuditedTotals:
    """一张审定表的两个派生合计：``receivable`` 原值（账面余额）、``net`` 账面价值。"""

    receivable: Source
    net: Source
    #: 前端出处（组合函数 / 存储键），写进推送规则的说明
    origin: str


# ── 求值 ──────────────────────────────────────────────────────────────────────


def evaluate(
    totals: AuditedTotals, kind: str | None, entries: Mapping[str, Any], conclusions: Mapping[str, Any],
) -> float | None:
    """按 kind（receivable / net）求审定合计；读不到返回 ``None``。"""
    if kind == "receivable":
        return _eval(totals.receivable, entries, conclusions)
    if kind == "net":
        return _eval(totals.net, entries, conclusions)
    raise ValueError(f"审定合计 kind={kind!r} 不合法")


def _eval(source: Source, entries: Mapping[str, Any], conclusions: Mapping[str, Any]) -> float | None:
    if isinstance(source, Unavailable):
        return None
    if isinstance(source, Key):
        store = conclusions if source.column == "conclusion" else entries
        return _parse_number(_text(store.get(source.item_id)))
    if isinstance(source, ByMode):
        mode = (_text(entries.get(source.mode_key)) or "").strip()
        for value, case in source.cases:
            if mode == value:
                return _eval(case, entries, conclusions)
        return _eval(source.default, entries, conclusions)
    if isinstance(source, Rows):
        return _eval_rows(source, entries)
    raise TypeError(f"未知的审定合计来源 {source!r}")


def _eval_rows(source: Rows, entries: Mapping[str, Any]) -> float | None:
    primary = next(rl for rl in source.lists if rl.sign > 0)
    total = 0.0
    for rl in source.lists:
        rows = _rows_of(entries, rl)
        if rows is None:
            if rl is primary:
                return None
            continue
        for row in rows:
            if _counts(row, rl):
                total += rl.sign * _row_amount(row, source.amount_fields)
    return _round2(total)


def _text(raw: Any) -> Any:
    """条目值：引擎快照是列值本身；部分调用方传 ``{remark, ...}``。"""
    if isinstance(raw, dict):
        return raw.get("remark") if raw.get("remark") not in (None, "") else raw.get("value")
    return raw


def _parse_number(raw: Any) -> float | None:
    """合计键的值：空 / 不是数 ⇒ ``None``（读不到），不当成 0。"""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        number = float(raw)
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    else:
        return None
    return _round2(number) if math.isfinite(number) else None


def _rows_of(entries: Mapping[str, Any], rl: RowList) -> list[Any] | None:
    """读一张行清单：主键 → 历史键，第一个非空 JSON 数组；都没有 ⇒ ``None``。"""
    for item_id in (rl.item_id, *rl.alternates):
        raw = _text(entries.get(item_id))
        if isinstance(raw, str):
            if not raw.strip():
                continue
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
        if isinstance(raw, list) and raw:
            return raw
    return None


def _counts(row: Any, rl: RowList) -> bool:
    if not isinstance(row, dict):
        return False
    if any(row.get(flag) for flag in _SKIP_FLAGS):
        return False
    name = next((str(row[f]).strip() for f in _NAME_FIELDS if row.get(f) not in (None, "")), "")
    if name in _SKIP_NAMES:
        return False
    if rl.section is not None:
        value = row.get(rl.section_field)
        if value in (None, ""):
            value = rl.section_default
        if value != rl.section:
            return False
    return True


def _row_amount(row: Mapping[str, Any], groups: tuple[tuple[str, ...], ...]) -> float:
    """行审定数：第一组在行里出现过的字段求和（前端 ``Number(x) || 0`` 同口径）。"""
    for group in groups:
        if any(row.get(f) is not None for f in group):
            return _round2(sum(_to_float(row.get(f)) for f in group))
    return 0.0


def _to_float(value: Any) -> float:
    if value is None or isinstance(value, bool):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _walk(source: Source) -> Iterator[Source]:
    yield source
    if isinstance(source, ByMode):
        for _, case in source.cases:
            yield from _walk(case)
        yield from _walk(source.default)


def conclusion_keys(totals: AuditedTotals) -> tuple[str, ...]:
    """需要从结论列读的合计键（binding 取数时一次查齐；引擎快照只带 remark 列）。"""
    keys = [
        s.item_id
        for root in (totals.receivable, totals.net)
        for s in _walk(root)
        if isinstance(s, Key) and s.column == "conclusion"
    ]
    return tuple(dict.fromkeys(keys))


def describe(source: Source) -> str:
    """来源的中文说明（推送规则的算式说明由此生成，守卫钉死两者一致）。"""
    if isinstance(source, Unavailable):
        return f"留空：{source.reason}"
    if isinstance(source, Key):
        where = "（结论列）" if source.column == "conclusion" else ""
        return f"前端已保存的合计「{source.item_id}」{where}"
    if isinstance(source, ByMode):
        cases = "；".join(f"{value}：{describe(case)}" for value, case in source.cases)
        return f"按「{source.mode_key}」取：{cases}；其他：{describe(source.default)}"
    if isinstance(source, Rows):
        terms = []
        for index, rl in enumerate(source.lists):
            name = f"「{rl.item_id}」"
            if rl.section is not None:
                name += f"中 {rl.section_field}={rl.section} 的行"
            sign = "" if index == 0 and rl.sign > 0 else ("+ " if rl.sign > 0 else "− ")
            terms.append(f"{sign}{name}")
        fields = "，或 ".join(" + ".join(group) for group in source.amount_fields)
        return f"行合计 {' '.join(terms)}（每行 {fields}）"
    raise TypeError(f"未知的审定合计来源 {source!r}")


def formula_text(account_name: str, totals: AuditedTotals, kind: str) -> str:
    """推送规则 ``source.formula_text``：``{科目}审定合计（原值 / 净值）= 来源；读不到时留空``。"""
    label = "原值" if kind == "receivable" else "净值"
    source = totals.receivable if kind == "receivable" else totals.net
    tail = "" if isinstance(source, Unavailable) else "；读不到时留空，不写 0"
    return f"{account_name}审定合计（{label}）= {describe(source)}{tail}"


# ── 逐底稿声明（前端出处均现读确认；改前端存储时须同步这里，守卫按此生成规则说明） ──────────────


def _same(source: Source, origin: str) -> AuditedTotals:
    """无备抵：原值 = 净值。"""
    return AuditedTotals(receivable=source, net=source, origin=origin)


def _blocks(
    gross: str, *contra: str, fields: tuple[tuple[str, ...], ...] = (U_AJE_RJE,), origin: str,
) -> AuditedTotals:
    """原值清单 + 备抵清单：原值 = Σ原值行；净值 = 原值 − Σ各备抵行。"""
    return AuditedTotals(
        receivable=Rows((RowList(gross),), fields),
        net=Rows((RowList(gross), *(RowList(c, -1) for c in contra)), fields),
        origin=origin,
    )


def _conclusion(item_id: str) -> Key:
    return Key(item_id, "conclusion")


_KEYED_STORE = "行存为按行键的对象（合计依赖前端静态行清单）"

_H3_FAIR = Rows((RowList("H3-1-fair-rows"),))
_H4_ORIGINAL = RowList("H4-1-rows", section="original", section_default="original")
_H4_IMPAIRMENT = RowList("H4-1-rows", -1, section="impairment", section_default="original")


AUDITED_SOURCES: dict[str, AuditedTotals] = {
    # ── G 循环（G7 另有 binding）──────────────────────────────────────────────
    "G1": _same(Unavailable(
        f"交易性金融资产审定表{_KEYED_STORE}；前端发布审定数时宿主只收科目码 1501 的事件，本底稿发的是 1101，"
        "「G1-1-adjudicated-amount」从未写入"),
        origin="useG1Adjudication / GtG1TradingFinancialAssets"),
    "G2": AuditedTotals(
        receivable=Unavailable(f"应收利息审定表{_KEYED_STORE}，前端只发布净额"),
        net=_conclusion("G2-1-adjudicated-amount"),
        origin="useG2Adjudication.subtotalRow（footer-total = 原值 − 坏账准备）经 GtG2InterestReceivable 写入结论列"),
    "G3": _same(_conclusion("G3-1-adjudicated-amount"),
                origin="useG3Adjudication 发布的审定合计（应收股利无备抵）经 GtG3DividendReceivable 写入结论列"),
    "G4": AuditedTotals(
        receivable=Unavailable(f"债权投资审定表{_KEYED_STORE}，前端只发布净值"),
        net=_conclusion("G4-1-adjudicated-amount"),
        origin="useG4MainAdjudication.amortizedCostRow（三、债权投资净值 = 原值 − 减值准备，已扣一年内到期）"
               "经 GtG4BondInvestmentMain 写入结论列"),
    "G5": AuditedTotals(
        receivable=Unavailable(f"长期应收款审定表{_KEYED_STORE}，前端只发布净额"),
        net=_conclusion("G5-1-adjudicated-amount"),
        origin="useG5Adjudication 的 net__row（原值 − 坏账准备，已扣一年内到期）经 GtG5LongTermReceivable 写入结论列"),
    "G6": _same(Unavailable(
        f"其他债权投资审定表{_KEYED_STORE}；前端发布审定数用的科目码（1505）与宿主监听的（1503）对不上，"
        "「G6-1-adjudicated-amount」从未写入"),
        origin="useG6MainAdjudication / GtG6OtherBondMain"),
    "G8": _same(Unavailable(
        f"其他权益工具投资审定表{_KEYED_STORE}；「G8-1-adjudicated-amount」会被调整回写覆盖成单行金额"
        "（g8CrossHelpers），不是审定合计"),
        origin="useG8Adjudication / g8CrossHelpers"),
    "G9": _same(_conclusion("G9-1-adjudicated-amount"),
                origin="useG9Adjudication.notifyAdjudicated（三类合计，无备抵）写入结论列"),
    "G10": _same(_conclusion("G10-1-adjudicated-amount"),
                 origin="useG10Adjudication.notifyAdjudicated（三、账面余额合计）写入结论列"),
    # ── H 循环 ────────────────────────────────────────────────────────────────
    "H1": _blocks("H1-1-cost-rows", "H1-1-dep-rows", "H1-1-impair-rows",
                  origin="useH1Adjudication（原值 / 累计折旧 / 减值准备三段行清单，行审定 = 未审 + AJE + RJE）"),
    "H2": _blocks("H2-1-rows", "H2-1-impair-rows", fields=(END_UNADJ_ADJ, U_AJE_RJE),
                  origin="useH2Adjudication（原值 / 减值准备行清单，行期末审定 = 期末未审 + 期末调整）"),
    "H3": AuditedTotals(
        receivable=ByMode("H3-measurement-model", (("fair_value", _H3_FAIR),),
                          Rows((RowList("H3-1-cost-original-rows"),))),
        net=ByMode("H3-measurement-model", (("fair_value", _H3_FAIR),),
                   Rows((RowList("H3-1-cost-original-rows"), RowList("H3-1-cost-dep-rows", -1),
                         RowList("H3-1-cost-impair-rows", -1)))),
        origin="useH3AdjudicationCost / useH3AdjudicationFair（按 H3-measurement-model 选成本或公允价值模式）"),
    "H4": AuditedTotals(
        receivable=Rows((_H4_ORIGINAL,), (END_UNADJ_ADJ, U_AJE_RJE)),
        net=Rows((_H4_ORIGINAL, _H4_IMPAIRMENT), (END_UNADJ_ADJ, U_AJE_RJE)),
        origin="useH4Adjudication（一个数组分原值 / 减值两段；净值与前端 H4-1-adjudicated-total 同口径）"),
    "H5": _blocks("H5-1-cost-rows", "H5-1-depletion-rows", "H5-1-impairment-rows",
                  origin="useH5Adjudication（原值 / 累计折耗 / 减值准备三段行清单）"),
    "H6": _same(Key("H6-1-end-balance-audited"), origin="useH6Adjudication._persist（期末审定合计）"),
    "H7": _same(Unavailable("生产性生物资产审定表前端尚未实现（只有取数函数，没有行、没有写入）"),
                origin="useH7AdjudicationCost（桩）"),
    "H8": AuditedTotals(
        receivable=Key("H8-1-cost-audited-total"), net=Key("H8-1-net-audited"),
        origin="useH8Adjudication._writeTotals（原值审定合计；净值 = 原值 − 累计折旧 − 减值准备）"),
    "H9": AuditedTotals(
        receivable=Key("H9-1-liability-audited"), net=Key("H9-1-net-audited"),
        origin="useH9Adjudication._persist（租赁负债审定合计；净额 = 租赁负债 − 未确认融资费用）"),
    "H10": _same(_conclusion("H10-1-adjudicated-amount"),
                 origin="useH10Adjudication.emitAdjudicated（本期审定数）写入结论列"),
    # ── I 循环 ────────────────────────────────────────────────────────────────
    "I1": _blocks("I1-adj-cost-rows", "I1-adj-amort-rows", "I1-adj-impair-rows",
                  origin="useI1Adjudication._persist（原价 / 累计摊销 / 减值准备三段行清单）"),
    "I2": _same(Rows((RowList("I2-1-rows"),), (("endUnadj", "endAdj"), U_AJE_RJE)),
                origin="i2AdjudicationModel（期末审定 = 期末未审 + 期末账项调整）"),
    "I3": AuditedTotals(
        receivable=Unavailable("商誉审定表按被投资单位一行承载净额，原值列不做账项调整，没有审定原值"),
        net=Rows((RowList("I3-adj-rows", alternates=("I3-1-adj-rows", "I3-1-rows")),)),
        origin="i3AdjudicationModel（审定 = 期末净额未审 + AJE + RJE）"),
    "I4": _same(Rows((RowList("I4-adj-rows"),)), origin="i4AdjudicationModel（审定 = 未审 + AJE + RJE）"),
    "I5": AuditedTotals(
        receivable=Unavailable("其他非流动资产审定表各行是 I5-2 明细的净值（已扣减值准备），没有审定原值"),
        net=Rows((RowList("I5-adj-rows"),)),
        origin="i5AdjudicationModel（审定 = 未审 + AJE + RJE，按明细净值带入）"),
    # ── K 循环（K2 / K3~K6 的扁平键与前端一致，仍走 AdjudicationSpec 的行模式）──────────
    "K7": _same(Key("K7-1-audited-total"), origin="useK7Adjudication._persist（递延收益审定合计）"),
}
