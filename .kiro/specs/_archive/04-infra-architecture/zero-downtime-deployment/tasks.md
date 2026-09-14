# 实施计划：服务器零停机滚动更新与无感版本迭代（zero-downtime-deployment）

## 概述

本计划将 design.md 拆解为可由编码代理增量执行的任务序列。任务按 **P0 → P1 → P2** 三阶段编排，逐一对齐 design 的 9 个组件，每个任务都建立在前序任务之上，最终接线成完整的硬零停机能力——不留孤立未接线代码。

核心定位是「**扩展接入已有体系，而非重建**」：凡 design「现状实证」标注为已有的组件（`/api/health`、`MigrationRunner` 的 `pg_advisory_lock`、`lifespan` 后台 worker graceful F44、`ImportProgress.vue` 重连、`sqlglot` pg 解析、`ResponseWrapperMiddleware`）一律复用/扩展，新增代码仅补齐 design「缺失能力清单」的 7 项。

实施语言：后端 **Python 3.12**（仓库根 `.venv`）；前端 **Vue3 + TypeScript**（`audit-platform/frontend/`）；数据层 **PostgreSQL 16** 手写迁移（MigrationRunner，非 alembic）。属性测试：后端 **Hypothesis**、前端 **fast-check**，**`max_examples=5` / `numRuns=5`**（用户铁律，禁默认 100）。每个属性测试以注释标注溯源 `# Feature: zero-downtime-deployment, Property N`。

> **零停机不变量（需求 11 / Property 20）是所有任务的验收基线**：任何环节不得引入「向客户端返回 5xx 或中断 in-flight 请求」的操作。

---

## 三层一致铁律（贯穿所有涉及 DB 的任务）

凡新增/变更数据库结构，必须三层同步，缺一即伪绿：

1. **DB 迁移**：本 spec 仅 feature flag 落库，用 **V068**（当前最高 V066，`deliverable-lineage` 占用 V067）。`V068__feature_flags.sql`（`CREATE TABLE IF NOT EXISTS` 幂等）+ 配对 `R068__rollback.sql`（DROP TABLE）。手写 DDL 必须**显式写 `created_at`/`updated_at`**（TimestampMixin 列不会自动进 DDL，漏写即 schema drift critical）。
2. **ORM**：`FeatureFlag(Base, TimestampMixin)` 加入 `audit_platform_models.py`，`Mapped[]` 列与 DDL 逐列对齐。
3. **Service**：`FeatureFlagService` 消费该模型。
4. **契约测试**：裸 SQL 引用经 `test_raw_sql_schema_contract.py` / `test_raw_sql_column_contract.py` 守护，新增表/列纳入校验。

## router 注册铁律

凡新建 router（探针 `/livez` `/readyz`、`feature-flags`）必在 `backend/app/router_registry/{group}.py` 注册，否则前端 404；FastAPI 不热加载 router（改后重启）。`/livez`、`/readyz` 还须加入 `ResponseWrapperMiddleware._SKIP_PATHS`（探针消费方 nginx/K8s 需原始 JSON + 裸状态码，不能被包成 `{code,message,data}`）。

---

## 验收里程碑

| 里程碑 | 完成判据 | 覆盖任务 |
|--------|----------|----------|
| **M0 P0 软无感基础** | 版本端点返真实 build version + X-App-Version 头 + 前端非阻断提示；`/livez` `/readyz` 注册并入 _SKIP_PATHS；SIGTERM drain 扩展 lifespan；Breaking_DDL CI 双档卡点（默认 warning）。P0 检查点全测试绿 | Phase 1（任务 1-6） |
| **M1 P1 硬零停机滚动** | compose 去 container_name + 多副本 + stop_grace_period 40s + healthcheck 改 readyz；nginx 反代 + 滚动脚本；SSE 服务端优雅关 + 前端 useSSEReconnect 推广；worker 选主去重。P1 检查点全测试绿 | Phase 2（任务 7-12） |
| **M2 P2 灰度与在线 DDL** | V068 feature_flags 三层一致 + 契约测试；FeatureFlagService（DB 权威 + 5s TTL + 稳定哈希灰度）；feature-flags API（admin）+ 前端开关；在线 DDL（CREATE INDEX 非 CONCURRENTLY）检测。P2 检查点全测试绿 | Phase 3（任务 13-15） |
| **M3 集成与收尾** | 零停机不变量集成测试（P20，滚动期持续打流量零 5xx）+ drain 集成 + 版本协商端到端 + 部署手册 + 生产启动命令文档；21 条属性测试全绿（max_examples=5）；文档/memory 更新 | 收尾（任务 15-18） |

---

## 任务依赖说明

```
Phase 1 (P0)
  ①Build Version ──► ④前端版本协商(读 X-App-Version)
       │
  ②探针(/livez /readyz) ──┐
       │ (readyz 依赖 health 数据源 + migration_state/shutdown_state 单例)
  ③优雅下线(inflight 中间件 + SIGTERM drain) ──┘
  ⑤迁移兼容检测(check_migration_compat + CI) ── 独立
  ⑥ P0 检查点

Phase 2 (P1)  依赖 P0 探针/下线
  ⑦nginx+滚动(compose 改造 + nginx.conf + rolling_update.sh) ── 依赖 ②readyz
  ⑧SSE(sse_registry 服务端优雅关 ── 依赖 ③drain 步骤3；前端 useSSEReconnect 抽自 ImportProgress)
  ⑨worker 去重(_leader_lock 选主)
  ⑩ P1 检查点

Phase 3 (P2)
  ⑪feature flag(V068+R068+ORM+契约 → FeatureFlagService → API → 前端)
  ⑫在线 DDL 检测(并入 ⑤ check_migration_compat 的 LOCK_PATTERNS)
  ⑬ P2 检查点

收尾
  ⑭零停机不变量集成测试(P20，最重要) ── 依赖 ⑦滚动 + ②③探针下线
  ⑮drain 集成 / 版本协商端到端 / 部署手册
  ⑯生产启动命令文档(禁 --reload) + 文档/memory 更新
```

- ②探针的 `readyz` 复用 `/api/health` 内部数据源（不重建健康逻辑），依赖 `migration_state`/`shutdown_state` 进程级单例。
- ③优雅下线的 drain 步骤 3「优雅关 SSE」物理依赖 ⑧的 `sse_registry.close_all()`——⑧服务端部分须在 ③接线点就位（先留空注册表桩，⑧补实现）。
- ⑦nginx 滚动脚本的就绪门控轮询 ②的 `/readyz`。
- ⑭零停机不变量集成测试（P20）是硬零停机核心验收，依赖 ⑦滚动 + ②③探针下线全部就位。

---

## Phase 1（P0）：软无感基础 + 优雅下线（对齐组件 1-5）

- [x] 1. 组件 1 — Build Version 注入 + Version Endpoint 改造 + X-App-Version 中间件（新增 + 扩展，A/B 通用）
  - 实现 build version 单一来源；`/api/version` 返真实版本；每个响应携带版本头；CI 构建期注入
  - _Requirements: 1.1, 1.2, 1.7, 12.3, 12.5_ / _Design: 组件 1_

  - [x] 1.1 实现 build_version 读取模块
    - 新建 `backend/app/core/build_version.py`：`get_build_version()`（`lru_cache`），优先级 环境变量 `BUILD_VERSION_JSON` > `_build_version.json` 文件 > 兜底 `{semantic_version:"dev", git_commit:"unknown", build_time:"unknown"}`；运行时**不执行 git 命令**（生产镜像可能无 .git/git 二进制）
    - 构建版本缺失时返回兜底不抛异常（错误处理表「构建版本缺失」）
    - _Requirements: 1.1, 1.7_ / _Design: 组件 1a + 错误处理_

  - [x] 1.2 改造 /api/version 端点（替换硬编码 1.0.0）
    - 扩展 `backend/app/main.py` 已有硬编码端点 `return {"version":"1.0.0",...}`，改为读 `get_build_version()` 返回 `version`/`git_commit`/`build_time`/`api_prefix`
    - _Requirements: 1.1, 12.3_ / _Design: 组件 1b + API 契约_

  - [x] 1.3 实现 X-App-Version 响应头中间件
    - 新建 `backend/app/middleware/app_version.py`：`AppVersionHeaderMiddleware` 在每个响应（含错误响应）注入 `X-App-Version: {git_commit}`；放在洋葱较外层；在 `main.py` 注册
    - _Requirements: 1.2_ / _Design: 组件 1c_

  - [x]* 1.4 编写 Property 1 属性测试（版本端点三字段）
    - **Property 1：版本端点返回完整构建版本**
    - **Validates: Requirements 1.1, 1.7, 12.3**
    - Hypothesis 随机生成三种版本来源（env/file/兜底），断言 `/api/version` 含 `version`/`git_commit`/`build_time` 且取值与生效来源一致（优先级 env > file > 兜底）；`# Feature: zero-downtime-deployment, Property 1`
    - _Requirements: 1.1, 1.7, 12.3_

  - [x]* 1.5 编写 Property 2 属性测试（每个响应携带版本头）
    - **Property 2：每个响应携带版本头**
    - **Validates: Requirements 1.2**
    - Hypothesis 随机端点 + 成功/错误响应，断言响应携带 `X-App-Version` 且值等于当前实例 `git_commit`；`# Feature: zero-downtime-deployment, Property 2`
    - _Requirements: 1.2_

  - [x] 1.6 CI 构建期版本注入脚本
    - 新建注入脚本（构建前执行）：`git rev-parse --short HEAD` + `date -u +%Y-%m-%dT%H:%M:%SZ` + 语义版本 → 写 `backend/app/_build_version.json`；CI 显式校验文件存在且 `git_commit` 非 `unknown`，缺失则 fail-fast（风险表「构建版本未注入」）
    - _Requirements: 1.7, 12.5_ / _Design: 组件 1a + 风险与缓解_

- [x] 2. 组件 2 — 探针端点 /livez 与 /readyz（新增，A/B 通用）
  - 实现存活/就绪分离探针；readyz 复用 health 数据源；注册到 router_registry + 加入 _SKIP_PATHS
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.8, 6.3, 13.1, 13.4_ / _Design: 组件 2_

  - [x] 2.1 实现进程级运行时状态单例
    - 新建 `migration_state`（`complete: bool`）、`shutdown_state`（`draining: bool`）进程级单例标志（内存，非持久化）；`lifespan` 在 `_run_migrations()` 完成后置 `migration_state.complete = True`
    - _Requirements: 3.2, 3.3_ / _Design: 组件 2 + 数据模型「进程级运行时状态」_

  - [x] 2.2 实现 /livez 与 /readyz 端点
    - 新建 `backend/app/api/probes.py`（无需认证）：`/livez` 只要事件循环能响应即 200，**不查 DB/依赖**；`/readyz` = draining → 503 / health=unhealthy 或迁移未完成 → 503 / 否则 200 且 body `degraded` = (health=degraded)
    - readyz 复用 `get_health_snapshot()`（`/api/health` 内部数据源），不重建健康逻辑；health 获取失败保守视为 unhealthy → 503（不让异常冒泡成 500，错误处理表）
    - **性能**：readyz 先零成本判进程内 draining/migration 标志；health 数据走**短 TTL 缓存（默认 2s，`READYZ_HEALTH_CACHE_TTL`）**，避免 nginx 被动探测+滚动脚本轮询高频跑全量 health（schema drift 查 information_schema）压库
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.8, 6.3, 13.4_ / _Design: 组件 2 + 错误处理_

  - [x] 2.3 注册 probes router 并加入 _SKIP_PATHS
    - 在 `backend/app/router_registry/{group}.py` 注册 probes router；将 `/livez`、`/readyz` 加入 `ResponseWrapperMiddleware._SKIP_PATHS`（探针需原始 JSON + 裸状态码）
    - _Requirements: 3.1, 3.2_ / _Design: 组件 2 + API 契约_

  - [x]* 2.4 编写 Property 10 属性测试（readyz 状态机）
    - **Property 10：readyz 状态机正确反映可接流量**
    - **Validates: Requirements 3.2, 3.3, 3.4, 6.3**
    - Hypothesis 随机 (migration_complete, health, draining) 组合，断言 draining→503 / unhealthy 或迁移未完成→503 / 否则 200 且 `degraded`=(health=degraded)；`# Feature: zero-downtime-deployment, Property 10`
    - _Requirements: 3.2, 3.3, 3.4, 6.3_

  - [x]* 2.5 编写 Property 11 属性测试（livez 恒就绪）
    - **Property 11：livez 在进程存活时恒为就绪**
    - **Validates: Requirements 3.1**
    - Hypothesis 随机依赖可达性，断言 `/livez` 恒 200 且不因 DB/依赖不可达而非 200；`# Feature: zero-downtime-deployment, Property 11`
    - _Requirements: 3.1_

- [x] 3. 组件 3 — GracefulShutdown：HTTP in-flight 计数 + SIGTERM drain（扩展 lifespan，A/B 通用）
  - 扩展现有 lifespan 关闭流程（当前仅后台 worker graceful），加 HTTP 请求级 drain
  - _Requirements: 3.4, 3.5, 3.6, 3.7, 11.2, 13.1_ / _Design: 组件 3_

  - [x] 3.1 实现 in-flight 计数中间件
    - 新建 `backend/app/middleware/inflight.py`：`InflightTrackingMiddleware` 维护进程级 `inflight_counter`（increment/decrement），探针请求（`/livez` `/readyz`）不计数（避免健康检查永远阻止 drain 完成）；在 `main.py` 注册
    - _Requirements: 3.5, 11.2_ / _Design: 组件 3a_

  - [x] 3.2 实现 SIGTERM handler + drain 逻辑
    - 在 lifespan 内注册 `loop.add_signal_handler(signal.SIGTERM, ...)`（POSIX），`NotImplementedError` 时 `signal.signal` 兜底（Windows）；handler 置 `shutdown_state.draining=True`（readyz 立即 503）；`_drain_http_requests(timeout)` 等 `inflight_counter` 归零，上限 `GRACEFUL_SHUTDOWN_TIMEOUT`（默认 30s），超时记录未完成数后退出
    - _Requirements: 3.4, 3.5, 3.6_ / _Design: 组件 3b + 错误处理「drain 超时」「Windows 无 SIGTERM」_

  - [x] 3.3 扩展 lifespan 关闭顺序
    - 在现有 yield 后逻辑前插入：①（draining 已置）②`sleep PRE_DRAIN_DELAY`（默认 2s，给 nginx 健康检查摘流窗口）③`sse_registry.close_all()`（先留空注册表桩，组件 7 补实现）④`await _drain_http_requests(GRACEFUL_SHUTDOWN_TIMEOUT)` → 之后才是现有 F44 worker `stop_event.set()` + `task.cancel()` + `dispose_engine()`（不变）
    - 新增配置 `GRACEFUL_SHUTDOWN_TIMEOUT`（默认 30）、`PRE_DRAIN_DELAY`（默认 2）
    - _Requirements: 3.5, 3.7_ / _Design: 组件 3c_

  - [x]* 3.4 编写 Property 12 属性测试（drain 等待 in-flight）
    - **Property 12：Drain 等待 in-flight 请求完成**
    - **Validates: Requirements 3.5, 11.2**
    - Hypothesis 随机 in-flight 序列，断言仍有未完成且未超时时 drain 不返回；in-flight 归零或达超时才结束；探针请求不计入；`# Feature: zero-downtime-deployment, Property 12`
    - _Requirements: 3.5, 3.6, 11.2_

- [x] 4. 组件 4 — 前端版本协商（新增，A/B 通用）
  - 检测服务端版本变化，非阻断提示，老前端继续运行（不强制刷新）
  - _Requirements: 1.3, 1.4, 1.5_ / _Design: 组件 4_

  - [x] 4.1 实现 useVersionCheck composable
    - 新建 `audit-platform/frontend/src/composables/useVersionCheck.ts`：首次锁定 `localVersion`，`recordServerVersion(v)` 检测漂移置 `updateAvailable`；≤60s 轮询 `/api/version` 作兜底；任意情形不调 `location.reload`
    - _Requirements: 1.3, 1.4, 1.5_ / _Design: 组件 4a_

  - [x] 4.2 实现 NewVersionBanner 非阻断提示组件
    - 新建 `<NewVersionBanner>`：`updateAvailable` 时显示可关闭的「新版本可用，建议刷新」横幅（GT 紫令牌 `--gt-color-primary`），不强制刷新、不中断操作；中文文案
    - _Requirements: 1.4, 1.5_ / _Design: 组件 4b_

  - [x] 4.3 http 拦截器读 X-App-Version
    - 在前端 http 拦截器从每个响应读 `X-App-Version` 头调 `recordServerVersion`，使检测延迟远低于 60s 轮询上限（轮询作兜底）
    - _Requirements: 1.2, 1.3_ / _Design: 组件 4 注释_

  - [x]* 4.4 编写 Property 3 属性测试（版本协商非阻断）
    - **Property 3：版本不一致触发非阻断提示且不强制刷新**
    - **Validates: Requirements 1.4, 1.5**
    - fast-check（`numRuns=5`）随机 (local, server) 版本对，断言不一致→`updateAvailable=true`、一致→`false`，且任意情形不调用 `location.reload`；`# Feature: zero-downtime-deployment, Property 3`
    - _Requirements: 1.4, 1.5_

- [x] 5. 组件 5 — 迁移向后兼容检测脚本 + CI 接入（新增，A/B 通用）
  - sqlglot 解析新增 V*.sql 识别 Breaking_DDL + 豁免声明 + 双档处置 + CI job
  - _Requirements: 2.2, 2.3, 2.5, 2.6, 2.8, 6.1, 10.1, 10.3, 10.5_ / _Design: 组件 5_

  - [x] 5.1 实现 Breaking_DDL 检测脚本
    - 新建 `backend/scripts/check/check_migration_compat.py`：用 `sqlglot.parse(sql, read="postgres")`（仓库既有依赖，勿引新依赖）识别 `DROP COLUMN`/`RENAME COLUMN`/不兼容 `ALTER COLUMN TYPE`/新增 `NOT NULL` 无默认列；`scan_changed_migrations()` 仅扫本次 PR 新增的 `V*.sql`
    - _Requirements: 2.2, 2.3, 2.5, 6.1, 10.1, 10.3_ / _Design: 组件 5_

  - [x] 5.2 实现豁免声明 + 双档退出码
    - 识别 `-- breaking-ddl-exempt:` 注释（标前置收缩版本号）→ 标 exempt 放行；`main(mode)`：`warning` 档恒退出 0（仅告警）、`strict` 档当且仅当存在非豁免违规时退出非 0（阻断合并）
    - _Requirements: 2.6, 2.8, 10.5_ / _Design: 组件 5_

  - [x] 5.3 CI 接入 migration-compat-check job
    - `.github/workflows/ci.yml` 新增 job，复用 `sqlfluff-lint` 的 `continue-on-error` 模式：`continue-on-error: ${{ vars.MIGRATION_COMPAT_MODE != 'strict' }}`，默认 `warning`；`fetch-depth: 0`（diff 新增迁移）；运行 `python backend/scripts/check/check_migration_compat.py --mode ${{ vars.MIGRATION_COMPAT_MODE || 'warning' }}`
    - _Requirements: 2.8, 10.3_ / _Design: 组件 5 CI 接入_

  - [x]* 5.4 编写 Property 4 属性测试（破坏性 DDL 检测）
    - **Property 4：破坏性 DDL 被检测并报告**
    - **Validates: Requirements 2.2, 2.3, 2.5, 6.1, 10.1, 10.3**
    - Hypothesis 生成含/不含破坏性 DDL 的 SQL，断言当且仅当含时报告对应违规并指出文件与语句；`# Feature: zero-downtime-deployment, Property 4`
    - _Requirements: 2.2, 2.3, 2.5, 6.1, 10.1, 10.3_

  - [x]* 5.5 编写 Property 5 属性测试（豁免声明放行）
    - **Property 5：豁免声明使破坏性 DDL 被放行**
    - **Validates: Requirements 2.6, 10.5**
    - Hypothesis 破坏性 DDL ± 豁免注释，断言含豁免→标 exempt 放行、不含→报违规；`# Feature: zero-downtime-deployment, Property 5`
    - _Requirements: 2.6, 10.5_

  - [x]* 5.6 编写 Property 7 属性测试（双档退出码）
    - **Property 7：CI 双档模式按档位决定退出码**
    - **Validates: Requirements 2.8**
    - Hypothesis 随机违规集合 × {warning, strict}，断言 warning→退出 0、strict→当且仅当存在非豁免违规时退出非 0；`# Feature: zero-downtime-deployment, Property 7`
    - _Requirements: 2.8_

  - [x]* 5.7 编写 Property 9 属性测试（V/R 配对完整）
    - **Property 9：V/R 迁移配对完整**
    - **Validates: Requirements 10.4**
    - Hypothesis 扫描 migrations 目录，断言每个 `V{n}*.sql` 存在对应 `R{n}*.sql`；`# Feature: zero-downtime-deployment, Property 9`
    - _Requirements: 10.4_

  - [x]* 5.8 编写 Property 8 属性测试（advisory lock 串行化，复用已有 MigrationRunner）
    - **Property 8：迁移 advisory lock 串行化多副本**
    - **Validates: Requirements 2.7, 4.4**
    - Hypothesis 模拟 N 个并发启动的 `MigrationRunner`（PostgreSQL 方言，需真实 PG），断言每版本 `schema_version` 恰记录一次；仅验证已有 `pg_advisory_lock` 机制不重写；`# Feature: zero-downtime-deployment, Property 8`
    - _Requirements: 2.7, 4.4_

- [x] 6. P0 检查点
  - 确保所有测试通过，如有疑问询问用户。运行后端 `python -m pytest backend/tests/ -v --tb=short`（用 `rtk` 前缀，`;` 连接）+ 前端 `npx vitest --run`；探针/drain 用 in-process `httpx.ASGITransport(app=app)` 验证（避免 uvicorn --reload 残留旧代码）
  - _Requirements: 1, 2, 3, 6, 10, 11_

---

## Phase 2（P1）：硬零停机滚动编排 + SSE（对齐组件 6、7、9）

- [x] 7. 组件 6 — nginx 反向代理 + 滚动替换脚本 + compose 改造（新增，**A 专属**）
  - 去固定 container_name + 多副本 + 滚动切流，依赖 Phase 1 的 /readyz
  - _Requirements: 4.1, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 13.2_ / _Design: 组件 6_

  - [x] 7.1 改造 docker-compose backend 服务
    - 删除 `container_name: audit-backend`（固定名无法多副本）；`expose: ["8000"]`（不再直接映射宿主机，由 nginx 统一入口）；**每副本单 worker** `command: uvicorn app.main:app --workers 1`（多容器副本，非单容器多 worker，禁 --reload）；具名容器副本（如 `backend1`/`backend2`）由滚动脚本管理，**不用 `deploy.replicas`+DNS**（nginx 需具名 upstream 精确控制成员）；`stop_grace_period: 40s`（> GRACEFUL_SHUTDOWN_TIMEOUT 30s）；healthcheck 改 `curl -f http://localhost:8000/readyz`；注入 `BUILD_VERSION_JSON` / `GRACEFUL_SHUTDOWN_TIMEOUT`
    - _Requirements: 4.1, 5.1_ / _Design: 组件 6a + 概述「生产部署拓扑」_

  - [x] 7.2 新增 nginx 反向代理配置
    - 新建 `docker/nginx/nginx.conf`（A 专属）：`upstream backend_pool` 用**具名 server 列表**（每副本一条 `server backendN:8000 max_fails=2 fail_timeout=5s`），**非单一服务名靠 DNS 动态解析**（开源 nginx 启动只解析一次 DNS 不感知容器增减→转发已停容器 502）；`/livez` `/readyz` `/` 路由；`proxy_next_upstream error timeout http_502 http_503`（不就绪副本自动切下一个）；SSE 需 `proxy_read_timeout 3600s` + `proxy_buffering off`；upstream 成员可用模板片段文件 + 脚本渲染；在 compose 新增 nginx 服务
    - _Requirements: 5.2, 5.7_ / _Design: 组件 6b + 概述「生产部署拓扑」+ 错误处理「nginx 转发到正在退出副本」_

  - [x] 7.3 实现滚动替换脚本
    - 新建 `scripts/deploy/rolling_update.sh`（A 专属）：逐副本 启新容器 → 轮询新副本 `/readyz` 至 200 或超 `READINESS_TIMEOUT`（超时中止 + 保留旧副本 + 非 0 退出码报告失败，**不停止任何旧副本**）→ nginx reload 纳入新副本 → `docker stop` 旧副本（SIGTERM，40s 内 drain）→ 确认退出 → nginx reload 移除旧副本；保留上一镜像 tag 支持回滚（`--image <上一就绪 tag>`）
    - _Requirements: 5.3, 5.4, 5.5, 5.6_ / _Design: 组件 6c + 部署运行手册_

  - [x]* 7.4 编写 Property 21 属性测试（就绪门控 + 回滚）
    - **Property 21：部署就绪门控与回滚**
    - **Validates: Requirements 5.5, 5.6, 12.2**
    - Hypothesis 随机 readyz 序列，断言 (a) 就绪超时未就绪→中止滚动 + 保留旧副本 + 报告失败、不停旧；(b) 失败回滚→活跃流量指向上一已知就绪版本（保留镜像 tag）；`# Feature: zero-downtime-deployment, Property 21`
    - _Requirements: 5.5, 5.6, 12.2_

- [x] 8. 组件 7 — SSE 优雅关闭 + 前端通用重连（扩展，服务端 A/B 通用 / 前端通用）
  - 服务端 drain 优雅关 SSE；前端 useSSEReconnect 抽自 ImportProgress 并推广
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_ / _Design: 组件 7_

  - [x] 8.1 实现服务端 SSE 注册表 + drain 优雅关 + 盘点接入所有现有 SSE 端点
    - 新建 `backend/app/core/sse_registry.py`：`SSERegistry` 登记活跃 SSE 连接（建立 register / 断开 unregister）；`close_all()` 发 `server_draining` 结束事件后关闭所有连接（触发客户端 `EventSource.onerror`）；接入组件 3c lifespan drain 步骤 3（替换桩）
    - **盘点接入所有现有 SSE 端点**（漏接则该连接 drain 时静默挂起）：用 grep/codegraph 盘出全部 SSE 端点（至少 `events.py` `/api/events/stream`、`ledger_import_v2.py` `/jobs/{job_id}/stream`，及可能的 task_events 等），**每个端点的生成器/EventSourceResponse 进入时 register、退出时 unregister**，不可只接一个
    - _Requirements: 7.1_ / _Design: 组件 7a + 现有 SSE 端点盘点_

  - [x] 8.2 实现前端 useSSEReconnect composable
    - 新建 `audit-platform/frontend/src/composables/useSSEReconnect.ts`（抽自 `ImportProgress.vue` 重连模式）：`onerror`→关流→`pollFallback()` 查真实状态：completed/failed/canceled→渲染终态（不报"中断"）/ running→重连（≤`maxAttempts` 默认 30，退避 `backoffMs` 默认 2000，加 jitter 分散重连）/ 超 maxAttempts→提示中断；收到消息重置 attempts
    - _Requirements: 7.2, 7.3, 7.4, 7.5_ / _Design: 组件 7b + 风险「SSE 重连风暴」_

  - [x] 8.3 重构 ImportProgress 消费 useSSEReconnect 并推广
    - 将 `ImportProgress.vue` 重构为消费 `useSSEReconnect`（消除重复实现）；其余 SSE 场景（stale 推送 `LINKAGE_STALE_CHANGED` 等）统一接入
    - _Requirements: 7.2, 7.3_ / _Design: 组件 7b 注释_

  - [x]* 8.4 编写 Property 14 属性测试（SSE 优雅关闭）
    - **Property 14：Drain 时 SSE 被优雅关闭而非静默挂起**
    - **Validates: Requirements 7.1**
    - Hypothesis 随机活跃 SSE 连接集合，断言 `close_all()` 后所有连接收到结束信号并关闭，无静默挂起；`# Feature: zero-downtime-deployment, Property 14`
    - _Requirements: 7.1_

  - [x]* 8.5 编写 Property 15 属性测试（SSE 断线重连真实状态回退）
    - **Property 15：SSE 断线重连并以真实状态回退**
    - **Validates: Requirements 7.2, 7.3, 7.4**
    - fast-check（`numRuns=5`）随机断开 + 作业状态，断言终态→渲染终态、running→重连，重连后状态与真实一致；`# Feature: zero-downtime-deployment, Property 15`
    - _Requirements: 7.2, 7.3, 7.4_

  - [x]* 8.6 编写 Property 16 属性测试（重连次数有界）
    - **Property 16：SSE 重连次数有界**
    - **Validates: Requirements 7.5**
    - fast-check（`numRuns=5`）持续失败连接，断言尝试次数 ≤ `maxAttempts` 后停止重连并提示，无无限重连风暴；`# Feature: zero-downtime-deployment, Property 16`
    - _Requirements: 7.5_

- [x] 9. 组件 9 — 后台 worker 多副本去重（扩展，A/B 通用）
  - 选主锁确保同一后台任务仅一个副本执行
  - _Requirements: 4.5_ / _Design: 组件 9_

  - [x] 9.1 实现选主锁辅助
    - 新建 `backend/app/workers/_leader_lock.py`：`try_acquire_leadership(worker_key, ttl_ms)` 用 Redis `SET key value NX PX ttl` 选主；Redis 不可用降级 `pg_try_advisory_lock`（非阻塞）；锁 TTL > 单轮任务最长耗时（防脑裂，风险表）
    - _Requirements: 4.5_ / _Design: 组件 9 + 风险「后台 worker 脑裂」_

  - [x] 9.2 接入 in-process worker run loop
    - 在仍需 in-process 的 worker（sla/outbox/cleanup 等）run loop 每轮先 `try_acquire_leadership`，抢到才执行本轮、未抢到 sleep 跳过；保留既有 `LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED` 关进程内 import runner 改 standalone 的路径
    - _Requirements: 4.5_ / _Design: 组件 9 + 关键设计决策「多副本后台 worker 去重」_

  - [x]* 9.3 编写 Property 13 属性测试（worker 选主唯一性）
    - **Property 13：后台 worker 选主唯一性**
    - **Validates: Requirements 4.5**
    - Hypothesis N 个副本对同一 worker key 并发选主，断言同一时刻至多一个 `try_acquire_leadership` 返回 true，其余跳过；`# Feature: zero-downtime-deployment, Property 13`
    - _Requirements: 4.5_

- [x] 10. P1 检查点
  - 确保所有测试通过，如有疑问询问用户。运行后端 + 前端测试套件；用 in-process ASGI 验证 SSE 优雅关 + drain；nginx 配置/滚动脚本做语法校验（`nginx -t` / `bash -n`）
  - _Requirements: 4, 5, 7_

---

## Phase 3（P2）：在线 DDL + Feature Flag 灰度（对齐组件 8、组件 5 在线 DDL 部分）

- [x] 11. 组件 8 — feature_flags 数据层（V068 三层一致 + 契约测试）
  - DB 迁移 + ORM + 契约，遵循三层一致铁律
  - _Requirements: 9.1, 9.3, 9.5_ / _Design: 数据模型「feature_flags 表」_

  - [x] 11.1 编写 V068 迁移 + R068 回滚
    - 新建 `backend/migrations/V068__feature_flags.sql`（`CREATE TABLE IF NOT EXISTS feature_flags`，列 `id`/`flag_key UNIQUE`/`description`/`enabled DEFAULT false`/`rollout_percentage SMALLINT DEFAULT 0 CHECK 0~100`/`whitelist_user_ids JSONB`，**显式写 `created_at`/`updated_at` TIMESTAMPTZ NOT NULL DEFAULT now()**）+ 配对 `R068__rollback.sql`（DROP TABLE）；CREATE/ALTER 必 `IF NOT EXISTS`，按数字去重
    - _Requirements: 9.1, 9.3, 9.5_ / _Design: 数据模型 + 三层一致铁律_

  - [x] 11.2 加入 FeatureFlag ORM 模型
    - `audit_platform_models.py` 新增 `FeatureFlag(Base, TimestampMixin)`，`Mapped[]` 列与 V068 DDL 逐列对齐
    - _Requirements: 9.1, 9.3, 9.5_ / _Design: 数据模型「三层一致性」_

  - [x]* 11.3 编写 feature_flags 契约测试
    - 将 feature_flags 表/列纳入 `test_raw_sql_schema_contract.py` / `test_raw_sql_column_contract.py` 守护；验证 DDL↔ORM 零 drift（含 created_at/updated_at）
    - _Requirements: 9.5_ / _Design: 三层一致铁律 + 契约测试_

- [x] 12. 组件 8 — FeatureFlagService + API + 前端开关（新增，A/B 通用）
  - DB 权威 + 5s TTL 缓存 + 稳定哈希灰度；admin API；前端开关
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_ / _Design: 组件 8_

  - [x] 12.1 实现 FeatureFlagService
    - 新建 `backend/app/services/feature_flag_service.py`：`is_enabled(db, flag_key, *, user_id)` 读 `feature_flags`（`_CACHE_TTL_SECONDS=5` TTL 缓存）；全局关→False / 白名单命中→True / `rollout_percentage>=100`→True / `<=0`→False / 否则稳定哈希 `md5(f"{flag_key}:{user_id}") % 100 < rollout_percentage`（同用户幂等）；DB 不可达返上次缓存值，无则按缺省（关闭）保守处理（错误处理表）
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_ / _Design: 组件 8 + 错误处理_

  - [x] 12.2 实现 feature-flags API 并注册到 router_registry
    - 新建 `backend/app/api/feature_flags.py`（admin 认证）：`GET /api/feature-flags`（列出）/ `GET /api/feature-flags/{key}` / `PUT /api/feature-flags/{key}`（设置 enabled/rollout_percentage/whitelist，即时生效 ≤TTL 无需重部署）；注册到 `router_registry`（否则前端 404）
    - _Requirements: 9.4_ / _Design: 组件 8 读写端点 + API 契约_

  - [x] 12.3 实现前端 feature flag 开关消费
    - 前端读取 flag 状态控制功能可见性（关闭时行为与未部署一致）；admin 管理界面调 PUT 设置开关（GT 紫令牌，中文文案）
    - _Requirements: 9.2, 9.4_ / _Design: 组件 8_

  - [x]* 12.4 编写 Property 17 属性测试（默认关 + 关闭即时不暴露）
    - **Property 17：Feature flag 默认关闭且关闭即时不暴露**
    - **Validates: Requirements 9.1, 9.2, 9.4**
    - Hypothesis 随机 flag 状态，断言未启用（默认/被关闭）→`is_enabled` 返 false；启用后关闭（TTL 内）→转 false 无需重部署；`# Feature: zero-downtime-deployment, Property 17`
    - _Requirements: 9.1, 9.2, 9.4_

  - [x]* 12.5 编写 Property 18 属性测试（灰度命中按百分比且稳定）
    - **Property 18：灰度命中按百分比且对同一用户稳定**
    - **Validates: Requirements 9.3**
    - Hypothesis 随机 `rollout_percentage` + 用户集，断言命中比例近似该百分比 + 同 (flag,user) 多次调用幂等 + 白名单恒命中；`# Feature: zero-downtime-deployment, Property 18`
    - _Requirements: 9.3_

  - [x]* 12.6 编写 Property 19 属性测试（多副本一致）
    - **Property 19：Feature flag 多副本一致**
    - **Validates: Requirements 9.5**
    - Hypothesis 两副本缓存一致后（TTL 内），断言同 (flag,user) 读取判定相同（DB 唯一权威源）；`# Feature: zero-downtime-deployment, Property 19`
    - _Requirements: 9.5_

- [x] 13. 组件 5（在线 DDL 部分）— 锁表语句检测（扩展 check_migration_compat）
  - 在已有检测脚本加 LOCK_PATTERNS：CREATE INDEX 非 CONCURRENTLY 标记
  - _Requirements: 8.2, 8.3_ / _Design: 组件 5 LOCK_PATTERNS_

  - [x] 13.1 扩展检测脚本识别非并发索引
    - 在 `check_migration_compat.py` 加 `LOCK_PATTERNS`：`CREATE INDEX` 未用 `CONCURRENTLY` 标记锁表告警（`exp.Create` kind=INDEX + `_is_concurrent` 判定）；`CREATE INDEX CONCURRENTLY` 不标记；纳入双档处置
    - _Requirements: 8.2, 8.3_ / _Design: 组件 5_

  - [x]* 13.2 编写 Property 6 属性测试（非并发索引标记）
    - **Property 6：非并发索引创建被标记为锁表风险**
    - **Validates: Requirements 8.2, 8.3**
    - Hypothesis 生成 `CREATE INDEX` ± `CONCURRENTLY`，断言当且仅当未用 CONCURRENTLY 时标记锁表告警；`# Feature: zero-downtime-deployment, Property 6`
    - _Requirements: 8.2, 8.3_

- [x] 14. P2 检查点
  - 确保所有测试通过，如有疑问询问用户。运行后端契约测试 + feature flag 测试 + 检测脚本测试；确认 V068 DDL↔ORM 零 drift（`/api/health` schema 检查）
  - _Requirements: 8, 9_

---

## 收尾：集成测试与文档

- [x] 15. 零停机不变量集成测试（P20，最重要）
  - 滚动期持续打流量断言无 5xx——硬零停机核心验收
  - _Requirements: 5.2, 5.3, 5.4, 11.1, 11.3_ / _Design: 测试策略「关键集成测试 1」_

  - [x] 15.1 实现滚动期持续负载不变量测试
    - 模拟新旧副本共存于同一 PG，滚动更新窗口内用后台协程以固定速率打真实 API 流量；断言整个窗口**零 5xx** + 连接不中断（SSE 长连接除外，由前端重连续传）+ 滚动全程始终 ≥1 就绪副本可服务
    - _Requirements: 5.4, 11.1, 11.3_ / _Design: 测试策略 1_

  - [x]* 15.2 编写 Property 20 属性测试（零停机不变量）
    - **Property 20：零停机不变量（滚动期任意请求不 5xx）**
    - **Validates: Requirements 5.2, 5.3, 5.4, 11.1, 11.3**
    - Hypothesis 随机滚动期请求序列（新旧共存同一 DB），断言无 5xx + 不中断已建连接（SSE 除外）+ 始终 ≥1 就绪副本；`# Feature: zero-downtime-deployment, Property 20`
    - _Requirements: 5.2, 5.3, 5.4, 11.1, 11.3_

- [x] 16. drain 集成测试 + 版本协商端到端
  - _Requirements: 1.1, 1.2, 1.4, 3.4, 3.5, 11.2_ / _Design: 测试策略「关键集成测试 3、4」_

  - [x] 16.1 drain 集成测试
    - 发送 SIGTERM → 断言 readyz 立即 503 → drain 窗口内发起的 in-flight 请求被完成（非中断）→ 进程在 in-flight 归零后退出；用 in-process ASGI 模拟信号（避免 uvicorn --reload 残留）
    - _Requirements: 3.4, 3.5, 11.2_ / _Design: 测试策略 3_

  - [x] 16.2 版本协商端到端测试
    - 构建期注入版本 → `/api/version` 与 `X-App-Version` 返真实值 → 前端检测漂移显示横幅且不刷新（`location.reload` 未被调用）
    - _Requirements: 1.1, 1.2, 1.4_ / _Design: 测试策略 4_

- [x] 17. 部署运行手册 + 生产启动命令文档
  - _Requirements: 5.3, 5.6, 12.2, 12.3, 12.4, 13.5_ / _Design: 部署运行手册 + K8s 预留章节 + 风险与缓解_

  - [x] 17.1 编写 A 方案部署运行手册
    - 文档化滚动更新步骤（构建注入版本 → migration-compat-check → rolling_update.sh → curl /api/version /readyz 验证）+ 回滚步骤（保留上一就绪 tag + R*.sql 经 `MigrationRunner.rollback_to` 收缩回滚）+ 健康验证清单
    - _Requirements: 5.3, 5.6, 12.2, 12.4_ / _Design: 部署运行手册_

  - [x] 17.2 编写生产启动命令文档（禁用 --reload）
    - 在部署文档与 compose 显式标注：**生产禁用 `uvicorn --reload`**（reloader 父子进程 SIGTERM 不干净，drain 不可靠）；生产用 `uvicorn --workers N` 或 `gunicorn -k uvicorn.workers.UvicornWorker`（无 reloader，SIGTERM 直达 worker，drain 生效）；`--reload` 仅本地开发
    - _Requirements: 3.7_ / _Design: 风险与缓解「uvicorn --reload kill 不净」_

  - [x] 17.3 编写 K8s 预留映射表文档
    - 文档化 A/B 通用抽象 vs A 专属 + A 专属 → B（K8s）替换映射表（探针→probe / nginx→Service+Ingress / compose→Deployment / rolling_update.sh→RollingUpdate strategy / stop_grace_period→terminationGracePeriodSeconds）
    - _Requirements: 13.5_ / _Design: K8s 预留章节_

- [x] 18. 文档与 memory 更新
  - 更新 `.kiro/specs/INDEX.md`（spec 状态）+ memory.md「任务状态」（V068 / 当前最高迁移号 / 新增组件）+ 操作铁律补充（生产启动命令禁 --reload、探针 _SKIP_PATHS）
  - _Requirements: 12.5_

---

## 备注

- 标 `*` 的子任务为测试/前端实测类「可选」任务（UI 不强制阻断），但**按用户铁律 `*` 也要做完**（除非明确跳过）；顶层任务与检查点不标 `*`。
- 每条正确性属性（共 21 条）由**单个**属性测试实现，注释标 `# Feature: zero-downtime-deployment, Property N`，Hypothesis `max_examples=5` / fast-check `numRuns=5`。
- 任务标 completed 必须有实际代码 + 测试通过证据；探针/drain/SSE 优雅关用 in-process `httpx.ASGITransport(app=app)` 验证最可靠。
- 本计划仅产出实现与测试代码；不含部署到生产/预发、性能压测执行（需求 12.1 负载基线属外部环境，非编码任务）、用户验收等非编码活动。
