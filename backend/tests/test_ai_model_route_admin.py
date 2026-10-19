"""模型管理接口的本机优先语义（spec llm-ocr-local-first-routing R4 / R6，ADR-ROUTE-002/010）。

启用 / 停用 / 删除 / 改端点走真实路由与真实校验链（出站换成 MockTransport），
路由状态汇总只替换探测函数，验证缓存、强刷、并发合并与冷却联动。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.ai_models import AIModelConfig, AIModelType, AIProvider
from app.routers.ai_models import router
from app.services import llm_route
from tests.test_llm_local_first_routing import _Net

LOCAL = "http://localhost:8100/v1"
ENTERPRISE = "https://ai.gt-china.com.cn:10010/v1"
OCR_HOST = "https://ai.gt-china.com.cn:10080"
CHAT_LOCAL = {"model_name": "Qwen3.5", "model_type": "chat", "provider": "openai_compatible", "endpoint_url": LOCAL}
CHAT_SERVER = {
    "model_name": "qwen3.8", "model_type": "chat", "provider": "custom",
    "endpoint_url": ENTERPRISE, "api_key": "sk-placeholder-not-real",
}
PROBE_OK = {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]}
LOCAL_CHAT_IDENTITY = f"chat|openai_compatible|{LOCAL}|Qwen3.5"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    from app.services import endpoint_dns_compat
    from app.services.model_route_status import clear_route_status_cache

    async def _describe(endpoint, exc):
        return type(exc).__name__

    monkeypatch.setattr("app.services.llm_runtime.describe_network_failure", _describe)
    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "route-admin-test-key")
    endpoint_dns_compat.clear_cache()
    llm_route.reset_route_health()
    clear_route_status_cache()
    yield
    llm_route.reset_route_health()
    clear_route_status_cache()


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(AIModelConfig.__table__.create)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
async def admin_client(session_factory):
    app = FastAPI()
    app.include_router(router)

    async def override_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), username="admin-user", role=SimpleNamespace(value="admin")
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def net(monkeypatch):
    def install(routes: dict[str, object]) -> _Net:
        stub = _Net(routes)
        monkeypatch.setattr("app.services.llm_runtime.build_runtime_client", stub.client)
        return stub

    return install


@pytest.fixture
def local_ocr(monkeypatch):
    """本机 OCR 引擎状态（默认未安装）；远程 OCR 探测默认成功。"""
    from app.services.unified_ocr_service import UnifiedOCRService

    state = {"available": False, "engines": {}, "reason": "本机未安装 PaddleOCR / Tesseract，MinerU 未启用"}
    monkeypatch.setattr(UnifiedOCRService, "local_engine_status", AsyncMock(side_effect=lambda: dict(state)))
    remote_probe = AsyncMock(return_value=None)
    monkeypatch.setattr("app.services.remote_ocr_runtime.probe_remote_ocr", remote_probe)
    return SimpleNamespace(state=state, remote_probe=remote_probe)


async def _create(client, **body) -> str:
    response = await client.post("/api/ai-models", json=body)
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def _active(factory) -> set[tuple[str, str]]:
    async with factory() as db:
        rows = (await db.execute(
            select(AIModelConfig).where(AIModelConfig.is_active.is_(True), AIModelConfig.is_deleted.is_(False))
        )).scalars().all()
    return {(row.model_name, row.deployment) for row in rows}


def _ocr_body(name: str, capability: str, *, remote: bool) -> dict:
    body = {"model_name": name, "model_type": "ocr", "provider": "paddleocr", "ocr_capability": capability}
    if not remote:
        return {**body, "ocr_protocol": "local"}
    path = "/ocr" if capability == "ocr" else "/layout-parsing"
    return {
        **body, "ocr_protocol": "paddlex_json", "endpoint_url": OCR_HOST, "api_path": path,
        "auth_scheme": "bearer", "api_key": "gt-placeholder-not-real",
    }


# ---------------------------------------------------------------------------
# 启用 / 停用 / 删除 / 改端点（R4）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unreachable_local_is_enabled_with_a_truthful_warning(admin_client, net, session_factory):
    local_id = await _create(admin_client, **CHAT_LOCAL)
    server_id = await _create(admin_client, **CHAT_SERVER)
    net({LOCAL: httpx.ConnectError("refused"), ENTERPRISE: httpx.Response(200, json=PROBE_OK)})

    first = await admin_client.post(f"/api/ai-models/{local_id}/activate")
    assert first.status_code == 200, first.text
    assert first.json()["deployment"] == "local"
    assert first.json()["warning"].startswith("本机模型当前不可用（模型端点不可达：ConnectError），已启用")
    assert first.json()["warning"].endswith("该类型尚未启用服务器模型，本机恢复前调用会失败")

    server = await admin_client.post(f"/api/ai-models/{server_id}/activate")
    assert (server.status_code, server.json()["deployment"], server.json()["warning"]) == (200, "server", None)

    again = await admin_client.post(f"/api/ai-models/{local_id}/activate")
    assert again.json()["warning"].endswith("调用时会自动使用已启用的服务器模型兜底")
    # 本机、服务器各一条同时参与路由（V197 前启用服务器会把本机挤掉）
    assert await _active(session_factory) == {("Qwen3.5", "local"), ("qwen3.8", "server")}


@pytest.mark.asyncio
@pytest.mark.parametrize(("body", "endpoint", "failure", "code"), [
    (CHAT_LOCAL, LOCAL, httpx.Response(404), "model_not_found"),        # 本机配置错误：拒绝
    (CHAT_LOCAL, LOCAL, httpx.Response(401), "provider_auth_failed"),
    (CHAT_SERVER, ENTERPRISE, httpx.ConnectError("refused"), "provider_unreachable"),  # 服务器必须连通
])
async def test_config_errors_and_unreachable_servers_are_rejected(
    admin_client, net, session_factory, body, endpoint, failure, code
):
    model_id = await _create(admin_client, **body)
    net({endpoint: failure})
    response = await admin_client.post(f"/api/ai-models/{model_id}/activate")
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error_code"] == code
    assert detail["message"].startswith("模型验证失败，未启用：")
    assert await _active(session_factory) == set()


@pytest.mark.asyncio
async def test_enabling_replaces_only_the_same_deployment(admin_client, net, session_factory):
    net({LOCAL: httpx.Response(200, json=PROBE_OK), ENTERPRISE: httpx.Response(200, json=PROBE_OK)})
    first_server = await _create(admin_client, **CHAT_SERVER)
    backup_server = await _create(admin_client, **{**CHAT_SERVER, "model_name": "qwen3.8-backup"})
    local_id = await _create(admin_client, **CHAT_LOCAL)
    for model_id in (first_server, local_id, backup_server):
        assert (await admin_client.post(f"/api/ai-models/{model_id}/activate")).status_code == 200
    assert await _active(session_factory) == {("Qwen3.5", "local"), ("qwen3.8-backup", "server")}


@pytest.mark.asyncio
async def test_embedding_keeps_one_enabled_model_and_says_there_is_no_fallback(admin_client, net, session_factory):
    vector = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
    net({LOCAL: httpx.ConnectError("refused"), ENTERPRISE: httpx.Response(200, json=vector)})
    server_id = await _create(admin_client, **{**CHAT_SERVER, "model_name": "bge-m3", "model_type": "embedding"})
    local_id = await _create(admin_client, **{**CHAT_LOCAL, "model_name": "Qwen3.5-embed", "model_type": "embedding"})
    assert (await admin_client.post(f"/api/ai-models/{server_id}/activate")).status_code == 200
    response = await admin_client.post(f"/api/ai-models/{local_id}/activate")
    assert response.status_code == 200
    assert response.json()["warning"].endswith("向量模型不跨模型兜底，本机恢复前向量检索不可用")
    assert await _active(session_factory) == {("Qwen3.5-embed", "local")}


@pytest.mark.asyncio
async def test_ocr_capability_slots_hold_local_and_server_together(admin_client, local_ocr, session_factory):
    local_id = await _create(admin_client, **_ocr_body("paddleocr", "ocr", remote=False))
    text_id = await _create(admin_client, **_ocr_body("paddleocrv6", "ocr", remote=True))
    layout_id = await _create(admin_client, **_ocr_body("paddleocrvl-1.6", "layout_parsing", remote=True))

    first = await admin_client.post(f"/api/ai-models/{local_id}/activate")
    assert first.status_code == 200, first.text
    assert "本机 OCR 引擎不可用" in first.json()["warning"]
    assert first.json()["warning"].endswith("该类型尚未启用服务器模型，本机恢复前调用会失败")
    for model_id in (text_id, layout_id):
        response = await admin_client.post(f"/api/ai-models/{model_id}/activate")
        assert (response.status_code, response.json()["warning"]) == (200, None)
    again = await admin_client.post(f"/api/ai-models/{local_id}/activate")
    assert again.json()["warning"].endswith("调用时会自动使用已启用的服务器模型兜底")
    assert local_ocr.remote_probe.await_count == 2
    assert await _active(session_factory) == {
        ("paddleocr", "local"), ("paddleocrv6", "server"), ("paddleocrvl-1.6", "server"),
    }


@pytest.mark.asyncio
async def test_enabled_models_must_be_deactivated_before_deletion(admin_client, net, session_factory):
    net({LOCAL: httpx.Response(200, json=PROBE_OK)})
    model_id = await _create(admin_client, **CHAT_LOCAL)
    assert (await admin_client.post(f"/api/ai-models/{model_id}/activate")).status_code == 200

    refused = await admin_client.delete(f"/api/ai-models/{model_id}")
    assert (refused.status_code, refused.json()["detail"]) == (409, "已启用的模型不能删除，请先停用")
    stopped = await admin_client.post(f"/api/ai-models/{model_id}/deactivate")
    assert (stopped.status_code, stopped.json()["message"]) == (200, "已停用")
    assert await _active(session_factory) == set()
    assert (await admin_client.delete(f"/api/ai-models/{model_id}")).status_code == 200


@pytest.mark.asyncio
async def test_moving_an_enabled_model_into_an_occupied_slot_is_rejected(admin_client, net, session_factory):
    net({LOCAL: httpx.Response(200, json=PROBE_OK), ENTERPRISE: httpx.Response(200, json=PROBE_OK)})
    local_id = await _create(admin_client, **CHAT_LOCAL)
    server_id = await _create(admin_client, **CHAT_SERVER)
    for model_id in (local_id, server_id):
        assert (await admin_client.post(f"/api/ai-models/{model_id}/activate")).status_code == 200

    moved = await admin_client.put(f"/api/ai-models/{local_id}", json={"endpoint_url": ENTERPRISE})
    assert moved.status_code == 409
    assert moved.json()["detail"] == "该类型已启用另一条服务器模型，请先停用后再修改端点"
    async with session_factory() as db:
        row = await db.get(AIModelConfig, UUID(local_id))
        assert (row.endpoint_url, row.deployment, row.is_active) == (LOCAL, "local", True)


@pytest.mark.asyncio
async def test_endpoint_change_recomputes_the_deployment(admin_client):
    model_id = await _create(admin_client, **CHAT_LOCAL)
    response = await admin_client.put(f"/api/ai-models/{model_id}", json={"endpoint_url": ENTERPRISE})
    assert response.status_code == 200, response.text
    assert (response.json()["deployment"], response.json()["warning"]) == ("server", None)


@pytest.mark.asyncio
async def test_saving_an_enabled_local_model_while_it_is_down_keeps_the_change(admin_client, net, session_factory):
    net({LOCAL: httpx.Response(200, json=PROBE_OK), "http://127.0.0.1:8101/v1": httpx.ConnectError("refused")})
    model_id = await _create(admin_client, **CHAT_LOCAL)
    assert (await admin_client.post(f"/api/ai-models/{model_id}/activate")).status_code == 200

    response = await admin_client.put(
        f"/api/ai-models/{model_id}", json={"endpoint_url": "http://127.0.0.1:8101/v1"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["warning"].startswith("本机模型当前不可用")
    async with session_factory() as db:
        row = await db.get(AIModelConfig, UUID(model_id))
        assert (row.endpoint_url, row.deployment, row.is_active) == ("http://127.0.0.1:8101/v1", "local", True)


# ---------------------------------------------------------------------------
# 路由状态（ADR-ROUTE-010）
# ---------------------------------------------------------------------------


@pytest.fixture
def probes(monkeypatch):
    """替换四类探测；对话按部署位置给结果（默认本机不可达、服务器可用）。"""
    from app.services import model_route_status as status

    chat_ok = {"local": False, "server": True}

    async def _chat(config):
        await asyncio.sleep(0.01)
        ok = chat_ok[config.deployment]
        return ok, "可用" if ok else "端点不可达：ConnectError"

    stubs = SimpleNamespace(
        chat=AsyncMock(side_effect=_chat),
        embedding=AsyncMock(return_value=(False, "模型或 API 路径不存在，请检查端点与模型名")),
        ocr_local=AsyncMock(return_value=(False, "本机未安装 PaddleOCR / Tesseract，MinerU 未启用")),
        ocr_remote=AsyncMock(return_value=(True, "可用")),
        chat_ok=chat_ok,
    )
    monkeypatch.setattr(status, "_probe_chat", stubs.chat)
    monkeypatch.setattr(status, "_probe_embedding", stubs.embedding)
    monkeypatch.setattr(status, "_probe_ocr_local", stubs.ocr_local)
    monkeypatch.setattr(status, "_probe_ocr_remote", stubs.ocr_remote)
    return stubs


async def _seed_chat_pair(factory) -> None:
    async with factory() as db:
        db.add_all([
            AIModelConfig(
                model_name="qwen3.8", model_type=AIModelType.chat, provider=AIProvider.custom,
                endpoint_url=ENTERPRISE, deployment="server", is_active=True,
            ),
            AIModelConfig(
                model_name="Qwen3.5", model_type=AIModelType.chat, provider=AIProvider.openai_compatible,
                endpoint_url=LOCAL, deployment="local", is_active=True,
            ),
        ])
        await db.commit()


def _route(status: dict, kind: str) -> dict:
    return next(item for item in status["routes"] if item["kind"] == kind)


@pytest.mark.asyncio
async def test_routes_endpoint_lists_local_then_server_and_the_effective_one(admin_client, session_factory, probes):
    await _seed_chat_pair(session_factory)
    response = await admin_client.get("/api/ai-models/routes")
    assert response.status_code == 200, response.text
    chat = _route(response.json(), "chat")
    assert [(c["deployment"], c["model_name"], c["status"]) for c in chat["candidates"]] == [
        ("local", "Qwen3.5", "unavailable"), ("server", "qwen3.8", "available"),
    ]
    assert chat["effective"]["model_name"] == "qwen3.8"
    assert (chat["policy"], chat["has_local"], chat["has_server"]) == ("local_first", True, True)
    assert chat["candidates"][1]["endpoint"] == ENTERPRISE  # 管理接口返回端点
    assert _route(response.json(), "embedding")["policy"] == "single"
    # 没有启用行：文字识别回落本机内置引擎，版面解析没有候选
    ocr, layout = _route(response.json(), "ocr"), _route(response.json(), "layout_parsing")
    assert [(c["implicit"], c["source"]) for c in ocr["candidates"]] == [(True, "builtin")]
    assert layout["candidates"] == [] and layout["effective"] is None


@pytest.mark.asyncio
async def test_probe_results_are_cached_and_refresh_forces_a_new_probe(session_factory, probes):
    from app.services.model_route_status import collect_route_status

    await _seed_chat_pair(session_factory)
    async with session_factory() as db:
        await collect_route_status(db)
        assert probes.chat.await_count == 2  # 本机、服务器各探一次
        await collect_route_status(db)
        assert probes.chat.await_count == 2  # 30 秒内复用
        await collect_route_status(db, refresh=True)
        assert probes.chat.await_count == 4


@pytest.mark.asyncio
async def test_concurrent_status_requests_share_one_probe_per_candidate(session_factory, probes):
    from app.services.model_route_status import collect_route_status

    await _seed_chat_pair(session_factory)

    async def one():
        async with session_factory() as db:  # AsyncSession 不能并发共用：每个请求各自一个
            return await collect_route_status(db, refresh=True)

    results = await asyncio.gather(one(), one(), one())
    assert probes.chat.await_count == 2
    assert all(_route(item, "chat")["effective"]["model_name"] == "qwen3.8" for item in results)


@pytest.mark.asyncio
async def test_probes_drive_the_route_cooldown(session_factory, probes):
    """「检测状态」也是让路由立刻重试本机的入口：探测失败写冷却，探测成功清冷却。"""
    from app.services.model_route_status import collect_route_status

    await _seed_chat_pair(session_factory)
    async with session_factory() as db:
        status = await collect_route_status(db)
        local = _route(status, "chat")["candidates"][0]
        identity = LOCAL_CHAT_IDENTITY
        assert local["status"] == "unavailable" and llm_route.is_cooling(identity)

        probes.chat_ok["local"] = True
        status = await collect_route_status(db, refresh=True)
    assert _route(status, "chat")["effective"]["deployment"] == "local"
    assert not llm_route.is_cooling(identity)


@pytest.mark.asyncio
async def test_a_failed_call_after_a_cached_success_is_reported(session_factory, probes):
    from app.services.model_route_status import collect_route_status

    probes.chat_ok["local"] = True
    await _seed_chat_pair(session_factory)
    async with session_factory() as db:
        assert _route(await collect_route_status(db), "chat")["effective"]["deployment"] == "local"
        # 探测缓存仍新鲜，但随后一次真实调用失败、路由已在跳过本机：状态页必须与之一致
        llm_route.mark_unavailable(LOCAL_CHAT_IDENTITY, "模型端点不可达：ConnectError")
        chat = _route(await collect_route_status(db), "chat")
    assert chat["candidates"][0]["status"] == "unavailable"
    assert chat["candidates"][0]["reason"] == "最近一次调用失败（冷却中）：模型端点不可达：ConnectError"
    assert chat["effective"]["deployment"] == "server"
    assert probes.chat.await_count == 2  # 没有为此多发探测


@pytest.mark.asyncio
async def test_public_health_probes_chat_only_and_hides_endpoints(session_factory, probes):
    from app.services.ai_service import AIService

    await _seed_chat_pair(session_factory)
    async with session_factory() as db:
        health = await AIService(db).health_check(public=True)
    assert probes.chat.await_count == 2
    probes.embedding.assert_not_awaited()
    probes.ocr_local.assert_not_awaited()
    assert health["llm_status"] == "healthy"
    assert health["chat_config"]["model_name"] == "qwen3.8"
    assert "endpoint_url" not in health["chat_config"]
    assert all("endpoint" not in c for route in health["routes"] for c in route["candidates"])
    assert _route(health, "embedding")["candidates"][0]["status"] == "unknown"


@pytest.mark.asyncio
async def test_same_model_as_chat_and_embedding_keeps_separate_health(session_factory, probes):
    """本机 8100 现状：同一端点同一模型名同时登记为对话与向量，/embeddings 404 而对话正常。

    候选身份不含模型类型时，向量探测失败会写同一条冷却记录 ⇒ 对话路由跳过本机 30 秒，
    状态页也会把两类的探测结果串用。
    """
    from app.services.model_route_status import collect_route_status

    probes.chat_ok["local"] = True
    async with session_factory() as db:
        for model_type in (AIModelType.chat, AIModelType.embedding):
            db.add(AIModelConfig(
                model_name="Qwen3.5", model_type=model_type, provider=AIProvider.openai_compatible,
                endpoint_url=LOCAL, deployment="local", is_active=True,
            ))
        await db.commit()
        status = await collect_route_status(db)
    assert _route(status, "chat")["candidates"][0]["status"] == "available"
    assert _route(status, "embedding")["candidates"][0]["status"] == "unavailable"
    assert not llm_route.is_cooling(LOCAL_CHAT_IDENTITY)
    assert llm_route.is_cooling(f"embedding|openai_compatible|{LOCAL}|Qwen3.5")
