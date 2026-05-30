# Design Document — workpaper-list-shrink

> **Spec 类型**：feature（重构性 P0）
> **关联**：requirements.md（10 user stories / 60 ACs / 2 PBT）
> **起草日期**：2026-05-28
> **前置探测**：grep 实测 WorkpaperList.vue 3463 行 / 79 reactive state / 7 viewMode / 2 service 写调用 / 0 keep-alive

---

## 1. 当前现状（实测 2026-05-28）

### 1.1 文件度量

| 维度 | 实测值 |
|---|---|
| 总行数 | **3463** |
| `<template>` | line 1–1010（1010 行） |
| `<script setup>` | line 1012–3325（2313 行） |
| `<style scoped>` | line 3327–3463（136 行） |
| reactive state（ref/computed/reactive） | **79 个** |
| service 写调用（api.post/put/delete） | **2 处**（line 1626 批量委派 / line 2163 链路执行） |
| keep-alive | **0**（当前无 keep-alive） |

### 1.2 viewMode 实际枚举（7 个，requirements 漏写 guide）

| viewMode | template 行号 | 内联代码量 | 已抽子组件？ |
|---|---|---|---|
| `list` | 46/80/88 + 树面板 | 与 workbench 共享 | 否（内联） |
| `kanban` | 100–108 | 8 行 | ✅ `WorkpaperKanban.vue` |
| `workbench` | 109–174 | 65 行 | 否（内联） |
| `lifecycle` | 176–185 | 9 行 | ✅ `WorkpaperLifecycleView.vue` |
| `graph` | 187–192 | 5 行 | ✅ `WorkpaperDependencyGraph.vue` |
| `matrix` | 194–202 | 8 行 | ✅ `WorkpaperAssignmentMatrix.vue` |
| `guide` | 203–454 | **252 行** | 否（内联） |

**关键发现**：kanban / lifecycle / graph / matrix 4 个 viewMode 已有独立子组件，只是 Shell 层仍内联 v-if 切换 + 79 个 reactive state 全部堆在一个 setup 里。真正需要"抽取"的内联代码集中在 `list + workbench + guide` 三块。

### 1.3 角色枚举（grep 实测修正）

**后端 UserRole**（`backend/app/models/base.py:16`）：
```
admin / partner / manager / auditor / qc / readonly
```

**前端 ROLE_PERMISSIONS**（`composables/usePermission.ts:76`）：
```
partner / manager / auditor / eqcr（项目级）
```
- `admin` 走 `role === 'admin'` 硬判断（不在 ROLE_PERMISSIONS 字典里）
- `assistant` 是 requirements 凭印象写的错误名，**真实名 = `auditor`**
- `reviewer` 不是独立角色，是 `ProjectUser.permission_level = 'review'` 项目级权限
- `qc` 是独立角色但 WorkpaperList 不做 qc 特殊分支

**修正 requirements Req 4**：角色应为 `admin / partner / manager / auditor / qc`（5 个系统角色），其中 `auditor` 隐藏 DelegationMatrix Tab。`reviewer` 不是角色而是项目级权限，不影响 Tab 可见性。

### 1.4 reactive state 三分类

**进 useWorkpaperListContext（共享，Shell provide）— 约 25 个**：
- 核心数据：`wpIndex / wpList / treeData / loading / projectId / currentYear / projectName`
- 筛选：`searchKeyword / filterCycle / filterStatus / filterAssignee / showTrimmedChecked / viewMode`
- 选中：`selectedWpId / selectedWpIds`（批量操作）
- 进度：`totalProgress / filteredProgress / hasFilter`
- 角色：`roleViewPreset / roleViewWpList / roleViewManualFilters`

**下沉到子 SFC（各自私有）— 约 40 个**：
- Workbench 私有：`wbPage / wbPageSize / pagedWorkbenchData / workbenchTableData / workbenchProgressCollapsed / cycleSummary`
- Guide 私有：`guideFocusCycle / guideCycleDetails / _guideExpanded`
- 上传/导入：`uploadLoading / parseLoading / uploadDialogVisible / uploadStep / pendingWpId / pendingNewVersion`
- 批注/复核：`showAddAnnotation / newAnnotation / annotationFilter / filteredAnnotations / unresolvedCount / unconfirmedAiCount / showRejectDialog / rejectReason / rejectingWpId / isReviewable`
- 委派：`showAssignDialog / assignLoading / showBatchAssign / batchAssignWpList`
- 门禁/链路：`hasTrialBalance / chainLoading / hasBlocking / blockingReasons / gateTraceId`
- 右键菜单：`wpCtxVisible / wpCtxX / wpCtxY`
- 在线编辑：`onlineEditAvailable / onlineEditEnabled / onlineEditMaturity`

**可删除（dead code / 冗余）— 约 14 个**：
- `showSodDialog / sodConflictType / sodPolicyCode / sodTraceId`（SoD 对话框已迁移到 Shell 级 confirm.ts）
- `fineChecksLoading / fineChecksPassed / fineChecksPassedCount / showTsjDetail`（精细化检查已迁移到 WorkpaperEditor）
- `showWpImport / qcLoading / downloadLoading / submitLoading`（loading 状态应合并到 useFirstLoad 或各子 SFC 私有）
- `showReplyDialog / replyContent`（复核回复已迁移到 ReviewWorkbench）


## 2. 架构设计

### 2.1 模块拓扑

```
router/index.ts
  └── path: 'projects/:projectId/workpapers'
      └── component: WorkpaperList.vue (Shell)
              │
              ├── provide(WP_LIST_CONTEXT_KEY, useWorkpaperListContext())
              │
              ├── <el-radio-group> Tab 切换 → viewMode ref
              │
              └── <keep-alive :include="visitedViews">
                    <component :is="currentViewComponent" v-bind="childProps" />
                  </keep-alive>
                        │
          ┌─────────────┼─────────────────────────────────────┐
          │             │             │             │          │
  Workbench    Lifecycle      Board      DependencyGraph  DelegationMatrix
  (list/wb/    (已有组件     (已有组件    (已有组件         (已有组件
   guide 收敛)  复用)         复用)        复用)             复用)
```

### 2.2 viewMode → 子 SFC 路由表

| route.query.view | 映射子 SFC | lazy import 路径 |
|---|---|---|
| `list` / `workbench` / `guide` / 缺省 / 非法值 | `WorkpaperWorkbenchView.vue` | `./workpaper-list/WorkpaperWorkbenchView.vue` |
| `kanban` | `WorkpaperBoardView.vue` | `./workpaper-list/WorkpaperBoardView.vue` |
| `lifecycle` | `WorkpaperLifecycleView.vue` | `./workpaper-list/WorkpaperLifecycleView.vue` |
| `graph` | `WorkpaperDependencyGraph.vue` | `./workpaper-list/WorkpaperDependencyGraph.vue` |
| `matrix` | `WorkpaperDelegationMatrix.vue` | `./workpaper-list/WorkpaperDelegationMatrix.vue` |

### 2.3 数据流方向

```
Shell (WorkpaperList.vue)
  │
  ├── onMounted: fetchWpIndex() → wpIndex / wpList / treeData
  │
  ├── provide(WP_LIST_CONTEXT_KEY, { wpList, loading, filters, actions })
  │
  └── <ChildSFC
        :project-id="projectId"
        :year="currentYear"
        @navigate="onNavigate"
        @refresh="fetchWpIndex"
        @mutate="onMutate"
      />

子 SFC 内部：
  const ctx = inject(WP_LIST_CONTEXT_KEY)!  // 共享只读数据
  // 写操作 → emit('mutate', { action: 'updateStatus', payload: {...} })
  // Shell onMutate → 调 service → 刷新 ctx
```

### 2.4 keep-alive 与 lazy import 协作

```
时序：
1. Shell mount → fetchWpIndex → provide context
2. 用户切 Tab → viewMode 变 → computed currentViewComponent 切换
3. 首次访问某 viewMode → defineAsyncComponent 触发 chunk 下载
4. chunk 加载完 → 子 SFC mount → inject context → 渲染
5. 用户切走 → keep-alive deactivated（实例保留）
6. 用户切回 → keep-alive activated（复用实例，不重新 mount）
```

## 3. 接口契约（TS 类型预演）

### 3.1 useWorkpaperListContext 返回值

```typescript
// composables/useWorkpaperListContext.ts
import type { InjectionKey, Ref, ComputedRef } from 'vue'

export interface WpListContextData {
  // reactive 数据
  wpIndex: Ref<WpIndexItem[]>
  wpList: Ref<WpListItem[]>
  treeData: Ref<TreeNode[]>
  loading: Ref<boolean>
  projectId: ComputedRef<string>
  currentYear: ComputedRef<number>
  projectName: Ref<string>
  viewMode: Ref<string>
  // 筛选
  searchKeyword: Ref<string>
  filterCycle: Ref<string>
  filterStatus: Ref<string>
  filterAssignee: Ref<string>
  showTrimmedFilter: ComputedRef<string>
  // 选中
  selectedWpId: Ref<string>
  // 进度
  totalProgress: ComputedRef<ProgressInfo>
  // 角色
  roleViewPreset: ComputedRef<RolePreset>
  roleViewWpList: ComputedRef<WpListItem[]>
}

export interface WpListContextActions {
  fetchWpIndex: () => Promise<void>
  refreshAfterMutate: () => Promise<void>
}

export type WpListContext = WpListContextData & WpListContextActions

export const WP_LIST_CONTEXT_KEY: InjectionKey<WpListContext> = Symbol('WpListContext')
```

### 3.2 子 SFC props/emits 统一接口

```typescript
// 5 子 SFC 共用 props 接口
export interface WpChildProps {
  projectId: string
  year: number
}

// 5 子 SFC 共用 emits
export interface WpChildEmits {
  (e: 'navigate', wpId: string): void
  (e: 'refresh'): void
  (e: 'mutate', payload: MutatePayload): void
}

export interface MutatePayload {
  action: 'updateStatus' | 'assign' | 'batchAssign' | 'delegate' | 'reorder'
  data: Record<string, unknown>
}
```

### 3.3 子 SFC inject 模板

```typescript
// 每个子 SFC 内部
import { inject } from 'vue'
import { WP_LIST_CONTEXT_KEY, type WpListContext } from '@/composables/useWorkpaperListContext'

const ctx = inject(WP_LIST_CONTEXT_KEY)
if (!ctx) throw new ReferenceError('WpListContext not provided — must be used inside WorkpaperList Shell')
```

## 4. 实施代码锚定

### 4.1 子 SFC 抽取源代码区间

| 子 SFC | 来源 | 预估行数 |
|---|---|---|
| **WorkpaperWorkbenchView** | template line 46-174 + line 203-454（guide 收敛）+ script 相关 computed/ref（约 line 1449-1850） | ~600 行 |
| **WorkpaperBoardView** | template line 100-108（已有 `<WorkpaperKanban>` 引用）+ script 拖拽逻辑（约 30 行） | ~150 行（薄包装，复用已有 WorkpaperKanban.vue） |
| **WorkpaperLifecycleView** | template line 176-185（已有组件引用）+ script lifecycle 相关 computed（约 line 2218-2260） | ~120 行（薄包装，复用已有 WorkpaperLifecycleView.vue 798 行组件） |
| **WorkpaperDependencyGraph** | template line 187-192（已有组件引用）+ script graph 相关 ref（约 10 行） | ~80 行（薄包装） |
| **WorkpaperDelegationMatrix** | template line 194-202（已有组件引用）+ script matrix 相关 ref（约 10 行） | ~80 行（薄包装） |

**预估总行数**：Shell ~800 + Workbench ~600 + Board ~150 + Lifecycle ~120 + Graph ~80 + Matrix ~80 = **~1830 行**（原 3463 行 → 拆后 1830 行，净减 47%，满足 ×1.2 预算 = 4156）

### 4.2 Shell 最终骨架（伪代码）

```vue
<template>
  <!-- Tab 切换栏 -->
  <div class="gt-wp-list-shell">
    <GtPageHeader>...</GtPageHeader>
    <el-radio-group v-model="viewMode" @change="onViewChange">
      <el-radio-button v-for="tab in visibleTabs" :key="tab.value" :value="tab.value">
        {{ tab.label }}
      </el-radio-button>
    </el-radio-group>

    <!-- 子 SFC 渲染区 -->
    <keep-alive :include="visitedViews" :max="5">
      <component
        :is="currentViewComponent"
        :key="viewMode"
        :project-id="projectId"
        :year="currentYear"
        @navigate="onNavigate"
        @refresh="fetchWpIndex"
        @mutate="onMutate"
      />
    </keep-alive>
  </div>
</template>

<script setup lang="ts">
// ~800 行：路由解析 + Tab 可见性 + lazy import map + provide context + onMutate 统一 service 调用
</script>
```

### 4.3 共享 composable 实现要点

- **Symbol key**：`WP_LIST_CONTEXT_KEY = Symbol('WpListContext')`，避免字符串 key 冲突
- **防重复 fetch**：`fetchWpIndex` 内部 `if (loading.value) return`（debounce 守卫）
- **provide 时机**：Shell `onMounted` 之前 `provide`（setup 顶层同步执行），子 SFC `inject` 时 context 已就绪
- **响应式穿透**：provide 的是 Ref/ComputedRef 本身（不是 `.value`），子 SFC 直接 `.value` 读取保持响应式

## 5. CI baseline 字段命名

按 conventions §CI Baseline 规约 `{property}-{format}-{scope}` 格式：

| 字段名 | 初始值 | 说明 |
|---|---|---|
| `workpaper-list-shell-lines` | 1000 | Shell 行数上限 |
| `workpaper-list-workbench-view-lines` | 700 | Workbench 子 SFC |
| `workpaper-list-board-view-lines` | 700 | Board 子 SFC |
| `workpaper-list-lifecycle-view-lines` | 700 | Lifecycle 子 SFC |
| `workpaper-list-dependency-graph-lines` | 700 | DependencyGraph 子 SFC |
| `workpaper-list-delegation-matrix-lines` | 700 | DelegationMatrix 子 SFC |

**写入位置**：`.github/workflows/ci.yml` `frontend-build` job 的"V3 大型 SFC 行数防膨胀 guard"段落，与既有 `WorkpaperList.vue=3238`（旧 baseline）替换为新 6 entry。

## 6. ADR（架构决策记录）

### ADR-1：Shell 替换原文件 vs 新建 WorkpaperListShell.vue

**决策**：替换原文件（保留 `WorkpaperList.vue` 文件名）。

**理由**：
- router/index.ts line 105 `component: () => import('@/views/WorkpaperList.vue')` 不需改动
- git history 连续（blame 可追溯到拆分前的每一行）
- 浏览器书签 / 外部链接 / 其他组件 `router.push({ name: 'WorkpaperList' })` 零破坏

**备选**：新建 `WorkpaperListShell.vue` + 修改 router import → 需改 router + 断 git history + 可能遗漏其他引用点。

### ADR-2：list / workbench / guide 收敛为 1 个 Workbench 子 SFC

**决策**：`list` / `workbench` / `guide` 三个 viewMode 都映射到 `WorkpaperWorkbenchView.vue`。

**理由**：
- `list` 与 `workbench` 业务语义同源（都是"底稿列表 + 工具栏"，仅展示密度不同）
- `guide`（手册视图 252 行）是 workbench 的折叠面板（用户手册/流程图/循环列表），不值得独立 SFC
- 收敛后 5 子 SFC 而非 7 个，降低 keep-alive 缓存压力 + Tab 数量

**备选**：guide 独立为第 6 个 SFC → 增加 1 个 chunk + 1 个 Tab + 1 个 CI baseline entry，收益不大。

### ADR-3：useWorkpaperListContext 用 provide/inject vs Pinia store

**决策**：provide/inject（组件树作用域）。

**理由**：
- WorkpaperList 的 reactive state 生命周期 = 路由 `/projects/:id/workpapers` 存活期间，离开路由应销毁
- Pinia store 是全局单例，离开路由后数据仍驻留内存（需手动 $reset），且跨项目切换时可能残留旧数据
- provide/inject 天然跟随 Shell 组件生命周期，unmount 时自动 GC
- 子 SFC 测试时通过 `provide` mock 注入即可，不需要 mock 整个 Pinia store

**备选**：Pinia `useWorkpaperListStore` → 需手动 $reset + 跨项目残留风险 + 测试需 `createPinia()`。

### ADR-4：Property 1 PBT 形式修订（避免恒真断言反模式）

**决策**：将 Property 1 从 hypothesis PBT 降级为**普通断言测试**（vitest snapshot 守门），保留 fast-check Property 2 作为唯一 PBT。

**理由**：
- 原 Property 1（"6 文件行数总和 ≤ 3463×1.2"）本质是静态 grep 断言，hypothesis `max_examples=N` 无 fuzzing 价值（输入空间 = 6 个固定文件路径，无随机性）
- 按 conventions §PBT 反模式清单"恒真断言"判定：strategy 已强制满足约束（文件路径固定），测试永真
- 降级为 vitest `test('line budget', () => { expect(sum).toBeLessThanOrEqual(4156) })` 更诚实
- CI 的 6 道 only-decrease grep 已覆盖同等防退化能力

**修订**：requirements.md Property 1 标注为"降级为普通断言测试"，不再声称 hypothesis PBT。

### ADR-5：keep-alive 缓存策略

**决策**：`<keep-alive :include="visitedViews" :max="5">`

**理由**：
- `:include` 动态数组：只缓存用户已访问过的子 SFC（首次访问前不占内存）
- `:max="5"`：最多缓存 5 个（恰好等于子 SFC 总数），超出时 LRU 淘汰最久未访问的
- 不用 `:exclude`（所有子 SFC 都值得缓存，DependencyGraph D3 实例化成本高）
- 内存估算：5 子 SFC 各自 DOM 节点 ~200-500 个，总计 ~2500 DOM 节点 ≈ 5-10MB（可接受）

**备选**：不用 keep-alive（每次切换重新 mount）→ DependencyGraph D3 force 重新计算 ~500ms 体感卡顿。

## 7. 风险与缓解

| # | 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|---|
| 1 | const 引用断裂（抽取时漏移依赖变量） | 高 | vue-tsc 报错 | 按拓扑顺序拆（先无依赖的 Graph/Matrix → 再 Board/Lifecycle → 最后 Workbench），每步收尾跑 vue-tsc |
| 2 | inject 链断裂（子 SFC 测试时 mock 不完整） | 中 | vitest 失败 | useWorkpaperListContext 导出 `createMockContext()` helper 供测试用 |
| 3 | keep-alive 内存膨胀（5 子 SFC 全缓存） | 低 | 长时间使用内存增长 | `:max="5"` + 路由离开时 Shell unmount 触发全部释放 |
| 4 | router.replace 频繁触发 watch 抖动 | 中 | 子 SFC 重复 fetch | viewMode watch 加 `{ flush: 'post' }` + 防抖 |
| 5 | bundle splitting 不生效（vite 没拆 chunk） | 低 | 首屏加载全量 | `defineAsyncComponent` 强制 dynamic import + build 后 `dist/stats.html` 验证 |
| 6 | guide 收敛入 Workbench 后行数超 700 | 中 | CI 卡点失败 | guide 252 行可进一步抽为 `WorkpaperGuidePanel.vue` 子组件（Workbench 内部 lazy import） |
| 7 | 已有子组件（WorkpaperKanban 等）props 接口不兼容新 Shell | 低 | 编译错误 | 薄包装层适配（Board/Lifecycle/Graph/Matrix 各自 ~80-150 行包含 props 桥接） |

## 8. 修订点清单（对 requirements.md 的修正）

| # | 修订内容 | 理由 |
|---|---|---|
| 1 | viewMode 实际 7 个（多 `guide`），收敛为 5 子 SFC 映射不变 | grep 实测发现 line 203-454 有 guide 视图 |
| 2 | 角色名 `assistant` → `auditor`，`reviewer` 不是角色而是项目级权限 | grep UserRole enum 确认 |
| 3 | Property 1 从 hypothesis PBT 降级为普通断言测试 | ADR-4 论证避免恒真断言反模式 |
| 4 | CI baseline 旧值 `WorkpaperList.vue=3238` 应更新为实测 3463（memory 过时数据） | grep 实测 |
| 5 | 已有 4 个子组件可复用（kanban/lifecycle/graph/matrix），真正需要新建的只有 Workbench | 探测发现 |

---

## 变更记录

| 版本 | 日期 | 摘要 | 触发 |
|---|---|---|---|
| v1.0 | 2026-05-28 | 初版起草（主 agent 直接执行，subagent 2 次网络中断降级） | requirements.md 批准后 |
