# Requirements Document — workpaper-editor-shrink-phase2

## Introduction

`audit-platform/frontend/src/views/WorkpaperEditor.vue` 当前 **2555 行**，是审计平台底稿编辑器的核心视图（route name=`WorkpaperEditor`，path=`/projects/:projectId/workpapers/:wpId`）。V3 spec（global-refinement-v3 Sprint 4 Req 12.1）已完成第一阶段基础设施建设：

- ✅ `useEditorToolbar`：工具栏配置驱动（4 主按钮 + 5 dropdown）
- ✅ `useEditorCycles`：7 cycle composable 实例化集中管理
- ✅ `useEditorMode`：HTML/Univer 双模式路由分发
- ✅ `editorDialogConfig`：17 dialog 元数据注册表
- ✅ 删除 44 处冗余别名 const

净减 70 行（2625→2555），但距目标 ≤1000 行仍差 **1555 行**。

**本 spec 目标**：继续瘦身至 ≤1000 行，通过以下策略：
1. 抽取 **3-4 个子 SFC**（CycleDialogHost / UniverEditorCore / EditorStatusBar / EditorBanners）
2. 进一步 composable 提取（useEditorUniver / useEditorSave / useEditorReview）
3. 模板 v-for 渲染替代散落的 cycle trigger/dialog v-if 块（~400 行 → ~30 行）
4. onMounted 初始化逻辑下沉到 composable

**范围严格锁定**：仅做结构性瘦身，不动业务逻辑，不动后端，不动路由，保留 `name: 'WorkpaperEditor'` 路由名向后兼容。

## 元数据

- **Spec 类型**：feature（重构性 P1）
- **关联文档**：design.md / tasks.md
- **工时**：3-5 工作日
- **依赖 spec**：`global-refinement-v3`（12.1.1-12.1.5 基础设施）、`workpaper-html-renderer`（GtWpRenderer 路由分发）、`workpaper-list-shrink`（同类 Shell+子SFC 模式参考）
- **CI 防退化**：既有 `WorkpaperEditor-vue-lines: 2555`（only-decrease）继续生效，完成后更新为 ≤1000

## Glossary

- **WorkpaperEditor**：底稿编辑器当前组件名，路由 `/projects/:projectId/workpapers/:wpId`，本 spec 瘦身后保留为 Shell 容器
- **Shell**：瘦身后的 WorkpaperEditor.vue，仅承担路由解析 + 模式分发 + 子 SFC 编排 + provide context，不持有 Univer 实例化 / 保存逻辑 / 弹窗渲染
- **CycleDialogHost**：抽出的子 SFC，承担 17 个 cycle dialog 的条件渲染（v-for 配置驱动替代 ~300 行散落 v-if）
- **UniverEditorCore**：抽出的子 SFC，承担 Univer 引擎初始化 / 画布渲染 / Sheet 导航 / 命令监听 / 保存逻辑
- **EditorStatusBar**：抽出的子 SFC，承担底部状态栏 + 智能提示 + autoSave 反馈
- **EditorBanners**：抽出的子 SFC，承担顶部横幅区（归档 / AI pending / 冲突 / 前置状态 / stale 影响）
- **useEditorUniver**：新 composable，封装 Univer createUniver / dispose / workbook 生命周期 / 命令监听
- **useEditorSave**：新 composable，封装 onSave / xlsx 导出 / 版本冲突处理 / stale 通知
- **useEditorReview**：（已合并入 ReviewMarkDialog 子 SFC，不单独建 composable；design §8 修订点 #3）
- **cycleDialogs**：已有 `useEditorCycles` 返回的 dialog 状态集合，本 spec 进一步利用其元数据做 v-for 渲染
- **editorDialogConfig**：已有 dialog 元数据注册表（`TEMPLATE_DIALOGS`），本 spec 扩展为包含组件引用的完整配置
- **only-decrease baseline**：CI 卡点形式，文件行数只能减少不能增加

## Requirements

### Requirement 1 — Shell 容器瘦身目标

**User Story**：作为开发者，我希望 WorkpaperEditor.vue 瘦身至 ≤1000 行，让后续维护、code review、vitest mount 都能精准定位职责边界。

#### Acceptance Criteria

1. THE Shell SHALL 在小于等于 1000 行内完成路由解析、模式分发（HTML/Univer/子编辑器）、子 SFC 编排、provide context
2. THE Shell SHALL 保留 `name: 'WorkpaperEditor'` 路由名，且 router/index.ts 的 component import 路径不变
3. THE Shell SHALL 保留现有 `onBeforeRouteLeave` dirty 检查逻辑（confirmLeave）
4. THE Shell SHALL 通过 `provide` 向子 SFC 注入共享 context（projectId / wpId / wpDetail / canEdit / componentType / useHtmlRenderer）
5. WHEN 瘦身完成，THE CI_frontend_build_job 既有 `WorkpaperEditor-vue-lines` baseline SHALL 更新为实际行数（≤1000）
6. THE 瘦身后 Shell + 所有新建子 SFC 总行数 SHALL 小于等于 2748 × 1.2 = 3298（容许桥接代码膨胀 20%）

### Requirement 2 — CycleDialogHost 子 SFC 抽取

**User Story**：作为开发者，我希望 17 个 cycle dialog 的条件渲染从 Shell 模板中移出，用配置驱动的 v-for 替代 ~300 行散落的 v-if 块。

#### Acceptance Criteria

1. THE CycleDialogHost SHALL 抽出至 `audit-platform/frontend/src/views/workpaper-editor/CycleDialogHost.vue`
2. THE CycleDialogHost SHALL 通过 props 接收 `projectId / wpId / wpDetail / sheetNavActiveId / cycleType / cycleDialogs`
3. THE CycleDialogHost SHALL 使用 `editorDialogConfig` 元数据 + `defineAsyncComponent` 实现配置驱动的 dialog 渲染，替代模板内 17 个独立 v-if 块
4. EACH dialog 组件 SHALL 通过 `defineAsyncComponent(() => import(...))` lazy 加载，仅在对应 cycle 激活时下载 chunk
5. THE CycleDialogHost SHALL 通过 emit `'saved'` / `'applied'` 通知 Shell 刷新数据
6. THE Shell 模板中原有的 17 个 dialog v-if 块（约 300 行）SHALL 被替换为单个 `<CycleDialogHost ... />` 标签（约 10 行）
7. THE CycleDialogHost SHALL 满足 `wc -l` 小于等于 200 行（配置驱动，不含业务逻辑）

### Requirement 3 — CycleTriggerPanel 子 SFC 抽取

**User Story**：作为开发者，我希望左侧栏中 15+ 个 cycle trigger 按钮的条件渲染从 Shell 模板中移出，用配置驱动的 v-for 替代 ~200 行散落的 v-if 块。

#### Acceptance Criteria

1. THE CycleTriggerPanel SHALL 抽出至 `audit-platform/frontend/src/views/workpaper-editor/CycleTriggerPanel.vue`
2. THE CycleTriggerPanel SHALL 通过 props 接收 `wpDetail / cycleType / cycleDialogs / iCycle / gCycle / kCycle / lCycle / mCycle / nCycle / fCycle`
3. THE CycleTriggerPanel SHALL 使用 `editorDialogConfig` 元数据中的 trigger 配置实现 v-for 渲染，替代模板内 15+ 个独立 v-if 按钮块
4. THE Shell 模板中原有的 cycle trigger 按钮区域（约 200 行）SHALL 被替换为单个 `<CycleTriggerPanel ... />` 标签
5. THE CycleTriggerPanel SHALL 通过 emit 通知 Shell 打开对应 dialog（或直接操作 cycleDialogs ref）
6. THE CycleTriggerPanel SHALL 满足 `wc -l` 小于等于 150 行

### Requirement 4 — UniverEditorCore 子 SFC 抽取

**User Story**：作为开发者，我希望 Univer 引擎初始化、画布渲染、Sheet 导航、命令监听、保存逻辑从 Shell 中移出，形成独立可测试的编辑器核心组件。

#### Acceptance Criteria

1. THE UniverEditorCore SHALL 抽出至 `audit-platform/frontend/src/views/workpaper-editor/UniverEditorCore.vue`
2. THE UniverEditorCore SHALL 封装 `createUniver` / `dispose` / workbook 创建 / 命令监听 / dirty 状态管理
3. THE UniverEditorCore SHALL 通过 props 接收 `projectId / wpId / wpDetail / canEdit`
4. THE UniverEditorCore SHALL 通过 emit 暴露 `'saved' / 'dirty-change' / 'sheet-switch' / 'locate-cell'` 事件
5. THE UniverEditorCore SHALL 内含 Sheet 导航（UniverSheetNav + SheetTopTabs）、Univer 画布容器、prefill tooltip、cross-ref overlay、formula bar
6. THE UniverEditorCore SHALL 内含 autoSave 逻辑（useWorkpaperAutoSave）和 onSave 完整流程（xlsx 导出 + JSON snapshot + 版本冲突处理）
7. THE UniverEditorCore SHALL 满足 `wc -l` 小于等于 800 行
8. THE Shell 中原有的 Univer 相关代码（initUniver + onSave + 画布 DOM + Sheet 导航 + prefill/crossRef overlay，约 800 行）SHALL 被替换为单个 `<UniverEditorCore ... />` 标签

### Requirement 5 — EditorStatusBar 子 SFC 抽取

**User Story**：作为开发者，我希望底部状态栏（编制人/复核人/版本/autoSave 反馈/智能提示）从 Shell 模板中移出，形成独立的状态展示组件。

#### Acceptance Criteria

1. THE EditorStatusBar SHALL 抽出至 `audit-platform/frontend/src/views/workpaper-editor/EditorStatusBar.vue`
2. THE EditorStatusBar SHALL 通过 props 接收 `wpDetail / dirty / autoSaveMsg / smartTip`
3. THE EditorStatusBar SHALL 内含智能提示详情展开/收起逻辑
4. THE EditorStatusBar SHALL 内含用户名解析逻辑（resolveUserName + loadUserMap）
5. THE Shell 模板中原有的状态栏 + 智能提示区域（约 50 行）SHALL 被替换为单个 `<EditorStatusBar ... />` 标签
6. THE EditorStatusBar SHALL 满足 `wc -l` 小于等于 120 行

### Requirement 6 — EditorBanners 子 SFC 抽取

**User Story**：作为开发者，我希望顶部横幅区（归档 / AI pending / 冲突 / 前置状态 / stale 影响 / 编辑锁）从 Shell 模板中移出，形成独立的横幅编排组件。

#### Acceptance Criteria

1. THE EditorBanners SHALL 抽出至 `audit-platform/frontend/src/views/workpaper-editor/EditorBanners.vue`
2. THE EditorBanners SHALL 通过 props 接收 `projectId / wpId / wpDetail / cycleType`
3. THE EditorBanners SHALL 内含 ArchivedBanner / AiContentPendingBanner / ConflictBanner + ConflictResolutionPanel / 编辑锁 alert / 前置状态横幅 / stale 影响横条
4. THE EditorBanners SHALL 通过 emit 暴露 `'conflict-resolved' / 'stale-item-click' / 'jump-to-prereq'` 事件
5. THE Shell 模板中原有的横幅区域（约 80 行）SHALL 被替换为单个 `<EditorBanners ... />` 标签
6. THE EditorBanners SHALL 满足 `wc -l` 小于等于 200 行

### Requirement 7 — useEditorSave composable 抽取

**User Story**：作为开发者，我希望保存逻辑（onSave / xlsx 导出 / 版本冲突 / stale 通知 / onSubmitForReview / onSyncStructure / onRefreshPrefill / onDownload / onExportPdf）从 Shell script 中移出，形成独立可测试的 composable。

#### Acceptance Criteria

1. THE useEditorSave SHALL 新建于 `audit-platform/frontend/src/composables/useEditorSave.ts`
2. THE useEditorSave SHALL 封装 onSave / onSubmitForReview / onSyncStructure / onRefreshPrefill / onDownload / onExportPdf / onUpload 共 7 个 action
3. THE useEditorSave SHALL 接收参数 `{ projectId, wpId, wpDetail, univerAPI, dirty, userOverrides, staleImpact, hasPrefillMapping }`
4. THE useEditorSave SHALL 返回 `{ saving, submitting, syncLoading, prefillLoading, exportingPdf, onSave, onSubmitForReview, onSyncStructure, onRefreshPrefill, onDownload, onExportPdf, onUpload }`
5. THE Shell script 中原有的 7 个 action 函数（约 250 行）SHALL 被替换为 `useEditorSave(...)` 调用
6. THE useEditorSave SHALL 满足 `wc -l` 小于等于 300 行

### Requirement 8 — useEditorUniver composable 抽取

**User Story**：作为开发者，我希望 Univer 引擎生命周期管理（createUniver / dispose / workbook 创建 / 命令监听 / dirty 标记）从 Shell script 中移出，形成独立可测试的 composable。

#### Acceptance Criteria

1. THE useEditorUniver SHALL 新建于 `audit-platform/frontend/src/composables/useEditorUniver.ts`
2. THE useEditorUniver SHALL 封装 initUniver / dispose / workbook 创建 / DIRTY_COMMAND_PATTERNS 监听 / sheet 切换监听
3. THE useEditorUniver SHALL 接收参数 `{ containerRef, projectId, wpId, wpDetail, sheetNavFacade }`
4. THE useEditorUniver SHALL 返回 `{ univerAPI, loading, loadingHint, loadErrorState, loadErrorMessage, dirty, initUniver, dispose }`
5. THE Shell script 中原有的 initUniver 函数 + Univer 相关 ref + DIRTY_COMMAND_PATTERNS（约 300 行）SHALL 被替换为 `useEditorUniver(...)` 调用
6. THE useEditorUniver SHALL 满足 `wc -l` 小于等于 350 行

### Requirement 9 — 版本历史抽屉抽取

**User Story**：作为开发者，我希望版本历史抽屉（el-drawer + VersionHistorySearch + timeline）从 Shell 模板中移出，减少 Shell 模板行数。

#### Acceptance Criteria

1. THE VersionHistoryDrawer SHALL 抽出至 `audit-platform/frontend/src/views/workpaper-editor/VersionHistoryDrawer.vue`
2. THE VersionHistoryDrawer SHALL 通过 props 接收 `wpId` 和 v-model `visible`
3. THE VersionHistoryDrawer SHALL 内含版本列表加载 / VersionHistorySearch / timeline 渲染
4. THE Shell 模板中原有的版本历史抽屉（约 40 行）SHALL 被替换为单个 `<VersionHistoryDrawer ... />` 标签
5. THE VersionHistoryDrawer SHALL 满足 `wc -l` 小于等于 120 行

### Requirement 10 — 审计导航图对话框抽取

**User Story**：作为开发者，我希望审计导航图全屏对话框从 Shell 模板中移出，减少 Shell 模板行数。

#### Acceptance Criteria

1. THE AuditNavDialog SHALL 抽出至 `audit-platform/frontend/src/views/workpaper-editor/AuditNavDialog.vue`
2. THE AuditNavDialog SHALL 通过 props 接收 `projectId / wpId / wpCode` 和 v-model `visible`
3. THE Shell 模板中原有的审计导航图对话框（约 40 行）SHALL 被替换为单个 `<AuditNavDialog ... />` 标签
4. THE AuditNavDialog SHALL 满足 `wc -l` 小于等于 80 行

### Requirement 11 — 复核标记对话框抽取

**User Story**：作为开发者，我希望复核标记对话框（el-dialog + form + onMarkReview）从 Shell 中移出。

#### Acceptance Criteria

1. THE ReviewMarkDialog SHALL 抽出至 `audit-platform/frontend/src/views/workpaper-editor/ReviewMarkDialog.vue`
2. THE ReviewMarkDialog SHALL 通过 props 接收 `wpId / projectId` 和 v-model `visible`，通过 emit 暴露 `'marked'` 事件
3. THE ReviewMarkDialog SHALL 内含 reviewDialogCell / reviewDialogStatus / reviewDialogComment / reviewMarkRules / onMarkReview 完整逻辑
4. THE Shell 模板 + script 中原有的复核标记相关代码（约 80 行）SHALL 被替换为单个 `<ReviewMarkDialog ... />` 标签
5. THE ReviewMarkDialog SHALL 满足 `wc -l` 小于等于 120 行

### Requirement 12 — 测试可观察性

**User Story**：作为质控人员，我希望每个新建子 SFC 和 composable 都有独立单测，重构后回归面可证。

#### Acceptance Criteria

1. EACH 新建子 SFC SHALL 至少有 1 个 vitest spec 文件（`audit-platform/frontend/src/views/workpaper-editor/__tests__/{Name}.spec.ts`），覆盖默认渲染 + 1 条主要交互
2. EACH 新建 composable SHALL 至少有 1 个 vitest spec 文件，覆盖核心返回值 + 1 条主要行为
3. THE Shell SHALL 保留既有 vitest 覆盖（如有），且新增 1 条 spec 验证子 SFC 编排正确性
4. WHEN 全套 vitest 跑完，failed_count SHALL 等于 0
5. WHEN vue-tsc 跑完，errors_count SHALL 等于 0（维持 V3 spec baseline=0）
6. THE 新建子 SFC SHALL 在 vitest 中可独立 mount，不依赖 Shell 注入（测试时通过 props / provide mock 注入）

### Requirement 13 — 防退化（CI baseline 更新）

**User Story**：作为质控负责人，我希望本次瘦身不会因为后续维护被反向膨胀回 god component。

#### Acceptance Criteria

1. THE CI_frontend_build_job 既有 `WorkpaperEditor-vue-lines` baseline SHALL 从 2555 更新为实际完成行数（≤1000）
2. THE CI_frontend_build_job SHALL 新增子 SFC only-decrease 卡点：`UniverEditorCore.vue` ≤ 800 / `CycleDialogHost.vue` ≤ 200 / `CycleTriggerPanel.vue` ≤ 150
3. WHEN 任一受锁文件行数超出阈值，THE CI SHALL 失败并输出当前行数与 baseline 差值
4. THE baselines.json SHALL 新增对应 entry，与既有 V3 spec entry 同 schema
5. IF 任一受锁文件被删除（误操作），THEN THE CI SHALL 显式失败并提示「编辑器瘦身文件丢失」

### Requirement 14 — 范围排除

**User Story**：作为遵循「spec 范围严格锁定」铁律的开发者，我希望明确本 spec 不会扩散到其他文件的业务逻辑变更。

#### Acceptance Criteria

1. THE 本_spec SHALL 不修改后端任何文件（routers / services / models / migrations）
2. THE 本_spec SHALL 不修改 `router/index.ts` 的路由结构（仅可在 WorkpaperEditor route 下保留同一 component import 路径）
3. THE 本_spec SHALL 不修改已有 composable 的公开 API 签名（useEditorToolbar / useEditorCycles / useEditorMode / editorDialogConfig 的导出接口不变）
4. THE 本_spec SHALL 不修改 GtWpRenderer / WorkpaperFormEditor / WorkpaperWordEditor / WorkpaperTableEditor / WorkpaperHybridEditor 任何一行
5. THE 本_spec SHALL 不改变用户可见的 UI 行为（按钮位置 / 弹窗交互 / 状态栏信息 / 快捷键 均保持不变）
6. THE 本_spec SHALL 不引入新的 npm 依赖

## Property-based 不变量

### Property 1 — 子 SFC 行数总和不超原文件 ×1.2（普通断言测试，非 PBT）

**位置**：`audit-platform/frontend/src/views/workpaper-editor/__tests__/line-budget.spec.ts`（vitest）

**不变量描述**：
拆分后 Shell + 所有新建子 SFC 的总行数小于等于拆分前 `WorkpaperEditor.vue` 行数 × 1.2，容许桥接代码膨胀 20%。

**形式化表达**：

```
∀ files ⊆ {WorkpaperEditor.vue, CycleDialogHost.vue, CycleTriggerPanel.vue,
            UniverEditorCore.vue, EditorStatusBar.vue, EditorBanners.vue,
            VersionHistoryDrawer.vue, AuditNavDialog.vue, ReviewMarkDialog.vue}:
  sum(line_count(f) for f in files) <= ORIGINAL_LINE_COUNT * 1.2
  where ORIGINAL_LINE_COUNT = 2748 (baseline locked at spec start, design §1.1 实测)
```

**降级理由**：与 workpaper-list-shrink Property 1 同理，输入空间固定无 fuzzing 价值，改为普通断言测试。

### Property 2 — CycleDialogHost 配置驱动渲染等价性（fast-check）

**位置**：`audit-platform/frontend/src/views/workpaper-editor/__tests__/property-cycle-dialog-host.spec.ts`（fast-check）

**不变量描述**：
对 11 个 cycle 代号（D~N）的任意子集组合，CycleDialogHost 通过配置驱动渲染的 dialog 集合 SHALL 与原始硬编码 v-if 逻辑产生的 dialog 集合完全一致（不多不少）。

**形式化表达**：

```
∀ cycleCode ∈ ['D','E','F','G','H','I','J','K','L','M','N']:
  ∀ wpCode: string matching /^{cycleCode}\d+/:
    let configDriven = CycleDialogHost.getVisibleDialogs(cycleCode, wpCode)
    let hardcoded = originalTemplate.getVisibleDialogs(cycleCode, wpCode)
    in configDriven == hardcoded  # 集合相等
```

**fast-check 参数化**：`fc.record({ cycleCode: fc.constantFrom(...CYCLES_11), wpCodeSuffix: fc.stringMatching(/^\d+(-\d+)?$/) })`，验证配置驱动与硬编码逻辑的等价性。

## 未来可扩展（预声明，本 spec 不实施）

| 优先级 | 方向 | 说明 |
|---|---|---|
| P2 | UniverEditorCore 进一步拆分 | 如 Univer 画布 vs Sheet 导航 vs prefill overlay 三层分离 |
| P2 | editorDialogConfig 扩展为完整 plugin 体系 | 每个 cycle 注册自己的 trigger + dialog + handler，Shell 零感知 |
| P3 | WorkpaperEditor 改为 router children 多视图 | HTML/Univer/Form/Word/Table/Hybrid 各自独立路由组件 |

## 文档输出度量

| 维度 | 数量 |
|---|---|
| Total User Stories | 14 |
| Total Acceptance Criteria | 62 |
| Total Property Invariants（PBT） | **1**（仅 Property 2 fast-check；Property 1 已降级为普通断言测试） |
| Glossary Terms | 12 |
| Future Spec Backlog | 3 |
