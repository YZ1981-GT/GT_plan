"""四表联动穿透查询 API"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.models.audit_platform_models import AccountCategory
from app.models.audit_platform_schemas import (
    AuxBalanceRow,
    BalanceFilter,
    LedgerFilter,
    PageResult,
)
from app.services.drilldown_service import DrilldownService

router = APIRouter(
    prefix="/api/projects/{project_id}/drilldown",
    tags=["drilldown"],
)


@router.get("/balance")
async def get_balance_list(
    project_id: UUID,
    year: int = Query(..., description="审计年度"),
    category: AccountCategory | None = Query(None),
    level: int | None = Query(None),
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> PageResult:
    """科目余额表（分页+筛选）"""
    svc = DrilldownService(db)
    filters = BalanceFilter(
        category=category, level=level, keyword=keyword,
        year=year, page=page, page_size=page_size,
    )
    return await svc.get_balance_list(project_id, year, filters)


@router.get("/ledger/{account_code}")
async def drill_to_ledger(
    project_id: UUID,
    account_code: str,
    year: int = Query(..., description="审计年度"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    amount_min: Decimal | None = Query(None),
    amount_max: Decimal | None = Query(None),
    voucher_no: str | None = Query(None),
    summary_keyword: str | None = Query(None),
    counterpart_account: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> PageResult:
    """穿透到序时账"""
    svc = DrilldownService(db)
    filters = LedgerFilter(
        date_from=date_from, date_to=date_to,
        amount_min=amount_min, amount_max=amount_max,
        voucher_no=voucher_no, summary_keyword=summary_keyword,
        counterpart_account=counterpart_account,
        page=page, page_size=page_size,
    )
    return await svc.drill_to_ledger(project_id, year, account_code, filters)


@router.get("/aux-balance/{account_code}")
async def drill_to_aux_balance(
    project_id: UUID,
    account_code: str,
    year: int = Query(..., description="审计年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> list[AuxBalanceRow]:
    """穿透到辅助余额表"""
    svc = DrilldownService(db)
    return await svc.drill_to_aux_balance(project_id, year, account_code)


@router.get("/aux-ledger/{account_code}")
async def drill_to_aux_ledger(
    project_id: UUID,
    account_code: str,
    year: int = Query(..., description="审计年度"),
    aux_type: str | None = Query(None),
    aux_code: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> PageResult:
    """穿透到辅助明细账"""
    svc = DrilldownService(db)
    return await svc.drill_to_aux_ledger(
        project_id, year, account_code,
        aux_type=aux_type, aux_code=aux_code,
        page=page, page_size=page_size,
    )


# ------------------------------------------------------------------
# 凭证查询
# ------------------------------------------------------------------


@router.get("/voucher/{voucher_no}")
async def get_voucher_detail(
    project_id: UUID,
    voucher_no: str,
    year: int = Query(..., description="审计年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> dict:
    """按凭证号查询完整分录（借贷明细+合计+平衡状态）"""
    svc = DrilldownService(db)
    return await svc.get_voucher_detail(project_id, year, voucher_no)


@router.get("/vouchers")
async def list_vouchers(
    project_id: UUID,
    year: int = Query(..., description="审计年度"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    keyword: str | None = Query(None, description="凭证号或摘要关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> PageResult:
    """凭证列表（按凭证号分组聚合，支持大数据量分页）"""
    svc = DrilldownService(db)
    return await svc.list_vouchers(
        project_id, year,
        date_from=date_from, date_to=date_to,
        keyword=keyword,
        page=page, page_size=page_size,
    )


# ------------------------------------------------------------------
# 余额表↔序时账联动校验
# ------------------------------------------------------------------


@router.get("/verify-consistency")
async def verify_balance_ledger_consistency(
    project_id: UUID,
    year: int = Query(..., description="审计年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> dict:
    """校验余额表与序时账的一致性（发生额核对+期末公式校验）"""
    svc = DrilldownService(db)
    issues = await svc.verify_balance_ledger_consistency(project_id, year)
    return {
        "total_issues": len(issues),
        "is_consistent": len(issues) == 0,
        "issues": issues,
    }
