"""Sprint A.7 — 集团附注模板基线路由.

5 端点:
- POST /api/group-note-baselines                       → save_baseline
- GET  /api/group-note-baselines/{id}/versions         → get_baseline_versions
- GET  /api/group-note-baselines/{id}/preview-diff     → diff_baseline
- POST /api/projects/{project_id}/apply-group-baseline → apply_baseline
- GET  /api/projects/{project_id}/baseline-sync-status → sync status
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.group_note_baseline_service import GroupNoteBaselineService

router = APIRouter(tags=["group-note-baseline"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class SaveBaselineRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    template_type: str = Field("soe", max_length=20)
    parent_baseline_id: UUID | None = None


class ApplyBaselineRequest(BaseModel):
    baseline_id: UUID
    year: int


class SyncBaselineRequest(BaseModel):
    child_project_ids: list[UUID]
    year: int | None = None


class UpgradeBaselineRequest(BaseModel):
    sections_data: list[dict] = Field(default_factory=list)
    bump: str = Field("minor", pattern="^(minor|major)$")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/api/group-note-baselines")
async def save_baseline(
    body: SaveBaselineRequest,
    project_id: UUID = Query(..., description="Parent project ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save current project notes as a group baseline."""
    svc = GroupNoteBaselineService(db)
    result = await svc.save_baseline(
        parent_project_id=project_id,
        name=body.name,
        template_type=body.template_type,
        parent_baseline_id=body.parent_baseline_id,
        created_by=current_user.id,
    )
    await db.commit()
    return result


@router.get("/api/group-note-baselines/{baseline_id}/versions")
async def get_baseline_versions(
    baseline_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all baseline versions for the parent project of this baseline."""
    svc = GroupNoteBaselineService(db)
    # First get the baseline to find parent_project_id
    baseline = await svc._get_baseline(baseline_id)
    if baseline is None:
        return {"error": "baseline_not_found", "versions": []}
    return {"versions": await svc.get_baseline_versions(baseline.parent_project_id)}


@router.get("/api/group-note-baselines/{baseline_id}/preview-diff")
async def preview_diff(
    baseline_id: UUID,
    project_id: UUID = Query(..., description="Child project ID"),
    year: int = Query(..., description="Year"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Preview diff between child project notes and baseline."""
    svc = GroupNoteBaselineService(db)
    return await svc.diff_baseline(project_id, year, baseline_id)


@router.post("/api/projects/{project_id}/apply-group-baseline")
async def apply_group_baseline(
    project_id: UUID,
    body: ApplyBaselineRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Apply a group baseline to a child project."""
    svc = GroupNoteBaselineService(db)
    result = await svc.apply_baseline(project_id, body.year, body.baseline_id)
    if result.get("success"):
        await db.commit()
    return result


@router.get("/api/projects/{project_id}/baseline-sync-status")
async def baseline_sync_status(
    project_id: UUID,
    year: int = Query(..., description="Year"),
    baseline_id: UUID = Query(..., description="Baseline ID to check against"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get sync status between child project and baseline."""
    svc = GroupNoteBaselineService(db)
    diff = await svc.diff_baseline(project_id, year, baseline_id)
    if "error" in diff:
        return {"synced": False, "error": diff["error"]}

    total_modified = len(diff.get("modified", []))
    total_added = len(diff.get("added", []))
    total_removed = len(diff.get("removed", []))

    return {
        "synced": total_modified == 0 and total_added == 0 and total_removed == 0,
        "modified_count": total_modified,
        "added_count": total_added,
        "removed_count": total_removed,
        "unchanged_count": len(diff.get("unchanged", [])),
        "baseline_id": str(baseline_id),
    }
