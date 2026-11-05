"""CITAR「鉴证报告」四个菜单接口（spec citar-assurance-report-menus）。

前缀 ``/api/projects/{project_id}/tax-assurance``；读项目只读权限、写项目编辑权限。

- 汇算申报表：``tax-return/sheets/{code}``（GET 取值 / PUT 保存手工值与「是否填报」）、``tax-return/export``
- 报告正文：``report-body``（GET / PUT 报告日期）、``report-body/amounts``（PUT 摘录表金额手工值）、``report-body/export``、
  ``report-body/preview.pdf``（网页预览：OnlyOffice 转 PDF）
- 审核说明：``review-notes``（GET / PUT 段落人工修改）、``review-notes/export``
- 单体财务报表：``financial-statements``（GET / PUT 企业会计制度格式手工值）、``financial-statements/export``

任何写接口（申报表格子与是否填报、报告日期、摘录表金额、审核说明段落、单体报表金额）另需账号开通「允许修改」
（``manual_edit_permission``，spec citar-manual-edit-permission）。
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_user_scope_cycles, require_project_access
from app.models.core import User
from app.services import onlyoffice_pdf
from app.services import tax_workpaper_service as tws
from app.services.manual_edit_permission import assert_manual_edit
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


class ReviewNotesSaveBody(BaseModel):
    """``edits`` = {段落键: {"text": 正文 | null(删除), "auto": 修改时的自动正文}}。"""
    version: int = Field(..., ge=0)
    edits: dict[str, Any] = Field(default_factory=dict)


class FsSaveBody(BaseModel):
    """``values`` = {表 key: {行号: {current|prior: 金额 | null}}}。"""
    version: int = Field(..., ge=0)
    values: dict[str, Any] = Field(default_factory=dict)


class ReportBodyAmountsBody(BaseModel):
    """``version`` = 底稿 1-01 那一行的版本（``amounts_version``）；``values`` = {摘录表行号: 数字 | null}。"""
    version: int = Field(..., ge=0)
    values: dict[str, Any] = Field(default_factory=dict)


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
    assert_manual_edit(current_user)
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
    assert_manual_edit(current_user)
    await report_body.save_report_date(db, project_id, year, body.version, body.report_date, current_user.id)
    await db.commit()
    return await report_body.build(db, project_id, year)


@router.put("/report-body/amounts")
async def put_report_body_amounts(
    project_id: UUID, body: ReportBodyAmountsBody, year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """摘录表 25 行金额手工值（整份替换；不在 values 里的行恢复为公式值）。"""
    assert_manual_edit(current_user)
    await report_body.save_amounts(db, project_id, year, body.version, body.values, current_user.id)
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


@router.get("/report-body/preview.pdf")
async def preview_report_body_pdf(
    project_id: UUID, year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """网页预览：导出的 Word 经 OnlyOffice 转成 PDF，版式与 Word 一致。

    ``X-Preview-Missing-Fonts``：OnlyOffice 缺的字体（URL 编码、逗号分隔；空 = 齐全）。
    转换不可用返回 503，原因在 ``message``。
    """
    data = await report_body.build(db, project_id, year)
    try:
        result = await report_body.preview_pdf(data)
    except onlyoffice_pdf.ConvertError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(
        content=result.pdf,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "X-Preview-Cache": "hit" if result.cached else "miss",
            "X-Preview-Missing-Fonts": ",".join(quote(f, safe="") for f in result.missing_fonts),
        },
    )


# ── 审核说明 ──
@router.get("/review-notes")
async def get_review_notes(
    project_id: UUID, year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    return await review_notes.build(db, project_id, year)


@router.put("/review-notes")
async def put_review_notes(
    project_id: UUID, body: ReviewNotesSaveBody, year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """段落人工修改整份替换（text = null 即删除本段；不在 edits 里的段恢复自动文字）。"""
    assert_manual_edit(current_user)
    await review_notes.save_edits(db, project_id, year, body.version, body.edits, current_user.id)
    await db.commit()
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


@router.put("/financial-statements")
async def put_financial_statements(
    project_id: UUID, body: FsSaveBody, year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """企业会计制度格式手工值整份替换（企业会计准则格式改审定报表手工值 PUT /api/reports/{pid}/{year}/manual）。"""
    assert_manual_edit(current_user)
    await financial_statements.save_values(db, project_id, year, body.version, body.values, current_user.id)
    await db.commit()
    return await financial_statements.build(db, project_id, year, await _scope_codes(current_user, project_id, db))


@router.get("/financial-statements/export")
async def export_financial_statements(
    project_id: UUID, year: int = YearQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    data = await financial_statements.build(db, project_id, year, await _scope_codes(current_user, project_id, db), diagnose=False)
    content = exports.export_financial_statements(data)
    name = data.get("entity_name") or "被审核单位"
    return download(content, f"{name}_{year}年度财务报表.xlsx", XLSX_MEDIA)
