# 需求文档：底稿前端大组件拆分（P1，Top 3）

## 简介

后端底稿模块经 pass2/pass3/pass4 治理，大文件已全部 ≤800 行。前端 `audit-platform/frontend/src/components/workpaper/` 经扫描确认反模式债≈0，唯一债是**大组件**——8 个 .vue 组件超 800 行。本 spec 聚焦交互最重、最常被改的 **Top 3**：

| 组件 | 行数 | 性质 |
|------|------|------|
| `GtAProgramConsole.vue` | 1625 | 程序表控制台（程序行表格 + 裁剪/状态流转 + 复核子码解析 + 审计逻辑图 + 子底稿弹窗） |
| `GtChecklistTable.vue` | 1437 | 核对表（章节导航 + 条目填写 + 搜索 + 批量标记 + 适用性 + 自动保存） |
| `GtAuditSheet.vue` | 1405 | 审定表（行项目可编辑表格 + 动态列 + TB 取数 + 审计说明/结论 + 合计汇总） |

.vue 文件由 template + script + style 三段构成，拆分手法不同于后端纯函数/类——通过**抽 composable（状态+逻辑）+ 拆展示型子组件**，主组件保持为编排器。

### 严格约束（用户明确要求 + 铁律）

- **行为零变更**：拆分纯结构调整，不改任何 props 契约、emit 事件、用户可见交互、联动行为。
- **响应式/事件流不破**：composable 用 ref/computed 保持响应式；子组件 props/emit 完整透传；避免 provide/inject 滥用导致的隐式耦合。
- **每组件拆完必 Playwright 实测**（铁律）：拆一个、验一个，确认渲染/编辑/保存/联动全链路不崩。
- **不过度拆分**：每组件降到 ≤800 即止，按"逻辑域/展示域"内聚拆，不机械按行数切割。
- **不动**已达标的其他底稿组件、views 层、后端。
- **vitest 现有 spec 必须全绿**（GtAnalyticalReview/GtCNoteTable 等已有 spec 模式参考）。

## 需求

### 需求 1：`GtAProgramConsole.vue` 拆分（≤800 行）

**用户故事：** 作为前端维护者，我希望程序表控制台按"复核子码解析/适用性判定/数据加载"抽到 composable，降低主组件复杂度。

#### 验收准则

1. WHEN 拆分完成 THEN `GtAProgramConsole.vue` SHALL ≤800 行
2. WHERE 逻辑内聚 THEN SHALL 抽出 composable（如 `useAProgramReview.ts` 复核子码/A17 版本适用性、`useAProgramData.ts` 程序行加载/项目信息/applicable_when），主组件 import 调用
3. WHEN 拆分后 THEN 全部 props（wpId/sheetName/schema/htmlData/readonly）和 emit 事件（program-trim/program-status-change/jump-to-workpaper/save/open-attachment/program-add）SHALL 逐字不变
4. WHEN 拆分完成 THEN Playwright 实测程序表渲染/裁剪/状态流转/弹窗/审计逻辑图全链路无崩；现有 vitest spec（如有）全绿

### 需求 2：`GtChecklistTable.vue` 拆分（≤800 行）

**用户故事：** 作为前端维护者，我希望核对表按"搜索/响应填写+自动保存/适用性"抽到 composable，主组件保导航+渲染。

#### 验收准则

1. WHEN 拆分完成 THEN `GtChecklistTable.vue` SHALL ≤800 行
2. WHERE 逻辑内聚 THEN SHALL 抽出 composable（如 `useChecklistResponses.ts` getResponse/updateConclusion/updateRemark/updateWpRef/自动保存 debounce、`useChecklistSearch.ts` 搜索/高亮/跳转、`useChecklistApplicability.ts` 章节适用性），主组件 import 调用
3. WHEN 拆分后 THEN 全部 props 和 emit 事件 SHALL 逐字不变；自动保存 debounce 2s 行为不变
4. WHEN 拆分完成 THEN Playwright 实测核对表导航/填写/搜索/批量标记/适用性/保存全链路无崩；现有 vitest spec 全绿

### 需求 3：`GtAuditSheet.vue` 拆分（≤800 行）

**用户故事：** 作为前端维护者，我希望审定表按"表格数据构建/动态列分组/说明结论"抽到 composable，主组件保渲染。

#### 验收准则

1. WHEN 拆分完成 THEN `GtAuditSheet.vue` SHALL ≤800 行
2. WHERE 逻辑内聚 THEN SHALL 抽出 composable（如 `useAuditSheetTable.ts` buildTableData/行类型判定/合计汇总、`useAuditSheetColumns.ts` 动态列分组/期初区折叠、`useAuditSheetSections.ts` 审计说明/结论），主组件 import 调用
3. WHEN 拆分后 THEN 全部 props 和 emit 事件 SHALL 逐字不变；TB 取数/合计汇总/可编辑行判定行为不变
4. WHEN 拆分完成 THEN Playwright 实测审定表渲染/编辑/动态列/说明结论/合计全链路无崩；现有 vitest spec 全绿

### 需求 4：全程零回归 + 守卫

**用户故事：** 作为维护者，我希望前端拆分不破坏任何功能。

#### 验收准则

1. WHEN 全部拆分完成 THEN 3 组件 SHALL 全部 ≤800 行
2. WHEN 全部拆分完成 THEN `npx vitest run`（底稿组件相关 spec）SHALL 全绿
3. WHEN 全部拆分完成 THEN `npx tsc --noEmit` SHALL 无新增类型错误
4. WHEN 全部拆分完成 THEN Playwright 实测 3 组件主链路 SHALL 全部通过
5. WHERE 拆分触及 import THEN composable/子组件依赖 SHALL 单向，无循环引用
