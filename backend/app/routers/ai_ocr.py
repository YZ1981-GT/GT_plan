"""AI OCR 识别路由

提供单据 OCR 识别接口：
- 单张上传识别
- 批量上传异步识别
- 任务进度查询
- 单据列表/提取结果/人工修正
- 触发匹配
"""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Path as PathParam, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models import (
    DocumentExtracted,
    DocumentMatch,
    DocumentScan,
    DocumentType,
    RecognitionStatus,
)
from app.models.ai_schemas import (
    DocumentScanResponse,
    DocumentMatchResponse,
    ExtractedFieldResponse,
    ExtractedFieldUpdate,
    OCRUploadResponse,
)
from app.services.ocr_service_v2 import OCRService, process_image_bytes, process_pdf_bytes

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai/ocr", tags=["AI-OCR"])

PROJECT_ID_DESC = "项目ID"
DOC_ID_DESC = "单据ID"


# ======================================================================
# 辅助函数
# ======================================================================

def _allowed_ext(filename: str) -> bool:
    return filename.lower().split(".")[-1] in {"pdf", "jpg", "jpeg", "png", "bmp", "tiff", "tif", "webp"}


def _save_upload(file: UploadFile, project_id: uuid.UUID) -> tuple[str, int]:
    """保存上传文件，返回 (file_path, file_size)"""
    upload_dir = Path(settings.STORAGE_ROOT) / "documents" / str(project_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = uuid.uuid4()
    safe_name = f"{file_id}_{file.filename}"
    file_path = upload_dir / safe_name

    size = 0
    with file_path.open("wb") as f:
        while chunk := file.file.read(8192):
            f.write(chunk)
            size += len(chunk)

    return str(file_path), size


# ======================================================================
# 6.1 / 通用 OCR 识别（保持向后兼容）
# ======================================================================

@router.post("/recognize")
async def recognize_document(
    file: UploadFile = File(..., description="上传图片或 PDF 文件"),
    ocr_type: str = "通用",
    db: AsyncSession = Depends(get_db),
) -> dict:
    """通用文档 OCR 识别（支持 PNG, JPG, PDF 等）"""
    content = await file.read()
    file_size = len(content)
    ext = file.filename.lower().split(".")[-1] if file.filename else ""

    if ext == "pdf":
        result = await process_pdf_bytes(content, ocr_type=ocr_type)
    elif ext in ("png", "jpg", "jpeg", "tiff", "tif", "bmp", "webp"):
        result = await process_image_bytes(content, ocr_type=ocr_type)
    else:
        raise HTTPException(status_code=400, detail="不支持的文件格式")

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "OCR 处理失败"))

    return {
        "success": True,
        "file_size": file_size,
        "items": result["items"],
        "full_text": result["full_text"],
        "stats": result["stats"],
    }


@router.post("/recognize/base64")
async def recognize_base64(
    image_data: str,
    ocr_type: str = "通用",
) -> dict:
    """Base64 编码图片 OCR 识别"""
    import base64 as b64

    try:
        decoded = b64.b64decode(image_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Base64 解码失败: {e}")

    result = await process_image_bytes(decoded, ocr_type=ocr_type)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "OCR 处理失败"))

    return {
        "success": True,
        "items": result["items"],
        "full_text": result["full_text"],
        "stats": result["stats"],
    }


# ======================================================================
# 6.4 — 业务接口
# ======================================================================

@router.post("/upload", response_model=OCRUploadResponse)
async def upload_and_recognize(
    project_id: Annotated[uuid.UUID, PathParam(description=PROJECT_ID_DESC)],
    file: UploadFile = File(..., description="单据图片或 PDF"),
    company_code: str | None = Query(None, description="公司代码"),
    year: str | None = Query(None, description="年度"),
    db: AsyncSession = Depends(get_db),
) -> OCRUploadResponse:
    """
    单张上传识别（POST /api/ai/ocr/upload）
    流程：保存文件 → OCR识别 → AI分类 → 字段提取 → 写入document_scan表
    """
    if not file.filename or not _allowed_ext(file.filename):
        raise HTTPException(status_code=400, detail="不支持的文件格式")

    # 保存文件
    file_path, file_size = _save_upload(file, project_id)

    # 创建扫描记录（初始pending）
    doc_scan = DocumentScan(
        id=uuid.uuid4(),
        project_id=project_id,
        company_code=company_code,
        year=year,
        file_path=file_path,
        file_name=file.filename,
        file_size=file_size,
        document_type=DocumentType.other,
        recognition_status=RecognitionStatus.processing,
    )
    db.add(doc_scan)
    await db.commit()
    await db.refresh(doc_scan)

    try:
        ocr = OCRService(db)

        # OCR识别
        ocr_result = await ocr.recognize_single(file_path)
        if not ocr_result.get("success"):
            doc_scan.recognition_status = RecognitionStatus.failed
            await db.commit()
            raise HTTPException(status_code=500, detail=ocr_result.get("error", "OCR识别失败"))

        full_text = ocr_result["full_text"]

        # AI分类
        doc_type = await ocr.classify_document(full_text)

        # 更新分类
        doc_scan.document_type = DocumentType(doc_type)
        doc_scan.recognition_status = RecognitionStatus.completed
        await db.commit()

        # AI字段提取（存入document_extracted）
        fields = await ocr.extract_fields(full_text, doc_type)
        for f in fields:
            extracted = DocumentExtracted(
                id=uuid.uuid4(),
                document_scan_id=doc_scan.id,
                field_name=f["field_name"],
                field_value=f["field_value"],
                confidence_score=Decimal(str(f.get("confidence_score", 0.5))),
                human_confirmed=False,
            )
            db.add(extracted)

        await db.commit()

        return OCRUploadResponse(
            document_id=doc_scan.id,
            file_name=doc_scan.file_name,
            recognition_status=doc_scan.recognition_status,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("upload_and_recognize failed")
        doc_scan.recognition_status = RecognitionStatus.failed
        await db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-upload")
async def batch_upload(
    project_id: Annotated[uuid.UUID, PathParam(description=PROJECT_ID_DESC)],
    files: list[UploadFile] = File(..., description="多个单据文件"),
    user_id: uuid.UUID | None = Query(None, description="用户ID"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    批量上传异步识别（POST /api/ai/ocr/batch-upload）
    立即返回task_id，后台异步处理
    """
    if not files:
        raise HTTPException(status_code=400, detail="未上传文件")

    file_paths = []
    for file in files:
        if not file.filename or not _allowed_ext(file.filename):
            raise HTTPException(status_code=400, detail=f"不支持的文件: {file.filename}")
        file_path, _ = _save_upload(file, project_id)
        file_paths.append(file_path)

    ocr = OCRService(db)
    task_id = await ocr.batch_recognize(project_id, file_paths, user_id)

    return {"task_id": task_id, "total_files": len(file_paths)}


@router.get("/task/{task_id}")
async def get_ocr_task_status(task_id: str) -> dict:
    """
    查询异步任务进度（GET /api/ai/ocr/task/{task_id}）
    """
    from app.services.ocr_service_v2 import _task_status

    status = _task_status.get(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="任务不存在")

    return status


# ======================================================================
# 6.4 — 单据管理接口（挂载在 /api/projects/{id}/documents 下）
# ======================================================================

document_router = APIRouter(prefix="/api/projects/{project_id}/documents", tags=["AI-Documents"])


@document_router.get("", response_model=list[DocumentScanResponse])
async def list_documents(
    project_id: Annotated[uuid.UUID, PathParam(description=PROJECT_ID_DESC)],
    document_type: DocumentType | None = Query(None),
    status: RecognitionStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentScan]:
    """
    单据列表（GET /api/projects/{id}/documents）
    """
    query = select(DocumentScan).where(DocumentScan.project_id == project_id)

    if document_type:
        query = query.where(DocumentScan.document_type == document_type)
    if status:
        query = query.where(DocumentScan.recognition_status == status)

    query = query.order_by(DocumentScan.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    return result.scalars().all()


@document_router.get("/{document_id}/extracted")
async def get_extracted_fields(
    project_id: Annotated[uuid.UUID, PathParam(description=PROJECT_ID_DESC)],
    document_id: Annotated[uuid.UUID, PathParam(description=DOC_ID_DESC)],
    db: AsyncSession = Depends(get_db),
) -> list[ExtractedFieldResponse]:
    """
    获取单据提取结果（GET /api/projects/{id}/documents/{did}/extracted）
    """
    # 验证单据归属
    scan = await db.get(DocumentScan, document_id)
    if not scan or scan.project_id != project_id:
        raise HTTPException(status_code=404, detail="单据不存在")

    result = await db.execute(
        select(DocumentExtracted).where(
            DocumentExtracted.document_scan_id == document_id
        )
    )
    return result.scalars().all()


@document_router.put("/{document_id}/extracted/{field_id}")
async def update_extracted_field(
    project_id: Annotated[uuid.UUID, PathParam(description=PROJECT_ID_DESC)],
    document_id: Annotated[uuid.UUID, PathParam(description=DOC_ID_DESC)],
    field_id: uuid.UUID = PathParam(description="字段ID"),
    update_data: ExtractedFieldUpdate = ...,
    db: AsyncSession = Depends(get_db),
) -> ExtractedFieldResponse:
    """
    人工修正提取字段（PUT /api/projects/{id}/documents/{did}/extracted/{eid}）
    """
    field = await db.get(DocumentExtracted, field_id)
    if not field or str(field.document_scan_id) != str(document_id):
        raise HTTPException(status_code=404, detail="字段不存在")

    # 更新
    field.field_value = update_data.field_value
    field.human_confirmed = update_data.human_confirmed
    if update_data.human_confirmed:
        field.confirmation_status = "confirmed"  # type: ignore

    await db.commit()
    await db.refresh(field)
    return ExtractedFieldResponse.model_validate(field)


@document_router.post("/{document_id}/match")
async def trigger_matching(
    project_id: Annotated[uuid.UUID, PathParam(description=PROJECT_ID_DESC)],
    document_id: Annotated[uuid.UUID, PathParam(description=DOC_ID_DESC)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    触发单据匹配（POST /api/projects/{id}/documents/{did}/match）
    按金额+日期+对方单位关键词匹配 journal_entries
    """
    from app.services.ocr_service_v2 import match_with_ledger

    # 验证单据
    scan = await db.get(DocumentScan, document_id)
    if not scan or scan.project_id != project_id:
        raise HTTPException(status_code=404, detail="单据不存在")

    result = await match_with_ledger(db, document_id, project_id)

    if result:
        return DocumentMatchResponse.model_validate(result).model_dump()
    else:
        return {
            "document_scan_id": str(document_id),
            "match_result": "no_match",
            "message": "未找到匹配账目",
        }
