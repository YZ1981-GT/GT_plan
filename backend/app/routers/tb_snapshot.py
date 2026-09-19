"""Trial Balance Snapshot Router — 试算表版本时光机端点"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.tb_snapshot_service import TbSnapshotService

router = APIRouter(
    prefix="/api/projects/{project_id}/trial-balance/snapshots",
    tags=["trial-balance-snapshots"],
)

_service = TbSnapshotService()


class CreateSnapshotRequest(BaseModel):
    trigger: str = "manual_save"
    summary_rows: Optional[list] = None
    detail_rows: Optional[list] = None


@router.post("")
async def create_snapshot(
    project_id: str,
    year: int = Query(...),
    body: CreateSnapshotRequest = None,
    db=Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a trial balance snapshot (dedup by content hash)."""
    if body is None:
        body = CreateSnapshotRequest()
    result = await _service.create_snapshot(
        db, project_id, year,
        trigger=body.trigger,
        actor_id=str(user.id) if user else None,
        detail_rows=body.detail_rows,
        summary_rows=body.summary_rows,
    )
    await db.commit()
    return result


@router.get("")
async def list_snapshots(
    project_id: str,
    year: int = Query(...),
    limit: int = Query(default=50, le=100),
    db=Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List snapshots for project+year."""
    return await _service.list_snapshots(db, project_id, year, limit)


# NOTE: /diff MUST be registered BEFORE /{version_no} to avoid
# FastAPI treating "diff" as a version_no path parameter.
@router.get("/diff")
async def diff_snapshots(
    project_id: str,
    year: int = Query(...),
    v1: int = Query(...),
    v2: int = Query(...),
    db=Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Compare two snapshot versions."""
    try:
        return await _service.diff_snapshots(db, project_id, year, v1, v2)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{version_no}")
async def get_snapshot(
    project_id: str,
    version_no: int,
    year: int = Query(...),
    db=Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get full snapshot detail."""
    result = await _service.get_snapshot(db, project_id, year, version_no)
    if not result:
        raise HTTPException(404, "Snapshot not found")
    return result


@router.post("/{version_no}/restore")
async def restore_snapshot(
    project_id: str,
    version_no: int,
    year: int = Query(...),
    db=Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Restore trial balance to a historical snapshot. Requires manager+."""
    try:
        result = await _service.restore_snapshot(
            db, project_id, year, version_no,
            actor_id=str(user.id) if user else None,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(404, str(e))
