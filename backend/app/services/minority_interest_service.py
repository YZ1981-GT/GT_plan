"""少数股东权益服务"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_

from app.models.consolidation_models import MinorityInterest
from app.models.consolidation_schemas import MinorityInterestResult


def get_mi_list(db, project_id: UUID, year: int) -> list[MinorityInterest]:
    return (
        db.query(MinorityInterest)
        .filter(
            MinorityInterest.project_id == project_id,
            MinorityInterest.year == year,
            MinorityInterest.is_deleted.is_(False),
        )
        .all()
    )


def get_mi(db, mi_id: UUID, project_id: UUID) -> MinorityInterest | None:
    return (
        db.query(MinorityInterest)
        .filter(MinorityInterest.id == mi_id, MinorityInterest.project_id == project_id)
        .first()
    )


def create_or_update_mi(
    db,
    project_id: UUID,
    year: int,
    company_code: str,
    data: MinorityInterestResult,
) -> MinorityInterest:
    existing = (
        db.query(MinorityInterest)
        .filter(
            MinorityInterest.project_id == project_id,
            MinorityInterest.year == year,
            MinorityInterest.subsidiary_company_code == company_code,
            MinorityInterest.is_deleted.is_(False),
        )
        .first()
    )

    if existing:
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(existing, key, value)
        mi = existing
    else:
        mi = MinorityInterest(
            project_id=project_id,
            year=year,
            subsidiary_company_code=company_code,
            **data.model_dump(),
        )
        db.add(mi)

    db.commit()
    db.refresh(mi)
    return mi


def calculate_mi(
    subsidiary_net_assets: Decimal | None,
    subsidiary_net_profit: Decimal | None,
    minority_share_ratio: Decimal | None,
    opening_equity: Decimal | None = None,
    equity_movement: dict | None = None,
) -> MinorityInterestResult:
    """计算少数股东权益"""
    if subsidiary_net_assets is None or minority_share_ratio is None:
        return MinorityInterestResult(
            year=0,
            subsidiary_company_code="",
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

    ratio = minority_share_ratio / Decimal("100")
    minority_equity = subsidiary_net_assets * ratio
    minority_profit = (subsidiary_net_profit * ratio) if subsidiary_net_profit else None

    # 检查超额亏损
    opening_mi = (opening_equity * ratio) if opening_equity else None
    excess_loss = Decimal("0")
    is_excess_loss = False
    if minority_profit and opening_mi and minority_profit < 0 and abs(minority_profit) > opening_mi:
        excess_loss = abs(minority_profit) - opening_mi
        is_excess_loss = True

    return MinorityInterestResult(
        year=0,
        subsidiary_company_code="",
        subsidiary_net_assets=subsidiary_net_assets,
        minority_share_ratio=minority_share_ratio,
        minority_equity=minority_equity,
        subsidiary_net_profit=subsidiary_net_profit,
        minority_profit=minority_profit,
        minority_equity_opening=opening_equity,
        minority_equity_movement=equity_movement,
        is_excess_loss=is_excess_loss,
        excess_loss_amount=excess_loss,
    )


def delete_mi(db, mi_id: UUID, project_id: UUID) -> bool:
    mi = get_mi(db, mi_id, project_id)
    if not mi:
        return False
    mi.is_deleted = True
    db.commit()
    return True
