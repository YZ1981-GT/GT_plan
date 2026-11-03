"""税审底稿取数：项目账套（客户科目余额表 / 序时账 / 科目映射）→ 规则目标格的值。

结构化规则由生成脚本从样表解析（``tax_workpaper_model.json`` 的 rules / lists），这里只执行：

1. ``load_account_book``：读当前有效账套的 ``tb_balance``，科目码剥 ``.0``、同码多行取名字
   不以「\\」开头的那一行（错位导入时同码有一行是别的科目名），按码前缀建父子树；
   标准科目 = 本码或最近上级在 ``account_mapping`` 里的映射。
2. 路径解析：一级名称 → 标准科目表 / 客户科目名找到「顶层节点」，后续各级在下级里按名称匹配
   （去空白、全半角括号、取「\\」后最后一段；先全等、再同义词、再包含）。
3. 口径：期初 / 期末按 ``*_direction`` 转借正贷负，再按科目方向转成自然正数；
   closing_debit / closing_credit 只取该方向的余额；按月发生额来自 ``tb_ledger``。

取不到时值为 ``None`` 并给出原因（不写 0），由页面提示。
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import AccountMapping, TbBalance, TbLedger
from app.services.dataset_query import get_active_filter
from app.services.ledger_import.direction_resolver import resolve_account_direction

_ZERO = Decimal(0)
_CHART = Path(__file__).resolve().parents[2] / "data" / "standard_account_chart.json"

# 一级名称别名组：规则里的名称 → 多个标准科目（资产负债表「存货」项目口径）
GROUP_ALIASES: dict[str, list[str]] = {
    "存货": ["1401", "1402", "1403", "1404", "1405", "1406", "1407", "1408", "1411", "1421", "1461", "4001"],
}
# 明细名称同义词：规则里的名称 → 客户科目表常见写法
SYNONYMS: dict[str, list[str]] = {
    "应付福利费": ["职工福利费", "福利费"],
    "职工教育经费": ["教育经费"],
    "工会经费": ["工会会费"],
    "企业年金": ["补充养老保险", "年金"],
    "补充医疗保险": ["补充医疗"],
    "住房公积金": ["公积金"],
    "房屋建筑物": ["房屋及建筑物", "房屋、建筑物", "房屋建筑", "建筑物", "房屋"],
    "飞机、火车、轮船、机器、机械和其他生产设备": ["机器设备", "生产设备", "机械设备", "专用设备", "通用设备"],
    "与生产经营活动有关的器具、工具、家具等": ["办公设备", "器具工具家具", "工具器具", "家具", "办公家具"],
    "飞机、火车、轮船以外的运输工具": ["运输工具", "运输设备", "交通工具", "车辆"],
    "电子设备": ["电子产品", "计算机设备", "电脑设备"],
    "土地使用权": ["土地"],
    "软件": ["软件使用权", "计算机软件"],
}


def normalize_code(code: str) -> str:
    code = str(code).strip()
    return code[:-2] if code.endswith(".0") else code


def display_name(name: str | None) -> str:
    """客户科目名常带全路径（「\\其他应付款\\北京某公司」），取最后一段。"""
    text = (name or "").strip().strip("\\")
    return text.split("\\")[-1].strip() if text else ""


_LABEL_PREFIX = re.compile(r"^(其中|减|加)[:：]")


def name_key(name: str) -> str:
    """名称比较口径：取最后一段、去「其中：」「减：」前缀、全半角括号统一、去空白。"""
    text = display_name(name)
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\s+", "", text)
    return _LABEL_PREFIX.sub("", text).lower()


@dataclass
class Node:
    code: str
    name: str
    standard: str | None = None
    direction: str = "debit"
    parent: str | None = None
    children: list[str] = field(default_factory=list)
    opening: Decimal = _ZERO  # 借正贷负
    debit: Decimal = _ZERO
    credit: Decimal = _ZERO
    closing: Decimal = _ZERO  # 借正贷负


def _signed(amount, direction: str | None) -> Decimal:
    value = Decimal(str(amount or 0))
    if direction == "credit":
        return -abs(value)
    if direction == "debit":
        return abs(value)
    return value


def _standard_chart() -> tuple[dict[str, list[str]], dict[str, str]]:
    """名称 → 标准码列表（同名的 6xxx 新码排在前）；标准码 → 方向。"""
    chart = json.loads(_CHART.read_text(encoding="utf-8"))
    by_name: dict[str, list[str]] = defaultdict(list)
    direction: dict[str, str] = {}
    for a in chart["accounts"]:
        by_name[a["name"]].append(a["code"])
        direction[a["code"]] = a["direction"]
    for codes in by_name.values():
        codes.sort(key=lambda c: (not c.startswith("6"), c))
    return by_name, direction


class AccountBook:
    def __init__(self, nodes: dict[str, Node], monthly: dict[str, dict[int, tuple[Decimal, Decimal]]] | None = None) -> None:
        self.nodes = nodes
        self.monthly = monthly
        self.chart_names, self.chart_direction = _standard_chart()

    @property
    def empty(self) -> bool:
        return not self.nodes

    # ── 树 ──
    def roots(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.parent is None]

    def kids(self, node: Node) -> list[Node]:
        return [self.nodes[c] for c in sorted(node.children)]

    def descendants(self, node: Node) -> list[Node]:
        """全部下级，按科目码先序（与客户科目表顺序一致）。"""
        out: list[Node] = []
        stack = list(reversed(sorted(node.children)))
        while stack:
            code = stack.pop()
            out.append(self.nodes[code])
            stack.extend(reversed(sorted(self.nodes[code].children)))
        return out

    def leaves(self, node: Node) -> list[Node]:
        if not node.children:
            return [node]
        return [n for n in self.descendants(node) if not n.children]

    def depth(self, node: Node) -> int:
        d, cur = 0, node
        while cur.parent:
            d, cur = d + 1, self.nodes[cur.parent]
        return d

    def is_under(self, node: Node, ancestor: Node) -> bool:
        cur: Node | None = node
        while cur is not None:
            if cur.code == ancestor.code:
                return True
            cur = self.nodes.get(cur.parent) if cur.parent else None
        return False

    # ── 名称匹配 ──
    def match(self, candidates: list[Node], target: str) -> list[Node]:
        """先全等，再同义词全等，再包含（较短一方 ≥ 2 字）。"""
        key = name_key(target)
        if not key:
            return []
        hits = [n for n in candidates if name_key(n.name) == key]
        if hits:
            return hits
        synonyms = {name_key(s) for s in SYNONYMS.get(display_name(target), [])}
        hits = [n for n in candidates if name_key(n.name) in synonyms]
        if hits:
            return hits

        def contains(a: str, b: str) -> bool:
            short, long_ = sorted((a, b), key=len)
            return len(short) >= 2 and short in long_
        return [n for n in candidates if name_key(n.name) and contains(name_key(n.name), key)]

    def _std_tops(self, std: str) -> list[Node]:
        """映射到标准科目 std、且上级不映射到 std 的客户科目（该标准科目在客户科目树里的最高层）。"""
        return [n for n in self.nodes.values() if n.standard == std
                and not (n.parent and self.nodes[n.parent].standard == std)]

    def tops(self, name: str) -> list[Node]:
        """一级名称 → 顶层节点。别名组（存货）取全部成员；否则按同名标准码依次找（6xxx 新码优先）。"""
        if name in GROUP_ALIASES:
            hits = [n for std in GROUP_ALIASES[name] for n in self._std_tops(std)]
            return sorted(hits, key=lambda n: n.code)
        for std in self.chart_names.get(name, []):
            hits = self._std_tops(std)
            if hits:
                return sorted(hits, key=lambda n: n.code)
        # 标准科目表没有 / 未映射：按客户科目名找最浅的同名科目
        hits = self.match(list(self.nodes.values()), name)
        if not hits:
            return []
        shallowest = min(self.depth(n) for n in hits)
        return sorted((n for n in hits if self.depth(n) == shallowest), key=lambda n: n.code)

    def resolve(self, path: list[str]) -> tuple[list[Node], str | None]:
        """科目路径 → 节点；取不到返回 ([], 原因)。"""
        nodes = self.tops(path[0])
        if not nodes:
            return [], f"未找到科目「{path[0]}」"
        walked = [path[0]]
        for part in path[1:]:
            pool = [k for n in nodes for k in self.kids(n)]
            hits = self.match(pool, part)
            if not hits:
                # 中间级没有这一层时在全部下级里找（客户科目表层级与规则不完全一致）
                hits = self.match([d for n in nodes for d in self.descendants(n)], part)
            if not hits:
                return [], f"「{'-'.join(walked)}」下未找到明细科目「{part}」"
            nodes = hits
            walked.append(part)
        return nodes, None

    # ── 口径 ──
    def natural_sign(self, node: Node) -> int:
        return -1 if node.direction == "credit" else 1

    def measure(self, nodes: list[Node], measure: str) -> Decimal:
        total = _ZERO
        for n in nodes:
            if measure == "debit":
                total += n.debit
            elif measure == "credit":
                total += n.credit
            elif measure == "opening":
                total += n.opening * self.natural_sign(n)
            elif measure == "closing":
                total += n.closing * self.natural_sign(n)
            elif measure == "closing_debit":
                total += max(n.closing, _ZERO)
            elif measure == "closing_credit":
                total += max(-n.closing, _ZERO)
            else:
                raise ValueError(f"未知口径 {measure}")
        return total

    def month(self, nodes: list[Node], measure: str, month: int) -> Decimal | None:
        if self.monthly is None:
            return None
        total = _ZERO
        for n in nodes:
            for code in [n.code] + [d.code for d in self.descendants(n)]:
                dr, cr = self.monthly.get(code, {}).get(month, (_ZERO, _ZERO))
                total += dr if measure == "debit" else cr
        return total

    def has_activity(self, node: Node) -> bool:
        return any(v != 0 for v in (node.opening, node.debit, node.credit, node.closing))


async def load_account_book(db: AsyncSession, project_id: UUID, year: int, *, with_ledger: bool) -> AccountBook:
    bal = TbBalance.__table__
    rows = (await db.execute(
        sa.select(
            bal.c.account_code, bal.c.account_name, bal.c.opening_balance, bal.c.opening_direction,
            bal.c.debit_amount, bal.c.credit_amount, bal.c.closing_balance, bal.c.closing_direction,
        ).where(await get_active_filter(db, bal, project_id, year))
    )).fetchall()

    picked: dict[str, tuple] = {}
    for row in rows:
        code = normalize_code(row.account_code)
        prev = picked.get(code)
        # 同码多行：优先名字不以「\」开头的行（真库错位导入时另一行挂的是相邻科目名）
        if prev is None or (str(prev.account_name or "").startswith("\\") and not str(row.account_name or "").startswith("\\")):
            picked[code] = row

    mapping: dict[str, str] = {}
    mp = AccountMapping.__table__
    for orig, std in (await db.execute(
        sa.select(mp.c.original_account_code, mp.c.standard_account_code).where(
            mp.c.project_id == project_id, mp.c.is_deleted == sa.false(),
        )
    )).fetchall():
        mapping[normalize_code(orig)] = std

    _, chart_direction = _standard_chart()
    nodes: dict[str, Node] = {}
    for code, row in picked.items():
        nodes[code] = Node(
            code=code,
            name=display_name(row.account_name) or code,
            opening=_signed(row.opening_balance, row.opening_direction),
            debit=Decimal(str(row.debit_amount or 0)),
            credit=Decimal(str(row.credit_amount or 0)),
            closing=_signed(row.closing_balance, row.closing_direction),
        )
    codes = set(nodes)
    for code, node in nodes.items():
        node.parent = next((code[:i] for i in range(len(code) - 1, 0, -1) if code[:i] in codes), None)
        node.standard = next((mapping[code[:i]] for i in range(len(code), 0, -1) if code[:i] in mapping), None)
        node.direction = chart_direction.get(node.standard or "") or resolve_account_direction(code, node.name)[0]
    for node in nodes.values():
        if node.parent:
            nodes[node.parent].children.append(node.code)
    for node in nodes.values():
        node.children.sort()

    monthly = await _load_monthly(db, project_id, year) if with_ledger else None
    return AccountBook(nodes, monthly)


async def _load_monthly(db: AsyncSession, project_id: UUID, year: int) -> dict[str, dict[int, tuple[Decimal, Decimal]]]:
    led = TbLedger.__table__
    month = sa.func.coalesce(led.c.accounting_period, sa.extract("month", led.c.voucher_date))
    rows = (await db.execute(
        sa.select(
            led.c.account_code, month.label("m"),
            sa.func.coalesce(sa.func.sum(led.c.debit_amount), 0).label("dr"),
            sa.func.coalesce(sa.func.sum(led.c.credit_amount), 0).label("cr"),
        ).where(await get_active_filter(db, led, project_id, year)).group_by(led.c.account_code, month)
    )).fetchall()
    out: dict[str, dict[int, tuple[Decimal, Decimal]]] = defaultdict(dict)
    for row in rows:
        if row.m is None:
            continue
        code, m = normalize_code(row.account_code), int(row.m)
        dr, cr = out[code].get(m, (_ZERO, _ZERO))
        out[code][m] = (dr + Decimal(str(row.dr)), cr + Decimal(str(row.cr)))
    return dict(out)
