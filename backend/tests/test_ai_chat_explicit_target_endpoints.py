"""AI 采纳 / 笔记转存端点契约（真实路由 + 真实 JSON 请求体解析）

spec: ai-chat-adopt-and-note-target-picker（R2.1 / R4.1 / R5.2）

为什么必须真发请求：旧前端的笔记请求体（嵌套 ``host``、不带 ``session_id``）在真实路由上
**恒 422**，而存量后端测试直接调用端点函数（绕过请求体解析）、唯一的前端守卫又不看请求体
形状 —— 两边都绿、产品里从未成功。这里用 ``TestClient`` 发 JSON：

1. 前端现行请求体被接受，字段原样传到服务层；
2. 旧形状被拒（防回退）；
3. 另选目标时来源宿主只按**读**权限授权、目标按写权限授权。

服务层（``adopt_message`` / ``save_note``）替身掉 —— 其规则由
``dsh_agent_panel/test_adopt_note_explicit_target.py`` 在真实 PostgreSQL 上守卫；宿主授权用
存量同形替身（``_ai_chat_host_stub``，形状由 ``AuthorizedHostContext`` 自校验）并记录调用。
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.deps import get_current_user
from app.routers import doc_ai_chat
from app.services.ai_chat.adopt import AdoptOutcome
from app.services.ai_chat.contracts import GLOBAL_KNOWLEDGE_HOST_ID, AiChatAction
from app.services.ai_chat.note_service import NoteSaveFailed, NoteSaveResult

from ._ai_chat_host_stub import _allow

PROJECT = str(uuid.uuid4())
GLOBAL_HOST = {"type": "global_knowledge", "id": GLOBAL_KNOWLEDGE_HOST_ID,
               "project_id": None, "year": None}


@pytest.fixture
def harness():
    """真实路由 + 依赖替身；``calls`` 记录每次宿主授权的 (doc_type, action, entrypoint)。"""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = MagicMock(value="auditor")
    calls: list[dict] = []

    async def recording_allow(db, current_user, **kw):
        calls.append(kw)
        return await _allow(db, current_user, **kw)

    async def _db():
        yield AsyncMock()

    app = FastAPI()
    app.include_router(doc_ai_chat.router)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    with patch("app.routers.doc_ai_chat._authorize_doc_host", recording_allow):
        yield TestClient(app), calls


def _authorized(calls):
    return [(c["doc_type"], c["action"], c["entrypoint"]) for c in calls]


def _outcome() -> AdoptOutcome:
    return AdoptOutcome(
        ai_content_log_id=uuid.uuid4(), content_hash="a" * 64, message_id=uuid.uuid4(),
        receipt_id=uuid.uuid4(), idempotent_replay=False,
    )


class TestAdoptEndpointBody:
    def test_explicit_target_authorizes_source_for_read_only(self, harness):
        client, calls = harness
        wp = str(uuid.uuid4())
        body = {
            "message_id": str(uuid.uuid4()),
            "host": {"type": "workpaper", "id": wp, "project_id": PROJECT, "year": 2025},
            "source_host": GLOBAL_HOST,
            "target_cell": "D12",
            "idempotency_key": str(uuid.uuid4()),
        }
        with patch("app.routers.doc_ai_chat.adopt_message", new_callable=AsyncMock,
                   return_value=_outcome()) as svc:
            resp = client.post("/api/ai-chat/adopt", json=body)
        assert resp.status_code == 200, resp.text
        assert _authorized(calls) == [
            ("workpaper", AiChatAction.adopt, "ai_chat.adopt"),
            ("global_knowledge", AiChatAction.history, "ai_chat.adopt.source"),
        ]
        kw = svc.call_args.kwargs
        assert kw["host"].resource_type.value == "workpaper" and kw["host"].resource_id == wp
        assert kw["source_host"].resource_type.value == "global_knowledge"
        assert kw["target_cell"] == "D12"

    def test_without_source_host_keeps_single_authorization(self, harness):
        client, calls = harness
        body = {
            "message_id": str(uuid.uuid4()),
            "host": {"type": "workpaper", "id": str(uuid.uuid4()), "project_id": PROJECT,
                     "year": None},
            "idempotency_key": str(uuid.uuid4()),
        }
        with patch("app.routers.doc_ai_chat.adopt_message", new_callable=AsyncMock,
                   return_value=_outcome()) as svc:
            resp = client.post("/api/ai-chat/adopt", json=body)
        assert resp.status_code == 200, resp.text
        assert _authorized(calls) == [("workpaper", AiChatAction.adopt, "ai_chat.adopt")]
        assert svc.call_args.kwargs["source_host"] is None


def _note_result(location: str = "") -> NoteSaveResult:
    return NoteSaveResult(
        document_id=uuid.uuid4(), folder_id=uuid.uuid4(), name="存货监盘要点", location=location,
    )


def _note_body(**overrides) -> dict:
    body = {
        "message_ids": [str(uuid.uuid4())],
        "name": "存货监盘要点",
        "host_type": "global_knowledge",
        "host_id": GLOBAL_KNOWLEDGE_HOST_ID,
        "project_id": None,
        "year": None,
        "idempotency_key": str(uuid.uuid4()),
    }
    body.update(overrides)
    return body


class TestNoteEndpointBody:
    def test_explicit_project_target_without_session_id(self, harness):
        """前端不发 session_id（服务端由消息反查）；显式位置时宿主只按读权限授权。"""
        client, calls = harness
        target = str(uuid.uuid4())
        location = "某项目（项目资料） / AI 对话笔记"
        with patch("app.services.ai_chat.note_service.save_note", new_callable=AsyncMock,
                   return_value=_note_result(location)) as svc:
            resp = client.post("/api/ai-chat/notes", json=_note_body(target_project_id=target))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["location"] == location
        assert data["jump_route"].startswith("/knowledge?folder_id=")
        assert _authorized(calls) == [
            ("global_knowledge", AiChatAction.history, "ai_chat.note_save"),
        ]
        kw = svc.call_args.kwargs
        assert kw["session_id"] is None
        assert kw["target_project_id"] == uuid.UUID(target) and kw["target_folder_id"] is None

    def test_explicit_folder_target(self, harness):
        client, calls = harness
        folder = str(uuid.uuid4())
        with patch("app.services.ai_chat.note_service.save_note", new_callable=AsyncMock,
                   return_value=_note_result()) as svc:
            resp = client.post("/api/ai-chat/notes", json=_note_body(target_folder_id=folder))
        assert resp.status_code == 200, resp.text
        assert svc.call_args.kwargs["target_folder_id"] == uuid.UUID(folder)
        assert calls[0]["action"] is AiChatAction.history

    def test_default_location_authorizes_host_for_note_create(self, harness):
        client, calls = harness
        body = _note_body(host_type="workpaper", host_id=str(uuid.uuid4()), project_id=PROJECT)
        with patch("app.services.ai_chat.note_service.save_note", new_callable=AsyncMock,
                   return_value=_note_result()):
            resp = client.post("/api/ai-chat/notes", json=body)
        assert resp.status_code == 200, resp.text
        assert _authorized(calls) == [
            ("workpaper", AiChatAction.note_create, "ai_chat.note_save"),
        ]

    def test_legacy_nested_host_shape_is_rejected(self, harness):
        """旧前端形状（嵌套 host + *_assertion）必须 422，防止前端回退到它。"""
        client, calls = harness
        legacy = {
            "message_ids": [str(uuid.uuid4())],
            "name": "存货监盘要点",
            "host": {"type": "workpaper", "id": str(uuid.uuid4()),
                     "project_id_assertion": PROJECT, "year_assertion": 2025},
            "idempotency_key": str(uuid.uuid4()),
        }
        with patch("app.services.ai_chat.note_service.save_note",
                   new_callable=AsyncMock) as svc:
            resp = client.post("/api/ai-chat/notes", json=legacy)
        assert resp.status_code == 422
        svc.assert_not_called()
        assert calls == []

    def test_typed_failure_maps_to_422_with_code_and_message(self, harness):
        client, _calls = harness
        with patch("app.services.ai_chat.note_service.save_note", new_callable=AsyncMock,
                   side_effect=NoteSaveFailed("no_target", "请选择笔记保存位置")):
            resp = client.post("/api/ai-chat/notes", json=_note_body())
        assert resp.status_code == 422
        assert resp.json()["detail"] == {"code": "no_target", "message": "请选择笔记保存位置"}
