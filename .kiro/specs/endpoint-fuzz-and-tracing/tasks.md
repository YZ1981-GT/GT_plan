# Tasks: 端点自动巡检 + 全链路追踪 + 检索降级增强

## Overview

三模块独立分组，可单独实施：组① Schemathesis / 组② OpenTelemetry / 组③ bm25s。各组互不依赖。组④收尾。

**勘察结论（实施前必读）**：
- `main.py`：`app = FastAPI(lifespan=lifespan)`（line ~276）后跟一串 `add_middleware`（AuditLog/LLMRateLimit/RequestID/ResponseWrapper/Observability/GZip/RequestBodyLimit/CORS）。`setup_tracing(app)` 应在 `app = FastAPI()` 之后、`add_middleware` 之前调用（FastAPIInstrumentor 需在 app 创建后 instrument）。已有 `ObservabilityMiddleware`（请求指标）——OTel 是其补充（trace 链路非聚合指标），不冲突。
- `knowledge_index_service.semantic_search`（line 230）：`try: _vector_search except: _ilike_fallback`。`_vector_search`(line ~274) 抛异常 → 现降级 `_ilike_fallback`(line ~326)。**两者返回完全相同 dict 结构**：`{source_type, source_id, content, score, chunk_index}`。bm25 fallback 必须返回同结构。`_ilike_fallback` 的 score=0.0。
- 中文分词：仓库**有 pypinyin（无 jieba）**。bm25s 中文分词用 bm25s 内置 tokenizer 或简单 bigram（2-gram 切分），不引 jieba。
- `_test_auth_helper.py` + `override_auth` 已存在（pytest 用）；Schemathesis 注入 token 复用之。
- 已有契约测试 `test_raw_sql_schema_contract.py` 的 `_KNOWN_PHANTOM_DEBT` allowlist 模式可参照。
- `KnowledgeIndex` model：`project_id`/`source_type`(enum KnowledgeSourceType)/`source_id`/`content_text`/`chunk_index`/`is_deleted`/`embedding_vector`。

## Tasks

### 组 ① Schemathesis 端点 fuzz

- [x] 1. 依赖 + 配置
  - `backend/requirements.txt` 加 `schemathesis`（pin，如 `schemathesis>=3.36,<4`）
  - `backend/app/core/config.py` 加 `SCHEMATHESIS_MAX_EXAMPLES: int = 5`
  - _Requirements: 1.4_

- [x] 2. `backend/tests/test_api_schemathesis.py`
  - **认证（关键）**：fixture 对 `app.dependency_overrides` 注入 fake admin user（`get_current_user`）+ test db（`get_db`），仿 `_test_auth_helper.override_auth` 但作用于 `app.main.app` 模块级实例；用完 `clear()`。**全仓无 Bearer token 体系，不可写 token header**
  - **DB 选择（关键，勘察）**：conftest 默认 SQLite，但大量业务端点（TB/序时账等）用 PG 专属裸 SQL，SQLite 下会报 500 → **污染"无 5xx"主断言**（误判端点 bug，实为 SQLite 不兼容）。两个处理选项，二选一写明：
    - **选项 A（推荐）**：本测试标 `@pytest.mark.pg_only` + 注入真 PG 测试会话，只在 PG 环境跑（CI 配 PG service）；非 PG 自动 skip
    - **选项 B**：SQLite 跑但把"PG 专属 SQL 端点"全列入 allowlist（量大、维护差，不推荐）
  - `schema = schemathesis.from_asgi("/openapi.json", app)`（必须用上面被 override 的同一 app 实例）
  - `@schema.parametrize()` + `@settings(max_examples=SCHEMATHESIS_MAX_EXAMPLES, deadline=None)`
  - **主断言 = `assert response.status_code < 500`**（核心价值：抓崩溃端点）
  - **不用默认 `case.validate_response`**（ResponseWrapperMiddleware 信封 vs openapi 未包装 schema 会全端点误报）；schema 校验改为：解信封取 `body["data"]`（若 `{code,message,data}` 结构）再做软校验，作增量收敛目标
  - 用 `schema.include(method="GET")` 限制只 fuzz GET（写端点排除，避免污染 DB）
  - _Requirements: 1.1, 1.2, 1.3, 1.5_

- [x] 3. allowlist 机制
  - `_SCHEMATHESIS_ALLOWLIST: set[str]`（端点 path 集合，仿 `_KNOWN_PHANTOM_DEBT`）
  - fuzz 内对 allowlist 端点 `pytest.skip` 或软断言（仅警告不红）
  - 注释：增量收敛——修一个从 allowlist 移除一个
  - _Requirements: 1.6_

- [x] 4. 检查点 — `python -m pytest backend/tests/test_api_schemathesis.py -v` 对核心 GET 端点跑通（5xx 的端点入 allowlist 或当场修复）
  - _Requirements: 5.1_

### 组 ② OpenTelemetry 全链路追踪

- [x] 5. 依赖 + 配置
  - `backend/requirements.txt` 加：`opentelemetry-sdk` / `opentelemetry-api` / `opentelemetry-instrumentation-fastapi` / `-asyncpg` / `-redis` / `-httpx` / `opentelemetry-exporter-otlp`（pin 版本）
  - `backend/app/core/config.py` 加 `OTEL_ENABLED: bool = False` / `OTEL_EXPORTER: str = "console"` / `OTEL_OTLP_ENDPOINT: str = "http://localhost:4317"`
  - `.env.example` 同步
  - _Requirements: 4.1_

- [x] 6. `backend/app/core/tracing.py`
  - `def setup_tracing(app) -> None`：`if not settings.OTEL_ENABLED: return`（no-op 零开销）
  - 真：TracerProvider + exporter（OTEL_EXPORTER=console→ConsoleSpanExporter / otlp→OTLPSpanExporter(endpoint)）
  - `FastAPIInstrumentor.instrument_app(app)` + `AsyncPGInstrumentor().instrument()` + `RedisInstrumentor().instrument()` + `HTTPXClientInstrumentor().instrument()`
  - httpx instrument 用 header 注入 trace context，**不走 env proxy，不破坏 trust_env=False**（注释说明 + 验证）
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 7. main.py 启动接入
  - `app = FastAPI(...)` 之后、首个 `add_middleware` 之前调 `from app.core.tracing import setup_tracing; setup_tracing(app)`
  - _Requirements: 2.1_

- [x] 8. `setup_tracing` 单测 `backend/tests/test_tracing.py`
  - `OTEL_ENABLED=False` → setup_tracing 不 instrument（mock Instrumentor 断言未调用）
  - `OTEL_ENABLED=True` + console exporter → instrument 链路不抛错（mock 各 Instrumentor）
  - _Requirements: 5.2_

- [ ]* 9. docker-compose jaeger service（dev profile）+ 真实 trace 验证（外部依赖）
  - `docker-compose.yml` 加 `jaeger`（jaegertracing/all-in-one，dev profile，暴露 16686 UI + 4317 OTLP）
  - `OTEL_ENABLED=True` + `OTEL_EXPORTER=otlp`；跑请求在 jaeger UI 看 trace 链 FastAPI→asyncpg→httpx(vLLM)
  - _Requirements: 2.5, 5.2_

- [x] 10. 检查点 — `test_tracing.py` 全绿 + `OTEL_ENABLED=False`（默认）时启动零开销（no instrument）

### 组 ③ bm25s 检索降级增强

- [x] 11. 依赖 + 配置 + 分词决策
  - `backend/requirements.txt` 加 `bm25s`
  - `backend/app/core/config.py` 加 `RETRIEVAL_BM25_FALLBACK_ENABLED: bool = True`
  - 分词决策：用 bm25s 内置 tokenizer 或自写 `_zh_tokenize`（中文 2-gram bigram + 英文 split）——**不引 jieba**（仓库无）；写入实现注释
  - _Requirements: 4.1_

- [x] 12. `knowledge_index_service._bm25_fallback`
  - 签名同 `_ilike_fallback(project_id, query, top_k, scope)`，**返回相同 dict 结构** `{source_type, source_id, content, score, chunk_index}`（score 用 BM25 归一化分数，非 0.0）
  - 取候选：按 scope/project 过滤 `KnowledgeIndex.content_text`（同 _ilike_fallback 的 conditions，去掉 ilike 条件取全集）
  - bm25s 建索引（`bm25s.BM25()` + tokenize content_text + tokenize query）召回 top_k
  - 中文分词用 task 11 决策的 `_zh_tokenize`
  - `try import bm25s except ImportError` / 索引构建异常 → `return await self._ilike_fallback(...)`
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 13. BM25 索引缓存
  - 模块级或实例级缓存：key=`(project_id, scope)`，value=(bm25 index, doc 列表, 构建时间)
  - 失效：复用 `incremental_update` 调用时机标记 dirty（或简单 TTL 60s）
  - 避免每次查询重建（content_text 集大时重建慢）
  - _Requirements: 3.4_

- [x] 14. 降级链接入 `semantic_search`
  - 改 `except` 分支：`if settings.RETRIEVAL_BM25_FALLBACK_ENABLED: results = await self._bm25_fallback(...) ` （其内部失败再降 ilike）`else: results = await self._ilike_fallback(...)`
  - hybrid retrieval 接口预留：`_vector_search` 成功时可选融合 bm25 分数（注释 TODO，本体标 `[ ]*`）
  - _Requirements: 3.1, 3.5, 3.6_

- [x] 15. bm25s 单测 + 降级链 PBT `backend/tests/test_bm25_fallback.py`
  - **测试环境（勘察确认）**：`KnowledgeIndex.content_text` 是 `Text`、`embedding_vector` 是 `String(5000)`（非 pgvector 原生类型）——**全 SQLite 兼容**，bm25s 是纯 Python 库不依赖 PG，故本测试**可在默认 SQLite 环境跑，无需 pg_only**
  - 构造 KnowledgeIndex 测试数据（含中文 content_text）→ `_bm25_fallback` 召回非空 + 相关 doc 排前（构造一个 ilike 漏召但 bm25 能召的 query 做精确对比）
  - PBT（hypothesis max_examples=5）：mock `_vector_search` 抛异常 → 验证三级降级 向量失败→bm25→（bm25 import 失败）→ilike 路径均返回合法结构（同 dict 字段）
  - _Requirements: 5.3_

- [x] 16. 检查点 — `test_bm25_fallback.py` 全绿（含降级 PBT）

### 组 ④ 收尾

- [x] 17. 最终检查点
  - 三模块单测全绿：`python -m pytest backend/tests/test_api_schemathesis.py backend/tests/test_tracing.py backend/tests/test_bm25_fallback.py -v`
  - 三开关默认值正确（OTEL_ENABLED=False / RETRIEVAL_BM25_FALLBACK_ENABLED=True / SCHEMATHESIS_MAX_EXAMPLES=5）+ 验证单独开关一个模块不影响其他两个（互相独立）
  - 外部依赖项（jaeger trace / hybrid 融合）如实标 `[ ]*`
  - _Requirements: 4.2_
