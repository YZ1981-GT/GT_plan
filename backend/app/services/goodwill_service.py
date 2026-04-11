"""商誉计算服务"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_

from app.models.consolidation_models import GoodwillCalc
from app.models.consolidation_schemas import GoodwillInput, GoodwillCalcResponse


def calculate_goodwill(
    acquisition_cost: Decimal | None,
    identifiable_net_assets_fv: Decimal | None,
    parent_share_ratio: Decimal | None,
) -> tuple[Decimal | None, bool, str | None]:
    """计算商誉/负商誉"""
    if acquisition_cost is None or identifiable_net_assets_fv is None or parent_share_ratio is None:
        return None, False, None

    goodwill = acquisition_cost - (identifiable_net_assets_fv * parent_share_ratio / Decimal("100"))
    is_negative = goodwill < 0
    treatment = None
    if is_negative:
        treatment = "计入损益" if abs(goodwill) < acquisition_cost * Decimal("0.25") else "递延收益摊销"
    return goodwill, is_negative, treatment


def get_goodwill_list(db, project_id: UUID, year: int) -> list[GoodwillCalc]:
    return (
        db.query(GoodwillCalc)
        .filter(
            GoodwillCalc.project_id == project_id,
            GoodwillCalc.year == year,
            GoodwillCalc.is_deleted.is_(False),
        )
        .all()
    )


def get_goodwill(db, goodwill_id: UUID, project_id: UUID) -> GoodwillCalc | None:
    return (
        db.query(GoodwillCalc)
        .filter(GoodwillCalc.id == goodwill_id, GoodwillCalc.project_id == project_id)
        .first()
    )


def create_goodwill(db, project_id: UUID, data: GoodwillInput) -> GoodwillCalc:
    goodwill_amount, is_negative, treatment = calculate_goodwill(
        data.acquisition_cost,
        data.identifiable_net_assets_fv,
        data.parent_share_ratio,
    )
    goodwill = GoodwillCalc(
        project_id=project_id,
        year=data.year,
        subsidiary_company_code=data.subsidiary_company_code,
        acquisition_date=data.acquisition_date,
        acquisition_cost=data.acquisition_cost,
        identifiable_net_assets_fv=data.identifiable_net_assets_fv,
        parent_share_ratio=data.parent_share_ratio,
        goodwill_amount=goodwill_amount,
        is_negative_goodwill=is_negative,
        negative_goodwill_treatment=treatment,
        accumulated_impairment=Decimal("0"),
        current_year_impairment=Decimal("0"),
    )
    db.add(goodwill)
    db.commit()
    db.refresh(goodwill)
    return goodwill


def update_goodwill(
    db, goodwill_id: UUID, project_id: UUID, data: GoodwillInput
) -> GoodwillCalc | None:
    goodwill = get_goodwill(db, goodwill_id, project_id)
    if not goodwill:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(goodwill, key, value)

    goodwill_amount, is_negative, treatment = calculate_goodwill(
        goodwill.acquisition_cost,
        goodwill.identifiable_net_assets_fv,
        goodwill.parent_share_ratio,
    )
    goodwill.goodwill_amount = goodwill_amount
    goodwill.is_negative_goodwill = is_negative
    goodwill.negative_goodwill_treatment = treatment

    db.commit()
    db.refresh(goodwill)
    return goodwill


def record_impairment(
    db, goodwill_id: UUID, project_id: UUID, impairment_amount: Decimal
) -> GoodwillCalc | None:
    goodwill = get_goodwill(db, goodwill_id, project_id)
    if not goodwill:
        return None
    goodwill.current_year_impairment = impairment_amount
    goodwill.accumulated_impairment = (goodwill.accumulated_impairment or Decimal("0")) + impairment_amount
    db.commit()
    db.refresh(goodwill)
    return goodwill


def delete_goodwill(db, goodwill_id: UUID, project_id: UUID) -> bool:
    goodwill = get_goodwill(db, goodwill_id, project_id)
    if not goodwill:
        return False
    goodwill.is_deleted = True
    db.commit()
    return True
