"""表格单元格来源（悬浮溯源卡片，spec citar-cell-source-hover）。

每类表一个只读端点，一次返回整张表每格的来源；全部要求项目只读权限。
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_user_scope_cycles, require_project_access
from app.models.core import User
from app.models.report_models import FinancialReportType
from app.services.cell_source import fs as fs_src
from app.services.cell_source import ledger, report, tax_sheet, trial_balance
from app.services.mapping_service import get_codes_by_cycles

router = APIRouter(prefix="/api/projects/{project_id}/cell-sources", tags=["单元格来源"])

YearQuery = Query(..., ge=1990, le=2100)


@router.get("/tax-sheet/{code}")
async def get_tax_sheet_sources(
    project_id: UUID,
    code: str,
    year: int = YearQuery,
    domain: Literal["workpaper", "tax_return"] = Query("workpaper"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """税审底稿 / 汇算申报表一张表各格的来源（取数格、公式格、手工值格）。"""
    return await tax_sheet.sheet_sources(db, project_id, year, code, domain)


async def _scope_codes(user: User, project_id: UUID, db: AsyncSession) -> set[str] | None:
    """受限成员可见的标准科目（与试算表 GET 同口径）；None = 不限。"""
    cycles = await get_user_scope_cycles(user, project_id, db)
    return None if cycles is None else set(await get_codes_by_cycles(project_id, cycles))


@router.get("/trial-balance")
async def get_trial_balance_sources(
    project_id: UUID,
    year: int = YearQuery,
    company_code: str = Query("001"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """试算平衡表（审定科目余额表 / 底稿取数余额表）各格的来源。"""
    scope = await _scope_codes(current_user, project_id, db)
    return await trial_balance.trial_balance_sources(db, project_id, year, company_code, scope)


@router.get("/report/{report_type}")
async def get_report_sources(
    project_id: UUID,
    report_type: FinancialReportType,
    year: int = YearQuery,
    mode: Literal["audited", "unadjusted"] = Query("audited"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """审定报表 / 报表分析一张表各格的来源（本轮只接资产负债表与利润表）。"""
    if report_type not in report.REPORT_TYPES:
        raise HTTPException(status_code=422, detail="该报表暂不提供数据来源")
    return await report.report_sources(db, project_id, year, report_type, mode)


@router.get("/financial-statements")
async def get_financial_statement_sources(
    project_id: UUID,
    year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """单体财务报表各格的来源（受限成员与单体财务报表页同口径只算可见科目）。"""
    scope = await _scope_codes(current_user, project_id, db)
    return await fs_src.fs_sources(db, project_id, year, scope)


@router.get("/ledger/balance")
async def get_ledger_balance_sources(
    project_id: UUID,
    year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """科目余额表：各列取自导入文件哪个表头（字段映射）+ 有特殊情况的行（舍弃的多列映射值、辅助汇总、人工修改）。"""
    return await ledger.balance_sources(db, project_id, year)


@router.get("/ledger/journal")
async def get_ledger_journal_sources(
    project_id: UUID,
    year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """序时账各列取自导入文件哪个表头（行级按 journal-row 单取）。"""
    return await ledger.journal_sources(db, project_id, year)


@router.get("/ledger/journal-row/{row_id}")
async def get_ledger_journal_row_source(
    project_id: UUID,
    row_id: UUID,
    year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """序时账一行的来源；没有特殊情况时 ``cell`` 为 null。"""
    return {"cell": await ledger.journal_row_source(db, project_id, year, row_id)}
