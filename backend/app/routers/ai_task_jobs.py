"""耐久 AI 批任务 API：创建、恢复查询、取消和单项重试。"""

from __future__ import annotations

import hashlib
from typing import Any, Literal
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user
from app.models.ai_task_job_models import AiTaskJob
from app.models.core import User
from app.models.report_models import DisclosureNote, NoteStatus
from app.services.ai_task_job_service import (
    AiTaskJobConflict,
    AiTaskJobNotFound,
    AiTaskTarget,
    canonical_hash,
    create_or_get_job,
    get_job_snapshot,
    request_cancel,
    retry_item,
)

router = APIRouter(prefix="/api/projects/{project_id}/ai-task-jobs", tags=["AI批任务"])


def _text_hash(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _broadcast_job_update(snapshot: dict[str, Any]) -> None:
    """通知已订阅页面重新读取 DB snapshot；事件本身不作为状态真源。"""
    from app.services.event_bus import event_bus

    event_bus.broadcast_raw("ai.task.updated", {
        "project_id": snapshot.get("project_id"),
        "year": snapshot.get("year"),
        "job_id": snapshot.get("job_id"),
        "status": snapshot.get("status"),
        "version": snapshot.get("version"),
    })


class AiTaskJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_kind: Literal["note_batch_prefill", "workpaper_batch_review"]
    year: int = Field(..., ge=1900, le=2999)
    idempotency_key: str = Field(..., min_length=1, max_length=128)
    doc_filter: list[UUID] = Field(default_factory=list, max_length=20)
    wp_code_prefix: str | None = Field(None, max_length=40)


async def _note_targets(db: AsyncSession, project_id: UUID, year: int, body: AiTaskJobCreate):
    rows = list((await db.execute(sa.select(DisclosureNote).where(
        DisclosureNote.project_id == project_id,
        DisclosureNote.year == year,
        DisclosureNote.is_deleted == sa.false(),
        DisclosureNote.is_local_override == sa.false(),
        sa.or_(
            DisclosureNote.text_content.is_(None),
            sa.func.length(sa.func.trim(DisclosureNote.text_content)) == 0,
            DisclosureNote.status == NoteStatus.draft,
        ),
    ).order_by(DisclosureNote.sort_order))).scalars().all())
    return [
        AiTaskTarget(
            "note_section", row.id, row.note_section,
            {
                "note_section": row.note_section,
                "section_title": row.section_title or row.note_section,
                "account_name": row.account_name or "",
                "doc_filter": [str(value) for value in body.doc_filter],
            },
            baseline_version=str(getattr(row, "updated_at", "") or ""),
            before_hash=_text_hash(row.text_content),
        )
        for row in rows
    ]


async def _review_targets(db: AsyncSession, project_id: UUID, body: AiTaskJobCreate):
    if not (body.wp_code_prefix or "").strip():
        raise HTTPException(422, "底稿批量复核必须提供 wp_code_prefix")
    from app.models.workpaper_models import WorkingPaper
    from app.services.batch_review_service import BatchReviewService

    rows = await BatchReviewService()._get_sheets_for_prefix(
        str(project_id), body.wp_code_prefix.strip()
    )
    ids = [UUID(row["wp_id"]) for row in rows]
    versions: dict[UUID, tuple[int, UUID | None, object]] = {}
    if ids:
        version_rows = (await db.execute(
            sa.select(
                WorkingPaper.id,
                WorkingPaper.content_revision,
                WorkingPaper.current_content_version_id,
                WorkingPaper.updated_at,
            ).where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.id.in_(ids),
                WorkingPaper.is_deleted == sa.false(),
            )
        )).all()
        versions = {
            row.id: (
                int(row.content_revision or 0),
                row.current_content_version_id,
                row.updated_at,
            )
            for row in version_rows
        }
    targets: list[AiTaskTarget] = []
    for row in rows:
        wp_id = UUID(row["wp_id"])
        version = versions.get(wp_id)
        if version is None:
            continue
        revision, content_version_id, updated_at = version
        fingerprint = {
            "content_revision": revision,
            "content_version_id": str(content_version_id) if content_version_id else None,
            "updated_at": str(updated_at or ""),
        }
        targets.append(AiTaskTarget(
            "workpaper", wp_id, row["sheet_name"],
            {"wp_code": row["wp_code"], "sheet_name": row["sheet_name"]},
            baseline_version=str(revision),
            before_hash=canonical_hash(fingerprint),
        ))
    return targets


@router.post("")
async def create_job(
    project_id: UUID,
    body: AiTaskJobCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    level = "readonly" if body.task_kind == "note_batch_prefill" else "review"
    await assert_project_permission(db, user, project_id, level)
    targets = (
        await _note_targets(db, project_id, body.year, body)
        if body.task_kind == "note_batch_prefill"
        else await _review_targets(db, project_id, body)
    )
    payload = body.model_dump(mode="json", exclude={"idempotency_key"})
    try:
        job, created = await create_or_get_job(
            db,
            project_id=project_id,
            year=body.year,
            task_kind=body.task_kind,
            actor_id=user.id,
            idempotency_key=body.idempotency_key,
            request_payload=payload,
            targets=targets,
        )
    except AiTaskJobConflict as exc:
        await db.rollback()
        raise HTTPException(409, str(exc)) from exc
    await db.commit()
    from app.workers.ai_task_worker import wake
    wake()
    snapshot = await get_job_snapshot(db, project_id=project_id, job_id=job.id)
    response = {**snapshot, "reused": not created}
    _broadcast_job_update(response)
    return response


@router.get("/{job_id}")
async def get_job(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await assert_project_permission(db, user, project_id, "readonly")
    try:
        return await get_job_snapshot(db, project_id=project_id, job_id=job_id)
    except AiTaskJobNotFound as exc:
        raise HTTPException(404, "AI 批任务不存在") from exc


@router.post("/{job_id}/cancel")
async def cancel_job(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = (await db.execute(sa.select(AiTaskJob).where(
        AiTaskJob.id == job_id, AiTaskJob.project_id == project_id,
    ))).scalar_one_or_none()
    if job is None:
        raise HTTPException(404, "AI 批任务不存在")
    level = "review" if job.task_kind == "workpaper_batch_review" else (
        "readonly" if job.actor_id == user.id else "edit"
    )
    await assert_project_permission(db, user, project_id, level)
    result = await request_cancel(db, project_id=project_id, job_id=job_id)
    await db.commit()
    _broadcast_job_update(result)
    return result


@router.post("/{job_id}/items/{item_id}/retry")
async def retry_job_item(
    project_id: UUID,
    job_id: UUID,
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = (await db.execute(sa.select(AiTaskJob).where(
        AiTaskJob.id == job_id, AiTaskJob.project_id == project_id,
    ))).scalar_one_or_none()
    if job is None:
        raise HTTPException(404, "AI 批任务不存在")
    level = "review" if job.task_kind == "workpaper_batch_review" else (
        "readonly" if job.actor_id == user.id else "edit"
    )
    await assert_project_permission(db, user, project_id, level)
    try:
        result = await retry_item(
            db, project_id=project_id, job_id=job_id, item_id=item_id
        )
    except AiTaskJobNotFound as exc:
        raise HTTPException(404, "AI 批任务明细不存在") from exc
    except AiTaskJobConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    await db.commit()
    from app.workers.ai_task_worker import wake
    wake()
    return result
