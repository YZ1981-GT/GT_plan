"""export-word 统一端点（PRE-2 骨架）.

GET /api/projects/{project_id}/working-papers/{wp_id}/export-word
GET /api/projects/{project_id}/working-papers/{wp_id}/export-word/check-incomplete

后端按 wp_code 分发到 spec 编排服务（a17_word_exporter、regulatory_letter_service 等）。
当前无编排服务就绪→全部返回 501。

Requirements: PRE-2（.kiro/specs/completion-phase-infra/requirements.md）
"""

from __future__ import annotations

import logging
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.wp_export_word_service import check_incomplete, export_word

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/working-papers/{wp_id}",
    tags=["wp-export-word"],
)


# ─── Response schemas ────────────────────────────────────────────────────────


class CheckIncompleteResponse(BaseModel):
    """完整性检查结果（completion badge 消费）."""

    complete: bool = Field(..., description="是否完整可导出")
    missing_fields: list[str] = Field(default_factory=list, description="缺失字段列表")
    wp_code: str = Field("", description="底稿编码")
    reason: str | None = Field(None, description="不完整原因（服务未就绪时返回）")


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/export-word")
async def get_export_word(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """导出 Word 文档。

    按 wp_code 前缀分发到 spec 编排服务。
    当前无编排服务就绪，返回 501 Not Implemented。
    """
    file_bytes, wp_code, status = await export_word(db, project_id, wp_id)

    if status == 404:
        raise HTTPException(status_code=404, detail="底稿不存在")

    if status == 501:
        raise HTTPException(
            status_code=501,
            detail=f"导出服务未就绪（wp_code={wp_code}）",
        )

    # 200 — 返回 docx 文件
    filename = f"{wp_code}.docx" if wp_code else "export.docx"
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


@router.get("/export-word/check-incomplete")
async def get_check_incomplete(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CheckIncompleteResponse:
    """导出前完整性检查。

    用于 completion badge 逻辑：complete=true 时才允许显示绿色 badge。
    当前无检查服务就绪，返回 complete=false + reason。
    """
    result, status = await check_incomplete(db, project_id, wp_id)

    if status == 404:
        raise HTTPException(status_code=404, detail="底稿不存在")

    if status == 501:
        # 501 时仍返回 JSON body（前端需要 schema），但设置 HTTP 状态为 501
        raise HTTPException(
            status_code=501,
            detail=result,
        )

    return CheckIncompleteResponse(**result)
