"""附注-底稿映射 API

Phase 9 Task 9.21
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.schemas._common import OptionalAmountDecimal
from app.services.note_edit_gate import require_note_edit_access
from app.services.note_readiness_service import run_validation_best_effort
from app.services.note_wp_mapping_service import NoteWpMappingService

router = APIRouter(prefix="/api/disclosure-notes", tags=["note-wp-mapping"])


# 原先被 disclosure_notes 的 /{project_id}/{year} 截走、从未可达（只挂了登录）；2026-10-31 改由 router_registry
# 先注册后可达，按附注其余只读端点同级补项目只读鉴权（spec platform-performance-residual-findings-closure）。
@router.get("/{project_id}/wp-mapping")
async def get_mapping(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    svc = NoteWpMappingService(db)
    return await svc.get_mapping(project_id)


@router.put("/{project_id}/wp-mapping")
async def update_mapping(
    project_id: UUID,
    mapping: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _gate=Depends(require_note_edit_access(consol_lock=False)),
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
    _gate=Depends(require_note_edit_access(consol_lock=False)),
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
    _gate=Depends(require_note_edit_access(consol_lock=False)),
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

    # 2. 公式二次求值：只对完整重算成功的章节再跑一遍
    formula_evaluated = 0
    formula_on = await is_note_formula_enabled(db, project_id)
    if formula_on and report.recomputed_sections:
        import sqlalchemy as sa
        from copy import deepcopy
        from app.models.report_models import DisclosureNote
        from sqlalchemy.orm.attributes import flag_modified

        for section in list(report.recomputed_sections):
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
                if not note or not note.table_data:
                    raise ValueError("章节没有可供公式求值的表格数据")
                original_td = deepcopy(note.table_data)
                updated_td = await engine._evaluate_note_formulas(
                    project_id, year, section, note.table_data,
                )
                if updated_td != original_td:
                    note.table_data = updated_td
                    flag_modified(note, "table_data")
                    if section not in report.changed_sections:
                        report.changed_sections.append(section)
                formula_evaluated += 1
            except Exception as e:
                message = f"公式求值失败 {section}: {e}"
                report.errors.append(message)
                report.error_details.append({
                    "section": section,
                    "stage": "formula",
                    "message": str(e),
                })
                if section not in report.failed_sections:
                    report.failed_sections.append(section)
                if section in report.recomputed_sections:
                    report.recomputed_sections.remove(section)

    # 3. 对完整重算成功的章节清除 stale（统一入口）
    stale_cleared = 0
    if report.recomputed_sections:
        from app.services.stale_state import clear_note_stale

        stale_cleared = await clear_note_stale(
            db,
            project_id,
            sections=report.recomputed_sections,
            year=year,
        )
        report.cleared_sections = list(report.recomputed_sections)

    await db.flush()
    await db.commit()

    resp = {
        "requested_sections": report.requested_sections,
        "recomputed_sections": report.recomputed_sections,
        "sections_recomputed": report.recomputed_sections,  # 兼容旧客户端
        "changed_sections": report.changed_sections,
        "failed_sections": report.failed_sections,
        "cleared_sections": report.cleared_sections,
        "cells_updated": report.cells_updated,
        "text_only_sections": report.text_only_sections,
        "formula_evaluated": formula_evaluated,
        "stale_cleared": stale_cleared,
        "errors": report.errors,
        "error_details": report.error_details,
        "message": f"已刷新 {len(report.recomputed_sections)} 个章节，"
                   f"更新 {report.cells_updated} 个单元格，"
                   f"公式求值 {formula_evaluated} 个章节"
                   + (f"，清除 {stale_cleared} 个过期标记" if stale_cleared else ""),
    }
    # 底稿来源章节列表（被 refill 跳过的，前端据此提示"请在底稿中同步"）
    wp_source_sections = [
        s for s in report.text_only_sections
        if s not in report.recomputed_sections
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
    _gate=Depends(require_note_edit_access(consol_lock=False)),
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
    col_index: int  # 数据列序号（从 0 起，不含标签列；与 ``_cell_modes`` 键一致）
    mode: Literal["auto", "manual"]
    manual_value: OptionalAmountDecimal = None


@router.post("/{project_id}/{year}/{note_id}/toggle-mode")
async def toggle_mode(
    project_id: UUID,
    year: int,
    note_id: UUID,
    data: ToggleModeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_note_edit_access(consol_lock=False)),
):
    """改单元格模式 = 用户编辑附注：附注编辑门禁 + 只认本项目本年度的章节 + 以当前用户盖「最近一次编辑」
    （原来只校验登录、按章节 id 不看项目；spec disclosure-note-template-word-realignment Task 17）。"""
    svc = NoteWpMappingService(db)
    result = await svc.toggle_cell_mode(project_id, year, note_id, data.row_label, data.col_index, data.mode,
                                        data.manual_value, user_id=user.id)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    await db.commit()
    return result
