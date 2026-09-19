"""全局知识库 + 项目级知识库 API

全局知识库（/api/knowledge）：所有项目共享的参考资料
  - 9 个分类：底稿模板/监管规定/会计准则/质控标准/审计程序/行业指引/提示词/报告模板/笔记
  - 上传委托 KnowledgeFolderService + 自动触发索引流水线

项目级知识库（/api/projects/{id}/knowledge）：项目专属文档
  - 文件存储在 storage/projects/{id}/knowledge/
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.knowledge_models import KnowledgeAccessLevel, KnowledgeFolder
from app.services.knowledge_folder_service import (
    KnowledgeDocumentService,
    PRESET_CATEGORIES,
)
from app.services.indexing_pipeline import run_indexing_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge-base"])

# 全局知识库根目录
_GLOBAL_ROOT = Path.home() / ".gt_audit_helper" / "knowledge"

# 项目知识库根目录
_PROJECT_ROOT = Path("storage") / "projects"

# 9 个全局知识库分类
LIBRARY_DEFS = [
    {"key": "workpaper_templates", "name": "底稿模板库", "icon": "📋", "description": "审计底稿模板文件"},
    {"key": "regulations", "name": "监管规定库", "icon": "⚖️", "description": "监管机构发布的规定和通知"},
    {"key": "accounting_standards", "name": "会计准则库", "icon": "📖", "description": "企业会计准则及解释"},
    {"key": "quality_control", "name": "质控标准库", "icon": "✅", "description": "质量控制标准和指引"},
    {"key": "audit_procedures", "name": "审计程序库", "icon": "📝", "description": "审计程序模板和参考"},
    {"key": "industry_guides", "name": "行业指引库", "icon": "🏭", "description": "各行业审计指引"},
    {"key": "prompts", "name": "提示词库", "icon": "💡", "description": "AI 提示词模板"},
    {"key": "report_templates", "name": "报告模板库", "icon": "📄", "description": "审计报告模板"},
    {"key": "notes", "name": "笔记库", "icon": "📌", "description": "个人笔记和备忘"},
]

VALID_CATEGORIES = {d["key"] for d in LIBRARY_DEFS}


async def _get_or_create_preset_folder(db: AsyncSession, category: str) -> KnowledgeFolder:
    """获取或创建预制分类文件夹（幂等）。

    按 category 查询已存在的顶级文件夹，不存在则创建。
    """
    result = await db.execute(
        sa.select(KnowledgeFolder).where(
            KnowledgeFolder.category == category,
            KnowledgeFolder.parent_id.is_(None),
            KnowledgeFolder.is_deleted == sa.false(),
        )
    )
    folder = result.scalar_one_or_none()
    if folder:
        return folder

    # 从 PRESET_CATEGORIES 取名称
    name = category
    for preset in PRESET_CATEGORIES:
        if preset["category"] == category:
            name = preset["name"]
            break

    folder = KnowledgeFolder(
        id=uuid.uuid4(),
        name=name,
        category=category,
        parent_id=None,
        access_level=KnowledgeAccessLevel.public,
    )
    db.add(folder)
    await db.flush()
    return folder


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _list_files(directory: Path) -> list[dict]:
    """列出目录下的文件"""
    if not directory.exists():
        return []
    files = []
    for f in sorted(directory.iterdir()):
        if f.is_file() and not f.name.startswith("."):
            stat = f.stat()
            files.append({
                "id": f.name,
                "name": f.name,
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    return files


# ═══════════════════════════════════════════════════════════
# 全局知识库 API
# ═══════════════════════════════════════════════════════════


@router.get("/api/knowledge/libraries")
async def list_libraries(current_user: User = Depends(get_current_user)):
    """获取全局知识库分类列表（含文档计数）"""
    result = []
    for lib in LIBRARY_DEFS:
        lib_dir = _GLOBAL_ROOT / lib["key"]
        doc_count = len(_list_files(lib_dir)) if lib_dir.exists() else 0
        result.append({**lib, "doc_count": doc_count})
    return result


@router.get("/api/knowledge/{category}/documents")
async def list_global_documents(
    category: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出全局知识库某分类下的文档（合并文件系统 + PG 数据源）

    Response headers include X-Deprecated and X-New-Endpoint for migration guidance.
    """
    from fastapi.responses import JSONResponse

    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"无效分类: {category}")

    # 从 PG preset folder 查询已入库文档
    from app.models.knowledge_models import KnowledgeDocument

    folder_result = await db.execute(
        sa.select(KnowledgeFolder).where(
            KnowledgeFolder.category == category,
            KnowledgeFolder.parent_id.is_(None),
            KnowledgeFolder.is_deleted == sa.false(),
        )
    )
    folder = folder_result.scalar_one_or_none()

    db_docs: list[dict] = []
    if folder:
        docs_result = await db.execute(
            sa.select(KnowledgeDocument).where(
                KnowledgeDocument.folder_id == folder.id,
                KnowledgeDocument.is_deleted == sa.false(),
            )
        )
        for doc in docs_result.scalars().all():
            db_docs.append({
                "id": str(doc.id),
                "name": doc.name,
                "size": doc.file_size or 0,
                "modified_at": doc.updated_at.isoformat() if doc.updated_at else None,
            })

    # 合并文件系统中的遗留文件（未迁移的）
    fs_docs = _list_files(_GLOBAL_ROOT / category)
    db_names = {d["name"] for d in db_docs}
    for fs_doc in fs_docs:
        if fs_doc["name"] not in db_names:
            db_docs.append(fs_doc)

    folder_id = str(folder.id) if folder else "unknown"
    return JSONResponse(
        content=db_docs,
        headers={
            "X-Deprecated": "true",
            "X-New-Endpoint": f"/api/knowledge/folders/{folder_id}/documents",
        },
    )


@router.post("/api/knowledge/{category}/documents")
async def upload_global_document(
    category: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """上传文档到全局知识库（委托 KnowledgeFolderService + 触发索引流水线）"""
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"无效分类: {category}")
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件")

    # 获取或创建预制分类文件夹
    folder = await _get_or_create_preset_folder(db, category)

    # 存储文件到本地
    from app.core.config import settings

    storage_root = Path(settings.STORAGE_ROOT)
    if not storage_root.is_absolute():
        backend_root = Path(__file__).resolve().parent.parent.parent
        storage_root = backend_root / settings.STORAGE_ROOT
    storage_base = storage_root / "knowledge" / str(folder.id)
    storage_base.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename).name or file.filename
    dest = storage_base / safe_name
    content = await file.read()
    dest.write_bytes(content)

    # 委托 KnowledgeDocumentService 创建文档记录
    svc = KnowledgeDocumentService(db)
    doc = await svc.create_document(
        folder_id=folder.id,
        name=safe_name,
        storage_path=str(dest),
        file_size=len(content),
        file_type=safe_name.rsplit(".", 1)[-1] if "." in safe_name else None,
        created_by=current_user.id,
    )
    await db.commit()

    # 触发索引流水线
    background_tasks.add_task(run_indexing_pipeline, doc.id)

    logger.info(
        "Global knowledge uploaded: %s/%s (%d bytes) by %s",
        category, safe_name, len(content), current_user.username,
    )
    return {
        "id": str(doc.id),
        "name": safe_name,
        "size": len(content),
        "category": category,
        "message": "上传成功",
    }


@router.delete("/api/knowledge/{category}/documents/{filename}")
async def delete_global_document(
    category: str,
    filename: str,
    current_user: User = Depends(get_current_user),
):
    """删除全局知识库文档"""
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"无效分类: {category}")

    file_path = _GLOBAL_ROOT / category / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    file_path.unlink()
    logger.info("Global knowledge deleted: %s/%s by %s", category, filename, current_user.username)
    return {"message": "已删除", "name": filename}


@router.get("/api/knowledge/{category}/documents/{filename}/download")
async def download_global_document(
    category: str,
    filename: str,
    current_user: User = Depends(get_current_user),
):
    """下载全局知识库文档"""
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"无效分类: {category}")

    file_path = _GLOBAL_ROOT / category / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    from fastapi.responses import FileResponse
    return FileResponse(str(file_path), filename=filename)


# ═══════════════════════════════════════════════════════════
# 项目级知识库 API
# ═══════════════════════════════════════════════════════════


def _project_kb_dir(project_id: str) -> Path:
    return _PROJECT_ROOT / project_id / "knowledge"


@router.get("/api/projects/{project_id}/knowledge/documents")
async def list_project_documents(
    project_id: str,
    current_user: User = Depends(get_current_user),
):
    """列出项目级知识库文档"""
    kb_dir = _project_kb_dir(project_id)
    return _list_files(kb_dir)


@router.post("/api/projects/{project_id}/knowledge/documents")
async def upload_project_document(
    project_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """上传文档到项目级知识库"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件")

    kb_dir = _ensure_dir(_project_kb_dir(project_id))
    dest = kb_dir / file.filename

    content = await file.read()
    dest.write_bytes(content)

    logger.info("Project knowledge uploaded: %s/%s (%d bytes) by %s",
                project_id, file.filename, len(content), current_user.username)
    return {
        "name": file.filename,
        "size": len(content),
        "project_id": project_id,
        "message": "上传成功",
    }


@router.delete("/api/projects/{project_id}/knowledge/documents/{filename}")
async def delete_project_document(
    project_id: str,
    filename: str,
    current_user: User = Depends(get_current_user),
):
    """删除项目级知识库文档"""
    file_path = _project_kb_dir(project_id) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    file_path.unlink()
    return {"message": "已删除", "name": filename}


@router.get("/api/projects/{project_id}/knowledge/documents/{filename}/download")
async def download_project_document(
    project_id: str,
    filename: str,
    current_user: User = Depends(get_current_user),
):
    """下载项目级知识库文档"""
    file_path = _project_kb_dir(project_id) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    from fastapi.responses import FileResponse
    return FileResponse(str(file_path), filename=filename)
