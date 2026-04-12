"""合并报表 API 路由

覆盖:
- POST /api/consolidation/reports/generate              生成合并报表
- GET  /api/consolidation/reports/{project_id}/{year}   获取合并报表
- GET  /api/consolidation/reports/{project_id}/{year}/balance-check  平衡校验
- POST /api/consolidation/reports/{project_id}/{year}/workpaper       生成合并底稿
- GET  /api/consolidation/reports/{project_id}/{year}/workpaper/download 下载底稿

Validates: Phase 2 Requirements (合并报表)
"""

from __future__ import annotations

from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.deps import get_current_user
from app.core.database import get_sync_db
from app.models.consolidation_schemas import (
    BalanceCheckResult,
    ConsolDisclosureSection,
    ConsolReportGenerateRequest,
    ConsolReportRow,
)
from app.models.report_models import FinancialReport, FinancialReportType
from app.services.consol_report_service import (
    generate_consol_reports_sync,
    generate_consol_workpaper_sync,
    verify_balance_sync,
)


router = APIRouter(
    prefix="/api/consolidation/reports",
    tags=["合并报表"],
)


# ---------------------------------------------------------------------------
# 生成合并报表
# ---------------------------------------------------------------------------


@router.post("/generate")
def generate_consol_reports(
    data: ConsolReportGenerateRequest,
    db: Session = Depends(get_sync_db),
    user=Depends(get_current_user),
):
    """生成合并报表（资产负债表、利润表）

    复用 Phase 1 Report_Engine，数据源切换为 consol_trial.consol_amount
    新增商誉、少数股东权益、少数股东损益行次
    """
    try:
        results = generate_consol_reports_sync(
            db,
            data.project_id,
            data.year,
            data.applicable_standard,
        )
        return {
            "message": "合并报表生成成功",
            "report_types": list(results.keys()),
            "row_counts": {k: len(v) for k, v in results.items()},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"合并报表生成失败: {str(e)}")


@router.get("/{project_id}/{year}")
def get_consol_report(
    project_id: UUID,
    year: int,
    report_type: FinancialReportType = Query(..., description="报表类型: balance_sheet / income_statement"),
    db: Session = Depends(get_sync_db),
    user=Depends(get_current_user),
):
    """获取合并报表数据"""
    rows = (
        db.query(FinancialReport)
        .filter(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.report_type == report_type,
            FinancialReport.is_deleted.is_(False),
        )
        .order_by(FinancialReport.row_code)
        .all()
    )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"合并{report_type.value}不存在，请先生成合并报表",
        )

    return [
        ConsolReportRow(
            row_code=r.row_code or "",
            row_name=r.row_name or "",
            current_period_amount=r.current_period_amount or 0,
            prior_period_amount=r.prior_period_amount or 0,
            is_bold=False,
            is_total=False,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# 资产负债表平衡校验
# ---------------------------------------------------------------------------


@router.get("/{project_id}/{year}/balance-check", response_model=BalanceCheckResult)
def balance_check(
    project_id: UUID,
    year: int,
    db: Session = Depends(get_sync_db),
    user=Depends(get_current_user),
):
    """合并资产负债表平衡校验

    校验规则：资产总计 = 负债总计 + 所有者权益总计 + 少数股东权益
    """
    return verify_balance_sync(db, project_id, year)


# ---------------------------------------------------------------------------
# 合并底稿
# ---------------------------------------------------------------------------


@router.post("/{project_id}/{year}/workpaper")
def create_consol_workpaper(
    project_id: UUID,
    year: int,
    db: Session = Depends(get_sync_db),
    user=Depends(get_current_user),
):
    """生成合并底稿.xlsx"""
    try:
        result = generate_consol_workpaper_sync(db, project_id, year)
        return {
            "message": "合并底稿生成成功",
            "file_name": result.file_name,
        }
    except ImportError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成合并底稿失败: {str(e)}")


@router.get("/{project_id}/{year}/workpaper/download")
def download_consol_workpaper(
    project_id: UUID,
    year: int,
    db: Session = Depends(get_sync_db),
    user=Depends(get_current_user),
):
    """下载合并底稿.xlsx"""
    try:
        result = generate_consol_workpaper_sync(db, project_id, year)
        if not result.file_data:
            raise HTTPException(status_code=500, detail="未生成底稿文件")

        output = BytesIO(result.file_data)
        output.seek(0)

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{result.file_name}"
            },
        )
    except ImportError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载合并底稿失败: {str(e)}")
