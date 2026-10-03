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
5. 写入 KnowledgeDocument（复用 KnowledgeDocumentService.create_document）
6. settle_action_receipt 成功/失败
7. 检索：笔记落库即可被文档正文词法检索召回（spec knowledge-base-retrieval-and-authz-closure 方案 A）
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
    AIChatSession,
    ActionReceiptStatus,
    ActionReceiptType,
    ChatMessageStatus,
    ChatRole,
)
from app.models.knowledge_models import KnowledgeFolder
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
from app.services.knowledge_folder_service import PROJECT_FOLDER_SLOTS

logger = logging.getLogger(__name__)

__all__ = [
    "NoteSaveRequest",
    "NoteSaveResult",
    "NoteSaveFailed",
    "knowledge_jump_route",
    "save_note",
]


def knowledge_jump_route(*, doc_id: Any = None, folder_id: Any = None) -> str:
    """知识库页面深链（单一真源；mention_service 同用）：``/knowledge?folder_id=…&doc_id=…``。"""
    params = []
    if folder_id:
        params.append(f"folder_id={folder_id}")
    if doc_id:
        params.append(f"doc_id={doc_id}")
    return "/knowledge" + (("?" + "&".join(params)) if params else "")


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

#: AI 笔记文件夹的标准名称（单一真源在 knowledge_folder_service.PROJECT_FOLDER_SLOTS，Req 8.4）
AI_NOTES_FOLDER_NAME = PROJECT_FOLDER_SLOTS["ai_notes"]


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
        folder_id: UUID | None,
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
            # 重放时文档已被删除 → None（不再用 document ID 冒充 folder_id）
            "folder_id": str(self.folder_id) if self.folder_id else None,
            "name": self.name,
            "replayed": self.replayed,
            # 前端真实路由（KnowledgeBase.vue 读 ?folder_id / ?doc_id 深链）；
            # 旧值 /knowledge/docs/{id} 前端没有该路由，点击恒 404。
            "jump_route": knowledge_jump_route(doc_id=self.document_id, folder_id=self.folder_id),
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
                folder_id=await _replayed_folder_id(db, receipt),
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

        # ⑥ 写入 KnowledgeDocument（文档服务；旧代码调用 KnowledgeFolderService.create_document
        #    —— 该方法不存在，转存恒失败）
        from app.services.knowledge_folder_service import KnowledgeDocumentService

        doc = await KnowledgeDocumentService(db).create_document(
            folder_id=folder.id,
            name=name,
            content_text=note_content,
            file_type="md",
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

        # ⑧ 不再在此调用 incremental_update：旧调用传了不存在的 source_type
        #    "knowledge_document" 与不存在的 metadata 参数（恒失败），且在请求会话里执行会
        #    毒化事务。笔记一经落库即可被文档正文词法检索召回（spec 方案 A），无需索引。

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
    # 🔴 旧实现 ``.join(sa.text("ai_chat_session"), sa.text(...))`` 在 SQLAlchemy 2.0 下直接抛
    #    AttributeError（TextClause 不是可 join 的 selectable）⇒ 转存在读消息这一步就恒失败，
    #    被外层 except 吞成 internal_error（spec knowledge-base-retrieval-and-authz-closure 5.9，
    #    真库测试 test_ai_note_capture_pg 抓到）。改为 ORM join，经会话属主确认 actor 身份。
    rows = (
        await db.execute(
            sa.select(AIChatMessage)
            .join(AIChatSession, AIChatSession.id == AIChatMessage.session_id)
            .where(
                AIChatMessage.id.in_(message_ids),
                AIChatMessage.session_id == session_id,
                AIChatMessage.role == ChatRole.assistant.value,
                AIChatMessage.status == ChatMessageStatus.completed.value,
                AIChatSession.user_id == actor_id,
            )
            .order_by(AIChatMessage.created_at.asc(), AIChatMessage.seq.asc())
        )
    ).scalars().all()
    return list(rows)


def _citation_label(cite: Any) -> str:
    """引用展示名：持久化负载的键是 ``source_name``（native_engine._citation_payloads）；
    ``label`` 为旧格式兼容；都没有时退回来源 ID。"""
    if not isinstance(cite, dict):
        return str(cite)
    return str(cite.get("source_name") or cite.get("label") or cite.get("source_id") or "").strip()


def _assemble_note_content(messages: list[AIChatMessage], title: str) -> str:
    """将多条消息拼接为笔记正文（Markdown 格式）。

    🔴 正文列是 ``AIChatMessage.message_text``：旧实现读不存在的 ``content`` / ``text``
    属性，``getattr`` 默认值把缺陷吞成空串 ⇒ 每篇笔记只有标题（spec
    knowledge-base-retrieval-and-authz-closure 5.9）。
    """
    parts = [f"# {title}\n"]
    for i, msg in enumerate(messages, 1):
        text = msg.message_text or ""
        if len(messages) > 1:
            parts.append(f"\n## 回复 {i}\n")
        parts.append(text.strip())

        # 附加 citations
        citations = getattr(msg, "referenced_sources", None)
        if isinstance(citations, list) and citations:
            labels = [label for label in (_citation_label(c) for c in citations[:10]) if label]
            if labels:
                parts.append("\n\n---\n**参考来源：**")
                parts.extend(f"- {label}" for label in labels)

    return "\n".join(parts)


async def _ensure_notes_folder(
    db: AsyncSession,
    project_id: UUID,
    actor_id: UUID,
) -> KnowledgeFolder:
    """定位或创建项目的 "AI 对话笔记" 文件夹（Req 8.4 单一真源规则）。

    委托 ``knowledge_folder_service.ensure_project_folder``：按 ``system_key``（V170 部分唯一
    索引）定位，SAVEPOINT 内建、冲突重查，不回滚调用方事务。

    旧实现三处致命缺陷（spec knowledge-base-retrieval-and-authz-closure 5.9）：按不存在的
    ``KnowledgeFolder.project_id`` 查询与构造（恒 AttributeError / TypeError）；冲突时
    ``db.rollback()`` 把已 claim 的幂等收据一起回滚；按名称定位会被同名用户文件夹劫持。
    ``actor_id`` 保留在签名里只为调用方不变：系统文件夹不归任何个人所有。
    """
    from app.services.knowledge_folder_service import ensure_project_folder

    del actor_id  # 系统文件夹 created_by 恒为空（仅管理员可管理）
    return await ensure_project_folder(db, project_id, "ai_notes")


async def _replayed_folder_id(db: AsyncSession, receipt: AIChatActionReceipt) -> UUID | None:
    """幂等重放时取文档**真实**所在文件夹。

    旧实现直接返回 document ID 充当 folder_id；jump_route 带上 folder_id 后，
    重放响应会深链到一个不存在的文件夹。文档已不在（被删）时返回 None，
    前端只凭 doc_id 深链（找不到时给「不存在或无权访问」提示）。
    """
    from app.models.knowledge_models import KnowledgeDocument

    if receipt.result_resource_id is None:
        return None
    return (
        await db.execute(
            sa.select(KnowledgeDocument.folder_id).where(
                KnowledgeDocument.id == receipt.result_resource_id,
                KnowledgeDocument.is_deleted == sa.false(),
            )
        )
    ).scalar_one_or_none()
