"""文档级 AI 对话持久化服务（宿主适配层）

复用现成的 ``ai_chat_session`` / ``ai_chat_message`` 表，按宿主
``(host_type, host_id, user, project, year)`` 维度持久化对话历史。

## Task 3 后的分层（dsh-agent-panel-integration）

本模块只做**宿主参数 → 持久化原语**的适配，所有会话定位、并发约束、history
排序与元数据装配都下沉到 ``app.services.ai_chat.persistence``（Task 4+ 的
run 创建 API 与本模块共用同一套原语，不存在第二份实现）。

三处行为变化（对应 Requirements 4.10 / 4.11）：

1. **定位键**从 ``AIChatSession.context_summary`` 的 ``"{doc_type}:{doc_id}:{user_id}"``
   改为服务端规范化 ``session_key``（含 user/project/year/host type/host ID 五要素），
   并由部分唯一索引 ``uq_ai_chat_session_user_key`` 约束。``context_summary``
   仍写入旧格式定位串作为**可读**旁注，但不再是定位依据。
2. **并发创建**从"先查后建"改为 ``INSERT … ON CONFLICT``（Property 6）。
3. **history** 从"最早 N 条"改为"最近 N 条 + 外层正序"，并携带真实 message ID /
   status / run status / engine / model / tokens / latency / citations。

替代了原孤儿 ``AIChatService``（其 AIChatMessage 字段名 content/token_count
与模型实际字段 message_text/tokens_used 不符，接线即崩）。
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import AIChatMessage, AIChatSession
from app.services.ai_chat import persistence
from app.services.ai_chat.persistence import DEFAULT_HISTORY_LIMIT, ChatHistoryEntry

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_HISTORY_LIMIT",
    "ChatHistoryEntry",
    "get_or_create_session",
    "append_message",
    "get_history",
    "get_history_entries",
    "clear_history",
]


def _locator(doc_type: str, doc_id: str, user_id: UUID) -> str:
    """旧版可读定位串，写入 ``AIChatSession.context_summary`` 作为人工排查旁注。

    🔴 **不再**是会话定位依据 —— 定位权威是 ``session_key``（见
    ``persistence.build_session_key``）。V147 已按本格式把存量行回填出 session_key，
    故格式不得随意更改：改了会让"存量行的 key"与"运行时算出的 key"错位。
    """
    return f"{doc_type}:{doc_id}:{user_id}"


async def get_or_create_session(
    db: AsyncSession,
    doc_type: str,
    doc_id: str,
    user_id: UUID,
    project_id: UUID | None,
    audit_year: int | None = None,
) -> AIChatSession:
    """按五要素定位键原子 upsert 宿主会话（并发只产生一行，Property 6）。"""
    session, created = await persistence.upsert_session(
        db,
        user_id=user_id,
        project_id=project_id,
        audit_year=audit_year,
        host_type=doc_type,
        host_id=doc_id,
        title=f"{doc_type} 文档对话",
    )
    if created and not session.context_summary:
        session.context_summary = _locator(doc_type, doc_id, user_id)
        await db.flush()
    return session


async def append_message(
    db: AsyncSession,
    session: AIChatSession,
    role: str,
    text: str,
    **metadata,
) -> AIChatMessage:
    """追加一条消息（``metadata`` 透传 run_id / citations / model / tokens 等）。"""
    return await persistence.append_message(
        db, session, role=role, text=text, **metadata
    )


async def get_history_entries(
    db: AsyncSession,
    doc_type: str,
    doc_id: str,
    user_id: UUID,
    project_id: UUID | None = None,
    audit_year: int | None = None,
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> list[ChatHistoryEntry]:
    """读取最近 ``limit`` 条历史（时间正序，带真实元数据）。会话不存在返回空列表。"""
    session = await persistence.find_session(
        db,
        user_id=user_id,
        project_id=project_id,
        audit_year=audit_year,
        host_type=doc_type,
        host_id=doc_id,
    )
    if session is None:
        return []
    return await persistence.load_recent_history(
        db, session_id=session.id, limit=limit
    )


async def get_history(
    db: AsyncSession,
    doc_type: str,
    doc_id: str,
    user_id: UUID,
    project_id: UUID | None = None,
    audit_year: int | None = None,
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> list[dict]:
    """``get_history_entries`` 的 dict 形态（LLM messages 与 API 响应都用它）。

    Req 4.10：返回的是**最近** N 条并按时间正序，每条带真实 message ID、
    status、run status、engine、model、token usage、latency 与 citations。
    """
    entries = await get_history_entries(
        db,
        doc_type,
        doc_id,
        user_id,
        project_id=project_id,
        audit_year=audit_year,
        limit=limit,
    )
    return [e.as_dict() for e in entries]


async def clear_history(
    db: AsyncSession,
    doc_type: str,
    doc_id: str,
    user_id: UUID,
    project_id: UUID | None = None,
    audit_year: int | None = None,
) -> bool:
    """清除宿主会话及其全部消息。会话不存在返回 False。

    ``ai_chat_runs`` / ``ai_chat_tool_calls`` / ``ai_chat_action_receipts`` 随会话
    ``ON DELETE CASCADE``；``ai_chat_attachments`` 是 **RESTRICT**（Req 7.9：磁盘
    文件删除失败不得先丢 metadata）⇒ 会话若仍挂着未清理的附件，本删除会被数据库
    拒绝。附件清理流程与状态展示由 Task 16/17 承担，本函数不代劳、也不绕过约束。
    """
    session = await persistence.find_session(
        db,
        user_id=user_id,
        project_id=project_id,
        audit_year=audit_year,
        host_type=doc_type,
        host_id=doc_id,
    )
    if session is None:
        return False

    await db.execute(
        sa.delete(AIChatMessage).where(AIChatMessage.session_id == session.id)
    )
    await db.execute(
        sa.delete(AIChatSession).where(AIChatSession.id == session.id)
    )
    await db.flush()
    return True
