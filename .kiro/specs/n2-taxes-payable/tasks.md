# Implementation Plan: N2 应交税费底稿专属HTML精美组件

## Overview

N2应交税费底稿专属组件`n2-taxes-payable`。N税费循环最复杂底稿（18 sheet/1 xlsx/~180+公式，其中O1A原底稿/出口退税额复核示例标记skip）。

主入口 GtN2TaxesPayable.vue（sheetName v-if，defineAsyncComponent lazy）+ 14个子组件（core/inspection/calc三分组）+ 14个composable + 后端3个py文件。

科目：2221应交税费（**贷方/负债类**！取期末余额）
公式特征：审定=未审+AJE+RJE；负债类期末=期初+贷方-借方；增值税=销项-(进项-进项转出)；各税种=计税依据×税率；土增税四级累进；计提联动N4税金及附加。

## Tasks

### Phase 0: 双源输入验证

- [ ] 0.1 openpyxl脚本读取N2应交税费.xlsx全部18 sheet
  - 提取：sheet名/列头/行数/公式单元格/合并区域/数据类型
  - 确认：审定表N2-1(31×14,85公式)/明细表N2-2(42×23,22公式)/认定表N2-5(54×15)/增值税测算N2-6(48×8)/其他税费测算N2-8(26×9,11公式)/房产税N2-9(30×7)/土增税N2-10(51×7)
  - 标记skip：O1A原底稿/出口退税额复核示例
  - 产出：n2_structure_summary.json（权威列头+公式清单）
  - _Requirements: 双源输入流程_

- [ ] 0.2 N税费循环底稿模板库md交叉验证
  - 核对：负债类取数规则/多税种测算逻辑/增值税销项进项/出口退税/N4计提联动/附注结构
  - 冲突解决：列名以xlsx为准，联动方向以md为准
  - 产出：n2_conflict_resolution.md（如有冲突）
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [ ] 1.1 注册componentType和映射
  - wp_code_overrides: N2/N2-1~N2-11/N2A → 'n2-taxes-payable'
  - VALID_COMPONENT_TYPES + htmlRendererRegistry注册
  - 创建 GtN2TaxesPayable.vue 骨架（sheetName prop v-if分发 + defineAsyncComponent lazy + selfLoad）
  - _Requirements: 1.1, 1.2, 1.3, 1.6, 1.7, 1.8, 1.9, 1.11_

- [ ] 1.2 编写注册契约测试
  - htmlRendererRegistry.spec.ts / VALID_COMPONENT_TYPES / wp_code_overrides / RENDERER_DISPATCH
  - _Requirements: 1.6, 1.7, 1.8_

### Phase 2: 公式引擎+税务引擎+PBT

- [ ] 2.1 创建 `composables/useN2FormulaEngine.ts`（负债类！）
  - calcAuditedAmount(u,a,r)=u+a+r
  - calcLiabilityEndBalance(begin,credit,debit)=begin+credit-debit（负债类期末，2221贷方）
  - calcSubtotal / calcDiff(bookAmount,declaredAmount)=账面-申报表
  - _Requirements: 1.5, 2.3, 2.4, 12.1-12.4_

- [ ] 2.2 创建 `composables/useN2VatEngine.ts`（增值税测算引擎，纯函数）
  - calcOutputVat(salesAmount,taxRate)=销售额×税率
  - calcPayableVat(outputVat,inputVat,inputTransferOut)=销项-(进项-进项转出)
  - calcVatBurdenRate(payableVat,salesAmount)=应交增值税/销售额
  - _Requirements: 4.2, 4.6_

- [ ] 2.3 创建 `composables/useN2MultiTaxEngine.ts`（多税种测算引擎，核心纯函数）
  - calcSurtax(vat,consumptionTax,rate)=(增值税+消费税)×税率
  - calcPropertyTaxByValue(originalValue,deductRate)=原值×(1-扣除比例)×1.2%
  - calcPropertyTaxByRent(rentIncome)=租金×12%
  - calcLandVat(appreciation,taxRate,deductItems,quickDeductCoef)=增值额×税率-扣除项目×速算扣除系数
  - calcAppreciationRate(appreciation,deductItems)=增值额/扣除项目
  - _Requirements: 5.2, 6.2, 7.2, 7.4_

- [ ]* 2.4 编写 Property P1 PBT：审定数公式链
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: n2-taxes-payable, Property P1: 审定数公式链**

- [ ]* 2.5 编写 Property P2 PBT：负债类期末余额（期初+贷-借）
  - 生成器：fc.float({min:0,max:1e9}) × 3 (begin, credit, debit)
  - 断言：calcLiabilityEndBalance(b, c, d) === b + c - d
  - **Feature: n2-taxes-payable, Property P2: 负债类期末余额（期初+贷-借）**

- [ ]* 2.6 编写 Property P3 PBT：增值税销项税额
  - 生成器：sales∈R≥0, rate∈[0,0.17]
  - 断言：calcOutputVat(sales, rate) === sales × rate
  - **Feature: n2-taxes-payable, Property P3: 增值税销项税额=销售额×税率**

- [ ]* 2.7 编写 Property P4 PBT：应交增值税（销项-进项）
  - 断言：calcPayableVat(out, in, trans) === out - (in - trans)
  - **Feature: n2-taxes-payable, Property P4: 应交增值税=销项-(进项-进项转出)**

- [ ]* 2.8 编写 Property P5 PBT：城建税及附加
  - 生成器：vat,ct∈R≥0, rate∈{0.07,0.05,0.01,0.03,0.02}
  - 断言：calcSurtax(vat, ct, rate) === (vat + ct) × rate
  - **Feature: n2-taxes-payable, Property P5: 城建税及附加=(增值税+消费税)×税率**

- [ ]* 2.9 编写 Property P6 PBT：房产税从价
  - 生成器：ov∈R≥0, dr∈[0,0.3]
  - 断言：calcPropertyTaxByValue(ov, dr) === ov × (1-dr) × 0.012
  - **Feature: n2-taxes-payable, Property P6: 房产税从价=原值×(1-扣除比例)×1.2%**

- [ ]* 2.10 编写 Property P7 PBT：土地增值税
  - 生成器：app,di∈R≥0, rate∈{0.3,0.4,0.5,0.6}, coef∈[0,0.35]
  - 断言：calcLandVat(app, rate, di, coef) === app × rate - di × coef
  - **Feature: n2-taxes-payable, Property P7: 土地增值税=增值额×税率-扣除项目×速算扣除系数**

- [ ]* 2.11 编写 Property P8 PBT：合计行恒等
  - 断言：calcSubtotal(arr) === Σarr
  - **Feature: n2-taxes-payable, Property P8: 合计行恒等**

- [ ]* 2.12 编写 Property P9 PBT：土增税增值率
  - 生成器：app∈R, di≠0
  - 断言：calcAppreciationRate(app, di) === app / di
  - **Feature: n2-taxes-payable, Property P9: 土增税增值率=增值额/扣除项目**

### Phase 3: Composable层

- [ ] 3.1 创建 useN2FormData.ts
  - selfLoad + checklist_responses + writebackTB(**期末余额**，科目2221贷方)
  - _Requirements: 1.9, 1.10, 2.7, 12.1-12.4_

- [ ] 3.2 创建 useN2CrossSheet.ts
  - adjudicationVsDetail / adjudicationVsCalcTables(N2-6/N2-8/N2-9/N2-10) / vatToSurtax(N2-6→N2-8计税依据) / accrualToN4(计提→N4)
  - _Requirements: 2.5, 2.6, 4.5, 5.3, 5.4, 6.3, 7.5, 8.4, 11.1-11.4_

- [ ] 3.3 创建 useN2DualMode.ts + useN2ImportExport.ts
  - 双模式（结构化/矩阵/在线编辑）+ 导入导出三级（多税种分sheet导出）
  - _Requirements: 3.4_

- [ ] 3.4 创建 sheet-specific composables
  - useN2Adjudication / useN2Detail / useN2VatCalc / useN2OtherTaxCalc / useN2PropertyTax / useN2Lvt / useN2ExportRefund
  - _Requirements: 2~10 全部_

### Phase 4: Vue子组件（core）

- [ ] 4.1 创建 N2TabIndex.vue 底稿目录
  - 18行（skip标记2行）+进度条+多税种统计仪表板+联动状态
  - _Requirements: 1.2, 1.11_

- [ ] 4.2 创建 N2TabAdjudication.vue 审定表N2-1
  - 85公式+负债类期末取数+税种分行+N2-2/各测算表交叉验证+TB回写+N4联动提示
  - _Requirements: 2.1-2.8_

- [ ] 4.3 创建 N2TabDetail.vue 明细表N2-2
  - 23列区段Tab（基础/计提缴纳/核对）+22公式+期末=期初+计提-缴纳+差异标红+动态行+统计摘要+导入导出
  - _Requirements: 3.1-3.6_

- [ ] 4.4 创建 N2TabAdjustment.vue 调整分录N2-3
  - 借贷平衡+EventBus+双向同步N2-1
  - _Requirements: 10.3_

- [ ] 4.5 创建 N2TabDisclosureListed/Soe.vue
  - 附注上市(27×11)/国企(24×11)+各税种期初期末明细
  - _Requirements: 13.1-13.3_

### Phase 4b: Vue子组件（inspection）

- [ ] 4.6 创建 N2TabPolicyCheck.vue 税收政策检查N2-4
  - 税收优惠/税率适用/纳税义务时点合规检查+合规/不合规/不适用判断+不合规红色摘要
  - _Requirements: 9.3-9.5_

- [ ] 4.7 创建 N2TabRecognition.vue 应交税金认定表N2-5
  - 54×15+各税种×期间矩阵认定+与各测算表交叉验证
  - _Requirements: 9.1-9.2_

- [ ] 4.8 创建 N2TabTaxCheck.vue 应交税费检查表N2-11
  - 逐税种核查（计提准确性/缴纳及时性/申报一致性）+行级抽凭
  - _Requirements: 10.1-10.2_

### Phase 4c: Vue子组件（calc，核心测算）

- [ ] 4.9 创建 N2TabVatCalc.vue 增值税测算表N2-6
  - 48×8+销项-进项测算+按月/季度分行+税负率分析+回填N2-1增值税行+供N2-8计税依据
  - _Requirements: 4.1-4.6_

- [ ] 4.10 创建 N2TabExportRefund.vue 出口退税核对表N2-7
  - 免抵退税额测算+与批复核对+差异标记+联动N2-6
  - _Requirements: 8.1-8.4_

- [ ] 4.11 创建 N2TabOtherTaxCalc.vue 其他税费测算表N2-8
  - 26×9+11公式+城建税/教育费附加/地方教育附加+计税依据取自N2-6+城建税税率地区选择+回填N2-1及联动N4
  - _Requirements: 5.1-5.5_

- [ ] 4.12 创建 N2TabPropertyTax.vue 房产税测算表N2-9
  - 30×7+从价(原值×(1-扣除比例)×1.2%)/从租(租金×12%)+扣除比例地区配置+回填N2-1及联动N4
  - _Requirements: 6.1-6.4_

- [ ] 4.13 创建 N2TabLvt.vue 土地增值税测算表N2-10
  - 51×7+增值额/增值率+四级累进税率自动匹配+速算扣除系数+回填N2-1
  - _Requirements: 7.1-7.5_

### Phase 5: 后端

- [ ] 5.1 创建 n2_taxes_payable_renderer.py
  - RENDERER_DISPATCH注册 + **负债类取数逻辑**（期末余额！2221贷方）
  - _Requirements: 1.6, 12.2_

- [ ] 5.2 创建 n2_taxes_payable.py 路由
  - 导出模板/导出数据/导入数据（axios+Authorization，多税种分sheet）
  - _Requirements: 3.4_

- [ ] 5.3 创建 n2_taxes_payable_service.py
  - 负债类取数（tb_balance期末余额，direction=贷）+ 多税种测算 + 增值税测算 + 出口退税 + 跨底稿合计
  - _Requirements: 4~8, 12.1-12.4_

### Phase 6: 集成

- [ ] 6.1 EventBus集成
  - publish 'substantive:adjudicated'（N2-1→附注）
  - publish 'adjustment:created'（N2-3→A13）
  - publish 'tax-accrual:updated'（各税种计提额→N4税金及附加）
  - subscribe 'disclosure:refresh'
  - _Requirements: 10.3, 11.1, 13.2_

- [ ] 6.2 跨底稿GtIndexChip
  - N2-1税种行 ↔ N4-1税金及附加对应项
  - N2-6增值税 → N2-8城建税计税依据
  - _Requirements: 11.2, 11.3_

- [ ] 6.3 六大集成标准
  - 版本链useVersionTrail + 附注EventBus + 复核对话provide/inject + 行级OCR + 导入导出 + 抽凭引擎
  - _Requirements: 1.5, 10.2, 13.2_

### Phase 7: 测试

- [ ] 7.1 单元测试：useN2FormulaEngine + useN2VatEngine + useN2MultiTaxEngine
  - 负债类方向(期初+贷-借) + 增值税销项进项 + 各税种计税依据×税率 + 土增税累进 + 边界(零值/大数/税率边界/留抵)
  - _Requirements: P1-P9_

- [ ] 7.2 集成测试：负债类取数+多税种测算+跨底稿联动
  - 期末余额取数正确性(贷方) / 各测算表→N2-1回填 / N2-6→N2-8计税依据 / 计提→N4联动 / 账面vs申报表差异
  - _Requirements: 2.5-2.6, 4.5, 5.3, 8.4, 11.1-11.4, 12.1-12.4_

- [ ] 7.3 Playwright E2E
  - 完整流程：打开N2→审定(验证负债类取数)→明细→增值税测算(销项-进项)→其他税费测算→房产税→土增税→出口退税→保存
  - _Requirements: 全部_

## Task Dependency Graph

```mermaid
graph TD
    P0[Phase 0: 双源输入] --> P1[Phase 1: 注册]
    P1 --> P2[Phase 2: 公式引擎+增值税引擎+多税种引擎+PBT]
    P2 --> P3[Phase 3: Composable]
    P3 --> P4[Phase 4: Vue组件 core]
    P3 --> P4b[Phase 4b: Vue组件 inspection]
    P3 --> P4c[Phase 4c: Vue组件 calc测算]
    P1 --> P5[Phase 5: 后端(负债类取数)]
    P4 --> P6[Phase 6: 集成+N4联动]
    P4b --> P6
    P4c --> P6
    P5 --> P6
    P6 --> P7[Phase 7: 测试]
```
