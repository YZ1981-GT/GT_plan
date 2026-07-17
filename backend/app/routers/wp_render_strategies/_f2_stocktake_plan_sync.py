"""F2-22 监盘计划 — 结构化 ↔ OnlyOffice docx 双向同步 API."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db, set_rls_context
from app.deps import get_current_user
from app.models.core import User
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.f2_stocktake_plan_sync import (
    FIELDS_ITEM_ID,
    create_g2_6_2_template_docx,
    extract_fields_from_docx,
    fill_plan_docx,
    merge_extracted_into_existing,
    parse_fields_json,
)
from app.services.wp_template_finder import TEMPLATES_DIR, find_template_file_any

logger = logging.getLogger(__name__)

router = APIRouter(tags=["f2-st-plan-sync"])

_SHEET_CODES = {"F2-22", "监盘计划F2-22"}


def _onlyoffice_dir(project_id: UUID) -> Path:
    """项目 OnlyOffice 缓存目录（避免从 wp_onlyoffice_router 循环导入）。"""
    return Path(settings.STORAGE_ROOT) / "projects" / str(project_id) / "workpapers" / "onlyoffice"


async def _load_wp(db: AsyncSession, wp_id: UUID) -> tuple[WorkingPaper, str]:
    result = await db.execute(
        sa.select(WorkingPaper, WpIndex.wp_code)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false())
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="底稿不存在")
    return row[0], row[1]


def _ensure_template() -> Path:
    """确保 F2-22 占位符模板存在；缺失则按 G2-6-2 结构生成。"""
    existing = find_template_file_any("F2-22")
    if existing and existing.suffix.lower() == ".docx":
        try:
            from docx import Document

            text = "\n".join(p.text for p in Document(str(existing)).paragraphs)
            if "${purpose}" in text:
                return existing
        except Exception:  # noqa: BLE001
            pass
    target = TEMPLATES_DIR / "F" / "F2-22 存货监盘计划.docx"
    return create_g2_6_2_template_docx(target)


async def _load_fields(db: AsyncSession, wp_id: UUID) -> dict[str, str]:
    result = await db.execute(
        sa.text(
            "SELECT remark FROM checklist_responses "
            "WHERE wp_id = :wid AND item_id = :iid LIMIT 1"
        ),
        {"wid": str(wp_id), "iid": FIELDS_ITEM_ID},
    )
    row = result.first()
    return parse_fields_json(row.remark if row else None)


async def _save_fields(
    db: AsyncSession,
    *,
    project_id: UUID,
    wp_id: UUID,
    fields: dict[str, str],
) -> None:
    import json

    payload = json.dumps(fields, ensure_ascii=False)
    await db.execute(
        sa.text(
            "INSERT INTO checklist_responses "
            "(project_id, wp_id, item_id, conclusion, remark) "
            "VALUES (:pid, :wid, :iid, NULL, :remark) "
            "ON CONFLICT (wp_id, item_id) "
            "DO UPDATE SET remark = EXCLUDED.remark, "
            "project_id = COALESCE(checklist_responses.project_id, EXCLUDED.project_id)"
        ),
        {
            "pid": str(project_id),
            "wid": str(wp_id),
            "iid": FIELDS_ITEM_ID,
            "remark": payload,
        },
    )
    await db.commit()


async def _project_context(db: AsyncSession, project_id: UUID) -> dict:
    result = await db.execute(
        sa.text(
            "SELECT client_name, audit_year, "
            "to_char(audit_period_end, 'YYYY-MM-DD') AS bs_date "
            "FROM projects WHERE id = :pid"
        ),
        {"pid": str(project_id)},
    )
    row = result.first()
    if not row:
        return {}
    return {
        "client_name": row.client_name or "",
        "audit_year": str(row.audit_year or ""),
        "bs_date": row.bs_date or "",
    }


def _normalize_sheet(sheet: str) -> str:
    s = (sheet or "").strip()
    if "F2-22" in s or s in _SHEET_CODES:
        return "F2-22"
    raise HTTPException(status_code=400, detail=f"不支持的 sheet: {sheet}")


@router.post("/api/workpapers/{wp_id}/f2-st/plan-sync-to-oo")
async def f2_st_plan_sync_to_oo(
    wp_id: UUID,
    sheet: str = Query("F2-22"),
    project_id: UUID | None = Query(None, description="可选；缺省时从底稿反查"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """结构化 → OnlyOffice：用 F2-22-fields 填充 docx 缓存。"""
    _ = current_user
    _normalize_sheet(sheet)
    wp, _wp_code = await _load_wp(db, wp_id)
    pid = project_id or wp.project_id
    if project_id and project_id != wp.project_id:
        raise HTTPException(status_code=400, detail="project_id 与底稿所属项目不一致")
    await set_rls_context(db, pid)
    template = _ensure_template()
    fields = await _load_fields(db, wp_id)
    ctx = await _project_context(db, pid)
    target = _onlyoffice_dir(pid) / "F2-22.docx"
    legacy = target.with_suffix(".xlsx")
    if legacy.exists():
        try:
            legacy.unlink()
        except OSError:
            pass
    fill_plan_docx(template, target, fields, project_context=ctx)
    return {
        "ok": True,
        "direction": "to_oo",
        "path": str(target),
        "filled_keys": [k for k, v in fields.items() if v],
        "size": target.stat().st_size,
    }


@router.post("/api/workpapers/{wp_id}/f2-st/plan-sync-from-oo")
async def f2_st_plan_sync_from_oo(
    wp_id: UUID,
    sheet: str = Query("F2-22"),
    project_id: UUID | None = Query(None, description="可选；缺省时从底稿反查"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """OnlyOffice → 结构化：解析 docx 缓存写回 F2-22-fields。"""
    _ = current_user
    _normalize_sheet(sheet)
    wp, _wp_code = await _load_wp(db, wp_id)
    pid = project_id or wp.project_id
    if project_id and project_id != wp.project_id:
        raise HTTPException(status_code=400, detail="project_id 与底稿所属项目不一致")
    await set_rls_context(db, pid)
    target = _onlyoffice_dir(pid) / "F2-22.docx"
    if not target.exists():
        raise HTTPException(status_code=404, detail="尚未生成监盘计划 Word 缓存，请先打开在线编辑")
    existing = await _load_fields(db, wp_id)
    try:
        extracted = extract_fields_from_docx(target)
    except Exception as exc:  # noqa: BLE001
        logger.exception("F2-22 plan-sync-from-oo 解析失败 wp_id=%s", wp_id)
        raise HTTPException(status_code=500, detail=f"Word 解析失败: {exc}") from exc
    merged = merge_extracted_into_existing(existing, extracted)
    try:
        await _save_fields(db, project_id=pid, wp_id=wp_id, fields=merged)
    except Exception as exc:  # noqa: BLE001
        logger.exception("F2-22 plan-sync-from-oo 落库失败 wp_id=%s", wp_id)
        raise HTTPException(status_code=500, detail=f"结构化落库失败: {exc}") from exc
    return {
        "ok": True,
        "direction": "from_oo",
        "extracted_keys": list(extracted.keys()),
        "fields": merged,
    }
