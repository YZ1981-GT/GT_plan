"""穿透查询 API 路由

高性能四表联查：余额→序时账→凭证、余额→辅助余额→辅助明细

- GET /api/projects/{id}/ledger/penetrate          — 统一穿透查询
- GET /api/projects/{id}/ledger/balance             — 科目余额
- GET /api/projects/{id}/ledger/entries/{code}      — 序时账明细
- GET /api/projects/{id}/ledger/voucher/{no}        — 凭证分录
- GET /api/projects/{id}/ledger/aux-balance/{code}  — 辅助余额
- GET /api/projects/{id}/ledger/aux-entries/{code}  — 辅助明细
- DELETE /api/projects/{id}/ledger/cache             — 清除缓存

Validates: Requirements 15.1-15.4
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.core.redis import get_redis
from app.services.ledger_penetration_service import LedgerPenetrationService

router = APIRouter(prefix="/api/projects/{project_id}/ledger", tags=["ledger-penetration"])


def _svc(db: AsyncSession, redis) -> LedgerPenetrationService:
    return LedgerPenetrationService(db, redis)


@router.get("/penetrate")
async def penetrate(
    project_id: UUID,
    year: int = Query(...),
    account_code: str | None = None,
    drill_level: str = "all",
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    page_size: int = 100,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """统一穿透查询（带缓存）"""
    svc = _svc(db, redis)
    return await svc.penetrate_cached(
        project_id, year, account_code, drill_level,
        date_from, date_to, page, page_size,
    )


@router.get("/balance")
async def get_balance(
    project_id: UUID,
    year: int = Query(...),
    account_code: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """科目余额汇总"""
    svc = _svc(db, None)
    return await svc.get_balance_summary(project_id, year, account_code)


@router.get("/entries/{account_code}")
async def get_ledger_entries(
    project_id: UUID,
    account_code: str,
    year: int = Query(...),
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    page_size: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """序时账明细（按科目穿透）"""
    svc = _svc(db, None)
    return await svc.get_ledger_entries(
        project_id, year, account_code, date_from, date_to, page, page_size,
    )


@router.get("/voucher/{voucher_no}")
async def get_voucher_entries(
    project_id: UUID,
    voucher_no: str,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """凭证分录明细（按凭证号穿透）"""
    svc = _svc(db, None)
    return await svc.get_voucher_entries(project_id, year, voucher_no)


@router.get("/aux-balance-all")
async def get_all_aux_balance(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """全量辅助余额（所有科目的辅助核算维度）"""
    svc = _svc(db, None)
    return await svc.get_all_aux_balance(project_id, year)


@router.get("/aux-balance/{account_code}")
async def get_aux_balance(
    project_id: UUID,
    account_code: str,
    year: int = Query(...),
    aux_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """辅助余额（按科目穿透到辅助维度）"""
    svc = _svc(db, None)
    return await svc.get_aux_balance(project_id, year, account_code, aux_type)


@router.get("/aux-entries/{account_code}")
async def get_aux_ledger_entries(
    project_id: UUID,
    account_code: str,
    year: int = Query(...),
    aux_type: str | None = None,
    aux_code: str | None = None,
    page: int = 1,
    page_size: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """辅助明细账（按辅助维度穿透）"""
    svc = _svc(db, None)
    return await svc.get_aux_ledger_entries(
        project_id, year, account_code, aux_type, aux_code, page, page_size,
    )


@router.delete("/cache")
async def clear_cache(
    project_id: UUID,
    year: int = Query(...),
    redis=Depends(get_redis),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """清除穿透查询缓存"""
    svc = _svc(db, redis)
    count = await svc.invalidate_cache(project_id, year)
    return {"cleared": count, "message": f"已清除 {count} 条缓存"}


@router.post("/upload")
async def upload_data(
    project_id: UUID,
    year: int = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传四表数据文件（支持历史年度）。

    自动识别 Excel 中的余额表/序时账/辅助账 sheet 并导入。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件")

    content = await file.read()
    from app.services.account_chart_service import _auto_import_data_sheets
    result, diagnostics = await _auto_import_data_sheets(
        project_id, content, year=year, db=db,
    )
    return {
        "imported": result,
        "diagnostics": diagnostics,
        "year": year,
        "file_name": file.filename,
    }


@router.get("/years")
async def get_available_years(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取该项目有数据的年度列表"""
    import sqlalchemy as sa
    from app.models.audit_platform_models import TbBalance
    tbl = TbBalance.__table__
    result = await db.execute(
        sa.select(sa.distinct(tbl.c.year))
        .where(tbl.c.project_id == project_id, tbl.c.is_deleted == sa.false())
        .order_by(tbl.c.year.desc())
    )
    years = [row[0] for row in result.fetchall()]
    return {"years": years}
