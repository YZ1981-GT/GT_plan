"""AI 智能问答服务

基于 RAG（检索增强生成）模式提供审计领域的智能问答。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import AIChatSession, AIChatMessage
from app.services.knowledge_index_service import KnowledgeIndexService
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)


class AIChatService:
    """AI 智能问答服务"""

    SYSTEM_PROMPT = """你是一名专业的审计顾问，熟悉中国会计准则、审计准则和内部控制规范。请根据提供的上下文信息，准确、专业地回答用户的问题。

回答要求：
1. 专业、准确、客观
2. 如涉及具体法规，请注明依据
3. 如上下文不足以回答，请明确说明
4. 保持审计人员的职业谨慎态度
"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.knowledge_service = KnowledgeIndexService(db)
        self.ai_service = AIService(db)

    async def create_session(
        self,
        project_id: UUID,
        session_type: str = "general",
        title: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> AIChatSession:
        """创建问答会话"""
        session = AIChatSession(
            project_id=project_id,
            session_type=session_type,
            title=title or f"会话_{datetime.utcnow().strftime('%Y%m%d%H%M')}",
            user_id=user_id,
            total_messages=0,
            total_tokens=0,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def chat(
        self,
        session_id: UUID,
        user_message: str,
        use_rag: bool = True,
        stream: bool = True,
    ) -> dict[str, Any]:
        """
        处理用户消息并生成回复

        Args:
            session_id: 会话 ID
            user_message: 用户消息
            use_rag: 是否使用 RAG 检索增强
            stream: 是否流式输出

        Returns:
            回复内容和元数据
        """
        # 获取会话
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # 保存用户消息
        user_msg = AIChatMessage(
            session_id=session_id,
            role="user",
            content=user_message,
            token_count=len(user_message) // 4,  # 估算
        )
        self.db.add(user_msg)
        session.total_messages += 1
        await self.db.flush()

        # RAG 检索上下文
        context_text = ""
        if use_rag:
            try:
                results = await self.knowledge_service.search(
                    project_id=session.project_id,
                    query=user_message,
                    top_k=3,
                )
                if results:
                    context_parts = []
                    for r in results:
                        context_parts.append(
                            f"【{r['metadata'].get('title', '文档')}】\n{r['content'][:500]}"
                        )
                    context_text = "\n\n".join(context_parts)
            except Exception as e:
                logger.warning(f"RAG search failed: {e}")

        # 构建消息列表
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]

        # 添加上下文
        if context_text:
            messages.append({
                "role": "system",
                "content": f"【参考上下文】\n{context_text}\n\n请基于以上上下文回答问题。",
            })

        # 添加历史消息（限制最近 10 轮）
        history = await self.get_session_messages(session_id, limit=20)
        for msg in history[-10:]:
            if msg.role != "system":
                messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        # 添加当前用户消息
        messages.append({"role": "user", "content": user_message})

        # 调用 AI
        if stream:
            # 流式响应
            return {
                "session_id": str(session_id),
                "use_rag": bool(context_text),
                "stream": True,
                "context_docs": context_text[:200] if context_text else None,
            }
        else:
            # 非流式响应
            response = await self.ai_service.chat(messages=messages, model="audit")

            # 保存助手消息
            assistant_msg = AIChatMessage(
                session_id=session_id,
                role="assistant",
                content=response.get("content", ""),
                token_count=response.get("usage", {}).get("total_tokens", 0),
            )
            self.db.add(assistant_msg)
            session.total_messages += 1
            session.total_tokens += assistant_msg.token_count
            await self.db.commit()

            return {
                "session_id": str(session_id),
                "message_id": str(assistant_msg.id),
                "content": response.get("content", ""),
                "model": response.get("model"),
                "use_rag": bool(context_text),
                "context_docs": context_text[:200] if context_text else None,
            }

    async def chat_stream(
        self,
        session_id: UUID,
        user_message: str,
        use_rag: bool = True,
    ) -> AsyncGenerator[str, None]:
        """
        流式生成回复

        Yields:
            文本片段
        """
        import asyncio

        # 获取会话
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # RAG 检索
        context_text = ""
        if use_rag:
            try:
                results = await self.knowledge_service.search(
                    project_id=session.project_id,
                    query=user_message,
                    top_k=3,
                )
                if results:
                    context_parts = []
                    for r in results:
                        context_parts.append(
                            f"【{r['metadata'].get('title', '文档')}】\n{r['content'][:500]}"
                        )
                    context_text = "\n\n".join(context_parts)
            except Exception as e:
                logger.warning(f"RAG search failed: {e}")

        # 构建消息
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        if context_text:
            messages.append({
                "role": "system",
                "content": f"【参考上下文】\n{context_text}",
            })

        history = await self.get_session_messages(session_id, limit=10)
        for msg in history:
            if msg.role != "system":
                messages.append({"role": msg.role, "content": msg.content})

        messages.append({"role": "user", "content": user_message})

        # 保存用户消息
        user_msg = AIChatMessage(
            session_id=session_id,
            role="user",
            content=user_message,
            token_count=len(user_message) // 4,
        )
        self.db.add(user_msg)
        session.total_messages += 1
        await self.db.flush()

        # 流式调用
        try:
            async for chunk in self.ai_service.chat_stream(messages=messages):
                yield chunk
        except Exception as e:
            logger.exception(f"Chat stream failed")
            yield f"\n\n[错误: {e}]"

        # 保存助手消息（完整内容由调用方收集）

    async def get_session(self, session_id: UUID) -> Optional[AIChatSession]:
        """获取会话"""
        result = await self.db.execute(
            select(AIChatSession).where(AIChatSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_session_messages(
        self,
        session_id: UUID,
        limit: int = 50,
    ) -> list[AIChatMessage]:
        """获取会话消息"""
        result = await self.db.execute(
            select(AIChatMessage)
            .where(AIChatMessage.session_id == session_id)
            .order_by(AIChatMessage.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_sessions(
        self,
        project_id: UUID,
        skip: int = 0,
        limit: int = 20,
    ) -> list[AIChatSession]:
        """列出项目的问答会话"""
        result = await self.db.execute(
            select(AIChatSession)
            .where(AIChatSession.project_id == project_id)
            .order_by(AIChatSession.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete_session(self, session_id: UUID) -> bool:
        """删除会话及其消息"""
        session = await self.get_session(session_id)
        if not session:
            return False

        # 删除消息
        from sqlalchemy import delete
        await self.db.execute(
            delete(AIChatMessage).where(AIChatMessage.session_id == session_id)
        )
        await self.db.delete(session)
        await self.db.commit()
        return True
