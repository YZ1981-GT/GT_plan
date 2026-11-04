"""税审底稿「按行标签分类」取数：把一级科目的末级明细分到表上各行，每个末级只归一行，归不进的列入「其他」明细。

用于样表没有「取数规则」区、行是固定费用项目的表（2-07 税金及附加、2-08 销售费用、2-09 管理费用、2-10 财务费用、
3-03-04 长期待摊费用；spec citar-audited-balance-and-workpaper-coverage R3）。保证：各行 + 其他 = 末级合计。

匹配一个末级时按层次找，第一个有命中的层次定归属：
1. 末级自己名称的最后一段（平铺科目「职工薪酬_社会保险_基本医疗保险」取「基本医疗保险」）：全等 / 别名全等 / 包含别名；
2. 末级名称的前面几段（由近到远）：只认全等 / 别名全等；
3. 上级科目（由近到远，不含一级科目本身）：只认全等 / 别名全等。
同一层次多行命中时：全等 > 包含；同分取匹配词较长的，再同分取表上靠前的行。
「其他」「其他费用」这类泛称不参与匹配（跳到上一层）；``not_contains`` 命中末级全路径时该行不参与。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.tax_workpaper_fetch import AccountBook, Node, display_name, name_key

#: 平铺科目名称分段（与 tax_workpaper_fetch._FLAT_SEP 同口径）
_SEP = re.compile(r"\s*[-_－—]\s*")
_GENERIC = frozenset({"其他", "其它", "其他费用", "其它费用", "杂费", "其他支出", "其他杂费", "零星支出"})
_EXACT, _CONTAINS, _REVERSE = 3, 2, 1
#: 行名本身被末级名称包含 / 末级名称被行名包含时，较短一方至少几个字才算（2~3 字太宽）
_REVERSE_MIN = 4


@dataclass(frozen=True)
class Category:
    """表上一行：``label`` 行名（样表原文）；别名口径见模块说明。"""

    index: int
    label: str
    exact: tuple[str, ...] = ()
    contains: tuple[str, ...] = ()
    not_contains: tuple[str, ...] = ()

    def keys(self) -> tuple[set[str], set[str]]:
        label = name_key(self.label)
        exact = {label, *(name_key(a) for a in self.exact)}
        contains = {name_key(a) for a in self.contains}
        if len(label) >= _REVERSE_MIN:
            contains.add(label)
        return exact, contains


@dataclass
class Assignment:
    """一组分类的结果：``by_category`` 行号 → 末级；``rest`` 归不进的末级；``base`` 一级科目节点。"""

    base: list[Node]
    by_category: dict[int, list[Node]] = field(default_factory=dict)
    rest: list[Node] = field(default_factory=list)
    issue: str | None = None


def _segments(text: str) -> list[str]:
    return [p for p in _SEP.split(text or "") if p]


def _is_generic(text: str, base_names: set[str]) -> bool:
    if text in _GENERIC:
        return True
    # 「其他销售费用」「其他管理费用」= 一级科目的泛称
    return any(text.startswith(("其他", "其它")) and text[2:] == b for b in base_names)


def _levels(book: AccountBook, leaf: Node, base_codes: set[str], base_names: set[str]) -> list[tuple[str, bool]]:
    """(比较用名称, 是否允许包含匹配)，由近到远。"""
    segs = [name_key(s) for s in _segments(display_name(leaf.label))] or [name_key(leaf.label)]
    out: list[tuple[str, bool]] = [(segs[-1], True)]
    out += [(s, False) for s in reversed(segs[:-1])]
    cur = leaf.parent
    while cur and cur not in base_codes:
        node = book.nodes[cur]
        last = _segments(display_name(node.label))
        out.append((name_key(last[-1] if last else node.label), False))
        cur = node.parent
    return [(t, c) for t, c in out if t and t not in base_names]


def _path_text(book: AccountBook, leaf: Node, base_codes: set[str]) -> str:
    parts = [name_key(leaf.label)]
    cur = leaf.parent
    while cur and cur not in base_codes:
        parts.append(name_key(book.nodes[cur].label))
        cur = book.nodes[cur].parent
    return "|".join(parts)


def _best(text: str, allow_contains: bool, cats: list[tuple[Category, set[str], set[str], tuple[str, ...]]],
          path: str) -> Category | None:
    best: tuple[int, int, int] | None = None
    hit: Category | None = None
    for cat, exact, contains, blocked in cats:
        if any(b in path for b in blocked):
            continue
        score, size = 0, 0
        if text in exact:
            score, size = _EXACT, len(text)
        elif allow_contains:
            found = [k for k in contains if k and k in text]
            if found:
                score, size = _CONTAINS, max(len(k) for k in found)
            elif len(text) >= _REVERSE_MIN and name_key(cat.label).find(text) >= 0:
                score, size = _REVERSE, len(text)
        if score and (best is None or (score, size, -cat.index) > best):
            best, hit = (score, size, -cat.index), cat
    return hit


def classify(book: AccountBook, base: list[Node], categories: list[Category], base_names: set[str]) -> Assignment:
    """把 ``base`` 下有余额或发生额的末级分到 ``categories``；``base_names`` 是一级科目的各种写法（比较时跳过）。"""
    out = Assignment(base=base, by_category={c.index: [] for c in categories})
    base_codes = {b.code for b in base}
    # 一级科目的写法：标准名 + 有下级的一级科目节点自己的名称（营业费用）。平铺科目表的末级本身就是 base
    # （无上级行，「销售费用-办公费」local 为「办公费」），不能把它的名称当一级科目名跳过
    names = {name_key(n) for n in base_names}
    names |= {name_key(x) for b in base if b.children for x in (b.label, b.name)}
    names.discard("")
    prepared = [(c, *c.keys(), tuple(name_key(x) for x in c.not_contains)) for c in categories]
    for b in base:
        for leaf in book.leaves(b):
            if not book.has_activity(leaf):
                continue
            path = _path_text(book, leaf, base_codes)
            chosen: Category | None = None
            for text, allow_contains in _levels(book, leaf, base_codes, names):
                if _is_generic(text, names):
                    continue
                chosen = _best(text, allow_contains, prepared, path)
                if chosen is not None:
                    break
            if chosen is None:
                out.rest.append(leaf)
            else:
                out.by_category[chosen.index].append(leaf)
    return out


def grouped_entries(book: AccountBook, base: list[Node], leaves: list[Node]) -> list[tuple[str, list[Node]]]:
    """「其他」明细的显示行：一级科目的某个直接下级其有余额 / 发生额的末级全在 ``leaves`` 里 ⇒ 合成一行用下级的名称；
    否则逐个末级列出。顺序按科目码。"""
    wanted = {n.code for n in leaves}
    out: list[tuple[str, list[Node]]] = []
    for b in base:
        for kid in book.kids(b) or [b]:
            active = [leaf for leaf in book.leaves(kid) if book.has_activity(leaf)]
            mine = [leaf for leaf in active if leaf.code in wanted]
            if not mine:
                continue
            if len(mine) == len(active) and kid is not b:
                out.append((short_name(kid), mine))
            else:
                out.extend((short_name(leaf), [leaf]) for leaf in mine)
    return out


def short_name(node: Node) -> str:
    """显示名：平铺科目去掉打头的一级科目名后的明细名。"""
    return display_name(node.label) or node.code
