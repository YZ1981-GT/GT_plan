"""附注内容模板 CRUD router（骨架）。

路径：``/api/projects/{project_id}/note-content-templates/...``
注册：``router_registry/report.py``
"""

from fastapi import APIRouter, Depends
from uuid import UUID

from app.deps import get_current_user, get_db, require_project_access

router = APIRouter(prefix="/api/projects/{project_id}/note-content-templates")


@router.get("", summary="列表：当前用户可见的附注内容模板")
async def list_templates(
    project_id: UUID,
    user=Depends(require_project_access("readonly")),
    db=Depends(get_db),
):
    return {"items": [], "total": 0}
