"""文档级 AI 对话持久化服务

复用现成的 ``ai_chat_session`` / ``ai_chat_message`` 表，按
``(doc_type, doc_id, user_id)`` 维度持久化文档级对话历史，替代 doc_ai_chat
原先的内存字典 ``_chat_history``（重启即丢的缺陷）。

定位键：``AIChatSession.context_summary`` 存 ``"{doc_type}:{doc_id}:{user_id}"``
（现成 Text 列，避免新增列引入 schema 漂移）。

替代了原孤儿 ``AIChatService``（其 AIChatMessage 字段名 content/token_count
与模型实际字段 message_text/tokens_used 不符，接线即崩——本 service 用正确字段）。
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import (
    AIChatMessage,
    AIChatSession,
    ChatRole,
    SessionType,
)

logger = logging.getLogger(__name__)


def _locator(doc_type: str, doc_id: str, user_id: UUID) -> str:
    """文档级会话定位键，存入 AIChatSession.context_summary。"""
    return f"{doc_type}:{doc_id}:{user_id}"


async def get_or_create_session(
    db: AsyncSession,
    doc_type: str,
    doc_id: str,
    user_id: UUID,
    project_id: UUID,
) -> AIChatSession:
    """按 (doc_type, doc_id, user_id) 获取或创建文档级会话。"""
    locator = _locator(doc_type, doc_id, user_id)
    result = await db.execute(
        sa.select(AIChatSession).where(
            AIChatSession.context_summary == locator
        )
    )
    session = result.scalar_one_or_none()
    if session is not None:
        return session

    session = AIChatSession(
        project_id=project_id,
        session_type=SessionType.general,
        title=f"{doc_type} 文档对话",
        user_id=user_id,
        context_summary=locator,
        total_messages=0,
        total_tokens=0,
    )
    db.add(session)
    await db.flush()
    return session


async def append_message(
    db: AsyncSession,
    session: AIChatSession,
    role: str,
    text: str,
) -> None:
    """追加一条消息到会话（用正确字段 message_text，非孤儿 service 的 content）。"""
    msg = AIChatMessage(
        session_id=session.id,
        role=ChatRole(role),
        message_text=text,
    )
    db.add(msg)
    session.total_messages = (session.total_messages or 0) + 1
    await db.flush()


async def get_history(
    db: AsyncSession,
    doc_type: str,
    doc_id: str,
    user_id: UUID,
    limit: int = 50,
) -> list[dict]:
    """读取文档级对话历史（按时间升序）。会话不存在返回空列表。"""
    locator = _locator(doc_type, doc_id, user_id)
    session_result = await db.execute(
        sa.select(AIChatSession.id).where(
            AIChatSession.context_summary == locator
        )
    )
    session_id = session_result.scalar_one_or_none()
    if session_id is None:
        return []

    rows = await db.execute(
        sa.select(AIChatMessage.role, AIChatMessage.message_text)
        .where(AIChatMessage.session_id == session_id)
        .order_by(AIChatMessage.created_at)
        .limit(limit)
    )
    return [
        {"role": r[0].value if hasattr(r[0], "value") else r[0], "content": r[1]}
        for r in rows.all()
    ]


async def clear_history(
    db: AsyncSession,
    doc_type: str,
    doc_id: str,
    user_id: UUID,
) -> bool:
    """清除文档级会话及其全部消息。会话不存在返回 False。"""
    locator = _locator(doc_type, doc_id, user_id)
    session_result = await db.execute(
        sa.select(AIChatSession.id).where(
            AIChatSession.context_summary == locator
        )
    )
    session_id = session_result.scalar_one_or_none()
    if session_id is None:
        return False

    await db.execute(
        sa.delete(AIChatMessage).where(AIChatMessage.session_id == session_id)
    )
    await db.execute(
        sa.delete(AIChatSession).where(AIChatSession.id == session_id)
    )
    await db.flush()
    return True
