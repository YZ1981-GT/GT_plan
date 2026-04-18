"""底稿 LLM 对话 API — Phase 10 Task 5.1-5.3"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """底稿 LLM 对话 — SSE 流式返回"""
    svc = WpChatService()
    return StreamingResponse(
        svc.chat_stream(db, wp_id, req.message, req.context),
        media_type="text/event-stream",
    )


@router.post("/projects/{project_id}/ai/generate-ledger-analysis")
async def generate_ledger_analysis(
    project_id: UUID,
    req: LedgerAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """台账分析底稿生成"""
    svc = WpChatService()
    return await svc.generate_ledger_analysis(
        db, project_id, req.account_codes, req.year
    )
