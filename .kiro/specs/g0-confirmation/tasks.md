# Implementation Plan: G0 投资循环函证

## Overview

实现G0投资循环函证。复用D0共享函证组件(7个直接映射) + 新建2个组件（confirmation-diff-securities + confirmation-alternative-g06）。源模板1个xlsx(878KB)/9有效sheet。科目覆盖：交易性金融资产/债权投资/长期股权投资/其他权益工具投资。核心公式：数量差异=回函-账面；处置损益=成交-成本-手续费；市值差异=回函市值-账面市值。Same pattern as F0。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1.1", "1.2"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9"] },
    { "id": "wave3", "tasks": ["3.1", "3.2"] },
    { "id": "wave4", "tasks": ["4.1", "4.2"] },
    { "id": "wave5", "tasks": ["5.1", "5.2"] },
    { "id": "wave6", "tasks": ["6.1", "6.2"] },
    { "id": "wave7", "tasks": ["7.1"] }
  ]
}
```

## Notes

- G0是函证循环，架构与F0完全一致：复用D0共享 + 新建循环特有组件
- G0与F0的差异：G0有证券投资/非证券投资两种差异核对模式（F0只有通用差异核对）
- G0-3(证券)是投资循环特有的证券差异核对（持仓数量/公允价值/市值三维度）
- G0-6替代程序(29列)是投资循环特有（4区块：持仓证明/股利收入/处置收益/公允价值佐证）
- G0-4(非证券)直接复用D0的confirmation-diff-reconcile，无需开发
- G0无截止自动提取（函证类底稿不适用截止测试）
- 宽表拆分策略：G0-6的29列→4区块各自拆为左右视觉分组（记账凭证5列|检查证据N列）
- G0-3(证券)17列不需拆分（≤17列可接受横向展示）

## Tasks

- [ ] 1. 组件注册与基础配置
  - [ ] 1.1 注册componentType和overrides映射
    - 在 `wp_code_overrides.json` 中添加G0→confirmation-hub, G0A→a-program-console, G0-1→confirmation-summary, G0-2→confirmation-entity-verify, G0-3→confirmation-followup, G0-3S→confirmation-diff-securities, G0-4→confirmation-diff-reconcile, G0-6→confirmation-alternative-g06, G0-7→confirmation-reliability, G0-8→confirmation-fraud-risk（10条）
    - 在 `VALID_COMPONENT_TYPES` 中注册 'confirmation-diff-securities' 和 'confirmation-alternative-g06'
    - 在 `htmlRendererRegistry.ts` 中注册两个新componentType→Vue组件映射
    - 创建 G0.yaml render schema（9 sheets配置）
    - 更新 account_package_registry.json 添加G0包（9 sheets按模板顺序）
    - _Requirements: 1.1~1.3, 4.1~4.5_

  - [ ]* 1.2 编写注册契约测试
    - htmlRendererRegistry.spec.ts 验证2个新componentType已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证10条G0映射
    - _Requirements: 4.3, 4.4_

- [ ] 2. 实现公式引擎 useG0FormulaEngine.ts
  - [ ] 2.1 创建 `g0-confirmation/composables/useG0FormulaEngine.ts`，实现全部6个纯函数
    - 实现 `calcQuantityDiff`（数量差异 = 回函持仓 - 账面持仓）
    - 实现 `calcFairValueDiff`（公允价值差异 = 回函公允值 - 账面公允值）
    - 实现 `calcMarketValueDiff`（市值差异 = 回函总市值 - 账面总市值）
    - 实现 `calcDisposalGain`（处置损益 = 成交金额 - 原始成本 - 手续费，手续费<0→0）
    - 实现 `calcDividendDiff`（股利差异 = 应收股利 - 实收金额 - 红利税）
    - 实现 `hasDifference`（有差异 = |数量差异|>0 OR |公允价值差异|>0.01）
    - _Requirements: 7.1~7.6_

  - [ ]* 2.2 编写 Property 1 PBT：数量差异公式
    - 生成器：`fc.integer({min:-1e6, max:1e6})` × confirmed/booked
    - 断言：calcQuantityDiff(confirmed, booked) === confirmed - booked
    - **Property 1: 数量差异=回函持仓-账面持仓**
    - **Validates: Requirements 2.5, 7.1**

  - [ ]* 2.3 编写 Property 2 PBT：公允价值差异公式
    - 生成器：`fc.float({min:-1e8, max:1e8})` × confirmedFV/bookedFV
    - 断言：calcFairValueDiff(confirmedFV, bookedFV) === confirmedFV - bookedFV
    - **Property 2: 公允价值差异=回函-账面**
    - **Validates: Requirements 2.6, 7.2**

  - [ ]* 2.4 编写 Property 3 PBT：市值差异公式
    - 生成器：`fc.float({min:0, max:1e9})` × confirmedMV/bookedMV
    - 断言：calcMarketValueDiff(confirmedMV, bookedMV) === confirmedMV - bookedMV
    - **Property 3: 市值差异=回函市值-账面市值**
    - **Validates: Requirements 2.7, 7.3**

  - [ ]* 2.5 编写 Property 4 PBT：处置损益公式
    - 生成器：`fc.float({min:0, max:1e8})` × proceeds/cost/fee
    - 断言：calcDisposalGain(proceeds, cost, fee) === proceeds - cost - fee
    - **Property 4: 处置损益=成交-成本-手续费**
    - **Validates: Requirements 3.13, 7.4**

  - [ ]* 2.6 编写 Property 5 PBT：股利差异恒等
    - 生成器：`fc.float({min:0, max:1e7})` × declared/received/tax
    - 断言：calcDividendDiff(declared, received, tax) === declared - received - tax
    - **Property 5: 股利差异=应收-实收-税**
    - **Validates: Requirements 7.5**

  - [ ]* 2.7 编写 Property 6 PBT：差异判定对称性
    - 生成器：`fc.float({min:-1e8, max:1e8})` × a/b
    - 断言：hasDifference(a, b) === hasDifference(b, a)
    - **Property 6: 差异判定对称**
    - **Validates: Requirements 7.6**

  - [ ]* 2.8 编写 Property 7 PBT：零差异恒等
    - 生成器：`fc.float({min:-1e8, max:1e8})` v
    - 断言：calcQuantityDiff(v, v) === 0 ∧ calcFairValueDiff(v, v) === 0 ∧ calcMarketValueDiff(v, v) === 0
    - **Property 7: 自身与自身差异=0**
    - **Validates: Requirements 7.1~7.3**

  - [ ]* 2.9 编写 Property 8 PBT：处置损益与手续费反比
    - 生成器：`fc.float({min:0, max:1e8})` proceeds/cost + `fc.float`排序fee1>fee2
    - 断言：calcDisposalGain(proceeds, cost, fee1) < calcDisposalGain(proceeds, cost, fee2)
    - **Property 8: 手续费越高→处置损益越低**
    - **Validates: Requirements 7.4**

- [ ] 3. 实现 composable 数据管理
  - [ ] 3.1 创建 `g0-confirmation/composables/useDiffSecuritiesData.ts`
    - Master-Detail结构（证券列表→选中证券→明细核对行）
    - 定义 SecuritiesDiffRow 类型（17列）
    - 实现CRUD + 差异公式自动计算 + 汇总统计
    - 实现差异高亮逻辑（|差异|>0→橙色）
    - 实现loadAll/persistAll/序列化/反序列化
    - _Requirements: 2.1~2.12, 5.1_

  - [ ] 3.2 创建 `g0-confirmation/composables/useAlternativeG06Data.ts`
    - Master-Detail结构（投资项目列表→选中项目→4区块检查表）
    - 定义4区块行类型（HoldingCheckRow/DividendEvidenceRow/DisposalEvidenceRow/FairValueEvidenceRow）
    - 实现4区块独立CRUD + 各区块合计行
    - 实现处置损益公式=成交金额-原始成本-手续费
    - 实现反向联动（从G0-1获取未回函项目列表）
    - 实现loadAll/persistAll/序列化/反序列化
    - _Requirements: 3.1~3.13, 5.2_

- [ ] 4. 实现 Vue 组件
  - [ ] 4.1 创建 `GtConfirmationDiffSecurities.vue`（G0-3证券差异核对）
    - 调用useDiffSecuritiesData
    - Master区（左侧证券列表 / el-select切换）
    - 差异汇总区（顶部卡片）
    - 明细核对区（17列el-table，差异行橙色高亮）
    - 差异原因下拉（估值时点/交易日结算日/计量方法/其他）
    - 底部汇总统计 + 审计结论textarea(AI) + 编制提示details
    - selfLoad + 动态行增删 + 导入导出
    - UI铁律：13px/公式列虚线/min-width/AI+复核按钮右对齐
    - _Requirements: 2.1~2.12_

  - [ ] 4.2 创建 `GtConfirmationAlternativeG06.vue`（G0-6替代程序）
    - 调用useAlternativeG06Data
    - Master区（左侧投资项目列表 / el-select切换）
    - 余额汇总区 + 抽样参数区
    - 4区块各自el-table（左右视觉分组：记账凭证5列|检查证据N列）
    - 区块③处置损益公式列（虚线+tooltip）
    - 区块④公允价值Level层级下拉(1/2/3)
    - 各区块底部合计行 + 索引号列
    - 反向联动G0-1未回函项目
    - 行级OCR上传（复用`/d4/contract-ocr`端点）
    - 底部审计说明+结论textarea(AI) + 编制提示details
    - selfLoad + 动态行增删 + 导入导出
    - _Requirements: 3.1~3.13_

- [ ] 5. 后端实现
  - [ ] 5.1 创建后端3个py文件
    - `_g0_confirmation.py`：2个render策略函数 + 注册RENDERER_DISPATCH
    - `_g0_confirmation_import_export.py`：3端点（export-template/export-data/import-data）
    - `_g0_confirmation_ai.py`：2个AI section端点
    - _Requirements: 4.5, 5.3~5.6_

  - [ ] 5.2 创建 `useG0ImportExport.ts` + `useG0DualMode.ts`
    - useG0ImportExport：el-dropdown"导入导出▾" + axios三端点
    - useG0DualMode：模式状态(html/onlyoffice) + 切换逻辑 + localStorage持久化
    - _Requirements: 5.3~5.6_

- [ ] 6. 跨模块联动集成
  - [ ] 6.1 版本链 + 复核集成
    - 两个新建组件主入口集成useVersionTrail（autoSnapshot on save + "版本历史"按钮 + drawer）
    - provide('openReviewDialog', openReviewDialog)供子组件inject
    - _Requirements: 6.1~6.4_

  - [ ] 6.2 行级OCR + 反向联动
    - G0-6: 📎OCR列POST contract-ocr→证券信息识别→确认弹窗→merge
    - G0-6: 从confirmation-hub的G0-1获取未回函项目列表（EventBus/API）
    - _Requirements: 3.8, 3.9_

- [ ] 7. 集成测试与验收
  - [ ] 7.1 编写集成测试
    - wp_code_overrides映射正确性（10条G0→对应componentType）
    - G0-3(证券)差异三维公式（数量/公允价值/市值）
    - G0-6处置损益公式（成交-成本-手续费）
    - G0-6四区块独立增删行+合计
    - G0-1→G0-6反向联动
    - 导入导出round-trip
    - 版本快照autoSnapshot
    - _Requirements: 全部_
