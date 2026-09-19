# Implementation Plan: 平台架构六项收敛

## Overview

实施顺序为“冻结真实基线 → 能力/契约 → render planner → startup → domain governance → events → frontend assembly → mutation/Playwright closure”。22 个任务全部 required；任何外部条件不满足时标 `[-]` 并写明 blocker，禁止绕开或假绿。

并发脏文件只做精确小块合并：`INDEX.md`、`wp_render_config.py`、`GtWpRenderer.vue`、`useWpRenderer.ts`。不得修改或复用 `workpaper-page-formula-toolbar-closure`。

## Task Dependency Graph

```json
{
  "waves": [
    {"wave": 0, "name": "调查与不可变基线", "tasks": [1], "depends_on": [], "rationale": "先冻结真实 payload、执行序列和并发边界"},
    {"wave": 1, "name": "component capability 真源", "tasks": [2, 3], "depends_on": [1], "rationale": "先统一 renderer 能力语言再改运行链"},
    {"wave": 2, "name": "render wire 契约", "tasks": [4, 5], "depends_on": [2, 3], "rationale": "以真实 golden 保护协调器拆分"},
    {"wave": 3, "name": "render planner 拆分", "tasks": [6, 7, 8], "depends_on": [4, 5], "rationale": "按七阶段逐段迁移且每段验证等价"},
    {"wave": 4, "name": "真实挂载契约", "tasks": [9], "depends_on": [3, 5, 8], "rationale": "把声明落实到真实 registry 与 DOM"},
    {"wave": 5, "name": "启动注册表", "tasks": [10, 11, 12], "depends_on": [1], "rationale": "独立平移启动顺序、报告和探针"},
    {"wave": 6, "name": "领域边界治理", "tasks": [13, 14, 15], "depends_on": [1], "rationale": "建立所有权真源、checker、债务和 CI"},
    {"wave": 7, "name": "事件规范与兼容层", "tasks": [16], "depends_on": [1], "rationale": "先建共享信封再修两条 transport"},
    {"wave": 8, "name": "事件确定缺陷与授权", "tasks": [17, 18], "depends_on": [16], "rationale": "修幂等、调用签名、outbox 隔离和门禁"},
    {"wave": 9, "name": "前端物理拆分", "tasks": [19, 20], "depends_on": [3, 5, 9], "rationale": "在契约和挂载守卫就绪后拆装配文件"},
    {"wave": 10, "name": "定向回归与变异", "tasks": [21], "depends_on": [8, 9, 12, 15, 18, 19, 20], "rationale": "按行为链验证且所有关键变异准确 RED"},
    {"wave": 11, "name": "浏览器实测与收口", "tasks": [22], "depends_on": [21], "rationale": "真实服务和 DOM 证据决定完成与归档"}
  ],
  "critical_path": [1, 2, 3, 4, 5, 6, 7, 8, 9, 19, 20, 21, 22],
  "parallelizable": [[2, 3], [10, 13, 16], [11, 14, 17], [12, 15, 18], [19, 20]]
}
```

## Tasks

### Baseline and Render Capability
- [x] 1. 冻结六域红基线、真实清册与并发边界
  - 保存 componentType 八真源差集、代表性 render-config 真实 payload digest、lifespan 真实顺序、事件确定缺陷、113 routes 与约 216 renderer entries 的动态清册
  - 实扫 schema/迁移/active spec/dirty files；每个共享文件记录 owner 与允许修改字节区间
  - 建立只读诊断脚本，输出不含客户正文/凭据；基线文件存在不代表任务完成
  - 证据：`.kiro/specs/platform-architecture-convergence/basis/T01-platform-skeleton-baseline.{json,md}`；复现 `python backend/scripts/diagnose/_freeze_pac_t01_baseline.py`；只读探针 `probe_platform_baseline.py`（已修 RENDERER_DISPATCH=0 假红，改走 generator AST）
  - **冻结当时**实数：DISPATCH 159 / REGISTRY 216 / manifest 220；router path 字面量 117；workers 12；最高迁移 V155；`idempotency_key` 列已在 TaskEvent，**当时**幂等仍走 `trace_id.like`
  - **现网对照**（勿写回冻结栏）：幂等已改 `idempotency_key` 等值；domain debt **4761**（过程中 ~5349 作废）；见 T01 双栏 + `basis/T23-post-closure-followups.md`
  - _Requirements: 1.2, 2.2, 4.3, 5.3, 7.3, 12.1, 12.2_
  - _Properties: 1, 3, 7, 9, 13, 23_

- [x] 2. 建立 component capability manifest 与幂等生成器
  - 新增版本化 manifest，正交声明 backend renderer/frontend component/override/host policy/owner/status/source
  - `wp_code_overrides.json` 继续只拥有 wp/sheet 映射；白名单与 confirmation 集合改为 manifest 投影
  - 生成器支持 `--check`，不写死条目数；exemption 必须有 owner/reason/source digest
  - 证据：`backend/app/data/component_capabilities.json`（220）+ `component_host_declarations.json`；`scripts/gen/generate_component_capability_manifest.py --check`；`wp_render_config` 经 `types_from_source` 导出投影，planner 只读 `host_policy`
  - **exemptions 机器派生（复核 §6 修复，Req 1.5）：** `build_exemptions()` 为每个能力不对称类型自动生成裁决记录（62 条：58 frontend_only + 1 backend_only[univer=宿主在 HTML registry 之外] + 3 manifest_only[skip/redirect/hub]），含 owner/reason[分类]/source_digest（sources 集合 sha256）。不再手写、不会漂移；新不对称→新 exemption→manifest drift→`--check` 失败逼裁决
  - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6_
  - _Properties: 1, 2_

- [x] 3. 建立 manifest 四向守卫、前端类型投影与 collision 红基线
  - AST/JSON/TS parser 提取真源，先 strip comments；报告 backend-only/frontend-only/manifest-missing/expired exemption
  - 前端 componentType 类型从投影消费，`useWpRenderer.ts` 不再维护第二 union
  - registry 在 Map 构造前检查声明 key；做改名/漏投影/重复 key/注释伪命中反向自检
  - 证据：`scripts/check/check_component_capabilities.py`；`tests/test_component_capability_contract.py`（**24 passed**）；`assertUniqueRegistryComponentTypes` 在 Map 前；`componentCapabilities.generated.ts`
  - **checker 硬化（复核 §6 修复，Req 1.4）：** `unadjudicated_asymmetries()` —— backend_only/frontend_only/manifest_only 任一未被 exemption 覆盖即 exit 1（此前只打印 exit 0）；变异测试 `test_checker_flags_unadjudicated_asymmetry_when_exemption_removed` 摘一条 exemption 必红 + 生成器发空 exemptions 触发 `--check` drift
  - _Requirements: 1.4, 1.7, 3.3, 11.4_
  - _Properties: 2, 5, 22_

### Render Contract and Planner

- [x] 4. 冻结真实 render-config golden 并绑定后端 response model
  - 从真实库选 HTML/OnlyOffice/confirmation/program/redirect/multi-sheet 代表底稿，脱敏保存字段/type/nullability/digest
  - endpoint 绑定 `RenderConfigResponse`；绑定前后 payload 双向比对为零差异
  - 新旧字段必须先裁决 active/reserved，禁止 Pydantic 静默裁掉运行字段
  - 证据：`capture_render_config_wire_golden.py` + `tests/fixtures/platform_architecture/render_config_wire_golden.json`（source=live；覆盖 6/6）；`response_model=RenderConfigResponse`；真库 `--check` OK；`basis/T04-T05-render-config-wire.md`
  - _Requirements: 2.1, 2.2, 2.6, 2.7_
  - _Properties: 3, 4_

- [x] 5. 建立前端 RenderConfigWire 与后端双向契约检查
  - 补 guidance/applicable_standards/sign_status/permissions；统一四类已知 nullability
  - 比较后端模型与前端 wire 的双向字段路径/type/nullability 差集
  - 对 reserved 字段建立消费/裁决清单；后端新增或前端凭空新增均打红
  - 证据：`types/renderConfig.ts` + `RENDER_CONFIG_FIELD_STATUS`；`check_render_config_wire_contract.py`；`test_render_config_wire_contract.py`（12 passed，含 nullability 四元组与 reserved 交叉断言）；前端 `renderConfig.wire.spec.ts`（4 passed）
  - _Requirements: 2.3, 2.4, 2.5, 2.6_
  - _Properties: 3, 4_
- [x] 6. 抽取 render subject、classification 与 scope redirect 阶段
  - 落显式不可变输入输出类型，抽 `load_render_subject` / `resolve_classification_sources` / `resolve_scope_redirect`
  - `/api/wp-classifications` 复用公共裁决核；同身份结果不一致时输出原因而非静默覆盖
  - 每抽一步重跑真实 golden；保留并发会话 canonical sheet identity 改动
  - 证据：`wp_render_pipeline.py` Stage 1–3；`resolve_common_classification_resolution` + `plan_sheets` 对照；`divergence_reason`；`basis/T06-T08-render-planner.md`
  - _Requirements: 3.1, 3.2, 4.1, 4.2, 4.3, 4.7_
  - _Properties: 5, 7, 8_

- [x] 7. 抽取 common facts、sheet plan 与 decision trace
  - 抽 `load_common_render_facts` / `plan_sheets`，逐 sheet 记录 candidates/winner/override/redirect/fallback
  - manifest host policy 成为 planner 输入；禁止读取第二套白名单
  - 保持原 fail-open/fail-fast 分支并把降级原因写入 trace；输出脱敏
  - 证据：`plan_sheets` 用 `host_policy`/`manifest_host_policy`；Stage 5/6 无 `_ONLYOFFICE_HTML_WHITELIST` 成员测试；`test_render_pipeline_stage_guards.py`
  - _Requirements: 4.1, 4.2, 4.4, 4.5, 4.6_
  - _Properties: 7, 8_

- [x] 8. 抽取 materialize/finalize 并收敛总协调器
  - 抽 `materialize_sheet` / `finalize_render_response`，入口只保留七阶段编排
  - 每阶段仅接收所需参数，不透传 request/db 全上下文；全 golden 字段等价
  - 为每阶段加行为测试，故意交换阶段或删除 fallback 必须准确打红
  - 证据：`_get_render_config_impl` 七段；`test_orchestrator_preserves_seven_stage_order`；characterization + stage_guards
  - _Requirements: 4.1, 4.2, 4.3, 4.5_
  - _Properties: 7, 8_

- [x] 9. 建立真实 payload→registry→DOM 挂载契约
  - 用真实 golden、真实 registry 和真实 `GtWpRenderer` 挂载，覆盖 active manifest componentType
  - 断言宿主根节点/sheet identity；unknown/unsupported/error 三态分离且异常不吞为空数据
  - collision 在 Map 前失败；manifest 声明但不可挂载必须打红
  - 证据：`GtWpRenderer.real-registry.contract.test.ts`（**13 passed**）：h-static-doc 真挂载 + core/forms `MOUNT_BATCH_SAMPLE_TYPES`（11 类经真实 GtWpRenderer→getRendererEntry→async 解析，非占位）+ **forms lane 真实 GtDForm 挂载**（5 个 d-form-* 共享同一组件引用，真 `.gt-d-form` 根 + form_type 分支分发断言）+ confirmation-summary 轻量 stub + 全量 has_frontend_component↔REGISTRY keys；legacy/barrel 双 assertUnique
  - **重型叶登记豁免（owner+reason+REGISTRY 成员，非从分母消失）：** confirmation-* Teleport 叶 / word-template / custom（OnlyOffice·Univer 内核）在 `MOUNT_UNIT_EXEMPTIONS`，`MOUNT_UNIT_EXEMPTIONS 均在 REGISTRY…不重叠` 用例守卫；深挂载走 Playwright（T22），不在 Vitest 单测批 — 见 `basis/T23-post-closure-followups.md`
  - _Requirements: 3.3, 3.4, 3.5, 3.6_
  - _Properties: 5, 6_

### Startup Lifecycle

- [x] 10. 冻结 lifespan 顺序/异常/skip/shutdown 特征测试
  - 捕获迁移至 Ready 的真实调用序列、critical/best-effort、skip、11+1 workers 和 shutdown 顺序
  - 用注入 callables 验证异常分支，不依赖真实外部服务碰巧在线
  - 交换相邻关键步骤、改变 criticality、漏 worker 的变异必须准确 RED
  - 证据：`backend/app/core/startup_registry.py`（`FROZEN_STARTUP_SEQUENCE_NAMES` / criticality lock）+ `backend/tests/test_startup_registry.py`
  - _Requirements: 5.2, 5.3, 5.4, 5.5, 5.7_
  - _Properties: 9, 10_
- [x] 11. 实现 ordered startup registry、串行 executor 与 worker 登记
  - `StartupTaskSpec` 声明 name/phase/criticality/callable/timeout/skip；tuple 顺序复刻旧链
  - executor 串行运行，不引入 DAG/并行/自动重试；critical 抛出、best-effort 记录继续
  - `_start_workers` 每个 worker 有稳定名称和 result；真实执行序列与 registry 同构
  - 证据：`STARTUP_TASKS` + `run_startup_tasks`；`app.main._start_workers` → `start_all_workers`；12 named workers
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  - _Properties: 9, 10_

- [x] 12. 接入 startup runtime report、health 与 probes
  - 保存 ok/skipped/failed/duration/error summary/skip reason 的只读 snapshot
  - `/api/health` 输出同构报告且脱敏；`/livez` 恒 200
  - `/readyz` draining→migration→PG/Redis 的优先级、状态码和响应结构保持不变
  - 证据：`startup_report_as_dict` → `health.startup`；probes 行为由 `test_startup_registry.py` 锁定
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_
  - _Properties: 11, 12_

### Domain Boundaries

- [x] 13. 建立 domain-boundaries.json 与全生产路径归属清册
  - 声明域、owners、paths、may_depend_on；先覆盖 backend/app 与 frontend/src 生产代码
  - 未归属生产模块单独报错；人工 capability ledger 只作迁移输入不作运行真源
  - 修正 `gen_service_deps.py` 默认输出路径并明确其可视化职责
  - 证据：`docs/architecture/domain-boundaries.json`（schema_version 1，22 domains）；`scripts/gen_service_deps.py` 默认 `docs/architecture/service-dependency.md`
  - _Requirements: 7.1, 7.4, 7.6_
  - _Properties: 13, 14_

- [x] 14. 实现无新依赖的边界 checker、exact debt baseline 与自测
  - Python stdlib AST + 现有前端 parser 生成跨域边，按 policy 计算 violations
  - baseline 只存稳定违规 identity；新增失败、减少提示更新，不锁全仓文件计数
  - 合成 allowed/forbidden/unowned/new-debt/reduced-debt/cycle 输入，防止只在合规数据上假绿
  - 证据：`backend/scripts/check/check_domain_boundaries.py`；`baselines/domain-boundary-debt.json`；`backend/tests/scripts/test_check_domain_boundaries.py`
  - _Requirements: 7.2, 7.3, 7.4, 7.5_
  - _Properties: 13, 14_

- [x] 15. 将领域边界作为独立归因型 CI job 接入
  - 独立运行 checker 与自测；禁止新增 import-linter/grimp/dependency-cruiser
  - CI 守卫只断言本 job 及其文件引用存在，不要求并发会话的其他 job 字节不变
  - 做新增违规/删除债务/删除 manifest domain 三类 CI 变异
  - 证据：`governance-checks.yml` job `domain-boundary-governance`；`TestCiAttributionGuard` + mutation tests
  - _Requirements: 7.5, 7.7_
  - _Properties: 14_

### Event Semantics and Security
- [x] 16. 实现 CanonicalEventEnvelopeV1 与双向兼容 adapters
  - 落完整身份/版本/kind/time/project/year/data/producer/trace/correlation/causation/actor/reason/idempotency/aggregate 字段
  - EventPayload 与 TaskEvent 双向 round-trip；EventBus/TaskEventBus 只共享 envelope，不合并 transport
  - 构造期拒绝缺必填字段；序列化脱敏；旧订阅签名在双写期保持
  - 证据：`app/core/events/{envelope,adapters}.py`；EventBus/TaskEventBus 只 import adapter，互不代理；`tests/test_canonical_event_envelope.py`（round-trip / 脱敏 / 旧签名 / 缺字段必红）
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_
  - _Properties: 15, 16_

- [x] 17. 修复 TaskEventBus 幂等、outbox 隔离与 task-events 授权
  - publish 真写/查 `idempotency_key` 等值；先实证列存在，否则 BLOCKED 回 design
  - replay 明确排除 procedure delivery outbox，不用 trace/string 猜类型
  - endpoint 先校验目标项目可见性；operator/actor 只取服务端认证身份
  - 证据：列已在 TaskEvent（V105 `uq_task_events_idempotency_key`）；publish 写/查 `idempotency_key==`；replay/consume 用 `AGGREGATE_PROCEDURE_ROW_TASK` 排除 outbox；`/task-events` 先 `assert_project_permission`，replay actor=`current_user.id`；`tests/test_task_event_bus_idempotency_auth.py`；`tests/test_task_event_bus_idempotency_auth.py`
  - _Requirements: 9.1, 9.2, 9.6_
  - _Properties: 17, 18_

- [x] 18. 修复事件调用错误并建立调用/行为守卫
  - await `dispatch_records.py` 的 async publish；清零不存在的 `app.core.event_bus` imports
  - `s_transaction_calculation.py` 对同步 broadcast_raw 去 await 并改正确参数名
  - 守卫覆盖协程真实执行、副作用恰一次、错误 import、参数签名、幂等、replay 和授权；逐项变异准确 RED
  - 证据：`tests/test_task_event_bus_idempotency_auth.py` + `tests/test_event_call_site_guards.py`（全树 `app.core.event_bus` 扫描、dispatch await、broadcast_raw 签名、reverse self-checks RED）；列已在 TaskEvent（V105）；publish 写/查 `idempotency_key==`；probe `writes_idempotency_key=True` / `dedup_by_trace_id_like=False` / bad imports=0；adjustments 频道调用已改为 `event_type`+`extra`
  - _Requirements: 9.3, 9.4, 9.5, 9.7_
  - _Properties: 17, 18_

### Frontend Assembly

- [x] 19. 按业务域拆分 Vue Router 并升级引用完整性守卫
  - 域模块导出显式 `RouteRecordRaw[]`，`index.ts` 单点同步装配且只保留一个 beforeEach
  - 保持所有动态 import 字面量；递归比较 path/name/meta/parent chain 等价
  - 升级 `FrontendReferenceIntegrity.spec.ts`，删除单文件/唯一 children 假设；测重复 name/path
  - 证据：`router/domains/{auth,dashboard,projects,workpapers,reports,notes,confirmations,qc,extension,system,standalone}.ts`；golden 113 routes；`FrontendReferenceIntegrity.spec.ts` §0b 投影等价 + 重复 name/path RED；`beforeEach`×1
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  - _Properties: 19, 20_

- [x] 20. 按业务域拆分 renderer entry arrays 与同步 barrel
  - 显式域数组取代约 216 entry 单文件；删除 startsWith classifier，不留 fallback
  - barrel 在 Map 前查 collision，确保每个域数组被消费，`getRendererEntry()` 保持同步
  - 比较 key/component/meta 全量投影与原 registry 等价；保持动态 import 字面量/chunk 边界
  - 证据：`registry/entries/{core,forms,programs,confirmations,reports,specialized}.ts`（16/12/53/22/16/97，合计 216）；`htmlRendererRegistry.ts` thin facade；barrel 无 `startsWith`/`classifyDomain`；`registryDomainSplit.spec.ts` + `registrySplitEquivalence.pbt.spec.ts` + `htmlRendererRegistry.spec.ts` + `FrontendReferenceIntegrity.spec.ts` 共 84 passed
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_
  - _Properties: 21, 22_
### Verification and Closure

- [x] 21. 运行定向后端/前端验证、typecheck/build 与四态变异
  - 按实际引用反查辐射测试；不跑全量 backend/tests；后端 pytest 与前端 Vitest 分域执行
  - 运行 typecheck/build；要求测试 0 failed、0 意外 skipped、控制台 0 errors
  - 变异前基线门，统一 pristine snapshot，finally 全复原；记录 RED/GREEN/ANCHOR-MISS/WRONG-TEST，只有准确 RED 通过
  - 证据：定向后端 **121 passed**；前端装配/挂载 **39 passed**；`mutate_pac_platform_architecture_guards.py` **11/11 RED**（复核 §7 补 M09 task-events授权/M10 health同构/M11 route flatten；collision 由常驻 PBT reverse-check 覆盖并注明）→ `basis/T21-mutation-report.json` + `basis/T21-directed-verification.md`；全仓 `vue-tsc` 8GB OOM（平台既有），隔离 `tsconfig.pac-t21.json` exit 0；manifest 生成器**仅** domain-split entries（已移除 `D_FORM_SUBTYPES.map`）；CI `pac-skeleton-typecheck` = vitest `pacNetworkGate` + vue-tsc
  - **typecheck 覆盖扩展（复核 §5 修复）：** 11 route domains + 6 registry entry arrays 全部经 `pacDomainEntryTypes.spec.ts` 的 `expectTypeOf(...).toEqualTypeOf<RouteRecordRaw[] / HtmlRendererEntry[]>()` 编译期断言（4 passed，`--typecheck` no errors）。**为何不进 tsconfig.pac-t21.json：** 域/entry 文件的 `()=>import('*.vue')` 会让 vue-tsc 解析 200+ SFC 图，6GB 仍 OOM；Vitest 经 Vue 插件解析 .vue 无此爆内存，故两个物理拆分面的纯类型形状放 Vitest typecheck，结构等价仍由 routeDomainProjection/registrySplitEquivalence 运行时守。CI 新增步骤 `PAC split-face type coverage`
  - _Requirements: 12.2, 12.3, 12.4, 12.5_
  - _Properties: 23, 24_

- [x] 22. 启动真实环境完成 Playwright、产物追踪与归档门
  - 用 `start-dev.bat` 启动后端 9980/前端 3030；实测登录、深链、未授权重定向和单 guard 行为
  - 打开 HTML/OnlyOffice/confirmation 代表底稿，验证真实 registry→DOM、decision trace、unknown/error；查询 health/livez/readyz
  - 保存 1280/1440/1920 证据、network/console/DOM/screenshot；控制台 0 errors（资源失败须 response 归因 + ambient allowlist）
  - 实扫所有正式产物 git 状态、回填真实数字与 blocker；未经用户要求不 commit/push
  - 证据：`e2e/platform-architecture-convergence.spec.ts` **4 passed**；`basis/T22-playwright/`；`basis/T22-playwright-closure.md`；console 闸门硬化 `pacNetworkGate.ts`；归档前对照 `basis/T01` 双栏 + `basis/T23-post-closure-followups.md`；未 commit/push
  - **产物 git 状态清单（Req 12.7）：** `basis/T22-porcelain-inventory.md`（55 产物 / 54 `??` / 1 tracked-mod），复现 `python backend/scripts/diagnose/pac_porcelain_inventory.py`；🔴 CI 已跟踪 yml 的 `domain-boundary-governance`/`pac-skeleton-typecheck` job 引用的 5+3 个文件全 `??`，需与 yml 同 commit 入库
  - _Requirements: 10.6, 12.1, 12.5, 12.6, 12.7_
  - _Properties: 20, 23, 24_

## Property Coverage

| Property | Implemented/verified by Task |
|---|---|
| 1 | 1, 2, 3 |
| 2 | 2, 3, 21 |
| 3 | 1, 4, 5, 21 |
| 4 | 4, 5, 21 |
| 5 | 3, 6, 9, 21 |
| 6 | 9, 21, 22 |
| 7 | 1, 6, 7, 8, 21 |
| 8 | 6, 7, 8, 21 |
| 9 | 1, 10, 11, 21 |
| 10 | 10, 11, 21 |
| 11 | 11, 12, 21 |
| 12 | 12, 21, 22 |
| 13 | 1, 13, 14, 21 |
| 14 | 13, 14, 15, 21 |
| 15 | 16, 21 |
| 16 | 16, 21 |
| 17 | 17, 18, 21 |
| 18 | 17, 18, 21 |
| 19 | 19, 21, 22 |
| 20 | 19, 21, 22 |
| 21 | 20, 21 |
| 22 | 3, 20, 21 |
| 23 | 1, 21, 22 |
| 24 | 21, 22 |
