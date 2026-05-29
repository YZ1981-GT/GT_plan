# 表格统一化 — 全部迁移到 el-table

## 前言

### 业务痛点
当前系统中表格实现混用原生 HTML `<table>` 和 Element Plus `<el-table>`，导致：
- 交互体验不一致（科目明细有单元格选中/右键/拖拽，试算平衡表没有）
- 样式维护成本高（两套 CSS 体系）
- 功能重复开发（行选择、复制、搜索在每个原生 table 都要手写）

### 技术根因
早期开发时部分复杂表格（双行表头、矩阵表）用原生 table 实现更快，但随着 `useCellSelection` composable 和全局样式体系成熟，el-table 已能覆盖所有场景。

### 本 spec 边界
统一所有原生 HTML table 为 el-table，复用已有的交互基建（useCellSelection/CellContextMenu/TableSearchBar）。

---

## §1 范围

### 1.1 必做（11 处原生 table）

| # | 文件 | 表格用途 | 复杂度 |
|---|------|---------|--------|
| F1 | TrialBalance.vue | 试算平衡表（双行表头） | 高 |
| F2 | ReportView.vue | 权益变动表（多列矩阵） | 高 |
| F3 | ReportView.vue | 减值准备表 | 中 |
| F4 | ConsolidationIndex.vue | 合并报表矩阵（3处） | 高 |
| F5 | ConsolTrialBalanceTab.vue | 合并试算表 | 中 |
| F6 | CustomQueryDialog.vue | 自定义查询转置视图 | 低 |
| F7 | FormulaEditDialog.vue | 公式编辑目标表 | 低 |
| F8 | DocumentOCRPanel.vue | OCR 结果表（2处） | 低 |
| F9 | KnowledgeBasePanel.vue | 知识库文档表 | 低 |
| F10 | RiskAssessmentPanel.vue | 风险矩阵热力图 | 中 |
| F11 | GtPrintPreview.vue | 打印预览表 | 低 |

### 1.2 排除

| # | 说明 |
|---|------|
| O1 | 剪贴板 HTML 生成（`<table border="1">` 用于 clipboard write，不是渲染用） |
| O2 | 底稿编辑器（继续用 Univer） |
| O3 | 第三方组件内部的 table（如 el-descriptions） |

---

## §2 功能需求

### F1 试算平衡表迁移
- 双行表头用嵌套 `<el-table-column>` 实现
- 复用 `useCellSelection` 支持单元格选中/多选/拖拽
- 复用 `CellContextMenu` 右键菜单
- 保留可编辑列（重分类调整借方/贷方）
- 合计行/分类行样式通过 `row-class-name` 实现
- 表头固定（el-table 原生 max-height）

### F4 合并报表矩阵迁移（ConsolidationIndex 3 处）
- 动态列（子公司列按项目组成员动态生成）用 `v-for` 嵌套 `<el-table-column>` 实现
- 合并单元格用 `:span-method` 实现
- 横向滚动保留（el-table 原生支持）
- **动态新增列**：用户可新增子公司列，el-table 响应式更新（v-for 绑定动态数组）
- **弹窗编辑**：单元格点击弹出编辑弹窗（如抵消分录编辑器），el-table slot 内嵌 el-dialog
- **列宽自适应**：动态列数变化时列宽自动调整（min-width + flex）
- **冻结首列**：项目名称列固定（el-table-column fixed="left"）

### F5 合并试算表迁移（ConsolTrialBalanceTab）
- 多公司列动态生成
- 合计列自动计算
- 支持展开/折叠子公司明细

### 通用要求
- 所有迁移后的表格统一接入 `useCellSelection`（可选，按需）
- 所有表格字号跟随 displayPrefs（动态 class 方案）
- 所有表格表头 `white-space: nowrap`
- 金额列统一 `.gt-amt` class
- **迁移后必须保留的编辑功能**：
  - 单元格点击编辑（如试算平衡表的重分类调整列）
  - 单元格/行选中（单选 + Shift 范围多选 + Ctrl 追加选择）
  - 选中样式：仅高亮背景色，不显示单元格边框（边框色设为透明）
  - 右键菜单（复制/查看公式/汇总明细/数据溯源）
  - Ctrl+C 复制选中区域（Tab 分隔，支持粘贴到 Excel）
  - Ctrl+A 全选
  - Ctrl+F 搜索
  - 双击穿透/溯源
  - 表头固定（滚动时不动）
  - 行样式区分（合计行加粗/分类行紫色/选中行高亮）
  - 列宽可拖拽调整
  - 导出 Excel（保留现有导出功能）

---

## §3 非功能需求

### 3.1 性能
- 迁移后页面首屏渲染时间不增加 >100ms
- 大数据表格（>500 行）使用 el-table 虚拟滚动或分页

### 3.2 兼容性
- 迁移过程中不破坏现有功能（逐个文件迁移，每个文件独立验证）
- 保留所有现有的复制/导出功能

### 3.3 可维护性
- 迁移后删除所有原生 table 相关的 CSS（gt-consol-matrix-table/gt-rv-eq-table/gt-tb-summary-table 等）
- 统一使用全局 el-table 样式覆盖

---

## §4 测试与回归

### 4.1 每个文件迁移后的验收 checklist
- [ ] getDiagnostics 零错误
- [ ] 数据显示正确（行数/金额与迁移前一致）
- [ ] 表头固定正常（滚动时不动）
- [ ] 可编辑列正常（点击进入编辑，blur 保存）
- [ ] 右键菜单正常弹出
- [ ] 选中高亮正常（只有背景色，无边框）
- [ ] 字号跟随 Aa 设置
- [ ] 导出 Excel 功能正常
- [ ] 复制粘贴功能正常

### 4.2 迁移顺序策略
- 先从简单表格练手（Sprint 4 的 F6-F11），验证 el-table 替换模式
- 再做核心复杂表格（Sprint 1-2 的 F1-F4）
- 实际执行顺序：Sprint 4 → Sprint 1 → Sprint 2 → Sprint 3 → Sprint 5

### 4.3 退出条件
- GtPrintPreview（F11）：如果 el-table 打印效果不如原生 table（`@media print` 样式丢失），保留原生 table 不迁移
- 性能：如果迁移后渲染时间增加 >200ms（合并报表矩阵 200+ 行场景），回退或使用 el-table-v2 虚拟滚动

### 4.4 性能基线
- 迁移前记录合并报表矩阵（ConsolidationIndex）的首屏渲染时间
- 迁移后对比，不允许劣化 >200ms

### 4.5 样式回归
- 迁移后表格视觉效果必须与当前一致或更好
- 紫色表头、边框色、行间距、金额对齐等不能"变丑"
- 每个 Sprint 完成后截图对比

---

## §5 成功判据

| 指标 | 目标 |
|------|------|
| 原生 HTML table 数量 | 0（排除 O1-O3） |
| el-table 统一样式覆盖 | 全局 1 套 CSS |
| useCellSelection 接入率 | 核心 4 个表格（试算/报表/合并/查账） |
| 字号跟随 Aa 设置 | 所有表格生效 |

### F2-F3 报表矩阵迁移（权益变动表/减值准备表）
- 多列动态表头用 `v-for` 嵌套 `<el-table-column>` 实现
- 合并单元格用 `:span-method` 实现
- 横向滚动保留

### F6-F11 简单表迁移
- 直接替换为 el-table + el-table-column
- 保留原有的排序/筛选功能
