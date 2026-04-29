"""Phase 16: 一致性复算路由"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.consistency_replay_engine import consistency_replay_engine

router = APIRouter(prefix="/consistency", tags=["ConsistencyReplay"])


class ConsistencyReplayRequest(BaseModel):
    project_id: uuid.UUID
    snapshot_id: Optional[str] = None


@router.post("/replay")
async def replay_consistency(
    req: ConsistencyReplayRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await consistency_replay_engine.replay_consistency(
        db, req.project_id, snapshot_id=req.snapshot_id
    )
    return {
        "snapshot_id": result.snapshot_id,
        "overall_status": result.overall_status,
        "blocking_count": result.blocking_count,
        "layers": [
            {
                "from": l.from_table,
                "to": l.to_table,
                "status": l.status,
                "diffs": [
                    {
                        "object_type": d.object_type,
                        "object_id": d.object_id,
                        "field": d.field_name,
                        "expected": d.expected,
                        "actual": d.actual,
                        "diff": d.diff,
                        "severity": d.severity,
                    }
                    for d in l.diffs
                ],
            }
            for l in result.layers
        ],
        "trace_id": result.trace_id,
    }


@router.get("/report/{project_id}")
async def get_consistency_report(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await consistency_replay_engine.generate_consistency_report(db, project_id)
