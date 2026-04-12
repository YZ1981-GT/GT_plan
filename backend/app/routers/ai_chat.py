"""AI 智能问答路由

提供基于 RAG 的审计智能问答接口，支持流式输出。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.services.ai_chat_service import AIChatService
from app.services.ai_service import AIService
from app.services.knowledge_index_service import KnowledgeIndexService
from app.services.nl_command_service import NLCommandService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["AI-智能问答"])
project_router = APIRouter(prefix="/api/projects/{project_id}/ai", tags=["AI-项目对话"])


class ChatSessionCreate(BaseModel):
    """创建会话"""
    project_id: str
    session_type: str = "general"
    title: Optional[str] = None


class ChatMessageRequest(BaseModel):
    """发送消息"""
    session_id: str
    message: str
    use_rag: bool = True


class ProjectChatRequest(BaseModel):
    """项目内发送消息"""
    message: str
    conversation_id: Optional[str] = None
    attachments: list[str] = []


class ProjectCommandParseRequest(BaseModel):
    """命令解析请求"""
    text: str


# ============ 会话管理 ============


@router.post("/sessions")
async def create_chat_session(
    data: ChatSessionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """创建新的问答会话"""
    from uuid import UUID

    service = AIChatService(db)
    session = await service.create_session(
        project_id=UUID(data.project_id),
        session_type=data.session_type,
        title=data.title,
        user_id=str(user.id),
    )

    return {
        "session_id": str(session.id),
        "session_type": session.session_type,
        "title": session.title,
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }


@router.get("/sessions/{session_id}")
async def get_chat_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """获取会话详情"""
    from uuid import UUID

    service = AIChatService(db)
    session = await service.get_session(UUID(session_id))

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    messages = await service.get_session_messages(session.id)

    return {
        "session_id": str(session.id),
        "session_type": session.session_type,
        "title": session.title,
        "total_messages": session.total_messages,
        "total_tokens": session.total_tokens,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        "messages": [
            {
                "message_id": str(m.id),
                "role": m.role,
                "content": m.content,
                "token_count": m.token_count,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.get("/sessions")
async def list_chat_sessions(
    project_id: str,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """列出项目的问答会话"""
    from uuid import UUID

    service = AIChatService(db)
    sessions = await service.list_sessions(
        project_id=UUID(project_id),
        skip=skip,
        limit=limit,
    )

    return [
        {
            "session_id": str(s.id),
            "session_type": s.session_type,
            "title": s.title,
            "total_messages": s.total_messages,
            "total_tokens": s.total_tokens,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in sessions
    ]


@router.delete("/sessions/{session_id}")
async def delete_chat_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """删除会话"""
    from uuid import UUID

    service = AIChatService(db)
    success = await service.delete_session(UUID(session_id))

    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")

    return {"status": "deleted", "session_id": session_id}


# ============ 消息发送 ============


@router.post("/message")
async def send_message(
    request: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """发送消息（非流式）"""
    from uuid import UUID

    service = AIChatService(db)

    result = await service.chat(
        session_id=UUID(request.session_id),
        user_message=request.message,
        use_rag=request.use_rag,
        stream=False,
    )

    return result


@router.post("/message/stream")
async def send_message_stream(
    request: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    发送消息（流式输出）

    使用 SSE 协议返回流式响应。
    """
    from uuid import UUID

    async def event_generator() -> AsyncGenerator[str, None]:
        service = AIChatService(db)
        full_content = []
        session_id = UUID(request.session_id)

        try:
            async for chunk in service.chat_stream(
                session_id=session_id,
                user_message=request.message,
                use_rag=request.use_rag,
            ):
                full_content.append(chunk)
                yield f"data: {json.dumps({'delta': chunk}, ensure_ascii=False)}\n\n"

            # 保存完整消息到数据库
            from app.models.ai_models import AIChatMessage
            full_text = "".join(full_content)
            msg = AIChatMessage(
                session_id=session_id,
                role="assistant",
                content=full_text,
                token_count=len(full_text) // 4,
            )
            db.add(msg)
            await db.commit()

            yield f"data: {json.dumps({'done': True, 'content': full_text}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.exception("Stream error")
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============ 知识库管理 ============


class KnowledgeDocAdd(BaseModel):
    """添加知识文档"""
    project_id: str
    content: str
    title: str
    source_type: str = "manual"
    source_id: Optional[str] = None
    tags: list[str] = []


@router.post("/knowledge")
async def add_knowledge_document(
    data: KnowledgeDocAdd,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """添加知识文档到向量库"""
    from uuid import UUID

    service = KnowledgeIndexService(db)

    result = await service.add_document(
        project_id=UUID(data.project_id),
        content=data.content,
        metadata={
            "title": data.title,
            "source_type": data.source_type,
            "source_id": data.source_id,
            "tags": data.tags,
            "user_id": str(user.id),
        },
    )

    return result


@router.get("/knowledge/search")
async def search_knowledge(
    project_id: str,
    query: str,
    top_k: int = 5,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """检索知识库"""
    from uuid import UUID

    service = KnowledgeIndexService(db)
    results = await service.search(
        project_id=UUID(project_id),
        query=query,
        top_k=top_k,
    )

    return results


@router.get("/knowledge")
async def list_knowledge_docs(
    project_id: str,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """列出知识库文档"""
    from uuid import UUID

    service = KnowledgeIndexService(db)
    docs = await service.get_knowledge_by_project(
        project_id=UUID(project_id),
        skip=skip,
        limit=limit,
    )

    return [
        {
            "knowledge_id": str(d.id),
            "doc_uuid": d.doc_uuid,
            "title": d.title,
            "source_type": d.source_type,
            "tags": d.tags.split(",") if d.tags else [],
            "chunk_count": d.chunk_count,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]


@router.delete("/knowledge/{knowledge_id}")
async def delete_knowledge_doc(
    knowledge_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """删除知识文档"""
    service = KnowledgeIndexService(db)
    knowledge = await service.get_knowledge_by_id(UUID(knowledge_id))

    if not knowledge:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 从 ChromaDB 删除
    await service.delete_document(knowledge.doc_uuid)

    # 从数据库删除
    await db.delete(knowledge)
    await db.commit()

    return {"status": "deleted", "knowledge_id": knowledge_id}


# ============================================================================
# 项目级 AI 对话端点
# ============================================================================


@project_router.post("/chat")
async def project_chat(
    project_id: UUID,
    request: ProjectChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    项目内发送消息（AI对话）

    工作上下文感知，支持追问、报告解读、异常分析。
    """
    service = NLCommandService(db)

    # 如果有 conversation_id，先尝试解析意图
    if request.conversation_id:
        # 解析意图
        intent = await service.parse_intent(
            text=request.message,
            user_id=str(user.id),
            project_id=project_id,
        )

        # 如果是系统操作，需要确认后执行
        if intent.get("requires_confirmation"):
            return {
                "success": True,
                "type": "intent",
                "intent": intent,
                "message": "请确认是否执行此操作",
                "conversation_id": request.conversation_id,
            }

        # 执行 AI 对话
        result = await service.chat(
            project_id=project_id,
            user_id=str(user.id),
            message=request.message,
            attachments=request.attachments,
        )
        result["conversation_id"] = request.conversation_id
        return result

    # 新对话：先解析意图
    intent = await service.parse_intent(
        text=request.message,
        user_id=str(user.id),
        project_id=project_id,
    )

    # 如果是系统操作，返回确认信息
    if intent.get("requires_confirmation"):
        return {
            "success": True,
            "type": "intent",
            "intent": intent,
            "message": "请确认是否执行此操作",
            "conversation_id": None,
        }

    # 执行 AI 对话
    result = await service.chat(
        project_id=project_id,
        user_id=str(user.id),
        message=request.message,
        attachments=request.attachments,
    )
    return result


@project_router.post("/chat/confirm")
async def project_chat_confirm(
    project_id: UUID,
    request: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    确认执行系统操作

    用户在确认卡片点击确认后调用此接口。
    """
    intent = request.get("intent", {})
    command_id = request.get("command_id")

    service = NLCommandService(db)

    # 执行命令
    result = await service.execute_command(
        intent=intent,
        user_id=str(user.id),
        project_id=project_id,
    )

    result["command_id"] = command_id
    return result


@project_router.post("/command/parse")
async def parse_command(
    project_id: UUID,
    request: ProjectCommandParseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    解析自然语言命令

    将用户的自然语言命令转换为平台的结构化操作指令。
    """
    service = NLCommandService(db)

    intent = await service.parse_intent(
        text=request.text,
        user_id=str(user.id),
        project_id=project_id,
    )

    return {
        "success": True,
        "intent": intent,
    }


@project_router.get("/history")
async def get_conversation_history(
    project_id: UUID,
    conversation_id: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    获取对话历史

    如果提供 conversation_id，返回该会话的历史消息。
    否则返回项目的所有会话列表。
    """
    service = AIChatService(db)

    if conversation_id:
        # 获取特定会话的消息
        messages = await service.get_conversation_history(
            project_id=project_id,
            conversation_id=UUID(conversation_id),
            limit=limit,
        )
        return {
            "conversation_id": conversation_id,
            "messages": [
                {
                    "role": m.get("role"),
                    "content": m.get("content"),
                    "created_at": m.get("created_at"),
                }
                for m in messages
            ],
        }
    else:
        # 获取会话列表
        sessions = await service.list_sessions(
            project_id=project_id,
            skip=0,
            limit=limit,
        )
        return {
            "sessions": [
                {
                    "conversation_id": str(s.id),
                    "title": s.title,
                    "total_messages": s.total_messages,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                }
                for s in sessions
            ],
        }


@project_router.delete("/history/{conv_id}")
async def delete_conversation(
    project_id: UUID,
    conv_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    删除对话会话
    """
    service = AIChatService(db)
    success = await service.delete_session(UUID(conv_id))

    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")

    return {"status": "deleted", "conversation_id": conv_id}


@project_router.post("/file-analysis")
async def analyze_file(
    project_id: UUID,
    request: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    文件智能分析

    检测文件类型并路由到对应的分析服务：
    - 合同 → 合同分析服务
    - Excel → 报表分析
    - 银行流水 → 流水分析
    - 扫描件 → OCR识别
    """
    file_path = request.get("file_path")

    if not file_path:
        raise HTTPException(status_code=400, detail="缺少 file_path 参数")

    service = NLCommandService(db)
    result = await service.analyze_file(
        file_path=file_path,
        project_id=project_id,
    )

    return result


@project_router.post("/folder-analysis")
async def analyze_folder(
    project_id: UUID,
    request: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    文件夹批量分析

    遍历文件 → 分类统计 → 生成资料清单 → 标注缺失 → 与PBC清单比对
    """
    folder_path = request.get("folder_path")

    if not folder_path:
        raise HTTPException(status_code=400, detail="缺少 folder_path 参数")

    service = NLCommandService(db)
    result = await service.analyze_folder(
        folder_path=folder_path,
        project_id=project_id,
        user_id=str(user.id),
    )

    return result
