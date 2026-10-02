"""合并差额表 API 路由

prefix=/api/consolidation/worksheet

端点：
- GET  /tree                    企业树（含合并方式识别、诊断、年度）
- GET  /accounts                差额录入可选科目
- GET  /node-amounts            节点按科目归一后的金额（实时求值）
- GET  /report-trial            合并试算平衡表页（按报表行次五列净额，读时计算）
- GET  /report-breakdown        报表差额表（汇总节点的子节点各一列 + 合计）
- GET  /drill/entries           报表行 → 分录明细（已审批、贡献之和 = 该行该列）
- GET  /drill/individual        报表行 → 各数据节点个别数
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
from app.deps import require_project_access
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
    current_user: User = Depends(require_project_access("readonly")),
):
    """企业树 + 合并方式识别 + 诊断 + 年度（consol-tree-three-code-autobuild 需求 3 / 4.4 / 9.4）。

    ``tree`` 节点保留旧字段并含 ``node_key/role/kind/display_name/relation/host_project_id/flags``；
    ``diagnostics`` 含企业树推导诊断与未归属的已审批分录。项目不存在时 ``tree`` 为空并给出说明。
    """
    from app.services.consol_tree_service import build_tree_view

    view = await build_tree_view(db, project_id)
    if view is None:
        return {
            "tree": None, "mode": None, "mode_label": None, "diagnostics": [], "year": None,
            "message": "项目不存在或已删除",
        }
    return view


@router.get("/accounts")
async def get_accounts(
    project_id: UUID = Query(...),
    year: int | None = Query(None, description="年度；不传取本项目审计年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """差额录入可选科目（需求 9.3）：本树数据叶子试算表科目 ∪ 本树分录明细行科目。

    每个科目带名称、类别、自然方向（借方性质 / 贷方性质，与金额归一同一判定）与来源。
    """
    from app.services.consol_calc_basis import load_account_options
    from app.services.consol_group_tree import build_group_tree

    result = await build_group_tree(db, project_id)
    if result is None or result.root is None:
        raise HTTPException(status_code=404, detail="项目不存在或已删除")
    effective_year = year if year is not None else result.year
    if effective_year is None:
        return {"year": None, "accounts": []}
    return {"year": effective_year, "accounts": await load_account_options(db, result.root, effective_year)}


@router.get("/node-amounts")
async def get_node_amounts(
    project_id: UUID = Query(...),
    node_key: str = Query(..., description="节点键：{企业代码}:{角色}"),
    year: int | None = Query(None, description="年度；不传取本项目审计年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """某节点按科目归一后的金额（需求 9.3）：实时按计算口径求值，与重算写入差额表的数一致，不写库。"""
    from app.services.consol_calc_basis import NodeNotFoundError, load_node_amounts

    try:
        payload = await load_node_amounts(db, project_id, node_key, year)
    except NodeNotFoundError:
        raise HTTPException(status_code=404, detail=f"企业树中没有节点 {node_key}") from None
    if payload is None:
        raise HTTPException(status_code=404, detail="项目不存在或已删除")
    return payload


async def _view_context(db: AsyncSession, project_id: UUID, year: int | None):
    from app.services.consol_report_view_service import load_view_context

    ctx = await load_view_context(db, project_id, year)
    if ctx is None:
        raise HTTPException(status_code=404, detail="项目不存在、不是合并项目，或无法确定审计年度")
    return ctx


def _view_error(err) -> HTTPException:
    return HTTPException(status_code=getattr(err, "status", 404), detail=str(err))


@router.get("/report-trial")
async def get_report_trial(
    project_id: UUID = Query(...),
    report_type: str = Query("balance_sheet", description="报表类型"),
    node_key: str | None = Query(None, description="汇总节点；不传取根合并节点"),
    year: int | None = Query(None, description="年度；不传取本项目审计年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """合并试算平衡表页（spec consol-elimination-single-source-push §五）：按报表行次的五列净额。

    审定汇总 / 权益抵销 / 往来交易抵销 / 报表调整 / 合并审定数，均为按科目自然方向归一后的净额；
    与合并报表、报表差额表同一个求值函数，读时计算不写库。
    """
    from app.services.consol_report_view_service import ViewError, trial_view

    ctx = await _view_context(db, project_id, year)
    try:
        view = await trial_view(ctx.basis, ctx.rows, report_type=report_type, node_key=node_key)
    except ViewError as e:
        raise _view_error(e) from e
    return {"year": ctx.year, "applicable_standard": ctx.standard, **view}


@router.get("/report-breakdown")
async def get_report_breakdown(
    project_id: UUID = Query(...),
    report_type: str = Query("balance_sheet", description="报表类型"),
    node_key: str | None = Query(None, description="汇总节点；不传取根合并节点"),
    year: int | None = Query(None, description="年度；不传取本项目审计年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """报表差额表（§六）：列 = 汇总节点的直接子节点（数据 / 差额 / 下级汇总），合计 = 该节点合并数。"""
    from app.services.consol_report_view_service import ViewError, aggregate_nodes, breakdown_view

    ctx = await _view_context(db, project_id, year)
    try:
        view = await breakdown_view(ctx.basis, ctx.rows, report_type=report_type, node_key=node_key)
    except ViewError as e:
        raise _view_error(e) from e
    return {
        "year": ctx.year, "applicable_standard": ctx.standard,
        "aggregate_nodes": aggregate_nodes(ctx.basis.tree), **view,
    }


@router.get("/drill/entries")
async def drill_entries(
    project_id: UUID = Query(...),
    row_code: str = Query(..., description="报表行次"),
    measure: str = Query(..., description="elim_equity / elim_trade / adjustment / consolidated"),
    node_key: str | None = Query(None, description="汇总节点；不传取根合并节点"),
    year: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """报表行 → 分录明细（§五 穿透）：只计已审批、已归属到该节点子树的分录；贡献之和 = 该行该列。"""
    from app.services.consol_report_view_service import ViewError, load_entry_drill

    ctx = await _view_context(db, project_id, year)
    try:
        return {"year": ctx.year, **await load_entry_drill(
            db, ctx, row_code=row_code, measure=measure, node_key=node_key,
        )}
    except ViewError as e:
        raise _view_error(e) from e


@router.get("/drill/individual")
async def drill_individual(
    project_id: UUID = Query(...),
    row_code: str = Query(..., description="报表行次"),
    node_key: str | None = Query(None, description="汇总节点；不传取根合并节点"),
    year: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """报表行 → 各数据节点个别数（§五 审定汇总列穿透）：子树内每个数据叶子对该行的求值。"""
    from app.services.consol_report_view_service import ViewError, load_individual_drill

    ctx = await _view_context(db, project_id, year)
    try:
        rows = await load_individual_drill(ctx, row_code=row_code, node_key=node_key)
    except ViewError as e:
        raise _view_error(e) from e
    return {"year": ctx.year, "row_code": row_code, "rows": rows}


@router.post("/recalc")
async def recalc_worksheet(
    body: RecalcRequest,
    project_id: UUID = Query(..., description="项目ID（用于权限校验）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
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
    current_user: User = Depends(require_project_access("readonly")),
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
    current_user: User = Depends(require_project_access("readonly")),
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
    current_user: User = Depends(require_project_access("readonly")),
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
    current_user: User = Depends(require_project_access("readonly")),
):
    """穿透到末端企业试算表"""
    from app.services.consol_drilldown_service import drill_to_trial_balance

    data = await drill_to_trial_balance(db, project_id, company_code)
    return data


@router.post("/pivot")
async def pivot_query(
    body: PivotRequest,
    project_id: UUID = Query(..., description="项目ID（用于权限校验）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
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
    current_user: User = Depends(require_project_access("readonly")),
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
    project_id: UUID = Query(..., description="项目ID（用于权限校验）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
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
    current_user: User = Depends(require_project_access("readonly")),
):
    """列出查询模板"""
    from app.services.consol_pivot_service import list_templates

    templates = await list_templates(db, project_id)
    return {"templates": templates}
