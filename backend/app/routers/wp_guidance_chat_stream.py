"""底稿 AI 对话的 SSE 流式生成器。

从 :mod:`wp_guidance_chat` 抽出的伴生模块：端点只负责鉴权与 prompt 组装，本模块
负责自建 session、RAG 降级、历史裁剪与「客户端断开也要持久化部分响应」的收尾。
路由注册仍留在原 router，不改变任何对外路径。
"""
from __future__ import annotations

import json
import logging
from typing import AsyncGenerator
from uuid import UUID

from app.models.core import User

logger = logging.getLogger(__name__)

_MAX_HISTORY_ROUNDS = 20  # 20 轮 = 40 条消息（user + assistant）


async def _stream_wp_chat(
    wp_id: str,
    query: str,
    system_prompt: str,
    user: User,
    project_id: UUID,
    wp_code: str = "",
) -> AsyncGenerator[str, None]:
    """SSE streaming 生成器：构建 messages → ai_service streaming → 收集回复 → 持久化

    ⚠️ 自建独立 session：FastAPI 在端点 return StreamingResponse 时即关闭 get_db
    的请求级 session，而本生成器在 response 返回后才被 ASGI 消费执行。

    客户端断开时 try/finally 确保部分响应也被持久化到 DB。
    """
    from app.core.database import async_session
    from app.services import doc_chat_persistence
    from app.services.ai_service import AIService
    from app.services.context_injector import ContextInjector

    async with async_session() as db:
        # ─── 检查 LLM 熔断器状态（提前 503 避免不必要的 RAG/history 查询）──
        try:
            ai_service = AIService(db)
            if hasattr(ai_service, '_breaker') and ai_service._breaker and ai_service._breaker.state.name == 'open':
                yield f"data: {json.dumps({'type': 'error', 'data': 'AI 服务暂不可用（熔断器已开启）'}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'data': {}}, ensure_ascii=False)}\n\n"
                return
        except Exception as e:
            logger.debug("检查 LLM 熔断器状态失败，继续正常流程: %s", e)

        # ─── RAG 知识库检索（降级：失败时继续无 RAG） ───────────────────
        citations: list[dict] = []
        rag_context = ""
        try:
            from app.services.knowledge_index_service import KnowledgeIndexService

            ks = KnowledgeIndexService(db)
            search_text = f"{wp_code} {query}"
            hits = await ks.semantic_search(
                project_id, search_text, scope="knowledge_doc", top_k=5
            )
            if hits:
                rag_parts: list[str] = []
                for hit in hits[:5]:
                    text = hit.get("content", "")[:1000]  # 500 tokens ≈ 1000 chars
                    source = hit.get("source_name", "")
                    rag_parts.append(f"[{source}] {text}")
                    citations.append({
                        "source_type": "knowledge_doc",
                        "source_id": hit.get("id", ""),
                        "source_name": source,
                    })
                rag_context = "\n\n相关知识库参考：\n" + "\n---\n".join(rag_parts)
        except Exception as e:
            logger.warning(f"RAG 检索失败 (降级继续): {e}")

        # 将 RAG 上下文追加到 system prompt
        if rag_context:
            system_prompt += rag_context

        # ─── 发送 citations 作为首个 SSE 事件 ─────────────────────────────
        if citations:
            yield f"data: {json.dumps({'type': 'citations', 'data': citations}, ensure_ascii=False)}\n\n"

        # 获取/创建会话（doc_type="workpaper", doc_id=wp_id）
        session = await doc_chat_persistence.get_or_create_session(
            db, "workpaper", wp_id, user.id, project_id
        )

        # 读取历史（限 20 轮 = 40 条消息）
        history = await doc_chat_persistence.get_history(
            db, "workpaper", wp_id, user.id, limit=_MAX_HISTORY_ROUNDS * 2
        )

        # 构建 LLM messages: [system] + history + [user query]
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]
        # 添加历史消息（最近 20 轮）
        for msg in history[-((_MAX_HISTORY_ROUNDS) * 2):]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        # 当前用户消息
        messages.append({"role": "user", "content": query})

        # 合并 system 消息（vLLM 约束）
        messages = ContextInjector.merge_system_messages(messages)

        # 记录用户消息到 DB + 提交
        await doc_chat_persistence.append_message(db, session, "user", query)
        await db.commit()

        # 流式调用 ai_service — try/finally 确保部分响应持久化
        full_response = ""
        response_saved = False

        try:
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
                logger.exception("workpaper_ai_chat streaming 失败")
                error_msg = "AI 服务暂不可用"
                if "熔断" in str(e) or "circuit" in str(e).lower():
                    error_msg = "AI 服务暂不可用（熔断器已开启）"
                yield f"data: {json.dumps({'type': 'error', 'data': error_msg}, ensure_ascii=False)}\n\n"

            # 记录助手回复到 DB + 提交（正常完成路径）
            if full_response:
                await doc_chat_persistence.append_message(db, session, "assistant", full_response)
            await db.commit()
            response_saved = True

            # 发送完成事件
            yield f"data: {json.dumps({'type': 'done', 'data': {}}, ensure_ascii=False)}\n\n"
        finally:
            # 确保部分响应也持久化（客户端断开时 generator 被 close）
            if not response_saved and full_response:
                try:
                    await doc_chat_persistence.append_message(db, session, "assistant", full_response)
                    await db.commit()
                except Exception as e:
                    logger.warning(f"部分响应持久化失败: {e}")
