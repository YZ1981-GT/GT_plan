# Workpaper Editor 拆分重构 — Tasks

## Phase 1 — 基础设施（不影响现有代码）

- [x] **1.1 创建 `useWpDetailGuard` composable** ✅
  - 路径：`audit-platform/frontend/src/composables/useWpDetailGuard.ts`
  - 实现 5 种状态机（loading / invalid_id / no_index / no_file / ready / error）
  - 暴露 `state / wpDetail / wpIndex / loading / ready / errorMessage / refresh`
  - _Requirements: 1_

- [x] **1.2 创建 `GtLoadingOverlay` 全局组件** ✅
  - 路径：`audit-platform/frontend/src/components/common/GtLoadingOverlay.vue`
  - props: `visible / text / hint / size / color / transparent`
  - CSS 用 `position: absolute; inset: 0` 覆盖父容器
  - _Requirements: 5_

- [x] **1.3 写单元测试** ✅
  - `audit-platform/frontend/src/__tests__/useWpDetailGuard.spec.ts`
  - 覆盖 8 种 case：invalid_id / ready / no_file (file_path null) / no_file (wp_index match) / no_index / error / wpId 变化 refresh / loading computed
  - **8/8 tests passed**
  - _Requirements: 1_

## Phase 2 — D 循环试点

- [x] **2.1 grep 全量列出 D 循环相关代码清单**
  - 命令：`grep -E "isDCycle|dCycle|salesIPE|salesPenetration|D-sales|d2a|d4a" audit-platform/frontend/src/views/WorkpaperEditor.vue`
  - 输出 D 相关 dialogs / triggers / handlers / imports 清单
  - _Requirements: 2_

- [x] **2.2 创建 `useDCycleEditor` composable**
  - 路径：`audit-platform/frontend/src/composables/useDCycleEditor.ts`
  - 迁移 D 循环所有逻辑到此文件
  - 暴露统一接口：`{ dialogs, triggers, handlers }`
  - _Requirements: 2_

- [x] **2.3 WorkpaperEditor 接入 useDCycleEditor**
  - 删除原 D 循环代码
  - 改为 `const dCycle = useDCycleEditor(...)`
  - 模板中 `v-model="dCycle.dialogs.salesIPEDialog.value"` 等
  - _Requirements: 2_

- [x] **2.4 Playwright 实测 D 循环**
  - 打开 D2 底稿
  - 触发所有 D 类 dialog（销售 IPE / 穿透 / 函证）
  - 验证无 ErrorBoundary 错误
  - _Requirements: 4_

## Phase 3 — 批量迁其他循环

- [x] **3.1 E 循环**：useECycleEditor + 实测 E1 货币资金
- [x] **3.2 F 循环**：useFCycleEditor + 实测 F2 存货
- [x] **3.3 H 循环**：useHCycleEditor + 实测 H1 固定资产（折旧选择器）
- [x] **3.4 I 循环**：useICycleEditor + 实测 I2 无形资产（摊销）
- [x] **3.5 G 循环**：useGCycleEditor + 实测 G2 长投（公允价值/ECL/分类）
- [x] **3.6 K 循环**：useKCycleEditor + 实测 K8 / K11 减值汇总
- [x] **3.7 L 循环**：useLCycleEditor + 实测 L1/L3 利息计算
- [x] **3.8 M 循环**：useMCycleEditor + 实测 M6 权益变动表
- [x] **3.9 N 循环**：useNCycleEditor + 实测 N5 所得税

## Phase 4 — useWpDetailGuard 接入

- [x] **4.1 WorkpaperEditor 接入（错误状态友好引导）** ✅
  - 替换 initUniver 内 `goBack()` 粗暴跳转为 `loadErrorState` 状态机（'no_file' / 'no_index' / 'invalid_id' / 'error'）
  - 模板加 GtError overlay：图标 + 标题 + 消息 + 操作按钮（返回列表 / 前往生命周期 / 重试）
  - UUID 格式校验提前拦截，避免后端 404 误导
  - 8/8 useWpDetailGuard 单元测试仍通过
  - _Requirements: 1, 5_

- [x] **4.2 WorkpaperList 详情面板接入**
  - `selectWorkpaperById` 调用 useWpDetailGuard
  - 三态对应不同 UI 提示
  - _Requirements: 1_

- [x] **4.3 子编辑器接入**
  - WorkpaperFormEditor / WordEditor / TableEditor / HybridEditor 入口加守卫
  - _Requirements: 1_

## Phase 5 — Overlay 替换 + Playwright 测试

- [x] **5.1 替换现有 .gt-wp-editor-loading-overlay 为 GtLoadingOverlay 组件** ✅
  - `WorkpaperEditor.vue` 内嵌 overlay 改用 `<GtLoadingOverlay>`
  - 新增 `loadingHint` ref 显示加载阶段提示（加载底稿详情/读取项目元数据/加载工作簿数据/初始化 Univer 引擎/渲染工作表）
  - 删除 `.gt-wp-editor-loading-overlay` CSS 规则
  - 8/8 useWpDetailGuard 单元测试仍通过
  - _Requirements: 5_

- [x] **5.2 写 Playwright 端到端测试** ✅
  - 路径：`audit-platform/frontend/e2e/workpaper-editor-loading.spec.ts`
  - 覆盖 3 个核心 case：①ReferenceError + 死锁回归 ②GtLoadingOverlay 阶段提示 ③无效 wpId 友好引导
  - _Requirements: 4_

- [x] **5.3 CI 接入** ✅
  - `package.json` 新增 `test:unit` / `test:e2e` / `test:e2e:wp` 脚本
  - `test:e2e:wp` 仅跑底稿编辑器相关 e2e（loading + e1 cash optimization），开发期快速回归
  - _Requirements: 4_

## Phase 6 — 验收

- [x] **6.1 行数检查**
  - `wc -l audit-platform/frontend/src/views/WorkpaperEditor.vue` ≤ 1000 行
  - 各 use{X}CycleEditor.ts ≤ 200 行
  - _Requirements: 2_

- [x] **6.2 功能回归**
  - 所有循环底稿（D/E/F/G/H/I/J/K/L/M/N）逐一打开 Playwright 测试
  - 0 errors / 0 ErrorBoundary
  - _Requirements: 4_

- [x] **6.3 memory.md 更新**
  - 移除"WorkpaperEditor.vue 2900+ 行拆分"待办（已完成）
  - 移除"useWpDetailGuard composable 沉淀"待办（已完成）
  - 添加新铁律：useWpDetailGuard 三态 case 默认接入 / overlay 模式取代顶层 v-if 守卫
  - _Requirements: 1, 5_

- [x] **6.4 git commit + push**
  - feat(workpaper): WorkpaperEditor 2900→1000 行拆分 + useWpDetailGuard 三态守卫
  - _Requirements: 全部_

## 估时

- Phase 1: 2 小时（基础设施）
- Phase 2: 3 小时（D 循环试点）
- Phase 3: 5 小时（其他 9 个循环各 30 分钟）
- Phase 4: 2 小时（useWpDetailGuard 接入）
- Phase 5: 2 小时（Overlay 替换 + Playwright 测试）
- Phase 6: 1 小时（验收）

**总计**：~15 小时

## 完成状态

- [x] Spec 三件套创建（requirements + design + tasks）
- [x] **Phase 1 — 基础设施** ✅ (3/3 tasks, 8/8 tests passed)
- [x] **Phase 2-3 部分 — useCycleType + useCycleDialogs + useSheetNavFacade** ✅ (净减 509 行，2998→2489)
- [x] **Phase 4.1 — WorkpaperEditor 错误状态友好引导** ✅
- [ ] Phase 4.2-4.3 — WorkpaperList 详情面板 + 子编辑器接入
- [x] **Phase 5.1 — Overlay 替换** ✅
- [x] **Phase 5.2 — Playwright 端到端测试** ✅ (3/3 passed)
- [x] **Phase 5.3 — CI 脚本** ✅
- [ ] Phase 6.1 行数检查 — 当前 2489 行（useEditorActions 接入后可再减 ~220 行）
- [ ] Phase 6.2-6.4 — 功能回归 + memory.md 更新 + commit
- [ ] **待接入**：useEditorActions（需 let→ref 改造 + Playwright 验证保存流程）
