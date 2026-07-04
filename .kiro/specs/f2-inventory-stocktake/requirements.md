# Requirements: F2 存货监盘专属 HTML 组件

## Introduction

F2-21A 程序表 + F2-21~F2-26 存货监盘底稿的 HTML 精美组件。底稿分析结论：**文本模块优先**（问卷/计划/小结为 d-form-confirmation 长文本），**表格仅用于** F2-24 核对、F2-25 抽盘汇总、F2-26 倒轧明细。componentType=`f2-stocktake-bundle`，OnlyOffice 作降级双模式。

## Glossary

- **Bundle**: `GtF2StocktakeBundle.vue`，Tab 切换 F2-21A + F2-21~26
- **SectionForm**: `F2StocktakeSectionForm.vue`，stack 布局文本字段 + 附件 + AI + 审计结论
- **Hybrid sheet**: F2-24/25/26 = 表前叙述块 + el-table 明细 + 导入导出/OCR

## User Stories

### US-1 监盘问卷与计划（F2-21~23）

**As** 审计人员  
**I want** 按底稿章节填写监盘问卷/计划/小结  
**So that** 不必在 Excel 中维护地点行表

**Acceptance Criteria:**
1. F2-21 使用 `F2-21-fields` JSON 持久化，无行级 Excel 导入导出
2. F2-22/23 多行 textarea 覆盖程序与结论字段
3. 支持附件上传、AI 生成结论、复核对话框

### US-2 核对/抽盘/倒轧（F2-24~26）

**As** 审计人员  
**I want** 表前说明 + 明细表 + OCR/导入  
**So that** 叙述与明细分工清晰

**Acceptance Criteria:**
1. 表前叙述存 `F2-{n}-fields`，明细存 `F2-{n}-rows`，结论存 `F2-{n}-note`
2. F2-24/25/26 支持 export-template / import-data / contract-ocr
3. F2-25 可调用 LLM 差异分析（stocktake-summary）

### US-3 旧数据兼容

**As** 已有项目用户  
**I want** 旧 `F2-21-rows` 自动显示在问卷文本中  
**So that** 升级 HTML 后不丢地点表数据

**Acceptance Criteria:**
1. `F2-21-fields` 为空且存在 `F2-21-rows` 时，双读迁移至 countSchedule/warehouses
2. 用户首次编辑后写入 `F2-21-fields`

### US-4 双模式与注册

**Acceptance Criteria:**
1. wp_code F2-21A~F2-26 → f2-stocktake-bundle
2. HTML ↔ OnlyOffice 切换，localStorage 持久化
3. F-cycle 契约测试映射 f2-stocktake-bundle
