"""四张抵销后表的服务端 canonical projection（consolidation-run-and-workpaper-lifecycle-closure 批 3 / ADR-CRW-004）。

四张表（抵消后长投、抵消后投资收益、少数股东权益损益、资本公积抵销列）此前从未填值的
空骨架 ``elimEquity`` / ``elimIncome`` 取「抵消分录数」，恒为 0。本模块改为从**唯一正式来源**
——已审批（``approved``）且归属成功的 ``elimination_entries``——派生权威的抵销金额。

**不新增事实表**：输入是同一棵树的 ``CalcBasis``（与差额表 / 合并试算 / 报表同源）、approved 分录
原始行（读 ``related_company_codes`` 作逐企业展示）与工作表 manual overrides；输出四个只读 DTO。

口径（与 ``consol_calc_basis.node_measures`` 完全一致，P2/P8）：

- **权威总额** = 根节点 ``MEASURE_ELIM_EQUITY`` 的某科目净额，``sign(a)·(借−贷)`` 归一后求和；
  这是进入合并数的权益抵销，不可争议。
- **逐企业展示** = 遍历 approved 权益类分录的明细行，对目标科目前缀按同一 ``sign`` 归一，
  用分录 ``related_company_codes`` 做归属：**恰有一个非根子公司代码**时归该企业，否则进「未分配」。
  绝不复制给每家、绝不平均分摊（``related_company_codes`` V167 起不参与正式金额分摊，ADR-CTREE-003，
  所以这里只能作尽力而为的展示拆分，拆不出的诚实留在未分配并 warning）。
- **恒等式**：``Σ 各企业 + 未分配 == 权威总额``（到分）。若因数据异常不等，差额并入未分配并记 warning，
  不崩、不静默吞。

自动列只读；用户判断走工作表的 manual override（本模块只把 override 原样带出，不反推成第二份分录事实）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

from app.services.consol_calc_basis import (
    CENT,
    EQUITY_ENTRY_TYPE,
    ZERO,
    CalcBasis,
    account_sign,
    line_items,
    to_cents,
)
from app.services.consol_calc_basis import (
    MEASURE_ELIM_EQUITY,
    node_measures,
)

# 标准科目码前缀（与报表 BasisResolver 同口径，按前缀匹配；来源 wp_account_mapping.json）
ACCOUNT_LONG_INVEST = "1511"   # 长期股权投资
ACCOUNT_INVEST_INCOME = "6111"  # 投资收益
ACCOUNT_CAPITAL_RESERVE = "4002"  # 资本公积
ACCOUNT_MINORITY_EQUITY = "4501"  # 少数股东权益


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


@dataclass(frozen=True)
class CompanyShare:
    """某企业在某科目上的抵销分解（展示用，金额为 sign 归一后净额）。"""

    company_code: str
    company_name: str
    amount: Decimal
    source_entry_ids: tuple[str, ...]


@dataclass(frozen=True)
class AccountElimination:
    """某科目的权威抵销总额 + 逐企业分解 + 未分配额。"""

    account_prefix: str
    label: str
    total: Decimal                       # 权威总额（node_measures 的权益抵销净额）
    by_company: tuple[CompanyShare, ...]  # 尽力而为的逐企业展示分解
    unallocated: Decimal                 # 无法唯一归属到单家的部分
    warnings: tuple[str, ...]

    def is_balanced(self) -> bool:
        allocated = sum((s.amount for s in self.by_company), ZERO)
        return (allocated + self.unallocated).quantize(CENT) == self.total.quantize(CENT)


@dataclass(frozen=True)
class PostEliminationProjection:
    """四张抵销后表的只读 canonical 数据。各表的「抵消分录数」列读这里，自动列只读。"""

    project_id: str
    year: int
    root_node_key: str
    # 按科目前缀的权威抵销（供四张表各取所需）
    accounts: dict[str, AccountElimination]
    # 工作表 manual overrides（原样带出，前端叠加到展示层，不写回分录）
    manual_overrides: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def account(self, prefix: str) -> AccountElimination | None:
        return self.accounts.get(prefix)


_PROJECTED_ACCOUNTS: tuple[tuple[str, str], ...] = (
    (ACCOUNT_LONG_INVEST, "长期股权投资"),
    (ACCOUNT_INVEST_INCOME, "投资收益"),
    (ACCOUNT_CAPITAL_RESERVE, "资本公积"),
    (ACCOUNT_MINORITY_EQUITY, "少数股东权益"),
)


def _root_equity_elim_by_account(basis: CalcBasis) -> dict[str, Decimal]:
    """根节点权益抵销净额（按完整科目码）。"""
    measures = node_measures(basis)
    root = measures.get(basis.tree.node_key, {})
    return dict(root.get(MEASURE_ELIM_EQUITY, {}))


def _sum_prefix(amounts_by_account: dict[str, Decimal], prefix: str) -> Decimal:
    return sum(
        (amount for code, amount in amounts_by_account.items() if code.startswith(prefix)),
        ZERO,
    )


def _single_subsidiary(
    related: Iterable[str] | None, subsidiary_codes: set[str], root_code: str,
) -> str | None:
    """分录相关企业里恰有一个非根子公司代码 ⇒ 归该企业；零个或多个 ⇒ None（进未分配）。"""
    if not related:
        return None
    candidates = sorted({
        str(code).strip() for code in related
        if str(code).strip() and str(code).strip() != root_code
        and str(code).strip() in subsidiary_codes
    })
    return candidates[0] if len(candidates) == 1 else None


def _company_elim_shares(
    approved_entries: Iterable[Any],
    prefix: str,
    subsidiary_codes: set[str],
    root_code: str,
    names: dict[str, str],
    signs: dict[str, Decimal],
) -> tuple[dict[str, Decimal], dict[str, set[str]], Decimal, list[str]]:
    """遍历 approved 权益类分录，按科目前缀归集逐企业净额与未分配净额。

    返回 ``(by_company_amount, by_company_entry_ids, unallocated, warnings)``。
    金额口径与 node_measures 一致：``sign(a)·(借−贷)``（EntryLine 已按录入方向存借贷）。
    """
    by_company: dict[str, Decimal] = {}
    entry_ids: dict[str, set[str]] = {}
    unallocated = ZERO
    warnings: list[str] = []
    multi_hit = 0
    no_hit = 0
    for entry in approved_entries:
        if _enum_value(getattr(entry, "entry_type", None)) != EQUITY_ENTRY_TYPE:
            continue
        try:
            lines = line_items(entry)
        except Exception:  # noqa: BLE001 — 坏明细行在 CalcBasis 已记孤儿，这里跳过展示
            continue
        net = ZERO
        touched = False
        for line in lines:
            if not line.account_code.startswith(prefix):
                continue
            sign = signs.get(line.account_code)
            if sign is None:
                sign = account_sign(line.account_code, line.account_name or names.get(line.account_code))
            net += sign * (to_cents(line.debit) - to_cents(line.credit))
            touched = True
        if not touched or net == ZERO:
            continue
        code = _single_subsidiary(
            getattr(entry, "related_company_codes", None), subsidiary_codes, root_code,
        )
        if code is None:
            unallocated += net
            related = getattr(entry, "related_company_codes", None) or []
            if len([c for c in related if str(c).strip() and str(c).strip() != root_code]) > 1:
                multi_hit += 1
            else:
                no_hit += 1
            continue
        by_company[code] = by_company.get(code, ZERO) + net
        entry_ids.setdefault(code, set()).add(str(getattr(entry, "id", "")))
    if multi_hit:
        warnings.append(f"{multi_hit} 笔权益抵销分录关联了多家企业，无法唯一归属，计入未分配")
    if no_hit:
        warnings.append(f"{no_hit} 笔权益抵销分录未标企业或企业不在合并范围，计入未分配")
    return by_company, entry_ids, unallocated, warnings


def _build_account(
    prefix: str,
    label: str,
    authoritative_total: Decimal,
    approved_entries: Iterable[Any],
    subsidiary_codes: set[str],
    root_code: str,
    names: dict[str, str],
    signs: dict[str, Decimal],
) -> AccountElimination:
    by_company, entry_ids, unallocated, warnings = _company_elim_shares(
        approved_entries, prefix, subsidiary_codes, root_code, names, signs,
    )
    shares = tuple(
        CompanyShare(
            company_code=code,
            company_name=names.get(code) or code,
            amount=amount.quantize(CENT),
            source_entry_ids=tuple(sorted(entry_ids.get(code, set()))),
        )
        for code, amount in sorted(by_company.items())
    )
    allocated = sum((s.amount for s in shares), ZERO)
    # 恒等式校验：Σ 企业 + 未分配 == 权威总额；差额并入未分配并 warning（不崩、不静默）
    residual = authoritative_total.quantize(CENT) - (allocated + unallocated).quantize(CENT)
    if residual != ZERO:
        unallocated = (unallocated + residual).quantize(CENT)
        warnings = [
            *warnings,
            f"逐企业分解与权威抵销总额差 {residual}，差额已并入未分配（请复核分录企业标注）",
        ]
    return AccountElimination(
        account_prefix=prefix,
        label=label,
        total=authoritative_total.quantize(CENT),
        by_company=shares,
        unallocated=unallocated.quantize(CENT),
        warnings=tuple(warnings),
    )


def build_post_elimination_projection(
    basis: CalcBasis,
    approved_entries: Iterable[Any],
    *,
    subsidiary_codes: set[str],
    root_code: str,
    manual_overrides: dict[str, Any] | None = None,
) -> PostEliminationProjection:
    """纯函数：装配四张抵销后表的 canonical projection。

    ``approved_entries`` 必须是已审批的权益抵销分录原始行（读 entry_type / lines /
    related_company_codes / id）；``basis`` 提供权威总额与科目名/符号。
    """
    equity_by_account = _root_equity_elim_by_account(basis)
    names = dict(basis.names)
    signs = dict(basis.signs)
    accounts: dict[str, AccountElimination] = {}
    all_warnings: list[str] = []
    for prefix, label in _PROJECTED_ACCOUNTS:
        total = _sum_prefix(equity_by_account, prefix)
        account = _build_account(
            prefix, label, total, approved_entries, subsidiary_codes, root_code, names, signs,
        )
        accounts[prefix] = account
        for w in account.warnings:
            all_warnings.append(f"{label}：{w}")
    return PostEliminationProjection(
        project_id=str(getattr(basis.tree, "project_id", "") or ""),
        year=basis.year,
        root_node_key=basis.tree.node_key,
        accounts=accounts,
        manual_overrides=dict(manual_overrides or {}),
        warnings=tuple(all_warnings),
    )


# ─────────────────────────────── 装载层（连库，只读） ───────────────────────────────

# 四张抵销后表对应的工作表 manual override sheet_key
_PROJECTION_SHEETS: tuple[str, ...] = ("post_invest", "post_income", "minority", "capital")


async def load_post_elimination_projection(db, project_id, year, *, tree=None, basis=None):
    """以合并项目为根，装载四表 canonical projection（只读，不写库）。

    - 计算口径只认 ``approved`` 分录（与合并数、推送、报表同口径）；
    - 逐企业展示用 approved 权益抵销分录的 ``related_company_codes``（保守单一归属）；
    - manual overrides 原样从 ``consol_worksheet_data`` 读出，不参与分录事实。

    项目不是合并项目 / 无企业树 ⇒ 返回 ``None``。
    """
    import sqlalchemy as sa

    from app.models.consol_worksheet_data_models import ConsolWorksheetData
    from app.services.consol_calc_basis import (
        data_leaves,
        load_calc_basis,
        load_tree_entries,
    )
    from app.services.consol_tree_service import build_tree

    resolved_tree = tree if tree is not None else (basis.tree if basis is not None else await build_tree(db, project_id))
    if resolved_tree is None:
        return None
    resolved_basis = basis
    if resolved_basis is None:
        resolved_basis = await load_calc_basis(db, project_id, year, tree=resolved_tree)
    if resolved_basis is None:
        return None

    # 非根数据叶子的企业代码集合（逐企业归属的候选域）
    subsidiary_codes = {
        leaf.company_code for leaf in data_leaves(resolved_tree, include_root=False)
        if leaf.company_code
    }
    root_code = (resolved_tree.company_code or "").strip()

    # 只认已审批的权益抵销分录（builder 内部再按 entry_type 筛 equity）
    approved_entries = await load_tree_entries(db, resolved_tree, year, approved_only=True)

    # 工作表 manual overrides（原样读出）
    rows = (await db.execute(
        sa.select(ConsolWorksheetData).where(
            ConsolWorksheetData.project_id == project_id,
            ConsolWorksheetData.year == year,
            ConsolWorksheetData.sheet_key.in_(_PROJECTION_SHEETS),
        )
    )).scalars().all()
    manual_overrides = {row.sheet_key: (row.data or {}) for row in rows}

    return build_post_elimination_projection(
        resolved_basis, approved_entries,
        subsidiary_codes=subsidiary_codes, root_code=root_code,
        manual_overrides=manual_overrides,
    )


def projection_to_dict(projection: PostEliminationProjection) -> dict[str, Any]:
    """DTO → 前端消费的 JSON（金额转字符串，保留分精度）。"""
    def account_json(acc: AccountElimination) -> dict[str, Any]:
        return {
            "account_prefix": acc.account_prefix,
            "label": acc.label,
            "total": str(acc.total),
            "unallocated": str(acc.unallocated),
            "balanced": acc.is_balanced(),
            "by_company": [
                {
                    "company_code": s.company_code,
                    "company_name": s.company_name,
                    "amount": str(s.amount),
                    "source_entry_ids": list(s.source_entry_ids),
                }
                for s in acc.by_company
            ],
            "warnings": list(acc.warnings),
        }

    return {
        "project_id": projection.project_id,
        "year": projection.year,
        "root_node_key": projection.root_node_key,
        "accounts": {prefix: account_json(acc) for prefix, acc in projection.accounts.items()},
        "manual_overrides": projection.manual_overrides,
        "warnings": list(projection.warnings),
    }
