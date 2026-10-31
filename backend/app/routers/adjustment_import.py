"""调整分录 Excel 导入（项目级端点，spec adjustment-hall-entry-review-closure 需求 2）。

- ``POST /preview``：解析 + 逐笔预检，不写库（只读权限）；
- ``POST ""``：导入（编辑权限、未归档、未合并锁定），逐笔保存点，返回逐笔结果与新建分录组。
年度必填。旧通用端点 ``/api/import-templates/adjustments/import`` 仍可用（已补项目级鉴权）。
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import check_consol_lock, require_project_access
from app.models.core import User
from app.services.adjustment_import_service import import_rows, preview_import
from app.services.import_template_service import ImportType, parse_import_data, validate_import_file

router = APIRouter(prefix="/api/projects/{project_id}/adjustments/import", tags=["adjustments"])

_MAX_UPLOAD = 50 * 1024 * 1024


async def _read_rows(file: UploadFile) -> tuple[list[dict], list, int, list[str]]:
    """读上传文件 → (数据行, 行位置, 跳过的示例行数, 表头级错误)。"""
    name = file.filename or ""
    if not name.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式的调整分录导入模板")
    content = await file.read()
    if len(content) > _MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="文件大小超过 50MB 限制")
    validation = validate_import_file(ImportType.adjustments, content, name)
    # 只取表头 / 文件级问题；逐行问题由逐笔预检给出（更具体，且不重复）
    structure = [e.message for e in validation.errors if e.row in (None, 1)]
    if structure:
        return [], [], 0, structure
    stats: dict = {}
    try:
        rows = parse_import_data(ImportType.adjustments, content, stats=stats)
    except Exception as exc:  # noqa: BLE001 — 文件损坏等
        raise HTTPException(status_code=400, detail=f"无法解析文件：{exc}")
    return rows, stats.get("row_locations") or [], int(stats.get("example_skipped") or 0), []


def _mode(mode: str) -> str:
    m = (mode or "append").strip().lower()
    if m not in ("append", "overwrite"):
        raise HTTPException(status_code=400, detail="导入模式只能是 append（追加）或 overwrite（按编号覆盖）")
    return m


@router.post("/preview")
async def preview_adjustment_import(
    project_id: UUID,
    year: int = Query(..., description="审计年度"),
    mode: str = Query("append"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """预检：逐笔解析结果与问题，不写库。"""
    mode = _mode(mode)
    rows, locations, example_skipped, structure = await _read_rows(file)
    if structure:
        return {"mode": mode, "groups": [], "warnings": [], "structure_errors": structure,
                "summary": {"total": 0, "ok": 0, "error": 0, "skip": 0, "replace": 0},
                "example_skipped": example_skipped}
    result = await preview_import(db, project_id, year, rows, mode=mode, locations=locations)
    result["structure_errors"] = []
    result["example_skipped"] = example_skipped
    return result


@router.post("")
async def import_adjustments_file(
    project_id: UUID,
    year: int = Query(..., description="审计年度"),
    mode: str = Query("append"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """导入：逐笔保存点，一笔失败不影响其他笔。"""
    mode = _mode(mode)
    rows, locations, example_skipped, structure = await _read_rows(file)
    if structure:
        raise HTTPException(status_code=400, detail="；".join(structure))
    if not rows:
        raise HTTPException(status_code=400, detail="文件中没有可导入的分录行"
                            + (f"（已跳过 {example_skipped} 行模板示例）" if example_skipped else ""))
    result = await import_rows(db, project_id, year, rows, current_user, mode=mode, locations=locations)
    await db.commit()
    parts = [f"成功导入 {result['imported']} 笔"]
    if result["skipped"]:
        parts.append(f"{result['skipped']} 笔跳过")
    if result["failed"]:
        parts.append(f"{result['failed']} 笔失败")
    return {**result, "example_skipped": example_skipped, "message": "，".join(parts)}
