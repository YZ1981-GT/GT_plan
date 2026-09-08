# Requirements Document

## Introduction

本 spec 收敛上一轮 CodeGraph 全平台扫描（13,326 文件）确认的六项平台级架构缺陷，范围严格限定为**平台骨架**：底稿渲染契约、`render-config` 总协调器、后端 `lifespan` 启动编排、领域所有权与依赖边界、事件信封语义、前端路由与 renderer registry 装配。

本 spec **不改任何底稿业务逻辑**、不改公式取数口径、不新增数据库迁移、不改动 UI 视觉。它只让"平台如何装配自己"这件事变成可声明、可校验、可追溯。

### 已确认红基线（调查实证，非推断）

- **componentType 有 8 处真源**且互不投影：`backend/app/data/wp_code_overrides.json`、`wp_classification_service.VALID_COMPONENT_TYPES`、`wp_render_strategies.RENDERER_DISPATCH`、`HtmlComponentType`、`htmlRendererRegistry.REGISTRY_LIST`、`useWpRenderer.WpComponentType`、`_ONLYOFFICE_HTML_WHITELIST`、`_CONFIRMATION_COMPONENTS`。
- `RenderConfigResponse` **未绑定 `response_model`**，实际响应字段由函数体决定，schema 不是契约。
- 前端渲染 DTO **缺** `guidance` / `applicable_standards` / `sign_status` / `permissions`；`schema` / `html_data` / `template_version` / `cross_refs.cell` 的 nullability 与后端不一致。
- `/api/wp-classifications` 的**前置宿主裁决**与 `/render-config` 的**最终 sheet 规划**是两套算法，可给出不同 componentType。
- registry 唯一性守卫检查的是 `Map` 的 **values**，重复 key 早已被 `Map` 覆盖 ⇒ **结构性假绿**。
- 未发现"真实 payload → 真实 registry → 真实 DOM 挂载"的端到端契约测试。
- `_get_render_config_impl` 单函数约 **630–1096 行**，宿主裁决、scope 重定向、sheet 规划、物化、兜底混在一处，无裁决追踪。
- `lifespan` 为长串顺序副作用，顺序语义（迁移 → migration complete → Redis/ACNR → handler 注册 → 事件回放 → grammar → GIN/LibreOffice → rollout → manifest → schema drift → cache warm → security gates → ACNR subscriber/outbox → AI recovery/health → GC → workers → SIGTERM → Ready）只存在于代码行序，无注册表、无运行报告。
- `scripts/gen_service_deps.py` 仅可视化且默认输出指向不存在的 `docs/SERVICE_DEPENDENCY.md`；领域所有权只有人工台账 `docs/architecture/service-capability-ledger.md`，**无可执行守卫**。
- `TaskEventBus.publish()` 计算了幂等 hash 却**未写入 `idempotency_key`**，去重改查 `trace_id LIKE` ⇒ **幂等实际失效**；`task_events` 同表还承载独立的 procedure delivery outbox，replay 会误动它。
- `dispatch_records.py` 有 async `publish()` **未 await**；`review_workflow_service.py` / `independence_signing_service.py` / `adjustments.py` import **不存在的** `app.core.event_bus`；`s_transaction_calculation.py` 对**同步** `broadcast_raw` 用了 `await` 且参数名错误。
- `/task-events` 缺项目访问门禁，replay 直接信任请求体 `operator_id`。
- `router/index.ts` 单文件 **113 routes**；`htmlRendererRegistry.ts` 约 **216 entries**；`components/workpaper/registry/index.ts` 只是按 `startsWith()` 前缀分类，generic componentType 会被错分，**不能作新真源**；`FrontendReferenceIntegrity.spec.ts` 假设 router 单文件且唯一 `children:`。

### 并发边界（硬约束）

以下文件正被其他会话修改，本 spec 只允许**读取后做精确小块合并**，禁止整文件重写或格式化：`.kiro/specs/INDEX.md`、`backend/app/routers/wp_render_config.py`、`audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue`、`audit-platform/frontend/src/composables/useWpRenderer.ts`。本 spec 不得把任何改动混入 `workpaper-page-formula-toolbar-closure`。

## Requirements

### Requirement 1: 组件能力矩阵单一真源

**User Story:** 作为平台维护者，我希望"某 componentType 有哪些能力"只有一处声明，而不是靠 8 个集合互相猜。

#### Acceptance Criteria

1. WHEN 声明 componentType 能力 THEN 必须存在一份 machine-readable component capability manifest，逐 componentType 声明 `has_backend_renderer` / `has_frontend_component` / `override_allowed` / `host_policy` / `owner` / `status`，四种能力**分列不合并**
2. WHEN 生成 manifest THEN 条目必须从现存真源派生并逐项标注来源，禁止手抄；componentType 集合不得写死数量
3. WHEN `wp_code_overrides.json` 被读取 THEN 它只拥有 `wp/sheet → componentType` 映射，不得承载能力、host 策略或白名单语义
4. WHEN 任一真源新增/删除/改名 componentType THEN 投影守卫必须打红并指名缺失方向（后端有前端无 / 前端有后端无 / manifest 未登记）
5. WHEN componentType 只在部分真源出现且属于有意为之 THEN 必须在 manifest 内登记 `exemption` 含 owner、理由与来源 digest，不得从分母消失
6. WHEN `_ONLYOFFICE_HTML_WHITELIST` / `_CONFIRMATION_COMPONENTS` 参与裁决 THEN 必须表达为 manifest 的 host 策略投影，不得作为第二套并行判据
7. WHEN 守卫读取源码提取集合 THEN 必须先 `stripComments()` 并做反向自检（故意改一字必红），禁止纯字符串存在判据

### Requirement 2: render-config 线上契约与前后端 DTO 对齐

**User Story:** 作为前端开发者，我希望后端声明的响应模型就是实际返回的字段，前端类型与之双向一致。

#### Acceptance Criteria

1. WHEN `GET /workpapers/{id}/render-config` 声明 THEN 必须绑定 `response_model`，且响应字段集合与模型字段集合等价
2. WHEN 绑定 `response_model` THEN 必须先以真实项目底稿采集响应 golden 基线，绑定后逐字段比对，出现任何字段丢失/新增/类型变化即打红
3. WHEN 前端渲染 DTO 定义 THEN 必须覆盖后端实际返回的 `guidance` / `applicable_standards` / `sign_status` / `permissions`，缺字段视为契约违规
4. WHEN 字段可为空 THEN `schema` / `html_data` / `template_version` / `cross_refs.cell` 的 nullability 必须前后端一致；前端不得把可空字段声明为必填
5. WHEN 契约变化 THEN 必须有一处守卫同时读后端模型与前端类型并做双向差集，单向检查不算通过
6. WHEN 响应包含未被前端消费的字段 THEN 必须登记为 `reserved` 或删除，不得长期存在无消费方的字段（假绿第①源）
7. WHEN 采集 golden 基线 THEN 必须使用真实数据库中的真实底稿，不得使用构造 fixture 替代

### Requirement 3: 宿主裁决一致性与挂载级契约守卫

**User Story:** 作为审计师，我希望前置分类接口告诉我的宿主类型，和真正打开底稿时渲染的宿主一致。

#### Acceptance Criteria

1. WHEN `/api/wp-classifications` 返回 componentType THEN 对同一 `wp_id/sheet` 必须与 `/render-config` 最终 plan 一致，或显式返回差异原因
2. WHEN 两者不一致且属已知 THEN 必须在裁决追踪与 manifest 内登记，不得静默取任一方
3. WHEN 校验 registry 唯一性 THEN 判据必须落在**声明源的 key 序列**上，不能查 `Map` 的 values（重复 key 已被覆盖）
4. WHEN 校验渲染可达性 THEN 必须有"真实 render-config payload → 真实 registry 查表 → 真实组件挂载"的端到端测试，且断言 DOM 真的产生了宿主根节点
5. WHEN componentType 在 manifest 声明 `has_frontend_component=true` THEN 必须能被该端到端测试实际挂载，声明与挂载不一致即打红
6. WHEN 挂载失败 THEN 必须以 ERROR 暴露并终止该用例，禁止 `try/except` 吞成"本项目无此数据"

### Requirement 4: render-config 协调器分阶段与裁决追踪

**User Story:** 作为平台维护者，我希望能指出"这张 sheet 为什么用这个宿主"，而不是读 460 行函数体。

#### Acceptance Criteria

1. WHEN 重构 `_get_render_config_impl` THEN 必须拆为 `load_render_subject` / `resolve_classification_sources` / `resolve_scope_redirect` / `load_common_render_facts` / `plan_sheets` / `materialize_sheet` / `finalize_render_response` 七个阶段
2. WHEN 拆分完成 THEN 阶段调用顺序与现有行为一致，且每阶段输入输出为显式数据结构，禁止透传整个请求上下文
3. WHEN 拆分完成 THEN 响应必须与 Requirement 2 的 golden 基线**逐字节或逐字段等价**，任何差异必须先被登记为有意变更
4. WHEN 规划 sheet THEN 必须输出裁决追踪，逐 sheet 记录 `chosen_component_type` / `candidate_sources` / `winning_source` / `override_hit` / `redirect_applied` / `fallback_reason`
5. WHEN 现有实现对某分支是 fail-open（异常后降级继续）THEN 重构后必须保持 fail-open 并把原因记入裁决追踪；fail-fast 分支必须保持 fail-fast
6. WHEN 裁决追踪返回 THEN 不得包含 token、完整表达式正文或任何凭据
7. WHEN 该文件被并发会话修改 THEN 只能做精确小块合并，且必须保留其未提交的 canonical sheet identity 改动

### Requirement 5: 声明式启动任务注册表

**User Story:** 作为运维人员，我希望启动步骤是一张能读的表，而不是一段几百行的顺序副作用。

#### Acceptance Criteria

1. WHEN 定义启动流程 THEN 必须使用**有序** registry，逐任务声明 `name` / `phase` / `criticality` / `callable` / `timeout` / `skip_condition`
2. WHEN 执行启动 THEN 必须**串行**按 registry 顺序执行；本 spec 不引入 DAG 拓扑排序、并行执行或自动重试
3. WHEN 迁移到 registry THEN 执行顺序必须与当前 `lifespan` 行序**逐项等价**，并有守卫锁定该顺序
4. WHEN 某任务当前失败会中断启动 THEN 迁移后必须仍中断（`criticality=critical`）；当前仅记录警告的任务迁移后仍只记录警告（`best_effort`），异常语义不得漂移
5. WHEN `_start_workers` 启动后台任务 THEN 必须逐 worker 登记名称并纳入运行报告，不得只报总数
6. WHEN registry 与实际执行不符 THEN 守卫必须打红；只断言"registry 里有 N 项"不算通过，必须断言真实执行序列
7. WHEN 关停 THEN SIGTERM/draining 语义与当前一致，不得因重构提前或延后

### Requirement 6: 启动运行报告与探针语义保持

**User Story:** 作为运维人员，我希望能看到每个启动任务的真实结果，同时探针的对外行为一分不变。

#### Acceptance Criteria

1. WHEN 启动执行 THEN 必须产出运行报告，逐任务记录 `status`（ok/skipped/failed）、耗时、错误摘要与 skip 原因
2. WHEN 查询 `/api/health` THEN 必须能取到该运行报告；报告条目集合必须与 registry 同构（无遗漏、无幻影）
3. WHEN 查询 `/livez` THEN 必须恒返回 200，不受启动任务失败影响
4. WHEN 查询 `/readyz` THEN 判定优先级必须保持 draining → migration → PG/Redis，状态码与响应结构不得改变
5. WHEN 某 best_effort 任务失败 THEN `/readyz` 不得因此变为未就绪，但报告必须显示 failed
6. WHEN 报告输出 THEN 不得包含连接串、密码、token 或完整异常堆栈中的凭据片段

### Requirement 7: 领域所有权地图与可执行依赖边界

**User Story:** 作为架构维护者，我希望"哪个域可以依赖哪个域"是一条能在 CI 里跑的规则，而不是一份人工台账。

#### Acceptance Criteria

1. WHEN 声明领域边界 THEN 必须新建 `docs/architecture/domain-boundaries.json` 作为单一真源，声明域、归属路径、允许依赖方向与 owner
2. WHEN 检查依赖 THEN 必须新建 `backend/scripts/check/check_domain_boundaries.py`，后端用 Python **标准库 AST**、前端复用仓库现有 parser；**不新增任何第三方依赖**
3. WHEN 存在历史违规 THEN 必须落 exact baseline `backend/scripts/check/baselines/domain-boundary-debt.json`，checker 只拦**新增**债务，且债务减少时必须提示更新基线
4. WHEN 后端模块未被任何域覆盖 THEN checker 必须打红，禁止"未归属即放行"
5. WHEN checker 自身被交付 THEN 必须有自测 `backend/tests/scripts/test_check_domain_boundaries.py`，用**合成的违规输入**验证必红，不得只在合规数据上跑（等价变异）
6. WHEN `scripts/gen_service_deps.py` 保留 THEN 必须修正其默认输出路径指向真实存在的文档位置，或明确其只读可视化定位
7. WHEN checker 接入 CI THEN 必须作为**独立追加**的 job，且以归因型判据验收（只断言变动落在本 spec 的字节区间内），不得使用"其他 job 一个都没变"的全局等值判据

### Requirement 8: 统一事件信封语义

**User Story:** 作为平台维护者，我希望进程内事件与持久事件共享同一套身份、版本、因果与幂等字段。

#### Acceptance Criteria

1. WHEN 定义事件 THEN 必须提供共享 `CanonicalEventEnvelopeV1`，字段至少含 `envelope_version` / `event_id` / `event_type` / `event_schema_version` / `event_kind` / `occurred_at` / `project_id` / `year` / `data` / `producer` / `trace_id` / `correlation_id` / `causation_id` / `actor_id` / `actor_role` / `reason_code` / `idempotency_key` / `aggregate_type` / `aggregate_id` / `aggregate_version`
2. WHEN 接入现有两条链 THEN `EventBus`（进程内 fan-out）与 `TaskEventBus`（DB delivery）**只共享 envelope 与 adapter**，transport 不合并
3. WHEN 现有 `EventPayload` / `TaskEvent` 仍在使用 THEN 必须提供双向 adapter 并保持向后兼容，现有订阅方不得因此改签名
4. WHEN 事件缺少必填字段 THEN 必须在构造期失败，不得写入半成品事件
5. WHEN 事件跨链传递 THEN `trace_id` / `correlation_id` / `causation_id` 必须可端到端还原一次业务操作
6. WHEN envelope 序列化 THEN 不得包含 token、密码或附件正文
7. WHEN 双写期结束条件未满足 THEN 不得删除旧字段；删除动作必须由独立任务在证据齐备后执行

### Requirement 9: 事件确定缺陷与授权修复

**User Story:** 作为质量控制复核人，我希望事件幂等真的生效、错误接线真的报错、事件接口真的鉴权。

#### Acceptance Criteria

1. WHEN `TaskEventBus.publish()` 计算幂等 hash THEN 必须真实写入 `idempotency_key` 列，去重必须按该键判定，禁止用 `trace_id LIKE` 近似匹配
2. WHEN 执行 replay THEN 必须排除 `task_events` 表内的 procedure delivery outbox 行，两类记录必须有可判别标记，禁止混用
3. WHEN `dispatch_records.py` 调用 async `publish()` THEN 必须 await；修复后必须有守卫防止再次出现未 await 的协程调用
4. WHEN `review_workflow_service.py` / `independence_signing_service.py` / `adjustments.py` 引用事件总线 THEN 必须 import 真实存在的模块；不存在的 `app.core.event_bus` 引用必须清零
5. WHEN `s_transaction_calculation.py` 调用同步 `broadcast_raw` THEN 必须去掉 `await` 并使用正确参数名
6. WHEN 访问 `/task-events` THEN 必须校验调用方对目标项目的访问权限；replay 的 `operator_id` 必须来自服务端认证身份，禁止信任请求体
7. WHEN 修复上述缺陷 THEN 每项必须有对应守卫，且变异检验必须准确 RED（打红的正是预期那条测试）

### Requirement 10: 前端路由按域拆分且守卫顺序不变

**User Story:** 作为前端维护者，我希望 113 条路由按业务域可读，同时导航守卫行为一分不变。

#### Acceptance Criteria

1. WHEN 拆分路由 THEN 必须按业务域拆为多个 `RouteRecordRaw[]` 模块，由 `router/index.ts` 单点装配
2. WHEN 装配完成 THEN 必须仍只注册**一个** `beforeEach` 守卫，禁止拆成多个守卫（会改变执行顺序语义）
3. WHEN 拆分完成 THEN 拆分前后的**扁平化路由集合**（path / name / meta / 层级关系）必须完全等价，并有守卫锁定
4. WHEN 路由指向 SFC/view THEN 动态 `import()` 必须保持**字面量路径**，禁止变量路径、eager import 或整域异步加载，避免 chunk 结构变化
5. WHEN 路由名或 path 重复 THEN 守卫必须打红并指名冲突项，不得按最后声明者静默覆盖
6. WHEN 拆分后 THEN 必须实测真实登录跳转、深链接与未授权重定向行为不变

### Requirement 11: renderer registry 声明式拆分

**User Story:** 作为底稿开发者，我希望 216 个 registry entry 按域可维护，且查表仍是同步的。

#### Acceptance Criteria

1. WHEN 拆分 registry THEN 必须拆为**显式的域 entry arrays** + 同步 barrel 汇总，禁止复用现有 `registry/index.ts` 的 `startsWith()` 前缀分类（generic componentType 会被错分）
2. WHEN 拆分完成 THEN `getRendererEntry()` 必须保持**同步**契约，调用方签名不得改变
3. WHEN 拆分完成 THEN 拆分前后 entry 集合（key、组件标识、元数据）必须完全等价并有守卫锁定
4. WHEN 出现重复 key THEN 必须在 barrel 汇总期以 collision 打红，禁止依赖 `Map` 覆盖
5. WHEN 域 entry array 未被 barrel 引用 THEN 守卫必须打红（防止新增域文件成为死代码）
6. WHEN 组件为动态 import THEN 必须保持字面量路径与原有懒加载边界

### Requirement 12: 并发安全、验证与完成门

**User Story:** 作为项目负责人，我希望这批骨架改造有可复核的证据，并且不破坏其他会话正在做的事。

#### Acceptance Criteria

1. WHEN 修改并发脏文件 THEN 必须先读磁盘真实内容（`python -c` 直读，不信缓存），只做精确小块合并，禁止整文件重写或格式化
2. WHEN 运行后端测试 THEN 禁止全量跑 `backend/tests`；必须按引用关系反查辐射面后定向执行
3. WHEN 建立守卫 THEN 每条守卫必须做变异检验，并按 RED / GREEN / ANCHOR-MISS / WRONG-TEST 四态记录；只有准确 RED 计通过
4. WHEN 变异脚本运行 THEN pristine 快照必须在起手统一拍摄、`finally` 无条件全量复原，且变异前先跑基线（红则拒绝执行）
5. WHEN 前端改动完成 THEN 必须通过 typecheck/build 与定向 Vitest，且控制台 0 errors
6. WHEN 全部实现完成 THEN 必须启动 `start-dev.bat` 后用 Playwright 实测底稿渲染、路由跳转与健康探针，保存证据
7. WHEN 收口 THEN 必须 `git status --porcelain` 核对本 spec 全部产物是否 tracked，`??` 项必须登记；不创建 commit 或 push，除非用户明确要求
