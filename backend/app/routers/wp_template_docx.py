"""底稿 docx 模板转换路由

提供 docx 模板文件转换为 Univer Doc JSON snapshot 的端点。
从 wp_template_files.py 拆分而来（Req 9.3）。
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.wp_template_init_service import find_template_file

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/template-file",
    tags=["workpaper-template-files"],
)


@router.get("/docx-to-json")
async def convert_docx_to_univer_doc(
    project_id: str,
    wp_id: str,
    db: AsyncSession = Depends(get_db),
):
    """将底稿 docx 模板转换为 Univer Doc IDocumentData JSON snapshot。

    R10 复盘补丁 — wp_templates 109 个 docx 类底稿前端编辑支持。

    流程：
    1. 查 wp_index.wp_code 获取模板编码
    2. find_template_file(wp_code) 找到 .docx 文件
    3. python-docx 解析 → docx_to_univer_doc_service 转 IDocumentData JSON
    4. 失败时由前端 fallback 到 mammoth → HTML → TipTap

    不同于 xlsx 链路：xlsx 走 importXLSX API，docx 必须后端先转 JSON 再前端 createUnit。
    """
    from app.services.docx_to_univer_doc_service import docx_path_to_univer_doc

    pid = UUID(project_id)
    wid = UUID(wp_id)

    # 查 wp_code
    row = (await db.execute(text("""
        SELECT i.wp_code
        FROM working_paper w
        LEFT JOIN wp_index i ON w.wp_index_id = i.id
        WHERE w.id = :wid
    """), {"wid": wp_id})).first()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="底稿不存在或无编码")

    wp_code = row[0]

    # 找模板文件（必须是 docx/doc）
    template_path = find_template_file(wp_code)
    if not template_path:
        raise HTTPException(status_code=404, detail=f"模板文件不存在: {wp_code}")

    suffix = template_path.suffix.lower()
    if suffix not in (".docx", ".doc"):
        raise HTTPException(
            status_code=400,
            detail=f"模板不是 Word 文档: {template_path.name}（component_type 应为 univer 走 xlsx 链路）",
        )

    # .doc 旧格式 python-docx 不支持，前端必须 fallback
    if suffix == ".doc":
        raise HTTPException(
            status_code=415,
            detail=f"旧版 .doc 格式不支持直接转换，请前端走 mammoth fallback: {template_path.name}",
        )

    try:
        snapshot = docx_path_to_univer_doc(template_path, doc_id=f"wp-{wid.hex[:12]}")
        return JSONResponse(
            content={
                "wp_code": wp_code,
                "filename": template_path.name,
                "snapshot": snapshot,
            }
        )
    except Exception as e:
        logger.error("docx-to-univer-doc conversion failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"docx 转换失败（前端应 fallback mammoth）: {type(e).__name__}: {e}",
        )
