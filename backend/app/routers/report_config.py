"""报表格式配置 API

覆盖：
- GET  列表（按 report_type / applicable_standard 筛选）
- GET  详情
- POST 克隆标准配置到项目
- PUT  修改配置行
- POST 加载种子数据
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.report_models import FinancialReportType, ReportConfig
from app.models.report_schemas import ReportConfigCloneRequest, ReportConfigRow
from app.services.report_config_service import ReportConfigService

router = APIRouter(
    prefix="/api/report-config",
    tags=["report-config"],
)


@router.get("")
async def list_report_configs(
    report_type: FinancialReportType | None = Query(None),
    applicable_standard: str | None = Query(None),
    project_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询报表配置列表。
    
    优先级：applicable_standard 显式传入 > 从 project_id 自动解析 > 降级 enterprise
    """
    if not applicable_standard and project_id:
        applicable_standard = await ReportConfigService.resolve_applicable_standard(db, project_id)
    if not applicable_standard:
        applicable_standard = "enterprise"
    svc = ReportConfigService(db)
    rows = await svc.list_configs(
        report_type=report_type,
        applicable_standard=applicable_standard,
    )
    return [ReportConfigRow.model_validate(r) for r in rows]


@router.get("/{config_id}")
async def get_report_config(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询单行配置详情"""
    svc = ReportConfigService(db)
    row = await svc.get_config(config_id)
    if row is None:
        raise HTTPException(status_code=404, detail="配置行不存在")
    return ReportConfigRow.model_validate(row)


@router.post("/clone")
async def clone_report_config(
    data: ReportConfigCloneRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """克隆标准配置到项目"""
    svc = ReportConfigService(db)
    try:
        count = await svc.clone_report_config(
            project_id=data.project_id,
            applicable_standard=data.applicable_standard,
        )
        await db.commit()
        return {"message": f"成功克隆 {count} 行配置", "count": count}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{config_id}")
async def update_report_config(
    config_id: UUID,
    updates: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """修改配置行"""
    svc = ReportConfigService(db)
    try:
        row = await svc.update_config(config_id, updates, user_id=current_user.id)
        await db.commit()
        return ReportConfigRow.model_validate(row)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("")
async def create_report_config(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新增配置行"""
    rc = ReportConfig(
        report_type=FinancialReportType(body["report_type"]),
        row_number=body.get("row_number", 0),
        row_code=body.get("row_code", ""),
        row_name=body.get("row_name", ""),
        indent_level=body.get("indent_level", 0),
        formula=body.get("formula"),
        applicable_standard=body.get("applicable_standard", "enterprise"),
        is_total_row=body.get("is_total_row", False),
        parent_row_code=body.get("parent_row_code"),
    )
    db.add(rc)
    await db.flush()
    await db.commit()
    return ReportConfigRow.model_validate(rc)


@router.delete("/{config_id}")
async def delete_report_config(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除配置行"""
    import sqlalchemy as sa
    result = await db.execute(
        sa.select(ReportConfig).where(ReportConfig.id == config_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="行不存在")
    row.is_deleted = True
    await db.commit()
    return {"deleted": True}


@router.post("/seed")
async def load_seed_data(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """加载种子数据"""
    svc = ReportConfigService(db)
    count = await svc.load_seed_data()
    await db.commit()
    return {"message": f"成功加载 {count} 行种子数据", "count": count}


@router.post("/batch-update")
async def batch_update_report_config(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量更新报表行的金额（从试算平衡表审定数回填）"""
    import sqlalchemy as sa

    project_id = body.get("project_id")
    report_type_str = body.get("report_type", "balance_sheet")
    applicable_standard = body.get("applicable_standard", "soe_consolidated")
    updates = body.get("updates", [])

    if not project_id or not updates:
        return {"updated": 0, "message": "无数据"}

    try:
        report_type = FinancialReportType(report_type_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的报表类型: {report_type_str}")

    updated = 0
    for upd in updates:
        row_code = upd.get("row_code")
        amount = upd.get("current_period_amount")
        if not row_code or amount is None:
            continue

        result = await db.execute(
            sa.select(ReportConfig).where(
                ReportConfig.report_type == report_type,
                ReportConfig.applicable_standard == applicable_standard,
                ReportConfig.row_code == row_code,
                ReportConfig.is_deleted == sa.false(),
            )
        )
        row = result.scalar_one_or_none()
        if row:
            row.current_period_amount = float(amount)
            updated += 1

    if updated:
        await db.commit()

    return {"updated": updated, "message": f"已更新 {updated} 行"}


@router.post("/drill-down")
async def report_drill_down(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """汇总穿透：查询各子企业在指定报表行次的实际金额

    请求体:
      project_id: 项目ID
      year: 年度
      report_type: 报表类型 (balance_sheet/income_statement/cash_flow_statement)
      row_code: 行次编码
      col_field: 列字段 (current_period_amount/prior_period_amount)
      company_codes: 子企业代码列表（可选，不传则查所有）
    """
    import json
    from sqlalchemy import text as sa_text

    project_id = body.get("project_id")
    year_val = body.get("year")
    report_type = body.get("report_type", "balance_sheet")
    row_code = body.get("row_code", "")
    col_field = body.get("col_field", "current_period_amount")
    company_codes = body.get("company_codes", [])

    if not project_id or not row_code:
        return {"rows": [], "message": "缺少 project_id 或 row_code"}

    # 1. 从 consol_worksheet_data 获取基本信息表（企业列表）
    result = await db.execute(
        sa_text("""
            SELECT data FROM consol_worksheet_data
            WHERE project_id = :pid AND year = :y AND sheet_key = 'info'
        """),
        {"pid": project_id, "y": year_val},
    )
    info_row = result.fetchone()
    companies = []
    if info_row and isinstance(info_row[0], dict):
        companies = info_row[0].get("rows", [])
    if not companies:
        return {"rows": [], "message": "未找到基本信息表数据"}

    # 2. 从各子企业的试算平衡表数据中提取指定行次的金额
    rows = []
    for comp in companies:
        code = comp.get("company_code", "")
        name = comp.get("company_name", "")
        if company_codes and code not in company_codes:
            continue

        # 查找该企业的试算平衡表数据
        tb_key = f"consol_tb_{report_type}_closing"
        tb_result = await db.execute(
            sa_text("""
                SELECT data FROM consol_worksheet_data
                WHERE project_id = :pid AND year = :y AND sheet_key = :sk
            """),
            {"pid": project_id, "y": year_val, "sk": tb_key},
        )
        tb_row = tb_result.fetchone()
        amount = None
        source = "无数据"

        if tb_row and isinstance(tb_row[0], dict):
            tb_rows = tb_row[0].get("rows", [])
            for tr in tb_rows:
                if tr.get("row_code") == row_code:
                    # 优先取审定数（audited），其次取汇总数（summary）
                    amount = tr.get("audited") or tr.get("summary")
                    source = "试算平衡表"
                    break

        # 如果试算表没有，尝试从 report_config 取
        if amount is None:
            try:
                rc_result = await db.execute(
                    sa_text("""
                        SELECT current_period_amount, prior_period_amount
                        FROM report_config
                        WHERE row_code = :rc AND report_type = :rt
                          AND is_deleted = false
                        LIMIT 1
                    """),
                    {"rc": row_code, "rt": report_type},
                )
                rc_row = rc_result.fetchone()
                if rc_row:
                    amount = float(rc_row[0]) if col_field == "current_period_amount" and rc_row[0] else (
                        float(rc_row[1]) if rc_row[1] else None
                    )
                    source = "报表配置"
            except Exception:
                pass

        ratio_val = comp.get("non_common_ratio") or comp.get("common_ratio") or 0
        rows.append({
            "company_code": code,
            "company_name": name,
            "amount": amount,
            "ratio": ratio_val,
            "source": source,
            "holding_type": comp.get("holding_type", "直接"),
            "parent_name": comp.get("indirect_holder", "母公司"),
        })

    # 计算占比
    total = sum(r["amount"] or 0 for r in rows)
    for r in rows:
        if total and r["amount"]:
            r["pct"] = round((r["amount"] / abs(total)) * 100, 2)
        else:
            r["pct"] = 0

    return {"rows": rows, "total": total, "row_code": row_code, "col_field": col_field}
