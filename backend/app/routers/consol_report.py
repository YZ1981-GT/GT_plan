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

import logging
import uuid as _uuid
from io import BytesIO
from urllib.parse import quote
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
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
from app.models.report_models import FinancialReportType
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
    """生成合并报表（全部报表类型，按项目口径；取不到数的行留空并写明原因）。"""
    from app.services.consol_report_values import CONSOL_STANDARDS, resolve_consol_standard

    if data.project_id != project_id:
        raise HTTPException(status_code=400, detail="请求体中的项目与权限校验的项目不一致")
    standard = data.applicable_standard if data.applicable_standard in CONSOL_STANDARDS else (
        await resolve_consol_standard(db, data.project_id)
    )
    try:
        results = await generate_consol_reports_sync(db, data.project_id, data.year, standard)
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        await db.rollback()
        logger.exception("合并报表生成失败 project=%s year=%s", data.project_id, data.year)
        raise HTTPException(status_code=500, detail=f"合并报表生成失败: {e}") from e
    # 报表行由 service flush（未 commit）。按"service 只 flush，router 统一 commit"铁律，
    # 此处先 commit 让报表行持久化，再独立写审计 —— 确保审计失败回滚绝不波及已落库的报表。
    await db.commit()
    # 5D.2 / 需求 7.2：合并公式审计纳入哈希链（module='consol'）。
    # 审计写入独立事务 + try/except，失败仅告警不影响报表生成主流程。
    await _write_consol_formula_audit(db, str(data.project_id), data.year, results, user_id=user.id if hasattr(user, "id") else None)
    blank = {k: sum(1 for r in v if r.get("blank_reason")) for k, v in results.items()}
    return {
        "message": "合并报表生成成功",
        "applicable_standard": standard,
        "standard_note": (
            None if data.applicable_standard in (None, standard)
            else f"传入口径「{data.applicable_standard}」不是合并口径，已按项目模板类型使用 {standard}"
        ),
        "report_types": list(results.keys()),
        "row_counts": {k: len(v) for k, v in results.items()},
        "blank_counts": {k: n for k, n in blank.items() if n},
    }


async def _write_consol_formula_audit(
    db: AsyncSession,
    project_id_str: str,
    year: int,
    results: dict[str, list[dict]],
    user_id: _uuid.UUID | None = None,
) -> None:
    """将合并报表公式执行结果写入哈希链 audit_log_entries（module='consol'）。

    统一调 append_audit_log(action='formula.changed')，与单体报表同源留痕。
    FormulaResult.trace 入留痕 details。

    前置：调用方已 commit 报表行 —— 故本函数内的 rollback 只会丢弃审计 INSERT，
    绝不波及已落库的报表（满足"审计失败不得破坏报表生成"约束）。
    """
    try:
        from app.services.audit_log_helper import append_audit_log

        pid = _uuid.UUID(project_id_str) if project_id_str else None
        for report_type, rows in results.items():
            for r in rows:
                formula_str = r.get("formula_used") or ""
                if not formula_str:
                    continue
                result_value = r.get("current_period_amount")
                try:
                    rv = str(float(result_value)) if result_value is not None else ""
                except (TypeError, ValueError):
                    rv = ""
                trace = r.get("trace", [])
                if not trace:
                    trace = [f"report_type={report_type}", f"row_name={r.get('row_name', '')}"]
                await append_audit_log(db, {
                    "user_id": user_id or _uuid.UUID("00000000-0000-0000-0000-000000000000"),
                    "project_id": pid,
                    "action": "formula.changed",
                    "resource_type": "report_config",
                    "resource_id": r.get("row_code") or "",
                    "details": {
                        "event_type": "formula_changed",
                        "module": "consol",
                        "row_code": r.get("row_code") or "",
                        "action": "execute",
                        "old_formula": "",
                        "new_formula": formula_str,
                        "result_value": rv,
                        "trace": trace,
                    },
                })
        await db.commit()
    except Exception as exc:  # 审计失败不影响主流程（报表已 commit）
        logger.warning("合并公式审计写入哈希链失败（不影响报表生成）: %s", exc)
        try:
            await db.rollback()
        except Exception:
            pass


@router.get("/{project_id}/{year}")
async def get_consol_report(
    project_id: UUID,
    year: int,
    report_type: FinancialReportType = Query(..., description="报表类型"),
    node_key: str | None = Query(default=None, description="企业树节点键；省略则使用根合并节点"),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    """获取合并报表数据（支持按节点读时计算）。"""
    # ── 节点验证（设计 §六.1）──
    # 空字符串是无效输入，不降级为省略。
    if node_key is not None and not node_key:
        raise HTTPException(status_code=400, detail="node_key 不能为空字符串；省略参数表示使用根合并节点")

    from app.services.consol_group_tree import ROLE_CONSOL, build_group_tree
    from app.services.consol_tree_service import find_node_by_key
    from app.services.project_audit_year import resolve_project_audit_year
    from app.models.core import Project

    # 1) 验证项目存在
    project = (await db.execute(
        sa.select(Project).where(
            Project.id == project_id,
            Project.is_deleted.is_(False),
        )
    )).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 2) 验证审计年度有效
    effective_year = resolve_project_audit_year(project)
    if effective_year is None:
        raise HTTPException(status_code=400, detail="项目没有有效审计年度")
    if year != effective_year:
        raise HTTPException(status_code=400, detail=f"请求年度 {year} 与项目审计年度 {effective_year} 不一致")

    # 3) 构建企业树
    tree_result = await build_group_tree(db, project_id)
    if tree_result is None or tree_result.root is None or tree_result.root.role != ROLE_CONSOL:
        raise HTTPException(status_code=400, detail="项目不是有效的合并项目")

    # 4) 解析节点：显式值精确验证，缺省使用根节点
    if node_key is not None:
        matched = find_node_by_key(tree_result.root, node_key)
        if matched is None:
            raise HTTPException(status_code=400, detail=f"企业树中没有节点 {node_key}")
        resolved_node_key = node_key
    else:
        resolved_node_key = tree_result.root.node_key

    # ── 节点读时计算（设计 §六.2）──
    # 通过 load_view_context 统一加载树、CalcBasis 和报表配置，
    # 然后用 node_measures + report_values 按 resolved_node_key 求行金额。
    # 不从项目级 FinancialReport 物化表读取金额（ADR-CNSC-003）。

    from app.services.consol_report_view_service import (
        ViewContext, load_view_context, _rows_of_type,
    )
    from app.services.consol_calc_basis import (
        MEASURE_CONSOLIDATED, node_measures as calc_node_measures,
    )
    from app.services.consol_report_values import report_values as calc_report_values

    ctx: ViewContext | None = await load_view_context(db, project_id, year)
    if ctx is None:
        raise HTTPException(status_code=400, detail="无法加载合并计算上下文")

    # 按 report_type 筛选报表配置行
    rt_str = report_type.value
    try:
        typed_rows = _rows_of_type(ctx.rows, rt_str)
    except Exception:
        raise HTTPException(status_code=400, detail=f"不支持的报表类型：{rt_str}")

    if not typed_rows:
        raise HTTPException(
            status_code=404,
            detail=f"合并{rt_str}的报表配置不存在，请先配置报表行",
        )

    # 全树节点度量（含 resolved_node_key）
    all_measures = calc_node_measures(ctx.basis)
    node_ms = all_measures.get(resolved_node_key)
    if node_ms is None:
        raise HTTPException(
            status_code=400,
            detail=f"节点 {resolved_node_key} 在当前计算口径中没有度量数据",
        )

    # 本期金额：使用合并数（consolidated）度量
    consol_amounts = node_ms.get(MEASURE_CONSOLIDATED, {})
    current_values = await calc_report_values(
        typed_rows,
        consol_amounts,
        categories=ctx.basis.categories,
        require_linear=False,
    )

    # 上期金额：同一 node_key 在上一审计年度的树与计算上下文。
    # 若上一年度不存在或节点不存在，则 prior = null。（设计 §六.4）
    prior_values: dict | None = None
    prior_year = year - 1
    try:
        prior_ctx = await load_view_context(db, project_id, prior_year)
        if prior_ctx is not None:
            prior_all = calc_node_measures(prior_ctx.basis)
            prior_ms = prior_all.get(resolved_node_key)
            if prior_ms is not None:
                prior_consol = prior_ms.get(MEASURE_CONSOLIDATED, {})
                prior_typed = _rows_of_type(prior_ctx.rows, rt_str)
                if prior_typed:
                    prior_values = await calc_report_values(
                        prior_typed,
                        prior_consol,
                        categories=prior_ctx.basis.categories,
                        require_linear=False,
                    )
    except Exception as exc:
        logger.debug("上期报表计算失败（降级为空）: %s", exc)

    # 构造响应行，保持 ConsolReportRow 字段契约（设计 §六.3）
    out: list[ConsolReportRow] = []
    for row in typed_rows:
        cv = current_values.get(row.row_code)
        pv = prior_values.get(row.row_code) if prior_values else None

        current_amount = cv.amount if cv else None
        prior_amount = pv.amount if pv else None

        # blank_reason：公式不支持/引用了留空行等原因
        reason = cv.reason if cv else None

        out.append(ConsolReportRow(
            row_code=row.row_code,
            row_name=row.row_name,
            indent_level=row.indent_level,
            is_total_row=row.is_total_row,
            is_total=row.is_total_row,
            current_period_amount=current_amount,
            prior_period_amount=prior_amount,
            formula_used=row.formula,
            source_accounts=None,
            blank_reason=reason,
            is_stale=False,
        ))

    return out


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
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(result.file_name)}"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载合并底稿失败: {str(e)}")
