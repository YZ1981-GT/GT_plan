"""科目表管理 API 路由

Validates: Requirements 2.2, 2.5, 2.6
"""

import time
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.audit_platform_schemas import (
    AccountChartResponse,
    AccountImportResult,
    AccountTreeNode,
)
from app.models.core import User
from app.services import account_chart_service
from app.services.import_ops_audit_service import ImportOpsAuditService

router = APIRouter(prefix="/api/projects", tags=["account-chart"])


def _build_sheet_diagnostics(diagnostics: list[dict] | None) -> list[dict]:
    """规范化智能导入诊断结构，供前端结果页稳定展示。"""
    normalized: list[dict] = []
    for sheet in diagnostics or []:
        column_mapping = sheet.get("column_mapping") or {}
        matched_cols = sheet.get("matched_cols")
        if not isinstance(matched_cols, list):
            matched_cols = sorted(set(column_mapping.values())) if isinstance(column_mapping, dict) else []
        normalized.append({
            "sheet_name": sheet.get("sheet", ""),
            "guessed_type": sheet.get("data_type", "unknown"),
            "matched_cols": matched_cols,
            "missing_cols": sheet.get("missing_cols") or [],
            "missing_recommended": sheet.get("missing_recommended") or [],
            "row_count": sheet.get("row_count", 0),
        })
    return normalized


def _ensure_supported_account_chart_uploads(files: list[UploadFile]) -> None:
    for upload in files:
        filename = (upload.filename or "").lower()
        if filename.endswith(".xls"):
            raise HTTPException(
                status_code=400,
                detail="暂不支持 Excel 97-2003 (.xls) 文件，请先转换为 .xlsx 后再上传",
            )


@router.get(
    "/{project_id}/account-chart/standard",
    response_model=list[AccountChartResponse],
)
async def get_standard_chart(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> list[AccountChartResponse]:
    """获取项目的标准科目表。

    如果尚未加载，则根据项目会计准则自动加载标准科目模板。

    Validates: Requirements 2.2
    """
    # Always try incremental load (adds missing standard accounts)
    from app.services.project_wizard_service import get_wizard_state
    state = await get_wizard_state(project_id, db)
    accounting_standard = "enterprise"  # default
    basic_info = state.steps.get("basic_info")
    if basic_info and basic_info.data:
        accounting_standard = basic_info.data.get("accounting_standard", "enterprise")

    return await account_chart_service.load_standard_template(
        project_id, accounting_standard, db
    )


@router.post("/{project_id}/account-chart/preview")
async def preview_file(
    project_id: UUID,
    files: list[UploadFile] | None = File(None),
    file: UploadFile | None = File(None),
    upload_token: str | None = Query(default=None, description="预览上传产物令牌"),
    skip_rows: int | None = Query(default=None, description="跳过前N行，None=自动检测表头"),
    current_user: User = Depends(require_project_access("readonly")),
):
    """Preview uploaded file: return first 20 rows per sheet + auto-matched column mapping.

    大文件优化：使用 smart_import_engine 的智能表头检测（支持双行合并表头），
    只读取前 20 行数据用于预览，不加载全部数据。
    """
    from app.services.ledger_import_application_service import LedgerImportApplicationService

    return await LedgerImportApplicationService.preview(
        project_id=project_id,
        user_id=str(current_user.id),
        files=files,
        file=file,
        upload_token=upload_token,
        preview_rows=20,
    )


@router.post(
    "/{project_id}/account-chart/import",
    response_model=AccountImportResult,
)
async def import_client_chart(
    project_id: UUID,
    files: list[UploadFile] | None = File(None),
    file: UploadFile | None = File(default=None),
    upload_token: str | None = Query(default=None, description="预览上传产物令牌"),
    year: int | None = Query(default=None, description="指定年度（不指定则自动提取）"),
    column_mapping: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
) -> AccountImportResult:
    """导入科目表 + 四表数据（支持多文件一次上传）。

    使用 smart_import_streaming 统一处理：
    - 多文件安全：只 soft-delete 一次，不会后续文件覆盖前面的
    - 内存可控：逐 sheet 解析并写入
    - 自动提取科目表、四表数据、诊断信息
    """
    from app.services.ledger_import_application_service import LedgerImportApplicationService

    result_payload = await LedgerImportApplicationService.run_account_chart_import(
        project_id=project_id,
        user_id=str(current_user.id),
        db=db,
        files=files,
        file=file,
        upload_token=upload_token,
        year=year,
        column_mapping=column_mapping,
    )
    return AccountImportResult(**result_payload)


@router.post("/{project_id}/account-chart/import-reset")
async def reset_import(
    project_id: UUID,
    request: Request,
    job_id: UUID | None = Query(default=None, description="可选：指定要重置的导入作业ID（推荐）"),
    force: bool = Query(default=False, description="未提供 job_id 时，是否允许项目级重置"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """强制释放导入锁 + 清理卡住的任务。

    用于上传中断后前端自动恢复，或用户手动重置。
    """
    from app.services.import_queue_service import ImportQueueService

    started_at = time.perf_counter()
    scope = {"project_id": str(project_id), "job_id": str(job_id) if job_id else None}
    params = {"force": force}

    if job_id is None and not force:
        await ImportOpsAuditService.log_operation(
            user_id=current_user.id,
            action_type="import_reset",
            project_id=project_id,
            params=params,
            scope=scope,
            outcome="rejected",
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            result={"code": "IMPORT_RESET_JOB_ID_REQUIRED"},
            request=request,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "IMPORT_RESET_JOB_ID_REQUIRED",
                "message": "未提供 job_id，拒绝项目级重置；如确认执行请显式 force=true",
            },
        )
    try:
        msg = await ImportQueueService.force_release(project_id, db, job_id=job_id, force=force)
        await ImportOpsAuditService.log_operation(
            user_id=current_user.id,
            action_type="import_reset",
            project_id=project_id,
            params=params,
            scope=scope,
            outcome="success",
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            result={"message": msg},
            request=request,
        )
        return {"message": msg}
    except Exception as exc:
        await ImportOpsAuditService.log_operation(
            user_id=current_user.id,
            action_type="import_reset",
            project_id=project_id,
            params=params,
            scope=scope,
            outcome="failed",
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            error=str(exc),
            request=request,
        )
        raise


@router.post("/{project_id}/account-chart/import-async")
async def import_async(
    project_id: UUID,
    files: list[UploadFile] | None = File(None),
    file: UploadFile | None = File(default=None),
    upload_token: str | None = Query(default=None, description="预览上传产物令牌"),
    year: int | None = Query(default=None, description="指定年度（不指定则自动提取）"),
    column_mapping: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """异步导入（多文件支持）：立即返回，后台处理，前端轮询进度。

    适合大文件（>10MB）或多文件场景，避免 HTTP 超时。
    """
    from app.services.ledger_import_application_service import LedgerImportApplicationService

    return await LedgerImportApplicationService.submit_import_job(
        project_id=project_id,
        user_id=str(current_user.id),
        db=db,
        files=files,
        file=file,
        upload_token=upload_token,
        year=year,
        custom_mapping=column_mapping,
        payload_style="account_chart",
    )


@router.get(
    "/{project_id}/account-chart/client",
    response_model=dict[str, list[AccountTreeNode]],
)
async def get_client_chart(
    project_id: UUID,
    year: int | None = Query(default=None, description="指定年度，提供后优先返回 active dataset 的客户科目表"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> dict[str, list[AccountTreeNode]]:
    """获取客户科目表（树形结构按类别分组）。

    Validates: Requirements 2.6
    """
    return await account_chart_service.get_client_chart_tree(project_id, db, year=year)


# ── 列映射保存/加载（持久化到 wizard_state） ──

from pydantic import BaseModel as _BaseModel


class SaveColumnMappingRequest(_BaseModel):
    """保存列映射"""
    file_type: str  # account_chart / ledger / balance / aux_balance
    sheet_name: str | None = None
    mapping: dict[str, str]  # {原列名: 标准字段名}


class ReferenceMatchRequest(_BaseModel):
    """参照匹配请求"""
    source_project_id: str
    source_year: int | None = None


@router.post("/{project_id}/column-mappings")
async def save_column_mapping(
    project_id: UUID,
    body: SaveColumnMappingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """保存用户确认的列映射（持久化到项目 wizard_state）"""
    from sqlalchemy import select
    from app.models.core import Project

    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)  # noqa: E712
    )
    project = result.scalar_one_or_none()
    if not project:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="项目不存在")

    # 保存到 wizard_state.column_mappings
    state = project.wizard_state or {}
    if "column_mappings" not in state:
        state["column_mappings"] = {}

    key = f"{body.file_type}"
    if body.sheet_name:
        key = f"{body.file_type}:{body.sheet_name}"
    state["column_mappings"][key] = body.mapping
    project.wizard_state = state

    await db.commit()
    return {"saved": True, "key": key, "field_count": len(body.mapping)}


@router.get("/{project_id}/column-mappings")
async def get_column_mappings(
    project_id: UUID,
    file_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取已保存的列映射"""
    from sqlalchemy import select
    from app.models.core import Project

    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)  # noqa: E712
    )
    project = result.scalar_one_or_none()
    if not project:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="项目不存在")

    state = project.wizard_state or {}
    mappings = state.get("column_mappings", {})

    if file_type:
        # 过滤指定文件类型
        filtered = {k: v for k, v in mappings.items() if k.startswith(file_type)}
        return filtered
    return mappings


@router.get("/{project_id}/column-mappings/reference-projects")
async def get_reference_projects(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取可参照的项目列表（有已保存列映射的其他项目）"""
    from sqlalchemy import select, func, cast, String
    from app.models.core import Project

    # 查找所有有 column_mappings 的项目（排除当前项目）
    result = await db.execute(
        select(Project.id, Project.name, Project.client_name, Project.wizard_state)
        .where(
            Project.id != project_id,
            Project.is_deleted == False,  # noqa: E712
            Project.wizard_state.isnot(None),
        )
        .order_by(Project.created_at.desc())
        .limit(20)
    )
    projects = []
    for row in result.all():
        ws = row.wizard_state or {}
        mappings = ws.get("column_mappings", {})
        if mappings:
            projects.append({
                "id": str(row.id),
                "name": row.name,
                "client_name": row.client_name,
                "mapping_count": len(mappings),
                "file_types": list(set(k.split(":")[0] for k in mappings.keys())),
            })
    return projects


@router.post("/{project_id}/column-mappings/reference-copy")
async def reference_copy_mappings(
    project_id: UUID,
    body: ReferenceMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """从其他项目参照复制列映射"""
    from sqlalchemy import select
    from app.models.core import Project

    # 获取源项目的映射
    source = await db.execute(
        select(Project).where(Project.id == UUID(body.source_project_id))
    )
    source_project = source.scalar_one_or_none()
    if not source_project or not source_project.wizard_state:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="源项目不存在或无映射数据")

    source_mappings = (source_project.wizard_state or {}).get("column_mappings", {})
    if not source_mappings:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="源项目无已保存的列映射")

    # 复制到目标项目
    target = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)  # noqa: E712
    )
    target_project = target.scalar_one_or_none()
    if not target_project:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="目标项目不存在")

    state = target_project.wizard_state or {}
    if "column_mappings" not in state:
        state["column_mappings"] = {}
    state["column_mappings"].update(source_mappings)
    target_project.wizard_state = state

    await db.commit()
    return {
        "copied": True,
        "source_project": body.source_project_id,
        "mapping_count": len(source_mappings),
    }


class AccountUpdateItem(_BaseModel):
    """单个科目更新"""
    account_code: str
    account_name: str | None = None
    direction: str | None = None


class BatchUpdateRequest(_BaseModel):
    """批量更新科目"""
    updates: list[AccountUpdateItem]


@router.put("/{project_id}/account-chart/batch-update")
async def batch_update_accounts(
    project_id: UUID,
    body: BatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
) -> dict:
    """批量更新客户科目（名称、借贷方向）"""
    from app.models.audit_platform_models import AccountChart, AccountSource, AccountDirection

    updated = 0
    for item in body.updates:
        result = await db.execute(
            select(AccountChart).where(
                AccountChart.project_id == project_id,
                AccountChart.account_code == item.account_code,
                AccountChart.source == AccountSource.client,
                AccountChart.is_deleted == False,  # noqa: E712
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            continue

        if item.account_name is not None:
            row.account_name = item.account_name
        if item.direction is not None:
            try:
                row.direction = AccountDirection(item.direction)
            except ValueError:
                pass
        updated += 1

    await db.commit()
    return {"updated": updated, "total": len(body.updates)}
