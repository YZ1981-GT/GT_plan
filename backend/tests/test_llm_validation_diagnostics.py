"""模型连接测试 / 激活：推理模型兼容 + 失败原因可诊断（2026-10-19 激活失败复盘）。

现场：企业 qwen3.8 激活只报「模型验证失败，请先检查端点、模型名和凭证」，用户以为 Key 错。
实际是本机代理 TUN 把企业域名解析成 fake-IP 198.18.0.224，代理再用公网 DNS 解析失败后关连接，
客户端只看到 TLS 握手 EOF。另：连接测试原先 max_tokens=1 且要求非空正文，推理模型返回
content=null + finish_reason=length（本机 vLLM Qwen3.5 实测 max_tokens=1/16 均如此）会被误判失败。
"""

from __future__ import annotations

import json
import socket
import ssl
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.deps import get_current_user
from app.models.ai_models import AIModelConfig
from app.routers.ai_models import router


@pytest.fixture(autouse=True)
def _isolate_fake_ip_compat_cache():
    from app.services import endpoint_dns_compat

    endpoint_dns_compat.clear_cache()
    yield
    endpoint_dns_compat.clear_cache()

ENTERPRISE = "https://ai.gt-china.com.cn:10010/v1"
REASONING_ONLY = {
    "choices": [{
        "message": {"role": "assistant", "content": None, "reasoning_content": "用户说 hi"},
        "finish_reason": "length",
    }],
    "usage": {"prompt_tokens": 11, "completion_tokens": 16, "total_tokens": 27},
}


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
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
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


def _runtime_client(handler, captured: list[dict]):
    """替换 build_runtime_client：保留生产 base_url/鉴权头，只把网络换成 MockTransport。"""

    async def factory(config, *, timeout, connect_timeout=10.0):
        def recording(request: httpx.Request) -> httpx.Response:
            captured.append({
                "path": request.url.path,
                "payload": json.loads(request.content) if request.content else None,
            })
            return handler(request)

        headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
        return httpx.AsyncClient(
            base_url=config.endpoint_url.rstrip("/") + "/",
            headers=headers,
            transport=httpx.MockTransport(recording),
        )

    return factory


def _tls_eof(request: httpx.Request) -> httpx.Response:
    try:
        raise ssl.SSLEOFError(8, "EOF occurred in violation of protocol")
    except ssl.SSLError as inner:
        raise httpx.ConnectError("handshake failed", request=request) from inner


def _resolve_to(address: str):
    return lambda *args, **kwargs: [(2, 1, 6, "", (address, 443))]


async def _create(admin_client, **overrides) -> str:
    body = {
        "model_name": "qwen3.8", "model_type": "chat", "provider": "custom",
        "endpoint_url": ENTERPRISE, "api_key": "sk-placeholder-not-real",
        "reasoning_effort": "low",
    }
    body.update(overrides)
    response = await admin_client.post("/api/ai-models", json=body)
    assert response.status_code == 200, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_probe_accepts_reasoning_only_truncated_response(
    admin_client, session_factory, monkeypatch
):
    from app.core.config import settings
    from app.services.llm_runtime import LLMRuntimeError, chat_sync, resolve_config_from_model

    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "diagnostics-test-key")
    model_id = await _create(admin_client)
    captured: list[dict] = []
    monkeypatch.setattr(
        "app.services.llm_runtime.build_runtime_client",
        _runtime_client(lambda request: httpx.Response(200, json=REASONING_ONLY), captured),
    )

    tested = await admin_client.post(f"/api/ai-models/{model_id}/test")
    assert tested.json()["status"] == "ok", tested.text
    activated = await admin_client.post(f"/api/ai-models/{model_id}/activate")
    assert activated.status_code == 200, activated.text

    # 探针与生产同一 payload 形态：思考强度照发，只是输出预算不追求完整答复。
    assert [call["path"] for call in captured] == ["/v1/chat/completions"] * 2
    assert all(call["payload"]["reasoning_effort"] == "low" for call in captured)
    assert all(call["payload"]["max_tokens"] == 16 for call in captured)

    async with session_factory() as db:
        row = await db.get(AIModelConfig, UUID(model_id))
        assert row.is_active is True
        # 生产调用的语义不放宽：真实对话仍必须拿到正文。
        with pytest.raises(LLMRuntimeError) as exc:
            await chat_sync(resolve_config_from_model(row), [{"role": "user", "content": "x"}])
    assert exc.value.code == "output_limit"


@pytest.mark.asyncio
async def test_probe_rejects_non_openai_payload(admin_client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "diagnostics-test-key")
    model_id = await _create(admin_client)
    monkeypatch.setattr(
        "app.services.llm_runtime.build_runtime_client",
        _runtime_client(lambda request: httpx.Response(200, json={"ok": True}), []),
    )
    tested = (await admin_client.post(f"/api/ai-models/{model_id}/test")).json()
    assert (tested["status"], tested["error_code"]) == ("error", "invalid_response")


@pytest.mark.asyncio
async def test_activation_reports_fake_ip_tls_failure_instead_of_generic_hint(
    admin_client, session_factory, monkeypatch
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "diagnostics-test-key")
    model_id = await _create(admin_client)
    monkeypatch.setattr(
        "app.services.llm_runtime.build_runtime_client", _runtime_client(_tls_eof, [])
    )
    monkeypatch.setattr(
        "app.services.llm_endpoint_policy.socket.getaddrinfo", _resolve_to("198.18.0.224")
    )

    tested = (await admin_client.post(f"/api/ai-models/{model_id}/test")).json()
    assert tested["error_code"] == "provider_unreachable"
    assert "TLS 握手被中断" in tested["message"]
    assert "fake-IP 198.18.0.224" in tested["message"]

    activated = await admin_client.post(f"/api/ai-models/{model_id}/activate")
    assert activated.status_code == 400
    detail = activated.json()["detail"]
    assert isinstance(detail, dict), f"激活失败必须返回 code + 具体原因，实际：{detail}"
    assert detail["error_code"] == "provider_unreachable"
    # 服务器模型（企业端点）连不上：仍拒绝启用（只有本机模型允许「当前不可用但已启用」）
    assert detail["message"].startswith("模型验证失败，未启用：模型端点不可达：TLS 握手被中断")
    assert "请检查端点、模型名和凭证" not in detail["message"]
    assert "sk-placeholder-not-real" not in activated.text
    async with session_factory() as db:
        assert (await db.get(AIModelConfig, UUID(model_id))).is_active is False


@pytest.mark.asyncio
async def test_http_400_with_reasoning_effort_points_at_the_parameter(admin_client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "diagnostics-test-key")
    model_id = await _create(admin_client)
    monkeypatch.setattr(
        "app.services.llm_runtime.build_runtime_client",
        _runtime_client(lambda request: httpx.Response(400, json={"error": "bad"}), []),
    )
    tested = (await admin_client.post(f"/api/ai-models/{model_id}/test")).json()
    assert tested["error_code"] == "provider_error"
    assert "思考强度" in tested["message"]
    assert "bad" not in tested["message"], "上游正文不得回传"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("inner", "address", "expected", "hint"),
    [
        (ssl.SSLEOFError(8, "EOF"), "198.18.0.224", "TLS 握手被中断", True),
        (ConnectionResetError(10054, "reset"), "198.18.0.224", "连接被对端重置", True),
        (ssl.SSLCertVerificationError(1, "bad cert"), "198.18.0.224", "TLS 证书校验失败", False),
        (ConnectionRefusedError(10061, "refused"), "203.0.113.10", "连接被拒绝", False),
        (socket.gaierror(11001, "getaddrinfo failed"), "203.0.113.10", "域名解析失败", False),
        (RuntimeError("unknown"), "203.0.113.10", "网络连接失败", False),
    ],
)
async def test_describe_network_failure_classification(monkeypatch, inner, address, expected, hint):
    from app.services.llm_endpoint_policy import describe_network_failure

    monkeypatch.setattr(
        "app.services.llm_endpoint_policy.socket.getaddrinfo", _resolve_to(address)
    )
    try:
        raise inner
    except Exception as cause:
        try:
            raise httpx.ConnectError("x") from cause
        except httpx.ConnectError as exc:
            text = await describe_network_failure(ENTERPRISE, exc)
    assert text.startswith(expected)
    assert ("fake-IP" in text) is hint


@pytest.mark.asyncio
async def test_remote_ocr_test_surfaces_reason_instead_of_engine_unavailable(
    admin_client, monkeypatch
):
    import app.services.remote_ocr_runtime as remote
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "diagnostics-test-key")
    created = await admin_client.post("/api/ai-models", json={
        "model_name": "paddleocrv6", "model_type": "ocr", "provider": "paddleocr",
        "endpoint_url": "https://ai.gt-china.com.cn:10080", "api_key": "gt-placeholder-not-real",
        "ocr_capability": "ocr", "ocr_protocol": "paddlex_json", "api_path": "/ocr",
        "auth_scheme": "bearer",
    })
    assert created.status_code == 200, created.text
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_tls_eof)
        return real_client(*args, **kwargs)

    from app.services.llm_endpoint_policy import SafeEndpoint

    monkeypatch.setattr(
        remote, "resolve_endpoint",
        AsyncMock(return_value=SafeEndpoint("https://ai.gt-china.com.cn:10080", "ai.gt-china.com.cn")),
    )
    monkeypatch.setattr(remote.httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(
        "app.services.llm_endpoint_policy.socket.getaddrinfo", _resolve_to("198.18.0.224")
    )
    tested = (await admin_client.post(f"/api/ai-models/{created.json()['id']}/test")).json()
    assert tested["status"] == "error"
    assert tested["error_code"] == "ocr_unreachable"
    assert tested["message"].startswith("远程 OCR 服务不可达：TLS 握手被中断")
    assert "gt-placeholder-not-real" not in json.dumps(tested, ensure_ascii=False)
