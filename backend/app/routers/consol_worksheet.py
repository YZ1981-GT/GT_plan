"""合并差额表 API 路由

prefix=/api/consolidation/worksheet

端点：
- GET  /tree                    企业树
- POST /recalc                  全量重算差额表
- GET  /aggregate               节点汇总查询
- GET  /drill/companies         穿透到企业构成
- GET  /drill/eliminations      穿透到抵消分录
- GET  /drill/trial-balance     穿透到试算表
- POST /pivot                   透视查询
- GET  /pivot/export            Excel 导出
- POST /pivot/templates         保存查询模板
- GET  /pivot/templates         列出查询模板
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

router = APIRouter(
    prefix="/api/consolidation/worksheet",
    tags=["合并差额表"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RecalcRequest(BaseModel):
    project_id: UUID
    year: int


class PivotRequest(BaseModel):
    project_id: UUID
    year: int
    row_dimension: str = "account"
    col_dimension: str = "company"
    value_field: str = "consolidated_amount"
    filters: dict | None = None
    transpose: bool = False
    node_company_code: str | None = None
    aggregation_mode: str = "self"


class TemplateCreateRequest(BaseModel):
    project_id: UUID
    name: str
    row_dimension: str = "account"
    col_dimension: str = "company"
    value_field: str = "consolidated_amount"
    filters: dict | None = None
    transpose: bool = False
    aggregation_mode: str = "self"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/tree")
async def get_tree(
    project_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回完整企业树 JSON"""
    from app.services.consol_tree_service import build_tree, to_dict

    tree = await build_tree(db, project_id)
    if not tree:
        return {"tree": None, "message": "未找到项目或无子项目"}
    return {"tree": to_dict(tree)}


@router.post("/recalc")
async def recalc_worksheet(
    body: RecalcRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """全量重算差额表"""
    from app.services.consol_worksheet_engine import recalc_full

    result = await recalc_full(db, body.project_id, body.year)
    return {"message": "重算完成", **result}


@router.get("/aggregate")
async def aggregate_node(
    project_id: UUID = Query(...),
    year: int = Query(...),
    node_code: str = Query(...),
    mode: str = Query("self"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """节点汇总查询（mode=self|children|descendants）"""
    from app.services.consol_aggregation_service import query_node

    if mode not in ("self", "children", "descendants"):
        raise HTTPException(status_code=400, detail="mode 必须是 self/children/descendants")
    data = await query_node(db, project_id, year, node_code, mode)
    return {"rows": data, "mode": mode, "node_code": node_code}


@router.get("/drill/companies")
async def drill_companies(
    project_id: UUID = Query(...),
    year: int = Query(...),
    node_code: str = Query(...),
    account_code: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """穿透到企业构成"""
    from app.services.consol_drilldown_service import drill_to_companies

    data = await drill_to_companies(db, project_id, year, node_code, account_code)
    return {"rows": data}


@router.get("/drill/eliminations")
async def drill_eliminations(
    project_id: UUID = Query(...),
    year: int = Query(...),
    company_code: str = Query(...),
    account_code: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """穿透到抵消分录"""
    from app.services.consol_drilldown_service import drill_to_eliminations

    data = await drill_to_eliminations(db, project_id, year, company_code, account_code)
    return {"rows": data}


@router.get("/drill/trial-balance")
async def drill_trial_balance(
    project_id: UUID = Query(...),
    company_code: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """穿透到末端企业试算表"""
    from app.services.consol_drilldown_service import drill_to_trial_balance

    data = await drill_to_trial_balance(db, project_id, company_code)
    return data


@router.post("/pivot")
async def pivot_query(
    body: PivotRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """透视查询"""
    from app.services.consol_pivot_service import execute_query

    data = await execute_query(
        db, body.project_id, body.year,
        body.row_dimension, body.col_dimension, body.value_field,
        body.filters, body.transpose, body.node_company_code, body.aggregation_mode,
    )
    return data


@router.get("/pivot/export")
async def pivot_export(
    project_id: UUID = Query(...),
    year: int = Query(...),
    row_dimension: str = Query("account"),
    col_dimension: str = Query("company"),
    value_field: str = Query("consolidated_amount"),
    transpose: bool = Query(False),
    node_company_code: str | None = Query(None),
    aggregation_mode: str = Query("self"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Excel 导出透视表"""
    from app.services.consol_pivot_service import export_excel
    import io

    excel_bytes = await export_excel(
        db, project_id, year, row_dimension, col_dimension,
        value_field, None, transpose, node_company_code, aggregation_mode,
    )
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=consol_pivot.xlsx"},
    )


@router.post("/pivot/templates")
async def create_template(
    body: TemplateCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """保存查询模板"""
    from app.services.consol_pivot_service import save_template

    tpl = await save_template(
        db, body.project_id, body.name,
        body.row_dimension, body.col_dimension, body.value_field,
        body.filters, body.transpose, body.aggregation_mode,
    )
    return tpl


@router.get("/pivot/templates")
async def get_templates(
    project_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出查询模板"""
    from app.services.consol_pivot_service import list_templates

    templates = await list_templates(db, project_id)
    return {"templates": templates}
