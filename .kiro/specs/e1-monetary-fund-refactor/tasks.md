# Implementation Plan: E1 货币资金专属组件

## Overview

E1货币资金循环专属组件。25个业务sheet拆为15个composable+18个Vue子组件+1个后端端点。按依赖顺序实现：公式引擎→审定表+明细表(核心联动)→盘点+核对→分析程序→检查程序→IPO组→后端导入导出→主入口集成。E1A/E26A程序表复用a-program-console不新建组件。

## Tasks

- [x] 1. 公式引擎 useE1FormulaEngine.ts
  - [x] 1.1 创建 `composables/useE1FormulaEngine.ts` 导出全部纯函数
    - parseNum / calcAudited(单列:未审+账项调整) / calcChange / calcChangeRate(模板口径) / calcCashBalance / calcReconciled / calcAccruedInterest / calcFxConvert / calcCountDiff / sumField / exceedsThreshold / isBalanced / serializeRows / deserializeRows
    - _Requirements: 1.2, 1.3, 3.2, 5.2, 6.2, 6.3, 7.4, 10.3, 12.2-12.5, 14.2_
  - [x]* 1.2 编写 PBT P1-P11 (useE1FormulaEngine.pbt.spec.ts)
    - 11个property测试覆盖全部纯函数 + 动态行增删 + JSON Round-Trip
    - **Validates: Requirements 1.2, 1.3, 3.2, 5.2, 6.2-6.4, 7.4, 10.3, 14.2**

- [x] 2. Checkpoint - 公式引擎验证

- [x] 3. useE1Adjudication.ts (审定表E1-1核心)
  - [x] 3.1 创建 `composables/useE1Adjudication.ts`
    - 固定项目行矩阵(库存现金/银行存款本金/存放财务公司款项/银行机构存款/其他货币资金/数字货币/应计利息小计/合计/境外/试算平衡/差异) + 审定数=未审数+账项调整(单列) + 跨sheet取数(E1-2/3/4未审+E1-5账项调整) + TB回写(按accountCode归集1001/1002/1012) + EventBus监听adjustment:created
    - 注：银行账户维度+函证核对在E1-3，此处仅从E1-3分组合计取数
    - _Requirements: 1.1-1.7, 12.1-12.5_

- [x] 4. useE1CashDetail.ts (现金明细E1-2)
  - [x] 4.1 创建 `composables/useE1CashDetail.ts`
    - 动态行(按币种:期初/增加/减少/期末原币/汇率/折算人民币/审计调整/审定) + 外币折算(calcFxConvert) + 合计行 + 期末合计写入allResponses供E1-1取数
    - _Requirements: 3.1-3.6_

- [x] 5. useE1BankDetail.ts (银行存款及其他货币资金明细E1-3)
  - [x] 5.1 创建 `composables/useE1BankDetail.ts`
    - 双variant(rmb/multi) + 分组(存款本金/财务公司/其他货币资金) + 动态行(银行/账号/账户性质/期初/增减/期末/账项调整/审定/对账单余额/差异) + 函证列(回函确认金额/询证函索引号,从E0取数) + 函证差异高亮 + GtIndexChip跳E0 + 外币版原币/人民币双列 + 分组合计写入allResponses
    - _Requirements: 2.1-2.6, 4.1-4.7_

- [x] 6. useE1Adjustment.ts (调整分录E1-5)
  - [x] 6.1 创建 `composables/useE1Adjustment.ts`
    - 动态行(调整事项说明/类别[报表调整/账项调整/其他]/报表项目/科目名称/附注项目/借方/贷方/索引/备注) + 借贷平衡校验(isBalanced) + EventBus发布 + 按项目归集账项调整净额写入allResponses供E1-1取数 + 推送A2
    - _Requirements: 5.1-5.5_
  - [x]* 6.2 编写 P12 借贷平衡 PBT (useE1Adjustment.pbt.spec.ts)
    - isBalanced === (Σ借方调整 === Σ贷方调整)
    - **Validates: Requirements 5.2**

- [x] 7. useE1Reconciliation.ts (余额调节E1-6)
  - [x] 7.1 创建 `composables/useE1Reconciliation.ts`
    - 按银行账户分组 + 调节公式(企业侧/银行侧) + 差异=调节后企业-调节后银行 + 差异≠0强制原因
    - _Requirements: 6.1-6.5_

- [x] 8. Checkpoint - 核心审定+明细组验证

- [x] 9. useE1CashCount.ts (盘点E1-7/8/9通用)
  - [x] 9.1 创建 `composables/useE1CashCount.ts`
    - variant配置(rmb:面值×张数/fx:外币+汇率/cert:存单) + 盘点差异=实盘-账面 + 差异≠0强制原因
    - _Requirements: 7.1-7.5_

- [x] 10. E1-10/E1-11简单组件(银行账户核对+承诺)
  - [x] 10.1 创建 `composables/useE1AccountList.ts` (E1-10核对表)
    - 动态行(开户银行/账号/账户性质/是否征信/是否审定表/核对结果) + 不一致高亮
    - _Requirements: 8.1-8.2_
  - [x] 10.2 E1-11承诺书(段落式,极简,无独立composable,直接在Vue组件内实现)
    - _Requirements: 8.3_

- [x] 11. useE1Analysis.ts (分析程序E1-14) + useE1CashDetail复用(E1-4数字货币)
  - [x] 11.1 创建 `composables/useE1Analysis.ts`
    - 货币资金构成分析(三年对比:金额/结构比/本期变动/上期变动) + 从E1-1取数(库存现金/银行存款/其他货币资金审定数作期末) + 其他货币资金构成分析 + >30%红色高亮 + AI生成变动原因
    - _Requirements: 9.1-9.3_
  - [x] 11.2 E1-4数字货币明细(复用useE1CashDetail模式,按开户银行/币种)
    - 动态行(序号/开户银行/币种/汇率/期初/增减/期末原币/本位币/账项调整/审定原币/审定人民币/查询余额/差异/索引/备注) + 折算(calcFxConvert) + 审定合计写入allResponses供E1-1数字货币行取数
    - _Requirements: 14.1-14.4_

- [x] 12. useE1InterestCalc.ts (利息计算E1-15/E1-20共用)
  - [x] 12.1 创建 `composables/useE1InterestCalc.ts`
    - E1-15模式:12月×类型矩阵(月均余额×月利率) + 差异=测算-账面
    - E1-20模式:按账户明细(本金×日利率×天数×汇率) + 合计
    - variant区分两种用途
    - _Requirements: 9.4-9.6, 10.3-10.4_

- [x] 13. Checkpoint - 盘点+分析组验证

- [x] 14. useE1CutoffTest.ts (截止测试E1-21/22)
  - [x] 14.1 创建 `composables/useE1CutoffTest.ts`
    - variant(bank/other) + determineCutoff(日期>BS日→跨期) + 跨期高亮
    - _Requirements: 10.4-10.5_

- [x] 15. E1-18/19/23简单检查表
  - [x] 15.1 E1-18/19征信查询+核对(共用composable或直接Vue内实现)
    - _Requirements: 10.1-10.2_
  - [x] 15.2 E1-23收支检查情况表
    - _Requirements: 10.6_

- [x] 16. useE1IpoSpecial.ts (IPO组E26A+E1-26~32)
  - [x] 16.1 创建 `composables/useE1IpoSpecial.ts`
    - 通用动态行composable + sheetCode配置驱动列定义(E1-23/26/27/28/29/30/31/32) + 适用性开关
    - 各sheet列定义不同但CRUD模式相同(现金交易分析12月矩阵/截止测试/收支检查/账户分析/存款利息匹配日矩阵/流水双向核对12月/董监高流水)
    - E26A程序表复用a-program-console(不新建,在主入口分发)
    - _Requirements: 11.1-11.9_

- [x] 16b. useE1DualMode.ts + useE1ImportExport.ts (通用能力composable)
  - [x] 16b.1 创建 `composables/useE1DualMode.ts` (复用D1模式)
    - el-segmented结构化视图/在线编辑切换 + GtOnlyOfficeSheet健康检查(/api/workpapers/onlyoffice/health,双层.data兼容) + 不可用禁用tooltip
    - _Requirements: 13.1_
  - [x] 16b.2 创建 `composables/useE1ImportExport.ts` (复用D4模式,http axios非fetch)
    - 三级导入导出(导出模板/导出数据/导入数据) + 用@/utils/http(带Bearer) + blob下载 + RFC5987中文文件名 + 科目白名单(1001/1002/1012)净化
    - _Requirements: 13.2, 13.3_

- [x] 17. Checkpoint - 检查+IPO组验证

- [x] 18. Vue子组件实现(18个)
  - [x] 18.1 E1TabAdjudication.vue (E1-1, ~400行, 最复杂)
  - [x] 18.2 E1TabCashDetail.vue (E1-2, ~250行)
  - [x] 18.3 E1TabBankDetail.vue (E1-3, ~300行, dual variant segmented)
  - [x] 18.4 E1TabDigitalCurrency.vue (E1-4, ~200行)
  - [x] 18.5 E1TabAdjustment.vue (E1-5, ~250行)
  - [x] 18.6 E1TabReconciliation.vue (E1-6, ~300行)
  - [x] 18.7 E1TabCashCount.vue (E1-7/8, ~250行, variant:rmb/fx)
  - [x] 18.8 E1TabCertificateCount.vue (E1-9, ~200行)
  - [x] 18.9 E1TabAccountList.vue (E1-10, ~200行)
  - [x] 18.10 E1TabAccountCommitment.vue (E1-11, ~150行)
  - [x] 18.11 E1TabAnalysis.vue (E1-14, ~250行)
  - [x] 18.12 E1TabInterestAnalysis.vue (E1-15, ~250行)
  - [x] 18.13 E1TabCreditReport.vue (E1-18/19, ~200行, variant)
  - [x] 18.14 E1TabAccruedInterest.vue (E1-20, ~300行)
  - [x] 18.15 E1TabCutoffTest.vue (E1-21/22, ~200行, variant)
  - [x] 18.16 E1TabLargeCheck.vue (E1-23, ~200行)
  - [x] 18.17 E1TabIpoSpecial.vue (E1-26~32, ~350行, sheetCode分发)
  - [x] 18.18 E1TabDisclosure.vue (附注, ~300行, variant:listed/soe)

- [x] 19. 主入口集成 GtE1MonetaryFund.vue
  - [x] 19.1 修改GtE1MonetaryFund.vue添加sheetName v-if分发+defineAsyncComponent lazy
    - currentSheet computed从sheetName提取编码(regex /E1-\d+/ 或 /E1A/ 或 /E26A/；附注按includes('上市')/includes('国企')匹配)
    - 25个业务sheet的v-if/v-else-if分支(相似sheet合并为同组件+variant prop；E1A/E26A走a-program-console)
    - E1-3双同名sheet：sheetName含"仅人民币"→variant=rmb，含"人民币及外币"→variant=multi
    - GtWpRenderer外层已有sheet目录行，本组件不自建el-tabs(避免双层Tab，同D1铁律)
    - _Requirements: 13.1-13.6_

  - [x] 19.2 注册契约(componentType/override/registry)
    - **✅已完成(2026-07-01)**：wp_code_overrides.json中E1/E1-1~E1-32(27条)已改为`e1-monetary-fund`；account_package_registry.json已新增E1_monetary_fund包(30 sheets,顺序对齐源模板tab)；E1-1/E1-2/E1-6/E1-10 YAML已修正真实语义
    - **待做**：①`VALID_COMPONENT_TYPES`(wp_classification_service.py)注册`e1-monetary-fund`(否则uvicorn启动ValueError) ②前端`htmlRendererRegistry`(componentType→GtE1MonetaryFund映射) ③后端`RENDERER_DISPATCH`/render策略(返回sheets[].html_data结构)
    - 更新`htmlRendererRegistry.spec.ts`的expected componentType计数断言
    - _Requirements: 13.1, 13.6_

- [x] 20. 后端导入导出 _e1_import_export.py
  - [x] 20.1 创建后端端点(复用_d1_import_export.py模式)
    - POST /api/workpapers/{wp_id}/e1/export-template?sheet=
    - POST /api/workpapers/{wp_id}/e1/export-data?sheet=
    - POST /api/workpapers/{wp_id}/e1/import-data?sheet=
    - 支持sheets: E1-2/E1-3/E1-5/E1-6/E1-7/E1-8/E1-9/E1-10/E1-20/E1-21/E1-22
    - _Requirements: 13.2_
  - [x]* 20.2 编写后端导入导出hypothesis测试
    - round-trip + 模板校验 + 列名篡改400

- [x] 21. Checkpoint - 全部集成验证

- [x] 22. 回归测试
  - [x] 22.1 运行全部E1相关测试确认无回归
    - vitest run E1相关 + pytest -k e1

## Notes

- E1A/E26A程序表复用现有a-program-console componentType，不新建专属组件（E26A=IPO大额现金交易程序表，独立于常规E1A）
- **⚠️源模板真实结构(openpyxl实读2026-07-01)**：审定表E1-1=项目行矩阵(非3科目section)，审定数=未审数+账项调整(单列,非AJE/RJE)；E1-2按币种(非按日期)；E1-5类别=报表调整/账项调整/其他；函证列在E1-3明细表(非E1-1)
- **✅注册四件套已对齐(2026-07-01)**：overrides(27条→e1-monetary-fund)+registry(E1包30 sheets)+E1-1/2/6/10 YAML真实语义修正(旧E1-6误标"受限货币资金"/E1-10误标"调整分录汇总"已改正)
- E1-3两个同名sheet用variant区分（el-segmented切换"仅人民币"/"人民币及外币"）
- E1-4数字货币复用useE1CashDetail模式(Task 11.2)，E1TabDigitalCurrency.vue独立
- E1-7/E1-8共用E1TabCashCount.vue(variant:rmb/fx)
- E1-18/E1-19共用E1TabCreditReport.vue(variant:query/check)
- E1-21/E1-22共用E1TabCutoffTest.vue(variant:bank/other)
- E1-23/E1-26~32共用E1TabIpoSpecial.vue(sheetCode prop驱动列定义)
- IPO组(E26A+E1-26~32)通过适用性开关控制可见性（非IPO项目不显示）
- 跨Sheet数据流通过allResponses Map computed链实现(不走API)
- 所有PBT使用fast-check numRuns:100；P12借贷平衡在Task 6.2(useE1Adjustment)
- 编码跳跃(E1-12/13/16/17/24/25)在致同2025修订版中不存在
