"""全局知识库 + 项目级知识库 API

全局知识库（/api/knowledge）：所有项目共享的参考资料
  - 9 个分类：底稿模板/监管规定/会计准则/质控标准/审计程序/行业指引/提示词/报告模板/笔记
  - 文件存储在 ~/.gt_audit_helper/knowledge/{category}/

项目级知识库（/api/projects/{id}/knowledge）：项目专属文档
  - 文件存储在 storage/projects/{id}/knowledge/
"""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from app.deps import get_current_user
from app.models.core import User

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
    current_user: User = Depends(get_current_user),
):
    """列出全局知识库某分类下的文档"""
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"无效分类: {category}")
    lib_dir = _GLOBAL_ROOT / category
    return _list_files(lib_dir)


@router.post("/api/knowledge/{category}/documents")
async def upload_global_document(
    category: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """上传文档到全局知识库"""
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"无效分类: {category}")
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件")

    lib_dir = _ensure_dir(_GLOBAL_ROOT / category)
    dest = lib_dir / file.filename

    content = await file.read()
    dest.write_bytes(content)

    logger.info("Global knowledge uploaded: %s/%s (%d bytes) by %s",
                category, file.filename, len(content), current_user.username)
    return {
        "name": file.filename,
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
