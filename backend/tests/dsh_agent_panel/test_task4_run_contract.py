# Feature: dsh-agent-panel-integration — Task 4 typed run contract 与幂等 run 创建守卫
"""Chat Run typed contract、幂等创建与"终态恰好一个"的行为守卫。

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 10.2
Properties:
  - **Property 6（会话与 Run 并发幂等）**：100 个并发相同 session key 的首次请求最终只
    产生一个 session；100 个相同 idempotency key 请求只产生一个 run、一条 user message
    和一次 engine invocation。
    **Validates: Requirements 4.6, 4.11**
  - **Property 7（Run 唯一终态）**：任意 run 的事件序列满足状态机，terminal event 恰好
    一个；注入 engine error 或 cancel 后，序列中不存在后续 ``done`` 或 completed
    assistant message。
    **Validates: Requirements 4.3, 4.5**

## 判据都落在哪里

| 判据类型 | 落点 |
|---|---|
| 契约取值域 | **design.md ↔ Python 枚举**双向比对（不是"代码里有这个字符串"） |
| 前端类型可生成 | 真实 ``FastAPI().openapi()`` 文档的 ``components.schemas`` + 枚举值双向 |
| 越权字段拒绝 | 真实 ``ChatRunRequest.model_validate`` 逐字段执行，含**嵌套**位置 |
| 授权先于写入 | 真实路由函数 + 真实 PG 行数差（session/run/message 三表零新增） |
| 幂等 | 真实 ``POST /runs`` 重复调用 + 真实唯一索引 + user message 计数 |
| 终态恰好一个 | 真实 PG ``UPDATE … WHERE status IN (…)`` compare-and-set，100 并发竞争 |

## 两类夹具

- **回滚型**（``_fixtures.run_with_fixture``）：单事务插入 + 整体回滚。用于顺序性、
  拒绝路径与行数差判据。denial audit 走 ``RecordingDenialResponder``／patch，不写 dev 库。
- **提交型**（:func:`_collect`）：跨连接并发**必须**真提交（未提交行对其他连接不可见）。
  🔴 全部快照在**一次** ``asyncio.run`` 内取完 —— 每个测试各自 ``asyncio.run`` 会污染
  共享连接池（第二个起报 ``NoneType has no attribute send``）。``finally`` 分**独立事务**
  逐步清理：一个事务里全清，任一步失败会把前面的清理一起回滚。
"""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.models.ai_models import (
    CHAT_RUN_TERMINAL_STATUSES,
    AIChatSession,
    ChatEngineName,
    ChatMessageStatus,
    ChatRunStatus,
)
from app.models.base import ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.report_models import DisclosureNote
from app.routers import doc_ai_chat as route_mod
from app.services.ai_chat.access import ResourceAccessResolver
from app.services.ai_chat.contracts import AiChatDenialCode, HostRef, HostType, ResourceType
from app.services.ai_chat.persistence import upsert_run
from app.services.ai_chat.run_contract import (
    ALLOWED_RUN_TRANSITIONS,
    CAPABILITIES_BY_ENGINE,
    CONTRACT_VERSION,
    ERROR_CODE_BY_DENIAL,
    ERROR_MESSAGE_ZH,
    EVENT_ID_WIDTH,
    MENTION_RESOURCE_TYPES,
    MESSAGE_BOUND_EVENT_TYPES,
    NON_TERMINAL_RUN_STATUSES,
    PRIVILEGED_REQUEST_FIELDS,
    RUN_EVENTS_URL_TEMPLATE,
    RUN_STARTED_EVENT_SEQ,
    TERMINAL_EVENT_BY_RUN_STATUS,
    TERMINAL_EVENT_TYPES,
    ChatErrorCode,
    ChatEvent,
    ChatEventType,
    ChatRunAccepted,
    ChatRunRequest,
    can_transition,
    event_seq,
    format_event_id,
    resolve_engine_name,
    run_events_url,
)
from app.services.ai_chat.run_service import ChatRunService, RunEventSequencer
from app.services.wp_visibility.denial import ExternalNotFound

from ._fixtures import FIXTURE_AUDIT_YEAR, IS_PG, AccessFixture, run_with_fixture

REPO_ROOT = Path(__file__).resolve().parents[3]
DESIGN = REPO_ROOT / ".kiro" / "specs" / "dsh-agent-panel-integration" / "design.md"

#: 并发规模（Property 6/7 明确要求 100）。
CONCURRENCY = 100

needs_pg = pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (run 状态机 CAS)")

#: 与消息**无关**的事件类型（硬编码，不从 ``MESSAGE_BOUND_EVENT_TYPES`` 取差集）。
#:
#: 🔴 从被测集合派生参数会让判据自证：把 ``MESSAGE_BOUND_EVENT_TYPES`` 改成全集时，
#: 差集为空 ⇒ 参数化用例数为 0 ⇒ 整条判据静默消失而不是变红（本会话变异实测 M06 踩过）。
_NON_MESSAGE_EVENT_TYPES: tuple[ChatEventType, ...] = (
    ChatEventType.run_started,
    ChatEventType.context_ready,
    ChatEventType.tool_started,
    ChatEventType.tool_finished,
    ChatEventType.quota,
    ChatEventType.error,
    ChatEventType.cancelled,
)


# ===========================================================================
# design.md ↔ 代码：契约取值域双向锁死
# ===========================================================================


def _fenced_block(marker: str, fence: str = "text") -> list[str]:
    """取 ``marker`` 之后**第一个** ```<fence> 围栏块的非空行。

    🔴 不用固定字符窗口：design 的清单块长度会变，窗口截断会让判据退化成"能不能解析"。
    这里按围栏配对截取，边界明确。
    """
    src = DESIGN.read_text(encoding="utf-8")
    start = src.index(marker)
    open_tag = f"```{fence}"
    o = src.index(open_tag, start) + len(open_tag)
    c = src.index("```", o)
    return [ln.strip() for ln in src[o:c].splitlines() if ln.strip()]


def _design_event_types() -> set[str]:
    """design "4. Typed Event Contract" 里 ``ChatEventType`` 的取值。"""
    lines = _fenced_block("### 4. Typed Event Contract", fence="python")
    body: list[str] = []
    started = False
    for ln in lines:
        if ln.startswith("class ChatEventType"):
            started = True
            continue
        if started:
            if ln.startswith("class "):
                break
            body.append(ln)
    values = {m.group(1) for ln in body if (m := re.fullmatch(r'\w+ = "([\w_]+)"', ln))}
    assert len(values) >= 10, f"design 的 ChatEventType 解析异常：{values}"
    return values


def _design_error_codes() -> set[str]:
    return set(_fenced_block("稳定 error code 包括"))


def _design_api_surface() -> list[str]:
    return _fenced_block("新 run API：")


class TestContractMatchesDesign:
    """契约取值域 = design 的清单，两侧任一漂移即打红。

    **Validates: Requirements 4.3**
    """

    def test_event_types_equal_design_list(self):
        """``ChatEventType`` 与 design 的十类事件**集合相等**（Req 4.3）。

        双向：代码少一类 ⇒ engine 无法表达该信号；代码多一类 ⇒ 前端不认识的事件
        （单向包含查不出后者）。
        """
        code = {e.value for e in ChatEventType}
        design = _design_event_types()
        assert code == design, (
            f"ChatEventType 与 design 漂移：\n  代码多出 {sorted(code - design)}\n"
            f"  design 多出 {sorted(design - code)}"
        )
        for required in (
            "run_started", "context_ready", "citation", "delta",
            "tool_started", "tool_finished", "quota", "error", "cancelled", "done",
        ):
            assert required in code, f"Req 4.3 明列的 {required} 缺失"

    def test_error_codes_equal_design_list(self):
        """``ChatErrorCode`` 与 design 的稳定 error code 清单**集合相等**（Req 12.5）。"""
        code = {c.value for c in ChatErrorCode}
        design = _design_error_codes()
        assert code == design, (
            f"ChatErrorCode 与 design 漂移：\n  代码多出 {sorted(code - design)}\n"
            f"  design 多出 {sorted(design - code)}"
        )

    def test_every_error_code_has_chinese_user_message(self):
        """每个 error code 都有中文用户消息（NFR-5 / Req 12.5）。

        判据不是"字典有这个 key"，而是**值里真的有汉字** —— 占位英文串会被抓出来。
        """
        missing = [c.value for c in ChatErrorCode if c not in ERROR_MESSAGE_ZH]
        assert not missing, f"缺中文消息：{missing}"
        for code, msg in ERROR_MESSAGE_ZH.items():
            assert re.search(r"[\u4e00-\u9fff]", msg), f"{code.value} 的消息不是中文：{msg!r}"

    def test_run_endpoint_paths_match_design_api_surface(self):
        """路由路径与 design "3. API Surface" 一致（不许自造第二套地址）。

        ``events_url`` 由 :data:`RUN_EVENTS_URL_TEMPLATE` 生成并写进响应；若它与 Task 5
        将要注册的真实路由不一致，前端拿到的是一个 404 地址 —— 故两侧必须同源。
        """
        surface = _design_api_surface()
        assert "POST   /api/ai-chat/runs" in surface, surface
        events_line = next(ln for ln in surface if ln.endswith("/events"))
        assert events_line.split()[-1] == RUN_EVENTS_URL_TEMPLATE, (
            f"事件订阅地址与 design 不一致：{events_line} vs {RUN_EVENTS_URL_TEMPLATE}"
        )
        paths = {
            r.path for r in route_mod.router.routes if getattr(r, "path", None)
        }
        assert "/api/ai-chat/runs" in paths, f"POST /runs 未注册：{sorted(paths)}"

    def test_mention_types_are_the_seven_design_values(self):
        """可引用资源类型 = design 的七类 mention（从 ResourceType 取差集，不另立枚举）。

        **Validates: Requirements 4.2**
        """
        assert {t.value for t in MENTION_RESOURCE_TYPES} == {
            "workpaper", "note", "report", "knowledge_doc",
            "knowledge_folder", "address", "attachment",
        }
        assert ResourceType.global_knowledge not in MENTION_RESOURCE_TYPES, (
            "global_knowledge 是宿主模式而非可引用资源"
        )


# ===========================================================================
# Req 4.4 / 4.5 — 事件形状与状态机
# ===========================================================================


class TestEventShapeAndStateMachine:
    """**Validates: Requirements 4.4, 4.5**"""

    def test_every_event_carries_req_4_4_identifiers(self):
        """每个事件都必带 event_id / run_id / session_id / request_id / type / timestamp。

        判据是**模型 required 集合**，不是"某处传了这些参数"：少一个必填字段，
        任何调用方都能构造出缺 ID 的事件而不报错。
        """
        required = set(ChatEvent.model_json_schema()["required"])
        assert {
            "event_id", "run_id", "session_id", "request_id", "type", "timestamp"
        } <= required, f"Req 4.4 的必带字段不全：{sorted(required)}"

    @pytest.mark.parametrize("event_type", sorted(MESSAGE_BOUND_EVENT_TYPES, key=lambda e: e.value))
    def test_message_bound_events_require_message_id(self, event_type):
        """与消息相关的事件缺 ``message_id`` 即构造失败（Req 4.4 后半句）。"""
        base = dict(
            event_id=format_event_id(2),
            run_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            type=event_type,
            timestamp=_utcnow(),
        )
        with pytest.raises(ValueError, match="message_id"):
            ChatEvent(**base)
        assert ChatEvent(**base, message_id=uuid.uuid4()).message_id is not None

    def test_message_bound_set_is_exactly_the_three_content_events(self):
        """与消息绑定的事件**恰好**是 delta / citation / done（固定期望，不自证）。

        🔴 上一条与下一条用例都以 ``MESSAGE_BOUND_EVENT_TYPES`` 为参数来源，集合被改大
        或改小时它们可能只是"少几个用例"而不变红（实测：改成全集会让下一条的参数集为空，
        整条用例直接消失）。本条给出固定期望，让集合本身的漂移有判据。
        """
        assert {e.value for e in MESSAGE_BOUND_EVENT_TYPES} == {
            "delta", "citation", "done"
        }, f"消息绑定事件集合漂移：{sorted(e.value for e in MESSAGE_BOUND_EVENT_TYPES)}"
        for e in _NON_MESSAGE_EVENT_TYPES:
            assert e not in MESSAGE_BOUND_EVENT_TYPES, (
                f"{e.value} 被要求携带 message_id —— error/cancelled 此时并无 completed "
                "assistant 消息，只能伪造一个 ID（Req 4.5）"
            )

    @pytest.mark.parametrize("event_type", _NON_MESSAGE_EVENT_TYPES)
    def test_non_message_events_do_not_require_message_id(self, event_type):
        """``error`` / ``cancelled`` 等不得被强制要求 message_id。

        这条是"必带 message_id"的反假绿控制：若把「所有事件都要 message_id」当成实现，
        error/cancelled 就只能伪造一条消息 ID —— 而 Req 4.5 明确此时**没有**
        completed assistant 消息。参数是**硬编码**的七类，不从被测集合派生。
        """
        ev = ChatEvent(
            event_id=format_event_id(3),
            run_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            type=event_type,
            timestamp=_utcnow(),
        )
        assert ev.message_id is None

    def test_event_ids_sort_identically_as_strings_and_numbers(self):
        """零填充 event ID 的字典序 == 数值序（``Last-Event-ID`` 续传的前提，Req 4.8）。"""
        seqs = [1, 2, 9, 10, 11, 99, 100, 1000, 123456]
        ids = [format_event_id(s) for s in seqs]
        assert all(len(i) == EVENT_ID_WIDTH for i in ids)
        assert sorted(ids) == ids, f"字典序与数值序不一致：{ids}"
        assert [event_seq(i) for i in ids] == seqs

    def test_terminal_statuses_and_events_are_bijective(self):
        """run 终态 ↔ terminal event 一一对应（防"库里 error、流里 done"）。"""
        assert set(TERMINAL_EVENT_BY_RUN_STATUS) == set(CHAT_RUN_TERMINAL_STATUSES)
        assert set(TERMINAL_EVENT_BY_RUN_STATUS.values()) == set(TERMINAL_EVENT_TYPES)
        assert len(set(TERMINAL_EVENT_BY_RUN_STATUS.values())) == len(
            TERMINAL_EVENT_BY_RUN_STATUS
        ), "映射不是单射 ⇒ 两个终态共用一个事件类型"
        assert NON_TERMINAL_RUN_STATUSES == frozenset(
            {ChatRunStatus.queued, ChatRunStatus.running, ChatRunStatus.interrupted}
        )

    @pytest.mark.parametrize("terminal", sorted(CHAT_RUN_TERMINAL_STATUSES, key=lambda s: s.value))
    def test_terminal_states_have_no_outgoing_transitions(self, terminal):
        """终态出边为空 ⇒ 任何"终态之后再迁移"在契约层即被拒（Property 7 的形式化）。"""
        assert ALLOWED_RUN_TRANSITIONS[terminal] == frozenset()
        for target in ChatRunStatus:
            assert not can_transition(terminal, target), (
                f"{terminal.value} → {target.value} 竟被允许"
            )

    def test_state_machine_covers_design_paths(self):
        """design 状态图里的合法路径都在表里（反假绿：表不能空到"什么都不允许"）。"""
        assert can_transition(ChatRunStatus.queued, ChatRunStatus.running)
        assert can_transition(ChatRunStatus.queued, ChatRunStatus.cancelled)
        for t in (ChatRunStatus.done, ChatRunStatus.error, ChatRunStatus.cancelled):
            assert can_transition(ChatRunStatus.running, t)
        assert can_transition(ChatRunStatus.running, ChatRunStatus.interrupted)
        assert can_transition(ChatRunStatus.interrupted, ChatRunStatus.queued)
        assert not can_transition(ChatRunStatus.queued, ChatRunStatus.done), (
            "未开跑就成功 = 绕过 engine"
        )


# ===========================================================================
# Req 4.2 — 请求体拒绝越权字段
# ===========================================================================


def _valid_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "host": {"type": "workpaper", "id": str(uuid.uuid4())},
        "query": "这份底稿的减值测试是否充分？",
        "idempotency_key": str(uuid.uuid4()),
    }
    body.update(overrides)
    return body


class TestRequestRejectsPrivilegedFields:
    """**Validates: Requirements 4.2, 10.2**"""

    def test_model_has_no_engine_or_scope_field_at_all(self):
        """模型上**根本不存在** engine / scope / content 字段（不是"接收后忽略"）。

        "接收但忽略"会让前端以为自己传的值生效（Req 10.4 明令禁止的静默忽略）。
        """
        fields = set(ChatRunRequest.model_fields)
        assert fields == {
            "host", "query", "idempotency_key", "session_id",
            "mentions", "attachment_ids", "review_mode", "sheet_name",
        }, f"请求体字段集合漂移：{sorted(fields)}"
        assert not (fields & PRIVILEGED_REQUEST_FIELDS), (
            f"请求体声明了越权字段：{sorted(fields & PRIVILEGED_REQUEST_FIELDS)}"
        )

    @pytest.mark.parametrize("field", sorted(PRIVILEGED_REQUEST_FIELDS))
    def test_each_privileged_field_is_rejected_by_name(self, field):
        """逐个越权字段真实解析一次，必须被拒且**中文**原因点名该字段。

        为什么要求中文原因：``extra="forbid"`` 自己就会拒绝未声明字段，但给的是
        pydantic 的英文 ``Extra inputs are not permitted``（NFR-5 要求可见状态全中文）。
        点名的中文原因只有显式越权扫描能给出 —— 断言中文即断言那段扫描真的在跑，
        而不是被 ``extra="forbid"`` 顺手挡掉后被误判为"守卫有效"。
        """
        with pytest.raises(ValueError) as exc:
            ChatRunRequest.model_validate(_valid_body(**{field: "x"}))
        text = str(exc.value)
        assert field in text, f"{field} 被拒但原因未点名该字段"
        assert "服务端专属字段" in text, (
            f"{field} 的拒绝原因不是点名的中文说明（越权扫描未生效）：{text[:200]}"
        )

    def test_privileged_list_covers_the_four_req_4_2_categories(self):
        """越权清单必须覆盖 Req 4.2 点名的四类，缺一即打红。

        🔴 上一条参数化用例是**以清单自身为参数**的（清单被删条目 ⇒ 少一个用例，不会红）。
        本条给出固定期望子集，让"悄悄放宽清单"这件事有判据。
        """
        required = {
            # ① engine / capability
            "engine", "engine_preference", "capabilities", "model",
            # ② 权限 scope
            "scope", "scopes", "extra_scopes", "allowed_actions", "permission_binding",
            # ③ 资源正文 / 上下文
            "context", "doc_excerpt", "knowledge_hits", "ocr_text", "citations",
            # ④ 消息正文
            "content", "message", "messages", "message_text", "assistant_content",
        }
        missing = sorted(required - PRIVILEGED_REQUEST_FIELDS)
        assert not missing, f"越权字段清单被放宽，缺少：{missing}"

    def test_privileged_field_nested_in_host_or_mention_is_rejected(self):
        """越权字段藏在嵌套对象里同样被拒，且原因仍是点名的中文说明。

        嵌套位置**也**会被 pydantic 的严格构造挡住（报英文
        ``Unexpected keyword argument``），所以这里的判据落在"原因是中文且点名"上 ——
        否则一个只查顶层的实现会因为 pydantic 顺手报错而被误判为守卫有效。
        """
        for body in (
            {
                "host": {"type": "note", "id": str(uuid.uuid4()), "content": "forged"},
                "query": "q",
                "idempotency_key": str(uuid.uuid4()),
            },
            _valid_body(mentions=[{"type": "note", "id": "x", "engine": "dsh"}]),
        ):
            with pytest.raises(ValueError) as exc:
                ChatRunRequest.model_validate(body)
            assert "服务端专属字段" in str(exc.value), (
                f"嵌套越权字段未被点名拒绝：{str(exc.value)[:200]}"
            )

    def test_unknown_field_is_rejected_by_extra_forbid(self):
        """未登记字段一律拒绝（越权清单之外的兜底）。"""
        with pytest.raises(ValueError):
            ChatRunRequest.model_validate(_valid_body(totally_new_field=1))

    def test_mention_rejects_non_mentionable_type_and_label(self):
        """mention 只收 ``{type, id}``；label 字段不存在，宿主模式类型被拒（Req 5.5）。"""
        with pytest.raises(ValueError):
            ChatRunRequest.model_validate(
                _valid_body(mentions=[{"type": "global_knowledge", "id": "global-knowledge"}])
            )
        with pytest.raises(ValueError):
            ChatRunRequest.model_validate(
                _valid_body(mentions=[{"type": "note", "id": "x", "label": "假名字"}])
            )

    def test_engine_is_resolved_from_server_config_only(self, monkeypatch):
        """engine 只由服务端配置决定；默认 native，非法取值回落 native（Req 10.1）。

        判据真的改配置再求值（不是读源码看有没有 default）：非法值必须落到 native 而不是
        抛异常（抛异常会让整条对话 500，比"用最安全的引擎"更糟）。
        """
        assert type(app_settings).model_fields["AI_CHAT_ENGINE"].default == "native", (
            "服务端默认引擎必须是 native（Req 10.1）"
        )
        monkeypatch.setattr(app_settings, "AI_CHAT_ENGINE", "")
        assert resolve_engine_name() is ChatEngineName.native
        monkeypatch.setattr(app_settings, "AI_CHAT_ENGINE", "not-an-engine")
        assert resolve_engine_name() is ChatEngineName.native
        monkeypatch.setattr(app_settings, "AI_CHAT_ENGINE", "dsh")
        assert resolve_engine_name() is ChatEngineName.dsh
        monkeypatch.setattr(app_settings, "AI_CHAT_ENGINE", "native")
        assert resolve_engine_name() is ChatEngineName.native

    def test_query_and_collection_bounds_are_enforced(self):
        """query 长度、mention/附件数量有硬上界（NFR-4）。"""
        with pytest.raises(ValueError):
            ChatRunRequest.model_validate(_valid_body(query=""))
        with pytest.raises(ValueError):
            ChatRunRequest.model_validate(_valid_body(query="x" * 4001))
        with pytest.raises(ValueError):
            ChatRunRequest.model_validate(
                _valid_body(mentions=[{"type": "note", "id": str(i)} for i in range(21)])
            )
        with pytest.raises(ValueError):
            ChatRunRequest.model_validate(
                _valid_body(attachment_ids=[str(uuid.uuid4()) for _ in range(11)])
            )


# ===========================================================================
# NFR-2 — OpenAPI 暴露前端类型
# ===========================================================================


@pytest.fixture(scope="module")
def openapi_doc() -> dict[str, Any]:
    """只挂 AI chat router 的探针 app 的真实 OpenAPI 文档。

    不导入 ``app.main``：那会拉起全量 router 与启动钩子，本判据只需要本 router 的 schema。
    """
    probe = FastAPI()
    probe.include_router(route_mod.router)
    return probe.openapi()


class TestOpenApiExposesFrontendTypes:
    """**Validates: Requirements 4.3, 4.4, 10.2**（NFR-2 单一真源）"""

    @pytest.mark.parametrize(
        "name",
        [
            "ChatRunRequest", "ChatRunAccepted", "ChatEvent", "ChatEventType",
            "ChatErrorCode", "EngineCapabilities", "HostRef", "MentionRef",
        ],
    )
    def test_type_is_present_in_components(self, openapi_doc, name):
        """前端需要的类型都在 ``components.schemas`` 里（可生成 TS，不手抄常量）。"""
        schemas = openapi_doc["components"]["schemas"]
        assert name in schemas, f"{name} 未进入 OpenAPI：{sorted(schemas)}"

    @pytest.mark.parametrize(
        "schema_name,enum_cls",
        [
            ("ChatEventType", ChatEventType),
            ("ChatErrorCode", ChatErrorCode),
            ("ChatRunStatus", ChatRunStatus),
            ("ChatEngineName", ChatEngineName),
            ("HostType", HostType),
        ],
    )
    def test_openapi_enum_values_equal_python_enum(self, openapi_doc, schema_name, enum_cls):
        """OpenAPI 枚举取值与 Python 枚举**双向**相等。

        单向包含会漏掉两侧各自多出的取值：前端多认一个不存在的事件类型 / 少认一个
        真会收到的事件类型，都是运行期才炸。
        """
        exposed = set(openapi_doc["components"]["schemas"][schema_name]["enum"])
        py = {m.value for m in enum_cls}
        assert exposed == py, (
            f"{schema_name} 取值漂移：OpenAPI 多出 {sorted(exposed - py)}，"
            f"Python 多出 {sorted(py - exposed)}"
        )

    def test_capabilities_manifest_declares_all_eight_req_10_3_fields(self, openapi_doc):
        """capability manifest 的八项齐备（Req 10.3）。"""
        props = set(
            openapi_doc["components"]["schemas"]["EngineCapabilities"]["properties"]
        )
        assert props == {
            "streaming", "tools", "subagents", "max_context",
            "structured_output", "local_only", "review_mode", "attachments",
        }, f"capability 字段漂移：{sorted(props)}"
        for engine in ChatEngineName:
            assert engine in CAPABILITIES_BY_ENGINE, f"{engine.value} 未登记 capability"
        assert CAPABILITIES_BY_ENGINE[ChatEngineName.native].local_only is True
        assert CAPABILITIES_BY_ENGINE[ChatEngineName.dsh].local_only is True

    def test_denial_codes_all_map_to_stable_error_codes(self):
        """内部拒绝码全部有对外 error code 映射，且不泄露资源存在性（Req 2.5）。"""
        missing = [c.value for c in AiChatDenialCode if c not in ERROR_CODE_BY_DENIAL]
        assert not missing, f"未登记对外映射的拒绝码：{missing}"
        leaky = {
            code.value
            for code, mapped in ERROR_CODE_BY_DENIAL.items()
            if code
            in (
                AiChatDenialCode.resource_not_found,
                AiChatDenialCode.cross_project,
                AiChatDenialCode.out_of_scope,
            )
            and mapped is not ChatErrorCode.access_denied
        }
        assert not leaky, f"这些拒绝码被原样透出，成为存在性探针：{sorted(leaky)}"


# ===========================================================================
# Req 4.1 / 4.6 — 幂等创建（回滚型夹具：顺序判据与行数差）
# ===========================================================================


def _note_request(fx: AccessFixture, **overrides: Any) -> ChatRunRequest:
    body = {
        "host": {
            "type": HostType.note.value,
            "id": str(fx.note_a.id),
            "project_id_assertion": str(fx.project_a.id),
            "year_assertion": FIXTURE_AUDIT_YEAR,
        },
        "query": "这段附注披露是否完整？",
        "idempotency_key": str(uuid.uuid4()),
    }
    body.update(overrides)
    return ChatRunRequest.model_validate(body)


def _service(fx: AccessFixture) -> ChatRunService:
    """服务实例：denial audit 走记录型 responder（真实 deny 路径，但不写 dev 库）。"""
    return ChatRunService(
        fx.session, access=ResourceAccessResolver(fx.session, responder=fx.responder)
    )


async def _counts(fx: AccessFixture, user_id: UUID) -> tuple[int, int, int]:
    sessions = (
        await fx.session.execute(
            sa.text("SELECT count(*) FROM ai_chat_session WHERE user_id = :u"),
            {"u": user_id},
        )
    ).scalar_one()
    runs = (
        await fx.session.execute(
            sa.text("SELECT count(*) FROM ai_chat_runs WHERE actor_id = :u"), {"u": user_id}
        )
    ).scalar_one()
    messages = (
        await fx.session.execute(
            sa.text(
                "SELECT count(*) FROM ai_chat_message m JOIN ai_chat_session s "
                "ON s.id = m.session_id WHERE s.user_id = :u"
            ),
            {"u": user_id},
        )
    ).scalar_one()
    return sessions, runs, messages


@needs_pg
class TestIdempotentRunCreation:
    """**Validates: Requirements 4.1, 4.6**（Property 6 的 API 侧）"""

    def test_repeat_requests_return_original_run_without_new_message(self):
        """同一 idempotency key 重复提交 → 同一 run、一条 user message、只有一次可调 engine。

        ``created`` 是**唯一**可以调用 engine 的闸门（Task 5 的 coordinator 只在它为真时
        入队）。这里同时断言：run 行数、user message 行数与 ``created`` 计数三者都为 1，
        任一放宽都会打红。
        """

        async def scenario(fx: AccessFixture, _sql):
            user = fx.actor("manager").user
            svc = _service(fx)
            req = _note_request(fx)

            results = [await svc.create_run(user, req) for _ in range(5)]
            await fx.session.flush()

            assert sum(1 for r in results if r.created) == 1, (
                f"{sum(1 for r in results if r.created)} 次调用自称创建者（应恰好 1）"
            )
            assert len({r.run_id for r in results}) == 1, "重复提交拿到了不同 run"
            assert len({r.session_id for r in results}) == 1
            assert [r.should_invoke_engine for r in results].count(True) == 1

            sessions, runs, messages = await _counts(fx, user.id)
            assert (sessions, runs, messages) == (1, 1, 1), (
                f"重复提交产生了多余行：session={sessions} run={runs} message={messages}"
            )
            assert results[0].user_message_id is not None
            assert all(r.user_message_id is None for r in results[1:]), (
                "重复请求也写了 user message"
            )
            assert [r.to_response().replayed for r in results] == [
                False, True, True, True, True
            ]

        run_with_fixture(scenario)

    def test_run_started_event_is_deterministic_across_replays(self):
        """``run_started`` 逐字相同（含 event_id 与 timestamp），客户端不会重复渲染。

        **Validates: Requirements 4.4, 4.6**
        时间戳取落库的 ``queued_at`` 而非"现在" —— 用 ``now()`` 生成会让每次重放都是
        一条"新事件"。
        """

        async def scenario(fx: AccessFixture, _sql):
            svc = _service(fx)
            req = _note_request(fx)
            first = (await svc.create_run(fx.actor("manager").user, req)).to_response()
            second = (await svc.create_run(fx.actor("manager").user, req)).to_response()
            assert first.run_started.model_dump() == second.run_started.model_dump()
            assert first.run_started.event_id == format_event_id(RUN_STARTED_EVENT_SEQ)
            assert first.run_started.type is ChatEventType.run_started
            assert first.run_started.message_id is None
            assert first.events_url == run_events_url(first.run_id)
            assert first.status is ChatRunStatus.queued

        run_with_fixture(scenario)

    def test_different_idempotency_keys_create_separate_runs_in_one_session(self):
        """不同 idempotency key ⇒ 不同 run，但共用同一会话（反假绿：幂等不能变成"永不新建"）。"""

        async def scenario(fx: AccessFixture, _sql):
            svc = _service(fx)
            user = fx.actor("manager").user
            a = await svc.create_run(user, _note_request(fx))
            b = await svc.create_run(user, _note_request(fx))
            assert a.run_id != b.run_id
            assert a.session_id == b.session_id
            assert a.created and b.created
            sessions, runs, messages = await _counts(fx, user.id)
            assert (sessions, runs, messages) == (1, 2, 2)

        run_with_fixture(scenario)

    def test_review_mode_is_persisted_on_server_session(self):
        """review mode 落到服务端会话（Req 9.5：不得只存无作用域 localStorage）。"""

        async def scenario(fx: AccessFixture, _sql):
            svc = _service(fx)
            creation = await svc.create_run(
                fx.actor("manager").user, _note_request(fx, review_mode=True)
            )
            stored = (
                await fx.session.execute(
                    sa.select(AIChatSession.review_mode).where(
                        AIChatSession.id == creation.session_id
                    )
                )
            ).scalar_one()
            assert stored is True, "review_mode 未持久化到服务端会话"

        run_with_fixture(scenario)

    def test_capability_snapshot_is_written_to_run_row(self):
        """capability 快照落库（Req 10.3：事后可追溯"这次执行当时能做什么"）。"""

        async def scenario(fx: AccessFixture, _sql):
            creation = await _service(fx).create_run(
                fx.actor("manager").user, _note_request(fx)
            )
            snapshot = (
                await fx.session.execute(
                    sa.text("SELECT capability_snapshot FROM ai_chat_runs WHERE id = :r"),
                    {"r": creation.run_id},
                )
            ).scalar_one()
            assert snapshot == creation.capabilities.model_dump(), (
                f"落库快照与响应不一致：{snapshot}"
            )
            assert creation.engine is ChatEngineName.native

        run_with_fixture(scenario)


@needs_pg
class TestAuthorizationPrecedesAnyWrite:
    """授权/断言拒绝发生在 session/run/message 任何写入之前。

    **Validates: Requirements 4.1, 4.2**（Property 1/2 在 run 创建路径上的复用）
    """

    def test_forged_host_assertion_writes_nothing(self):
        """伪造宿主断言 → 不可枚举 404，且三张表零新增（真实行数差）。"""

        async def scenario(fx: AccessFixture, _sql):
            user = fx.actor("manager").user
            before = await _counts(fx, user.id)
            svc = _service(fx)
            forged = (
                # 附注真实属于 project_a，断言 project_b
                {"type": "note", "id": str(fx.note_a.id),
                 "project_id_assertion": str(fx.project_b.id),
                 "year_assertion": FIXTURE_AUDIT_YEAR},
                # 年度断言错
                {"type": "note", "id": str(fx.note_a.id),
                 "project_id_assertion": str(fx.project_a.id),
                 "year_assertion": FIXTURE_AUDIT_YEAR - 1},
                # 不存在的附注实例
                {"type": "note", "id": str(uuid.uuid4()),
                 "project_id_assertion": str(fx.project_a.id),
                 "year_assertion": FIXTURE_AUDIT_YEAR},
                # 跨项目附注（用户不是 project_b 成员）
                {"type": "note", "id": str(fx.note_b.id),
                 "project_id_assertion": str(fx.project_b.id),
                 "year_assertion": FIXTURE_AUDIT_YEAR},
            )
            for host in forged:
                with pytest.raises(ExternalNotFound):
                    await svc.create_run(user, _note_request(fx, host=host))
                assert await _counts(fx, user.id) == before, (
                    f"被拒请求留下了副作用：host={host}"
                )
            assert fx.responder.records, "拒绝未留下内部 denial audit"

        run_with_fixture(scenario)

    def test_forged_session_id_is_rejected_before_session_upsert(self):
        """伪造 ``session_id`` → 拒绝，且**连会话都不创建**。

        校验顺序是"只读定位 → 比对 → 才 upsert"：反过来写的话，一个伪造 session_id 的
        请求会先建出一行会话，再被拒绝 —— 副作用与拒绝并存。
        """

        async def scenario(fx: AccessFixture, _sql):
            user = fx.actor("manager").user
            before = await _counts(fx, user.id)
            with pytest.raises(ExternalNotFound):
                await _service(fx).create_run(
                    user, _note_request(fx, session_id=str(uuid.uuid4()))
                )
            assert await _counts(fx, user.id) == before, "伪造 session_id 竟创建了会话"

        run_with_fixture(scenario)

    def test_matching_session_id_passes(self):
        """一致的 session_id 正常通过（上一条断言的反假绿控制）。"""

        async def scenario(fx: AccessFixture, _sql):
            svc = _service(fx)
            user = fx.actor("manager").user
            first = await svc.create_run(user, _note_request(fx))
            second = await svc.create_run(
                user, _note_request(fx, session_id=str(first.session_id))
            )
            assert second.session_id == first.session_id

        run_with_fixture(scenario)

    def test_route_denies_without_touching_context_or_engine(self):
        """真实路由函数：无权用户被拒（不可枚举 404），且不产生任何 run。"""

        async def scenario(fx: AccessFixture, _sql):
            async def fake_write_outbox(_self, **fields):
                return None

            with patch(
                "app.services.wp_visibility.denial.DenialResponder._write_outbox",
                fake_write_outbox,
            ):
                outsider = fx.outsider
                before = await _counts(fx, outsider.id)
                with pytest.raises(ExternalNotFound):
                    await route_mod.create_chat_run(
                        _note_request(fx), fx.session, outsider
                    )
                assert await _counts(fx, outsider.id) == before

        run_with_fixture(scenario)


# ===========================================================================
# Property 7 — 终态恰好一个（顺序注入 + 真实 CAS）
# ===========================================================================


@needs_pg
class TestSingleTerminalSequential:
    """**Validates: Requirements 4.3, 4.5**"""

    def test_engine_error_blocks_later_done_and_completed_message(self):
        """注入 engine error 后：``done`` 不再产生、completed assistant 消息不存在。

        Property 7 的核心判据，全部落在**真实 PG CAS 与真实行**上：
        1. ``finish_error`` 胜出并给出唯一 error 事件；
        2. 随后的 ``finish_success`` 返回 ``(None, None)``（CAS 未命中）；
        3. 库里 run 状态仍是 ``error``；
        4. 该 run 下**没有** completed assistant 消息；
        5. 后续业务事件（delta / tool_started）一律被拒。
        """

        async def scenario(fx: AccessFixture, _sql):
            svc = _service(fx)
            user = fx.actor("manager").user
            creation = await svc.create_run(user, _note_request(fx))
            session_obj = (
                await fx.session.execute(
                    sa.select(AIChatSession).where(AIChatSession.id == creation.session_id)
                )
            ).scalar_one()
            events: list[ChatEvent] = [creation.run_started_event()]

            assert await svc.mark_running(creation.run_id) is True
            ctx = await svc.emit(
                run_id=creation.run_id, event_type=ChatEventType.context_ready
            )
            assert ctx is not None
            events.append(ctx)

            err = await svc.finish_error(
                run_id=creation.run_id, error_code=ChatErrorCode.engine_unavailable
            )
            assert err is not None and err.type is ChatEventType.error
            events.append(err)
            assert err.payload["code"] == ChatErrorCode.engine_unavailable.value
            assert re.search(r"[\u4e00-\u9fff]", err.payload["message"])

            # ① 再发成功终态：CAS 必须落空，且不写任何消息
            done_event, message = await svc.finish_success(
                session=session_obj, run_id=creation.run_id, text="伪造的成功回复"
            )
            assert done_event is None, "error 之后仍发出了 done 事件"
            assert message is None, "error 之后仍写入了 assistant 消息"

            # ② 再发一次 error / cancelled 也不得产生第二个终态事件
            assert await svc.finish_error(
                run_id=creation.run_id, error_code=ChatErrorCode.rate_limited
            ) is None
            assert await svc.finish_cancelled(run_id=creation.run_id) is None

            # ③ 业务事件被拒
            for et in (ChatEventType.delta, ChatEventType.tool_started):
                assert await svc.emit(
                    run_id=creation.run_id,
                    event_type=et,
                    message_id=uuid.uuid4() if et in MESSAGE_BOUND_EVENT_TYPES else None,
                ) is None, f"终态后仍签发了 {et.value}"
            assert await svc.append_assistant_draft(
                session=session_obj, run_id=creation.run_id, text="终态后的草稿"
            ) is None

            # ④ 真实库状态与消息
            status, code = (
                await fx.session.execute(
                    sa.text("SELECT status, error_code FROM ai_chat_runs WHERE id = :r"),
                    {"r": creation.run_id},
                )
            ).one()
            assert status == ChatRunStatus.error.value
            assert code == ChatErrorCode.engine_unavailable.value
            completed = (
                await fx.session.execute(
                    sa.text(
                        "SELECT count(*) FROM ai_chat_message "
                        "WHERE run_id = :r AND role = 'assistant' AND status = :s"
                    ),
                    {"r": creation.run_id, "s": ChatMessageStatus.completed.value},
                )
            ).scalar_one()
            assert completed == 0, f"error 终态下存在 {completed} 条 completed assistant 消息"

            terminal = [e for e in events if e.is_terminal]
            assert len(terminal) == 1, f"事件序列里有 {len(terminal)} 个终态事件"
            assert [event_seq(e.event_id) for e in events] == sorted(
                event_seq(e.event_id) for e in events
            ), "event ID 非单调"

        run_with_fixture(scenario)

    def test_cancel_blocks_later_done_and_completed_message(self):
        """注入 cancel 后同样不再产生 ``done`` 与 completed 消息（Req 4.7 的前置）。"""

        async def scenario(fx: AccessFixture, _sql):
            svc = _service(fx)
            creation = await svc.create_run(fx.actor("manager").user, _note_request(fx))
            session_obj = (
                await fx.session.execute(
                    sa.select(AIChatSession).where(AIChatSession.id == creation.session_id)
                )
            ).scalar_one()
            assert await svc.mark_running(creation.run_id) is True

            cancelled = await svc.finish_cancelled(run_id=creation.run_id)
            assert cancelled is not None and cancelled.type is ChatEventType.cancelled
            assert await svc.finish_cancelled(run_id=creation.run_id) is None, "取消不幂等"

            done_event, message = await svc.finish_success(
                session=session_obj, run_id=creation.run_id, text="取消后的回复"
            )
            assert (done_event, message) == (None, None)

            status, cancel_at = (
                await fx.session.execute(
                    sa.text(
                        "SELECT status, cancel_requested_at FROM ai_chat_runs WHERE id = :r"
                    ),
                    {"r": creation.run_id},
                )
            ).one()
            assert status == ChatRunStatus.cancelled.value
            assert cancel_at is not None, "取消未记录 cancel_requested_at"
            completed = (
                await fx.session.execute(
                    sa.text(
                        "SELECT count(*) FROM ai_chat_message "
                        "WHERE run_id = :r AND status = :s AND role = 'assistant'"
                    ),
                    {"r": creation.run_id, "s": ChatMessageStatus.completed.value},
                )
            ).scalar_one()
            assert completed == 0

        run_with_fixture(scenario)

    def test_success_path_writes_exactly_one_completed_message(self):
        """成功路径确实能写出 completed 消息（上面两条空值断言的反假绿控制）。"""

        async def scenario(fx: AccessFixture, _sql):
            svc = _service(fx)
            creation = await svc.create_run(fx.actor("manager").user, _note_request(fx))
            session_obj = (
                await fx.session.execute(
                    sa.select(AIChatSession).where(AIChatSession.id == creation.session_id)
                )
            ).scalar_one()
            assert await svc.mark_running(creation.run_id) is True
            event, message = await svc.finish_success(
                session=session_obj,
                run_id=creation.run_id,
                text="附注披露完整，建议补充关联方口径说明。",
                usage={"total_tokens": 128},
                latency_ms=321,
            )
            assert event is not None and event.type is ChatEventType.done
            assert message is not None
            assert event.message_id == message.id, "done 事件未绑定服务端签发的 message_id"
            status, usage, latency = (
                await fx.session.execute(
                    sa.text(
                        "SELECT status, usage, latency_ms FROM ai_chat_runs WHERE id = :r"
                    ),
                    {"r": creation.run_id},
                )
            ).one()
            assert status == ChatRunStatus.done.value
            assert usage == {"total_tokens": 128}
            assert latency == 321

        run_with_fixture(scenario)

    def test_transition_rejects_illegal_expected_states(self):
        """显式给出非法前驱状态时直接抛错（不给"悄悄允许非法迁移"的口子）。"""

        async def scenario(fx: AccessFixture, _sql):
            svc = _service(fx)
            creation = await svc.create_run(fx.actor("manager").user, _note_request(fx))
            with pytest.raises(ValueError, match="非法迁移"):
                await svc.transition(
                    run_id=creation.run_id,
                    new_status=ChatRunStatus.done,
                    expected=[ChatRunStatus.error],
                )
            with pytest.raises(ValueError, match="终态事件"):
                await svc.emit(
                    run_id=creation.run_id,
                    event_type=ChatEventType.done,
                    message_id=uuid.uuid4(),
                )

        run_with_fixture(scenario)


def test_sequencer_is_strictly_monotonic_and_starts_after_run_started():
    """事件序号严格单调且从 ``run_started`` 之后开始（Req 4.4）。"""
    seq = RunEventSequencer()
    run_id = uuid.uuid4()
    got = [seq.next(run_id) for _ in range(5)]
    assert got == [RUN_STARTED_EVENT_SEQ + i + 1 for i in range(5)]
    other = uuid.uuid4()
    assert seq.next(other) == RUN_STARTED_EVENT_SEQ + 1, "不同 run 的序号不应互相污染"
    seq.forget(run_id)
    assert seq.next(run_id) == RUN_STARTED_EVENT_SEQ + 1


# ===========================================================================
# 提交型快照：100 并发（Property 6 后半 + Property 7 的竞态）
# ===========================================================================


async def _make_committed_fixture(engine) -> dict[str, Any]:
    """最小提交型夹具：manager 用户 + 项目 + 项目成员 + 附注实例。

    只建 note 宿主授权真正需要的四行（成员关系 + 附注实例），因此 ``finally`` 的清理
    清单短且可复核。底稿宿主要走 ``gate_wp`` 的委派链，那是 Task 1/2 已覆盖的面，
    这里不重复建。
    """
    async with AsyncSession(bind=engine) as db:
        user = User(
            username=f"ai_t4_{uuid.uuid4().hex[:10]}",
            email=f"{uuid.uuid4().hex[:12]}@ai-task4.example",
            hashed_password="x",
            role=UserRole("manager"),
            is_active=True,
        )
        db.add(user)
        await db.flush()
        project = Project(
            name=f"ai_t4_proj_{uuid.uuid4().hex[:8]}",
            client_name="Task4 并发夹具",
            audit_year=FIXTURE_AUDIT_YEAR,
        )
        db.add(project)
        await db.flush()
        db.add(
            ProjectUser(
                project_id=project.id,
                user_id=user.id,
                role=ProjectUserRole.manager,
                scope_cycles="D",
            )
        )
        note = DisclosureNote(
            project_id=project.id,
            year=FIXTURE_AUDIT_YEAR,
            note_section="五、并发夹具",
            section_title="货币资金",
            section_id=f"sec_{uuid.uuid4().hex[:8]}",
            text_content="附注正文",
        )
        db.add(note)
        await db.flush()
        ids = {"user_id": user.id, "project_id": project.id, "note_id": note.id}
        await db.commit()
    return ids


def _committed_request(ids: dict[str, Any], idem: uuid.UUID) -> ChatRunRequest:
    return ChatRunRequest.model_validate(
        {
            "host": {
                "type": HostType.note.value,
                "id": str(ids["note_id"]),
                "project_id_assertion": str(ids["project_id"]),
                "year_assertion": FIXTURE_AUDIT_YEAR,
            },
            "query": "并发幂等提问",
            "idempotency_key": str(idem),
        }
    )


async def _concurrent_create(engine, ids: dict[str, Any]) -> dict[str, Any]:
    """100 个并发 ``create_run``（同一 idempotency key），各持独立连接与事务。"""
    idem = uuid.uuid4()
    engine_invocations: list[str] = []

    async def one(_i: int) -> bool:
        async with AsyncSession(bind=engine) as db:
            user = await db.get(User, ids["user_id"])
            creation = await ChatRunService(db).create_run(
                user, _committed_request(ids, idem)
            )
            created = creation.created
            await db.commit()
            if creation.should_invoke_engine:
                engine_invocations.append(str(creation.run_id))
            return created

    flags = await asyncio.gather(*[one(i) for i in range(CONCURRENCY)])

    async with engine.begin() as conn:
        run_rows = (
            await conn.execute(
                sa.text(
                    "SELECT id FROM ai_chat_runs WHERE actor_id = :u AND idempotency_key = :k"
                ),
                {"u": ids["user_id"], "k": str(idem)},
            )
        ).fetchall()
        session_rows = (
            await conn.execute(
                sa.text("SELECT id FROM ai_chat_session WHERE user_id = :u"),
                {"u": ids["user_id"]},
            )
        ).fetchall()
        user_messages = (
            await conn.execute(
                sa.text(
                    "SELECT count(*) FROM ai_chat_message "
                    "WHERE run_id = :r AND role = 'user'"
                ),
                {"r": run_rows[0][0]},
            )
        ).scalar_one()
    return {
        "created_count": sum(1 for f in flags if f),
        "run_row_count": len(run_rows),
        "session_row_count": len(session_rows),
        "engine_invocation_count": len(engine_invocations),
        "user_message_count": user_messages,
        "session_id": session_rows[0][0],
    }


async def _concurrent_terminal_race(
    engine, ids: dict[str, Any], session_id: UUID
) -> dict[str, Any]:
    """100 个并发终态尝试（done/error/cancelled 轮转）竞争同一 running run。"""
    async with AsyncSession(bind=engine) as db:
        run, _ = await upsert_run(
            db,
            session_id=session_id,
            actor_id=ids["user_id"],
            idempotency_key=f"race-{uuid.uuid4().hex[:12]}",
            project_id=ids["project_id"],
            host_type=HostType.note,
            host_id=str(ids["note_id"]),
            engine=ChatEngineName.native,
        )
        run_id = run.id
        assert await ChatRunService(db).mark_running(run_id) is True
        await db.commit()

    async def one(i: int) -> tuple[str, str | None]:
        async with AsyncSession(bind=engine) as db:
            svc = ChatRunService(db)
            kind = ("done", "error", "cancelled")[i % 3]
            if kind == "done":
                session_obj = await db.get(AIChatSession, session_id)
                event, _msg = await svc.finish_success(
                    session=session_obj, run_id=run_id, text=f"并发回复 {i}"
                )
            elif kind == "error":
                event = await svc.finish_error(
                    run_id=run_id, error_code=ChatErrorCode.engine_unavailable
                )
            else:
                event = await svc.finish_cancelled(run_id=run_id)
            await db.commit()
            return kind, event.type.value if event is not None else None

    outcomes = await asyncio.gather(*[one(i) for i in range(CONCURRENCY)])
    winners = [(kind, ev) for kind, ev in outcomes if ev is not None]

    async with engine.begin() as conn:
        status = (
            await conn.execute(
                sa.text("SELECT status FROM ai_chat_runs WHERE id = :r"), {"r": run_id}
            )
        ).scalar_one()
        completed = (
            await conn.execute(
                sa.text(
                    "SELECT count(*) FROM ai_chat_message "
                    "WHERE run_id = :r AND role = 'assistant' AND status = :s"
                ),
                {"r": run_id, "s": ChatMessageStatus.completed.value},
            )
        ).scalar_one()
        finished_at = (
            await conn.execute(
                sa.text("SELECT finished_at FROM ai_chat_runs WHERE id = :r"), {"r": run_id}
            )
        ).scalar_one()
    return {
        "terminal_event_count": len(winners),
        "winner_kind": winners[0][0] if winners else None,
        "winner_event": winners[0][1] if winners else None,
        "db_status": status,
        "completed_assistant_count": completed,
        "finished_at_set": finished_at is not None,
        "run_id": run_id,
    }


async def _post_terminal_flood(
    engine, ids: dict[str, Any], session_id: UUID
) -> dict[str, Any]:
    """先落定 error 终态，再 100 并发尝试 done —— 全部必须落空。"""
    async with AsyncSession(bind=engine) as db:
        run, _ = await upsert_run(
            db,
            session_id=session_id,
            actor_id=ids["user_id"],
            idempotency_key=f"flood-{uuid.uuid4().hex[:12]}",
            project_id=ids["project_id"],
            host_type=HostType.note,
            host_id=str(ids["note_id"]),
            engine=ChatEngineName.native,
        )
        run_id = run.id
        svc = ChatRunService(db)
        assert await svc.mark_running(run_id) is True
        first = await svc.finish_error(
            run_id=run_id, error_code=ChatErrorCode.context_build_failed
        )
        assert first is not None
        await db.commit()

    async def one(i: int) -> str | None:
        async with AsyncSession(bind=engine) as db:
            session_obj = await db.get(AIChatSession, session_id)
            event, _msg = await ChatRunService(db).finish_success(
                session=session_obj, run_id=run_id, text=f"终态后的成功回复 {i}"
            )
            await db.commit()
            return event.type.value if event is not None else None

    late = await asyncio.gather(*[one(i) for i in range(CONCURRENCY)])

    async with engine.begin() as conn:
        status = (
            await conn.execute(
                sa.text("SELECT status FROM ai_chat_runs WHERE id = :r"), {"r": run_id}
            )
        ).scalar_one()
        assistant_rows = (
            await conn.execute(
                sa.text(
                    "SELECT count(*) FROM ai_chat_message "
                    "WHERE run_id = :r AND role = 'assistant'"
                ),
                {"r": run_id},
            )
        ).scalar_one()
    return {
        "late_done_count": sum(1 for e in late if e is not None),
        "db_status": status,
        "assistant_message_count": assistant_rows,
        "run_id": run_id,
    }


async def _collect() -> dict[str, Any]:
    # 🔴 不开 pool_pre_ping：asyncpg 下 pre-ping 会在池回收路径上同步调用 ping()，
    #    落在 greenlet 上下文之外 ⇒ MissingGreenlet（Task 3 实测踩过）。
    engine = create_async_engine(
        app_settings.DATABASE_URL, pool_size=20, max_overflow=10
    )
    cleanup: dict[str, Any] = {}
    try:
        ids = await _make_committed_fixture(engine)
        # 🔴 清理登记在**任何后续步骤之前**完成：登记写在后面时，中途异常会让 finally
        #    拿不到 ID，真实写入的 user/project 变成 dev 库垃圾（Task 3 实测踩过）。
        cleanup.update(ids)
        create = await _concurrent_create(engine, ids)
        cleanup["session_id"] = create["session_id"]
        race = await _concurrent_terminal_race(engine, ids, create["session_id"])
        flood = await _post_terminal_flood(engine, ids, create["session_id"])
        return {"create": create, "race": race, "flood": flood, "ids": ids}
    finally:
        stmts: list[tuple[str, dict[str, Any]]] = []
        uid = cleanup.get("user_id")
        pid = cleanup.get("project_id")
        if uid:
            stmts += [
                (
                    "DELETE FROM ai_chat_message WHERE session_id IN "
                    "(SELECT id FROM ai_chat_session WHERE user_id = :u)",
                    {"u": uid},
                ),
                ("DELETE FROM ai_chat_runs WHERE actor_id = :u", {"u": uid}),
                ("DELETE FROM ai_chat_session WHERE user_id = :u", {"u": uid}),
            ]
        if pid:
            stmts += [
                ("DELETE FROM disclosure_notes WHERE project_id = :p", {"p": pid}),
                ("DELETE FROM project_users WHERE project_id = :p", {"p": pid}),
            ]
        if uid:
            # 列名是 actor_user_id（不是 actor_id）。本夹具的请求全部授权通过，理论上
            # 不产生 outbox 行；这条只是兜住"将来加了拒绝场景"的清理缺口。
            stmts.append(
                (
                    "DELETE FROM wp_access_security_outbox WHERE actor_user_id = :u",
                    {"u": uid},
                )
            )
        if pid:
            stmts.append(("DELETE FROM projects WHERE id = :p", {"p": pid}))
        if uid:
            stmts.append(("DELETE FROM users WHERE id = :u", {"u": uid}))

        for sql, params in stmts:
            try:
                async with engine.begin() as conn:
                    await conn.execute(sa.text(sql), params)
            except Exception as exc:  # noqa: BLE001 - 记录并继续清理下一条
                print(f"[cleanup] {sql[:60]}… 失败: {type(exc).__name__}: {exc}")

        leftovers: dict[str, int] = {}
        try:
            async with engine.begin() as conn:
                for table, col, val in (
                    ("ai_chat_session", "user_id", uid),
                    ("ai_chat_runs", "actor_id", uid),
                    ("disclosure_notes", "project_id", pid),
                    ("users", "id", uid),
                    ("projects", "id", pid),
                ):
                    if val is None:
                        continue
                    leftovers[table] = (
                        await conn.execute(
                            sa.text(f"SELECT count(*) FROM {table} WHERE {col} = :v"),
                            {"v": val},
                        )
                    ).scalar_one()
        except Exception as exc:  # noqa: BLE001
            print(f"[cleanup] 复核失败: {type(exc).__name__}: {exc}")
        if any(leftovers.values()):
            print(f"[cleanup] ⚠️ 仍有残留（需人工清理）: {leftovers}")
        await engine.dispose()


@pytest.fixture(scope="module")
def concurrency() -> dict[str, Any]:
    """模块级：一次 ``asyncio.run`` 取完三个并发场景的快照。"""
    if not IS_PG:
        pytest.skip("need PostgreSQL (并发 CAS)")
    return asyncio.run(_collect())


@needs_pg
class TestConcurrentIdempotencyAndTerminalRace:
    """**Validates: Requirements 4.5, 4.6**（Property 6 后半 + Property 7 竞态）"""

    def test_hundred_concurrent_creates_produce_one_run_one_message(self, concurrency):
        """100 并发相同 idempotency key → 一个 run、一条 user message、一次 engine 调用。

        Property 6。跨连接并发**必须**真提交才可见；此处的一致性完全来自
        ``uq_ai_chat_runs_idempotency``，不是应用层判断。
        """
        c = concurrency["create"]
        assert c["run_row_count"] == 1, f"run 落库 {c['run_row_count']} 行（应为 1）"
        assert c["session_row_count"] == 1, (
            f"session 落库 {c['session_row_count']} 行（应为 1）"
        )
        assert c["created_count"] == 1, (
            f"{c['created_count']} 个并发调用自称创建者（应恰好 1）"
        )
        assert c["engine_invocation_count"] == 1, (
            f"engine 可被调用 {c['engine_invocation_count']} 次（应为 1）"
        )
        assert c["user_message_count"] == 1, (
            f"该 run 下有 {c['user_message_count']} 条 user message（应为 1）"
        )

    def test_hundred_concurrent_terminals_yield_exactly_one_terminal_event(
        self, concurrency
    ):
        """100 并发混合终态尝试 → terminal event 恰好一个，且与库内状态一致。

        Property 7 的竞态侧：胜者由 PG 行锁 + WHERE 重求值决定，其余 99 个必须拿到 None。
        """
        r = concurrency["race"]
        assert r["terminal_event_count"] == 1, (
            f"产生了 {r['terminal_event_count']} 个终态事件（应恰好 1）"
        )
        expected_status = {
            "done": ChatRunStatus.done,
            "error": ChatRunStatus.error,
            "cancelled": ChatRunStatus.cancelled,
        }[r["winner_kind"]]
        assert r["db_status"] == expected_status.value, (
            f"胜者是 {r['winner_kind']} 但库内状态是 {r['db_status']}"
        )
        assert r["winner_event"] == TERMINAL_EVENT_BY_RUN_STATUS[expected_status].value
        assert r["finished_at_set"] is True, "终态未写 finished_at"
        expected_completed = 1 if r["winner_kind"] == "done" else 0
        assert r["completed_assistant_count"] == expected_completed, (
            f"胜者 {r['winner_kind']} 下有 {r['completed_assistant_count']} 条 completed "
            f"assistant 消息（应为 {expected_completed}）"
        )

    def test_no_late_done_or_assistant_message_after_terminal(self, concurrency):
        """终态落定后，100 并发 ``finish_success`` 全部落空且**零** assistant 消息。

        Property 7 的确定性侧：胜者已知（error），因此断言是"恒 0"而不是"看竞争结果"。
        """
        f = concurrency["flood"]
        assert f["late_done_count"] == 0, (
            f"终态之后仍有 {f['late_done_count']} 次 done 成功"
        )
        assert f["db_status"] == ChatRunStatus.error.value
        assert f["assistant_message_count"] == 0, (
            f"终态之后写入了 {f['assistant_message_count']} 条 assistant 消息"
        )


def _utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def test_contract_version_is_declared():
    """契约版本存在（不兼容变更必须升版本，否则新旧前端各自解读同一条流）。"""
    assert re.fullmatch(r"v\d+", CONTRACT_VERSION), CONTRACT_VERSION
    assert ChatRunAccepted.model_config.get("frozen") is True
