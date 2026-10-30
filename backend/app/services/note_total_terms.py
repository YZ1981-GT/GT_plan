"""附注表格合计构成 —— 单体 / 合并、前端 / 后端共用的唯一判定（spec note-pull-header-formula-closure R5）。

合计 / 小计行由哪些行加减而来，只在判得准时给出（``total_terms``）；判不准的回原因，调用方不算、不猜：

* 只有一个合计 / 小计：上方的明细行；「其中：」标记行下面列的是上一行的明细（不重复加）。小计的范围跨了两个以上
  分段标题（「一、」「（二）」）⇒ 判不准（融资租赁「三、调节」下的「…收款额小计」只该加「二、」那一段）。
* 几个小计 + 至多一个合计（合计在最后）：
  - 常规（小计在本组之下）：小计 = 上一个小计之后到本行的明细；合计 = 各小计 ± 最后一个小计与合计之间的行
    （「减：」减，「加：」与明细加）。
  - 标题式（第一行就是小计、每个小计下面列本组明细）：小计 = 下面到下一个小计 / 合计之前的明细；合计 = 各小计之和。
  - 某个小计自己判不准（组内有「其中：X」/ 减项）不影响合计 = 各小计。
  - 整表判不准：小计范围跨分段标题、「X小计」与「小计」并存（嵌套）、多个合计 / 合计后还有小计。
* 「其中：X」行内写法、减项 / 加项夹在明细中间（不在小计之后）⇒ 判不准。
* 段首合计（spec note-pull-followup-closure R7，先于以上判定）：所有合计都是分段标题式（「一、账面原值合计」）、表的第一行
  就是合计 ⇒ 每个合计 = 它下面到下一个合计之前的本段明细；段内「其中：X」只许是本段第一行（列举本段构成），其余位置的
  「其中」/ 减项 / 加项 / 段内分段标题 ⇒ 该合计判不准。

谁在用：附注预设公式（``note_formula_tables``）、生成 / 刷新后的合计回填（``disclosure_engine``）、合并附注拉数 /
汇总 / 保存回填（``consol_note_table_totals`` / ``consol_note_formula_service``）、旧派生登记（``note_formula_derivation``）、
前端结构编辑与合并附注编辑（``noteTotalTerms.ts``，按模板逐表的 golden ``note_total_terms_golden.json`` 交叉锁死）。
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Callable, Iterable

__all__ = [
    "flatten_terms", "label_row_type", "plan_description", "row_kind", "sum_terms", "total_order", "total_terms",
]

#: 结构行（占位 / 动态区标记 / 表内子表头）：不参与合计
_SKIP_ROW_TYPES = frozenset({"header_label", "dynamic_anchor", "dynamic_marker_end", "expandable", "header"})
_PLACEHOLDER_RE = re.compile(r"[.…·]+")
_MARKER_RE = re.compile(r"其中[:：]?")
#: 分段标题：「一、」「（二）」
_HEADING_RE = re.compile(r"^(?:[一二三四五六七八九十]+、|[（(][一二三四五六七八九十]+[）)])")
_PLAIN_SUBTOTAL_RE = re.compile(r"小计[:：]?")
_NO_DETAIL = "没有可合计的明细行"
_SUB_DETAIL = "表里有「其中：…」明细行，分不出明细到哪一行为止"
_MINUS_PLUS = "减项 / 加项不在小计之后"
_SEGMENT_HEADING = "合计的范围跨了几个分段标题（「一、」「（二）」），合计范围无法自动判定"


def _label(row: Any) -> str:
    return re.sub(r"\s+", "", str(row.get("label") or "")) if isinstance(row, dict) else ""


def label_row_type(label: Any) -> str:
    """只有行名时的行类型（合并附注模板 / 来源行）：「合计」「总计」= total，以「小计」结尾 = subtotal，其余 data。

    与合并拉数读单体附注（``consol_note_standalone_reader._source_row_type``）同一口径；「小计」先判（旧正则把
    「小计」当成合计，多段小计全按合计加总）。
    """
    key = re.sub(r"\s+", "", str(label or "")).rstrip(":：")
    if key.endswith("小计"):
        return "subtotal"
    if key in ("合计", "总计"):
        return "total"
    return "data"


def row_kind(row: Any) -> str:
    """skip（占位 / 动态区标记）/ total / subtotal / marker（「其中：」标记行）/ sub（「其中：X」）/ minus / plus / data。"""
    if not isinstance(row, dict):
        return "skip"
    label = _label(row)
    if row.get("row_type") in _SKIP_ROW_TYPES or (label and _PLACEHOLDER_RE.fullmatch(label)):
        return "skip"
    if row.get("is_total") is True or row.get("row_type") in ("total", "subtotal"):
        return "subtotal" if (row.get("row_type") == "subtotal" or "小计" in label) else "total"
    if _MARKER_RE.fullmatch(label):
        return "marker"
    if label.startswith("其中"):
        return "sub"
    if label.startswith(("减:", "减：")):
        return "minus"
    if label.startswith(("加:", "加：")):
        return "plus"
    return "data"


def _top_rows(kinds: list[str], idxs: list[int]) -> tuple[list[int] | None, str | None]:
    """一段（合计 / 小计的范围）参与合计的行。

    没有「其中」⇒ 全部明细行；有「其中：」标记行 ⇒ 第一个标记之前的明细行 + 每个标记紧前的那一行（标记下面列的是它的
    明细，不重复加）。含「其中：X」行内写法 / 减项 / 加项 ⇒ 判不准（None + 原因）。
    """
    if any(kinds[i] == "sub" for i in idxs):
        return None, _SUB_DETAIL
    if any(kinds[i] in ("minus", "plus") for i in idxs):
        return None, _MINUS_PLUS
    seq = [i for i in idxs if kinds[i] != "skip"]
    markers = [i for i in seq if kinds[i] == "marker"]
    if not markers:
        data = [i for i in seq if kinds[i] == "data"]
        return (data, None) if data else (None, _NO_DETAIL)
    top = [i for i in seq if i < markers[0] and kinds[i] == "data"]
    for m in markers:
        pos = seq.index(m)
        prev = seq[pos - 1] if pos else None
        if prev is None or kinds[prev] != "data":
            return None, "「其中：」上一行不是明细行"
        if prev not in top:
            top.append(prev)
    return (sorted(top), None) if top else (None, _NO_DETAIL)


def _heading_issue(rows: list[Any], kinds: list[str], idxs: list[int]) -> str | None:
    """一段里的分段标题只能是第一行；跨了标题的小计范围认不准。"""
    seq = [i for i in idxs if kinds[i] != "skip"]
    heads = [i for i in seq if _HEADING_RE.match(_label(rows[i]))]
    if not heads or heads == seq[:1]:
        return None
    return "小计的范围跨了几个分段标题（「一、」「（二）」），合计范围无法自动判定"


def _subtotal_groups(kinds: list[str], subs: list[int], end: int) -> tuple[list[tuple[int, list[int]]], bool]:
    """(小计行, 本组行)，以及是不是标题式（小计在本组之上）。

    标题式 = 第一行就是小计、下面有明细、没有减项 / 加项（有一组删空了也还是标题式：该组小计判不准，不把上一组的
    明细算给它）；「小计 / 减：X / 合计」（续表只剩合计部分）不是标题式。
    """
    first = next((i for i, k in enumerate(kinds) if k != "skip"), None)
    below = [(s, list(range(s + 1, b))) for s, b in zip(subs, subs[1:] + [end])]
    under = [kinds[i] for _s, g in below for i in g]
    if first == subs[0] and not {"minus", "plus"} & set(under) and {"data", "marker", "sub"} & set(under):
        return below, True
    above: list[tuple[int, list[int]]] = []
    prev = -1
    for s in subs:
        above.append((s, list(range(prev + 1, s))))
        prev = s
    return above, False


def _segment_head_terms(rows: list[Any], kinds: list[str], totals: list[int],
                        ) -> tuple[dict[int, list[tuple[int, int]]], dict[int, str]] | None:
    """段首合计（spec note-pull-followup-closure R7）：每个合计都是分段标题式（「一、账面原值合计」）、表的第一行就是合计、
    合计下面到下一个合计之前是本段明细 ⇒ 合计 = 本段明细之和（固定资产 / 投资性房地产 / 无形资产 / 油气资产 / 使用权资产
    「一、原价合计 / 二、累计折旧合计 / …」，原先整表按「多个合计」判不准）。

    段内「其中：X」只许是本段第一行（列举本段构成：「一、成本合计 / 其中：1、房屋、建筑物 / 2、土地使用权」）；其余位置的
    「其中」、「其中：」标记行、减项 / 加项、段内另有分段标题 ⇒ 该合计判不准。有小计、某个合计不是分段标题式、第一行不是
    合计（「资产合计 / 负债合计」夹在明细中间）⇒ 不是这种形态，返回 None 走原判定。
    """
    first = next((i for i, k in enumerate(kinds) if k != "skip"), None)
    if first != totals[0] or any(kinds[t] != "total" or not _HEADING_RE.match(_label(rows[t])) for t in totals):
        return None
    plans: dict[int, list[tuple[int, int]]] = {}
    reasons: dict[int, str] = {}
    for t, end in zip(totals, totals[1:] + [len(rows)]):
        seq = [i for i in range(t + 1, end) if kinds[i] != "skip"]
        if any(kinds[i] == "marker" for i in seq) or any(kinds[i] == "sub" for i in seq[1:]):
            reasons[t] = _SUB_DETAIL
        elif any(kinds[i] in ("minus", "plus") for i in seq):
            reasons[t] = _MINUS_PLUS
        elif any(_HEADING_RE.match(_label(rows[i])) for i in seq):
            reasons[t] = _SEGMENT_HEADING
        elif not seq:
            reasons[t] = _NO_DETAIL
        else:
            plans[t] = [(i, 1) for i in seq]
    return plans, reasons


def total_terms(rows: list[Any]) -> tuple[dict[int, list[tuple[int, int]]], dict[int, str]]:
    """合计 / 小计行 → 参与合计的 ``(行号, 符号)``；判不准的合计行 → 原因（不生成、不回填）。"""
    kinds = [row_kind(r) for r in rows]
    totals = [i for i, k in enumerate(kinds) if k in ("total", "subtotal")]
    plans: dict[int, list[tuple[int, int]]] = {}
    reasons: dict[int, str] = {}
    if not totals:
        return plans, reasons
    head = _segment_head_terms(rows, kinds, totals)
    if head is not None:
        return head
    if len(totals) == 1:
        t = totals[0]
        idxs = list(range(t))
        top, why = _top_rows(kinds, idxs)
        if top and kinds[t] == "subtotal":
            why = _heading_issue(rows, kinds, idxs)
            top = None if why else top
        if top:
            plans[t] = [(i, 1) for i in top]
        else:
            reasons[t] = why or _NO_DETAIL
        return plans, reasons

    subs = [i for i in totals if kinds[i] == "subtotal"]
    tots = [i for i in totals if kinds[i] == "total"]
    whole: str | None = None
    if len(tots) > 1 or (tots and tots[0] != totals[-1]):
        whole = "表里有多个合计行（或合计行之后还有小计），合计范围无法自动判定"
    else:
        plain = [bool(_PLAIN_SUBTOTAL_RE.fullmatch(_label(rows[s]))) for s in subs]
        if any(plain) and not all(plain):
            whole = "分项小计与小计并存（嵌套小计），合计范围无法自动判定"
    groups: list[tuple[int, list[int]]] = []
    heading = False
    if whole is None:
        groups, heading = _subtotal_groups(kinds, subs, tots[0] if tots else len(rows))
        if not heading:
            whole = next((w for _s, g in groups if (w := _heading_issue(rows, kinds, g))), None)
    if whole is not None:
        return {}, {t: whole for t in totals}

    for s, g in groups:
        top, why = _top_rows(kinds, g)
        if top:
            plans[s] = [(i, 1) for i in top]
        else:
            reasons[s] = why or _NO_DETAIL
    if tots:
        t = tots[0]
        between = [] if heading else [i for i in range(subs[-1] + 1, t) if kinds[i] != "skip"]
        if any(kinds[i] not in ("data", "minus", "plus") for i in between):
            reasons[t] = "最后一个小计与合计之间有「其中」行，合计范围无法自动判定"
        else:
            plans[t] = [(s, 1) for s in subs] + [(i, -1 if kinds[i] == "minus" else 1) for i in between]
    return plans, reasons


def total_order(rows: list[Any], plans: Iterable[int]) -> list[int]:
    """回填顺序：先小计、再合计（合计的构成里有小计）。"""
    return sorted(plans, key=lambda r: (row_kind(rows[r]) != "subtotal", r))


def flatten_terms(rows: list[Any], plans: dict[int, list[tuple[int, int]]],
                  row: int) -> list[tuple[int, int]] | None:
    """合计构成展开到明细行（小计换成它自己的明细）；本行或其中某个小计判不准 ⇒ None。"""
    if row not in plans:
        return None
    out: list[tuple[int, int]] = []
    for r, sign in plans[row]:
        if row_kind(rows[r]) in ("total", "subtotal"):
            inner = flatten_terms(rows, plans, r) if r != row else None
            if inner is None:
                return None
            out.extend((i, sign * s) for i, s in inner)
        else:
            out.append((r, sign))
    return out


def sum_terms(terms: Iterable[tuple[int, int]], read: Callable[[int], Decimal | None]) -> Decimal | None:
    """按合计构成求和：``read(行号)`` 取这一列的数；构成里的格全空 ⇒ None（不写 0）。"""
    total, seen = Decimal(0), False
    for r, sign in terms:
        value = read(r)
        if value is None:
            continue
        total += value if sign > 0 else -value
        seen = True
    return total if seen else None


def plan_description(rows: list[Any], terms: list[tuple[int, int]]) -> str:
    """「明细之和」/「小计 − 减：坏账准备」/「各小计之和」—— 公式管理里的可读说明。"""
    subs = [r for r, _s in terms if row_kind(rows[r]) == "subtotal"]
    if not subs:
        return "明细之和"
    head = "小计" if len(subs) == 1 else "各小计之和"
    return head + "".join(
        f" {'−' if s < 0 else '+'} {str(rows[r].get('label') or '').strip()}" for r, s in terms if r not in subs)
