# 实施计划：生产就绪改进（production-readiness）

## 概述

按优先级分四个 Sprint 实施，覆盖 P0 数据正确性、P1+P2 核心流程与体验、P2+P3 前置、P3 核心四个阶段。所有任务均为编码任务，按设计文档中的文件变更清单组织。

---

## Sprint 1：P0 数据正确性（需求 0 → 0.5 → 3 → 1 → 2）

- [ ] 0. 底稿编辑器 Univer 公式引擎集成（需求 13）
  - [x] 0.1 安装 `@univerjs/preset-sheets-formula` 依赖
    - 在 `audit-platform/frontend/` 目录下执行 `npm install @univerjs/preset-sheets-formula`
    - 确认 `package.json` 中已新增该依赖
    - 文件：`audit-platform/frontend/package.json`
    - _需求：13.1_

  - [x] 0.2 在 `WorkpaperEditor.vue` 中添加 `UniverSheetsFormulaPreset` 和对应 locale
    - 新增 import：`UniverSheetsFormulaPreset` 和 `UniverPresetSheetsFormulaZhCN`
    - 在 `createUniver` 的 `locales` 中合并 `UniverPresetSheetsFormulaZhCN`
    - 在 `presets` 数组中追加 `UniverSheetsFormulaPreset()`
    - 文件：`audit-platform/frontend/src/views/WorkpaperEditor.vue`
    - _需求：13.1、13.2、13.3_

  - [x] 0.3 验证公式计算正常
    - 在底稿编辑器中输入 `=SUM(A1:A3)`，确认单元格显示计算结果而非公式字符串
    - 修改 A1 的值，确认公式单元格自动更新
    - _需求：13.2、13.3_

- [x] 0.5 底稿编辑器错误信息修正（需求 14）
  - [x] 0.5.1 `onSave` 改为返回 `Promise<boolean>`
    - 将 `async function onSave()` 改为 `async function onSave(): Promise<boolean>`
    - 成功时 `return true`，catch 块中 `return false`（不再 throw）
    - 文件：`audit-platform/frontend/src/views/WorkpaperEditor.vue`
    - _需求：14.2_

  - [x] 0.5.2 `onSyncStructure` 中判断 `onSave` 返回值
    - 将 `if (dirty.value) await onSave()` 改为：
      ```typescript
      if (dirty.value) {
        const saveOk = await onSave()
        if (!saveOk) return
      }
      ```
    - 保留 catch 块中的"同步失败"提示（仅用于 `rebuildWorkpaperStructure` 失败的情况）
    - 文件：`audit-platform/frontend/src/views/WorkpaperEditor.vue`
    - _需求：14.1_

- [x] 1. 实现底稿编辑器 Dirty 标记完整覆盖（需求 3）
  - [x] 1.1 扩展 `WorkpaperEditor.vue` 中的命令过滤逻辑
    - 将现有 `onCommandExecuted` 回调中的命令 ID 过滤替换为 `DIRTY_COMMAND_PATTERNS` 数组匹配
    - 覆盖范围：`set-range-values`、`set-cell`、`set-formula`、`formula.`、`array-formula`、`set-style`、`set-border`、`set-number-format`、`set-font`、`clear-selection`、`delete-range`、`insert-row`、`insert-col`、`remove-row`、`remove-col`、`merge-cells`、`unmerge-cells`
    - 文件：`audit-platform/frontend/src/views/WorkpaperEditor.vue`
    - _需求：3.1、3.2、3.6_

  - [x] 1.2 新增未保存变更提示 UI 和路由离开守卫
    - 在工具栏区域添加 `<span v-if="dirty">有未保存的变更</span>` 提示
    - 新增 `onBeforeRouteLeave` 守卫：`dirty.value` 为 true 时弹出 `ElMessageBox.confirm` 确认对话框
    - 文件：`audit-platform/frontend/src/views/WorkpaperEditor.vue`
    - _需求：3.3、3.4、3.5_

  - [x]* 1.3 为属性 4 编写属性测试（Dirty 标记触发）
    - **属性 4：编辑命令触发 Dirty 标记**
    - **验证：需求 3.1、3.2、3.6**

  - [x]* 1.4 为属性 5 编写属性测试（保存后 Dirty 重置）
    - **属性 5：保存后 Dirty 标记重置**
    - **验证：需求 3.5**

- [x] 2. 实现底稿保存事件触发附注自动刷新（需求 1）
  - [x] 2.1 扩展 `eventBus.ts` 新增事件类型
    - 新增 `WorkpaperSavedPayload` 接口（`projectId: string`、`wpId: string`、`year?: number`）
    - 在 `Events` 映射表中新增 `'workpaper:saved': WorkpaperSavedPayload`
    - 文件：`audit-platform/frontend/src/utils/eventBus.ts`
    - _需求：1.1_

  - [x] 2.2 在 `WorkpaperEditor.vue` 的 `onSave` 成功后发布事件
    - 在 `dirty.value = false` 和 `ElMessage.success(...)` 之后添加 `eventBus.emit('workpaper:saved', { projectId, wpId, year })`
    - 文件：`audit-platform/frontend/src/views/WorkpaperEditor.vue`
    - _需求：1.1_

  - [x] 2.3 在 `DisclosureEditor.vue` 中注册防抖监听器并处理同步失败
    - 使用原生 `setTimeout`/`clearTimeout` 实现 1000ms 防抖（项目未安装 @vueuse/core，不可使用 `useDebounceFn`）
    - 声明模块级变量 `let syncDebounceTimer: ReturnType<typeof setTimeout> | null = null`
    - 定义 `onWorkpaperSaved(payload)` 函数：校验 `projectId` 一致后清除旧 timer 并设置新 timer
    - timer 回调内：调用 `refreshDisclosureFromWorkpapers`，失败时设置 `syncError.value = true`
    - `onMounted` 中调用 `eventBus.on('workpaper:saved', onWorkpaperSaved)`
    - `onBeforeUnmount` 中调用 `eventBus.off` 并 `clearTimeout(syncDebounceTimer)` 清理
    - 若 `WorkpaperEditor.vue` 中没有 `year` 变量，从 `route.query.year` 获取：`const year = computed(() => Number(route.query.year) || new Date().getFullYear() - 1)`
    - 新增 `syncError` 状态和失败提示 UI（`el-alert` + 手动重试按钮）
    - 文件：`audit-platform/frontend/src/views/DisclosureEditor.vue`
    - _需求：1.2、1.3、1.4、1.5_

  - [x]* 2.4 为属性 1 编写属性测试（事件传播）
    - **属性 1：底稿保存事件传播**
    - **验证：需求 1.1**

  - [x]* 2.5 为属性 2 编写属性测试（防抖合并）
    - **属性 2：附注刷新防抖**
    - **验证：需求 1.5**

- [x] 3. 实现 Dashboard 趋势图接入真实 API 数据（需求 2）
  - [x] 3.1 后端新增 `GET /stats/trend` 端点
    - 在 `dashboard.py` 中新增路由 `@router.get("/stats/trend")`，接受 `project_id`（可选）和 `days`（默认 7）参数
    - 文件：`backend/app/routers/dashboard.py`
    - _需求：2.1、2.2_

  - [x] 3.2 后端新增 `get_stats_trend()` 服务方法
    - 在 `DashboardService` 中新增 `async def get_stats_trend(self, project_id, days)` 方法
    - 使用单次 SQL 聚合查询（`GROUP BY date, status`），避免 Python 循环逐天查询（N 次 DB 查询）
    - 预填所有日期（补全无数据的日期），返回 `{ days, trend: { date: { status: count } } }` 格式
    - 文件：`backend/app/services/dashboard_service.py`
    - _需求：2.1、2.3_

  - [x] 3.3 前端 `Dashboard.vue` 删除硬编码数据并接入 API
    - 删除 Mock `sparkData` 硬编码块
    - 新增 `trendData` ref 和 `loadTrendData()` 函数（调用 `/api/dashboard/stats/trend`）
    - 新增 `sparkSeries` computed 属性从 `trendData` 提取各状态近 7 天数组
    - 新增 `trendLoadError` 状态和错误提示 UI（`el-empty`）
    - 文件：`audit-platform/frontend/src/views/Dashboard.vue`
    - _需求：2.1、2.2、2.4、2.5_

  - [x]* 3.4 为属性 3 编写属性测试（趋势图数据一致性）
    - **属性 3：趋势图数据与 API 响应一致**
    - **验证：需求 2.3**

- [x] 3.8 QC 项目汇总 N+1 查询优化（需求 26）
  - [x] 3.8.1 重写 `get_project_summary` 方法为单次批量查询
    - 用子查询（`GROUP BY working_paper_id` 取 `max(check_timestamp)`）替换原有循环查询
    - JOIN 回 `WpQcResult` 表取完整记录，构建 `{wp_id: result}` 映射
    - `wp_ids` 为空时直接返回空汇总，不执行查询
    - 文件：`backend/app/services/qc_engine.py`
    - _需求：26.1、26.2_

- [x] 3.9 审计报告定稿后端状态保护（需求 27）
  - [x] 3.9.1 `update_paragraph` 端点添加 `final` 状态校验
    - 在端点逻辑开头查询报告状态，若 `status == 'final'` 则 `raise HTTPException(403, "报告已定稿，不允许修改段落内容")`
    - 文件：`backend/app/routers/audit_report.py`
    - _需求：27.1_

  - [x] 3.9.2 `update_status` 端点禁止从 `final` 回退至 `review`
    - 若当前状态为 `final` 且目标状态为 `review`，返回 HTTP 403
    - 文件：`backend/app/routers/audit_report.py`
    - _需求：27.2_

- [x] 3.10 QC-16 数据一致性规则字段修正（需求 28）
  - [x] 3.10.1 修正 `DataReferenceConsistencyRule.check` 字段名和查询逻辑
    - 将 `audited_debit`/`audited_credit` 替换为 `audited_amount`
    - 通过底稿的 `account_code` 查询 `TrialBalance` 对应科目，而非取第一条记录
    - 差异超过 0.01 元时产生阻断级发现
    - 文件：`backend/app/services/qc_engine.py`
    - _需求：28.1、28.2_

- [x] 3.5 修正 ReviewInbox 查看按钮跳转（需求 18）
  - [x] 3.5.1 修改 `ReviewInbox.vue` 中的 `goToWorkpaper` 函数
    - 将跳转目标从底稿列表页改为 `WorkpaperEditor`
    - 使用 `router.push({ name: 'WorkpaperEditor', params: { projectId: row.project_id, wpId: row.id } })`
    - 实施前先确认 router 中 `WorkpaperEditor` 路由的实际 `name` 值
    - 文件：`audit-platform/frontend/src/views/ReviewInbox.vue`
    - _需求：18.1、18.2_

- [x] 3.6 填充报表权益变动表和资产减值准备表（需求 17）
  - [x] 3.6.1 确认后端 `equity_statement` 和 `impairment_provision` 数据生成逻辑
    - 读取 `backend/app/routers/reports.py`，确认 `GET /api/projects/{id}/reports/{report_type}` 对这两种 `report_type` 是否有数据返回
    - 若无，在后端补充对应的数据聚合逻辑
    - 文件：`backend/app/routers/reports.py`（只读确认，按需修改）
    - _需求：17.1、17.2_

  - [x] 3.6.2 修改 `ReportView.vue` 权益变动表和资产减值准备表为数据驱动
    - 将两张表的 `<tbody>` 中所有硬编码 `-` 改为从 `rows` 数据读取对应字段
    - 无数据时显示 `0` 或空白，不得显示 `-`
    - 文件：`audit-platform/frontend/src/views/ReportView.vue`
    - _需求：17.1、17.2、17.3_

- [x] 3.7 AuditCheckDashboard N+1 请求优化（需求 19）
  - [x] 3.7.1 后端新增批量精细化检查汇总端点
    - 在 `wp_fine_rules.py` 中新增 `GET /projects/{project_id}/fine-checks/summary` 端点
    - 一次返回项目所有底稿的精细化检查结果，避免前端逐条请求
    - 文件：`backend/app/routers/wp_fine_rules.py`
    - _需求：19.2_

  - [x] 3.7.2 前端 `AuditCheckDashboard.vue` 改为调用批量接口
    - 删除 `for (const wp of wpList)` 串行循环
    - 改为单次调用 `GET /api/projects/{id}/fine-checks/summary`
    - 文件：`audit-platform/frontend/src/views/AuditCheckDashboard.vue`
    - _需求：19.1、19.2_

- [x] 3.11 PBC 清单和函证管理后端路由注册（需求 33）
  - [x] 3.11.1 检查后端 PBC 和函证路由文件是否存在
    - 检查 `backend/app/routers/pbc.py` 和 `backend/app/routers/confirmations.py` 是否存在
    - 若存在但未注册，直接进入 3.11.2；若不存在，先新建最小骨架路由文件
    - 文件：`backend/app/routers/pbc.py`、`backend/app/routers/confirmations.py`（按需新建）
    - _需求：33.3_

  - [x] 3.11.2 在 `router_registry.py` 中注册 PBC 和函证路由
    - 导入 `pbc_router` 和 `confirmations_router`
    - 使用 `app.include_router(pbc_router, prefix="/api", tags=["PBC清单"])` 注册
    - 使用 `app.include_router(confirmations_router, prefix="/api", tags=["函证管理"])` 注册
    - 文件：`backend/app/router_registry.py`
    - _需求：33.3_

  - [x] 3.11.3 在 `CollaborationIndex.vue` 的 `onMounted` 中补充数据加载逻辑
    - 新增 PBC 清单加载：`GET /api/projects/{id}/pbc`，结果赋值给 `pbcItems`
    - 新增函证列表加载：`GET /api/projects/{id}/confirmations`，结果赋值给 `confirmations`
    - 两者均用 `try/catch` 包裹，失败时赋值空数组，不阻断页面加载
    - 文件：`audit-platform/frontend/src/views/CollaborationIndex.vue`
    - _需求：33.1、33.2_

- [x] 3.12 进度看板卡片直接跳转底稿编辑器（需求 34）
  - [x] 3.12.1 修改 `ProjectProgressBoard.vue` 中的 `goToWorkpaper` 函数
    - 实施前确认 router 中 `WorkpaperEditor` 路由的实际 `name` 值（与需求 18 一致）
    - `item.id` 存在时：`router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId: item.id } })`
    - `item.id` 不存在时：降级跳转 `router.push('/projects/${projectId.value}/workpapers')`
    - 文件：`audit-platform/frontend/src/views/ProjectProgressBoard.vue`
    - _需求：34.1、34.2_

- [x] 3.13 个人工作台待办和工时数据加载（需求 35）
  - [x] 3.13.1 确认 `getMyTodos`、`getMyStaffId`、`listWorkHours` 是否已在 services 中存在
    - 检查 `audit-platform/frontend/src/services/` 目录下相关 service 文件
    - 若不存在，新增对应 API 调用函数（调用已有后端接口）
    - 文件：相关 service 文件（按需修改）

  - [x] 3.13.2 在 `PersonalDashboard.vue` 的 `onMounted` 中补充待办和工时加载逻辑
    - 新增待办加载：调用 `getMyTodos()`，结果赋值给 `todos`，失败时赋值空数组
    - 新增工时加载：先调用 `getMyStaffId()` 获取 `staff_id`，再调用 `listWorkHours(staff_id, { start_date, end_date })` 获取本周工时
    - 本周起始日期计算：`weekStart.setDate(today.getDate() - today.getDay() + 1)`
    - 文件：`audit-platform/frontend/src/views/PersonalDashboard.vue`
    - _需求：35.1、35.2_

- [x] 4. Sprint 1 检查点
  - 确保所有测试通过，如有疑问请向用户确认。

---

## Sprint 2：P1+P2 核心流程与体验（需求 4 → 5 → 6 → 8）

- [x] 5. 实现复核收件箱导航入口（需求 4）
  - [x] 5.0 读取 `ThreeColumnLayout.vue` 确认导航 slot 结构
    - 读取 `audit-platform/frontend/src/layouts/ThreeColumnLayout.vue` 全文
    - 确认是否有 `#header`、`#nav-icons`、`#nav-extra` 或其他可注入导航入口的 slot
    - 根据实际 slot 结构选择实现方案（A: ThreeColumnLayout slot / B: FourColumnCatalog 顶部 / C: 其他位置）
    - 文件：`audit-platform/frontend/src/layouts/ThreeColumnLayout.vue`（只读）

  - [x] 5.1 在正确位置添加复核收件箱入口（具体位置待 5.0 确认后实施）
    - 在 5.0 确认的 slot/位置中添加复核收件箱入口
    - 使用 `roleStore.hasRole(['reviewer', 'partner', 'admin'])` 控制可见性（替代 `v-permission`，因为 DefaultLayout 已有 roleStore）
    - 使用 `el-badge` 显示 `pendingReviewCount`，数量为 0 时隐藏角标
    - 文件：根据 5.0 结果确定（`DefaultLayout.vue` 或 `ThreeColumnLayout.vue` 或 `FourColumnCatalog.vue`）
    - _需求：4.1、4.2、4.3、4.4_

  - [x] 5.2 在 `DefaultLayout.vue` 中实现 badge 数量加载与定时刷新
    - 新增 `pendingReviewCount` ref，`onMounted` 时调用 `getGlobalReviewInbox(1, 1)` 获取 `total`
    - 使用 `setInterval` 每 5 分钟刷新一次，`onBeforeUnmount` 中清理定时器
    - 仅当 `roleStore.hasRole(['reviewer', 'partner', 'admin'])` 时才发起请求
    - 文件：`audit-platform/frontend/src/layouts/DefaultLayout.vue`
    - _需求：4.3、4.5_

  - [x]* 5.3 为属性 6 编写属性测试（权限控制）
    - **属性 6：复核收件箱入口权限控制**
    - **验证：需求 4.1、4.4**

  - [x]* 5.4 为属性 7 编写属性测试（Badge 数量一致性）
    - **属性 7：复核收件箱 Badge 数量一致性**
    - **验证：需求 4.3、4.5**

- [x] 6. 实现底稿列表负责人姓名显示（需求 5）
  - [x] 6.1 在 `WorkpaperList.vue` 中新增用户名映射逻辑
    - 新增 `userNameMap` ref（`Map<string, string>`）
    - 修改已有的 `listUsers()` 调用：加载用户列表时同步建立 `userNameMap`（key 为 `u.id` UUID，value 为 `u.full_name || u.username || u.id`）
    - 新增 `resolveUserName(uuid)` 函数：`null/undefined` 返回"未分配"，未找到返回"未知用户"，找到返回姓名
    - 注意：`listUsers` 返回字段为 `id`（UUID）和 `username`，不是 `display_name`
    - 文件：`audit-platform/frontend/src/views/WorkpaperList.vue`
    - _需求：5.1、5.2、5.3、5.4_

  - [x] 6.2 替换模板中所有 UUID 展示点
    - 将 `{{ selectedWp.assigned_to || '未分配' }}` 等所有直接展示 `assigned_to` 的位置改为 `{{ resolveUserName(selectedWp.assigned_to) }}`
    - 包括详情面板、树形节点 label 等所有展示点
    - 文件：`audit-platform/frontend/src/views/WorkpaperList.vue`
    - _需求：5.1、5.2、5.3_

  - [x]* 6.3 为属性 8 编写属性测试（UUID 映射完整性）
    - **属性 8：UUID 到姓名映射完整性**
    - **验证：需求 5.1、5.2、5.3**

- [x] 7. 实现底稿列表整体进度百分比（需求 6）
  - [x] 7.1 在 `WorkpaperList.vue` 中新增进度计算属性
    - 定义 `COMPLETED_STATUSES = new Set(['review_passed', 'archived'])`（`edit_complete` 不算完成，需通过复核才算）
    - 新增 `totalProgress` computed：基于 `wpList.value`（原始底稿列表）全量计算 `{ completed, total, percent }`
    - 新增 `filteredWpList` computed：基于 `filterCycle`、`filterStatus`、`searchKeyword` 等现有筛选 ref 过滤 `wpList.value`
    - 新增 `filteredProgress` computed：基于 `filteredWpList.value` 计算筛选后进度
    - `percent` 使用 `Math.floor((completed / total) * 100)`，`total` 为 0 时返回 0
    - 注意：`WorkpaperList.vue` 中没有 `filteredWorkpapers` computed，不要引用该变量
    - 文件：`audit-platform/frontend/src/views/WorkpaperList.vue`
    - _需求：6.1、6.2、6.3、6.4_

  - [x] 7.2 在模板中添加进度指示器 UI
    - 在页面顶部添加进度条区域：显示"总体进度：X/Y"、`el-progress` 进度条、百分比数字
    - 有筛选条件时（`hasFilter`）额外显示筛选结果进度
    - 文件：`audit-platform/frontend/src/views/WorkpaperList.vue`
    - _需求：6.1、6.2、6.4_

  - [x]* 7.3 为属性 9 编写属性测试（进度百分比计算正确性）
    - **属性 9：进度百分比计算正确性**
    - **验证：需求 6.2、6.4**

- [x] 8. 实现借贷平衡指示器损益类科目修正（需求 8）
  - [x] 8.1 在 `TrialBalance.vue` 中修正 `liabEquityTotal` 计算属性
    - 删除 `auditType` 相关逻辑（`projectStore.currentProject` 中没有 `audit_type` 字段）
    - 修改 `liabEquityTotal` computed：始终纳入损益类科目，计算 `负债合计 + 权益合计 + 损益净额`
    - 损益净额 = 所有 `account_category` 为 `income`/`cost`/`expense` 的科目 `audited_amount` 之和
    - `isBalanced` 和 `balanceDiff` 逻辑不变，自动使用修正后的 `liabEquityTotal`
    - 文件：`audit-platform/frontend/src/views/TrialBalance.vue`
    - _需求：8.1、8.2、8.3、8.4_

  - [x] 8.2 更新借贷平衡 Tooltip 文案
    - 平衡时固定显示："资产 = 负债 + 权益 + 损益净额"
    - 不平衡时显示："差额：X 元"
    - 删除期中/期末两种文案的条件分支
    - 文件：`audit-platform/frontend/src/views/TrialBalance.vue`
    - _需求：8.3、8.4、8.5_

  - [x]* 8.3 为属性 11 编写属性测试（借贷平衡计算正确性）
    - **属性 11：借贷平衡计算正确性**
    - **验证：需求 8.1、8.3、8.4**

- [x] 8.8 底稿汇总年度从项目上下文获取（需求 29）
  - [x] 8.8.1 修改 `WorkpaperSummary.vue` 年度取值逻辑
    - 引入 `useProjectStore`，新增 `year = computed(() => projectStore.year || new Date().getFullYear())`
    - 将 `doGenerate` 中所有 `new Date().getFullYear()` 替换为 `year.value`
    - 文件：`audit-platform/frontend/src/views/WorkpaperSummary.vue`
    - _需求：29.1_

- [x] 8.9 审计报告导出 Word 入口（需求 30）
  - [x] 8.9.1 `AuditReportEditor.vue` 工具栏新增"导出 Word"按钮
    - 在工具栏添加 `<el-button size="small" @click="onExportWord" :loading="exportingWord" round>导出 Word</el-button>`
    - 新增 `exportingWord` ref 和 `onExportWord` 函数：以 blob 方式调用后端已有的 `export-word` 接口，触发浏览器下载 `.docx` 文件
    - 下载文件名格式：`审计报告_${year.value}.docx`
    - 文件：`audit-platform/frontend/src/views/AuditReportEditor.vue`
    - _需求：30.1、30.2_

- [x] 8.10 QC-17 附件充分性规则改用 ORM 查询（需求 31）
  - [x] 8.10.1 重写 `AttachmentSufficiencyRule.check` 改用 ORM 查询
    - 删除 `sa.text` 裸 SQL，改为 `sa.select(sa.func.count()).select_from(AttachmentWorkpaper).where(...)`
    - 将 `except Exception: count = 0` 替换为：记录 `logger.warning(...)` 并 `return []`
    - 文件：`backend/app/services/qc_engine.py`
    - _需求：31.1、31.2_

- [x] 8.11 调整分录批量驳回支持逐条原因（需求 32）
  - [x] 8.11.1 `Adjustments.vue` 批量驳回弹窗新增逐条原因模式
    - 新增 `rejectMode` ref（`'unified' | 'individual'`，默认 `'unified'`）和 `individualReasons` ref（`Record<string, string>`）
    - 弹窗顶部添加 `el-radio-group` 切换统一/逐条模式
    - 逐条模式下展示选中分录列表，每条旁边有独立 `el-input`
    - 打开弹窗时初始化 `individualReasons`（每条分录 id 对应空字符串）
    - 提交时按模式构建每条分录的驳回原因，逐条模式下原因为空时降级使用统一原因
    - 文件：`audit-platform/frontend/src/views/Adjustments.vue`
    - _需求：32.1、32.2_

- [x] 8.5 错报超限联动 QC 门禁（需求 20）
  - [x] 8.5.1 后端 `gate_rules_phase14.py` 新增错报超限门禁规则
    - 新增 `check_misstatement_exceeds_materiality` 函数：查询 `misstatements` 表累计金额与 `materiality` 表 `overall_materiality` 比较
    - 将该规则集成到门禁检查链中
    - 文件：`backend/app/services/gate_rules_phase14.py`
    - _需求：20.1_

  - [x] 8.5.2 前端 `AuditReportEditor.vue` 新增错报超限警告横幅
    - `onMounted` 时调用 `GET /api/projects/{id}/misstatements/summary`
    - 若 `exceeds_materiality` 为 true，在页面顶部显示 `el-alert` 警告横幅
    - 文件：`audit-platform/frontend/src/views/AuditReportEditor.vue`
    - _需求：20.2_

- [x] 8.6 重要性变更后试算表标记自动更新（需求 21）
  - [x] 8.6.1 后端 `materiality.py` 保存后触发试算表标记更新
    - 在保存重要性水平的路由处理函数中，调用 `trial_balance_service.update_exceeds_materiality_flags(project_id, db)`
    - 文件：`backend/app/routers/materiality.py`
    - _需求：21.1_

  - [x] 8.6.2 前端 `Materiality.vue` 保存成功后发布事件
    - 保存成功后调用 `eventBus.emit('materiality:changed', { projectId: projectId.value })`
    - 文件：`audit-platform/frontend/src/views/Materiality.vue`
    - _需求：21.1_

  - [x] 8.6.3 前端 `TrialBalance.vue` 监听 `materiality:changed` 事件并刷新
    - `onMounted` 注册监听，`onBeforeUnmount` 清理
    - 收到事件且 `projectId` 匹配时调用 `loadRows()` 重新加载数据
    - 文件：`audit-platform/frontend/src/views/TrialBalance.vue`
    - _需求：21.2_

- [x] 8.7 账套导入完成通知（需求 22）
  - [x] 8.7.1 `LedgerPenetration.vue` 导入后启动状态轮询
    - 导入任务提交成功后，启动 `setInterval`（每 3 秒）轮询 `GET /api/projects/{id}/ledger/import-status/{job_id}`
    - 状态变为 `completed` 时：停止轮询，调用 `ElNotification.success`，自动刷新余额表
    - 状态变为 `failed` 时：停止轮询，调用 `ElNotification.error`
    - 超过 10 分钟未完成时：停止轮询，显示"导入状态未知，请手动刷新"提示
    - `onBeforeUnmount` 中清理定时器
    - 文件：`audit-platform/frontend/src/views/LedgerPenetration.vue`
    - _需求：22.1、22.2_

- [x] 8.12 抽样增强年度从项目上下文获取（需求 36）
  - [x] 8.12.1 修改 `SamplingEnhanced.vue` 年度取值逻辑
    - 引入 `useProjectStore`，将 `cutoffForm` 中硬编码的 `year: 2025` 改为 `year: projectStore.year || new Date().getFullYear() - 1`
    - 文件：`audit-platform/frontend/src/views/SamplingEnhanced.vue`
    - _需求：36.1_

- [x] 8.13 审计程序裁剪"参照其他单位"改为下拉选择（需求 37）
  - [x] 8.13.1 修改 `ProcedureTrimming.vue` 参照弹窗为下拉选择
    - 新增 `projectOptions` ref 和 `onMounted` 中调用 `listProjects()` 加载项目列表（失败时静默处理）
    - 将参照弹窗中的 UUID 手动输入框替换为 `el-select`，`filterable` 支持搜索，`label` 显示 `p.name || p.client_name`
    - 文件：`audit-platform/frontend/src/views/ProcedureTrimming.vue`
    - _需求：37.1、37.2_

- [x] 8.14 工时编辑功能修正（需求 38）
  - [x] 8.14.1 修正 `WorkHoursPage.vue` 编辑工时调用接口
    - 新增 `editingHourId` ref（`string | null`，默认 `null`）
    - 修改 `editHour` 函数：设置 `editingHourId.value = row.id`，再填充表单并打开弹窗
    - 修改 `submitHour` 函数：`editingHourId.value` 非空时调用 `updateWorkHour`，为空时调用 `createWorkHour`；提交后重置 `editingHourId.value = null`
    - 弹窗标题和提交按钮文案根据 `editingHourId` 动态切换（"编辑工时"/"填报工时"，"更新"/"保存"）
    - 文件：`audit-platform/frontend/src/views/WorkHoursPage.vue`
    - _需求：38.1、38.2_

- [x] 8.15 知识库文档预览携带认证头（需求 39）
  - [x] 8.15.1 修改 `KnowledgeBase.vue` 图片/PDF 预览逻辑
    - 在 `onPreviewDoc` 函数中，对 `isImageFile(doc)` 或 `isPdfFile(doc)` 的情况，改为通过 `httpApi.get(..., { responseType: 'blob' })` 获取文件内容
    - 用 `new Blob([response], { type: ... })` 创建 blob，再用 `URL.createObjectURL(blob)` 生成 `previewUrl`
    - 在 `onBeforeUnmount` 中检查 `previewUrl.value.startsWith('blob:')` 后调用 `URL.revokeObjectURL` 清理
    - 文件：`audit-platform/frontend/src/views/KnowledgeBase.vue`
    - _需求：39.1_

- [x] 8.16 QC 归档检查结果缓存（需求 40）
  - [x] 8.16.1 修改 `QCDashboard.vue` 归档检查逻辑
    - 新增 `archiveLoading` ref（若不存在）
    - 修改 Tab 切换逻辑：`watch(activeTab, ...)` 中，切换到 `'archive'` 且 `!archiveResult.value` 时，先尝试 `GET` 加载上次结果（`getArchiveReadiness`），失败时静默处理（不自动执行检查）
    - 新增 `loadArchive` 函数：调用 `runArchiveReadinessCheck`（POST）重新执行检查，更新 `archiveResult`
    - 模板中添加上次检查时间显示（`archiveResult.checked_at`）和"重新检查"按钮（绑定 `loadArchive`）
    - 无上次结果时显示"执行归档前检查"按钮
    - 文件：`audit-platform/frontend/src/views/QCDashboard.vue`
    - _需求：40.1、40.2_

- [x] 8.17 底稿列表编制人筛选下拉框填充（需求 41）
  - [x] 8.17.1 在 `WorkpaperList.vue` 的 `onMounted` 中补充用户列表加载
    - 在 `onMounted` 中调用 `listUsers()`，将结果同时赋值给 `userOptions` 和 `userNameMap`
    - 注意：`listUsers` 已在 imports 中引入，无需新增 import
    - 文件：`audit-platform/frontend/src/views/WorkpaperList.vue`
    - _需求：41.1_

  - [x] 8.17.2 替换编制人筛选下拉框为动态选项
    - 将 `<el-option label="全部" value="" />` 替换为 `v-for="u in userOptions"` 动态渲染
    - `value` 使用 `u.id`（UUID），`label` 使用 `u.full_name || u.username`
    - 文件：`audit-platform/frontend/src/views/WorkpaperList.vue`
    - _需求：41.2、41.3_

- [x] 8.18 底稿编辑器状态栏姓名显示（需求 42）
  - [x] 8.18.1 在 `WorkpaperEditor.vue` 中新增用户名映射逻辑
    - 新增 `userNameMap` ref 和 `resolveUserName` 函数（逻辑与 WorkpaperList 一致）
    - 在 `initUniver` 中非阻塞调用 `loadUserMap()`
    - 文件：`audit-platform/frontend/src/views/WorkpaperEditor.vue`
    - _需求：42.1、42.2、42.3_

  - [x] 8.18.2 替换状态栏中的 UUID 展示
    - 将 `{{ wpDetail.assigned_to || '未分配' }}` 改为 `{{ resolveUserName(wpDetail.assigned_to) }}`
    - 将 `{{ wpDetail.reviewer || '未分配' }}` 改为 `{{ resolveUserName(wpDetail.reviewer) }}`
    - 文件：`audit-platform/frontend/src/views/WorkpaperEditor.vue`
    - _需求：42.1、42.2_

- [x] 8.19 底稿编辑器版本历史入口（需求 43）
  - [x] 8.19.1 工具栏新增"版本历史"按钮和侧边抽屉
    - 新增 `showVersionDrawer`、`versionList`、`versionLoading` ref
    - 新增 `onShowVersions` 函数：调用 `GET /api/workpapers/${wpId}/versions`
    - 工具栏右侧新增 `<el-button size="small" @click="onShowVersions">📋 版本历史</el-button>`
    - 新增 `el-drawer` 展示版本列表（`el-timeline`），显示版本号和保存时间
    - 文件：`audit-platform/frontend/src/views/WorkpaperEditor.vue`
    - _需求：43.1、43.2、43.3_

- [x] 8.20 底稿编辑器自动保存（需求 44）
  - [x] 8.20.1 复用 `useAutoSave` composable 实现自动保存
    - 引入 `useAutoSave`（已有，附注编辑器在用）
    - 新增 `autoSaveMsg` ref 和 `watch(loading, ...)` 在加载完成后启动自动保存
    - `onSave` 改为返回 `Promise<boolean>`（需求 14.2 已要求，此处确认）
    - `onUnmounted` 中调用 `stopAutoSave()`
    - 状态栏新增 `<span v-if="autoSaveMsg" style="color: #67c23a">✓ {{ autoSaveMsg }}</span>`
    - 文件：`audit-platform/frontend/src/views/WorkpaperEditor.vue`
    - _需求：44.1、44.2、44.3、44.4_

- [x] 8.21 底稿并发编辑版本冲突检测（需求 45）
  - [x] 8.21.1 后端 `univer-save` 端点新增 `expected_version` 参数校验
    - 从 `body` 中读取 `expected_version`（可选）
    - 若 `expected_version is not None` 且 `wp.file_version != expected_version`，返回 HTTP 409
    - 文件：`backend/app/routers/working_paper.py`
    - _需求：45.1、45.2_

  - [x] 8.21.2 前端 `onSave` 携带 `expected_version` 并处理 409 响应
    - 请求体新增 `expected_version: wpDetail.value.file_version`
    - 捕获 409 响应，弹出 `ElMessageBox.confirm` 提供"刷新放弃"和"强制覆盖"两个选项
    - 文件：`audit-platform/frontend/src/views/WorkpaperEditor.vue`
    - _需求：45.1、45.2、45.3_

- [x] 8.22 预填充引擎保留公式字段（需求 46）
  - [x] 8.22.1 修改 `prefill_workpaper_real` 函数，改为更新 structure.json 的 v 字段
    - 删除 `cell_obj.value = value`（覆盖公式为静态数字）
    - 删除将公式移入 comment 的代码
    - 改为读取 `structure.json`，只更新对应单元格的 `v` 字段，保留 `f` 字段
    - 若 `structure.json` 不存在，记录 warning 日志并跳过该单元格（不修改 xlsx）
    - 文件：`backend/app/services/prefill_engine.py`
    - _需求：46.1、46.2、46.3_

- [x] 9. Sprint 2 检查点
  - 确保所有测试通过，如有疑问请向用户确认。

---

## Sprint 3：P2+P3 前置（需求 7 → 15 → 16 → 11 → 10）

- [x] 10. 实现项目启动流程步骤引导（需求 7）
  - [x] 10.1 在 `TrialBalance.vue` 中新增步骤状态机（基于 localStorage）
    - 步骤引导放在 `TrialBalance.vue` 的空数据区域（`rows.length === 0` 时显示），因为试算表是整个流程的终点
    - 步骤状态通过 `localStorage` 持久化，key 为 `setup_step_{projectId}`，避免跨页面状态丢失
    - 新增 `setupCurrentStep` computed（getter/setter 读写 localStorage）
    - 新增 `setupStepStatus` computed（基于 `setupCurrentStep` 推导 `['finish'|'process'|'wait', ...]`）
    - 新增 `showSetupGuide` computed：`rows.value.length === 0` 时为 true
    - 实现 `advanceSetupStep()` 函数：`setupCurrentStep.value + 1`
    - 文件：`audit-platform/frontend/src/views/TrialBalance.vue`
    - _需求：7.1、7.2、7.3、7.4_

  - [x] 10.2 在 `TrialBalance.vue` 模板中添加 `el-steps` 步骤条 UI
    - 在空数据区域（`v-if="showSetupGuide"`）替换或扩展原有 `el-alert` 为步骤条
    - 包含三步：数据导入、科目映射、重新计算，各步绑定 `setupStepStatus`
    - 各步骤提供跳转按钮：步骤 0 → 导入页，步骤 1 → 映射页，步骤 2 → 触发重算
    - 文件：`audit-platform/frontend/src/views/TrialBalance.vue`
    - _需求：7.1、7.2、7.3、7.5、7.6_

  - [x]* 10.3 为属性 10 编写属性测试（步骤状态单调递进）
    - **属性 10：步骤状态单调递进**
    - **验证：需求 7.2、7.3**

- [x] 10.5 底稿 xlsx 公式值预加载（需求 15）
  - [x] 10.5.1 修改 `xlsx_to_univer.py`，双次加载 xlsx
    - 将 `load_workbook(str(path), data_only=False)` 保存为 `wb_formula`
    - 新增 `wb_value = load_workbook(str(path), data_only=True)` 获取计算值版本
    - 遍历单元格时同时获取两个 workbook 对应位置的 cell，传入 `_convert_cell`
    - 文件：`backend/app/services/xlsx_to_univer.py`
    - _需求：15.1_

  - [x] 10.5.2 修改 `_convert_cell` 函数，公式单元格 `v` 字段使用计算值
    - 函数签名改为 `_convert_cell(cell: Cell, value_cell: Cell | None = None)`
    - 公式单元格（`cell.value.startswith("=")`）：若 `value_cell.value is not None`，将其作为 `v` 字段值（按类型设置 `t`）；否则 `v = ""`
    - 文件：`backend/app/services/xlsx_to_univer.py`
    - _需求：15.1、15.2_

- [x] 10.6 底稿导出 PDF（需求 16）
  - [x] 10.6.1 后端新增 `export-pdf` 端点
    - 在 `working_paper.py` 中新增 `GET /working-papers/{wp_id}/export-pdf` 端点
    - 使用 LibreOffice headless（`subprocess.run(["libreoffice", "--headless", "--convert-to", "pdf", ...])`）将 xlsx 转换为 PDF
    - 转换超时设为 60 秒，失败时返回 HTTP 500 并附带错误信息
    - 返回 `Response(content=pdf_bytes, media_type="application/pdf")`，Content-Disposition 含中文文件名（RFC 5987 编码）
    - 文件：`backend/app/routers/working_paper.py`
    - _需求：16.1、16.2、16.3_

  - [x] 10.6.2 前端 `WorkpaperEditor.vue` 工具栏新增"导出 PDF"按钮
    - 在工具栏右侧新增 `<el-button size="small" @click="onExportPdf" :loading="exportingPdf">📄 导出 PDF</el-button>`
    - 新增 `exportingPdf` ref 和 `onExportPdf` 函数：调用 `export-pdf` 端点，以 blob 方式接收响应，触发浏览器下载
    - 文件：`audit-platform/frontend/src/views/WorkpaperEditor.vue`
    - _需求：16.1、16.2_

- [x] 11. 统一路由前缀规范（需求 11）
  - [x] 11.1 修改 `router_registry.py` 删除 Phase 14 hasattr 补丁
    - 找到 Phase 14 的 `for r in [gate_router, trace_router, sod_router]:` 循环
    - 将 `prefix="/api" if not hasattr(r, 'prefix') or not r.prefix.startswith('/api') else ""` 替换为直接 `prefix="/api"`
    - 因为 gate/trace/sod 三个路由器内部 prefix 均为 `/gate`、`/trace`、`/sod`（不含 `/api`），直接加 `/api` 是正确的
    - 在文件头添加路由前缀规范注释（含 dashboard 例外说明：内部带 `/api/dashboard`，注册时不加额外前缀）
    - 文件：`backend/app/router_registry.py`
    - _需求：11.1、11.2、11.3、11.4、11.5_

  - [x]* 11.2 为属性 14 编写属性测试（路由前缀规范一致性）
    - **属性 14：路由前缀规范一致性**
    - **验证：需求 11.1、11.2、11.4**

- [x] 12. 实现后台定时任务模块化拆分（需求 10）
  - [x] 12.1 新增 `sla_worker.py` 模块
    - 创建 `backend/app/workers/sla_worker.py`
    - 实现 `async def run(stop_event: asyncio.Event) -> None`
    - 每 900 秒（15 分钟）调用 `issue_ticket_service.check_sla_timeout(db)` 并提交
    - 异常时记录 warning 日志并继续，`CancelledError` 时 break 退出
    - 文件：`backend/app/workers/sla_worker.py`（新增）
    - _需求：10.1、10.3、10.5_

  - [x] 12.2 新增 `import_recover_worker.py` 模块
    - 创建 `backend/app/workers/import_recover_worker.py`
    - 实现 `async def run(stop_event: asyncio.Event) -> None`
    - 检查 `settings.LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED`，每 30 秒调用 `ImportJobRunner.recover_jobs()`
    - 文件：`backend/app/workers/import_recover_worker.py`（新增）
    - _需求：10.1、10.3、10.5_

  - [x] 12.3 新增 `outbox_replay_worker.py` 模块
    - 创建 `backend/app/workers/outbox_replay_worker.py`
    - 将 `main.py` 中 `_outbox_replay_loop` 的完整逻辑迁移至此
    - 函数签名改为 `async def run(stop_event: asyncio.Event) -> None`，`while True` 改为 `while not stop_event.is_set()`
    - 文件：`backend/app/workers/outbox_replay_worker.py`（新增）
    - _需求：10.1、10.3、10.5_

  - [x] 12.4 重构 `main.py` lifespan 函数
    - 提取 `_run_migrations()` 辅助函数（数据库迁移逻辑）
    - 提取 `_register_phase_handlers()` 辅助函数（Phase 14/15 事件处理器注册）
    - 提取 `_start_workers(stop_event)` 辅助函数（启动所有 worker，返回 task 列表）
    - `lifespan` 函数精简至 ~25 行，仅负责编排
    - 文件：`backend/app/main.py`
    - _需求：10.2、10.3、10.4_

  - [x]* 12.5 为属性 13 编写属性测试（Worker 异常隔离）
    - **属性 13：Worker 异常隔离**
    - **验证：需求 10.5**

- [x] 12.6 底稿工作台 AI 分析本地缓存（需求 23）
  - [x] 12.6.1 `WorkpaperWorkbench.vue` 新增 `aiAnalysisCache` Map
    - 新增 `const aiAnalysisCache = ref<Map<string, any>>(new Map())`
    - 修改 `loadAiAnalysis` 函数：先检查缓存，命中时直接赋值返回，不发请求；未命中时请求完成后写入缓存
    - 文件：`audit-platform/frontend/src/views/WorkpaperWorkbench.vue`
    - _需求：23.1、23.2_

- [x] 12.7 报表对比视图新增上年审定数列（需求 24）
  - [x] 12.7.1 `ReportView.vue` 对比视图表格新增"上年审定数"列
    - 在对比视图（`reportMode === 'compare'`）的表头新增"上年审定数"列
    - 数据行新增 `{{ fmt(row.prior_period_amount) }}`（字段已存在于 `compareRows`）
    - 文件：`audit-platform/frontend/src/views/ReportView.vue`
    - _需求：24.1、24.2_

- [x] 12.8 序时账异常凭证视觉标记（需求 25）
  - [x] 12.8.1 `LedgerPenetration.vue` 扩展 `ledgerRowClass` 函数
    - 从 `projectStore.currentProject` 获取 `performance_materiality` 和 `audit_period_end`
    - 新增三种 CSS class：
      - `gt-ledger-row--over-materiality`：借方或贷方金额绝对值超过执行重要性水平（橙色背景 + 警告图标）
      - `gt-ledger-row--period-end`：凭证日期在审计期末最后 6 天内（含周末缓冲，约 5 个工作日）（"截止"标记）
      - `gt-ledger-row--red-reversal`：借方或贷方金额为负数（红色文字）
    - 在组件 `<style scoped>` 中添加对应 CSS 样式
    - 文件：`audit-platform/frontend/src/views/LedgerPenetration.vue`
    - _需求：25.1、25.2、25.3_

- [x] 13. Sprint 3 检查点
  - 确保所有测试通过，如有疑问请向用户确认。

---

## Sprint 4：P3 核心（需求 9 → 12）

- [x] 14. 实现数据库迁移至 PostgreSQL（需求 9）
  - [x] 14.1 配置 PostgreSQL 连接池参数
    - 在 `database.py` 中针对 PostgreSQL URL 配置连接池：`pool_size=20`、`max_overflow=80`、`pool_timeout=30`、`pool_recycle=1800`、`echo=False`
    - 文件：`backend/app/core/database.py`
    - _需求：9.1、9.5_

  - [x] 14.2 更新环境变量示例文件
    - 在 `.env.example` 中添加 PostgreSQL `DATABASE_URL` 示例和注释说明
    - 区分生产环境（PostgreSQL）和开发环境（SQLite 可选）
    - 文件：`.env.example`
    - _需求：9.1、9.5_

  - [x] 14.3 验证并补全 Alembic 迁移脚本
    - 检查 `backend/app/migrations/` 目录下现有迁移脚本
    - 若表数量不足 144，运行 `alembic revision --autogenerate -m "add_missing_tables"` 生成补全脚本
    - 确保迁移脚本覆盖全部 144 张表及索引
    - 文件：`backend/app/migrations/`
    - _需求：9.2、9.4_

  - [x]* 14.4 为属性 12 编写属性测试（数据库迁移完整性）
    - **属性 12：数据库迁移完整性**
    - **验证：需求 9.2**

- [x] 15. 实现压测验证脚本完善（需求 12）
  - [x] 15.1 完善 `load_test.py` 覆盖核心接口
    - 确认覆盖 5 个核心接口：`POST /api/auth/login`、`GET /api/projects/{id}/working-papers`、`GET /api/projects/{id}/working-papers/{wp_id}`、`GET /api/projects/{id}/disclosure-notes`、`GET /api/dashboard/overview`
    - 文件：`load_test.py`
    - _需求：12.1_

  - [x] 15.2 完善压测报告输出格式
    - 确保报告输出包含：`total_requests`、`duration_seconds`、`tps`、`avg_response_ms`、`p95_response_ms`、`p99_response_ms`、`error_rate`
    - 按接口分组输出各接口的 `avg_ms`、`p99_ms`、`error_rate`
    - 若未达性能目标，在报告中标注瓶颈接口并输出慢查询日志
    - 文件：`load_test.py`
    - _需求：12.2、12.3、12.4、12.5_

- [x] 16. 最终检查点
  - 确保所有测试通过，如有疑问请向用户确认。

---

## 备注

- 标有 `*` 的子任务为可选测试任务，可在 MVP 阶段跳过
- 每个任务均引用了具体需求条款，便于追溯
- 属性测试使用后端 Hypothesis、前端 fast-check（需安装：`npm install -D fast-check`）
- Sprint 4 的需求 9 需要 PostgreSQL 环境就绪后才能完整验证
