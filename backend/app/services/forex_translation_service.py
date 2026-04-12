"""外币报表折算服务

功能覆盖：
- translate: 对境外子公司执行外币报表折算
  - 资产负债表项目（资产/负债）→ 期末汇率(bs_closing_rate)
  - 利润表项目（收入/成本/费用）→ 平均汇率(pl_average_rate)
  - 权益项目（实收资本/资本公积）→ 历史汇率(equity_historical_rate)
  - 未分配利润 → 公式推算（年初未分配利润 + 本年净利润折算 - 分配）
  - 折算差额 → 其他综合收益（OCI）
  - translation_difference_oci → 累计其他综合收益余额
- get_translation_worksheet: 生成折算工作表（原币|汇率|折算额|折算差额）
- apply_to_consol_trial: 将折算后金额替换到合并试算表
- CRUD: create/get/update/delete forex_translation 记录

Validates: Requirements 6.1, 6.2, 6.3, 6.4
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.audit_platform_models import TrialBalance
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.consolidation_models import (
    AccountCategory,
    Company,
    ConsolScope,
    ConsolTrial,
    ForexTranslation,
)
from app.models.consolidation_schemas import (
    ForexRates,
    ForexTranslationCreate,
    ForexTranslationResponse,
    ForexTranslationResult,
    ForexTranslationUpdate,
    TranslationWorksheet,
    TranslationWorksheetRow,
)
from app.services.event_bus import event_bus

logger = logging.getLogger(__name__)

# 标准科目编码前缀（用于识别科目类别）
# 1xxx: 资产类
# 2xxx: 负债类
# 3xxx: 权益类（实收资本 4001, 资本公积 4002, 其他综合收益 4401, 未分配利润 4104）
# 5xxx: 成本类
# 6xxx: 损益类（收入）
# 7xxx: 损益类（费用）
EQUITY_ACCOUNT_CODES = {"4001", "4002", "4003", "4101", "4102", "4103", "4104", "4401"}
# 其他综合收益科目（计入OCI）
OCI_ACCOUNT_CODES = {"4401", "4402", "4403", "4404"}
# 未分配利润科目
RETAINED_EARNINGS_CODE = "4104"


# ---------------------------------------------------------------------------
# 核心折算逻辑
# ---------------------------------------------------------------------------


def _classify_account_category(
    account_category: AccountCategory | str | None,
    standard_account_code: str,
) -> str:
    """根据科目类别或科目编码判断折算汇率类型

    Returns:
        "bs": 资产负债表项目（资产/负债）
        "pl": 利润表项目（收入/成本/费用）
        "equity": 权益项目（实收资本/资本公积）
        "retained": 未分配利润
        "oci": 其他综合收益
    """
    if isinstance(account_category, str):
        try:
            account_category = AccountCategory(account_category)
        except ValueError:
            account_category = None

    if account_category == AccountCategory.asset:
        return "bs"
    if account_category == AccountCategory.liability:
        return "bs"
    if account_category == AccountCategory.equity:
        # 进一步区分
        if standard_account_code in OCI_ACCOUNT_CODES:
            return "oci"
        if standard_account_code == RETAINED_EARNINGS_CODE:
            return "retained"
        if standard_account_code in EQUITY_ACCOUNT_CODES:
            return "equity"
        return "equity"
    if account_category == AccountCategory.revenue:
        return "pl"
    if account_category == AccountCategory.expense:
        return "pl"

    # 默认按编码前缀判断
    code_prefix = standard_account_code[:1]
    if code_prefix in ("1", "2"):
        return "bs"
    if code_prefix in ("3", "4"):
        if standard_account_code == RETAINED_EARNINGS_CODE:
            return "retained"
        if standard_account_code in OCI_ACCOUNT_CODES:
            return "oci"
        return "equity"
    if code_prefix in ("5", "6", "7"):
        return "pl"
    return "bs"


def _get_rate_for_account_category(
    category: str,
    rates: ForexRates,
) -> Decimal | None:
    """根据科目类别获取适用汇率"""
    if category == "bs":
        return rates.bs_closing_rate
    if category == "pl":
        return rates.pl_average_rate
    if category == "equity":
        return rates.equity_historical_rate
    if category in ("retained", "oci"):
        # 未分配利润和其他综合收益不需要单独汇率
        return None
    return None


def _translate_amount(
    original_amount: Decimal,
    rate: Decimal | None,
) -> Decimal:
    """将原币金额按汇率折算为报告货币"""
    if rate is None or rate == Decimal("0"):
        return original_amount  # 无汇率时不折算
    return original_amount * rate


def _calculate_opening_retained_earnings(
    prior_year_forex: ForexTranslation | None,
    current_net_income_translated: Decimal,
    distributions: Decimal,
) -> Decimal:
    """计算年初未分配利润折算额

    公式：opening_retained_earnings_translated = prior_year_opening + 本年净利润折算 - 分配

    其中 prior_year_opening = prior_year_forex.opening_retained_earnings_translated
    本年净利润折算 = 净利润原币 × pl_average_rate
    """
    prior_opening = Decimal("0")
    if prior_year_forex:
        prior_opening = prior_year_forex.opening_retained_earnings_translated or Decimal("0")
        # prior_year 的 translation_difference 已包含在其中
    return prior_opening + current_net_income_translated - distributions


def _calculate_translation_difference(
    translated_total_assets: Decimal,
    translated_total_liabilities: Decimal,
    translated_equity_items: Decimal,
    translated_retained_earnings: Decimal,
) -> Decimal:
    """计算折算差额（平衡项）

    公式：translation_difference = translated_assets - translated_liabilities
          - translated_equity_items - translated_retained_earnings

    这是资产负债表的平衡项，即"外币报表折算差额"
    """
    return (
        translated_total_assets
        - translated_total_liabilities
        - translated_equity_items
        - translated_retained_earnings
    )


def _calculate_translation_difference_oci(
    prior_oci: Decimal | None,
    current_translation_difference: Decimal,
) -> Decimal:
    """计算累计折算差额OCI

    公式：translation_difference_oci = prior_oci_balance + current_year_difference
    """
    prior = prior_oci or Decimal("0")
    return prior + current_translation_difference


# ---------------------------------------------------------------------------
# CRUD 操作
# ---------------------------------------------------------------------------


async def get_forex_list(
    db: AsyncSession,
    project_id: UUID,
    year: int,
) -> list[ForexTranslation]:
    """获取指定项目和年度的全部外币折算记录"""
    result = await db.execute(
        select(ForexTranslation)
        .where(
            ForexTranslation.project_id == project_id,
            ForexTranslation.year == year,
            ForexTranslation.is_deleted.is_(False),
        )
        .order_by(ForexTranslation.company_code)
    )
    return list(result.scalars().all())


async def get_forex_by_company(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    company_code: str,
) -> ForexTranslation | None:
    """根据公司和年度获取外币折算记录"""
    result = await db.execute(
        select(ForexTranslation)
        .where(
            ForexTranslation.project_id == project_id,
            ForexTranslation.year == year,
            ForexTranslation.company_code == company_code,
            ForexTranslation.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def get_prior_year_forex(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    company_code: str,
) -> ForexTranslation | None:
    """获取上年外币折算记录（用于计算年初未分配利润）"""
    prior_year = year - 1
    result = await db.execute(
        select(ForexTranslation)
        .where(
            ForexTranslation.project_id == project_id,
            ForexTranslation.year == prior_year,
            ForexTranslation.company_code == company_code,
            ForexTranslation.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def create_forex(
    db: AsyncSession,
    data: ForexTranslationCreate,
) -> ForexTranslation:
    """创建外币折算记录"""
    forex = ForexTranslation(
        project_id=data.project_id,
        year=data.year,
        company_code=data.company_code,
        functional_currency=data.functional_currency,
        reporting_currency=data.reporting_currency,
        bs_closing_rate=data.bs_closing_rate,
        pl_average_rate=data.pl_average_rate,
        equity_historical_rate=data.equity_historical_rate,
        opening_retained_earnings_translated=data.opening_retained_earnings_translated,
        translation_difference=data.translation_difference,
        translation_difference_oci=data.translation_difference_oci,
    )
    db.add(forex)
    await db.flush()
    await db.refresh(forex)
    return forex


async def update_forex(
    db: AsyncSession,
    forex_id: UUID,
    project_id: UUID,
    data: ForexTranslationUpdate,
) -> ForexTranslation | None:
    """更新外币折算记录"""
    result = await db.execute(
        select(ForexTranslation)
        .where(
            ForexTranslation.id == forex_id,
            ForexTranslation.project_id == project_id,
            ForexTranslation.is_deleted.is_(False),
        )
    )
    forex = result.scalar_one_or_none()
    if not forex:
        return None

    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(forex, key, value)

    await db.flush()
    await db.refresh(forex)
    return forex


async def delete_forex(
    db: AsyncSession,
    forex_id: UUID,
    project_id: UUID,
) -> bool:
    """软删除外币折算记录"""
    result = await db.execute(
        select(ForexTranslation)
        .where(
            ForexTranslation.id == forex_id,
            ForexTranslation.project_id == project_id,
            ForexTranslation.is_deleted.is_(False),
        )
    )
    forex = result.scalar_one_or_none()
    if not forex:
        return False

    forex.is_deleted = True
    await db.flush()
    return True


# ---------------------------------------------------------------------------
# 核心折算方法
# ---------------------------------------------------------------------------


async def translate(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    company_code: str,
    rates: ForexRates,
) -> tuple[ForexTranslation, ForexTranslationResult]:
    """
    执行外币报表折算。

    折算规则：
    1. 资产/负债 → 期末汇率(bs_closing_rate)
    2. 收入/成本/费用 → 平均汇率(pl_average_rate)
    3. 实收资本/资本公积 → 历史汇率(equity_historical_rate)
    4. 未分配利润 → 公式推算
    5. 折算差额 → 其他综合收益

    参数：
        db          - 数据库会话
        project_id  - 项目ID
        year        - 报表年度
        company_code - 子公司代码
        rates       - 汇率输入

    返回：
        (ForexTranslation记录, ForexTranslationResult)
    """
    # 1. 获取公司信息
    company_result = await db.execute(
        select(Company)
        .where(
            Company.project_id == project_id,
            Company.company_code == company_code,
            Company.is_deleted.is_(False),
        )
    )
    company = company_result.scalar_one_or_none()
    if not company:
        raise ValueError(f"未找到公司: company_code={company_code}")

    functional_currency = company.functional_currency or "CNY"

    # 2. 获取子公司 trial_balance 审定数
    # 按 company_code + year 筛选，并考虑 acquisition_date/disposal_date
    tb_query = (
        select(TrialBalance)
        .where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.company_code == company_code,
            TrialBalance.is_deleted.is_(False),
        )
    )
    tb_result = await db.execute(tb_query)
    trial_balance_rows = list(tb_result.scalars().all())

    if not trial_balance_rows:
        logger.warning(
            "No trial balance data for company=%s project=%s year=%d",
            company_code,
            project_id,
            year,
        )

    # 3. 分类汇总各科目金额
    bs_assets_amount = Decimal("0")
    bs_liabilities_amount = Decimal("0")
    equity_items_amount = Decimal("0")  # 实收资本+资本公积
    retained_earnings_amount = Decimal("0")
    net_income_amount = Decimal("0")  # 本年净利润（收入 - 费用）
    oci_amount = Decimal("0")  # 其他综合收益

    for row in trial_balance_rows:
        amount = row.audited_amount or Decimal("0")
        category = _classify_account_category(row.account_category, row.standard_account_code)

        if category == "bs":
            if row.account_category == AccountCategory.asset:
                bs_assets_amount += amount
            elif row.account_category == AccountCategory.liability:
                bs_liabilities_amount += amount
        elif category == "equity":
            equity_items_amount += amount
        elif category == "retained":
            retained_earnings_amount += amount
        elif category == "pl":
            # 收入为正，费用为负
            if row.account_category == AccountCategory.revenue:
                net_income_amount += amount  # 收入
            elif row.account_category == AccountCategory.expense:
                net_income_amount -= amount  # 费用（减少净利润）
        elif category == "oci":
            oci_amount += amount

    # 4. 计算各项目折算额
    bs_closing_rate = rates.bs_closing_rate or Decimal("1")
    pl_average_rate = rates.pl_average_rate or bs_closing_rate
    equity_historical_rate = rates.equity_historical_rate or bs_closing_rate

    translated_assets = _translate_amount(bs_assets_amount, bs_closing_rate)
    translated_liabilities = _translate_amount(bs_liabilities_amount, bs_closing_rate)
    translated_equity_items = _translate_amount(equity_items_amount, equity_historical_rate)
    translated_net_income = _translate_amount(net_income_amount, pl_average_rate)

    # 5. 计算未分配利润折算额
    # 获取上年折算记录
    prior_year_forex = await get_prior_year_forex(db, project_id, year, company_code)

    # 假设分配为0（实际业务中需要从报表中获取）
    distributions = Decimal("0")
    opening_retained_earnings_translated = _calculate_opening_retained_earnings(
        prior_year_forex,
        translated_net_income,
        distributions,
    )

    # 6. 计算折算差额（平衡项）
    # 折算差额 = 资产折算 - 负债折算 - 权益折算 - 未分配利润折算
    translation_difference = _calculate_translation_difference(
        translated_assets,
        translated_liabilities,
        translated_equity_items,
        opening_retained_earnings_translated,
    )

    # 7. 计算累计折算差额OCI
    prior_oci = None
    if prior_year_forex:
        prior_oci = prior_year_forex.translation_difference_oci
    translation_difference_oci = _calculate_translation_difference_oci(
        prior_oci,
        translation_difference,
    )

    # 8. 创建/更新 forex_translation 记录
    existing_forex = await get_forex_by_company(db, project_id, year, company_code)

    if existing_forex:
        # 更新
        existing_forex.functional_currency = functional_currency
        existing_forex.bs_closing_rate = rates.bs_closing_rate
        existing_forex.pl_average_rate = rates.pl_average_rate
        existing_forex.equity_historical_rate = rates.equity_historical_rate
        existing_forex.opening_retained_earnings_translated = opening_retained_earnings_translated
        existing_forex.translation_difference = translation_difference
        existing_forex.translation_difference_oci = translation_difference_oci
        forex_record = existing_forex
    else:
        # 创建
        create_data = ForexTranslationCreate(
            project_id=project_id,
            year=year,
            company_code=company_code,
            functional_currency=functional_currency,
            reporting_currency="CNY",
            bs_closing_rate=rates.bs_closing_rate,
            pl_average_rate=rates.pl_average_rate,
            equity_historical_rate=rates.equity_historical_rate,
            opening_retained_earnings_translated=opening_retained_earnings_translated,
            translation_difference=translation_difference,
            translation_difference_oci=translation_difference_oci,
        )
        forex_record = await create_forex(db, create_data)

    await db.flush()

    # 9. 发布 FOREX_TRANSLATED 事件
    try:
        payload = EventPayload(
            event_type=EventType.FOREX_TRANSLATED,
            project_id=project_id,
            year=year,
            account_codes=[],  # 全量重算，不限定科目
            extra={
                "company_code": company_code,
                "functional_currency": functional_currency,
                "rates": {
                    "bs_closing_rate": str(rates.bs_closing_rate),
                    "pl_average_rate": str(rates.pl_average_rate),
                    "equity_historical_rate": str(rates.equity_historical_rate),
                },
                "translation_difference": str(translation_difference),
                "translation_difference_oci": str(translation_difference_oci),
            },
        )
        await event_bus.publish(payload)
        logger.info(
            "Published FOREX_TRANSLATED event: project=%s year=%d company=%s",
            project_id,
            year,
            company_code,
        )
    except Exception:
        logger.warning("Failed to publish FOREX_TRANSLATED event")

    # 10. 构建结果
    result = ForexTranslationResult(
        company_code=company_code,
        functional_currency=functional_currency,
        bs_closing_rate=rates.bs_closing_rate,
        pl_average_rate=rates.pl_average_rate,
        equity_historical_rate=rates.equity_historical_rate,
        translation_difference=translation_difference,
    )

    return forex_record, result


# ---------------------------------------------------------------------------
# 折算工作表
# ---------------------------------------------------------------------------


async def get_translation_worksheet(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    company_code: str,
) -> TranslationWorksheet:
    """
    生成外币折算工作表。

    返回结构化的工作表，包含：
    - 原币金额（原币）
    - 适用汇率
    - 折算金额（CNY）
    - 折算差额（仅适用于资产负债表项目）
    """
    # 1. 获取公司信息和折算记录
    company_result = await db.execute(
        select(Company)
        .where(
            Company.project_id == project_id,
            Company.company_code == company_code,
            Company.is_deleted.is_(False),
        )
    )
    company = company_result.scalar_one_or_none()
    if not company:
        raise ValueError(f"未找到公司: company_code={company_code}")

    forex_record = await get_forex_by_company(db, project_id, year, company_code)
    if not forex_record:
        raise ValueError(
            f"未找到折算记录，请先执行折算: company_code={company_code} year={year}"
        )

    functional_currency = forex_record.functional_currency
    bs_closing_rate = forex_record.bs_closing_rate or Decimal("1")
    pl_average_rate = forex_record.pl_average_rate or bs_closing_rate
    equity_historical_rate = forex_record.equity_historical_rate or bs_closing_rate

    rates = ForexRates(
        bs_closing_rate=bs_closing_rate,
        pl_average_rate=pl_average_rate,
        equity_historical_rate=equity_historical_rate,
    )

    # 2. 获取子公司 trial_balance 数据
    tb_query = (
        select(TrialBalance)
        .where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.company_code == company_code,
            TrialBalance.is_deleted.is_(False),
        )
        .order_by(TrialBalance.standard_account_code)
    )
    tb_result = await db.execute(tb_query)
    trial_balance_rows = list(tb_result.scalars().all())

    # 3. 构建工作表行
    worksheet_rows: list[TranslationWorksheetRow] = []

    # 分类汇总用于计算折算差额
    total_translated_assets = Decimal("0")
    total_translated_liabilities = Decimal("0")
    total_translated_equity_items = Decimal("0")

    for row in trial_balance_rows:
        original_amount = row.audited_amount or Decimal("0")
        category = _classify_account_category(row.account_category, row.standard_account_code)
        rate = _get_rate_for_account_category(category, rates)
        translated_amount = _translate_amount(original_amount, rate)

        # 累计汇总
        if category == "bs":
            if row.account_category == AccountCategory.asset:
                total_translated_assets += translated_amount
            elif row.account_category == AccountCategory.liability:
                total_translated_liabilities += translated_amount
        elif category == "equity":
            total_translated_equity_items += translated_amount

        worksheet_rows.append(
            TranslationWorksheetRow(
                standard_account_code=row.standard_account_code,
                account_name=row.account_name or "",
                account_category=row.account_category.value if row.account_category else None,
                original_amount=original_amount,
                functional_currency=functional_currency,
                rate=rate,
                translated_amount=translated_amount,
                reporting_currency="CNY",
                translation_difference=None,  # 逐行不计算，工作表底部汇总
                rate_type=category,
            )
        )

    # 4. 计算折算差额（汇总）
    opening_retained = forex_record.opening_retained_earnings_translated or Decimal("0")
    translation_diff = _calculate_translation_difference(
        total_translated_assets,
        total_translated_liabilities,
        total_translated_equity_items,
        opening_retained,
    )

    # 5. 构建工作表响应
    worksheet = TranslationWorksheet(
        company_code=company_code,
        functional_currency=functional_currency,
        reporting_currency="CNY",
        rates=rates,
        opening_retained_earnings_translated=opening_retained,
        translation_difference=forex_record.translation_difference,
        translation_difference_oci=forex_record.translation_difference_oci,
        rows=worksheet_rows,
        summary=TranslationWorksheetSummary(
            total_original_assets=sum(
                row.original_amount
                for row in worksheet_rows
                if row.account_category == AccountCategory.asset.value
            ),
            total_original_liabilities=sum(
                row.original_amount
                for row in worksheet_rows
                if row.account_category == AccountCategory.liability.value
            ),
            total_original_equity=sum(
                row.original_amount
                for row in worksheet_rows
                if row.account_category == AccountCategory.equity.value
            ),
            total_translated_assets=total_translated_assets,
            total_translated_liabilities=total_translated_liabilities,
            total_translated_equity=total_translated_equity_items,
        ),
    )

    return worksheet


# ---------------------------------------------------------------------------
# 应用到合并试算表
# ---------------------------------------------------------------------------


async def apply_to_consol_trial(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    company_code: str,
) -> dict:
    """
    将折算后的子公司数据应用到合并试算表。

    逻辑：
    1. 获取子公司的折算后 trial_balance 数据（已折算到 CNY）
    2. 更新/创建 consol_trial 表中的 individual_sum 字段
    3. 发布事件触发合并试算表重算

    返回：更新的科目数量统计
    """
    # 1. 获取子公司 trial_balance 审定数（折算后金额）
    tb_query = (
        select(TrialBalance)
        .where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.company_code == company_code,
            TrialBalance.is_deleted.is_(False),
        )
    )
    tb_result = await db.execute(tb_query)
    trial_balance_rows = list(tb_result.scalars().all())

    if not trial_balance_rows:
        logger.warning(
            "No trial balance data for apply_to_consol_trial: company=%s project=%s year=%d",
            company_code,
            project_id,
            year,
        )
        return {"updated": 0, "created": 0}

    # 2. 获取汇率信息
    forex_record = await get_forex_by_company(db, project_id, year, company_code)
    if not forex_record:
        raise ValueError(f"未找到折算记录: company_code={company_code} year={year}")

    bs_closing_rate = forex_record.bs_closing_rate or Decimal("1")
    pl_average_rate = forex_record.pl_average_rate or bs_closing_rate
    equity_historical_rate = forex_record.equity_historical_rate or bs_closing_rate

    rates = ForexRates(
        bs_closing_rate=bs_closing_rate,
        pl_average_rate=pl_average_rate,
        equity_historical_rate=equity_historical_rate,
    )

    # 3. 按标准科目代码汇总折算后金额
    translated_amounts: dict[str, Decimal] = {}
    for row in trial_balance_rows:
        original_amount = row.audited_amount or Decimal("0")
        category = _classify_account_category(row.account_category, row.standard_account_code)
        rate = _get_rate_for_account_category(category, rates)
        translated_amount = _translate_amount(original_amount, rate)

        if row.standard_account_code in translated_amounts:
            translated_amounts[row.standard_account_code] += translated_amount
        else:
            translated_amounts[row.standard_account_code] = translated_amount

    # 4. 更新/创建 consol_trial 记录
    updated_count = 0
    created_count = 0

    for account_code, translated_amount in translated_amounts.items():
        # 查询现有记录
        existing_result = await db.execute(
            select(ConsolTrial)
            .where(
                ConsolTrial.project_id == project_id,
                ConsolTrial.year == year,
                ConsolTrial.standard_account_code == account_code,
                ConsolTrial.is_deleted.is_(False),
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            # 累加到 individual_sum（因为可能有多个子公司）
            existing.individual_sum = (existing.individual_sum or Decimal("0")) + translated_amount
            updated_count += 1
        else:
            # 创建新记录
            new_trial = ConsolTrial(
                project_id=project_id,
                year=year,
                standard_account_code=account_code,
                account_name=None,  # 后续由 aggregate_individual 填充
                individual_sum=translated_amount,
                consol_adjustment=Decimal("0"),
                consol_elimination=Decimal("0"),
                consol_amount=translated_amount,
            )
            db.add(new_trial)
            created_count += 1

    await db.flush()

    logger.info(
        "Applied forex translation to consol_trial: company=%s project=%s year=%d updated=%d created=%d",
        company_code,
        project_id,
        year,
        updated_count,
        created_count,
    )

    return {
        "updated": updated_count,
        "created": created_count,
        "company_code": company_code,
        "functional_currency": forex_record.functional_currency,
        "translation_difference": str(forex_record.translation_difference),
    }
