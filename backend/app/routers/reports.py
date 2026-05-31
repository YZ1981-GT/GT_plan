"""报表 API 路由

覆盖：
- POST /api/reports/generate — 生成/重新生成四张报表
- GET  /api/reports/{project_id}/{year}/consistency-check — 跨报表一致性校验
- GET  /api/reports/{project_id}/{year}/{report_type} — 获取指定报表数据
- GET  /api/reports/{project_id}/{year}/{report_type}/drilldown/{row_code} — 穿透查询
- GET  /api/reports/{project_id}/{year}/{report_type}/export-excel — 导出Excel
- GET  /api/projects/{pid}/reports/line-composition?line_code={line_code} — 报表行构成科目

Validates: Requirements 2.1-2.10, F1.2
"""

from __future__ import annotations

from io import BytesIO
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access, check_consol_lock
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.core import User
from app.models.report_models import FinancialReport, FinancialReportType
from app.models.report_schemas import (
    ReportGenerateRequest,
    ReportRow,
)
from app.services.event_bus import event_bus
from app.services.report_engine import ReportEngine

router = APIRouter(
    prefix="/api/reports",
    tags=["reports"],
)


async def _resolve_applicable_standard(db: AsyncSession, project_id: UUID) -> str:
    """从项目配置动态确定报表标准（代理到服务层）。"""
    from app.services.report_config_service import ReportConfigService
    return await ReportConfigService.resolve_applicable_standard(db, project_id)


@router.post("/generate")
async def generate_reports(
    data: ReportGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """生成/重新生成四张报表"""
    from app.services.prerequisite_checker import PrerequisiteChecker

    # 合并锁定检查（project_id 在 body，显式调用反查）— Phase 1 Task 5
    await check_consol_lock(project_id=data.project_id, db=db)

    check = await PrerequisiteChecker().check(db, data.project_id, data.year, "generate_reports")
    if not check["ok"]:
        raise HTTPException(status_code=400, detail=check)

    # 从项目配置动态确定报表标准（国企/上市 × 合并/单体）
    applicable_standard = await _resolve_applicable_standard(db, data.project_id)

    engine = ReportEngine(db)
    try:
        results = await engine.generate_all_reports(data.project_id, data.year, applicable_standard)
        await db.commit()
        await event_bus.publish_immediate(EventPayload(
            event_type=EventType.REPORTS_UPDATED,
            project_id=data.project_id,
            year=data.year,
            extra={"report_types": list(results.keys())},
        ))

        # F23: 计算 summary 统计
        total_rows = sum(len(v) for v in results.values())
        non_zero_rows = 0
        for rows in results.values():
            for row in rows:
                amt = row.get("current_period_amount") if isinstance(row, dict) else None
                if amt is not None:
                    try:
                        if float(str(amt)) != 0:
                            non_zero_rows += 1
                    except (ValueError, TypeError):
                        pass

        return {
            "message": "报表生成成功",
            "report_types": list(results.keys()),
            "row_counts": {k: len(v) for k, v in results.items()},
            "summary": {
                "total_rows": total_rows,
                "non_zero_rows": non_zero_rows,
                "failed_rows": 0,
            },
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
    """公式审核——执行 logic_check + reasonability 类型公式校验"""
    applicable_standard = await _resolve_applicable_standard(db, project_id)
    engine = ReportEngine(db)
    checks = await engine.run_audit_checks(project_id, year, applicable_standard)

    logic_checks = [c for c in checks if c["category"] == "logic_check"]
    reason_checks = [c for c in checks if c["category"] == "reasonability"]
    all_passed = all(c["passed"] for c in checks) if checks else True

    return {
        "consistent": all_passed,
        "total": len(checks),
        "logic_check_count": len(logic_checks),
        "logic_check_passed": len([c for c in logic_checks if c["passed"]]),
        "reasonability_count": len(reason_checks),
        "reasonability_passed": len([c for c in reason_checks if c["passed"]]),
        "checks": [
            {
                "name": c["name"],
                "category": c["category"],
                "category_label": c["category_label"],
                "passed": c["passed"],
                "expected": c["expected"],
                "actual": c["actual"],
                "diff": c["diff"],
                "formula": c["formula"],
                "source": c["source"],
            }
            for c in checks
        ],
    }


@router.get("/{project_id}/{year}/{report_type}")
async def get_report(
    project_id: UUID,
    year: int,
    report_type: FinancialReportType,
    unadjusted: bool = Query(False, description="是否返回未审报表数据"),
    applicable_standard: str | None = Query(None, description="报表标准，如 soe_consolidated"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定报表数据（支持未审/已审切换+国企/上市切换）"""
    # 确定标准
    std = applicable_standard
    if not std:
        std = await _resolve_applicable_standard(db, project_id)

    if unadjusted:
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
        # 无已生成数据——返回该标准的模板行次结构（空值）
        from app.services.report_config_service import ReportConfigService
        svc = ReportConfigService(db)
        configs = await svc.list_configs(report_type=report_type, applicable_standard=std)
        if configs:
            return [
                ReportRow(
                    id=c.id, project_id=project_id, year=year,
                    report_type=report_type, row_code=c.row_code or '',
                    row_name=c.row_name or '', row_number=c.row_number or 0,
                    current_period_amount=None, prior_period_amount=None,
                    indent_level=c.indent_level or 0, is_total_row=c.is_total_row or False,
                    formula_used=c.formula or '',
                )
                for c in configs
            ]
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


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 3 F1.2: 报表行构成科目 API（项目级路由）
# ═══════════════════════════════════════════════════════════════════════════════

from pydantic import BaseModel

from app.models.audit_platform_models import ReportLineMapping, TbBalance


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 4 F2: 多年度对比分析 API
# ═══════════════════════════════════════════════════════════════════════════════

multi_year_router = APIRouter(
    prefix="/api/projects/{project_id}/reports",
    tags=["multi-year-compare"],
)


class MultiYearRow(BaseModel):
    """多年度对比行"""
    line_code: str
    item_name: str
    values: dict[str, float | None]  # year -> amount
    yoy_changes: dict[str, float | None]  # year -> change_pct


class MultiYearResponse(BaseModel):
    """多年度对比响应"""
    years: list[int]
    report_type: str
    rows: list[MultiYearRow]


def _calc_yoy(current: float | None, previous: float | None) -> float | None:
    """计算同比变动率: (current - previous) / abs(previous) * 100

    处理除零: previous 为 0 或 None 时返回 None
    """
    if current is None or previous is None:
        return None
    if previous == 0:
        return None
    return round((current - previous) / abs(previous) * 100, 2)


@multi_year_router.get("/multi-year", response_model=MultiYearResponse)
async def get_multi_year_report(
    project_id: UUID,
    years: str = Query(..., description="逗号分隔的年度列表，如 2023,2024,2025"),
    report_type: FinancialReportType = Query(..., description="报表类型"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """多年度对比查询 API

    查询同一项目不同年度的报表数据，计算 YoY 变动率。
    最多支持 5 年并列。

    Requirements: F2.1~F2.4
    """
    # 解析年度列表
    try:
        year_list = sorted([int(y.strip()) for y in years.split(",") if y.strip()])
    except ValueError:
        raise HTTPException(status_code=400, detail="年度参数格式错误，请使用逗号分隔的数字")

    if len(year_list) < 1:
        raise HTTPException(status_code=400, detail="至少需要选择 1 个年度")
    if len(year_list) > 5:
        raise HTTPException(status_code=400, detail="最多支持 5 年对比")

    # 查询所有年度的报表数据
    result = await db.execute(
        sa.select(FinancialReport)
        .where(
            FinancialReport.project_id == project_id,
            FinancialReport.year.in_(year_list),
            FinancialReport.report_type == report_type,
            FinancialReport.is_deleted == sa.false(),
        )
        .order_by(FinancialReport.row_code, FinancialReport.year)
    )
    all_rows = result.scalars().all()

    # 按 row_code 分组
    row_map: dict[str, dict[int, FinancialReport]] = {}
    row_names: dict[str, str] = {}
    row_order: list[str] = []

    for row in all_rows:
        code = row.row_code
        if code not in row_map:
            row_map[code] = {}
            row_order.append(code)
        row_map[code][row.year] = row
        if code not in row_names:
            row_names[code] = row.row_name or code

    # 构建响应
    response_rows: list[MultiYearRow] = []
    for code in row_order:
        year_data = row_map[code]
        values: dict[str, float | None] = {}
        yoy_changes: dict[str, float | None] = {}

        for yr in year_list:
            report_row = year_data.get(yr)
            amount = float(report_row.current_period_amount) if report_row and report_row.current_period_amount is not None else None
            values[str(yr)] = amount

        # 计算 YoY（从第二年开始）
        for i in range(1, len(year_list)):
            current_yr = year_list[i]
            prev_yr = year_list[i - 1]
            current_val = values.get(str(current_yr))
            prev_val = values.get(str(prev_yr))
            yoy_changes[str(current_yr)] = _calc_yoy(current_val, prev_val)

        response_rows.append(MultiYearRow(
            line_code=code,
            item_name=row_names[code],
            values=values,
            yoy_changes=yoy_changes,
        ))

    return MultiYearResponse(
        years=year_list,
        report_type=report_type.value,
        rows=response_rows,
    )


line_composition_router = APIRouter(
    prefix="/api/projects/{project_id}/reports",
    tags=["report-line-composition"],
)


class LineCompositionAccount(BaseModel):
    """构成科目条目"""
    code: str
    name: str
    closing_balance: float
    pct: float


class LineCompositionResponse(BaseModel):
    """报表行构成科目响应"""
    line_code: str
    item_name: str
    total_amount: float
    accounts: list[LineCompositionAccount]


@line_composition_router.get("/line-composition", response_model=LineCompositionResponse)
async def get_line_composition(
    project_id: UUID,
    line_code: str = Query(..., description="报表行次代码，如 BS-001"),
    year: int | None = Query(None, description="年度，默认取最新年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """查询报表行的构成科目列表。

    根据 report_line_mapping 获取该行对应的科目编号列表，
    再查询 tb_balance 获取各科目余额，计算各科目占比(pct)，
    按金额降序返回。

    Requirements: F1.2
    """
    # 1. 确定年度：如果未指定，取该项目 tb_balance 最新年度
    if year is None:
        year_result = await db.execute(
            sa.select(sa.func.max(TbBalance.year)).where(
                TbBalance.project_id == project_id,
                TbBalance.is_deleted == sa.false(),
            )
        )
        year = year_result.scalar_one_or_none()
        if year is None:
            raise HTTPException(
                status_code=404,
                detail="该项目无试算平衡表数据",
            )

    # 2. 查询 report_line_mapping 获取该行对应的科目编号列表
    mapping_result = await db.execute(
        sa.select(ReportLineMapping).where(
            ReportLineMapping.project_id == project_id,
            ReportLineMapping.report_line_code == line_code,
            ReportLineMapping.is_deleted == sa.false(),
            ReportLineMapping.is_confirmed == sa.true(),
        )
    )
    mappings = mapping_result.scalars().all()

    if not mappings:
        raise HTTPException(
            status_code=404,
            detail=f"报表行 '{line_code}' 无映射科目",
        )

    # 获取行次名称（取第一条映射的 report_line_name）
    item_name = mappings[0].report_line_name

    # 提取所有科目编号
    account_codes = list({m.standard_account_code for m in mappings})

    # 3. 查询 tb_balance 获取各科目余额
    tb_result = await db.execute(
        sa.select(TbBalance).where(
            TbBalance.project_id == project_id,
            TbBalance.year == year,
            TbBalance.account_code.in_(account_codes),
            TbBalance.is_deleted == sa.false(),
        )
    )
    tb_rows = tb_result.scalars().all()

    # 4. 计算总金额和各科目占比
    accounts: list[LineCompositionAccount] = []
    total_amount = 0.0

    for tb in tb_rows:
        balance = float(tb.closing_balance) if tb.closing_balance is not None else 0.0
        total_amount += abs(balance)

    # 按金额绝对值降序排列，计算占比
    for tb in sorted(tb_rows, key=lambda t: abs(float(t.closing_balance) if t.closing_balance is not None else 0.0), reverse=True):
        balance = float(tb.closing_balance) if tb.closing_balance is not None else 0.0
        pct = (abs(balance) / total_amount * 100.0) if total_amount != 0 else 0.0
        accounts.append(LineCompositionAccount(
            code=tb.account_code,
            name=tb.account_name or "",
            closing_balance=balance,
            pct=round(pct, 1),
        ))

    # total_amount 使用实际余额之和（非绝对值），用于显示
    actual_total = sum(
        float(tb.closing_balance) if tb.closing_balance is not None else 0.0
        for tb in tb_rows
    )

    return LineCompositionResponse(
        line_code=line_code,
        item_name=item_name,
        total_amount=actual_total,
        accounts=accounts,
    )
