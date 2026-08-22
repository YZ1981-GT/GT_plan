"""``HostContextResolver`` · 服务端可信 HostContext 反查（Task 2）

Feature: dsh-agent-panel-integration
Requirements:
  - 2.3：客户端提交的 ``project_id`` / ``year`` / ``doc_type`` / ``doc_id`` 只作**一致性
    断言**；服务端从目标资源反查可信 HostContext，不一致请求返回 ``host_context_mismatch``。
  - 3.1：宿主类型受后端枚举约束（真源 = ``contracts.HostType``，本模块不新建第二套枚举）。
  - 3.2：``workpaper`` 以 working paper instance ID 解析；``note`` 以项目 + 年度 +
    稳定 section/instance 标识解析；``report`` 以项目 + 年度 + report type 解析；
    ``knowledge_folder`` 以 folder ID 解析。
  - 3.3：每个宿主返回 canonical ``{project_id, year, resource_type, resource_id,
    display_label, permission_binding}``；不存在的字段用 **None**，绝不用空字符串
    伪装有效 ID。
  - 3.4：页面无法解析项目上下文时项目工具关闭（``project_id is None`` +
    ``allowed_actions`` 只剩读类），不猜测最近项目。
  - 3.6：``ContextBuilder`` 只接受本模块产出的 ``AuthorizedHostContext``。
  - 3.7：每种 HostType 调用**唯一对应**的业务 loader（``HOST_BUSINESS_MODEL`` 是该映射的
    机器可读真源），note / report / knowledge_folder 绝不回退到 ``WorkingPaper``。
Design: "Components and Interfaces → 2. HostContextResolver"。

## 三段式解析顺序（与 Design "1. ResourceAccessResolver" 的固定顺序一致）

    ① locate  解析最小资源标识（只读 project_id / year / 稳定键等**绑定字段**）
    ② gate    ResourceAccessResolver 授权决策（Task 1，唯一授权真源）
    ③ label   授权通过后才读 display_label（wp_name / section_title / 文档名）

①只触碰绑定列，不读 label / 摘要 / 正文 / 索引 —— Property 1 的"拒绝前零读取"因此仍然成立；
③被 ``AccessDecision.allowed`` 严格门控，越过②直接调用会抛 ``HostContextContractError``。

## 为什么 note / report 必须有自己的 loader

旧实现 ``ContextBuilder._get_doc_content`` 把 ``note`` / ``report`` 直接转给
``_get_workpaper_content``：附注/报表的 UUID 在 ``working_paper`` 表里查不到 → 正文恒空，
而 AI 仍然照常回答（Req 3.2/3.7 明令禁止的形态）。本模块把每个宿主钉在自己的业务模型上，
并由 ``tests/dsh_agent_panel/test_task2_host_context.py`` 以 **loader 调用计数 + SQL 语句流**
证明映射唯一。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.knowledge_models import KnowledgeDocument, KnowledgeFolder
from app.models.report_models import DisclosureNote, FinancialReport
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.ai_chat.access import ResourceAccessResolver
from app.services.ai_chat.contracts import (
    GLOBAL_KNOWLEDGE_HOST_ID,
    REPORT_HOST_IDS,
    AccessDecision,
    AiChatAction,
    AiChatDenialCode,
    HostRef,
    HostType,
    ResourceType,
    coerce_uuid,
)
from app.services.wp_visibility.denial import ExternalNotFound

logger = logging.getLogger(__name__)

__all__ = [
    "HOST_BUSINESS_MODEL",
    "GLOBAL_KNOWLEDGE_LABEL",
    "AuthorizedHostContext",
    "HostContextDenial",
    "HostContextContractError",
    "HostLocator",
    "HostContextResolver",
]

#: 宿主类型 → 该宿主**允许触碰**的业务表（Property 5 的机器可读真源）。
#:
#: 该表**不是**注释：守卫拿它逐宿主断言"实际 SQL 流命中的业务表 ⊆ 本宿主自己的表"，
#: 因此 note / report / knowledge_* 不可能悄悄走 ``working_paper`` 查询。
#:
#: ``knowledge_doc`` 同时列出文件夹表：知识文档权限**继承**所属文件夹
#: （``KnowledgeAccessPolicy.can_read_document`` 会加载 folder 判权三元组），
#: 这属于该宿主自己的权限域，不是回退到别人的 loader。
HOST_BUSINESS_MODEL: dict[HostType, tuple[str, ...]] = {
    HostType.workpaper: (WorkingPaper.__tablename__, WpIndex.__tablename__),
    HostType.note: (DisclosureNote.__tablename__,),
    HostType.report: (FinancialReport.__tablename__,),
    HostType.knowledge_doc: (
        KnowledgeDocument.__tablename__,
        KnowledgeFolder.__tablename__,
    ),
    HostType.knowledge_folder: (KnowledgeFolder.__tablename__,),
    HostType.global_knowledge: (),
}

#: 受限全局知识模式的展示名（无项目绑定，项目工具关闭）。
GLOBAL_KNOWLEDGE_LABEL = "全局知识库（无项目上下文）"

#: 宿主类型 → 权限绑定描述（写入 ``AuthorizedHostContext.permission_binding``，供审计与
#: 前端"当前 AI 可见范围"提示使用；取值稳定，前端不自造第二份）。
_PERMISSION_BINDING: dict[HostType, str] = {
    HostType.workpaper: "workpaper:gate_wp",
    HostType.note: "project:member",
    HostType.report: "project:member",
    HostType.knowledge_doc: "knowledge:access_policy",
    HostType.knowledge_folder: "knowledge:access_policy",
    HostType.global_knowledge: "global:knowledge_readonly",
}


class HostContextContractError(RuntimeError):
    """调用顺序被破坏（未经授权决策就要求读取 label）。

    这是**编程错误**而非用户拒绝：不映射成 404，直接抛出以便在测试与日志中显形。
    """


@dataclass(frozen=True)
class HostLocator:
    """①locate 阶段产物：服务端反查出的权威绑定，尚未授权、尚未读 label。"""

    host_type: HostType
    #: canonical resource id（note 的稳定 section key 已归一为 instance UUID 字符串）。
    resource_id: str
    project_id: UUID | None
    year: int | None
    #: 交给 ``ResourceAccessResolver`` 的 HostRef（project 断言已替换为服务端反查值）。
    canonical_ref: HostRef
    detail: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthorizedHostContext:
    """已授权且服务端反查完成的宿主上下文（Design "2. HostContextResolver"）。

    字段语义（Req 3.3）：

    - ``project_id`` / ``year``：None = 该宿主**确实没有**项目/年度绑定（受限全局知识模式，
      或年度无法从任何权威列反查）。不得用空字符串或 0 伪装。
    - ``resource_id``：canonical 服务端标识（note 已归一为 instance UUID）。
    - ``display_label``：授权通过后才加载的展示名。
    - ``permission_binding``：本次授权依据的权限域（见 ``_PERMISSION_BINDING``）。
    - ``allowed_actions``：该宿主上实际允许的动作（角色上界 ∩ 资源权限，来自 Task 1）。
    """

    principal_id: UUID
    project_id: UUID | None
    year: int | None
    resource_type: HostType
    resource_id: str
    display_label: str
    permission_binding: str
    cycle_scope: frozenset[str] = frozenset()
    allowed_actions: frozenset[str] = frozenset()
    scope_unbounded: bool = False
    detail: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:  # noqa: D401 — 契约一致性守卫
        if self.resource_id == "":
            raise ValueError("resource_id 不得为空字符串（Req 3.3：用 None 表达缺失）")
        if self.resource_type is HostType.global_knowledge:
            if self.project_id is not None:
                raise ValueError("受限全局知识模式不得携带 project_id")
        elif self.resource_type in (HostType.workpaper, HostType.note, HostType.report):
            if self.project_id is None:
                raise ValueError(
                    f"{self.resource_type.value} 宿主必须有权威 project_id（Req 3.4）"
                )

    @property
    def project_tools_enabled(self) -> bool:
        """项目工具是否可用（Req 3.4：无项目绑定时必须关闭，不猜测最近项目）。"""
        return self.project_id is not None

    def allows(self, action: AiChatAction) -> bool:
        return action.value in self.allowed_actions


@dataclass(frozen=True)
class HostContextDenial:
    """拒绝结果：只携带内部真实拒绝码，**不含** label / 项目名 / 摘要（Req 2.5）。"""

    denial_code: str
    principal_id: UUID
    project_id: UUID | None = None
    resource_type: HostType | None = None


class HostContextResolver:
    """把客户端 ``HostRef`` 反查成可信 ``AuthorizedHostContext``。

    用法::

        resolver = HostContextResolver(db)
        host = await resolver.enforce(user, host_ref, AiChatAction.read,
                                      entrypoint="ai_chat.doc_chat")
        # ↑ 拒绝在此抛 ExternalNotFound（不可枚举 404）；此后 ContextBuilder 才允许取正文

    ``resolve()`` 返回 ``AuthorizedHostContext | HostContextDenial``（不抛异常，供 mention
    批量过滤与矩阵测试）；``enforce()`` 在拒绝时写内部 denial audit 并抛 404。
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        access: ResourceAccessResolver | None = None,
    ) -> None:
        self._db = db
        self._access = access if access is not None else ResourceAccessResolver(db)
        # 每宿主专属 locate / label 分派表（Property 5：唯一映射，无 default 回退）。
        self._locators: dict[HostType, Callable[[HostRef], Awaitable[HostLocator | str]]] = {
            HostType.workpaper: self._locate_workpaper,
            HostType.note: self._locate_note,
            HostType.report: self._locate_report,
            HostType.knowledge_doc: self._locate_knowledge_doc,
            HostType.knowledge_folder: self._locate_knowledge_folder,
            HostType.global_knowledge: self._locate_global_knowledge,
        }
        self._labelers: dict[HostType, Callable[[HostLocator], Awaitable[str]]] = {
            HostType.workpaper: self._label_workpaper,
            HostType.note: self._label_note,
            HostType.report: self._label_report,
            HostType.knowledge_doc: self._label_knowledge_doc,
            HostType.knowledge_folder: self._label_knowledge_folder,
            HostType.global_knowledge: self._label_global_knowledge,
        }
        assert set(self._locators) == set(HostType) == set(self._labelers), (
            "每个 HostType 必须有专属 locate + label（禁止 default 回退到 WorkingPaper）"
        )

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    async def resolve(
        self,
        user: Any,
        host: HostRef,
        action: AiChatAction = AiChatAction.read,
    ) -> AuthorizedHostContext | HostContextDenial:
        principal_id = coerce_uuid(getattr(user, "id", None))
        if principal_id is None:
            return HostContextDenial(
                denial_code=AiChatDenialCode.access_denied.value,
                principal_id=UUID(int=0),
                resource_type=host.type,
            )

        locate = self._locators.get(host.type)
        if locate is None:  # pragma: no cover — 构造期 assert 已保证覆盖
            return HostContextDenial(
                denial_code=AiChatDenialCode.unsupported_resource.value,
                principal_id=principal_id,
                resource_type=host.type,
            )

        # ① locate：服务端反查绑定（只读 project_id / year / 稳定键）
        try:
            located = await locate(host)
        except Exception as exc:  # noqa: BLE001 — Req 2.8 反查异常 fail-closed
            logger.error(
                "HostContext 反查异常（fail-closed）host=%s/%s: %s",
                host.type.value, host.id, exc,
            )
            return HostContextDenial(
                denial_code=AiChatDenialCode.resolver_error.value,
                principal_id=principal_id,
                resource_type=host.type,
            )
        if isinstance(located, str):
            # locate 以拒绝码字符串表达失败（不存在 / 非法 ID / 断言冲突）
            return HostContextDenial(
                denial_code=located,
                principal_id=principal_id,
                resource_type=host.type,
            )

        # ② gate：唯一授权真源（Task 1）
        decision = await self._access.authorize_host(user, located.canonical_ref, action)
        if not decision.allowed:
            return HostContextDenial(
                denial_code=decision.denial_code or AiChatDenialCode.access_denied.value,
                principal_id=principal_id,
                project_id=located.project_id,
                resource_type=host.type,
            )

        # ③ label：授权后才读展示名
        return await self.finalize(located, decision)

    async def finalize(
        self, located: HostLocator, decision: AccessDecision
    ) -> AuthorizedHostContext:
        """③label 阶段：只在 ``decision.allowed`` 为真时读取 display_label。"""
        if not decision.allowed:
            raise HostContextContractError(
                "display_label 只能在授权通过后加载（Design 授权顺序：授权 → 读 label）"
            )
        label = await self._labelers[located.host_type](located)
        project_id = (
            None
            if located.host_type is HostType.global_knowledge
            else (decision.project_id or located.project_id)
        )
        return AuthorizedHostContext(
            principal_id=decision.principal_id,
            project_id=project_id,
            year=located.year,
            resource_type=located.host_type,
            resource_id=located.resource_id,
            display_label=label,
            permission_binding=_PERMISSION_BINDING[located.host_type],
            cycle_scope=decision.cycle_scope,
            allowed_actions=decision.allowed_actions,
            scope_unbounded=decision.scope_unbounded,
            detail={**located.detail, **decision.detail},
        )

    async def enforce(
        self,
        user: Any,
        host: HostRef,
        action: AiChatAction = AiChatAction.read,
        *,
        entrypoint: str = "ai_chat.host",
        request_id: str | None = None,
    ) -> AuthorizedHostContext:
        """``resolve`` + 拒绝时写内部 denial audit 并抛不可枚举 404。"""
        outcome = await self.resolve(user, host, action)
        if isinstance(outcome, HostContextDenial):
            await self._access.audit_denial(
                principal_id=outcome.principal_id,
                project_id=outcome.project_id,
                denial_code=outcome.denial_code,
                entrypoint=entrypoint,
                action=action,
                resource_type=_RESOURCE_BY_HOST.get(host.type),
                resource_id=host.id,
                request_id=request_id,
            )
            raise ExternalNotFound()
        return outcome

    # ------------------------------------------------------------------
    # ①locate —— 每宿主专属，只读绑定列
    # ------------------------------------------------------------------
    async def _locate_workpaper(self, host: HostRef) -> HostLocator | str:
        """底稿：``working_paper JOIN wp_index`` 反查 project；年度取 ``projects.audit_year``。"""
        wp_id = coerce_uuid(host.id)
        if wp_id is None:
            return AiChatDenialCode.invalid_resource_id.value

        row = (
            await self._db.execute(
                sa.select(
                    WorkingPaper.id,
                    WorkingPaper.project_id,
                    WpIndex.id.label("wp_index_id"),
                    Project.audit_year,
                )
                .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
                .join(Project, WorkingPaper.project_id == Project.id)
                .where(
                    WorkingPaper.id == wp_id,
                    WorkingPaper.is_deleted == sa.false(),
                )
            )
        ).first()
        if row is None:
            return AiChatDenialCode.resource_not_found.value

        _wp_id, project_id, wp_index_id, audit_year = row
        mismatch = _assert_bindings(host, project_id=project_id, year=audit_year)
        if mismatch:
            return mismatch
        return HostLocator(
            host_type=HostType.workpaper,
            resource_id=str(wp_id),
            project_id=project_id,
            year=audit_year,
            canonical_ref=HostRef(
                type=HostType.workpaper,
                id=str(wp_id),
                project_id_assertion=project_id,
                year_assertion=audit_year,
            ),
            detail={"wp_index_id": str(wp_index_id)},
        )

    async def _locate_note(self, host: HostRef) -> HostLocator | str:
        """附注：``disclosure_notes`` 反查 project + year。

        稳定输入二选一（Req 3.2）：

        - instance UUID → 直接按主键定位，project/year 完全由行自身给出；
        - 稳定 section key（``section_id`` 或 ``note_section``）→ 需要 project + year
          断言作**查找过滤**才能唯一定位（section key 在项目/年度间重复）。

        绝不调用 ``WorkingPaper`` loader。
        """
        note_id = coerce_uuid(host.id)
        stmt = sa.select(
            DisclosureNote.id,
            DisclosureNote.project_id,
            DisclosureNote.year,
            DisclosureNote.note_section,
        ).where(DisclosureNote.is_deleted == sa.false())

        if note_id is not None:
            stmt = stmt.where(DisclosureNote.id == note_id)
        else:
            key = (host.id or "").strip()
            if not key:
                return AiChatDenialCode.invalid_resource_id.value
            if host.project_id_assertion is None:
                # 无项目断言时无法唯一定位 section key —— 不猜测最近项目（Req 3.4）
                return AiChatDenialCode.invalid_resource_id.value
            stmt = stmt.where(
                DisclosureNote.project_id == host.project_id_assertion,
                sa.or_(
                    DisclosureNote.section_id == key,
                    DisclosureNote.note_section == key,
                ),
            )
            if host.year_assertion is not None:
                stmt = stmt.where(DisclosureNote.year == host.year_assertion)
            stmt = stmt.order_by(DisclosureNote.sort_index, DisclosureNote.note_section)

        row = (await self._db.execute(stmt.limit(1))).first()
        if row is None:
            return AiChatDenialCode.resource_not_found.value

        resolved_id, project_id, year, note_section = row
        mismatch = _assert_bindings(host, project_id=project_id, year=year)
        if mismatch:
            return mismatch
        return HostLocator(
            host_type=HostType.note,
            resource_id=str(resolved_id),
            project_id=project_id,
            year=year,
            canonical_ref=HostRef(
                type=HostType.note,
                id=str(resolved_id),
                project_id_assertion=project_id,
                year_assertion=year,
            ),
            detail={"note_section": str(note_section or "")},
        )

    async def _locate_report(self, host: HostRef) -> HostLocator | str:
        """报表：``financial_report`` 反查。稳定输入 = report type（不是 UUID，也不是 project ID）。

        年度取客户端断言，缺省时回落 ``projects.audit_year``；随后用 ``(project, year, type)``
        验证报表**已实例化**（零行 = 未生成 → ``resource_not_found``，不伪造空宿主）。
        """
        report_type = (host.id or "").strip()
        if report_type not in REPORT_HOST_IDS:
            # project UUID / 空串 / 分析类 tab 名一律非法（Req 3.5：不得把 project ID 当 doc ID）
            return AiChatDenialCode.invalid_resource_id.value
        project_id = host.project_id_assertion
        if project_id is None:
            return AiChatDenialCode.invalid_resource_id.value

        year = host.year_assertion
        if year is None:
            year = (
                await self._db.execute(
                    sa.select(Project.audit_year).where(Project.id == project_id)
                )
            ).scalar_one_or_none()
        if year is None:
            return AiChatDenialCode.resource_not_found.value

        exists = (
            await self._db.execute(
                sa.select(FinancialReport.id)
                .where(
                    FinancialReport.project_id == project_id,
                    FinancialReport.year == year,
                    FinancialReport.report_type == report_type,
                    FinancialReport.is_deleted == sa.false(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if exists is None:
            return AiChatDenialCode.resource_not_found.value

        return HostLocator(
            host_type=HostType.report,
            resource_id=report_type,
            project_id=project_id,
            year=year,
            canonical_ref=HostRef(
                type=HostType.report,
                id=report_type,
                project_id_assertion=project_id,
                year_assertion=year,
            ),
            detail={"report_type": report_type},
        )

    async def _locate_knowledge_doc(self, host: HostRef) -> HostLocator | str:
        """知识文档：``knowledge_documents`` 只反查存在性与 folder 绑定（权限由 policy 判）。"""
        doc_id = coerce_uuid(host.id)
        if doc_id is None:
            return AiChatDenialCode.invalid_resource_id.value
        row = (
            await self._db.execute(
                sa.select(KnowledgeDocument.id, KnowledgeDocument.folder_id).where(
                    KnowledgeDocument.id == doc_id,
                    KnowledgeDocument.is_deleted == sa.false(),
                )
            )
        ).first()
        if row is None:
            return AiChatDenialCode.resource_not_found.value
        return HostLocator(
            host_type=HostType.knowledge_doc,
            resource_id=str(doc_id),
            # 知识资源可跨项目共享：项目绑定沿用客户端断言（授权时由 policy 复核）。
            project_id=host.project_id_assertion,
            year=host.year_assertion,
            canonical_ref=HostRef(
                type=HostType.knowledge_doc,
                id=str(doc_id),
                project_id_assertion=host.project_id_assertion,
                year_assertion=host.year_assertion,
            ),
            detail={"folder_id": str(row[1]) if row[1] else ""},
        )

    async def _locate_knowledge_folder(self, host: HostRef) -> HostLocator | str:
        """知识文件夹：``knowledge_folders`` 按 folder ID 反查（Req 3.2）。"""
        folder_id = coerce_uuid(host.id)
        if folder_id is None:
            return AiChatDenialCode.invalid_resource_id.value
        exists = (
            await self._db.execute(
                sa.select(KnowledgeFolder.id).where(
                    KnowledgeFolder.id == folder_id,
                    KnowledgeFolder.is_deleted == sa.false(),
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            return AiChatDenialCode.resource_not_found.value
        return HostLocator(
            host_type=HostType.knowledge_folder,
            resource_id=str(folder_id),
            project_id=host.project_id_assertion,
            year=host.year_assertion,
            canonical_ref=HostRef(
                type=HostType.knowledge_folder,
                id=str(folder_id),
                project_id_assertion=host.project_id_assertion,
                year_assertion=host.year_assertion,
            ),
        )

    async def _locate_global_knowledge(self, host: HostRef) -> HostLocator | str:
        """受限全局知识模式：显式 sentinel，无项目/年度绑定，零 SQL。"""
        if host.id != GLOBAL_KNOWLEDGE_HOST_ID:
            return AiChatDenialCode.invalid_resource_id.value
        if host.project_id_assertion is not None:
            # 全局模式携带 project 断言 = 前端契约错误（要么用项目宿主，要么用全局模式）
            return AiChatDenialCode.host_context_mismatch.value
        return HostLocator(
            host_type=HostType.global_knowledge,
            resource_id=GLOBAL_KNOWLEDGE_HOST_ID,
            project_id=None,
            year=None,
            canonical_ref=HostRef(
                type=HostType.global_knowledge, id=GLOBAL_KNOWLEDGE_HOST_ID
            ),
        )

    # ------------------------------------------------------------------
    # ③label —— 授权后才读展示名
    # ------------------------------------------------------------------
    async def _label_workpaper(self, located: HostLocator) -> str:
        row = (
            await self._db.execute(
                sa.select(WpIndex.wp_code, WpIndex.wp_name).where(
                    WpIndex.id == UUID(located.detail["wp_index_id"])
                )
            )
        ).first()
        if row is None:  # pragma: no cover — locate 已 JOIN 过 wp_index
            return "底稿"
        code, name = row
        return f"{code} {name}".strip()

    async def _label_note(self, located: HostLocator) -> str:
        row = (
            await self._db.execute(
                sa.select(DisclosureNote.note_section, DisclosureNote.section_title).where(
                    DisclosureNote.id == UUID(located.resource_id)
                )
            )
        ).first()
        if row is None:  # pragma: no cover
            return "附注"
        section, title = row
        return f"{section} {title}".strip()

    async def _label_report(self, located: HostLocator) -> str:
        return REPORT_LABELS.get(located.resource_id, located.resource_id)

    async def _label_knowledge_doc(self, located: HostLocator) -> str:
        name = (
            await self._db.execute(
                sa.select(KnowledgeDocument.name).where(
                    KnowledgeDocument.id == UUID(located.resource_id)
                )
            )
        ).scalar_one_or_none()
        return name or "知识文档"

    async def _label_knowledge_folder(self, located: HostLocator) -> str:
        name = (
            await self._db.execute(
                sa.select(KnowledgeFolder.name).where(
                    KnowledgeFolder.id == UUID(located.resource_id)
                )
            )
        ).scalar_one_or_none()
        return name or "知识库文件夹"

    async def _label_global_knowledge(self, located: HostLocator) -> str:
        return GLOBAL_KNOWLEDGE_LABEL


#: 报表类型 → 中文展示名（NFR-5 全中文；取值域由 ``REPORT_HOST_IDS`` 锁死）。
REPORT_LABELS: dict[str, str] = {
    "balance_sheet": "资产负债表",
    "income_statement": "利润表",
    "cash_flow_statement": "现金流量表",
    "equity_statement": "所有者权益变动表",
    "cash_flow_supplement": "现金流量表补充资料",
    "impairment_provision": "资产减值准备表",
}

#: 宿主类型 → 资源类型（授权用；与 ``access._RESOURCE_BY_HOST`` 同源语义）。
_RESOURCE_BY_HOST: dict[HostType, ResourceType] = {
    HostType.workpaper: ResourceType.workpaper,
    HostType.note: ResourceType.note,
    HostType.report: ResourceType.report,
    HostType.knowledge_doc: ResourceType.knowledge_doc,
    HostType.knowledge_folder: ResourceType.knowledge_folder,
    HostType.global_knowledge: ResourceType.global_knowledge,
}


def _assert_bindings(
    host: HostRef, *, project_id: UUID | None, year: int | None
) -> str | None:
    """客户端断言 vs 服务端反查值一致性（Req 2.3 / Property 2）。

    只与**已反查出的非 None 值**比较：服务端解析不出年度时（``projects.audit_year`` 为空）
    不存在"不一致"，按 nullable 语义放过并在上下文里回传 None，而不是拿客户端值冒充权威。
    """
    if (
        host.project_id_assertion is not None
        and project_id is not None
        and host.project_id_assertion != project_id
    ):
        return AiChatDenialCode.host_context_mismatch.value
    if (
        host.year_assertion is not None
        and year is not None
        and host.year_assertion != year
    ):
        return AiChatDenialCode.host_context_mismatch.value
    return None
