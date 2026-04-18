"""报表 API 路由

覆盖：
- POST /api/reports/generate — 生成/重新生成四张报表
- GET  /api/reports/{project_id}/{year}/consistency-check — 跨报表一致性校验
- GET  /api/reports/{project_id}/{year}/{report_type} — 获取指定报表数据
- GET  /api/reports/{project_id}/{year}/{report_type}/drilldown/{row_code} — 穿透查询
- GET  /api/reports/{project_id}/{year}/{report_type}/export-excel — 导出Excel

Validates: Requirements 2.1-2.10
"""

from __future__ import annotations

from io import BytesIO
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.models.report_models import FinancialReport, FinancialReportType
from app.models.report_schemas import (
    ReportGenerateRequest,
    ReportRow,
)
from app.services.report_engine import ReportEngine

router = APIRouter(
    prefix="/api/reports",
    tags=["reports"],
)


@router.post("/generate")
async def generate_reports(
    data: ReportGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """生成/重新生成四张报表"""
    engine = ReportEngine(db)
    try:
        results = await engine.generate_all_reports(data.project_id, data.year)
        await db.commit()
        return {
            "message": "报表生成成功",
            "report_types": list(results.keys()),
            "row_counts": {k: len(v) for k, v in results.items()},
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"报表生成失败: {str(e)}")


# NOTE: consistency-check MUST be defined BEFORE /{report_type} to avoid
# FastAPI matching "consistency-check" as a FinancialReportType enum value.


@router.get("/{project_id}/{year}/consistency-check")
async def consistency_check(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """跨报表一致性校验"""
    engine = ReportEngine(db)
    checks = await engine.check_balance(project_id, year)
    all_passed = all(c["passed"] for c in checks) if checks else True
    return {
        "all_passed": all_passed,
        "checks": checks,
    }


@router.get("/{project_id}/{year}/{report_type}")
async def get_report(
    project_id: UUID,
    year: int,
    report_type: FinancialReportType,
    unadjusted: bool = Query(False, description="是否返回未审报表数据"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定报表数据（支持未审/已审切换）"""
    if unadjusted:
        # 未审报表：动态计算，不存储
        engine = ReportEngine(db)
        try:
            rows = await engine.generate_unadjusted_report(project_id, year, report_type)
            return rows
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"未审报表生成失败: {str(e)}")

    result = await db.execute(
        sa.select(FinancialReport)
        .where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.report_type == report_type,
            FinancialReport.is_deleted == sa.false(),
        )
        .order_by(FinancialReport.row_code)
    )
    rows = result.scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="报表数据不存在，请先生成报表")
    return [ReportRow.model_validate(r) for r in rows]


@router.get("/{project_id}/{year}/{report_type}/drilldown/{row_code}")
async def drilldown_report_row(
    project_id: UUID,
    year: int,
    report_type: FinancialReportType,
    row_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """报表行穿透查询"""
    engine = ReportEngine(db)
    result = await engine.drilldown(project_id, year, report_type, row_code)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/{project_id}/{year}/{report_type}/export-excel")
async def export_report_excel(
    project_id: UUID,
    year: int,
    report_type: FinancialReportType,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出单张报表为 Excel"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        "report_export: user=%s project=%s year=%s type=%s",
        str(current_user.id), str(project_id), year, report_type.value,
    )
    result = await db.execute(
        sa.select(FinancialReport)
        .where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.report_type == report_type,
            FinancialReport.is_deleted == sa.false(),
        )
        .order_by(FinancialReport.row_code)
    )
    rows = result.scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="报表数据不存在")

    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = report_type.value

        # Header
        ws.append(["行次代码", "项目", "期末余额", "年初余额"])

        for row in rows:
            ws.append([
                row.row_code,
                row.row_name or "",
                float(row.current_period_amount) if row.current_period_amount else 0,
                float(row.prior_period_amount) if row.prior_period_amount else 0,
            ])

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"{report_type.value}_{year}.xlsx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl 未安装，无法导出 Excel")
