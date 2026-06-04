# Design: 端点自动巡检 + 全链路追踪 + 检索降级增强

## Overview

三个"可观测性 + 质量自动化"基础设施合一个 spec（彼此独立，可分组实施）：
1. **Schemathesis**：从 FastAPI 自动生成的 OpenAPI 直接做 property-based fuzz，自动巡检所有端点，替代手工 429 端点逐个写契约测试。
2. **OpenTelemetry**：自动 instrument FastAPI/asyncpg/redis/httpx，前端→后端→PG/Redis/vLLM 全链路 trace，定位"哪个端点慢、慢在哪一跳"。
3. **bm25s**：把 RAG 向量召回失败时的 `ilike` 降级，升级为 BM25 词法检索（embed 不可用期间显著优于 ilike），embed 恢复后保留作 hybrid。

均本地、可独立开关、不改业务语义。

## 现状勘察

### Schemathesis 替代对象
- memory.md："14 个 GET 500 全清零（429 端点巡检）"——当前手工巡检
- FastAPI 自带 `/openapi.json`，Schemathesis 可直接消费
- 已有 `test_raw_sql_schema_contract.py` / `test_raw_sql_column_contract.py` 做静态契约——Schemathesis 补运行时 fuzz

### OpenTelemetry 接入点
- 后端 FastAPI（uvicorn 9980）+ asyncpg + redis + httpx（含 vLLM 调用）
- 无现成 trace，性能问题靠手工 grep 日志（memory.md 多处"in-process ASGI 实测"佐证缺乏链路视图）

### bm25s 增强对象
- `knowledge_index_service.semantic_search`：向量召回失败 → `_ilike_fallback`（朴素 LIKE）
- memory.md："embedding 404 → RAG 向量召回降级 ilike"——embed 实例未起，当前长期跑在 ilike 降级上
- bm25s 是纯 Python BM25（无需 GPU/外部服务），是 ilike 与向量之间的中间档

## Architecture

### 模块 A：Schemathesis 端点 fuzz

> 🔴 **关键约束 1（信封）**：`ResponseWrapperMiddleware` 把所有 2xx JSON 包成 `{code, message, data}`，但 `openapi.json` 声明的是各端点**原始 payload schema（未包装）**。`_SKIP_PATHS` 只豁免 `/openapi.json`、`/docs` 等，**不豁免业务端点**。因此 Schemathesis 默认的 `case.validate_response()` 会拿"已包装的实际响应"比对"未包装的声明 schema"→ 全端点 schema 不匹配误报。**不能用默认 validate_response。**

> 🔴 **关键约束 2（认证，勘察发现）**：全仓测试**统一用 `dependency_overrides[get_current_user]` 注入认证，没有真实 Bearer token 体系**（`_test_auth_helper.override_auth` 注入 get_db/get_redis/get_current_user override + ASGITransport）。**Schemathesis 必须复用同一个被 override 的 app 实例**——在 `dependency_overrides` 注入 fake user 后再 `from_asgi(app)`，否则所有端点 401。不能写"注入 token header"（无 token 体系）。

```python
# backend/tests/test_api_schemathesis.py
import schemathesis
from app.main import app
from app.deps import get_current_user, get_db
# fixture：注入 dependency_overrides（仿 override_auth，但作用于模块级 app）
# app.dependency_overrides[get_current_user] = lambda: fake_admin_user
# app.dependency_overrides[get_db] = lambda: test_db_session
schema = schemathesis.from_asgi("/openapi.json", app)

@schema.parametrize()
@settings(max_examples=5, deadline=None)   # 遵守 memory 铁律 max_examples=5
def test_api(case):
    response = case.call_asgi()             # 经过 override 后的 app（已认证）
    # 主断言：无 5xx（核心价值——抓服务端崩溃）
    assert response.status_code < 500, f"{case.method} {case.path} → {response.status_code}"
    # 软校验：解信封后对 data 校验（best-effort，非主断言）
    body = response.json()
    payload = body["data"] if isinstance(body, dict) and {"code","message","data"} <= set(body) else body
```

- **认证方案**：在 fixture 中对 `app.dependency_overrides` 注入 fake admin user + test db（仿 `override_auth` 但作用于 `app.main.app` 模块级实例），用完 `clear()`；`from_asgi` 必须用这个被 override 的同一 app 实例
- **DB 选择**：用真实 PG 或 SQLite test db（注意只读 fuzz 不写真实数据；写端点已排除）；若用 PG dependency_overrides[get_db] 指测试会话
- **核心断言 = 无 5xx**（替代手工 429 端点巡检的真实价值：自动抓崩溃端点）；schema 一致性因信封问题降级为软校验/增量目标
- 范围控制：先覆盖 GET 只读端点（`schema.include(method="GET")`），写端点排除避免污染 DB
- 已知豁免：把已知问题端点登记 allowlist（仿 `_KNOWN_PHANTOM_DEBT` 模式），增量收敛
- **铁律呼应**：这正是 memory.md "原生 fetch 调后端必手动解 `{code,message,data}` 信封" 的服务端测试镜像
- **铁律呼应**：这正是 memory.md "原生 fetch 调后端必手动解 `{code,message,data}` 信封" 的服务端测试镜像——测试侧也必须解信封

### 模块 B：OpenTelemetry 全链路 trace

```python
# backend/app/core/tracing.py
def setup_tracing(app):
    if not settings.OTEL_ENABLED:
        return
    FastAPIInstrumentor.instrument_app(app)
    AsyncPGInstrumentor().instrument()
    RedisInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()   # 覆盖 vLLM 调用
    # OTLP exporter → 本地 jaeger/tempo（dev）；console exporter（无 collector 时）
```

- main.py lifespan/启动调 `setup_tracing(app)`，`OTEL_ENABLED=False` 时零开销 no-op
- exporter 可配：OTLP（指本地 jaeger 容器）/ console（无 collector 时降级打印）
- span 自动覆盖：HTTP 请求 → DB 查询 → Redis → httpx(vLLM)，无需手工埋点
- docker-compose 可选加 `jaeger` service（all-in-one，仅 dev profile）
- 注意：httpx 全仓 `trust_env=False`——instrument 不破坏该约束（OTel 用 header 注入不走 env proxy）

### 模块 C：bm25s 检索降级增强

```python
# knowledge_index_service.py — 降级链升级
# 现状：向量失败 → _ilike_fallback
# 新：向量失败 → _bm25_fallback（bm25s）→ _ilike_fallback（bm25 也不可用时）

async def _bm25_fallback(self, project_id, query, top_k, scope):
    """BM25 词法检索（bm25s，纯 Python）。
    对 scope 下 KnowledgeIndex.content_text 建 BM25 索引（带 TTL 缓存或按需构建）
    中文分词：复用现有分词（pypinyin/jieba 视现状）或 bm25s 自带 tokenizer
    """
```

- bm25s 索引构建：对候选文档集（按 scope/project 过滤）的 content_text 建索引
- 中文分词：勘察现有是否有 jieba；无则用简单 bigram 或 bm25s tokenizer（中文检索可接受）
- 缓存：BM25 索引按 (project_id, scope) 缓存，文档变更时失效（复用 incremental_update 钩子时机）
- embed 恢复后：作为 **hybrid retrieval** 的词法分支（向量 + BM25 加权融合），design 预留接口但 hybrid 融合作为可选增强

## 配置

```python
OTEL_ENABLED: bool = False              # 全链路追踪总开关（dev 调性能时开）
OTEL_EXPORTER: str = "console"          # console | otlp
OTEL_OTLP_ENDPOINT: str = "http://localhost:4317"
RETRIEVAL_BM25_FALLBACK_ENABLED: bool = True   # 向量失败时用 BM25 而非直接 ilike
SCHEMATHESIS_MAX_EXAMPLES: int = 5      # 遵守铁律
```

## Error Handling

| 场景 | 处理 |
|------|------|
| Schemathesis 发现 5xx | 测试红，登记 allowlist 或修复（增量收敛，不一次性卡死 CI） |
| OTel collector 不可达 | exporter 降级 console，不阻断请求 |
| OTEL_ENABLED=False | setup_tracing no-op，零运行时开销 |
| bm25s 未安装 | _bm25_fallback 捕获 ImportError → 降级 _ilike_fallback |
| BM25 索引构建失败/空文档集 | 降级 ilike |
| 写端点被 Schemathesis 误触发 | hooks 限制只 fuzz GET / 隔离测试 DB |

## 测试策略

- 模块 A：Schemathesis 本身就是测试（在线 fuzz，标核心 GET 端点必过 + allowlist 收敛）
- 模块 B：`setup_tracing` 单测（OTEL_ENABLED 开关 no-op 验证 + instrument 不抛错）；trace 实际产出标 `[ ]*`（需 jaeger）
- 模块 C：`_bm25_fallback` 单测（BM25 召回非空且相关性优于 ilike）+ 降级链 PBT（向量失败→bm25→ilike 三级）

## 与现有能力的关系

| 能力 | 复用 | 新增 |
|------|------|------|
| 端点测试 | `_test_auth_helper` token + in-process ASGI | Schemathesis 自动 fuzz |
| 静态契约 | raw_sql contract 测试 | 运行时 fuzz 补充 |
| 检索降级 | `semantic_search` + `_ilike_fallback` | `_bm25_fallback` 中间档 |
| httpx 约束 | trust_env=False | OTel 不破坏 |
| allowlist 模式 | `_KNOWN_PHANTOM_DEBT` | Schemathesis 已知问题豁免 |
