"""AI 合同分析路由

提供合同文本上传、分析和管理接口。
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.services.contract_analysis_service import ContractAnalysisService
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai/contract", tags=["AI-合同分析"])


class ContractAnalysisRequest(BaseModel):
    """合同分析请求"""
    project_id: str
    contract_text: str
    contract_type: str = "采购合同"
    analysis_type: str = "full"


class ContractAnalysisResponse(BaseModel):
    """合同分析响应"""
    report_id: str
    document_type: str
    analysis_type: str
    summary: str
    status: str


@router.post("/analyze")
async def analyze_contract(
    request: ContractAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    分析合同文本

    Args:
        request: 包含合同文本和分析类型

    Returns:
        分析报告
    """
    from uuid import UUID

    analysis_types = ["full", "risk", "clause"]
    if request.analysis_type not in analysis_types:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的分析类型: {request.analysis_type}",
        )

    service = ContractAnalysisService(db)
    ai_service = AIService(db)

    try:
        report = await service.analyze_contract(
            project_id=UUID(request.project_id),
            contract_text=request.contract_text,
            contract_type=request.contract_type,
            analysis_type=request.analysis_type,
            ai_service=ai_service,
            user_id=str(user.id),
        )

        return {
            "report_id": str(report.id),
            "document_type": report.document_type,
            "analysis_type": report.analysis_type,
            "summary": report.summary,
            "status": report.status,
        }
    except Exception as e:
        logger.exception("Contract analysis failed")
        raise HTTPException(status_code=500, detail=f"分析失败: {e}")


@router.post("/analyze/file")
async def analyze_contract_file(
    file: UploadFile = File(...),
    project_id: str = "",
    contract_type: str = "采购合同",
    analysis_type: str = "full",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    上传合同文件并分析

    支持格式: TXT, PDF, DOCX
    """
    from uuid import UUID

    content = await file.read()
    file_size = len(content)

    if file_size > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件大小超过 10MB")

    filename = file.filename or ""
    ext = filename.lower().split(".")[-1] if "." in filename else ""

    # 提取文本
    if ext == "txt":
        contract_text = content.decode("utf-8", errors="replace")
    elif ext == "pdf":
        # 简单的 PDF 文本提取（完整实现需要 pdfplumber）
        try:
            import pdfplumber
            import io
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                contract_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        except ImportError:
            raise HTTPException(status_code=400, detail="PDF 处理需要安装 pdfplumber")
        except Exception:
            raise HTTPException(status_code=400, detail="PDF 文本提取失败")
    elif ext in ("docx", "doc"):
        try:
            from docx import Document
            import io
            doc = Document(io.BytesIO(content))
            contract_text = "\n".join(p.text for p in doc.paragraphs)
        except Exception:
            raise HTTPException(status_code=400, detail="Word 文档读取失败")
    else:
        raise HTTPException(status_code=400, detail=f"不支持的格式: .{ext}")

    if not project_id:
        raise HTTPException(status_code=400, detail="project_id 不能为空")

    service = ContractAnalysisService(db)
    ai_service = AIService(db)

    try:
        report = await service.analyze_contract(
            project_id=UUID(project_id),
            contract_text=contract_text,
            contract_type=contract_type,
            analysis_type=analysis_type,
            ai_service=ai_service,
            user_id=str(user.id),
        )

        return {
            "report_id": str(report.id),
            "filename": filename,
            "document_type": report.document_type,
            "analysis_type": report.analysis_type,
            "summary": report.summary,
            "status": report.status,
        }
    except Exception as e:
        logger.exception("Contract file analysis failed")
        raise HTTPException(status_code=500, detail=f"分析失败: {e}")


@router.get("/reports/{report_id}")
async def get_analysis_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """获取分析报告详情"""
    from uuid import UUID

    service = ContractAnalysisService(db)
    report = await service.get_report(UUID(report_id))

    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    items = await service.get_report_items(report.id)

    return {
        "report_id": str(report.id),
        "document_type": report.document_type,
        "document_name": report.document_name,
        "analysis_type": report.analysis_type,
        "summary": report.summary,
        "full_content": report.full_content,
        "status": report.status,
        "token_usage": report.token_usage,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "items": [
            {
                "item_type": item.item_type,
                "item_title": item.item_title,
                "item_content": item.item_content,
                "severity": item.severity,
                "page_reference": item.page_reference,
            }
            for item in items
        ],
    }


@router.get("/reports")
async def list_reports(
    project_id: str,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """列出项目的合同分析报告"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.ai_models import AIAnalysisReport

    result = await db.execute(
        select(AIAnalysisReport)
        .where(
            AIAnalysisReport.project_id == UUID(project_id),
            AIAnalysisReport.document_type == "contract",
        )
        .order_by(AIAnalysisReport.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    reports = result.scalars().all()
    return [
        {
            "report_id": str(r.id),
            "document_name": r.document_name,
            "analysis_type": r.analysis_type,
            "summary": r.summary,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reports
    ]


class ContractUploadResponse(BaseModel):
    contract_id: str
    file_name: str
    file_size: int
    uploaded_at: str


class BatchAnalyzeRequest(BaseModel):
    contract_ids: list[str]


class CrossReferenceRequest(BaseModel):
    pass  # uses path params


class LinkWorkpaperRequest(BaseModel):
    workpaper_id: str
    link_type: str  # direct / reference / backup


@router.post("/projects/{project_id}/contracts/upload")
async def upload_contract(
    project_id: str,
    file: UploadFile = File(...),
    contract_type: str = "采购合同",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """上传合同文件"""
    from uuid import UUID
    from app.models.ai_models import DocumentScan

    # Save file
    import os, uuid, aiofiles
    upload_dir = f"uploads/contracts/{project_id}"
    os.makedirs(upload_dir, exist_ok=True)
    file_id = uuid.uuid4()
    file_path = f"{upload_dir}/{file_id}_{file.filename}"
    content = await file.read()
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    # Record in document_scan table
    doc = DocumentScan(
        id=file_id,
        project_id=UUID(project_id),
        company_code=None,
        year=None,
        file_path=file_path,
        file_name=file.filename,
        file_size=len(content),
        document_type="contract",
        recognition_status="pending",
        uploaded_by=user.id,
    )
    db.add(doc)
    await db.commit()
    return {
        "contract_id": str(file_id),
        "file_name": file.filename,
        "file_size": len(content),
        "uploaded_at": datetime.utcnow().isoformat(),
    }


@router.post("/projects/{project_id}/contracts/batch-analyze")
async def batch_analyze_contracts(
    project_id: str,
    req: BatchAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """批量合同分析"""
    from uuid import UUID
    from celery import Celery

    service = ContractAnalysisService(db)
    task_id = await service.batch_analyze(
        project_id=UUID(project_id),
        contract_ids=[UUID(cid) for cid in req.contract_ids],
        user_id=str(user.id),
    )
    return {"task_id": task_id, "status": "queued"}


@router.get("/projects/{project_id}/contracts")
async def list_contracts(
    project_id: str,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """合同列表"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.ai_models import DocumentScan

    result = await db.execute(
        select(DocumentScan)
        .where(
            DocumentScan.project_id == UUID(project_id),
            DocumentScan.document_type == "contract",
            DocumentScan.is_deleted == False,  # noqa: E712
        )
        .order_by(DocumentScan.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    docs = result.scalars().all()
    return [
        {
            "contract_id": str(d.id),
            "file_name": d.file_name,
            "file_size": d.file_size,
            "recognition_status": d.recognition_status,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]


@router.get("/projects/{project_id}/contracts/{contract_id}/extracted")
async def get_contract_extracted(
    project_id: str,
    contract_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取合同提取结果"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.ai_models import DocumentExtracted

    result = await db.execute(
        select(DocumentExtracted).where(
            DocumentExtracted.document_scan_id == UUID(contract_id)
        )
    )
    items = result.scalars().all()
    return {
        "contract_id": contract_id,
        "extracted_fields": [
            {
                "field_name": i.field_name,
                "field_value": i.field_value,
                "confidence_score": float(i.confidence_score) if i.confidence_score else None,
                "human_confirmed": i.human_confirmed,
            }
            for i in items
        ],
    }


@router.post("/projects/{project_id}/contracts/{contract_id}/cross-reference")
async def cross_reference_contract(
    project_id: str,
    contract_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """合同与账面交叉比对"""
    from uuid import UUID

    service = ContractAnalysisService(db)
    result = await service.cross_reference_ledger(
        contract_id=UUID(contract_id),
        project_id=UUID(project_id),
    )
    return {"contract_id": contract_id, "cross_references": result}


@router.post("/projects/{project_id}/contracts/{contract_id}/link-workpaper")
async def link_contract_workpaper(
    project_id: str,
    contract_id: str,
    req: LinkWorkpaperRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """关联合同与底稿"""
    from uuid import UUID

    service = ContractAnalysisService(db)
    result = await service.link_to_workpaper(
        contract_id=UUID(contract_id),
        workpaper_id=UUID(req.workpaper_id),
        link_type=req.link_type,
    )
    return result


@router.get("/projects/{project_id}/contracts/summary")
async def get_contract_summary(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """合同汇总报告"""
    from uuid import UUID

    service = ContractAnalysisService(db)
    result = await service.generate_contract_summary(UUID(project_id))
    return {"project_id": project_id, "summary": result}

