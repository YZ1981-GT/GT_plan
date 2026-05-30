# Sprint 3（P2）需求文档 — 大改造

## 目标

全局组件铺设、枚举收敛、QC 工作台升级、EQCR 影子对比、底稿右栏统一、客户主数据、权限铺设、选中升级、四表穿透、跨表核对。1 个月完成。

## 需求清单

### R7-S3-01：全局组件铺设 Sprint
- 目标：GtPageHeader 接入率从 6/73 → 73/73
- 分批：高频 6 页先做（WorkpaperList/Adjustments/Misstatements/Materiality/KnowledgeBase/Projects），其余按"触碰即迁移"
- 每页改造内容：banner→GtPageHeader / toolbar→GtToolbar / infobar→GtInfoBar / 金额→GtAmountCell / 状态→GtStatusTag
- CI 新增 lint：禁止 inline hex color + 禁止裸 el-tag 表达状态

### R7-S3-02：statusMaps → dictStore 单向收敛
- 盘点 statusMaps.ts 9 套 StatusMap
- 后端 /api/system/dicts 补齐全部 9 套
- 前端删除 statusMaps.ts
- GtStatusTag 删除 STATUS_MAP_TO_DICT_KEY 桥接表和 fallback 分支
- 所有模板 :type="statusMap(...)" 改为 <GtStatusTag dict-key="xxx" :value="..." />

### R7-S3-03：QC 主工作台升级
- QcInspectionWorkbench.vue 升级为 /qc 根页面，内部 6 Tab
- QCDashboard.vue 降级为 ProjectDashboard 的 Tab "质控"
- 侧栏 QC 角色新增"质控"一级导航（动态导航已就绪）
- 顶栏 QC 角色加"待抽查"badge

### R7-S3-04：EQCR 5 Tab 影子对比 + 备忘录版本
- 新建 components/eqcr/ShadowCompareRow.vue（项目组值 vs 影子值 vs 差异）
- EqcrProjectView 5 判断 Tab 改为左右对比布局
- eqcr_memo JSONB 扩展 history 数组（最多 5 版）
- EqcrProjectView memo Tab 加版本下拉
- 新增 GET /api/eqcr/projects/{pid}/memo/export?format=docx

### R7-S3-05：底稿右栏面板统一 WorkpaperSidePanel
- 新建 components/workpaper/WorkpaperSidePanel.vue
- Tab：AI / 附件 / 版本 / 批注 / 程序要求 / 依赖 / 一致性 / 智能提示
- 接入 WorkpaperEditor / WorkpaperWorkbench / DisclosureEditor / AuditReportEditor / ReportConfigEditor
- 删除各编辑器自写的独立 AI/附件/批注面板

### R7-S3-06：客户主数据 + 项目标签
- 新建 clients 表（id/name/normalized_name/industry/listed/parent_id）
- Project.client_id FK（nullable，保留 client_name 冗余）
- 迁移脚本从 Project.client_name 抽取去重生成 clients
- 新建 project_tags 关联表 + 预置标签
- Projects.vue 支持"按客户聚合"视图 + 标签多选筛选

### R7-S3-07：v-permission 全按钮铺设
- 盘点所有"危险操作按钮"（删除/审批/签字/归档/转错报/催办/导出）
- 逐一加 v-permission
- 后端 /api/users/me 确保返回 permissions 字段
- 前端 ROLE_PERMISSIONS 补齐新增权限字符串

### R7-S3-08：单元格选中升级
- useCellSelection 新增 selectRow / selectColumn / selectAll
- Ctrl+A 全选（表格 focus 时）
- 新建 composables/usePasteImport.ts（粘贴入库）
- Adjustments / Misstatements / Materiality 接入 usePasteImport
- SelectionBar 挂到所有 useCellSelection 视图

### R7-S3-09：四表-报表-底稿-附注统一穿透
- 新建 composables/usePenetrate.ts
- 所有金额单元格双击 → penetrate-by-amount
- 右键 → 5 穿透目标
- 报表行 → 底稿反向跳（后端 GET /api/reports/{pid}/{year}/{type}/{row_code}/related-workpapers）
- 附注单元格 hover 显示 CellProvenanceTooltip

### R7-S3-10：跨表核对视图 + 联动状态横条
- ReportView 新增"跨表核对"Tab
- 7-10 条关键等式自动校验
- 不平时高亮红色 + "定位差异"按钮
- 新建 components/common/LinkageStatusBar.vue
- 当项目有 stale 数据时 Detail 第二行显示黄色横条

### R7-S3-11：附件预览抽屉组件化
- 新建 `components/common/AttachmentPreviewDrawer.vue`
- 从右侧滑入抽屉（480px 宽），替代当前 window.open 新标签预览
- 支持 PDF/图片直接嵌入（iframe / img）
- Word/Excel 调 LibreOffice 转 PDF 后嵌入
- OCR 结果并排显示（左原图右文字）
- 所有附件位置（WorkpaperEditor 右栏、AttachmentManagement、AttachmentHub）统一唤起此抽屉
- 新建 `components/common/OcrStatusBadge.vue`（Props: status: ok|processing|failed|pending）
- 替换 WorkpaperWorkbench 的 `.gt-wpb-ocr-badge` 内联样式
