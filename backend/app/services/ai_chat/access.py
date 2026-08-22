"""``ResourceAccessResolver`` · AI 对话统一资源授权适配层（Task 1）

Feature: dsh-agent-panel-integration
Requirements:
  - 2.1：任何 AI 端点在读取资源 label / 摘要 / 正文 / 索引片段 / 历史消息之前调用本模块；
    私有 ContextBuilder 方法不再充当跨路由授权 API。
  - 2.2：只编排平台既有公开权限服务（项目成员关系、``gate_wp``/批量底稿可见性、
    ``KnowledgeAccessPolicy``、``VisibilityRoleClassifier``、``scope_cycles``、
    冻结的 ``role_capability_contract``）；不在 AI 模块复制第二套角色或资源权限算法。
  - 2.4：mention 搜索、HostContext、history、clear、adopt、attachment、note、review、
    MCP callback 与 citation jump 使用同一决策函数，不存在"搜索不可见但直接 ID 可读"的旁路。
  - 2.5：拒绝发生在敏感字段读取之前；对外统一不可枚举响应（404 +
    ``资源不存在或不可访问``），内部真实 denial code 写安全审计。
  - 2.6：``scope_cycles`` 限制随决策返回，mention / RAG / MCP / Agent 共用同一裁剪上界。
  - 2.7：五角色 × 跨项目 × 跨循环 × private/project_group 的允许/拒绝矩阵可测。
  - 2.8：授权服务内部异常 fail-closed（拒绝），绝不降级为"空上下文继续调用模型"。
Design: "Components and Interfaces → 1. ResourceAccessResolver"；授权调用顺序固定为
  ``解析最小资源标识 → 授权决策 → 读取 label/正文/索引 → 脱敏 → 进入上下文``。

判定维度（最终允许集合 = 全部维度的**交集**）：

==============  ====================================================
维度            真源
==============  ====================================================
角色动作上界    ``role_capability_contract``（系统角色 = ``users.role``）
项目成员关系    ``ProjectUser``（active）
底稿资源权限    ``wp_visibility.entry_integration.gate_wp`` / ``try_gate_wp``
批量底稿可见集  ``wp_visibility.entry_integration.make_bulk_visible_filter``
知识库权限      ``knowledge_access_policy.KnowledgeAccessPolicy``
角色分类/scope  ``wp_visibility.role_classifier.VisibilityRoleClassifier``
==============  ====================================================

本模块**不**产生任何额外允许项：每个 authorizer 只能在上述服务判定为允许时返回 allow。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import ProjectUser
from app.services.ai_chat.contracts import (
    ACTION_CAPABILITIES,
    GLOBAL_KNOWLEDGE_HOST_ID,
    HOST_WRITE_ACTIONS,
    KNOWLEDGE_WRITE_ACTIONS,
    REPORT_HOST_IDS,
    AccessDecision,
    AiChatAction,
    AiChatDenialCode,
    DENIAL_REASON_BY_CODE,
    HostRef,
    HostType,
    ResourceType,
    coerce_uuid,
    role_allowed_actions,
    role_allows_action,
)
from app.services.knowledge_access_policy import (
    KnowledgeAccessPolicy,
    KnowledgeAccessSubject,
)
from app.services.wp_visibility.contracts import VisibilityRole
from app.services.wp_visibility.denial import DenialResponder, ExternalNotFound
from app.services.wp_visibility.entry_integration import (
    make_bulk_visible_filter,
    try_gate_wp,
)
from app.services.wp_visibility.role_classifier import VisibilityRoleClassifier

logger = logging.getLogger(__name__)

__all__ = ["ResourceAccessResolver", "AI_ENTRY_FAMILY"]

#: 安全审计 outbox 的 entry_family（把 AI 面板的拒绝与底稿页面级拒绝区分开）。
AI_ENTRY_FAMILY = "ai_chat"

#: 宿主类型 → 资源类型（一一对应；HostRef 就是"以某资源为宿主"）。
_RESOURCE_BY_HOST: dict[HostType, ResourceType] = {
    HostType.workpaper: ResourceType.workpaper,
    HostType.note: ResourceType.note,
    HostType.report: ResourceType.report,
    HostType.knowledge_doc: ResourceType.knowledge_doc,
    HostType.knowledge_folder: ResourceType.knowledge_folder,
    HostType.global_knowledge: ResourceType.global_knowledge,
}

#: 底稿 gate 的读入口（已登记于 ``ActionMatrix``：entrypoint/method/action 三元组）。
_WP_READ_GATE = ("workpaper.ai_context", "GET", "ai_read")
#: 底稿 gate 的写入口（采纳把 AI 正文写回宿主底稿）。
_WP_WRITE_GATE = ("workpaper.ai_generate", "POST", "ai_generate")

#: 需要项目绑定的资源类型（全局知识模式之外，AI 项目工具必须有 project 绑定）。
_PROJECT_BOUND_RESOURCES: frozenset[ResourceType] = frozenset(
    {ResourceType.workpaper, ResourceType.note, ResourceType.report}
)


#: UUID 归一（单一真源在 ``contracts.coerce_uuid``；此处只保留本模块惯用的私有别名）。
_coerce_uuid = coerce_uuid


def _system_role(user: Any) -> str | None:
    """系统角色（capability actor）。取值真源 = ``users.role``，不读 JWT claim。

    ``role_capability_contract.ROLE_SOURCE_OF_TRUTH == "database"``；此处只做枚举取值归一。
    """
    raw = getattr(user, "role", None)
    if raw is None:
        return None
    value = getattr(raw, "value", raw)
    return str(value) if value else None


class ResourceAccessResolver:
    """AI 对话资源授权唯一入口。

    使用方式（固定顺序）::

        resolver = ResourceAccessResolver(db)
        host = await resolver.enforce_host(user, host_ref, AiChatAction.read)
        # ↑ 拒绝在此抛 ExternalNotFound（404 不可枚举）；此后才允许读 label / 正文 / 索引
        decision = await resolver.enforce_resource(
            user, host, ResourceType.knowledge_doc, doc_id, AiChatAction.read
        )

    ``authorize_*`` 返回 ``AccessDecision``（不抛异常，供批量过滤与矩阵测试）；
    ``enforce_*`` 在拒绝时写审计并抛 ``ExternalNotFound``（供路由直接使用）。
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        responder: DenialResponder | None = None,
        classifier: VisibilityRoleClassifier | None = None,
    ) -> None:
        self._db = db
        self._responder = responder if responder is not None else DenialResponder()
        self._classifier = classifier if classifier is not None else VisibilityRoleClassifier(db)
        self._subject: tuple[Any, KnowledgeAccessSubject] | None = None

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    async def authorize_host(
        self,
        user: Any,
        host: HostRef,
        action: AiChatAction = AiChatAction.read,
    ) -> AccessDecision:
        """判定当前用户能否以 ``host`` 为宿主执行 ``action``。

        判定顺序：角色动作上界 → 资源标识合法性 → 资源级权限（只取判权字段）。
        任一步失败即返回拒绝决策，且**不**读取 label / 摘要 / 正文 / 索引。
        """
        principal_id = _coerce_uuid(getattr(user, "id", None))
        if principal_id is None:
            return AccessDecision(
                allowed=False,
                principal_id=UUID(int=0),
                project_id=None,
                denial_code=AiChatDenialCode.access_denied.value,
            )

        resource_type = _RESOURCE_BY_HOST.get(host.type)
        if resource_type is None:
            return self._deny(
                principal_id, None, AiChatDenialCode.unsupported_resource
            )

        try:
            return await self._authorize(
                user=user,
                principal_id=principal_id,
                resource_type=resource_type,
                resource_id=host.id,
                action=action,
                project_hint=host.project_id_assertion,
            )
        except Exception as exc:  # noqa: BLE001 — Req 2.8 授权服务异常 fail-closed
            logger.error(
                "AI 授权解析异常（fail-closed）principal=%s host=%s/%s action=%s: %s",
                principal_id, host.type.value, host.id, action.value, exc,
            )
            return self._deny(principal_id, None, AiChatDenialCode.resolver_error)

    async def authorize_resource(
        self,
        user: Any,
        host: AccessDecision,
        resource_type: ResourceType,
        resource_id: str,
        action: AiChatAction,
    ) -> AccessDecision:
        """在**已授权宿主**下判定某个具体资源（mention / citation / MCP 取数用）。

        ``host`` 必须是本 resolver 先前返回的 allow 决策：宿主未授权时任何资源判定直接拒绝
        （防止"先拿资源、后补宿主"的旁路，Req 2.4）。资源所属项目与宿主项目不一致时按
        ``cross_project`` 拒绝。
        """
        principal_id = _coerce_uuid(getattr(user, "id", None))
        if principal_id is None:
            return AccessDecision(
                allowed=False,
                principal_id=UUID(int=0),
                project_id=None,
                denial_code=AiChatDenialCode.access_denied.value,
            )
        if not host.allowed:
            return self._deny(principal_id, host.project_id, AiChatDenialCode.access_denied)
        if host.principal_id != principal_id:
            # 宿主决策属于另一主体 —— 绝不跨主体复用授权结果。
            return self._deny(principal_id, host.project_id, AiChatDenialCode.access_denied)

        try:
            return await self._authorize(
                user=user,
                principal_id=principal_id,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                project_hint=host.project_id,
                host=host,
            )
        except Exception as exc:  # noqa: BLE001 — Req 2.8 fail-closed
            logger.error(
                "AI 资源授权异常（fail-closed）principal=%s resource=%s/%s action=%s: %s",
                principal_id, resource_type.value, resource_id, action.value, exc,
            )
            return self._deny(principal_id, host.project_id, AiChatDenialCode.resolver_error)

    async def enforce_host(
        self,
        user: Any,
        host: HostRef,
        action: AiChatAction = AiChatAction.read,
        *,
        entrypoint: str = "ai_chat.host",
        request_id: str | None = None,
    ) -> AccessDecision:
        """``authorize_host`` + 拒绝时写审计并抛不可枚举 404。"""
        decision = await self.authorize_host(user, host, action)
        if not decision.allowed:
            await self._audit_denial(
                decision=decision,
                entrypoint=entrypoint,
                action=action,
                resource_type=_RESOURCE_BY_HOST.get(host.type),
                resource_id=host.id,
                request_id=request_id,
            )
            raise ExternalNotFound()
        return decision

    async def enforce_resource(
        self,
        user: Any,
        host: AccessDecision,
        resource_type: ResourceType,
        resource_id: str,
        action: AiChatAction,
        *,
        entrypoint: str = "ai_chat.resource",
        request_id: str | None = None,
    ) -> AccessDecision:
        """``authorize_resource`` + 拒绝时写审计并抛不可枚举 404。"""
        decision = await self.authorize_resource(
            user, host, resource_type, resource_id, action
        )
        if not decision.allowed:
            await self._audit_denial(
                decision=decision,
                entrypoint=entrypoint,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                request_id=request_id,
            )
            raise ExternalNotFound()
        return decision

    async def audit_denial(
        self,
        *,
        principal_id: UUID,
        project_id: UUID | None,
        denial_code: str,
        entrypoint: str,
        action: AiChatAction,
        resource_type: ResourceType | None,
        resource_id: str | None,
        request_id: str | None = None,
    ) -> None:
        """公共 denial audit 入口（供 ``HostContextResolver`` 的反查阶段拒绝复用）。

        Task 2 的 locate 阶段会在授权之前就拒绝（资源不存在 / 断言冲突 / 非法 ID），
        这些拒绝同样必须留下内部可追溯记录。审计的映射与脱敏逻辑只有一份
        （``_audit_denial``），此处只是把它暴露成公共 API，不复制第二套。
        """
        await self._audit_denial(
            decision=AccessDecision(
                allowed=False,
                principal_id=principal_id,
                project_id=project_id,
                denial_code=denial_code,
            ),
            entrypoint=entrypoint,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=request_id,
        )

    async def filter_visible_resources(
        self,
        user: Any,
        host: AccessDecision,
        resource_type: ResourceType,
        resource_ids: Iterable[str],
        action: AiChatAction = AiChatAction.search,
    ) -> list[str]:
        """搜索/枚举场景的可见集过滤：不可见项静默剔除，不泄露存在性（Req 2.5）。

        底稿走平台既有 ``make_bulk_visible_filter``（与批量导出同一可见集语义），
        其余资源类型逐项复用 ``authorize_resource``。**同一 (资源, 动作) 的判定与
        直接 ID 访问完全一致**（Property 4：不得出现"搜索不可见但直接 ID 可读"）。
        """
        ids = [rid for rid in resource_ids if rid]
        if not ids or not host.allowed:
            return []

        if resource_type is ResourceType.workpaper and role_allows_action(
            _system_role(user), action
        ):
            visible = make_bulk_visible_filter(
                self._db,
                user,
                entrypoint=_WP_READ_GATE[0],
                action=_WP_READ_GATE[2],
                method=_WP_READ_GATE[1],
                entry_family=AI_ENTRY_FAMILY,
            )
            out: list[str] = []
            for rid in ids:
                if _coerce_uuid(rid) is None:
                    continue
                if await visible(rid, None):
                    out.append(rid)
            return out

        out = []
        for rid in ids:
            decision = await self.authorize_resource(
                user, host, resource_type, rid, action
            )
            if decision.allowed:
                out.append(rid)
        return out

    # ------------------------------------------------------------------
    # 内部：统一判定管线
    # ------------------------------------------------------------------
    async def _authorize(
        self,
        *,
        user: Any,
        principal_id: UUID,
        resource_type: ResourceType,
        resource_id: str,
        action: AiChatAction,
        project_hint: UUID | None,
        host: AccessDecision | None = None,
    ) -> AccessDecision:
        # ① 角色动作上界（无 IO，最先拒绝）
        role = _system_role(user)
        if not role_allows_action(role, action):
            code = (
                AiChatDenialCode.role_capability_denied
                if role and action in ACTION_CAPABILITIES
                else AiChatDenialCode.action_denied
            )
            return self._deny(principal_id, project_hint, code)

        # ② 资源标识合法性（非法 ID 与不存在同构，避免 loader 抛异常泄露形态）
        if resource_type is ResourceType.global_knowledge:
            if resource_id != GLOBAL_KNOWLEDGE_HOST_ID:
                return self._deny(
                    principal_id, None, AiChatDenialCode.invalid_resource_id
                )
        elif resource_type is ResourceType.report:
            # 报表实例由 (project, year, report_type) 唯一确定，没有 instance UUID：
            # 其稳定 ID 是 report type 字面量（取值域真源 = contracts.REPORT_HOST_IDS）。
            # 这条分支同时挡住"把 project UUID 当 doc ID 传"的旧契约（Req 3.5）。
            if resource_id not in REPORT_HOST_IDS:
                return self._deny(
                    principal_id, project_hint, AiChatDenialCode.invalid_resource_id
                )
        elif resource_type is ResourceType.address:
            # 地址坐标 ID 是稳定字符串（{wp_code}/{sheet_code}/{coordinate_key}），
            # 非 UUID，非空即合法（Req 6.1）。
            if not resource_id or not resource_id.strip():
                return self._deny(
                    principal_id, project_hint, AiChatDenialCode.invalid_resource_id
                )
        else:
            if _coerce_uuid(resource_id) is None:
                return self._deny(
                    principal_id, project_hint, AiChatDenialCode.invalid_resource_id
                )

        # ③ 资源级权限（每类资源只走既有权限服务）
        if resource_type is ResourceType.workpaper:
            return await self._authorize_workpaper(
                user, principal_id, UUID(str(resource_id)), action, role
            )
        if resource_type in (ResourceType.note, ResourceType.report):
            return await self._authorize_project_resource(
                user, principal_id, project_hint, action, role
            )
        if resource_type in (ResourceType.knowledge_doc, ResourceType.knowledge_folder):
            return await self._authorize_knowledge(
                user, principal_id, resource_type, UUID(str(resource_id)), action, role,
                project_hint=host.project_id if host is not None else project_hint,
            )
        if resource_type is ResourceType.global_knowledge:
            # 受限全局知识模式：无项目绑定，项目工具由 project_id=None 关闭。
            return AccessDecision(
                allowed=True,
                principal_id=principal_id,
                project_id=None,
                cycle_scope=frozenset(),
                allowed_actions=self._effective_actions(role, project_bound=False),
            )

        if resource_type is ResourceType.address:
            return await self._authorize_address(
                user, principal_id, resource_id, action,
                project_hint=host.project_id if host is not None else project_hint,
                role=role,
            )

        # 未注册资源类型（attachment）→ fail-closed
        return self._deny(principal_id, project_hint, AiChatDenialCode.unsupported_resource)

    async def _authorize_workpaper(
        self,
        user: Any,
        principal_id: UUID,
        wp_id: UUID,
        action: AiChatAction,
        role: str | None,
    ) -> AccessDecision:
        """底稿：完全委托平台统一门 ``gate_wp``（项目反查 + 委派 + scope + Action_Matrix）。

        采纳等写宿主动作走已登记的 ``workpaper.ai_generate`` 写入口；其余走
        ``workpaper.ai_context`` 读入口。门内部拒绝时静默返回 None（不写底稿侧安全 outbox），
        由本 resolver 统一写 AI 侧 denial audit，避免同一次拒绝被记两遍。
        """
        entrypoint, method, gate_action = (
            _WP_WRITE_GATE if action in HOST_WRITE_ACTIONS else _WP_READ_GATE
        )
        ctx = await try_gate_wp(
            self._db,
            user,
            entrypoint=entrypoint,
            action=gate_action,
            method=method,
            wp_id=wp_id,
            entry_family=AI_ENTRY_FAMILY,
        )
        if ctx is None:
            return self._deny(principal_id, None, AiChatDenialCode.access_denied)

        # scope 上界与角色分类：项目由门反查得到，不用客户端断言。
        scope, unbounded = await self._resolve_scope(user, ctx.project_id)
        return AccessDecision(
            allowed=True,
            principal_id=principal_id,
            project_id=ctx.project_id,
            cycle_scope=scope,
            allowed_actions=self._effective_actions(
                role, project_bound=True, readonly=ctx.readonly
            ),
            scope_unbounded=unbounded,
            detail={"wp_index_id": str(ctx.wp_index_id)},
        )

    async def _authorize_project_resource(
        self,
        user: Any,
        principal_id: UUID,
        project_id: UUID | None,
        action: AiChatAction,
        role: str | None,
    ) -> AccessDecision:
        """附注 / 报表：项目级资源，判定 = active ``ProjectUser`` 成员关系（admin 除外）。

        **Task 2 边界**：把 note/report 实例反查到权威 project/year（Req 2.3/3.2）由
        ``host_context.py`` 的专属 resolver 完成；本层只保证"必须是该项目的成员"，
        这已经消除了"任何登录用户都能就任意项目发起 AI 对话"的旁路。
        """
        if project_id is None:
            return self._deny(principal_id, None, AiChatDenialCode.access_denied)

        scope, unbounded = await self._resolve_scope(user, project_id)
        if not unbounded and not await self._is_project_member(principal_id, project_id):
            return self._deny(principal_id, project_id, AiChatDenialCode.access_denied)

        return AccessDecision(
            allowed=True,
            principal_id=principal_id,
            project_id=project_id,
            cycle_scope=scope,
            allowed_actions=self._effective_actions(role, project_bound=True),
            scope_unbounded=unbounded,
        )

    async def _authorize_knowledge(
        self,
        user: Any,
        principal_id: UUID,
        resource_type: ResourceType,
        resource_id: UUID,
        action: AiChatAction,
        role: str | None,
        *,
        project_hint: UUID | None,
    ) -> AccessDecision:
        """知识库文档 / 文件夹：完全委托公共 ``KnowledgeAccessPolicy``。

        只取判权三元组（access_level / project_ids / created_by），不读 name / content_text /
        content_summary —— 拒绝路径上没有任何可泄露字段（Req 2.5）。
        """
        subject = await self._knowledge_subject(user)
        write = action in (KNOWLEDGE_WRITE_ACTIONS | HOST_WRITE_ACTIONS)

        if resource_type is ResourceType.knowledge_folder:
            folder = await KnowledgeAccessPolicy.load_folder_permission(
                self._db, resource_id
            )
            if folder is None:
                return self._deny(
                    principal_id, project_hint, AiChatDenialCode.resource_not_found
                )
            ok = (
                KnowledgeAccessPolicy.can_create_in_folder(subject, folder)
                if write
                else KnowledgeAccessPolicy.can_read(subject, folder)
            )
        else:
            loaded = await KnowledgeAccessPolicy.load_document_permission(
                self._db, resource_id
            )
            if loaded is None:
                return self._deny(
                    principal_id, project_hint, AiChatDenialCode.resource_not_found
                )
            document, folder = loaded
            ok = KnowledgeAccessPolicy.can_read_document(subject, document, folder)
            if ok and write:
                ok = folder is not None and KnowledgeAccessPolicy.can_create_in_folder(
                    subject, folder
                )

        if not ok:
            return self._deny(principal_id, project_hint, AiChatDenialCode.access_denied)

        # 知识资源可跨项目共享：项目绑定沿用宿主项目（无宿主项目时为受限全局范围）。
        scope: frozenset[str] = frozenset()
        unbounded = False
        if project_hint is not None:
            scope, unbounded = await self._resolve_scope(user, project_hint)
        return AccessDecision(
            allowed=True,
            principal_id=principal_id,
            project_id=project_hint,
            cycle_scope=scope,
            allowed_actions=self._effective_actions(
                role, project_bound=project_hint is not None
            ),
            scope_unbounded=unbounded,
        )

    async def _authorize_address(
        self,
        user: Any,
        principal_id: UUID,
        resource_id: str,
        action: AiChatAction,
        *,
        project_hint: UUID | None,
        role: str | None,
    ) -> AccessDecision:
        """地址坐标：项目成员关系 + 地址域权限（Req 6.7）。

        授权逻辑：
        1. 必须有项目绑定（地址坐标属于项目数据）
        2. 必须是该项目的 active 成员（或 admin/scope unbounded）
        3. 地址域权限由 scope_cycles 上界约束（地址所属底稿循环必须在 scope 内）

        未授权用户不能通过语义搜索获知地址 label 或当前值（Property 17）。
        """
        if project_hint is None:
            return self._deny(principal_id, None, AiChatDenialCode.access_denied)

        scope, unbounded = await self._resolve_scope(user, project_hint)
        if not unbounded and not await self._is_project_member(principal_id, project_hint):
            return self._deny(principal_id, project_hint, AiChatDenialCode.access_denied)

        return AccessDecision(
            allowed=True,
            principal_id=principal_id,
            project_id=project_hint,
            cycle_scope=scope,
            allowed_actions=self._effective_actions(role, project_bound=True),
            scope_unbounded=unbounded,
        )

    # ------------------------------------------------------------------
    # 内部：维度取数
    # ------------------------------------------------------------------
    async def _resolve_scope(
        self, user: Any, project_id: UUID
    ) -> tuple[frozenset[str], bool]:
        """``scope_cycles`` 上界 + 是否不受 scope 限制（Admin）。

        复用 ``VisibilityRoleClassifier``（唯一角色分类入口）；不重算 scope 语义。
        """
        ctx = await self._classifier.classify(user, project_id)
        return ctx.scope_cycles, ctx.role is VisibilityRole.admin

    async def _is_project_member(self, user_id: UUID, project_id: UUID) -> bool:
        count = (
            await self._db.execute(
                sa.select(sa.func.count())
                .select_from(ProjectUser)
                .where(
                    ProjectUser.project_id == project_id,
                    ProjectUser.user_id == user_id,
                    ProjectUser.is_deleted == sa.false(),
                )
            )
        ).scalar_one()
        return bool(count)

    async def _knowledge_subject(self, user: Any) -> KnowledgeAccessSubject:
        if self._subject is not None and self._subject[0] is user:
            return self._subject[1]
        subject = await KnowledgeAccessPolicy.resolve_subject(self._db, user)
        self._subject = (user, subject)
        return subject

    # ------------------------------------------------------------------
    # 内部：决策构造与审计
    # ------------------------------------------------------------------
    @staticmethod
    def _effective_actions(
        role: str | None, *, project_bound: bool, readonly: bool = False
    ) -> frozenset[str]:
        """角色上界 ∩ 资源写能力 → 该资源上实际允许的动作集合。

        - ``readonly``：命中只读 grant（History_Only）时写类动作全部剔除。
        - ``project_bound=False``：受限全局知识模式禁用项目类写动作（Req 3.4）。
        """
        actions = role_allowed_actions(role)
        if readonly or not project_bound:
            actions = frozenset(
                a
                for a in actions
                if not ACTION_CAPABILITIES.get(a)  # 只保留读类（capability 空集）动作
            )
        return frozenset(a.value for a in actions)

    @staticmethod
    def _deny(
        principal_id: UUID, project_id: UUID | None, code: AiChatDenialCode
    ) -> AccessDecision:
        return AccessDecision(
            allowed=False,
            principal_id=principal_id,
            project_id=project_id,
            denial_code=code.value,
        )

    async def _audit_denial(
        self,
        *,
        decision: AccessDecision,
        entrypoint: str,
        action: AiChatAction,
        resource_type: ResourceType | None,
        resource_id: str | None,
        request_id: str | None,
    ) -> None:
        """写内部 denial audit（对外响应不变，审计失败也不改变 404）。

        复用平台既有 ``DenialResponder`` 的独立事务 outbox：AI 拒绝码映射到 outbox 允许的
        ``DenialReason`` 取值，detail 只留资源类型/标识与 AI 真实拒绝码，**不含** label /
        项目名 / 正文摘要（Req 2.5 / 12.7）。
        """
        try:
            code = AiChatDenialCode(decision.denial_code or AiChatDenialCode.access_denied.value)
        except ValueError:  # pragma: no cover — denial_code 恒来自枚举
            code = AiChatDenialCode.access_denied
        reason = DENIAL_REASON_BY_CODE[code]
        try:
            await self._responder.deny(
                reason=reason,
                entrypoint=entrypoint,
                entry_family=AI_ENTRY_FAMILY,
                http_method="POST",
                action=action.value,
                request_id=request_id,
                actor_user_id=decision.principal_id,
                project_id=decision.project_id,
                detail={
                    "ai_denial_code": code.value,
                    "resource_type": resource_type.value if resource_type else "unknown",
                    "resource_id": resource_id or "",
                },
            )
        except ExternalNotFound:
            # DenialResponder.deny 以抛 ExternalNotFound 结束（NoReturn）；审计已写入。
            return
