# 表格统一化 — 任务清单

> 执行顺序：Sprint 4（简单练手）→ Sprint 1（核心）→ Sprint 2（报表）→ Sprint 3（合并）→ Sprint 5（收尾）
>
> **每个表格迁移前必须**：先 readCode 分析现有表格的列定义/数据结构/交互逻辑/样式，确认适配方案后再动手。不能盲目替换。

## Sprint 4：辅助表格（先做，练手验证模式，5 task）

- [x] 4.1 CustomQueryDialog.vue 转置视图迁移
- [x] 4.2 FormulaEditDialog.vue 公式编辑目标表迁移
- [x] 4.3 DocumentOCRPanel.vue 2 处 OCR 结果表迁移
- [x] 4.4 KnowledgeBasePanel.vue 知识库文档表迁移
- [x] 4.5 RiskAssessmentPanel.vue 风险矩阵热力图迁移

## Sprint 1：核心表格（P0，6 task）

- [x] 1.0 前置：提取 el-table 统一样式到全局 CSS（紫色表头/边框色/字号 class/表头 nowrap），所有后续 Sprint 复用
- [x] 1.1 TrialBalance.vue 试算平衡表迁移到 el-table（双行表头 + 可编辑列 + 行样式 + 右键菜单）
- [x] 1.2 接入 useCellSelection（单元格选中/多选/拖拽/Ctrl+A）
- [x] 1.3 接入 CellContextMenu（复制/公式/明细/溯源）
- [x] 1.4 删除原生 table CSS（.gt-tb-summary-table 相关样式）
- [x] 1.5 验证：双行表头显示正确 + 可编辑列正常 + 合计行样式 + 字号跟随 Aa

## Sprint 2：报表表格（P0，4 task）

- [x] 2.1 ReportView.vue 权益变动表迁移（动态列 v-for + span-method 合并单元格）
- [x] 2.2 ReportView.vue 减值准备表迁移
- [x] 2.3 接入 useCellSelection + CellContextMenu
- [x] 2.4 删除原生 table CSS（.gt-rv-eq-table 相关样式）

## Sprint 3：合并报表（P1，3 task）

- [x] 3.1 ConsolidationIndex.vue 3 处矩阵表迁移（动态列 + 合并单元格）
- [x] 3.2 ConsolTrialBalanceTab.vue 合并试算表迁移
- [x] 3.3 删除原生 table CSS（.gt-consol-matrix-table 相关样式）

## Sprint 5：收尾（P2，3 task）

- [x] 5.1 GtPrintPreview.vue 打印预览表迁移（需验证打印效果）
- [x] 5.2 全局样式统一：将 el-table 紫色表头/边框色/字号 class 提取到全局 CSS 文件
- [x] 5.3 最终验证：grep `<table` 确认 0 处原生 table（排除剪贴板 HTML）

## UAT 验收

- [ ] U1 试算平衡表：双行表头 + 单元格选中 + 右键菜单 + 可编辑列 + 合计行样式
- [ ] U2 权益变动表：动态列 + 合并单元格 + 横向滚动
- [ ] U3 合并报表矩阵：多公司列 + 数据正确
- [ ] U4 所有表格字号跟随 Aa 设置
- [ ] U5 vue-tsc 零错误
