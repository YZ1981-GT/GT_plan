"""完成阶段公共 API — A16 推荐 / 摘要 / issue hints / export-word."""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.workpaper_models import WorkingPaper
from app.services.a16_version_service import recommend_main_version, recommend_supplement
from app.services.docx_template_filler import check_incomplete_text, fill_docx_template
from app.services.wp_template_init_service import find_template_file_any

logger = logging.getLogger(__name__)

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
    from app.services.checklist_docx_parser import get_checklist_template
    from app.services.checklist_xlsx_parser import get_checklist_xlsx_template, is_xlsx_checklist

    wp = await db.get(WorkingPaper, wp_id)
    if not wp or wp.project_id != project_id:
        raise HTTPException(404, "底稿不存在")

    try:
        if is_xlsx_checklist(wp_code):
            template_data = await get_checklist_xlsx_template(wp_code)
        else:
            template_data = await get_checklist_template(wp_code)
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
                "JOIN working_papers wp ON wp.id = cr.wp_id "
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
            "JOIN working_papers wp ON wp.id = cr.wp_id "
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
            "JOIN working_papers wp ON wp.id = cr.wp_id "
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


@router.get("/{project_id}/working-papers/{wp_id}/export-word")
async def export_workpaper_word(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    wp = await db.get(WorkingPaper, wp_id)
    if not wp or wp.project_id != project_id:
        raise HTTPException(404, "底稿不存在")
    path = find_template_file_any(wp.wp_code)
    if not path:
        raise HTTPException(404, f"模板未找到: {wp.wp_code}")
    r = await db.execute(
        sa.text("SELECT client_name, audit_period_end FROM projects WHERE id = :pid"),
        {"pid": str(project_id)},
    )
    row = r.one_or_none()
    replacements = {}
    if row:
        if row.client_name:
            replacements["××公司"] = row.client_name
            replacements["XX公司"] = row.client_name
        if row.audit_period_end:
            year = str(row.audit_period_end.year)
            replacements["202X"] = year
            replacements["201X"] = year
    data, incomplete = fill_docx_template(path, replacements=replacements)
    if incomplete:
        logger.info("export-word incomplete placeholders wp=%s: %s", wp.wp_code, incomplete[:5])
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{wp.wp_code}_export.docx"'},
    )


@router.get("/{project_id}/working-papers/{wp_id}/export-word/check-incomplete")
async def check_export_incomplete(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    wp = await db.get(WorkingPaper, wp_id)
    if not wp or wp.project_id != project_id:
        raise HTTPException(404, "底稿不存在")
    r = await db.execute(
        sa.text(
            "SELECT remark FROM checklist_responses WHERE wp_id = :wid AND remark IS NOT NULL"
        ),
        {"wid": str(wp_id)},
    )
    issues: list[str] = []
    for (remark,) in r.fetchall():
        if remark:
            issues.extend(check_incomplete_text(str(remark)))
    return {"incomplete": issues, "count": len(issues)}
