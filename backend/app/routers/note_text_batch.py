"""附注正文上传/知识库解析与原子批量应用 router（骨架）。

路径：``/api/projects/{project_id}/disclosure-note-import/...``
    ``/api/projects/{project_id}/disclosure-note-text-batch/...``
    ``/api/projects/{project_id}/disclosure-note-text-sections``
注册：``router_registry/report.py``
"""

from fastapi import APIRouter, Depends
from uuid import UUID

from app.deps import get_current_user, get_db, require_project_access

router = APIRouter()


@router.get(
    "/api/projects/{project_id}/disclosure-note-text-sections",
    summary="当前项目附注章节列表（scope=narrative|all）",
)
async def list_text_sections(
    project_id: UUID,
    year: int,
    scope: str = "narrative",
    user=Depends(require_project_access("readonly")),
    db=Depends(get_db),
):
    return {"items": [], "total": 0}
