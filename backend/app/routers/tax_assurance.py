"""CITAR「鉴证报告」四个菜单接口（spec citar-assurance-report-menus）。

前缀 ``/api/projects/{project_id}/tax-assurance``；读项目只读权限、写项目编辑权限。

- 汇算申报表：``tax-return/sheets/{code}``（GET 取值 / PUT 保存手工值与「是否填报」）、``tax-return/export``
- 报告正文：``report-body``（GET / PUT 报告日期）、``report-body/export``
- 审核说明：``review-notes``、``review-notes/export``
- 单体财务报表：``financial-statements``、``financial-statements/export``
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_user_scope_cycles, require_project_access
from app.models.core import User
from app.services import tax_workpaper_service as tws
from app.services.mapping_service import get_codes_by_cycles
from app.services.tax_assurance import exports, financial_statements, report_body, review_notes
from app.services.tax_assurance.common import DOCX_MEDIA, XLSX_MEDIA, download

router = APIRouter(prefix="/api/projects/{project_id}/tax-assurance", tags=["税审鉴证报告"])

TAX_RETURN = "tax_return"
YearQuery = Query(..., ge=1990, le=2100)


class SheetSaveBody(BaseModel):
    version: int = Field(..., ge=0)
    inputs: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ReportBodySaveBody(BaseModel):
    version: int = Field(..., ge=0)
    report_date: str | None = Field(None, max_length=10)


async def _client_name(db: AsyncSession, project_id: UUID, year: int) -> str:
    params = await tws.get_params(db, project_id, year)
    for p in params["params"]:
        if p["ref"] == "B1" and p["value"]:
            return str(p["value"])
    return "被审核单位"


# ── 汇算申报表 ──
@router.get("/tax-return/sheets/{code}")
async def get_tax_return_sheet(
    project_id: UUID, code: str, year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    return await tws.compute_sheet(db, project_id, year, code, domain=TAX_RETURN)


@router.put("/tax-return/sheets/{code}")
async def put_tax_return_sheet(
    project_id: UUID, code: str, body: SheetSaveBody, year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    await tws.save_sheet_inputs(db, project_id, year, code, body.version, body.inputs, current_user.id, domain=TAX_RETURN)
    await db.commit()
    return await tws.compute_sheet(db, project_id, year, code, domain=TAX_RETURN)


@router.get("/tax-return/export")
async def export_tax_return(
    project_id: UUID, year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    content = await exports.export_tax_return(db, project_id, year)
    name = await _client_name(db, project_id, year)
    return download(content, f"{name}_{year}年度企业所得税年度纳税申报表.xlsx", XLSX_MEDIA)


# ── 报告正文 ──
@router.get("/report-body")
async def get_report_body(
    project_id: UUID, year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    return await report_body.build(db, project_id, year)


@router.put("/report-body")
async def put_report_body(
    project_id: UUID, body: ReportBodySaveBody, year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    await report_body.save_report_date(db, project_id, year, body.version, body.report_date, current_user.id)
    await db.commit()
    return await report_body.build(db, project_id, year)


@router.get("/report-body/export")
async def export_report_body(
    project_id: UUID, year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    data = await report_body.build(db, project_id, year)
    content = report_body.export_docx(data)
    return download(content, f"{data['cover']['client'] or '被审核单位'}_{year}年度企业所得税年度纳税申报审核报告.docx", DOCX_MEDIA)


# ── 审核说明 ──
@router.get("/review-notes")
async def get_review_notes(
    project_id: UUID, year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    return await review_notes.build(db, project_id, year)


@router.get("/review-notes/export")
async def export_review_notes(
    project_id: UUID, year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    data = await review_notes.build(db, project_id, year)
    content = review_notes.export_docx(data)
    name = await _client_name(db, project_id, year)
    return download(content, f"{name}_{year}年度企业所得税年度纳税申报审核报告说明.docx", DOCX_MEDIA)


# ── 单体财务报表 ──
async def _scope_codes(current_user: User, project_id: UUID, db: AsyncSession) -> set[str] | None:
    """受限成员只看分配给他的循环的科目（与试算平衡表页同口径）。"""
    cycles = await get_user_scope_cycles(current_user, project_id, db)
    if cycles is None:
        return None
    return set(await get_codes_by_cycles(project_id, cycles))


@router.get("/financial-statements")
async def get_financial_statements(
    project_id: UUID, year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    return await financial_statements.build(db, project_id, year, await _scope_codes(current_user, project_id, db))


@router.get("/financial-statements/export")
async def export_financial_statements(
    project_id: UUID, year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    data = await financial_statements.build(db, project_id, year, await _scope_codes(current_user, project_id, db))
    content = exports.export_financial_statements(data)
    name = data.get("entity_name") or "被审核单位"
    return download(content, f"{name}_{year}年度财务报表.xlsx", XLSX_MEDIA)
