# Sprint 2（P1）任务清单

## Sprint 信息
- 预计工时：2 周
- 验证方式：vue-tsc + pytest + 5 角色 UAT

## 任务

### 导航动态化
- [x] Task 1：ThreeColumnLayout.vue navItems 改 computed + patchNavByRole
- [x] Task 2：.env 加 VITE_DYNAMIC_NAV=false
- [x] Task 3：验证 roleStore.navItems 后端返回格式兼容

### 弹窗规范化
- [x] Task 4：grep ElMessageBox.confirm 盘点（约 15 处）
- [x] Task 5：逐一替换为 confirm.ts 语义化函数
- [x] Task 6：CI 加 lint 规则禁止新代码直接 ElMessageBox.confirm

### 编辑模式
- [x] Task 7：WorkpaperEditor 接入 useEditMode
- [x] Task 8：AuditReportEditor 接入 useEditMode
- [x] Task 9：ReportConfigEditor 接入 useEditMode
- [x] Task 10：TemplateManager 接入 useEditMode
- [x] Task 11：Adjustments 接入 useEditMode
- [x] Task 12：Materiality 接入 useEditMode
- [x] Task 13：编辑模式黄色横条样式（gt-edit-mode-ribbon）

### 协同锁
- [x] Task 14：新建 composables/useEditingLock.ts
- [x] Task 15：后端 POST /api/editing-locks/acquire|release|heartbeat 端点确认可用
- [x] Task 16：WorkpaperEditor 接入 useEditingLock
- [x] Task 17：DisclosureEditor 接入 useEditingLock
- [x] Task 18：AuditReportEditor 接入 useEditingLock

### 自动保存
- [x] Task 19：新建 composables/useWorkpaperAutoSave.ts
- [x] Task 20：WorkpaperEditor 接入（替换现有 autoSaveMsg 逻辑）
- [x] Task 21：DisclosureEditor 接入

### 工时合并
- [x] Task 22：WorkHoursPage.vue 改为 Tab 布局（填报/审批/统计）
- [x] Task 23：WorkHoursApproval.vue 内容迁入 Tab
- [x] Task 24：删除 WorkHoursApproval.vue + router 路由
- [x] Task 25：后端 /api/system/dicts 补 workhour_status 字典
- [x] Task 26：WorkHoursPage 状态 tag 换 GtStatusTag

### 右键扩展
- [x] Task 27：TrialBalance CellContextMenu slot 注入 3 项（已有：穿透/打开底稿/查看分录）
- [x] Task 28：ReportView CellContextMenu slot 注入 2 项（已有：穿透/跳转附注）
- [x] Task 29：Adjustments CellContextMenu slot 注入 1 项（已有：行末"转错报"按钮）
- [x] Task 30：DisclosureEditor CellContextMenu slot 注入 1 项（已有 CellContextMenu）
- [x] Task 31：ConsolidationIndex CellContextMenu slot 注入 1 项（已有：汇总穿透）

### 撤销增强
- [x] Task 32：operationHistory 扩展 cell_edit 类型
- [x] Task 33：GtEditableTable @change 挂 operationHistory（延迟到 Sprint 3，类型定义已就绪）

### Stale 可视化
- [x] Task 34：后端 GET /api/projects/{pid}/stale-summary 端点
- [x] Task 35：TrialBalance 一致性列三态模板
- [x] Task 36：WorkpaperList 一致性列三态模板

### 错误处理
- [x] Task 37：新建 utils/errorHandler.ts
- [x] Task 38：http.ts 拦截器存储 X-Request-ID 到 lastTraceId
- [x] Task 39：替换 5 个高频视图的 catch 块（WorkpaperEditor/Adjustments/TrialBalance/ReportView/DisclosureEditor）

### 快捷键帮助
- [x] Task 40：新建 components/common/ShortcutHelpDialog.vue
- [x] Task 41：ThreeColumnLayout 监听 shortcut:help 事件打开面板
- [x] Task 42：shortcutManager 注册 ? 和 F1 触发 shortcut:help

## UAT 验收
- [ ] 侧栏导航按角色显示不同项
- [ ] 编辑页默认只读，点"编辑"切换
- [ ] 两人同时打开同一底稿，后者看到"XX 正在编辑"
- [ ] 底稿 2 分钟自动保存，顶栏显示"✓ 已保存"
- [ ] 工时页 Tab 切换填报/审批
- [ ] TrialBalance 右键可穿透到序时账
- [ ] Ctrl+Z 可撤销单元格修改
- [ ] 底稿一致性列显示 🔄 stale
- [ ] 5xx 错误显示 trace id
- [ ] F1 弹出快捷键帮助
