# 任务清单：审计平台全局化增强

## Sprint 1：收尾 + 快速见效（~3天）

### Task 1.1 — formatters.ts 剩余替换 [R2.1]
- [x] Drilldown.vue 替换本地 fmt 函数为 fmtAmount
- [x] CFSWorksheet.vue 替换
- [x] Adjustments.vue 替换
- [x] Misstatements.vue 替换
- [x] Materiality.vue 替换
- [x] LedgerPenetration.vue 替换（最大，1300+行）
- [x] WorkpaperSummary.vue 替换
- [x] ReviewWorkstation.vue 替换
- [x] MobilePenetration.vue 替换
- [x] 其余 10+ 组件批量替换
- [x] 验证 vue-tsc 零错误 + Vite 构建通过

### Task 1.2 — displayPrefs 接入 13 worksheet [R2.2]
- [x] 13 个 worksheet 组件添加 displayPrefs import + fmt wrapper
- [x] 替换 fmtAmount → fmt（跟随全局单位）
- [x] 添加 `:style="{ fontSize: displayPrefs.fontConfig.tableFont }"`
- [ ] 验证构建

### Task 1.3 — CommentTooltip 接入 [R2.3]
- [x] DisclosureEditor 金额单元格包裹 CommentTooltip
- [x] ConsolidationIndex 报表金额列包裹
- [x] ConsolNoteTab 附注表格包裹
- [x] TrialBalance 金额列包裹（未审数/审定数）

### Task 1.4 — VirtualScrollTable 接入 formatters [R6.7]
- [x] formatCell 改用 fmtAmount 替代内联 toLocaleString

### Task 1.5 — confirm.ts 语义化确认弹窗 [R6.3]
- [x] 创建 utils/confirm.ts：confirmDelete/confirmBatch/confirmDangerous
- [x] 替换 5 个高频模块的 ElMessageBox.confirm 调用
- [x] 验证构建

### Task 1.6 — statusMaps.ts + GtStatusTag [R6.2 + R5.7]
- [x] 创建 utils/statusMaps.ts：WP_STATUS/ADJUSTMENT_STATUS/REPORT_STATUS/TEMPLATE_STATUS 映射表
- [x] 创建 components/common/GtStatusTag.vue
- [x] 替换 TrialBalance/Adjustments/WorkpaperList 的 statusTagType/statusLabel
- [ ] 验证构建

### Task 1.7 — useEditMode composable [R3.4]
- [x] 创建 composables/useEditMode.ts：isEditing/isDirty/enterEdit/exitEdit/markDirty/onBeforeRouteLeave
- [x] 接入 DisclosureEditor（已有 editMode ref）
- [x] 接入 ConsolNoteTab（已有 noteEditMode ref）
- [ ] 验证构建

### Task 1.8 — ExcelImportPreviewDialog [R5.3]
- [x] 创建 components/common/ExcelImportPreviewDialog.vue
- [x] 内置：隐藏 file input + xlsx 解析 + 预览表格 + 统计 + 确认追加
- [x] 替换 SubsidiaryInfoSheet 的导入弹窗（示范）
- [ ] 验证构建

### Task 1.9 — operationHistory 接入 [R6.6]
- [x] 在 Adjustments 删除操作接入 operationHistory.execute
- [x] 在 RecycleBin 永久删除接入
- [x] 验证撤销功能正常

### Task 1.10 — GtAmountCell 金额单元格组件 [R5.6]
- [x] 创建 components/common/GtAmountCell.vue
- [x] 跟随 displayPrefs 格式化 + amountClass 条件格式
- [x] 可点击穿透 + hover 高亮 + CommentTooltip 包裹
- [x] 在 ReportView 本期金额列试点替换

### Task 1.11 — Sprint 1 收尾
- [x] git commit + push
- [x] 更新 memory.md 待办状态

---

## Sprint 2：核心基础设施（~5天）

### Task 2.1 — mitt 事件总线 [R3.1]
- [x] 安装 mitt：`npm i mitt`
- [x] 创建 utils/eventBus.ts：定义 Events 类型映射
- [x] 替换 ThreeColumnLayout 的 gt-switch-four-col CustomEvent
- [x] 替换 ConsolidationIndex 的 consol-standard-change
- [x] 替换 gt-open-formula-manager / gt-formula-changed
- [x] 删除 _redispatched 补丁逻辑
- [x] 验证所有事件通道正常

### Task 2.2 — useProjectStore [R3.2]
- [x] 创建 stores/project.ts
- [x] DefaultLayout watch route 自动同步
- [x] 替换 TrialBalance 的 useProjectSelector
- [x] 替换 ReportView 的手动 projectId/year 解析
- [x] 替换 DisclosureEditor 的手动解析
- [x] 验证路由切换数据同步

### Task 2.3 — apiPaths.ts [R6.1]
- [x] 创建 services/apiPaths.ts：按业务域分组定义所有 API 路径
- [x] 替换 consolidationApi.ts 的硬编码路径
- [x] 替换 auditPlatformApi.ts
- [x] 替换 commonApi.ts
- [x] 逐步替换其余 15 个 service 文件

### Task 2.4 — 后端响应格式统一 [R7.2]
- [x] 审查所有路由：确保只返回业务数据，不自己包装 {code,message,data}
- [x] 修复双重包装的路由
- [x] 前端删除所有 `data?.data ?? data` 兼容代码
- [x] 验证全链路

### Task 2.5 — usePermission + v-permission [R3.10]
- [x] 创建 composables/usePermission.ts：can(permission)/canAny()
- [x] 创建 directives/permission.ts：v-permission="'project:edit'"
- [x] main.ts 注册指令
- [x] 在 Adjustments 删除按钮加 v-permission
- [x] 在 UserManagement 加 v-permission="'admin'"
- [x] 验证权限隐藏/禁用

### Task 2.6 — 路由守卫统一 [R7.1]
- [x] router/index.ts beforeEach：权限守卫
- [x] 项目上下文自动加载（配合 useProjectStore）
- [x] 未保存变更拦截（配合 useEditMode）
- [x] 验证路由切换

### Task 2.7 — API 调用统一收口 [R1.4]
- [x] 审查所有直接 import http 的文件
- [x] 迁移到 apiProxy.ts 或对应 service 文件
- [x] 保留 authHttp（auth store 专用）
- [ ] 验证全链路

### Task 2.8 — 批量操作场景优化 [R1.6]
- [x] 后端：调整分录 API 支持 batch_mode 参数
- [x] 后端：batch_mode=true 时暂不触发事件，提交时统一触发一次
- [x] 前端：调整分录页面加"批量提交"按钮
- [x] 验证：批量录入 20 笔后一次性重算

### Task 2.9 — shortcuts.ts 接入各模块 [R6.4]
- [x] TrialBalance 监听 shortcut:save → 保存试算平衡表
- [x] DisclosureEditor 监听 shortcut:save → 保存附注
- [x] ConsolNoteTab 监听 shortcut:save → 保存附注数据
- [x] 全局 shortcut:undo → operationHistory.undo()
- [x] 验证快捷键不与 Ctrl+F 冲突

### Task 2.10 — Sprint 2 收尾
- [x] git commit + push
- [x] 更新 memory.md

---

## Sprint 3：组件层 + 后端统一（~7天）

### Task 3.1 — GtToolbar 标准工具栏 [R5.1]
- [x] 创建 components/common/GtToolbar.vue
- [x] slot：left（模块特有）/ right（通用：导出/导入/全屏/公式/模板/编辑切换）
- [x] 接入 TrialBalance（示范）
- [x] 接入 ReportView
- [x] 接入 DisclosureEditor

### Task 3.2 — GtPageHeader + GtInfoBar [R5.4 + R5.5]
- [x] 创建 components/common/GtPageHeader.vue：紫色渐变横幅
- [x] 创建 components/common/GtInfoBar.vue：单位/年度/模板选择+徽章
- [x] 替换 TrialBalance 的 gt-tb-banner
- [x] 替换 ReportView 的 gt-rv-banner
- [x] 替换 DisclosureEditor 的 gt-de-banner
- [x] 删除各模块的重复横幅 CSS

### Task 3.3 — useExcelIO composable [R3.5]
- [x] 创建 composables/useExcelIO.ts
- [x] exportTemplate/exportData/parseFile/onFileSelected
- [x] 替换 SubsidiaryInfoSheet 的导出导入逻辑
- [x] 替换 InvestmentCostSheet
- [x] 逐步替换其余 12 个 worksheet

### Task 3.4 — useTableToolbar [R3.3]
- [x] 创建 composables/useTableToolbar.ts
- [x] addRow/deleteSelectedRows/onSelectionChange/exportExcel/importExcel/copyTable
- [x] 接入 ConsolNoteTab（示范）
- [x] 接入 worksheet 组件

### Task 3.5 — useDictStore [R4.1]
- [x] 后端创建 GET /api/system/dicts 接口
- [x] 创建 stores/dict.ts
- [x] 启动时加载，sessionStorage 缓存
- [x] 替换 WorkpaperList 的 statusTagType/statusLabel
- [x] 替换 Adjustments/AuditReportEditor

### Task 3.6 — 后端 PaginationParams/SortParams [R7.3]
- [x] 创建 app/core/pagination.py：PaginationParams/SortParams
- [x] 替换 5 个高频列表 API
- [x] 验证分页排序

### Task 3.7 — 后端批量操作 [R7.4]
- [x] 创建 app/core/bulk_operations.py
- [x] 接入批量删除（RecycleBin/Adjustments）
- [x] 接入批量审批（ReviewInbox）

### Task 3.8 — 后端审计日志装饰器 [R7.5]
- [x] 创建 app/core/audit_decorator.py：@audit_log
- [x] 接入删除操作（before/after diff）
- [x] 接入审批操作
- [x] 接入状态变更

### Task 3.9 — SharedTemplatePicker 扩展 [R5.8]
- [x] 在公式管理页面接入 configType="formula_config"
- [x] 在附注编辑器接入 configType="note_template"
- [x] 在合并范围接入 configType="consol_scope"
- [x] 在科目映射接入 configType="account_mapping"

### Task 3.10 — useCopyPaste composable [R3.6]
- [x] 创建 composables/useCopyPaste.ts
- [x] 复制：选中区域→制表符分隔文本（已有 copySelectedValues，增强为 HTML+纯文本双格式）
- [x] 粘贴：监听 paste 事件，解析制表符文本写入选中区域
- [x] 接入 TrialBalance + ReportView

### Task 3.11 — useKnowledge + KnowledgePickerDialog [R3.7]
- [x] 创建 composables/useKnowledge.ts：search/getDocContent/pickDocuments/buildContext
- [x] 创建 components/common/KnowledgePickerDialog.vue
- [x] 接入 DisclosureEditor AI 续写（提供上下文）
- [x] 接入 AuditReportEditor

### Task 3.12 — useAutoSave 草稿恢复 [R3.8]
- [x] 创建 composables/useAutoSave.ts：定时 localStorage 保存 + 恢复提示
- [x] 接入 DisclosureEditor（附注编辑）
- [x] 接入 ConsolNoteTab（合并附注）
- [x] 接入 Adjustments（调整分录）

### Task 3.13 — useLoading + NProgress [R3.9]
- [x] 安装 nprogress
- [x] 创建 composables/useLoading.ts：withLoading 包装函数
- [x] router beforeEach/afterEach 触发 NProgress
- [x] http.ts 拦截器触发 NProgress
- [x] 替换 3 个高频模块的手动 loading.value

### Task 3.14 — useAddressRegistry Store [R4.2]
- [x] 创建 stores/addressRegistry.ts
- [x] 对接后端 address_registry API
- [x] CellSelector/FormulaRefPicker 改用 store 数据源
- [x] 新增表样后自动刷新

### Task 3.15 — Sprint 3 收尾
- [ ] git commit + push
- [ ] 更新 memory.md

---

## Sprint 4：高阶组件 + 验证 + 优化（~7天）

### Task 4.1 — GtEditableTable 高阶组件 [R5.2]
- [x] 创建 components/common/GtEditableTable.vue
- [x] 内置：useCellSelection + setupTableDrag + useLazyEdit + useEditMode
- [x] 内置：SelectionBar + CellContextMenu + CommentTooltip
- [x] 内置：增删行 + 多选 + 全屏 + displayPrefs
- [x] 列配置声明式（prop/label/width/formatter/sortable/fixed）
- [x] 迁移 ConsolNoteTab 表格（示范）
- [x] 迁移 1-2 个 worksheet 组件验证

### Task 4.2 — 端到端验证 [R1.1]
- [x] 准备测试数据（3-5 家子公司的合并审计项目）
- [x] 导入科目余额表 + 序时账
- [x] 科目映射 + 试算表重算
- [x] 录入调整分录 + 验证五环联动
- [x] 生成报表 + 审核校验
- [x] 生成附注 + AI 续写
- [x] 底稿编制 + QC 检查
- [x] Word 导出
- [x] 记录发现的问题并修复

### Task 4.3 — 数据库 migration [R1.2]
- [x] 创建 backend/migrations/ 目录
- [x] 创建 migration_runner.py：扫描+执行+记录版本
- [x] 创建 schema_version 表
- [x] 将当前 create_all 转为 V001__init.sql
- [x] 在 lifespan 中自动执行迁移
- [x] 验证新表/新列的迁移流程

### Task 4.4 — 合并模块集成测试 [R1.5]
- [x] 创建 test_consolidation_chain.py
- [x] 测试：创建合并范围 → 导入子公司数据
- [x] 测试：合并试算表重算
- [x] 测试：抵消分录 CRUD
- [x] 测试：差额表计算
- [x] 测试：合并报表生成

### Task 4.5 — 事件链路失败通知 + SSE 全局接入 [R1.3 + R6.5]
- [x] 后端：事件处理失败时发布 EventType.SYNC_FAILED
- [x] 后端：SSE 推送失败事件
- [x] 前端：ThreeColumnLayout 接入 sse.ts 全局连接
- [x] 前端：顶栏显示同步状态指示器（成功/失败/进行中）
- [x] 前端：失败时弹出详情面板

### Task 4.6 — 架构优化 [R8]
- [x] Element Plus 按需导入（unplugin-vue-components）
- [x] ResponseWrapperMiddleware 跳过 blob/大文件响应
- [x] POST 请求防重复提交（pendingMap 扩展到 POST）
- [x] 压力测试脚本（locust/k6）

### Task 4.7 — 用户体验 [R9]
- [x] 合并模块向导式步骤条 [R9.1]
- [x] 500 重试 loading 提示 [R9.2]
- [x] 423 锁定详情（锁定人/时间/解锁方式）[R9.3]
- [x] useEditMode 推广到全模块 [R9.4]
- [x] 键盘导航（Tab 切换单元格）+ 批量粘贴（配合 useCopyPaste）[R9.5]

### Task 4.8 — 表格交互 WPS 借鉴 [R10]
- [x] GtEditableTable 列配置支持 hidden/validator/_locked [R10.1/R10.2/R10.3]
- [x] 分组折叠（groupBy 配置）[R10.4]
- [x] 排序筛选默认开启 [R10.5]
- [x] 打印预览弹窗 [R10.6]
- [x] 批注线程（回复链）[R10.7]

### Task 4.9 — 功能完善 [R11]
- [x] 模拟权益法 6 项改进
- [x] 合并抵消分录表汇总中心
- [x] 内部抵消表自动汇总

### Task 4.10 — 最终收尾
- [ ] 全量 vue-tsc + Vite 构建验证
- [ ] git commit + push + 合并到 master
- [ ] 更新 memory.md + architecture.md + dev-history.md
