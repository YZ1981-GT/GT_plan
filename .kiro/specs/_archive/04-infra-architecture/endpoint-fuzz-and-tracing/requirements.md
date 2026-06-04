# Requirements: 端点自动巡检 + 全链路追踪 + 检索降级增强

## Introduction

三个可观测性/质量自动化基础设施合并交付（彼此独立、可分组实施、各自可开关）：
- **Schemathesis**：从 FastAPI OpenAPI 自动 property-based fuzz 所有端点，替代手工逐个写端点契约测试（memory.md 的"429 端点巡检"曾手工做）。
- **OpenTelemetry**：自动 instrument FastAPI/asyncpg/redis/httpx，提供前端→后端→PG/Redis/vLLM 全链路 trace，定位性能瓶颈。
- **bm25s**：把 RAG 向量召回失败时的 ilike 朴素降级升级为 BM25 词法检索（embed 长期不可用期间显著优于 ilike），并为 embed 恢复后的 hybrid 检索预留接口。

均本地、零业务语义改动。

## Glossary

- **Schemathesis**: 基于 OpenAPI schema 的 property-based API 测试工具，自动生成请求并校验响应
- **from_asgi**: Schemathesis in-process 模式，直接对 ASGI app fuzz，无需起 server
- **OpenTelemetry (OTel)**: 可观测性框架，自动 instrument 框架/驱动产生 trace span
- **span / trace**: 一次调用的耗时记录 / 一个请求贯穿多组件的 span 链
- **OTLP exporter**: OTel 标准导出协议，指向 collector（如 jaeger/tempo）
- **bm25s**: 纯 Python BM25 词法检索库，无需 GPU/外部服务
- **降级链**: 向量召回失败 → BM25 → ilike 三级
- **hybrid retrieval**: 向量召回 + BM25 词法加权融合（embed 恢复后的增强）
- **allowlist**: 已知问题端点豁免清单，仿 `_KNOWN_PHANTOM_DEBT` 增量收敛

## Requirements

### Requirement 1: Schemathesis 端点自动 fuzz

**User Story:** As a 后端开发者, I want 从 OpenAPI 自动 fuzz 所有端点, so that 不必为每个端点手写契约测试，且新增端点自动纳入巡检。

#### Acceptance Criteria
1. THE 系统 SHALL 提供 `backend/tests/test_api_schemathesis.py`，用 `from_asgi(app)` in-process fuzz。
2. THE fuzz SHALL 通过 `app.dependency_overrides` 注入 fake user + test db（复用 `_test_auth_helper.override_auth` 的 dependency_overrides 模式，作用于 `from_asgi` 所用的同一 app 实例）——全仓无 Bearer token 体系，不可用 token header。
3. THE 主断言 SHALL 为响应无 5xx（抓服务端崩溃）。因 `ResponseWrapperMiddleware` 把响应包成 `{code,message,data}` 而 openapi.json 声明未包装 schema，THE schema 一致性校验 SHALL 在解信封（取 `data`）后进行且作为软校验/增量收敛目标，不得用默认 `validate_response` 直接比对（会全端点误报）。
4. THE fuzz SHALL 用 `SCHEMATHESIS_MAX_EXAMPLES`（默认 5，遵守 memory 铁律）。
5. THE 系统 SHALL 默认覆盖 GET 只读端点；写端点 SHALL 通过 hooks 限制或隔离，避免污染测试 DB。
6. THE 系统 SHALL 提供 allowlist 机制登记已知问题端点，增量收敛而非一次性卡死。

### Requirement 2: OpenTelemetry 全链路追踪

**User Story:** As a 性能工程师, I want 自动 trace 请求贯穿后端/PG/Redis/vLLM, so that 我能定位某端点慢在哪一跳，无需手工 grep 日志。

#### Acceptance Criteria
1. THE 系统 SHALL 提供 `backend/app/core/tracing.py` 的 `setup_tracing(app)`，instrument FastAPI/asyncpg/redis/httpx。
2. WHEN `OTEL_ENABLED` 为假, THE `setup_tracing` SHALL no-op（零运行时开销）。
3. THE exporter SHALL 可配 `console`（无 collector 降级打印）或 `otlp`（指 collector）。
4. THE httpx instrument SHALL NOT 破坏全仓 `trust_env=False` 约束。
5. THE docker-compose SHALL 可选提供 jaeger service（dev profile）。

### Requirement 3: bm25s 检索降级增强

**User Story:** As an 审计助理, I want 向量检索不可用时仍有较好的检索质量, so that embed 实例未起期间知识库搜索不退化到朴素 LIKE。

#### Acceptance Criteria
1. THE `knowledge_index_service` 降级链 SHALL 升级为：向量失败 → `_bm25_fallback`（bm25s）→ `_ilike_fallback`。
2. THE `_bm25_fallback` SHALL 对 scope/project 过滤后的 `content_text` 建 BM25 索引并召回 top_k。
3. WHEN bm25s 未安装或索引构建失败, THE 系统 SHALL 降级 `_ilike_fallback`（不崩）。
4. THE BM25 索引 SHALL 按 (project_id, scope) 缓存，文档变更时失效。
5. THE 设计 SHALL 为 embed 恢复后的 hybrid retrieval（向量+BM25 加权）预留接口（融合本体可选）。
6. WHERE `RETRIEVAL_BM25_FALLBACK_ENABLED` 为假, THE 降级 SHALL 保持原 ilike 直降级。

### Requirement 4: 配置开关

#### Acceptance Criteria
1. THE 系统 SHALL 提供 `OTEL_ENABLED`(默认 False) / `OTEL_EXPORTER`(默认 console) / `OTEL_OTLP_ENDPOINT` / `RETRIEVAL_BM25_FALLBACK_ENABLED`(默认 True) / `SCHEMATHESIS_MAX_EXAMPLES`(默认 5)。
2. 三模块开关 SHALL 互相独立，单独开关不影响其他。

### Requirement 5: 验证

#### Acceptance Criteria
1. THE Schemathesis SHALL 对核心 GET 端点全过（已知问题入 allowlist）。
2. THE `setup_tracing` SHALL 有单测验证 OTEL_ENABLED 开关 no-op + instrument 不抛错；真实 trace 产出标 `[ ]*`（需 jaeger）。
3. THE `_bm25_fallback` SHALL 有单测验证召回非空且相关性优于 ilike；降级链 SHALL 有 PBT（max_examples=5）覆盖三级降级。
