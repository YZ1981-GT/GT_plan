# D 循环相关代码清单 — WorkpaperEditor.vue

> Task 2.1 grep 全量列出 D 循环相关代码清单
> 执行日期：2026-05-25

## 总结

D 循环在 WorkpaperEditor.vue 中的代码**相对轻量**，与 F/H/I/G/K/L/M/N 循环不同：
- **无专属弹窗（dialog）**：D 循环没有类似 InventoryStocktakeDialog / DepreciationCalcDialog 的专属弹窗组件
- **无专属触发按钮（trigger button）**：D 循环没有在工具栏区域的专属按钮
- D 循环的核心逻辑已通过 `useDSalesCycleSheetGroups` + `useSheetNavFacade` + `useCycleType` 拆分

## 1. 循环类型识别（已迁移到 useCycleType）

| 行号 | 代码 | 状态 |
|------|------|------|
| 1084 | `const isDCycle = cycleType.isDCycle` | ✅ 已迁移到 `useCycleType.ts` |

## 2. Sheet 导航路由（已迁移到 useSheetNavFacade）

| 行号 | 代码 | 状态 |
|------|------|------|
| 1079 | 注释: `// Sprint 2 F5 task 2.6: D 销售循环按 wp_code 路由到 useDSalesCycleSheetGroups` | ✅ 已迁移 |
| 1097 | `const sheetNavFacade = useSheetNavFacade(univerAPIRef, wpDetail, cycleType, scenarioFilter, measurementModelRef)` | ✅ 已迁移 |

**外部文件**：`audit-platform/frontend/src/composables/useDSalesCycleSheetGroups.ts`（D 循环 13 类 sheet 分组规则）

## 3. 前置状态横幅（prerequisiteBanner）— 共享逻辑含 D 分支

| 行号 | 代码 | 说明 |
|------|------|------|
| 27-44 | 模板 `<el-alert v-if="prerequisiteBanner && (... \|\| isDCycle \|\| ...)">` | D 循环参与前置横幅显示条件 |
| 1156 | 注释: `// D-sales-cycle F8 Task 2.19: 扩展支持 D 循环前置状态横幅（B23-1/C2/B51-5）` | |
| 1168 | `if (isDCycle.value) return wpDetail.value?.wp_code \|\| 'D2'` | `prerequisiteCycleCode` computed 中的 D 分支 |
| 982 | `import { usePrerequisiteStatus } from '@/composables/usePrerequisiteStatus'` | 共享 import |
| 1171 | `const prerequisiteStatus = usePrerequisiteStatus(projectId.value, prerequisiteCycleCode.value)` | 共享调用 |

## 4. 审计导航图（AuditNav）— 共享逻辑含 D 分支

| 行号 | 代码 | 说明 |
|------|------|------|
| 67-73 | 模板: `<el-button v-if="hasAuditNav" @click="showAuditNavDrawer = true">🧭 审计导航图</el-button>` | 按钮 |
| 604-638 | 模板: `<el-dialog v-model="showAuditNavDrawer">` + `<WorkpaperAuditNav>` | 全屏对话框 |
| 956 | `import WorkpaperAuditNav from '@/components/workpaper/WorkpaperAuditNav.vue'` | import |
| 1422-1431 | `const showAuditNavDrawer = ref(false)` / `const auditNavFullscreen = ref(true)` / `const hasAuditNav = computed(...)` | 状态 + 计算属性 |
| 1428 | `isDCycle.value \|\| isFCycle.value \|\| isHCycle.value \|\| ...` | hasAuditNav 条件含 D |

## 5. Cross-Ref 事件处理（D 循环原创，后扩展到 H 循环）

| 行号 | 代码 | 说明 |
|------|------|------|
| 940 | `import { eventBus, type CrossRefUpdatedPayload } from '@/utils/eventBus'` | import（共享） |
| 2226-2240 | `function onCrossRefUpdated(payload: CrossRefUpdatedPayload) { ... }` | D0 函证回函 → 刷新 sheet nav + prefill |
| 2242-2255 | `function onSSECrossRefUpdated(payload: SyncEventPayload) { ... }` | SSE → cross-ref:updated 映射（H-F8 扩展） |
| 2271-2274 | `eventBus.on('cross-ref:updated', onCrossRefUpdated)` | onMounted 订阅 |
| 2273-2274 | `eventBus.on('sse:sync-event', onSSECrossRefUpdated)` | onMounted 订阅 |
| 2285-2286 | `eventBus.off('cross-ref:updated', onCrossRefUpdated)` / `eventBus.off('sse:sync-event', onSSECrossRefUpdated)` | onUnmounted 清理 |

## 6. Cross-Ref Overlay（共享 UI，非 D 专属）

| 行号 | 代码 | 说明 |
|------|------|------|
| 573-580 | 模板: `<div class="gt-cross-ref-overlay" v-if="crossRefTags.length > 0">` | 跨模块引用标签覆盖层 |
| 1411 | `const crossRefTags = ref<Array<...>>([])` | 状态 |
| 2564-2588 | CSS: `.gt-cross-ref-overlay` / `.gt-cross-ref-tag` | 样式 |

## 7. Stale Impact 面板（共享逻辑，非 D 专属但 D 循环首创）

| 行号 | 代码 | 说明 |
|------|------|------|
| 949 | `import { useStaleImpact, type StaleAffectedItem } from '@/composables/useStaleImpact'` | import |
| 1064-1066 | `const staleImpact = useStaleImpact(...)` / `const showStaleImpactPanel = ref(false)` | 状态 |
| 159-182 | 模板: Stale 影响范围横条 | UI |
| 1218-1250 | `formatStaleItem` / `staleImpactTagType` / `onStaleItemClick` | 辅助函数 |
| 1912-1934 | `staleImpact.notify(...)` 在 onSave 后调用 | 保存后触发 |
| 2381-2421 | CSS: `.gt-stale-impact-bar` 系列 | 样式 |

## 8. 加载路径注释引用

| 行号 | 代码 | 说明 |
|------|------|------|
| 1606 | `// 2. 直接从后端 GET /xlsx-to-json 加载完整 Univer JSON（D2 PoC 最终方案）` | 注释引用 D2 |

---

## 迁移分析

### D 循环专属代码（可迁移到 useDCycleEditor）

| 类别 | 行数估算 | 说明 |
|------|----------|------|
| `onCrossRefUpdated` handler | ~15 行 | D0 函证回函刷新逻辑（D 循环原创） |
| `prerequisiteCycleCode` D 分支 | 1 行 | 共享 computed 中的一个 if 分支 |
| `hasAuditNav` D 分支 | 1 行 | 共享 computed 中的一个条件 |

### 已迁移到其他 composable 的 D 循环代码

| composable | 内容 |
|------------|------|
| `useCycleType.ts` | `isDCycle` computed（正则 `/^D\d/i`） |
| `useSheetNavFacade.ts` | D 循环 nav 路由（`isDCycle → dCycleNav`） |
| `useDSalesCycleSheetGroups.ts` | D 循环 13 类 sheet 分组规则 |

### 共享逻辑（D 参与但非 D 专属，不应迁移）

| 功能 | 说明 |
|------|------|
| prerequisiteBanner | 所有循环共享，D 只是条件之一 |
| hasAuditNav | 所有循环共享，D 只是条件之一 |
| AuditNav dialog | 所有循环共享 UI |
| Cross-Ref overlay | 通用跨模块引用 UI |
| Stale Impact panel | 通用保存后影响范围 UI |
| `onSSECrossRefUpdated` | H-F8 扩展，已不是 D 专属 |

---

## 结论

D 循环在 WorkpaperEditor.vue 中的**独占代码极少**（约 15-20 行），原因：
1. D 循环没有专属弹窗（设计文档中提到的 salesIPE / salesPenetration / confirmation 弹窗**尚未实现**）
2. D 循环的 sheet 分组逻辑已通过 `useDSalesCycleSheetGroups` + `useSheetNavFacade` 完全外置
3. D 循环的类型识别已通过 `useCycleType` 外置
4. 剩余代码主要是共享逻辑中的 D 分支（prerequisite / auditNav / cross-ref）

### 对 Task 2.2 的建议

创建 `useDCycleEditor` composable 时，可迁移的内容：
1. **`onCrossRefUpdated` handler**（D 循环原创的函证回函刷新逻辑）
2. **D 循环特有的 trigger 判定**（如果未来添加 D 专属弹窗）
3. **prerequisiteCycleCode 的 D 分支逻辑**（可选，因为是共享 computed 的一部分）

当前 D 循环的"穿透/IPE/勾稽"弹窗（设计文档 design.md 中描述的 `salesIPEDialog` / `salesPenetrationDialog` / `confirmationDialog`）在 WorkpaperEditor.vue 中**不存在**——这些是 Task 2.2 需要新建的功能，而非从现有代码迁移。
