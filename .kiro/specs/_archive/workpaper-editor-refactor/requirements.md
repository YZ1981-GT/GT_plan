# Workpaper Editor 拆分重构 — Requirements

## 背景

`WorkpaperEditor.vue` 当前 2900+ 行（含 60+ 状态 ref / 30+ 业务函数 / 15+ 子组件路由），是项目最大的单文件组件。本轮底稿模块改造中暴露了 4 类问题：

1. **Vue setup ref 顺序坑**（`Cannot access 'wpDetail' before initialization` — wpDetail 定义在第 1370 行但第 943 行的 computed 已引用）
2. **顶层 v-if 守卫拦 init 死锁**（守卫等 loading=false / loading=false 等 container 渲染 / container 渲染等守卫不拦）
3. **每个底稿视图都自己写 loading 处理**，模式不一致（`onOnlineEdit` 自检 hasRealWp / `onCycleNodeClick` 检查 wp_index → workingpaper / `WorkpaperEditor` 内部加载 wpDetail），三态 case 处理散落多处
4. **千行组件改动必须 Playwright 实测**（仅 `getDiagnostics` 通过不代表运行时无错），但实测频次低导致 bug 反复

## 目标

将 WorkpaperEditor.vue 从 2900+ 行拆到 1000 行内，sub-1000 行可读、可维护。统一 wpDetail 加载 / 三态校验逻辑到 composable。

## 验收标准（EARS）

### Req 1 — useWpDetailGuard composable 沉淀

**WHEN** 任何依赖 `wpId` 的视图（WorkpaperList 详情面板 / WorkpaperEditor / 子编辑器）需要校验底稿状态
**THE SYSTEM SHALL** 调用统一的 `useWpDetailGuard(projectId, wpId)` composable 处理三种 case：
- ① wpId 无效（路由参数缺失或格式错） → 返回 `state: 'invalid_id'`
- ② 后端无 WpIndex 记录 → 返回 `state: 'no_index'` + 提示"该编码不在项目中"
- ③ 有 WpIndex 但无 WorkingPaper 文件记录 → 返回 `state: 'no_file'` + 提示"请先在生命周期生成"
- ④ 完整加载成功 → 返回 `state: 'ready', wpDetail, wpIndex, workingPaper`

**AND** 该 composable 内部封装 loading / error 状态，调用方只需 `if (guard.state.value === 'ready')` 决定渲染。

### Req 2 — WorkpaperEditor 业务逻辑按循环拆分

**WHEN** 阅读 WorkpaperEditor.vue 时
**THE SYSTEM SHALL** 主组件文件 ≤ 1000 行，业务逻辑按循环拆分到独立 composable：
- `useDCycleEditor.ts` — D 销售循环专属逻辑（穿透/IPE/勾稽）
- `useECycleEditor.ts` — E 货币资金（外币/数字货币）
- `useFCycleEditor.ts` — F 采购存货（监盘/计价）
- `useHCycleEditor.ts` — H 固定资产（折旧/减值/在建转固）
- `useICycleEditor.ts` — I 无形资产（摊销/商誉减值）
- `useGCycleEditor.ts` — G 投资（公允价值/ECL/分类）
- `useKCycleEditor.ts` — K 管理费用（费用分析/减值汇总）
- `useLCycleEditor.ts` — L 筹资（利息/摊余成本）
- `useMCycleEditor.ts` — M 股东权益（变动表）
- `useNCycleEditor.ts` — N 税费（所得税）

**AND** 每个 composable 暴露 `dialogs / triggers / handlers` 三类对外 API，主组件按 wp_code 前缀路由调用。

### Req 3 — 顶层 ref 定义顺序铁律落地

**WHEN** 主组件改动时
**THE SYSTEM SHALL** 业务核心 ref（`wpDetail` / `loading` / `dirty` / `saving` / `wpId` / `projectId`）在 `<script setup>` 顶部统一定义（紧跟 import 和 router 之后），所有 computed/composable 调用之后。

**AND** 加 ESLint 规则或注释守卫，防止后续添加 ref 时插到 computed 之间。

### Req 4 — Playwright 实测覆盖

**WHEN** WorkpaperEditor 改动后
**THE SYSTEM SHALL** 至少有 1 个 Playwright 测试覆盖核心路径：
- ① 列表页点击底稿 → 在线编辑 → 编辑器正常加载（不出现 ErrorBoundary "页面渲染出错"）
- ② Univer 画布渲染（canvas count > 0）
- ③ Sheet 切换 tab 可点击切换
- ④ 保存按钮可点击触发 onSave

**AND** 该测试在 `audit-platform/frontend/tests/e2e/` 下，CI 必跑。

### Req 5 — overlay 加载守卫模式统一

**WHEN** 任何依赖 template ref 挂载触发 init 的视图（如 Univer container）
**THE SYSTEM SHALL** 不在顶层加 `v-if="loading"` 守卫（避免拦住 ref 挂载死锁）

**AND** 改用 overlay 模式：容器永远渲染 + 内部 absolute-positioned `.loading-overlay`（v-if=loading）覆盖加载状态。

**AND** 该模式封装为 `<GtLoadingOverlay>` 组件，全局通用。

## 边界与不动项

- **不动**：现有路由 `/projects/:projectId/workpapers/:wpId/edit` 保持
- **不动**：所有现有按钮/弹窗/快捷键交互保持
- **不动**：Univer Sheets 编辑器本身不替换（不引入 AG Grid / Luckysheet）
- **不动**：现有 13 个循环 sheet 编排逻辑（D/E/F/H/I 等的 `useUniverSheetNav` / `useDSalesCycleSheetGroups` 等保留，本次只重组 dialog 触发逻辑）

## 风险与缓解

- **风险 1**：拆分过程中漏掉某个 dialog/handler → 视图功能缺失
  - **缓解**：拆分前先用 grep 全量列出所有 `showXxxDialog` / `onXxx` 函数清单，逐一 checklist 迁移
- **风险 2**：Vue setup 重构破坏 ref 之间的 watch 关系
  - **缓解**：每完成一个 composable 立即 Playwright 实测一次，不积累风险
- **风险 3**：useWpDetailGuard 引入后破坏现有 onMounted 顺序
  - **缓解**：先在 WorkpaperEditor 单点试用，验证后再推广到 WorkpaperList 详情面板等

## 完成定义

- [ ] WorkpaperEditor.vue 行数 ≤ 1000
- [ ] 10 个循环 composable 文件创建（D/E/F/G/H/I/J/K/L/M/N）+ 各 ≤ 200 行
- [ ] useWpDetailGuard composable 创建 + 至少在 WorkpaperEditor 接入
- [ ] GtLoadingOverlay 组件创建 + WorkpaperEditor 接入
- [ ] Playwright 端到端测试 1 个 + CI 通过
- [ ] memory.md 更新（Req 5 的 overlay 守卫模式 / Req 1 的 useWpDetailGuard 沉淀）
