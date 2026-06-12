"""底稿导出/导入增强 API 路由

新增端点（区别于已有 wp_download.py 的 download-file/upload-file）：
- POST /{wp_id}/export-with-metadata → StreamingResponse（嵌入元数据+记快照）
- POST /batch-export-enhanced → StreamingResponse (ZIP + manifest.json)
- GET  /{wp_id}/export-history → list[WpExportSnapshot]
- POST /{wp_id}/import-validate → ValidationReport（仅校验不执行）
- POST /import-enhanced → ImportResult（完整增强导入流程）
- POST /import/resolve → ImportResult（冲突解决）
- GET  /{wp_id}/versions → list[WpVersionArchive]

设计原则：
- router 层统一 commit（service 只 flush）
- Content-Disposition 使用 RFC5987 编码支持中文文件名
- 静态路径端点先于通配路径注册

Requirements: 1.1, 2.1, 3.3, 4.4, 5.6, 6.1
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional
from urllib.parse import quote
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.models.wp_export_models import WpExportSnapshot, WpVersionArchive
from app.schemas.wp_export_schemas import (
    ConflictResolution,
    ImportResult,
    ValidationReport,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers",
    tags=["wp-export-import"],
)


# ─── Request Schemas ──────────────────────────────────────────────────────────


class BatchExportEnhancedRequest(BaseModel):
    """批量增强导出请求体"""

    audit_cycles: list[str] = Field(..., description="要导出的审计循环代号列表")
    status_filter: Optional[list[str]] = Field(
        None, description="可选状态过滤 (draft/in_review/approved)"
    )


class ImportResolveRequest(BaseModel):
    """冲突解决请求体"""

    wp_id: UUID
    resolution: ConflictResolution
    file_content_b64: Optional[str] = Field(
        None, description="Base64 编码的文件内容（若需重新提交）"
    )
    filename: Optional[str] = None


# ─── 导出端点 ─────────────────────────────────────────────────────────────────


@router.post("/{wp_id}/export-with-metadata")
async def export_with_metadata(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """导出单份底稿（嵌入元数据 + 记录快照哈希）

    区别于 download-file：本端点嵌入 MetadataBundle 元数据并记录
    wp_export_snapshot，供后续导入时冲突检测使用。
    """
    from app.services.wp_export.export_engine import WpExportEngine

    engine = WpExportEngine()
    try:
        result = await engine.export_single(
            db=db,
            wp_id=wp_id,
            project_id=project_id,
            exported_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # router 层 commit
    await db.commit()

    # 构建 Content-Disposition（RFC5987 中文文件名）
    filename = result.filename
    ascii_name = filename.encode("ascii", "ignore").decode() or "workpaper.xlsx"
    utf8_name = quote(filename, safe="")
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"

    # 确定 MIME 类型
    if result.file_format == "docx":
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return StreamingResponse(
        BytesIO(result.file_content),
        media_type=media_type,
        headers={
            "Content-Disposition": disposition,
            "X-Snapshot-Hash": result.snapshot_hash,
            "X-File-Version": str(result.metadata.file_version),
        },
    )


@router.post("/batch-export-enhanced")
async def batch_export_enhanced(
    project_id: UUID,
    body: BatchExportEnhancedRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """批量增强导出为 ZIP（含 manifest.json + SHA-256 + 元数据嵌入）

    区别于 download-pack：本端点每份底稿嵌入元数据、记录快照，
    ZIP 根目录含 manifest.json 文件清单。
    """
    import zipfile

    from app.models.workpaper_models import WorkingPaper, WpIndex
    from app.services.wp_export.batch_packager import BatchPackager
    from app.services.wp_export.export_engine import WpExportEngine

    engine = WpExportEngine()

    # 查询指定循环的底稿
    stmt = (
        sa.select(WorkingPaper, WpIndex)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
            WpIndex.audit_cycle.in_(body.audit_cycles),
        )
    )
    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"指定循环 {body.audit_cycles} 下无可导出底稿",
        )

    # 逐底稿导出（失败跳过）
    workpapers_data: list[dict] = []
    for wp, idx in rows:
        # 状态过滤
        if body.status_filter and wp.status not in body.status_filter:
            continue

        wp_entry: dict = {
            "wp_code": idx.wp_code,
            "wp_name": idx.wp_name or "",
            "audit_cycle": idx.audit_cycle or "",
            "status": wp.status,
            "is_deleted": False,
            "file_format": "xlsx",
            "file_content": None,
            "error": None,
        }

        try:
            export_result = await engine.export_single(
                db=db,
                wp_id=wp.id,
                project_id=project_id,
                exported_by=current_user.id,
            )
            wp_entry["file_content"] = export_result.file_content
            wp_entry["file_format"] = export_result.file_format
        except Exception as e:
            logger.warning("批量导出失败 wp_code=%s: %s", idx.wp_code, e)
            wp_entry["error"] = str(e)

        workpapers_data.append(wp_entry)

    # 使用 BatchPackager 构建 manifest 和结构
    packager = BatchPackager()
    try:
        pack_result = packager.package(
            workpapers=workpapers_data,
            audit_cycles=body.audit_cycles,
            status_filter=body.status_filter,
            project_meta={
                "project_id": str(project_id),
                "exported_by": str(current_user.id),
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # 构建 ZIP
    import json

    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for zip_path, content in pack_result["zip_entries"]:
            zf.writestr(zip_path, content)
        # manifest.json
        manifest_json = json.dumps(
            pack_result["manifest"], ensure_ascii=False, indent=2
        )
        zf.writestr("manifest.json", manifest_json.encode("utf-8"))

    zip_buf.seek(0)

    # router 层 commit
    await db.commit()

    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=\"workpapers_enhanced.zip\"; "
            "filename*=UTF-8''workpapers_enhanced.zip",
        },
    )


@router.get("/{wp_id}/export-history")
async def get_export_history(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """查询底稿导出历史（WpExportSnapshot 列表）"""
    result = await db.execute(
        sa.select(WpExportSnapshot)
        .where(
            WpExportSnapshot.working_paper_id == wp_id,
            WpExportSnapshot.project_id == project_id,
        )
        .order_by(WpExportSnapshot.exported_at.desc())
    )
    snapshots = result.scalars().all()

    return [
        {
            "id": str(s.id),
            "working_paper_id": str(s.working_paper_id),
            "project_id": str(s.project_id),
            "file_version": s.file_version,
            "snapshot_hash": s.snapshot_hash,
            "exported_by": str(s.exported_by) if s.exported_by else None,
            "exported_at": s.exported_at.isoformat() if s.exported_at else None,
            "file_format": s.file_format,
            "file_size_bytes": s.file_size_bytes,
            "metadata_bundle": s.metadata_bundle,
        }
        for s in snapshots
    ]


# ─── 导入端点 ─────────────────────────────────────────────────────────────────


@router.post("/{wp_id}/import-validate")
async def import_validate(
    project_id: UUID,
    wp_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """仅校验导入文件（不执行实际导入）

    返回结构化 ValidationReport，前端据此展示校验结果。
    加载目标底稿的 render_schema 以进行结构/必填/数值校验。
    """
    from app.services.wp_export.format_validator import FormatValidator

    content = await file.read()
    filename = file.filename or "unknown.xlsx"

    # 加载 render_schema 以启用结构校验
    render_schema = None
    try:
        from app.models.workpaper_models import WorkingPaper, WpIndex
        from app.services.wp_render_schema_service import WpRenderSchemaService

        wp_result = await db.execute(
            sa.select(WpIndex.wp_code)
            .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
            .where(WorkingPaper.id == wp_id, WorkingPaper.project_id == project_id)
        )
        wp_code = wp_result.scalar()
        if wp_code:
            _schema_svc = WpRenderSchemaService()
            render_schema = _schema_svc.load_schema(wp_code=wp_code)
    except Exception:
        pass  # render_schema 加载失败时仅做 MIME 校验

    validator = FormatValidator()
    report = validator.validate(
        file_content=content,
        filename=filename,
        render_schema=render_schema,
    )

    return report.model_dump()


@router.post("/import-enhanced")
async def import_enhanced(
    project_id: UUID,
    file: UploadFile = File(...),
    force_overwrite: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """增强导入（元数据提取+校验+哈希冲突+归档+上传）

    完整流程编排，调用 WpImportEngine.import_file。
    冲突时返回 409 + conflict 详情。
    """
    from app.services.wp_export.import_engine import WpImportEngine

    content = await file.read()
    filename = file.filename or "unknown.xlsx"

    engine = WpImportEngine()
    resolution = ConflictResolution.FORCE_OVERWRITE if force_overwrite else None

    try:
        result = await engine.import_file(
            db=db,
            project_id=project_id,
            file_content=content,
            filename=filename,
            resolution=resolution,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 冲突时返回 409
    if result.status == "conflict":
        await db.commit()
        raise HTTPException(status_code=409, detail=result.model_dump(mode="json"))

    # 校验失败返回 422
    if result.status == "validation_error":
        await db.commit()
        raise HTTPException(status_code=422, detail=result.model_dump(mode="json"))

    # router 层统一 commit
    await db.commit()

    return result.model_dump(mode="json")


@router.post("/import/resolve")
async def import_resolve(
    project_id: UUID,
    body: ImportResolveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """冲突解决端点

    在 import-enhanced 返回 409 后，用户选择处理方式：
    - force_overwrite: 强制覆盖
    - parallel_version: 创建并行版本
    - cancel: 取消导入
    """
    import base64

    from app.services.wp_export.import_engine import WpImportEngine

    if body.resolution == ConflictResolution.CANCEL:
        return {
            "status": "cancelled",
            "wp_id": str(body.wp_id),
            "message": "用户取消导入",
        }

    # 需要文件内容才能执行 force_overwrite 或 parallel_version
    if not body.file_content_b64:
        raise HTTPException(
            status_code=400,
            detail="force_overwrite/parallel_version 需要提供 file_content_b64",
        )

    file_content = base64.b64decode(body.file_content_b64)
    filename = body.filename or "import.xlsx"

    engine = WpImportEngine()
    try:
        result = await engine.import_file(
            db=db,
            project_id=project_id,
            file_content=file_content,
            filename=filename,
            resolution=body.resolution,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # router 层统一 commit
    await db.commit()

    return result.model_dump(mode="json")


@router.get("/{wp_id}/versions")
async def get_version_history(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """查询底稿版本归档历史（WpVersionArchive 列表）"""
    result = await db.execute(
        sa.select(WpVersionArchive)
        .where(
            WpVersionArchive.working_paper_id == wp_id,
            WpVersionArchive.project_id == project_id,
        )
        .order_by(WpVersionArchive.version_no.desc())
    )
    archives = result.scalars().all()

    return [
        {
            "id": str(a.id),
            "working_paper_id": str(a.working_paper_id),
            "project_id": str(a.project_id),
            "version_no": a.version_no,
            "source": a.source,
            "content_hash": a.content_hash,
            "file_size_bytes": a.file_size_bytes,
            "archive_path": a.archive_path,
            "file_retained": a.file_retained,
            "created_by": str(a.created_by) if a.created_by else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in archives
    ]
