# Design Document: 平台架构六项收敛

## 1. Overview

本设计把六项平台骨架问题收敛为四条可独立验证的装配链：

1. **渲染控制面**：component capability manifest → render wire schema → staged planner → renderer registry → DOM。
2. **启动控制面**：ordered startup registry → sequential executor → runtime report → health/readiness projection。
3. **治理控制面**：domain boundary manifest → AST/parser dependency graph → exact debt baseline → CI。
4. **事件控制面**：canonical envelope → EventBus/TaskEventBus adapters → transport-specific delivery/audit。

前端路由与 renderer registry 是装配层的两个投影：都采用“显式域数组 + 同步 barrel + 单点运行时装配”，不改变 route guard 顺序、chunk 边界或同步查表契约。

### Goals

- 把隐含在代码分支、集合和行序中的平台决策变成 machine-readable 声明。
- 给每条声明补真实消费链守卫，防止 additive 注入成为死代码。
- 在不改变业务行为的前提下拆分长协调器和启动链。
- 统一事件身份/因果/版本/幂等/审计字段，但不合并 transport。
- 让依赖边界在 CI 中拦新增债务，同时允许历史债务渐进归零。

### Non-goals

- 不改底稿业务字段、公式、四表取数、OnlyOffice 协议或审计方法论。
- 不引入 DAG 启动器、启动并行、自动重试或新第三方依赖。
- 不把 `wp_code_overrides.json` 扩成能力注册表。
- 不合并 EventBus 与 TaskEventBus，也不混用 procedure delivery outbox replay。
- 不拆成多个 Vue Router 全局 guard，不改变动态 import 字面量。
- 不新增数据库迁移；若实现调查证明 schema 缺列，必须先回 design 重新裁决。

## 2. Architecture

```text
wp_code/sheet ── overrides ─┐
backend renderer dispatch ──┼─> component-capability manifest ─> render planner
frontend domain entries ────┘             │                         │
                                           └─ contract guards ───────┤
render subject -> classify -> redirect -> facts -> plan -> materialize -> finalize
                                                                  │
                                                wire response -> registry -> DOM

startup task declarations -> sequential executor -> task results -> health report

domain ownership JSON -> source import graph -> policy evaluation -> exact debt diff

domain event -> CanonicalEventEnvelopeV1 -> in-process adapter / durable adapter
```

## 3. Key Decisions

### 3.1 能力与映射分权

`wp_code_overrides.json` 继续只回答“这个 wp/sheet 映射到什么 componentType”；新 manifest 回答“该 componentType 能做什么”。后端 renderer、前端组件、override 准入和 host 策略是四个正交维度，不允许压成 `supported=true`。
### 3.2 生成物与权威源

manifest 采用“声明性裁决 + 可重建投影”：componentType 条目由既有后端/前端注册源派生，owner、host policy、exemption 是人工裁决。生成器必须提供 `--check`，磁盘文件与重建结果不同即失败，不能在请求路径临时重建。

### 3.3 兼容优先拆分

`_get_render_config_impl` 先抽纯阶段，再切换入口；每一步都由真实响应 golden 锁住。阶段函数不重新解释业务规则，只搬运当前判据。裁决追踪是附加字段，先通过 schema/前端 reserved 机制接入，避免 Pydantic 绑定时意外裁字段。

### 3.4 启动顺序是公共契约

startup registry 使用有序 tuple，executor 串行执行。现有行序、critical/best-effort、skip 和 shutdown 语义是迁移基线；不会用“更聪明”的拓扑排序优化它。

### 3.5 exact baseline 只容纳历史债务

领域 checker 每次现算依赖图，与允许边界比较后得到 violations。baseline 存稳定 violation identity，不存全树快照；新增 violation 失败、已消失 violation 提示更新，不因仓库新增合规文件假红。

### 3.6 共享语义、不共享运输

`CanonicalEventEnvelopeV1` 是共享 wire/domain 模型。EventBus 仍负责进程内 fan-out；TaskEventBus 仍负责 DB delivery/retry。adapter 在边界转换，禁止两个 bus 相互代理形成递归或重复投递。

### 3.7 前端显式域装配

route 与 renderer 都由每个业务域导出显式数组，再由同步 barrel 汇总。域归属写在文件位置/entry metadata 中，不用 componentType 前缀推断。所有 SFC import 保持现有字面量。

## 4. Component Capability Manifest

建议权威文件：`backend/app/data/component_capabilities.json`；生成/校验器：`backend/scripts/check/check_component_capabilities.py`。前端通过生成的只读 TS 投影或构建期 JSON import 消费，不复制手写 union。

```json
{
  "schema_version": 1,
  "components": {
    "d-form-table": {
      "owner": "workpaper-rendering",
      "has_backend_renderer": true,
      "has_frontend_component": true,
      "override_allowed": true,
      "host_policy": "html",
      "status": "active",
      "sources": ["RENDERER_DISPATCH", "htmlRendererRegistry"]
    }
  },
  "exemptions": []
}
```

manifest checker 读取声明源时先剥离注释，再用 AST/JSON/TS parser 提取。它输出四向差集、重复声明、无消费 entry、过期 exemption。前端 registry barrel 在构造 `Map` **之前**检查 key collision。

## 5. Render Wire Contract

### 5.1 后端模型

`RenderConfigResponse` 作为 endpoint `response_model`，保留现有字段与 nullability；新增 `decision_trace` 前先纳入模型和前端 DTO。绑定前采集真实 DB 项目的代表性响应：HTML、OnlyOffice、confirmation、program console、redirect/multi-sheet 各至少一份。
### 5.2 前端 DTO

前端建立单一 `RenderConfigWire`，覆盖：

- identity：wp/project/year/sheet；
- renderer：componentType/schema/html_data/template_version；
- governance：guidance/applicable_standards/sign_status/permissions；
- linkage：cross_refs（`cell` 可空）；
- trace：decision_trace。

不再在 `useWpRenderer.ts` 内维护第二份 componentType union；类型由 capability 投影导出。reserved 字段必须显式列出并由消费检查追踪，避免字段“有类型但无人用”。

### 5.3 双向契约检查

后端模型导出字段路径与类型/nullability，前端检查器解析 `RenderConfigWire`，比较 `backend - frontend` 与 `frontend - backend` 两个差集。真实 golden 另锁运行时 payload，防止模型正确但 endpoint 未绑定/函数返回不同形态。

## 6. Render Planning Pipeline

新增邻近模块（最终命名以现有包结构为准）承载显式类型：

```python
@dataclass(frozen=True)
class RenderSubject: ...

@dataclass(frozen=True)
class ClassificationResolution: ...

@dataclass(frozen=True)
class RenderPlan:
    sheets: tuple[SheetPlan, ...]
    decisions: tuple[RenderDecision, ...]

@dataclass(frozen=True)
class RenderDecision:
    sheet_key: str
    chosen_component_type: str
    candidate_sources: tuple[str, ...]
    winning_source: str
    override_hit: bool
    redirect_applied: bool
    fallback_reason: str | None
```

入口仅编排七阶段：

1. `load_render_subject`
2. `resolve_classification_sources`
3. `resolve_scope_redirect`
4. `load_common_render_facts`
5. `plan_sheets`
6. `materialize_sheet`
7. `finalize_render_response`

每阶段只接收所需参数。现有 broad-catch 分支不得顺手“清理”；先忠实标成 decision/fallback，再由独立后续任务裁决是否改为 fail-fast。`/api/wp-classifications` 必须复用 `resolve_classification_sources`/`plan_sheets` 的公共裁决核，不能复制算法。

## 7. Mount Contract

测试装配真实 app/router/store 和真实 `htmlRendererRegistry`，输入真实 golden payload，挂载 `GtWpRenderer`，断言：

- manifest 声明的 componentType 被真实查到；
- 组件根节点和 sheet identity 出现在 DOM；
- 重复 key 在 Map 构建前失败；
- unknown/unsupported/error 三态有不同可见结果；
- 异常不会被伪装成 empty data。
## 8. Startup Registry and Runtime Report

```python
@dataclass(frozen=True)
class StartupTaskSpec:
    name: str
    phase: str
    criticality: Literal["critical", "best_effort"]
    run: Callable[..., Awaitable[None]]
    timeout_seconds: float | None = None
    skip_condition: Callable[[StartupContext], str | None] | None = None

@dataclass(frozen=True)
class StartupTaskResult:
    name: str
    phase: str
    status: Literal["ok", "skipped", "failed"]
    duration_ms: int
    detail: str | None
```

`STARTUP_TASKS` 是 tuple，顺序严格复刻现状。executor 对 critical 异常重新抛出，对 best-effort 记录失败继续；不会自动重试。worker 启动也展开为有名 task/result。运行报告保存在进程内只读 snapshot，由 `/api/health` 投影。

`/livez` 不读取报告并恒 200；`/readyz` 继续使用既有 draining → migration → PG/Redis 判据。运行报告只提供诊断，不参与 readiness，除非原逻辑本来参与。

## 9. Domain Boundary Governance

`docs/architecture/domain-boundaries.json` 结构：

```json
{
  "schema_version": 1,
  "domains": {
    "workpaper-rendering": {
      "owners": ["platform"],
      "paths": ["backend/app/routers/wp_render_*", "audit-platform/frontend/src/components/workpaper/**"],
      "may_depend_on": ["core", "four-table", "events"]
    }
  }
}
```

checker 流程：路径归域 → 提取 import → 解析内部模块目标 → 生成跨域边 → 对照 `may_depend_on` → 与 exact debt baseline 做集合差。未归域生产文件是独立 violation。测试用临时目录构造允许、禁止、未归属、债务新增、债务减少、循环依赖六类场景。

`gen_service_deps.py` 只保留可视化职责，默认输出改到 `docs/architecture/service-dependency.md`（或该目录内实际既有文档），不成为边界真源。

## 10. Canonical Event Envelope

```python
class CanonicalEventEnvelopeV1(BaseModel):
    envelope_version: Literal["1"] = "1"
    event_id: UUID
    event_type: str
    event_schema_version: int
    event_kind: str
    occurred_at: datetime
    project_id: UUID | None
    year: int | None
    data: dict[str, Any]
    producer: str
    trace_id: str
    correlation_id: str
    causation_id: str | None
    actor_id: UUID | None
    actor_role: str | None
    reason_code: str | None
    idempotency_key: str
    aggregate_type: str | None
    aggregate_id: str | None
    aggregate_version: int | None
```
构造器集中生成 event_id/time/trace/idempotency，调用方提供业务语义。`EventPayloadAdapter` 与 `TaskEventAdapter` 双向转换；转换后必须 round-trip 保持身份、因果和 payload digest。

TaskEventBus 使用 `idempotency_key` 等值查询/唯一语义，不再借 `trace_id LIKE`。若数据库当前已存在该列则直接接线；若不存在，本 spec 因 non-goal 不允许偷偷迁移，任务必须标 BLOCKED 并回 design。

procedure delivery outbox 与 generic task event 必须由现有可用的 kind/type 字段判别；若无法可靠区分，同样回 design，不用字符串猜测。`/task-events` 先做认证和项目 visibility，再查询/重放；actor 取服务端身份。

## 11. Frontend Assembly

### 11.1 Routes

建议结构：

```text
src/router/
  domains/{auth,projects,workpapers,reports,notes,system,...}.ts
  guards.ts
  index.ts
```

每个域导出 `RouteRecordRaw[]`，`index.ts` 同步展开并创建 router，再注册现有唯一 `beforeEach`。route projection 测试递归扁平化拆分前后 path/name/meta/parent chain，不能继续假设源文件只有一个 `children:`。

### 11.2 Renderer registry

建议结构：

```text
components/workpaper/registry/
  entries/{core,forms,programs,confirmations,reports,specialized}.ts
  index.ts
```

每个文件显式导出 `HtmlRendererEntry[]`。barrel 先拼数组、查重复 key，再构造只读 Map；`getRendererEntry()` 保持同步。现有 `startsWith()` classifier 删除，不留 fallback classifier。

## 12. Security, Errors and Observability

- 所有 API 先授权后取资源；replay actor 不信任请求体。
- decision/startup/event 日志只记录稳定 id、阶段、verdict、耗时和脱敏错误码。
- broad catch 若保留兼容 fail-open，必须把 ERROR/fallback 写入结构化 trace，不能只 warning。
- capability/route/registry/domain manifests 均有 schema version 和 digest。
- 真实 payload/evidence 文件不得包含 token、Cookie、连接串或客户敏感正文。

## 13. Rollout

1. 先落 manifest/checkers/schema 与红基线，不改运行路径。
2. 对齐 render DTO 并绑定 response model；golden 必须零差异。
3. 逐阶段抽 render planner，每抽一段重跑 golden。
4. 平移 lifespan 到 registry，先 shadow 记录执行序列，再切 executor。
5. 领域 checker 以 exact debt baseline 接 CI。
6. 事件先 adapter/双写兼容，再修确定缺陷；不删旧模型。
7. 最后拆 route/renderer 物理文件，投影等价后切 barrel。

回滚以层为单位：manifest/checker 可独立撤回；render planner 入口可切回旧协调器；startup executor 可切回旧 lifespan；事件 adapter 可停止双写；前端 barrel 可回指旧数组。任何回滚都不删除已写业务数据。

## 14. Testing Strategy

- **后端**：schema/golden、planner stage、startup sequence/report/probes、domain checker、envelope adapters/idempotency/auth。
- **前端**：wire DTO contract、真实 renderer mount、duplicate key、route projection、single guard、registry projection。
- **变异**：每条关键守卫有唯一锚点与预期测试名，四态记录并 finally 复原。
- **浏览器**：真实登录后打开至少 HTML/OnlyOffice/confirmation 三类底稿；验证 route 深链、未知 component error、health 报告；控制台 0 error。
- **辐射面**：通过引用搜索选择测试，不运行全部 1522 个后端测试文件。
## 15. Correctness Properties

### Property 1: component 能力四维声明可由现有真源重建且 mapping/能力不混权

**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2: component 任一方向漂移、豁免过期或注释伪命中都必定打红

**Validates: Requirements 1.4, 1.5, 1.6, 1.7**

### Property 3: response_model、真实 payload 与前端 DTO 的字段和 nullability 一致

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

### Property 4: render wire 双向差集为零且所有字段都有真实消费或 reserved 裁决

**Validates: Requirements 2.5, 2.6, 2.7**

### Property 5: 前置分类与最终 sheet plan 对同一身份给出同一 componentType 或显式差异

**Validates: Requirements 3.1, 3.2, 3.3**

### Property 6: manifest 声明的前端能力经真实 registry 后必能挂载为真实 DOM

**Validates: Requirements 3.4, 3.5, 3.6**

### Property 7: render 七阶段顺序、显式输入输出与重构前 payload 保持等价

**Validates: Requirements 4.1, 4.2, 4.3**

### Property 8: 每张 sheet 的 winner/fallback/redirect 可追溯且异常语义和并发改动不丢失

**Validates: Requirements 4.4, 4.5, 4.6, 4.7**

### Property 9: startup registry 的真实执行顺序和 criticality 与旧 lifespan 完全一致

**Validates: Requirements 5.1, 5.2, 5.3, 5.4**

### Property 10: 所有 worker 和 shutdown 步骤均有唯一登记且执行序列守卫可打红

**Validates: Requirements 5.5, 5.6, 5.7**

### Property 11: startup report 与 registry 一一对应并可由 health 查询

**Validates: Requirements 6.1, 6.2, 6.3**

### Property 12: livez/readyz 状态码优先级不变且诊断报告不泄密

**Validates: Requirements 6.4, 6.5, 6.6**
### Property 13: 领域 manifest、AST/parser 图与 exact baseline 只拦新增债务

**Validates: Requirements 7.1, 7.2, 7.3**

### Property 14: 未归属模块、checker 等价变异、错误文档路径和 CI 漂移都必定打红

**Validates: Requirements 7.4, 7.5, 7.6, 7.7**

### Property 15: 两类 bus 共享完整 envelope/adapter 但 transport 保持隔离

**Validates: Requirements 8.1, 8.2, 8.3**

### Property 16: envelope 必填、因果链、脱敏和兼容删除门在 round-trip 中守恒

**Validates: Requirements 8.4, 8.5, 8.6, 8.7**

### Property 17: TaskEvent 幂等按真实 idempotency_key 且 replay 不触碰 procedure outbox

**Validates: Requirements 9.1, 9.2, 9.3**

### Property 18: 所有事件调用签名有效且 task-events 授权/actor 来源不可伪造

**Validates: Requirements 9.4, 9.5, 9.6, 9.7**

### Property 19: route 域数组装配后 flattened route 与单一 guard 语义等价

**Validates: Requirements 10.1, 10.2, 10.3**

### Property 20: route 懒加载边界、唯一性和真实导航行为不因物理拆分改变

**Validates: Requirements 10.4, 10.5, 10.6**

### Property 21: renderer 显式域 arrays 汇总后同步查表与原 registry 等价

**Validates: Requirements 11.1, 11.2, 11.3**

### Property 22: renderer duplicate/unconsumed domain/lazy import 漂移均在 Map 前失败

**Validates: Requirements 11.4, 11.5, 11.6**

### Property 23: 并发脏文件不被覆盖且所有关键守卫经基线门和四态变异验证

**Validates: Requirements 12.1, 12.2, 12.3, 12.4**

### Property 24: typecheck/build/定向测试/Playwright/tracked 产物共同决定完成

**Validates: Requirements 12.5, 12.6, 12.7**
