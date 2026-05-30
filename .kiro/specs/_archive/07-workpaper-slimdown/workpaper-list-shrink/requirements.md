# Requirements Document — workpaper-list-shrink

## Introduction

`audit-platform/frontend/src/views/WorkpaperList.vue` 当前 **3463 行**，是审计平台底稿模块的入口视图（route name=`WorkpaperList`），承担 7 种子视图模式（list / kanban / workbench / lifecycle / graph / matrix / guide）的全部 reactive 状态、数据加载、Tab 切换、拖拽、依赖图、委派矩阵渲染。

- god component 风险：

- 触发 Vue setup const 顺序铁律（V3 spec 已 2 次踩点）
- 7 视图 reactive 状态纠缠，单点修改回归面失控
- 首屏 bundle 拖累（无 lazy import / 无 keep-alive）
- vitest 覆盖断层（单文件无法独立 mount Tab 子区域）
- 是底稿模块用户每天进入的第一个视图，体感即产品形象

本 spec 范围严格锁定：仅做结构性瘦身（拆 5 子 SFC + 1 shell），不动业务逻辑，不动后端，不动路由 children，保留 `name: 'WorkpaperList'` 路由名向后兼容（router/index.ts:105），保留 `?view=` query 切换约定（router/index.ts:120 已有 `query: { view: 'workbench' }` 重定向；当前实现见 WorkpaperList.vue 实测 7 viewMode 白名单 `['list','kanban','workbench','lifecycle','graph','matrix','guide']`，详见 design §1.2）。

## 元数据

- **Spec 类型**：feature（重构性 P0）
- **关联文档**：design.md / tasks.md（README stub 已于 2026-05-28 三件套就绪后删除，避免双源；详见 Req 9.1）
- **工时**：1 周（5 工作日）
- **依赖 spec**：`global-refinement-v3`（CI vue-tsc 0 / vitest 0 baseline）、`html-renderer-registry`（lazy 注册模式可借鉴）、`cycle-editor-generic`（generic composable 抽离模式）
- **同类未列入治理（本 spec 不动，预声明未来路线）**：
  - `LedgerPenetration.vue` 3794 行（最大！P0，独立 spec）
  - `TrialBalance.vue` 2766 行（P1）
  - `DisclosureEditor.vue` 2603 行（P1）
  - `ReportView.vue` 2538 行（P1）
  - `GtCNoteTable.vue` 1608 / `GtDFormReview.vue` 1670 / `GtDFormConfirmation.vue` 1434（已有 stub `gt-c-note-table-shrink/`）
- **CI 防退化**：本 spec 完成后扩展 `frontend-build` job baseline，`WorkpaperList.vue ≤ 1000` only-decrease（与 WorkpaperEditor 同模式）+ 5 个新 SFC `≤ 700` only-decrease


## Glossary

- **WorkpaperList**：底稿模块入口视图当前组件名，路由 `/projects/:projectId/workpapers`，本 spec 拆分后保留为 shell 容器
- **Shell**：拆分后的容器组件（即重构后的 WorkpaperList.vue），仅承担路由 + Tab 切换 + 共享 store 注入 + lazy 加载子 SFC，不持有业务 reactive state
- **子 SFC**：拆出的 5 个职责单一组件（Lifecycle / Board / DelegationMatrix / DependencyGraph / Workbench）
- **viewMode**：当前路由 `?view=` query 控制的子视图标识，**7 个枚举值** `list | kanban | workbench | lifecycle | graph | matrix | guide`（其中 `list` / `workbench` / `guide` 都映射到 Workbench 子 SFC，本 spec 收敛为 5 子 SFC；详见 design §1.2 实测）
- **Lifecycle 视图**：底稿生命周期推进视图（A→B→C→已完成），对应 `?view=lifecycle`
- **Board 视图**：看板拖拽视图，对应 `?view=kanban`
- **DelegationMatrix 视图**：委派矩阵（成员 × 底稿 × 复核层级），对应 `?view=matrix`
- **DependencyGraph 视图**：底稿依赖图（D3 force-graph），对应 `?view=graph`
- **Workbench 视图**：工作台 + 列表（默认入口），对应 `?view=workbench` 或 `?view=list` 或缺省
- **共享 composable**：从 WorkpaperList.vue 抽出的 reactive state hook（`useWorkpaperListContext`），所有子 SFC 通过 `inject` 或显式 props 共享，不允许子 SFC 自行重建数据源
- **route name 兼容**：保留 `name: 'WorkpaperList'` + `path: 'projects/:projectId/workpapers'` 路由不变，shell 替换 component 引用
- **only-decrease baseline**：CI 卡点形式，文件行数只能减少不能增加（V3 spec WorkpaperEditor 同模式）
- **god component**：≥ 1500 行单文件 SFC（memory 铁律），本 spec 触发阈值 = 3463 行


## Requirements

### Requirement 1 — Shell 容器与路由兼容

**User Story**：作为 5 类用户（admin / partner / manager / auditor / qc），我希望书签和深链（`/projects/:id/workpapers?view=lifecycle` 等）在重构后仍能直达对应子视图，且用户感知不到任何变化。

#### Acceptance Criteria

1. THE Shell SHALL 替换 `audit-platform/frontend/src/views/WorkpaperList.vue` 当前文件，文件名维持 `WorkpaperList.vue`（仅内部内容替换为容器实现）以保证路由 component import 路径不变
2. THE Shell SHALL 在小于等于 1000 行内完成路由 query 解析、子 SFC 切换、共享 store 注入、首屏 loading 守卫
3. WHEN 路由进入 `/projects/:projectId/workpapers`，THE Shell SHALL 读取 `route.query.view`，按白名单 `['list','kanban','workbench','lifecycle','graph','matrix','guide']` 校验后选择对应子 SFC 渲染
4. WHEN `route.query.view` 缺省或非法，THE Shell SHALL 回退渲染 `workbench` 子视图
5. WHEN `route.query.view` 在 7 枚举值之间切换，THE Shell SHALL 保留项目级 store 数据（projectStore / wpStore 等），仅切换子 SFC 渲染节点
6. THE Shell SHALL 保留 `name: 'WorkpaperList'` 路由名，且 `WorkpaperWorkbench` 路由的 `redirect` 链路（router/index.ts:117 `query: { view: 'workbench' }`）SHALL 在重构后仍正确命中 Workbench 子 SFC
7. IF 用户深链命中已废弃 viewMode（白名单外），THEN THE Shell SHALL 通过 `logger.warn` 输出一次警告并 `router.replace` 到 `?view=workbench`，不抛错不白屏
8. THE Shell SHALL 通过 `<keep-alive>` 缓存 5 子 SFC 实例，在 `viewMode` 切换回已访问过的子视图时复用实例（避免重复 mount 引起的数据闪烁）


### Requirement 2 — 5 子 SFC 边界与文件行数约束

**User Story**：作为开发者，我希望每个子 SFC 职责单一、可独立 vitest mount、单文件不超过 700 行，让后续维护和性能优化能精准定位。

#### Acceptance Criteria

1. THE Lifecycle_View SHALL 抽出至 `audit-platform/frontend/src/views/workpaper-list/WorkpaperLifecycleView.vue`，仅承担生命周期推进 UI 与对应数据 fetch
2. THE Board_View SHALL 抽出至 `audit-platform/frontend/src/views/workpaper-list/WorkpaperBoardView.vue`，仅承担看板拖拽与状态切换 UI
3. THE DelegationMatrix_View SHALL 抽出至 `audit-platform/frontend/src/views/workpaper-list/WorkpaperDelegationMatrix.vue`，仅承担委派矩阵 UI（成员 × 底稿 × 复核层级三维渲染）
4. THE DependencyGraph_View SHALL 抽出至 `audit-platform/frontend/src/views/workpaper-list/WorkpaperDependencyGraph.vue`，仅承担依赖图渲染（D3 force-graph 隔离在该 SFC 内 lazy import，不污染 Shell bundle）
5. THE Workbench_View SHALL 抽出至 `audit-platform/frontend/src/views/workpaper-list/WorkpaperWorkbenchView.vue`，承担工作台与列表 UI（含分页 / 搜索 / 批量）
6. THE Shell SHALL 满足 `wc -l audit-platform/frontend/src/views/WorkpaperList.vue` 小于等于 1000
7. EACH 子 SFC SHALL 满足 `wc -l` 小于等于 700（5 文件独立断言）
8. THE 5 子 SFC SHALL 通过 `defineAsyncComponent(() => import('./workpaper-list/...'))` lazy 加载，首屏只下载当前 viewMode 对应 chunk

### Requirement 3 — 子 SFC 对外契约（props / emits / 共享 composable）

**User Story**：作为开发者，我希望子 SFC 与 Shell 的数据流向显式声明，避免隐式 inject 链断裂或循环依赖。

#### Acceptance Criteria

1. EACH 子 SFC SHALL 通过 `defineProps` 显式声明所需 props（至少包含 `projectId: string` 与 `year: number`），不允许直接调用 `useRoute().params`
2. EACH 子 SFC SHALL 通过 `defineEmits` 显式声明对外事件，至少包含 `'navigate'`（穿透至 WorkpaperEditor）与 `'refresh'`（请求 Shell 刷新共享数据）
3. THE Shell SHALL 通过 composable `useWorkpaperListContext()`（新建于 `audit-platform/frontend/src/composables/useWorkpaperListContext.ts`）暴露共享 reactive state（底稿列表 / 加载状态 / 筛选条件 / 选中集），子 SFC 通过 `inject` 或 `useWorkpaperListContext()` 调用获取
4. THE useWorkpaperListContext SHALL 是 Shell 范围 `provide` / `inject` 单例，子 SFC 重复调用 SHALL 返回同一引用（不重复 fetch）
5. WHERE 子 SFC 需要触发后端写操作（拖拽改状态 / 矩阵改委派），THE 子 SFC SHALL 通过 emit `'mutate'` 通知 Shell，由 Shell 统一调用 service 层并触发 EventBus（不允许子 SFC 直接调 service）
6. IF 子 SFC 的 props 未提供必需字段（projectId 或 year），THEN THE 子 SFC SHALL 在 onMounted 抛 `ReferenceError` 中止渲染（不静默 fallback，避免 god component 时代的 reactive 错乱再现）


### Requirement 4 — 用户角色覆盖

**User Story**：作为不同角色用户（auditor / manager / partner / qc / admin），我希望进入 WorkpaperList 时看到符合自己权限的子视图与按钮组，且重构不破坏现有角色分支。

> **角色枚举源**：后端 `UserRole` enum（`backend/app/models/base.py:16`）= `admin / partner / manager / auditor / qc / readonly` 共 6 个；前端 `ROLE_PERMISSIONS`（`composables/usePermission.ts:76`）= `partner / manager / auditor / eqcr`，admin 走 `role === 'admin'` 硬判断绕过字典。`reviewer` **不是独立角色**，是 `ProjectUser.permission_level = 'review'` 项目级权限，不影响 Tab 可见性。详见 design §1.3。

#### Acceptance Criteria

1. WHEN 角色为 `admin`，THE Shell SHALL 渲染全部 5 子 SFC 的 Tab 入口
2. WHEN 角色为 `partner` 或 `manager`，THE Shell SHALL 渲染 Workbench / Lifecycle / Board / DependencyGraph / DelegationMatrix 全部 5 Tab
3. WHEN 角色为 `auditor`（审计助理），THE Shell SHALL 隐藏 DelegationMatrix Tab（保留其余 4 Tab）
4. WHEN 角色为 `auditor` 且深链命中 `?view=matrix`，THE Shell SHALL 通过 `router.replace` 跳转到 `?view=workbench`
5. WHEN 角色为 `qc`（质控），THE Shell SHALL 渲染与 `auditor` 相同的 4 Tab（Workbench / Lifecycle / Board / DependencyGraph），DelegationMatrix 隐藏
6. THE Workbench_View SHALL 对所有 5 角色可见，且批量操作按钮组按 `useRoleViewPreset` 既有逻辑差异化展示（不在本 spec 改动 preset 内容）
7. THE Lifecycle_View 内的「推进至下阶段」按钮 SHALL 按现有 `canEdit` 与 `signature_level` 逻辑保留（V3 spec 已治理，不重做）
8. THE 项目级 `permission_level = 'review'`（"复核人"语义）SHALL 不影响 Tab 可见性，仅影响 Workbench / Lifecycle 内部按钮可点性（既有逻辑保留）

### Requirement 5 — 路由与深链兼容性（书签不破）

**User Story**：作为已使用半年的产品用户，我希望浏览器里的旧书签（`/projects/abc/workpapers?view=kanban` 等）在升级后第一次点击仍能直达，不需要重新收藏。

#### Acceptance Criteria

1. THE Shell SHALL 接受 7 个历史 viewMode 字符串（`list | kanban | workbench | lifecycle | graph | matrix | guide`）并映射至 5 子 SFC
2. THE Shell SHALL 把 `list` / `workbench` / `guide` 都映射到 `WorkpaperWorkbenchView.vue`（详见 design §2.2 路由表 + ADR-2 收敛理由）
3. WHEN 用户从 `WorkpaperEditor` 通过 Backspace 返回（DefaultLayout `initGlobalBackspace`），THE Shell SHALL 恢复用户离开时的 `?view=` 参数，不重置为默认 `workbench`
4. THE Shell SHALL 维持 `WorkpaperWorkbench` 路由 redirect 链路（router/index.ts:113-122），第二跳到 `WorkpaperList` 加 `query: { view: 'workbench' }` 时正确命中 Workbench 子 SFC
5. WHEN `?view=` 任意切换，THE Shell SHALL 通过 `router.replace`（非 `router.push`）更新 URL，避免污染浏览器 history 栈
6. IF 路由 `params.projectId` 缺失或非合法 UUID，THEN THE Shell SHALL 通过现有 `useWpDetailGuard` 与 `useAuditContext` 异常路径处理（不在本 spec 重做）


### Requirement 6 — 测试可观察性

**User Story**：作为质控人员，我希望每个子 SFC 都能独立单测、且 Playwright e2e 覆盖 5 视图主要交互，重构后回归面可证。

#### Acceptance Criteria

1. EACH 子 SFC SHALL 至少有 1 个 vitest spec 文件（`audit-platform/frontend/src/views/workpaper-list/__tests__/Workpaper{X}View.spec.ts`），覆盖默认渲染加 1 条主要交互
2. THE Shell SHALL 至少有 1 个 vitest spec，覆盖 6 个 viewMode 切换、非法 viewMode 回退、keep-alive 实例复用 3 条断言
3. THE Playwright_E2E SHALL 在 `audit-platform/frontend/e2e/` 下新增或扩展 `workpaper-list-views.spec.ts`，覆盖 5 子视图各 1 条主路径（进入 / 渲染就绪 / 1 次主交互 / 切换离开），共 5 个回归点
4. THE 子 SFC SHALL 在 vitest 中可独立 mount，不依赖 Shell 注入的 `useWorkpaperListContext`（测试时通过 `provide` 注入 mock context）
5. WHEN 全套 vitest 跑完，failed_count SHALL 等于 0（V3 spec 已建 baseline=0）
6. WHEN vue-tsc 跑完，errors_count SHALL 等于 0（V3 spec 已建 baseline=0）

### Requirement 7 — 性能可观察性（首屏与懒加载）

**User Story**：作为合伙人，我希望进入项目后第一眼看到 Workbench 列表的时间不超过当前体感，且切到 DependencyGraph（D3 重）也不卡。

#### Acceptance Criteria

1. THE Shell 首屏 SHALL 仅同步加载 Workbench 子 SFC chunk（缺省 viewMode），其余 4 子 SFC chunk SHALL 通过 `defineAsyncComponent` lazy import，按用户切换 Tab 时按需下载
2. THE DependencyGraph_View SHALL 在 SFC 内部 lazy import D3 force-graph 子模块（如 `const d3 = await import('d3-force')`），避免污染 Shell 与其他子 SFC bundle
3. WHEN viewMode 切换至已访问过的子视图，keep-alive 缓存 SHALL 复用 SFC 实例，DOM 重新挂载次数 SHALL 等于 1（vitest fake-timers 验证 mount 调用次数 = 1）
4. THE 首屏渲染时间（FCP）SHALL 通过 Playwright 实测保持与重构前同等量级（±10% 容差，记录 baseline 数值不强卡 CI）
5. WHERE Bundle visualizer 已配置，THE 5 子 SFC chunk SHALL 在 `dist/stats.html` 中显示为独立 chunk（命名以 `workpaper-list-` 前缀识别）


### Requirement 8 — 防退化（CI baseline 扩展）

**User Story**：作为质控负责人，我希望本次瘦身不会因为后续维护被反向膨胀回 god component。

#### Acceptance Criteria

1. THE CI_frontend_build_job SHALL 新增 4 道 only-decrease grep 卡点：`WorkpaperList.vue` 小于等于 1000 / `WorkpaperLifecycleView.vue` 小于等于 700 / `WorkpaperBoardView.vue` 小于等于 700 / `WorkpaperDelegationMatrix.vue` 小于等于 700
2. THE CI_frontend_build_job SHALL 新增 2 道 only-decrease grep 卡点：`WorkpaperDependencyGraph.vue` 小于等于 700 / `WorkpaperWorkbenchView.vue` 小于等于 700
3. WHEN 任一受锁文件行数超出阈值，THE CI SHALL 失败并输出当前行数与 baseline 差值
4. THE baselines.json SHALL 在 `audit-platform/frontend/baselines.json` 新增 6 个 entry（5 子 SFC 加 1 shell），与既有 V3 spec entry 同 schema
5. IF 任一受锁文件被删除（误操作），THEN THE CI SHALL 显式失败并提示「god component 拆分文件丢失」
6. THE 本 spec 完成后 SHALL 在 `.kiro/specs/INDEX.md` §2.3 占位待办区移除 `workpaper-list-shrink` 行，并在 §2.1 实施区登记完成度

### Requirement 9 — 文档与历史档案治理

**User Story**：作为新加入的开发者，我希望从 spec 索引就能找到完整的设计 / 任务 / 复盘链路，不用反复 grep。

#### Acceptance Criteria

1. THE README_stub `.kiro/specs/workpaper-list-shrink/README.md` SHALL 在三件套就绪后被删除（已于 2026-05-28 删除，避免双源）
2. THE INDEX.md §2.1 SHALL 登记 `workpaper-list-shrink` 完成度（已于 2026-05-28 从 §2.3 占位待办迁入 §2.1 实施区，状态 0/13）
3. THE 本 requirements.md SHALL 是唯一的需求来源（single source of truth），design.md 与 tasks.md 在后续阶段引用本文件章节号而非已删除的 README

### Requirement 10 — 范围排除（不顺手治理同类 god component）

**User Story**：作为遵循「spec 范围严格锁定」铁律的开发者，我希望明确本 spec 不会扩散到其他 god component，但同时预声明未来 spec 路线，避免治理盲区。

#### Acceptance Criteria

1. THE 本_spec SHALL 不修改 `LedgerPenetration.vue`（3794 行）、`TrialBalance.vue`（2766）、`DisclosureEditor.vue`（2603）、`ReportView.vue`（2538）任何一行
2. THE 本_spec SHALL 不修改 `GtCNoteTable.vue`（1608）、`GtDFormReview.vue`（1670）、`GtDFormConfirmation.vue`（1434）任何一行
3. THE 本_spec SHALL 不修改后端任何文件（routers / services / models / migrations）
4. THE 本_spec SHALL 不修改 `router/index.ts` 的 children 结构，仅可在 `WorkpaperList` route 下保留同一 component import 路径
5. THE 后续_spec_路线 SHALL 在本 requirements.md 末尾「未来可扩展」段落预声明（见下文）


## 未来可扩展（预声明，本 spec 不实施）

按 god component 行数排序，未列入本 spec 治理但已沉淀到 INDEX.md 与 memory 的同类待办：

| 优先级 | Spec 名 | 目标文件 | 当前行数 | 状态 |
|---|---|---|---|---|
| P0 | `ledger-penetration-shrink`（建议名） | `LedgerPenetration.vue` | 3794 | 未起 stub |
| P1 | `trial-balance-shrink`（建议名） | `TrialBalance.vue` | 2766 | 未起 stub |
| P1 | `disclosure-editor-shrink`（建议名） | `DisclosureEditor.vue` | 2603 | 未起 stub |
| P1 | `report-view-shrink`（建议名） | `ReportView.vue` | 2538 | 未起 stub |
| P1 | `workpaper-editor-shrink-phase2` | `WorkpaperEditor.vue` | 2555 | gaps.md 已记录 |
| P2 | `gt-c-note-table-shrink` | `GtCNoteTable.vue` 等 | 1608 / 1670 / 1434 | README stub 已建 |

**本 spec 不顺手治理理由**：

- spec 三件套铁律要求范围严格锁定，god component 拆分单 spec 工时 1 周，5 个并行风险面失控
- 各 god component 的子视图边界差异大（LedgerPenetration 是 4 表联查 / DisclosureEditor 是附注模板渲染 / ReportView 是报表加附注双引擎），共用一个 spec 会变成「大杂烩重构」违反 default_to_action 铁律
- WorkpaperList 是用户每日入口（最高频体感），治理收益最大化优先


## Property-based 不变量

> **修订（2026-05-28）**：design ADR-4 决议把 Property 1 从 hypothesis PBT 降级为普通断言测试（避免 conventions §PBT 反模式清单中的"恒真断言"）。本节保留 Property 1 描述作为业务不变量记录，实施位置改为 vitest。Property 2 仍保留为 fast-check PBT。

### Property 1 — 子 SFC 行数总和不超原文件 ×1.2（**普通断言测试，非 PBT**）

**位置**：`audit-platform/frontend/src/views/workpaper-list/__tests__/line-budget.spec.ts`（vitest，对应 tasks 9.4）

**不变量描述**：
拆分后 5 子 SFC 加 1 shell 的总行数小于等于拆分前 `WorkpaperList.vue` 行数 × 1.2，容许 shell 桥接代码（lazy import / provide / inject context / router watcher）膨胀 20%。

**形式化表达**：

```
∀ files ⊆ {WorkpaperList.vue, WorkpaperLifecycleView.vue, WorkpaperBoardView.vue,
            WorkpaperDelegationMatrix.vue, WorkpaperDependencyGraph.vue, WorkpaperWorkbenchView.vue}:
  sum(line_count(f) for f in files) <= ORIGINAL_LINE_COUNT * 1.2
  where ORIGINAL_LINE_COUNT = 3463 (baseline locked at spec start)
```

**降级理由**：原拟用 hypothesis `strategies.sampled_from` 参数化 6 文件路径，但输入空间固定无 fuzzing 价值（按 conventions §PBT 反模式清单"恒真断言"），改为 `expect(totalLines).toBeLessThanOrEqual(4156)` 普通断言更诚实；CI 6 道 only-decrease grep 已覆盖同等防退化能力（详见 design ADR-4）。

### Property 2 — 路由切换 lazy import 加 keep-alive 不重复 mount（fast-check）

**位置**：`audit-platform/frontend/src/views/workpaper-list/__tests__/property-route-switch.spec.ts`（fast-check）

**不变量描述**：
对 7 个 viewMode 枚举值的任意切换序列（含重复访问 / 双向跳转 / 非法值），shell 容器 mount 子 SFC 实例的次数小于等于 5（5 子 SFC 各最多 mount 1 次），即使切换序列长度大于等于 100。

**形式化表达**：

```
∀ sequence: List<viewMode> where viewMode ∈ ['list','kanban','workbench','lifecycle','graph','matrix','guide']:
  let mount_counts = simulate_shell(sequence) in
    sum(mount_counts.values()) <= 5
    AND ∀ view ∈ visited(sequence): mount_counts[mapped_sfc(view)] >= 1   # 已访问的 viewMode 触发了对应 SFC 至少 1 次 mount
    AND ∀ sfc ∉ visited_sfcs(sequence): mount_counts[sfc] == 0           # 未访问 SFC 0 次 mount
    AND ∀ sfc: mount_counts[sfc] <= 1                                     # keep-alive 保证每 SFC 最多 1 次
  where mapped_sfc(view) maps {list, workbench, guide} → Workbench, others → identity
```

**fast-check 参数化**：`fc.array(fc.constantFrom(...VIEWMODES_7), { minLength: 1, maxLength: 100 })`，模拟 keep-alive 缓存语义，验证累计 mount 次数恒 ≤ 5（list/workbench/guide 三 viewMode 共享 Workbench SFC 不重复 mount）。


## 文档输出度量

| 维度 | 数量 |
|---|---|
| Total User Stories | 10 |
| Total Acceptance Criteria | 61 |
| Total Property Invariants（PBT） | **1**（仅 Property 2 fast-check；Property 1 已降级为普通断言测试，详见 ADR-4） |
| Glossary Terms | 12 |
| Future Spec Backlog | 6 |
