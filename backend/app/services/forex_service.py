"""外币折算服务"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_

from app.models.consolidation_models import ForexTranslation
from app.models.consolidation_schemas import (
    ForexRates,
    TranslationWorksheet,
    ForexTranslationResponse,
)


def get_forex_list(db, project_id: UUID, year: int) -> list[ForexTranslation]:
    return (
        db.query(ForexTranslation)
        .filter(
            ForexTranslation.project_id == project_id,
            ForexTranslation.year == year,
            ForexTranslation.is_deleted.is_(False),
        )
        .all()
    )


def get_forex(db, forex_id: UUID, project_id: UUID) -> ForexTranslation | None:
    return (
        db.query(ForexTranslation)
        .filter(ForexTranslation.id == forex_id, ForexTranslation.project_id == project_id)
        .first()
    )


def create_or_update_forex(
    db,
    project_id: UUID,
    company_code: str,
    year: int,
    functional_currency: str,
    reporting_currency: str = "CNY",
    rates: ForexRates | None = None,
    worksheet: TranslationWorksheet | None = None,
) -> ForexTranslation:
    existing = (
        db.query(ForexTranslation)
        .filter(
            ForexTranslation.project_id == project_id,
            ForexTranslation.year == year,
            ForexTranslation.company_code == company_code,
            ForexTranslation.is_deleted.is_(False),
        )
        .first()
    )

    if existing:
        if rates:
            existing.bs_closing_rate = rates.bs_closing_rate
            existing.pl_average_rate = rates.pl_average_rate
            existing.equity_historical_rate = rates.equity_historical_rate
        if worksheet:
            existing.opening_retained_earnings_translated = worksheet.opening_retained_earnings_translated
            existing.translation_difference = worksheet.translation_difference
            existing.translation_difference_oci = worksheet.translation_difference_oci
        forex = existing
    else:
        forex = ForexTranslation(
            project_id=project_id,
            year=year,
            company_code=company_code,
            functional_currency=functional_currency,
            reporting_currency=reporting_currency,
            bs_closing_rate=rates.bs_closing_rate if rates else None,
            pl_average_rate=rates.pl_average_rate if rates else None,
            equity_historical_rate=rates.equity_historical_rate if rates else None,
            opening_retained_earnings_translated=(
                worksheet.opening_retained_earnings_translated if worksheet else None
            ),
            translation_difference=worksheet.translation_difference if worksheet else None,
            translation_difference_oci=worksheet.translation_difference_oci if worksheet else None,
        )
        db.add(forex)

    db.commit()
    db.refresh(forex)
    return forex


def translate_amount(
    amount: Decimal, rate: Decimal | None, method: str = "bs"
) -> Decimal:
    """按汇率折算金额"""
    if rate is None or rate == 0:
        return amount
    if method == "bs":
        return amount * rate
    elif method == "pl":
        return amount * rate
    return amount  # equity uses historical, return as-is


def delete_forex(db, forex_id: UUID, project_id: UUID) -> bool:
    forex = get_forex(db, forex_id, project_id)
    if not forex:
        return False
    forex.soft_delete()
    db.commit()
    return True
