"""Phase 16: 版本链路由"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.version_line_service import version_line_service

router = APIRouter(prefix="/version-line", tags=["VersionLine"])


@router.get("/{project_id}")
async def query_version_line(
    project_id: uuid.UUID,
    object_type: Optional[str] = Query(None),
    object_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = await version_line_service.query_lineage(db, project_id, object_type, object_id)
    return {"project_id": str(project_id), "items": items}
