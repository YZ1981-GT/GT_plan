"""企业预设在模型配置页的录 Key / 启用 / 保存（spec enterprise-embedding-rerank-closure R11）。

走真实路由与校验链（出站换成 MockTransport），模拟用户在前端「录入 Key」→「启用」：
- 没录 Key 的企业预设不能启用（否则网关不可达时会带警告启用，向量还会顶掉现有向量行）；
- 已启用的企业预设重新保存时连不上，与启用同口径：保存并提示（原先 400）；
- 未勾选「清除凭证」（预设表单每次都带 clear_api_key=false）不算连接变更、不重新验证；
- 向量 / 重排预设不可达时的提示按类型说明后果。
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.core.config import settings  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.audit_log_models import AuditChainHead, AuditLogEntry  # noqa: E402
from app.models.ai_models import AIModelConfig, AIModelType  # noqa: E402
from app.routers.ai_models import router  # noqa: E402
from app.services import llm_route  # noqa: E402
from app.services.ai_model_presets import GT_QWEN3_RERANKER_4B, GT_WEMM_EMBEDDING_4B  # noqa: E402
from tests.test_llm_local_first_routing import _Net  # noqa: E402

GATEWAY = "https://ai.gt-china.com.cn:10010/v1"
LOCAL_EMBED = "http://localhost:8100/v1"
TRUST = {"trust_zone": "firm_private", "client_data_allowed": True, "mask_policy": "strict"}


# ── 夹具（与 test_ai_model_route_admin.py 同口径；按名导入会让 ruff 报 F811，故在本文件定义） ──────


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    from app.services import endpoint_dns_compat
    from app.services.model_route_status import clear_route_status_cache

    async def _describe(endpoint, exc):
        return type(exc).__name__

    monkeypatch.setattr("app.services.llm_runtime.describe_network_failure", _describe)
    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "preset-admin-test-key")
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
        for table in (AIModelConfig.__table__, AuditLogEntry.__table__, AuditChainHead.__table__):
            await conn.run_sync(table.create)
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
        id=uuid.uuid4(), username="admin-user", role=SimpleNamespace(value="admin")
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


async def _seed_presets(factory) -> dict[str, str]:
    """两条致同预设（未启用、无 Key）+ 共享库现状那条已启用的本机向量行（复用对话模型、没有 /embeddings）。"""
    async with factory() as db:
        objects: dict[str, AIModelConfig] = {}
        for preset in (GT_WEMM_EMBEDDING_4B, GT_QWEN3_RERANKER_4B):
            row = AIModelConfig(**preset.orm_values())
            row.deployment, row.trust_zone, row.client_data_allowed, row.mask_policy = "server", "firm_private", True, "strict"
            objects[preset.preset_key] = row
        objects["local_embedding"] = AIModelConfig(
            id=uuid.uuid4(), model_name="Kbenkhaled/Qwen3.5-27B-NVFP4", model_type=AIModelType.embedding,
            provider="openai_compatible", endpoint_url=LOCAL_EMBED, is_active=True, deployment="local",
            trust_zone="local_device", client_data_allowed=True, mask_policy="role_based",
        )
        db.add_all(objects.values())
        await db.commit()
        return {key: str(row.id) for key, row in objects.items()}


async def _row(factory, model_id: str) -> AIModelConfig:
    async with factory() as db:
        return (await db.execute(select(AIModelConfig).where(AIModelConfig.id == uuid.UUID(model_id)))).scalar_one()


async def _audit_count(factory) -> int:
    async with factory() as db:
        return int((await db.execute(select(func.count()).select_from(AuditLogEntry))).scalar_one())


@pytest.mark.asyncio
async def test_preset_without_key_cannot_be_activated(admin_client, session_factory, net):
    ids = await _seed_presets(session_factory)
    stub = net({})
    response = await admin_client.post(f"/api/ai-models/{ids['gt_wemm_embedding_4b']}/activate")
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error_code"] == "api_key_required" and "先录入 API Key" in detail["message"]
    assert stub.seen == [], "没有 Key 不应去连网关"
    assert (await _row(session_factory, ids["gt_wemm_embedding_4b"])).is_active is False
    assert (await _row(session_factory, ids["local_embedding"])).is_active is True, "不能顶掉现有向量行"
    assert await _audit_count(session_factory) == 0


@pytest.mark.asyncio
async def test_manual_key_entry_then_activate_replaces_the_local_embedding_row(admin_client, session_factory, net):
    """用户在前端录 Key（PUT，不验证未启用行）→ 启用：网关不可达时带向量专用提示启用，并替换本机向量行。"""
    ids = await _seed_presets(session_factory)
    stub = net({GATEWAY: httpx.ConnectError("refused")})
    saved = await admin_client.put(
        f"/api/ai-models/{ids['gt_wemm_embedding_4b']}",
        json={"api_key": "user-typed-key", "clear_api_key": False, **TRUST},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["has_api_key"] is True and stub.seen == []

    activated = await admin_client.post(f"/api/ai-models/{ids['gt_wemm_embedding_4b']}/activate")
    assert activated.status_code == 200, activated.text
    warning = activated.json()["warning"]
    assert "企业预设当前不可达" in warning and "语义检索不可用" in warning and "词法召回" in warning, warning
    assert "本机恢复前" not in warning, warning
    assert (await _row(session_factory, ids["gt_wemm_embedding_4b"])).is_active is True
    assert (await _row(session_factory, ids["local_embedding"])).is_active is False
    assert await _audit_count(session_factory) == 2  # 录 Key + 启用各一条


@pytest.mark.asyncio
async def test_rerank_preset_unreachable_warning_says_search_is_not_reranked(admin_client, session_factory, net):
    ids = await _seed_presets(session_factory)
    net({GATEWAY: httpx.ConnectError("refused")})
    await admin_client.put(
        f"/api/ai-models/{ids['gt_qwen3_reranker_4b']}",
        json={"api_key": "user-typed-key", "clear_api_key": False, **TRUST},
    )
    activated = await admin_client.post(f"/api/ai-models/{ids['gt_qwen3_reranker_4b']}/activate")
    assert activated.status_code == 200, activated.text
    warning = activated.json()["warning"]
    assert "知识检索不重排" in warning and "AI 调用会失败" not in warning, warning


@pytest.mark.asyncio
async def test_active_preset_resave_unreachable_saves_with_warning(admin_client, session_factory, net):
    ids = await _seed_presets(session_factory)
    net({GATEWAY: httpx.ConnectError("refused")})
    await admin_client.put(
        f"/api/ai-models/{ids['gt_wemm_embedding_4b']}", json={"api_key": "k1", "clear_api_key": False, **TRUST}
    )
    assert (await admin_client.post(f"/api/ai-models/{ids['gt_wemm_embedding_4b']}/activate")).status_code == 200

    replaced = await admin_client.put(
        f"/api/ai-models/{ids['gt_wemm_embedding_4b']}", json={"api_key": "k2", "clear_api_key": False, **TRUST}
    )
    assert replaced.status_code == 200, replaced.text
    assert "语义检索不可用" in (replaced.json()["warning"] or "")


@pytest.mark.asyncio
async def test_unchecked_clear_key_is_not_a_connection_change(admin_client, session_factory, net):
    ids = await _seed_presets(session_factory)
    stub = net({GATEWAY: httpx.Response(200, json={"data": [{"embedding": [0.0] * 1024, "index": 0}]})})
    await admin_client.put(
        f"/api/ai-models/{ids['gt_wemm_embedding_4b']}", json={"api_key": "k1", "clear_api_key": False, **TRUST}
    )
    assert (await admin_client.post(f"/api/ai-models/{ids['gt_wemm_embedding_4b']}/activate")).status_code == 200
    calls = len(stub.seen)
    assert calls >= 1, "启用要真发一次向量请求"

    policy_only = await admin_client.put(
        f"/api/ai-models/{ids['gt_wemm_embedding_4b']}",
        json={"clear_api_key": False, "trust_zone": "firm_private", "client_data_allowed": True, "mask_policy": "strict"},
    )
    assert policy_only.status_code == 200, policy_only.text
    assert len(stub.seen) == calls, "只改信任策略、没勾选清除凭证：不应重新验证"
