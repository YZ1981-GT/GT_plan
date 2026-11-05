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
from functools import lru_cache
from pathlib import Path
from typing import Callable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import AccountMapping, TbBalance, TbLedger
from app.services.dataset_query import get_active_filter
from app.services.ledger_import.direction_resolver import resolve_account_direction

_ZERO = Decimal(0)
_CENT = Decimal("0.005")
_CHART = Path(__file__).resolve().parents[2] / "data" / "standard_account_chart.json"

# 一级名称别名组：规则里的名称 → 多个标准科目（资产负债表「存货」项目口径）
GROUP_ALIASES: dict[str, list[str]] = {
    "存货": ["1401", "1402", "1403", "1404", "1405", "1406", "1407", "1408", "1411", "1421", "1461", "4001"],
}
# 明细名称同义词：规则里的名称 → 客户科目表常见写法
SYNONYMS: dict[str, list[str]] = {
    "应付福利费": ["职工福利费", "福利费"],
    # 工资薪金：平铺科目表（SAP）的工资、奖金分科目，股权激励属工资薪金（国家税务总局公告 2012 年第 18 号）
    "工资": ["应付工资", "应付工资津贴补贴", "工资津贴补贴", "应付奖金", "奖金", "股份支付", "应付股份支付",
             "工资、奖金、津贴和补贴", "工资奖金津贴和补贴"],
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
    # 企业会计制度科目写法（字序不同）
    "非流动资产处置损失": ["处置非流动资产损失"],
    "非流动资产处置利得": ["处置非流动资产利得", "处置非流动资产收益", "非流动资产处置收益"],
}
# 规则路径 (一级, 二级) 取不到时改在另一个一级科目下找：企业会计制度把工会经费、职工教育经费
# 计提在「其他应付款」（应付工资 / 应付福利费没有这两项）。住房公积金不回退：其他应付款-住房公积金
# 是代扣职工个人部分，不是单位缴纳的公积金。
FALLBACK_PATHS: dict[tuple[str, str], str] = {
    ("应付职工薪酬", "工会经费"): "其他应付款",
    ("应付职工薪酬", "职工教育经费"): "其他应付款",
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
    # 平铺科目表（SAP 10 位码、无上级行，名称「一级-明细」）去掉一级名称后的明细名；其余同 name
    local: str = ""

    @property
    def label(self) -> str:
        return self.local or self.name


#: 平铺科目名称的分段符（「应付职工薪酬-应付工会经费」「应收票据_银行承兑汇票」）
_FLAT_SEP = re.compile(r"\s*[-_－—]\s*")


def flat_local_name(name: str, top_names: set[str]) -> str:
    """平铺科目名称去掉打头的一级科目名：首段是本科目的标准一级科目名（``top_names``）才去掉，
    否则原样（「福利费-宿舍费用」映射到销售费用，首段不是一级名称，不能丢）。"""
    parts = [p for p in _FLAT_SEP.split(name or "") if p]
    if len(parts) >= 2 and name_key(parts[0]) in top_names:
        return "-".join(parts[1:])
    return name


def flat_segment(label: str, depth: int) -> str:
    """平铺科目明细名的第 ``depth`` 段（「应交增值税-进项税额」第 0 段「应交增值税」、第 1 段「进项税额」）。"""
    parts = [p for p in _FLAT_SEP.split(label or "") if p]
    return parts[depth] if depth < len(parts) else ""


def _signed(amount, direction: str | None) -> Decimal:
    value = Decimal(str(amount or 0))
    if direction == "credit":
        return -abs(value)
    if direction == "debit":
        return abs(value)
    return value


def _standard_chart() -> tuple[dict[str, list[str]], dict[str, str]]:
    """名称 → 标准码列表（同名的 6xxx 新码排在前）；标准码 → 方向。"""
    by_name: dict[str, list[str]] = defaultdict(list)
    direction: dict[str, str] = {}
    for a in _chart_accounts():
        by_name[a["name"]].append(a["code"])
        direction[a["code"]] = a["direction"]
    for codes in by_name.values():
        codes.sort(key=lambda c: (not c.startswith("6"), c))
    return by_name, direction


@lru_cache(maxsize=1)
def _chart_accounts() -> tuple[dict, ...]:
    return tuple(json.loads(_CHART.read_text(encoding="utf-8"))["accounts"])


@lru_cache(maxsize=1)
def _pl_codes() -> frozenset[str]:
    return frozenset(a["code"] for a in _chart_accounts() if a.get("category") in ("revenue", "expense"))


def is_pl_standard(standard: str | None) -> bool:
    """标准科目是否损益类（标准科目表 category = revenue / expense；「6601-01」类带后缀的码取主码）。"""
    return bool(standard) and standard.split("-")[0] in _pl_codes()


def _chart_top_names(standard: str | None) -> set[str]:
    """标准科目（含「1231-02」这类带后缀的码取其主码）的名称，按 ``name_key`` 口径。"""
    if not standard:
        return set()
    codes = {standard, standard.split("-")[0]}
    return {name_key(a["name"]) for a in _chart_accounts() if a["code"] in codes}


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
    def match(
        self, candidates: list[Node], target: str, *, contains_ok: bool = True,
        key: Callable[[Node], str] | None = None,
    ) -> list[Node]:
        """先全等，再同义词全等，再包含（较短一方 ≥ 2 字；``contains_ok=False`` 时不做包含）。

        比较的是节点的 ``label``（平铺科目去掉一级名称后的明细名），``key`` 可换成别的取名方式。
        """
        get = key or (lambda n: n.label)
        target_key = name_key(target)
        if not target_key:
            return []
        keyed = [(n, name_key(get(n))) for n in candidates]
        hits = [n for n, k in keyed if k == target_key]
        if hits:
            return hits
        synonyms = {name_key(s) for s in SYNONYMS.get(display_name(target), [])}
        hits = [n for n, k in keyed if k in synonyms]
        if hits or not contains_ok:
            return hits

        def contains(a: str, b: str) -> bool:
            short, long_ = sorted((a, b), key=len)
            return len(short) >= 2 and short in long_
        return [n for n, k in keyed if k and contains(k, target_key)]

    def _std_tops(self, std: str) -> list[Node]:
        """映射到标准科目 std、且上级不映射到 std 的客户科目（该标准科目在客户科目树里的最高层）。"""
        return [n for n in self.nodes.values() if n.standard == std
                and not (n.parent and self.nodes[n.parent].standard == std)]

    def tops(self, name: str) -> list[Node]:
        """一级名称 → 顶层节点（spec mapping-code-collision-and-fetch-by-mapping R3：一级科目只认映射）。

        - 别名组（存货）：映射到组内标准科目的客户科目；
        - 名称在标准科目表里：只取映射到该标准科目的客户科目（同名多码时 6xxx 新码优先）；没有 ⇒ 空，
          不按客户科目名兜底（原兜底的包含匹配会让「短期借款」「长期借款」都取到其他应付款-借款）；
        - 不在标准科目表里（民非 / 事业单位科目）：只认**客户一级科目**的名称全等 / 同义词，不做包含匹配、不认同名明细。
        """
        if name in GROUP_ALIASES:
            hits = [n for std in GROUP_ALIASES[name] for n in self._std_tops(std)]
            return sorted(hits, key=lambda n: n.code)
        std_codes = self.chart_names.get(name, [])
        for std in std_codes:
            hits = self._std_tops(std)
            if hits:
                return sorted(hits, key=lambda n: n.code)
        if std_codes:
            return []
        return sorted(self.match(self.roots(), name, contains_ok=False, key=lambda n: n.name), key=lambda n: n.code)

    def top_issue(self, name: str) -> str:
        """一级科目取不到时的原因。"""
        std_codes = list(GROUP_ALIASES.get(name) or self.chart_names.get(name, []))
        if std_codes:
            return f"没有客户科目映射到标准科目「{name}」（{' / '.join(std_codes)}），请在底稿映射「客户科目 → 标准科目」补映射"
        return f"未找到科目「{name}」"

    def resolve(self, path: list[str]) -> tuple[list[Node], str | None]:
        """科目路径 → 节点；取不到返回 ([], 原因)。

        原路径取不到、且 (一级, 二级) 在 ``FALLBACK_PATHS`` 里时，按回退的一级科目再找一次（原因仍报原路径）。
        """
        nodes, issue = self._resolve(path)
        if not nodes and len(path) > 1:
            fallback = FALLBACK_PATHS.get((path[0], path[1]))
            if fallback:
                alt, _ = self._resolve([fallback, *path[1:]])
                if alt:
                    return alt, None
        return nodes, issue

    def fallback_top(self, path: list[str]) -> str | None:
        """``resolve(path)`` 是否经 ``FALLBACK_PATHS`` 改用了别的一级科目：是则返回该一级科目名（单元格来源写明，spec citar-cell-source-hover）。"""
        if len(path) < 2 or self._resolve(path)[0]:
            return None
        fallback = FALLBACK_PATHS.get((path[0], path[1]))
        return fallback if fallback and self._resolve([fallback, *path[1:]])[0] else None

    def _resolve(self, path: list[str]) -> tuple[list[Node], str | None]:
        nodes = self.tops(path[0])
        if not nodes:
            return [], self.top_issue(path[0])
        walked = [path[0]]
        for part in path[1:]:
            pool = [k for n in nodes for k in self.kids(n)]
            hits = self.match(pool, part)
            if not hits:
                # 中间级没有这一层时在全部下级里找（客户科目表层级与规则不完全一致）
                hits = self.match([d for n in nodes for d in self.descendants(n)], part)
            if not hits:
                # 平铺科目表（无上级行，名称「一级-明细-…」）：在本组没有下级的节点里按名称第 d 段找
                depth = len(walked) - 1
                hits = self.match([n for n in nodes if not n.children], part,
                                  key=lambda n, d=depth: flat_segment(n.label, d))
            if not hits:
                return [], f"「{'-'.join(walked)}」下未找到明细科目「{part}」"
            nodes = hits
            walked.append(part)
        return nodes, None

    # ── 口径 ──
    def natural_sign(self, node: Node) -> int:
        return -1 if node.direction == "credit" else 1

    def _unclosed_pl_leaves(self, node: Node, measure: str) -> list[Node]:
        """损益类科目取「本方向发生额」（费用借方 / 收入贷方）时，期末没结平的末级明细。

        账套每期把损益结转到本年利润时，对方发生额就是结转额，本方向发生额即本年发生额；
        没结转的账套（SAP 等，损益科目留有余额）对方发生额是冲减（成本冲回、销售退回），
        本方向发生额要减掉它（spec citar-case-chain-fetch-fixes R12：案例 2 主营业务成本借方
        14,502,719.31，贷方冲减 2,109,933.76，底稿年末未审数 12,392,785.55）。
        """
        natural = "debit" if node.direction == "debit" else "credit"
        if measure != natural or not is_pl_standard(node.standard):
            return []
        return [leaf for leaf in self.leaves(node) if abs(leaf.closing) >= _CENT]

    def measure(self, nodes: list[Node], measure: str) -> Decimal:
        total = _ZERO
        for n in nodes:
            if measure == "debit":
                total += n.debit - sum((leaf.credit for leaf in self._unclosed_pl_leaves(n, measure)), _ZERO)
            elif measure == "credit":
                total += n.credit - sum((leaf.debit for leaf in self._unclosed_pl_leaves(n, measure)), _ZERO)
            elif measure == "opening":
                total += n.opening * self.natural_sign(n)
            elif measure == "closing":
                total += n.closing * self.natural_sign(n)
            elif measure == "closing_debit":
                total += max(n.closing, _ZERO)
            elif measure == "closing_credit":
                total += max(-n.closing, _ZERO)
            elif measure == "paid_opening":
                # 本年支付以前年度金额 = min(年初余额, 本年借方)（职工薪酬类审核表；spec citar-audited-balance-and-workpaper-coverage）
                total += max(_ZERO, min(max(n.opening * self.natural_sign(n), _ZERO), n.debit))
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
            # 没结转的损益明细：本月对方发生额是冲减，扣掉（口径同 measure）
            for leaf in self._unclosed_pl_leaves(n, measure):
                dr, cr = self.monthly.get(leaf.code, {}).get(month, (_ZERO, _ZERO))
                total -= cr if measure == "debit" else dr
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

    mapping: dict[str, str] = {}
    mp = AccountMapping.__table__
    for orig, std in (await db.execute(
        sa.select(mp.c.original_account_code, mp.c.standard_account_code).where(
            mp.c.project_id == project_id, mp.c.is_deleted == sa.false(),
        )
    )).fetchall():
        mapping[normalize_code(orig)] = std

    monthly = await _load_monthly(db, project_id, year) if with_ledger else None
    return build_account_book(rows, mapping, monthly)


def build_account_book(
    rows, mapping: dict[str, str], monthly: dict[str, dict[int, tuple[Decimal, Decimal]]] | None = None,
) -> AccountBook:
    """余额行（带 account_code / account_name / opening_balance / opening_direction / debit_amount /
    credit_amount / closing_balance / closing_direction 属性）+ 客户科目 → 标准科目映射 → 科目树。

    不读库：离线验收（导入转换结果直接建树）与 ``load_account_book`` 共用。
    """
    picked: dict[str, tuple] = {}
    for row in rows:
        code = normalize_code(row.account_code)
        prev = picked.get(code)
        # 同码多行：优先名字不以「\」开头的行（真库错位导入时另一行挂的是相邻科目名）
        if prev is None or (str(prev.account_name or "").startswith("\\") and not str(row.account_name or "").startswith("\\")):
            picked[code] = row

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
        node.local = flat_local_name(node.name, _chart_top_names(node.standard)) if node.parent is None else node.name
    for node in nodes.values():
        if node.parent:
            nodes[node.parent].children.append(node.code)
    for node in nodes.values():
        node.children.sort()

    return AccountBook(nodes, monthly)


def monthly_totals(rows) -> dict[str, dict[int, tuple[Decimal, Decimal]]]:
    """(account_code, m, dr, cr) 行 → 科目 → 月 → (借, 贷)。"""
    out: dict[str, dict[int, tuple[Decimal, Decimal]]] = defaultdict(dict)
    for row in rows:
        if row.m is None:
            continue
        code, m = normalize_code(row.account_code), int(row.m)
        dr, cr = out[code].get(m, (_ZERO, _ZERO))
        out[code][m] = (dr + Decimal(str(row.dr or 0)), cr + Decimal(str(row.cr or 0)))
    return dict(out)


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
    return monthly_totals(rows)
