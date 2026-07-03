# Implementation Plan: G7 长期股权投资(main组)底稿专属HTML精美组件

## Overview

G7长期股权投资(main组)专属组件 `g7-long-term-equity-main`，覆盖7个sheet（G7A程序表+G7-1审定表+G7-2明细表+G7-3调整分录+附注上市/国企+底稿目录）。核心挑战：97行最大审定表(分组折叠+虚拟滚动)、54列最宽明细表(5区段Tab+行同步)、355行最长附注(虚拟滚动)、8纯函数公式引擎、5大集成联动。

前端 TypeScript/Vue 3 + 后端 Python/FastAPI。

## Tasks

- [ ] 1. 公式引擎 + 注册基础
  - [ ] 1.1 实现 useG7FormulaEngine.ts（8纯函数+parseNum）
    - 创建 `audit-platform/frontend/src/components/workpaper/composables/useG7FormulaEngine.ts`
    - 实现 parseNum / calcDebitBalance / calcAdjustedAmount / calcEndingCost / calcEndingEquityAdj / calcBookValue / calcChangeRate / isDebitCreditBalanced
    - 每个函数 JSDoc 注释标注公式来源
    - _Requirements: 6.2, 3.3, 5.3, 5.4, 5.5_

  - [ ]* 1.2 PBT: Property 1 借方余额公式
    - **Property 1: calcDebitBalance(opening, debit, credit) === opening + debit - credit**
    - **Validates: Requirements 3.3, 6.2**
    - 文件: `composables/__tests__/useG7FormulaEngine.spec.ts`
    - fast-check numRuns:100

  - [ ]* 1.3 PBT: Property 2 审定数公式
    - **Property 2: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje**
    - **Validates: Requirements 3.3, 6.2**

  - [ ]* 1.4 PBT: Property 3 期末投资成本公式
    - **Property 3: calcEndingCost(opening, increase, decrease) === opening + increase - decrease**
    - **Validates: Requirements 5.3, 6.2**

  - [ ]* 1.5 PBT: Property 4 期末权益法调整公式
    - **Property 4: calcEndingEquityAdj(opening, equityIncrease, equityDecrease) === opening + equityIncrease - equityDecrease**
    - **Validates: Requirements 5.4, 6.2**

  - [ ]* 1.6 PBT: Property 5 账面价值公式
    - **Property 5: calcBookValue(subtotal, impairment) === subtotal - impairment**
    - **Validates: Requirements 5.5, 6.2**

  - [ ]* 1.7 PBT: Property 6 变动率方向性与除零保护
    - **Property 6: calcChangeRate方向性 + calcChangeRate(0, any) === null**
    - **Validates: Requirements 3.5, 6.2**

  - [ ]* 1.8 PBT: Property 7 借贷平衡恒等
    - **Property 7: isDebitCreditBalanced(debits, credits) ↔ |SUM(debits)-SUM(credits)| < 0.01**
    - **Validates: Requirements 6.1, 6.2**

  - [ ]* 1.9 PBT: Property 8 parseNum健壮性
    - **Property 8: parseNum(null/undefined/''/NaN) === 0; parseNum(finite n) === n**
    - **Validates: Requirements 6.2**

  - [ ] 1.10 注册四件套 + componentType
    - wp_code_overrides.json 添加7条映射
    - htmlRendererRegistry 注册 `g7-long-term-equity-main`
    - 后端 VALID_COMPONENT_TYPES 添加
    - 后端 RENDERER_DISPATCH 注册 render_g7_long_term_equity_main
    - _Requirements: 1.1, 1.3_

- [ ] 2. 主入口 + 数据层 composables
  - [ ] 2.1 创建 GtG7LongTermEquityMain.vue 主入口
    - sheetName prop → regex提取编码 → v-if分发7个defineAsyncComponent
    - 未匹配 → OnlyOffice fallback
    - useVersionTrail(wpId) + autoSnapshot
    - provide('openReviewDialog', openReviewDialog)
    - useG7DualMode 双模式切换
    - _Requirements: 1.1, 1.2, 1.4, 6.3, 6.7_

  - [ ] 2.2 实现 useG7FormData.ts
    - selfLoad逻辑(htmlData=null时API加载)
    - 数据加载/保存（指数退避重试3次+localStorage暂存）
    - writebackTB（科目1511审定数回写trial_balance）
    - _Requirements: 1.4, 3.3_

  - [ ] 2.3 实现 useG7DualMode.ts
    - HTML ↔ OnlyOffice 切换 + localStorage持久化模式偏好
    - _Requirements: 6.7_

  - [ ] 2.4 实现 useG7ImportExport.ts
    - 导入导出composable（2张表: G7-2 / G7-3）
    - G7-2按5区段分sheet导出（基础/期初/变动/期末+减值/权益法详情）
    - el-dropdown(导出模板/导出数据/导入数据)
    - _Requirements: 5.6, 6.1, 6.4_

- [ ] 3. Checkpoint - 公式引擎+注册+主入口
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. G7-1 审定表（97行×12列，分组折叠+虚拟滚动）
  - [ ] 4.1 实现 G7TabAdjudication.vue
    - 97行×12列多层结构（5组+净值行）
    - 分组折叠(localStorage持久化折叠状态 per wpId)
    - 虚拟滚动(97行，降级分页模式30行/页)
    - TB取数(1511)显示 + 差异校验
    - |变动率|>20% 橙色高亮 + tooltip
    - 公式列虚线下划线+cursor:help+tooltip来源
    - EventBus publish `substantive:adjudicated`(accountCode='1511')
    - section标题栏右侧复核按钮(inject openReviewDialog)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 6.3, 6.6_

  - [ ]* 4.2 单元测试: G7-1分组折叠+净值计算+变动率高亮
    - 验证collapse/expand切换、子行隐藏/显示
    - 验证netValue = totalAdjusted - impairmentAdjusted
    - 验证|changeRate|>0.2时行class包含orange-highlight
    - _Requirements: 3.1, 3.4, 3.5_

- [ ] 5. G7-2 明细表（54列→5区段Tab+虚拟滚动）
  - [ ] 5.1 实现 G7TabDetail.vue
    - 103行×54列拆为5区段Tab（基础8/期初10/变动12/期末+减值12/权益法12）
    - 虚拟滚动103行
    - 5区段Tab行同步（切换Tab保持selectedRowIndex）
    - Tab4/Tab5公式列自动计算(使用useG7FormulaEngine)
    - 控制类型下拉(子公司/合营/联营)
    - 动态行增删(ElMessageBox.prompt必填被投资单位名称)
    - 底部合计行
    - 导入导出el-dropdown(useG7ImportExport)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.4, 6.6_

  - [ ]* 5.2 PBT: Property 9 五区段Tab行同步
    - **Property 9: 任意selectedRowIndex∈[0,rowCount)，Tab切换后selectedRowIndex保持不变**
    - **Validates: Requirements 5.6**
    - fast-check生成随机rowIndex+随机Tab切换序列

  - [ ]* 5.3 单元测试: G7-2动态行新增+公式计算
    - 验证ElMessageBox取消时不创建行
    - 验证closingInvestCost/closingEquityAdj/closingBookValue/auditedAmount公式
    - 验证shareOfNetAssets = investeeNetAssets × holdingRatio
    - _Requirements: 5.3, 5.4, 5.5, 5.6_

- [ ] 6. G7-3 调整分录 + G7A 程序表 + 底稿目录
  - [ ] 6.1 实现 G7TabAdjustment.vue（G7-3 调整分录）
    - 23行×10列 AJE/RJE
    - 借贷平衡实时校验(差额≠0红色❌)
    - 动态行增删
    - 保存时自动回写G7-1审定表AJE/RJE列
    - 导入导出(useG7ImportExport)
    - _Requirements: 6.1, 6.4_

  - [ ] 6.2 实现 G7TabProcedure.vue（G7A 程序表）
    - 复用 a-program-console（32行×14列）
    - selfLoad逻辑
    - 抽凭引擎(GtVoucherSamplingEngine dialog-mode, accountCodes=['1511'])
    - 截止自动提取(useCutoffAutoSampling, accountCode:'1511', days:5)
    - _Requirements: 2.1, 6.3_

  - [ ] 6.3 实现 G7TabDirectory.vue（底稿目录）
    - 24行×8列静态目录页
    - _Requirements: 1.2_

  - [ ]* 6.4 单元测试: G7-3借贷平衡+AJE回写
    - 验证borrowing/credit平衡检测
    - 验证保存后G7-1对应行AJE/RJE列更新
    - _Requirements: 6.1_

- [ ] 7. Checkpoint - 前端7个子组件完成
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. 附注披露（上市253行+国企355行，虚拟滚动）
  - [ ] 8.1 实现 G7TabDisclosureListed.vue（上市公司附注）
    - 253行×13列虚拟滚动
    - 5个section（成本法/权益法分类+重要合营联营+结构化主体+持股5%+限制性条件）
    - EventBus subscribe `substantive:adjudicated`(accountCode='1511')刷新
    - EventBus publish `disclosure:note-text-updated`(accountCode='1511')
    - 每section AI辅助按钮(section标题行右侧)
    - section标题栏右侧复核按钮
    - _Requirements: 4.1, 4.3, 6.3, 6.5, 6.6_

  - [ ] 8.2 实现 G7TabDisclosureSOE.vue（国企附注）
    - 355行×17列虚拟滚动（全平台最长附注）
    - 在上市基础上增加3个section(国有资本保值增值率+投资决策合规性+境外投资)
    - EventBus subscribe/publish同上市附注
    - 每section AI辅助 + 复核按钮
    - 分段懒加载(每段50行)+滚动节流(16ms)
    - _Requirements: 4.2, 4.3, 6.3, 6.5, 6.6_

  - [ ]* 8.3 单元测试: 附注EventBus联动+虚拟滚动
    - 验证subscribe接收后刷新数据
    - 验证publish发送正确payload
    - 验证mounted时主动拉取最新审定数
    - _Requirements: 4.3, 6.3_

- [ ] 9. 后端服务层
  - [ ] 9.1 实现 _g7_long_term_equity_main.py（render策略）
    - render_g7_long_term_equity_main函数
    - 返回componentType='g7-long-term-equity-main' + sheets配置
    - RENDERER_DISPATCH注册
    - _Requirements: 1.1, 1.3_

  - [ ] 9.2 实现 _g7_long_term_equity_main_service.py（业务逻辑）
    - G7LongTermEquityMainService类
    - get_trial_balance_data(project_id, year)：科目1511取数
    - save_adjudication(wp_id, data)：保存+公式验证
    - validate_formulas(data)：后端公式校验
    - EventBus publish `substantive:adjudicated`
    - _Requirements: 3.3, 6.2, 6.3_

  - [ ] 9.3 实现 _g7_long_term_equity_main_import_export.py（导入导出）
    - POST export-template?sheet={code}（G7-2 / G7-3）
    - POST export-data?sheet={code}（G7-2按5区段分sheet）
    - POST import-data?sheet={code}（multipart/form-data）
    - StreamingResponse中文文件名RFC5987编码
    - _Requirements: 6.4, 5.6_

  - [ ] 9.4 实现 _g7_long_term_equity_main_ai.py（AI生成）
    - POST /api/workpapers/{wp_id}/g7-main/ai/{section}
    - section: adjudication-analysis / disclosure-text
    - _Requirements: 6.5_

  - [ ]* 9.5 后端PBT: 公式验证(hypothesis)
    - 文件: `backend/tests/test_g7_long_term_equity_main_pbt.py`
    - 9个property对应前端公式引擎后端校验
    - hypothesis max_examples=5
    - _Requirements: 6.2_

  - [ ]* 9.6 后端集成测试: API端点
    - 测试render-config返回正确componentType
    - 测试导入导出3端点×2表=6场景
    - 测试AI 2 section端点
    - _Requirements: 1.1, 6.4, 6.5_

- [ ] 10. Final checkpoint - 全量测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (9个property覆盖8纯函数+Tab行同步)
- 公式引擎优先开发（无UI依赖，PBT可立即验证）
- 前端7子组件按复杂度分批（审定表→明细表→调整分录→附注）
- 后端4py文件独立，可与前端并行开发
- 虚拟滚动4个表(97/103/253/355行)统一使用相同滚动方案
- G7-2宽表5区段Tab行同步是本组件最关键的交互特性

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.10"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9", "2.2", "2.3", "2.4"] },
    { "id": 2, "tasks": ["2.1", "9.1"] },
    { "id": 3, "tasks": ["4.1", "6.2", "6.3", "9.2"] },
    { "id": 4, "tasks": ["4.2", "5.1", "6.1", "9.3", "9.4"] },
    { "id": 5, "tasks": ["5.2", "5.3", "6.4", "8.1", "9.5"] },
    { "id": 6, "tasks": ["8.2", "8.3", "9.6"] }
  ]
}
```
