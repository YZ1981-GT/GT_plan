"""底稿 LLM 对话 API。SSE 响应开始前完成 DB 上下文与项目权限校验。"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user_stream, require_project_access
from app.models.core import User
from app.services.wp_chat_service import WpChatService

router = APIRouter(prefix="/api/workpapers", tags=["wp-chat"])


class WpChatRequest(BaseModel):
    message: str
    context: dict[str, Any] | None = None


class LedgerAnalysisRequest(BaseModel):
    account_codes: list[str] | None = None
    year: int | None = None


@router.post("/{wp_id}/ai/chat")
async def wp_chat(
    wp_id: UUID,
    req: WpChatRequest,
    db: AsyncSession = Depends(get_db, scope="function"),
    current_user: User = Depends(get_current_user_stream),
):
    """底稿 LLM SSE：请求期准备/鉴权，响应期只流 LLM，不持有数据库连接。"""
    svc = WpChatService()
    prepared = await svc.prepare_chat(db, wp_id, req.message, req.context)
    if prepared.project_id is None:
        raise HTTPException(status_code=404, detail="底稿不存在")
    await assert_project_permission(db, current_user, prepared.project_id, "readonly")
    return StreamingResponse(svc.stream_prepared(prepared), media_type="text/event-stream")


@router.post("/projects/{project_id}/ai/generate-ledger-analysis")
async def generate_ledger_analysis(
    project_id: UUID,
    req: LedgerAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """台账分析底稿生成（读项目序时账：要求项目成员）。"""
    svc = WpChatService()
    return await svc.generate_ledger_analysis(db, project_id, req.account_codes, req.year)
