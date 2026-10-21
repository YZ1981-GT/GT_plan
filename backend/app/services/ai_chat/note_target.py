"""AI 笔记转存的来源会话与保存位置（spec ai-chat-adopt-and-note-target-picker R4）

两件事都在占用幂等收据**之前**完成，失败零副作用：

1. **来源会话**：服务端按消息 ID 反查所属会话，客户端 ``session_id`` 只作一致性断言；
   会话必须属于当前用户，所选回复只能来自同一个会话。旧前端从不发 ``session_id``
   而后端把它设为必填 ⇒ 转存在任何页面都恒 422，这里改为服务端反查。
2. **保存位置**：``target_project_id`` / ``target_folder_id`` 二选一，都不传时用宿主项目。
   会话绑定了项目时只能保存到该项目（旧实现不比会话项目 ⇒ 发 P2 宿主 + P1 会话的
   消息即可把 P1 的对话存进 P2）。项目目标按「角色上界 + 项目成员（admin 除外）」判权，
   文件夹目标按知识库写权限（与 ``knowledge_folders._authorize_folder_create`` 同口径）。
   不存在与无权对外是同一句原因，真实拒绝码只进内部审计。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import AIChatMessage, AIChatSession, ChatMessageStatus, ChatRole
from app.models.knowledge_models import KnowledgeFolder
from app.services.ai_chat.access import ResourceAccessResolver
from app.services.ai_chat.contracts import (
    AiChatAction,
    AiChatDenialCode,
    HostType,
    ResourceType,
    role_allows_action,
)
from app.services.ai_chat.host_context import AuthorizedHostContext
from app.services.knowledge_access_policy import KnowledgeAccessPolicy, KnowledgeWritePolicy

__all__ = [
    "NoteSaveFailed",
    "NoteSource",
    "NoteTarget",
    "TARGET_DENIED_MESSAGE",
    "folder_location_label",
    "resolve_note_source",
    "resolve_note_target",
]

#: 不存在与无权共用一句（不可枚举）
TARGET_DENIED_MESSAGE = "所选保存位置不存在或无权访问"
ROLE_DENIED_MESSAGE = "当前角色无权创建笔记"
OUT_OF_SCOPE_MESSAGE = "这段对话属于项目，只能保存到该项目的笔记"

#: 宿主项目由客户端断言（未复核成员关系）的宿主类型：走默认位置时须补项目判权
_ASSERTED_PROJECT_HOSTS = frozenset({HostType.knowledge_doc, HostType.knowledge_folder})


class NoteSaveFailed(Exception):
    """笔记转存失败（``code`` 稳定、``message`` 为可直接展示的中文）。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class NoteSource:
    """消息所在会话（服务端反查）。``project_id`` 为 None = 全局知识等无项目会话。"""

    session_id: UUID
    project_id: UUID | None


@dataclass(frozen=True)
class NoteTarget:
    """已授权的保存位置：项目「AI 对话笔记」文件夹，或某个知识库文件夹（二者恰一）。"""

    project_id: UUID | None = None
    folder_id: UUID | None = None

    @property
    def document_access(self) -> tuple[str | None, list[str] | None]:
        """新文档的 (access_level, project_ids)：文件夹目标继承文件夹，项目目标项目组可见。"""
        if self.folder_id is not None:
            return None, None
        return "project_group", [str(self.project_id)]

    async def ensure_folder(self, db: AsyncSession) -> KnowledgeFolder:
        """项目目标委托 ``ensure_project_folder``（按 system_key 定位、SAVEPOINT 内建、冲突
        重查、不回滚调用方事务，单一真源 Req 8.4）；文件夹目标按 ID 取未删除行。"""
        if self.folder_id is not None:
            folder = (
                await db.execute(
                    sa.select(KnowledgeFolder).where(
                        KnowledgeFolder.id == self.folder_id,
                        KnowledgeFolder.is_deleted == sa.false(),
                    )
                )
            ).scalar_one_or_none()
            if folder is None:  # 判权之后被删
                raise NoteSaveFailed("target_denied", TARGET_DENIED_MESSAGE)
            return folder
        from app.services.knowledge_folder_service import ensure_project_folder

        return await ensure_project_folder(db, self.project_id, "ai_notes")


# ---------------------------------------------------------------------------
# 来源会话
# ---------------------------------------------------------------------------


async def resolve_note_source(
    db: AsyncSession,
    *,
    actor_id: UUID,
    message_ids: list[UUID],
    session_id: UUID | None,
) -> NoteSource:
    """反查所选回复所在的**唯一**会话（属于当前用户，消息为 completed assistant）。

    ``session_id`` 传入时只作断言：该会话必须属于当前用户（消息过滤沿用该会话）。
    """
    if session_id is not None:
        project_id = (
            await db.execute(
                sa.select(AIChatSession.project_id).where(
                    AIChatSession.id == session_id,
                    AIChatSession.user_id == actor_id,
                )
            )
        ).first()
        if project_id is None:
            raise NoteSaveFailed("messages_not_found", "所选回复不存在、未完成或不属于你的对话")
        return NoteSource(session_id=session_id, project_id=project_id[0])

    rows = (
        await db.execute(
            sa.select(AIChatSession.id, AIChatSession.project_id)
            .join(AIChatMessage, AIChatMessage.session_id == AIChatSession.id)
            .where(
                AIChatMessage.id.in_(message_ids),
                AIChatMessage.role == ChatRole.assistant.value,
                AIChatMessage.status == ChatMessageStatus.completed.value,
                AIChatSession.user_id == actor_id,
            )
            .distinct()
        )
    ).all()
    if not rows:
        raise NoteSaveFailed("messages_not_found", "所选回复不存在、未完成或不属于你的对话")
    if len(rows) > 1:
        raise NoteSaveFailed("mixed_sessions", "所选回复来自不同的对话，请分开保存")
    return NoteSource(session_id=rows[0][0], project_id=rows[0][1])


# ---------------------------------------------------------------------------
# 保存位置
# ---------------------------------------------------------------------------


async def resolve_note_target(
    db: AsyncSession,
    *,
    user: Any,
    host: AuthorizedHostContext,
    source: NoteSource,
    target_project_id: UUID | None,
    target_folder_id: UUID | None,
    access: ResourceAccessResolver | None = None,
) -> NoteTarget:
    """判定保存位置（规则顺序：二选一 → 会话项目范围 → 判权 → 存在性）。"""
    if target_project_id is not None and target_folder_id is not None:
        raise NoteSaveFailed("ambiguous_target", "保存位置只能选择一个")
    resolver = access if access is not None else ResourceAccessResolver(db)
    bound = source.project_id

    if target_folder_id is not None:
        if bound is not None:
            raise NoteSaveFailed("target_out_of_scope", OUT_OF_SCOPE_MESSAGE)
        await _authorize_folder(db, resolver, user, target_folder_id)
        return NoteTarget(folder_id=target_folder_id)

    if target_project_id is not None:
        if bound is not None and bound != target_project_id:
            raise NoteSaveFailed("target_out_of_scope", OUT_OF_SCOPE_MESSAGE)
        await _authorize_project(db, resolver, user, target_project_id)
        return NoteTarget(project_id=target_project_id)

    project_id = host.project_id
    if project_id is None:
        raise NoteSaveFailed("no_target", "请选择笔记保存位置")
    if not host.allows(AiChatAction.note_create):
        raise NoteSaveFailed("action_denied", ROLE_DENIED_MESSAGE)
    if bound is not None and bound != project_id:
        raise NoteSaveFailed("target_out_of_scope", OUT_OF_SCOPE_MESSAGE)
    if host.resource_type in _ASSERTED_PROJECT_HOSTS:
        # 知识库宿主的项目是客户端断言（locate 不复核成员关系）⇒ 写入前补判权
        await _authorize_project(db, resolver, user, project_id)
    return NoteTarget(project_id=project_id)


async def _authorize_project(
    db: AsyncSession, resolver: ResourceAccessResolver, user: Any, project_id: UUID
) -> None:
    from app.models.core import Project

    decision = await resolver.authorize_project(user, project_id, AiChatAction.note_create)
    if not decision.allowed:
        await _audit(resolver, decision.principal_id, decision.denial_code, project_id, None)
        if decision.denial_code in (
            AiChatDenialCode.role_capability_denied.value,
            AiChatDenialCode.action_denied.value,
        ):
            raise NoteSaveFailed("action_denied", ROLE_DENIED_MESSAGE)
        raise NoteSaveFailed("target_denied", TARGET_DENIED_MESSAGE)
    exists = (
        await db.execute(
            sa.select(Project.id).where(Project.id == project_id, Project.is_deleted == sa.false())
        )
    ).scalar_one_or_none()
    if exists is None:
        await _audit(
            resolver, decision.principal_id, AiChatDenialCode.resource_not_found.value,
            project_id, None,
        )
        raise NoteSaveFailed("target_denied", TARGET_DENIED_MESSAGE)


async def _authorize_folder(
    db: AsyncSession, resolver: ResourceAccessResolver, user: Any, folder_id: UUID
) -> None:
    role = getattr(user, "role", None)
    principal_id = getattr(user, "id", None)
    role_value = getattr(role, "value", role)
    if not role_allows_action(str(role_value) if role_value else None, AiChatAction.note_create):
        raise NoteSaveFailed("action_denied", ROLE_DENIED_MESSAGE)
    subject = await KnowledgeAccessPolicy.resolve_subject(db, user)
    folder = await KnowledgeAccessPolicy.load_folder_permission(db, folder_id)
    if folder is None or not KnowledgeWritePolicy.can_create(subject, folder, role):
        code = (
            AiChatDenialCode.resource_not_found if folder is None
            else AiChatDenialCode.access_denied
        )
        await _audit(resolver, principal_id, code.value, None, folder_id)
        raise NoteSaveFailed("target_denied", TARGET_DENIED_MESSAGE)


async def _audit(
    resolver: ResourceAccessResolver,
    principal_id: Any,
    denial_code: str | None,
    project_id: UUID | None,
    folder_id: UUID | None,
) -> None:
    """写内部 denial audit（失败不改变对外结果）。"""
    if principal_id is None:
        return
    await resolver.audit_denial(
        principal_id=principal_id,
        project_id=project_id,
        denial_code=denial_code or AiChatDenialCode.access_denied.value,
        entrypoint="ai_chat.note_save.target",
        action=AiChatAction.note_create,
        resource_type=ResourceType.knowledge_folder if folder_id is not None else None,
        resource_id=str(folder_id or project_id or ""),
    )


async def folder_location_label(db: AsyncSession, folder_id: UUID | None) -> str:
    """文件夹完整路径「根 / … / 本级」（只在判权通过、写入成功后调用）。"""
    names: list[str] = []
    current = folder_id
    for _ in range(12):  # 防环：知识库层级远小于 12
        if current is None:
            break
        row = (
            await db.execute(
                sa.select(KnowledgeFolder.name, KnowledgeFolder.parent_id).where(
                    KnowledgeFolder.id == current
                )
            )
        ).first()
        if row is None:
            break
        names.append(row[0])
        current = row[1]
    return " / ".join(reversed(names))
