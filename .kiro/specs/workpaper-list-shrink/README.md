# workpaper-list-shrink — WorkpaperList.vue 瘦身（3238→拆 5 SFC）

> 起草日期：2026-05-28
> 触发：底稿模块复盘（V3 spec gaps.md §B/G + memory.md 超级 SFC 风险铁律）
> 工时：1 周（5 工作日）
> 优先级：**P0**

## 触发问题

`audit-platform/frontend/src/views/WorkpaperList.vue` = **3238 行**，比 V3 spec 主攻的 WorkpaperEditor (2555) 还大，但 V3 完全没盯。

风险：
- 上帝组件容易触发 Vue setup const 顺序错误
- 多 Tab 视图（生命周期 / 工作台 / 看板 / 委派矩阵 / 依赖图）reactive 依赖纠缠
- 测试覆盖率断层，重构 conflict 率高
- 用户进项目后第一个加载的视图，首屏 bundle 直接被拖累

## 范围

拆为 5 个 SFC + 1 个 shell：

| 新文件 | 职责 | 估行 |
|---|---|---|
| `WorkpaperListPage.vue`（shell）| 路由 + Tab 切换 + 共享 store | ≤ 300 |
| `WorkpaperLifecycleView.vue` | 生命周期视图（A→B→C 推进）| ≤ 600 |
| `WorkpaperBoardView.vue` | 看板视图（拖拽/状态切换）| ≤ 500 |
| `WorkpaperDelegationMatrix.vue` | 委派矩阵（成员 × 底稿 × 复核层级） | ≤ 600 |
| `WorkpaperDependencyGraph.vue` | 依赖图（D3 force-graph 子模块） | ≤ 500 |
| `WorkpaperWorkbenchView.vue` | 工作台 + 列表 | ≤ 700 |

合计 ≤ 3200 行（与现状持平），但**单文件 ≤ 700**。

## 不在范围

- 修改 list 业务逻辑（仅做结构拆分）
- 改 router_registry（路由维持 `/projects/:id/workpapers`）
- 触碰 WorkpaperEditor / GtCNoteTable / GtEControlTest（独立 spec）

## 验收

- `wc -l src/views/WorkpaperListPage.vue` ≤ 300
- 5 个子 view 各自 ≤ 700 行
- 现有 vitest（含 list 相关）全绿，0 回归
- vue-tsc 0 errors
- Playwright 现有 e2e 全过（覆盖列表/Tab 切换/看板拖拽）

## Sprint 划分（5 天）

| Sprint | 工时 | 内容 |
|---|---|---|
| 0. 准备 | 0.5 天 | grep 现有 reactive 依赖 + Tab 切换逻辑 + emit 链 |
| 1. shell + Lifecycle 拆分 | 1 天 | 抽出 Page 框架 + 生命周期视图 |
| 2. Board + Workbench | 1 天 | 看板（保持拖拽逻辑）+ 工作台 |
| 3. Delegation + Dependency | 1 天 | 委派矩阵 + 依赖图（D3 隔离） |
| 4. 测试 + 回归 | 1 天 | 补 5 子组件 vitest + Playwright e2e + 全套回归 |
| 5. CI 卡点 | 0.5 天 | 5 个新文件加行数防膨胀 baseline |

下一步：触发时起完整 requirements + design + tasks 三件套。本 README 是占位 spec stub，正式起草前不创建子文件。
