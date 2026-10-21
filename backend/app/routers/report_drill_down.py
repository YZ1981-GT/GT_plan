"""合并报表汇总穿透（spec consol-elimination-single-source-push 需求 9.3）。

2026-10-20 原样迁出 ``report_config.py``（该文件超行数门），路径不变
（``POST /api/report-config/drill-down``；自带完整前缀，在 ``router_registry/report.py`` §4 紧随
report_config 注册，路由守卫按文件内 prefix 静态抽取才看得到）。
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user
from app.models.core import User

router = APIRouter(prefix="/api/report-config", tags=["report-config"])


@router.post("/drill-down")
async def report_drill_down(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """汇总穿透：合并报表某行由企业树各节点怎样构成（spec consol-elimination-single-source-push 需求 9.3）。

    与报表差额表同一求值（``consol_report_view_service.child_contributions``）：``rows`` = 所选汇总节点
    （默认根合并节点）的直接子节点，``leaf_rows`` = 子树全部末级节点；线性行两层之和都 = 合并数。
    不再读 ``consol_worksheet_data['info']``、不再按持股比例估算。项目在请求体里 ⇒ 函数体内做项目级鉴权。

    请求体：``project_id``、``year``（可选，默认项目审计年度）、``report_type``、``row_code``、``node_key``（可选）。
    """
    from app.services.consol_report_view_service import ViewError, child_contributions, load_view_context

    try:
        project_id = UUID(str(body.get("project_id") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="缺少或无效的 project_id") from exc
    row_code = str(body.get("row_code") or "").strip()
    if not row_code:
        raise HTTPException(status_code=400, detail="缺少 row_code")
    await assert_project_permission(db, current_user, project_id, "readonly")
    year_val = body.get("year")
    ctx = await load_view_context(db, project_id, int(year_val) if year_val else None)
    if ctx is None:
        raise HTTPException(status_code=404, detail="不是合并报表项目或没有审计年度，无法穿透")
    try:
        result = await child_contributions(
            ctx.basis, ctx.rows, report_type=str(body.get("report_type") or "balance_sheet"),
            row_code=row_code, node_key=body.get("node_key") or None,
        )
    except ViewError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {"year": ctx.year, "applicable_standard": ctx.standard, **result}
