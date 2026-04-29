"""Excel ↔ HTML 互转 API — 双格式保存 + ONLYOFFICE 联动

提供：
- 上传 Excel → 解析为 structure.json + 渲染 HTML 预览
- 编辑保存 → 更新 structure.json + 回写 Excel
- ONLYOFFICE 保存后同步 structure.json
- 双格式下载（.xlsx / .html）
"""

import json
import shutil
import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.excel_html_converter import (
    excel_to_structure,
    structure_to_html,
    structure_to_excel,
    update_structure_from_edits,
    sync_structure_from_excel,
)

router = APIRouter(prefix="/api/projects/{project_id}/excel-html", tags=["Excel-HTML互转"])


class EditRequest(BaseModel):
    """编辑请求"""
    edits: list[dict]  # [{"cell": "0:1", "value": "新值"}, ...]
    sheet_index: int = 0


class ConfirmTemplateRequest(BaseModel):
    """确认为正式模板"""
    template_name: str
    template_type: str = "workpaper"  # workpaper / report
    wp_code: str | None = None
    audit_cycle: str | None = None


@router.post("/upload-parse")
async def upload_and_parse(
    project_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传 Excel → 解析为 structure.json + 返回 HTML 预览

    用户上传 Excel 文档，自动解析为结构化数据，
    返回 HTML 预览供用户在线编辑确认。
    """
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx/.xls 文件")

    # 保存上传文件
    project_dir = Path("storage") / "projects" / str(project_id) / "excel_html"
    project_dir.mkdir(parents=True, exist_ok=True)

    # 保存原始 Excel
    excel_path = project_dir / file.filename
    content = await file.read()
    excel_path.write_bytes(content)

    # 解析为 structure.json
    try:
        structure = excel_to_structure(str(excel_path))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Excel 解析失败: {e}")

    # 保存 structure.json
    stem = Path(file.filename).stem
    structure_path = project_dir / f"{stem}.structure.json"
    structure_path.write_text(json.dumps(structure, ensure_ascii=False, indent=2), encoding="utf-8")

    # 生成 HTML 预览
    html = structure_to_html(structure, editable=True)

    # 保存 HTML
    html_path = project_dir / f"{stem}.html"
    html_path.write_text(html, encoding="utf-8")

    return {
        "file_name": file.filename,
        "structure_path": str(structure_path),
        "excel_path": str(excel_path),
        "html_path": str(html_path),
        "sheet_count": len(structure.get("sheets", [])),
        "sheets": [{"name": s["name"], "cells": len(s.get("cells", {}))} for s in structure.get("sheets", [])],
        "html_preview": html,
        "message": "Excel 解析成功，请在线编辑确认",
    }


@router.get("/preview/{file_stem}")
async def get_html_preview(
    project_id: UUID,
    file_stem: str,
    sheet_index: int = Query(default=0),
    editable: bool = Query(default=True),
    current_user: User = Depends(get_current_user),
):
    """获取 HTML 预览（可编辑模式）"""
    structure_path = Path("storage") / "projects" / str(project_id) / "excel_html" / f"{file_stem}.structure.json"
    if not structure_path.exists():
        raise HTTPException(status_code=404, detail="结构文件不存在")

    structure = json.loads(structure_path.read_text(encoding="utf-8"))
    html = structure_to_html(structure, sheet_index=sheet_index, editable=editable)

    return {"html": html, "sheet_index": sheet_index, "version": structure.get("metadata", {}).get("version", 1)}


@router.post("/save-edits/{file_stem}")
async def save_edits(
    project_id: UUID,
    file_stem: str,
    data: EditRequest,
    current_user: User = Depends(get_current_user),
):
    """保存在线编辑结果 → 更新 structure.json + 回写 Excel"""
    project_dir = Path("storage") / "projects" / str(project_id) / "excel_html"
    structure_path = project_dir / f"{file_stem}.structure.json"

    if not structure_path.exists():
        raise HTTPException(status_code=404, detail="结构文件不存在")

    # 加载并更新 structure
    structure = json.loads(structure_path.read_text(encoding="utf-8"))
    structure = update_structure_from_edits(structure, data.edits, data.sheet_index)

    # 保存 structure.json
    structure_path.write_text(json.dumps(structure, ensure_ascii=False, indent=2), encoding="utf-8")

    # 回写 Excel
    excel_path = project_dir / f"{file_stem}.xlsx"
    structure_to_excel(structure, str(excel_path))

    # 更新 HTML
    html = structure_to_html(structure, sheet_index=data.sheet_index, editable=True)
    html_path = project_dir / f"{file_stem}.html"
    html_path.write_text(html, encoding="utf-8")

    return {
        "version": structure["metadata"]["version"],
        "edits_applied": len(data.edits),
        "message": "编辑已保存（双格式同步更新）",
    }


@router.post("/confirm-template/{file_stem}")
async def confirm_as_template(
    project_id: UUID,
    file_stem: str,
    data: ConfirmTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """确认为正式模板（编辑完成后）

    将编辑确认后的文件注册为项目模板，双格式保存到正式目录。
    """
    project_dir = Path("storage") / "projects" / str(project_id) / "excel_html"
    structure_path = project_dir / f"{file_stem}.structure.json"
    excel_path = project_dir / f"{file_stem}.xlsx"

    if not structure_path.exists():
        raise HTTPException(status_code=404, detail="结构文件不存在")

    # 复制到正式模板目录
    if data.template_type == "workpaper":
        target_dir = Path("storage") / "projects" / str(project_id) / "workpapers" / (data.audit_cycle or "CUSTOM")
    else:
        target_dir = Path("storage") / "projects" / str(project_id) / "templates"
    target_dir.mkdir(parents=True, exist_ok=True)

    final_name = data.wp_code or file_stem
    final_excel = target_dir / f"{final_name}.xlsx"
    final_structure = target_dir / f"{final_name}.structure.json"
    final_html = target_dir / f"{final_name}.html"

    # 复制文件
    if excel_path.exists():
        shutil.copy2(excel_path, final_excel)
    shutil.copy2(structure_path, final_structure)

    # 生成最终 HTML（不可编辑版本）
    structure = json.loads(structure_path.read_text(encoding="utf-8"))
    html = structure_to_html(structure, editable=False)
    final_html.write_text(html, encoding="utf-8")

    return {
        "template_name": data.template_name,
        "excel_path": str(final_excel),
        "structure_path": str(final_structure),
        "html_path": str(final_html),
        "message": f"已确认为正式{('底稿' if data.template_type == 'workpaper' else '报表')}模板",
    }


@router.post("/sync-from-onlyoffice/{file_stem}")
async def sync_from_onlyoffice(
    project_id: UUID,
    file_stem: str,
    current_user: User = Depends(get_current_user),
):
    """ONLYOFFICE 保存后同步 structure.json

    当用户通过 ONLYOFFICE 编辑 Excel 后（WOPI put_file），
    调用此接口重新解析 Excel 更新 structure.json（保留取数规则绑定）。
    """
    project_dir = Path("storage") / "projects" / str(project_id) / "excel_html"
    excel_path = project_dir / f"{file_stem}.xlsx"
    structure_path = project_dir / f"{file_stem}.structure.json"

    if not excel_path.exists():
        raise HTTPException(status_code=404, detail="Excel 文件不存在")

    try:
        new_structure = sync_structure_from_excel(str(excel_path), str(structure_path))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步失败: {e}")

    # 更新 HTML
    html = structure_to_html(new_structure, editable=True)
    html_path = project_dir / f"{file_stem}.html"
    html_path.write_text(html, encoding="utf-8")

    return {
        "version": new_structure["metadata"]["version"],
        "synced_from": "onlyoffice",
        "message": "已从 ONLYOFFICE 同步更新",
    }


@router.get("/download/{file_stem}")
async def download_file(
    project_id: UUID,
    file_stem: str,
    format: str = Query(default="xlsx", regex="^(xlsx|html|json)$"),
    current_user: User = Depends(get_current_user),
):
    """下载文件（支持三种格式）"""
    from fastapi.responses import FileResponse

    project_dir = Path("storage") / "projects" / str(project_id) / "excel_html"

    ext_map = {"xlsx": ".xlsx", "html": ".html", "json": ".structure.json"}
    file_path = project_dir / f"{file_stem}{ext_map[format]}"

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_path.name}")

    media_types = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "html": "text/html",
        "json": "application/json",
    }

    return FileResponse(
        path=str(file_path),
        media_type=media_types[format],
        filename=file_path.name,
    )



# ═══ 统一模块接口：任意模块 → 三形式 ═══

@router.get("/module/{module}/structure")
async def get_module_structure(
    project_id: UUID,
    module: str,
    year: int = Query(default=2025),
    wp_code: str | None = Query(None),
    note_section: str | None = Query(None),
    report_type: str | None = Query(None),
    entry_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """统一接口：获取任意模块的 structure.json

    module: workpaper / disclosure_note / financial_report /
            adjustment_summary / trial_balance / consol_worksheet
    """
    from app.services.triple_format_adapter import module_to_structure

    kwargs = {}
    if wp_code:
        kwargs["wp_code"] = wp_code
    if note_section:
        kwargs["note_section"] = note_section
    if report_type:
        kwargs["report_type"] = report_type
    if entry_type:
        kwargs["entry_type"] = entry_type

    result = await module_to_structure(db, project_id, year, module, **kwargs)
    return result


@router.get("/module/{module}/html")
async def get_module_html(
    project_id: UUID,
    module: str,
    year: int = Query(default=2025),
    editable: bool = Query(default=True),
    wp_code: str | None = Query(None),
    note_section: str | None = Query(None),
    report_type: str | None = Query(None),
    entry_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """统一接口：获取任意模块的 HTML 渲染"""
    from app.services.triple_format_adapter import module_to_html

    kwargs = {}
    if wp_code:
        kwargs["wp_code"] = wp_code
    if note_section:
        kwargs["note_section"] = note_section
    if report_type:
        kwargs["report_type"] = report_type
    if entry_type:
        kwargs["entry_type"] = entry_type

    html = await module_to_html(db, project_id, year, module, editable=editable, **kwargs)
    return {"module": module, "html": html}


@router.post("/module/{module}/export-excel")
async def export_module_excel(
    project_id: UUID,
    module: str,
    year: int = Query(default=2025),
    wp_code: str | None = Query(None),
    note_section: str | None = Query(None),
    report_type: str | None = Query(None),
    entry_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """统一接口：任意模块导出 Excel"""
    from fastapi.responses import FileResponse
    from app.services.triple_format_adapter import module_to_excel

    kwargs = {}
    if wp_code:
        kwargs["wp_code"] = wp_code
    if note_section:
        kwargs["note_section"] = note_section
    if report_type:
        kwargs["report_type"] = report_type
    if entry_type:
        kwargs["entry_type"] = entry_type

    # 生成临时文件（加时间戳防并发冲突）
    import time
    output_dir = Path("storage") / "projects" / str(project_id) / "exports"
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    filename = f"{module}_{wp_code or note_section or report_type or entry_type or 'data'}_{ts}.xlsx"
    output_path = str(output_dir / filename)

    try:
        await module_to_excel(db, project_id, year, module, output_path, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return FileResponse(
        path=output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )



@router.post("/module/{module}/export-word")
async def export_module_word(
    project_id: UUID,
    module: str,
    year: int = Query(default=2025),
    wp_code: str | None = Query(None),
    note_section: str | None = Query(None),
    report_type: str | None = Query(None),
    entry_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """统一接口：任意模块导出 Word（致同三线表排版）"""
    from fastapi.responses import FileResponse
    from app.services.triple_format_adapter import module_to_word
    import time

    kwargs = {}
    if wp_code:
        kwargs["wp_code"] = wp_code
    if note_section:
        kwargs["note_section"] = note_section
    if report_type:
        kwargs["report_type"] = report_type
    if entry_type:
        kwargs["entry_type"] = entry_type

    output_dir = Path("storage") / "projects" / str(project_id) / "exports"
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    filename = f"{module}_{wp_code or note_section or report_type or entry_type or 'data'}_{ts}.docx"
    output_path = str(output_dir / filename)

    try:
        await module_to_word(db, project_id, year, module, output_path, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return FileResponse(
        path=output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )



@router.get("/cell-info/{file_stem}")
async def get_cell_info(
    project_id: UUID,
    file_stem: str,
    cell: str = Query(..., description="单元格坐标如 0:1"),
    sheet_index: int = Query(default=0),
    current_user: User = Depends(get_current_user),
):
    """获取单元格详细信息（地址/公式/合并范围/取数规则）

    用于公式编辑栏显示当前选中单元格的完整信息。
    """
    from app.services.excel_html_converter import _col_to_letter

    structure_path = Path("storage") / "projects" / str(project_id) / "excel_html" / f"{file_stem}.structure.json"
    if not structure_path.exists():
        raise HTTPException(status_code=404, detail="结构文件不存在")

    structure = json.loads(structure_path.read_text(encoding="utf-8"))
    sheets = structure.get("sheets", [])
    if sheet_index >= len(sheets):
        raise HTTPException(status_code=404, detail="Sheet不存在")

    sheet = sheets[sheet_index]
    cells = sheet.get("cells", {})
    merges = sheet.get("merges", [])

    cell_data = cells.get(cell, {})
    parts = cell.split(":")
    r, c = int(parts[0]), int(parts[1])

    # Excel 风格地址
    addr = f"{_col_to_letter(c)}{r + 1}"

    # 检查是否在合并区域内
    merge_info = None
    for m in merges:
        if m["start_row"] <= r <= m["end_row"] and m["start_col"] <= c <= m["end_col"]:
            merge_info = {
                "range": f"{_col_to_letter(m['start_col'])}{m['start_row']+1}:{_col_to_letter(m['end_col'])}{m['end_row']+1}",
                "start": f"{m['start_row']}:{m['start_col']}",
                "end": f"{m['end_row']}:{m['end_col']}",
                "rowspan": m["end_row"] - m["start_row"] + 1,
                "colspan": m["end_col"] - m["start_col"] + 1,
            }
            break

    return {
        "cell": cell,
        "address": addr,
        "value": cell_data.get("value"),
        "formula": cell_data.get("formula"),
        "formula_type": cell_data.get("_formula_type"),
        "formula_desc": cell_data.get("_formula_desc"),
        "fetch_rule_id": cell_data.get("fetch_rule_id"),
        "style": cell_data.get("style"),
        "merge": merge_info,
        "is_merged": merge_info is not None,
    }
