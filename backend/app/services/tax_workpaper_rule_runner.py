"""执行税审底稿结构化取数规则（model.rules / model.lists）→ 目标格的值、状态、原因。

op（见 spec design §3）：
- amount：``path``（可带本行标签格 ``label`` 作为最后一级）+ ``measure``
- month：同上 + ``month``（序时账按月发生额）
- list_name / list_amount：列表第 index 行的名称 / 金额；列表按 ``lists[id]`` 现算，
  行数不够时超出部分并入最后一行（「其他（共 N 个科目）」）
- others_sum：``path`` 下排除 ``exclude`` 名称后的合计
status：auto 照取 / confirm 照取但标待确认 / manual 不取数（需人工判断）
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from app.services.tax_workpaper_fetch import SYNONYMS, AccountBook, Node, display_name, name_key


@dataclass
class RuleResult:
    value: Decimal | str | None
    status: str
    rule: str
    issue: str | None = None


@dataclass
class _Entry:
    name: str
    nodes: list[Node]
    bundled: bool = False  # 溢出合并行


class RuleRunner:
    def __init__(
        self,
        book: AccountBook,
        lists: dict[str, dict],
        label_text: Callable[[str, str], str | None],
    ) -> None:
        self.book = book
        self.lists = lists
        self.label_text = label_text
        self._entries: dict[str, tuple[list[_Entry], str | None]] = {}

    # ── 列表 ──
    def entries(self, list_id: str) -> tuple[list[_Entry], str | None]:
        if list_id in self._entries:
            return self._entries[list_id]
        spec = self.lists[list_id]
        base, issue = self.book.resolve(spec["path"])
        candidates: list[Node] = []
        if base:
            exclude = spec.get("exclude") or []
            if spec["mode"] == "leaves":
                candidates = [leaf for n in base for leaf in self.book.leaves(n)]
            else:
                kids = [k for n in base for k in self.book.kids(n)]
                if spec["mode"] == "children" and not kids and len(spec["path"]) > 1:
                    kids = list(base)  # 三级科目内容：二级科目下没有明细时列二级本身
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
        entries = [_Entry(display_name(n.name) or n.code, [n]) for n in candidates]
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
            nk = name_key(n.name)
            if not nk:
                continue
            short, long_ = sorted((nk, key), key=len)
            if nk == key or nk in synonyms or (len(short) >= 4 and short in long_):
                out.append(n)
        return out

    def _amount_nodes(self, entry: _Entry, base: list[Node]) -> list[Node]:
        """列表行的明细在金额路径下对应的节点：同一棵树直接用，否则按名称在金额路径下找。"""
        out: list[Node] = []
        for node in entry.nodes:
            if any(self.book.is_under(node, b) for b in base):
                out.append(node)
                continue
            # 金额路径本身可能就是末级（累计折旧-房屋建筑物 下不再分明细）：连同自身一起找
            pool = [x for b in base for x in [b, *self.book.descendants(b)]]
            hits = self.book.match(pool, node.name)
            out.extend(hits)
        return out

    # ── 单格 ──
    def run(self, item: dict) -> RuleResult:
        status, rule = item["status"], item["rule"]
        if status == "manual":
            return RuleResult(None, status, rule, "需人工判断后填写")
        if self.book.empty:
            return RuleResult(None, status, rule, "本年度尚未导入科目余额表")
        op = item["op"]
        if op == "list_name":
            entries, issue = self.entries(item["list"])
            i = item["index"]
            name = entries[i].name if i < len(entries) else None
            return RuleResult(name, status, rule, issue if i == 0 else None)
        if op == "list_amount":
            return self._list_amount(item)
        if op == "others_sum":
            return self._others_sum(item)
        path = list(item["path"])
        if item.get("label"):
            label = self.label_text(item["sheet"], item["label"])
            if not label:
                return RuleResult(None, status, rule, None)  # 本行没有科目名：空行
            path.append(label)
        nodes, issue = self.book.resolve(path)
        if not nodes:
            return RuleResult(None, status, rule, issue)
        if op == "month":
            value = self.book.month(nodes, item["measure"], item["month"])
            if value is None:
                return RuleResult(None, status, rule, "本年度尚未导入序时账")
            return RuleResult(value, status, rule)
        return RuleResult(self.book.measure(nodes, item["measure"]), status, rule)

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
            # 用户改了这一行的科目名：按改后的名称在金额路径下找
            hits = self.book.match([d for b in base for d in self.book.descendants(b)], override)
            if not hits:
                return RuleResult(None, status, rule, f"未找到明细科目「{override}」")
            return RuleResult(self.book.measure(hits, item["measure"]), status, rule)
        if i >= len(entries):
            return RuleResult(None, status, rule, None)
        nodes = self._amount_nodes(entries[i], base)
        if not nodes:
            return RuleResult(None, status, rule, f"「{'-'.join(item.get('path') or list_spec['path'])}」下未找到与「{entries[i].name}」对应的明细")
        return RuleResult(self.book.measure(nodes, item["measure"]), status, rule)

    def _others_sum(self, item: dict) -> RuleResult:
        status, rule = item["status"], item["rule"]
        base, issue = self.book.resolve(item["path"])
        if not base:
            return RuleResult(None, status, rule, issue)
        kids = [k for n in base for k in self.book.kids(n)]
        excluded = {k.code for name in item["exclude"] for k in self._strict(kids, name)}
        rest = [k for k in kids if k.code not in excluded]
        return RuleResult(self.book.measure(rest, item["measure"]), status, rule)
