# gt-c-note-table-shrink — HTML 渲染器超级 SFC 拆分

> 起草日期：2026-05-28
> 触发：底稿模块复盘（V3 spec gaps.md §B + memory.md 超级 SFC 风险铁律）
> 工时：2-3 工作日
> 优先级：**P2**（触碰时做）

## 触发问题

V3 把底稿渲染从 Univer 切到 HTML，但拆得不彻底，每个 cycle 的"超级 SFC"还在：

| 文件 | 行数 | 问题 |
|---|---|---|
| `GtCNoteTable.vue` | **1608** | 附注表（合并/展开/批注/穿透/表头多级 全 in 一个 SFC）|
| `GtEControlTest.vue` | **1125** | 6 步骤决策树 + 4 互斥结论 + 联动建议 全 in 一个 SFC |
| `GtAProgramConsole.vue` | 629 | A 程序控制台（OK 边缘）|

合计 ~3300 行/3 SFC。

## 拆分方案

### A. GtCNoteTable.vue（1608→拆 5 子组件）

| 新文件 | 职责 | 估行 |
|---|---|---|
| `GtCNoteTable.vue` (shell) | Props 路由 + emit 透传 | ≤ 300 |
| `CNoteTableHeader.vue` | 多级表头渲染 | ≤ 250 |
| `CNoteTableBody.vue` | 数据行 + cell 编辑 | ≤ 400 |
| `CNoteTableMerge.vue` | 合并/展开逻辑（subtable-toggle） | ≤ 250 |
| `CNoteTablePenetrate.vue` | 穿透 hooks（jump-to-reference） | ≤ 200 |
| `CNoteTableComments.vue` | 批注/标准切换 | ≤ 250 |

合计 ≤ 1650 行，**单文件 ≤ 400**。

### B. GtEControlTest.vue（1125→拆 7 步骤）

按 6 步骤决策树拆：

| 新文件 | 职责 | 估行 |
|---|---|---|
| `GtEControlTest.vue` (shell) | el-steps + state machine | ≤ 200 |
| `EControlStep1.vue` ~ `EControlStep6.vue` | 6 步骤独立 SFC | 各 ≤ 150 |
| `EControlConclusion.vue` | 4 互斥结论 + 联动 | ≤ 200 |

合计 ≤ 1300 行，**单文件 ≤ 200**。

### C. GtAProgramConsole.vue（保持，触碰时再拆）

629 行可接受，本 spec 不动。

## 不在范围

- 修改 cycle 业务逻辑（仅 SFC 结构拆分）
- 触碰 htmlRendererRegistry（registry 由 shell 统一注册）
- 改 backend service / DB / router

## 验收

- 5+7 个新子组件各自 ≤ 400 行 / ≤ 200 行
- 现有 vitest（GtCNoteTable / GtEControlTest 测试）全绿，0 回归
- vue-tsc 0 errors
- Playwright 现有 e2e 通过（含附注同步 / 控制测试 6 步骤导航）

## Sprint 划分（2-3 天）

| Sprint | 工时 | 内容 |
|---|---|---|
| 0. 准备 | 0.5 天 | 静态依赖图 + 现有测试基线 |
| 1. GtCNoteTable 拆 5 | 1 天 | 5 子组件 + shell |
| 2. GtEControlTest 拆 7 | 1 天 | 步骤 + 结论 + shell |
| 3. 测试 + CI 卡点 | 0.5 天 | 补子组件 vitest + 加 baseline |

下一步：触碰时（如新增 C 类子表 / E 步骤变化）起完整三件套。
