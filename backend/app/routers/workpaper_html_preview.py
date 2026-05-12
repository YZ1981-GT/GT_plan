"""底稿 HTML 预览 API — Round 4 需求 8（移动端）

GET /api/projects/{project_id}/workpapers/{wp_id}/html
  返回底稿 HTML 预览（只读），支持 ?mask=true 脱敏。
  复用 excel_html_converter.structure_to_html。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.workpaper_models import WorkingPaper
from app.services.excel_html_converter import excel_to_structure, structure_to_html
from app.services.export_mask_service import export_mask_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}",
    tags=["底稿HTML预览"],
)


def _mask_structure(structure: dict) -> dict:
    """对 structure 中的单元格值进行脱敏处理。

    遍历所有 sheet 的 cells，对字符串值和大额数值进行脱敏。
    """
    import copy

    masked = copy.deepcopy(structure)
    for sheet in masked.get("sheets", []):
        cells = sheet.get("cells", {})
        for key, cell in cells.items():
            value = cell.get("value")
            if value is None:
                continue
            if isinstance(value, str) and value.strip():
                masked_text, _ = export_mask_service.mask_text(value)
                cell["value"] = masked_text
            elif isinstance(value, (int, float)):
                if export_mask_service._is_sensitive_amount(value):
                    cell["value"] = "[amount]"
    return masked


@router.get("/html", response_class=HTMLResponse)
async def get_workpaper_html_preview(
    project_id: UUID,
    wp_id: UUID,
    mask: bool = Query(False, description="是否启用脱敏"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """获取底稿 HTML 预览（只读，移动端使用）

    优先使用 parsed_data 中的 structure 数据渲染 HTML。
    若 parsed_data 无 structure，则从 file_path 解析 xlsx 文件。
    支持 ?mask=true 对敏感数据（金额/客户名/身份证号）进行脱敏。
    """
    # 查询底稿
    stmt = select(WorkingPaper).where(
        WorkingPaper.id == wp_id,
        WorkingPaper.project_id == project_id,
        WorkingPaper.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    wp = result.scalar_one_or_none()

    if wp is None:
        raise HTTPException(status_code=404, detail="底稿不存在")

    # 获取 structure 数据
    structure = None

    # 优先从 parsed_data 获取 structure
    if wp.parsed_data and isinstance(wp.parsed_data, dict):
        # parsed_data 本身可能就是 structure 格式（含 sheets 键）
        if "sheets" in wp.parsed_data:
            structure = wp.parsed_data
        # 或者 parsed_data 中有 structure 子键
        elif "structure" in wp.parsed_data:
            structure = wp.parsed_data["structure"]

    # 若无 structure，尝试从 file_path 解析
    if structure is None and wp.file_path:
        file_path = Path(wp.file_path)
        # 尝试同目录下的 structure.json
        structure_json_path = file_path.with_suffix(".structure.json")
        if structure_json_path.exists():
            try:
                structure = json.loads(structure_json_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"读取 structure.json 失败: {e}")

        # 若仍无 structure，从 xlsx 文件解析
        if structure is None and file_path.exists() and file_path.suffix in (".xlsx", ".xls"):
            try:
                structure = excel_to_structure(str(file_path))
            except Exception as e:
                logger.warning(f"解析 Excel 文件失败: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"底稿文件解析失败: {str(e)}",
                )

    if structure is None:
        raise HTTPException(
            status_code=404,
            detail="底稿无可预览的数据（无 parsed_data 且无可解析的文件）",
        )

    # 脱敏处理
    if mask:
        structure = _mask_structure(structure)

    # 渲染 HTML（只读模式，不可编辑）
    html = structure_to_html(structure, sheet_index=0, editable=False)

    # 包装为完整 HTML 页面（移动端友好）
    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>底稿预览</title>
<style>
body {{
    margin: 0;
    padding: 8px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #fff;
    overflow-x: auto;
}}
.gt-excel-table {{
    font-size: 9pt;
}}
</style>
</head>
<body>
{html}
</body>
</html>"""

    return HTMLResponse(content=full_html)
