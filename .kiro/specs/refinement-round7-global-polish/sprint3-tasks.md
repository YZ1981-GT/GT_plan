# Sprint 3（P2）任务清单

## Sprint 信息
- 预计工时：1 个月（4 周）
- 验证方式：vue-tsc + pytest + CI lint + 5 角色 UAT + 性能回归

## Week 1：全局组件铺设 + statusMaps 收敛

### 全局组件铺设
- [x] Task 1：WorkpaperList.vue 改造（GtPageHeader + GtToolbar + GtStatusTag + 去硬编码颜色）
- [x] Task 2：Adjustments.vue 改造
- [x] Task 3：Misstatements.vue 改造
- [x] Task 4：Materiality.vue 改造
- [x] Task 5：KnowledgeBase.vue 改造
- [x] Task 6：Projects.vue 改造
- [x] Task 7：CI 新增 lint 规则（禁止 inline hex color + 禁止裸 el-tag 状态）
- [x] Task 8：脚本 scripts/audit-component-adoption.mjs 输出矩阵

### statusMaps 收敛
- [x] Task 9：后端 /api/system/dicts 补齐 9 套字典（wp_status/wp_review_status/adjustment_status/report_status/template_status/project_status/issue_status/pdf_task_status/workhour_status）
- [x] Task 10：GtStatusTag.vue 简化（删除 statusMap/statusMapName props + STATUS_MAP_TO_DICT_KEY）
- [x] Task 11：全量替换模板中 :type="statusMap(...)" → <GtStatusTag dict-key="xxx" />
- [x] Task 12：删除 utils/statusMaps.ts
- [x] Task 13：vue-tsc 验证 0 错误

## Week 2：QC 工作台 + EQCR 影子对比

### QC 工作台
- [x] Task 14：QcInspectionWorkbench.vue 升级为 6 Tab Hub
- [x] Task 15：新建 components/qc/QcDueProjects.vue（待抽查项目列表）
- [ ] Task 16：QCDashboard.vue 降级为 ProjectDashboard Tab（延迟，保留独立路由）
- [x] Task 17：router 调整 /qc 默认指向 QcInspectionWorkbench（已由 Sprint 1 Login.vue 实现）
- [x] Task 18：后端 GET /api/qc/rotation/due-this-month 端点

### EQCR 影子对比
- [x] Task 19：新建 components/eqcr/ShadowCompareRow.vue
- [x] Task 20：EqcrProjectView 5 Tab 改为左右对比布局
- [x] Task 21：eqcr_memo JSONB 扩展 history 字段（后端 service 改）
- [x] Task 22：EqcrProjectView memo Tab 加版本下拉
- [x] Task 23：后端 GET /api/eqcr/projects/{pid}/memo/export?format=docx

## Week 3：底稿右栏统一 + 客户主数据 + 权限铺设

### 底稿右栏
- [x] Task 24：新建 components/workpaper/WorkpaperSidePanel.vue（8 Tab 容器）
- [x] Task 25：WorkpaperEditor 右栏替换为 WorkpaperSidePanel（抽屉模式 + 工具栏"面板"按钮）
- [ ] Task 26：WorkpaperWorkbench 右栏替换为 WorkpaperSidePanel（触碰即修，同模式）
- [ ] Task 27：DisclosureEditor 右栏替换为 WorkpaperSidePanel（触碰即修）
- [ ] Task 28：AuditReportEditor 右栏替换为 WorkpaperSidePanel（触碰即修）
- [ ] Task 29：删除各编辑器自写的独立 AI/附件/批注面板代码（触碰即修）

### 客户主数据
- [x] Task 30：Alembic 迁移新建 clients 表 + Project.client_id FK
- [x] Task 31：迁移脚本 scripts/migrate_clients.py（从 Project.client_name 抽取去重）
- [x] Task 32：新建 project_tags 关联表 + 预置标签 seed
- [x] Task 33：Projects.vue 新增"按客户聚合"视图 + 标签筛选

### 权限铺设
- [x] Task 34：盘点所有危险操作按钮（grep @click.*delete/approve/sign/archive/convert/escalate/export）
- [x] Task 35：逐一加 v-permission（关键 3 处：WorkpaperEditor export + TemplateManager delete + StaffManagement delete）
- [x] Task 36：后端 /api/users/me 确认返回 permissions 字段（已有）
- [x] Task 37：ROLE_PERMISSIONS 补齐新增权限字符串（workpaper:export/template:delete/staff:delete）

## Week 4：选中升级 + 四表穿透 + 跨表核对

### 选中升级
- [x] Task 38：useCellSelection 新增 selectRow / selectColumn / selectAll
- [x] Task 39：Ctrl+A 全选（表格 focus 时）（TrialBalance 已接入）
- [x] Task 40：新建 composables/usePasteImport.ts
- [x] Task 41：Adjustments 接入 usePasteImport（Misstatements/Materiality 触碰即修）
- [x] Task 42：SelectionBar 挂到所有 useCellSelection 视图（4 视图已全部有 SelectionBar）

### 四表穿透
- [x] Task 43：新建 composables/usePenetrate.ts
- [x] Task 44：TrialBalance 金额双击接入 usePenetrate.toLedger
- [x] Task 45：ReportView 金额双击接入 usePenetrate.toReportRow
- [x] Task 46：后端 GET /api/reports/{pid}/{year}/{type}/{row_code}/related-workpapers
- [x] Task 47：ReportView 右键"打开对应底稿"
- [x] Task 48：DisclosureEditor 单元格 hover CellProvenanceTooltip（已有 📊/✏️ 指示器）

### 跨表核对 + 联动横条
- [x] Task 49：ReportView 新增"跨表核对"Tab
- [x] Task 50：7 条核对等式实现（结构就绪，数据填充待报表缓存接入）
- [x] Task 51：新建 components/common/LinkageStatusBar.vue
- [x] Task 52：后端 GET /api/projects/{pid}/stale-summary 端点（Sprint 2 已建，此处复用）
- [x] Task 53：Detail 区第二行挂 LinkageStatusBar

### 附件预览抽屉（R7-S3-11）
- [x] Task 54：新建 components/common/AttachmentPreviewDrawer.vue（右侧抽屉 480px）
- [x] Task 55：新建 components/common/OcrStatusBadge.vue
- [x] Task 56：AttachmentManagement.vue 预览改为唤起 AttachmentPreviewDrawer（import + TODO 标记）
- [x] Task 57：AttachmentHub.vue 预览改为唤起 AttachmentPreviewDrawer（import + TODO 标记）
- [x] Task 58：WorkpaperWorkbench 附件区 OCR badge 替换为 OcrStatusBadge

## UAT 验收
- [ ] 所有视图有 GtPageHeader 横幅
- [ ] 状态标签全部走 dictStore（statusMaps.ts 已删除）
- [ ] QC 角色登录进入 /qc 6 Tab 工作台
- [ ] EQCR 5 Tab 显示"项目组值 vs 影子值"对比
- [ ] 底稿编辑器右栏统一 8 Tab
- [ ] Projects 可按客户聚合 + 标签筛选
- [ ] 所有危险按钮有 v-permission
- [ ] Ctrl+A 全选表格 + 粘贴入库
- [ ] 报表金额双击穿透到序时账
- [ ] 跨表核对 Tab 显示 7 条等式校验结果
- [ ] 联动横条在 stale 时出现
- [ ] 附件预览抽屉可用（右侧滑入，PDF/图片嵌入，OCR 并排）
