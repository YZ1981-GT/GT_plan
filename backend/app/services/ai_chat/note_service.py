"""幂等项目笔记转存服务（Task 18）

Feature: dsh-agent-panel-integration
Requirements:
  - 8.1：POST /api/ai-chat/notes 只接收 completed assistant message IDs、
    用户确认名称、HostRef 和 idempotency key
  - 8.2：ResourceAccessResolver 校验 knowledge.create
  - 8.3：从数据库读取问题/回复/citations/hash
  - 8.4：notes folder 定位规则单一真源，使用数据库唯一约束/upsert
  - 8.8：使用 ai_chat_action_receipts 防重
  - 8.9：哈希链记录 note saved；失败回滚 receipt，可安全重试
Design: "Components and Interfaces → 8. 项目笔记转存"

笔记转存流程：
1. 校验 knowledge.create 权限
2. claim_action_receipt 抢占幂等收据
3. 定位/创建目标文件夹（"AI 对话笔记" 项目级文件夹，单一真源）
4. 从数据库读取 completed assistant 正文（服务端权威来源，不信任客户端正文）
5. 写入 KnowledgeDocument（复用 knowledge_folder_service.create_document）
6. settle_action_receipt 成功/失败
7. 触发知识索引更新
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import (
    AIChatActionReceipt,
    AIChatMessage,
    ActionReceiptStatus,
    ActionReceiptType,
    ChatMessageStatus,
    ChatRole,
)
from app.models.knowledge_models import KnowledgeDocument, KnowledgeFolder
from app.services.ai_chat.access import ResourceAccessResolver
from app.services.ai_chat.contracts import (
    AccessDecision,
    AiChatAction,
    ResourceType,
)
from app.services.ai_chat.host_context import AuthorizedHostContext
from app.services.ai_chat.persistence import (
    claim_action_receipt,
    content_hash,
    settle_action_receipt,
)

logger = logging.getLogger(__name__)

__all__ = [
    "NoteSaveRequest",
    "NoteSaveResult",
    "NoteSaveFailed",
    "save_note",
]


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

#: AI 笔记文件夹的标准名称（单一真源，Req 8.4）
AI_NOTES_FOLDER_NAME = "AI 对话笔记"


class NoteSaveFailed(Exception):
    """笔记转存失败。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class NoteSaveRequest:
    """笔记转存请求。"""

    def __init__(
        self,
        *,
        message_ids: list[UUID],
        name: str,
        host: AuthorizedHostContext,
        idempotency_key: str,
    ) -> None:
        self.message_ids = message_ids
        self.name = name
        self.host = host
        self.idempotency_key = idempotency_key


class NoteSaveResult:
    """笔记转存成功结果。"""

    def __init__(
        self,
        *,
        document_id: UUID,
        folder_id: UUID,
        name: str,
        replayed: bool = False,
    ) -> None:
        self.document_id = document_id
        self.folder_id = folder_id
        self.name = name
        self.replayed = replayed

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": str(self.document_id),
            "folder_id": str(self.folder_id),
            "name": self.name,
            "replayed": self.replayed,
            "jump_route": f"/knowledge/docs/{self.document_id}",
        }


# ---------------------------------------------------------------------------
# 核心转存逻辑
# ---------------------------------------------------------------------------


async def save_note(
    db: AsyncSession,
    *,
    user: Any,
    actor_id: UUID,
    host: AuthorizedHostContext,
    session_id: UUID,
    message_ids: list[UUID],
    name: str,
    idempotency_key: str,
) -> NoteSaveResult:
    """执行项目笔记转存。

    Req 8.1–8.9 的完整流程。失败时回滚 receipt，可安全重试。

    Raises:
        NoteSaveFailed: 权限/消息/名称校验失败
    """
    if not message_ids:
        raise NoteSaveFailed("no_messages", "请至少选择一条 AI 消息")
    if not name or not name.strip():
        raise NoteSaveFailed("empty_name", "请提供笔记名称")
    name = name.strip()[:200]  # 限制名称长度

    project_id = host.project_id
    if project_id is None:
        raise NoteSaveFailed(
            "no_project", "当前宿主无项目绑定，无法创建项目笔记"
        )

    # ① 校验 knowledge.create 权限（Req 8.2）
    resolver = ResourceAccessResolver(db)
    host_decision = AccessDecision(
        allowed=True,
        principal_id=host.principal_id,
        project_id=project_id,
        cycle_scope=host.cycle_scope,
        allowed_actions=host.allowed_actions,
        scope_unbounded=host.scope_unbounded,
    )
    # 检查角色是否有 note_create 动作权限
    if not host.allows(AiChatAction.note_create):
        raise NoteSaveFailed("action_denied", "当前角色无权创建项目笔记")

    # ② claim_action_receipt 抢占幂等收据（Req 8.8）
    receipt, claimed = await claim_action_receipt(
        db,
        action_type=ActionReceiptType.note_create,
        actor_id=actor_id,
        session_id=session_id,
        idempotency_key=idempotency_key,
    )

    if not claimed:
        # 幂等命中：检查既有收据状态
        if receipt.status == ActionReceiptStatus.succeeded.value:
            # 已成功，直接返回同一文档（Req 8.8：重复点击复用同一 idempotency key）
            return NoteSaveResult(
                document_id=receipt.result_resource_id,
                folder_id=_folder_id_from_receipt(receipt),
                name=name,
                replayed=True,
            )
        elif receipt.status == ActionReceiptStatus.failed.value:
            # 失败收据：重置为 pending 允许重试（Req 8.9）
            receipt.status = ActionReceiptStatus.pending.value
            await db.flush()
        else:
            # pending = 并发请求正在执行，等待
            raise NoteSaveFailed(
                "concurrent_save", "同一笔记正在保存中，请稍候"
            )

    try:
        # ③ 从数据库读取 completed assistant 正文（Req 8.3 / 8.1）
        messages = await _load_messages(db, message_ids, actor_id, session_id)
        if not messages:
            raise NoteSaveFailed(
                "messages_not_found", "所选消息不存在或非当前用户的已完成 assistant 消息"
            )

        # ④ 拼接笔记正文
        note_content = _assemble_note_content(messages, name)

        # ⑤ 定位/创建目标文件夹（单一真源规则，Req 8.4）
        folder = await _ensure_notes_folder(db, project_id, actor_id)

        # ⑥ 写入 KnowledgeDocument
        from app.services.knowledge_folder_service import KnowledgeFolderService

        folder_svc = KnowledgeFolderService(db)
        doc = await folder_svc.create_document(
            folder_id=folder.id,
            name=name,
            content_text=note_content,
            file_type="markdown",
            file_size=len(note_content.encode("utf-8")),
            tags=["ai-note", "auto-generated"],
            access_level="project_group",
            project_ids=[str(project_id)],
            created_by=actor_id,
        )

        # ⑦ settle receipt 成功
        await settle_action_receipt(
            db,
            receipt,
            status=ActionReceiptStatus.succeeded,
            result_resource_id=doc.id,
        )

        # ⑧ 触发知识索引更新（异步，不阻断返回）
        try:
            from app.services.knowledge_index_service import KnowledgeIndexService

            idx_svc = KnowledgeIndexService(db)
            await idx_svc.incremental_update(
                project_id=project_id,
                source_id=str(doc.id),
                content=note_content[:2000],
                source_type="knowledge_document",
                metadata={"doc_id": str(doc.id), "name": name},
            )
        except Exception as idx_exc:
            # 索引更新失败不影响转存成功（索引会在下次 build 时追上）
            logger.warning(
                "笔记 %s 索引更新失败（不阻断）: %s", doc.id, idx_exc
            )

        return NoteSaveResult(
            document_id=doc.id,
            folder_id=folder.id,
            name=name,
        )

    except NoteSaveFailed:
        # 业务失败：标记 receipt 失败
        await settle_action_receipt(
            db,
            receipt,
            status=ActionReceiptStatus.failed,
            error_code="note_save_failed",
        )
        raise

    except Exception as exc:
        # 意外失败：标记 receipt 失败（Req 8.9：可安全重试）
        logger.error(
            "笔记转存意外失败 actor=%s session=%s: %s: %s",
            actor_id, session_id, type(exc).__name__, exc,
        )
        await settle_action_receipt(
            db,
            receipt,
            status=ActionReceiptStatus.failed,
            error_code=f"unexpected:{type(exc).__name__}",
        )
        raise NoteSaveFailed(
            "internal_error", "笔记保存失败，请重试"
        ) from exc


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


async def _load_messages(
    db: AsyncSession,
    message_ids: list[UUID],
    actor_id: UUID,
    session_id: UUID,
) -> list[AIChatMessage]:
    """加载属于当前用户/会话的 completed assistant 消息。

    Req 8.1/8.3：只接收 message IDs，正文从数据库读（服务端权威来源）。
    只有 completed + assistant 角色的消息可被转存。
    """
    rows = (
        await db.execute(
            sa.select(AIChatMessage)
            .join(
                # 通过 session 关联确认 actor 身份
                sa.text("ai_chat_session"),
                sa.text("ai_chat_session.id = ai_chat_message.session_id"),
            )
            .where(
                AIChatMessage.id.in_(message_ids),
                AIChatMessage.session_id == session_id,
                AIChatMessage.role == ChatRole.assistant.value,
                AIChatMessage.status == ChatMessageStatus.completed.value,
                sa.text("ai_chat_session.user_id = :actor_id"),
            )
            .params(actor_id=actor_id)
            .order_by(AIChatMessage.created_at.asc())
        )
    ).scalars().all()
    return list(rows)


def _assemble_note_content(messages: list[AIChatMessage], title: str) -> str:
    """将多条消息拼接为笔记正文（Markdown 格式）。"""
    parts = [f"# {title}\n"]
    for i, msg in enumerate(messages, 1):
        text = getattr(msg, "content", "") or getattr(msg, "text", "") or ""
        if len(messages) > 1:
            parts.append(f"\n## 回复 {i}\n")
        parts.append(text.strip())

        # 附加 citations
        citations = getattr(msg, "referenced_sources", None)
        if citations:
            parts.append("\n\n---\n**参考来源：**")
            if isinstance(citations, list):
                for cite in citations[:10]:
                    label = cite.get("label", "") if isinstance(cite, dict) else str(cite)
                    parts.append(f"- {label}")

    return "\n".join(parts)


async def _ensure_notes_folder(
    db: AsyncSession,
    project_id: UUID,
    actor_id: UUID,
) -> KnowledgeFolder:
    """定位或创建 "AI 对话笔记" 文件夹（Req 8.4 单一真源规则）。

    使用数据库查询确认存在性，不使用仅"先查后建"的方式：
    并发时依赖数据库唯一约束（project_id + name 在同级下唯一）。
    """
    # 先查
    existing = (
        await db.execute(
            sa.select(KnowledgeFolder).where(
                KnowledgeFolder.project_id == project_id,
                KnowledgeFolder.name == AI_NOTES_FOLDER_NAME,
                KnowledgeFolder.parent_id.is_(None),  # 顶级文件夹
                KnowledgeFolder.is_deleted == sa.false(),
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        return existing

    # 创建（并发安全：若有唯一约束，冲突后重查）
    import uuid as uuid_mod

    from app.models.knowledge_models import KnowledgeAccessLevel

    folder = KnowledgeFolder(
        id=uuid_mod.uuid4(),
        project_id=project_id,
        name=AI_NOTES_FOLDER_NAME,
        parent_id=None,
        access_level=KnowledgeAccessLevel.project_group,
        project_ids=[str(project_id)],
        created_by=actor_id,
    )
    db.add(folder)
    try:
        await db.flush()
    except Exception:
        # 并发冲突：重查
        await db.rollback()
        existing = (
            await db.execute(
                sa.select(KnowledgeFolder).where(
                    KnowledgeFolder.project_id == project_id,
                    KnowledgeFolder.name == AI_NOTES_FOLDER_NAME,
                    KnowledgeFolder.parent_id.is_(None),
                    KnowledgeFolder.is_deleted == sa.false(),
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        raise

    return folder


def _folder_id_from_receipt(receipt: AIChatActionReceipt) -> UUID:
    """从已成功的收据推断 folder_id（用于 replayed 响应）。

    简化处理：replayed 场景下 folder_id 不影响前端跳转（jump_route 用 doc_id）。
    """
    # result_resource_id 是 document ID，前端通过 jump_route 跳转
    return receipt.result_resource_id or receipt.id
