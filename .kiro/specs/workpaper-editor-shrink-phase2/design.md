# Design Document — workpaper-editor-shrink-phase2

> **Spec 类型**：feature（重构性 P1）
> **关联**：requirements.md（14 user stories / 62 ACs / 1 PBT）
> **起草日期**：2026-05-28
> **前置探测**：grep 实测 WorkpaperEditor.vue 2748 行 / ~55 reactive state / 17 cycle dialog / 15+ cycle trigger / 4 已抽 composable

---

## 1. 当前现状（实测 2026-05-28）

### 1.1 文件度量

| 维度 | 实测值 |
|---|---|
| 总行数 | **2748** |
| `<template>` | line 1–949（949 行） |
| `<script setup>` | line 951–2488（1537 行） |
| `<style scoped>` | line 2490–2648（158 行） |
| `<style>` 全局 | line 2651–2748（97 行） |
| reactive state（ref/computed） | **~55 个** |
| cycle dialog 实例 | **17 个**（F×2 / H×3 / I×3 / G×3 / K×2 / L×2 / M×1 / N×1） |
| cycle trigger 按钮 | **15+ 个**（散落 v-if 块） |
| 已抽 composable | 4 个（useEditorToolbar / useEditorCycles / useEditorMode / editorDialogConfig） |

### 1.2 模板结构分区（实测行号）

| 区域 | 行号范围 | 行数 | 抽取目标 |
|---|---|---|---|
| 顶部横幅区（Archived/AI/Conflict/Trust/SM/TM） | 1–22 | 22 | EditorBanners |
| HTML 渲染器路由分发 | 24–55 | 32 | 保留 Shell |
| 编辑锁 alert + 前置状态横幅 | 57–85 | 29 | EditorBanners |
| 顶部工具栏 | 87–165 | 79 | 保留 Shell（已配置驱动） |
| Step Navigation Bar | 167–185 | 19 | 保留 Shell |
| Stale 影响范围横条 | 187–210 | 24 | EditorBanners |
| 版本历史抽屉 | 212–248 | 37 | VersionHistoryDrawer |
| 左侧 Sheet 导航 + cycle trigger 按钮 | 250–470 | **221** | CycleTriggerPanel |
| 中间 Univer 画布区 | 472–510 | 39 | UniverEditorCore |
| Prefill tooltip + Cross-ref overlay | 512–530 | 19 | UniverEditorCore |
| Formula bar | 532–538 | 7 | UniverEditorCore |
| CellFormulaDetail 弹窗 | 540–550 | 11 | 保留 Shell |
| 审计导航图对话框 | 552–600 | 49 | AuditNavDialog |
| 17 个 cycle dialog 实例 | 602–880 | **279** | CycleDialogHost |
| 复核标记对话框 | 882–910 | 29 | ReviewMarkDialog |
| 底部状态栏 + 智能提示 | 912–940 | 29 | EditorStatusBar |
| 右栏面板抽屉 | 942–949 | 8 | 保留 Shell |

### 1.3 Script 结构分区（实测行号）

| 区域 | 行号范围 | 行数 | 抽取目标 |
|---|---|---|---|
| import 声明 | 951–1060 | 110 | 各子 SFC 分摊 |
| 动态编辑器 + DIRTY_COMMAND_PATTERNS | 1062–1090 | 29 | useEditorUniver |
| 路由/核心 ref + editorMode | 1092–1160 | 69 | 保留 Shell |
| 冲突/信任度/状态机/时光机 ref | 1162–1200 | 39 | EditorBanners |
| wpDetail/loading/error ref | 1202–1230 | 29 | useEditorUniver |
| cycleType + sheetNavFacade | 1232–1340 | 109 | 保留 Shell |
| prerequisite + stale + autoSave | 1342–1420 | 79 | EditorBanners / useEditorSave |
| reviewMarkers + saving/dirty ref | 1420–1470 | 51 | useEditorSave / ReviewMarkDialog |
| useEditorCycles 实例化 | 1470–1500 | 31 | 保留 Shell |
| useEditorToolbar 实例化 | 1500–1540 | 41 | 保留 Shell |
| review dialog state | 1540–1590 | 51 | ReviewMarkDialog |
| auditNav + userNameMap | 1590–1650 | 61 | AuditNavDialog / EditorStatusBar |
| 版本历史 | 1650–1710 | 61 | VersionHistoryDrawer |
| initUniver 函数 | 1710–1960 | **251** | useEditorUniver |
| loadReviewMarkers | 1960–2000 | 41 | 保留 Shell |
| onSave 函数 | 2000–2100 | **101** | useEditorSave |
| onSubmitForReview | 2100–2130 | 31 | useEditorSave |
| onSyncStructure | 2130–2150 | 21 | useEditorSave |
| onRefreshPrefill | 2150–2210 | 61 | useEditorSave |
| onDownload / onExportPdf / onUpload | 2210–2280 | 71 | useEditorSave |
| loadSmartTips | 2280–2310 | 31 | EditorStatusBar |
| Sprint 2 helpers | 2310–2400 | 91 | UniverEditorCore |
| onMarkReview | 2400–2430 | 31 | ReviewMarkDialog |
| lifecycle hooks (onMounted/onUnmounted) | 2430–2488 | 59 | 保留 Shell |

### 1.4 抽取预算汇总

| 抽取目标 | 模板行数 | Script 行数 | 预估总行数 |
|---|---|---|---|
| **CycleDialogHost** | 279 | 20（props 桥接） | ~180（配置驱动 v-for 替代） |
| **CycleTriggerPanel** | 221 | 20 | ~140（配置驱动 v-for 替代） |
| **UniverEditorCore** | 65 | 251+91=342 | ~500（含 useEditorUniver 内联） |
| **EditorStatusBar** | 29 | 61+31=92 | ~110 |
| **EditorBanners** | 75 | 79+39=118 | ~180 |
| **VersionHistoryDrawer** | 37 | 61 | ~100 |
| **AuditNavDialog** | 49 | 10 | ~70 |
| **ReviewMarkDialog** | 29 | 51+31=82 | ~110 |
| **useEditorSave** | — | 101+31+21+61+71=285 | ~280 |
| **useEditorUniver** | — | 251+29=280 | ~300 |
| **Shell 剩余** | ~165 | ~500 | ~800（含 style） |

**预估总行数**：Shell ~800 + 子 SFC ~1290 + composable ~580 = **~2670 行**（原 2748 行 → 拆后 2670 行，满足 ×1.2 预算 = 3066）


## 2. 架构设计

### 2.1 模块拓扑

```
router/index.ts
  └── path: 'projects/:projectId/workpapers/:wpId'
      └── component: WorkpaperEditor.vue (Shell, ≤1000 行)
              │
              ├── provide(EDITOR_CONTEXT_KEY, useEditorContext())
              │
              ├── 路由分发：HTML → GtWpRenderer / 子编辑器 → EDITOR_MAP / Univer → UniverEditorCore
              │
              ├── <EditorBanners />          ← 顶部横幅区
              ├── <toolbar>                  ← 已配置驱动（useEditorToolbar）
              ├── <UniverEditorCore />       ← Univer 编辑器核心
              │     ├── useEditorUniver()    ← Univer 生命周期
              │     ├── useEditorSave()      ← 保存/导出逻辑
              │     ├── <CycleTriggerPanel />← 左侧 cycle 按钮
              │     └── <EditorStatusBar />  ← 底部状态栏
              ├── <CycleDialogHost />        ← 17 dialog 配置驱动渲染
              ├── <VersionHistoryDrawer />   ← 版本历史抽屉
              ├── <AuditNavDialog />         ← 审计导航图
              └── <ReviewMarkDialog />       ← 复核标记
```

### 2.2 数据流方向

```
Shell (WorkpaperEditor.vue)
  │
  ├── onMounted: fetchComponentType → wpDetail → 路由分发
  │
  ├── provide(EDITOR_CONTEXT_KEY, {
  │     projectId, wpId, wpDetail, canEdit, componentType,
  │     cycleType, cycleDialogs, sheetNavFacade
  │   })
  │
  └── 子 SFC 通过 props + inject 获取数据
      └── 写操作通过 emit 通知 Shell（Shell 持有 wpDetail 刷新权）

UniverEditorCore 内部：
  ├── useEditorUniver() → initUniver / dispose / dirty / univerAPI
  ├── useEditorSave() → onSave / onSubmitForReview / onDownload / ...
  └── emit('saved') / emit('dirty-change') → Shell 响应
```

### 2.3 provide/inject vs props 决策

| 数据 | 传递方式 | 理由 |
|---|---|---|
| projectId / wpId / wpDetail / canEdit | **provide** | 多层子 SFC 共享，避免 prop drilling |
| cycleType / cycleDialogs | **provide** | CycleDialogHost + CycleTriggerPanel 都需要 |
| sheetNavFacade / sheetNavActiveId | **props → UniverEditorCore** | 仅 Univer 路径使用 |
| dirty / autoSaveMsg / smartTip | **props → EditorStatusBar** | 单层传递，语义清晰 |
| visible (v-model) | **props + emit** | 弹窗/抽屉标准模式 |

### 2.4 抽取拓扑顺序（依赖关系决定执行顺序）

```
Phase 1（无依赖，可并行）:
  ├── EditorStatusBar（纯展示，0 依赖）
  ├── VersionHistoryDrawer（纯展示 + API 调用）
  ├── AuditNavDialog（纯展示）
  └── ReviewMarkDialog（自含逻辑）

Phase 2（依赖 editorDialogConfig 元数据扩展）:
  ├── CycleDialogHost（依赖 cycleDialogs + editorDialogConfig）
  └── CycleTriggerPanel（依赖 cycleDialogs + editorDialogConfig）

Phase 3（依赖 Phase 1-2 完成后 Shell 行数已大幅减少）:
  ├── useEditorSave（从 Shell script 抽取 7 个 action）
  ├── useEditorUniver（从 Shell script 抽取 initUniver + DIRTY_COMMAND_PATTERNS）
  └── EditorBanners（依赖 provide context 就绪）

Phase 4（收尾）:
  └── UniverEditorCore（组合 useEditorUniver + useEditorSave + CycleTriggerPanel + EditorStatusBar）
```

## 3. 接口契约（TS 类型预演）

### 3.1 Shell provide context

```typescript
// composables/useEditorContext.ts
import type { InjectionKey, Ref, ComputedRef } from 'vue'

export interface EditorContextData {
  projectId: ComputedRef<string>
  wpId: ComputedRef<string>
  wpDetail: Ref<WorkpaperDetail | null>
  canEdit: ComputedRef<boolean>
  componentType: Ref<string>
  cycleType: CycleTypeFlags
  cycleDialogs: CycleDialogsAPI
  sheetNavActiveId: ComputedRef<string>
}

export const EDITOR_CONTEXT_KEY: InjectionKey<EditorContextData> = Symbol('EditorContext')
```

### 3.2 CycleDialogHost

```typescript
// views/workpaper-editor/CycleDialogHost.vue
interface Props {
  projectId: string
  wpId: string
  wpDetail: WorkpaperDetail
  sheetNavActiveId: string
  cycleType: CycleTypeFlags
  cycleDialogs: CycleDialogsAPI
}

interface Emits {
  (e: 'saved'): void
  (e: 'applied', sheet: string): void
}
```

### 3.3 CycleTriggerPanel

```typescript
// views/workpaper-editor/CycleTriggerPanel.vue
interface Props {
  wpDetail: WorkpaperDetail
  cycleType: CycleTypeFlags
  cycleDialogs: CycleDialogsAPI
  iCycle: ICycleEditorAPI
  gCycle: GCycleEditorAPI
  kCycle: KCycleEditorAPI
  lCycle: LCycleEditorAPI
  mCycle: MCycleEditorAPI
  nCycle: NCycleEditorAPI
  fCycle: FCycleEditorAPI
}

interface Emits {
  (e: 'open-dialog', key: string): void
}
```

### 3.4 UniverEditorCore

```typescript
// views/workpaper-editor/UniverEditorCore.vue
interface Props {
  projectId: string
  wpId: string
  wpDetail: WorkpaperDetail
  canEdit: boolean
  sheetNavFacade: SheetNavFacadeAPI
  cycleType: CycleTypeFlags
  cycleDialogs: CycleDialogsAPI
  // cycle instances for trigger panel
  iCycle: ICycleEditorAPI
  gCycle: GCycleEditorAPI
  kCycle: KCycleEditorAPI
  lCycle: LCycleEditorAPI
  mCycle: MCycleEditorAPI
  nCycle: NCycleEditorAPI
  fCycle: FCycleEditorAPI
}

interface Emits {
  (e: 'saved'): void
  (e: 'dirty-change', dirty: boolean): void
  (e: 'sheet-switch', sheetId: string): void
  (e: 'locate-cell', payload: { sheetName?: string; cellRef: string }): void
}
```

### 3.5 EditorStatusBar

```typescript
// views/workpaper-editor/EditorStatusBar.vue
interface Props {
  wpDetail: WorkpaperDetail | null
  dirty: boolean
  autoSaveMsg: string
  smartTip: SmartTipData | null
}
```

### 3.6 EditorBanners

```typescript
// views/workpaper-editor/EditorBanners.vue
interface Props {
  projectId: string
  wpId: string
  wpDetail: WorkpaperDetail | null
  cycleType: CycleTypeFlags
  editLock: EditingLockAPI
  prerequisiteBanner: PrerequisiteBannerData | null
  staleImpact: StaleImpactAPI
  showStaleImpactPanel: boolean
}

interface Emits {
  (e: 'conflict-resolved', id: string, resolution: string): void
  (e: 'stale-item-click', item: StaleAffectedItem): void
  (e: 'jump-to-prereq'): void
  (e: 'update:showStaleImpactPanel', val: boolean): void
}
```

### 3.7 VersionHistoryDrawer

```typescript
// views/workpaper-editor/VersionHistoryDrawer.vue
interface Props {
  wpId: string
  visible: boolean  // v-model
}

interface Emits {
  (e: 'update:visible', val: boolean): void
  (e: 'jump', payload: { versionId: string; sheet: string; cellRef: string }): void
}
```

### 3.8 AuditNavDialog

```typescript
// views/workpaper-editor/AuditNavDialog.vue
interface Props {
  projectId: string
  wpId: string
  wpCode: string
  visible: boolean  // v-model
}

interface Emits {
  (e: 'update:visible', val: boolean): void
}
```

### 3.9 ReviewMarkDialog

```typescript
// views/workpaper-editor/ReviewMarkDialog.vue
interface Props {
  projectId: string
  wpId: string
  visible: boolean  // v-model
  cell: { sheet: string; cellRef: string }
}

interface Emits {
  (e: 'update:visible', val: boolean): void
  (e: 'marked'): void
}
```

### 3.10 useEditorSave

```typescript
// composables/useEditorSave.ts
interface UseEditorSaveOptions {
  projectId: ComputedRef<string>
  wpId: ComputedRef<string>
  wpDetail: Ref<WorkpaperDetail | null>
  univerAPI: Ref<any>
  dirty: Ref<boolean>
  userOverrides: UserOverridesAPI
  staleImpact: StaleImpactAPI
  hasPrefillMapping: Ref<boolean>
  autoSave: WorkpaperAutoSaveAPI
}

interface UseEditorSaveReturn {
  saving: Ref<boolean>
  submitting: Ref<boolean>
  syncLoading: Ref<boolean>
  prefillLoading: Ref<boolean>
  exportingPdf: Ref<boolean>
  onSave: () => Promise<boolean>
  onSubmitForReview: () => Promise<void>
  onSyncStructure: () => Promise<void>
  onRefreshPrefill: () => Promise<void>
  onDownload: () => Promise<void>
  onExportPdf: () => Promise<void>
  onUpload: () => void
}
```

### 3.11 useEditorUniver

```typescript
// composables/useEditorUniver.ts
interface UseEditorUniverOptions {
  containerRef: Ref<HTMLElement | null>
  projectId: ComputedRef<string>
  wpId: ComputedRef<string>
  wpDetail: Ref<WorkpaperDetail | null>
  sheetNavFacade: SheetNavFacadeAPI
}

interface UseEditorUniverReturn {
  univerAPI: Ref<any>
  loading: Ref<boolean>
  loadingHint: Ref<string>
  loadErrorState: Ref<'no_file' | 'no_index' | 'invalid_id' | 'error' | null>
  loadErrorMessage: Ref<string>
  dirty: Ref<boolean>
  loadedFromXlsx: Ref<boolean>
  fileOpenedAt: Ref<number>
  initUniver: () => Promise<void>
  dispose: () => void
}
```


## 4. 数据模型

### 4.1 editorDialogConfig 扩展（配置驱动渲染所需）

当前 `editorDialogConfig.ts` 仅为观察性元数据（devtools 用），本 spec 需扩展为可执行配置：

```typescript
// 扩展 TemplateDialogConfig
export interface TemplateDialogConfig {
  // ... 既有字段 ...
  /** 组件 lazy import 工厂（CycleDialogHost 用） */
  component: () => Promise<{ default: Component }>
  /** trigger 按钮配置（CycleTriggerPanel 用） */
  triggerButton?: {
    icon: string
    label: string
    type?: 'primary' | 'warning'
    plain?: boolean
  }
  /** trigger 可见性判断函数（接收 wp_code + sheetId） */
  triggerVisible?: (wpCode: string, sheetId: string) => boolean
  /** dialog props 工厂（从 context 派生 props） */
  propsFactory?: (ctx: DialogPropsContext) => Record<string, any>
}

interface DialogPropsContext {
  projectId: string
  wpId: string
  wpDetail: WorkpaperDetail
  sheetNavActiveId: string
}
```

### 4.2 Shell 最终骨架（伪代码）

```vue
<template>
  <!-- 横幅区 -->
  <EditorBanners v-bind="bannerProps" @conflict-resolved="..." @stale-item-click="..." />

  <!-- HTML 渲染器路由分发 -->
  <GtWpRenderer v-if="useHtmlRenderer" ... />

  <!-- 子编辑器路由分发 -->
  <component v-else-if="isSubEditor" :is="editorComponent" ... />

  <!-- Univer 编辑器核心 -->
  <UniverEditorCore v-else v-bind="univerProps" @saved="onChildSaved" @dirty-change="..." />

  <!-- 弹窗/抽屉（条件渲染，不占主布局） -->
  <CycleDialogHost v-bind="dialogHostProps" @saved="onChildSaved" @applied="..." />
  <VersionHistoryDrawer v-model:visible="showVersionDrawer" :wp-id="wpId" @jump="..." />
  <AuditNavDialog v-model:visible="showAuditNavDrawer" v-bind="auditNavProps" />
  <ReviewMarkDialog v-model:visible="showReviewDialog" v-bind="reviewProps" @marked="..." />
  <CellFormulaDetail ... />
  <WorkpaperSidePanel ... />
</template>

<script setup lang="ts">
// ≤800 行：路由解析 + provide context + 子 SFC 编排 + toolbar + lifecycle hooks
</script>
```

## 5. CI baseline 字段命名

按 conventions `{property}-{format}-{scope}` 格式：

| 字段名 | 初始值 | 说明 |
|---|---|---|
| `workpaper-editor-shell-lines` | 1000 | Shell 行数上限 |
| `workpaper-editor-univer-core-lines` | 800 | UniverEditorCore 子 SFC |
| `workpaper-editor-cycle-dialog-host-lines` | 200 | CycleDialogHost 子 SFC |
| `workpaper-editor-cycle-trigger-panel-lines` | 150 | CycleTriggerPanel 子 SFC |
| `workpaper-editor-banners-lines` | 200 | EditorBanners 子 SFC |
| `workpaper-editor-status-bar-lines` | 120 | EditorStatusBar 子 SFC |

**写入位置**：`.github/workflows/ci.yml` `frontend-build` job 的"V3 大型 SFC 行数防膨胀 guard"段落，替换既有 `WorkpaperEditor-vue-lines: 2555` 为新 6 entry。

## 6. ADR（架构决策记录）

### ADR-1：UniverEditorCore 内含 useEditorSave vs Shell 持有 save 逻辑

**决策**：useEditorSave 在 UniverEditorCore 内部实例化。

**理由**：
- onSave 需要 `univerAPI.getActiveWorkbook().getSnapshot()`，univerAPI 是 UniverEditorCore 私有状态
- 如果 save 留在 Shell，需要 UniverEditorCore expose univerAPI 或通过 emit 传递 snapshot，增加耦合
- UniverEditorCore 作为"编辑器核心"，save 是其核心职责之一
- Shell 只需响应 `@saved` 事件刷新 wpDetail

**备选**：Shell 持有 useEditorSave + UniverEditorCore expose univerAPI → 增加 expose 复杂度 + 违反封装原则。

### ADR-2：CycleDialogHost 配置驱动 vs 保留硬编码 v-if

**决策**：配置驱动（editorDialogConfig 扩展 + defineAsyncComponent + v-for）。

**理由**：
- 17 个 dialog 的 v-if 块占 279 行，结构高度重复（仅 props 差异）
- 配置驱动后新增 cycle dialog 只需在 editorDialogConfig 添加 1 条 entry，不改模板
- defineAsyncComponent 保证 lazy loading（与当前行为等价）
- 可通过 fast-check PBT 验证配置驱动与硬编码的等价性

**风险**：每个 dialog 的 props 略有差异（如 InterestCalcDialog 有 `:wp-code` 动态计算）→ 通过 `propsFactory` 函数处理。

### ADR-3：CycleTriggerPanel 内含 vs 外置于 UniverEditorCore

**决策**：CycleTriggerPanel 作为 UniverEditorCore 的子组件（内含在左侧栏）。

**理由**：
- trigger 按钮在 Univer 编辑器左侧栏内（`.gt-wp-editor-left-col`），与 Sheet 导航同级
- 仅 Univer 模式显示（HTML/子编辑器模式不显示）
- 与 UniverEditorCore 的 sheetNavActiveId 强关联（trigger 可见性依赖当前 sheet）

**备选**：Shell 直接渲染 CycleTriggerPanel → 需要 Shell 知道 Univer 左侧栏布局细节，违反封装。

### ADR-4：provide/inject 粒度 — 单一 EDITOR_CONTEXT_KEY vs 多个 key

**决策**：单一 `EDITOR_CONTEXT_KEY` 注入所有共享数据。

**理由**：
- 子 SFC 数量有限（6 个），不需要细粒度 key 隔离
- 单一 key 简化测试 mock（一个 provide 覆盖所有）
- 与 workpaper-list-shrink 的 `WP_LIST_CONTEXT_KEY` 模式一致

**备选**：多个 key（`EDITOR_WP_KEY` / `EDITOR_CYCLE_KEY` / ...）→ 增加 inject 调用次数 + 测试 mock 复杂度。

### ADR-5：Shell 替换原文件 vs 新建 WorkpaperEditorShell.vue

**决策**：替换原文件（保留 `WorkpaperEditor.vue` 文件名）。

**理由**：
- 与 workpaper-list-shrink ADR-1 同理
- router/index.ts `component: () => import('@/views/WorkpaperEditor.vue')` 不需改动
- git history 连续
- 其他组件 `router.push({ name: 'WorkpaperEditor' })` 零破坏

### ADR-6：editorDialogConfig 扩展方式 — 原地扩展 vs 新建 editorDialogRegistry

**决策**：原地扩展 `editorDialogConfig.ts`，添加 `component` / `triggerButton` / `triggerVisible` / `propsFactory` 字段。

**理由**：
- 既有 17 条 entry 已在 editorDialogConfig 中，原地扩展避免重复声明
- requirements Req 14.3 要求"不修改已有 composable 的公开 API 签名"→ 新增字段不破坏既有 API（向后兼容）
- 新增字段为 optional（`component?` / `triggerButton?`），既有消费方（devtools 枚举）不受影响

**备选**：新建 `editorDialogRegistry.ts` 独立文件 → 与 editorDialogConfig 数据重复 + 维护两份 entry。

## 7. 风险与缓解

| # | 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|---|
| 1 | dialog propsFactory 遗漏某个 dialog 的特殊 prop | 高 | 运行时 dialog 缺 prop 报错 | 逐个 dialog 对照原模板写 propsFactory + vitest 断言 props 完整性 |
| 2 | UniverEditorCore 行数超 800（含 save + univer + trigger + statusbar） | 中 | CI 卡点失败 | UniverEditorCore 内部进一步拆分：useEditorSave + useEditorUniver 作为 composable 不计入 SFC 行数 |
| 3 | provide/inject 链断裂（子 SFC 测试时 mock 不完整） | 中 | vitest 失败 | 导出 `createMockEditorContext()` helper 供测试用 |
| 4 | CycleTriggerPanel trigger 可见性逻辑与原 v-if 不等价 | 高 | 按钮丢失/多余 | fast-check PBT 验证等价性（Property 1） |
| 5 | onBeforeRouteLeave dirty 检查在 UniverEditorCore 内部 dirty 变化时 Shell 未同步 | 中 | 离开页面不提示 | UniverEditorCore emit('dirty-change') → Shell 同步 dirty ref |
| 6 | Univer 相关 import 在 UniverEditorCore 中重复打包 | 低 | bundle 膨胀 | Univer 已是 vendor chunk（vite splitVendorChunkPlugin），不会重复 |
| 7 | editorDialogConfig 扩展后 TS 类型不兼容既有消费方 | 低 | vue-tsc 报错 | 新增字段全部 optional + 既有消费方不读新字段 |

## 8. 修订点清单（对 requirements.md 的修正）

| # | 修订内容 | 理由 |
|---|---|---|
| 1 | 实测行数 2748（非 requirements 写的 2555）| grep 实测发现文件已增长（可能是 workpaper-list-shrink 期间有其他 commit） |
| 2 | CycleTriggerPanel 应作为 UniverEditorCore 子组件而非 Shell 直接子组件 | 布局位置在 Univer 左侧栏内，仅 Univer 模式可见 |
| 3 | useEditorSave 在 UniverEditorCore 内部实例化（非 Shell 直接调用） | ADR-1 论证：save 需要 univerAPI 私有状态 |
| 4 | EditorBanners 需额外接收 editLock / prerequisiteBanner / staleImpact props | 实测发现横幅区依赖这些状态 |
| 5 | Property 2 的 fast-check 应同时覆盖 trigger 可见性（不仅 dialog 可见性） | 两者共用 editorDialogConfig 元数据，合并测试更全面 |

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Config-driven rendering equivalence

*For any* cycle code ∈ {D, E, F, G, H, I, J, K, L, M, N} and *for any* wp_code matching the pattern `^{cycleCode}\d+(-\d+)?$`, the set of visible dialogs produced by CycleDialogHost's config-driven v-for rendering SHALL equal the set of visible dialogs that the original hardcoded v-if logic would produce, AND the set of visible trigger buttons produced by CycleTriggerPanel's config-driven v-for rendering SHALL equal the set of visible trigger buttons that the original hardcoded v-if logic would produce.

**Validates: Requirements 2.3, 3.3**

---

## Error Handling

### 子 SFC 错误边界

| 子 SFC | 错误场景 | 处理策略 |
|---|---|---|
| UniverEditorCore | initUniver 失败 | 内部 loadErrorState 三态展示（no_file / no_index / error），不 propagate 到 Shell |
| UniverEditorCore | onSave 失败 | handleApiError 弹 toast，返回 false，不影响编辑状态 |
| CycleDialogHost | dialog 组件 chunk 加载失败 | defineAsyncComponent onError → 弹 ElMessage.error + 关闭 dialog |
| EditorBanners | 前置状态 API 失败 | 静默（横幅不显示），不阻断编辑 |
| VersionHistoryDrawer | 版本列表 API 失败 | 内部 handleApiError + 显示 el-empty |
| ReviewMarkDialog | onMarkReview 失败 | handleApiError 弹 toast，dialog 保持打开 |

### provide/inject 防御

所有子 SFC 的 inject 调用必须包含 fallback 或 throw：

```typescript
const ctx = inject(EDITOR_CONTEXT_KEY)
if (!ctx) throw new ReferenceError('EditorContext not provided — must be used inside WorkpaperEditor Shell')
```

## Testing Strategy

### 双测试方法

**Unit tests（vitest）**：
- 每个新建子 SFC 至少 1 个 spec 文件，覆盖默认渲染 + 1 条主要交互
- 每个新建 composable 至少 1 个 spec 文件，覆盖核心返回值 + 1 条主要行为
- Shell 新增 1 条 spec 验证子 SFC 编排正确性
- 行数预算断言测试（line-budget.spec.ts）

**Property-based tests（fast-check）**：
- Property 1：配置驱动渲染等价性
  - 库：fast-check v4.8.0（已安装）
  - 最少 100 iterations
  - Tag: `Feature: workpaper-editor-shrink-phase2, Property 1: Config-driven rendering equivalence`

### 测试文件布局

```
audit-platform/frontend/src/views/workpaper-editor/__tests__/
  ├── CycleDialogHost.spec.ts
  ├── CycleTriggerPanel.spec.ts
  ├── UniverEditorCore.spec.ts
  ├── EditorStatusBar.spec.ts
  ├── EditorBanners.spec.ts
  ├── VersionHistoryDrawer.spec.ts
  ├── AuditNavDialog.spec.ts
  ├── ReviewMarkDialog.spec.ts
  ├── line-budget.spec.ts
  └── property-config-driven-equivalence.spec.ts   ← fast-check PBT
audit-platform/frontend/src/composables/__tests__/
  ├── useEditorSave.spec.ts
  └── useEditorUniver.spec.ts
```

### Property-based test 配置

```typescript
// property-config-driven-equivalence.spec.ts
import * as fc from 'fast-check'

// Feature: workpaper-editor-shrink-phase2, Property 1: Config-driven rendering equivalence
describe('Property 1: Config-driven rendering equivalence', () => {
  it('dialog visibility matches original hardcoded logic for all cycle/wpCode combinations', () => {
    fc.assert(
      fc.property(
        fc.record({
          cycleCode: fc.constantFrom('D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N'),
          wpCodeSuffix: fc.stringMatching(/^\d+(-\d+)?$/),
          sheetId: fc.string({ minLength: 1, maxLength: 20 }),
        }),
        ({ cycleCode, wpCodeSuffix, sheetId }) => {
          const wpCode = `${cycleCode}${wpCodeSuffix}`
          const configDialogs = getVisibleDialogsFromConfig(cycleCode, wpCode, sheetId)
          const hardcodedDialogs = getVisibleDialogsFromOriginalLogic(cycleCode, wpCode, sheetId)
          expect(configDialogs).toEqual(hardcodedDialogs)

          const configTriggers = getVisibleTriggersFromConfig(cycleCode, wpCode, sheetId)
          const hardcodedTriggers = getVisibleTriggersFromOriginalLogic(cycleCode, wpCode, sheetId)
          expect(configTriggers).toEqual(hardcodedTriggers)
        },
      ),
      { numRuns: 200 },
    )
  })
})
```

### 测试隔离策略

- 子 SFC 测试通过 `provide` mock 注入 `EDITOR_CONTEXT_KEY`
- UniverEditorCore 测试 stub Univer SDK（`vi.mock('@univerjs/presets')`）
- useEditorSave 测试 mock `httpApi`（`vi.mock('@/services/apiProxy')`）
- CycleDialogHost 测试 stub 所有 dialog 组件（`defineAsyncComponent` 返回空 div）

---

## 变更记录

| 版本 | 日期 | 摘要 | 触发 |
|---|---|---|---|
| v1.0 | 2026-05-28 | 初版起草 | requirements.md 批准后 |
