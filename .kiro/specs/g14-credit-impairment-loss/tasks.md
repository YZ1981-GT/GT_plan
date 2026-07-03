# Implementation Plan: G14 信用减值损失底稿专属HTML精美组件

## Overview

实现G14信用减值损失专属组件`g14-credit-impairment-loss`。按D~N底稿开发标准8步：注册→公式引擎→数据层→各sheet Vue组件→后端→联动集成→集成测试。主入口GtG14CreditImpairmentLoss.vue + 6个子组件 + 4个composable + 后端4个py文件。核心公式：审定=未审+调整；净信用减值=计提-转回；坏账准备滚动=期初+计提-转回-核销；变动率=(本期-上期)/|上期|；借贷平衡。6个有效sheet，1个xlsx源模板。科目6702信用减值损失（**损益类/借方费用类**）。G循环中信用风险管理核心科目，汇总各金融资产ECL减值计提/转回的净损失，与D1/D5/G2/G4/G5/G6各科目减值数据交叉验证。**坏账准备滚动验证**为本底稿特色。

## Tasks

- [ ] 1. 组件注册与基础配置
  - [ ] 1.1 注册componentType和映射
    - 在 `wp_code_overrides.json` 中将G14A/G14-1/G14-2/G14-3/附注披露(上市)/附注披露(国企)/底稿目录映射为'g14-credit-impairment-loss'（7个wp_code条目）
    - 在 `VALID_COMPONENT_TYPES` 中注册'g14-credit-impairment-loss'
    - 在 `htmlRendererRegistry.ts` 中注册 'g14-credit-impairment-loss' → GtG14CreditImpairmentLoss 映射
    - 创建 `GtG14CreditImpairmentLoss.vue` 主入口骨架（sheetName prop + regex提取编码 + v-if分发 + defineAsyncComponent lazy×6 + selfLoad逻辑 + OnlyOffice fallback + useVersionTrail + provide openReviewDialog）
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ]* 1.2 编写注册契约测试
    - htmlRendererRegistry.spec.ts 中验证'g14-credit-impairment-loss'已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证7个映射条目
    - _Requirements: 1.3_

- [ ] 2. 实现公式引擎 useG14FormulaEngine.ts
  - [ ] 2.1 创建 `composables/useG14FormulaEngine.ts`，实现6个纯函数+parseNum
    - 实现 `parseNum(v: unknown): number` — null/undefined/NaN/''→0
    - 实现 `calcAdjustedAmount(unadjusted, adjustment): number` — 审定=未审+调整
    - 实现 `calcNetImpairmentLoss(provision, reversal): number` — 净信用减值损失=计提-转回
    - 实现 `calcProvisionRollForward(opening, provision, reversal, writeoff): number` — 坏账准备滚动=期初+计提-转回-核销
    - 实现 `calcChangeRate(prior, current): number|null` — 变动率=(本期-上期)/|上期|，上期=0→null
    - 实现 `isDebitCreditBalanced(debits[], credits[]): boolean` — |SUM(debits)-SUM(credits)|<0.01
    - 实现 `calcVariance(computed, actual): number` — 差异=computed-actual（坏账滚动差异/审定交叉差异）
    - _Requirements: 4.2, 4.3, 4.4_

  - [ ]* 2.2 编写 Property 1 PBT：审定数公式
    - 生成器：`fc.float({min:-1e8, max:1e8})` × unadjusted/adjustment
    - 断言：calcAdjustedAmount(unadjusted, adjustment) === unadjusted + adjustment
    - **Property 1: 审定数=未审数+调整数**
    - **Validates: Requirements 2.2, 4.2**

  - [ ]* 2.3 编写 Property 2 PBT：净信用减值损失公式
    - 生成器：`fc.float({min:0, max:1e8})` × provision/reversal
    - 断言：calcNetImpairmentLoss(provision, reversal) === provision - reversal
    - **Property 2: 净信用减值损失=计提-转回**
    - **Validates: Requirements 3.2, 4.3**

  - [ ]* 2.4 编写 Property 3 PBT：坏账准备滚动恒等
    - 生成器：`fc.float({min:0, max:1e8})` × opening/provision/reversal/writeoff
    - 断言：calcProvisionRollForward(opening, provision, reversal, writeoff) === opening + provision - reversal - writeoff
    - **Property 3: 坏账准备滚动=期初+计提-转回-核销**
    - **Validates: Requirements 3.3, 4.4**

  - [ ]* 2.5 编写 Property 4 PBT：坏账准备滚动验证检测
    - 生成器：`fc.float({min:0, max:1e8})` × opening/provision/reversal/writeoff/closingActual
    - 断言：|calcProvisionRollForward(...) - closingActual| > 0.01 → 不平衡；≤ 0.01 → 平衡
    - **Property 4: 坏账准备滚动验证检测**
    - **Validates: Requirements 3.4**

  - [ ]* 2.6 编写 Property 5 PBT：变动率方向性与除零保护
    - 生成器：`fc.float({min:0.01, max:1e8})` prior + `fc.float()` current
    - 断言：current>prior → rate>0；current<prior → rate<0；calcChangeRate(0, any)===null
    - **Property 5: 变动率方向正确+除零→null**
    - **Validates: Requirements 2.5, 4.2**

  - [ ]* 2.7 编写 Property 6 PBT：借贷平衡恒等
    - 生成器：`fc.array(fc.float({min:0, max:1e6}), {minLength:1, maxLength:20})` × debits/credits
    - 断言：isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)
    - **Property 6: 借贷平衡**
    - **Validates: Requirements 4.1, 4.2**

  - [ ]* 2.8 编写 Property 7 PBT：parseNum健壮性
    - 生成器：`fc.oneof(fc.constant(null), fc.constant(undefined), fc.constant(''), fc.constant(NaN), fc.constant('abc'))` + `fc.float()`有效数
    - 断言：无效输入→0；有效finite数→原值
    - **Property 7: parseNum健壮性**
    - **Validates: Requirements 4.2**

- [ ] 3. Checkpoint - 公式引擎验证
  - Ensure all PBT tests pass (P1~P7), ask the user if questions arise.

- [ ] 4. 实现数据层composable
  - [ ] 4.1 创建 `composables/useG14FormData.ts`
    - 实现 selfLoad逻辑（GET render-config → 解析sheets → 分发htmlData）
    - 实现 saveImmediate / debouncedSave（POST /checklist-responses）
    - 实现 trial_balance取数(科目6702，损益类/借方费用取发生额：借方-贷方)
    - 实现 writebackTB(审定数回写trial_balance)
    - _Requirements: 1.4, 2.4_

  - [ ] 4.2 创建 `composables/useG14ImportExport.ts` + `composables/useG14DualMode.ts`
    - useG14ImportExport：el-dropdown"导入导出▾" + axios三端点(export-template/export-data/import-data) + 2张表(G14-2/G14-3)
    - useG14DualMode：模式状态(html/onlyoffice) + 切换按钮 + localStorage持久化
    - _Requirements: 4.6, 4.8_

- [ ] 5. 实现Vue子组件（6个sheet）
  - [ ] 5.1 创建 `g14-credit-impairment-loss/G14TabProcedure.vue`（G14A程序表）
    - 复用a-program-console（22行×10列）
    - GtVoucherSamplingEngine集成（dialog, accountCode='6702'）
    - useCutoffAutoSampling集成（accountCode='6702', days=5）
    - selfLoad逻辑（bundle内嵌场景htmlData为null时自加载）
    - _Requirements: 2.1_

  - [ ] 5.2 创建 `g14-credit-impairment-loss/G14TabAdjudication.vue`（G14-1审定表36行×11列）
    - 按减值来源科目分组（应收账款/其他应收款/应收票据/应收款项融资/债权投资/其他债权投资/长期应收款/应收利息/合计）
    - 列结构：项目|本期(未审|调整|审定)|上期(未审|调整|审定)|变动额|变动率|原因分析|索引
    - 损益类/借方费用公式：审定=未审+调整；变动额=本期审定-上期审定；变动率=(本期-上期)/|上期|
    - trial_balance取数(6702) → EventBus publish `substantive:adjudicated`(accountCode='6702')
    - |变动率|>20%橙色高亮+原因分析必填验证
    - GtIndexChip + inject openReviewDialog + AI按钮(adjudication-analysis)
    - UI铁律：13px字体/公式列虚线下划线+cursor:help+tooltip/min-width自适应
    - _Requirements: 2.2, 2.3, 2.4, 2.5_

  - [ ] 5.3 创建 `g14-credit-impairment-loss/G14TabDetail.vue`（G14-2明细表36行×13列）
    - 列结构：来源科目|来源科目代码|被评估资产|计提方式(组合/单项下拉)|期初坏账准备|本期计提|本期转回|本期核销|期末坏账准备|本期信用减值损失(公式)|上期信用减值损失|源科目索引|交叉验证结论(下拉)
    - 公式列：本期信用减值损失=计提-转回（calcNetImpairmentLoss）
    - **坏账准备滚动验证**：calcProvisionRollForward(期初,计提,转回,核销) vs 期末坏账准备，|差异|>0.01→红色高亮期末单元格+tooltip差异金额
    - ECL交叉验证：与D1/D5/G2/G4/G5/G6各科目减值数据勾稽，crossVerification下拉(consistent/inconsistent/pending)
    - 按来源科目分组小计+总计；总计信用减值损失与G14-1合计比对，不一致红色提示
    - 动态行增删(弹ElMessageBox.prompt输入来源科目名称) + 导入导出
    - GtIndexChip(sourceIndex跳转源科目底稿) + inject openReviewDialog
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [ ] 5.4 创建 `g14-credit-impairment-loss/G14TabAdjustment.vue`（G14-3调整分录24行×10列）
    - 标准AJE/RJE列：序号|类型(AJE/RJE)|日期|摘要|科目编码|科目名称|借方|贷方|编制人|备注
    - 借贷平衡校验：isDebitCreditBalanced → 不平衡红色提示
    - 回写G14-1审定表adjustment列（AJE+RJE汇总）
    - 动态行增删 + 导入导出
    - _Requirements: 4.1_

  - [ ] 5.5 创建 `g14-credit-impairment-loss/G14TabDisclosureListed.vue` + `G14TabDisclosureSOE.vue`（附注披露）
    - 上市公司附注(18行×5列) + 国企附注(15行×7列)
    - EventBus subscribe `substantive:adjudicated`(accountCode='6702') → 刷新审定数
    - EventBus publish `disclosure:note-text-updated`(accountCode='6702') → 联动附注模块
    - AI辅助按钮(impairment-conclusion) + section标题行右侧
    - mounted时主动拉取最新审定数（非纯被动监听）
    - _Requirements: 2.6_

- [ ] 6. 实现后端4个py文件
  - [ ] 6.1 创建后端render策略 + service
    - `_g14_credit_impairment_loss.py`：render策略函数 render_g14_credit_impairment_loss + 注册RENDERER_DISPATCH['g14-credit-impairment-loss']
    - `_g14_credit_impairment_loss_service.py`：G14CreditImpairmentLossService（get_trial_balance_data/save_adjudication/validate_formulas/validate_roll_forward）
    - _Requirements: 1.3, 4.2_

  - [ ] 6.2 创建后端导入导出 + AI端点
    - `_g14_credit_impairment_loss_import_export.py`：6端点(export-template/export-data/import-data × G14-2/G14-3) + RFC5987中文文件名编码
    - `_g14_credit_impairment_loss_ai.py`：2个AI section端点(adjudication-analysis/impairment-conclusion) + 30秒超时
    - _Requirements: 4.6, 4.7_

- [ ] 7. 跨模块联动集成（5大集成）
  - [ ] 7.1 五大集成接入验证
    - ①版本链：主入口useVersionTrail(autoSnapshot on save + "版本历史"按钮)
    - ②抽凭引擎：G14A程序表GtVoucherSamplingEngine(dialog, accountCode='6702')
    - ③截止自动提取：G14A useCutoffAutoSampling(accountCode='6702', days=5)
    - ④附注EventBus：G14-1 publish + 附注 subscribe/publish（双向联动）
    - ⑤复核对话：主入口provide openReviewDialog → 子组件inject → section标题栏右侧按钮
    - _Requirements: 4.5_

- [ ] 8. 最终验证
  - [ ]* 8.1 编写集成测试
    - sheetName分发正确性（6个sheet→对应子组件 + 未知sheet→OnlyOffice fallback）
    - 损益类/借方费用公式链（TB取数6702 → 未审+调整=审定 → EventBus → 附注刷新）
    - 净信用减值损失公式（计提-转回）+ G14-2总计与G14-1合计比对
    - 坏账准备滚动验证（期初+计提-转回-核销=期末 → 不平衡红色高亮）
    - ECL交叉验证（D1/D5/G2/G4/G5/G6勾稽 → consistent/inconsistent/pending）
    - 变动率公式（方向性+除零null+>20%橙色高亮）
    - 借贷平衡（G14-3 AJE/RJE → 回写G14-1）
    - 导入导出round-trip（2张表G14-2/G14-3）
    - _Requirements: 全部_

  - [ ] 8.2 Final checkpoint
    - Ensure all tests pass, ask the user if questions arise.

## Notes

- G14是损益类/借方费用类科目6702：本期发生额=借方-贷方（损失为正，借方增加费用）
- G循环中信用风险管理核心科目：汇总各金融资产ECL减值计提/转回的净损失
- **坏账准备滚动验证为本底稿特色**：期末=期初+计提-转回-核销，不平衡红色高亮
- **ECL交叉验证**：G14-2明细与D1/D5/G2/G4/G5/G6各科目减值数据勾稽
- 最大sheet仅36行×13列，无需虚拟滚动、无需宽表拆分
- 公式引擎6个纯函数+parseNum：calcAdjustedAmount/calcNetImpairmentLoss/calcProvisionRollForward/calcChangeRate/isDebitCreditBalanced/calcVariance
- 导入导出仅2张动态行表格（G14-2/G14-3）
- AI辅助仅2个section（adjudication-analysis / impairment-conclusion）
- 五大集成（版本链/抽凭/截止/附注EventBus/复核），无OCR（无凭证检查表）
- 动态行新增需弹ElMessageBox.prompt输入来源科目名称
- 区别于G13（贷方收益类6101）：G14是借方费用类6702
- Tasks marked with `*` are optional and can be skipped for faster MVP
- Property tests validate universal correctness properties (7 PBT)
- Checkpoints ensure incremental validation

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8"] },
    { "id": 3, "tasks": ["4.1", "4.2", "6.1", "6.2"] },
    { "id": 4, "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5"] },
    { "id": 5, "tasks": ["7.1", "8.1"] }
  ]
}
```
