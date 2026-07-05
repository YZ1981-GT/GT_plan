# Implementation Plan: G4 债权投资底稿(main组)专属HTML精美组件

## Overview

G4债权投资(main组)专属组件 `g4-bond-investment-main`，覆盖8个sheet（G4A/G4-1/G4-2/G4-3/G4-4/附注披露(上市)/附注披露(国企)/底稿目录）。采用sheetName v-if dispatch模式 + defineAsyncComponent懒加载 + 公式引擎composable + 六大集成联动。按D~N底稿开发标准8步组织为10波次。

## Tasks

- [x] 1. 注册四件套 + render schema/yaml
  - [x] 1.1 后端注册：VALID_COMPONENT_TYPES添加'g4-bond-investment-main' + RENDERER_DISPATCH注册render_g4_bond_investment_main策略函数
    - 创建 `backend/app/routers/wp_render_strategies/_g4_bond_investment_main.py`
    - 在 `VALID_COMPONENT_TYPES` 列表中添加 `'g4-bond-investment-main'`
    - 在 `RENDERER_DISPATCH` 中注册 `'g4-bond-investment-main': render_g4_bond_investment_main`
    - render函数返回8个sheet的配置（componentType/sheetName/columns/rows）
    - _Requirements: 1.1, 1.3, 1.5_

  - [x] 1.2 前端注册：htmlRendererRegistry添加'g4-bond-investment-main'映射 + 创建主入口骨架GtG4BondInvestmentMain.vue
    - 在 `htmlRendererRegistry` 中添加 `'g4-bond-investment-main': () => import('./workpaper/GtG4BondInvestmentMain.vue')`
    - 创建 `GtG4BondInvestmentMain.vue` 骨架（接收props，v-if分发占位，defineAsyncComponent导入）
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 1.3 wp_code_overrides.json添加8条映射（G4A/G4-1/G4-2/G4-3/G4-4/附注披露(上市)/附注披露(国企)/底稿目录→g4-bond-investment-main）
    - 确保8个wp_code条目全部映射到 `g4-bond-investment-main`
    - _Requirements: 1.4_

  - [x] 1.4 创建render schema YAML配置文件
    - 在 `backend/data/` 对应目录创建G4 main组的render schema yaml
    - 配置8个sheet的列定义、行定义、公式标记
    - _Requirements: 1.1, 1.4_

- [x] 2. 公式引擎composable + PBT测试
  - [x] 2.1 实现useG4MainFormulaEngine.ts（14个纯函数 + parseNum）
    - 创建 `audit-platform/frontend/src/composables/useG4MainFormulaEngine.ts`
    - 实现 parseNum（null/undefined/NaN/空串→0）
    - 实现 calcDebitBalance / calcAdjustedAmount / calcBalanceSubtotal / calcAmortizedCost
    - 实现 calcEffectiveInterest / calcCashInflow / calcEndingBalance / calcInitialCarryingAmount
    - 实现 isDebitCreditBalanced / calcPeriodEndComponent / calcChangeRate
    - 实现 calcOneYearMaturity / calcBookValue
    - 所有函数无副作用、无Vue响应式依赖、输入通过parseNum清洗
    - _Requirements: 8.1~8.15_

  - [x] 2.2 PBT: Property 1 — 借方余额公式
    - **Property 1: calcDebitBalance(opening, debit, credit) === opening + debit - credit**
    - **Validates: Requirements 3.3, 8.1**
    - 使用 `fc.float({min: 0, max: 1e9, noNaN: true})` 生成opening/debit/credit
    - numRuns ≥ 100

  - [x] 2.3 PBT: Property 2 — 审定数公式
    - **Property 2: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje**
    - **Validates: Requirements 3.4, 8.2**

  - [x] 2.4 PBT: Property 3 — 余额小计公式（三要素加法）
    - **Property 3: calcBalanceSubtotal(cost, interestAdj, accruedInterest) === cost + interestAdj + accruedInterest**
    - **Validates: Requirements 5.2, 5.4, 5.8, 8.4**

  - [x] 2.5 PBT: Property 4 — 摊余成本公式
    - **Property 4: calcAmortizedCost(subtotal, impairment) === subtotal - impairment**
    - **Validates: Requirements 3.5, 5.3, 5.9, 7.3, 8.3**

  - [x] 2.6 PBT: Property 5 — 实际利息收入公式
    - **Property 5: calcEffectiveInterest整年 === amortizedCost × rate；按天数 === amortizedCost × rate × days / 365**
    - **Validates: Requirements 7.4, 7.5, 8.5**
    - 使用 `fc.integer({min: 1, max: 366})` 生成days

  - [x] 2.7 PBT: Property 6 — 现金流入公式
    - **Property 6: calcCashInflow(faceValue, couponRate) === faceValue × couponRate [× days/365]**
    - **Validates: Requirements 7.6, 8.6**

  - [x] 2.8 PBT: Property 7 — 期末账面余额公式
    - **Property 7: calcEndingBalance === opening + interest - cashInflow - principalRepaid**
    - **Validates: Requirements 7.7, 8.7**

  - [x] 2.9 PBT: Property 8 — 初始入账价值公式
    - **Property 8: calcInitialCarryingAmount(price, fees) === price + fees**
    - **Validates: Requirements 7.2, 8.8**

  - [x] 2.10 PBT: Property 9 — 借贷平衡恒等
    - **Property 9: isDebitCreditBalanced ↔ |SUM(debits)-SUM(credits)| < 0.01**
    - **Validates: Requirements 6.2, 8.12**
    - 使用 `fc.array(fc.float(...))` 生成debits/credits数组

  - [x] 2.11 PBT: Property 10 — 期末分项一致性（加法交换律）
    - **Property 10: calcPeriodEndComponent(opening, change) === opening + change 且满足交换律**
    - **Validates: Requirements 5.5, 5.6, 5.7, 8.13**

  - [x] 2.12 PBT: Property 11 — 变动率方向性
    - **Property 11: current>prior>0→正; current<prior,prior>0→负; prior=0→null**
    - **Validates: Requirements 3.10, 8.9**

  - [x] 2.13 PBT: Property 12 — 一年内到期小计公式
    - **Property 12: calcOneYearMaturity(balance, impairment) === balance - impairment**
    - **Validates: Requirements 5.10, 8.10**

  - [x] 2.14 PBT: Property 13 — 账面价值公式
    - **Property 13: calcBookValue(amortized, oneYear) === amortized - oneYear**
    - **Validates: Requirements 5.11, 8.11**

  - [x] 2.15 单元测试：parseNum边界 + 除零保护 + 浮点精度
    - 测试 parseNum(null/undefined/NaN/''/非数字字符串) 均返回0
    - 测试 calcChangeRate(0, x) 返回null不抛异常
    - 测试金额保留2位小数（四舍五入）、利率至少4位小数
    - _Requirements: 8.14, 8.15_

- [x] 3. 主入口 GtG4BondInvestmentMain.vue（sheetName v-if dispatch + selfLoad + defineAsyncComponent）
  - [x] 3.1 实现sheetName正则提取 + v-if分发逻辑（8 sheets→对应子组件 + 未匹配→OnlyOffice fallback）
    - 正则从sheetName提取编码：G4A/G4-1/G4-2/G4-3/G4-4/附注披露(上市)/附注披露(国企)/底稿目录
    - SHEET_CODE_MAP映射到子组件标识
    - defineAsyncComponent懒加载所有8个子组件
    - 未匹配sheetName渲染OnlyOffice fallback
    - _Requirements: 1.1, 1.2, 1.7, 1.8_

  - [x] 3.2 实现selfLoad模式（htmlData为null时调用render-config获取数据）
    - 当 `htmlData` prop为null时，自动调用 `render-config?force_component_type=g4-bond-investment-main`
    - 加载失败时显示错误卡片+重试按钮
    - _Requirements: 1.6_

  - [x] 3.3 集成useVersionTrail（autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer）
    - 主入口调用 `useVersionTrail(wpId)`
    - 保存时触发 `autoSnapshot()`
    - 工具栏添加"版本历史"按钮打开drawer
    - _Requirements: 9.1_

  - [x] 3.4 provide openReviewDialog给所有子组件（复核对话集成）
    - 使用 `useReviewDialog(wpId)` 获取 `openReviewDialog`
    - `provide('openReviewDialog', openReviewDialog)` 供子组件inject
    - _Requirements: 9.5_

  - [x] 3.5 实现双模式切换（HTML↔OnlyOffice）+ localStorage持久化
    - 创建 `useG4MainDualMode.ts` composable
    - 模式状态保存到localStorage（key含wpId）
    - 切换按钮在工具栏展示
    - _Requirements: 10.6_

  - [x] 3.6 创建子目录结构（core/ + measurement/）+ 子组件占位文件
    - 创建 `g4-bond-investment-main/core/` 目录：G4TabProcedure/G4TabAdjudication/G4TabDetail/G4TabAdjustment/G4TabDisclosureListed/G4TabDisclosureSOE/G4TabDirectory
    - 创建 `g4-bond-investment-main/measurement/` 目录：G4TabInterestCalc
    - 每个文件创建基础骨架（props接收、inject openReviewDialog）
    - _Requirements: 1.9_

- [x] 4. Checkpoint - 确认注册+公式+主入口基础联通
  - 确保所有测试通过，ask the user if questions arise.

- [x] 5. 核心子组件 Wave1: G4-1审定表 + G4-3调整分录
  - [x] 5.1 实现useG4MainAdjudication.ts composable（三层数据结构 + TB取数 + 公式计算）
    - 三大分组：原值/减值/摊余成本 + 附加一年内到期
    - 试算表取数（科目1501 trial_balance）
    - 审定数公式：审定 = 未审 + AJE + RJE
    - 借方余额公式：期末未审 = 期初审定 + 借方 - 贷方
    - 摊余成本 = 原值小计 - 减值小计
    - 分组小计自动汇总
    - 差异 = 审定 - 试算表数
    - 变动率 = (期末审定 - 期初审定) / 期初审定
    - _Requirements: 3.1~3.13_

  - [x] 5.2 实现G4TabAdjudication.vue（三层结构表格 + 展开/折叠 + EventBus发布）
    - 46行×11列三层结构表格
    - 列：项目|期初(未审/AJE/RJE/审定)|期末(未审/AJE/RJE/审定)|变动额|变动率|原因分析
    - 差异≠0红色高亮；|变动率|>20%橙色高亮+原因分析必填
    - 审定数变更时EventBus发布 `substantive:adjudicated`(accountCode='1501')
    - GtIndexChip索引列跳转；展开/折叠分组（默认展开）
    - 公式列虚线下划线+cursor:help+tooltip
    - section标题栏右侧复核按钮（inject openReviewDialog）
    - _Requirements: 3.1~3.13, 9.4, 11.1~11.4_

  - [x] 5.3 实现useG4MainAdjustment.ts composable（借贷校验 + AJE/RJE汇总回写G4-1）
    - 22行×10列数据管理
    - isDebitCreditBalanced实时校验
    - 保存时汇总AJE/RJE金额回写G4-1审定表
    - 动态行增删（ElMessageBox.prompt输入摘要）
    - _Requirements: 6.1~6.5_

  - [x] 5.4 实现G4TabAdjustment.vue（调整分录表格 + 借贷不平衡红色高亮 + 回写联动）
    - 列：序号|分录类型(AJE/RJE)|日期|摘要|科目代码|科目名称|借方金额|贷方金额|编制人|备注
    - 借贷不平衡时红色高亮显示差额
    - 动态行增删 + ElMessageBox.prompt输入摘要确认
    - 保存时自动汇总回写G4-1
    - section标题栏右侧复核按钮
    - _Requirements: 6.1~6.5, 11.1, 11.5_

  - [x] 5.5 单元测试：G4-1审定表公式链 + G4-3借贷平衡校验
    - 测试三层结构小计汇总正确性
    - 测试借方余额公式链完整性
    - 测试G4-3借贷平衡→回写G4-1流程
    - _Requirements: 3.3~3.6, 6.2, 6.5_

- [x] 6. 核心子组件 Wave2: G4-2明细表 + G4-4利息测算
  - [x] 6.1 实现useG4MainDetail.ts composable（5区段列定义 + 行同步 + 公式链 + 分类逻辑）
    - 44列分5区段Tab：基础信息(6)/期初余额(10)/本期变动(4)/期末余额+减值(10)/摊余成本+审定(8)
    - 公式链：期初小计/期初摊余成本/本期变动小计/期末各项/期末小计/摊余成本/一年内到期小计/账面价值
    - 按到期日与资产负债表日比较进行数据分类（一年内到期 vs 超过一年）
    - 底部合计行（按投资种类分类小计 + 总计）
    - 动态行增删（max 500行，ElMessageBox.prompt输入投资项目名称）
    - 空值/非数字输入视为0参与计算
    - _Requirements: 5.1~5.17_

  - [x] 6.2 实现G4TabDetail.vue（5区段Tab切换 + el-table动态列 + 行选中同步 + 虚拟滚动）
    - Tab切换不销毁el-table实例，仅切换列定义(columns computed)
    - 行数据共享同一reactive数组，5区段引用同一rows
    - selectedRowIndex跨Tab同步（切换前后行索引不变）
    - 行数>50启用虚拟滚动
    - 公式列tooltip显示公式来源
    - 新增行时空白名称阻止创建
    - _Requirements: 5.1, 5.12~5.17, 11.2, 11.5, 11.8_

  - [x] 6.3 实现useG4MainInterestCalc.ts composable（分组管理 + 实际利率法公式 + Stage条件）
    - InterestCalcGroup分组管理（每投资项目独立成组）
    - (一)初始入账价值：initialCarryingAmount = purchasePrice + transactionCost
    - (二)利息计算多行：amortizedCost/effectiveInterest/cashInflow/closingBalance
    - Stage1/2/3条件：公式相同但Stage3减值更大→摊余成本基数更低
    - 各项目实际利息收入合计 vs G4-1审定利息收入比对
    - 差异>0.01元红色高亮
    - _Requirements: 7.1~7.11_

  - [x] 6.4 实现G4TabInterestCalc.vue（双section分组表格 + 动态行 + 审计结论 + 编制提示）
    - 每个投资项目独立成组，组间分隔线+标题
    - (一)确定初始入账价值(9列) + (二)计算利息收入(10列，多行=多计息期间)
    - 减值阶段Stage下拉选择
    - 底部：合计对比行 + 审计结论textarea(AI按钮) + 编制提示details折叠
    - 新增投资项目ElMessageBox.prompt输入名称
    - section(二)支持动态行增删
    - _Requirements: 7.1~7.11, 11.1~11.5_

  - [x] 6.5 单元测试：G4-2五区段Tab行同步 + G4-4 Stage条件计算
    - 测试Tab切换行索引保持
    - 测试5区段公式链完整性（从期初到账面价值）
    - 测试Stage1/2/3利息计算基数差异
    - 测试利息测算合计vs G4-1差异比对
    - _Requirements: 5.2~5.11, 5.13, 7.3~7.7, 7.11_

- [x] 7. Checkpoint - 确认4个核心子组件功能完整
  - 确保所有测试通过，ask the user if questions arise.

- [x] 8. 附注披露 + 底稿目录
  - [x] 8.1 实现G4TabDisclosureListed.vue（上市公司附注130行 + 虚拟滚动 + EventBus订阅/发布）
    - 130行×11列结构化表格
    - 启用虚拟滚动（el-table-v2 或 vxe-table virtual）
    - 监听EventBus `substantive:adjudicated`(accountCode='1501')自动刷新审定数据
    - 发布 `disclosure:note-text-updated` 联动附注模块
    - 每个文本区section标题行右侧AI辅助按钮
    - section标题栏右侧复核按钮
    - _Requirements: 4.1, 4.3~4.6, 9.4, 11.1, 11.6_

  - [x] 8.2 实现G4TabDisclosureSOE.vue（国企附注71行 + 虚拟滚动 + EventBus订阅/发布）
    - 71行×7列结构化表格
    - 启用虚拟滚动（>50行阈值）
    - 同样监听/发布EventBus事件
    - AI辅助按钮 + 复核按钮
    - _Requirements: 4.2~4.6, 9.4, 11.1, 11.6_

  - [x] 8.3 实现G4TabDirectory.vue（底稿目录页）
    - 27行×8列目录页渲染
    - 静态展示为主，支持索引跳转
    - _Requirements: 1.8, 1.9_

  - [x] 8.4 实现G4TabProcedure.vue（G4A程序表：复用a-program-console + 抽凭引擎 + 截止自动提取）
    - 复用GtAProgramConsole组件渲染41行×10列程序步骤
    - selfLoad模式（bundle内嵌场景）
    - 集成GtVoucherSamplingEngine抽凭引擎（dialog模式，科目1501）
    - 集成useCutoffAutoSampling（序时账±5天截止测试）
    - 执行人/执行日期/结论/索引字段编辑
    - _Requirements: 2.1~2.4, 9.2, 9.3_

- [x] 9. 六大集成联动（版本链+抽凭+截止+附注EventBus+复核）
  - [x] 9.1 完善EventBus联动：G4-1发布substantive:adjudicated → 附注(上市/国企)订阅刷新 → 发布disclosure:note-text-updated
    - 确保payload格式正确：`{accountCode:'1501', adjudicatedAmount}`
    - 附注订阅后正确刷新审定数据
    - 附注文本更新后发布 `disclosure:note-text-updated`
    - _Requirements: 3.9, 4.3, 4.4, 9.4_

  - [x] 9.2 完善G4-3调整分录→G4-1审定表回写联动
    - 保存调整分录时汇总AJE/RJE金额
    - 自动更新G4-1对应行的AJE/RJE列
    - 触发审定数重算
    - _Requirements: 6.5_

  - [x] 9.3 完善G4-4利息测算→G4-1比对联动
    - 利息测算完成后将合计与G4-1利息收入审定数比对
    - 差异>0.01元红色高亮
    - _Requirements: 7.11_

  - [x] 9.4 集成测试：EventBus跨组件传递验证
    - 测试G4-1审定数变更→附注自动刷新
    - 测试G4-3回写→G4-1重算
    - 测试G4-4比对差异高亮
    - _Requirements: 3.9, 4.3, 6.5, 7.11, 9.4_

- [x] 10. 导入导出 + AI辅助
  - [x] 10.1 实现useG4MainImportExport.ts composable（3张表×3端点=9端点调用）
    - 导出模板/导出数据/导入数据 三端点
    - 支持G4-2/G4-3/G4-4三张动态行表格
    - G4-2按5区段分sheet导出
    - 使用axios（非原生fetch）确保Authorization header
    - StreamingResponse中文文件名RFC5987编码
    - _Requirements: 10.1~10.3_

  - [x] 10.2 后端实现_g4_bond_investment_main_import_export.py（导出模板/导出数据/导入数据 3端点）
    - POST /api/workpapers/{wp_id}/g4-main/export-template?sheet={code}
    - POST /api/workpapers/{wp_id}/g4-main/export-data?sheet={code}
    - POST /api/workpapers/{wp_id}/g4-main/import-data?sheet={code} (multipart/form-data)
    - G4-2分sheet导出（5区段→多sheet Excel）
    - 导入格式校验（行号/字段/原因详细错误列表）
    - _Requirements: 10.1~10.3_

  - [x] 10.3 后端实现_g4_bond_investment_main_ai.py（4 section AI生成端点）
    - POST /api/workpapers/{wp_id}/g4-main/ai/{section}
    - section: adjudication-analysis / interest-conclusion / disclosure-text / overall-opinion
    - 每个section返回AI生成的审计文本
    - _Requirements: 10.4, 10.5_

  - [x] 10.4 前端集成导入导出UI（el-dropdown"导入导出▾"）+ AI按钮联动
    - G4-2/G4-3/G4-4各表添加el-dropdown"导入导出▾"(导出模板/导出数据/导入数据)
    - 各文本区section标题行右侧AI辅助按钮
    - AI按钮调用对应section端点，流式填入textarea
    - _Requirements: 10.1~10.5, 11.1_

- [x] 11. Checkpoint - 确认导入导出和AI功能完整
  - 确保所有测试通过，ask the user if questions arise.

- [x] 12. UI精调 + 双模式OO切换
  - [x] 12.1 公式列UI规范：虚线下划线 + cursor:help + tooltip显示公式来源
    - 所有公式列统一样式：border-bottom dashed + cursor:help
    - tooltip内容示例："摊余成本 = 小计 - 减值"、"期末未审 = 期初审定 + 借方 - 贷方"
    - _Requirements: 11.2_

  - [x] 12.2 变动率高亮：|变动率|>20%橙色高亮 + 原因分析必填提示
    - G4-1变动率列条件格式化
    - 超阈值时原因分析列强制聚焦
    - _Requirements: 3.11, 11.2_

  - [x] 12.3 编制提示details折叠 + 审计说明/结论el-card包裹 + 字体/对齐规范
    - 各子组件底部添加<details>编制提示</details>
    - 审计结论textarea用el-card包裹
    - 表格字体13px统一
    - AI+复核按钮右对齐在section标题同行
    - 列宽min-width自适应
    - _Requirements: 11.1~11.5_

  - [x] 12.4 完善双模式OO切换逻辑 + localStorage持久化
    - HTML↔OnlyOffice切换无闪烁
    - 模式选择持久化到localStorage
    - 切换时正确传递sheetName给OnlyOffice
    - _Requirements: 10.6_

- [x] 13. 集成测试 + Playwright E2E + 文档收尾
  - [x] 13.1 前端集成测试：sheetName分发正确性（8 sheets + fallback）
    - 测试8个有效sheetName→正确子组件渲染
    - 测试未知sheetName→OnlyOffice fallback
    - 测试selfLoad模式（htmlData为null时自动加载）
    - _Requirements: 1.1~1.8_

  - [x] 13.2 前端集成测试：公式链端到端验证
    - 借方余额公式链完整性（期初+借方-贷方=期末未审→+AJE+RJE=审定）
    - G4-2五区段公式链（期初→本期变动→期末→摊余成本→账面价值）
    - G4-4实际利率法完整流程（初始入账→多期利息→期末余额）
    - _Requirements: 3.3~3.5, 5.2~5.11, 7.2~7.7_

  - [x] 13.3 后端集成测试：render策略 + 注册契约 + 导入导出round-trip
    - render_g4_bond_investment_main返回正确结构
    - VALID_COMPONENT_TYPES/RENDERER_DISPATCH/wp_code_overrides契约验证
    - 导入导出3张表round-trip（导出→修改→导入→验证数据一致）
    - _Requirements: 1.1~1.5, 10.1~10.3_

  - [x] 13.4 Playwright E2E测试：G4-1审定表完整流程
    - 打开底稿→sheetName分发到G4-1
    - TB取数→审定表数据正确显示
    - 修改AJE→审定数重算→变动率更新→EventBus发布验证
    - _Requirements: 3.1~3.12_

  - [x] 13.5 Playwright E2E测试：G4-2明细表5区段Tab操作
    - Tab切换无闪烁+行选中状态保持
    - 新增行→弹窗输入名称→行创建
    - 公式列tooltip显示+按到期日分类正确
    - _Requirements: 5.1, 5.12~5.17, 11.8_

  - [x] 13.6 Playwright E2E测试：G4-4利息测算+导入导出
    - 新增投资项目→填入初始入账数据→计息期间动态行增删
    - Stage下拉选择→利息收入计算→与G4-1比对差异
    - 导出数据→修改→导入→验证数据完整
    - _Requirements: 7.1~7.11, 10.1~10.3_

- [x] 14. Final checkpoint - 确保所有测试通过
  - 确保所有测试通过，ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 每个task引用具体requirements确保可追溯
- PBT测试覆盖所有13个Correctness Properties（P1~P13）
- 六大集成中行级OCR明确不集成（G4-2非凭证表）
- G4A程序表复用a-program-console componentType，不重新开发
- 宽表策略：G4-2(44列→5区段Tab) / G4-4(双section分组)
- 虚拟滚动阈值：>50行启用（附注上市130行/国企71行/G4-2动态≤500行）
- 导入导出仅对动态行表格（G4-2/G4-3/G4-4），静态表格不需要

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9", "2.10", "2.11", "2.12", "2.13", "2.14", "2.15"] },
    { "id": 3, "tasks": ["3.1", "3.2", "3.3", "3.4", "3.5", "3.6"] },
    { "id": 4, "tasks": ["5.1", "5.3"] },
    { "id": 5, "tasks": ["5.2", "5.4", "5.5", "6.1", "6.3"] },
    { "id": 6, "tasks": ["6.2", "6.4", "6.5"] },
    { "id": 7, "tasks": ["8.1", "8.2", "8.3", "8.4"] },
    { "id": 8, "tasks": ["9.1", "9.2", "9.3", "9.4", "10.1", "10.2", "10.3"] },
    { "id": 9, "tasks": ["10.4", "12.1", "12.2", "12.3", "12.4"] },
    { "id": 10, "tasks": ["13.1", "13.2", "13.3", "13.4", "13.5", "13.6"] }
  ]
}
```
