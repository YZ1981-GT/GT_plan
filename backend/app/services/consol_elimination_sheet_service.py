"""合并抵消分录明细表后端（spec consol-elimination-single-source-push 任务 6，design §九，ADR-CSP-001）。

分录唯一存储是 ``elimination_entries``；明细表只读它、写它，不再落 JSON：

- ``tree_lines``：本企业树内全部未删分录展开为明细行（含下级合并项目承载的分录），带归属差额节点、
  只读判定（分录不在当前合并项目 ⇒ 只读，给出承载项目）、是否计入（已审批且找到归属节点）与孤儿原因。
  归属与计算口径同一函数（``attribute_entries``）⇒「计入」的恰是重算里计入的那批。
- ``generate_from_worksheet``：合并工作底稿（模拟权益法 / 内部往来 / 内部交易）算出的来源分组 ⇒ 草稿分录。
  逐组：科目映射（``SubjectMapper``）→ 借贷平衡 → 按 ``(origin, origin_key)`` 更新或新建；
  草稿 / 已驳回随来源更新，待审批 / 已审批不改只报告；请求声明负责的来源里不再产出的来源键 ⇒ 草稿软删。
- 旧版明细表（``consol_worksheet_data['elimination']`` 的自定义行）：按录入顺序累计借贷，平衡处切成一笔，
  ``origin='legacy_sheet'``，走同一个生成函数。

科目映射只用确定规则，不猜：本集团科目（数据叶子试算表 + 已有分录）名称优先，其次标准科目表名称，
另有少量写明依据的别名（``SUBJECT_ALIASES``）；同名多个科目时优先落在本项目合并报表公式取数范围内的那个。
映射不到 ⇒ 该组不生成、逐行给原因，绝不以名称代替编码入账（需求 2.3）；映射到的科目不在报表取数范围内 ⇒
照常生成但给警告（合并试算按科目计入，合并报表看不到这笔金额），明细行也标出 ``in_report``，不静默。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation_models import EliminationEntry, EliminationEntryType, ReviewStatusEnum
from app.services.consol_calc_basis import (
    ZERO,
    EntryDataError,
    account_options,
    attribute_entries,
    data_leaves,
    index_tree,
    line_items,
    load_tb_rows,
    load_tree_entries,
    records_from_entries,
    suggest_branch_entity,
    to_cents,
)
from app.services.consol_group_tree import KIND_ELIM, ROLE_CONSOL, ROLE_CONSOL_ELIM
from app.services.consol_report_values import ReportRow, analyze_formula, load_report_rows, resolve_consol_standard
from app.services.consol_tree_service import TreeNode, iter_nodes

ORIGIN_EQUITY_SIM = "ws_equity_sim"
ORIGIN_INTERNAL_ARAP = "ws_internal_arap"
ORIGIN_INTERNAL_TRADE = "ws_internal_trade"
ORIGIN_LEGACY = "legacy_sheet"
WORKSHEET_ORIGINS = (ORIGIN_EQUITY_SIM, ORIGIN_INTERNAL_ARAP, ORIGIN_INTERNAL_TRADE)
ORIGIN_LABELS: dict[str, str] = {
    ORIGIN_EQUITY_SIM: "模拟权益法",
    ORIGIN_INTERNAL_ARAP: "内部往来",
    ORIGIN_INTERNAL_TRADE: "内部交易",
    ORIGIN_LEGACY: "旧版明细表",
}
ORIGINS = tuple(ORIGIN_LABELS)
# 各来源可生成的分录类型（首个为默认）：模拟权益法也可按「调整」列示；未实现利润属内部交易；旧版行类型未知
ORIGIN_ENTRY_TYPES: dict[str, tuple[str, ...]] = {
    ORIGIN_EQUITY_SIM: ("equity", "other"),
    ORIGIN_INTERNAL_ARAP: ("internal_ar_ap",),
    ORIGIN_INTERNAL_TRADE: ("internal_trade", "unrealized_profit"),
    ORIGIN_LEGACY: ("other", "equity", "internal_ar_ap", "internal_trade", "unrealized_profit"),
}
DEFAULT_DESCRIPTIONS = {
    ORIGIN_EQUITY_SIM: "模拟权益法自动生成",
    ORIGIN_INTERNAL_ARAP: "内部往来抵销自动生成",
    ORIGIN_INTERNAL_TRADE: "内部交易抵销自动生成",
    ORIGIN_LEGACY: "旧版明细表转入",
}
ENTRY_TYPE_LABELS = {
    "equity": "权益抵销", "internal_ar_ap": "内部往来抵销", "internal_trade": "内部交易抵销",
    "unrealized_profit": "未实现利润抵销", "other": "其他调整",
}
STATUS_LABELS = {"draft": "草稿", "pending_review": "待审批", "approved": "已审批", "rejected": "已驳回"}
STANDARD_LABELS = {"soe_consolidated": "国企版合并报表", "listed_consolidated": "上市版合并报表"}
EDITABLE_STATUSES = frozenset({ReviewStatusEnum.draft, ReviewStatusEnum.rejected})
_REJECTION_MARK = "\n驳回原因:"   # elimination_service 驳回时追加到说明末尾的标记
LEGACY_SHEET_KEY = "elimination"


class SheetError(ValueError):
    """请求与企业树 / 来源声明不符；``status`` 供路由转 400 / 404。"""

    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


def _enum(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


# ─────────────────────────────── 科目名称规范化 ───────────────────────────────

_SPACES = re.compile(r"[\s\u3000]+")
_MARKERS = re.compile(r"^(?:减：|加：|其中：|减:|加:|其中:|[△▲*＊#＃])+")
_SEPARATORS = re.compile(r"[-—－_/·・]+")
_ALT_NAME = re.compile(r"^(.+?)[（(]或(.+?)[）)]$")      # 「实收资本（或股本）」
_EQUITY_ITEM = re.compile(r"^\d+(?:-\d+)+")             # 权益变动表项目：「2-3股份支付…」「4-1-1法定公积金」
_SECTION_LABEL = re.compile(r"^[（(][一二三四五六七八九十]+[）)]")  # 权益变动表分节：「（四）利润分配」

# 合并报表列报项目：科目表里没有对应科目，报表该行也不从科目取数
REPORT_ONLY_SUBJECTS = frozenset({"少数股东权益", "少数股权权益", "少数股东损益", "少数股权损益"})

# 工作底稿按报表口径起的名称 → 会计科目名称（按序尝试；只收有确定依据的，其余一律不猜）
SUBJECT_ALIASES: dict[str, tuple[str, ...]] = {
    # 利润表「营业收入 / 营业成本」取 6001~6099 / 6401~6499；内部销售记在主营业务收入 / 成本
    "营业收入": ("主营业务收入",),
    "营业成本": ("主营业务成本",),
    # 合并口径只有期末审定数：对年初未分配利润的调整就是对未分配利润余额的调整
    "年初未分配利润": ("未分配利润", "利润分配"),
    # 4 开头权益类科目表里 4104「利润分配」的期末余额即未分配利润（合并报表「未分配利润」行取 4104）
    "未分配利润": ("利润分配",),
    # 资产负债表「存货」取 1401~1499；内部交易未实现利润留在购货方的库存商品里
    "存货": ("库存商品",),
    "股本": ("实收资本",),
    "实收资本": ("股本",),
}


def normalize_name(value: Any) -> str:
    """去空白（含全角空格）与行首标记（△ ▲ * # 减： 加： 其中：）。"""
    return _MARKERS.sub("", _SPACES.sub("", str(value or "")))


def name_key(value: Any) -> str:
    """比较键：规范化后再去分隔符（「长期股权投资-损益调整」==「长期股权投资—损益调整」）。"""
    return _SEPARATORS.sub("", normalize_name(value))


def candidate_names(subject: str) -> list[tuple[str, str | None]]:
    """科目名称的候选 ``(比较键, 别名说明)``，按序：原名 → 「（或…）」拆出的名称 → 显式别名。"""
    names: list[tuple[str, str | None]] = [(subject, None)]
    alt = _ALT_NAME.match(subject)
    if alt:
        names += [(alt.group(1), None), (alt.group(2), alt.group(2))]
    for name, _via in list(names):
        names += [(alias, alias) for alias in SUBJECT_ALIASES.get(name, ())]
    out: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for name, via in names:
        key = name_key(name)
        if key and key not in seen:
            seen.add(key)
            out.append((key, via))
    return out


# ─────────────────────────────── 科目映射 ───────────────────────────────


_ROW_PREFIX = re.compile(r"^(?:[（(]\s*[0-9一二三四五六七八九十]+\s*[）)]|[一二三四五六七八九十]+[、．.]|\d+[、．.])\s*")


def clean_row_name(value: Any) -> str:
    """报表行名去掉行首序号（「一、」「（二）」「3.」）与标记（△ * 减：…），直到不再变化。"""
    text, prev = normalize_name(value), None
    while text != prev:
        prev = text
        text = _MARKERS.sub("", _ROW_PREFIX.sub("", text))
    return text


def row_name_key(value: Any) -> str:
    return name_key(clean_row_name(value))


@dataclass
class AccountPool:
    """一个科目来源（本集团科目 / 合并报表行次 / 标准科目表）：编码 → 展示名，比较键 → 编码。

    同一编码在不同子企业可能叫法不同（6001「营业收入」/「主营业务收入」）：每个名称都登记为比较键，
    展示名取第一次出现的。
    """

    label: str
    names: dict[str, str] = field(default_factory=dict)
    by_key: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def build(
        cls, label: str, items: Iterable[tuple[Any, Any]], *,
        key: Callable[[Any], str] = name_key, display: Callable[[Any], str] | None = None,
    ) -> AccountPool:
        pool = cls(label)
        for code, name in items:
            code, name = str(code or "").strip(), str(name or "").strip()
            if not code or not name or not key(name):
                continue
            pool.names.setdefault(code, display(name) if display else name)
            codes = pool.by_key.setdefault(key(name), [])
            if code not in codes:
                codes.append(code)
        return pool


REPORT_ROW_POOL_TYPES = frozenset({"balance_sheet", "income_statement"})


def report_row_accounts(rows: Iterable[ReportRow]) -> list[tuple[str, str]]:
    """资产负债表 / 利润表里「只取一个科目」的行（公式恰为一个 ``TB('码', 列)``，系数 1、无常数）⇒ (科目码, 行名)。

    工作底稿按报表项目起名（「实收资本（或股本）」「△一般风险准备」「未分配利润」）：本集团科目里没有同名科目时，
    按同名报表行取数的那个科目入账，金额就落在该行 —— 这是报表口径自己给出的对应关系，不是猜测。
    只取两张主表：减值准备表、补充资料等附表的单科目行有配错的（如「在建工程减值准备」取 1604 在建工程），不作映射依据。
    """
    out: list[tuple[str, str]] = []
    for row in rows:
        text = (row.formula or "").strip()
        if not text or row.report_type not in REPORT_ROW_POOL_TYPES:
            continue
        shape = analyze_formula(text)
        if shape.error or shape.nonlinear or shape.constant or len(shape.terms) != 1:
            continue
        term, coef = shape.terms[0]
        if term[0] == "tb" and coef == 1:
            out.append((term[1], row.row_name))
    return out


@dataclass(frozen=True)
class ReportCoverage:
    """合并报表公式直接取数的科目范围（``TB`` 前缀 / ``SUM_TB`` 区间，与 ``BasisResolver`` 同口径）。"""

    prefixes: tuple[str, ...] = ()
    ranges: tuple[tuple[str, str], ...] = ()

    @classmethod
    def from_rows(cls, rows: Iterable[ReportRow]) -> ReportCoverage:
        prefixes: set[str] = set()
        ranges: set[tuple[str, str]] = set()
        for row in rows:
            text = (row.formula or "").strip()
            if not text:
                continue
            shape = analyze_formula(text)
            if shape.error:
                continue  # 求值即留空的行不算取数
            prefixes.update(shape.tb_codes)
            ranges.update(shape.tb_ranges)
        return cls(tuple(sorted(prefixes)), tuple(sorted(ranges)))

    def covers(self, code: str) -> bool:
        return any(code.startswith(p) for p in self.prefixes) or any(
            a <= code[:len(a)] <= b for a, b in self.ranges
        )


@dataclass(frozen=True)
class MappedAccount:
    """一行来源科目的映射结果：``reason`` 非空 ⇒ 映射失败（该组不生成）；``warning`` 只提示。"""

    account_code: str | None = None
    account_name: str | None = None
    source: str | None = None       # 本集团科目 / 合并报表行次 / 标准科目表
    note: str | None = None         # 别名、父科目兜底等说明
    in_report: bool = False         # 编码落在合并报表公式取数范围内
    reason: str | None = None
    warning: str | None = None


@dataclass(frozen=True)
class _Hit:
    code: str
    name: str
    pool: str
    via: str | None = None


class SubjectMapper:
    """来源科目名称（+ 明细）→ 科目编码（design §9.2）。

    查找顺序：本集团科目 → 合并报表行次（``report_row_accounts``）→ 标准科目表，前一处有候选就不看后一处
    （本集团编码体系优先，否则抵销金额与子企业个别数落在不同编码上，合并试算逐科目抵不掉；
    报表行次先于标准科目表：标准表权益类是 3 开头，而合并报表公式按 4 开头取权益）；
    同一处多个候选 ⇒ 原名优先于别名（需求 2.3「名称精确匹配」在前），同级里落在报表取数范围内的优先
    （如标准科目表 5001 / 6001 都叫「主营业务收入」，合并报表取 6001~6099），再短码、小码优先（确定性）。
    带明细：先按「名称+明细」整体匹配（「长期股权投资」+「减值准备」⇒ 长期股权投资减值准备）→
    再找父科目下名称为明细的子科目 → 都没有用父科目并注明。
    """

    def __init__(self, pools: Sequence[AccountPool], coverage: ReportCoverage, standard_label: str):
        self.pools = tuple(pools)
        self.coverage = coverage
        self.standard_label = standard_label

    def _pick(self, candidates: list[tuple[tuple, _Hit]]) -> _Hit | None:
        return min(candidates, key=lambda c: c[0])[1] if candidates else None

    def _find(self, names: list[tuple[str, str | None]]) -> _Hit | None:
        for pool in self.pools:
            candidates = [
                ((rank, not self.coverage.covers(code), len(code), code), _Hit(code, pool.names[code], pool.label, via))
                for rank, (key, via) in enumerate(names)
                for code in pool.by_key.get(key, ())
            ]
            hit = self._pick(candidates)
            if hit is not None:
                return hit
        return None

    def _sub_account(self, parent: _Hit, detail: str) -> _Hit | None:
        """父科目下名称为明细的子科目（编码以父科目编码开头且更长）。"""
        key = name_key(detail)
        for pool in self.pools:
            candidates = [
                ((not self.coverage.covers(code), len(code), code), _Hit(code, pool.names[code], pool.label))
                for code in pool.by_key.get(key, ())
                if len(code) > len(parent.code) and code.startswith(parent.code)
            ]
            hit = self._pick(candidates)
            if hit is not None:
                return hit
        return None

    def _finish(self, hit: _Hit, *, name: str | None = None, note: str | None = None) -> MappedAccount:
        notes = [f"按「{hit.via}」匹配"] if hit.via else []
        if note:
            notes.append(note)
        in_report = self.coverage.covers(hit.code)
        warning = None if in_report else (
            f"科目 {hit.code} {hit.name} 不在{self.standard_label}任何行次的取数范围内："
            "合并试算按科目计入，合并报表看不到这笔金额"
        )
        return MappedAccount(
            hit.code, name or hit.name, hit.pool, "；".join(notes) or None, in_report, warning=warning,
        )

    def map(self, subject: Any, detail: Any = None) -> MappedAccount:
        s, d = normalize_name(subject), normalize_name(detail)
        if not s:
            return MappedAccount(reason="没有科目名称")
        if _EQUITY_ITEM.match(s) or (d and _SECTION_LABEL.match(d)):
            # 只有金额非 0 的行会走到这里（0 金额行不入账）：权益变动表列不是科目，不能替它选编码
            return MappedAccount(reason=f"「{s}」是所有者权益变动表项目，不是会计科目，请在差额节点面板按科目录入")
        if d:
            hit = self._find([(name_key(s + d), None)])
            if hit is not None:
                return self._finish(hit)
        parent = self._find(candidate_names(s))
        if parent is None:
            if s in REPORT_ONLY_SUBJECTS:
                return MappedAccount(reason=(
                    f"「{s}」是合并报表列报项目，科目表中没有对应科目（合并报表该行也不从科目取数）；"
                    "请在差额节点面板录入本集团使用的科目编码"
                ))
            return MappedAccount(reason=f"「{s}」在本集团科目、合并报表行次与标准科目表中都找不到对应科目")
        if not d:
            return self._finish(parent)
        sub = self._sub_account(parent, d)
        if sub is not None:
            return self._finish(sub)
        return self._finish(
            parent, name=f"{parent.name}-{d}", note=f"明细「{d}」没有对应子科目，按父科目 {parent.code} 入账",
        )


def build_mapper(
    tree_accounts: Iterable[tuple[Any, Any]],
    chart_entries: Iterable[dict],
    report_rows: Iterable[ReportRow],
    standard: str,
) -> SubjectMapper:
    """本集团科目 + 标准科目表 + 报表取数范围 ⇒ 映射器。

    标准科目表里 4 开头是成本类（生产成本 / 制造费用 …），而合并报表公式里 4 开头是权益类（4001 实收资本 …）
    ⇒ 不从标准科目表取 4 开头科目，免得名称落到成本类编码、再被报表当成权益取走。
    """
    report_rows = list(report_rows)
    chart = (
        (e.get("code") or e.get("account_code"), e.get("name") or e.get("account_name"))
        for e in chart_entries
        if not str(e.get("code") or e.get("account_code") or "").startswith("4")
    )
    return SubjectMapper(
        (
            AccountPool.build("本集团科目", tree_accounts),
            AccountPool.build("合并报表行次", report_row_accounts(report_rows), key=row_name_key, display=clean_row_name),
            AccountPool.build("标准科目表", chart),
        ),
        ReportCoverage.from_rows(report_rows),
        STANDARD_LABELS.get(standard, standard),
    )


async def load_mapper(db: AsyncSession, project_id: UUID, tree: TreeNode, year: int) -> tuple[SubjectMapper, str]:
    """本集团科目 = 数据叶子试算表科目 ∪ 本树已有分录科目（与差额录入科目下拉同一来源）。"""
    from app.services.account_chart_service import standard_chart_entries

    leaves = data_leaves(tree)
    tb_rows = await load_tb_rows(db, (n.project_id for n in leaves if n.project_id is not None), year)
    records, _invalid = records_from_entries(await load_tree_entries(db, tree, year, approved_only=False))
    # 已有分录里的科目也算本集团科目：审计师手工录过的合并专用科目（如商誉、少数股东权益）后续可直接生成
    options = account_options(tree, tb_rows, records)
    standard = await resolve_consol_standard(db, project_id)
    mapper = build_mapper(
        ((o["account_code"], o["account_name"]) for o in options),
        standard_chart_entries(),
        await load_report_rows(db, standard),
        standard,
    )
    return mapper, standard


# ─────────────────────────────── 来源分组 → 计划（纯函数） ───────────────────────────────

_DIRECTIONS = {"借": "debit", "debit": "debit", "贷": "credit", "credit": "credit"}


@dataclass
class SourceLine:
    subject: str
    detail: str | None
    direction: str
    amount: Any


@dataclass
class SourceGroup:
    """与 ``WorksheetSourceGroup`` 同形（旧版明细表转入在服务端构造它）。"""

    origin: str
    origin_key: str
    description: str | None
    lines: list[SourceLine]
    entry_type: str | None = None
    related_company_codes: list[str] = field(default_factory=list)


@dataclass
class PlannedLine:
    index: int                     # 来源分组内行号（1 起；零金额行跳过但保留序号）
    subject: str
    detail: str
    direction: str | None          # debit / credit（负金额已换向）
    amount: Decimal | None         # 正数，到分
    mapped: MappedAccount = field(default_factory=MappedAccount)
    reason: str | None = None

    @property
    def debit(self) -> Decimal:
        return self.amount if self.direction == "debit" and self.amount is not None else ZERO

    @property
    def credit(self) -> Decimal:
        return self.amount if self.direction == "credit" and self.amount is not None else ZERO

    def label(self) -> str:
        text = f"{self.subject}-{self.detail}" if self.detail else self.subject
        return text or "（无科目）"

    def to_dict(self) -> dict:
        m = self.mapped
        return {
            "index": self.index,
            "subject": self.subject,
            "detail": self.detail or None,
            "direction": self.direction,
            "amount": None if self.amount is None else str(self.amount),
            "account_code": m.account_code,
            "account_name": m.account_name,
            "source": m.source,
            "note": m.note,
            "in_report": m.in_report,
            "warning": m.warning,
            "reason": self.reason,
        }


def _related_list(value: Any) -> list[str]:
    if isinstance(value, dict):
        value = list(value.values())
    if not isinstance(value, (list, tuple)):
        return []
    return sorted({str(v).strip() for v in value if isinstance(v, str) and v.strip()})


def _base_description(text: Any) -> str:
    """去掉驳回时追加的「驳回原因」：同一来源数据被驳回后原样再生成，不算变化。"""
    return str(text or "").split(_REJECTION_MARK)[0].strip()


def _signature(entry_type: str, description: Any, lines: Iterable[tuple], related: Iterable[str]) -> tuple:
    return (
        entry_type,
        _base_description(description),
        tuple((code, name or "", to_cents(debit), to_cents(credit)) for code, name, debit, credit in lines),
        tuple(sorted(set(related))),
    )


def entry_signature(entry: Any) -> tuple | None:
    """已有分录的内容签名（类型、说明、明细行、交易方）；明细行坏掉 ⇒ None（与任何计划都不同）。"""
    try:
        lines = line_items(entry)
    except EntryDataError:
        return None
    return _signature(
        _enum(entry.entry_type), entry.description,
        ((ln.account_code, ln.account_name, ln.debit, ln.credit) for ln in lines),
        _related_list(entry.related_company_codes),
    )


@dataclass
class GroupPlan:
    """一个来源分组的生成计划：``reasons`` 非空 ⇒ 不生成（blocked）。"""

    origin: str
    origin_key: str
    entry_type: str
    description: str
    related: list[str]
    lines: list[PlannedLine]
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # created / updated / unchanged / blocked / review_locked / empty / discarded（旧版转入后已被删除，不再转回）
    action: str = ""
    entry_id: UUID | None = None
    entry_no: str | None = None
    review_status: str | None = None

    @property
    def empty(self) -> bool:
        return not self.lines

    @property
    def debit_total(self) -> Decimal:
        return sum((ln.debit for ln in self.lines), ZERO)

    @property
    def credit_total(self) -> Decimal:
        return sum((ln.credit for ln in self.lines), ZERO)

    def entry_lines(self) -> list[tuple[str, str, Decimal, Decimal]]:
        return [(ln.mapped.account_code or "", ln.mapped.account_name or "", ln.debit, ln.credit) for ln in self.lines]

    def signature(self) -> tuple:
        return _signature(self.entry_type, self.description, self.entry_lines(), self.related)

    def to_dict(self) -> dict:
        return {
            "origin": self.origin,
            "origin_label": ORIGIN_LABELS.get(self.origin, self.origin),
            "origin_key": self.origin_key,
            "action": self.action,
            "entry_id": str(self.entry_id) if self.entry_id else None,
            "entry_no": self.entry_no,
            "review_status": self.review_status,
            "entry_type": self.entry_type,
            "entry_type_label": ENTRY_TYPE_LABELS.get(self.entry_type, self.entry_type),
            "description": self.description,
            "related_company_codes": self.related,
            "debit_total": str(self.debit_total),
            "credit_total": str(self.credit_total),
            "lines": [ln.to_dict() for ln in self.lines],
            "reasons": self.reasons,
            "warnings": self.warnings,
        }


def _plan_line(index: int, line: Any, mapper: SubjectMapper) -> PlannedLine | None:
    """一行来源 ⇒ 计划行；金额为 0 ⇒ None（不入账）。负金额换向取绝对值。"""
    subject = normalize_name(getattr(line, "subject", None))
    detail = normalize_name(getattr(line, "detail", None))
    planned = PlannedLine(index, subject, detail, None, None)
    raw_direction = str(getattr(line, "direction", "") or "").strip()
    direction = _DIRECTIONS.get(raw_direction)
    try:
        amount = to_cents(getattr(line, "amount", None))
    except (InvalidOperation, ValueError, TypeError):
        planned.reason = f"第 {index} 行（{planned.label()}）金额无法识别：{getattr(line, 'amount', None)!r}"
        return planned
    if amount == 0:
        return None
    if direction is None:
        planned.reason = f"第 {index} 行（{planned.label()}）借贷方向「{raw_direction}」无法识别"
        return planned
    if amount < 0:
        direction = "credit" if direction == "debit" else "debit"
        amount = -amount
    planned.direction, planned.amount = direction, amount
    planned.mapped = mapper.map(subject, detail)
    if planned.mapped.reason:
        planned.reason = f"第 {index} 行（{planned.label()}）：{planned.mapped.reason}"
    return planned


def plan_group(group: Any, mapper: SubjectMapper, *, existing_type: str | None = None) -> GroupPlan:
    """来源分组 ⇒ 计划（design §9.1）：逐行映射、借贷平衡、分录类型。不连库。"""
    origin = group.origin
    requested = _enum(group.entry_type) or None
    allowed = ORIGIN_ENTRY_TYPES[origin]
    entry_type = requested or existing_type or allowed[0]
    description = normalize_description(group.description) or DEFAULT_DESCRIPTIONS[origin]
    plan = GroupPlan(
        origin, group.origin_key, entry_type, description,
        _related_list(group.related_company_codes), [],
    )
    for i, line in enumerate(group.lines or (), 1):
        planned = _plan_line(i, line, mapper)
        if planned is not None:
            plan.lines.append(planned)
    if plan.empty:
        plan.action = "empty"
        return plan
    if requested and requested not in allowed:
        plan.reasons.append(
            f"来源「{ORIGIN_LABELS[origin]}」不能生成「{ENTRY_TYPE_LABELS.get(requested, requested)}」类型的分录"
        )
    plan.reasons += [ln.reason for ln in plan.lines if ln.reason]
    if plan.debit_total != plan.credit_total:
        plan.reasons.append(f"借贷不平衡：借方合计 {plan.debit_total}，贷方合计 {plan.credit_total}")
    plan.warnings += list(dict.fromkeys(ln.mapped.warning for ln in plan.lines if ln.mapped.warning))
    if plan.reasons:
        plan.action = "blocked"
    return plan


def normalize_description(value: Any) -> str:
    return re.sub(r"[ \t]+", " ", str(value or "")).strip()


# ─────────────────────────────── 明细表（读） ───────────────────────────────


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def sheet_lines(tree: TreeNode, project_id: UUID, entries: Iterable[Any]) -> dict:
    """本树全部未删分录 ⇒ 明细行（纯函数，design §九）。

    归属与合并计算同一函数 ``attribute_entries``：``counted``（已审批且找到归属节点）的分录恰是重算计入的那批；
    其余已审批分录给出孤儿原因。明细行无法识别的分录列一行占位（不给金额）并给原因，不静默丢弃。
    """
    entries = list(entries)
    index = index_tree(tree)
    records, invalid = records_from_entries(entries)
    attributed, orphans = attribute_entries(records, index, invalid)
    node_of = {e.id: key for e, key in attributed}
    orphan_of = {o.entry_id: o.reason for o in orphans}
    labels = {n.node_key: n.display_name or n.company_name for n in iter_nodes(tree)}
    host_names = {pid: node.company_name for pid, node in index.consol_by_project.items()}
    totals = {k: [ZERO, ZERO, 0] for k in ("all", "approved", "counted")}
    rows: list[dict] = []

    def order(e: Any) -> tuple:
        return (e.project_id != project_id, host_names.get(e.project_id, ""), e.entry_no or "", str(e.id))

    for entry in sorted(entries, key=order):
        status = _enum(entry.review_status)
        key = node_of.get(entry.id)
        counted = status == "approved" and key is not None
        try:
            lines = line_items(entry)
        except EntryDataError:
            lines = ()
        buckets = ["all"] + (["approved"] if status == "approved" else []) + (["counted"] if counted else [])
        for b in buckets:
            totals[b][2] += 1
        base = {
            "entry_id": str(entry.id),
            "entry_no": entry.entry_no,
            "origin": entry.origin,
            "origin_label": ORIGIN_LABELS.get(entry.origin, entry.origin) if entry.origin else "手工录入",
            "origin_key": entry.origin_key,
            "node_key": key,
            "node_label": labels.get(key) if key else None,
            "branch_entity_code": (entry.branch_entity_code or "").strip() or None,
            "host_project_id": str(entry.project_id),
            "host_project_name": host_names.get(entry.project_id),
            "readonly": entry.project_id != project_id,
            "entry_type": _enum(entry.entry_type),
            "entry_type_label": ENTRY_TYPE_LABELS.get(_enum(entry.entry_type), _enum(entry.entry_type)),
            "description": entry.description,
            "review_status": status,
            "review_status_label": _status_label(status),
            "counted": counted,
            "orphan_reason": orphan_of.get(entry.id),
            "related_company_codes": _related_list(entry.related_company_codes),
        }
        if not lines:
            rows.append({**base, "line_index": 1, "line_count": 1, "account_code": None,
                         "account_name": None, "debit": None, "credit": None})
            continue
        for i, line in enumerate(lines, 1):
            rows.append({**base, "line_index": i, "line_count": len(lines), "account_code": line.account_code,
                         "account_name": line.account_name, "debit": str(line.debit), "credit": str(line.credit)})
            for b in buckets:
                totals[b][0] += line.debit
                totals[b][1] += line.credit
    hosted = [
        {
            "node_key": n.node_key,
            "label": n.display_name or n.company_name,
            "branch_entity_code": None if n.role == ROLE_CONSOL_ELIM else n.company_code,
        }
        for n in iter_nodes(tree) if n.kind == KIND_ELIM and n.host_project_id == project_id
    ]
    return {
        "rows": rows,
        "hosted_nodes": hosted,
        "totals": {
            k: {"debit": str(d), "credit": str(c), "difference": str(d - c), "entry_count": n}
            for k, (d, c, n) in totals.items()
        },
    }


async def _consol_tree(db: AsyncSession, project_id: UUID) -> tuple[TreeNode, int | None]:
    from app.services.consol_group_tree import build_group_tree

    result = await build_group_tree(db, project_id)
    if result is None or result.root is None:
        raise SheetError("项目不存在", status=404)
    if result.root.role != ROLE_CONSOL:
        raise SheetError("只有合并报表项目有合并抵消分录明细表")
    return result.root, result.year


def _effective_year(requested: int | None, tree_year: int | None) -> int:
    year = requested if requested is not None else tree_year
    if year is None:
        raise SheetError("项目没有审计年度，请先在项目基本信息中填写")
    return year


async def tree_lines(db: AsyncSession, project_id: UUID, year: int | None = None) -> dict:
    tree, tree_year = await _consol_tree(db, project_id)
    effective = _effective_year(year, tree_year)
    entries = await load_tree_entries(db, tree, effective, approved_only=False)
    return {"year": effective, "project_id": str(project_id), **sheet_lines(tree, project_id, entries)}


# ─────────────────────────────── 工作底稿 → 草稿分录（写） ───────────────────────────────


@dataclass
class GenerateResult:
    year: int
    standard: str
    dry_run: bool
    plans: list[GroupPlan] = field(default_factory=list)
    deleted: list[dict] = field(default_factory=list)
    changed_after_review: list[dict] = field(default_factory=list)

    def count(self, action: str) -> int:
        return sum(1 for p in self.plans if p.action == action)

    def to_dict(self) -> dict:
        blocked = [
            {"origin": p.origin, "origin_key": p.origin_key, "reason": "；".join(p.reasons), "reasons": p.reasons,
             "entry_id": str(p.entry_id) if p.entry_id else None}
            for p in self.plans if p.action == "blocked"
        ]
        return {
            "year": self.year,
            "standard": self.standard,
            "dry_run": self.dry_run,
            "created": self.count("created"),
            "updated": self.count("updated"),
            "unchanged": self.count("unchanged"),
            "discarded": self.count("discarded"),
            "deleted": len(self.deleted),
            "blocked": blocked,
            "changed_after_review": self.changed_after_review,
            "deleted_entries": self.deleted,
            "warnings": list(dict.fromkeys(w for p in self.plans for w in p.warnings)),
            "groups": [p.to_dict() for p in self.plans],
        }


def _check_request(groups: Sequence[Any], origins: Iterable[str] | None, allowed: Iterable[str]) -> list[str]:
    allowed = tuple(allowed)
    declared = list(dict.fromkeys(origins)) if origins is not None else list(dict.fromkeys(g.origin for g in groups))
    bad = [o for o in declared if o not in allowed] + [g.origin for g in groups if g.origin not in allowed]
    if bad:
        raise SheetError(f"来源 {sorted(set(bad))} 不能由本接口生成")
    if origins is not None:
        stray = sorted({g.origin for g in groups} - set(declared))
        if stray:
            raise SheetError(f"分组来源 {stray} 不在本次声明的来源 {declared} 内")
    seen: set[tuple[str, str]] = set()
    dup: set[str] = set()
    for g in groups:
        key = (g.origin, g.origin_key)
        if key in seen:
            dup.add(f"{g.origin}:{g.origin_key}")
        seen.add(key)
    if dup:
        raise SheetError(f"来源键重复：{sorted(dup)}")
    return declared


def _review_note(entry: EliminationEntry, reason: str) -> dict:
    status = _enum(entry.review_status)
    hint = "如需按来源更新，请先撤销审批" if status == "approved" else "如需按来源更新，请先驳回"
    return {
        "origin": entry.origin,
        "origin_key": entry.origin_key,
        "entry_id": str(entry.id),
        "entry_no": entry.entry_no,
        "review_status": status,
        "reason": f"{reason}，{_status_label(status)}分录未改动；{hint}",
    }


def _entry_lines(plan: GroupPlan) -> tuple[list[dict], Decimal, Decimal]:
    from app.models.consolidation_schemas import EliminationEntryLine
    from app.services.elimination_service import _serialize_lines

    return _serialize_lines([
        EliminationEntryLine(account_code=code, account_name=name, debit_amount=debit, credit_amount=credit)
        for code, name, debit, credit in plan.entry_lines()
    ])


async def _existing_by_key(
    db: AsyncSession, project_id: UUID, year: int, origins: Iterable[str], *, include_deleted: bool = False,
) -> dict[tuple[str, str], EliminationEntry]:
    """来源键 → 分录（部分唯一索引保证同键至多一笔未删的）。

    ``include_deleted``：同键没有未删分录时取已软删的那笔 —— 旧版转入后审计师删掉的草稿算「已处理」，不再转回来。
    """
    origins = list(origins)
    if not origins:
        return {}
    stmt = sa.select(EliminationEntry).where(
        EliminationEntry.project_id == project_id,
        EliminationEntry.year == year,
        EliminationEntry.origin.in_(origins),
        EliminationEntry.origin_key.is_not(None),
    )
    if not include_deleted:
        stmt = stmt.where(EliminationEntry.is_deleted == sa.false())
    result = await db.execute(stmt.order_by(EliminationEntry.is_deleted, EliminationEntry.entry_no, EliminationEntry.id))
    out: dict[tuple[str, str], EliminationEntry] = {}
    for e in result.scalars().all():
        out.setdefault((e.origin, e.origin_key), e)  # 未删的排在前面
    return out


def _apply_plan(entry: EliminationEntry, plan: GroupPlan, user_id: UUID | None) -> None:
    """按计划改写草稿 / 已驳回分录：明细行、表头代表科目、借贷合计、类型、说明、交易方；状态置草稿。

    驳回时追加在说明末尾的「驳回原因」保留（审批痕迹不因重新生成丢失）；归属节点不动（审计师可能改过）。
    """
    rows, debit, credit = _entry_lines(plan)
    old = str(entry.description or "")
    cut = old.find(_REJECTION_MARK)
    entry.description = plan.description + (old[cut:] if cut >= 0 else "")
    entry.lines = rows
    entry.account_code = rows[0]["account_code"]
    entry.account_name = rows[0]["account_name"]
    entry.debit_amount = debit
    entry.credit_amount = credit
    entry.entry_type = EliminationEntryType(plan.entry_type)
    entry.related_company_codes = plan.related
    entry.review_status = ReviewStatusEnum.draft
    entry.reviewer_id = None
    entry.reviewed_at = None
    entry.updated_by = user_id


async def _create_entry(
    db: AsyncSession, project_id: UUID, year: int, plan: GroupPlan, *,
    tree: TreeNode, group_id: UUID, user_id: UUID | None,
) -> EliminationEntry:
    from app.services.elimination_service import _generate_entry_no

    rows, debit, credit = _entry_lines(plan)
    entry_type = EliminationEntryType(plan.entry_type)
    entry = EliminationEntry(
        id=uuid4(),
        project_id=project_id,
        year=year,
        entry_no=await _generate_entry_no(db, project_id, year, entry_type),
        entry_type=entry_type,
        description=plan.description,
        account_code=rows[0]["account_code"],
        account_name=rows[0]["account_name"],
        lines=rows,
        entry_group_id=group_id,
        related_company_codes=plan.related,
        # 归属预填（只是草稿默认值，审批前由审计师确认）：交易各方在同一母公司分公司闭包内 ⇒ 母分差额
        branch_entity_code=suggest_branch_entity(tree, project_id, plan.related),
        origin=plan.origin,
        origin_key=plan.origin_key,
        review_status=ReviewStatusEnum.draft,
        debit_amount=debit,
        credit_amount=credit,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(entry)
    await db.flush()  # 下一笔取编号时能看到这一笔
    return entry


async def _serialize_generation(db: AsyncSession, project_id: UUID, year: int) -> None:
    """同一合并项目同一年度的生成串行（PG 事务级咨询锁；SQLite 无此能力，靠部分唯一索引兜底）。"""
    if db.get_bind().dialect.name != "postgresql":
        return
    await db.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"consol_elim_generate:{project_id}:{year}"},
    )


async def generate_from_worksheet(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    groups: Sequence[Any],
    *,
    origins: Iterable[str] | None = None,
    dry_run: bool = False,
    user_id: UUID | None = None,
    allowed_origins: Iterable[str] = WORKSHEET_ORIGINS,
    sync: bool = True,
) -> GenerateResult:
    """来源分组 ⇒ 草稿分录（design §9.1，需求 2.2~2.6）。``dry_run`` 只返回计划不写库；只 flush 不提交。

    ``sync=True``（工作底稿，来源是活数据，草稿随来源走）：
    - 无记录 ⇒ 新建草稿；草稿 / 已驳回且内容变了 ⇒ 改写并置草稿；内容相同 ⇒ 不动（P6 幂等）；
    - 待审批 / 已审批 ⇒ 不动（P7），内容不同记 ``changed_after_review``；
    - 声明负责的来源里本次没有产出（或金额全为 0）的来源键 ⇒ 草稿 / 已驳回软删，待审批 / 已审批只报告；
    - 映射失败或借贷不平 ⇒ 该组 blocked 并逐条给原因；已有草稿保持原样（``entry_id`` 标出）。
    ``sync=False``（旧版明细表转入，来源已冻结，转入后分录归审计师）：只新建缺的，已有的一律不动、不删。
    """
    tree, _tree_year = await _consol_tree(db, project_id)
    declared = _check_request(groups, origins, allowed_origins)
    mapper, standard = await load_mapper(db, project_id, tree, year)
    try:
        return await _generate(
            db, project_id, year, groups, declared, mapper, standard, tree,
            dry_run=dry_run, user_id=user_id, sync=sync,
        )
    except IntegrityError as exc:
        await db.rollback()
        raise SheetError("另一次生成正在写入同一来源的草稿，请刷新后重试", status=409) from exc


async def _generate(
    db: AsyncSession, project_id: UUID, year: int, groups: Sequence[Any], declared: list[str],
    mapper: SubjectMapper, standard: str, tree: TreeNode, *, dry_run: bool, user_id: UUID | None, sync: bool,
) -> GenerateResult:
    if not dry_run:
        await _serialize_generation(db, project_id, year)
    existing = await _existing_by_key(db, project_id, year, declared, include_deleted=not sync)
    result = GenerateResult(year, standard, dry_run)
    produced: set[tuple[str, str]] = set()
    group_ids: dict[str, UUID] = {}
    for group in groups:
        key = (group.origin, group.origin_key)
        entry = existing.get(key)
        plan = plan_group(group, mapper, existing_type=_enum(entry.entry_type) if entry is not None else None)
        result.plans.append(plan)
        if entry is not None:
            plan.entry_id, plan.entry_no, plan.review_status = entry.id, entry.entry_no, _enum(entry.review_status)
        if plan.empty:
            continue  # 来源不再产出这笔 ⇒ 与缺席同样处理（下面软删草稿）
        produced.add(key)
        if entry is not None and not sync:
            # 已转入过：分录归审计师（改过、删过都算处理过），不再按冻结的旧数据改写或转回
            plan.action = "discarded" if entry.is_deleted else "unchanged"
            continue
        same = entry is not None and not plan.reasons and entry_signature(entry) == plan.signature()
        if entry is not None and entry.review_status not in EDITABLE_STATUSES:
            if same:
                plan.action = "unchanged"
            else:
                plan.action = "review_locked"
                why = f"来源数据当前无法生成（{'；'.join(plan.reasons)}）" if plan.reasons else "来源数据已变化"
                result.changed_after_review.append(_review_note(entry, why))
            continue
        if plan.reasons:
            plan.action = "blocked"
            if entry is not None:
                plan.warnings.append(f"已有草稿 {entry.entry_no} 保持原样（来源数据当前无法生成）")
            continue
        if entry is None:
            plan.action, plan.review_status = "created", "draft"
            if not dry_run:
                gid = group_ids.setdefault(plan.origin, uuid4())
                created = await _create_entry(db, project_id, year, plan, tree=tree, group_id=gid, user_id=user_id)
                plan.entry_id, plan.entry_no = created.id, created.entry_no
        elif same:
            plan.action = "unchanged"  # 已驳回且来源没变 ⇒ 驳回结论不被重新生成推翻
        else:
            plan.action, plan.review_status = "updated", "draft"
            if not dry_run:
                _apply_plan(entry, plan, user_id)
    for key, entry in existing.items() if sync else ():
        if key in produced:
            continue
        if entry.review_status in EDITABLE_STATUSES:
            result.deleted.append({
                "origin": entry.origin, "origin_key": entry.origin_key, "entry_id": str(entry.id),
                "entry_no": entry.entry_no, "review_status": _enum(entry.review_status),
            })
            if not dry_run:
                entry.soft_delete()
                entry.updated_by = user_id
        else:
            result.changed_after_review.append(_review_note(entry, "来源数据已不再产出这笔分录"))
    if not dry_run:
        await db.flush()  # 只 flush，由路由统一提交
    return result


# ─────────────────────────────── 旧版明细表（JSON）转入 ───────────────────────────────


def _legacy_items(data: Any) -> list[dict]:
    """旧版明细表 JSON 的行：``{"rows": [...]}``（EliminationSheet 保存的全部行）或 ``{"rows": {"equity": [...], ...}}``。"""
    rows = data.get("rows") if isinstance(data, dict) else data
    if isinstance(rows, dict):
        rows = [item for part in rows.values() if isinstance(part, list) for item in part]
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def legacy_custom_rows(data: Any) -> tuple[list[dict], int]:
    """自定义行（``_custom`` 为真，或带 ``source`` 键且为空）：返回 (有金额的行, 金额为 0 被跳过的行数)。

    自动拉取行（有来源）是工作底稿的计算结果，由新明细表按来源重新生成，不在转入范围；
    整行空白（无科目无金额）不计。
    """
    custom = [
        r for r in _legacy_items(data)
        if r.get("_custom") is True or ("source" in r and not str(r.get("source") or "").strip())
    ]
    kept: list[dict] = []
    skipped = 0
    for r in custom:
        try:
            zero = to_cents(r.get("amount")) == 0
        except (InvalidOperation, ValueError, TypeError):
            zero = False  # 金额认不出也要列出原因，不能当 0 丢掉
        if zero:
            skipped += 1 if normalize_name(r.get("subject")) else 0
            continue
        kept.append(r)
    return kept, skipped


def _signed(direction: str | None, amount: Decimal) -> tuple[Decimal, Decimal]:
    side = _DIRECTIONS.get(str(direction or "").strip())
    if amount < 0:
        side, amount = ("credit" if side == "debit" else "debit") if side else None, -amount
    if side == "debit":
        return amount, ZERO
    if side == "credit":
        return ZERO, amount
    return ZERO, ZERO


def legacy_groups(rows: Sequence[dict], entry_type: str | None = None) -> list[SourceGroup]:
    """按录入顺序累计借贷，借贷相等处切成一笔（旧版表没有分录边界，只有逐行借贷）；
    末尾不平的剩余行成最后一组（生成时报借贷不平衡）。来源键 = 序号 + 内容摘要（确定、重复转入幂等）。"""
    groups: list[SourceGroup] = []
    current: list[dict] = []
    debit = credit = ZERO

    def close() -> None:
        nonlocal current, debit, credit
        if not current:
            return
        lines = [SourceLine(str(r.get("subject") or ""), str(r.get("detail") or "") or None,
                            str(r.get("direction") or ""), r.get("amount")) for r in current]
        descs = list(dict.fromkeys(normalize_description(r.get("desc")) for r in current if normalize_description(r.get("desc"))))
        digest = hashlib.sha1(json.dumps(
            [[ln.subject, ln.detail, ln.direction, str(ln.amount)] for ln in lines], ensure_ascii=False,
        ).encode("utf-8")).hexdigest()[:12]
        groups.append(SourceGroup(
            ORIGIN_LEGACY, f"legacy:{len(groups) + 1:03d}:{digest}",
            f"{DEFAULT_DESCRIPTIONS[ORIGIN_LEGACY]}：{'；'.join(descs)}" if descs else DEFAULT_DESCRIPTIONS[ORIGIN_LEGACY],
            lines, entry_type,
        ))
        current, debit, credit = [], ZERO, ZERO

    for r in rows:
        current.append(r)
        try:
            d, c = _signed(r.get("direction"), to_cents(r.get("amount")))
        except (InvalidOperation, ValueError, TypeError):
            d = c = ZERO
        debit, credit = debit + d, credit + c
        if debit == credit and debit > 0:
            close()
    close()
    return groups


async def load_legacy_sheet(db: AsyncSession, project_id: UUID, year: int) -> Any:
    from app.models.consol_worksheet_data_models import ConsolWorksheetData

    return (await db.execute(sa.select(ConsolWorksheetData.data).where(
        ConsolWorksheetData.project_id == project_id,
        ConsolWorksheetData.year == year,
        ConsolWorksheetData.sheet_key == LEGACY_SHEET_KEY,
    ))).scalar_one_or_none()


async def legacy_sheet(
    db: AsyncSession, project_id: UUID, year: int | None = None, *,
    convert: bool = False, entry_type: str | None = None, user_id: UUID | None = None,
) -> dict:
    """旧版明细表自定义行：检测（``convert=False``，预演）或转为草稿分录（需求 1.6）。

    ``pending`` = 还没有对应分录的组数（0 且有自定义行 ⇒ 已全部转入）；转不了的组逐条列原因。
    """
    _tree, tree_year = await _consol_tree(db, project_id)
    effective = _effective_year(year, tree_year)
    rows, skipped = legacy_custom_rows(await load_legacy_sheet(db, project_id, effective))
    groups = legacy_groups(rows, entry_type)
    result = await generate_from_worksheet(
        db, project_id, effective, groups, origins=[ORIGIN_LEGACY], dry_run=not convert,
        user_id=user_id, allowed_origins=(ORIGIN_LEGACY,), sync=False,
    )
    body = result.to_dict()
    # 还没有对应分录的组：预演时 = 将新建 + 转不了；转入后 = 转不了（新建的已有 entry_id）
    pending = sum(1 for p in result.plans if p.entry_id is None and p.action in ("created", "blocked"))
    return {
        **body,
        "custom_row_count": len(rows),
        "skipped_zero_rows": skipped,
        "group_count": len(groups),
        "pending": pending,
        "message": (
            f"检测到旧版自定义抵销行 {len(rows)} 条，旧版数据未参与合并计算" if rows else "没有旧版自定义抵销行"
        ),
    }
