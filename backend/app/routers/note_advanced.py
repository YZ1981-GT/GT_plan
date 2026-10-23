"""附注高级功能路由 — 上年导入/交叉引用/变动分析

Requirements: 42.1-42.5, 43.1-43.5, 51.1-51.8

鉴权（spec disclosure-note-template-word-realignment Task 15）：路由前缀带 ``{project_id}``，原来五个端点一个鉴权依赖
都没挂 ⇒ 未登录即可读写任意项目附注。改为与附注其余端点同级：读 ``readonly``、写 ``edit``；写附注的两处（上年
Word 导入 / 上年继承）以当前用户盖「最近一次编辑」，项目合并锁定时拒绝（423；spec consol-note-header-library-and-node-reaggregate
R7.2）。年度改为必填查询参数（原来取不存在的 ``project.current_year`` ⇒ 恒为 2025）。
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_project_access
from app.services.note_edit_gate import require_note_edit_access
from app.models.core import User

router = APIRouter(prefix="/api/projects/{project_id}/notes")


# ---------------------------------------------------------------------------
# 上年附注导入 (Requirements: 51.1-51.8)
# ---------------------------------------------------------------------------


@router.post("/import-prior-year")
async def import_prior_year_notes(
    project_id: UUID,
    year: int = Query(..., description="本年附注年度（上年 Word 内容填进这一年的章节）"),
    mode: Literal["auto", "preview", "apply"] = Query(
        "auto", description="auto：写正文与自动认出的表；preview：只返回逐表规划；apply：按 decisions 逐表写入"),
    file: UploadFile = File(...),
    decisions: str | None = Form(None, description="apply：逐表确认 JSON [{key, prior_table_id, col_map}]"),
    file_sha256: str | None = Form(None, description="apply：预览返回的文件指纹（重传同一文件）"),
    import_text: bool = Form(True, description="是否同时填入上年正文"),
    db: AsyncSession = Depends(get_db),
    # 合并锁定时拒绝（423，含预览）：上年内容会写进本年附注，与其余附注批量写入同口径（R7.2）
    current_user: User = Depends(require_note_edit_access(consol_lock=True)),
) -> dict[str, Any]:
    """上传上年附注 .docx，按标题匹配本年章节，填入正文与表格期初列（上年期末 → 本年期初，只填空格）。

    表格逐张规划（spec consol-note-header-library-and-node-reaggregate R6.6）：认不出的表不静默丢弃，
    ``preview`` 给出每张表的状态与原因，弹窗逐表确认后 ``apply``；``auto``（原行为）只写自动认出的表。
    """
    if not file.filename or not file.filename.lower().endswith('.docx'):  # 扩展名大小写不敏感（与前端同口径）
        raise HTTPException(status_code=400, detail="仅支持 .docx 格式文件")

    file_bytes = await file.read()
    if len(file_bytes) > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=400, detail="文件大小超过 50MB 限制")
    parsed: Any = None
    if mode == "apply":
        try:
            parsed = json.loads(decisions or "")
        except ValueError:
            raise HTTPException(status_code=400, detail="确认内容不是合法 JSON，请重新预览") from None
        if not file_sha256:
            raise HTTPException(status_code=400, detail="按确认写入需要带上预览返回的文件指纹，请重新预览")

    from app.services.note_prior_year_import_service import NotePriorYearImportService, PriorYearImportError

    service = NotePriorYearImportService(db)
    try:
        import_result = await service.import_from_docx(
            project_id, year, file_bytes, user_id=current_user.id, mode=mode, decisions=parsed,
            file_sha256=file_sha256, import_text=import_text)
    except PriorYearImportError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None
    if mode != "preview":
        await db.commit()
    return import_result


@router.post("/inherit-prior-year")
async def inherit_prior_year_notes(
    project_id: UUID,
    year: int = Query(..., description="本年附注年度（从 year-1 年继承正文）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_note_edit_access(consol_lock=True)),  # 合并锁定时拒绝（R7.2）
) -> dict[str, Any]:
    """连续审计：从本库上一年度附注继承正文（标记待更新）。"""
    from app.services.note_prior_year_import_service import NotePriorYearImportService

    service = NotePriorYearImportService(db)
    result = await service.inherit_from_prior_year(project_id, year, user_id=current_user.id)
    await db.commit()
    return result


# ---------------------------------------------------------------------------
# 交叉引用 (Requirements: 42.1-42.5)
# ---------------------------------------------------------------------------


@router.get("/cross-references")
async def get_cross_references(
    project_id: UUID,
    year: int = Query(..., description="附注年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> dict[str, Any]:
    """Get cross-reference mappings between report rows and note sections."""
    from app.services.note_cross_reference_service import NoteCrossReferenceService

    service = NoteCrossReferenceService(db)
    return await service.generate_cross_references(project_id, year)


@router.post("/cross-references/update")
async def update_cross_references(
    project_id: UUID,
    year: int = Query(..., description="附注年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_note_edit_access(consol_lock=False)),
) -> dict[str, Any]:
    """章节重排后重算全部交叉引用（系统重算，不盖「最近一次编辑」）。"""
    from app.services.note_cross_reference_service import NoteCrossReferenceService

    service = NoteCrossReferenceService(db)
    result = await service.update_all_references(project_id, year)
    await db.commit()
    return result


# ---------------------------------------------------------------------------
# 变动分析 (Requirements: 43.1-43.5)
# ---------------------------------------------------------------------------


@router.post("/generate-variation-analysis")
async def generate_variation_analysis(
    project_id: UUID,
    year: int = Query(..., description="附注年度"),
    threshold: float | None = None,
    force_row_codes: list[str] | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> dict[str, Any]:
    """Generate variation analysis paragraphs for accounts exceeding threshold（只返回段落，不写库）.

    Default threshold: 20%. Accounts with change rate > threshold get
    auto-generated analysis paragraphs with {原因占位} for user to fill.
    """
    from app.services.note_variation_analysis_service import NoteVariationAnalysisService

    service = NoteVariationAnalysisService(db)
    effective_threshold = Decimal(str(threshold)) if threshold else None
    return await service.generate_variation_analysis(
        project_id, year, effective_threshold, force_row_codes
    )
