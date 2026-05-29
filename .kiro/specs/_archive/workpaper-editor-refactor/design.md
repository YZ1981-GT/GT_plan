# Workpaper Editor 拆分重构 — Design

## 整体架构

```
WorkpaperEditor.vue (≤1000 行)
├── useWpDetailGuard(projectId, wpId)        # 统一 wpDetail 加载 + 三态
├── useEditingLock({ resourceId })           # 已有：编辑锁
├── useUniverSheetNav(univerAPIRef)          # 已有：Sheet 导航
├── useDCycleEditor(univerAPIRef, wpDetail)  # 新建：D 循环 dialogs/triggers
├── useECycleEditor(...)                     # 新建：E 循环
├── useFCycleEditor(...)                     # 新建
├── ... (10 个循环 composable)
├── useHybridFlow(univerAPIRef)              # 新建：混合流（保存/提交/版本/校验）
└── 主模板（仅渲染 + 路由分发）
```

## Composable 接口设计

### useWpDetailGuard

```ts
interface WpDetailGuardState {
  state: Ref<'loading' | 'invalid_id' | 'no_index' | 'no_file' | 'ready' | 'error'>
  wpDetail: Ref<WorkpaperDetail | null>
  wpIndex: Ref<WpIndexItem | null>
  workingPaper: Ref<WorkingPaper | null>
  loading: ComputedRef<boolean>
  errorMessage: ComputedRef<string>
  refresh: () => Promise<void>
}

export function useWpDetailGuard(
  projectId: Ref<string>,
  wpId: Ref<string>,
): WpDetailGuardState
```

**实现要点**：
- `onMounted` 先检查 wpId 格式（UUID），不合法直接 `state = 'invalid_id'`
- 调 `getWorkpaper(projectId, wpId)`：
  - 404 → 检查 wpId 是否是 wp_index.id（调 wp-index 查询） → `state = 'no_file'` + 引导生成
  - 200 但 file_path 为空 → `state = 'no_file'`
  - 200 完整 → 加载 wp_index → `state = 'ready'`
- watch `wpId` 变化时自动 refresh
- 暴露 `refresh()` 给保存/提交后手动刷新

### use{X}CycleEditor 通用接口

```ts
interface CycleEditorAPI {
  // 弹窗状态 ref
  dialogs: {
    [key: string]: Ref<boolean>
  }
  // 触发判定 computed（基于 wpCode + 当前 sheet）
  triggers: {
    [key: string]: ComputedRef<boolean>
  }
  // 业务处理函数
  handlers: {
    [key: string]: (...args: any[]) => void | Promise<void>
  }
}
```

**示例 — useDCycleEditor**：

```ts
export function useDCycleEditor(
  univerAPIRef: Ref<FUniver | null>,
  wpDetail: Ref<WorkpaperDetail | null>,
  sheetNav: SheetNavAPI,
): CycleEditorAPI {
  const dialogs = {
    salesIPEDialog: ref(false),
    salesPenetrationDialog: ref(false),
    confirmationDialog: ref(false),
  }

  const triggers = {
    showSalesIPE: computed(() => /^D2/.test(wpDetail.value?.wp_code || '')),
    showPenetration: computed(() => isDCycle(wpDetail.value?.wp_code) && hasD2Sheet(sheetNav)),
  }

  const handlers = {
    onSalesIPEApplied: (data: any) => { /* ... */ },
    onPenetrate: () => { dialogs.salesPenetrationDialog.value = true },
  }

  return { dialogs, triggers, handlers }
}
```

### useHybridFlow

封装"保存 / 提交复核 / 同步公式 / 一键填充 / 版本冲突解决"等通用业务流：

```ts
interface HybridFlowAPI {
  saving: Ref<boolean>
  submitting: Ref<boolean>
  prefillLoading: Ref<boolean>
  syncLoading: Ref<boolean>
  dirty: Ref<boolean>
  onSave: () => Promise<void>
  onSubmitForReview: () => Promise<void>
  onSyncStructure: () => Promise<void>
  onRefreshPrefill: () => Promise<void>
}
```

## GtLoadingOverlay 组件

```vue
<template>
  <div v-if="visible" class="gt-loading-overlay">
    <el-icon class="is-loading" :size="size" :color="color"><Loading /></el-icon>
    <p v-if="text">{{ text }}</p>
  </div>
</template>
<script setup>
defineProps<{
  visible: boolean
  text?: string
  size?: number
  color?: string
}>()
</script>
<style scoped>
.gt-loading-overlay {
  position: absolute; inset: 0; z-index: 100;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: var(--gt-color-bg-white, #fff);
}
</style>
```

**使用模式**（替代顶层 v-if 守卫）：

```vue
<div class="gt-wp-editor">
  <!-- 容器永远渲染，让 ref 挂载触发 init -->
  <div ref="univerContainer" class="gt-wp-editor-univer"></div>

  <!-- 加载蒙层覆盖 -->
  <GtLoadingOverlay :visible="loading" text="加载底稿中..." />
</div>
```

## 渐进式拆分策略

为避免一次性大改引入风险，按 5 个 phase 渐进推进：

### Phase 1 — 基础设施（最低风险）

1. 创建 `useWpDetailGuard` composable（不接入，先单元测试）
2. 创建 `GtLoadingOverlay` 组件（不接入）
3. WorkpaperEditor 顶部 ref 顺序整理（已完成）

### Phase 2 — 单循环试点（D 循环）

1. 创建 `useDCycleEditor` composable
2. 把 WorkpaperEditor 中所有 D 循环相关的 `dialogs / triggers / handlers` 迁过去
3. 主组件引用 `const dCycle = useDCycleEditor(...)` 后访问 `dCycle.dialogs.xxx`
4. Playwright 实测 D 循环底稿（D2 应收账款审定表）所有 dialog 触发

### Phase 3 — 批量迁其他循环

按 D → E → F → H → I → G → K → L → M → N 顺序，每完成一个立即 Playwright 实测对应循环底稿

### Phase 4 — useWpDetailGuard 接入

1. WorkpaperEditor 用 useWpDetailGuard 替换内部 wpDetail 加载逻辑
2. WorkpaperList 详情面板也用 useWpDetailGuard
3. 统一三态 case 的提示文案

### Phase 5 — GtLoadingOverlay 接入 + Playwright 测试

1. 替换 WorkpaperEditor 现有 `.gt-wp-editor-loading-overlay`
2. 写 Playwright 端到端测试 + CI 接入

## 边界与已知陷阱

- **Vue setup ref 顺序铁律**（已沉淀 memory.md）：业务 ref 必须在所有 computed/composable 调用前定义
- **顶层 v-if 守卫拦 init 死锁铁律**（已沉淀 memory.md）：不要在顶层加 v-if=loading 守卫，改 overlay 模式
- **append-to-body :deep() 失效铁律**（已沉淀 memory.md）：dialog 样式必须放全局 style 块

## 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 拆分时漏 dialog/handler | 中 | 高 | grep 全量清单 + checklist 迁移 |
| ref 间 watch 关系破坏 | 中 | 中 | 每个 composable 完成立即测 |
| Playwright 测试不稳定 | 低 | 低 | 用 wait_for + retry |
| 用户在拆分期间使用编辑器 | 低 | 中 | 在 feature/wp-editor-refactor 分支做，merge 前完整测 |
