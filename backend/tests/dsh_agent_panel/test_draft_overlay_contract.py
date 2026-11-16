"""Chat Run 的「未保存草稿」请求契约与字段校验（chat-host-draft-overlay Task 1）。

Requirements:
  - 2.2：纳入时必须携带 ``host_type`` / ``host_id`` / ``baseline_version`` /
    ``content_hash`` / ``content_length``。
  - 3（宿主范围）：第一批只做底稿宿主；附注侧已有 overlay，语义必须一致。
  - 4.2：草稿不得进入任何持久化 AI 产物。
  - 6.1：默认关闭（缺省 ``draft_overlay``）时行为与现状完全一致。

Design: §2 请求契约 / §3 服务端校验顺序（fail-closed）。

本文件只覆盖 **Task 1**（契约 + 校验）。版本核对与 manifest 条目是 Task 2，
不可信内容包装与不落库是 Task 3 —— 它们需要真实 PG 与真实装配链路，
不在此处的纯契约判据里假装覆盖。

判据取向（对应仓库既有纪律）：
  - 「缺省不改变现有行为」用**精确键集/快照相等**证明，不用"没报错"证明；
  - 「服务端重算 hash」用**客户端送假 hash** 的反例证明，而不是读源码看有没有重算；
  - 上限判据用**客户端谎报 content_length=1** 的反例证明（否则"读客户端字段"的实现
    也能通过）。
"""

from __future__ import annotations

import hashlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.services.ai_chat.contracts import HostType
from app.services.ai_chat.draft_overlay import (
    DRAFT_OVERLAY_HOST_TYPES,
    MAX_DRAFT_OVERLAY_CHARS,
    DraftOverlayRef,
)
from app.services.ai_chat.run_contract import (
    PRIVILEGED_REQUEST_FIELDS,
    ChatRunRequest,
)

#: 夹具用的宿主 ID（overlay 必须绑定本次请求的宿主，故两处共用一个值）。
HOST_ID = str(uuid.uuid4())

#: 未保存正文样例（含中文与换行，长度与客户端声明值不同）。
DRAFT_TEXT = "未保存草稿：\n减值测试结论待补，应收款账龄需重算。"


def _body(**overrides: object) -> dict[str, object]:
    """最小合法请求体（workpaper 宿主）。"""
    body: dict[str, object] = {
        "host": {"type": HostType.workpaper.value, "id": HOST_ID},
        "query": "这份底稿的减值测试是否充分？",
        "idempotency_key": str(uuid.uuid4()),
    }
    body.update(overrides)
    return body


def _overlay(**overrides: object) -> dict[str, object]:
    """合法 overlay；``content_length`` / ``content_hash`` 故意与真实值不符。"""
    payload: dict[str, object] = {
        "host_type": HostType.workpaper.value,
        "host_id": HOST_ID,
        "baseline_version": "2026-11-15T10:00:00+00:00",
        "content": DRAFT_TEXT,
        "content_length": 1,
        "content_hash": "0" * 64,
    }
    payload.update(overrides)
    return payload


def _sha256_of(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# ===========================================================================
# 契约形状：缺省不改变现有行为（Req 6.1）
# ===========================================================================


class TestAbsentOverlayKeepsExistingBehaviour:
    """**Validates: Requirements 6.1**"""

    def test_field_is_optional_and_defaults_to_none(self) -> None:
        """``draft_overlay`` 缺省为 None —— 老客户端一字不改仍能通过校验。"""
        request = ChatRunRequest.model_validate(_body())
        assert request.draft_overlay is None

    def test_request_field_set_only_gains_draft_overlay(self) -> None:
        """新增字段**只有** ``draft_overlay``，且它不与越权清单冲突。

        🔴 这里刻意断言完整集合而不是"包含"：少一个字段与多一个字段都是契约变更，
        只查包含会让「顺手加了个字段」静默通过。``PRIVILEGED_REQUEST_FIELDS`` 的交集
        为空是硬要求 —— 声明了越权字段等于让客户端能覆盖服务端权威值。
        """
        fields = set(ChatRunRequest.model_fields)
        assert fields == {
            "host",
            "query",
            "idempotency_key",
            "session_id",
            "mentions",
            "attachment_ids",
            "project_attachment_ids",
            "review_mode",
            "sheet_name",
            "draft_overlay",
        }, f"请求体字段集合漂移：{sorted(fields)}"
        assert not (fields & PRIVILEGED_REQUEST_FIELDS), (
            f"请求体声明了越权字段：{sorted(fields & PRIVILEGED_REQUEST_FIELDS)}"
        )

    def test_context_snapshot_is_byte_identical_and_excludes_overlay(self) -> None:
        """持久化快照与加字段前**逐键相同**，且不含 overlay。

        Req 4.2：草稿不得进入任何持久化 AI 产物。该快照会落
        ``ai_chat_runs.context_request_snapshot``，因此它是"草稿是否落库"的
        直接判据；顺带证明缺省请求的恢复载荷没有被新字段改变。
        """
        with_overlay = ChatRunRequest.model_validate(_body(draft_overlay=_overlay()))
        without = ChatRunRequest.model_validate(_body())
        expected = {
            "mentions": [],
            "attachment_ids": [],
            "project_attachment_ids": [],
            "review_mode": False,
            "sheet_name": None,
        }
        assert without.context_snapshot() == expected
        # 带 overlay 的请求，快照也必须与不带时完全相同（草稿不进快照）。
        assert with_overlay.context_snapshot() == expected


# ===========================================================================
# 服务端重算 hash / 长度（不采信客户端）
# ===========================================================================


class TestServerRecomputesDerivedValues:
    """**Validates: Requirements 2.2**（``content_hash`` 由服务端计算）"""

    def test_client_hash_is_ignored_and_server_hash_is_authoritative(self) -> None:
        """反例：客户端送假 hash → 权威值仍是服务端重算的那个。

        设计 §2 明写「服务端重新算 sha256，不采信客户端传来的 hash」。若实现只是
        把客户端值原样存下，本条会红 —— 这正是它存在的意义。
        """
        forged = "f" * 64
        request = ChatRunRequest.model_validate(
            _body(draft_overlay=_overlay(content_hash=forged))
        )
        overlay = request.draft_overlay
        assert overlay is not None
        assert overlay.content_hash == _sha256_of(DRAFT_TEXT)
        assert overlay.content_hash != forged
        # 客户端值只保留在诊断字段里，不参与任何判定。
        assert overlay.client_content_hash == forged

    def test_server_hash_matches_content_even_without_client_hash(self) -> None:
        """客户端不送 hash 时同样算得出（说明权威值不依赖客户端输入）。"""
        payload = _overlay()
        payload.pop("content_hash")
        overlay = DraftOverlayRef.model_validate(payload)
        assert overlay.content_hash == _sha256_of(DRAFT_TEXT)
        assert overlay.client_content_hash is None

    def test_content_length_is_recomputed_from_actual_content(self) -> None:
        """``content_length`` 由服务端按实际正文覆盖（客户端声明 1 被改写为真实长度）。"""
        overlay = DraftOverlayRef.model_validate(_overlay(content_length=1))
        assert overlay.content_length == len(DRAFT_TEXT)
        assert overlay.content_length != 1

    def test_overlay_is_immutable_after_validation(self) -> None:
        """校验后不能再改正文 —— 否则"先校验后替换"就能绕过长度/空值判据。"""
        overlay = DraftOverlayRef.model_validate(_overlay())
        with pytest.raises(ValidationError):
            overlay.content = "篡改"  # type: ignore[misc]


# ===========================================================================
# 字段校验（每一项都必须真实被拒，且原因是中文可读）
# ===========================================================================


class TestOverlayValidationRejects:
    """**Validates: Requirements 2.2, 3**（design §3 步骤 2~4）"""

    def test_host_id_must_equal_request_host_id(self) -> None:
        """``host_id`` ≠ ``request.host.id`` → 拒绝，且原因点名两个值。

        不允许借 overlay 把别的宿主（哪怕同项目）的正文塞进本轮上下文：
        鉴权过的是 ``host``，内容却来自别处，等于绕过宿主鉴权。
        """
        other = str(uuid.uuid4())
        with pytest.raises(ValidationError) as exc:
            ChatRunRequest.model_validate(_body(draft_overlay=_overlay(host_id=other)))
        text = str(exc.value)
        assert "host_id" in text
        assert other in text and HOST_ID in text, f"原因未点名两个 ID：{text[:300]}"

    def test_host_type_must_match_request_host_type(self) -> None:
        """``host_type`` 与 ``host.type`` 不一致 → 拒绝。"""
        with pytest.raises(ValidationError) as exc:
            ChatRunRequest.model_validate(
                {
                    "host": {"type": HostType.note.value, "id": HOST_ID},
                    "query": "q",
                    "idempotency_key": str(uuid.uuid4()),
                    "draft_overlay": _overlay(),
                }
            )
        assert "host_type" in str(exc.value)

    @pytest.mark.parametrize(
        "host_type",
        [t.value for t in HostType if t not in DRAFT_OVERLAY_HOST_TYPES],
    )
    def test_unsupported_host_type_is_rejected(self, host_type: str) -> None:
        """第一批只接受 workpaper：其余宿主**逐个**真实试一次。

        参数化取值来自 ``HostType`` 全集的差集，而不是手写清单 —— 将来新增宿主类型时
        会自动多一条用例，不会因为漏改清单而静默放行。
        """
        with pytest.raises(ValidationError) as exc:
            DraftOverlayRef.model_validate(_overlay(host_type=host_type))
        assert "暂不支持" in str(exc.value)

    @pytest.mark.parametrize("content", ["", "   ", "\n\t \r\n"])
    def test_empty_or_blank_content_is_rejected(self, content: str) -> None:
        """空 / 全空白正文 → 拒绝（纳入一份空草稿只会浪费预算并误导模型）。"""
        with pytest.raises(ValidationError) as exc:
            DraftOverlayRef.model_validate(_overlay(content=content))
        assert "不能为空" in str(exc.value)

    def test_content_over_limit_is_rejected_not_truncated(self) -> None:
        """超上限 → 拒绝；且**不是**静默裁剪。

        design §2：「超限直接 422，不裁剪（静默裁剪会让模型看到半截内容）」。
        因此断言的是"抛错"，而不是"取回一个变短的 content"。
        """
        too_long = "字" * (MAX_DRAFT_OVERLAY_CHARS + 1)
        with pytest.raises(ValidationError) as exc:
            DraftOverlayRef.model_validate(_overlay(content=too_long))
        text = str(exc.value)
        assert "超过上限" in text
        assert str(MAX_DRAFT_OVERLAY_CHARS) in text

    def test_client_content_length_cannot_bypass_the_limit(self) -> None:
        """反例：客户端谎报 ``content_length=1`` 而正文超限 → 仍被拒。

        若实现用客户端声明的长度判上限，本条会静默通过 —— 这是一个 10MB 正文
        撑爆预算的入口。
        """
        too_long = "字" * (MAX_DRAFT_OVERLAY_CHARS + 1)
        with pytest.raises(ValidationError) as exc:
            DraftOverlayRef.model_validate(_overlay(content=too_long, content_length=1))
        assert "超过上限" in str(exc.value)

    def test_content_exactly_at_limit_is_accepted(self) -> None:
        """边界：正好等于上限应通过（否则实际可用上限比声明的小）。"""
        overlay = DraftOverlayRef.model_validate(
            _overlay(content="字" * MAX_DRAFT_OVERLAY_CHARS)
        )
        assert overlay.content_length == MAX_DRAFT_OVERLAY_CHARS

    def test_unknown_overlay_field_is_rejected(self) -> None:
        """overlay 内的未声明字段一律拒绝（``extra="forbid"``）。"""
        with pytest.raises(ValidationError):
            DraftOverlayRef.model_validate(_overlay(project_id=str(uuid.uuid4())))


# ===========================================================================
# 越权字段豁免必须窄到 draft_overlay 这一层
# ===========================================================================


class TestPrivilegedContentExemptionIsNarrow:
    """**Validates: Requirements 4.2**（正文默认仍属越权字段）"""

    def test_content_inside_overlay_is_accepted(self) -> None:
        """``draft_overlay.content`` 是唯一放行位置（未保存正文只能由前端提交）。"""
        request = ChatRunRequest.model_validate(_body(draft_overlay=_overlay()))
        assert request.draft_overlay is not None
        assert request.draft_overlay.content == DRAFT_TEXT

    @pytest.mark.parametrize(
        "body_factory",
        [
            pytest.param(lambda: _body(content="forged"), id="top-level"),
            pytest.param(
                lambda: {
                    "host": {
                        "type": HostType.workpaper.value,
                        "id": HOST_ID,
                        "content": "forged",
                    },
                    "query": "q",
                    "idempotency_key": str(uuid.uuid4()),
                },
                id="inside-host",
            ),
            pytest.param(
                lambda: _body(mentions=[{"type": "note", "id": "x", "content": "forged"}]),
                id="inside-mention",
            ),
            pytest.param(
                lambda: _body(draft_overlay={**_overlay(), "nested": {"content": "forged"}}),
                id="nested-inside-overlay",
            ),
        ],
    )
    def test_content_elsewhere_is_still_rejected_by_name(self, body_factory) -> None:
        """除 ``draft_overlay.content`` 之外，``content`` 一律按越权字段点名拒绝。

        🔴 豁免写成路径前缀通配就会在这里漏：``host.content`` 与
        ``draft_overlay.nested.content`` 都不该被放行。
        """
        with pytest.raises(ValidationError) as exc:
            ChatRunRequest.model_validate(body_factory())
        text = str(exc.value)
        assert "服务端专属字段" in text, f"未按越权字段点名拒绝：{text[:300]}"
        assert "content" in text


class TestOverlayModuleIsCanonical:
    """**Validates: Requirements 3**（全平台只有一套 overlay 契约）"""

    def test_run_contract_reexports_the_same_objects(self) -> None:
        """``run_contract`` 的重导出必须与 ``draft_overlay`` 是**同一批对象**。

        重导出是为了不打断既有 ``from ...run_contract import DraftOverlayRef`` 的调用方；
        但若将来有人在 ``run_contract`` 里再定义一份同名类，两边就会各自漂移成
        "两套 overlay 契约"（需求 3 明令禁止）。``is`` 判等能直接抓住这种情况。
        """
        import app.services.ai_chat.draft_overlay as canonical
        import app.services.ai_chat.run_contract as reexport

        assert reexport.DraftOverlayRef is canonical.DraftOverlayRef
        assert reexport.MAX_DRAFT_OVERLAY_CHARS == canonical.MAX_DRAFT_OVERLAY_CHARS
        assert reexport.DRAFT_OVERLAY_HOST_TYPES == canonical.DRAFT_OVERLAY_HOST_TYPES


# ===========================================================================
# 端点层：非法 overlay 必须是真的 422（不是 200 + 静默忽略）
# ===========================================================================


@pytest.fixture(scope="module")
def overlay_client() -> TestClient:
    """只挂 AI chat router 的探针 app（不导入 ``app.main``，不起全量 router）。

    鉴权与 DB 依赖被替换成纯内存替身：本文件要判的是**请求体解析**，
    422 在进入 handler 之前就已产生，替身不会被调用。
    """
    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers import doc_ai_chat as route_mod

    probe = FastAPI()
    probe.include_router(route_mod.router)
    probe.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid.uuid4(), username="draft-overlay-probe", role=SimpleNamespace(value="admin")
    )
    probe.dependency_overrides[get_db] = lambda: AsyncMock()
    return TestClient(probe)


class TestEndpointReturns422:
    """**Validates: Requirements 2.2, 6.1**（非法 overlay 是真 422）"""

    @pytest.mark.parametrize(
        "overlay_patch, reason",
        [
            ({"host_id": str(uuid.uuid4())}, "host_id"),
            ({"host_type": HostType.report.value}, "暂不支持"),
            ({"content": ""}, "不能为空"),
            ({"content": "字" * (MAX_DRAFT_OVERLAY_CHARS + 1)}, "超过上限"),
        ],
    )
    def test_invalid_overlay_yields_422(
        self, overlay_client: TestClient, overlay_patch: dict[str, object], reason: str
    ) -> None:
        """非法 overlay → HTTP 422，且响应体点名原因。

        端点层断言不可省：只在模型层 `pytest.raises` 的话，"路由把异常吞成 200"
        这一类接线错误完全测不出来。
        """
        response = overlay_client.post(
            "/api/ai-chat/runs", json=_body(draft_overlay=_overlay(**overlay_patch))
        )
        assert response.status_code == 422, (
            f"预期 422，实际 {response.status_code}：{response.text[:300]}"
        )
        assert reason in response.text, f"422 响应未点名原因 {reason!r}：{response.text[:300]}"

    def test_absent_overlay_reaches_the_handler(self, overlay_client: TestClient) -> None:
        """缺省 overlay 的请求体**能通过解析并进入 handler**（Req 6.1 的向后兼容判据）。

        做法：把 ``ChatRunService.create_run`` 换成抛哨兵异常，断言哨兵被抛出 —— 哨兵能
        抛出来就证明"请求体解析通过了、handler 真的跑到了"。这比断言"状态码不是 422"
        强：后者在 handler 因别的原因 500 时也会通过（假绿）。

        🔴 不断言最终 200：建 run 需要真实 PG 与真实事件总线，那是 Task 4/5 的判据范围。
        """
        from app.services.ai_chat.run_service import ChatRunService

        sentinel = "__draft_overlay_body_parsed__"
        with patch.object(
            ChatRunService, "create_run", new=AsyncMock(side_effect=RuntimeError(sentinel))
        ):
            with pytest.raises(RuntimeError, match=sentinel):
                overlay_client.post("/api/ai-chat/runs", json=_body())


# ===========================================================================
# 透传：已授权请求必须带得上 overlay（Task 2/3 的输入）
# ===========================================================================


class TestOverlayReachesAuthorizedRequest:
    """**Validates: Requirements 2.2**（engine 侧拿得到草稿）"""

    def test_from_creation_passes_overlay_through(self) -> None:
        """``AuthorizedChatRunRequest.from_creation`` 透传 overlay（不重算、不改写）。"""
        from app.models.ai_models import ChatEngineName
        from app.services.ai_chat.engine import AuthorizedChatRunRequest
        from app.services.ai_chat.run_contract import capabilities_for

        request = ChatRunRequest.model_validate(_body(draft_overlay=_overlay()))
        creation = SimpleNamespace(
            run_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            host=SimpleNamespace(resource_type=HostType.workpaper, resource_id=HOST_ID),
            request=request,
            engine=ChatEngineName.native,
            capabilities=capabilities_for(ChatEngineName.native),
        )
        authorized = AuthorizedChatRunRequest.from_creation(creation)
        assert authorized.draft_overlay is request.draft_overlay
        assert authorized.draft_overlay is not None
        assert authorized.draft_overlay.content_hash == _sha256_of(DRAFT_TEXT)

    def test_absent_overlay_stays_none_downstream(self) -> None:
        """缺省时下游也是 None —— 装配层据此走既有分支（Req 6.1）。"""
        from app.models.ai_models import ChatEngineName
        from app.services.ai_chat.engine import AuthorizedChatRunRequest
        from app.services.ai_chat.run_contract import capabilities_for

        request = ChatRunRequest.model_validate(_body())
        creation = SimpleNamespace(
            run_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            host=SimpleNamespace(resource_type=HostType.workpaper, resource_id=HOST_ID),
            request=request,
            engine=ChatEngineName.native,
            capabilities=capabilities_for(ChatEngineName.native),
        )
        assert AuthorizedChatRunRequest.from_creation(creation).draft_overlay is None

    def test_overlay_survives_the_real_coordinator_execution_path(self) -> None:
        """走**真实** ``RunExecution.from_creation`` + ``coerce`` 两级，overlay 不丢。

        🔴 不省这一步的理由：``run_coordinator.RunExecution`` 与
        ``AuthorizedChatRunRequest.from_creation`` 靠**字段同名**对齐（两者互不 import，
        会循环）。只测 ``from_creation`` 的话，"协调器那一层把 request 换掉了"这类
        接线错误测不出来 —— 而那正是 engine 实际拿到的东西。
        """
        from app.models.ai_models import ChatEngineName
        from app.services.ai_chat.engine import AuthorizedChatRunRequest
        from app.services.ai_chat.run_contract import capabilities_for
        from app.services.ai_chat.run_coordinator import RunExecution

        request = ChatRunRequest.model_validate(_body(draft_overlay=_overlay()))
        creation = SimpleNamespace(
            run_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            host=SimpleNamespace(principal_id=uuid.uuid4()),
            request=request,
            engine=ChatEngineName.native,
            capabilities=capabilities_for(ChatEngineName.native),
        )
        execution = RunExecution.from_creation(creation)
        authorized = AuthorizedChatRunRequest.coerce(execution)

        assert authorized.draft_overlay is request.draft_overlay, (
            "overlay 在协调器 / engine 归一链路上丢失"
        )
        assert authorized.draft_overlay.content == DRAFT_TEXT
        assert authorized.draft_overlay.content_hash == _sha256_of(DRAFT_TEXT)
