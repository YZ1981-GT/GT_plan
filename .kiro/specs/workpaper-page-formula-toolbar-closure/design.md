# Design Document

## Overview

本设计将 workpaper route 收敛为一个 runtime owner：

```text
Host facts + G-ID
       ↓
WorkpaperCapabilityShell
  ├─ CanonicalLocationState reducer
  ├─ CapabilitySnapshot gate
  ├─ ToolbarOutletRegistry → ToolbarArbiter → FormulaManager command
  ├─ FormulaProviderRegistry → AggregateResult
  ├─ AI review actions / DSH AI-assist adapter
  ├─ HumanReviewProvider
  └─ RightRailArbiter(review → guidance → ai)
```

共享 wire 类型全部 import 自 `G-C0`；本设计不重述 `CanonicalWorkpaperLocation`、`GuidanceRailAdapter` 或 `EvidenceEnvelope` 字段。`G-ID` 提供 stable template/sheet identity，`G-RAIL` 提供 guidance adapter。`F-SHELL` 是经行为守卫验证后交付 custom 的公共壳层能力。

## 1. Scope and Ownership

唯一性范围是 `/workpapers/...` active workpaper route。TB/report/note 等 domain route 的专用 formula dialog 不纳入重复清理。

| Concern | Owner |
|---|---|
| C0 wire contract、G-ID、GuidanceRailAdapter | guidance spec |
| runtime location state/reducer/provider | 本 spec `WorkpaperCapabilityShell` |
| toolbar named outlets 与 placement | 本 spec |
| workpaper page FormulaManager command/dialog owner | 本 spec |
| provider aggregation / user formula v2 | 本 spec |
| review/guidance/AI rail DOM/CSS | 本 spec |
| custom workbook parsing/sync | custom spec（只消费 F-SHELL） |

## 2. Host Capability Inventory

```ts
interface WorkpaperHostCapabilityRecord {
  inventoryVersion: string
  entryId: string
  componentType: string
  routeScope: 'workpaper' | 'domain-owned'
  host: 'html' | 'univer' | 'onlyoffice' | 'grid' | 'word'
  locationGranularity: 'page' | 'sheet' | 'section' | 'cell' | 'document' | 'whole_workbook'
  primaryOutlet: 'supported' | 'unsupported' | 'pending'
  compatibilityOutlet: 'supported' | 'unsupported' | 'pending'
  formulaProviders: string[]
  aiReview: boolean
  aiAssist: boolean
  humanReview: boolean
  guidanceRail: boolean
  reason: string | null
  sourceDigest: string
}
```

Inventory 合并 renderer registry、render-config、实际 adapter registration telemetry 与 runtime custom entries。它输出 evidence projection，不作为第二 dispatch 真源。Domain-owned route 只记录 exclusion evidence。

## 3. CanonicalLocationState Runtime

共享 ready snapshot 来自 C0；本 spec 只定义 runtime 状态：

```ts
type CanonicalLocationState =
  | { status: 'uninitialized'; ownerEpoch: number }
  | { status: 'blocked'; ownerEpoch: number; reasonCode: string; detail: string }
  | { status: 'ready'; ownerEpoch: number; contextRevision: number; location: CanonicalWorkpaperLocation }
```

状态机：

```text
route enter → uninitialized(epoch N)
  → capability + base context valid → ready(epoch N, revision 1)
  → host fact changes → ready(epoch N, revision + 1)
  → invalid identity/capability → blocked(epoch N)
route owner/wp change → uninitialized(epoch N + 1)
```

Host adapter 只 dispatch `activateWorkpaper/activateSheet/activateSection/activateCell/activateDocument/activateWholeWorkbook` facts。Reducer 校验 G-ID、membership 和 stable locator，再发布 immutable snapshot。任何其他 store 不得自称 owner。

异步落地门固定为：

```text
same canonical subject identity
∧ same ownerEpoch
∧ same contextRevision
∧ capability snapshot still valid
```

## 4. Capability Gate

```ts
interface WorkpaperCapabilitySnapshot {
  snapshotVersion: string
  subjectDigest: string
  ownerEpoch: number
  expiresAt: string
  formulaView: CapabilityDecision
  formulaEditUser: CapabilityDecision
  formulaHistory: CapabilityDecision
  aiReviewPage: CapabilityDecision
  aiReviewBatch: CapabilityDecision
  aiAssistChat: CapabilityDecision
  humanReviewRead: CapabilityDecision
  humanReviewWrite: CapabilityDecision
  guidanceRead: CapabilityDecision
}

interface CapabilityDecision {
  allowed: boolean
  reasonCode: string | null
  owner: string | null
  nextAction: string | null
}
```

Shell 在 provider/command/action 前检查 snapshot；endpoint 再做权威验证。Capability refresh 可关闭、降级或重新加载已打开能力。

## 5. Real Toolbar Outlets

`.gt-wp-toolbar__right` 只是 CSS class。实现必须新增真实 named slot，例如：

```vue
<!-- primary toolbar: 插入位置固定在 AI助手后、金额单位前 -->
<slot name="page-capabilities-primary" />

<!-- GtWpToolbar compatibility host 的右侧真实 slot -->
<slot name="page-capabilities-compatibility" />
```

具体 slot 名可在实现前冻结一次，但 contract/挂载测试与组件模板必须一致，禁止伪写 `GtWpToolbar.__right`。

### 5.1 Registration protocol

```ts
type ToolbarOutletKind = 'primary' | 'compatibility'

interface ToolbarOutletRegistration {
  registrationId: string
  hostInstanceId: string
  ownerEpoch: number
  kind: ToolbarOutletKind
  outletElement: HTMLElement
  mountedAt: number
  leaseToken: string
}

type ToolbarPlacementState =
  | { status: 'pending'; ownerEpoch: number }
  | { status: 'registered'; selected: ToolbarOutletRegistration }
  | { status: 'blocked'; reasonCode: string }
```

Host render cycle 结束前保持 pending；primary 注册优先。只有 primary 明确 unavailable 后 compatibility 才可 selected。Unmount/epoch change 撤销 lease。跨 epoch、重复 kind 或多个 active primary 是 collision。

按钮可通过 shell-controlled Teleport/portal 进入 selected outlet，但 owner 仍是 shell。DOM 行为守卫验证顺序、可见性和唯一性。

## 6. Formula Manager Command and Draft Pin

页面入口调用 shell command，而不是业务 EventBus：

```ts
interface OpenFormulaManagerCommand {
  commandVersion: '2.0'
  location: CanonicalWorkpaperLocation
  capabilitySnapshotVersion: string
  ownerEpoch: number
  contextRevision: number
  legacyNodeKey?: string
}
```

`ThreeColumnLayout` 保持 workpaper route 唯一 `FormulaManagerDialog` owner。单元格 `FormulaEditDialog` 只由管理器对 editable user formula 下钻。

Dialog session：

```ts
interface FormulaManagerSession {
  openedAtLocation: CanonicalWorkpaperLocation
  pinnedLocation: CanonicalWorkpaperLocation
  dirty: boolean
  followLatestWhenClean: boolean
}
```

- clean + location change：跟随 latest；
- dirty + location change：保持 pinned，显示 banner；保存仍使用 pinned location 并重验 capability/base version；
- discard 后可切 latest；
- route owner 失效时不可保存，只允许导出/丢弃草稿。

## 7. Orthogonal Formula Descriptor

```ts
type FormulaOrigin = 'platform' | 'user' | 'runtime_generated'
type FormulaRuleKind = 'data_fetch' | 'calculation' | 'logic_check' | 'reasonableness' | 'presentation'
type FormulaEngine = 'backend_formula' | 'user_formula_store' | 'auto_data_resolver' | 'frontend_formula_engine'
type FormulaProtection = 'editable' | 'protected' | 'system_managed'

interface FormulaDescriptor {
  descriptorVersion: '2.0'
  formulaId: string
  semanticDigest: string
  origin: FormulaOrigin
  ruleKind: FormulaRuleKind
  engine: FormulaEngine
  protection: FormulaProtection
  location: CanonicalWorkpaperLocation
  target: { addrId: string | null; fieldKey: string | null; rowKey: string | null; columnKey: string | null; a1: string | null }
  formulaFunction: string | null
  ruleCategory: string
  expression: string | null
  ruleSummary: string
  refs: string[]
  currentValue: unknown
  valueStatus: 'resolved' | 'error' | 'unavailable' | 'stale'
  calculatedAt: string | null
  contextFingerprint: string
  manualOverride: boolean
  version: string
  owner: string
  protectionReason: string | null
  updatedBy: string | null
  updatedAt: string | null
  provenance: { providerId: string; sourceDigest: string }
}
```

### 7.1 Truth-source matrix

| Existing class | origin | ruleKind | engine | protection |
|---|---|---|---|---|
| platform formula | platform | data_fetch/calculation/presentation | backend_formula | protected |
| user formula | user | data_fetch/calculation | user_formula_store | editable（capability 后） |
| auto_data_source | runtime_generated | data_fetch | auto_data_resolver | system_managed |
| logic/reasonableness check | platform/runtime_generated | logic_check/reasonableness | backend_formula 或 frontend_formula_engine | protected/system_managed |
| frontend formula engine | platform/user/runtime_generated（按真源） | calculation/presentation | frontend_formula_engine | 按 owner 裁决 |

Adapter 不改变权威存储，只投影 descriptor。

### 7.2 AggregateResult

```ts
interface FormulaAggregateResult {
  status: 'complete' | 'partial' | 'blocked'
  location: CanonicalWorkpaperLocation
  descriptors: FormulaDescriptor[]
  providerResults: Array<{ providerId: string; verdict: 'ok' | 'unsupported' | 'error' | 'timeout'; reason: string | null }>
  collisions: Array<{ formulaId: string; providerIds: string[]; semanticDigests: string[] }>
  generatedAt: string
}
```

相同 id 只有 semantic digest 相同才可合并 provenance；不同 digest 使 aggregate 至少 partial/blocked。Provider 支持的粒度由 `supports(location.anchor.kind)` 明确声明。

## 8. Value and Lineage Enrichment

聚合后批量查询 ACNR/linkage bus，追加 upstream/downstream/cross-reference/stale。查询失败保留 descriptor 并标 partial。项目年度、准则、dataset、target/source digest 共同组成 context fingerprint；任一变化使值/evidence stale。

## 9. User Formula API v2

旧 `dict[cell_key, formula]` route 只保留明确迁移期，不承载 v2。建议资源：

```text
GET  /api/workpapers/{wpId}/user-formulas/v2?location=...
POST /api/workpapers/{wpId}/user-formulas/v2:batchMutate
GET  /api/workpapers/{wpId}/user-formulas/v2/{formulaId}/history
```

### 9.1 Command

```ts
interface UserFormulaCommand {
  commandVersion: '2.0'
  operationId: string
  action: 'create' | 'update' | 'delete' | 'restore'
  formulaId: string | null
  location: CanonicalWorkpaperLocation
  target: FormulaDescriptor['target']
  formulaFunction: string | null
  ruleCategory: 'auto_calc' | 'logic_check' | 'reasonability' | string
  expression: string | null
  refs: string[]
  baseVersion: string | null
  reason: string
}
```

`formulaFunction` 与 `ruleCategory` 永不共用字段。

### 9.2 Result

```ts
interface UserFormulaBatchResult {
  overallStatus: 'success' | 'partial' | 'failed'
  operationId: string
  items: Array<{
    clientItemId: string
    status: 'success' | 'conflict' | 'forbidden' | 'invalid' | 'error'
    formulaId: string | null
    serverVersion: string | null
    fieldConflicts: Array<{ field: string; base: unknown; current: unknown; incoming: unknown }>
    errorCode: string | null
  }>
}
```

每项独立版本与结果。Audit/outbox 是 commit gate：同一事务写 version + audit/outbox，或在 durable outbox 成功后提交；失败回滚并返回 error。恢复创建新 immutable version。

## 10. AI Taxonomy

```text
AI review:  ai_review_page / ai_review_batch
AI assist:  ai_assist_chat
Human:     human_review_thread
Lifecycle: submit_for_lifecycle_review
```

公共 AI review toolbar 只发 review actions；DSH rail 只承载 assist chat。Scope 绑定 ready location/selection + owner/capability epoch。按 inventory 成组删除业务重复按钮、refs、handlers、ReviewPanel 与 bare mounts。

## 11. Human Review Threads

Canonical key：

```text
projectId / wpId / (sheetUid | whole-workbook) / anchorId
```

`anchorId` 来源 stable section/addr/row-column/document/page anchor。Legacy migration：scan → deterministic mapping → collision/orphan report → dry-run → idempotent apply → rollback evidence。冲突不自动合并。

Provider 对 create/reply/resolve/reopen/read 分能力校验。Shell 只挂一份 `GtWpReviewRail`。

## 12. WorkpaperCapabilityShell and Rails

Shell 组合：

```text
review adapter order 10
guidance adapter order 20   (import G-RAIL)
ai-assist adapter order 30
```

`RightRailArbiter` 只允许一个 open id。Visible=false、epoch stale 或 capability denied 的 adapter 不进入 DOM、不占 slot。切换调用 close({preserveDraft:true})。

所有 trigger DOM、gap、top/right/z-index、panel width、content inset、focus/scroll 和 responsive CSS 都属于 shell。Guidance/custom 不写偏移。

## 13. Responsive and Accessibility

- 1280/1440/1920 与 200% text zoom 使用同一 shell token/layout 算法；
- outlets、dialog、rails 具备中文 accessible name、focus-visible、Escape、return focus、scroll lock；
- modal/rail 不形成双 focus trap；
- Word 作为 inventory host：可达即纳入 mounted/Playwright；不可达需有期 exemption，仍在 denominator 中单列。

## 14. Error, Audit and Security

所有 query/mutation/action 先 capability gate，后端再验证 visibility/membership。Error model 含 canonical subject、operation/provider、correlation、epoch/version 和 safe reason。日志不记录 token、完整表达式或附件正文。

禁止 broad catch + success；禁止 audit warning + commit；禁止 provider error → empty success。

## 15. Migration Sequence

1. 消费 `G-C0`，建立 scope inventory 与红守卫；
2. 前置 capability snapshot；
3. 消费 `G-ID`，上线唯一 location state/reducer；
4. 给 primary toolbar 与 `GtWpToolbar` 增真实 named outlets 和 registration protocol；
5. 接唯一 dialog，落 dirty draft pin；
6. 上线正交 provider descriptors/AggregateResult；
7. 上线 user formula API v2 + durable audit；
8. 去重 AI，迁移 review keys；
9. 消费 `G-RAIL`，由 shell 接管 rail DOM/CSS；
10. 删除旧 event/bare mount/fixed offset；
11. 行为/变异通过后发布 `F-SHELL`；
12. 五宿主/三 viewport Playwright 后 closure。

回退开关不得恢复重复 dialog、串 location、旧 dict LWW 或未审计 commit。

## 16. Correctness Properties

### Property 1: host inventory 由真实 mounted capability 推导且 scope 不误伤 domain dialogs
**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**

### Property 2: C0/G-ID 只被 import，runtime location 只有一个 owner
**Validates: Requirements 2.1, 2.2, 2.4**

### Property 3: ownerEpoch/contextRevision 单调且旧结果永不落新位置
**Validates: Requirements 2.3, 2.5, 2.6**

### Property 4: capability 未 ready/过期/拒绝时所有公共动作 fail-closed
**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

### Property 5: 每个 active workpaper 恰有一个真实 mounted 公式入口或明确 blocked
**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6**

### Property 6: 页面入口只打开 workpaper route 唯一全局管理器
**Validates: Requirements 5.1, 5.2, 5.3, 5.6**

### Property 7: dirty draft 永远保存到 pinned location
**Validates: Requirements 5.4, 5.5**

### Property 8: provider 四维 descriptor 与五类真源映射一致
**Validates: Requirements 6.1, 6.2, 6.3**

### Property 9: collision/partial/unsupported 在 AggregateResult 中守恒
**Validates: Requirements 6.4, 6.5, 6.6**

### Property 10: 值、lineage、保护与 stale 与当前真源一致
**Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5**

### Property 11: v2 mutation 逐项版本化且函数/分类不混用
**Validates: Requirements 8.1, 8.2, 8.3, 8.4**

### Property 12: conflict/partial 不丢草稿，审计失败不提交
**Validates: Requirements 8.5, 8.6, 8.7**

### Property 13: AI review/assist/human/lifecycle taxonomy 与承载链互斥
**Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5**

### Property 14: review thread canonical key 稳定且 migration 不丢/不串
**Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 10.6**

### Property 15: shell 是 toolbar/dialog/location/rail DOM/CSS 唯一 owner
**Validates: Requirements 11.1, 11.2, 11.3, 11.5, 11.6**

### Property 16: rail 同时最多一个展开且不可见项不占位
**Validates: Requirements 11.4**

### Property 17: shell 在三 viewport、缩放与键盘路径可用
**Validates: Requirements 12.1, 12.2, 12.5**

### Property 18: 错误可见且 observability 不泄漏敏感内容
**Validates: Requirements 12.3, 12.4**

### Property 19: 外部里程碑拓扑显式且 `F-SHELL` 可供 custom conformance
**Validates: Requirements 13.1**

### Property 20: 自动化和变异覆盖真实消费链
**Validates: Requirements 13.2, 13.3**

### Property 21: 所有 reachable host 的浏览器证据绑定真实 location/capability
**Validates: Requirements 13.4, 13.5**

### Property 22: 只有清册、API、权限、审计、tracked evidence 全闭环才可归档
**Validates: Requirements 13.6**

## 17. Testing Strategy

| 层 | 重点 |
|---|---|
| Contract | import-only C0/G-ID/G-RAIL、major compatibility、F-SHELL conformance |
| Inventory | route scope、mounted outlet、domain exclusions、stale placement |
| Runtime state | uninitialized/blocked/ready、epoch/revision、host facts、race gate |
| Capability | ready/expiry/revalidate、前后端权限、no-leak |
| Toolbar | named slot、registration lease、pending→primary/fallback、collision、DOM order |
| Dialog | unique owner、FormulaEdit distinction、clean follow/dirty pin、empty state |
| Providers | 四维 matrix、五类 adapters、collision、partial、lineage/stale |
| User API | v2 commands、field conflict、partial、history/restore、audit rollback |
| AI/review | taxonomy、dedupe、scope、thread migration/capabilities/durability |
| Shell | G-RAIL、single-open、visibility、focus/scroll/responsive |
| Mutation | 单点破坏且精确 RED，区分 GREEN/ANCHOR-MISS/WRONG-TEST |
| Playwright | HTML/Univer/OnlyOffice/Grid/Word、三 viewport、权限、network/trace/console |

字符串存在、CSS class、接口 200、按钮可点或历史 passed 数都不是完成证据。

## 18. 页面实际接线补验

Renderer 复用 render-config/preparationYear 五字段，经 typed EventBus 到 Layout 唯一弹窗快照；全局入口清旧快照。Dialog 声明 wpId/wpCode/sheetName，页面入口优先于 legacy nodeKey，默认全册聚合 wpFormula.list(wpId) 的 items/surfaced/extraction，不再 code 反查。来源 sheetName 只展示。主查询、用户查询使用请求序号和身份快照，关闭/重开/换身份失效旧返回；错误与空结果区分。用户确认操作固定原 wpId 并复验位置。本次不扩大旧用户 API 的版本迁移范围，R8 历史验收不作为本次通过证据。

### Property 23: 页面入口真实身份与全册一致
**Validates: Requirements 14.1, 14.2, 14.3**

### Property 24: 错误可见、过期查询与操作不串底稿
**Validates: Requirements 14.4, 14.5, 14.6**

## 19. 文件行数债务（FormulaManagerDialog.vue）

`audit-platform/frontend/src/components/formula/FormulaManagerDialog.vue` 是 workpaper route 唯一的 FormulaManagerDialog 宿主（R5.1 要求唯一 owner，不允许业务组件挂第二份 dialog）。行数门禁实测（`backend/scripts/check/check_file_size.py`，口径 `read_text().splitlines()`）：

| 版本 | 行数 | 门限 |
|---|---|---|
| 交付前（HEAD） | 2875 | 1500（已超） |
| 本次交付后 | 3985 | 1500（已超） |

本次 +1110 行的构成：项目级/模板级层级标签与来源提示、公式看板的域/层级/分类健康度分组与筛选、全局作用域总览的 7 域全列与空态引导、项目级 ↔ 主模板差异面板（复用既有 `report_config_baseline` 三端点）、模板引用撤销、以及请求会话隔离（`dialogSession` + 请求序号，防切换底稿后旧响应覆盖新结果）。

**处置：登记 whitelist 真实基线 3985，不使用 `--no-verify`。** 白名单语义是「豁免超限、但仍拦膨胀（>基线 5%）」，因此这不等于债务已解决。

**拆分方向（独立任务，不在本 spec 范围）**：按关注点抽伴生模块 —— ① 公式看板（dashboard 分组/筛选/定位）② 全局作用域总览 + 主模板差异 ③ 用户公式 v2 面板 ④ 变更历史与回滚。拆分时必须保持「唯一 dialog owner」与 `dialogSession` 身份隔离语义不变；拆完从 whitelist 移除。

🔴 不拆的硬约束：依赖可 monkeypatch 符号或共享 `dialogSession` 闭包的 handler 不能搬走（搬走后会读伴生模块的全局名，导致既有守卫替身失效）——与仓库既往 `custom_query.py` 登记时记录的同型约束一致。
