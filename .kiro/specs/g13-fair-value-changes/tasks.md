# Implementation Plan: G13 公允价值变动收益底稿专属HTML精美组件

## Overview

实现G13公允价值变动收益专属组件`g13-fair-value-changes`。按D~N底稿开发标准8步：注册→公式引擎→数据层→各sheet Vue组件→后端→联动集成→集成测试。主入口GtG13FairValueChanges.vue + 6个子组件 + 4个composable + 后端4个py文件。核心公式：审定=未审+调整；FV变动=期末-期初；变动率=(本期-上期)/|上期|；借贷平衡。6个有效sheet，1个xlsx源模板。科目6101公允价值变动收益/损失（损益类）。G循环中最简洁科目，无凭证检查表、无虚拟滚动、无宽表拆分。

## Tasks

- [ ] 1. 组件注册与基础配置
  - [ ] 1.1 注册componentType和映射
    - 在 `wp_code_overrides.json` 中将G13A/G13-1/G13-2/G13-3/附注披露(上市)/附注披露(国企)/底稿目录映射为'g13-fair-value-changes'（7个wp_code条目）
    - 在 `VALID_COMPONENT_TYPES` 中注册'g13-fair-value-changes'
    - 在 `htmlRendererRegistry.ts` 中注册 'g13-fair-value-changes' → GtG13FairValueChanges 映射
    - 创建 `GtG13FairValueChanges.vue` 主入口骨架（sheetName prop + regex提取编码 + v-if分发 + defineAsyncComponent lazy×6 + selfLoad逻辑 + OnlyOffice fallback + useVersionTrail + provide openReviewDialog）
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ]* 1.2 编写注册契约测试
    - htmlRendererRegistry.spec.ts 中验证'g13-fair-value-changes'已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证7个映射条目
    - _Requirements: 1.3_

- [ ] 2. 实现公式引擎 useG13FormulaEngine.ts
  - [ ] 2.1 创建 `composables/useG13FormulaEngine.ts`，实现5个纯函数+parseNum
    - 实现 `parseNum(v: unknown): number` — null/undefined/NaN/''→0
    - 实现 `calcAdjustedAmount(unadjusted, adjustment): number` — 审定=未审+调整
    - 实现 `calcFVChange(opening, closing): number` — 公允价值变动=期末-期初
    - 实现 `calcChangeRate(prior, current): number|null` — 变动率=(本期-上期)/|上期|，上期=0→null
    - 实现 `isDebitCreditBalanced(debits[], credits[]): boolean` — |SUM(debits)-SUM(credits)|<0.01
    - 实现 `calcVariance(fvChange, adjustedAmount): number` — 差异=fvChange-adjustedAmount
    - _Requirements: 4.2_

  - [ ]* 2.2 编写 Property 1 PBT：审定数公式
    - 生成器：`fc.float({min:-1e8, max:1e8})` × unadjusted/adjustment
    - 断言：calcAdjustedAmount(unadjusted, adjustment) === unadjusted + adjustment
    - **Property 1: 审定数=未审数+调整数**
    - **Validates: Requirements 2.2, 3.3, 4.2**

  - [ ]* 2.3 编写 Property 2 PBT：公允价值变动公式
    - 生成器：`fc.float({min:-1e9, max:1e9})` × opening/closing
    - 断言：calcFVChange(opening, closing) === closing - opening
    - **Property 2: FV变动=期末-期初**
    - **Validates: Requirements 3.2, 4.2**

  - [ ]* 2.4 编写 Property 3 PBT：FV变动与审定差异检测
    - 生成器：`fc.float()` × opening/closing/unadjusted/adjustment，约束 calcFVChange===calcAdjustedAmount
    - 断言：calcVariance(calcFVChange(o,c), calcAdjustedAmount(u,a)) === 0
    - **Property 3: FV变动=审定数时差异为零**
    - **Validates: Requirements 3.4**

  - [ ]* 2.5 编写 Property 4 PBT：变动率方向性与除零保护
    - 生成器：`fc.float({min:0.01, max:1e8})` prior + `fc.float()` current
    - 断言：current>prior → rate>0；current<prior → rate<0；calcChangeRate(0, any)===null
    - **Property 4: 变动率方向正确+除零→null**
    - **Validates: Requirements 2.2, 4.2**

  - [ ]* 2.6 编写 Property 5 PBT：借贷平衡恒等
    - 生成器：`fc.array(fc.float({min:0, max:1e6}), {minLength:1, maxLength:20})` × debits/credits
    - 断言：isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)
    - **Property 5: 借贷平衡**
    - **Validates: Requirements 4.1, 4.2**

  - [ ]* 2.7 编写 Property 6 PBT：parseNum健壮性
    - 生成器：`fc.oneof(fc.constant(null), fc.constant(undefined), fc.constant(''), fc.constant(NaN), fc.constant('abc'))` + `fc.float()`有效数
    - 断言：无效输入→0；有效finite数→原值
    - **Property 6: parseNum健壮性**
    - **Validates: Requirements 4.2**

- [ ] 3. Checkpoint - 公式引擎验证
  - Ensure all PBT tests pass (P1~P6), ask the user if questions arise.

- [ ] 4. 实现数据层composable
  - [ ] 4.1 创建 `composables/useG13FormData.ts`
    - 实现 selfLoad逻辑（GET render-config → 解析sheets → 分发htmlData）
    - 实现 saveImmediate / debouncedSave（POST /checklist-responses）
    - 实现 trial_balance取数(科目6101，损益类取发生额)
    - 实现 writebackTB(审定数回写trial_balance)
    - _Requirements: 1.4, 2.4_

  - [ ] 4.2 创建 `composables/useG13ImportExport.ts` + `composables/useG13DualMode.ts`
    - useG13ImportExport：el-dropdown"导入导出▾" + axios三端点(export-template/export-data/import-data) + 2张表(G13-2/G13-3)
    - useG13DualMode：模式状态(html/onlyoffice) + 切换按钮 + localStorage持久化
    - _Requirements: 4.4, 4.6_

- [ ] 5. 实现Vue子组件（6个sheet）
  - [ ] 5.1 创建 `g13-fair-value-changes/G13TabProcedure.vue`（G13A程序表）
    - 复用a-program-console（23行×10列）
    - GtVoucherSamplingEngine集成（dialog, accountCode='6101'）
    - useCutoffAutoSampling集成（accountCode='6101', days=5）
    - selfLoad逻辑（bundle内嵌场景htmlData为null时自加载）
    - _Requirements: 2.1_

  - [ ] 5.2 创建 `g13-fair-value-changes/G13TabAdjudication.vue`（G13-1审定表35行×11列）
    - 按金融资产/负债类型分组（交易性金融资产FV变动/交易性金融负债FV变动/指定以FV计量的金融资产变动/衍生金融工具FV变动/其他/合计）
    - 列结构：项目|本期(未审|调整|审定)|上期(未审|调整|审定)|变动额|变动率|原因分析|索引
    - 损益类公式：审定=未审+调整；变动额=本期审定-上期审定；变动率=(本期-上期)/|上期|
    - trial_balance取数(6101) → EventBus publish `substantive:adjudicated`(accountCode='6101')
    - |变动率|>20%橙色高亮+原因分析必填验证
    - GtIndexChip + inject openReviewDialog + AI按钮(adjudication-analysis)
    - UI铁律：13px字体/公式列虚线下划线+cursor:help+tooltip/min-width自适应
    - _Requirements: 2.2, 2.3, 2.4, 2.5_

  - [ ] 5.3 创建 `g13-fair-value-changes/G13TabDetail.vue`（G13-2明细表34行×12列）
    - 列结构：金融工具名称|所属科目(G1/G8/G9/G10下拉)|金融工具类型|期初FV|期末FV|FV变动(公式)|本期未审|调整数|审定数(公式)|源科目索引|交叉验证结论(下拉)|备注
    - 公式列：FV变动=期末-期初；审定=未审+调整
    - 差异检测：FV变动≠审定数 → 红色高亮"FV变动与审定数不一致"
    - 按所属科目分组小计+总计
    - 动态行增删(弹ElMessageBox.prompt输入金融工具名称) + 导入导出
    - GtIndexChip(sourceIndex跳转源科目) + 交叉验证结论下拉(consistent/inconsistent/pending)
    - UI铁律 + inject openReviewDialog
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ] 5.4 创建 `g13-fair-value-changes/G13TabAdjustment.vue`（G13-3调整分录22行×10列）
    - 标准AJE/RJE列：序号|类型(AJE/RJE)|日期|摘要|科目编码|科目名称|借方|贷方|编制人|备注
    - 借贷平衡校验：isDebitCreditBalanced → 不平衡红色提示
    - 回写G13-1审定表adjustment列（AJE+RJE汇总）
    - 动态行增删 + 导入导出
    - _Requirements: 4.1_

  - [ ] 5.5 创建 `g13-fair-value-changes/G13TabDisclosureListed.vue` + `G13TabDisclosureSOE.vue`（附注披露）
    - 上市公司附注(18行×5列) + 国企附注(17行×5列)
    - EventBus subscribe `substantive:adjudicated`(accountCode='6101') → 刷新审定数
    - EventBus publish `disclosure:note-text-updated`(accountCode='6101') → 联动附注模块
    - AI辅助按钮(fv-change-conclusion) + section标题行右侧
    - mounted时主动拉取最新审定数（非纯被动监听）
    - _Requirements: 2.6_

- [ ] 6. 实现后端4个py文件
  - [ ] 6.1 创建后端render策略 + service
    - `_g13_fair_value_changes.py`：render策略函数 render_g13_fair_value_changes + 注册RENDERER_DISPATCH['g13-fair-value-changes']
    - `_g13_fair_value_changes_service.py`：G13FairValueChangesService（get_trial_balance_data/save_adjudication/validate_formulas）
    - _Requirements: 1.3, 4.2_

  - [ ] 6.2 创建后端导入导出 + AI端点
    - `_g13_fair_value_changes_import_export.py`：6端点(export-template/export-data/import-data × G13-2/G13-3) + RFC5987中文文件名编码
    - `_g13_fair_value_changes_ai.py`：2个AI section端点(adjudication-analysis/fv-change-conclusion) + 30秒超时
    - _Requirements: 4.4, 4.5_

- [ ] 7. 跨模块联动集成（5大集成）
  - [ ] 7.1 五大集成接入验证
    - ①版本链：主入口useVersionTrail(autoSnapshot on save + "版本历史"按钮)
    - ②抽凭引擎：G13A程序表GtVoucherSamplingEngine(dialog, accountCode='6101')
    - ③截止自动提取：G13A useCutoffAutoSampling(accountCode='6101', days=5)
    - ④附注EventBus：G13-1 publish + 附注 subscribe/publish（双向联动）
    - ⑤复核对话：主入口provide openReviewDialog → 子组件inject → section标题栏右侧按钮
    - _Requirements: 4.3_

- [ ] 8. 最终验证
  - [ ]* 8.1 编写集成测试
    - sheetName分发正确性（6个sheet→对应子组件 + 未知sheet→OnlyOffice fallback）
    - 损益类公式链（TB取数6101 → 未审+调整=审定 → EventBus → 附注刷新）
    - FV变动公式（期末-期初）+ 差异检测（FV变动≠审定数→红色）
    - 变动率公式（方向性+除零null+>20%橙色高亮）
    - 借贷平衡（G13-3 AJE/RJE → 回写G13-1）
    - G13-2明细按所属科目分组小计+总计
    - 导入导出round-trip（2张表G13-2/G13-3）
    - 交叉验证结论下拉+GtIndexChip跳转
    - _Requirements: 全部_

  - [ ] 8.2 Final checkpoint
    - Ensure all tests pass, ask the user if questions arise.

## Notes

- G13是损益类科目6101：本期发生额=贷方-借方（净收益为贷方）
- G循环中最简洁科目之一：仅6个有效sheet，无凭证检查表，无虚拟滚动需求
- 最大sheet仅35行×11列，无需宽表拆分
- 交叉验证核心：G13-2明细与G1/G8/G9/G10各科目公允价值变动数据勾稽
- 公式引擎仅5个纯函数+parseNum，计算逻辑简单
- 导入导出仅2张动态行表格（G13-2/G13-3）
- AI辅助仅2个section（adjudication-analysis / fv-change-conclusion）
- 五大集成（版本链/抽凭/截止/附注EventBus/复核），无OCR（无凭证检查表）
- 动态行新增需弹ElMessageBox.prompt输入金融工具名称
- Tasks marked with `*` are optional and can be skipped for faster MVP
- Property tests validate universal correctness properties (6 PBT)
- Checkpoints ensure incremental validation

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "2.7"] },
    { "id": 3, "tasks": ["4.1", "4.2", "6.1", "6.2"] },
    { "id": 4, "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5"] },
    { "id": 5, "tasks": ["7.1", "8.1"] }
  ]
}
```
