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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """保存在线编辑结果 → 更新 structure.json + 回写 Excel

    自动执行：
    1. 检查编辑锁（无锁或锁不属于当前用户时拒绝）
    2. 更新 structure.json
    3. 保存版本快照（保留最近20个）
    4. 回写 Excel + 更新 HTML
    """
    from app.services.excel_html_converter import (
        get_lock_status, save_version_snapshot,
    )

    project_dir = Path("storage") / "projects" / str(project_id) / "excel_html"
    structure_path = project_dir / f"{file_stem}.structure.json"

    if not structure_path.exists():
        raise HTTPException(status_code=404, detail="结构文件不存在")

    # 1. 检查编辑锁
    file_key = f"{project_id}:{file_stem}"
    lock = get_lock_status(file_key)
    if lock and lock["user_id"] != str(current_user.id):
        raise HTTPException(status_code=423, detail=f"文件正在被其他用户编辑")

    # 2. 加载并更新 structure
    structure = json.loads(structure_path.read_text(encoding="utf-8"))
    structure = update_structure_from_edits(structure, data.edits, data.sheet_index)

    # 3. 保存版本快照
    versions_dir = str(project_dir / "versions")
    save_version_snapshot(structure, versions_dir)

    # 4. 保存 structure.json
    structure_path.write_text(json.dumps(structure, ensure_ascii=False, indent=2), encoding="utf-8")

    # 回写 Excel
    excel_path = project_dir / f"{file_stem}.xlsx"
    structure_to_excel(structure, str(excel_path))

    # 更新 HTML
    html = structure_to_html(structure, sheet_index=data.sheet_index, editable=True)
    html_path = project_dir / f"{file_stem}.html"
    html_path.write_text(html, encoding="utf-8")

    # 5. 如果是附注模块，同步回 DisclosureNote.table_data（双路径一致性）
    module = structure.get("metadata", {}).get("module")
    if module == "disclosure_note" and db:
        try:
            from app.services.triple_format_adapter import DisclosureNoteAdapter
            note_section = structure["metadata"].get("note_section", "")
            year = structure["metadata"].get("year", 2025)
            await DisclosureNoteAdapter.update_note_from_structure(
                db, project_id, year, note_section, structure
            )
            await db.commit()
        except Exception as _e:
            import logging
            logging.getLogger(__name__).warning("sync note from structure failed: %s", _e)

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



# ═══ 版本管理 ═══

@router.get("/versions/{file_stem}")
async def list_file_versions(
    project_id: UUID,
    file_stem: str,
    current_user: User = Depends(get_current_user),
):
    """列出文件的所有版本快照"""
    from app.services.excel_html_converter import list_versions
    storage_dir = str(Path("storage") / "projects" / str(project_id) / "excel_html" / "versions")
    return list_versions(storage_dir, file_stem)


@router.get("/versions/{file_stem}/diff")
async def diff_file_versions(
    project_id: UUID,
    file_stem: str,
    v1: int = Query(...),
    v2: int = Query(...),
    current_user: User = Depends(get_current_user),
):
    """对比两个版本的差异"""
    from app.services.excel_html_converter import diff_versions
    storage_dir = str(Path("storage") / "projects" / str(project_id) / "excel_html" / "versions")
    return diff_versions(storage_dir, file_stem, v1, v2)


@router.post("/versions/{file_stem}/rollback/{version}")
async def rollback_file_version(
    project_id: UUID,
    file_stem: str,
    version: int,
    current_user: User = Depends(get_current_user),
):
    """回滚到指定版本"""
    from app.services.excel_html_converter import rollback_to_version, save_version_snapshot
    storage_dir = str(Path("storage") / "projects" / str(project_id) / "excel_html" / "versions")
    structure = rollback_to_version(storage_dir, file_stem, version)
    if not structure:
        raise HTTPException(status_code=404, detail=f"版本 {version} 不存在")

    # 保存回滚后的版本
    project_dir = Path("storage") / "projects" / str(project_id) / "excel_html"
    structure_path = project_dir / f"{file_stem}.structure.json"
    structure_path.write_text(json.dumps(structure, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"message": f"已回滚到版本 {version}", "current_version": structure["metadata"]["version"]}


# ═══ 编辑锁 ═══

@router.post("/lock/{file_stem}")
async def acquire_lock(
    project_id: UUID,
    file_stem: str,
    current_user: User = Depends(get_current_user),
):
    """获取编辑锁（防止多人同时编辑冲突）"""
    from app.services.excel_html_converter import acquire_edit_lock
    file_key = f"{project_id}:{file_stem}"
    result = acquire_edit_lock(file_key, str(current_user.id))
    if not result["locked"]:
        raise HTTPException(status_code=423, detail=f"文件正在被其他用户编辑，剩余 {result['expires_in']} 秒")
    return result


@router.delete("/lock/{file_stem}")
async def release_lock(
    project_id: UUID,
    file_stem: str,
    current_user: User = Depends(get_current_user),
):
    """释放编辑锁"""
    from app.services.excel_html_converter import release_edit_lock
    file_key = f"{project_id}:{file_stem}"
    released = release_edit_lock(file_key, str(current_user.id))
    return {"released": released}


@router.put("/lock/{file_stem}/refresh")
async def refresh_lock(
    project_id: UUID,
    file_stem: str,
    current_user: User = Depends(get_current_user),
):
    """刷新编辑锁（用户仍在编辑时定期调用）"""
    from app.services.excel_html_converter import refresh_edit_lock
    file_key = f"{project_id}:{file_stem}"
    refreshed = refresh_edit_lock(file_key, str(current_user.id))
    if not refreshed:
        raise HTTPException(status_code=423, detail="锁已过期或不属于当前用户")
    return {"refreshed": True}



# ═══ 公式执行 ═══

@router.post("/execute-formulas/{file_stem}")
async def execute_formulas(
    project_id: UUID,
    file_stem: str,
    sheet_index: int = Query(default=0),
    year: int = Query(default=2025),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行 structure.json 中所有公式并回填计算结果

    遍历所有含 formula 的单元格，调用 execute_formula 计算值并写回。
    """
    from app.services.formula_unified import execute_formula
    from app.services.excel_html_converter import save_version_snapshot

    project_dir = Path("storage") / "projects" / str(project_id) / "excel_html"
    structure_path = project_dir / f"{file_stem}.structure.json"

    if not structure_path.exists():
        raise HTTPException(status_code=404, detail="结构文件不存在")

    structure = json.loads(structure_path.read_text(encoding="utf-8"))
    sheets = structure.get("sheets", [])
    if sheet_index >= len(sheets):
        raise HTTPException(status_code=400, detail="Sheet索引越界")

    sheet = sheets[sheet_index]
    cells = sheet.get("cells", {})

    # 找出所有有公式的单元格
    formula_cells = {k: v for k, v in cells.items() if v.get("formula")}
    if not formula_cells:
        return {"executed": 0, "message": "无公式需要执行"}

    # 预加载 trial_balance 全量数据（避免N+1查询）
    from app.models.audit_platform_models import TrialBalance
    tb_result = await db.execute(
        sa.select(TrialBalance).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.is_deleted == sa.false(),
        )
    )
    _tb_cache = {row.standard_account_code: row for row in tb_result.scalars().all()}

    # 将 trial_balance 数据注入到 cells 上下文中（供 execute_formula 使用）
    # 格式：_tb_context.{account_code}.{field} = value
    cells["_tb_context"] = {
        code: {
            "audited_amount": float(row.audited_amount) if row.audited_amount else 0,
            "unadjusted_amount": float(row.unadjusted_amount) if row.unadjusted_amount else 0,
            "opening_balance": float(row.opening_balance) if row.opening_balance else 0,
            "aje_adjustment": float(row.aje_adjustment) if row.aje_adjustment else 0,
            "rje_adjustment": float(row.rje_adjustment) if row.rje_adjustment else 0,
        }
        for code, row in _tb_cache.items()
    }

    executed = 0
    errors = []

    for key, cell_data in formula_cells.items():
        formula = cell_data["formula"]
        result = await execute_formula(formula, db, project_id, year, cells)

        if result.get("error"):
            errors.append({"cell": key, "formula": formula, "error": result["error"]})
        elif result.get("value") is not None:
            cells[key]["value"] = result["value"]
            cells[key]["_calc_sources"] = result.get("sources", [])
            executed += 1

    # 清理临时上下文
    cells.pop("_tb_context", None)

    # 保存更新后的 structure
    sheet["cells"] = cells
    structure["metadata"]["version"] = structure["metadata"].get("version", 0) + 1
    structure["metadata"]["last_calc_at"] = __import__("datetime").datetime.utcnow().isoformat()
    structure_path.write_text(json.dumps(structure, ensure_ascii=False, indent=2), encoding="utf-8")

    # 版本快照
    save_version_snapshot(structure, str(project_dir / "versions"))

    # 同步 Excel + HTML
    from app.services.excel_html_converter import structure_to_excel, structure_to_html
    structure_to_excel(structure, str(project_dir / f"{file_stem}.xlsx"))
    html = structure_to_html(structure, sheet_index=sheet_index, editable=True)
    (project_dir / f"{file_stem}.html").write_text(html, encoding="utf-8")

    return {
        "executed": executed,
        "total_formulas": len(formula_cells),
        "errors": errors[:10],
        "version": structure["metadata"]["version"],
        "message": f"已执行 {executed}/{len(formula_cells)} 个公式",
    }
