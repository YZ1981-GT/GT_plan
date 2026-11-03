"""附注表格标题行库 · 逐列对应与选表（单体↔合并）。

spec: consol-note-header-library-and-node-reaggregate（design §5）

识别口径（表头路径 / 列语义键 / 续表）在 ``note_table_header_library``；本模块只做对应：
``match_columns`` 把合并模板列对到单体单元（主表 + 列续表）的列，``choose_unit`` 在单体章节里选单元。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Sequence

from app.services.note_table_header_library import (
    _FAMILY,
    _OPPOSITE,
    ColumnKey,
    ContinuationLink,
    Vocabulary,
    _has_period,
    _name_of,
    base_key,
    column_keys,
    continuation_links,
    is_continuation_name,
    load_vocabulary,
    norm,
    table_key,
)

__all__ = [
    "RULES",
    "STRONG_RULES",
    "ColumnMatch",
    "UnitChoice",
    "choose_unit",
    "fill_main_period",
    "match_columns",
    "match_table_name",
    "row_values",
    "takes_amount",
    "to_number",
    "unit_member_keys",
]


# ─── 逐列对应 ────────────────────────────────────────────────────────────────


def _rule_exact(t: ColumnKey, s: ColumnKey) -> bool:
    return t.period == s.period and t.measure == s.measure


def _rule_suffix(t: ColumnKey, s: ColumnKey) -> bool:
    """单体表省略了非期间的分组层（合并「账面余额/金额」↔ 单体「金额」）。"""
    n = len(s.measure)
    return t.period == s.period and 0 < n < len(t.measure) and t.measure[-n:] == s.measure


def _rule_prefix(t: ColumnKey, s: ColumnKey) -> bool:
    """合并表多一层说明（「第一阶段/未来12个月预期信用损失」↔ 单体「第一阶段」）。"""
    n = len(s.measure)
    return t.period == s.period and 0 < n < len(t.measure) and t.measure[:n] == s.measure


def _rule_reverse_suffix(t: ColumnKey, s: ColumnKey) -> bool:
    """合并表省略了分组层（合并「金额」↔ 单体「账面余额/金额」）。"""
    n = len(t.measure)
    return t.period == s.period and 0 < n < len(s.measure) and s.measure[-n:] == t.measure


def _rule_reverse_prefix(t: ColumnKey, s: ColumnKey) -> bool:
    """单体表多一层说明（合并「第一阶段」↔ 单体「第一阶段/未来12个月预期信用损失」）。"""
    n = len(t.measure)
    return t.period == s.period and 0 < n < len(s.measure) and s.measure[:n] == t.measure


def _rule_period_only(t: ColumnKey, s: ColumnKey) -> bool:
    """同期间、一侧只写了期间（合并「期末余额」↔ 单体「期末公允价值」）：靠唯一性兜底，多于一列即放弃；
    最终只留两列是同一项的（``_same_item``）。"""
    return bool(t.period) and t.period == s.period and (not t.measure) != (not s.measure)


#: 计量词末尾的金额单位注记（规范化后半角括号 / 冒号）：「金额（万元）」「金额（单位：元）」，或整段就是单位「万元」
_UNIT_NOTE_RE = re.compile(r"\((?:单位:)?(?:万元|千元|亿元|元)\)$|^(?:单位:)?(?:万元|千元|亿元|元)$")


#: 计量词以这些结尾 = 某项金额本身（实收资本「投资金额」），不是利息 / 面值 / 数量这类另一项
_AMOUNT_SUFFIXES = ("金额", "余额")


def _has_pure_amount(keys: Sequence[ColumnKey]) -> bool:
    return any(k.kind == "amount" and k.period and not k.measure for k in keys[1:])


def _same_item(
    t: ColumnKey, s: ColumnKey, t_keys: Sequence[ColumnKey], s_keys: Sequence[ColumnKey], vocab: Vocabulary,
) -> bool:
    """「只写了期间」对上的两列是不是同一项（纯期间列 = 该项目的余额 / 发生额），R7.7：

    - 写了计量的一侧去掉单位注记与「金额」这类纯余额词后什么都不剩，或是余额类（账面余额 / 公允价值）/ 净额（账面价值）⇒ 是；
    - 是「…金额 / …余额」（实收资本「年初余额/投资金额」）且它那张表没有纯期间金额列 ⇒ 是；那张表另有纯期间金额列
      ⇒ 余额在纯期间列里，这一列是另一项；
    - 其余（「年初应付利息」「面值」「数量」）⇒ 不是。国企 五-50-2「期初余额」曾对到单体「年初应付利息」、上市 五-12-2
      「期末余额/面值」对到单体「期末余额」。
    """
    measured, keys = (t, t_keys) if t.measure else (s, s_keys)
    core = tuple(p for p in (_UNIT_NOTE_RE.sub("", m) for m in measured.measure) if p not in vocab.pure_remainders)
    if not core or core in vocab.balance_measures or core in vocab.net_measures:
        return True
    return core[-1].endswith(_AMOUNT_SUFFIXES) and not _has_pure_amount(keys)


def _rule_period_family(t: ColumnKey, s: ColumnKey) -> bool:
    """同侧期间（期末余额 ↔ 本期发生额）计量相同：只在更强规则都没命中时才用。"""
    return (
        bool(t.period and s.period) and t.period != s.period
        and _FAMILY[t.period] == _FAMILY[s.period] and t.measure == s.measure
    )


def _synonym_rule(vocab: Vocabulary):
    syn = vocab.measure_synonyms

    def rule(t: ColumnKey, s: ColumnKey) -> bool:
        """同义计量词（坏账准备 ↔ 减值准备）：词表 measure_synonyms，次于精确。"""
        if t.period != s.period or t.measure == s.measure or len(t.measure) != len(s.measure):
            return False
        return all(syn.get(a, a) == syn.get(b, b) for a, b in zip(t.measure, s.measure))

    return rule


def _balance_pick(keys: Sequence[ColumnKey], vocab: Vocabulary) -> ColumnKey | None:
    """「只写了期间」对上同期间多列时的唯一候选：纯期间列 = 该项目的余额（``column_role`` 同口径），
    对唯一的余额计量列（账面余额 / 公允价值）；同期间还有净额列（账面价值）时余额 / 净额分不出，不选。"""
    if any(k.measure in vocab.net_measures for k in keys):
        return None
    hits = [k for k in keys if k.measure in vocab.balance_measures]
    return hits[0] if len(hits) == 1 else None


#: 强 → 弱；弱规则只在强规则零命中时才试；命中不唯一放弃（「只写了期间」多列时按 ``_balance_pick`` 取唯一余额列，
#: 记作 period_balance）；同一单体列被多列认领全部放弃（都是「只写了期间」时同样按 ``_balance_pick``）；
#: 「只写了期间」单列命中最后再核两列是同一项（``_same_item``）。
#: 无期间无计量的金额列不走这些规则，只按表头文字对（``_bare_hit``，记作 bare_label，R7.7）
RULES = (
    ("exact", _rule_exact), ("synonym", None), ("suffix", _rule_suffix), ("prefix", _rule_prefix),
    ("reverse_suffix", _rule_reverse_suffix), ("reverse_prefix", _rule_reverse_prefix),
    ("period_only", _rule_period_only), ("period_family", _rule_period_family),
)
#: 选表打分里算「强命中」的规则
STRONG_RULES = frozenset({"exact", "synonym"})


def _bare_text(k: ColumnKey) -> str:
    """无期间、无计量的金额列（表头只写「金额」）的表头文字；有期间 / 计量的列、空表头返回空串。"""
    return "/".join(k.path) if k.kind == "amount" and not (k.period or k.measure) else ""


def takes_amount(k: ColumnKey) -> bool:
    """这一列取不取数：有期间或计量的金额列，加上表头只写「金额」这类无键但有字的金额列；空表头不取。"""
    return k.kind == "amount" and bool(k.period or k.measure or _bare_text(k))


def _bare_hit(t: ColumnKey, sources: Sequence[tuple[int, ColumnKey]]):
    """无键金额列按表头文字对：来源单元里同字的列恰有一列（同名同结构的单金额列表「项目 | 金额」）。目标侧两列同字时
    两列认领同一来源列，由「同一单体列被多列认领全部放弃」挡掉。"""
    text = _bare_text(t)
    hits = [(pos, s.index) for pos, s in sources if text and _bare_text(s) == text]
    return hits[0] if len(hits) == 1 else None


@dataclass
class ColumnMatch:
    col_map: dict[int, tuple[int, int]] = field(default_factory=dict)  # 目标列 → (成员序, 来源列)
    rules: dict[int, str] = field(default_factory=dict)
    unmatched: list[int] = field(default_factory=list)
    ratio: list[int] = field(default_factory=list)
    aux_matched: int = 0  # 比例列 / 说明类列表头一致的个数（不取数，只作选表的结构证据）

    @property
    def exact_count(self) -> int:
        return sum(1 for r in self.rules.values() if r == "exact")

    @property
    def strong_count(self) -> int:
        return sum(1 for r in self.rules.values() if r in STRONG_RULES)


def match_columns(
    target: Sequence[ColumnKey],
    members: Sequence[Sequence[ColumnKey]],
    vocab: Vocabulary | None = None,
) -> ColumnMatch:
    """合并模板列 → 单体单元（主表 + 列续表）里的列。比例列不对应（跨企业加总没有意义）。"""
    vocab = vocab or load_vocabulary()
    rules = [(name, fn or _synonym_rule(vocab)) for name, fn in RULES]
    claims: dict[int, tuple[int, int, str]] = {}
    ratio: list[int] = []
    sources = [
        (pos, s) for pos, keys in enumerate(members) for s in keys[1:] if s.kind == "amount"
    ]
    aux_sources = {
        (s.period, s.measure, s.kind) for keys in members for s in keys[1:] if s.kind in ("text", "ratio")
    }
    aux_matched = 0
    for t in target[1:]:
        if t.kind in ("text", "ratio"):
            aux_matched += int((t.period, t.measure, t.kind) in aux_sources)
        if t.kind == "ratio":
            ratio.append(t.index)
            continue
        if t.kind == "text":
            continue
        if t.kind != "amount":
            continue
        if not (t.period or t.measure):
            hit = _bare_hit(t, sources)
            if hit is not None:
                claims[t.index] = (*hit, "bare_label")
            continue  # 空表头不取数
        for name, rule in rules:
            hits = [(pos, s) for pos, s in sources if rule(t, s)]
            if hits:
                if len(hits) == 1:
                    claims[t.index] = (hits[0][0], hits[0][1].index, name)
                elif name == "period_only" and not t.measure:
                    pick = _balance_pick([s for _pos, s in hits], vocab)
                    if pick is not None:
                        claims[t.index] = (next(p for p, s in hits if s is pick), pick.index, "period_balance")
                break
    owners: dict[tuple[int, int], list[int]] = {}
    for c, (pos, col, _rule) in claims.items():
        owners.setdefault((pos, col), []).append(c)
    by_index = {t.index: t for t in target}
    kept: dict[int, str] = {}
    for cols in owners.values():
        strong = [c for c in cols if claims[c][2] in STRONG_RULES]
        if len(cols) == 1:
            kept[cols[0]] = claims[cols[0]][2]
        elif len(strong) == 1:
            kept[strong[0]] = claims[strong[0]][2]  # 精确 / 同义命中唯一时它胜出，弱规则命中让位
        elif all(claims[c][2] == "period_only" for c in cols):
            # 同一纯期间列被同期间多列认领（合并「期末数/账面余额」「期末数/坏账准备」↔ 单体「期末数」）
            pick = _balance_pick([by_index[c] for c in cols], vocab)
            if pick is not None:
                kept[pick.index] = "period_balance"
    source_keys = {(pos, s.index): s for pos, s in sources}
    out = ColumnMatch(ratio=ratio, aux_matched=aux_matched)
    for c, rule in sorted(kept.items()):
        pos = claims[c][0]
        if rule == "period_only" and not _same_item(by_index[c], source_keys[claims[c][:2]], target, members[pos], vocab):
            continue  # 两列不是同一项（宁缺不错）
        out.col_map[c] = claims[c][:2]
        out.rules[c] = rule
    out.unmatched = [t.index for t in target[1:] if takes_amount(t) and t.index not in out.col_map]
    return out


# ─── 选表 ────────────────────────────────────────────────────────────────────

_FUZZY_TABLE_RATIO = 0.9


def match_table_name(
    cands: Sequence[tuple[int, Any]], want: Any, vocab: Vocabulary | None = None,
) -> tuple[list[int], str]:
    """按表名找候选表：规范化相等 → 去期间 / 续表标记后相等 → 相似度 ≥ 0.9（唯一）。

    后两级只在续表 / 非续表同类之间比（「（续：期初数）」不冒充主表）。不做包含匹配：
    「货币资金」包含于「受限制的货币资金明细」，包含匹配会取错表。
    """
    vocab = vocab or load_vocabulary()
    key = table_key(want)
    exact = [i for i, t in cands if table_key(_name_of(t)) == key]
    if exact:
        return exact, "exact"
    want_cont = is_continuation_name(want, vocab)
    same_kind = [(i, t) for i, t in cands if is_continuation_name(_name_of(t), vocab) == want_cont]
    base = base_key(want, vocab)
    by_base = [i for i, t in same_kind if base and base_key(_name_of(t), vocab) == base]
    if by_base:
        return by_base, "base"
    scored = sorted(
        ((SequenceMatcher(None, key, table_key(_name_of(t))).ratio(), i) for i, t in same_kind),
        reverse=True,
    )
    if scored and scored[0][0] >= _FUZZY_TABLE_RATIO and (len(scored) == 1 or scored[1][0] < _FUZZY_TABLE_RATIO):
        return [scored[0][1]], "fuzzy"
    return [], ""


@dataclass
class UnitChoice:
    primary: int | None
    members: list[int] = field(default_factory=list)  # 主表 + 列续表（按行名对行）
    row_members: list[int] = field(default_factory=list)  # 行续表（行追加在主表后）
    method: str = "none"  # name / structure / single_table / none
    reason: str | None = None
    match: ColumnMatch | None = None
    member_keys: list[list[ColumnKey]] = field(default_factory=list)
    score_reason: str | None = None  # 选表决策说明（复盘建议 #5：可解释性）


def _unit(index: int, links: dict[int, ContinuationLink]) -> tuple[list[int], list[int]]:
    if index in links:  # 续表自成一个单元（合并表本身就是续表时直接对它）
        return [index], []
    cols = [c for c, lk in sorted(links.items()) if lk.of == index and lk.kind == "columns"]
    rows = [c for c, lk in sorted(links.items()) if lk.of == index and lk.kind == "rows"]
    return [index, *cols], rows


def unit_member_keys(
    tables: Sequence[Any],
    members: Sequence[int],
    *,
    target_keys: Sequence[ColumnKey] | None = None,
    identities: Sequence[tuple[str, str] | None] | None = None,
    vocab: Vocabulary | None = None,
) -> list[list[ColumnKey]]:
    """单元各成员的列语义键。主表整表没有期间时：有列续表就取续表的对侧期间，否则合并表只有一个期间就取它。"""
    vocab = vocab or load_vocabulary()
    out: list[list[ColumnKey]] = []
    for pos, idx in enumerate(members):
        identity = identities[idx] if identities and idx < len(identities) else None
        out.append(column_keys(tables[idx], identity=identity, vocab=vocab))
    if out:
        out[0] = fill_main_period(out[0], out[1:], target_keys)
    return out


def fill_main_period(
    main: Sequence[ColumnKey],
    continuations: Sequence[Sequence[ColumnKey]],
    target_keys: Sequence[ColumnKey] | None = None,
) -> list[ColumnKey]:
    """主表整表没有期间时补期间：列续表都是同一期间 ⇒ 取对侧（「有『续：期初』续表的主表承载期末」）；
    否则对照的目标表只有一个期间就取它。主表本有期间或补不出 ⇒ 原样。合并选表与上年附注导入共用。"""
    if _has_period(main):
        return list(main)
    fill: str | None = None
    cont_periods = {k.period for keys in continuations for k in keys[1:] if k.period}
    if len(cont_periods) == 1:
        fill = _OPPOSITE[next(iter(cont_periods))]
    elif target_keys is not None:
        periods = {k.period for k in target_keys[1:] if k.kind == "amount" and k.period}
        if len(periods) == 1:
            fill = next(iter(periods))
    if not fill:
        return list(main)
    return [k if k.kind == "label" else ColumnKey(k.index, k.path, fill, k.measure, k.kind, k.source) for k in main]


def row_values(row: Any) -> list[Any]:
    """行的数据单元格（不含第 0 列行名）：``{label, values:[...]}`` 或 ``[label, v1, ...]``。"""
    if isinstance(row, dict):
        vals = row.get("values")
        return list(vals) if isinstance(vals, (list, tuple)) else []
    if isinstance(row, (list, tuple)):
        return list(row[1:])
    return []


def to_number(value: Any) -> float | int | None:
    """单元格 → 数值；空 / 非数值 → None（文本列、占位符 X.XX 都不参与加总）。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value if value == value else None  # NaN
    if isinstance(value, dict):  # 带元数据的单元格
        return to_number(value.get("value", value.get("manual_value")))
    s = str(value).strip().replace(",", "").replace("，", "")
    if not s or s in ("-", "—", "－"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _data_cells(tables: Sequence[Any], choice: UnitChoice) -> int:
    """单元在已对上的列里有多少个非零数：表头分不出时取有数的那张（同一章节新旧模板表并存）。"""
    if choice.match is None:
        return 0
    count = 0
    for pos, col in choice.match.col_map.values():
        table = tables[choice.members[pos]]
        for row in table.get("rows") or []:
            vals = row_values(row)
            if 0 <= col - 1 < len(vals) and to_number(vals[col - 1]):
                count += 1
    return count


def _used_tables(choice: UnitChoice) -> frozenset[int]:
    """单元实际取数的表（对上的列来自哪些成员表）。"""
    if choice.match is None:
        return frozenset()
    return frozenset(choice.members[pos] for pos, _c in choice.match.col_map.values())


def _score(
    tables: Sequence[Any], choice: UnitChoice, specific: set[int], width: int,
) -> tuple[int, ...]:
    """选表打分（从高到低比）：具体列强命中 → 强命中 → 命中 → 比例 / 说明类列一致 → 命中都在主表 →
    主表列数与合并表接近 → 有数 → 成员少。"""
    m = choice.match or ColumnMatch()
    direct = int(bool(m.col_map) and all(pos == 0 for pos, _c in m.col_map.values()))
    specific_strong = sum(1 for c, r in m.rules.items() if r in STRONG_RULES and c in specific)
    gap = abs(len(choice.member_keys[0]) - width) if choice.member_keys else width
    has_data = int(_data_cells(tables, choice) > 0)
    score = (specific_strong, m.strong_count, len(m.col_map), m.aux_matched, direct, -gap, has_data,
             -len(choice.members))
    # 生成可读的决策说明（复盘建议 #5）
    parts: list[str] = []
    if specific_strong:
        parts.append(f"具体列强命中{specific_strong}")
    if m.strong_count:
        parts.append(f"强命中{m.strong_count}列")
    if m.col_map:
        parts.append(f"共对上{len(m.col_map)}列")
    if m.aux_matched:
        parts.append(f"辅助列一致{m.aux_matched}")
    if direct:
        parts.append("全在主表")
    parts.append(f"列数差{abs(gap)}")
    if has_data:
        parts.append("有数")
    if len(choice.members) > 1:
        parts.append(f"{len(choice.members)}表组合")
    choice.score_reason = "、".join(parts) if parts else "无评分依据"
    return score


def _name_hits(cands: Sequence[tuple[int, Any]], want: Any, vocab: Vocabulary) -> list[int]:
    """一个名字证据命中的表：表名规范化相等 ∪ 同类（续表 / 非续表）里去期间 / 续表标记后相等；都没有再用相似度。"""
    key, base, want_cont = table_key(want), base_key(want, vocab), is_continuation_name(want, vocab)
    hits = [i for i, t in cands if table_key(_name_of(t)) == key]
    hits += [
        i for i, t in cands
        if base and i not in hits and is_continuation_name(_name_of(t), vocab) == want_cont
        and base_key(_name_of(t), vocab) == base
    ]
    return hits or match_table_name(cands, want, vocab)[0]


def _choose_by_names(cands, tables, hints, evaluate, vocab) -> UnitChoice | None:
    """带合并表头时的名字阶段：子表名、合并表标题两路命中合在一起，多于一张按列语义键重合度定。

    合起来比而不是子表名优先：映射里的子表名来自种子，种子表名有错位（国企 八、54 敏感性分析表叫「计划资产」），
    项目附注里表名是对的那一张也要能参加比较。返回 None = 名字一个都没命中。
    """
    # 裸「续：」标题不带表的身份：有更具体的名字证据时不参与（否则旧格式里一堆「续：」表都成了候选）
    specific_hints = [h for h in hints if base_key(h, vocab)]
    hints = specific_hints or hints
    hint_keys = {table_key(h) for h in hints}
    hits: list[int] = []
    for want in hints:
        hits += [i for i in _name_hits(cands, want, vocab) if i not in hits]
    if not hits:
        return None
    if len(hits) == 1:
        return evaluate(hits[0], "name")[0]

    def exact_named(pool):
        return [ch for ch in pool if table_key(_name_of(tables[ch.primary])) in hint_keys]

    ranked = sorted((evaluate(i, "name") for i in hits), key=lambda pair: pair[1], reverse=True)
    (top, top_score), (_second, second_score) = ranked[0], ranked[1]
    reason = f"单体附注有 {len(hits)} 张与「{hints[0]}」同名的表，表头也分不出取哪一张"
    if top_score[2] == 0:
        # 一列金额都对不上 = 没有结构证据：只认表名精确命中的唯一一张
        named = exact_named([ch for ch, _sc in ranked])
        return named[0] if len(named) == 1 else UnitChoice(None, reason=reason)
    if top_score == second_score:
        named = exact_named([ch for ch, sc in ranked if sc == top_score])
        return named[0] if len(named) == 1 else UnitChoice(None, reason=reason)
    if table_key(_name_of(tables[top.primary])) not in hint_keys:
        top.method = "structure"
    return top


def choose_unit(
    tables: Sequence[Any],
    *,
    target_keys: Sequence[ColumnKey] | None = None,
    table_name: Any = None,
    title: Any = None,
    section_title: Any = None,
    links: dict[int, ContinuationLink] | None = None,
    identities: Sequence[tuple[str, str] | None] | None = None,
    vocab: Vocabulary | None = None,
) -> UnitChoice:
    """在单体章节的表格里选与合并表对应的单元（主表 + 列续表）。

    依据依次是映射给出的子表名 ``table_name``、合并表标题 ``title``。名字缩小候选（表名规范化相等 ∪
    去期间 / 续表标记后相等；都没有才用相似度），候选多于一个时按列语义键重合度定（``_score``）。名字都
    对不上：只在合并表有「具体列」（带计量词，不只是期末 / 期初）且唯一最优单元强命中（精确 / 同义）其中
    至少一半时按结构选中；否则映射没给表名的单表章节直接用它，
    唯一一张无名表（旧单表格式）且要的就是章节主表（子表名 = 章节标题）也用它。``target_keys`` 为空 = 只按名字选。
    """
    vocab = vocab or load_vocabulary()
    cands = [(i, t) for i, t in enumerate(tables) if isinstance(t, dict)]
    if not cands:
        return UnitChoice(None, reason="单体附注该章节没有表格")
    links = continuation_links(tables, vocab=vocab) if links is None else links
    hints = [h for h in (table_name, title) if table_key(h)]
    specific = {
        k.index for k in (target_keys or [])[1:] if k.kind == "amount" and k.measure
    }

    def evaluate(index: int, method: str) -> tuple[UnitChoice, tuple[int, ...]]:
        members, rows = _unit(index, links)
        choice = UnitChoice(index, members, rows, method)
        if target_keys is None:
            return choice, ()
        choice.member_keys = unit_member_keys(
            tables, members, target_keys=target_keys, identities=identities, vocab=vocab,
        )
        choice.match = match_columns(target_keys, choice.member_keys, vocab)
        return choice, _score(tables, choice, specific, len(target_keys))

    if target_keys is None:  # 只按名字：子表名优先，没命中再按合并表标题
        for want in hints:
            hits, _how = match_table_name(cands, want, vocab)
            if len(hits) == 1:
                return evaluate(hits[0], "name")[0]
            if hits:
                return UnitChoice(None, reason=f"单体附注有多张同名表「{want}」，无法确定取哪一张")
    else:
        choice = _choose_by_names(cands, tables, hints, evaluate, vocab)
        if choice is not None:
            return choice

    if target_keys is not None and specific:
        pool = [i for i, _t in cands]
        if any(is_continuation_name(h, vocab) and not base_key(h, vocab) for h in hints):
            # 合并表就是裸「续：」：只在续表（或带列续表的主表）里找
            pool = [i for i in pool if i in links or any(lk.of == i for lk in links.values())]
        ranked = sorted((evaluate(i, "structure") for i in pool), key=lambda pair: pair[1], reverse=True)
        need = max(1, math.ceil(len(specific) / 2))
        if ranked:
            top, top_score = ranked[0]
            used = _used_tables(top)
            # 没有名字证据：金额列证据必须比「取自别的表」的次优者强（同构的表只靠次要特征分不出就不猜）；
            # 「主表 + 列续表」单元的数全取自续表时与续表本身是同一份证据，不算对手
            rivals = [sc for ch, sc in ranked[1:] if _used_tables(ch) != used]
            # 只比强命中（精确 / 同义）：弱规则命中常来自合并表头缺陷（如「组合」盖到数据列），不能据此改选
            clear = not rivals or top_score[:2] > rivals[0][:2]
            if clear and top_score[0] >= need:
                return top

    if len(cands) == 1:
        only_index, only = cands[0]
        if not table_key(table_name) or (
            not norm(_name_of(only)) and section_title and table_key(table_name) == table_key(section_title)
        ):
            only_choice = evaluate(only_index, "single_table")[0]
            has_amounts = any(takes_amount(k) for k in (target_keys or [])[1:])
            if not has_amounts or (only_choice.match and only_choice.match.col_map):
                return only_choice
            # 章节只有一张表、但一列金额都对不上：多半是章节映射错位，不拿它凑数
            return UnitChoice(None, reason=f"单体附注该章节只有一张表「{_name_of(only) or '（无名表）'}」，表头与合并表对不上")
    want = hints[0] if hints else ""
    if len(cands) == 1:
        return UnitChoice(None, reason=f"单体附注该章节有 1 张表，没有与「{want}」对应的表")
    return UnitChoice(None, reason=f"单体附注该章节有 {len(cands)} 张表，没有与「{want}」对应的表")
