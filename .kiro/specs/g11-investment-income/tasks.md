# Implementation Plan: G11 投资收益底稿专属HTML精美组件

## Overview

实现G11投资收益专属组件 `g11-investment-income`，覆盖9个有效sheet。科目6111（损益类/贷方），核心特色为收益率分析G11-4（平均余额+收益率+异常波动）。架构采用sheetName v-if分发 + defineAsyncComponent懒加载 + 子目录分组(core/analysis/voucher)。

前端：TypeScript + Vue 3 Composition API + Element Plus
后端：Python FastAPI + asyncpg

## Tasks

- [x] 1. 公式引擎与注册基础
  - [x] 1.1 实现 useG11FormulaEngine.ts（6个纯函数）
  - [x]* 1.2 PBT: Property 1 — 审定数公式
  - [x]* 1.3 PBT: Property 2 — 平均余额公式
  - [x]* 1.4 PBT: Property 3 — 收益率公式
  - [x]* 1.5 PBT: Property 4 — 收益率除零保护
  - [x]* 1.6 PBT: Property 5 — 变动率方向性与除零保护
  - [x]* 1.7 PBT: Property 6 — 借贷平衡恒等
  - [x]* 1.8 PBT: Property 7 — parseNum健壮性
  - [x] 1.9 注册四件套

- [x] 2. 主入口与数据层Composable
  - [x] 2.1 实现主入口 GtG11InvestmentIncome.vue
  - [x] 2.2 实现 useG11FormData.ts（含 retry + localStorage draft + TB writeback）
  - [x] 2.3 实现 useG11DualMode.ts

- [x] 3. Checkpoint - 基础验证

- [x] 4. 核心Sheet组件（core/）
  - [x] 4.1 实现 G11TabProcedure.vue（G11A 程序表）
  - [x] 4.2 实现 G11TabAdjudication.vue（G11-1 审定表，18数据行+61指引行）
  - [x]* 4.3 单元测试: G11-1 变动率>20%高亮 + 核对异常自动检测
  - [x] 4.4 实现 G11TabDetailAnalysis.vue（G11-2 明细分析表，13列）
  - [x] 4.5 实现 G11TabAdjustment.vue（G11-3 调整分录）
  - [x] 4.6 实现 G11TabDisclosureListed.vue（附注-上市）
  - [x] 4.7 实现 G11TabDisclosureSOE.vue（附注-国企）
  - [x] 4.8 实现 G11TabDirectory.vue（底稿目录）

- [x] 5. Checkpoint - core/ 组件验证

- [x] 6. 特色Sheet: 收益率分析G11-4
  - [x] 6.1 实现 G11TabReturnRateAnalysis.vue（期初/期末→平均投资/收益率）
  - [x]* 6.2 单元测试: 收益率变动>5pp标记逻辑

- [x] 7. 宽表Sheet: 凭证检查G11-5
  - [x] 7.1 实现 G11TabVoucherCheck.vue（3区段Tab + G11 OCR端点）
  - [x]* 7.2 单元测试: G11-5核对异常自动检测 + 3区段Tab行同步

- [x] 8. Checkpoint - 前端全部组件验证

- [x] 9. 后端服务
  - [x] 9.1 实现 _g11_investment_income.py（render策略 + TB取数）
  - [x] 9.2 实现 _g11_investment_income_service.py（业务逻辑）
  - [x] 9.3 实现 _g11_investment_income_import_export.py（导入导出15端点）
  - [x] 9.4 实现 _g11_investment_income_ai.py（AI 3 section）
  - [x] 9.5 实现 _g11_contract_ocr.py（凭证 OCR）

- [x] 10. 导入导出Composable
  - [x] 10.1 实现 useG11ImportExport.ts（G11-1~5）

- [x] 11. 后端PBT测试
  - [x]* 11.1 PBT(后端): 公式验证7属性
  - [x]* 11.2 集成测试: API端点

- [x] 12. Final checkpoint - 全部测试通过

- [x] 13. 增强项（第二轮「全做」）
  - [x] 13.1 G11-5 AI 抽查结论（`voucher-conclusion` + 结论区 UI）
  - [x] 13.2 G11-3 → G11-1/G11-2 调整回写（`g11AdjStorage` + `syncWriteback`）
  - [x] 13.3 后端 `validate-formulas` / `save-adjudication` HTTP API
  - [x] 13.4 G11-2 分组汇总 + 附注行扩展（上市 33 / 国企 25）
  - [x] 13.5 G11-CHK-01/02 fine-rule 勾稽标签 + 发布审定数联动校验
  - [x] 13.6 E2E 扩展（G11-5 分段 Tab、validate-formulas、fine-checks）

## Notes

- G11-1 数据行与 xlsx 一致（18行），编制指引 61 行只读展示，合计 79 行结构
- 导入导出：5张表 × 3端点 = 15（含 G11-1 审定表 object-store）
- 修订前 sheet 映射为 `skip`（非 onlyoffice-sheet）
