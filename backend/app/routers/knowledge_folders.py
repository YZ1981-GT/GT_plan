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


@router.get("/search")
async def search_documents(
    q: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """全文搜索（跨文件夹搜索文档名和内容）"""
    from app.models.knowledge_models import KnowledgeDocument, KnowledgeFolder
    import sqlalchemy as _sa

    query = (
        _sa.select(
            KnowledgeDocument.id,
            KnowledgeDocument.name,
            KnowledgeDocument.file_type,
            KnowledgeDocument.file_size,
            KnowledgeDocument.created_at,
            KnowledgeFolder.name.label("folder_name"),
            KnowledgeFolder.id.label("folder_id"),
        )
        .join(KnowledgeFolder, KnowledgeDocument.folder_id == KnowledgeFolder.id)
        .where(
            KnowledgeDocument.is_deleted == _sa.false(),
            KnowledgeFolder.is_deleted == _sa.false(),
            _sa.or_(
                KnowledgeDocument.name.ilike(f"%{q}%"),
                KnowledgeDocument.content_text.ilike(f"%{q}%"),
                KnowledgeDocument.tags.cast(_sa.String).ilike(f"%{q}%"),
            ),
        )
        .order_by(KnowledgeDocument.created_at.desc())
        .limit(50)
    )
    result = await db.execute(query)
    rows = result.all()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "file_type": r.file_type,
            "file_size": r.file_size,
            "folder_name": r.folder_name,
            "folder_id": str(r.folder_id),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.put("/folders/{folder_id}/rename")
async def rename_folder(
    folder_id: UUID,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重命名文件夹"""
    from app.models.knowledge_models import KnowledgeFolder
    import sqlalchemy as _sa

    new_name = data.get("name", "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="名称不能为空")

    result = await db.execute(
        _sa.select(KnowledgeFolder).where(
            KnowledgeFolder.id == folder_id,
            KnowledgeFolder.is_deleted == _sa.false(),
        )
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")

    folder.name = new_name
    await db.commit()
    return {"id": str(folder.id), "name": folder.name, "message": "重命名成功"}


@router.put("/documents/{doc_id}/move")
async def move_document(
    doc_id: UUID,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """移动文档到其他文件夹"""
    from app.models.knowledge_models import KnowledgeDocument, KnowledgeFolder
    import sqlalchemy as _sa

    target_folder_id = data.get("target_folder_id")
    if not target_folder_id:
        raise HTTPException(status_code=400, detail="目标文件夹不能为空")

    # 验证文档存在
    doc_result = await db.execute(
        _sa.select(KnowledgeDocument).where(
            KnowledgeDocument.id == doc_id,
            KnowledgeDocument.is_deleted == _sa.false(),
        )
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 验证目标文件夹存在
    folder_result = await db.execute(
        _sa.select(KnowledgeFolder).where(
            KnowledgeFolder.id == UUID(target_folder_id),
            KnowledgeFolder.is_deleted == _sa.false(),
        )
    )
    if not folder_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="目标文件夹不存在")

    doc.folder_id = UUID(target_folder_id)
    await db.commit()
    return {"id": str(doc.id), "name": doc.name, "new_folder_id": target_folder_id, "message": "移动成功"}


@router.get("/documents/{doc_id}/preview")
async def preview_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """文档预览（返回文本内容或下载链接）"""
    from app.models.knowledge_models import KnowledgeDocument
    import sqlalchemy as _sa

    result = await db.execute(
        _sa.select(KnowledgeDocument).where(
            KnowledgeDocument.id == doc_id,
            KnowledgeDocument.is_deleted == _sa.false(),
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 文本类文档直接返回内容
    if doc.content_text:
        return {
            "id": str(doc.id),
            "name": doc.name,
            "file_type": doc.file_type,
            "preview_type": "text",
            "content": doc.content_text[:100000],  # 最多 100K 字符
        }

    # 二进制文档返回下载链接
    if doc.storage_path:
        from pathlib import Path
        if Path(doc.storage_path).exists():
            return {
                "id": str(doc.id),
                "name": doc.name,
                "file_type": doc.file_type,
                "preview_type": "download",
                "download_url": f"/api/knowledge-library/documents/{doc_id}/download",
            }

    return {"id": str(doc.id), "name": doc.name, "preview_type": "unavailable", "message": "无法预览"}


@router.get("/documents/{doc_id}/download")
async def download_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """下载文档文件"""
    from app.models.knowledge_models import KnowledgeDocument
    from fastapi.responses import FileResponse
    from pathlib import Path
    import sqlalchemy as _sa

    result = await db.execute(
        _sa.select(KnowledgeDocument).where(
            KnowledgeDocument.id == doc_id,
            KnowledgeDocument.is_deleted == _sa.false(),
        )
    )
    doc = result.scalar_one_or_none()
    if not doc or not doc.storage_path:
        raise HTTPException(status_code=404, detail="文档不存在或无文件")

    file_path = Path(doc.storage_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(file_path, filename=doc.name)
