# Implementation Plan: G10 交易性金融负债底稿专属HTML精美组件

## Overview

基于design.md架构，将G10交易性金融负债底稿实现为独立专属组件`g10-trading-financial-liabilities`。覆盖12个有效sheet，采用sheetName v-if dispatch模式 + defineAsyncComponent懒加载。核心特色：贷方科目公式、衍生工具78行问卷、分类适当性检查、L3调节表（负债方向）、4处虚拟滚动。前端TypeScript/Vue3，后端Python/FastAPI。

## Tasks

- [x] 1. 注册四件套 + 主入口sheetName分发
  - [x] 1.1 创建主入口 GtG10TradingFinancialLiabilities.vue，实现sheetName prop接收、正则提取编码、v-if分发12子组件(defineAsyncComponent lazy)、selfLoad逻辑、OnlyOffice fallback、provide openReviewDialog、useVersionTrail autoSnapshot
    - 12个sheetName映射：G10A/G10-1~G10-8/附注披露(上市)/附注披露(国企)/底稿目录
    - props: htmlData/sheetName/wpId/projectId/readonly
    - _Requirements: 1.1, 1.2, 1.4, 10.2, 10.6_

  - [x] 1.2 注册htmlRendererRegistry条目 + wp_code_overrides.json(12条override) + VALID_COMPONENT_TYPES + RENDERER_DISPATCH
    - htmlRendererRegistry: `'g10-trading-financial-liabilities': () => import(...)`
    - wp_code_overrides.json 12条：G10A~/G10-1~/G10-2~/G10-3~/G10-4~/G10-5~/G10-6~/G10-7~/G10-8~/附注上市/附注国企/底稿目录
    - 后端VALID_COMPONENT_TYPES添加 + RENDERER_DISPATCH注册
    - _Requirements: 1.3_

- [x] 2. 公式引擎 useG10FormulaEngine
  - [x] 2.1 创建 useG10FormulaEngine.ts，实现6个纯函数 + parseNum
    - parseNum: null/undefined/NaN/空→0
    - calcCreditBalance(opening, credit, debit) = opening + credit - debit（贷方公式）
    - calcAdjustedAmount(unadjusted, adjustment) = unadjusted + adjustment
    - calcChangeRate(prior, current): prior=0→null, else (current-prior)/prior
    - isDebitCreditBalanced(debits[], credits[]): |SUM差|<0.01
    - calcL3Reconciliation(opening,new,terminated,transferIn,transferOut,fvChange,interest,other)
    - _Requirements: 10.1, 3.3, 3.4, 7.3_

  - [x]* 2.2 PBT: Property 1 — 贷方余额公式
    - **Property 1: calcCreditBalance(opening, credit, debit) === opening + credit - debit**
    - fast-check fc.float({noNaN:true}) 三参数任意组合
    - **Validates: Requirements 3.3, 10.1**

  - [x]* 2.3 PBT: Property 2 — 审定数公式
  - [x]* 2.4 PBT: Property 3 — L3调节表恒等
  - [x]* 2.5 PBT: Property 4 — 变动率方向性与除零保护
  - [x]* 2.6 PBT: Property 5 — 借贷平衡恒等
  - [x]* 2.7 PBT: Property 6 — parseNum健壮性

- [x] 3. G10-1 审定表（63行分组+虚拟滚动+贷方公式+TB取数）
  - [x] 3.1 创建 G10TabAdjudication.vue，实现63行×12列审定表
    - 分组结构：(一)初始金额/(二)公允价值变动/合计，折叠/展开
    - 列：项目|期初(未审|账项调整|审定)|期末(未审|账项调整|审定)|变动额|变动率|原因分析|索引
    - 贷方公式列：closingUnadjusted ≈ calcCreditBalance(openingAdjusted, credit, debit)
    - 审定数列：calcAdjustedAmount(unadjusted, adjustment)
    - 变动率列：calcChangeRate + |>20%|橙色高亮+原因必填
    - trial_balance取数(2201) + 差异红色高亮
    - 63行虚拟滚动
    - EventBus publish `substantive:adjudicated`(accountCode='2201')
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 10.5_

  - [x]* 3.2 单元测试：G10-1审定表贷方方向 + 分组折叠 + 变动率高亮
    - 验证calcCreditBalance方向与借方相反
    - 验证|变动率|>20%触发橙色高亮+必填
    - 验证分组折叠/展开状态
    - _Requirements: 3.3, 3.7, 3.8_

- [x] 4. G10-2 明细表（24列→2区段Tab）
  - [x] 4.1 创建 G10TabDetail.vue，实现39行×24列2区段Tab
    - Tab1基础信息(12列): 负债名称|类型(下拉)|对手方|合同日|到期日|初始金额|期初余额|期初审定|本期增加|本期减少|期末余额|审定数(公式)
    - Tab2公允价值+分类(12列): 负债名称|FV层次|估值方法|期初FV|期末FV|FV变动|损益|是否衍生|主合同|嵌入衍生|发函|备注
    - 行同步：Tab切换保持行索引
    - 动态行增删(ElMessageBox.prompt输入负债名称)
    - 底部合计行
    - _Requirements: 5.1, 5.2_

  - [x]* 4.2 单元测试：G10-2区段Tab行同步 + 动态行 + 合计
    - _Requirements: 5.1, 5.2_

- [x] 5. Checkpoint — 核心表完成
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. G10-3 调整分录 + G10-4 分类检查
  - [x] 6.1 创建 G10TabAdjustment.vue，实现23行×10列 AJE/RJE
    - 列：序号|类型(AJE/RJE)|日期|摘要|科目代码|科目名称|借方|贷方|编制人|备注
    - 借贷平衡校验(isDebitCreditBalanced) + 差额≠0红色
    - 动态行增删 + 回写审定表
    - _Requirements: 6.1, 6.4_

  - [x] 6.2 创建 G10TabClassificationCheck.vue，实现28行×9列问卷式
    - 顶部方法论上下文(琥珀色左边线+浅黄背景：CAS22/37分类条件)
    - 多section(检查区域)：每section标题行右侧AI按钮+复核按钮
    - 列：序号|检查项目|审计要求|管理层回复(textarea)|是否合规(下拉)|结论(textarea)|索引
    - 底部综合审计结论textarea(AI: classification-conclusion)
    - <details>编制提示</details>折叠
    - _Requirements: 6.2, 6.3, 10.4_

  - [x]* 6.3 单元测试：G10-3借贷平衡 + G10-4问卷下拉联动
    - _Requirements: 6.1, 6.2_

- [x] 7. G10-5 公允价值测试 + G10-6 L3调节表
  - [x] 7.1 创建 G10TabFairValueTest.vue，实现39行×18列2区段Tab
    - 方法论上下文(Level1/2/3定义)
    - Tab1基础+审定(9列): 名称|初始日期|未审(数量/单价/FV)|审定(数量/单价/FV)|层次(下拉)
    - Tab2估值详情(9列): 估值方法(下拉)|与上期一致|来源机构|输入值来源(textarea)|估值技术|不可观察输入值描述(textarea)|数值|敏感性分析(textarea)|索引
    - Level3必填校验：层次=Level3时Tab2(估值技术+不可观察输入值)必填
    - 动态行增删 + AI辅助(fair-value-conclusion)
    - _Requirements: 7.1, 7.4_

  - [x] 7.2 创建 G10TabL3Reconciliation.vue，实现23行×13列L3调节表
    - 列：负债名称|期初|本期新增|本期终止|转入L3|转出L3|FV变动|利息费用|其他|期末(公式)|差异(公式)|备注
    - 期末=calcL3Reconciliation(...)
    - 差异=actualClosing - calcL3Reconciliation(...)
    - 负债方向术语：新增(新发行/新确认) / 终止(到期/提前清偿)
    - 动态行增删
    - _Requirements: 7.2, 7.3, 7.4_

  - [x]* 7.3 单元测试：Level3必填校验 + L3调节差异计算
    - _Requirements: 7.1, 7.3_

- [x] 8. G10-7 凭证检查（99行3区段Tab+OCR+虚拟滚动）
  - [x] 8.1 创建 G10TabVoucherCheck.vue，实现99行×17列3区段Tab
    - Tab1凭证基础(6列): 日期|凭证编号|业务内容|对方科目|借方|贷方
    - Tab2核对内容(6列): 📎附件(OCR触发)|文件描述|✓完整|✓授权|✓账务正确|✓公允价值正确
    - Tab3结论(5列): 索引号(GtIndexChip)|是否异常|异常说明(textarea)|风险等级(下拉)|备注
    - 行同步：3Tab切换保持行索引
    - 任一check✗→isAbnormal自动置true
    - 抽凭引擎GtVoucherSamplingEngine + 行级OCR(/d4/contract-ocr)
    - 虚拟滚动(99行) + 借贷差额汇总(≠0红色)
    - 动态行增删 + GtIndexChip
    - _Requirements: 8.1, 8.2, 8.3, 10.5_

  - [x]* 8.2 单元测试：异常自动检测 + Tab行同步 + 借贷平衡
    - 验证check1-4任一false→isAbnormal=true
    - _Requirements: 8.1, 8.2_

- [x] 9. G10-8 衍生金融工具核查（78行5section问卷+虚拟滚动）
  - [x] 9.1 创建 G10TabDerivativeCheck.vue，实现78行×10列5section问卷
    - 顶部方法论上下文(琥珀色左边线：衍生工具五要素CAS22)
    - 5个section:
      - (一)衍生金融工具基本信息
      - (二)嵌入衍生工具判断
      - (三)公允价值计量
      - (四)套期关系检查
      - (五)披露完整性
    - 列：序号|检查区域|检查项目|审计要求(方法论)|检查结果(textarea)|是否合规(下拉)|风险等级(下拉)|审计结论(textarea)|索引|备注
    - 每section标题行右侧AI按钮+复核按钮
    - 78行虚拟滚动
    - 底部综合审计结论textarea(AI: derivative-conclusion) + <details>编制提示</details>
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 10.5_

  - [x]* 9.2 单元测试：G10-8虚拟滚动 + section折叠 + 问卷下拉
    - _Requirements: 9.1, 9.3_

- [x] 10. Checkpoint — 全部sheet组件完成
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. 附注披露 + G10A程序表 + 底稿目录 + EventBus联动
  - [x] 11.1 创建 G10TabDisclosureListed.vue(上市42行) + G10TabDisclosureSOE.vue(国企79行虚拟滚动)
    - EventBus subscribe `substantive:adjudicated`(2201) → 刷新数据
    - EventBus publish `disclosure:note-text-updated`(2201)
    - AI辅助文本区
    - _Requirements: 4.1, 4.2, 4.3, 10.5_

  - [x] 11.2 创建 G10TabProcedure.vue(G10A程序表) + G10TabDirectory.vue(底稿目录)
    - G10A: 复用a-program-console + selfLoad + 抽凭引擎(GtVoucherSamplingEngine) + 截止自动提取(useCutoffAutoSampling, accountCode='2201', days=5)
    - 底稿目录: 25行×8列静态渲染
    - _Requirements: 2.1, 10.2_

- [x] 12. 六大集成 + 导入导出5张表 + 双模式
  - [x] 12.1 实现 useG10ImportExport.ts 导入导出composable(5张表)
    - 支持表: G10-2/G10-3/G10-5/G10-6/G10-7
    - el-dropdown"导入导出▾"(导出模板/导出数据/导入数据)
    - 宽表按区段分sheet导出: G10-2(2sheet)/G10-5(2sheet)/G10-7(3sheet)/G10-3(1sheet)/G10-6(1sheet)
    - 使用http(axios)不用原生fetch
    - _Requirements: 10.3_

  - [x] 12.2 实现 useG10DualMode.ts 双模式切换 + useG10FormData.ts 数据加载/保存
    - 双模式(HTML ↔ OnlyOffice) + localStorage持久化
    - useG10FormData: selfLoad/save/writebackTB
    - _Requirements: 10.6, 1.4_

  - [x] 12.3 集成验证：版本链+抽凭+截止+附注EventBus+OCR+复核 全链路连通
    - 版本链: autoSnapshot on save
    - 抽凭: G10A+G10-7 GtVoucherSamplingEngine
    - 截止: G10A useCutoffAutoSampling
    - 附注EventBus: publish+subscribe双向
    - OCR: G10-7 📎列 /d4/contract-ocr
    - 复核: provide/inject openReviewDialog
    - _Requirements: 10.2_

- [x] 13. AI辅助5 section
  - [x] 13.1 实现AI辅助调用逻辑(5 section)
    - adjudication-analysis: G10-1审定分析
    - classification-conclusion: G10-4分类结论
    - fair-value-conclusion: G10-5公允价值结论
    - derivative-conclusion: G10-8衍生工具结论
    - voucher-conclusion: G10-7凭证结论
    - POST /api/workpapers/{wp_id}/g10/ai/{section}
    - 每个section标题行右侧AI按钮触发
    - _Requirements: 10.4_

- [x] 14. 后端4py文件
  - [x] 14.1 创建 _g10_trading_financial_liabilities.py (render策略+RENDERER_DISPATCH)
    - render_g10_trading_financial_liabilities函数
    - 返回componentType='g10-trading-financial-liabilities' + sheets配置
    - _Requirements: 1.3_

  - [x] 14.2 创建 _g10_trading_financial_liabilities_service.py (业务逻辑)
    - G10TradingFinancialLiabilitiesService类
    - get_trial_balance_data(project_id, year): SELECT 2201%
    - save_adjudication(wp_id, data): 保存+公式校验
    - validate_formulas(data): 后端公式验证
    - _Requirements: 3.5, 10.1_

  - [x] 14.3 创建 _g10_trading_financial_liabilities_import_export.py (导入导出15端点)
    - POST /api/workpapers/{wp_id}/g10/export-template?sheet={code}
    - POST /api/workpapers/{wp_id}/g10/export-data?sheet={code}
    - POST /api/workpapers/{wp_id}/g10/import-data?sheet={code} (multipart/form-data)
    - 5张表×3=15端点, StreamingResponse中文文件名RFC5987编码
    - _Requirements: 10.3_

  - [x] 14.4 创建 _g10_trading_financial_liabilities_ai.py (AI生成5section)
    - POST /api/workpapers/{wp_id}/g10/ai/{section}
    - 5 section: adjudication-analysis/classification-conclusion/fair-value-conclusion/derivative-conclusion/voucher-conclusion
    - _Requirements: 10.4_

- [x] 15. Checkpoint — 全栈完成
  - Ensure all tests pass, ask the user if questions arise.

- [x] 16. PBT(后端) + 集成测试 + E2E
  - [x]* 16.1 后端PBT: 6属性 hypothesis验证
    - Property 1-6 后端Python验证
    - test_g10_trading_financial_liabilities_pbt.py
    - max_examples=5
    - **Validates: Requirements 10.1**

  - [x]* 16.2 集成测试: API端点(render+导入导出+AI)
    - render-config端点返回正确componentType
    - 导入导出15端点基本流程
    - AI 5 section端点响应
    - _Requirements: 1.3, 10.3, 10.4_

  - [x]* 16.3 E2E Playwright: 关键用户路径
    - 审定表完整流程(贷方方向): TB取数→公式→调整→EventBus→附注刷新
    - 分类适当性检查: 问卷填写→AI结论
    - 衍生工具核查: 78行虚拟滚动→5section问卷
    - 公允价值测试: Level3必填校验→L3调节表联动
    - 凭证检查: 抽凭→OCR→异常检测
    - _Requirements: 3.1~3.8, 6.2, 9.1~9.6, 7.1, 8.1_

- [x] 17. Final checkpoint — 全部测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 前端使用TypeScript/Vue3，后端使用Python/FastAPI
- 贷方公式是G10核心差异点（与G8借方方向相反）
- 虚拟滚动4处：G10-1(63行)/G10-7(99行)/G10-8(78行)/附注国企(79行)
- 宽表区段Tab：G10-2(2Tab)/G10-5(2Tab)/G10-7(3Tab)
- G10比标准G多2个sheet：G10-4分类检查 + G10-8衍生工具核查
- EventBus双事件：substantive:adjudicated + disclosure:note-text-updated
- 导入导出5张表(G10-2/G10-3/G10-5/G10-6/G10-7)，宽表按区段分sheet导出
- AI 5 section（比G8多derivative-conclusion）
- Property tests validate universal correctness properties from design document
- Each task references specific requirements for traceability

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "2.1"] },
    { "id": 1, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "14.1", "14.2"] },
    { "id": 2, "tasks": ["3.1", "4.1", "14.3", "14.4"] },
    { "id": 3, "tasks": ["3.2", "4.2", "6.1", "6.2"] },
    { "id": 4, "tasks": ["6.3", "7.1", "7.2"] },
    { "id": 5, "tasks": ["7.3", "8.1", "9.1"] },
    { "id": 6, "tasks": ["8.2", "9.2", "11.1", "11.2"] },
    { "id": 7, "tasks": ["12.1", "12.2", "13.1"] },
    { "id": 8, "tasks": ["12.3"] },
    { "id": 9, "tasks": ["16.1", "16.2", "16.3"] }
  ]
}
```
