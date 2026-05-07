# Sprint 2（P1）需求文档 — 核心改造

## 目标

角色感知导航、弹窗规范化、编辑模式统一、协同锁、自动保存、工时合并、右键扩展、撤销增强、stale 可视化、错误处理规范、快捷键帮助。2 周完成。

## 需求清单

### R7-S2-01：侧栏 navItems 动态化
- ThreeColumnLayout.vue 的 navItems 改为 computed，优先读 roleStore.navItems
- 后端 navItems 不可用时回退硬编码 + 按 effectiveRole 覆盖路径
- 灰度开关 VITE_DYNAMIC_NAV（默认 false，验证后开启）

### R7-S2-02：全局替换 ElMessageBox.confirm
- 盘点所有 views/*.vue 中直接使用 ElMessageBox.confirm 的位置（约 15 处）
- 全部替换为 Sprint 1 新增的 confirm.ts 语义化函数
- CI 规则：新代码不得直接 import ElMessageBox.confirm（允许 .prompt/.alert）

### R7-S2-03：所有编辑页接入 useEditMode
- 接入清单：WorkpaperEditor / AuditReportEditor / ReportConfigEditor / TemplateManager / Adjustments / Materiality / ReportView
- 默认进入"查看模式"，显式点击"编辑"切换
- 未保存时路由切换触发 confirmLeave 拦截
- 编辑模式顶部加黄色横条"✏️ 编辑中 · 请记得保存"

### R7-S2-04：useEditingLock composable + 5 编辑器接入
- 新建 composables/useEditingLock.ts
- 进入编辑模式时 acquire lock，心跳 2 分钟，beforeUnload release
- 返回 { locked, lockedBy, isMine }
- 接入：WorkpaperEditor / DisclosureEditor / AuditReportEditor / ReportConfigEditor / TemplateManager
- 他人持锁时显示"XX 正在编辑，只读模式"

### R7-S2-05：useWorkpaperAutoSave composable
- 新建 composables/useWorkpaperAutoSave.ts
- setInterval 每 2 分钟调 onSave
- 状态：saving / lastSavedAt / lastError / isDirty
- 绑定到 SyncStatusIndicator
- 接入 WorkpaperEditor + DisclosureEditor

### R7-S2-06：工时填报/审批 Tab 合并
- WorkHoursPage.vue 内部改为 Tab：填报 / 审批 / 统计
- 审批 Tab 用 v-if="can('approve_workhours')" 控制
- 删除 WorkHoursApproval.vue 独立路由（内容迁入 Tab）
- 后端补 workhour_status 字典到 /api/system/dicts
- 所有工时状态 tag 换 GtStatusTag

### R7-S2-07：右键菜单模块扩展
- TrialBalance：穿透到序时账 / 打开底稿 / 查看调整分录
- ReportView：穿透到行明细 / 查看公式
- Adjustments：转未更正错报
- DisclosureEditor：取数到该单元格
- ConsolidationIndex：穿透到企业构成
- 通过 CellContextMenu 的 slot 注入

### R7-S2-08：单元格编辑纳入 operationHistory
- 扩展 operationHistory 接收 cell_edit 类型
- 所有 GtEditableTable 的 @change 事件挂 history
- Ctrl+Z 可恢复到上一步单元格修改

### R7-S2-09：Stale 状态三态可视化
- WorkpaperList / TrialBalance 的一致性列增加第三态 🔄 stale
- 点击 stale 图标弹窗显示原因 + "立即重算"按钮
- 后端端点 GET /api/projects/{pid}/stale-summary 返回 stale 底稿列表

### R7-S2-10：错误处理规范 errorHandler.ts
- 新建 utils/errorHandler.ts
- 提供 handleApiError(e, context) 统一策略
- 网络错误/401/403/404/409/5xx 分级处理
- 5xx 显示 trace_id + "复制"按钮
- 全局替换 catch 块中的手搓 ElMessage.error

### R7-S2-11：Trace ID 暴露
- error toast 右下角加"复制 trace id"小按钮
- trace_id 从响应头 X-Request-ID 获取（http.ts 拦截器存储）

### R7-S2-12：快捷键帮助面板
- 新建 components/common/ShortcutHelpDialog.vue
- F1 或 ? 触发（shortcut:help 事件）
- 按 scope 分组展示 shortcutManager.getAll()
- 支持搜索
