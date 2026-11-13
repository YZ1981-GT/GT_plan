"""完成阶段公共 API — 核对表模板包 / A16 推荐 / 摘要 / issue hints / 完成标记 / A30 归档检查建议。

2026-11-12 删除本文件里 ``GET …/working-papers/{wp_id}/export-word`` 与
``…/export-word/check-incomplete`` 两个端点（spec ``api-prefix-fix-recovery`` R3 / 任务 4）：
它们与 ``wp_export_word`` 同路径、比后者先注册（FastAPI 取首条命中）⇒ 后者永远不可达；
且生效实现本身是坏的 —— ``WorkingPaper`` 模型没有 ``wp_code`` 列（只有 ``wp_index_id``），
``find_template_file_any(wp.wp_code)`` 恒 ``AttributeError`` ⇒ 导出 Word 恒 500；
check 返回 ``{incomplete, count}`` 而 ``wp_export_word.CheckIncompleteResponse`` 与前端读
``{complete, missing_fields, wp_code, reason}`` ⇒ 确认框永不弹。两个端点现由 ``wp_export_word``
提供（按编码分发到 A17-1 / A17-2-1 / A18-2 的专用导出服务）。

同文件另有 3 个与专用路由同路径的端点（``a16/recommended-version``、``issue-hints``、
``workpaper-summaries/{key}``），仍为「先注册者遮蔽后注册者」，已冻结在
``tests/test_duplicate_route_registration_baseline.py::_KNOWN_DUPLICATES`` 里，不在本 spec 范围。

守卫 ``tests/test_duplicate_route_registration_baseline.py``。
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.models.workpaper_models import WorkingPaper
from app.services.a16_version_service import recommend_main_version, recommend_supplement

router = APIRouter(prefix="/api/projects", tags=["completion-phase"])


class SummaryResponse(BaseModel):
    ready: bool
    key: str
    source_wp: list[str] = []
    summary: dict | None = None
    reason: str | None = None


@router.get("/{project_id}/checklist-templates/{wp_code}")
async def get_checklist_template_bundle(
    project_id: UUID,
    wp_code: str,
    wp_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Bundle Tab 嵌入核对表 — 按 wp_code 取模板 + wp_id 取填写数据."""
    from app.services.checklist_template_loader import load_checklist_template

    wp = await db.get(WorkingPaper, wp_id)
    if not wp or wp.project_id != project_id:
        raise HTTPException(404, "底稿不存在")

    try:
        template_data = await load_checklist_template(wp_code)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e

    r = await db.execute(
        sa.text(
            "SELECT item_id, conclusion, remark, wp_ref "
            "FROM checklist_responses WHERE wp_id = :wp_id"
        ),
        {"wp_id": str(wp_id)},
    )
    responses = {
        row.item_id: {
            "conclusion": row.conclusion,
            "remark": row.remark,
            "wp_ref": row.wp_ref,
        }
        for row in r.fetchall()
    }
    return {"template": template_data, "responses": responses}


@router.get("/{project_id}/a16/recommended-version")
async def get_a16_recommended_version(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    main = await recommend_main_version(db, project_id)
    supplement = await recommend_supplement(db, project_id)
    return {"main": main, "supplement": supplement}


@router.get("/{project_id}/completion-flags")
async def get_completion_flags(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """项目级完成标记（供 A1-11 等签发入口解锁）。

    a17_completed：A17 签发自检硬项全部通过。
    """
    from app.services.a17_signoff_self_check import get_signoff_self_check

    check = await get_signoff_self_check(db, project_id)
    return {
        "a17_completed": bool(check.get("a17_completed")),
        "ready": bool(check.get("ready")),
        "checked_at": None,
    }


@router.get("/{project_id}/workpaper-summaries/{key}")
async def get_workpaper_summary(
    project_id: UUID,
    key: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """摘要 API 骨架 — plus 阶段扩展各 key 取数."""
    handlers = {
        "misstatement": _summary_misstatement,
        "going_concern": _summary_going_concern,
        "control_deficiency": _summary_control_deficiency,
    }
    fn = handlers.get(key)
    if not fn:
        return SummaryResponse(ready=False, key=key, reason=f"未知摘要 key: {key}")
    return await fn(db, project_id, key)


async def _summary_misstatement(db: AsyncSession, project_id: UUID, key: str) -> SummaryResponse:
    try:
        r = await db.execute(
            sa.text(
                "SELECT COUNT(*) FROM checklist_responses cr "
                "JOIN working_paper wp ON wp.id = cr.wp_id "
                "WHERE wp.project_id = :pid AND cr.item_id LIKE 'A13%'"
            ),
            {"pid": str(project_id)},
        )
        count = int(r.scalar_one() or 0)
        return SummaryResponse(
            ready=count > 0,
            key=key,
            source_wp=["A13-1", "A13-4"],
            summary={"response_count": count},
            reason=None if count > 0 else "A13 表单未填写",
        )
    except Exception as e:
        return SummaryResponse(ready=False, key=key, reason=str(e))


async def _summary_going_concern(db: AsyncSession, project_id: UUID, key: str) -> SummaryResponse:
    r = await db.execute(
        sa.text(
            "SELECT COUNT(*) FROM checklist_responses cr "
            "JOIN working_paper wp ON wp.id = cr.wp_id "
            "WHERE wp.project_id = :pid AND cr.item_id LIKE 'A15-1%'"
        ),
        {"pid": str(project_id)},
    )
    count = int(r.scalar_one() or 0)
    return SummaryResponse(
        ready=count > 0,
        key=key,
        source_wp=["A15-1"],
        summary={"filled_items": count},
        reason=None if count > 0 else "A15-1 未填写",
    )


async def _summary_control_deficiency(db: AsyncSession, project_id: UUID, key: str) -> SummaryResponse:
    r = await db.execute(
        sa.text(
            "SELECT COUNT(*) FROM checklist_responses cr "
            "JOIN working_paper wp ON wp.id = cr.wp_id "
            "WHERE wp.project_id = :pid AND cr.item_id LIKE 'A14-1%'"
        ),
        {"pid": str(project_id)},
    )
    count = int(r.scalar_one() or 0)
    return SummaryResponse(
        ready=count > 0,
        key=key,
        source_wp=["A14-1"],
        summary={"defect_rows": count},
        reason=None if count > 0 else "A14-1 未填写",
    )


@router.get("/{project_id}/issue-hints")
async def get_issue_hints(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """舞弊/违规 issue_tickets 计数提示（不写入正文）."""
    fraud_q = sa.text(
        "SELECT id, title FROM issue_tickets "
        "WHERE project_id = :pid AND severity IN ('major','blocker') "
        "AND (title ILIKE '%舞弊%' OR description ILIKE '%舞弊%') LIMIT 20"
    )
    legal_q = sa.text(
        "SELECT id, title FROM issue_tickets "
        "WHERE project_id = :pid AND severity IN ('blocker','major') "
        "AND (title ILIKE '%违法%' OR title ILIKE '%违规%' OR description ILIKE '%违法%') LIMIT 20"
    )
    fraud_rows = (await db.execute(fraud_q, {"pid": str(project_id)})).fetchall()
    legal_rows = (await db.execute(legal_q, {"pid": str(project_id)})).fetchall()
    return {
        "fraud": {"count": len(fraud_rows), "titles": [r.title for r in fraud_rows]},
        "legal": {"count": len(legal_rows), "titles": [r.title for r in legal_rows]},
    }


@router.get("/{project_id}/workpapers/{wp_id}/archive-checklist/suggestions")
async def get_archive_checklist_suggestions(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
):
    """A30 电子底稿归档检查表「按项目底稿建议」（spec attachment-archive-and-a-class-evidence 需求 8.2）。

    项目里有该编码的未删除底稿 ⇒「是」，否则「否」；只给建议，填写与保存仍走核对表现有保存（前端只填空项）。
    """
    from app.models.workpaper_models import WpIndex
    from app.services.checklist_index_parser import (
        checklist_item_codes,
        get_index_checklist_template,
        is_index_checklist,
        normalize_code,
    )

    row = (await db.execute(
        sa.select(WorkingPaper.project_id, WorkingPaper.is_deleted, WpIndex.wp_code)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(WorkingPaper.id == wp_id)
    )).first()
    if row is None or row.project_id != project_id or row.is_deleted:
        raise HTTPException(404, "底稿不存在")
    if not is_index_checklist(row.wp_code):
        raise HTTPException(404, "该底稿没有归档检查建议")
    try:
        template = await get_index_checklist_template(row.wp_code)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    present = {normalize_code(code) for code in (await db.execute(
        sa.select(WpIndex.wp_code).join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
        .where(WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == sa.false())
    )).scalars().all()}
    codes = checklist_item_codes(template)
    suggestions = {item_id: ("是" if code in present else "否") for item_id, code in codes.items()}
    return {"suggestions": suggestions, "total": len(codes),
            "present": sum(1 for v in suggestions.values() if v == "是")}
