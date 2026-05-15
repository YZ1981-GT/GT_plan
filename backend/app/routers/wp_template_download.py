"""底稿模板下载路由

提供底稿模板文件的下载端点：
- GET  /api/projects/{pid}/wp-templates/{wp_code}/download  — 下载单个科目模板
- GET  /api/projects/{pid}/wp-templates/download-all         — 批量下载全部模板（ZIP）
"""
from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.services.wp_template_init_service import (
    find_template_file_any,
    find_all_template_files,
    TEMPLATES_DIR,
    _load_index,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/wp-templates",
    tags=["workpaper-template-download"],
)


@router.get("/{wp_code}/download")
async def download_template_by_code(
    project_id: str,
    wp_code: str,
    current_user: User = Depends(require_project_access("readonly")),
):
    """下载单个科目的模板文件（从 wp_templates/ 目录）

    如果该科目有多个模板文件（如 D2 有审定表+分析程序+检查程序），
    打包为 ZIP 返回；单文件直接返回 xlsx。
    """
    all_files = find_all_template_files(wp_code)
    if not all_files:
        # 尝试单文件
        single = find_template_file_any(wp_code)
        if single:
            all_files = [single]

    if not all_files:
        raise HTTPException(status_code=404, detail=f"模板不存在: {wp_code}")

    # 单文件直接返回
    if len(all_files) == 1:
        f = all_files[0]
        from urllib.parse import quote
        filename = f.name
        ascii_name = filename.encode("ascii", "ignore").decode() or "template.xlsx"
        utf8_name = quote(filename, safe="")
        return FileResponse(
            str(f),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{utf8_name}',
            },
        )

    # 多文件打包为 ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in all_files:
            zf.write(f, f.name)
    buf.seek(0)

    from urllib.parse import quote
    zip_name = f"{wp_code}_模板.zip"
    utf8_name = quote(zip_name, safe="")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{wp_code}_templates.zip"; filename*=UTF-8\'\'{utf8_name}',
        },
    )


@router.get("/list")
async def list_all_templates(
    project_id: str,
    current_user: User = Depends(require_project_access("readonly")),
):
    """列出所有可用底稿模板（供树形展示）

    返回按循环分组的模板列表，包含 wp_code/wp_name/cycle/filename。
    """
    index = _load_index()
    if not index:
        return {"items": [], "total": 0}

    # 按 wp_code 去重，取主文件
    seen: dict[str, dict] = {}
    CYCLE_NAMES = {
        'A': 'A 完成阶段', 'B': 'B 风险评估', 'C': 'C 控制测试',
        'D': 'D 销售循环', 'E': 'E 货币资金', 'F': 'F 存货',
        'G': 'G 投资', 'H': 'H 固定资产', 'I': 'I 无形资产',
        'J': 'J 薪酬', 'K': 'K 费用', 'L': 'L 负债',
        'M': 'M 权益', 'N': 'N 税项', 'S': 'S 特定项目',
    }
    for entry in sorted(index, key=lambda x: (x["wp_code"], len(x["filename"]))):
        code = entry["wp_code"]
        if code in seen or code.startswith("_"):
            continue
        cycle = code[0] if code else '?'
        # 从文件名提取底稿名称（去掉编码前缀）
        fname = entry["filename"]
        # "D1 应收票据.xlsx" → "应收票据"
        name_part = fname.rsplit('.', 1)[0]  # 去扩展名
        if ' ' in name_part:
            name_part = name_part.split(' ', 1)[1]  # 去编码前缀
        seen[code] = {
            "wp_code": code,
            "wp_name": name_part,
            "cycle": cycle,
            "cycle_name": CYCLE_NAMES.get(cycle, f'{cycle}类'),
            "filename": fname,
            "format": entry.get("format", "xlsx"),
        }

    items = list(seen.values())
    return {"items": items, "total": len(items)}


@router.get("/download-all")
async def download_all_templates(
    project_id: str,
    current_user: User = Depends(require_project_access("readonly")),
):
    """批量下载全部底稿模板（ZIP，按循环分目录）

    目录结构: {循环字母}/{wp_code} {名称}.xlsx
    """
    index = _load_index()
    if not index:
        raise HTTPException(status_code=404, detail="模板索引为空")

    buf = io.BytesIO()
    file_count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        seen = set()
        for entry in index:
            rel_path = entry.get("relative_path", "")
            if not rel_path or rel_path in seen:
                continue
            full_path = TEMPLATES_DIR / rel_path
            if not full_path.exists():
                continue
            seen.add(rel_path)
            # 保持原始目录结构
            zf.write(full_path, rel_path)
            file_count += 1

    buf.seek(0)
    logger.info("download_all_templates: %d files, %d bytes", file_count, buf.getbuffer().nbytes)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="workpaper_templates_all.zip"; filename*=UTF-8\'\'%E5%BA%95%E7%A8%BF%E6%A8%A1%E6%9D%BF%E5%85%A8%E9%87%8F.zip',
        },
    )
