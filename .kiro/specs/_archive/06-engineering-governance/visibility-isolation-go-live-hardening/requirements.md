# Requirements Document

## Introduction

本 feature 是已完成 spec `procedure-delegation-visibility-isolation`（下称 Parent_Spec）的上线加固与真实验收（go-live hardening）。Parent_Spec 已建成并在开发库上以 property/integration 测试验证了一套服务端强制、fail-closed 的底稿与页面可见性隔离机制：统一 Wp_Bound_Gate、`resolve_wp_binding_and_access()`、Action_Matrix、External_Not_Found、两层委派、`scope_cycles` 上界、OnlyOffice/WOPI 令牌绑定与回调重校验、epoch 失效通道、Route_Coverage_Ledger 与 Evidence_Manifest。相关服务位于 `backend/app/services/wp_visibility/`，迁移 head 为 V113。

本 feature **不重建**该可见性系统。它把已 BUILT-and-TESTED 的机制转为 LIVE、生产可信、真正被接受（truly-accepted）的状态：启用、挂载、审计、真实压测、真实浏览器验收、提交与依赖交互验证。所有术语沿用 Parent_Spec 的 Glossary（Wp_Bound_Gate、native_authz、Rate_Limit_Profile、Evidence_Manifest、External_Not_Found、scope_cycles、access_kind、Sheet_Key、Delegated_Set、History_Set、Performance_Profile、Completion_Guard、Smoke_Profile、Correctness_Profile、Security_Audit、policy epoch、invalidation outbox 等），本文不再重新定义整套系统，仅补充本次加固引入或收敛的术语。

本 feature 覆盖 Parent_Spec 复盘遗留的 6 个上线 GAP 及一条贯穿的证据纪律要求。每个 GAP 以 fail-closed 框架表达，其严谨度与 Parent_Spec 一致：加固动作必须真正生效并被独立证据证明为 LIVE/ACCEPTED，而非仅仅"已构建"。

本 feature 假设 Parent_Spec 的机制实现保持不变；如加固过程中发现机制缺陷，应回到 Parent_Spec 修复而非在本 feature 内重写。

## Glossary

- **Parent_Spec（父规格）**：已完成的 `procedure-delegation-visibility-isolation`，本 feature 复用其全部机制与 Glossary。
- **Go_Live_Item（上线项）**：本 feature 定义的 6 个上线 GAP 之一，每一项均须从"已构建"推进到"真正 LIVE 且被接受"。
- **Enforcement_Flag（强制开关）**：安全配置项 `settings.ONLYOFFICE_JWT_ENFORCE`；当前默认 `False`，导致 OnlyOffice/WOPI 令牌绑定与回调重校验机制虽已构建且恒 fail-closed 校验，但在门拒绝时仅记录告警并放行，未在真实应用上生效。
- **Staged_Enablement（分阶段启用）**：通过配置默认值翻转或环境门控（environment-gated）逐步开启 Enforcement_Flag 的受控上线方式，包含明确的回退（rollback）路径。
- **Rollback_Path（回退路径）**：将 Enforcement_Flag 或已挂载运行时组件恢复到启用前行为、且不需要代码回滚的可执行配置操作。
- **Invalidation_Dispatcher（失效派发器）**：Parent_Spec 已构建的 `app.services.wp_visibility.invalidation_dispatcher`（`InvalidationDispatcher` publisher + `run_invalidation_subscriber` psubscribe subscriber），负责把 invalidation outbox 行提交后 fan-out 到 Redis 并订阅淘汰本地权限缓存的 ≤1 秒快路径。
- **App_Lifespan（应用生命周期）**：`app.main` 的 FastAPI lifespan 启停钩子，用于挂载与优雅停止长生命周期后台组件。
- **DB_Epoch_Safety_Net（数据库 epoch 安全网）**：在 Invalidation_Dispatcher 未挂载或 Redis 不可用时，仅依赖持久 policy epoch 复查（≤1 秒）发现 stale cache 并重取权威授权或拒绝的兜底机制。
- **Fast_Path（Redis 快路径）**：通过 Invalidation_Dispatcher 提交后 fan-out 使权限缓存收敛的路径，区别于 DB_Epoch_Safety_Net。
- **Graceful_Degradation（优雅降级）**：Redis 不可用或 dispatcher 故障时，系统保持 fail-closed（DB_Epoch_Safety_Net 生效、不产生 stale-allow）且不崩溃应用启动的行为。
- **Native_Authz_Entry（原生授权入口）**：Route_Coverage_Ledger 中 `by_gate` 归类为 `native_authz` 的 wp-bound HTTP 入口，仅受既有项目级授权保护，未接入新的细粒度 Wp_Bound_Gate。
- **Native_Authz_Set（原生授权入口集）**：当前 Route_Coverage_Ledger 中全部 Native_Authz_Entry 的集合，基线计数为 72。
- **Leak_Risk_Entry（泄漏风险入口）**：Native_Authz_Set 中经审计判定可能泄漏"scope-internal-not-delegated"内容或 unmapped-sheet 内容的 Native_Authz_Entry。
- **Justified_Allowlist（豁免白名单）**：经审计判定无 Leak_Risk 而显式保留为 `native_authz` 的 Native_Authz_Entry 记录集合，每条含判定理由（rationale）。
- **Capacity_Report（容量报告）**：6000 并发（或最大可诚实达成规模并附外推依据）真实压测产出的、含 p95/错误率/拒绝正确率/限流行为/缓存一致性测量结果的报告。
- **Capacity_Report_Hash（容量报告哈希）**：Capacity_Report 原始字节的 SHA-256，用于将生产 Rate_Limit_Profile 与其测量来源绑定并冻结。
- **Honest_Extrapolation（诚实外推）**：当无法字面达成 6000 并发时，采用可复现工具与配置达到的最大真实并发规模，并以文档化的外推依据说明推算方法与局限，而非以代表性负载冒充 6000 并发。
- **Fresh_Context_Acceptance（新上下文验收）**：使用 Playwright 为每个角色创建全新 browser context 并执行 fresh navigation 的端到端验收，禁止跨角色复用会话状态。
- **Acceptance_Role（验收角色）**：本 feature Fresh_Context_Acceptance 覆盖的角色集合，包括 Admin、Supervisor、Workpaper_Lead、Row_Assignee、Operation_Reviewer、History_Lead、History_Row 与无委派的 Restricted_User。
- **Dev_Servers（开发服务）**：后端（端口 9980）与前端（端口 3030）本地运行实例，Fresh_Context_Acceptance 的前置条件。
- **Dependency_Spec（依赖规格）**：`procedure-delegation-notification`，已知存在 `service_identities` 的 create_all 既有测试失败，需与本 feature 验证互不回归。
- **Interaction_Validation（交互验证）**：验证 Parent_Spec 实现与 Dependency_Spec 共存时两者不互相引入回归的验证过程。
- **Closeout_Evidence（上线证据）**：本 feature 各上线任务复用 Parent_Spec 的 Evidence_Manifest 模式（append-only、对易变 artifact 采用确定性摘要哈希锁定、latest-run-per-task 语义）产出的验收证据。
- **Go_Live_Gate（上线终局门）**：确认全部 6 个 Go_Live_Item 均真正 LIVE/ACCEPTED（而非仅已构建）的最终阻断门禁。
- **Deterministic_Summary（确定性摘要）**：对含易变字段（计时、缓冲、时间戳等）的 artifact 剥离易变部分后生成的、两次生成字节一致的摘要，用于 hash-pin。

## Requirements

### Requirement 1: 启用编辑器令牌强制（Enable Editor Token Enforcement）

**User Story:** 作为平台维护者，我希望 OnlyOffice/WOPI 令牌绑定与回调重校验在真实应用上生效，以便已构建的编辑器安全机制不再因默认放行而失效。

#### Acceptance Criteria

1. WHEN 本 feature 交付生产配置，THE Visibility_System SHALL 使 `settings.ONLYOFFICE_JWT_ENFORCE` 在生产环境求值为 `True`。
2. WHILE Enforcement_Flag 为 `True`，WHEN Wp_Bound_Gate 拒绝一次 OnlyOffice/WOPI 请求，THE Visibility_System SHALL 返回 External_Not_Found 而不放行。
3. WHILE Enforcement_Flag 为 `True`，WHEN OnlyOffice/WOPI 请求携带有效签名、未过期且逐 claim 绑定一致的令牌，THE Visibility_System SHALL 在真实应用上允许该请求继续。
4. WHILE Enforcement_Flag 为 `True`，IF OnlyOffice/WOPI 请求令牌的签名校验失败，THEN THE Visibility_System SHALL 拒绝该请求并记录 `token_invalid`。
5. WHILE Enforcement_Flag 为 `True`，IF OnlyOffice/WOPI 请求令牌已过期，THEN THE Visibility_System SHALL 拒绝该请求并记录 `token_invalid`。
6. WHILE Enforcement_Flag 为 `True`，IF 任一 Token_Binding_Claims 与 URL 参数或服务端解析资源不一致，THEN THE Visibility_System SHALL 拒绝该请求并记录 `token_invalid`。
7. WHILE Enforcement_Flag 为 `True`，IF 只读令牌请求写动作，THEN THE Wp_Bound_Gate SHALL 拒绝写入。
8. WHILE Enforcement_Flag 为 `True`，IF 令牌 secret 或安全配置缺失，THEN THE Visibility_System SHALL fail-closed 拒绝请求。
9. WHILE Enforcement_Flag 为 `True`，WHEN OnlyOffice/WOPI callback 准备写入 Wp_Bound_Resource，THE Wp_Bound_Gate SHALL 重新校验 Current_Version、Action_Matrix 与 claim 中的 `action`。
10. WHERE 采用配置默认值翻转或环境门控作为启用方式，THE Visibility_System SHALL 提供不需要代码回滚的 Rollback_Path 将 Enforcement_Flag 恢复为启用前行为。
11. THE Visibility_System SHALL 在合法开发编辑（JWT disabled 的开发环境）中保持可编辑，不因生产启用而破坏开发编辑流程。
12. WHEN Enforcement_Flag 的启用与 Rollback_Path 被验收，THE Closeout_Evidence SHALL 记录启用方式、生效环境标识与验证结果。

### Requirement 2: 挂载 epoch 失效 Redis dispatcher 到 App_Lifespan（Mount Invalidation Dispatcher）

**User Story:** 作为平台运营者，我希望 epoch 失效的 Redis 快路径在应用运行时真正生效，以便 ≤1 秒撤权不再仅依赖数据库 epoch 复查安全网。

#### Acceptance Criteria

1. WHEN `app.main` 应用启动，THE App_Lifespan SHALL 挂载 Invalidation_Dispatcher 的 publisher 与 subscriber。
2. WHEN 权限、委派、history、scope、角色或项目成员变更事务提交后，THE Invalidation_Dispatcher SHALL 通过 Fast_Path 将 invalidation outbox 行 fan-out 到 Redis。
3. WHEN Invalidation_Dispatcher 的 subscriber 收到失效消息，THE Visibility_System SHALL 在 1 秒内使权限缓存拒绝已撤销访问。
4. WHEN 委派或权限被撤销且 Fast_Path 可用，THE Visibility_System SHALL 通过 Fast_Path 使撤权在 1 秒内收敛。
5. IF Redis 在应用启动时不可用，THEN THE App_Lifespan SHALL 完成应用启动并保持 Graceful_Degradation。
6. IF Redis 在运行期不可用或 Invalidation_Dispatcher 投递失败，THEN THE Visibility_System SHALL 通过 DB_Epoch_Safety_Net 在最多 1 秒内发现 stale cache 并重取权威授权或拒绝请求。
7. WHILE Redis 不可用，THE Visibility_System SHALL 保持 fail-closed 且不产生 stale-allow。
8. WHEN `app.main` 应用关闭，THE App_Lifespan SHALL 优雅停止 Invalidation_Dispatcher 的 subscriber。
9. WHEN Invalidation_Dispatcher 的 Redis 连接中断，THE Invalidation_Dispatcher SHALL 重连并恢复订阅，且重连期间由 DB_Epoch_Safety_Net 兜底。
10. WHEN 挂载与降级行为被验收，THE Closeout_Evidence SHALL 记录 Fast_Path 收敛与 Redis 不可用两类场景的验证结果。

### Requirement 3: 审计 72 条 native_authz 入口（Audit Native Authz Entries）

**User Story:** 作为安全负责人，我希望每一条仅受项目级授权保护的 wp-bound 入口都经过审计，以便 scope_cycles、sheet_key 与委派级隔离在这些入口上不被绕过。

#### Acceptance Criteria

1. THE Visibility_System SHALL 审计 Native_Authz_Set 中的每一条 Native_Authz_Entry。
2. WHEN 审计一条 Native_Authz_Entry，THE Visibility_System SHALL 判定该入口是否可能泄漏 scope-internal-not-delegated 内容或 unmapped-sheet 内容。
3. IF 一条 Native_Authz_Entry 被判定为 Leak_Risk_Entry，THEN THE Visibility_System SHALL 将该入口接入 Wp_Bound_Gate。
4. WHEN Leak_Risk_Entry 被接入 Wp_Bound_Gate，THE Wp_Bound_Gate SHALL 对该入口强制 scope_cycles 上界、Sheet_Key 页面隔离与委派级隔离。
5. WHERE 一条 Native_Authz_Entry 被判定无 Leak_Risk 而保留为 `native_authz`，THE Visibility_System SHALL 在 Justified_Allowlist 中为该入口记录显式判定理由。
6. THE Justified_Allowlist SHALL 使 Native_Authz_Set 中每一条未接入 Wp_Bound_Gate 的入口都有对应记录。
7. WHEN 审计完成，THE Visibility_System SHALL 使 Native_Authz_Set 中的每一条入口要么接入 Wp_Bound_Gate，要么存在于 Justified_Allowlist。
8. THE Visibility_System SHALL 保持 Wp_Bound_Gate 判定诚实，不对任一 Native_Authz_Entry 产生 silent pass。
9. WHEN Route_Coverage_Ledger 记录审计结果，THE Route_Coverage_Ledger SHALL 为每条被接入或被豁免的入口更新 gate、matrix、rationale 与测试证据。
10. IF 一条 Native_Authz_Entry 既未接入 Wp_Bound_Gate 也未记录于 Justified_Allowlist，THEN THE Route_Drift_Guard SHALL 阻断 CI。
11. WHEN 审计结果被验收，THE Closeout_Evidence SHALL 记录被接入入口清单、Justified_Allowlist 及其理由。

### Requirement 4: 真实 6000 并发容量验收与冻结生产 Rate_Limit_Profile（True Capacity Acceptance and Frozen Rate Limit Profile）

**User Story:** 作为平台运营者，我希望生产限流阈值来源于真实容量测量，以便高负载下的隔离行为可信且不因外推假设失真。

#### Acceptance Criteria

1. THE Performance_Profile SHALL 定义运行真实 6000 并发已认证用户基线所需的环境与工具。
2. WHEN 环境或工具无法字面达成 6000 并发，THE Performance_Profile SHALL 以 Honest_Extrapolation 达成最大可诚实实现的并发规模并记录外推依据。
3. WHEN Performance_Profile 执行底稿列表场景，THE Visibility_System SHALL 使服务端列表延迟 p95 不超过 2 秒。
4. WHEN Performance_Profile 执行单资源 gate 场景，THE Wp_Bound_Gate SHALL 使服务端授权延迟 p95 不超过 1 秒。
5. WHEN Performance_Profile 执行预期成功请求，THE Visibility_System SHALL 使服务端错误率不超过 1%。
6. WHEN Performance_Profile 执行越权请求，THE Visibility_System SHALL 使错误允许数等于 0。
7. WHEN Performance_Profile 完成容量测试，THE Performance_Profile SHALL 依据测量结果确定每用户、每项目与每 Entry_Family 的 Rate_Limit_Profile 阈值。
8. WHEN Rate_Limit_Profile 由测量结果确定，THE Visibility_System SHALL 以 Capacity_Report_Hash 将 Rate_Limit_Profile 与其 Capacity_Report 来源绑定并冻结。
9. THE Visibility_System SHALL 仅从被冻结的 Rate_Limit_Profile 读取每用户、每项目与每 Entry_Family 的限流阈值。
10. IF Capacity_Report 或 Capacity_Report_Hash 缺失，THEN THE Visibility_System SHALL 拒绝激活 Rate_Limit_Profile。
11. WHEN Capacity_Report 含易变测量字段，THE Performance_Profile SHALL 以 Deterministic_Summary 生成可稳定 hash-pin 的证据。
12. WHEN 容量验收完成，THE Closeout_Evidence SHALL 记录 Performance_Profile 版本、Rate_Limit_Profile 版本、Capacity_Report_Hash、外推依据与测量结果。

### Requirement 5: Playwright 多角色 fresh-navigation 验收（Fresh Context Multi-Role Acceptance）

**User Story:** 作为验收负责人，我希望以真实浏览器逐角色验证隔离行为，以便用户可见行为被证明与服务端授权一致。

#### Acceptance Criteria

1. WHILE Dev_Servers 运行（后端 9980 与前端 3030），THE Fresh_Context_Acceptance SHALL 为每个 Acceptance_Role 创建全新 browser context 并执行 fresh navigation。
2. WHEN Restricted_User 仅凭程序行层身份请求 scope-internal-not-delegated 的底稿，THE Visibility_System SHALL 在浏览器可见行为上拒绝访问。
3. WHEN Restricted_User 请求 scope-external-delegated 的底稿，THE Visibility_System SHALL 在浏览器可见行为上拒绝访问。
4. WHEN Fresh_Context_Acceptance 覆盖 Acceptance_Role 行为，THE Fresh_Context_Acceptance SHALL 验证列表、tab、URL、写入、复核、附件、AI、版本与 OnlyOffice/WOPI 入口的可见性与动作权限。
5. WHEN 委派或权限被撤销，THE Fresh_Context_Acceptance SHALL 验证浏览器刷新后撤权在 1 秒内生效。
6. WHEN Visibility_System 在浏览器上返回 External_Not_Found，THE Frontend SHALL 显示"资源不存在或不可访问"且不闪现底稿名称或正文。
7. WHEN Fresh_Context_Acceptance 执行任一 Acceptance_Role 场景，THE Frontend SHALL 保持 console error 计数为 0。
8. THE Fresh_Context_Acceptance SHALL 覆盖 Admin、Supervisor、Workpaper_Lead、Row_Assignee、Operation_Reviewer、History_Lead、History_Row 与无委派 Restricted_User 全部 Acceptance_Role。
9. WHEN Fresh_Context_Acceptance 完成，THE Closeout_Evidence SHALL 记录每个 Acceptance_Role 的验收结果与拒绝证据。

### Requirement 6: 提交与依赖 spec 交互验证（Commit and Dependency Spec Interaction Validation）

**User Story:** 作为发布负责人，我希望 Parent_Spec 实现通过 PR 提交并与依赖规格验证互不回归，以便变更可追溯且不破坏相邻功能。

#### Acceptance Criteria

1. WHEN 提交 Parent_Spec 与本 feature 的实现，THE Visibility_System SHALL 通过 Pull Request 提交而不直接推送到 `main` 或 `master`。
2. WHEN 创建提交分支，THE Visibility_System SHALL 推送到新分支并设置远程跟踪。
3. WHEN 暂存变更，THE Visibility_System SHALL 暂存明确属于本次交付的文件，不暂存无关变更。
4. IF 待提交文件疑似包含 secret，THEN THE Visibility_System SHALL 在提交前标记该文件。
5. WHEN 验证与 Dependency_Spec 的交互，THE Interaction_Validation SHALL 确认 Parent_Spec 实现不引入 Dependency_Spec 的新回归。
6. WHEN 验证与 Dependency_Spec 的交互，THE Interaction_Validation SHALL 确认 Dependency_Spec 的既有 `service_identities` create_all 测试失败不掩盖 Parent_Spec 的回归。
7. THE Interaction_Validation SHALL 将 Dependency_Spec 的既有 `service_identities` create_all 测试失败与本 feature 引入的任何失败区分记录。
8. WHEN 提交与交互验证完成，THE Closeout_Evidence SHALL 记录 PR 标识、分支名与 Interaction_Validation 结果。

### Requirement 7: 上线证据纪律与终局门（Closeout Evidence Discipline and Go-Live Gate）

**User Story:** 作为验收负责人，我希望上线状态由可验证证据控制并有终局门确认，以便全部 6 项真正 LIVE/ACCEPTED 而非仅仅已构建。

#### Acceptance Criteria

1. THE Closeout_Evidence SHALL 复用 Parent_Spec 的 Evidence_Manifest 模式，对每个上线任务追加 append-only 记录。
2. WHEN 上线任务产出含易变 artifact 的证据，THE Closeout_Evidence SHALL 以 Deterministic_Summary 对易变 artifact 进行 hash-pin。
3. WHEN Completion_Guard 校验上线证据，THE Completion_Guard SHALL 采用 latest-run-per-task 语义对每任务最新 run 的 artifact 重算 SHA-256 与 size。
4. IF artifact 相对路径包含 `..` 路径段，THEN THE Completion_Guard SHALL 拒绝该 artifact。
5. IF 上线证据的 Evidence_Manifest、Evidence_Schema 或必需 artifact 缺失，THEN THE Go_Live_Gate SHALL 阻断上线声明。
6. IF 任一 Go_Live_Item 的最新 Criterion_Run 结果不为 `passed`，THEN THE Go_Live_Gate SHALL 阻断上线声明。
7. WHEN Go_Live_Gate 评估上线状态，THE Go_Live_Gate SHALL 分别确认 6 个 Go_Live_Item 均为 LIVE/ACCEPTED。
8. IF 任一 Go_Live_Item 仅"已构建"而未被证据证明为 LIVE/ACCEPTED，THEN THE Go_Live_Gate SHALL 阻断上线声明。
9. THE Go_Live_Gate SHALL 拒绝以 Smoke_Profile 结果冒充 Correctness_Profile 或 acceptance 证据。
10. WHEN Go_Live_Gate 通过，THE Closeout_Evidence SHALL 记录 6 个 Go_Live_Item 全部 LIVE/ACCEPTED 的最终确认结果。
