# Implementation Plan: workpaper-editor-shrink-phase2

## Overview

按 design §2.4 拓扑顺序实施：Phase 1（无依赖纯展示子 SFC）→ Phase 2（依赖 editorDialogConfig 扩展的配置驱动子 SFC）→ Phase 3（composable 抽取 + EditorBanners）→ Phase 4（UniverEditorCore 组装）→ Phase 5（Shell 替换收尾）→ Phase 6（测试 + CI + 清理）。每步收尾跑 vue-tsc + vitest 双卡点。

## Tasks

- [x] 1. Phase 1 — 无依赖子 SFC 抽取（可并行）
  - [x] 1.1 创建 EditorStatusBar 子 SFC
    - 创建 `audit-platform/frontend/src/views/workpaper-editor/EditorStatusBar.vue`
    - `defineProps<{ wpDetail: WorkpaperDetail | null; dirty: boolean; autoSaveMsg: string; smartTip: SmartTipData | null }>()`
    - 从 Shell template line 912-940 抽取底部状态栏 + 智能提示区域（~29 行）
    - 从 Shell script line 1590-1650 抽取 userNameMap / resolveUserName / loadUserMap 逻辑（~61 行）
    - 从 Shell script line 2280-2310 抽取 loadSmartTips 逻辑（~31 行）
    - 内含智能提示详情展开/收起逻辑
    - `wc -l` ≤ 120 行
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 1.2 创建 VersionHistoryDrawer 子 SFC
    - 创建 `audit-platform/frontend/src/views/workpaper-editor/VersionHistoryDrawer.vue`
    - `defineProps<{ wpId: string; visible: boolean }>()` + `defineEmits<{ 'update:visible': [val: boolean]; 'jump': [payload: { versionId: string; sheet: string; cellRef: string }] }>()`
    - 从 Shell template line 212-248 抽取版本历史抽屉（~37 行）
    - 从 Shell script line 1650-1710 抽取版本列表加载 / VersionHistorySearch / timeline 渲染逻辑（~61 行）
    - 内含 handleApiError + el-empty 错误处理
    - `wc -l` ≤ 120 行
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 1.3 创建 AuditNavDialog 子 SFC
    - 创建 `audit-platform/frontend/src/views/workpaper-editor/AuditNavDialog.vue`
    - `defineProps<{ projectId: string; wpId: string; wpCode: string; visible: boolean }>()` + `defineEmits<{ 'update:visible': [val: boolean] }>()`
    - 从 Shell template line 552-600 抽取审计导航图全屏对话框（~49 行）
    - 从 Shell script line 1590-1650 抽取 auditNav 相关 ref（~10 行）
    - `wc -l` ≤ 80 行
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 1.4 创建 ReviewMarkDialog 子 SFC
    - 创建 `audit-platform/frontend/src/views/workpaper-editor/ReviewMarkDialog.vue`
    - `defineProps<{ projectId: string; wpId: string; visible: boolean; cell: { sheet: string; cellRef: string } }>()` + `defineEmits<{ 'update:visible': [val: boolean]; 'marked': [] }>()`
    - 从 Shell template line 882-910 抽取复核标记对话框（~29 行）
    - 从 Shell script line 1540-1590 抽取 reviewDialogCell / reviewDialogStatus / reviewDialogComment / reviewMarkRules（~51 行）
    - 从 Shell script line 2400-2430 抽取 onMarkReview 完整逻辑（~31 行）
    - `wc -l` ≤ 120 行
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [x] 1.5 验收卡点 — Phase 1
    - `vue-tsc` 0 errors
    - `vitest --run` 0 failed
    - 4 文件行数 grep 验证：EditorStatusBar ≤120 / VersionHistoryDrawer ≤120 / AuditNavDialog ≤80 / ReviewMarkDialog ≤120
    - Shell 模板中对应区域已替换为单标签引用（~160 行净减）
    - _Requirements: 12.5, 14.5_

- [x] 2. Phase 2 — 配置驱动子 SFC（依赖 editorDialogConfig 扩展）
  - [x] 2.1 扩展 editorDialogConfig 元数据
    - 在 `audit-platform/frontend/src/composables/editorDialogConfig.ts` 中扩展 `TemplateDialogConfig` 接口
    - 新增 optional 字段：`component: () => Promise<{ default: Component }>` / `triggerButton?: { icon, label, type?, plain? }` / `triggerVisible?: (wpCode, sheetId) => boolean` / `propsFactory?: (ctx: DialogPropsContext) => Record<string, any>`
    - 为 17 个 dialog entry 逐一补充 `component`（defineAsyncComponent import 路径）和 `propsFactory`
    - 为 15+ 个 trigger entry 补充 `triggerButton` + `triggerVisible` 配置
    - 确保既有消费方（devtools 枚举）不受影响（新增字段全部 optional）
    - _Requirements: 2.3, 3.3, 14.3_

  - [x] 2.2 创建 CycleDialogHost 子 SFC
    - 创建 `audit-platform/frontend/src/views/workpaper-editor/CycleDialogHost.vue`
    - `defineProps<{ projectId: string; wpId: string; wpDetail: WorkpaperDetail; sheetNavActiveId: string; cycleType: CycleTypeFlags; cycleDialogs: CycleDialogsAPI }>()` + `defineEmits<{ 'saved': []; 'applied': [sheet: string] }>()`
    - 使用 `editorDialogConfig` 元数据 + `defineAsyncComponent` 实现配置驱动 v-for 渲染
    - 每个 dialog 通过 `defineAsyncComponent(() => import(...))` lazy 加载
    - defineAsyncComponent onError → ElMessage.error + 关闭 dialog
    - 替代 Shell template line 602-880 的 17 个独立 v-if 块（~279 行 → ~30 行 v-for）
    - `wc -l` ≤ 200 行
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 2.3 创建 CycleTriggerPanel 子 SFC
    - 创建 `audit-platform/frontend/src/views/workpaper-editor/CycleTriggerPanel.vue`
    - `defineProps<{ wpDetail: WorkpaperDetail; cycleType: CycleTypeFlags; cycleDialogs: CycleDialogsAPI; iCycle; gCycle; kCycle; lCycle; mCycle; nCycle; fCycle }>()` + `defineEmits<{ 'open-dialog': [key: string] }>()`
    - 使用 `editorDialogConfig` 元数据中的 trigger 配置实现 v-for 渲染
    - 替代 Shell template line 250-470 中 cycle trigger 按钮区域（~221 行 → ~20 行 v-for）
    - `wc -l` ≤ 150 行
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 2.4 验收卡点 — Phase 2
    - `vue-tsc` 0 errors
    - `vitest --run` 0 failed
    - CycleDialogHost ≤200 / CycleTriggerPanel ≤150
    - Shell 模板中 17 dialog v-if 块 + 15+ trigger 按钮块已替换为 2 个单标签（~500 行净减）
    - _Requirements: 12.5, 14.3, 14.5_

- [x] 3. Phase 3 — Composable 抽取 + EditorBanners
  - [x] 3.1 创建 useEditorSave composable
    - 创建 `audit-platform/frontend/src/composables/useEditorSave.ts`
    - 接收参数 `{ projectId, wpId, wpDetail, univerAPI, dirty, userOverrides, staleImpact, hasPrefillMapping, autoSave }`
    - 封装 7 个 action：onSave / onSubmitForReview / onSyncStructure / onRefreshPrefill / onDownload / onExportPdf / onUpload
    - 返回 `{ saving, submitting, syncLoading, prefillLoading, exportingPdf, onSave, onSubmitForReview, onSyncStructure, onRefreshPrefill, onDownload, onExportPdf, onUpload }`
    - 从 Shell script line 2000-2280 抽取 7 个 action 函数（~285 行）
    - `wc -l` ≤ 300 行
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x] 3.2 创建 useEditorUniver composable
    - 创建 `audit-platform/frontend/src/composables/useEditorUniver.ts`
    - 接收参数 `{ containerRef, projectId, wpId, wpDetail, sheetNavFacade }`
    - 封装 initUniver / dispose / workbook 创建 / DIRTY_COMMAND_PATTERNS 监听 / sheet 切换监听
    - 返回 `{ univerAPI, loading, loadingHint, loadErrorState, loadErrorMessage, dirty, loadedFromXlsx, fileOpenedAt, initUniver, dispose }`
    - 从 Shell script line 1062-1090（DIRTY_COMMAND_PATTERNS）+ line 1710-1960（initUniver 函数）+ line 2310-2400（Sprint 2 helpers）抽取（~280+91=371 行）
    - `wc -l` ≤ 350 行
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 3.3 创建 EditorBanners 子 SFC
    - 创建 `audit-platform/frontend/src/views/workpaper-editor/EditorBanners.vue`
    - `defineProps<{ projectId: string; wpId: string; wpDetail: WorkpaperDetail | null; cycleType: CycleTypeFlags; editLock: EditingLockAPI; prerequisiteBanner: PrerequisiteBannerData | null; staleImpact: StaleImpactAPI; showStaleImpactPanel: boolean }>()`
    - `defineEmits<{ 'conflict-resolved': [id: string, resolution: string]; 'stale-item-click': [item: StaleAffectedItem]; 'jump-to-prereq': []; 'update:showStaleImpactPanel': [val: boolean] }>()`
    - 从 Shell template line 1-22 + 57-85 + 187-210 抽取横幅区（~75 行）
    - 从 Shell script line 1162-1200 + 1342-1420 抽取冲突/信任度/状态机/前置状态/stale ref（~118 行）
    - 内含 ArchivedBanner / AiContentPendingBanner / ConflictBanner + ConflictResolutionPanel / 编辑锁 alert / 前置状态横幅 / stale 影响横条
    - `wc -l` ≤ 200 行
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 3.4 验收卡点 — Phase 3
    - `vue-tsc` 0 errors
    - `vitest --run` 0 failed
    - useEditorSave ≤300 / useEditorUniver ≤350 / EditorBanners ≤200
    - Shell script 中 7 个 action + initUniver + 横幅 ref 已替换为 composable 调用 + 子 SFC 标签
    - _Requirements: 12.5, 14.5_

- [x] 4. Phase 4 — UniverEditorCore 组装
  - [x] 4.1 创建 UniverEditorCore 子 SFC
    - 创建 `audit-platform/frontend/src/views/workpaper-editor/UniverEditorCore.vue`
    - `defineProps<{ projectId: string; wpId: string; wpDetail: WorkpaperDetail; canEdit: boolean; sheetNavFacade: SheetNavFacadeAPI; cycleType: CycleTypeFlags; cycleDialogs: CycleDialogsAPI; iCycle; gCycle; kCycle; lCycle; mCycle; nCycle; fCycle }>()`
    - `defineEmits<{ 'saved': []; 'dirty-change': [dirty: boolean]; 'sheet-switch': [sheetId: string]; 'locate-cell': [payload: { sheetName?: string; cellRef: string }] }>()`
    - 内部实例化 `useEditorUniver()` + `useEditorSave()`
    - 内含 Univer 画布容器（template line 472-510）+ prefill tooltip + cross-ref overlay（line 512-530）+ formula bar（line 532-538）
    - 内含 Sheet 导航（UniverSheetNav + SheetTopTabs）从 template line 250-470 中的 sheet nav 部分
    - 内含 `<CycleTriggerPanel />` 作为左侧栏子组件
    - 内含 `<EditorStatusBar />` 作为底部子组件
    - 内含 autoSave 逻辑（useWorkpaperAutoSave）
    - emit('dirty-change') → Shell 同步 dirty ref（保证 onBeforeRouteLeave 正确）
    - emit('saved') → Shell 刷新 wpDetail
    - `wc -l` ≤ 800 行
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [x] 4.2 验收卡点 — Phase 4
    - `vue-tsc` 0 errors
    - `vitest --run` 0 failed
    - UniverEditorCore ≤800
    - Shell 中 Univer 相关代码（画布 + Sheet 导航 + prefill + crossRef + save + autoSave，~800 行）已替换为单个 `<UniverEditorCore ... />` 标签
    - _Requirements: 4.7, 12.5_

- [x] 5. Phase 5 — Shell 替换收尾
  - [x] 5.1 Shell 容器最终改造
    - 保留 `name: 'WorkpaperEditor'` 路由名，router/index.ts component import 路径不变
    - 实现 `provide(EDITOR_CONTEXT_KEY, { projectId, wpId, wpDetail, canEdit, componentType, cycleType, cycleDialogs, sheetNavActiveId })`
    - 保留 onBeforeRouteLeave dirty 检查逻辑（confirmLeave）
    - 保留路由解析 + 模式分发（HTML → GtWpRenderer / 子编辑器 → EDITOR_MAP / Univer → UniverEditorCore）
    - 保留 useEditorToolbar / useEditorCycles / useEditorMode 实例化
    - 保留 onMounted / onUnmounted lifecycle hooks
    - 保留 CellFormulaDetail 弹窗 + WorkpaperSidePanel 右栏面板
    - Shell 最终骨架：EditorBanners + toolbar + UniverEditorCore + CycleDialogHost + VersionHistoryDrawer + AuditNavDialog + ReviewMarkDialog
    - `wc -l` ≤ 1000 行（预估 ~800 含 style）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_

  - [x] 5.2 创建 useEditorContext composable
    - 创建 `audit-platform/frontend/src/composables/useEditorContext.ts`
    - 定义 `EDITOR_CONTEXT_KEY: InjectionKey<EditorContextData>` Symbol key
    - 定义 `EditorContextData` 接口（projectId / wpId / wpDetail / canEdit / componentType / cycleType / cycleDialogs / sheetNavActiveId）
    - 导出 `createMockEditorContext()` helper 供测试用
    - _Requirements: 1.4, 12.6_

  - [x] 5.3 验收卡点 — Phase 5
    - `vue-tsc` 0 errors
    - `vitest --run` 0 failed
    - `wc -l WorkpaperEditor.vue` ≤ 1000 行
    - Shell + 所有新建子 SFC 总行数 ≤ 3298（2748 × 1.2）
    - 确认 router/index.ts 无需修改
    - 确认 UI 行为不变（按钮位置 / 弹窗交互 / 状态栏信息 / 快捷键）
    - _Requirements: 1.1, 1.2, 1.5, 1.6, 14.2, 14.5_

- [x] 6. Checkpoint — 全量编译与类型检查
  - Ensure all tests pass, ask the user if questions arise.
  - `vue-tsc` 0 errors（全项目）
  - `vitest --run` 0 failed（全项目）
  - 所有文件行数 grep 验证：Shell ≤1000 / UniverEditorCore ≤800 / CycleDialogHost ≤200 / CycleTriggerPanel ≤150 / EditorBanners ≤200 / EditorStatusBar ≤120 / VersionHistoryDrawer ≤120 / AuditNavDialog ≤80 / ReviewMarkDialog ≤120 / useEditorSave ≤300 / useEditorUniver ≤350

- [x] 7. Phase 6 — 测试
  - [x] 7.1 Shell spec：`audit-platform/frontend/src/views/workpaper-editor/__tests__/WorkpaperEditorShell.spec.ts`
    - 测试子 SFC 编排正确性（UniverEditorCore / CycleDialogHost / EditorBanners / VersionHistoryDrawer / AuditNavDialog / ReviewMarkDialog 均渲染）
    - 测试 provide(EDITOR_CONTEXT_KEY) 注入正确
    - 测试 onBeforeRouteLeave dirty=true 时弹 confirm
    - 通过 `provide` 注入 `createMockEditorContext()` mock context
    - _Requirements: 12.3, 12.6_

  - [x] 7.2 子 SFC spec（6 文件）
    - `EditorStatusBar.spec.ts`：默认渲染 + 智能提示展开/收起交互
    - `VersionHistoryDrawer.spec.ts`：默认渲染 + 版本列表加载
    - `AuditNavDialog.spec.ts`：默认渲染 + v-model:visible 切换
    - `ReviewMarkDialog.spec.ts`：默认渲染 + onMarkReview emit 'marked'
    - `CycleDialogHost.spec.ts`：默认渲染 + 配置驱动 dialog 条件渲染
    - `CycleTriggerPanel.spec.ts`：默认渲染 + trigger 按钮点击 emit 'open-dialog'
    - 每个 spec 通过 `provide` 注入 mock context 独立 mount，不依赖 Shell
    - _Requirements: 12.1, 12.6_

  - [x]* 7.3 Composable spec（2 文件）
    - `audit-platform/frontend/src/composables/__tests__/useEditorSave.spec.ts`：核心返回值 + onSave 主要行为
    - `audit-platform/frontend/src/composables/__tests__/useEditorUniver.spec.ts`：核心返回值 + initUniver 主要行为
    - mock httpApi + stub Univer SDK
    - _Requirements: 12.2_

  - [x]* 7.4 Property-based test（fast-check）
    - **Property 1: Config-driven rendering equivalence**
    - **Validates: Requirements 2.3, 3.3**
    - 文件：`audit-platform/frontend/src/views/workpaper-editor/__tests__/property-config-driven-equivalence.spec.ts`
    - `fc.record({ cycleCode: fc.constantFrom('D','E','F','G','H','I','J','K','L','M','N'), wpCodeSuffix: fc.stringMatching(/^\d+(-\d+)?$/), sheetId: fc.string({ minLength: 1, maxLength: 20 }) })`
    - 验证 configDriven dialog 集合 === hardcoded dialog 集合
    - 验证 configDriven trigger 集合 === hardcoded trigger 集合
    - `{ numRuns: 200 }`
    - Tag: `Feature: workpaper-editor-shrink-phase2, Property 1: Config-driven rendering equivalence`

  - [x] 7.5 行数预算断言测试
    - **Validates: Requirements §Property 1（降级为普通断言），ACs 1.6**
    - 文件：`audit-platform/frontend/src/views/workpaper-editor/__tests__/line-budget.spec.ts`
    - `expect(totalLines).toBeLessThanOrEqual(3298)`（2748 × 1.2）
    - 各文件独立断言：Shell ≤1000 / UniverEditorCore ≤800 / CycleDialogHost ≤200 / CycleTriggerPanel ≤150 / EditorBanners ≤200 / EditorStatusBar ≤120 / VersionHistoryDrawer ≤120 / AuditNavDialog ≤80 / ReviewMarkDialog ≤120
    - _Requirements: 1.6, 13.1_

  - [x] 7.6 验收卡点 — 测试全绿
    - `vitest --run src/views/workpaper-editor/__tests__/` 全绿
    - `vitest --run src/composables/__tests__/useEditorSave.spec.ts` 全绿
    - `vitest --run src/composables/__tests__/useEditorUniver.spec.ts` 全绿
    - _Requirements: 12.4, 12.5_

- [x] 8. CI baseline 更新
  - [x] 8.1 更新 `audit-platform/frontend/baselines.json`
    - 替换旧 `WorkpaperEditor-vue-lines: 2555` 为新 6 entry：
      - `workpaper-editor-shell-lines: 1000`
      - `workpaper-editor-univer-core-lines: 800`
      - `workpaper-editor-cycle-dialog-host-lines: 200`
      - `workpaper-editor-cycle-trigger-panel-lines: 150`
      - `workpaper-editor-banners-lines: 200`
      - `workpaper-editor-status-bar-lines: 120`
    - _Requirements: 13.1, 13.2, 13.4_

  - [x] 8.2 更新 `.github/workflows/ci.yml` frontend-build job
    - 在"V3 大型 SFC 行数防膨胀 guard"段落替换旧 WorkpaperEditor 2555 baseline 为新 6 道 only-decrease grep 卡点
    - 添加文件存在性检查（文件被删时显式失败 + 提示「编辑器瘦身文件丢失」）
    - _Requirements: 13.1, 13.2, 13.3, 13.5_

  - [x] 8.3 验收卡点 — CI 配置
    - CI yaml 语法校验通过
    - baselines.json 合法 JSON
    - _Requirements: 13.4_

- [x] 9. Final checkpoint — 确保全部通过
  - Ensure all tests pass, ask the user if questions arise.
  - `vue-tsc` 0 errors
  - `vitest --run` 0 failed
  - 所有文件行数 grep 全部达标
  - CI yaml + baselines.json 合法
  - 确认无新 npm 依赖引入（Requirements 14.6）
  - 确认 router/index.ts 未修改（Requirements 14.2）
  - 确认已有 composable 公开 API 签名未变（Requirements 14.3）

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 拓扑顺序保证每步编译通过：Phase 1 纯展示 → Phase 2 配置驱动 → Phase 3 composable → Phase 4 组装 → Phase 5 Shell 收尾
- editorDialogConfig 扩展为向后兼容（新增字段全部 optional），既有消费方零影响
- UniverEditorCore 内部实例化 useEditorSave + useEditorUniver（ADR-1：save 需要 univerAPI 私有状态）
- CycleTriggerPanel 作为 UniverEditorCore 子组件（ADR-3：布局在 Univer 左侧栏内）
- provide/inject 使用单一 EDITOR_CONTEXT_KEY（ADR-4：与 workpaper-list-shrink 模式一致）
- Property 1（行数总和）降级为普通断言测试；Property 2（配置驱动等价性）保留 fast-check PBT
- 预估总行数：Shell ~800 + UniverEditorCore ~500 + CycleDialogHost ~180 + CycleTriggerPanel ~140 + EditorBanners ~180 + EditorStatusBar ~110 + VersionHistoryDrawer ~100 + AuditNavDialog ~70 + ReviewMarkDialog ~110 + useEditorSave ~280 + useEditorUniver ~300 = ~2770（原 2748，满足 ×1.2 预算 = 3298）
