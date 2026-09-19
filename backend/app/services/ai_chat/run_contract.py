"""Chat Run typed contract · 服务端单一真源（Task 4）

Feature: dsh-agent-panel-integration
Requirements:
  - 4.1：对话使用两阶段 API —— 先创建幂等 Chat Run，再订阅该 run 的事件。本模块定义
    第一阶段的请求/响应形状与第二阶段事件的负载形状。
  - 4.2：``ChatRunRequest`` 只接收会话标识、query、mentions、attachment IDs、review
    mode 与客户端生成的 idempotency key；**拒绝** engine / 权限 scope / 资源正文 /
    客户端 message content 等越权字段（见 :data:`PRIVILEGED_REQUEST_FIELDS`）。
  - 4.3：``ChatEventType`` 是 ChatEvent 的**单一真源**，至少含 10 类事件。
  - 4.4：每个 ChatEvent 携带单调 event ID、run/session/request ID、type 与服务端时间戳；
    与消息相关的事件另带 server-issued ``message_id``（见 :data:`MESSAGE_BOUND_EVENT_TYPES`）。
  - 4.5：一个 run 只能进入一个终态；终态与 terminal event 一一对应
    （:data:`TERMINAL_EVENT_BY_RUN_STATUS`），状态迁移受
    :data:`ALLOWED_RUN_TRANSITIONS` 约束。
  - 10.2：engine 消费统一 ``ChatRunRequest`` 并产出统一 ``ChatEvent``，而不是裸字符串流。
Design: "Components and Interfaces → 3. API Surface"（端点清单 + ``ChatRunRequest``
  与响应形状）、"→ 4. Typed Event Contract"（``ChatEventType`` / ``ChatEvent`` /
  状态机 / 稳定 error code 清单）、"→ 12. Engine Contract"（``EngineCapabilities``）。
Properties: 6（会话与 Run 并发幂等）、7（Run 唯一终态）

## 为什么取值域都从既有真源派生

本模块**不新建**第二套宿主/资源/状态枚举：

- ``HostType`` / ``HostRef`` / ``ResourceType`` / ``AiChatDenialCode`` 来自
  :mod:`app.services.ai_chat.contracts`（Task 1/2 冻结）；
- ``ChatRunStatus`` / ``CHAT_RUN_TERMINAL_STATUSES`` / ``ChatEngineName`` 来自
  :mod:`app.models.ai_models`（V147 的 CHECK 约束是它们的投影）。

新增的只有本 Task 真正拥有的东西：事件类型、事件形状、对外稳定 error code、
engine capability 形状、请求/响应 schema 与状态迁移表。

## OpenAPI 暴露（NFR-2：前端不手抄第二份常量）

``POST /api/ai-chat/runs`` 以 :class:`ChatRunRequest` 为请求体、
:class:`ChatRunAccepted` 为 ``response_model``。后者内嵌
:class:`ChatEvent`（``run_started``）、:class:`EngineCapabilities`、
``ChatRunStatus`` 与 :class:`ChatErrorCode`，因此这五类前端需要的类型全部进入
OpenAPI ``components.schemas``，可直接生成 TS 类型或由运行时契约测试对账。
"""

from __future__ import annotations

import enum
import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.ai_models import (
    CHAT_RUN_TERMINAL_STATUSES,
    ChatEngineName,
    ChatRunStatus,
)
from app.services.ai_chat.contracts import (
    AiChatDenialCode,
    HostRef,
    ResourceType,
)

logger = logging.getLogger(__name__)

__all__ = [
    "CONTRACT_VERSION",
    "ChatEventType",
    "TERMINAL_EVENT_TYPES",
    "MESSAGE_BOUND_EVENT_TYPES",
    "TERMINAL_EVENT_BY_RUN_STATUS",
    "NON_TERMINAL_RUN_STATUSES",
    "ALLOWED_RUN_TRANSITIONS",
    "ChatErrorCode",
    "ERROR_MESSAGE_ZH",
    "ERROR_CODE_BY_DENIAL",
    "EVENT_ID_WIDTH",
    "RUN_STARTED_EVENT_SEQ",
    "format_event_id",
    "event_seq",
    "ChatEvent",
    "EngineCapabilities",
    "CAPABILITIES_BY_ENGINE",
    "capabilities_for",
    "resolve_engine_name",
    "MENTION_RESOURCE_TYPES",
    "MAX_MENTIONS_PER_RUN",
    "MAX_ATTACHMENTS_PER_RUN",
    "MAX_QUERY_CHARS",
    "PRIVILEGED_REQUEST_FIELDS",
    "MentionRef",
    "ChatRunRequest",
    "ChatRunAccepted",
    "RUN_EVENTS_URL_TEMPLATE",
    "run_events_url",
    "can_transition",
]

#: 契约版本。事件类型、事件形状或请求 schema 发生**不兼容**变更必须升版本，
#: 否则新旧前端对同一条流各自解读（Req 4.3 的单一真源就形同虚设）。
CONTRACT_VERSION = "v1"


# ---------------------------------------------------------------------------
# 事件类型与状态机（Req 4.3 / 4.5）
# ---------------------------------------------------------------------------


class ChatEventType(str, enum.Enum):
    """ChatEvent 类型的单一真源（Req 4.3 的十类）。

    engine（native / DSH）产出的一切对外信号都必须落在本枚举内 —— 不允许某个 engine
    私自新增事件字符串，否则前端只能靠猜（Req 10.2：两种 engine 遵守同一协议）。
    """

    run_started = "run_started"
    context_ready = "context_ready"
    citation = "citation"
    delta = "delta"
    tool_started = "tool_started"
    tool_finished = "tool_finished"
    quota = "quota"
    error = "error"
    cancelled = "cancelled"
    done = "done"


#: 终态事件：一个 run 恰好出现其中一个（Req 4.5 / Property 7）。
TERMINAL_EVENT_TYPES: frozenset[ChatEventType] = frozenset(
    {ChatEventType.done, ChatEventType.error, ChatEventType.cancelled}
)

#: 与消息绑定的事件：必须携带 server-issued ``message_id``（Req 4.4 后半句）。
#:
#: ``delta`` / ``citation`` 是往某条 assistant 消息上追加内容与引用；``done`` 是该消息
#: 定稿。三者缺 ``message_id`` 前端就无法把流式片段挂到正确消息上（多轮并发时会串）。
#: ``run_started`` / ``context_ready`` / ``tool_*`` / ``quota`` / ``error`` /
#: ``cancelled`` 与具体消息无关 —— 尤其 ``error`` / ``cancelled`` 时**不存在** completed
#: assistant 消息（Req 4.5），要求它们带 message_id 反而会逼出一条假消息。
MESSAGE_BOUND_EVENT_TYPES: frozenset[ChatEventType] = frozenset(
    {ChatEventType.delta, ChatEventType.citation, ChatEventType.done}
)

#: run 终态 → 对应 terminal event type。**一一对应**，两侧都不许单独增删。
#:
#: 该映射存在的意义：把"数据库状态"与"对外事件"钉在一起。若分别在两处写死，就可能
#: 出现 run 落库 ``error`` 而流里发 ``done``（Property 7 要防的正是这种）。
TERMINAL_EVENT_BY_RUN_STATUS: dict[ChatRunStatus, ChatEventType] = {
    ChatRunStatus.done: ChatEventType.done,
    ChatRunStatus.error: ChatEventType.error,
    ChatRunStatus.cancelled: ChatEventType.cancelled,
}

if set(TERMINAL_EVENT_BY_RUN_STATUS) != set(CHAT_RUN_TERMINAL_STATUSES) or set(
    TERMINAL_EVENT_BY_RUN_STATUS.values()
) != set(TERMINAL_EVENT_TYPES):
    raise RuntimeError(  # pragma: no cover — import 期契约，漂移即启动失败
        "run 终态与 terminal event 必须一一对应："
        f"状态侧 {sorted(s.value for s in TERMINAL_EVENT_BY_RUN_STATUS)} vs "
        f"{sorted(s.value for s in CHAT_RUN_TERMINAL_STATUSES)}；"
        f"事件侧 {sorted(e.value for e in TERMINAL_EVENT_BY_RUN_STATUS.values())} vs "
        f"{sorted(e.value for e in TERMINAL_EVENT_TYPES)}"
    )

#: 非终态集合（可继续接收业务事件）。由终态集合取补，不手写第二份清单。
NON_TERMINAL_RUN_STATUSES: frozenset[ChatRunStatus] = frozenset(
    s for s in ChatRunStatus if s not in CHAT_RUN_TERMINAL_STATUSES
)

#: 合法状态迁移（Design "4. Typed Event Contract" 的状态图）。
#:
#: ``queued → error`` 是刻意允许的：队列满、engine 不可用、local-only 违规等失败发生在
#: 真正开跑之前，此时必须能直接进 error 终态并给出 typed error（Req 10.5 / 12.4），
#: 而不是先假装 running 再失败。
#:
#: 终态的出边是**空集** —— 这正是"终态恰好一个"的形式化表述：任何从终态出发的迁移
#: 在 :func:`can_transition` 处即被拒绝，不依赖调用方自觉。
ALLOWED_RUN_TRANSITIONS: dict[ChatRunStatus, frozenset[ChatRunStatus]] = {
    ChatRunStatus.queued: frozenset(
        {ChatRunStatus.running, ChatRunStatus.cancelled, ChatRunStatus.error}
    ),
    ChatRunStatus.running: frozenset(
        {
            ChatRunStatus.done,
            ChatRunStatus.error,
            ChatRunStatus.cancelled,
            ChatRunStatus.interrupted,
        }
    ),
    ChatRunStatus.interrupted: frozenset({ChatRunStatus.queued, ChatRunStatus.error}),
    ChatRunStatus.done: frozenset(),
    ChatRunStatus.error: frozenset(),
    ChatRunStatus.cancelled: frozenset(),
}


def can_transition(current: ChatRunStatus, new: ChatRunStatus) -> bool:
    """``current → new`` 是否为合法迁移（终态出边为空 ⇒ 恒 False）。"""
    return new in ALLOWED_RUN_TRANSITIONS.get(current, frozenset())


# ---------------------------------------------------------------------------
# 稳定 error code（Design "4. Typed Event Contract" 末尾清单 / Req 12.5）
# ---------------------------------------------------------------------------


class ChatErrorCode(str, enum.Enum):
    """对外稳定 error code。用户看中文消息，内部 exception 细节只进受控日志。

    与 :class:`~app.services.ai_chat.contracts.AiChatDenialCode` 的分工：
    后者是**内部**真实拒绝原因（只进审计），本枚举是**对外**可见码。两者通过
    :data:`ERROR_CODE_BY_DENIAL` 显式桥接 —— 多个内部拒绝原因刻意塌到同一个
    ``access_denied``，以维持"不泄露资源是否存在"的不可枚举语义（Req 2.5）。
    """

    access_denied = "access_denied"
    host_context_mismatch = "host_context_mismatch"
    context_build_failed = "context_build_failed"
    semantic_unavailable = "semantic_unavailable"
    ocr_unavailable = "ocr_unavailable"
    engine_unavailable = "engine_unavailable"
    local_only_violation = "local_only_violation"
    rate_limited = "rate_limited"
    tool_budget_exceeded = "tool_budget_exceeded"
    attachment_invalid = "attachment_invalid"
    run_cancelled = "run_cancelled"
    run_interrupted = "run_interrupted"
    adopt_log_failed = "adopt_log_failed"


#: error code → 中文用户消息（NFR-5：可见状态全中文并给出可执行下一步）。
ERROR_MESSAGE_ZH: dict[ChatErrorCode, str] = {
    ChatErrorCode.access_denied: "当前账号无权访问该资源，请联系项目负责人调整权限范围。",
    ChatErrorCode.host_context_mismatch: "页面上下文与服务端记录不一致，请刷新页面后重试。",
    ChatErrorCode.context_build_failed: "无法加载当前文档上下文，请稍后重试。",
    ChatErrorCode.semantic_unavailable: "语义检索服务当前不可用，本轮未使用语义匹配结果。",
    ChatErrorCode.ocr_unavailable: "OCR 服务当前不可用，请稍后重新识别附件。",
    ChatErrorCode.engine_unavailable: "AI 引擎当前不可用，请稍后重试或联系管理员。",
    ChatErrorCode.local_only_violation: "检测到非本地模型路由，已阻止本次执行。",
    ChatErrorCode.rate_limited: "请求过于频繁，请稍候再试；您的输入已保留。",
    ChatErrorCode.tool_budget_exceeded: "本次执行的取数配额已用尽，请缩小问题范围后重试。",
    ChatErrorCode.attachment_invalid: "附件不可用或不属于当前会话，请重新上传。",
    ChatErrorCode.run_cancelled: "本次回答已取消。",
    ChatErrorCode.run_interrupted: "服务重启导致本次回答中断，请重新提问。",
    ChatErrorCode.adopt_log_failed: "采纳留痕写入失败，内容未进入确认流，请重试。",
}

#: 内部真实拒绝码 → 对外稳定 error code（**全覆盖**，未登记即缺口）。
#:
#: 除 ``host_context_mismatch``（Req 2.3 明确要求可辨识）外，其余一律塌到
#: ``access_denied``：把 ``resource_not_found`` / ``cross_project`` / ``out_of_scope``
#: 原样透出去，等于给攻击者一个"资源是否存在 / 属于哪个项目"的枚举探针。
ERROR_CODE_BY_DENIAL: dict[AiChatDenialCode, ChatErrorCode] = {
    AiChatDenialCode.access_denied: ChatErrorCode.access_denied,
    AiChatDenialCode.resource_not_found: ChatErrorCode.access_denied,
    AiChatDenialCode.cross_project: ChatErrorCode.access_denied,
    AiChatDenialCode.out_of_scope: ChatErrorCode.access_denied,
    AiChatDenialCode.action_denied: ChatErrorCode.access_denied,
    AiChatDenialCode.role_capability_denied: ChatErrorCode.access_denied,
    AiChatDenialCode.unsupported_resource: ChatErrorCode.access_denied,
    AiChatDenialCode.host_context_mismatch: ChatErrorCode.host_context_mismatch,
    AiChatDenialCode.invalid_resource_id: ChatErrorCode.access_denied,
    AiChatDenialCode.resolver_error: ChatErrorCode.access_denied,
    # 采纳来源判定（Task 7）：对外仍是不可枚举拒绝 —— "消息存在但不可采纳"与"哈希不符"
    # 都不该告诉客户端具体哪一条不成立（否则可以拿它探测哪些 message ID 真实存在）。
    # ``adopt_log_failed`` 只保留给**写入路径**失败（Req 8.7），不复用到来源判定上。
    AiChatDenialCode.adopt_source_unusable: ChatErrorCode.access_denied,
    AiChatDenialCode.adopt_content_tampered: ChatErrorCode.access_denied,
}


# ---------------------------------------------------------------------------
# 事件 ID（Req 4.4：单调）
# ---------------------------------------------------------------------------

#: event ID 的零填充宽度。零填充让字符串比较与整数比较**同序**，于是
#: ``Last-Event-ID`` 断点续传既可以按字符串排序也可以按整数排序，不会因为
#: "10" < "9" 这种字典序陷阱丢事件或重放事件（Req 4.8 / Property 9）。
EVENT_ID_WIDTH = 12

#: ``run_started`` 的固定序号。它必须**确定性可复现** —— 重复提交同一 idempotency key
#: 时服务端返回原 run 与同一条 ``run_started``（Req 4.6），若用递增计数器生成，
#: 第二次请求就会拿到不同 event ID，客户端会当成新事件重复渲染。
RUN_STARTED_EVENT_SEQ = 1


def format_event_id(seq: int) -> str:
    """把单调序号格式化为 event ID（零填充定宽）。"""
    if seq < 1:
        raise ValueError(f"event 序号必须从 1 开始，收到 {seq}")
    return str(seq).zfill(EVENT_ID_WIDTH)


def event_seq(event_id: str) -> int:
    """从 event ID 反解序号（``Last-Event-ID`` 续传用）。"""
    return int(event_id)


# ---------------------------------------------------------------------------
# ChatEvent（Req 4.3 / 4.4）
# ---------------------------------------------------------------------------


class ChatEvent(BaseModel):
    """Chat Run 对外事件。engine 产出它，SSE 逐条下发，前端按 ``type`` 分派。

    ``payload`` 是类型专属负载（delta 的文本片段、context_ready 的 manifest、
    error 的 ``code``/``message`` 等）。刻意保持为开放 dict：把十类事件的负载各写成
    一个模型会让 engine 每加一个字段都要改协议层，而前端本就按 type 分派。
    """

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(
        ..., min_length=1, max_length=64, description="单调事件 ID（零填充定宽）"
    )
    run_id: UUID = Field(..., description="所属 run")
    session_id: UUID = Field(..., description="所属会话")
    request_id: UUID = Field(..., description="创建该 run 的请求 ID（贯穿日志与审计）")
    type: ChatEventType = Field(..., description="事件类型")
    timestamp: datetime = Field(..., description="服务端时间戳")
    message_id: UUID | None = Field(
        None, description="与消息相关的事件必须携带；其余为 null"
    )
    payload: dict[str, Any] = Field(default_factory=dict, description="类型专属负载")

    @model_validator(mode="after")
    def _message_bound_events_carry_message_id(self) -> ChatEvent:
        """Req 4.4：与消息相关的事件必须带 server-issued ``message_id``。

        这条校验放在模型上而不是靠调用方自觉 —— 少带 message_id 的 delta 在单轮对话里
        看不出问题（前端会挂到"当前消息"上），只有并发多轮时才串消息，属于最难复现的一类。
        """
        if self.type in MESSAGE_BOUND_EVENT_TYPES and self.message_id is None:
            raise ValueError(
                f"{self.type.value} 是消息相关事件，必须携带服务端签发的 message_id"
            )
        return self

    @property
    def is_terminal(self) -> bool:
        return self.type in TERMINAL_EVENT_TYPES


# ---------------------------------------------------------------------------
# EngineCapabilities（Design "12. Engine Contract" / Req 10.3）
# ---------------------------------------------------------------------------


class EngineCapabilities(BaseModel):
    """engine capability manifest（Req 10.3 的八项）。

    前端据此禁用不支持的入口并显示中文原因（Req 10.4）；创建 run 时快照写入
    ``ai_chat_runs.capability_snapshot``，使"这次执行当时能做什么"可事后追溯。
    """

    model_config = ConfigDict(frozen=True)

    streaming: bool = Field(..., description="是否支持流式增量输出")
    tools: bool = Field(..., description="是否支持工具调用")
    subagents: bool = Field(..., description="是否支持子 Agent")
    max_context: int = Field(..., gt=0, description="上下文 token 上限")
    structured_output: bool = Field(..., description="是否支持结构化输出")
    local_only: bool = Field(..., description="是否保证全本地执行")
    review_mode: bool = Field(..., description="是否支持底稿复核模式")
    attachments: bool = Field(..., description="是否支持会话附件")


#: engine → capability manifest 基线。
#:
#: 🔴 这里描述的是**引擎本身的能力形态**（native 是本地流式单体模型，无工具无子 Agent；
#: DSH 是本地多步 Agent），不是"平台功能做到哪一步"。Task 6（NativeEngine）与
#: Task 28（DshEngine）落地后，``ChatEngine.capabilities()`` 必须返回与此**相等**的
#: manifest 或直接返回本表项 —— 两处各写一份就会出现"声明支持而实际不支持"。
CAPABILITIES_BY_ENGINE: dict[ChatEngineName, EngineCapabilities] = {
    ChatEngineName.native: EngineCapabilities(
        streaming=True,
        tools=False,
        subagents=False,
        max_context=32768,
        structured_output=False,
        local_only=True,
        review_mode=True,
        attachments=True,
    ),
    ChatEngineName.dsh: EngineCapabilities(
        streaming=True,
        tools=True,
        subagents=True,
        max_context=32768,
        structured_output=True,
        local_only=True,
        review_mode=True,
        attachments=True,
    ),
}


def capabilities_for(engine: ChatEngineName) -> EngineCapabilities:
    """取该 engine 的 capability manifest（未登记 engine fail-closed）。"""
    caps = CAPABILITIES_BY_ENGINE.get(engine)
    if caps is None:  # pragma: no cover — 枚举全覆盖时不可达；保留以防新增 engine 漏登记
        raise KeyError(f"engine {engine!r} 未登记 capability manifest")
    return caps


def resolve_engine_name() -> ChatEngineName:
    """服务端决定 engine（Req 10.1：默认 native，客户端**不可**通过请求体覆盖）。

    取值只来自服务端配置；配置缺失或取值非法时回落 ``native`` —— native 是受控的
    本地链路，"看不懂配置就用最安全的那条"比"猜一个"正确。

    Task 6 的 ``resolve_engine()`` 在此之上叠加 feature flag 与项目 allowlist；
    Task 30 再接 local-only 自检。本函数刻意不读任何请求字段，
    ``ChatRunRequest`` 里也不存在 engine 字段（:data:`PRIVILEGED_REQUEST_FIELDS`）。
    """
    from app.core.config import settings

    raw = settings.AI_CHAT_ENGINE
    if not raw:
        return ChatEngineName.native
    try:
        return ChatEngineName(str(raw))
    except ValueError:
        logger.warning("AI_CHAT_ENGINE=%r 非法，回落 native", raw)
        return ChatEngineName.native


# ---------------------------------------------------------------------------
# ChatRunRequest（Req 4.2）
# ---------------------------------------------------------------------------

#: 可被 ``@`` 引用的资源类型（Design "7. …Mention…" 的七类）。
#:
#: 取值域从既有 :class:`ResourceType` **取差集**得到，而不是另写一份 ``MentionType``
#: 枚举 —— 后者一旦与 ResourceType 漂移，"mention 授权"与"资源授权"就会判到两套取值上。
#: ``global_knowledge`` 是宿主模式而非可引用资源，故排除。
MENTION_RESOURCE_TYPES: frozenset[ResourceType] = frozenset(ResourceType) - {
    ResourceType.global_knowledge
}

#: 单次 run 的 mention / 附件数量上限（NFR-4：所有输入都要有容量上限）。
#: Task 12 接入服务端配额配置后改为读配置；此处是协议层硬上界，防止一次请求撑爆预算。
MAX_MENTIONS_PER_RUN = 20
MAX_ATTACHMENTS_PER_RUN = 10
MAX_QUERY_CHARS = 4000

#: 客户端**不得**提交的字段名（Req 4.2 / NFR-3 数据最小化）。
#:
#: 四类越权：
#:   1. engine 与 capability —— 只由服务端配置与 feature flag 决定（Req 10.1）；
#:   2. 权限 scope / allowed actions / permission binding —— 由授权层反查（Req 2.x）；
#:   3. 资源正文与上下文（doc_excerpt / knowledge_hits / ocr_text / context …）
#:      —— 服务端授权后自行加载（Req 5.5）；
#:   4. 消息正文（content / message / messages / assistant_content …）
#:      —— assistant 正文以服务端签发的 message 为权威（Req 8.1）。
#:
#: ``extra="forbid"`` 已经会拒绝一切未声明字段；本清单额外存在的意义是给出
#: **点名的中文错误消息**，并让"哪些字段属于越权"成为可被守卫断言的显式声明。
PRIVILEGED_REQUEST_FIELDS: frozenset[str] = frozenset(
    {
        # ① engine / capability
        "engine",
        "engine_name",
        "engine_preference",
        "capabilities",
        "capability_snapshot",
        "model",
        "model_name",
        # ② 权限 scope
        "scope",
        "scopes",
        "extra_scopes",
        "cycle_scope",
        "scope_cycles",
        "allowed_actions",
        "permission_binding",
        "role",
        "actor_id",
        # ③ 资源正文 / 上下文
        "context",
        "doc_excerpt",
        "knowledge_hits",
        "citations",
        "context_manifest",
        "ocr_text",
        "attachment_content",
        "attachments",
        # ④ 消息正文
        "content",
        "message",
        "messages",
        "message_text",
        "assistant_content",
        "history",
    }
)

#: 递归扫描越权字段的最大深度（请求体只有一层嵌套；给足余量即可，防御畸形深层负载）。
_PRIVILEGED_SCAN_MAX_DEPTH = 6


def _scan_privileged(node: Any, depth: int = 0) -> set[str]:
    """递归找出请求体里出现的越权字段名。

    必须递归：把 ``content`` 藏在 ``host`` 或 ``mentions[0]`` 里同样是越权提交，
    而 pydantic 对嵌套 stdlib dataclass 默认忽略多余键 —— 只查顶层会漏。
    """
    if depth > _PRIVILEGED_SCAN_MAX_DEPTH:
        return set()
    found: set[str] = set()
    if isinstance(node, Mapping):
        for key, value in node.items():
            if isinstance(key, str) and key in PRIVILEGED_REQUEST_FIELDS:
                found.add(key)
            found |= _scan_privileged(value, depth + 1)
    elif isinstance(node, (list, tuple, set)):
        for item in node:
            found |= _scan_privileged(item, depth + 1)
    return found


class MentionRef(BaseModel):
    """客户端提交的 mention：**只有**类型与稳定 ID。

    Req 5.5：label 与正文一律由服务端在当前 HostContext 下重新授权后加载，
    客户端提交的任何展示性字段都不可信 —— 所以这里连 ``label`` 字段都不存在，
    而不是"接收但忽略"（后者会让前端以为自己传的 label 会被用上）。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: ResourceType = Field(..., description="被引用资源的类型")
    id: str = Field(..., min_length=1, max_length=128, description="资源稳定 ID")

    @field_validator("type")
    @classmethod
    def _must_be_mentionable(cls, value: ResourceType) -> ResourceType:
        if value not in MENTION_RESOURCE_TYPES:
            raise ValueError(
                f"{value.value} 不是可引用资源类型（可选：" 
                f"{sorted(t.value for t in MENTION_RESOURCE_TYPES)}）"
            )
        return value


class ChatRunRequest(BaseModel):
    """创建 Chat Run 的请求体（Design "3. API Surface"）。

    ``extra="forbid"`` + :func:`_scan_privileged` 共同实现 Req 4.2 的"拒绝越权字段"：
    前者兜住一切未声明字段，后者对已知越权字段给出点名的中文原因。
    """

    model_config = ConfigDict(extra="forbid")

    host: HostRef = Field(
        ...,
        description="宿主引用（类型 + 稳定 ID + 可选断言）；项目/年度由服务端反查",
    )
    query: str = Field(
        ..., min_length=1, max_length=MAX_QUERY_CHARS, description="用户提问"
    )
    idempotency_key: UUID = Field(..., description="客户端生成的幂等键")
    session_id: UUID | None = Field(
        None, description="已知的服务端会话 ID；与服务端定位结果不一致则拒绝"
    )
    mentions: list[MentionRef] = Field(
        default_factory=list, max_length=MAX_MENTIONS_PER_RUN, description="显式引用"
    )
    attachment_ids: list[UUID] = Field(
        default_factory=list,
        max_length=MAX_ATTACHMENTS_PER_RUN,
        description="会话附件 ID（正文与 OCR 由服务端按 owner/session 授权后读取）",
    )
    review_mode: bool = Field(False, description="是否启用底稿复核模式")
    sheet_name: str | None = Field(
        None, max_length=200, description="复核模式的目标 sheet"
    )

    @model_validator(mode="before")
    @classmethod
    def _reject_privileged_fields(cls, data: Any) -> Any:
        found = sorted(_scan_privileged(data))
        if found:
            raise ValueError(
                "请求体包含服务端专属字段，已拒绝："
                + "、".join(found)
                + "。engine、权限范围、资源正文与消息正文一律由服务端解析，"
                "客户端只提交稳定 ID 与用户输入。"
            )
        return data

    def mention_pairs(self) -> Sequence[tuple[ResourceType, str]]:
        """交给授权层逐项复核的最小标识对（不含任何客户端展示字段）。"""
        return tuple((m.type, m.id) for m in self.mentions)


# ---------------------------------------------------------------------------
# 响应（Design "3. API Surface" 的响应形状）
# ---------------------------------------------------------------------------

#: 事件订阅 URL 模板。Task 5 的 ``GET /runs/{run_id}/events`` 必须复用它，
#: 否则响应里给的地址与真实路由不一致（前端拿到一个 404 的 URL）。
RUN_EVENTS_URL_TEMPLATE = "/api/ai-chat/runs/{run_id}/events"


def run_events_url(run_id: UUID) -> str:
    return RUN_EVENTS_URL_TEMPLATE.format(run_id=run_id)


class ChatRunAccepted(BaseModel):
    """``POST /api/ai-chat/runs`` 的响应。

    也是前端 TS 类型的来源：内嵌 :class:`ChatEvent`、:class:`EngineCapabilities`、
    ``ChatRunStatus`` 与 :class:`ChatErrorCode`，故这些类型全部随本模型进入
    OpenAPI ``components.schemas``（NFR-2：前端不手抄第二份常量）。
    """

    model_config = ConfigDict(frozen=True)

    run_id: UUID
    session_id: UUID
    request_id: UUID
    status: ChatRunStatus = Field(..., description="run 当前状态")
    error_code: ChatErrorCode | None = Field(
        None, description="仅当重复提交命中的原 run 已进入 error 终态时返回"
    )
    engine: ChatEngineName = Field(..., description="服务端选定的 engine")
    capabilities: EngineCapabilities = Field(..., description="该 run 的能力快照")
    events_url: str = Field(..., description="SSE 事件订阅地址")
    replayed: bool = Field(
        ...,
        description="True = 命中既有 run（未重复保存用户消息、未重复调用 engine）",
    )
    run_started: ChatEvent = Field(
        ...,
        description=(
            "该 run 的首个事件；确定性可复现，重复提交返回同一条。"
            "客户端可用其 event_id 作为 Last-Event-ID 避免重复接收"
        ),
    )
