# 需求文档：服务器零停机滚动更新与无感版本迭代（zero-downtime-deployment）

## 简介

本功能为审计平台建立**服务器侧硬零停机部署能力**：在后端版本迭代、数据库迁移、实例替换的全过程中，用户**完全无感知**——不掉线、不报错、不需要手动刷新或重启，正在进行的请求不被中断。

**未来形态定位**：本平台是**服务器版 Web 应用（B/S 架构）**，而非桌面 exe。后端为 FastAPI + uvicorn 多副本，前端为 Vite 构建的 SPA 静态资源，通过浏览器访问；数据层为 PostgreSQL 16 + Redis + 周边 Docker 服务。

**"无感"的精确含义**：本功能追求**硬零停机**（用户完全无感知），而非**软无感**（弹窗提示用户刷新页面）。硬零停机的核心约束是：在滚动更新期间，新旧后端实例**同时连接同一个数据库**，任意时刻到达的任意请求都不得返回 500 或连接中断。

**部署架构策略——A 单机多副本起步，预留 B（K8s）接口**：

- **A（本期落地）**：单台服务器上 Docker Compose 运行多个后端副本 + nginx 反向代理切流 + 滚动替换后端容器。适合事务所私有化交付（数据合规、单机自治）。
- **B（预留接口，本期不实现）**：未来迁移到 Kubernetes（Deployment / Service / Ingress + readiness/liveness probe + HPA + 原生滚动）。适合云 SaaS 形态。
- 本功能的设计**须为 A/B 通用抽象预留接口**（就绪探针 `/readyz`、版本端点、迁移幂等性等是 A/B 通用的），**不得绑死单机方案**（如 nginx 切流脚本是 A 专属，B 用 K8s 原生原语替换）。

> **核心定位：扩展接入已有体系，而非重建。** 经 codegraph 实证，平台已具备零停机的多项关键基础（`MigrationRunner` 的 `pg_advisory_lock` 多 worker 串行化、`/api/health` 健康检查、JWT 无状态认证天然支持多副本、后台 worker 优雅关闭）。本功能以"接入/适配/扩展已有组件"为前提，仅补齐缺失的 7 项能力（见现有基础设施清单）。

## 实施范围与前置说明

### 本功能聚焦

本功能**仅聚焦服务器侧零停机部署能力**，包括：版本协商、迁移向后兼容规约、就绪探针与优雅下线、反向代理多副本滚动编排、SSE 长连接零停机、在线 DDL 安全、feature flag 灰度发布。

### 桌面端（仅点出原则，本期不展开）

桌面端为 **P2 优先级**，未来用 **Tauri**（系统 webview，非 Electron）封装同一套 Vue 前端壳。**关键原则：桌面壳的前端从服务器运行时加载，不打包死**——使零停机能力对 Web 端与桌面端统一生效，桌面壳本质只是浏览器壳，不引入客户端自动更新器的复杂度。本功能**不展开桌面端的具体实现**，仅在此声明该原则以约束架构方向（前端资源版本化、版本协商等设计不得假设客户端为打包死的固定版本）。

### 明确不在本期范围

- 桌面端 Tauri 壳的实现（仅声明原则）
- K8s 部署清单的实际编写（仅预留通用抽象接口）
- 蓝绿/金丝雀的完整自动化编排（P2，本期出抽象与规约）

---

## 现有基础设施复用清单（Codegraph 实证，勿重建）

> 以下组件均已存在并在生产运行。本功能 SHALL 复用，SHALL NOT 重建。

### 已有基础（标注「已有」，复用勿重建）

| 组件 | 位置 | 已有能力 | 本功能如何复用 |
|------|------|----------|----------------|
| **健康检查端点** | `/api/health` | 含 schema drift `degraded` 状态 + redis / ledger-import 子健康检查 | 复用为 readiness 探针的健康数据源（需求 3）|
| **版本端点** | `/api/version` | **当前硬编码返回 `{"version":"1.0.0"}`** | **改造**为返回真实 build 版本 + git hash（需求 1）|
| **MigrationRunner** | `migration_runner.py` | 启动跑 `V*.sql`；`schema_version` 表去重；**`pg_advisory_lock` 多 worker 串行化**（多副本同时启动只有一个跑迁移，其余等锁）；V/R 配对回滚 + `rollback_to` + resilient 模式（单迁移失败不阻塞启动、写 `schema_migration_failures`、health=degraded）| **复用为零停机迁移的执行内核**（A/B 通用），扩展向后兼容校验（需求 2、6）|
| **main.py lifespan** | `main.py` | 启动跑迁移 + 注册事件 handler + 启动后台 worker；关闭时后台 worker 已有优雅关闭（F44：`stop_event` + `task.cancel` + 30s timeout）| **扩展** HTTP 请求级优雅下线（当前只有后台 worker graceful，需求 3）|
| **JWT 无状态认证** | 认证层 | token 在客户端，session 走 Redis | **天然支持多副本水平扩展**，无需改造（需求 4 的前提）|
| **docker-compose.yml** | 仓库根 | 后端 `--profile docker-backend`（固定 `container_name=audit-backend`，单容器无法滚动）；PG16 / Redis / OnlyOffice / Metabase / Paperless | **改造**：去固定 container_name，改多副本（需求 5）|
| **前端 SPA** | `audit-platform/frontend/` | Vite 构建静态资源 + 大量 SSE（导入进度 `ImportProgress` 已部分加断线重连 + stale 推送 `LINKAGE_STALE_CHANGED`）| **扩展** 版本检测与 SSE 自动重连（需求 1、7）|

### 缺失（标注「缺失」，本功能补齐）

| 编号 | 缺失能力 | 优先级 | 对应需求 |
|------|----------|--------|----------|
| ① | 前后端版本协商（SPA 浏览器缓存，后端滚动到新版后老前端调用改动过的 API 报错）| P0 | 需求 1 |
| ② | 迁移向后兼容规约（当前迁移可随意 DROP COLUMN / 改类型，滚动期新旧后端同连一 DB 老代码读不到改动的列就 500）| P0 | 需求 2、需求 10（铁律）|
| ③ | 优雅下线 / 就绪探针（uvicorn `--reload` 父子进程 kill 不净；无 `/readyz` 区分存活 vs 可接流量；HTTP 请求无 drain）| P0 | 需求 3 |
| ④ | nginx 反向代理 + 滚动替换编排（去固定 container_name；多副本 + 健康检查 + 滚动策略）| P1 | 需求 5 |
| ⑤ | SSE / 长连接零停机（实例替换时 SSE 断开）| P1 | 需求 7 |
| ⑥ | 数据库迁移在线安全（大表 DDL 锁表阻塞）| P2 | 需求 8 |
| ⑦ | feature flag 解耦部署与发布（代码上线但功能灰度开）| P2 | 需求 9 |

---

## 术语表

- **System（系统）**：本审计平台的服务器侧整体（后端 + 反向代理 + 数据层）
- **Backend_Instance（后端实例/副本）**：一个运行中的 FastAPI + uvicorn 进程容器；多个实例同时运行构成多副本
- **Old_Instance / New_Instance（旧实例 / 新实例）**：滚动更新中被替换的旧版本副本 / 新部署的新版本副本
- **Reverse_Proxy（反向代理）**：nginx，负责将客户端请求分发到健康的后端实例，并在滚动期切流（A 方案专属；B 方案由 K8s Service/Ingress 替代）
- **Rolling_Deployment（滚动更新）**：逐个用新实例替换旧实例、全程保持至少一个健康实例可接流量的部署过程
- **Liveness（存活探针）**：判断实例进程是否存活、需不需要重启的探针；对应 `/livez`
- **Readiness（就绪探针）**：判断实例是否已准备好接收流量的探针；对应 `/readyz`
- **Drain（排空）**：实例下线前停止接收新请求、等待正在处理的请求完成的过程
- **Build_Version（构建版本）**：一次构建的唯一标识，由语义版本号 + git commit hash + 构建时间组成
- **Version_Endpoint（版本端点）**：`/api/version`，返回 Build_Version
- **Version_Header（版本响应头）**：后端在每个 HTTP 响应中携带的标识当前实例 Build_Version 的响应头（如 `X-App-Version`）
- **Migration_Runner（迁移执行器）**：现有 `MigrationRunner`，启动时执行 `V*.sql` 迁移
- **Expand_Migrate_Contract（扩展-迁移-收缩三步法）**：向后兼容迁移规约——先扩展（加列 / 双写），新版上线稳定后，后续版本再收缩（删旧列）；禁止同一次发布做破坏性 DDL
- **Breaking_DDL（破坏性 DDL）**：会导致旧版本后端代码读写失败的 DDL，如 `DROP COLUMN`、`RENAME COLUMN`、`ALTER COLUMN TYPE`（不兼容类型）、加 `NOT NULL` 无默认值列
- **Feature_Flag（功能开关）**：解耦部署与发布的开关，代码上线后功能默认关闭，按开关灰度启用
- **Online_DDL（在线 DDL）**：不长时间锁表的 DDL，如 `CREATE INDEX CONCURRENTLY`
- **Zero_Downtime_Invariant（零停机不变量）**：滚动期新旧后端共存于同一 DB 时，任意时刻任意请求都不返回 5xx 或连接中断
- **Target_Concurrency（目标并发）**：6000 并发用户
- **SSE（服务器推送）**：Server-Sent Events 长连接，平台用于导入进度、stale 推送等

---

## 需求

> 需求按优先级编排：**P0**（需求 1-3，软无感基础 + 优雅下线）→ **P1**（需求 4-7，硬零停机滚动编排 + SSE）→ **P2**（需求 8-9，在线 DDL + 灰度）→ **铁律与不变量**（需求 10-11）→ **非功能与 K8s 预留**（需求 12-13）。

### 需求 1（P0）：前后端版本协商

**User Story:** As a 运维与终端用户, I want 后端滚动到新版本后，老的浏览器 SPA 能感知到版本变化并继续正常运行直到用户自然刷新, so that 老前端调用已改动的 API 不会因版本不匹配而报错。

> **现状**：`/api/version` 当前硬编码返回 `{"version":"1.0.0"}`，无真实 build 版本；前端无版本检测。

#### Acceptance Criteria

1. THE Version_Endpoint SHALL 返回真实 Build_Version，包含语义版本号、git commit hash、构建时间三个字段。
2. WHEN 一个 HTTP 响应由某个 Backend_Instance 返回, THE Backend_Instance SHALL 在响应中携带标识其 Build_Version 的 Version_Header。
3. THE 前端 SPA SHALL 以不超过 60 秒的间隔轮询 Version_Endpoint 或读取 Version_Header 来检测当前服务端 Build_Version。
4. WHEN 前端检测到服务端 Build_Version 与本地加载时的 Build_Version 不一致, THE 前端 SPA SHALL 显示非阻断式「新版本可用」提示，且不强制刷新、不中断当前操作。
5. WHILE 服务端处于较新 Build_Version 而前端仍为较旧 Build_Version, THE 老前端 SHALL 继续正常运行至用户自行刷新（硬零停机下老前端不被强制中断）。
6. WHERE 后端 API 发生了不向后兼容的契约变更, THE 后端 SHALL 在变更上线前以扩展-迁移-收缩方式保留旧契约，使老前端调用旧契约不返回 5xx（与需求 2 协同）。
7. THE Build_Version SHALL 在构建流水线中由 git commit hash 自动注入，不依赖人工填写。

### 需求 2（P0）：迁移向后兼容规约（扩展-迁移-收缩三步法）

**User Story:** As a 开发者, I want 数据库迁移强制遵循向后兼容规约, so that 滚动更新期间新旧后端同时连接同一个数据库时，老版本代码读不到被改动的列而返回 500 的情况不会发生。

> **现状**：当前迁移可随意 `DROP COLUMN` / 改类型；滚动期新旧后端同连一 DB，老代码读不到改了的列就 500。

#### Acceptance Criteria

1. THE 迁移规约 SHALL 要求结构变更按 Expand_Migrate_Contract 三步执行：先扩展（加列 / 双写）→ 新版上线稳定 → 后续版本收缩（删旧列）。
2. IF 单次发布的迁移包含 Breaking_DDL（`DROP COLUMN` / `RENAME COLUMN` / 不兼容的 `ALTER COLUMN TYPE` / 加无默认值的 `NOT NULL` 列）, THEN THE CI 校验 SHALL 检测并报告违规的迁移文件与语句。
3. WHEN 新增列, THE 迁移 SHALL 为该列提供默认值或允许 NULL，使老版本后端代码的 INSERT 语句（不含该列）继续成功。
4. WHEN 需要重命名或删除列, THE 迁移规约 SHALL 要求拆分为至少两次发布：第一次发布新列并双写、第二次发布在旧列无引用后删除。
5. THE CI 校验 SHALL 扫描每个新增的 `V*.sql` 迁移文件，识别 Breaking_DDL 模式。
6. WHERE 一个 Breaking_DDL 在业务上确属必要且已确认旧版本无引用, THE 迁移规约 SHALL 要求该迁移附带显式的豁免声明（标注前置收缩版本号）。
7. THE 迁移规约 SHALL 沿用现有 `MigrationRunner` 的 `pg_advisory_lock` 串行化机制，使多副本同时启动时仅一个实例执行迁移。
8. THE CI Breaking_DDL 校验 SHALL 支持两档模式：**初稿期为 `warning` 模式**（检测到违规仅告警、不阻断合并，避免开发不便）；**程序初稿完成后切 `strict` 模式**（违规阻断合并）。模式由配置开关控制，默认 `warning`，初稿稳定后由团队显式切 `strict`。

### 需求 3（P0）：就绪探针与 HTTP 优雅下线

**User Story:** As a 运维, I want 后端实例提供区分「存活」与「可接流量」的探针，并在下线时先停止接流、排空正在处理的请求再退出, so that 实例替换时正在处理的请求不被中断、新流量不会被打到尚未就绪的实例。

> **现状**：uvicorn `--reload` 父子进程 kill 不净；无 `/readyz` 区分存活与就绪；当前只有后台 worker 有优雅关闭，HTTP 请求无 drain。

#### Acceptance Criteria

1. THE System SHALL 提供 Liveness 探针端点 `/livez`，仅反映进程是否存活。
2. THE System SHALL 提供 Readiness 探针端点 `/readyz`，反映实例是否已准备好接收流量（含迁移已完成、数据库连接可用、依赖健康）。
3. WHILE 一个 Backend_Instance 尚未完成启动迁移或数据库连接不可用, THE `/readyz` SHALL 返回非就绪状态（HTTP 503）。
4. WHEN 一个 Backend_Instance 收到下线信号（SIGTERM）, THE Backend_Instance SHALL 立即将 `/readyz` 切换为非就绪状态，使 Reverse_Proxy 停止向其分发新请求。
5. WHEN 一个 Backend_Instance 进入 Drain 状态, THE Backend_Instance SHALL 等待正在处理的 HTTP 请求完成后再退出，等待上限为可配置的排空超时（默认 30 秒）。
6. IF Drain 等待超过排空超时仍有未完成请求, THEN THE Backend_Instance SHALL 记录未完成请求数量并退出。
7. THE HTTP 请求级优雅关闭 SHALL 复用并扩展现有 main.py lifespan 的关闭流程（当前已有后台 worker 的 `stop_event` + `task.cancel` + 30s timeout）。
8. THE `/readyz` SHALL 复用现有 `/api/health` 的健康数据（schema drift `degraded` / redis / 子健康检查），不重建健康检查逻辑。

### 需求 4（P1）：多副本水平扩展与共存

**User Story:** As a 运维, I want 后端以多副本运行且任意副本可独立处理任意请求, so that 滚动更新可以逐个替换副本而始终保持服务可用。

#### Acceptance Criteria

1. THE System SHALL 支持同时运行至少 2 个 Backend_Instance 副本，且每个副本可独立处理任意请求。
2. THE Backend_Instance SHALL 保持无状态（认证 token 在客户端、session 在 Redis），不在进程内存中保存跨请求的用户会话状态。
3. WHILE 多个 Backend_Instance 同时运行, THE 任意副本 SHALL 能处理任意已认证用户的请求而无需会话亲和（sticky session）。
4. WHEN 多个 Backend_Instance 同时启动, THE Migration_Runner SHALL 通过 `pg_advisory_lock` 确保仅一个实例执行迁移，其余实例等待锁释放后继续启动。
5. THE 后台 worker SHALL 在多副本环境下避免重复执行（同一后台任务不被多个副本并发重复处理）。

### 需求 5（P1）：反向代理 + 滚动替换编排

**User Story:** As a 运维, I want 通过 nginx 反向代理 + 滚动替换编排实现零停机切流, so that 部署新版本时不产生停机窗口。

> **现状**：docker-compose 后端固定 `container_name=audit-backend`（单容器无法滚动）。本需求为 A 方案专属，B 方案由 K8s Service/Ingress + Deployment 滚动替代。

#### Acceptance Criteria

1. THE 部署编排 SHALL 移除后端容器的固定 `container_name`，使后端可作为多副本运行。
2. THE Reverse_Proxy SHALL 仅将请求分发给 `/readyz` 返回就绪状态的 Backend_Instance。
3. WHEN 执行 Rolling_Deployment, THE 编排 SHALL 按以下顺序逐副本替换：启动 New_Instance → 等待其 `/readyz` 就绪 → Reverse_Proxy 将流量切向 New_Instance → 向 Old_Instance 发送下线信号并排空 → 停止 Old_Instance。
4. WHILE Rolling_Deployment 进行中, THE System SHALL 始终保持至少一个就绪的 Backend_Instance 可接收流量。
5. IF New_Instance 在可配置的就绪超时内未通过 `/readyz`, THEN THE 编排 SHALL 中止本次滚动、保留 Old_Instance 运行，并报告失败。
6. WHEN Rolling_Deployment 失败需要回滚, THE 编排 SHALL 能将流量切回上一个已知就绪的 Backend_Instance 版本。
7. THE Reverse_Proxy 配置 SHALL 设置上游健康检查间隔与失败阈值，使不就绪实例被及时摘除。

### 需求 6（P1）：迁移与多版本共存的运行时安全

**User Story:** As a 开发者, I want 迁移在滚动期执行时不破坏正在运行的旧实例, so that 迁移与新旧实例共存期间数据库始终对两个版本的代码都可用。

#### Acceptance Criteria

1. WHILE Rolling_Deployment 期间新旧 Backend_Instance 共存于同一数据库, THE 已执行的迁移 SHALL 仅包含向后兼容变更（与需求 2 协同），使 Old_Instance 的读写不失败。
2. WHEN New_Instance 启动并执行迁移, THE 迁移 SHALL 在 Old_Instance 仍在处理请求期间保持数据库 schema 对 Old_Instance 兼容。
3. IF 某个迁移失败, THEN THE Migration_Runner SHALL 沿用现有 resilient 模式（写 `schema_migration_failures`、health 置 `degraded`、不阻塞实例启动），且失败实例的 `/readyz` SHALL 反映 degraded 状态。
4. THE 迁移 SHALL 与应用代码部署解耦到可独立追踪的版本，使「先迁移后部署」或「先部署后迁移」的顺序可控。

### 需求 7（P1）：SSE / 长连接零停机

**User Story:** As a 终端用户, I want 实例替换时我的导入进度等 SSE 长连接能自动重连到新实例并续传, so that 我看不到连接中断或进度丢失。

> **现状**：实例替换时 SSE 断开；前端 `ImportProgress` 已部分加断线重连 + stale 推送 `LINKAGE_STALE_CHANGED`。

#### Acceptance Criteria

1. WHEN 一个承载 SSE 连接的 Backend_Instance 进入 Drain 状态, THE Backend_Instance SHALL 优雅关闭其 SSE 连接，触发客户端重连而非静默挂起。
2. WHEN 前端的 SSE 连接（EventSource）断开, THE 前端 SHALL 自动重连，并在重连后从最近已知进度续传，不丢失或重复展示进度。
3. WHILE SSE 断线重连进行中, THE 前端 SHALL 回退到轮询真实作业状态以判断作业是否已完成（沿用现有 `ImportProgress` 重连 + 轮询模式）。
4. WHEN 前端重连后作业已在另一实例完成, THE 前端 SHALL 展示终态而非「连接中断」错误。
5. THE SSE 重连机制 SHALL 设置最大重连次数与退避间隔，避免无限重连风暴。

### 需求 8（P2）：数据库迁移在线安全

**User Story:** As a 开发者, I want 大表 DDL 不长时间锁表阻塞业务, so that 迁移执行期间业务请求不被阻塞超时。

#### Acceptance Criteria

1. THE 迁移规约 SHALL 要求迁移不得长时间持有会阻塞业务读写的表级锁。
2. WHERE 在大表上创建索引, THE 迁移 SHALL 使用 `CREATE INDEX CONCURRENTLY` 等 Online_DDL 方式。
3. IF 一个迁移包含可能长时间锁表的语句, THEN THE CI 校验 SHALL 标记告警并要求显式确认（本期至少规约层面卡点）。
4. THE 迁移规约 SHALL 为锁等待设置上限，使迁移在无法及时获取锁时失败而非无限阻塞业务。

### 需求 9（P2）：Feature Flag 解耦部署与发布

**User Story:** As a 产品负责人, I want 功能代码上线后默认关闭、按开关灰度启用, so that 部署与发布解耦，配合金丝雀逐步放量。

#### Acceptance Criteria

1. THE System SHALL 提供 Feature_Flag 机制，使新功能代码上线后默认关闭。
2. WHEN 一个新功能代码部署上线但其 Feature_Flag 关闭, THE System SHALL 不向用户暴露该功能，且行为与未部署该功能时一致。
3. WHERE 一个 Feature_Flag 启用, THE System SHALL 仅向被灰度命中的用户或范围启用该功能。
4. WHEN 一个已启用的 Feature_Flag 被关闭, THE System SHALL 立即停止暴露该功能，无需重新部署。
5. THE Feature_Flag 的读取 SHALL 在多副本环境下保持一致（同一开关状态对所有副本可见）。

### 需求 10（铁律）：迁移向后兼容铁律

**User Story:** As a 团队, I want 一条不可违反的迁移铁律写入规约并由 CI 强制, so that 任何破坏滚动期新旧共存的迁移都无法合入。

#### Acceptance Criteria

1. THE 迁移铁律 SHALL 规定：同一次发布的迁移**禁止**包含 Breaking_DDL（破坏性 DDL）。
2. THE 迁移铁律 SHALL 规定：所有结构变更必须按 Expand_Migrate_Contract 三步法跨多次发布完成。
3. WHEN 一个迁移文件被提交, THE CI 校验 SHALL 自动检测其是否违反迁移铁律；检测结果按需求 2.8 的双档模式处置（初稿期 `warning` 告警、初稿完成后 `strict` 阻断合并）。
4. THE 迁移铁律 SHALL 沿用现有 V/R 配对回滚约定（每个 `V*.sql` 配 `R*.sql`），使收缩步骤可回滚。
5. WHERE 迁移需要破坏性变更, THE 铁律 SHALL 要求附带豁免声明并标注其前置扩展发布的版本号。

### 需求 11（不变量）：零停机不变量

**User Story:** As a 团队, I want 一条核心不变量贯穿所有设计, so that 硬零停机的本质约束在每个环节都被守住。

#### Acceptance Criteria

1. WHILE Rolling_Deployment 期间新旧 Backend_Instance 共存于同一数据库, THE System SHALL 保证任意时刻到达的任意请求都不返回 5xx 错误（Zero_Downtime_Invariant）。
2. WHILE 任意 Backend_Instance 处于 Drain 状态, THE 正在处理的请求 SHALL 被完成而非被中断。
3. WHEN 流量在 Old_Instance 与 New_Instance 间切换, THE 客户端 SHALL 不感知到连接中断（除 SSE 长连接的自动重连，见需求 7）。
4. THE Zero_Downtime_Invariant SHALL 作为所有滚动编排、迁移、下线设计的验收基线，任何环节不得引入违反该不变量的操作。

### 需求 12（非功能）：并发、回滚与可观测性

**User Story:** As a 运维, I want 滚动更新在目标并发下不降级、可回滚、可观测, so that 高负载下的部署同样安全可控。

#### Acceptance Criteria

1. WHILE Target_Concurrency（6000 并发用户）负载下执行 Rolling_Deployment, THE System SHALL 保持服务可用且不出现整体性能降级到不可用。

> **并发假设（用户确认）**：6000 用户**不会同时触发更新**，而是陆续在不同时间段访问；滚动更新期间的真实并发压力远低于 6000 峰值。故滚动编排无需为"6000 同时在线 + 同时滚动"的极端场景设计，但仍须保证滚动期单副本临时承载不击穿（至少 1 个就绪副本可服务陆续到达的请求）。
2. THE System SHALL 提供回滚能力，使一次失败或有问题的部署能切回上一个已知就绪的 Build_Version。
3. THE System SHALL 使每个 Backend_Instance 当前运行的 Build_Version 可被运维查询追踪（部署版本可观测）。
4. WHEN Rolling_Deployment 进行中, THE System SHALL 暴露各副本的就绪状态与版本，使运维可观测滚动进度。
5. THE 部署版本追踪 SHALL 复用需求 1 的 Build_Version（git commit hash 注入），不引入第二套版本标识。

### 需求 13（K8s 预留）：A/B 通用抽象与专属边界

**User Story:** As a 架构师, I want 明确区分哪些设计是 A/B 通用抽象、哪些是 A 单机专属, so that 未来迁移到 K8s 时只替换专属部分而通用部分零改动。

#### Acceptance Criteria

1. THE 设计 SHALL 将以下能力实现为 A/B 通用抽象（不绑定单机或 K8s）：`/readyz` 与 `/livez` 探针、Version_Endpoint、Migration_Runner 的幂等性与 `pg_advisory_lock` 串行化、HTTP 优雅下线。
2. THE 设计 SHALL 将以下能力标注为 A 单机专属，后续由 K8s 原语替换：nginx 切流配置与脚本（B 用 K8s Service / Ingress）、Docker Compose 多副本编排（B 用 K8s Deployment）、滚动替换脚本（B 用 K8s 滚动更新策略 + readiness/liveness probe）。
3. WHERE 未来迁移到 K8s（B 方案）, THE 通用抽象（探针 / 版本 / 迁移幂等 / 优雅下线）SHALL 无需修改即可被 K8s 的 readiness/liveness probe 与 Deployment 滚动直接复用。
4. THE 探针端点 `/readyz` 与 `/livez` 的语义 SHALL 与 K8s readiness/liveness probe 约定一致（就绪探针决定是否接流、存活探针决定是否重启）。
5. THE 设计文档 SHALL 显式列出 A 专属组件到 B 对应 K8s 原语的替换映射表。

---

## 优先级汇总

| 优先级 | 需求 | 主题 |
|--------|------|------|
| **P0** | 需求 1 | 前后端版本协商（build hash + 前端检测提示）|
| **P0** | 需求 2、需求 10 | 迁移向后兼容三步法规约 + CI 卡点 + 迁移铁律 |
| **P0** | 需求 3 | readyz 就绪探针 + HTTP 优雅下线 |
| **P1** | 需求 4 | 多副本水平扩展与共存 |
| **P1** | 需求 5 | nginx 反向代理多副本 + 滚动替换编排（零停机切流）|
| **P1** | 需求 6 | 迁移与多版本共存的运行时安全 |
| **P1** | 需求 7 | SSE 自动重连 |
| **P2** | 需求 8 | 在线 DDL（CONCURRENTLY）|
| **P2** | 需求 9 | feature flag 灰度 |
| **贯穿** | 需求 11 | 零停机不变量（核心约束）|
| **贯穿** | 需求 12 | 非功能：6000 并发不降级 / 回滚 / 可观测 |
| **贯穿** | 需求 13 | K8s 接口抽象（A/B 通用 vs A 专属）|
