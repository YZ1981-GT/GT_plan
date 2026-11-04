"""执行税审底稿结构化取数规则（model.rules / model.lists）→ 目标格的值、状态、原因。

op（见 spec design §3）：
- amount：``path``（可带本行标签格 ``label`` 作为最后一级）+ ``measure``
- month：同上 + ``month``（序时账按月发生额）
- list_name / list_amount：列表第 index 行的名称 / 金额；列表按 ``lists[id]`` 现算，
  行数不够时超出部分并入最后一行（「其他（共 N 个科目）」）
- others_sum：``path`` 下排除 ``exclude`` 名称后的合计
status：auto 照取 / confirm 照取但标待确认 / manual 不取数（需人工判断）

底稿映射页「科目 → 税审底稿」据此反查（与取数同一套执行代码）：
- ``RuleResult.nodes``：本格实际用到的客户科目节点；manual / 取不到 / 空行为空。
- ``RuleResult.scope``：取不到（有 ``issue``）时，规则一级科目对应的客户科目 —— 规则指向它、但没取到数
  （如「主营业务成本」下没有「销售商品」明细）；一级科目口径与取数相同（``AccountBook.tops``：只认标准科目映射，
  标准表没有的名称只认客户一级科目全等 / 同义）；一级科目都找不到、manual、空行为空。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable

from app.services.tax_workpaper_classify import Assignment, Category, classify, grouped_entries
from app.services.tax_workpaper_fetch import SYNONYMS, AccountBook, Node, display_name, name_key


@dataclass
class RuleResult:
    value: Decimal | str | None
    status: str
    rule: str
    issue: str | None = None
    nodes: list[Node] = field(default_factory=list)
    scope: list[Node] = field(default_factory=list)


@dataclass
class _Entry:
    name: str
    nodes: list[Node]
    bundled: bool = False  # 溢出合并行
    itself: bool = False  # 上级下面没有明细、列的是上级本身（金额路径也按上级本身取）


#: 分类表的余项类别名（按 ``name_key`` 口径）
OTHERS_KEY = "其他"
_MEASURE_LABEL = {"debit": "借方发生额", "credit": "贷方发生额", "closing": "期末余额", "opening": "期初余额"}
#: 事业单位 / 民间非营利组织专用表（sheet 名带「（3)」）：规则里混有企业科目同名项（投资收益、管理费用），
#: 企业账套照样取得到，会把企业的投资收益填进事业单位收入表、算进广告费扣除基数。
_ENTITY_SHEET_RE = re.compile(r"[（(]3[)）]")


def sibling_categories(rules: list[dict]) -> dict[tuple[str, tuple[str, ...]], list[str]]:
    """同一张表、同一上级路径下，与「其他」并列的具名类别（2-01 主营业务收入：商品销售收入 / 提供劳务收入 / …）。

    「其他」= 上级科目里不属于任何具名类别的明细（余项），保证各类别 + 其他 = 一级科目合计
    （spec citar-case-chain-fetch-fixes R6：原按名字找叫「其他」的明细，客户明细叫不上类别名时整笔丢失）。
    """
    by_prefix: dict[tuple[str, tuple[str, ...]], list[str]] = {}
    has_others: set[tuple[str, tuple[str, ...]]] = set()
    for r in rules:
        path = r.get("path") or []
        if len(path) < 2:
            continue
        key = (r["sheet"], tuple(path[:-1]))
        last = path[-1]
        if name_key(last) == OTHERS_KEY:
            has_others.add(key)
            continue
        names = by_prefix.setdefault(key, [])
        if last not in names:
            names.append(last)
    return {k: v for k, v in by_prefix.items() if k in has_others}


class RuleRunner:
    def __init__(
        self,
        book: AccountBook,
        lists: dict[str, dict],
        label_text: Callable[[str, str], str | None],
        rules: list[dict] | None = None,
        groups: dict[str, dict] | None = None,
    ) -> None:
        self.book = book
        self.lists = lists
        self.label_text = label_text
        #: 按行标签分类的组（model.classify_groups，spec citar-audited-balance-and-workpaper-coverage R3）
        self.groups = groups or {}
        self._assignments: dict[str, tuple[Assignment | None, str | None]] = {}
        self._entries: dict[str, tuple[list[_Entry], str | None]] = {}
        self._siblings = sibling_categories(rules or [])
        self._entity_tops: dict[str, set[str]] = {}
        for r in rules or []:
            if _ENTITY_SHEET_RE.search(r["sheet"]) and r.get("path"):
                self._entity_tops.setdefault(r["sheet"], set()).add(r["path"][0])
        self._entity_applies: dict[str, bool] = {}

    def entity_sheet_applies(self, sheet: str) -> bool:
        """事业单位 / 民非专用表是否适用：账套里有该表的专用一级科目（标准企业科目表没有的名称，
        如事业收入 / 经营收入 / 会费收入 / 业务活动成本）才取数。spec citar-case-chain-fetch-fixes R13。"""
        tops = self._entity_tops.get(sheet)
        if not tops:
            return True
        if sheet not in self._entity_applies:
            own = [t for t in tops if t not in self.book.chart_names]
            self._entity_applies[sheet] = any(self.book.tops(t) for t in own)
        return self._entity_applies[sheet]

    def resolve(self, sheet: str, path: list[str]) -> tuple[list[Node], str | None]:
        """规则路径 → 节点。末级是「其他」且本表有并列具名类别时取余项，否则同 ``AccountBook.resolve``。"""
        if len(path) >= 2 and name_key(path[-1]) == OTHERS_KEY:
            siblings = self._siblings.get((sheet, tuple(path[:-1])))
            if siblings:
                return self._remainder(list(path[:-1]), siblings)
        return self.book.resolve(path)

    def _remainder(self, prefix: list[str], siblings: list[str]) -> tuple[list[Node], str | None]:
        base, issue = self.book.resolve(prefix)
        if not base:
            return [], issue
        taken: set[str] = set()
        for name in siblings:
            hits, _ = self.book.resolve([*prefix, name])
            for h in hits:
                taken.add(h.code)
                taken.update(d.code for d in self.book.descendants(h))
        rest = [leaf for b in base for leaf in self.book.leaves(b) if leaf.code not in taken]
        return rest, None

    # ── 按行标签分类 ──
    def assignment(self, group_id: str) -> tuple[Assignment | None, str | None]:
        """一组的分类结果（每组只算一次）；一级科目取不到时 (None, 原因)。末级合计与一级科目不等时给原因。"""
        if group_id in self._assignments:
            return self._assignments[group_id]
        g = self.groups[group_id]
        base, issue = self.book.resolve(g["path"])
        if not base:
            self._assignments[group_id] = (None, issue)
            return self._assignments[group_id]
        cats = [Category(c["index"], c["label"], tuple(c.get("exact") or ()), tuple(c.get("contains") or ()),
                         tuple(c.get("not_contains") or ())) for c in g["categories"]]
        result = classify(self.book, base, cats, set(g.get("base_names") or ()) | set(g["path"]))
        leaves = [n for ns in result.by_category.values() for n in ns] + result.rest
        diff = self.book.measure(base, g["measure"]) - self.book.measure(leaves, g["measure"])
        if abs(diff) >= Decimal("0.005"):
            result.issue = (f"「{g['path'][0]}」一级科目的{_MEASURE_LABEL.get(g['measure'], '')}与末级明细合计相差 {diff}，"
                            "各行按末级明细取数，请核对余额表上下级")
        self._assignments[group_id] = (result, None)
        return self._assignments[group_id]

    def _classify(self, item: dict) -> RuleResult:
        status, rule = item["status"], item["rule"]
        group = self.groups[item["group"]]
        result, issue = self.assignment(item["group"])
        first = item["category"] == group["categories"][0]["index"]
        if result is None:
            return RuleResult(None, status, rule, issue if first else None)
        nodes = result.by_category.get(item["category"]) or []
        if not nodes:
            return RuleResult(None, status, rule, result.issue if first else None)
        return RuleResult(self.book.measure(nodes, group["measure"]), status, rule, result.issue if first else None, nodes)

    def _classified_entries(self, spec: dict) -> tuple[list[_Entry], str | None]:
        result, issue = self.assignment(spec["group"])
        if result is None:
            return [], issue
        cat = spec.get("category")
        leaves = result.rest if cat is None else (result.by_category.get(cat) or [])
        return [_Entry(name, nodes) for name, nodes in grouped_entries(self.book, result.base, leaves)], None

    # ── 列表 ──
    def entries(self, list_id: str) -> tuple[list[_Entry], str | None]:
        if list_id in self._entries:
            return self._entries[list_id]
        spec = self.lists[list_id]
        if spec["mode"] == "classified":
            entries, issue = self._classified_entries(spec)
            slots = len(spec["refs"])
            if len(entries) > slots:
                keep, rest = entries[: slots - 1], entries[slots - 1:]
                entries = keep + [_Entry(f"其他（共 {len(rest)} 个科目）", [n for e in rest for n in e.nodes], bundled=True)]
            self._entries[list_id] = (entries, issue)
            return self._entries[list_id]
        base, issue = self.book.resolve(spec["path"])
        candidates: list[Node] = []
        itself = False
        if base:
            exclude = spec.get("exclude") or []
            if spec["mode"] == "leaves":
                candidates = [leaf for n in base for leaf in self.book.leaves(n)]
            else:
                kids = [k for n in base for k in self.book.kids(n)]
                if not kids:
                    # 上级下面没有明细时列上级本身：三级科目内容（二级下无明细）、一级科目无下级
                    # （其他收益 / 营业外收入只有一级科目、平铺科目表的「一级-明细」节点）
                    kids = list(base)
                    itself = True
                if exclude:
                    excluded = {k.code for name in exclude for k in self._strict(kids, name)}
                    kids = [k for k in kids if k.code not in excluded]
                if spec["mode"] == "others":
                    kids = [leaf for k in kids for leaf in (self.book.kids(k) or [k])]
                candidates = kids
            candidates = [n for n in candidates if self.book.has_activity(n)]
            if not candidates and not issue:
                issue = f"「{'-'.join(spec['path'])}」下没有有余额或发生额的明细科目"
        slots = len(spec["refs"])
        entries = [_Entry(display_name(n.label) or n.code, [n], itself=itself and n in base) for n in candidates]
        if len(entries) > slots:
            keep, rest = entries[: slots - 1], entries[slots - 1:]
            bundle = _Entry(f"其他（共 {len(rest)} 个科目）", [n for e in rest for n in e.nodes], bundled=True)
            entries = keep + [bundle]
        self._entries[list_id] = (entries, issue)
        return entries, issue

    def _strict(self, nodes: list[Node], name: str) -> list[Node]:
        """排除名单的匹配：全等、同义词全等、较短一方 ≥ 4 字的包含。

        比 ``AccountBook.match`` 严：表上已列示的「其他」「其中：」不能把客户的同名 / 近名科目误排除掉
        （包含匹配在 2~3 字时太宽）。
        """
        key = name_key(name)
        # 「其他」行本身就是「其中」明细的合计行，客户叫「其他」的科目应列在其中明细里，不排除
        if not key or key == "其他":
            return []
        synonyms = {name_key(s) for s in SYNONYMS.get(display_name(name), [])}
        out = []
        for n in nodes:
            nk = name_key(n.label)
            if not nk:
                continue
            short, long_ = sorted((nk, key), key=len)
            if nk == key or nk in synonyms or (len(short) >= 4 and short in long_):
                out.append(n)
        return out

    def _amount_nodes(self, entry: _Entry, base: list[Node]) -> list[Node]:
        """列表行的明细在金额路径下对应的节点：同一棵树直接用，否则按名称在金额路径下找。

        列的是上级本身（固定资产下没有明细）时，金额路径同样取其上级本身（累计折旧）——两者名称不同，
        按名称找不到（spec citar-case-chain-fetch-fixes R8：案例 1 折旧整笔漏掉）。
        """
        out: list[Node] = []
        for node in entry.nodes:
            if any(self.book.is_under(node, b) for b in base):
                out.append(node)
                continue
            # 金额路径本身可能就是末级（累计折旧-房屋建筑物 下不再分明细）：连同自身一起找
            pool = [x for b in base for x in [b, *self.book.descendants(b)]]
            hits = self.book.match(pool, node.label)
            if not hits and entry.itself:
                hits = [b for b in base if not b.children]
            out.extend(hits)
        return out

    # ── 单格 ──
    def run(self, item: dict) -> RuleResult:
        res = self._run(item)
        if res.issue and not res.nodes and res.status != "manual" and not self.book.empty:
            path = item.get("path") or (self.lists[item["list"]]["path"] if item.get("list") else None)
            if not path and item.get("group"):
                path = self.groups[item["group"]]["path"]
            if path:
                res.scope = self.book.tops(path[0])
        return res

    def _run(self, item: dict) -> RuleResult:
        status, rule = item["status"], item["rule"]
        if status == "manual":
            return RuleResult(None, status, rule, "需人工判断后填写")
        if self.book.empty:
            return RuleResult(None, status, rule, "本年度尚未导入科目余额表")
        if not self.entity_sheet_applies(item["sheet"]):
            return RuleResult(None, status, rule, None)  # 企业账套：事业单位 / 民非专用表不取数
        op = item["op"]
        if op == "list_name":
            entries, issue = self.entries(item["list"])
            i = item["index"]
            if i >= len(entries):
                return RuleResult(None, status, rule, issue if i == 0 else None)
            return RuleResult(entries[i].name, status, rule, issue if i == 0 else None, list(entries[i].nodes))
        if op == "list_amount":
            return self._list_amount(item)
        if op == "others_sum":
            return self._others_sum(item)
        if op == "classify":
            return self._classify(item)
        path = list(item["path"])
        if item.get("label"):
            label = self.label_text(item["sheet"], item["label"])
            if not label:
                return RuleResult(None, status, rule, None)  # 本行没有科目名：空行
            path.append(label)
        nodes, issue = self.resolve(item["sheet"], path)
        if not nodes:
            return RuleResult(None, status, rule, issue)
        if op == "month":
            value = self.book.month(nodes, item["measure"], item["month"])
            if value is None:
                # 科目已找到、只是没读序时账：节点照带（底稿映射页不读序时账也能反查）
                return RuleResult(None, status, rule, "本年度尚未导入序时账", nodes)
            return RuleResult(value, status, rule, None, nodes)
        return RuleResult(self.book.measure(nodes, item["measure"]), status, rule, None, nodes)

    def _list_amount(self, item: dict) -> RuleResult:
        status, rule = item["status"], item["rule"]
        entries, issue = self.entries(item["list"])
        i = item["index"]
        list_spec = self.lists[item["list"]]
        name_ref = list_spec["refs"][i]
        override = self.label_text(list_spec["sheet"], name_ref)
        base, base_issue = self.book.resolve(item.get("path") or list_spec["path"])
        if not base:
            return RuleResult(None, status, rule, base_issue)
        if override and (i >= len(entries) or override != entries[i].name):
            # 用户改了这一行的科目名：按改后的名称在金额路径下找（金额路径没有下级时连同自身）
            hits = self.book.match([d for b in base for d in (self.book.descendants(b) or [b])], override)
            if not hits:
                return RuleResult(None, status, rule, f"未找到明细科目「{override}」")
            return RuleResult(self.book.measure(hits, item["measure"]), status, rule, None, hits)
        if i >= len(entries):
            return RuleResult(None, status, rule, None)
        nodes = self._amount_nodes(entries[i], base)
        if not nodes:
            return RuleResult(None, status, rule, f"「{'-'.join(item.get('path') or list_spec['path'])}」下未找到与「{entries[i].name}」对应的明细")
        return RuleResult(self.book.measure(nodes, item["measure"]), status, rule, None, nodes)

    def _others_sum(self, item: dict) -> RuleResult:
        status, rule = item["status"], item["rule"]
        base, issue = self.book.resolve(item["path"])
        if not base:
            return RuleResult(None, status, rule, issue)
        kids = [k for n in base for k in (self.book.kids(n) or [n])]  # 没有下级时按上级本身归类
        excluded = {k.code for name in item["exclude"] for k in self._strict(kids, name)}
        rest = [k for k in kids if k.code not in excluded]
        return RuleResult(self.book.measure(rest, item["measure"]), status, rule, None, rest)
