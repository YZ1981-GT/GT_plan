# Implementation Plan: workpaper-list-shrink

## Overview

按 design §4.1 拓扑顺序实施：先无依赖的共享 composable → 薄包装子 SFC（Graph/Matrix/Board/Lifecycle）→ 最复杂的 Workbench → Shell 容器收尾 → 测试 → CI → 清理。每步收尾跑 vue-tsc + vitest 双卡点。

## Tasks

- [ ] 1. 创建 useWorkpaperListContext composable
  - [x] 1.1 创建 `audit-platform/frontend/src/composables/useWorkpaperListContext.ts`
    - 定义 `WP_LIST_CONTEXT_KEY: InjectionKey<WpListContext>` Symbol key
    - 定义 `WpListContextData` 接口（~25 个共享 reactive state：wpIndex/wpList/treeData/loading/projectId/currentYear/viewMode/searchKeyword/filterCycle/filterStatus/filterAssignee/selectedWpId/totalProgress/roleViewPreset 等）
    - 定义 `WpListContextActions` 接口（fetchWpIndex/refreshAfterMutate）
    - 定义 `WpListContext = WpListContextData & WpListContextActions`
    - 定义 `WpChildProps` 接口（projectId: string, year: number）
    - 定义 `WpChildEmits` 接口（navigate/refresh/mutate）
    - 定义 `MutatePayload` 接口（action + data）
    - 导出 `createMockContext()` helper 供测试用
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [x] 1.2 验收卡点
    - `vue-tsc` 0 errors
    - `vitest --run` 0 failed
    - `wc -l useWorkpaperListContext.ts` ≤ 150 行
    - _Requirements: 6.5, 6.6_

- [ ] 2. WorkpaperDependencyGraph 薄包装
  - [x] 2.1 创建 `audit-platform/frontend/src/views/workpaper-list/WorkpaperDependencyGraph.vue`
    - 从 WorkpaperList.vue template line 187-192 抽取已有 `<WorkpaperDependencyGraph>` 组件引用
    - `defineProps<WpChildProps>()`
    - `defineEmits<WpChildEmits>()`
    - `inject(WP_LIST_CONTEXT_KEY)` + ReferenceError 守卫
    - 内部 lazy import D3：`const d3 = await import('d3-force')`
    - 桥接已有 `WorkpaperDependencyGraph.vue` 组件（路径 `components/workpaper/WorkpaperDependencyGraph.vue`）
    - _Requirements: 2.4, 3.1, 3.2, 3.3, 3.6, 7.2_
  - [x] 2.2 验收卡点
    - `vue-tsc` 0 errors
    - `wc -l WorkpaperDependencyGraph.vue` ≤ 80 行
    - WorkpaperList.vue 行数变化：3463 → ~3455（删除 graph 相关内联代码 ~8 行）
    - _Requirements: 2.7, 8.2_

- [ ] 3. WorkpaperDelegationMatrix 薄包装
  - [x] 3.1 创建 `audit-platform/frontend/src/views/workpaper-list/WorkpaperDelegationMatrix.vue`
    - 从 WorkpaperList.vue template line 194-202 抽取已有 `<WorkpaperAssignmentMatrix>` 组件引用
    - `defineProps<WpChildProps>()`
    - `defineEmits<WpChildEmits>()`
    - `inject(WP_LIST_CONTEXT_KEY)` + ReferenceError 守卫
    - 桥接已有 `WorkpaperAssignmentMatrix.vue` 组件
    - 角色隐藏逻辑由 Shell Tab 控制（本 SFC 不做角色判断）
    - _Requirements: 2.3, 3.1, 3.2, 3.5, 4.3, 4.5_
  - [x] 3.2 验收卡点
    - `vue-tsc` 0 errors
    - `wc -l WorkpaperDelegationMatrix.vue` ≤ 80 行
    - WorkpaperList.vue 行数变化：~3455 → ~3447（删除 matrix 相关内联代码 ~8 行）
    - _Requirements: 2.7, 8.2_

- [ ] 4. WorkpaperBoardView 薄包装
  - [x] 4.1 创建 `audit-platform/frontend/src/views/workpaper-list/WorkpaperBoardView.vue`
    - 从 WorkpaperList.vue template line 100-108 抽取已有 `<WorkpaperKanban>` 组件引用
    - `defineProps<WpChildProps>()`
    - `defineEmits<WpChildEmits>()`
    - `inject(WP_LIST_CONTEXT_KEY)` + ReferenceError 守卫
    - 桥接已有 `WorkpaperKanban.vue` 组件 + 拖拽逻辑（script ~30 行）
    - _Requirements: 2.2, 3.1, 3.2, 3.5_
  - [x] 4.2 验收卡点
    - `vue-tsc` 0 errors
    - `wc -l WorkpaperBoardView.vue` ≤ 150 行
    - WorkpaperList.vue 行数变化：~3447 → ~3410（删除 kanban 相关内联代码 + 拖拽逻辑 ~37 行）
    - _Requirements: 2.7, 8.2_

- [ ] 5. WorkpaperLifecycleView 薄包装
  - [x] 5.1 创建 `audit-platform/frontend/src/views/workpaper-list/WorkpaperLifecycleView.vue`
    - 从 WorkpaperList.vue template line 176-185 抽取已有 `<WorkpaperLifecycleView>` 组件引用
    - `defineProps<WpChildProps>()`
    - `defineEmits<WpChildEmits>()`
    - `inject(WP_LIST_CONTEXT_KEY)` + ReferenceError 守卫
    - 桥接已有 `WorkpaperLifecycleView.vue` 组件 + lifecycle 相关 computed（script line 2218-2260 ~42 行）
    - _Requirements: 2.1, 3.1, 3.2, 4.7_
  - [x] 5.2 验收卡点
    - `vue-tsc` 0 errors
    - `wc -l WorkpaperLifecycleView.vue` ≤ 120 行
    - WorkpaperList.vue 行数变化：~3410 → ~3360（删除 lifecycle 相关内联代码 ~50 行）
    - _Requirements: 2.7, 8.2_

- [ ] 6. WorkpaperWorkbenchView 新建（最复杂）
  - [x] 6.1 Template 抽取
    - 从 WorkpaperList.vue template line 46-174（list/workbench 区域）+ line 203-454（guide 区域 252 行）抽取到新 SFC template
    - 保留 v-if 切换 list/workbench/guide 三个子模式的逻辑
    - 替换直接引用的 reactive state 为 `ctx.xxx` inject 路径
    - _Requirements: 2.5, 5.1, 5.2_
  - [x] 6.2 Script 抽取
    - 迁移 Workbench 私有 reactive state（~40 个：wbPage/wbPageSize/pagedWorkbenchData/workbenchTableData/guideFocusCycle/guideCycleDetails 等）
    - 迁移上传/导入/批注/复核/委派/门禁/右键菜单/在线编辑相关 state
    - 删除 dead code（~14 个：showSodDialog/fineChecksLoading/showWpImport 等，design §1.4 已标注）
    - 写操作走 `emit('mutate', payload)` 不直调 service
    - _Requirements: 3.5, 4.6_
  - [x] 6.3 Style 迁移
    - 从 WorkpaperList.vue `<style scoped>` line 3327-3463 中迁移 Workbench 相关样式
    - 保留 Shell 级样式在原文件
    - _Requirements: 2.5_
  - [x] 6.4 验收卡点
    - `vue-tsc` 0 errors
    - `wc -l WorkpaperWorkbenchView.vue` ≤ 700 行（预估 ~600）
    - WorkpaperList.vue 行数变化：~3360 → ~1500（删除 list/workbench/guide template + 私有 script + 部分 style）
    - _Requirements: 2.5, 2.7_

- [ ] 7. Shell 容器改造
  - [x] 7.1 替换 WorkpaperList.vue 内容为 Shell 实现
    - 保留 `name: 'WorkpaperList'` 组件名
    - 实现 `<el-radio-group>` Tab 切换栏 + 角色可见性（admin/partner/manager 全 5 Tab，auditor/qc 隐藏 DelegationMatrix；reviewer 是项目级 permission_level 不影响 Tab）
    - 实现 `<keep-alive :include="visitedViews" :max="5">` + `<component :is="currentViewComponent">`
    - 实现 `defineAsyncComponent(() => import('./workpaper-list/...'))` 5 子 SFC lazy import
    - 实现 `provide(WP_LIST_CONTEXT_KEY, useWorkpaperListContext())` 共享 context 注入
    - 实现 viewMode watch + `router.replace` 更新 URL（非 push）
    - 实现非法 viewMode `logger.warn` + 回退 workbench
    - 实现 7 viewMode 白名单（含 guide）→ 5 子 SFC 路由表（list/workbench/guide → Workbench；kanban → Board；lifecycle → Lifecycle；graph → DependencyGraph；matrix → DelegationMatrix）
    - 实现 `onMutate` 统一 service 调用（批量委派 line 1626 / 链路执行 line 2163）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 4.1, 4.2, 4.3, 4.4, 4.5, 4.8, 5.1, 5.2, 5.3, 5.4, 5.5_
  - [x] 7.2 验收卡点
    - `vue-tsc` 0 errors
    - `vitest --run` 0 failed
    - `wc -l WorkpaperList.vue` ≤ 1000 行（预估 ~800）
    - 确认 `router/index.ts` 无需修改（component import 路径不变）
    - _Requirements: 1.2, 2.6, 5.6, 7.1_

- [x] 8. Checkpoint — 确保编译与类型检查通过
  - Ensure all tests pass, ask the user if questions arise.
  - `vue-tsc` 0 errors（全项目）
  - `vitest --run` 0 failed（全项目）
  - 6 文件行数 grep 验证：Shell ≤1000 / 5 子 SFC 各 ≤700

- [ ] 9. Vitest 测试
  - [x] 9.1 Shell spec：`audit-platform/frontend/src/views/workpaper-list/__tests__/WorkpaperListShell.spec.ts`
    - 测试 7 个 viewMode 切换（list/kanban/workbench/lifecycle/graph/matrix/guide → 正确子 SFC 渲染；list/workbench/guide 都映射 Workbench）
    - 测试非法 viewMode 回退到 workbench
    - 测试 keep-alive 实例复用（切走再切回 mount 次数 = 1）
    - 测试角色 Tab 可见性（auditor / qc 隐藏 DelegationMatrix；admin/partner/manager 全 5 Tab）
    - 通过 `provide` 注入 `createMockContext()` mock context
    - _Requirements: 6.2, 6.4_
  - [x] 9.2 5 子 SFC spec（各 1 文件）
    - `WorkpaperWorkbenchView.spec.ts`：默认渲染 + 搜索交互
    - `WorkpaperBoardView.spec.ts`：默认渲染 + 拖拽 emit mutate
    - `WorkpaperLifecycleView.spec.ts`：默认渲染 + 推进按钮
    - `WorkpaperDependencyGraph.spec.ts`：默认渲染 + D3 lazy import
    - `WorkpaperDelegationMatrix.spec.ts`：默认渲染 + 委派 emit mutate
    - 每个 spec 通过 `provide` 注入 mock context 独立 mount
    - _Requirements: 6.1, 6.4_
  - [ ]* 9.3 Property 2 fast-check：路由切换 mount 次数
    - **Property 2: 路由切换 lazy import + keep-alive 不重复 mount**
    - **Validates: Requirements 7.3, 1.8**
    - 文件：`audit-platform/frontend/src/views/workpaper-list/__tests__/property-route-switch.spec.ts`
    - `fc.array(fc.constantFrom('list','kanban','workbench','lifecycle','graph','matrix','guide'), { minLength: 1, maxLength: 100 })`
    - 验证 `sum(mount_counts.values()) <= 5` 且每个已访问 SFC mount 恰好 1 次（list/workbench/guide 共享 Workbench SFC 不重复 mount）
  - [x] 9.4 行数预算断言测试（requirements §Property 1 已降级为普通断言）
    - **Validates: Requirements §Property 1（降级条款），ACs 2.6, 2.7, 8.1, 8.2**
    - 文件：`audit-platform/frontend/src/views/workpaper-list/__tests__/line-budget.spec.ts`
    - `expect(totalLines).toBeLessThanOrEqual(4156)`（3463 × 1.2）
    - 6 文件各自独立断言（Shell ≤1000 / 5 子 SFC 各 ≤700）
    - **此任务非可选**（status `[ ]`），与 CI baseline 双保险防退化
  - [x] 9.5 验收卡点
    - `vitest --run src/views/workpaper-list/__tests__/` 全绿
    - _Requirements: 6.5_

- [ ] 10. CI baseline 扩展
  - [x] 10.1 更新 `audit-platform/frontend/baselines.json`
    - 新增 6 entry：`workpaper-list-shell-lines: 1000` / `workpaper-list-workbench-view-lines: 700` / `workpaper-list-board-view-lines: 700` / `workpaper-list-lifecycle-view-lines: 700` / `workpaper-list-dependency-graph-lines: 700` / `workpaper-list-delegation-matrix-lines: 700`
    - 替换旧 `WorkpaperList.vue=3238` baseline 为新 6 entry
    - _Requirements: 8.1, 8.2, 8.4_
  - [x] 10.2 更新 `.github/workflows/ci.yml` frontend-build job
    - 在"V3 大型 SFC 行数防膨胀 guard"段落新增 6 道 only-decrease grep 卡点
    - 添加文件存在性检查（文件被删时显式失败 + 提示「god component 拆分文件丢失」）
    - 替换旧 WorkpaperList.vue 3238 baseline
    - _Requirements: 8.1, 8.2, 8.3, 8.5_
  - [x] 10.3 验收卡点
    - CI yaml 语法校验通过
    - baselines.json 合法 JSON
    - _Requirements: 8.4_

- [ ]* 11. Playwright e2e 回归
  - [x]* 11.1 创建或扩展 `audit-platform/frontend/e2e/workpaper-list-views.spec.ts`
    - 5 子视图各 1 条主路径：进入 → 渲染就绪 → 1 次主交互 → 切换离开
    - Workbench：进入默认视图 → 表格渲染 → 搜索 → 切到 kanban
    - Board：切到 kanban → 看板渲染 → 拖拽卡片 → 切到 lifecycle
    - Lifecycle：切到 lifecycle → 阶段渲染 → 点击推进 → 切到 graph
    - DependencyGraph：切到 graph → D3 图渲染 → 节点交互 → 切到 matrix
    - DelegationMatrix：切到 matrix → 矩阵渲染 → 委派操作 → 切回 workbench
    - _Requirements: 6.3_
  - [x]* 11.2 验收卡点
    - 需 dev server 运行（`start-dev.bat`），按 conventions 拆独立 spec 执行
    - _Requirements: 6.3, 7.4_

- [x]* 12. 清理与文档收口（已于 2026-05-28 三件套对齐时完成）
  - [x]* 12.1 删除 `.kiro/specs/workpaper-list-shrink/README.md`（已删，避免双源）
    - _Requirements: 9.1_
  - [x]* 12.2 更新 `.kiro/specs/INDEX.md`
    - §2.3 已移除 `workpaper-list-shrink` 占位待办行
    - §2.1 已登记完成度 `0/13 📝`（待 Task 1 启动）
    - _Requirements: 8.6, 9.2_

- [x] 13. Final checkpoint — 确保全部通过
  - Ensure all tests pass, ask the user if questions arise.
  - `vue-tsc` 0 errors
  - `vitest --run` 0 failed
  - 6 文件行数 grep 全部达标
  - CI yaml + baselines.json 合法

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 拓扑顺序保证每步编译通过：composable → 薄包装（无内联代码依赖）→ Workbench（最复杂）→ Shell（收尾集成）
- 已有 4 个子组件可复用（WorkpaperKanban/WorkpaperLifecycleView/WorkpaperDependencyGraph/WorkpaperAssignmentMatrix），薄包装层仅做 props/emits 桥接
- Property 1 降级为普通断言（ADR-4），Property 2 保留 fast-check PBT
- 预估总行数：Shell ~800 + Workbench ~600 + Board ~150 + Lifecycle ~120 + Graph ~80 + Matrix ~80 = ~1830（原 3463，净减 47%）
