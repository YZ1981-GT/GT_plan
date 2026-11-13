"""企业向量 / 重排模型接入与知识库向量检索（spec enterprise-embedding-rerank-closure）。

出站一律换成 MockTransport（``_Net``）；路由解析与 AIService 走 SQLite 真 ORM；
检索阶段用 mock 会话只验证编排（真 PG 的写入 / pgvector 召回由一次性库验证脚本覆盖，见 design §5）。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.models.ai_models import AIModelConfig, AIModelType, AIProvider
from app.services import llm_route
from app.services.ai_model_presets import (
    BUILTIN_TRUSTED_ENDPOINTS,
    ENTERPRISE_MODEL_PRESETS,
    GT_QWEN3_RERANKER_4B,
    GT_QWEN38,
    GT_WEMM_EMBEDDING_4B,
)
from app.services.knowledge_vector_support import (
    INDEX_VECTOR_DIM,
    chunk_vector_values,
    has_foreign_signature,
    recall_size,
    rerank_hits,
    score_text_vector_chunks,
)
from app.services.llm_provider_registry import provider_profile
from app.services.llm_runtime import (
    LLMRuntimeError,
    RerankScore,
    ResolvedLLMConfig,
    RouteCandidate,
    embedding,
    rerank,
    resolve_config_from_model,
    resolve_route,
)
from app.services.llm_runtime import test_runtime_config as run_connection_test  # 别名：免被当成用例收集
from tests._kb_mock_session import make_retrieval_session
from tests.test_llm_local_first_routing import _Net

LOCAL = "http://localhost:8100/v1"
ENTERPRISE = GT_QWEN38.endpoint_url
MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    from app.services.model_route_status import clear_route_status_cache

    async def _describe(endpoint, exc):
        return type(exc).__name__

    monkeypatch.setattr("app.services.llm_runtime.describe_network_failure", _describe)
    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "embed-rerank-test-key")
    llm_route.reset_route_health()
    llm_route.clear_route_outcome()
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
def net(monkeypatch):
    def install(routes: dict[str, object]) -> _Net:
        stub = _Net(routes)
        monkeypatch.setattr("app.services.llm_runtime.build_runtime_client", stub.client)
        return stub

    return install


def _config(
    model_type: AIModelType, *, endpoint: str = ENTERPRISE, model_name: str = "m", dims: int | None = None
) -> ResolvedLLMConfig:
    local = endpoint.startswith("http://localhost")
    provider = AIProvider.openai_compatible if local else AIProvider.custom
    return ResolvedLLMConfig(
        model_name=model_name, model_type=model_type, provider=provider, endpoint_url=endpoint,
        api_key=None, profile=provider_profile(provider), source="database",
        deployment="local" if local else "server", embedding_dimensions=dims,
        trust_zone="local_device" if local else "firm_private", client_data_allowed=True,
    )


def _candidate(config: ResolvedLLMConfig) -> RouteCandidate:
    return RouteCandidate(config.model_name, config.deployment, uuid4(), config)


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


# ── R1 企业预设 ────────────────────────────────────────────────────────────────


def test_enterprise_presets_share_the_qwen38_gateway_and_declare_index_dims():
    assert GT_WEMM_EMBEDDING_4B in ENTERPRISE_MODEL_PRESETS
    assert GT_QWEN3_RERANKER_4B in ENTERPRISE_MODEL_PRESETS
    for preset in (GT_WEMM_EMBEDDING_4B, GT_QWEN3_RERANKER_4B):
        assert preset.endpoint_url == ENTERPRISE and preset.endpoint_url in BUILTIN_TRUSTED_ENDPOINTS
        assert preset.provider == AIProvider.custom and preset.orm_values()["is_active"] is False
    assert (GT_WEMM_EMBEDDING_4B.model_name, GT_WEMM_EMBEDDING_4B.model_type) == (
        "wemm-embedding-4b", AIModelType.embedding,
    )
    assert (GT_QWEN3_RERANKER_4B.model_name, GT_QWEN3_RERANKER_4B.model_type) == (
        "qwen3-reranker-4b", AIModelType.rerank,
    )
    # 预设维度必须等于索引列维度：否则写进 vector(1024) 必被拒收
    assert GT_WEMM_EMBEDDING_4B.embedding_dimensions == INDEX_VECTOR_DIM == 1024
    assert GT_QWEN3_RERANKER_4B.embedding_dimensions is None
    assert len({preset.id for preset in ENTERPRISE_MODEL_PRESETS}) == len(ENTERPRISE_MODEL_PRESETS)


def test_v262_seed_rows_match_the_preset_single_source():
    # 向量预设的固定 id 在 dev1.0 合并时改为 …0006（…0004 已被 V208 的 qwen3.7-max 占用），由 V271 补建；
    # V262 已在部分库落地，不改它的内容（否则 checksum 漂移）⇒ 种子来源 = V262 + V271。
    sql = "\n".join(
        next(MIGRATIONS.glob(pattern)).read_text(encoding="utf-8")
        for pattern in ("V262__*.sql", "V271__*.sql")
    )
    for preset in (GT_WEMM_EMBEDDING_4B, GT_QWEN3_RERANKER_4B):
        for value in (str(preset.id), preset.preset_key, preset.model_name, preset.endpoint_url,
                      preset.performance_notes, f"'{preset.model_type.value}'::ai_model_type_enum"):
            assert value in sql, (preset.preset_key, value)
    assert "api_key" not in sql.lower(), "种子不得预置任何 Key"


def test_dimensions_come_only_from_the_embedding_preset():
    preset_row = AIModelConfig(**GT_WEMM_EMBEDDING_4B.orm_values(), deployment="server", is_deleted=False)
    assert resolve_config_from_model(preset_row).embedding_dimensions == 1024
    custom_row = AIModelConfig(
        model_name="other-embed", model_type=AIModelType.embedding, provider=AIProvider.custom,
        endpoint_url=ENTERPRISE, deployment="server", is_deleted=False,
    )
    assert resolve_config_from_model(custom_row).embedding_dimensions is None
    chat_row = AIModelConfig(**GT_QWEN38.orm_values(), deployment="server", is_deleted=False)
    assert resolve_config_from_model(chat_row).embedding_dimensions is None


# ── R3 向量调用 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_embedding_sends_dimensions_and_rejects_a_wrong_size(net):
    stub = net({ENTERPRISE: httpx.Response(200, json={"data": [{"embedding": [0.1] * 1024}]})})
    vector = await embedding(_config(AIModelType.embedding, dims=1024), "应收账款")
    assert len(vector) == 1024
    assert _body(stub.seen[-1]) == {"model": "m", "input": "应收账款", "dimensions": 1024}

    net({ENTERPRISE: httpx.Response(200, json={"data": [{"embedding": [0.1] * 2560}]})})
    with pytest.raises(LLMRuntimeError) as exc:
        await embedding(_config(AIModelType.embedding, dims=1024), "x")
    assert exc.value.code == "embedding_dimension_mismatch" and exc.value.kind == "config"

    stub = net({LOCAL: httpx.Response(200, json={"data": [{"embedding": [0.1] * 768}]})})
    assert len(await embedding(_config(AIModelType.embedding, endpoint=LOCAL), "x")) == 768
    assert "dimensions" not in _body(stub.seen[-1])  # 未声明维度的模型不发 dimensions


# ── R2 重排调用与路由 ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rerank_parses_cohere_results_sorted_and_skips_bad_items(net):
    results = [
        {"index": 0, "relevance_score": 0.1},
        {"index": 2, "relevance_score": 0.9},
        {"index": 7, "relevance_score": 1.0},  # 越界
        {"index": 1, "score": 0.5},  # 兼容 score 键
        {"index": True, "relevance_score": 0.8},  # bool 不是下标
        {"index": 2, "relevance_score": 0.3},  # 重复下标只认第一条
    ]
    stub = net({ENTERPRISE: httpx.Response(200, json={"results": results})})
    scores = await rerank(_config(AIModelType.rerank), "坏账", ["a", "b", "c"], top_n=3)
    assert scores == [RerankScore(2, 0.9), RerankScore(1, 0.5), RerankScore(0, 0.1)]
    request = stub.seen[-1]
    assert str(request.url) == f"{ENTERPRISE}/rerank"
    assert _body(request) == {"model": "m", "query": "坏账", "documents": ["a", "b", "c"], "top_n": 3}


@pytest.mark.asyncio
async def test_rerank_rejects_incompatible_bodies_and_skips_empty_input(net):
    net({ENTERPRISE: httpx.Response(200, json={"data": []})})
    with pytest.raises(LLMRuntimeError) as exc:
        await rerank(_config(AIModelType.rerank), "q", ["a"])
    assert exc.value.code == "invalid_response" and exc.value.kind == "config"
    net({ENTERPRISE: httpx.Response(200, json={"results": []})})
    with pytest.raises(LLMRuntimeError) as exc:
        await rerank(_config(AIModelType.rerank), "q", ["a"])
    assert exc.value.code == "empty_response"
    net({ENTERPRISE: AssertionError("没有文档时不得发请求")})
    assert await rerank(_config(AIModelType.rerank), "q", []) == []


@pytest.mark.asyncio
async def test_rerank_route_falls_over_without_claiming_the_chat_outcome(net):
    local = _config(AIModelType.rerank, endpoint=LOCAL, model_name="local-rr")
    server = _config(AIModelType.rerank, model_name="qwen3-reranker-4b")
    net({
        LOCAL: httpx.ConnectError("refused"),
        ENTERPRISE: httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.7}]}),
    })
    scores = await llm_route.route_rerank([_candidate(local), _candidate(server)], "q", ["a"])
    assert scores == [RerankScore(0, 0.7)]
    assert llm_route.is_cooling(local.identity) and not llm_route.is_cooling(server.identity)
    # 「对话由谁回答」的记录不能被重排模型改写（生成留痕读它）
    assert llm_route.last_route_outcome() is None


@pytest.mark.asyncio
async def test_rerank_route_raises_non_failover_errors_without_trying_the_server(net):
    local = _config(AIModelType.rerank, endpoint=LOCAL)
    net({LOCAL: httpx.Response(429), ENTERPRISE: AssertionError("限流不得换候选重发")})
    with pytest.raises(LLMRuntimeError) as exc:
        await llm_route.route_rerank([_candidate(local), _candidate(_config(AIModelType.rerank))], "q", ["a"])
    assert exc.value.code == "provider_rate_limited"


@pytest.mark.asyncio
async def test_rerank_route_has_no_env_fallback_and_orders_local_first(session_factory):
    async with session_factory() as db:
        assert await resolve_route(db, AIModelType.rerank) == []
        db.add_all([
            AIModelConfig(model_name="qwen3-reranker-4b", model_type=AIModelType.rerank,
                          provider=AIProvider.custom, endpoint_url=ENTERPRISE, deployment="server",
                          is_active=True, is_deleted=False),
            AIModelConfig(model_name="local-rr", model_type=AIModelType.rerank,
                          provider=AIProvider.openai_compatible, endpoint_url=LOCAL, deployment="local",
                          is_active=True, is_deleted=False),
        ])
        await db.commit()
        route = await resolve_route(db, AIModelType.rerank)
    assert [(c.deployment, c.model_name) for c in route] == [("local", "local-rr"), ("server", "qwen3-reranker-4b")]


@pytest.mark.asyncio
async def test_connection_test_probes_the_rerank_endpoint(net):
    stub = net({ENTERPRISE: httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.5}]})})
    await run_connection_test(_config(AIModelType.rerank))
    assert str(stub.seen[-1].url).endswith("/rerank")


# ── R3 数据政策与签名 ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ai_service_embedding_requires_client_data_and_records_the_signature(session_factory, net):
    from app.services.ai_service import AIService, AIServiceUnavailableError

    async with session_factory() as db:
        values = {**GT_WEMM_EMBEDDING_4B.orm_values(), "is_active": True}
        db.add(AIModelConfig(**values, deployment="server", is_deleted=False,
                             trust_zone="restricted", client_data_allowed=False, mask_policy="strict"))
        await db.commit()
        row = await db.get(AIModelConfig, GT_WEMM_EMBEDDING_4B.id)
        net({ENTERPRISE: AssertionError("受限端点不得收到检索文本")})
        with pytest.raises(AIServiceUnavailableError, match="客户数据"):
            await AIService(db).embedding("应收账款")

        row.trust_zone, row.client_data_allowed = "firm_private", True
        await db.commit()
        stub = net({ENTERPRISE: httpx.Response(200, json={"data": [{"embedding": [0.2] * 1024}]})})
        service = AIService(db)
        assert len(await service.embedding("应收账款")) == 1024
    assert service.last_embedding_signature == "wemm-embedding-4b@1024"
    assert _body(stub.seen[-1])["dimensions"] == 1024


@pytest.mark.asyncio
async def test_ai_service_rerank_is_unavailable_until_a_model_is_enabled(session_factory):
    from app.services.ai_service import AIService, AIServiceUnavailableError

    async with session_factory() as db:
        service = AIService(db)
        assert await service.rerank_route() == []
        with pytest.raises(AIServiceUnavailableError, match="未启用重排模型"):
            await service.rerank("q", ["a", "b"])


# ── R4 / R5 向量列门控 ─────────────────────────────────────────────────────────


def test_chunk_vector_values_gate_the_pgvector_column_and_dimension():
    plain = chunk_vector_values([0.5, 0.25], pgvector_column=False, signature="s@2")
    assert plain == {"embedding_vector": "0.5,0.25", "embedding_model": "s@2"}  # 列不存在就不能出现在语句里
    good = chunk_vector_values([0.1] * 1024, pgvector_column=True, signature="m@1024")
    assert len(good["embedding_vec"]) == 1024
    other = chunk_vector_values([0.1] * 768, pgvector_column=True, signature="bge@768")
    assert "embedding_vec" in other and other["embedding_vec"] is None  # 写 NULL 清掉旧模型的向量


def test_recall_size_widens_only_when_rerank_is_enabled():
    assert recall_size(5, False) == 5
    assert recall_size(5, True) == 15
    assert recall_size(30, True) == 50
    assert recall_size(80, True) == 80  # 上限不小于调用方要的条数


# ── R6 重排阶段 ────────────────────────────────────────────────────────────────


def _hits() -> list[dict]:
    return [
        {"content": "固定资产折旧", "score": 0.8, "source_id": "a", "chunk_index": 0, "source_type": "knowledge_doc"},
        {"content": "坏账准备计提", "score": 0.7, "source_id": "b", "chunk_index": 0, "source_type": "knowledge_doc"},
        {"content": "货币资金", "score": 0.6, "source_id": "c", "chunk_index": 0, "source_type": "knowledge_doc"},
    ]


@pytest.mark.asyncio
async def test_rerank_hits_reorders_keeps_recall_score_and_fails_open():
    hits = _hits()
    ai = SimpleNamespace(rerank=AsyncMock(return_value=[RerankScore(1, 0.95), RerankScore(0, 0.2)]))
    ranked = await rerank_hits(ai, ["route"], "坏账", hits)
    assert [h["source_id"] for h in ranked] == ["b", "a", "c"]
    assert (ranked[0]["recall_score"], ranked[0]["rerank_score"], ranked[0]["score"]) == (0.7, 0.95, 0.95)
    assert "rerank_score" not in ranked[2]  # 没拿到分数的保持原样排在后面
    assert ai.rerank.await_args.args[1] == ["固定资产折旧", "坏账准备计提", "货币资金"]

    broken = SimpleNamespace(rerank=AsyncMock(side_effect=RuntimeError("down")))
    assert await rerank_hits(broken, ["route"], "坏账", hits) is hits
    idle = SimpleNamespace(rerank=AsyncMock())
    assert await rerank_hits(idle, [], "坏账", hits) is hits
    assert await rerank_hits(idle, ["route"], "  ", hits) is hits
    assert await rerank_hits(idle, ["route"], "坏账", hits[:1]) == hits[:1]
    idle.rerank.assert_not_awaited()


def _search_service():
    from app.services.knowledge_index_service import KnowledgeIndexService

    service = KnowledgeIndexService(make_retrieval_session())
    service._resolve_subject = AsyncMock(return_value=None)  # type: ignore[method-assign]
    service._filter_by_permission = AsyncMock(side_effect=lambda hits, *a, **k: hits)  # type: ignore[method-assign]
    service._enrich_results = AsyncMock(side_effect=lambda hits: hits)  # type: ignore[method-assign]
    service._doc_search.search = AsyncMock(return_value=[])  # type: ignore[method-assign]
    return service


@pytest.mark.asyncio
async def test_semantic_search_widens_recall_and_orders_by_rerank():
    service = _search_service()
    service._vector_search = AsyncMock(return_value=_hits()[:2])  # type: ignore[method-assign]
    service._ai_svc.rerank = AsyncMock(return_value=[RerankScore(1, 0.9), RerankScore(0, 0.1)])  # type: ignore[method-assign]
    with patch("app.services.knowledge_index_service.resolve_rerank_route", AsyncMock(return_value=["route"])):
        results = await service.semantic_search(uuid4(), "坏账准备", top_k=1, scope="knowledge_doc")
    assert service._vector_search.await_args.args[2] == 3  # top_k × 3
    assert [r["source_id"] for r in results] == ["b"] and results[0]["rerank_score"] == 0.9

    service._ai_svc.rerank = AsyncMock(side_effect=RuntimeError("gateway down"))  # type: ignore[method-assign]
    with patch("app.services.knowledge_index_service.resolve_rerank_route", AsyncMock(return_value=["route"])):
        results = await service.semantic_search(uuid4(), "坏账准备", top_k=1, scope="knowledge_doc")
    assert [r["source_id"] for r in results] == ["a"]  # 重排失败：保持召回顺序

    with patch("app.services.knowledge_index_service.resolve_rerank_route", AsyncMock(return_value=[])):
        await service.semantic_search(uuid4(), "坏账准备", top_k=4, scope="knowledge_doc")
    assert service._vector_search.await_args.args[2] == 4  # 未启用重排：召回条数不变


@pytest.mark.asyncio
async def test_foreign_vectors_trigger_fallback_and_strict_rebuild_hint():
    from app.services.ai_chat.address_index_source import EmbeddingUnavailableError

    service = _search_service()

    async def only_foreign(*args, **kwargs):
        service._foreign_vectors = True
        return []

    service._vector_search = only_foreign  # type: ignore[method-assign]
    service._index_lexical_fallback = AsyncMock(return_value=[])  # type: ignore[method-assign]
    with patch("app.services.knowledge_index_service.resolve_rerank_route", AsyncMock(return_value=[])):
        await service.semantic_search(uuid4(), "坏账", top_k=5, scope="all")
        service._index_lexical_fallback.assert_awaited_once()  # 旧模型分块仍可经词法兜底召回
        with pytest.raises(EmbeddingUnavailableError, match="重建"):
            await service.semantic_search_strict(uuid4(), "坏账", top_k=5)

    async def nothing(*args, **kwargs):
        service._foreign_vectors = False
        return []

    service._vector_search = nothing  # type: ignore[method-assign]
    with patch("app.services.knowledge_index_service.resolve_rerank_route", AsyncMock(return_value=[])):
        assert await service.semantic_search_strict(uuid4(), "坏账", top_k=5) == []  # 真的没有匹配


@pytest.mark.asyncio
async def test_vector_search_compares_only_same_signature_chunks_on_a_real_session():
    """签名过滤落在 SQL 上（mock 会话不看 WHERE）：SQLite 真 ORM 验证内存计算分支。"""
    from app.models.ai_models import KnowledgeIndex, KnowledgeSourceType
    from app.services.knowledge_index_service import KnowledgeIndexService

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(KnowledgeIndex.__table__.create)
    project = uuid4()
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            for text, model in (("同模型分块", "m@2"), ("旧模型分块", "old@2"), ("无签名分块", None)):
                db.add(KnowledgeIndex(
                    id=uuid4(), project_id=project, source_type=KnowledgeSourceType.knowledge_doc,
                    source_id=uuid4(), content_text=text, embedding_vector="1,0", embedding_model=model,
                    chunk_index=0, is_deleted=False,
                ))
            await db.commit()
            service = KnowledgeIndexService(db)

            async def fake_embedding(text: str, model: str | None = None) -> list[float]:
                service._ai_svc.last_embedding_signature = "m@2"
                return [1.0, 0.0]

            service._ai_svc.embedding = fake_embedding  # type: ignore[method-assign]
            hits = await service._vector_search(project, "坏账", 5, "knowledge_doc")
    finally:
        await engine.dispose()
    assert [hit["content"] for hit in hits] == ["同模型分块"]
    assert service._foreign_vectors is True


# ── R2 调用路由面板 ────────────────────────────────────────────────────────────


def test_orm_route_indexes_include_the_rerank_slot():
    from app.models.ai_model_options import active_route_indexes

    assert {index.name for index in active_route_indexes()} == {
        "uq_ai_model_config_active_chat_route",
        "uq_ai_model_config_active_embedding",
        "uq_ai_model_config_active_ocr_route",
        "uq_ai_model_config_active_rerank_route",
    }


@pytest.mark.asyncio
async def test_route_status_lists_the_rerank_route_and_probes_it(session_factory, monkeypatch):
    from app.services import model_route_status as status

    probe = AsyncMock(return_value=(True, "可用"))
    monkeypatch.setattr(status, "_probe_rerank", probe)
    async with session_factory() as db:
        values = {**GT_QWEN3_RERANKER_4B.orm_values(), "is_active": True}
        db.add(AIModelConfig(**values, deployment="server", is_deleted=False,
                             trust_zone="firm_private", client_data_allowed=True, mask_policy="strict"))
        await db.commit()
        result = await status.collect_route_status(db, probe_kinds=("rerank",))
    route = next(item for item in result["routes"] if item["kind"] == "rerank")
    assert (route["label"], route["policy"], route["has_server"]) == ("重排模型", "local_first", True)
    assert route["effective"]["model_name"] == "qwen3-reranker-4b"
    probe.assert_awaited_once()
    assert [item["kind"] for item in result["routes"]] == ["chat", "embedding", "rerank", "ocr", "layout_parsing"]


# ── R5 补口：pgvector 可用但历史同签名分块的 embedding_vec 为空 ───────────────────


def test_text_only_same_signature_vectors_are_scored_and_bad_values_are_skipped():
    """纯 helper：不让单条历史坏值阻断同批文本向量评分。"""
    import numpy as np

    chunks = [
        SimpleNamespace(embedding_vector="1,0"),
        SimpleNamespace(embedding_vector="bad"),
        SimpleNamespace(embedding_vector="1,0,0"),
        SimpleNamespace(embedding_vector=None),
    ]
    values = score_text_vector_chunks(
        chunks, np.array([1.0, 0.0]),
        parse_vector=lambda raw: np.array([float(v) for v in raw.split(",")]),
        cosine_similarity=lambda _q, v: float(v[0]),
    )
    assert len(values) == 1 and values[0][1] is chunks[0]


@pytest.mark.asyncio
async def test_pgvector_path_also_scores_same_signature_text_only_rows(monkeypatch):
    """ANN 查询只看 embedding_vec；V263 加列前写入的同签名文本向量仍须参加排序，不能静默消失。"""
    from app.models.ai_models import KnowledgeSourceType
    from app.services.knowledge_index_service import KnowledgeIndexService

    class _Result:
        def __init__(self, *, rows=None, scalar_rows=None):
            self._rows = rows or []
            self._scalar_rows = scalar_rows or []

        def all(self):
            return self._rows

        def scalars(self):
            return SimpleNamespace(all=lambda: self._scalar_rows)

    query_values = [1.0] + [0.0] * 1023
    pg_row = SimpleNamespace(
        source_type=KnowledgeSourceType.knowledge_doc, source_id=uuid4(), content_text="ANN 分块",
        chunk_index=0, doc_version=None, is_stale=False, embedding_vector=",".join("0" for _ in query_values),
    )
    text_row = SimpleNamespace(
        source_type=KnowledgeSourceType.knowledge_doc, source_id=uuid4(), content_text="历史文本向量分块",
        chunk_index=0, doc_version=None, is_stale=False, embedding_vector=",".join(str(v) for v in query_values),
    )
    db = make_retrieval_session()
    db.execute = AsyncMock(side_effect=[_Result(rows=[(pg_row, 0.5)]), _Result(scalar_rows=[text_row])])
    service = KnowledgeIndexService(db)

    async def fake_embedding(_query: str, model: str | None = None) -> list[float]:
        service._ai_svc.last_embedding_signature = "wemm-embedding-4b@1024"
        return query_values

    service._ai_svc.embedding = fake_embedding  # type: ignore[method-assign]
    service._pgvector_column_available = AsyncMock(return_value=True)  # type: ignore[method-assign]
    monkeypatch.setattr("app.services.knowledge_index_service.has_foreign_signature", AsyncMock(return_value=False))
    hits = await service._vector_search(uuid4(), "坏账", 2, "knowledge_doc")
    assert [h["content"] for h in hits] == ["历史文本向量分块", "ANN 分块"]
    assert db.execute.await_count == 2, "ANN 查询后还要取 embedding_vec 为空的同签名分块"
