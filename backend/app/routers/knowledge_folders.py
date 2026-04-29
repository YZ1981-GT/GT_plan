"""知识库文件夹与文档管理 API

支持树形目录、文档 CRUD、项目组权限、批量操作。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.knowledge_folder_service import (
    KnowledgeDocumentService,
    KnowledgeFolderService,
)

router = APIRouter(prefix="/api/knowledge-library", tags=["知识库管理"])


class FolderCreateRequest(BaseModel):
    name: str
    parent_id: str | None = None
    access_level: str = "public"
    project_ids: list[str] | None = None


class DocumentCreateRequest(BaseModel):
    name: str
    content_text: str | None = None
    file_type: str | None = None
    tags: list[str] | None = None
    access_level: str | None = None
    project_ids: list[str] | None = None


@router.get("/tree")
async def get_folder_tree(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取知识库完整文件夹树（含权限过滤）"""
    svc = KnowledgeFolderService(db)
    tree = await svc.get_folder_tree()
    return tree


@router.post("/folders")
async def create_folder(
    data: FolderCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建文件夹"""
    svc = KnowledgeFolderService(db)
    folder = await svc.create_folder(
        name=data.name,
        parent_id=UUID(data.parent_id) if data.parent_id else None,
        access_level=data.access_level,
        project_ids=data.project_ids,
        created_by=current_user.id,
    )
    await db.commit()
    return {"id": str(folder.id), "name": folder.name, "message": "文件夹创建成功"}


@router.get("/folders/{folder_id}/documents")
async def list_documents(
    folder_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出文件夹下的文档"""
    svc = KnowledgeDocumentService(db)
    docs = await svc.list_documents(folder_id)
    return [
        {
            "id": str(d.id),
            "name": d.name,
            "file_type": d.file_type,
            "file_size": d.file_size,
            "tags": d.tags,
            "access_level": d.access_level.value if d.access_level else None,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]


@router.post("/folders/{folder_id}/documents")
async def create_document(
    folder_id: UUID,
    data: DocumentCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建文档（文本内容）"""
    svc = KnowledgeDocumentService(db)
    doc = await svc.create_document(
        folder_id=folder_id,
        name=data.name,
        content_text=data.content_text,
        file_type=data.file_type,
        tags=data.tags,
        access_level=data.access_level,
        project_ids=data.project_ids,
        created_by=current_user.id,
    )
    await db.commit()
    return {"id": str(doc.id), "name": doc.name, "message": "文档创建成功"}


@router.post("/folders/{folder_id}/upload")
async def upload_documents(
    folder_id: UUID,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量上传文档文件"""
    from app.core.config import settings
    from pathlib import Path
    import shutil

    svc = KnowledgeDocumentService(db)
    storage_base = Path(settings.STORAGE_ROOT) / "knowledge" / str(folder_id)
    storage_base.mkdir(parents=True, exist_ok=True)

    uploaded = []
    for file in files:
        if not file.filename:
            continue
        # 保存文件
        file_path = storage_base / file.filename
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # 提取文本内容
        content_text = None
        filename_lower = file.filename.lower()
        if filename_lower.endswith((".txt", ".md")):
            content_text = content.decode("utf-8", errors="ignore")[:50000]
        elif filename_lower.endswith(".docx"):
            # Word 文档提取文本
            try:
                import io
                from docx import Document as DocxDocument
                doc_obj = DocxDocument(io.BytesIO(content))
                paragraphs = [p.text for p in doc_obj.paragraphs if p.text.strip()]
                content_text = "\n".join(paragraphs)[:50000]
            except Exception:
                pass
        elif filename_lower.endswith(".pdf"):
            # PDF 提取文本（简单方式，复杂 PDF 需要 OCR）
            try:
                import io
                import PyPDF2
                reader = PyPDF2.PdfReader(io.BytesIO(content))
                pages_text = []
                for page in reader.pages[:50]:  # 最多 50 页
                    text = page.extract_text()
                    if text:
                        pages_text.append(text)
                content_text = "\n".join(pages_text)[:50000]
            except Exception:
                pass

        doc = await svc.create_document(
            folder_id=folder_id,
            name=file.filename,
            file_type=file.filename.rsplit(".", 1)[-1] if "." in file.filename else None,
            file_size=len(content),
            storage_path=str(file_path),
            content_text=content_text,
            created_by=current_user.id,
        )
        uploaded.append({"id": str(doc.id), "name": doc.name, "size": len(content), "text_extracted": content_text is not None})

    await db.commit()
    return {"uploaded": len(uploaded), "files": uploaded}


@router.delete("/folders/{folder_id}")
async def delete_folder(
    folder_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除文件夹（含子文件夹和文档）"""
    svc = KnowledgeFolderService(db)
    await svc.delete_folder(folder_id)
    await db.commit()
    return {"message": "文件夹已删除"}


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除文档"""
    svc = KnowledgeDocumentService(db)
    await svc.delete_document(doc_id)
    await db.commit()
    return {"message": "文档已删除"}


@router.post("/init-presets")
async def init_preset_folders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """初始化预制分类文件夹（幂等）"""
    svc = KnowledgeFolderService(db)
    count = await svc.init_preset_folders()
    await db.commit()
    return {"message": f"初始化了 {count} 个预制文件夹", "created": count}
