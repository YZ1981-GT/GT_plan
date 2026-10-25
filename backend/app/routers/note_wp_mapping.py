"""附注-底稿映射 API

Phase 9 Task 9.21
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.schemas._common import OptionalAmountDecimal
from app.services.note_readiness_service import run_validation_best_effort
from app.services.note_wp_mapping_service import NoteWpMappingService

router = APIRouter(prefix="/api/disclosure-notes", tags=["note-wp-mapping"])


@router.get("/{project_id}/wp-mapping")
async def get_mapping(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = NoteWpMappingService(db)
    return await svc.get_mapping(project_id)


@router.put("/{project_id}/wp-mapping")
async def update_mapping(
    project_id: UUID,
    mapping: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = NoteWpMappingService(db)
    result = await svc.update_mapping(project_id, mapping)
    await db.commit()
    return result


@router.post("/{project_id}/{year}/refresh-from-workpapers")
async def refresh_from_workpapers(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = NoteWpMappingService(db)
    result = await svc.refresh_from_workpapers(project_id, year)
    await db.commit()
    # 透传更丰富返回体：显式添加 cells_updated 便于前端消费
    # service 返回 refreshed=cells_updated（向后兼容旧键名），
    # 同时增加 cells_updated 明确语义供前端区分提示文案（Req 2.7, 2.8）
    result["cells_updated"] = result.get("refreshed", 0)
    # P0-4（附注联动复盘）：刷新后自动补跑校验并落库（fail-open，不影响已提交刷新）
    result["validation"] = await run_validation_best_effort(db, project_id, year)
    return result


@router.post("/{project_id}/{year}/refresh-all-bindings")
async def refresh_all_bindings(
    project_id: UUID,
    year: int,
    note_section: str | None = Query(default=None, description="指定章节号则只刷新该章节"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """全量 binding 取数刷新：对所有已有 binding 的章节走 _build_with_binding 重取数。

    与 refresh-from-workpapers 区别：
    - refresh-from-workpapers 只刷新有底稿映射（DEFAULT_WP_MAPPING）的章节
    - 本端点刷新**所有**已生成且有 binding 的章节（binding 从 note_template_bindings.json 加载），
      包括从未收到底稿同步的章节（这些章节的表格完全由 binding + resolver 驱动）
    - 执行公式二次求值（sum/report/aging 公式家族）

    返回 { cells_updated, sections_recomputed, text_only_sections, formula_evaluated, errors }
    """
    from app.services.disclosure_engine import DisclosureEngine
    from app.services.note_formula_gray_service import is_note_formula_enabled

    engine = DisclosureEngine(db)

    # 1. binding 取数刷新（section_codes=None 刷新全部已生成章节）
    section_codes = [note_section] if note_section else None
    report = await engine.refill_sections(
        project_id, year, section_codes, skip_manual=True
    )

    # 2. 公式二次求值：对重算过的章节再跑一遍公式
    formula_evaluated = 0
    formula_on = await is_note_formula_enabled(db, project_id)
    if formula_on and report.sections_recomputed:
        import sqlalchemy as sa
        from app.models.report_models import DisclosureNote
        from sqlalchemy.orm.attributes import flag_modified

        for section in report.sections_recomputed:
            try:
                result = await db.execute(
                    sa.select(DisclosureNote).where(
                        DisclosureNote.project_id == project_id,
                        DisclosureNote.year == year,
                        DisclosureNote.note_section == section,
                        DisclosureNote.is_deleted == sa.false(),
                    )
                )
                note = result.scalar_one_or_none()
                if note and note.table_data:
                    updated_td = await engine._evaluate_note_formulas(
                        project_id, year, section, note.table_data,
                    )
                    note.table_data = updated_td
                    flag_modified(note, "table_data")
                    formula_evaluated += 1
            except Exception as e:
                report.errors.append(f"公式求值失败 {section}: {e}")

    # 3. 对成功重算的章节清除 is_stale 标记
    stale_cleared = 0
    if report.sections_recomputed:
        import sqlalchemy as sa
        from app.models.report_models import DisclosureNote as DN2
        stale_result = await db.execute(
            sa.select(DN2).where(
                DN2.project_id == project_id,
                DN2.year == year,
                DN2.note_section.in_(report.sections_recomputed),
                DN2.is_deleted == sa.false(),
                DN2.is_stale == sa.true(),
            )
        )
        for note in stale_result.scalars().all():
            note.is_stale = False
            note.stale_source = None
            stale_cleared += 1

    await db.flush()
    await db.commit()

    resp = {
        "cells_updated": report.cells_updated,
        "sections_recomputed": report.sections_recomputed,
        "text_only_sections": report.text_only_sections,
        "formula_evaluated": formula_evaluated,
        "stale_cleared": stale_cleared,
        "errors": report.errors,
        "message": f"已刷新 {len(report.sections_recomputed)} 个章节，"
                   f"更新 {report.cells_updated} 个单元格，"
                   f"公式求值 {formula_evaluated} 个章节"
                   + (f"，清除 {stale_cleared} 个过期标记" if stale_cleared else ""),
    }
    # 底稿来源章节列表（被 refill 跳过的，前端据此提示"请在底稿中同步"）
    wp_source_sections = [
        s for s in report.text_only_sections
        if s not in report.sections_recomputed
    ]
    if wp_source_sections:
        resp["workpaper_source_skipped"] = wp_source_sections
    # 刷新后自动补跑校验（fail-open）
    resp["validation"] = await run_validation_best_effort(db, project_id, year)
    return resp


@router.post("/{project_id}/{year}/{note_section}/refresh-from-workpaper")
async def refresh_section_from_workpaper(
    project_id: UUID,
    year: int,
    note_section: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """只重算单个章节的科目数据（当前页面刷新）。

    与项目级 refresh-from-workpapers 区别：后端仅重算 note_section 本节，
    使「刷新」按钮的前后端行为一致（只动当前节，避免全量写库→前端只重载
    当前节造成的其它章节前后端不一致）。
    """
    svc = NoteWpMappingService(db)
    result = await svc.refresh_section_from_workpapers(project_id, year, note_section)
    await db.commit()
    result["cells_updated"] = result.get("refreshed", 0)
    # P0-4：单章节刷新后同样自动补跑校验（fail-open）
    result["validation"] = await run_validation_best_effort(db, project_id, year)
    return result


class ToggleModeRequest(BaseModel):
    row_label: str
    col_index: int
    mode: str  # auto / manual
    manual_value: OptionalAmountDecimal = None


@router.post("/{project_id}/{year}/{note_id}/toggle-mode")
async def toggle_mode(
    project_id: UUID,
    year: int,
    note_id: UUID,
    data: ToggleModeRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = NoteWpMappingService(db)
    result = await svc.toggle_cell_mode(note_id, data.row_label, data.col_index, data.mode, data.manual_value)
    await db.commit()
    return result
