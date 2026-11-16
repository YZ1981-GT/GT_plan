"""export-word 统一端点（PRE-2 骨架）.

GET /api/projects/{project_id}/working-papers/{wp_id}/export-word
GET /api/projects/{project_id}/working-papers/{wp_id}/export-word/check-incomplete

后端按 wp_code 分发到 spec 编排服务（a17_word_exporter、regulatory_letter_service 等）。
未注册 wp_code 的返回 501。

🔴 2026-11-12（spec ``api-prefix-fix-recovery`` 任务 4）：本 router 的两条路径原先被
``completion_phase`` 里同路径的两份实现**先注册**遮蔽（FastAPI 取首条命中）⇒ 本文件一直不可达。
那两份实现是坏的（``WorkingPaper`` 无 ``wp_code`` 列 ⇒ 导出恒 500；check 返回
``{incomplete, count}`` 与 ``CheckIncompleteResponse`` 不符）⇒ 导出 Word 三个月不可用。
遮蔽实现已删（见 ``routers/completion_phase.py`` 头注释），本文件成为唯一实现，
两条端点补项目级只读门（原先只有 ``get_current_user``：任何登录用户可导出任意项目底稿）。

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
from app.deps import require_project_access
from app.models.core import User
from app.services.wp_export_word_service import check_incomplete, export_word

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/working-papers/{wp_id}",
    tags=["wp-export-word"],
)


# ─── Response schemas ────────────────────────────────────────────────────────


class CheckIncompleteResponse(BaseModel):
    """完整性检查结果（completion badge / 导出前确认框消费）."""

    complete: bool = Field(..., description="是否完整可导出")
    missing_fields: list[str] = Field(default_factory=list, description="未完成项的可读标签列表")
    wp_code: str = Field("", description="底稿编码")
    reason: str | None = Field(None, description="不完整原因（服务未就绪时返回）")


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/export-word")
async def get_export_word(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> Response:
    """导出 Word 文档。

    按 wp_code 前缀分发到 spec 编排服务；未注册编码返回 501。
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
    current_user: User = Depends(require_project_access("readonly")),
) -> CheckIncompleteResponse:
    """导出前完整性检查。

    用于导出确认框逻辑：``complete=false`` 时前端列明 ``missing_fields`` 再让用户决定是否继续导出。
    未注册编码的服务返回 501（此时 result 里仍带完整 schema）。
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
