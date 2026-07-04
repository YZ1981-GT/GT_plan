# Implementation Plan: F2 存货监盘 f2-stocktake-bundle

## Overview

F2-21A + F2-21~26 监盘 HTML 组件。文本模块优先：F2-21~23 纯 SectionForm；F2-24~26 叙述 + 表格 + 导入导出/OCR。主入口 `GtF2StocktakeBundle.vue` + 7 Tab + 5 composable + 后端 4 py。

## Notes

- F2-21 已从 f2-st 导入导出/OCR 行级能力移除
- 旧 `F2-21-rows` 通过 `migrateF21RowsToFields` 双读
- 与 `f2-inventory-main/special/valuation` 独立 componentType

## Tasks

- [x] 1. 注册与主入口
  - [x] 1.1 wp_code F2-21A~F2-26 → f2-stocktake-bundle
  - [x] 1.2 htmlRendererRegistry + VALID_COMPONENT_TYPES
  - [x] 1.3 GtF2StocktakeBundle（Tab + 双模式 + save-items 事件）
  - [x] 1.4 htmlRendererRegistry.spec.ts 契约

- [x] 2. 数据层 composable
  - [x] 2.1 useF2StocktakeFormData（checklist 加载/保存）
  - [x] 2.2 useF2StocktakeSheet（fields/rows + debounce）
  - [x] 2.3 useF2StocktakeDualMode
  - [x] 2.4 migrateF21RowsToFields 旧表双读

- [x] 3. 文本模块 Tab（F2-21~23）
  - [x] 3.1 f2StocktakeConfigs F2_21/22/23_FIELDS
  - [x] 3.2 F2StocktakeSectionForm（stack/multiline/compact）
  - [x] 3.3 F2TabStocktakeQuestionnaire / Plan / Summary
  - [x] 3.4 附件 F2StocktakeSheetAttachments + ItemAttachment

- [x] 4. 混合 Tab（F2-24~26）
  - [x] 4.1 F2_24/25/26_NARRATIVE_FIELDS + compact SectionForm
  - [x] 4.2 F2TabStocktakeReconcile / SampleResult / Rollforward 表格区
  - [x] 4.3 cycleImportExportRegistry f2-st sheets F2-24~26

- [x] 5. 后端
  - [x] 5.1 _f2_stocktake.py render
  - [x] 5.2 _f2_stocktake_import_export.py（F2-24~26）
  - [x] 5.3 _f2_stocktake_contract_ocr.py（F2-24~26）
  - [x] 5.4 _f2_stocktake_ai.py

- [x] 6. OCR / AI 前端
  - [x] 6.1 useF2StocktakeOcr + F2SheetToolbar 📎列
  - [x] 6.2 useF2StocktakeAiGenerate + F2-25 LLM 差异分析

- [x] 7. 测试
  - [x] 7.1 f_cycle_f2_html_contract + phase4/export_import 更新
  - [x] 7.2 test_f2_stocktake_ocr_ai.py
  - [x] 7.3 test_f2_stocktake_import_export.py（F2-21 拒绝）
  - [x] 7.4 useF2StocktakeSheet.spec.ts（迁移 + 持久化）
  - [x] 7.5 e2e f2-html-smoke F2-24 round-trip
  - [x] 7.6 e2e f-cycle-f2-21-inventory-count
  - [x] 7.7 e2e f2-stocktake-html.spec.ts（F2-21~24 文本/混合 + F2-24/25 round-trip）
  - [x] 7.8 单元：cycleImportExportRegistry + useF2StocktakeSheet/Ocr + test_f2_stocktake_contract

- [ ] 8. 可选增强
  - [ ] 8.1 F2-22/23 附件 OCR 填叙述字段
  - [ ] 8.2 首次双读迁移后可选一键写入 F2-21-fields
  - [ ] 8.3 浏览器 E2E 全量回归（需运行环境）
