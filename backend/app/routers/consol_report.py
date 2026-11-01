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
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.deps import check_consol_lock, require_project_access
from app.core.database import get_db
from app.models.consolidation_schemas import (
    BalanceCheckResult,
    ConsolReportGenerateRequest,
    ConsolReportRow,
)
from app.models.report_models import FinancialReportType
from app.schemas.consol_report_run import ConsolArtifactCreate
from app.services.consol_report_service import (
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
    _lock_check=Depends(check_consol_lock),
):
    """兼容入口：把“生成合并报表”收敛到持久 operation，不再直接覆盖正式报表。"""
    from app.services.consol_operation_service import (
        OperationBoundaryError,
        OperationConflict,
        operation_payload,
        request_operation,
    )
    from app.services.consol_report_values import CONSOL_STANDARDS, resolve_consol_standard

    if data.project_id != project_id:
        raise HTTPException(status_code=400, detail="请求体中的项目与权限校验的项目不一致")
    standard = data.applicable_standard if data.applicable_standard in CONSOL_STANDARDS else (
        await resolve_consol_standard(db, data.project_id)
    )
    try:
        requested = await request_operation(
            db,
            project_id=data.project_id,
            year=data.year,
            operation_type="refresh_all",
            trigger_source="report_generate_compat",
            triggered_by=getattr(user, "id", None),
            requested_actions=("report",),
        )
        await db.commit()
    except OperationBoundaryError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except OperationConflict as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "OPERATION_CONFLICT", "message": str(exc)},
        ) from exc
    from app.workers.consol_operation_worker import wake

    wake()
    return {
        "message": "合并报表已进入更新队列",
        "applicable_standard": standard,
        "standard_note": (
            None if data.applicable_standard in (None, standard)
            else f"传入口径「{data.applicable_standard}」不是合并口径，已按项目模板类型使用 {standard}"
        ),
        "report_types": [],
        "row_counts": {},
        "blank_counts": {},
        "operation": operation_payload(requested.operation),
        "operation_id": str(requested.operation.id),
        "status": requested.operation.status,
        "disposition": requested.disposition,
    }


async def _write_consol_formula_audit(
    db: AsyncSession,
    project_id_str: str,
    year: int,
    results: dict[str, list[dict]],
    user_id: UUID | None = None,
) -> None:
    """兼容薄壳：审计实现已收敛到 report run 服务，旧测试/调用方仍可导入本符号。"""
    if not project_id_str:
        return
    from app.services.consol_report_run_service import write_consol_formula_audit

    await write_consol_formula_audit(db, UUID(project_id_str), year, results, user_id)


@router.get("/{project_id}/{year}")
async def get_consol_report(
    project_id: UUID,
    year: int,
    report_type: FinancialReportType = Query(..., description="报表类型"),
    node_key: str | None = Query(default=None, description="企业树节点键；省略则使用根合并节点"),
    mode: Literal["published", "preview"] = Query(default="published", description="正式结果或实时预览"),
    operation_id: UUID | None = Query(default=None, description="固定到某次已发布 operation"),
    report_run_id: UUID | None = Query(default=None, description="固定到某次已发布 report run"),
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

    # 正式模式只允许根节点，且只读 succeeded operation 精确引用的 immutable report run。
    if mode == "published":
        if resolved_node_key != tree_result.root.node_key:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "NON_ROOT_PUBLISHED_UNSUPPORTED",
                    "message": "非根节点属于分析预览，请切换 mode=preview",
                },
            )
        from app.services.consol_report_run_service import ReportRunError, published_report_payload

        try:
            run, rows = await published_report_payload(
                db,
                project_id,
                year,
                report_type.value,
                operation_id=operation_id,
                report_run_id=report_run_id,
            )
        except ReportRunError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
        return {
            "mode": "published",
            "published": True,
            "project_id": str(project_id),
            "year": year,
            "node_key": resolved_node_key,
            "report_type": report_type.value,
            "operation_id": str(run.operation_id),
            "operation_revision": run.operation_revision,
            "report_run_id": str(run.id),
            "input_digest": run.input_digest,
            "row_digest": run.row_digest,
            "applicable_standard": run.applicable_standard,
            "download_allowed": True,
            "rows": rows,
            "notice": "正式结果：页面与导出固定到同一报表运行",
        }

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

    # 上期金额：上年同企业合并项目同一 node_key 的合并数（spec consol-autotree-linkage-closure R8.1）。
    # 取不到（无上年合并项目 / 上年树没有该节点 / 上年无法计算）⇒ 留空并写明原因（prior_blank_reason）。
    from app.services.consol_report_view_service import prior_node_values

    prior_values: dict | None = None
    prior_reason: str | None = None
    try:
        # SAVEPOINT：上年计算的查询失败不能让本请求事务 aborted
        async with db.begin_nested():
            prior_values, prior_reason = await prior_node_values(
                db, project_id, year, resolved_node_key, rt_str, standard=ctx.standard)
    except Exception as exc:  # noqa: BLE001 —— 上期是附加列，失败如实说明
        logger.warning("合并上期计算失败（留空）: %s", exc)
        prior_values, prior_reason = None, f"合并上期留空：上年数据计算失败（{exc}）"

    # 构造响应行，保持 ConsolReportRow 字段契约（设计 §六.3）
    out: list[ConsolReportRow] = []
    for row in typed_rows:
        cv = current_values.get(row.row_code)
        pv = prior_values.get(row.row_code) if prior_values else None

        current_amount = cv.amount if cv else None
        prior_amount = pv.amount if pv else None

        # blank_reason：公式不支持/引用了留空行等原因
        reason = cv.reason if cv else None
        prior_row_reason = prior_reason if prior_values is None else (pv.reason if pv else None)

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
            prior_blank_reason=prior_row_reason,
            is_stale=False,
        ))

    preview_rows = [row.model_dump(mode="json") for row in out]
    from app.services.consol_version_vector import digest_payload

    return {
        "mode": "preview",
        "published": False,
        "project_id": str(project_id),
        "year": year,
        "node_key": resolved_node_key,
        "report_type": report_type.value,
        "operation_id": None,
        "operation_revision": None,
        "report_run_id": None,
        "input_digest": None,
        "row_digest": digest_payload(preview_rows),
        "applicable_standard": ctx.standard,
        "download_allowed": False,
        "rows": preview_rows,
        "notice": "实时预览，未发布；不可用于正式导出或签字",
    }


@router.get("/{project_id}/{year}/balance-check", response_model=BalanceCheckResult)
async def balance_check(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    """合并资产负债表平衡校验"""
    return await verify_balance_sync(db, project_id, year)


def _artifact_http_error(exc: Exception) -> HTTPException:
    from app.services.consol_artifact_service import ArtifactError
    from app.services.consol_operation_service import OperationBoundaryError
    from app.services.consol_report_run_service import ReportRunError

    if isinstance(exc, OperationBoundaryError):
        return HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        )
    if isinstance(exc, (ArtifactError, ReportRunError)):
        return HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        )
    return HTTPException(
        status_code=500,
        detail={"code": "ARTIFACT_GENERATION_FAILED", "message": f"生成合并文件失败：{exc}"},
    )


async def _create_artifact_impl(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    body: ConsolArtifactCreate,
    user_id: UUID | None,
):
    from app.services.consol_artifact_service import (
        artifact_payload,
        generate_reserved_artifact,
        mark_artifact_failed,
        reserve_artifact,
    )
    from app.services.consol_operation_service import validate_project_boundary

    await validate_project_boundary(db, project_id, year, writable=True)
    artifact, should_generate = await reserve_artifact(
        db,
        project_id,
        year,
        report_run_id=body.report_run_id,
        kind=body.kind,
        node_key=body.node_key,
        created_by=user_id,
    )
    await db.commit()  # 短事务提交 generating 预留；文件生成期间不持有行锁
    if not should_generate:
        if artifact.status == "ready":
            return artifact_payload(artifact)
        raise HTTPException(
            status_code=409,
            detail={"code": "ARTIFACT_GENERATING", "message": "同一正式运行的文件正在生成"},
        )
    try:
        artifact = await generate_reserved_artifact(db, artifact.id)
        await db.commit()
        return artifact_payload(artifact)
    except Exception as exc:
        await db.rollback()
        try:
            await mark_artifact_failed(db, artifact.id, exc)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("合并 artifact 失败状态写回失败：artifact=%s", artifact.id)
        raise _artifact_http_error(exc) from exc


@router.post("/{project_id}/{year}/artifacts")
async def create_consol_artifact(
    project_id: UUID,
    year: int,
    body: ConsolArtifactCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """为指定已发布 report run 一次生成不可变 Excel artifact；重复请求复用同一文件。"""
    try:
        return await _create_artifact_impl(db, project_id, year, body, getattr(user, "id", None))
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        raise _artifact_http_error(exc) from exc


@router.get("/{project_id}/{year}/artifacts/{artifact_id}/download")
async def download_consol_artifact(
    project_id: UUID,
    year: int,
    artifact_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    """下载既有 ready artifact；重验 size/hash，绝不现场重算。"""
    from app.services.consol_artifact_service import get_artifact, verify_artifact_file
    from app.services.consol_operation_service import validate_project_boundary

    try:
        await validate_project_boundary(db, project_id, year, writable=False)
        artifact = await get_artifact(db, project_id, year, artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail={"code": "ARTIFACT_NOT_FOUND", "message": "文件不存在"})
        path = verify_artifact_file(artifact)
        return FileResponse(
            path,
            media_type=artifact.content_type,
            filename=artifact.file_name,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _artifact_http_error(exc) from exc


@router.post("/{project_id}/{year}/workpaper")
async def create_consol_workpaper(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """兼容入口：为最近已发布 report run 生成不可变合并工作底稿。"""
    from app.services.consol_report_run_service import resolve_published_run
    from app.services.consol_operation_service import validate_project_boundary

    try:
        await validate_project_boundary(db, project_id, year, writable=True)
    except Exception as exc:
        raise _artifact_http_error(exc) from exc
    run = await resolve_published_run(db, project_id, year)
    if run is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "PUBLISHED_REPORT_NOT_FOUND", "message": "请先完成“更新合并结果”"},
        )
    return await _create_artifact_impl(
        db,
        project_id,
        year,
        ConsolArtifactCreate(report_run_id=run.id, kind="consol_workpaper"),
        getattr(user, "id", None),
    )


@router.get("/{project_id}/{year}/workpaper/download")
async def download_consol_workpaper(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    """兼容入口：下载最近正式 run 的既有工作底稿；没有 artifact 时明确失败，不重算。"""
    from app.models.report_generation_models import ConsolArtifact
    from app.services.consol_artifact_service import verify_artifact_file
    from app.services.consol_report_run_service import resolve_published_run
    from app.services.consol_operation_service import validate_project_boundary

    await validate_project_boundary(db, project_id, year, writable=False)
    run = await resolve_published_run(db, project_id, year)
    if run is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "PUBLISHED_REPORT_NOT_FOUND", "message": "当前没有已发布的合并报表"},
        )
    artifact = (await db.execute(sa.select(ConsolArtifact).where(
        ConsolArtifact.report_run_id == run.id,
        ConsolArtifact.kind == "consol_workpaper",
        ConsolArtifact.node_key == run.node_key,
        ConsolArtifact.status == "ready",
    ))).scalar_one_or_none()
    if artifact is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "ARTIFACT_NOT_FOUND", "message": "请先生成合并工作底稿"},
        )
    try:
        path = verify_artifact_file(artifact)
    except Exception as exc:
        raise _artifact_http_error(exc) from exc
    return FileResponse(path, media_type=artifact.content_type, filename=artifact.file_name)
