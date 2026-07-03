# Implementation Plan: G11 投资收益底稿专属HTML精美组件

## Overview

实现G11投资收益专属组件 `g11-investment-income`，覆盖9个有效sheet。科目6111（损益类/贷方），核心特色为收益率分析G11-4（平均余额+收益率+异常波动）。架构采用sheetName v-if分发 + defineAsyncComponent懒加载 + 子目录分组(core/analysis/voucher)。

前端：TypeScript + Vue 3 Composition API + Element Plus
后端：Python FastAPI + asyncpg

## Tasks

- [ ] 1. 公式引擎与注册基础
  - [ ] 1.1 实现 useG11FormulaEngine.ts（6个纯函数）
    - 创建 `audit-platform/frontend/src/components/workpaper/composables/useG11FormulaEngine.ts`
    - 实现 parseNum / calcAdjustedAmount / calcChangeRate / calcAverageBalance / calcReturnRate / isDebitCreditBalanced
    - parseNum: null/undefined/NaN/空字符串/'  '/'abc' → 0；有效数值→原值
    - calcAdjustedAmount: 审定 = 未审 + 调整
    - calcChangeRate: (current - prior) / |prior|，prior=0→null
    - calcAverageBalance: (opening + closing) / 2
    - calcReturnRate: income / avgBalance，avgBalance=0→null
    - isDebitCreditBalanced: |SUM(debits) - SUM(credits)| < 0.01
    - _Requirements: 9.1, 9.2, 3.3, 3.5, 7.2, 7.3, 7.4, 6.1_

  - [ ]* 1.2 PBT: Property 1 — 审定数公式
    - **Property 1: 审定数公式**
    - ∀ unadjusted, adj ∈ ℝ: calcAdjustedAmount(unadjusted, adj) === unadjusted + adj
    - **Validates: Requirements 3.3, 9.1**

  - [ ]* 1.3 PBT: Property 2 — 平均余额公式
    - **Property 2: 平均余额**
    - ∀ opening, closing ∈ ℝ≥0: calcAverageBalance(opening, closing) === (opening+closing)/2
    - **Validates: Requirements 7.2, 9.1**

  - [ ]* 1.4 PBT: Property 3 — 收益率公式
    - **Property 3: 收益率公式**
    - ∀ income ∈ ℝ, avgBalance > 0: calcReturnRate(income, avgBalance) === income/avgBalance
    - **Validates: Requirements 7.3, 9.2**

  - [ ]* 1.5 PBT: Property 4 — 收益率除零保护
    - **Property 4: 收益率除零保护**
    - ∀ income ∈ ℝ: calcReturnRate(income, 0) === null
    - **Validates: Requirements 7.3, 9.2**

  - [ ]* 1.6 PBT: Property 5 — 变动率方向性与除零保护
    - **Property 5: 变动率方向性与除零保护**
    - ∀ current, prior ∈ ℝ where prior ≠ 0: calcChangeRate(current, prior) === (current - prior) / |prior|；calcChangeRate(any, 0) === null
    - **Validates: Requirements 3.5, 5.3, 9.1**

  - [ ]* 1.7 PBT: Property 6 — 借贷平衡恒等
    - **Property 6: 借贷平衡恒等**
    - ∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) === (|SUM(debits) - SUM(credits)| < 0.01)
    - **Validates: Requirements 6.1, 9.1**

  - [ ]* 1.8 PBT: Property 7 — parseNum健壮性
    - **Property 7: parseNum健壮性**
    - ∀ input ∈ {null, undefined, '', NaN, '  ', 'abc'}: parseNum(input) === 0；∀ n ∈ ℝ (finite): parseNum(n) === n
    - **Validates: Requirements 9.1**

  - [ ] 1.9 注册四件套
    - htmlRendererRegistry: 'g11-investment-income' → GtG11InvestmentIncome.vue
    - wp_code_overrides.json: 10条映射（含排除修订前→onlyoffice-sheet）
    - VALID_COMPONENT_TYPES: 添加 'g11-investment-income'
    - RENDERER_DISPATCH: 'g11-investment-income' → render_g11_investment_income
    - _Requirements: 1.1, 1.3_

- [ ] 2. 主入口与数据层Composable
  - [ ] 2.1 实现主入口 GtG11InvestmentIncome.vue
    - 创建 `audit-platform/frontend/src/components/workpaper/GtG11InvestmentIncome.vue`
    - 接收 props: htmlData / sheetName / wpId / projectId / readonly
    - sheetName正则提取编码 → v-if分发到9个子组件（defineAsyncComponent懒加载）
    - 集成 useVersionTrail（autoSnapshot）、provide openReviewDialog、useG11DualMode
    - 未匹配sheetName → OnlyOffice fallback
    - _Requirements: 1.1, 1.2, 1.4, 9.3_

  - [ ] 2.2 实现 useG11FormData.ts
    - 创建 `audit-platform/frontend/src/components/workpaper/composables/useG11FormData.ts`
    - selfLoad逻辑（htmlData为null时自动请求render-config）
    - 保存逻辑（PUT /workpapers/{id}/content + autoSnapshot）
    - trial_balance取数（科目6111，发生额字段）
    - writebackTB回写审定数
    - 自动重试3次(指数退避) + localStorage暂存
    - _Requirements: 1.4, 3.4, 9.3_

  - [ ] 2.3 实现 useG11DualMode.ts
    - 创建 `audit-platform/frontend/src/components/workpaper/composables/useG11DualMode.ts`
    - HTML ↔ OnlyOffice双模式切换 + localStorage持久化
    - _Requirements: 9.7_

- [ ] 3. Checkpoint - 基础验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. 核心Sheet组件（core/）
  - [ ] 4.1 实现 G11TabProcedure.vue（G11A 程序表）
    - 创建 `audit-platform/frontend/src/components/workpaper/g11-investment-income/core/G11TabProcedure.vue`
    - 复用 a-program-console（22行×10列）
    - 集成 GtVoucherSamplingEngine（科目6111, dialog-mode）
    - 集成 useCutoffAutoSampling（accountCode:'6111', days:5）
    - selfLoad逻辑
    - _Requirements: 2.1, 9.3_

  - [ ] 4.2 实现 G11TabAdjudication.vue（G11-1 审定表，79行×11列）
    - 创建 `audit-platform/frontend/src/components/workpaper/g11-investment-income/core/G11TabAdjudication.vue`
    - 按投资类型分组（8大类+合计），79行多层结构
    - 列结构：项目|本期(未审|调整|审定)|上期(未审|调整|审定)|变动额|变动率|原因分析|索引
    - 损益类公式：本期审定 = calcAdjustedAmount(未审, 调整)
    - 变动率 = calcChangeRate(本期审定, 上期审定)
    - |变动率|>20% → 橙色高亮 + 原因分析必填
    - 虚拟滚动（79行）+ 分组折叠
    - EventBus publish `substantive:adjudicated`(accountCode='6111')
    - inject openReviewDialog → section标题栏右侧按钮
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 9.6_

  - [ ]* 4.3 单元测试: G11-1 变动率>20%高亮 + 核对异常自动检测
    - 验证|changeRate|>0.2时触发橙色+必填
    - 验证本期和上期使用相同公式结构（对称性）
    - _Requirements: 3.5, 3.8_

  - [ ] 4.4 实现 G11TabDetailAnalysis.vue（G11-2 明细分析表，39行×13列）
    - 创建 `audit-platform/frontend/src/components/workpaper/g11-investment-income/core/G11TabDetailAnalysis.vue`
    - 13列：投资项目名称|投资类型(下拉)|被投资单位|持股比例|投资余额|本期收益|上期收益|变动额|变动率|收益来源说明(textarea)|是否关联方|索引|备注
    - 按投资类型分组小计+总计
    - 变动率公式 = calcChangeRate(currentIncome, priorIncome)
    - 动态行增删（ElMessageBox.prompt输入投资项目名称）
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ] 4.5 实现 G11TabAdjustment.vue（G11-3 调整分录，23行×10列）
    - 创建 `audit-platform/frontend/src/components/workpaper/g11-investment-income/core/G11TabAdjustment.vue`
    - 标准AJE/RJE分录表 + 借贷平衡校验（isDebitCreditBalanced）
    - 借贷差额≠0红色提示
    - 动态行增删 + 回写审定表
    - _Requirements: 6.1_

  - [ ] 4.6 实现 G11TabDisclosureListed.vue（附注-上市，34行×5列）
    - 创建 `audit-platform/frontend/src/components/workpaper/g11-investment-income/core/G11TabDisclosureListed.vue`
    - EventBus subscribe `substantive:adjudicated` 刷新
    - EventBus publish `disclosure:note-text-updated`
    - AI辅助（section标题行右侧AI按钮）
    - _Requirements: 4.1, 4.3_

  - [ ] 4.7 实现 G11TabDisclosureSOE.vue（附注-国企，26行×4列）
    - 创建 `audit-platform/frontend/src/components/workpaper/g11-investment-income/core/G11TabDisclosureSOE.vue`
    - 同上市附注联动逻辑
    - _Requirements: 4.2, 4.3_

  - [ ] 4.8 实现 G11TabDirectory.vue（底稿目录）
    - 创建 `audit-platform/frontend/src/components/workpaper/g11-investment-income/core/G11TabDirectory.vue`
    - 底稿目录页（21行×7列），只读展示
    - _Requirements: 1.2_

- [ ] 5. Checkpoint - core/ 组件验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. 特色Sheet: 收益率分析G11-4
  - [ ] 6.1 实现 G11TabReturnRateAnalysis.vue（G11-4，31行×10列）
    - 创建 `audit-platform/frontend/src/components/workpaper/g11-investment-income/analysis/G11TabReturnRateAnalysis.vue`
    - 顶部方法论上下文（琥珀色左边线+浅黄背景）
    - 10列：投资项目|类型(下拉)|期初余额|期末余额|平均余额(公式)|本期收益|收益率(公式)|上期收益率|收益率变动|异常说明(textarea)
    - 平均余额 = calcAverageBalance(opening, closing)
    - 收益率 = calcReturnRate(income, averageBalance)，null时显示"N/A"+tooltip
    - 收益率变动 = returnRate - priorReturnRate
    - |收益率变动|>5pp → 橙色高亮行 + tooltip"收益率异常波动"
    - 底部：审计结论textarea(AI辅助) + details折叠编制提示
    - 动态行增删（ElMessageBox.prompt输入投资项目名称）
    - inject openReviewDialog → section标题栏AI+复核按钮
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [ ]* 6.2 单元测试: 收益率变动>5pp标记逻辑
    - 验证|returnRateChange|>0.05时橙色高亮行
    - 验证平均余额为0时收益率显示"N/A"
    - _Requirements: 7.3, 7.5_

- [ ] 7. 宽表Sheet: 凭证检查G11-5
  - [ ] 7.1 实现 G11TabVoucherCheck.vue（G11-5，45行×17列→3区段Tab）
    - 创建 `audit-platform/frontend/src/components/workpaper/g11-investment-income/voucher/G11TabVoucherCheck.vue`
    - 3区段Tab切换（凭证基础7列 / 核对内容5列 / 结论5列），行同步
    - Tab1: 日期|凭证编号|业务内容|对方科目|借方|贷方|📎附件(OCR触发)
    - Tab2: 文件描述|✓完整|✓授权|✓账务正确|✓收益确认正确
    - Tab3: 索引号(GtIndexChip)|是否异常|异常说明|风险等级(下拉)|备注
    - Tab2任一✗ → Tab3 isAbnormal自动true + 橙色高亮
    - 顶部借贷差额汇总（差额≠0红色）— isDebitCreditBalanced
    - 集成 GtVoucherSamplingEngine（科目6111, dialog-mode）
    - 行级OCR: 📎上传→POST /d4/contract-ocr→ElMessageBox确认→mergeOCRResult
    - 动态行增删 + GtIndexChip
    - _Requirements: 8.1, 8.2, 8.3_

  - [ ]* 7.2 单元测试: G11-5核对异常自动检测 + 3区段Tab行同步
    - 验证check1-4任一false时isAbnormal自动true
    - 验证Tab切换保持行索引一致
    - _Requirements: 8.1, 8.2_

- [ ] 8. Checkpoint - 前端全部组件验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. 后端服务
  - [ ] 9.1 实现 _g11_investment_income.py（render策略）
    - 创建 `backend/app/routers/wp_render_strategies/_g11_investment_income.py`
    - render_g11_investment_income函数：返回componentType='g11-investment-income' + sheets配置
    - 注册到 RENDERER_DISPATCH
    - _Requirements: 1.1, 1.3_

  - [ ] 9.2 实现 _g11_investment_income_service.py（业务逻辑）
    - 创建 `backend/app/routers/wp_render_strategies/_g11_investment_income_service.py`
    - G11InvestmentIncomeService类
    - get_trial_balance_data: 科目6111取发生额
    - save_adjudication: 保存审定数据+公式验证
    - validate_formulas: 后端公式校验（与前端一致）
    - _Requirements: 3.4, 9.1_

  - [ ] 9.3 实现 _g11_investment_income_import_export.py（导入导出12端点）
    - 创建 `backend/app/routers/wp_render_strategies/_g11_investment_income_import_export.py`
    - 4张表(G11-2/G11-3/G11-4/G11-5) × 3端点(export-template/export-data/import-data) = 12端点
    - G11-5宽表按区段分sheet导出（3sheet）
    - 中文文件名RFC5987编码
    - _Requirements: 5.4, 6.1, 7.7, 8.3, 9.4_

  - [ ] 9.4 实现 _g11_investment_income_ai.py（AI 3 section）
    - 创建 `backend/app/routers/wp_render_strategies/_g11_investment_income_ai.py`
    - POST /api/workpapers/{wp_id}/g11/ai/{section}
    - section: adjudication-analysis / return-rate-conclusion / voucher-conclusion
    - _Requirements: 9.5_

- [ ] 10. 导入导出Composable
  - [ ] 10.1 实现 useG11ImportExport.ts
    - 创建 `audit-platform/frontend/src/components/workpaper/composables/useG11ImportExport.ts`
    - 4张表导入导出：G11-2 / G11-3 / G11-4 / G11-5
    - el-dropdown"导入导出▾"(导出模板/导出数据/导入数据)
    - 使用http(axios)不能用原生fetch
    - _Requirements: 5.4, 7.7, 8.3, 9.4_

- [ ] 11. 后端PBT测试
  - [ ]* 11.1 PBT(后端): 公式验证7属性
    - 创建 `backend/tests/test_g11_investment_income_pbt.py`
    - 用 hypothesis (max_examples=5) 验证后端公式函数
    - 覆盖 Property 1-7 全部属性
    - Tag: Feature: g11-investment-income, Property {N}: {描述}
    - **Validates: Requirements 9.1, 9.2, 3.3, 7.2, 7.3, 6.1**

  - [ ]* 11.2 集成测试: API端点
    - 创建 `backend/tests/test_g11_investment_income_api.py`
    - 测试 render策略 + 12导入导出端点 + 3 AI端点
    - _Requirements: 1.1, 9.4, 9.5_

- [ ] 12. Final checkpoint - 全部测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (7 properties × front+back)
- 损益类科目核心区别：取发生额非余额，本期/上期模式（非期初/期末）
- G11-4收益率分析为本组件最大特色，需重点关注公式正确性和异常标记逻辑
- G11-5凭证检查宽表(17列)拆分为3区段Tab，行同步是关键实现点
- 后端导入导出用StreamingResponse + RFC5987中文文件名编码

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.9"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "2.1", "2.2", "2.3"] },
    { "id": 2, "tasks": ["4.1", "4.8", "9.1", "9.2"] },
    { "id": 3, "tasks": ["4.2", "4.4", "4.5", "9.3", "9.4"] },
    { "id": 4, "tasks": ["4.3", "4.6", "4.7", "10.1"] },
    { "id": 5, "tasks": ["6.1", "7.1"] },
    { "id": 6, "tasks": ["6.2", "7.2", "11.1", "11.2"] }
  ]
}
```
