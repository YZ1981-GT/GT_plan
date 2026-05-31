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

import json as _json
import logging
import uuid as _uuid
from datetime import datetime, timezone
from io import BytesIO
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.deps import require_project_access
from app.core.database import get_db
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


@router.post("/generate")
async def generate_consol_reports(
    data: ConsolReportGenerateRequest,
    project_id: UUID = Query(..., description="项目ID（用于权限校验）"),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("edit")),
):
    """生成合并报表"""
    try:
        # Phase 1 A3：generate_consol_reports_sync 已改 async（sync→async 统一），需 await。
        results = await generate_consol_reports_sync(db, data.project_id, data.year, data.applicable_standard)
        # 报表行由 service flush（未 commit）。按"service 只 flush，router 统一 commit"铁律，
        # 此处先 commit 让报表行持久化，再独立写审计 —— 确保审计失败回滚绝不波及已落库的报表。
        await db.commit()
        # 5D.2 / 需求 7.2：合并公式审计纳入 formula_audit_log（module='consol'）。
        # 与单体报表（report_config.py，module='report'）同源留痕。
        # 审计写入独立事务 + try/except，失败仅告警不影响报表生成主流程。
        await _write_consol_formula_audit(db, str(data.project_id), data.year, results)
        return {
            "message": "合并报表生成成功",
            "report_types": list(results.keys()),
            "row_counts": {k: len(v) for k, v in results.items()},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"合并报表生成失败: {str(e)}")


async def _write_consol_formula_audit(
    db: AsyncSession,
    project_id_str: str,
    year: int,
    results: dict[str, list[dict]],
) -> None:
    """将合并报表公式执行结果写入 formula_audit_log（module='consol'）。

    每个含公式的报表行写一条 action='execute' 记录，trace 记录 report_type，
    与单体报表 report_config.py 的留痕模式一致。

    前置：调用方已 commit 报表行 —— 故本函数内的 rollback 只会丢弃审计 INSERT，
    绝不波及已落库的报表（满足"审计失败不得破坏报表生成"约束）。
    """
    try:
        from app.routers.formula_audit_log import ensure_table as ensure_fal_table
        await ensure_fal_table(db)
        now = datetime.now(timezone.utc)
        for report_type, rows in results.items():
            for r in rows:
                formula_str = r.get("formula_used") or ""
                if not formula_str:
                    continue
                result_value = r.get("current_period_amount")
                try:
                    rv = float(result_value) if result_value is not None else None
                except (TypeError, ValueError):
                    rv = None
                await db.execute(
                    text(
                        """INSERT INTO formula_audit_log
                        (id, project_id, year, module, row_code, action, new_formula, result_value, trace, created_at)
                        VALUES (:id, :pid, :y, 'consol', :rc, 'execute', :nf, :rv, CAST(:tr AS jsonb), :now)"""
                    ),
                    {
                        "id": str(_uuid.uuid4()),
                        "pid": project_id_str,
                        "y": year,
                        "rc": r.get("row_code") or "",
                        "nf": formula_str,
                        "rv": rv,
                        "tr": _json.dumps(
                            {"report_type": report_type, "row_name": r.get("row_name", "")},
                            ensure_ascii=False,
                        ),
                        "now": now,
                    },
                )
        await db.commit()
    except Exception as exc:  # 审计失败不影响主流程（报表已 commit）
        logger.warning("合并公式审计写入 formula_audit_log 失败（不影响报表生成）: %s", exc)
        try:
            await db.rollback()
        except Exception:
            pass


@router.get("/{project_id}/{year}")
async def get_consol_report(
    project_id: UUID,
    year: int,
    report_type: FinancialReportType = Query(..., description="报表类型"),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    """获取合并报表数据"""
    result = await db.execute(
        sa.select(FinancialReport).where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.report_type == report_type,
            FinancialReport.is_deleted.is_(False),
        ).order_by(FinancialReport.row_code)
    )
    rows = list(result.scalars().all())

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


@router.get("/{project_id}/{year}/balance-check", response_model=BalanceCheckResult)
async def balance_check(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    """合并资产负债表平衡校验"""
    return await verify_balance_sync(db, project_id, year)


@router.post("/{project_id}/{year}/workpaper")
async def create_consol_workpaper(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("edit")),
):
    """生成合并底稿.xlsx"""
    try:
        result = await generate_consol_workpaper_sync(db, project_id, year)
        return {"message": "合并底稿生成成功", "file_name": result.file_name}
    except ImportError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成合并底稿失败: {str(e)}")


@router.get("/{project_id}/{year}/workpaper/download")
async def download_consol_workpaper(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    """下载合并底稿.xlsx"""
    try:
        result = await generate_consol_workpaper_sync(db, project_id, year)
        if not result.file_data:
            raise HTTPException(status_code=500, detail="未生成底稿文件")
        output = BytesIO(result.file_data)
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{result.file_name}"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载合并底稿失败: {str(e)}")
