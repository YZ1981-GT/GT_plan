"""AI 对话授权契约 · 服务端单一真源（Task 1）

Feature: dsh-agent-panel-integration
Requirements:
  - 2.1/2.4：宿主类型、资源类型、动作 capability 与拒绝语义只有一个服务端定义，
    mention / HostContext / history / clear / adopt / attachment / note / review /
    MCP 共用同一决策输入。
  - 2.2：角色只作动作上界，取值直接复用平台冻结的
    ``app.services.evidence_governance.role_capability_contract``，不在 AI 模块
    复制第二套角色算法。
  - 2.5：对外拒绝语义不可枚举（响应体由 ``wp_visibility.denial.ExternalNotFound`` 提供），
    内部真实拒绝码只进审计。
Design: "Components and Interfaces → 1. ResourceAccessResolver"（``AccessDecision``）
  与 "→ 2. HostContextResolver"（``HostType`` / ``HostRef``）。

本模块纯数据、无 IO、无副作用，便于在任何取数之前完成判定。

**Task 2 边界**：``HostType`` / ``HostRef`` 在此冻结取值与形状；``AuthorizedHostContext``
与各宿主的服务端反查 resolver 由 Task 2 在 ``host_context.py`` 实现（Req 2.3/3.x）。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from uuid import UUID

from app.services.evidence_governance.role_capability_contract import (
    Capability,
    is_permitted,
)
from app.services.wp_visibility.denial import DenialReason

__all__ = [
    "GLOBAL_KNOWLEDGE_HOST_ID",
    "REPORT_HOST_IDS",
    "HostType",
    "HostRef",
    "ResourceType",
    "coerce_uuid",
    "AiChatAction",
    "READ_CLASS_ACTIONS",
    "WRITE_CLASS_ACTIONS",
    "HOST_WRITE_ACTIONS",
    "KNOWLEDGE_WRITE_ACTIONS",
    "ACTION_CAPABILITIES",
    "AiChatDenialCode",
    "DENIAL_REASON_BY_CODE",
    "AccessDecision",
    "role_allows_action",
    "role_allowed_actions",
]


#: 无项目宿主（受限全局知识模式）的显式 sentinel —— 禁止用空字符串伪装有效 ID（Req 3.3）。
GLOBAL_KNOWLEDGE_HOST_ID = "global-knowledge"


def _report_host_ids() -> frozenset[str]:
    """报表宿主的稳定 ID 取值域（Task 2 / Req 3.2）。

    报表实例由 ``(project, year, report_type)`` 唯一确定，**没有** instance UUID，
    因此其稳定 ID 是 report type 字面量。取值域直接派生自平台既有
    ``FinancialReportType`` 枚举 —— 不在 AI 模块写第二份报表类型清单。
    """
    from app.models.report_models import FinancialReportType

    return frozenset(t.value for t in FinancialReportType)


#: 报表宿主允许的稳定 ID 集合（唯一真源见 ``_report_host_ids``）。
REPORT_HOST_IDS: frozenset[str] = _report_host_ids()


def coerce_uuid(value: object) -> UUID | None:
    """把任意输入归一为 UUID，非法输入返回 None（不抛异常，避免泄露资源形态）。

    ``access`` 与 ``host_context`` 共用同一实现，禁止各自复制一份宽松解析。
    """
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


class HostType(str, enum.Enum):
    """AI 面板宿主类型（后端枚举约束，Req 3.1）。"""

    workpaper = "workpaper"
    note = "note"
    report = "report"
    knowledge_doc = "knowledge_doc"
    knowledge_folder = "knowledge_folder"
    global_knowledge = "global_knowledge"


@dataclass(frozen=True)
class HostRef:
    """客户端可提交的最小宿主标识：类型 + 稳定 ID + 可选断言。

    ``project_id_assertion`` / ``year_assertion`` 只作一致性断言，不作权威值
    （权威反查由 Task 2 的 HostContextResolver 完成，Req 2.3）。
    """

    type: HostType
    id: str
    project_id_assertion: UUID | None = None
    year_assertion: int | None = None


class ResourceType(str, enum.Enum):
    """授权判定的资源类型（比 HostType 多出非宿主资源：地址坐标、会话附件、会话本体）。"""

    workpaper = "workpaper"
    note = "note"
    report = "report"
    knowledge_doc = "knowledge_doc"
    knowledge_folder = "knowledge_folder"
    global_knowledge = "global_knowledge"
    # 尚未接入的资源域：``ResourceAccessResolver`` 对其 **fail-closed**（Task 22 接地址坐标、
    # Task 16 接会话附件时才注册对应 authorizer）。列在此处是为了让"未注册即拒绝"可被断言，
    # 而不是让调用方以为已支持。
    address = "address"
    attachment = "attachment"


class AiChatAction(str, enum.Enum):
    """AI 对话动作 capability（Task 1 冻结的九个动作）。"""

    read = "read"
    search = "search"
    history = "history"
    clear = "clear"
    upload = "upload"
    note_create = "note-create"
    adopt = "adopt"
    review = "review"
    agent_run = "agent-run"


#: 读类动作：不要求额外角色 capability，允许集合完全由资源级权限决定。
READ_CLASS_ACTIONS: frozenset[AiChatAction] = frozenset(
    {
        AiChatAction.read,
        AiChatAction.search,
        AiChatAction.history,
        AiChatAction.clear,
        AiChatAction.review,
    }
)

#: 写类动作：资源级权限之上**再**要求角色 capability 上界（Req 2 角色表）。
WRITE_CLASS_ACTIONS: frozenset[AiChatAction] = frozenset(
    {
        AiChatAction.upload,
        AiChatAction.note_create,
        AiChatAction.adopt,
        AiChatAction.agent_run,
    }
)

#: 写**宿主资源**的动作（采纳把 AI 正文写回宿主）→ 宿主授权用写动作过门，不用读动作。
HOST_WRITE_ACTIONS: frozenset[AiChatAction] = frozenset({AiChatAction.adopt})

#: 写**知识资产**的动作（项目笔记转存）→ 目标文件夹须过 KnowledgeAccessPolicy 创建权。
KNOWLEDGE_WRITE_ACTIONS: frozenset[AiChatAction] = frozenset({AiChatAction.note_create})


#: 动作 → 平台既有 capability 集合（**全部** permitted 才通过；空集 = 读类动作不额外要求）。
#:
#: 角色上界的唯一真源是冻结的 ``role_capability_contract.CAPABILITY_MATRIX``；
#: 本表只做"AI 动作 → 既有 capability"的声明式映射，不新建第二套角色矩阵（Req 2.2）。
#: 由该映射推导出的五角色结果与 Requirements §2 角色表一致：
#:   审计助理/现场经理/业务合伙人 可上传附件、创建项目笔记、发起采纳、驱动 Agent；
#:   质量控制复核合伙人/EQCR 技术复核人默认只读（写类动作全部被拒）。
ACTION_CAPABILITIES: dict[AiChatAction, frozenset[str]] = {
    AiChatAction.read: frozenset(),
    AiChatAction.search: frozenset(),
    AiChatAction.history: frozenset(),
    AiChatAction.clear: frozenset(),
    AiChatAction.review: frozenset(),
    AiChatAction.upload: frozenset(
        {Capability.ai_generate.value, Capability.attachment_create.value}
    ),
    AiChatAction.note_create: frozenset({Capability.ai_generate.value}),
    AiChatAction.adopt: frozenset(
        {Capability.ai_generate.value, Capability.ai_confirm.value}
    ),
    AiChatAction.agent_run: frozenset({Capability.ai_generate.value}),
}


class AiChatDenialCode(str, enum.Enum):
    """AI 侧稳定拒绝码（对外统一非枚举响应；本码只进审计与诊断日志）。"""

    access_denied = "access_denied"
    resource_not_found = "resource_not_found"
    cross_project = "cross_project"
    out_of_scope = "out_of_scope"
    action_denied = "action_denied"
    role_capability_denied = "role_capability_denied"
    unsupported_resource = "unsupported_resource"
    host_context_mismatch = "host_context_mismatch"
    invalid_resource_id = "invalid_resource_id"
    resolver_error = "resolver_error"
    # ── Task 7 采纳来源判定（``ai_chat.adopt``）────────────────────────────
    #: 消息存在但不是可采纳来源（非 assistant / 非 completed / 正文为空）。
    adopt_source_unusable = "adopt_source_unusable"
    #: 服务端 ``content_hash`` 缺失或与正文重算值不符 ⇒ 来源不可证明（Req 8.6）。
    adopt_content_tampered = "adopt_content_tampered"


#: AI 拒绝码 → 平台 ``wp_access_security_outbox.reason``（该列有 CHECK 约束，取值必须落在
#: ``DenialReason`` 内）。映射保持"内部真实原因可追溯"，同时不新增 outbox 取值域。
DENIAL_REASON_BY_CODE: dict[AiChatDenialCode, DenialReason] = {
    AiChatDenialCode.access_denied: DenialReason.not_delegated,
    AiChatDenialCode.resource_not_found: DenialReason.not_found,
    AiChatDenialCode.cross_project: DenialReason.cross_project,
    AiChatDenialCode.out_of_scope: DenialReason.out_of_scope,
    AiChatDenialCode.action_denied: DenialReason.action_denied,
    AiChatDenialCode.role_capability_denied: DenialReason.action_denied,
    AiChatDenialCode.unsupported_resource: DenialReason.not_found,
    AiChatDenialCode.host_context_mismatch: DenialReason.binding_conflict,
    AiChatDenialCode.invalid_resource_id: DenialReason.not_found,
    AiChatDenialCode.resolver_error: DenialReason.not_delegated,
    AiChatDenialCode.adopt_source_unusable: DenialReason.not_found,
    AiChatDenialCode.adopt_content_tampered: DenialReason.binding_conflict,
}

assert set(DENIAL_REASON_BY_CODE) == set(AiChatDenialCode), (
    "每个 AI 拒绝码必须有 outbox reason 映射，否则 denial audit 在运行时 KeyError："
    f"缺映射 {sorted(c.value for c in set(AiChatDenialCode) - set(DENIAL_REASON_BY_CODE))}"
)


@dataclass(frozen=True)
class AccessDecision:
    """单次授权判定的不可变结果（Design "1. ResourceAccessResolver"）。

    - ``allowed``：是否允许本次 (资源, 动作)。
    - ``principal_id``：判定主体（当前用户）。
    - ``project_id``：判定所绑定的项目；全局知识模式为 None（不得伪造空 UUID）。
    - ``cycle_scope``：``scope_cycles`` 上界（Admin 恒空集 = 不受 scope 限制）。
    - ``allowed_actions``：当前主体在该资源上**实际**允许的动作集合（角色上界 ∩ 资源权限）。
    - ``denial_code``：拒绝时的内部真实原因；允许时为 None。
    - ``scope_unbounded``：True 表示 scope 上界不适用（Admin），供调用方区分"空集=无任何循环"
      与"空集=不受限"两种语义，避免下游误裁剪。

    决策对象**不含** label / 名称 / 正文 / 摘要，确保拒绝路径上不存在可泄露字段。
    """

    allowed: bool
    principal_id: UUID
    project_id: UUID | None
    cycle_scope: frozenset[str] = frozenset()
    allowed_actions: frozenset[str] = frozenset()
    denial_code: str | None = None
    scope_unbounded: bool = False
    detail: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:  # noqa: D401 — 契约一致性守卫
        if self.allowed and self.denial_code is not None:
            raise ValueError("allowed 决策不得携带 denial_code")
        if not self.allowed and not self.denial_code:
            raise ValueError("拒绝决策必须携带内部 denial_code（供审计）")
        if not self.allowed and self.allowed_actions:
            raise ValueError("拒绝决策不得携带 allowed_actions")


def role_allows_action(role: str | None, action: AiChatAction) -> bool:
    """角色上界判定：该角色是否**可能**执行该动作（资源权限另判）。

    未知角色 fail-closed（``is_permitted`` 对未登记 actor 默认 deny）。读类动作没有
    capability 要求，但仍要求角色是平台已登记角色，避免未知角色拿到读权限。
    """
    if not role:
        return False
    caps = ACTION_CAPABILITIES.get(action)
    if caps is None:
        return False  # 未登记动作 → 默认拒绝
    if not caps:
        # 读类动作：只要求角色是已登记 actor（用任一 capability 探测矩阵行是否存在）。
        from app.services.evidence_governance.role_capability_contract import (
            CAPABILITY_MATRIX,
        )

        return role in CAPABILITY_MATRIX
    return all(is_permitted(role, cap) for cap in caps)


def role_allowed_actions(role: str | None) -> frozenset[AiChatAction]:
    """该角色的动作上界全集（不含资源级权限，仅角色维度）。"""
    return frozenset(a for a in AiChatAction if role_allows_action(role, a))
