"""外部 LLM provider 闭环：密文、权限、endpoint policy 与真实调用链。"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import base64
import httpx
import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.deps import get_current_user
from app.models.ai_models import AIModelConfig, AIModelType, AIProvider
from app.routers.ai_models import router


@pytest.fixture(autouse=True)
def _isolate_fake_ip_compat_cache():
    # fake-IP 兼容的发现结果是进程级缓存，用例之间必须隔离。
    from app.services import endpoint_dns_compat

    endpoint_dns_compat.clear_cache()
    yield
    endpoint_dns_compat.clear_cache()


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(AIModelConfig.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _actor(role: str):
    return SimpleNamespace(
        id=uuid4(), username=f"{role}-user", role=SimpleNamespace(value=role)
    )


@pytest.fixture
async def admin_client(session_factory):
    app = FastAPI()
    app.include_router(router)

    async def override_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: _actor("admin")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_all_model_endpoints_reject_non_admin(session_factory):
    app = FastAPI()
    app.include_router(router)

    async def override_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: _actor("auditor")
    model_id = uuid4()
    calls = [
        ("GET", "/api/ai-models", None),
        ("GET", "/api/ai-models/providers", None),
        ("GET", "/api/ai-models/health", None),
        ("POST", "/api/ai-models/seed", None),
        ("POST", "/api/ai-models", {
            "model_name": "x", "model_type": "chat", "provider": "openai_compatible",
        }),
        ("PUT", f"/api/ai-models/{model_id}", {"model_name": "x"}),
        ("DELETE", f"/api/ai-models/{model_id}", None),
        ("POST", f"/api/ai-models/{model_id}/test", None),
        ("POST", f"/api/ai-models/{model_id}/activate", None),
    ]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for method, path, body in calls:
            response = await client.request(method, path, json=body)
            assert response.status_code == 403, (method, path, response.text)


@pytest.mark.asyncio
async def test_key_is_ciphertext_and_update_contract(
    admin_client, session_factory, monkeypatch
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "test-fernet-key")
    plaintext = "sk-secret-never-store-this"
    response = await admin_client.post(
        "/api/ai-models",
        json={
            "model_name": "deepseek-chat",
            "model_type": "chat",
            "provider": "deepseek",
            "endpoint_url": "https://api.deepseek.com/v1",
            "api_key": plaintext,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["has_api_key"] is True
    assert "api_key" not in body
    model_id = body["id"]

    async with session_factory() as db:
        row = await db.get(AIModelConfig, UUID(model_id))
        assert row is not None
        first_ciphertext = row.api_key_ciphertext
        assert first_ciphertext and first_ciphertext.startswith("v1:")
        assert plaintext not in first_ciphertext

    # 空白 Key = 保留旧密文。
    kept = await admin_client.put(
        f"/api/ai-models/{model_id}", json={"api_key": "   ", "performance_notes": "保留"}
    )
    assert kept.status_code == 200
    async with session_factory() as db:
        row = await db.get(AIModelConfig, UUID(model_id))
        assert row.api_key_ciphertext == first_ciphertext

    # 改 provider/endpoint 时禁止把不可见旧 Key 沿用到新主机。
    rebound = await admin_client.put(
        f"/api/ai-models/{model_id}",
        json={"provider": "custom", "endpoint_url": "https://attacker.example/v1"},
    )
    assert rebound.status_code == 422
    assert "重新输入 API Key" in rebound.text
    async with session_factory() as db:
        row = await db.get(AIModelConfig, UUID(model_id))
        assert row.provider == AIProvider.deepseek
        assert row.api_key_ciphertext == first_ciphertext

    # 显式 clear 才清除。
    cleared = await admin_client.put(
        f"/api/ai-models/{model_id}", json={"clear_api_key": True}
    )
    assert cleared.status_code == 200
    assert cleared.json()["has_api_key"] is False


@pytest.mark.asyncio
async def test_missing_encryption_key_fails_closed(admin_client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "")
    response = await admin_client.post(
        "/api/ai-models",
        json={
            "model_name": "qwen-plus",
            "model_type": "chat",
            "provider": "qwen",
            "endpoint_url": "https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
            "api_key": "sk-must-not-store",
        },
    )
    assert response.status_code == 503
    assert "ENCRYPTION_KEY" in response.text


@pytest.mark.asyncio
async def test_endpoint_policy_blocks_official_host_spoof_and_metadata(monkeypatch):
    from app.services.llm_endpoint_policy import (
        LLMEndpointPolicyError,
        assert_endpoint_safe,
        validate_endpoint_structure,
    )
    from app.services.llm_provider_registry import provider_profile

    with pytest.raises(LLMEndpointPolicyError, match="官方"):
        validate_endpoint_structure(
            "https://attacker.example/v1", provider_profile(AIProvider.deepseek)
        )
    with pytest.raises(LLMEndpointPolicyError, match="禁止"):
        await assert_endpoint_safe(
            "https://169.254.169.254/v1", provider_profile(AIProvider.custom)
        )

    # IPv6 ::1 同时可能被标为 reserved，但对本地 provider 应按 loopback 放行。
    monkeypatch.setattr(
        "app.services.llm_endpoint_policy.socket.getaddrinfo",
        lambda *args, **kwargs: [(10, 1, 6, "", ("::1", 8100, 0, 0))],
    )
    assert await assert_endpoint_safe(
        "http://localhost:8100/v1", provider_profile(AIProvider.openai_compatible)
    ) == "http://localhost:8100/v1"


@pytest.mark.asyncio
async def test_private_endpoint_requires_explicit_allowlist(monkeypatch):
    from app.core.config import settings
    from app.services.llm_endpoint_policy import assert_endpoint_safe
    from app.services.llm_provider_registry import provider_profile

    endpoint = "http://10.10.0.8:8000/v1"
    monkeypatch.setattr(settings, "LLM_ENDPOINT_ALLOWLIST", endpoint)
    monkeypatch.setattr(
        "app.services.llm_endpoint_policy.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("10.10.0.8", 8000))],
    )
    assert await assert_endpoint_safe(
        endpoint, provider_profile(AIProvider.custom)
    ) == endpoint


def _mock_runtime_client(captured: list[dict]):
    async def factory(config, *, timeout, connect_timeout=10.0):
        headers = {}
        if config.api_key and config.profile.api_key_header == "Authorization":
            headers["Authorization"] = f"Bearer {config.api_key}"
        elif config.api_key and config.profile.api_key_header:
            headers[config.profile.api_key_header] = config.api_key

        def handler(request: httpx.Request) -> httpx.Response:
            payload = None
            if request.content:
                import json
                payload = json.loads(request.content)
            captured.append({
                "url": str(request.url),
                "authorization": request.headers.get("Authorization"),
                "api_key_header": request.headers.get("api-key"),
                "payload": payload,
            })
            if request.url.path.endswith("/embeddings"):
                return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}]})
            if payload and payload.get("stream"):
                content = b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
                return httpx.Response(200, content=content, headers={"content-type": "text/event-stream"})
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        return httpx.AsyncClient(
            base_url=config.endpoint_url.rstrip("/") + "/",
            headers=headers,
            transport=httpx.MockTransport(handler),
        )
    return factory


@pytest.mark.asyncio
async def test_active_db_model_drives_ai_service_and_llm_client(
    session_factory, monkeypatch
):
    from app.core.config import settings
    from app.services.ai_model_secret_service import encrypt_api_key
    from app.services.ai_service import AIService
    import app.services.llm_client as llm_client

    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "runtime-test-key")
    async with session_factory() as db:
        model = AIModelConfig(
            model_name="deepseek-chat",
            model_type=AIModelType.chat,
            provider=AIProvider.deepseek,
            endpoint_url="https://api.deepseek.com/v1",
            api_key_ciphertext=encrypt_api_key("sk-runtime-secret"),
            is_active=True,
            is_deleted=False,
        )
        db.add(model)
        await db.commit()

    captured: list[dict] = []
    monkeypatch.setattr(
        "app.services.llm_runtime.build_runtime_client",
        _mock_runtime_client(captured),
    )
    async with session_factory() as db:
        assert await AIService(db).chat_completion(
            [{"role": "user", "content": "service"}]
        ) == "ok"

    # 模块公共入口必须重新查同一个 active row，而不是读进程全局 URL/Key。
    monkeypatch.setattr(llm_client, "async_session", session_factory)
    assert await llm_client.chat_completion(
        [{"role": "user", "content": "module"}]
    ) == "ok"

    assert len(captured) == 2
    for call in captured:
        assert call["url"] == "https://api.deepseek.com/v1/chat/completions"
        assert call["authorization"] == "Bearer sk-runtime-secret"
        assert call["payload"]["model"] == "deepseek-chat"
        assert "chat_template_kwargs" not in call["payload"]


@pytest.mark.asyncio
async def test_native_engine_model_client_uses_same_runtime(
    session_factory, monkeypatch
):
    from app.core.config import settings
    from app.services.ai_chat.native_engine import AIServiceModelClient
    from app.services.ai_model_secret_service import encrypt_api_key

    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "native-test-key")
    async with session_factory() as db:
        db.add(AIModelConfig(
            model_name="qwen-plus", model_type=AIModelType.chat,
            provider=AIProvider.qwen,
            endpoint_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key_ciphertext=encrypt_api_key("sk-qwen"),
            is_active=True, is_deleted=False,
        ))
        await db.commit()
        captured: list[dict] = []
        monkeypatch.setattr(
            "app.services.llm_runtime.build_runtime_client",
            _mock_runtime_client(captured),
        )
        client = AIServiceModelClient(db)
        model_name = await client.resolve_model()
        chunks = [chunk async for chunk in client.stream_chat(
            [{"role": "user", "content": "native"}], model=model_name
        )]

    assert chunks == ["ok"]
    assert captured[0]["url"].endswith("/compatible-mode/v1/chat/completions")
    assert captured[0]["authorization"] == "Bearer sk-qwen"


def test_provider_registry_covers_enum_and_types():
    from app.services.llm_provider_registry import PROVIDER_PROFILES

    assert set(PROVIDER_PROFILES) == set(AIProvider)
    assert AIModelType.chat in PROVIDER_PROFILES[AIProvider.deepseek].supported_types
    assert PROVIDER_PROFILES[AIProvider.azure_openai].api_key_header == "api-key"
    assert PROVIDER_PROFILES[AIProvider.paddleocr].supported_types == (AIModelType.ocr,)


@pytest.mark.asyncio
async def test_model_endpoints_require_authentication(session_factory):
    app = FastAPI()
    app.include_router(router)

    async def override_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/ai-models/providers")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_rejects_is_active_bypass(admin_client):
    response = await admin_client.post(
        "/api/ai-models",
        json={
            "model_name": "bypass",
            "model_type": "chat",
            "provider": "openai_compatible",
            "is_active": True,
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_test_then_activate_uses_production_transport(
    admin_client, session_factory, monkeypatch
):
    created = await admin_client.post(
        "/api/ai-models",
        json={
            "model_name": "local-qwen",
            "model_type": "chat",
            "provider": "openai_compatible",
            "endpoint_url": "http://localhost:8100/v1",
        },
    )
    assert created.status_code == 200
    model_id = created.json()["id"]
    captured: list[dict] = []
    monkeypatch.setattr(
        "app.services.llm_runtime.build_runtime_client",
        _mock_runtime_client(captured),
    )
    tested = await admin_client.post(f"/api/ai-models/{model_id}/test")
    assert tested.status_code == 200
    assert tested.json()["status"] == "ok"
    activated = await admin_client.post(f"/api/ai-models/{model_id}/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["model_name"] == "local-qwen"
    async with session_factory() as db:
        row = await db.get(AIModelConfig, UUID(model_id))
        assert row.is_active is True
    assert len(captured) == 2
    assert all(call["payload"]["model"] == "local-qwen" for call in captured)


@pytest.mark.asyncio
async def test_enterprise_qwen_config_sends_reasoning_effort_low(
    admin_client, session_factory, monkeypatch
):
    from app.core.config import settings
    from app.services.llm_runtime import chat_sync, resolve_runtime_config

    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "enterprise-qwen-test-key")
    created = await admin_client.post(
        "/api/ai-models",
        json={
            "model_name": "qwen3.8",
            "model_type": "chat",
            "provider": "custom",
            "endpoint_url": "https://ai.gt-china.com.cn:10010/v1",
            "api_key": "sk-placeholder-not-real",
            "context_window": 262144,
            "reasoning_effort": "low",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["context_window"] == 262144
    assert body["reasoning_effort"] == "low"
    assert "api_key" not in body

    async with session_factory() as db:
        row = await db.get(AIModelConfig, UUID(body["id"]))
        row.is_active = True
        await db.commit()
        config = await resolve_runtime_config(db, AIModelType.chat)

    captured: list[dict] = []
    monkeypatch.setattr(
        "app.services.llm_runtime.build_runtime_client",
        _mock_runtime_client(captured),
    )
    assert await chat_sync(config, [{"role": "user", "content": "test"}]) == "ok"
    call = captured[0]
    assert call["url"] == "https://ai.gt-china.com.cn:10010/v1/chat/completions"
    assert call["authorization"] == "Bearer sk-placeholder-not-real"
    assert call["payload"]["model"] == "qwen3.8"
    assert call["payload"]["reasoning_effort"] == "low"
    assert call["payload"]["max_tokens"] == 2000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_name", "capability", "api_path", "response_body", "expected_text"),
    [
        (
            "paddleocrv6", "ocr", "/ocr",
            {"errorCode": 0, "errorMsg": "Success", "result": {"ocrResults": [
                {"prunedResult": {"rec_texts": ["GT OCR TEST"], "rec_scores": [0.99],
                                  "rec_polys": [[[0, 0], [10, 0], [10, 10], [0, 10]]]}}
            ]}},
            "GT OCR TEST",
        ),
        (
            "paddleocrvl-1.6", "layout_parsing", "/layout-parsing",
            {"errorCode": 0, "errorMsg": "Success", "result": {"layoutParsingResults": [
                {"prunedResult": {"page_index": 0, "parsing_res_list": [
                    {"block_label": "text", "block_content": "版面解析结果",
                     "block_bbox": [0, 0, 20, 10], "block_order": 1}
                ]}}
            ]}},
            "版面解析结果",
        ),
    ],
)
async def test_remote_paddlex_contract_without_real_network(
    monkeypatch, model_name, capability, api_path, response_body, expected_text
):
    import app.services.remote_ocr_runtime as remote
    from app.core.config import settings
    from app.services.ai_model_secret_service import encrypt_api_key

    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "remote-ocr-test-key")
    model = AIModelConfig(
        id=uuid4(), model_name=model_name, model_type=AIModelType.ocr,
        provider=AIProvider.paddleocr,
        endpoint_url="https://ai.gt-china.com.cn:10080",
        api_key_ciphertext=encrypt_api_key("gt-placeholder-not-real"),
        ocr_capability=capability, ocr_protocol="paddlex_json",
        api_path=api_path, auth_scheme="bearer", request_timeout_seconds=120,
        is_active=False, is_deleted=False,
    )
    config = remote.resolve_ocr_config_from_model(model)
    captured = {}
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json=response_body)

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    from app.services.llm_endpoint_policy import SafeEndpoint

    monkeypatch.setattr(
        remote, "resolve_endpoint",
        AsyncMock(return_value=SafeEndpoint("https://ai.gt-china.com.cn:10080", "ai.gt-china.com.cn")),
    )
    monkeypatch.setattr(remote.httpx, "AsyncClient", client_factory)
    result = await remote.recognize_remote_bytes(
        config, b"synthetic-image", filename="connection-test.png"
    )
    assert result["text"] == expected_text
    assert captured["url"] == f"https://ai.gt-china.com.cn:10080{api_path}"
    assert captured["authorization"] == "Bearer gt-placeholder-not-real"
    assert captured["payload"]["fileType"] == 1
    assert captured["payload"]["visualize"] is False
    assert base64.b64decode(captured["payload"]["file"]) == b"synthetic-image"


@pytest.mark.asyncio
async def test_two_ocr_capabilities_can_be_active_together(session_factory):
    async with session_factory() as db:
        db.add_all([
            AIModelConfig(
                model_name="paddleocrv6", model_type=AIModelType.ocr,
                provider=AIProvider.paddleocr, ocr_capability="ocr",
                ocr_protocol="local", auth_scheme="none",
                is_active=True, is_deleted=False,
            ),
            AIModelConfig(
                model_name="paddleocrvl-1.6", model_type=AIModelType.ocr,
                provider=AIProvider.paddleocr, endpoint_url="https://ai.gt-china.com.cn:10080",
                ocr_capability="layout_parsing", ocr_protocol="paddlex_json",
                api_path="/layout-parsing", auth_scheme="none",
                is_active=True, is_deleted=False,
            ),
        ])
        await db.commit()
        rows = list((await db.execute(
            select(AIModelConfig).where(AIModelConfig.is_active.is_(True))
        )).scalars().all())
    assert {row.ocr_capability for row in rows} == {"ocr", "layout_parsing"}


@pytest.mark.asyncio
async def test_unified_ocr_prefers_active_remote_adapter(monkeypatch):
    from app.services.unified_ocr_service import OCREngine, UnifiedOCRService

    expected = {
        "text": "远程识别", "engine": "paddleocr_remote",
        "regions": [], "layout_blocks": [], "capability": "ocr",
    }
    remote = AsyncMock(return_value=expected)
    monkeypatch.setattr(
        "app.services.remote_ocr_runtime.recognize_with_active_remote_ocr", remote
    )
    result = await UnifiedOCRService().recognize(
        "never-read-customer-file.png", OCREngine.AUTO
    )
    assert result == expected
    remote.assert_awaited_once_with(
        "never-read-customer-file.png", capability="ocr"
    )


@pytest.mark.asyncio
async def test_ocr_fields_does_not_turn_remote_failure_into_empty_success(monkeypatch):
    from app.services.ocr_fields_service import OcrFieldsService
    from app.services.unified_ocr_service import OCRServiceUnavailableError

    monkeypatch.setattr(
        "app.services.unified_ocr_service.UnifiedOCRService.recognize",
        AsyncMock(side_effect=OCRServiceUnavailableError("remote down")),
    )
    with pytest.raises(OCRServiceUnavailableError, match="remote down"):
        await OcrFieldsService(SimpleNamespace())._perform_ocr("evidence.png")


@pytest.mark.asyncio
async def test_builtin_enterprise_endpoint_honors_fake_ip_without_open_ssrf(monkeypatch):
    from app.core.config import settings
    from app.services.llm_endpoint_policy import LLMEndpointPolicyError, assert_endpoint_safe
    from app.services.llm_provider_registry import provider_profile

    monkeypatch.setattr(
        "app.services.llm_endpoint_policy.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("198.18.0.224", 10010))],
    )
    monkeypatch.setattr(settings, "LLM_ENDPOINT_ALLOWLIST", "")
    # 本用例只验证策略层对 fake-IP 的放行边界；兼容解析另有 test_endpoint_dns_compat.py 覆盖。
    monkeypatch.setattr(settings, "LLM_FAKE_IP_COMPAT", False)
    enterprise = "https://ai.gt-china.com.cn:10010/v1"
    assert await assert_endpoint_safe(
        enterprise, provider_profile(AIProvider.custom)
    ) == enterprise

    untrusted = "https://untrusted.example:10010/v1"
    with pytest.raises(LLMEndpointPolicyError, match="allowlist"):
        await assert_endpoint_safe(untrusted, provider_profile(AIProvider.custom))
    monkeypatch.setattr(settings, "LLM_ENDPOINT_ALLOWLIST", untrusted)
    assert await assert_endpoint_safe(
        untrusted, provider_profile(AIProvider.custom)
    ) == untrusted

    # metadata/link-local 即使误写 allowlist 也必须拒绝。
    metadata = "https://169.254.169.254/v1"
    monkeypatch.setattr(settings, "LLM_ENDPOINT_ALLOWLIST", metadata)
    monkeypatch.setattr(
        "app.services.llm_endpoint_policy.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("169.254.169.254", 443))],
    )
    with pytest.raises(LLMEndpointPolicyError, match="禁止"):
        await assert_endpoint_safe(metadata, provider_profile(AIProvider.custom))


@pytest.mark.asyncio
async def test_enterprise_presets_seed_without_any_api_key(session_factory):
    from app.services.ai_model_presets import ENTERPRISE_MODEL_PRESETS
    from app.services.ai_service import AIService

    async with session_factory() as db:
        await AIService.init_default_models(db)
        await db.commit()
        await AIService.init_default_models(db)
        await db.commit()
        rows = list((await db.execute(
            select(AIModelConfig).where(AIModelConfig.preset_key.is_not(None))
        )).scalars().all())
    assert {row.preset_key for row in rows} == {
        preset.preset_key for preset in ENTERPRISE_MODEL_PRESETS
    }
    assert all(row.api_key_ciphertext is None for row in rows)
    qwen = next(row for row in rows if row.preset_key == "gt_qwen38")
    assert qwen.endpoint_url == "https://ai.gt-china.com.cn:10010/v1"
    assert qwen.context_window == 262144
    # 思考强度默认「未指定」（V195），由用户在配置页选择。
    assert qwen.reasoning_effort is None


@pytest.mark.asyncio
async def test_preset_only_accepts_key_update_and_cannot_be_deleted(
    admin_client, session_factory, monkeypatch
):
    from app.core.config import settings
    from app.services.ai_model_presets import GT_QWEN38

    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "preset-test-key")
    async with session_factory() as db:
        db.add(AIModelConfig(**GT_QWEN38.orm_values()))
        await db.commit()

    forbidden = await admin_client.put(
        f"/api/ai-models/{GT_QWEN38.id}",
        json={"endpoint_url": "https://attacker.example/v1"},
    )
    assert forbidden.status_code == 422
    assert "只允许录入或清除 API Key" in forbidden.text

    saved = await admin_client.put(
        f"/api/ai-models/{GT_QWEN38.id}",
        json={"api_key": "sk-user-input"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["preset_key"] == "gt_qwen38"
    assert saved.json()["has_api_key"] is True
    assert "api_key" not in saved.json()
    deleted = await admin_client.delete(f"/api/ai-models/{GT_QWEN38.id}")
    assert deleted.status_code == 409

    async with session_factory() as db:
        row = await db.get(AIModelConfig, GT_QWEN38.id)
        assert row.api_key_ciphertext.startswith("v1:")
        assert "sk-user-input" not in row.api_key_ciphertext


@pytest.mark.asyncio
async def test_preset_reasoning_effort_is_user_selectable_but_destination_stays_locked(
    admin_client, session_factory, monkeypatch
):
    from app.core.config import settings
    from app.services.ai_model_presets import GT_PADDLEOCR_V6, GT_QWEN38

    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "preset-test-key")
    async with session_factory() as db:
        db.add_all([
            AIModelConfig(**GT_QWEN38.orm_values()),
            AIModelConfig(**GT_PADDLEOCR_V6.orm_values()),
        ])
        await db.commit()

    for value in ("xhigh", None, "medium", "low"):
        saved = await admin_client.put(
            f"/api/ai-models/{GT_QWEN38.id}", json={"reasoning_effort": value}
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["reasoning_effort"] == value
        # 前端据此只展示网关实际支持的取值，并说明「未指定」= 服务端默认 xhigh。
        assert saved.json()["reasoning_effort_options"] == ["low", "medium", "xhigh"]
        assert saved.json()["reasoning_effort_server_default"] == "xhigh"

    # 企业网关实测不接受 high（400 Unexpected reasoning effort high），保存时就拒绝。
    unsupported = await admin_client.put(
        f"/api/ai-models/{GT_QWEN38.id}", json={"reasoning_effort": "high"}
    )
    assert unsupported.status_code == 422, unsupported.text
    assert "low、medium、xhigh" in unsupported.text

    # 思考强度放开不等于预设整体解锁：目的地 / 模型名 / 上下文仍拒绝，且整单不落库。
    for field, value in (
        ("endpoint_url", "https://attacker.example/v1"),
        ("model_name", "qwen-other"),
        ("provider", "openai"),
        ("context_window", 4096),
    ):
        rejected = await admin_client.put(
            f"/api/ai-models/{GT_QWEN38.id}",
            json={"reasoning_effort": "medium", field: value},
        )
        assert rejected.status_code == 422, (field, rejected.text)
    # OCR 预设没有思考强度这一参数。
    ocr = await admin_client.put(
        f"/api/ai-models/{GT_PADDLEOCR_V6.id}", json={"reasoning_effort": "low"}
    )
    assert ocr.status_code == 422, ocr.text

    async with session_factory() as db:
        qwen = await db.get(AIModelConfig, GT_QWEN38.id)
        assert qwen.reasoning_effort == "low"
        assert qwen.endpoint_url == GT_QWEN38.endpoint_url
        assert qwen.model_name == GT_QWEN38.model_name
        assert qwen.context_window == GT_QWEN38.context_window
        assert (await db.get(AIModelConfig, GT_PADDLEOCR_V6.id)).reasoning_effort is None


@pytest.mark.asyncio
async def test_non_preset_reasoning_effort_accepts_xhigh_and_is_unrestricted(admin_client):
    created = await admin_client.post("/api/ai-models", json={
        "model_name": "custom-reasoner", "model_type": "chat",
        "provider": "openai_compatible", "endpoint_url": "http://localhost:8100/v1",
        "reasoning_effort": "xhigh",
    })
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["reasoning_effort"] == "xhigh"
    assert body["reasoning_effort_options"] is None
    assert body["reasoning_effort_server_default"] is None
    updated = await admin_client.put(
        f"/api/ai-models/{body['id']}", json={"reasoning_effort": "high"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["reasoning_effort"] == "high"
