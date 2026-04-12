"""少数股东权益服务

功能覆盖：
- calculate：计算少数股东权益和少数股东损益（含超额亏损处理）
- batch_calculate：批量计算所有全额合并子公司的少数股东权益
- CRUD：create/get/update/delete minority_interest 记录
- 数据模型：minority_interest 表

公式：
- minority_share_ratio = 1 - parent_share_ratio
- minority_equity = subsidiary_net_assets × minority_share_ratio
- minority_profit = subsidiary_net_profit × minority_share_ratio

超额亏损处理（Requirement 5.7）：
- 若子公司累计亏损导致少数股东权益为负，
  且少数股东无义务承担超额亏损，则 cap minority_equity at 0
- is_excess_loss = True，excess_loss_amount 记录超额亏损金额
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models.audit_platform_models import TrialBalance
from app.models.consolidation_models import (
    Company,
    ConsolMethod,
    AccountCategory,
    MinorityInterest,
)
from app.models.consolidation_schemas import (
    EliminationEntryLine,
    MinorityInterestEliminationResponse,
    MinorityInterestCreate,
    MinorityInterestResult,
    MinorityInterestBatchResult,
    MinorityInterestUpdate,
)


# ---------------------------------------------------------------------------
# 核心计算
# ---------------------------------------------------------------------------

def calculate_minority_interest(
    subsidiary_net_assets: Decimal | None,
    subsidiary_net_profit: Decimal | None,
    minority_share_ratio: Decimal | None,
    opening_equity: Decimal | None = None,
    equity_movement: dict | None = None,
) -> MinorityInterestResult:
    """
    计算少数股东权益和少数股东损益。

    公式：
        minority_equity = subsidiary_net_assets × minority_share_ratio
        minority_profit = subsidiary_net_profit × minority_share_ratio

    超额亏损处理（Requirement 5.7）：
        若 minority_equity < 0 且少数股东无承担义务，则：
            is_excess_loss = True
            excess_loss_amount = abs(minority_equity)
            minority_equity = 0（不出现负数权益）

    参数：
        subsidiary_net_assets - 子公司净资产（从合并试算表取：资产总计 - 负债总计）
        subsidiary_net_profit - 子公司净利润（从合并试算表取：净利润行）
        minority_share_ratio  - 少数股东持股比例（小数，如 20% 传 0.20）
        opening_equity        - 期初少数股东权益（用于变动分析，可为 None）
        equity_movement       - 权益变动明细 dict，可包含：
            - profit_share: 本年少数股东损益
            - dividend: 本年少数股东分红（减少）
            - other_comprehensive: 其他综合收益归属
            - other: 其他变动

    返回：
        MinorityInterestResult（含计算值、超额亏损标识）
    """
    if subsidiary_net_assets is None or minority_share_ratio is None:
        return MinorityInterestResult(
            subsidiary_company_code="",
            year=0,
            subsidiary_net_assets=subsidiary_net_assets,
            minority_share_ratio=minority_share_ratio,
            minority_equity=None,
            subsidiary_net_profit=subsidiary_net_profit,
            minority_profit=None,
            minority_equity_opening=opening_equity,
            minority_equity_movement=equity_movement,
            is_excess_loss=False,
            excess_loss_amount=Decimal("0"),
        )

    # 少数股东权益 = 子公司净资产 × 少数股东持股比例
    raw_equity = subsidiary_net_assets * minority_share_ratio

    # 超额亏损处理：少数股东权益不低于 0（除非少数股东有承担义务）
    if raw_equity < 0:
        is_excess_loss = True
        excess_loss_amount = abs(raw_equity)
        minority_equity = Decimal("0")
    else:
        is_excess_loss = False
        excess_loss_amount = Decimal("0")
        minority_equity = raw_equity

    # 少数股东损益 = 子公司净利润 × 少数股东持股比例
    if subsidiary_net_profit is not None:
        minority_profit = subsidiary_net_profit * minority_share_ratio
    else:
        minority_profit = None

    return MinorityInterestResult(
        subsidiary_company_code="",
        year=0,
        subsidiary_net_assets=subsidiary_net_assets,
        minority_share_ratio=minority_share_ratio,
        minority_equity=minority_equity,
        subsidiary_net_profit=subsidiary_net_profit,
        minority_profit=minority_profit,
        minority_equity_opening=opening_equity,
        minority_equity_movement=equity_movement,
        is_excess_loss=is_excess_loss,
        excess_loss_amount=excess_loss_amount,
    )


def calculate_minority_share_ratio(
    db: Session, project_id: UUID, company_code: str
) -> Decimal | None:
    """
    根据公司代码从 companies 表查找 parent_share_ratio，
    返回 minority_share_ratio = 1 - parent_share_ratio。
    """
    company = (
        db.query(Company)
        .filter(
            Company.project_id == project_id,
            Company.company_code == company_code,
            Company.is_deleted.is_(False),
        )
        .first()
    )
    if company is None:
        return None
    parent_ratio = company.shareholding or Decimal("0")
    return Decimal("1") - parent_ratio / Decimal("100")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def get_minority_interest_list(
    db: Session, project_id: UUID, year: int
) -> list[MinorityInterest]:
    """获取指定项目和年度的全部少数股东权益记录"""
    return (
        db.query(MinorityInterest)
        .filter(
            MinorityInterest.project_id == project_id,
            MinorityInterest.year == year,
            MinorityInterest.is_deleted.is_(False),
        )
        .order_by(MinorityInterest.subsidiary_company_code)
        .all()
    )


def get_minority_interest(
    db: Session, mi_id: UUID, project_id: UUID
) -> MinorityInterest | None:
    """根据 ID 获取单条少数股东权益记录"""
    return (
        db.query(MinorityInterest)
        .filter(
            MinorityInterest.id == mi_id,
            MinorityInterest.project_id == project_id,
            MinorityInterest.is_deleted.is_(False),
        )
        .first()
    )


def get_minority_interest_by_company(
    db: Session, project_id: UUID, year: int, company_code: str
) -> MinorityInterest | None:
    """根据公司和年度获取少数股东权益记录"""
    return (
        db.query(MinorityInterest)
        .filter(
            MinorityInterest.project_id == project_id,
            MinorityInterest.year == year,
            MinorityInterest.subsidiary_company_code == company_code,
            MinorityInterest.is_deleted.is_(False),
        )
        .first()
    )


def create_minority_interest(
    db: Session,
    project_id: UUID,
    data: MinorityInterestCreate,
) -> MinorityInterest:
    """
    创建少数股东权益记录。

    - minority_equity / minority_profit 由 calculate_minority_interest 计算得到
    - 超额亏损时 minority_equity cap 为 0
    """
    result = calculate_minority_interest(
        subsidiary_net_assets=data.subsidiary_net_assets,
        subsidiary_net_profit=data.subsidiary_net_profit,
        minority_share_ratio=data.minority_share_ratio,
        opening_equity=data.minority_equity_opening,
        equity_movement=data.minority_equity_movement,
    )

    mi = MinorityInterest(
        project_id=project_id,
        year=data.year,
        subsidiary_company_code=data.subsidiary_company_code,
        subsidiary_net_assets=data.subsidiary_net_assets,
        minority_share_ratio=data.minority_share_ratio,
        minority_equity=result.minority_equity,
        subsidiary_net_profit=data.subsidiary_net_profit,
        minority_profit=result.minority_profit,
        minority_equity_opening=data.minority_equity_opening,
        minority_equity_movement=data.minority_equity_movement,
        is_excess_loss=result.is_excess_loss,
        excess_loss_amount=result.excess_loss_amount,
    )
    db.add(mi)
    db.commit()
    db.refresh(mi)
    return mi


def update_minority_interest(
    db: Session,
    mi_id: UUID,
    project_id: UUID,
    data: MinorityInterestUpdate,
) -> MinorityInterest | None:
    """
    更新少数股东权益记录。

    - 若 subsidiary_net_assets / subsidiary_net_profit / minority_share_ratio 变化，
      则重新执行 calculate_minority_interest
    - 超额亏损标识同步更新
    """
    mi = get_minority_interest(db, mi_id, project_id)
    if not mi:
        return None

    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(mi, key, value)

    # 若关键参数变化则重算
    recalc_keys = {"subsidiary_net_assets", "subsidiary_net_profit", "minority_share_ratio"}
    if any(k in changes for k in recalc_keys):
        net_assets = mi.subsidiary_net_assets
        net_profit = mi.subsidiary_net_profit
        ratio = mi.minority_share_ratio
        result = calculate_minority_interest(
            subsidiary_net_assets=net_assets,
            subsidiary_net_profit=net_profit,
            minority_share_ratio=ratio,
            opening_equity=mi.minority_equity_opening,
            equity_movement=mi.minority_equity_movement,
        )
        mi.minority_equity = result.minority_equity
        mi.minority_profit = result.minority_profit
        mi.is_excess_loss = result.is_excess_loss
        mi.excess_loss_amount = result.excess_loss_amount

    db.commit()
    db.refresh(mi)
    return mi


def delete_minority_interest(
    db: Session, mi_id: UUID, project_id: UUID
) -> bool:
    """软删除少数股东权益记录"""
    mi = get_minority_interest(db, mi_id, project_id)
    if not mi:
        return False
    mi.is_deleted = True
    db.commit()
    return True


# ---------------------------------------------------------------------------
# 批量计算（Requirement 5.5 + 5.7）
# ---------------------------------------------------------------------------

def batch_calculate(
    db: Session,
    project_id: UUID,
    year: int,
) -> MinorityInterestBatchResult:
    """
    批量计算所有全额合并子公司的少数股东权益。

    业务规则（Requirement 5.5）：
    - 从 companies 表筛选 consol_method = full 且 is_active = true 的子公司
    - 从 TrialBalance（Phase 1 各公司审定数）按 company_code 汇总净资产和净利润
      * 净资产 = 资产类别合计 - 负债类别合计（每个子公司单独计算）
      * 净利润 = "净利润"科目的 audited_amount（每个子公司单独计算）
    - minority_share_ratio = 1 - parent_share_ratio（从 companies 表读取）
    - 对每个子公司调用 calculate_minority_interest
    - 将结果写入 minority_interest 表（upsert 逻辑）

    返回： MinorityInterestBatchResult（含汇总数）
    """
    # 筛选全额合并子公司
    subsidiaries = (
        db.query(Company)
        .filter(
            Company.project_id == project_id,
            Company.consol_method == ConsolMethod.full,
            Company.is_active.is_(True),
            Company.is_deleted.is_(False),
        )
        .all()
    )

    results: list[MinorityInterestResult] = []
    total_mi_equity = Decimal("0")
    total_mi_profit = Decimal("0")

    for sub in subsidiaries:
        # 从 companies 表读取持股比例
        parent_ratio = sub.shareholding or Decimal("0")
        minority_ratio = Decimal("1") - parent_ratio / Decimal("100")

        # ---- 按子公司分别从 TrialBalance 汇总 ----
        # 资产合计（该子公司）
        asset_sum = (
            db.query(func.coalesce(func.sum(TrialBalance.audited_amount), Decimal("0")))
            .filter(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.company_code == sub.company_code,
                TrialBalance.account_category == AccountCategory.asset,
                TrialBalance.is_deleted.is_(False),
            )
            .scalar()
        ) or Decimal("0")

        # 负债合计（该子公司）
        liability_sum = (
            db.query(func.coalesce(func.sum(TrialBalance.audited_amount), Decimal("0")))
            .filter(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.company_code == sub.company_code,
                TrialBalance.account_category == AccountCategory.liability,
                TrialBalance.is_deleted.is_(False),
            )
            .scalar()
        ) or Decimal("0")

        # 净利润（该子公司，查找"净利润"科目行）
        net_profit = (
            db.query(TrialBalance.audited_amount)
            .filter(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.company_code == sub.company_code,
                TrialBalance.account_category == AccountCategory.equity,
                TrialBalance.account_name.like("%净利润%"),
                TrialBalance.is_deleted.is_(False),
            )
            .scalar()
        )
        if net_profit is None:
            # 尝试从利润表收入科目净额推算（备选：取"净利润"行）
            net_profit = (
                db.query(TrialBalance.audited_amount)
                .filter(
                    TrialBalance.project_id == project_id,
                    TrialBalance.year == year,
                    TrialBalance.company_code == sub.company_code,
                    TrialBalance.account_name.like("%净利润%"),
                    TrialBalance.is_deleted.is_(False),
                )
                .scalar()
            )

        net_assets = asset_sum - liability_sum

        # 查找期初少数股东权益（从上年记录）
        prior_year_mi = (
            db.query(MinorityInterest)
            .filter(
                MinorityInterest.project_id == project_id,
                MinorityInterest.year == year - 1,
                MinorityInterest.subsidiary_company_code == sub.company_code,
                MinorityInterest.is_deleted.is_(False),
            )
            .first()
        )
        opening_equity = prior_year_mi.minority_equity if prior_year_mi else None

        # 计算
        result = calculate_minority_interest(
            subsidiary_net_assets=net_assets,
            subsidiary_net_profit=net_profit,
            minority_share_ratio=minority_ratio,
            opening_equity=opening_equity,
        )
        result.subsidiary_company_code = sub.company_code
        result.year = year

        # Upsert：若已存在则更新，否则创建
        existing = get_minority_interest_by_company(db, project_id, year, sub.company_code)
        if existing:
            existing.subsidiary_net_assets = net_assets
            existing.subsidiary_net_profit = net_profit
            existing.minority_share_ratio = minority_ratio
            existing.minority_equity = result.minority_equity
            existing.minority_profit = result.minority_profit
            existing.minority_equity_opening = opening_equity
            existing.is_excess_loss = result.is_excess_loss
            existing.excess_loss_amount = result.excess_loss_amount
        else:
            mi = MinorityInterest(
                project_id=project_id,
                year=year,
                subsidiary_company_code=sub.company_code,
                subsidiary_net_assets=net_assets,
                minority_share_ratio=minority_ratio,
                minority_equity=result.minority_equity,
                subsidiary_net_profit=net_profit,
                minority_profit=result.minority_profit,
                minority_equity_opening=opening_equity,
                is_excess_loss=result.is_excess_loss,
                excess_loss_amount=result.excess_loss_amount,
            )
            db.add(mi)

        results.append(result)

        if result.minority_equity is not None:
            total_mi_equity += result.minority_equity
        if result.minority_profit is not None:
            total_mi_profit += result.minority_profit

    db.commit()
    return MinorityInterestBatchResult(
        results=results,
        total_minority_equity=total_mi_equity,
        total_minority_profit=total_mi_profit,
    )



# ---------------------------------------------------------------------------
# 生成少数股东权益/损益抵消分录（Requirement 5.8）
# ---------------------------------------------------------------------------


def generate_minority_elimination(
    db: Session,
    project_id: UUID,
    year: int,
    subsidiary_code: str,
) -> MinorityInterestEliminationResponse:
    """
    为指定子公司生成少数股东权益/损益抵消分录，并写入数据库。

    抵消逻辑（完全合并法，Requirement 5.8）：
        借：少数股东损益     （子公司净利润 × 少数股东持股比例）
        贷：少数股东权益     （期末少数股东权益 - 期初少数股东权益）

    仅在 minority_interest 表存在有效记录时才生成。
    若少数股东权益和损益均为零，跳过分录生成（返回 skipped=True）。

    参数：
        project_id       - 项目 ID
        year            - 年度
        subsidiary_code - 子公司代码

    返回：
        MinorityInterestEliminationResponse（含分录编号、行项、借贷金额）
    """
    from uuid import uuid4

    from app.models.consolidation_models import (
        EliminationEntry,
        EliminationEntryType,
        ReviewStatusEnum,
    )

    # 读取少数股东权益记录
    mi = get_minority_interest_by_company(db, project_id, year, subsidiary_code)
    if not mi:
        raise ValueError(f"未找到少数股东权益记录：{subsidiary_code}，year={year}")

    # 少数股东损益（净利润 × 少数股东持股比例）
    mi_profit = mi.minority_profit or Decimal("0")

    # 少数股东权益
    mi_equity = mi.minority_equity or Decimal("0")

    # 期初少数股东权益
    mi_equity_opening = mi.minority_equity_opening or Decimal("0")

    # 本期净增加 = 期末 - 期初（贷方）
    equity_increase = mi_equity - mi_equity_opening

    # 若贷方金额 < 借方，调整贷方以保证借贷平衡
    credit_total = equity_increase
    if credit_total < mi_profit:
        credit_total = mi_profit

    # 生成编号 CE-MI-{year}-XXX
    prefix = "CE-MI"
    last_entry = (
        db.query(EliminationEntry.entry_no)
        .filter(
            EliminationEntry.project_id == project_id,
            EliminationEntry.year == year,
            EliminationEntry.entry_no.like(f"{prefix}-{year}-%"),
            EliminationEntry.is_deleted.is_(False),
        )
        .order_by(EliminationEntry.entry_no.desc())
        .first()
    )
    seq = 1
    if last_entry:
        try:
            seq = int(last_entry[0].split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    entry_no = f"{prefix}-{year}-{seq:03d}"
    group_id = uuid4()

    description = f"少数股东权益/损益抵消（子公司 {subsidiary_code}，年度 {year}）"

    # 若少数股东权益和损益均为零，跳过写入
    if mi_profit == 0 and equity_increase == 0:
        return MinorityInterestEliminationResponse(
            entry_group_id=str(group_id),
            entry_no=entry_no,
            description=description,
            lines=[],
            minority_profit=str(mi_profit),
            minority_equity=str(mi_equity),
            minority_equity_opening=str(mi_equity_opening),
            total_debit="0",
            total_credit="0",
            skipped=True,
            reason="少数股东权益和损益均为零，无需生成抵消分录",
        )

    lines: list[EliminationEntryLine] = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")

    # 借方：少数股东损益
    if mi_profit > 0:
        lines.append(EliminationEntryLine(
            account_code="4104",
            account_name="少数股东损益",
            debit_amount=mi_profit,
            credit_amount=Decimal("0"),
        ))
        total_debit += mi_profit

    # 贷方：少数股东权益（本期净增加）
    if credit_total > 0:
        lines.append(EliminationEntryLine(
            account_code="3003",
            account_name="少数股东权益",
            debit_amount=Decimal("0"),
            credit_amount=credit_total,
        ))
        total_credit += credit_total

    # 借贷平衡校验（允许极小舍入误差 ≤ 0.01）
    diff = abs(total_debit - total_credit)
    if diff > Decimal("0.01"):
        raise ValueError(
            f"少数股东权益抵消分录借贷不平衡：借方={total_debit}, 贷方={total_credit}"
        )

    # 写入数据库（每行一条 EliminationEntry）
    for line in lines:
        db.add(EliminationEntry(
            project_id=project_id,
            year=year,
            entry_no=entry_no,
            entry_type=EliminationEntryType.equity,
            description=description,
            account_code=line.account_code,
            account_name=line.account_name,
            debit_amount=line.debit_amount,
            credit_amount=line.credit_amount,
            entry_group_id=group_id,
            related_company_codes=[subsidiary_code],
            is_continuous=False,
            review_status=ReviewStatusEnum.draft,
        ))

    db.commit()

    return MinorityInterestEliminationResponse(
        entry_group_id=str(group_id),
        entry_no=entry_no,
        description=description,
        lines=lines,
        minority_profit=str(mi_profit),
        minority_equity=str(mi_equity),
        minority_equity_opening=str(mi_equity_opening),
        total_debit=str(total_debit),
        total_credit=str(total_credit),
        skipped=False,
        reason=None,
    )
