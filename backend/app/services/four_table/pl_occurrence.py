"""损益类科目「本期发生额」取数（跨循环共享，四表取数唯一入口之一）。

**为什么不能用 `debit - credit`**

含年末「结转损益」分录的全年账上，损益类科目的借贷两侧金额**恒相等** —— 计提时
借（或贷）记 6xxx，年末结转时反向记同额到「本年利润」。活体逐行实证
（项目 ``005a6f2d``，``6601 销售费用`` 及其 40+ 子科目，**每一行**都成立）::

    account_code       debit_amount        credit_amount       debit - credit
    6601               163,042,014.46      163,042,014.46      0.00
    6601.01            37,189,411.65       37,189,411.65       0.00
    6601.01.06         26,492,879.05       26,492,879.05       0.00
    6601.11            42,997,579.18       42,997,579.18       0.00
    …（全部子科目同）                                            0.00

即 ``debit - credit`` 对损益类是**结构性恒零**，不是「这个项目恰好为 0」。
K8~K13 六个循环原先都写着 ``"audited_amount": debit - credit`` → 审定表
「与试算平衡表核对」列恒 0，有明细后显整额假差异。N4/N5 已修过同款，本模块是收敛点。

**权威口径 = `trial_balance`**

``report_config`` 的损益行公式读的就是它（``IS-022 销售费用 =
TB('6601','本期发生额')``，四准则一致），``recalc`` 已按发生额写好。活体实证
``6601 = 505,080,400.27`` / ``6602 = 72,957,201.11`` 均非 0。
``tb_balance`` 的**方向侧**发生额作兜底：费用类取 ``debit_amount``、
收益类取 ``credit_amount``（不做减法）。

**符号处理**

``trial_balance`` 中损益类符号在项目间不统一（实证 ``6117 其他收益`` 在项目
``005a6f2d`` 为 ``-146,477.91``、在 ``37814426`` 为 ``+15,712.56``；``6301``
同样正负并存）—— 「借正贷负」与「正数口径」两种约定并存。

裁决依据取自报表语义：``IS-010 加：其他收益`` 前置运算符是 ``+``，即报表期望
收益类以**正数**贡献 → 收益类按 :func:`normalize_for_report` 取绝对值。
费用类**保留原符号**（负值是合法的净冲回，翻正会掩盖真实业务）。
两种口径都输出，``raw_sign`` 留证，绝不静默丢弃原始符号。

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 3.1~3.4 / Property 5, 6, 7
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from enum import Enum

import sqlalchemy as sa

from .leaf_aggregation import LeafRow, filter_by_prefixes
from .tb_fetch import fetch_tb_balance_leaves

logger = logging.getLogger(__name__)

SOURCE_TRIAL_BALANCE = "trial_balance"
SOURCE_TB_BALANCE = "tb_balance"
SOURCE_NONE = "none"


class AccountNature(str, Enum):
    """损益类科目的增加方向。

    只有两个值 —— 资产负债类走 :mod:`leaf_aggregation` 取余额，不经本模块。
    """

    #: 借方增加（销售费用 6601 / 管理费用 6602 / 资产减值损失 6701 / 营业外支出 6711）
    EXPENSE = "expense"
    #: 贷方增加（其他收益 6117 / 营业外收入 6301）
    INCOME = "income"


@dataclass(frozen=True)
class PlOccurrence:
    """损益类发生额取数结果。

    Attributes:
        unadjusted: `trial_balance.unadjusted_amount` 合计（**原始符号**）。
        audited: `trial_balance.audited_amount` 合计（原始符号）。
        fallback_amount: `tb_balance` 叶子的方向侧发生额合计（费用取借方 / 收益取贷方）。
        leaf_total: 同 ``fallback_amount``，语义上供「明细行之和 == 汇总标量」自检。
        source: ``trial_balance`` / ``tb_balance`` / ``none`` —— 实际生效的口径。
        raw_sign: ``unadjusted`` 的原始符号（``-1`` / ``0`` / ``1``）。
        nature: 科目性质，供前端选列头文案（发生额 vs 余额）。
    """

    unadjusted: float = 0.0
    audited: float = 0.0
    fallback_amount: float = 0.0
    leaf_total: float = 0.0
    source: str = SOURCE_NONE
    raw_sign: int = 0
    nature: str = AccountNature.EXPENSE.value

    @property
    def report_unadjusted(self) -> float:
        """报表口径未审数（收益类取绝对值，费用类保留符号）。"""
        return normalize_for_report(self.effective_unadjusted, self.nature)

    @property
    def report_audited(self) -> float:
        """报表口径审定数。``trial_balance`` 缺失时退化为未审数（无 AJE 时二者相等）。"""
        base = self.audited if self.source == SOURCE_TRIAL_BALANCE else self.fallback_amount
        return normalize_for_report(base, self.nature)

    @property
    def effective_unadjusted(self) -> float:
        """实际生效的未审数（`trial_balance` 优先，缺失时用 `tb_balance` 兜底）。"""
        if self.source == SOURCE_TRIAL_BALANCE:
            return self.unadjusted
        return self.fallback_amount

    def as_dict(self) -> dict:
        """供 render 输出（前端消费）。"""
        out = asdict(self)
        out["report_unadjusted"] = self.report_unadjusted
        out["report_audited"] = self.report_audited
        out["effective_unadjusted"] = self.effective_unadjusted
        return out


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数（可独立单测，无 DB）
# ─────────────────────────────────────────────────────────────────────────────


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def pick_occurrence(debit: float, credit: float, nature: AccountNature | str) -> float:
    """按科目性质取**方向侧**发生额。

    🔴 **禁止** ``debit - credit`` —— 见模块 docstring 的逐行实证（恒零）。

    Args:
        debit: 借方发生额。
        credit: 贷方发生额。
        nature: :class:`AccountNature`（费用类取借方 / 收益类取贷方）。

    Returns:
        该方向的发生额。
    """
    nat = nature.value if isinstance(nature, AccountNature) else str(nature or "")
    return _f(credit) if nat == AccountNature.INCOME.value else _f(debit)


def normalize_for_report(amount: float, nature: AccountNature | str) -> float:
    """把原始符号归一为报表口径。

    收益类取绝对值（报表公式 ``加：其他收益`` 的前置符号是 ``+``，期望正数贡献；
    而 `trial_balance` 存在「借正贷负」与「正数口径」两种约定并存）；
    费用类**保留原符号**（负值 = 合法的净冲回）。
    """
    nat = nature.value if isinstance(nature, AccountNature) else str(nature or "")
    v = _f(amount)
    return abs(v) if nat == AccountNature.INCOME.value else v


def sum_longest_prefix_only(rows, wanted) -> float:
    """按**最长前缀**归属求和，防父子双计。

    `trial_balance` 中父码与子码可能并存（``2701`` 与 ``2701-01``、``6601`` 与
    ``6601-01``）；``LIKE '6601%'`` 会把父行与全部子行一并累加 ≈ 真值的 2 倍。
    本函数对每一行只归属到**最长**的命中前缀，同一行只被计一次。

    Args:
        rows: ``[(code, amount), ...]`` 序列。
        wanted: 目标前缀集（标准码）。

    Returns:
        归属到 ``wanted`` 的金额合计；无命中返 ``0.0``。
    """
    codes = [s for c in (wanted or []) if (s := str(c or "").strip())]
    if not codes:
        return 0.0
    total = 0.0
    for raw_code, amount in rows or []:
        code = str(raw_code or "").strip()
        if not code:
            continue
        best = ""
        for c in codes:
            if (code == c or code.startswith(c)) and len(c) > len(best):
                best = c
        if best:
            total += _f(amount)
    return total


def sum_leaf_occurrence(
    leaves: list[LeafRow], prefixes, nature: AccountNature | str
) -> float:
    """叶子科目的方向侧发生额合计（纯函数）。

    只汇总叶子（调用方须先 :func:`select_leaves`），前缀匹配要求点号边界。
    """
    picked = filter_by_prefixes(leaves, prefixes)
    return sum(pick_occurrence(r.debit, r.credit, nature) for r in picked)


def build_occurrence_prefill(
    leaves: list[LeafRow], prefixes, nature: AccountNature | str
) -> list[dict]:
    """按叶子科目建审定表行候选（损益口径）。

    返回 ``[{name, code, unadjusted, audited}]``，按金额绝对值降序。
    ``audited`` 初始等于 ``unadjusted``（无 AJE/RJE 时成立，审计师可改）。

    **宁缺勿造**：科目名为空或金额为零的叶子跳过；无命中返 ``[]``。

    🔴 不再输出 ``unadjustedDebit`` / ``unadjustedCredit`` 双列 —— 损益类
    ``debit == credit`` 恒成立，两列并列只会误导审计师以为有净额差异。
    """
    picked = filter_by_prefixes(leaves, prefixes)
    rows: list[dict] = []
    for r in picked:
        name = (r.account_name or "").strip()
        if not name:
            continue
        amount = normalize_for_report(pick_occurrence(r.debit, r.credit, nature), nature)
        if abs(amount) < 0.005:
            continue
        rows.append(
            {
                "name": name,
                "code": r.account_code,
                "unadjusted": amount,
                "audited": amount,
            }
        )
    rows.sort(key=lambda x: abs(x["unadjusted"]), reverse=True)
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# DB 访问（全程 fail-open）
# ─────────────────────────────────────────────────────────────────────────────


async def fetch_pl_leaves(ctx) -> list[LeafRow]:
    """取 active 数据集全部 `tb_balance` 行并筛出叶子（委托 :mod:`tb_fetch`）。"""
    return await fetch_tb_balance_leaves(ctx, label="损益取数")


async def fetch_trial_balance_occurrence(ctx, standard_codes) -> tuple[float, float, bool]:
    """按标准码取 `trial_balance` 未审/审定发生额（最长前缀归属）。

    Returns:
        ``(unadjusted, audited, hit)``。``hit`` 为 ``False`` 表示该科目在
        `trial_balance` 中不存在（**注意与「存在但为 0」区分** —— 后者 ``hit=True``，
        是合法的零发生额，不应回退兜底口径）。
    """
    codes = [s for c in (standard_codes or []) if (s := str(c or "").strip())]
    if not codes:
        return 0.0, 0.0, False
    try:
        result = await ctx.db.execute(
            sa.text(
                """
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                """
            ),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        rows = [
            (
                (r.standard_account_code or "").strip(),
                _f(r.unadjusted_amount),
                _f(r.audited_amount),
            )
            for r in result.fetchall()
        ]
    except Exception as e:  # noqa: BLE001
        logger.warning("损益取数: trial_balance 查询失败: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return 0.0, 0.0, False

    hit = any(
        code == c or code.startswith(c) for code, _u, _a in rows for c in codes
    )
    unadjusted = sum_longest_prefix_only([(c, u) for c, u, _a in rows], codes)
    audited = sum_longest_prefix_only([(c, a) for c, _u, a in rows], codes)
    return unadjusted, audited, hit


async def fetch_pl_occurrence(
    ctx,
    accounts,
    nature: AccountNature,
    *,
    leaves: list[LeafRow] | None = None,
) -> PlOccurrence:
    """损益类发生额取数（`trial_balance` 权威 + `tb_balance` 方向侧兜底）。

    Args:
        ctx: `RenderContext`（鸭子类型，只用 ``db`` / ``project_id`` / ``year``）。
        accounts: :class:`~.report_line_accounts.ReportLineAccounts` 解析结果。
        nature: 科目性质。
        leaves: 已取好的叶子行（同一 render 内多处取数时复用，避免重复全表扫）。

    Returns:
        :class:`PlOccurrence`；全程 fail-open，任何失败都返回可用结果。
    """
    rows = leaves if leaves is not None else await fetch_pl_leaves(ctx)
    fallback = sum_leaf_occurrence(rows, getattr(accounts, "gross", []) or [], nature)

    unadjusted, audited, hit = await fetch_trial_balance_occurrence(
        ctx, getattr(accounts, "gross_standard", []) or []
    )

    if hit:
        source = SOURCE_TRIAL_BALANCE
    elif abs(fallback) >= 0.005:
        source = SOURCE_TB_BALANCE
    else:
        source = SOURCE_NONE

    base = unadjusted if source == SOURCE_TRIAL_BALANCE else fallback
    raw_sign = 0 if abs(base) < 0.005 else (1 if base > 0 else -1)

    return PlOccurrence(
        unadjusted=unadjusted,
        audited=audited,
        fallback_amount=fallback,
        leaf_total=fallback,
        source=source,
        raw_sign=raw_sign,
        nature=nature.value if isinstance(nature, AccountNature) else str(nature),
    )


def build_pl_tb_values(occ: PlOccurrence) -> dict[str, float]:
    """把 :class:`PlOccurrence` 装配成前端 `tb_values`（键名沿用既有契约）。

    🔴 **方向列编码约定**：把本期发生额放**方向侧**列、对侧列置 ``0``。

    前端 6 个循环各自的 ``calcIncomeStatementOccurrence`` 算的是
    ``debit - credit``（费用类）/ ``credit - debit``（收益类）。后端原先两列
    喂的是 `tb_balance` 的原始借贷发生额，而损益类**两侧恒相等**（年末结转损益），
    故前端算出来恒为 0。改成「方向侧 = 发生额、对侧 = 0」后，前端同一段
    减法就得到正确结果 —— 无需等前端改造即可让审定表显示真实金额。

    对侧置 0 是**有依据的**：对侧发生额全部来自年末「结转损益」分录，
    不是业务上的冲回。真实的业务冲回体现在 `trial_balance` 的净额里
    （费用类为负即净冲回，见 :func:`normalize_for_report` 保留符号的原因）。

    Wave 4 会把审定表改成单一「本期发生额」列，届时 ``unadjusted_debit`` /
    ``unadjusted_credit`` 双列退役。
    """
    amount = occ.report_unadjusted
    is_income = occ.nature == AccountNature.INCOME.value
    return {
        "unadjusted_debit": 0.0 if is_income else amount,
        "unadjusted_credit": amount if is_income else 0.0,
        "audited_amount": occ.report_audited,
        "unadjusted_amount": amount,
        "occurrence_unadjusted": amount,
        "occurrence_audited": occ.report_audited,
        "occurrence_raw_sign": float(occ.raw_sign),
        "trial_balance_unadjusted": occ.unadjusted,
        "trial_balance_audited": occ.audited,
        "tb_balance_occurrence": occ.fallback_amount,
    }


async def build_pl_payload(ctx, spec) -> dict:
    """损益类循环的 render 载荷装配（K8~K13 六个循环共用）。

    Args:
        ctx: `RenderContext`。
        spec: :class:`~.k_cycle_specs.KCycleSpec`（必须是损益类，``nature`` 非 None）。

    Returns:
        ``{"tb_values", "adjudication_prefill", "tb_source_codes", "account_codes",
        "occurrence"}``。全程 fail-open。
    """
    from .report_line_accounts import (
        fetch_applicable_standards,
        resolve_report_line_accounts,
    )

    nature = spec.nature or AccountNature.EXPENSE
    standards = await fetch_applicable_standards(ctx)
    accounts = await resolve_report_line_accounts(ctx, spec.spec_for(standards))

    leaves = await fetch_pl_leaves(ctx)
    occ = await fetch_pl_occurrence(ctx, accounts, nature, leaves=leaves)

    source_codes = accounts.as_dict()
    source_codes["nature"] = nature.value
    source_codes["account_name"] = spec.account_name
    source_codes["occurrence_source"] = occ.source
    source_codes["occurrence_raw_sign"] = occ.raw_sign
    source_codes["empty_reason"] = None

    return {
        "tb_values": build_pl_tb_values(occ),
        "adjudication_prefill": build_occurrence_prefill(leaves, accounts.gross, nature),
        "tb_source_codes": source_codes,
        "account_codes": list(accounts.gross_standard),
        "occurrence": occ,
    }


__all__ = [
    "SOURCE_NONE",
    "SOURCE_TB_BALANCE",
    "SOURCE_TRIAL_BALANCE",
    "AccountNature",
    "PlOccurrence",
    "build_occurrence_prefill",
    "build_pl_payload",
    "build_pl_tb_values",
    "fetch_pl_leaves",
    "fetch_pl_occurrence",
    "fetch_trial_balance_occurrence",
    "normalize_for_report",
    "pick_occurrence",
    "sum_leaf_occurrence",
    "sum_longest_prefix_only",
]
