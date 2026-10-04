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
    node_key: str | None = Query(None, description="合并树节点；省略时默认当前树的根合并节点"),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    """获取合并报表数据（按所选树节点 node_key **读时计算**，复用合并计算内核）。

    node_key（spec consol-node-key-isolation-and-shared-context 任务 4.1/4.2，设计 §六，需求 4.1~4.4）：
    - 省略 ⇒ 默认选当前合并项目企业树的**根合并节点**，保持旧页面默认行为；
    - 显式值 ⇒ 经**当前项目/年度企业树**精确校验（`find_node_by_key`），不在树中则 400，
      非合并项目 / 无有效年度 / 跨年 则由 `resolve_report_node_scope` 以明确 400 / 404 拒绝；
      禁按 company_code、冒号前缀或 `:consol` 后缀兜底判根（ADR-CNSC-001）。

    金额来源（任务 4.2 / 4.3，设计 §六.2~§六.5）：以校验后的 `scope.node_key` 经
    `load_view_context` → `node_measures(basis)[node_key]` → `consol_report_values.node_report`
    求所选 `report_type` 行的**合并数**（`MEASURE_CONSOLIDATED`），与合并试算 / 差额 / 附注共用同一
    求值口径（`consol_report_view_service.trial_view` / `note_cell_values` 同款）。**不再**读取项目级
    物化 `FinancialReport` 冒充非根节点金额；无法求值的行给 `current_period_amount=null` + `blank_reason`。

    本期 / 上期共享口径（任务 4.3，设计 §六.4）：
    - **本期**金额按请求 `scope.node_key` 读时计算（上方 `consolidated`）；
    - **上期**金额只用**上一有效审计年度同一 node_key** 的树与同一共享求值上下文计算
      （`load_prior_year_node_report`）：上年无同企业合并项目 / 上年合并树无此节点 ⇒ 整体
      `prior_period_amount=null` 并带原因；行级公式不支持 ⇒ 该行上期 `null` + 原因。**绝不**复用根项目级
      `FinancialReport.prior_period_amount` 冒充非根节点上期。

    股东权益表（设计 §六.5）：与其余报表同走节点 `node_report` 合并数求值，**不**调用项目级
    `ReportEngine.enrich_equity_statement_rows`，即节点金额不被项目级 enrichment 覆盖。

    `ConsolReportRow[]` 既有字段语义保留（设计 §六.3）：row_code / row_name / row_index / indent_level /
    is_total(_row) / current_period_amount / prior_period_amount / formula_used / source_accounts /
    blank_reason / is_stale —— 该填的填、该 null 的 null 并给原因，不伪造 0、不冒充。
    """
    from app.services.consol_calc_basis import MEASURE_CONSOLIDATED, node_measures
    from app.services.consol_note_scope import NoteScopeError, resolve_report_node_scope
    from app.services.consol_report_values import REPORT_TYPE_ORDER, node_report
    from app.services.consol_report_view_service import load_prior_year_node_report, load_view_context

    try:
        scope = await resolve_report_node_scope(db, project_id, year, node_key=node_key)
    except NoteScopeError as e:
        raise HTTPException(status_code=getattr(e, "status", 400), detail=str(e)) from e

    # 读时计算：装载合并视图上下文（企业树 + 计算口径 + 报表配置），只装载一次。
    # scope.year 为经企业树解析的有效年度（_load_tree 保证非 None）。
    ctx = await load_view_context(db, project_id, scope.year)
    if ctx is None:
        # resolve_report_node_scope 已拦非合并项目 / 无年度；此处 None 仅为防御（口径漂移时明确报错而非静默）。
        raise HTTPException(status_code=404, detail="只有合并报表项目有合并报表（项目不存在、不是合并项目或没有审计年度）")

    report_type_value = report_type.value
    if report_type_value not in REPORT_TYPE_ORDER:
        raise HTTPException(status_code=400, detail=f"不支持的报表类型：{report_type_value}")

    measures_by_node = node_measures(ctx.basis)
    node_measure_values = measures_by_node.get(scope.node_key)
    if node_measure_values is None:
        # 校验已保证 node_key 在树中；node_measures 遍历同一棵树必含该键，缺失即口径漂移。
        raise HTTPException(status_code=500, detail=f"节点 {scope.node_key} 不在合并计算口径内")

    # 全部报表类型一起求值（跨表 ROW 需要），只返回所请求类型；合并数度量不要求线性。
    by_measure = await node_report(ctx.rows, node_measure_values, categories=ctx.basis.categories)
    consolidated = by_measure[MEASURE_CONSOLIDATED]

    # 报表配置（report config）无该类型的任何行 ⇒ 该项目口径下不出此表（设计 §六.6：无报表配置按明确错误）。
    type_rows = [r for r in ctx.rows if r.report_type == report_type_value]
    if not type_rows:
        raise HTTPException(
            status_code=404,
            detail=f"合并{report_type.value}没有报表配置，无法生成",
        )

    # 上期（任务 4.3，设计 §六.4）：按**同一 node_key、上一有效审计年度**的树与共享求值上下文计算。
    # 整体不可用（上年无同企业合并项目 / 上年合并树无此节点）⇒ prior 为 None 的空表 + unavailable 原因；
    # 行级公式不支持 ⇒ 该行上期 null + 该行原因。绝不读项目级 FinancialReport.prior 冒充非根节点上期。
    prior = await load_prior_year_node_report(
        db, project_id=project_id, node_key=scope.node_key, year=scope.year, report_type=report_type_value,
    )

    # 权益表（equity_statement）与其余报表同走上方节点 node_report 合并数求值，不再调用项目级
    # ReportEngine.enrich_equity_statement_rows ⇒ 节点金额不被项目级 enrichment 覆盖（设计 §六.5）。
    out: list[ConsolReportRow] = []
    for row in type_rows:
        value = consolidated.get(row.row_code)
        amount = None if value is None else (None if value.amount is None else str(value.amount))
        reason = None if value is None else value.reason
        prior_value = prior.amounts.get(row.row_code)
        prior_amount = None if prior_value is None else (
            None if prior_value.amount is None else str(prior_value.amount)
        )
        out.append(
            ConsolReportRow(
                row_code=row.row_code or "",
                row_name=row.row_name or "",
                row_index=row.row_number or 0,
                indent_level=row.indent_level or 0,
                is_total_row=bool(row.is_total_row),
                is_total=bool(row.is_total_row),
                current_period_amount=amount,
                prior_period_amount=prior_amount,
                formula_used=row.formula,
                source_accounts=None,
                blank_reason=reason,
                is_stale=False,
            )
        )
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
