"""文档级 AI 对话端点

POST /api/ai-chat/doc/{doc_type}/{doc_id}  — streaming 对话（复用 ai_service）
GET  /api/ai-chat/doc/{doc_type}/{doc_id}/history — 对话历史
POST /api/ai-chat/adopt — 采纳 AI 内容回写（走确认流 AIContentMustBeConfirmedRule）

需求: 1.1, 4.1, 4.2, 5.3
属性: D4（确认流门禁：AI 生成内容回写前必经 AIContentMustBeConfirmedRule）
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.ai_service import AIService
from app.services.doc_ai_context_builder import ContextBuilder, ChatContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai-chat", tags=["doc-ai-chat"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class DocChatRequest(BaseModel):
    """文档级对话请求"""
    query: str = Field(..., min_length=1, max_length=4000, description="用户提问")
    year: int = Field(..., description="审计年度")
    project_id: str = Field(..., description="项目 ID")
    extra_scopes: list[str] | None = Field(None, description="额外知识范围（文件夹 ID 列表）")


class AdoptRequest(BaseModel):
    """采纳 AI 内容回写请求（走确认流）"""
    content: str = Field(..., min_length=1, description="AI 生成的内容")
    project_id: str = Field(..., description="项目 ID")
    doc_type: str = Field(..., description="目标文档类型")
    doc_id: str = Field(..., description="目标文档 ID")
    target_cell: str | None = Field(None, description="目标单元格引用")
    target_field: str | None = Field(None, description="目标字段名")
    confidence: float = Field(0.85, ge=0.0, le=1.0, description="置信度")


# ---------------------------------------------------------------------------
# 内存对话历史（简单实现，后续可迁移到 DB）
# ---------------------------------------------------------------------------

# key: "{doc_type}:{doc_id}:{user_id}" → list of messages
_chat_history: dict[str, list[dict]] = {}

_MAX_HISTORY_PER_DOC = 50


def _history_key(doc_type: str, doc_id: str, user_id: UUID) -> str:
    return f"{doc_type}:{doc_id}:{user_id}"


def _append_history(key: str, role: str, content: str) -> None:
    if key not in _chat_history:
        _chat_history[key] = []
    _chat_history[key].append({"role": role, "content": content})
    # 限制历史长度
    if len(_chat_history[key]) > _MAX_HISTORY_PER_DOC:
        _chat_history[key] = _chat_history[key][-_MAX_HISTORY_PER_DOC:]


def _get_history(key: str) -> list[dict]:
    return _chat_history.get(key, [])


# ---------------------------------------------------------------------------
# POST /api/ai-chat/doc/{doc_type}/{doc_id} — streaming 对话
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你是一名专业的审计顾问，熟悉中国会计准则（CAS）、审计准则和内部控制规范。
请根据提供的文档上下文和关联知识，准确、专业地回答用户的问题。

回答要求：
1. 专业、准确、客观
2. 如涉及具体法规，请注明依据
3. 如上下文不足以回答，请明确说明
4. 保持审计人员的职业谨慎态度
5. 引用来源时标注知识文件名称或底稿编号
"""


@router.post("/doc/{doc_type}/{doc_id}")
async def doc_ai_chat(
    doc_type: str,
    doc_id: str,
    req: DocChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """文档级 AI 对话 — SSE streaming 响应

    复用 ContextBuilder 构建上下文 → ai_service streaming → 留痕。
    需求: 1.1, 5.3
    """
    try:
        project_id = UUID(req.project_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="无效的 project_id")

    # 构建上下文
    builder = ContextBuilder(db)
    try:
        context = await builder.build(
            doc_type=doc_type,
            doc_id=doc_id,
            project_id=project_id,
            year=req.year,
            query=req.query,
            user=current_user,
            extra_scopes=req.extra_scopes,
        )
    except Exception as e:
        logger.warning(f"ContextBuilder.build 失败: {e}")
        # 降级：无上下文继续对话
        context = ChatContext(
            doc_excerpt="",
            knowledge_hits=[],
            project_summary="",
            citations=[],
            token_estimate=0,
        )

    return StreamingResponse(
        _stream_chat(db, doc_type, doc_id, req.query, context, current_user),
        media_type="text/event-stream",
    )


async def _stream_chat(
    db: AsyncSession,
    doc_type: str,
    doc_id: str,
    query: str,
    context: ChatContext,
    user: User,
) -> AsyncGenerator[str, None]:
    """SSE streaming 生成器：构建 messages → ai_service streaming → 收集完整回复 → 留痕"""

    # 构建 LLM messages
    messages = _build_messages(doc_type, doc_id, query, context, user)

    # 记录用户消息到历史
    history_key = _history_key(doc_type, doc_id, user.id)
    _append_history(history_key, "user", query)

    # 发送引用来源（作为第一个 SSE 事件）
    if context.citations:
        citations_data = [
            {
                "source_type": c.source_type,
                "source_id": c.source_id,
                "source_name": c.source_name,
                "paragraph_index": c.paragraph_index,
            }
            for c in context.citations
        ]
        yield f"data: {json.dumps({'type': 'citations', 'data': citations_data}, ensure_ascii=False)}\n\n"

    # 流式调用 ai_service
    ai_service = AIService(db)
    full_response = ""

    try:
        stream_gen = await ai_service.chat_completion(
            messages=messages,
            stream=True,
            temperature=0.3,
        )
        async for chunk in stream_gen:
            full_response += chunk
            yield f"data: {json.dumps({'type': 'content', 'data': chunk}, ensure_ascii=False)}\n\n"
    except Exception as e:
        logger.exception("doc_ai_chat streaming 失败")
        yield f"data: {json.dumps({'type': 'error', 'data': f'AI 服务暂不可用: {e}'}, ensure_ascii=False)}\n\n"

    # 记录助手回复到历史
    if full_response:
        _append_history(history_key, "assistant", full_response)

    # 发送完成事件
    yield f"data: {json.dumps({'type': 'done', 'data': {'token_estimate': context.token_estimate}}, ensure_ascii=False)}\n\n"


def _build_messages(
    doc_type: str,
    doc_id: str,
    query: str,
    context: ChatContext,
    user: User,
) -> list[dict[str, str]]:
    """构建 LLM 消息列表（system + context + history + user）"""
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    # 注入上下文
    context_parts: list[str] = []
    if context.project_summary:
        context_parts.append(f"【项目信息】\n{context.project_summary}")
    if context.doc_excerpt:
        context_parts.append(f"【当前文档内容】\n{context.doc_excerpt}")
    if context.knowledge_hits:
        knowledge_text = "\n\n".join(
            f"【{hit.source_name or hit.source_type}】\n{hit.content}"
            for hit in context.knowledge_hits[:5]
        )
        context_parts.append(f"【关联知识】\n{knowledge_text}")

    if context_parts:
        messages.append({
            "role": "system",
            "content": "\n\n".join(context_parts),
        })

    # 添加历史消息（最近 10 轮）
    history_key = _history_key(doc_type, doc_id, user.id)
    history = _get_history(history_key)
    for msg in history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # 当前用户消息
    messages.append({"role": "user", "content": query})

    return messages


# ---------------------------------------------------------------------------
# GET /api/ai-chat/doc/{doc_type}/{doc_id}/history — 对话历史
# ---------------------------------------------------------------------------


@router.get("/doc/{doc_type}/{doc_id}/history")
async def get_chat_history(
    doc_type: str,
    doc_id: str,
    current_user: User = Depends(get_current_user),
):
    """获取文档级对话历史

    需求: 5.2（本地缓存断网可查历史）
    """
    history_key = _history_key(doc_type, doc_id, current_user.id)
    history = _get_history(history_key)
    return {"messages": history, "total": len(history)}


# ---------------------------------------------------------------------------
# POST /api/ai-chat/adopt — 采纳 AI 内容回写（走确认流）
# ---------------------------------------------------------------------------


@router.post("/adopt")
async def adopt_ai_content(
    req: AdoptRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """采纳 AI 生成内容回写 — 走确认流（D4 属性）

    调用 wrap_ai_output_with_log 写入 ai_content_log（pending 状态），
    触发 AIContentMustBeConfirmedRule 门禁。
    AI 内容未经确认不直接写入底稿/附注。

    需求: 4.1, 4.2
    属性: D4（确认流门禁：AI 生成内容回写前必经 AIContentMustBeConfirmedRule）
    """
    from app.services.wp_ai_service import wrap_ai_output_with_log

    try:
        project_id = UUID(req.project_id)
        doc_id = UUID(req.doc_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="无效的 project_id 或 doc_id")

    # D4: 调用 wrap_ai_output_with_log 写入 ai_content_log（pending 状态）
    # 5 参齐全时强制写 ai_content_log 表 → 触发 AIContentMustBeConfirmedRule
    result = await wrap_ai_output_with_log(
        content=req.content,
        confidence=req.confidence,
        target_cell=req.target_cell,
        target_field=req.target_field,
        db=db,
        project_id=project_id,
        user_id=current_user.id,
        instance_type=req.doc_type,
        instance_id=doc_id,
    )

    await db.commit()

    return {
        "success": True,
        "ai_content_log_id": result.get("ai_content_log_id"),
        "confirm_action": result.get("confirm_action"),
        "content_hash": result.get("content_hash"),
        "message": "AI 内容已提交确认流，待审核确认后方可写入文档",
    }
