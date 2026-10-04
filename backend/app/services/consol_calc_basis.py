"""合并计算口径 —— 差额表与合并试算两条路径唯一共用的取数、归属与符号（spec consol-tree-three-code-autobuild 任务 7）。

design §五 / ADR-CTREE-003 / ADR-CTREE-005：
- 节点金额：data = 单体项目 ``trial_balance.audited_amount``（按项目 × 科目求和，项目为空计 0）；
  elim = 归属本节点的已审批分录**明细行** ``sign(a)·(借−贷)``（「其他调整」进调整列，其余进抵销列）；
  aggregate = Σ 直接子节点（P7）。
- 符号 ``sign(a)``：``resolve_account_direction`` 借方性质 +1、贷方性质 −1（备抵按名称识别），
  与单体调整分录同源；科目名取数据叶子试算表，缺失取分录行。
- 归属 ``attribute_entry``：``branch_entity_code`` 为空 ⇒ ``{承载合并项目企业代码}:consol_elim``；
  非空 ⇒ ``{branch_entity_code}:branch_elim``，且该节点须由分录所在项目承载；找不到 ⇒ 孤儿分录，
  两条路径都不计入，只在结果与诊断里列出（P9）。``related_company_codes`` 只作留痕与筛选。
- 装载范围：树内全部合并节点的合并项目 × 年度 × 已审批 × 未删（多级合并纳入下级抵销，需求 6.3）。
- 科目集合 = 数据叶子试算表科目 ∪ 已归属分录明细行科目（需求 5.6）。

``consol_worksheet_engine.recalc_full`` 与 ``consol_trial_service.recalculate_trial`` 只调本模块，
所以根节点合并数 = 个别数汇总 + 调整 + 抵销，逐科目恒等（P8）。纯函数层（``build_calc_basis`` /
``node_values`` / ``worksheet_rows`` / ``trial_amounts``）不连库，属性测试直接喂树与内存行。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.models.consolidation_models import EliminationEntry, ReviewStatusEnum
from app.services.consol_group_tree import (
    KIND_DATA,
    KIND_ELIM,
    ROLE_BRANCH_ELIM,
    ROLE_CONSOL,
    ROLE_CONSOL_ELIM,
    Diagnostic,
)
from app.services.consol_group_tree import node_key as make_node_key
from app.services.consol_tree_service import TreeNode, build_tree, iter_nodes
from app.services.ledger_import.direction_resolver import resolve_account_direction

ZERO = Decimal("0")
ONE = Decimal("1")
CENT = Decimal("0.01")
# 「其他调整」类分录进调整列（需求 5.7），其余类型（权益/内部交易/内部往来/未实现利润）进抵销列
ADJUSTMENT_ENTRY_TYPE = "other"


# ─────────────────────────────── 输入结构（与 ORM 解耦） ───────────────────────────────


@dataclass(frozen=True)
class TbRow:
    """数据叶子单体项目的一行试算表（审定数口径）。"""

    project_id: UUID
    account_code: str
    account_name: str | None
    account_category: Any
    audited_amount: Decimal | None


@dataclass(frozen=True)
class EntryLine:
    account_code: str
    account_name: str | None
    debit: Decimal
    credit: Decimal


@dataclass(frozen=True)
class EntryRecord:
    """一笔已审批分录（明细行已归一成 ``EntryLine``）。"""

    id: UUID
    project_id: UUID
    entry_no: str
    entry_type: str
    branch_entity_code: str | None
    lines: tuple[EntryLine, ...]


@dataclass(frozen=True)
class OrphanEntry:
    """找不到归属差额节点的分录（需求 6.4：列出，不静默丢弃、不挪到别的节点）。"""

    entry_id: UUID
    entry_no: str
    project_id: UUID
    branch_entity_code: str | None
    reason: str

    def to_dict(self) -> dict:
        return {
            "entry_id": str(self.entry_id),
            "entry_no": self.entry_no,
            "project_id": str(self.project_id),
            "branch_entity_code": self.branch_entity_code,
            "reason": self.reason,
        }


@dataclass
class ElimTotals:
    """某差额节点某科目的已归属明细行原始借贷合计（未归一，按录入方向）。

    ``by_type``：同一批明细行再按分录类型分桶（spec consol-elimination-single-source-push §4.1），
    供报表行级度量拆「权益抵销 / 往来交易抵销 / 调整」；四个合计列恒等于各桶之和（只经 ``add`` 累加）。
    """

    adj_debit: Decimal = ZERO
    adj_credit: Decimal = ZERO
    elim_debit: Decimal = ZERO
    elim_credit: Decimal = ZERO
    by_type: dict[str, tuple[Decimal, Decimal]] = field(default_factory=dict)

    def add(self, entry_type: str, debit: Decimal, credit: Decimal) -> None:
        if entry_type == ADJUSTMENT_ENTRY_TYPE:
            self.adj_debit += debit
            self.adj_credit += credit
        else:
            self.elim_debit += debit
            self.elim_credit += credit
        d, c = self.by_type.get(entry_type, (ZERO, ZERO))
        self.by_type[entry_type] = (d + debit, c + credit)


@dataclass(frozen=True)
class NodeAmounts:
    """差额表一行（节点 × 科目）的 7 个金额列。"""

    children_amount_sum: Decimal = ZERO
    adjustment_debit: Decimal = ZERO
    adjustment_credit: Decimal = ZERO
    elimination_debit: Decimal = ZERO
    elimination_credit: Decimal = ZERO
    net_difference: Decimal = ZERO
    consolidated_amount: Decimal = ZERO

    def columns(self) -> dict[str, Decimal]:
        return {
            "children_amount_sum": self.children_amount_sum,
            "adjustment_debit": self.adjustment_debit,
            "adjustment_credit": self.adjustment_credit,
            "elimination_debit": self.elimination_debit,
            "elimination_credit": self.elimination_credit,
            "net_difference": self.net_difference,
            "consolidated_amount": self.consolidated_amount,
        }


@dataclass(frozen=True)
class TrialAmounts:
    """合并试算一行：个别数汇总 + 调整 + 抵销 = 合并数，外加个别数溯源。"""

    individual_sum: Decimal
    consol_adjustment: Decimal
    consol_elimination: Decimal
    consol_amount: Decimal
    by_company: list[dict]


@dataclass(frozen=True)
class TreeIndex:
    nodes: dict[str, TreeNode]                  # node_key → 节点
    consol_by_project: dict[UUID, TreeNode]     # 合并项目 id → 它的「合并」节点


@dataclass
class CalcBasis:
    """一棵企业树在某年度的全部计算输入（两条路径共用，P8 的前提）。"""

    tree: TreeNode
    year: int
    accounts: list[str]                                   # 科目集合（有序）
    names: dict[str, str]                                 # 科目名：数据叶子试算表优先，缺失取分录行
    categories: dict[str, Any]                            # 科目类别：试算表优先，缺失按编码/名称推断
    signs: dict[str, Decimal]                             # 科目自然方向 ±1
    leaf_amounts: dict[str, dict[str, Decimal]]           # 数据叶子 node_key → {科目: 审定数}
    elim_totals: dict[str, dict[str, ElimTotals]]         # 差额节点 node_key → {科目: 原始借贷}
    attributed: dict[UUID, str] = field(default_factory=dict)  # 分录 id → 归属差额节点
    orphans: list[OrphanEntry] = field(default_factory=list)


class EntryDataError(ValueError):
    """分录明细行无法识别（格式或金额错误）：该分录按孤儿处理，列出原因，不计入。"""


# ─────────────────────────────── 纯函数：符号 / 明细行 / 归属 ───────────────────────────────


def account_sign(code: str, name: str | None = None) -> Decimal:
    """科目自然方向：借方性质 +1，贷方性质 −1（design §5.2，与单体调整分录同源）。"""
    direction, _source = resolve_account_direction(code, name or "")
    return -ONE if direction == "credit" else ONE


def to_cents(value: Any) -> Decimal:
    """金额到分（四舍五入）。库列都是 ``Numeric(20,2)``：输入先到分，派生值落库后才能逐分恒等（P7/P8）。"""
    if value is None or value == "":
        return ZERO
    d = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    if not d.is_finite():
        raise InvalidOperation(f"非有限金额：{value!r}")
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def _amount(value: Any, what: str) -> Decimal:
    try:
        return to_cents(value)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise EntryDataError(f"{what}金额无法识别（{value!r}）") from exc


def line_items(entry: Any) -> tuple[EntryLine, ...]:
    """分录明细行（金额取明细行，design §5.1）；旧数据没有明细行时退回表头作唯一一行。

    明细行不是列表（库里是 JSON，可能被写坏）⇒ ``EntryDataError``，不静默退回表头。
    """
    raw = getattr(entry, "lines", None)
    if raw is not None and not isinstance(raw, list):
        raise EntryDataError("明细行格式错误（不是列表）")
    if raw:
        out: list[EntryLine] = []
        for i, line in enumerate(raw, 1):
            if not isinstance(line, dict):
                raise EntryDataError(f"第 {i} 行明细格式错误")
            debit = _amount(line.get("debit_amount"), f"第 {i} 行借方")
            credit = _amount(line.get("credit_amount"), f"第 {i} 行贷方")
            code = str(line.get("account_code") or "").strip()
            if not code:
                if debit or credit:
                    raise EntryDataError(f"第 {i} 行有金额但没有科目")
                continue
            out.append(EntryLine(code, (line.get("account_name") or None), debit, credit))
        return tuple(out)
    code = str(getattr(entry, "account_code", "") or "").strip()
    if not code:
        return ()
    return (EntryLine(
        code,
        getattr(entry, "account_name", None) or None,
        _amount(getattr(entry, "debit_amount", None), "表头借方"),
        _amount(getattr(entry, "credit_amount", None), "表头贷方"),
    ),)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def entry_record(entry: Any) -> EntryRecord:
    """ORM 分录 → ``EntryRecord``；明细行无法识别抛 ``EntryDataError``。"""
    return EntryRecord(
        id=entry.id,
        project_id=entry.project_id,
        entry_no=entry.entry_no or "",
        entry_type=_enum_value(entry.entry_type),
        branch_entity_code=(entry.branch_entity_code or "").strip() or None,
        lines=line_items(entry),
    )


def records_from_entries(entries: Iterable[Any]) -> tuple[list[EntryRecord], list[OrphanEntry]]:
    """批量转换；明细行坏掉的分录进孤儿清单（列出原因，不静默丢弃，需求 6.4）。"""
    records: list[EntryRecord] = []
    invalid: list[OrphanEntry] = []
    for e in entries:
        try:
            records.append(entry_record(e))
        except EntryDataError as err:
            invalid.append(OrphanEntry(
                e.id, e.entry_no or "", e.project_id,
                (e.branch_entity_code or "").strip() or None, f"明细行无法识别：{err}",
            ))
    return records, invalid


def _entry_sort_key(entry: EntryRecord) -> tuple[str, str, str]:
    return (str(entry.project_id), entry.entry_no, str(entry.id))


def _orphan_sort_key(orphan: OrphanEntry) -> tuple[str, str, str]:
    return (str(orphan.project_id), orphan.entry_no, str(orphan.entry_id))


def index_tree(tree: TreeNode) -> TreeIndex:
    nodes: dict[str, TreeNode] = {}
    consol: dict[UUID, TreeNode] = {}
    for n in iter_nodes(tree):
        nodes.setdefault(n.node_key, n)
        if n.role == ROLE_CONSOL and n.project_id is not None:
            consol.setdefault(n.project_id, n)
    return TreeIndex(nodes=nodes, consol_by_project=consol)


def data_leaves(root: TreeNode, *, include_root: bool = True) -> list[TreeNode]:
    """数据叶子（子公司、分公司、本部、无分公司的母公司），先序。"""
    return [
        n for n in iter_nodes(root)
        if n.kind == KIND_DATA and not n.children and (include_root or n is not root)
    ]


def attribute_entry(entry: EntryRecord, index: TreeIndex) -> tuple[str | None, str | None]:
    """分录归属的差额节点（design §5.3 唯一真源）。返回 ``(node_key, 孤儿原因)``，二者恰一个非空。"""
    host = index.consol_by_project.get(entry.project_id)
    if host is None:
        return None, "分录所在项目不是本企业树中的合并项目"
    code = (entry.branch_entity_code or "").strip()
    if not code:
        key = make_node_key(host.company_code, ROLE_CONSOL_ELIM)
        if key in index.nodes:
            return key, None
        return None, f"「{host.display_name or host.company_name}」没有合并差额节点"
    key = make_node_key(code, ROLE_BRANCH_ELIM)
    node = index.nodes.get(key)
    if node is None:
        return None, f"企业 {code} 在本企业树中没有母分差额节点（该企业没有分公司，或不在本树中）"
    if node.host_project_id != entry.project_id:
        owner = index.consol_by_project.get(node.host_project_id) if node.host_project_id else None
        where = f"「{owner.company_name}」的合并项目" if owner is not None else "其他合并项目"
        return None, f"「{node.company_name}」的母分差额由{where}承载，应到该合并项目录入"
    return key, None


def attribute_entries(
    entries: Iterable[EntryRecord],
    index: TreeIndex,
    invalid_entries: Iterable[OrphanEntry] = (),
) -> tuple[list[tuple[EntryRecord, str]], list[OrphanEntry]]:
    """逐笔归属（确定性顺序）：返回 ``([(分录, 差额节点键)], 孤儿清单)``。

    计算口径（``build_calc_basis``）与企业树诊断（``load_orphan_entries``）共用这一处，
    所以「重算里没计入的分录」与「树上提示未归属的分录」恒为同一批（需求 6.4）。
    """
    attributed: list[tuple[EntryRecord, str]] = []
    orphans: list[OrphanEntry] = list(invalid_entries)
    for entry in sorted(entries, key=_entry_sort_key):
        key, reason = attribute_entry(entry, index)
        if key is None:
            orphans.append(OrphanEntry(
                entry.id, entry.entry_no, entry.project_id, entry.branch_entity_code, reason or "",
            ))
        else:
            attributed.append((entry, key))
    orphans.sort(key=_orphan_sort_key)
    return attributed, orphans


def suggest_branch_entity(tree: TreeNode, host_project_id: UUID, company_codes: Iterable[str]) -> str | None:
    """自动生成草稿的归属预填（任务 8.4）：交易各方数据叶子的最近公共祖先向上找第一个
    「由本项目承载母分差额」的汇总节点 ⇒ 返回该企业代码（母分差额）；否则 None（本项目合并差额）。

    只是草稿默认值 —— 金额计算只认分录上显式保存的 ``branch_entity_code``（ADR-CTREE-003），
    审批前由审计师确认。任一方不在树中 ⇒ None。
    """
    parent_of: dict[int, TreeNode | None] = {id(tree): None}
    leaf_of: dict[str, TreeNode] = {}
    for n in iter_nodes(tree):
        for c in n.children:
            parent_of[id(c)] = n
        if n.kind == KIND_DATA and not n.children:
            leaf_of.setdefault(n.company_code, n)

    def chain(node: TreeNode) -> list[TreeNode]:
        out: list[TreeNode] = []
        cur: TreeNode | None = node
        while cur is not None:
            out.append(cur)
            cur = parent_of.get(id(cur))
        return out

    codes = sorted({c for c in company_codes if c})
    if not codes or any(c not in leaf_of for c in codes):
        return None
    common = chain(leaf_of[codes[0]])
    for code in codes[1:]:
        ids = {id(n) for n in chain(leaf_of[code])}
        common = [n for n in common if id(n) in ids]
    # 自下而上。母分差额只出现在「本企业数据」汇总节点下；合并节点的直接子节点只有合并差额、母公司与成员，
    # 且合并节点之上只有合并节点 ⇒ 公共祖先一旦越过合并节点就不会再命中，天然不跨合并边界预填。
    for node in common:
        for child in node.children:
            if child.role == ROLE_BRANCH_ELIM and child.host_project_id == host_project_id:
                return child.company_code
    return None


def entity_kinds(root: TreeNode) -> dict[str, str]:
    """企业代码 → 在本树中的企业类型：``parent``（根企业）/ ``subsidiary`` / ``branch``。

    先序遍历时企业的放置节点（合并 / 子公司 / 分公司）先于它的「母公司 / 本部」数据节点，
    所以本部、母公司数据节点沿用所属企业的类型（分公司的本部仍是分公司）。
    """
    kinds: dict[str, str] = {}
    for n in iter_nodes(root):
        if n.company_code in kinds:
            continue
        if n is root or n.company_code == root.company_code:
            kinds[n.company_code] = "parent"
        elif n.role in ("branch", "subsidiary"):
            kinds[n.company_code] = n.role
        elif n.role == ROLE_CONSOL:
            kinds[n.company_code] = "subsidiary"  # 只有子公司类成员才会展开成合并节点
    return kinds


# ─────────────────────────────── 纯函数：口径装配 ───────────────────────────────


def _canonical_tb_rows(leaves: list[TreeNode], tb_rows: Iterable[TbRow]) -> list[tuple[TreeNode, TbRow]]:
    """数据叶子试算表行的确定顺序（树序 × 科目码）；单体项目只归它首次出现的叶子（P2）。

    科目名、类别「试算表优先、按此顺序取第一个非空值」：计算口径与可选科目清单共用这一顺序，
    同一科目在两处显示的名称与方向一致。
    """
    leaf_of_project: dict[UUID, str] = {}
    for leaf in leaves:
        if leaf.project_id is not None:
            leaf_of_project.setdefault(leaf.project_id, leaf.node_key)
    rows_by_project: dict[UUID, list[TbRow]] = {}
    for row in tb_rows:
        if row.project_id in leaf_of_project:
            rows_by_project.setdefault(row.project_id, []).append(row)
    ordered: list[tuple[TreeNode, TbRow]] = []
    for leaf in leaves:
        if leaf.project_id is None or leaf_of_project.get(leaf.project_id) != leaf.node_key:
            continue
        for row in sorted(rows_by_project.get(leaf.project_id, []), key=lambda r: r.account_code or ""):
            ordered.append((leaf, row))
    return ordered


def build_calc_basis(
    tree: TreeNode,
    year: int,
    tb_rows: Iterable[TbRow],
    entries: Iterable[EntryRecord],
    invalid_entries: Iterable[OrphanEntry] = (),
) -> CalcBasis:
    """把树、数据叶子试算表与已审批分录装配成计算口径（纯函数，与输入顺序无关）。"""
    from app.services.account_chart_service import _infer_category

    index = index_tree(tree)
    leaves = data_leaves(tree)
    accounts: set[str] = set()
    names: dict[str, str] = {}
    categories: dict[str, Any] = {}
    leaf_amounts: dict[str, dict[str, Decimal]] = {leaf.node_key: {} for leaf in leaves}
    for leaf, row in _canonical_tb_rows(leaves, tb_rows):
        code = (row.account_code or "").strip()
        if not code:
            continue
        accounts.add(code)
        bucket = leaf_amounts[leaf.node_key]
        bucket[code] = bucket.get(code, ZERO) + to_cents(row.audited_amount)
        if row.account_name and code not in names:
            names[code] = row.account_name
        if row.account_category is not None and code not in categories:
            categories[code] = row.account_category

    elim_totals: dict[str, dict[str, ElimTotals]] = {}
    attributed: dict[UUID, str] = {}
    pairs, orphans = attribute_entries(entries, index, invalid_entries)
    for entry, key in pairs:
        attributed[entry.id] = key
        node_bucket = elim_totals.setdefault(key, {})
        for line in entry.lines:
            node_bucket.setdefault(line.account_code, ElimTotals()).add(entry.entry_type, line.debit, line.credit)
            accounts.add(line.account_code)
            if line.account_name and line.account_code not in names:
                names[line.account_code] = line.account_name

    ordered = sorted(accounts)
    for code in ordered:
        if code not in categories:
            categories[code] = _infer_category(code, names.get(code, ""))
    return CalcBasis(
        tree=tree,
        year=year,
        accounts=ordered,
        names=names,
        categories=categories,
        signs={code: account_sign(code, names.get(code)) for code in ordered},
        leaf_amounts=leaf_amounts,
        elim_totals=elim_totals,
        attributed=attributed,
        orphans=orphans,
    )


# ─────────────────────────────── 纯函数：节点金额 / 试算金额 ───────────────────────────────


def aggregate_leaf_amounts(
    company_amounts: Iterable[tuple[dict, dict[str, Decimal]]],
) -> tuple[dict[str, Decimal], dict[str, list[dict]]]:
    """个别数汇总 + 溯源（B1 核心，合并试算唯一实现）。

    ``company_amounts`` = ``[(节点元信息, {科目: 审定数}), ...]``；元信息至少含 ``company_code`` /
    ``company_name``，其余键（``node_key`` / ``role`` …）原样带进溯源行。
    金额 0 不写溯源行；``acc[a]`` 恒等于 ``Σ prov[a][*].amount``（P2），全程 Decimal（P7）。
    """
    acc: dict[str, Decimal] = {}
    prov: dict[str, list[dict]] = {}
    for meta, amounts in company_amounts:
        extra = {k: v for k, v in meta.items() if k not in ("company_code", "company_name")}
        for code, amount in amounts.items():
            if amount == ZERO:
                continue
            acc[code] = acc.get(code, ZERO) + amount
            prov.setdefault(code, []).append({
                "company_code": meta.get("company_code"),
                "company_name": meta.get("company_name"),
                "amount": str(amount),
                **extra,
            })
    return acc, prov


def elim_net(basis: CalcBasis, node_key: str, account: str) -> tuple[Decimal, Decimal]:
    """差额节点某科目按自然方向归一后的（调整净额, 抵销净额）。"""
    totals = basis.elim_totals.get(node_key, {}).get(account)
    if totals is None:
        return ZERO, ZERO
    sign = basis.signs.get(account, ONE)
    return (
        sign * (totals.adj_debit - totals.adj_credit),
        sign * (totals.elim_debit - totals.elim_credit),
    )


# ─────────────── 报表行级度量（spec consol-elimination-single-source-push §4.1） ───────────────

MEASURE_INDIVIDUAL = "individual"        # 个别数汇总（审定汇总）
MEASURE_ADJUSTMENT = "adjustment"        # 调整净额（「其他调整」类分录）
MEASURE_ELIM_EQUITY = "elim_equity"      # 权益抵销净额
MEASURE_ELIM_TRADE = "elim_trade"        # 往来交易抵销净额（内部交易 + 内部往来 + 未实现利润）
MEASURE_CONSOLIDATED = "consolidated"    # 合并数
MEASURES = (
    MEASURE_INDIVIDUAL, MEASURE_ADJUSTMENT, MEASURE_ELIM_EQUITY, MEASURE_ELIM_TRADE, MEASURE_CONSOLIDATED,
)
EQUITY_ENTRY_TYPE = "equity"


def elim_measures(basis: CalcBasis, node_key: str, account: str) -> tuple[Decimal, Decimal, Decimal]:
    """差额节点某科目按自然方向归一后的（调整, 权益抵销, 往来交易抵销）。

    往来交易抵销 = 除「其他调整」「权益抵销」外的全部类型，所以 ``权益 + 往来交易 = elim_net`` 的抵销净额
    恒成立（``ElimTotals.add`` 保证分桶之和 = 合计列），P2 不依赖分录类型枚举是否再扩充。
    """
    totals = basis.elim_totals.get(node_key, {}).get(account)
    if totals is None:
        return ZERO, ZERO, ZERO
    sign = basis.signs.get(account, ONE)
    equity = trade = ZERO
    for entry_type, (debit, credit) in totals.by_type.items():
        if entry_type == ADJUSTMENT_ENTRY_TYPE:
            continue
        if entry_type == EQUITY_ENTRY_TYPE:
            equity += debit - credit
        else:
            trade += debit - credit
    return sign * (totals.adj_debit - totals.adj_credit), sign * equity, sign * trade


def node_measures(basis: CalcBasis) -> dict[str, dict[str, dict[str, Decimal]]]:
    """每个节点 × 度量 × 科目的金额（稀疏：只存非零），供报表行级求值（design §4.1）。

    数据节点：个别数 = 合并数 = 单户审定数；差额节点：调整 / 权益抵销 / 往来交易抵销，合并数 = 三者之和；
    汇总节点：各度量 = Σ 直接子节点同度量。于是逐节点逐科目
    ``个别数 + 调整 + 权益抵销 + 往来交易抵销 = 合并数``（P2），且合并数与 ``node_values`` 的差额表合并数相同。
    """
    out: dict[str, dict[str, dict[str, Decimal]]] = {}

    def put(bucket: dict[str, Decimal], account: str, amount: Decimal) -> None:
        total = bucket.get(account, ZERO) + amount
        if total:
            bucket[account] = total
        else:
            bucket.pop(account, None)

    def visit(node: TreeNode) -> dict[str, dict[str, Decimal]]:
        measures: dict[str, dict[str, Decimal]] = {m: {} for m in MEASURES}
        if node.kind == KIND_ELIM:
            for account in sorted(basis.elim_totals.get(node.node_key, {})):
                adj, equity, trade = elim_measures(basis, node.node_key, account)
                put(measures[MEASURE_ADJUSTMENT], account, adj)
                put(measures[MEASURE_ELIM_EQUITY], account, equity)
                put(measures[MEASURE_ELIM_TRADE], account, trade)
                put(measures[MEASURE_CONSOLIDATED], account, adj + equity + trade)
        elif node.children:
            for child in node.children:
                for m, amounts in visit(child).items():
                    for account, amount in amounts.items():
                        put(measures[m], account, amount)
        else:
            for account, amount in basis.leaf_amounts.get(node.node_key, {}).items():
                put(measures[MEASURE_INDIVIDUAL], account, amount)
                put(measures[MEASURE_CONSOLIDATED], account, amount)
        out[node.node_key] = measures
        return measures

    visit(basis.tree)
    return out


def node_values(basis: CalcBasis) -> dict[str, dict[str, NodeAmounts]]:
    """后序计算每个节点逐科目的差额表金额（design §5.1）。

    data：``children_amount_sum`` = 单体审定数，差额 0；elim：借贷列取原始录入方向合计，
    ``net_difference`` = 归一后调整 + 抵销，``consolidated_amount`` = ``net_difference``；
    aggregate：``children_amount_sum`` = Σ 直接子节点合并数，自身调整/抵销列恒 0（P7）。
    """
    out: dict[str, dict[str, NodeAmounts]] = {}
    accounts = basis.accounts

    def visit(node: TreeNode) -> dict[str, NodeAmounts]:
        if node.kind == KIND_ELIM:
            totals = basis.elim_totals.get(node.node_key, {})
            values: dict[str, NodeAmounts] = {}
            for a in accounts:
                t = totals.get(a)
                if t is None:
                    values[a] = NodeAmounts()
                    continue
                adj, elim = elim_net(basis, node.node_key, a)
                net = adj + elim
                values[a] = NodeAmounts(
                    adjustment_debit=t.adj_debit, adjustment_credit=t.adj_credit,
                    elimination_debit=t.elim_debit, elimination_credit=t.elim_credit,
                    net_difference=net, consolidated_amount=net,
                )
        elif node.children:
            kids = [visit(c) for c in node.children]
            values = {}
            for a in accounts:
                s = sum((k[a].consolidated_amount for k in kids), ZERO)
                values[a] = NodeAmounts(children_amount_sum=s, consolidated_amount=s)
        else:
            own = basis.leaf_amounts.get(node.node_key, {})
            values = {
                a: NodeAmounts(children_amount_sum=own.get(a, ZERO), consolidated_amount=own.get(a, ZERO))
                for a in accounts
            }
        out[node.node_key] = values
        return values

    visit(basis.tree)
    return out


def worksheet_rows(basis: CalcBasis) -> list[tuple[str, str, NodeAmounts]]:
    """差额表全部行（节点 × 科目，节点按树序、科目按编码）。"""
    values = node_values(basis)
    return [
        (n.node_key, a, values[n.node_key][a])
        for n in iter_nodes(basis.tree)
        for a in basis.accounts
    ]


def leaf_meta(leaf: TreeNode, entity_kind: str) -> dict:
    """数据叶子的溯源元信息（需求 5.9：标注每行来自哪个节点）。"""
    return {
        "company_code": leaf.company_code,
        "company_name": leaf.company_name,
        "node_key": leaf.node_key,
        "role": leaf.role,
        "entity_kind": entity_kind,
        "display_name": leaf.display_name or leaf.company_name,
        "source_project_id": str(leaf.project_id) if leaf.project_id else None,
    }


def trial_amounts(basis: CalcBasis) -> dict[str, TrialAmounts]:
    """合并试算逐科目：个别数汇总（全部数据叶子）+ 调整 + 抵销 = 合并数（需求 5.9 / P8）。

    溯源 ``by_company`` 按数据叶子逐行记录（金额 0 不写），合计恒等于个别数汇总。
    """
    kinds = entity_kinds(basis.tree)
    acc, prov = aggregate_leaf_amounts(
        (leaf_meta(leaf, kinds.get(leaf.company_code, "subsidiary")), basis.leaf_amounts.get(leaf.node_key, {}))
        for leaf in data_leaves(basis.tree)
    )
    elim_keys = [n.node_key for n in iter_nodes(basis.tree) if n.kind == KIND_ELIM]
    out: dict[str, TrialAmounts] = {}
    for a in basis.accounts:
        individual = acc.get(a, ZERO)
        adjustment = elimination = ZERO
        for key in elim_keys:
            adj, elim = elim_net(basis, key, a)
            adjustment += adj
            elimination += elim
        out[a] = TrialAmounts(
            individual_sum=individual,
            consol_adjustment=adjustment,
            consol_elimination=elimination,
            consol_amount=individual + adjustment + elimination,
            by_company=prov.get(a, []),
        )
    return out


_STATUS_TEXT = {"draft": "草稿", "pending_review": "待审批", "rejected": "已驳回"}


def orphan_diagnostics(
    orphans: Iterable[OrphanEntry], statuses: dict[UUID, str] | None = None,
) -> list[Diagnostic]:
    """未归属分录 → 企业树诊断（需求 6.4 / 9.4）。

    已审批的 ⇒「未计入合并」；其余状态（``statuses`` 给出）⇒ 提示先改归属或删除，否则提交审批会被拦下。
    没给状态的按已审批处理（重算结果只含已审批分录）。
    """
    out: list[Diagnostic] = []
    for o in orphans:
        status = (statuses or {}).get(o.entry_id, "approved")
        label = o.entry_no or o.entry_id
        if status == "approved":
            message = f"分录 {label} 未计入合并：{o.reason}"
        else:
            message = (
                f"分录 {label}（{_STATUS_TEXT.get(status, status)}）找不到归属节点：{o.reason}；"
                "请修改归属或删除后再提交审批"
            )
        out.append(Diagnostic("orphan_entries", message, company_code=o.branch_entity_code))
    return out


def account_options(tree: TreeNode, tb_rows: Iterable[TbRow], entries: Iterable[EntryRecord]) -> list[dict]:
    """差额录入可选科目（需求 9.3）：数据叶子试算表科目 ∪ 本树分录明细行科目（含未审批分录）。

    名称、类别、方向与计算口径同一取法（试算表按树序优先、缺失取分录行；方向即 ``account_sign``），
    所以面板里看到的「借方性质 / 贷方性质」就是金额归一用的方向。按科目码排序。
    """
    from app.services.account_chart_service import _infer_category

    names: dict[str, str] = {}
    categories: dict[str, Any] = {}
    sources: dict[str, set[str]] = {}
    for _leaf, row in _canonical_tb_rows(data_leaves(tree), tb_rows):
        code = (row.account_code or "").strip()
        if not code:
            continue
        sources.setdefault(code, set()).add("trial_balance")
        if row.account_name and code not in names:
            names[code] = row.account_name
        if row.account_category is not None and code not in categories:
            categories[code] = row.account_category
    for entry in sorted(entries, key=_entry_sort_key):
        for line in entry.lines:
            sources.setdefault(line.account_code, set()).add("entries")
            if line.account_name and line.account_code not in names:
                names[line.account_code] = line.account_name

    options: list[dict] = []
    for code in sorted(sources):
        name = names.get(code)
        category = categories.get(code)
        if category is None:
            category = _infer_category(code, name or "")
        options.append({
            "account_code": code,
            "account_name": name,
            "account_category": _enum_value(category) or None,
            "direction": "credit" if account_sign(code, name) < ZERO else "debit",
            "in_trial_balance": "trial_balance" in sources[code],
            "in_entries": "entries" in sources[code],
        })
    return options


# ─────────────────────────────── 薄装载（连库） ───────────────────────────────


async def load_tb_rows(db: AsyncSession, project_ids: Iterable[UUID], year: int) -> list[TbRow]:
    """数据叶子单体项目的审定数（``audited_amount``，未删，按标准科目码）。"""
    ids = sorted(set(project_ids), key=str)
    if not ids:
        return []
    result = await db.execute(
        sa.select(
            TrialBalance.project_id,
            TrialBalance.standard_account_code,
            TrialBalance.account_name,
            TrialBalance.account_category,
            TrialBalance.audited_amount,
        ).where(
            TrialBalance.project_id.in_(ids),
            TrialBalance.year == year,
            TrialBalance.is_deleted == sa.false(),
        )
    )
    return [TbRow(r[0], r[1], r[2], r[3], r[4]) for r in result.all()]


async def load_tree_entries(
    db: AsyncSession, tree: TreeNode, year: int, *, approved_only: bool = True,
) -> list[EliminationEntry]:
    """树内全部合并节点的合并项目在该年度的分录（未删；默认只取已审批，需求 6.3）。"""
    consol_ids = sorted(index_tree(tree).consol_by_project, key=str)
    if not consol_ids:
        return []
    stmt = sa.select(EliminationEntry).where(
        EliminationEntry.project_id.in_(consol_ids),
        EliminationEntry.year == year,
        EliminationEntry.is_deleted == sa.false(),
    )
    if approved_only:
        stmt = stmt.where(EliminationEntry.review_status == ReviewStatusEnum.approved)
    result = await db.execute(stmt.order_by(EliminationEntry.entry_no, EliminationEntry.id))
    return list(result.scalars().all())


async def load_orphan_diagnostics(db: AsyncSession, tree: TreeNode, year: int) -> list[Diagnostic]:
    """本树全部未删分录中找不到归属差额节点的 ⇒ 企业树诊断（需求 6.4）。

    与重算同一归属函数；已审批的就是重算里没计入的那批。草稿等未审批分录也列出 —— 它们的归属节点
    已不在树上，差额面板里找不到，不提示就只能等提交审批时被拦。
    """
    entries = await load_tree_entries(db, tree, year, approved_only=False)
    statuses = {e.id: _enum_value(e.review_status) for e in entries}
    records, invalid = records_from_entries(entries)
    orphans = attribute_entries(records, index_tree(tree), invalid)[1]
    return orphan_diagnostics(orphans, statuses)


async def load_account_options(db: AsyncSession, tree: TreeNode, year: int) -> list[dict]:
    """差额录入可选科目：数据叶子试算表 + 本树全部未删分录（明细行无法识别的分录不提供科目）。"""
    leaves = data_leaves(tree)
    tb_rows = await load_tb_rows(db, (n.project_id for n in leaves if n.project_id is not None), year)
    records, _invalid = records_from_entries(await load_tree_entries(db, tree, year, approved_only=False))
    return account_options(tree, tb_rows, records)


class NodeNotFoundError(LookupError):
    """企业树中没有该 node_key 的节点。"""


def node_amount_rows(basis: CalcBasis, node_key: str) -> list[dict]:
    """某节点逐科目金额（与差额表同一口径 ``node_values``），只列有非零金额的科目，按科目码排序。"""
    values = node_values(basis).get(node_key)
    if values is None:
        raise NodeNotFoundError(node_key)
    rows: list[dict] = []
    for code in basis.accounts:
        amounts = values[code]
        cols = amounts.columns()
        if not any(cols.values()):
            continue
        rows.append({
            "account_code": code,
            "account_name": basis.names.get(code),
            "direction": "credit" if basis.signs.get(code, ONE) < ZERO else "debit",
            **{k: str(v) for k, v in cols.items()},
        })
    return rows


async def load_node_amounts(
    db: AsyncSession, project_id: UUID, node_key: str, year: int | None = None,
) -> dict | None:
    """实时按计算口径求某节点金额（不读差额表存量，也不写库）。

    差额分录面板用（需求 9.3）：审批后差额表由事件异步重算，面板直接求值，看到的就是重算会写入的数。
    项目不存在返回 None；节点不在本项目企业树中抛 ``NodeNotFoundError``。
    """
    from app.services.consol_group_tree import build_group_tree

    result = await build_group_tree(db, project_id)
    if result is None or result.root is None:
        return None
    tree = result.root
    node = next((n for n in iter_nodes(tree) if n.node_key == node_key), None)
    if node is None:
        raise NodeNotFoundError(node_key)
    effective_year = year if year is not None else result.year
    payload = {
        "year": effective_year,
        "node_key": node.node_key,
        "display_name": node.display_name or node.company_name,
        "kind": node.kind,
        "rows": [],
    }
    if effective_year is None:
        return payload
    basis = await load_calc_basis(db, project_id, effective_year, tree=tree)
    assert basis is not None
    payload["rows"] = node_amount_rows(basis, node_key)
    return payload


async def load_calc_basis(
    db: AsyncSession, project_id: UUID, year: int, *, tree: TreeNode | None = None,
) -> CalcBasis | None:
    """以合并项目为根装载计算口径；项目不存在返回 None。树可由调用方传入以免重复推导。"""
    if tree is None:
        tree = await build_tree(db, project_id)
    if tree is None:
        return None
    leaves = data_leaves(tree)
    tb_rows = await load_tb_rows(db, (n.project_id for n in leaves if n.project_id is not None), year)
    records, invalid = records_from_entries(await load_tree_entries(db, tree, year))
    return build_calc_basis(tree, year, tb_rows, records, invalid)


__all__ = [
    "ADJUSTMENT_ENTRY_TYPE",
    "EQUITY_ENTRY_TYPE",
    "MEASURES",
    "MEASURE_ADJUSTMENT",
    "MEASURE_CONSOLIDATED",
    "MEASURE_ELIM_EQUITY",
    "MEASURE_ELIM_TRADE",
    "MEASURE_INDIVIDUAL",
    "CalcBasis",
    "ElimTotals",
    "EntryDataError",
    "EntryLine",
    "EntryRecord",
    "NodeAmounts",
    "OrphanEntry",
    "TbRow",
    "TreeIndex",
    "TrialAmounts",
    "account_options",
    "account_sign",
    "aggregate_leaf_amounts",
    "attribute_entries",
    "attribute_entry",
    "build_calc_basis",
    "data_leaves",
    "elim_measures",
    "elim_net",
    "entity_kinds",
    "entry_record",
    "index_tree",
    "leaf_meta",
    "line_items",
    "load_account_options",
    "NodeNotFoundError",
    "load_calc_basis",
    "load_node_amounts",
    "load_orphan_diagnostics",
    "load_tb_rows",
    "node_amount_rows",
    "load_tree_entries",
    "node_measures",
    "node_values",
    "orphan_diagnostics",
    "records_from_entries",
    "suggest_branch_entity",
    "to_cents",
    "trial_amounts",
    "worksheet_rows",
]
