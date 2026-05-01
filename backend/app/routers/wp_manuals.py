"""底稿操作手册 API

GET  /api/wp-manuals                    — 所有循环的md文件索引
GET  /api/wp-manuals/stats              — 统计信息
GET  /api/wp-manuals/{cycle}            — 指定循环的md文件列表
GET  /api/wp-manuals/{cycle}/manual     — 操作手册内容
GET  /api/wp-manuals/{cycle}/template   — 底稿模板库内容
GET  /api/wp-manuals/{cycle}/context    — LLM上下文（操作手册+模板库+控制底稿合并）
GET  /api/wp-manuals/{cycle}/{filename} — 指定md文件内容
"""
from fastapi import APIRouter, Depends, Query, HTTPException

from app.deps import get_current_user
from app.services.wp_manual_service import (
    get_all_manuals, get_cycle_manuals, get_manual_content,
    get_operation_manual, get_template_lib, get_context_for_llm,
    get_stats,
)

router = APIRouter(prefix="/api/wp-manuals", tags=["底稿操作手册"])


@router.get("")
async def list_all_manuals(_user=Depends(get_current_user)):
    """获取所有循环的md文件索引"""
    index = get_all_manuals()
    return {
        "cycles": {k: v for k, v in index.items() if k != "_framework"},
        "framework": index.get("_framework", []),
        "total": sum(len(v) for v in index.values()),
    }


@router.get("/stats")
async def manual_stats(_user=Depends(get_current_user)):
    """操作手册统计"""
    return get_stats()


@router.get("/{cycle}")
async def list_cycle_manuals(
    cycle: str,
    _user=Depends(get_current_user),
):
    """获取指定循环的md文件列表"""
    files = get_cycle_manuals(cycle)
    return {"cycle": cycle.upper(), "files": files, "count": len(files)}


@router.get("/{cycle}/manual")
async def get_cycle_manual(
    cycle: str,
    max_chars: int = Query(8000),
    _user=Depends(get_current_user),
):
    """获取操作手册内容（审计程序步骤、检查要点）"""
    content = get_operation_manual(cycle, max_chars)
    if not content:
        raise HTTPException(status_code=404, detail=f"{cycle}循环暂无操作手册")
    return {"cycle": cycle.upper(), "type": "manual", "content": content}


@router.get("/{cycle}/template")
async def get_cycle_template_lib(
    cycle: str,
    max_chars: int = Query(8000),
    _user=Depends(get_current_user),
):
    """获取底稿模板库内容（底稿结构说明、填写指引）"""
    content = get_template_lib(cycle, max_chars)
    if not content:
        raise HTTPException(status_code=404, detail=f"{cycle}循环暂无底稿模板库")
    return {"cycle": cycle.upper(), "type": "template_lib", "content": content}


@router.get("/{cycle}/context")
async def get_llm_context(
    cycle: str,
    wp_code: str = Query(""),
    max_chars: int = Query(12000),
    _user=Depends(get_current_user),
):
    """获取LLM上下文（操作手册+模板库+控制底稿合并，供AI面板使用）"""
    context = get_context_for_llm(cycle, wp_code, max_chars)
    return {
        "cycle": cycle.upper(),
        "wp_code": wp_code,
        "context": context,
        "char_count": len(context),
    }


@router.get("/{cycle}/{filename}")
async def get_file_content(
    cycle: str,
    filename: str,
    max_chars: int = Query(0),
    _user=Depends(get_current_user),
):
    """获取指定md文件内容"""
    content = get_manual_content(cycle, filename, max_chars)
    if not content:
        raise HTTPException(status_code=404, detail=f"文件不存在: {cycle}/{filename}")
    return {"cycle": cycle.upper(), "filename": filename, "content": content}
