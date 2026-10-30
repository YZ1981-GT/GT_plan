"""批量建项与集团树导入路由。"""
from __future__ import annotations

from datetime import date as date_type
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, readable_project_ids, require_project_access, require_role
from app.models.core import User
from app.services import consol_tree_service
from app.services.batch_project_service import (
    BatchImportResult,
    BatchValidateResponse,
    export_group_tree,
    export_projects,
    generate_template,
    parse_and_import,
)
from app.services.batch_project_workbook import MAX_UPLOAD_BYTES
from app.services.batch_project_execution import (
    BatchApplyRequest,
    BatchPlanStatusResponse,
    apply_validation_plan,
    build_plan_error_workbook,
    create_validation_plan,
    get_readable_plan,
    mark_plan_failed,
    plan_status_response,
)

router = APIRouter(prefix="/api/projects", tags=["批量建项"])
_BATCH_CREATE_USER = require_role(["admin", "partner", "manager"])
_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _make_content_disposition(filename: str) -> str:
    encoded = quote(filename, safe="")
    return f"attachment; filename*=UTF-8''{encoded}"


async def _read_xlsx(file: UploadFile) -> bytes:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix != ".xlsx":
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式文件")
    content = bytearray()
    while True:
        chunk = await file.read(min(1024 * 1024, MAX_UPLOAD_BYTES + 1 - len(content)))
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="文件超过 5MB，请精简后重新上传")
    return bytes(content)


@router.get("/batch-template")
async def download_batch_template(
    mode: Literal["project", "consolidation"] = Query("project"),
    current_user: User = Depends(_BATCH_CREATE_USER),
) -> StreamingResponse:
    output = await generate_template(mode=mode)
    filename = "合并批量建项模板.xlsx" if mode == "consolidation" else "建项模板.xlsx"
    return StreamingResponse(
        output,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": _make_content_disposition(filename)},
    )


@router.get("/tree")
async def get_group_tree(
    year: int | None = None,
    scope: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    effective_scope = None if scope in (None, "", "all") else scope
    return await consol_tree_service.build_tree_by_codes(
        db, year=year, scope=effective_scope, user=current_user
    )


@router.post("/batch-validate", response_model=BatchValidateResponse)
async def batch_validate_projects(
    file: UploadFile = File(...),
    idempotency_key: str | None = Form(None),
    mode: Literal["project", "consolidation"] = Query("project"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_BATCH_CREATE_USER),
) -> BatchValidateResponse:
    file_bytes = await _read_xlsx(file)
    _plan, response, _reused = await create_validation_plan(
        file_bytes, db, actor=current_user,
        file_name=file.filename or "建项模板.xlsx", mode=mode,
        idempotency_key=idempotency_key,
    )
    await db.commit()
    return response


@router.post("/batch-apply", response_model=BatchImportResult)
async def batch_apply_projects(
    body: BatchApplyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_BATCH_CREATE_USER),
) -> BatchImportResult:
    try:
        result = await apply_validation_plan(
            db, plan_id=body.validation_id, actor=current_user,
            idempotency_key=body.idempotency_key,
        )
        await db.commit()
        return result
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        try:
            await mark_plan_failed(
                db, plan_id=body.validation_id, actor=current_user, error=exc
            )
            await db.commit()
        except Exception:
            await db.rollback()
        if isinstance(exc, IntegrityError):
            raise HTTPException(
                status_code=409,
                detail="项目或集团关系已被其他操作修改，请重新预校验",
            ) from exc
        raise HTTPException(
            status_code=500,
            detail="批量建项执行失败，已全部回滚，请重新预校验后重试",
        ) from exc


@router.get("/batch-imports/{validation_id}", response_model=BatchPlanStatusResponse)
async def get_batch_import_status(
    validation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BatchPlanStatusResponse:
    # 等待 apply 持有的计划行锁，避免在未提交窗口读取旧的 validated 快照并误报未写入。
    plan = await get_readable_plan(db, validation_id, current_user, for_update=True)
    return plan_status_response(plan)


@router.get("/batch-imports/{validation_id}/errors.xlsx")
async def download_batch_import_errors(
    validation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    output = await build_plan_error_workbook(
        db, plan_id=validation_id, actor=current_user
    )
    return StreamingResponse(
        output,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": _make_content_disposition("批量建项错误明细.xlsx")},
    )


@router.post("/batch-import", response_model=BatchImportResult)
async def batch_import_projects(
    file: UploadFile = File(...),
    mode: Literal["project", "consolidation"] = Query("project"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_BATCH_CREATE_USER),
) -> BatchImportResult:
    """兼容入口：错误行隔离且回执准确；新前端走持久计划的整批原子 apply。"""
    file_bytes = await _read_xlsx(file)
    return await parse_and_import(
        file_bytes, db, current_user=current_user, mode=mode
    )


@router.get("/{project_id}/group-import-template")
async def export_group_import_template(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    # 合并项目本身的读权限走门禁（与 readable_project_ids 同口径：admin 放行，其余看本人成员行）；
    # 企业树里每个项目还须可读，见下方子集校验（2026-10-30 同步：远端「仅登录不校项目」棘轮已收紧到 165）
    current_user: User = Depends(require_project_access("readonly")),
) -> StreamingResponse:
    output, project_ids = await export_group_tree(project_id, db)
    readable = await readable_project_ids(db, current_user)
    if readable is not None and not set(project_ids).issubset(readable):
        raise HTTPException(status_code=403, detail="当前企业树包含无权读取的项目，不能导出")
    filename = f"当前集团树_{date_type.today():%Y%m%d}.xlsx"
    return StreamingResponse(
        output,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": _make_content_disposition(filename)},
    )


class BatchExportRequest(BaseModel):
    project_ids: list[UUID]


@router.post("/batch-export")
async def batch_export_projects(
    body: BatchExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    requested = set(body.project_ids)
    if not requested:
        raise HTTPException(status_code=422, detail="请至少选择一个项目")
    readable = await readable_project_ids(db, current_user)
    if readable is not None and not requested.issubset(readable):
        raise HTTPException(status_code=403, detail="无权导出所选项目")
    output = await export_projects(body.project_ids, db)
    filename = f"项目数据导出_{date_type.today():%Y%m%d}.xlsx"
    return StreamingResponse(
        output,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": _make_content_disposition(filename)},
    )
