# Implementation Plan: G6 其他债权投资(main组)底稿专属HTML精美组件

## Overview

实现G6其他债权投资(main组)专属组件 `g6-other-bond-investment-main`，覆盖8个sheet（G6A程序表/G6-1审定表/G6-2明细表/G6-3坏账准备/G6-4调整分录/附注上市/附注国企/底稿目录）。核心特色：77行8层审定表(FVOCI-Debt双重计量)+33列3区段Tab明细表+137行虚拟滚动附注+ECL公式链(5个纯函数)+借方科目公式。五大集成（版本链/抽凭/截止/附注EventBus/复核），3张表导入导出，2个AI section，无OCR无凭证检查。

## Tasks

- [ ] 1. 公式引擎与核心composable
  - [ ] 1.1 实现 useG6MainFormulaEngine.ts（10个纯函数+parseNum）
    - 实现 parseNum / calcDebitBalance / calcAdjustedAmount / calcSubtotal / calcEndingSubtotal / calcUnadjustedProvision / calcImpairmentAdjustment / calcAdjustedBookValue / calcChangeRate / isDebitCreditBalanced / calcReportAmount
    - 每个函数导出为纯函数，无副作用
    - _Requirements: 3.3, 5.2, 6.2, 7.2_

  - [ ]* 1.2 PBT: Property 1 — 借方余额公式
    - **Property 1: calcDebitBalance(opening, debit, credit) === opening + debit - credit**
    - fast-check numRuns:100, float(-1e9,1e9)
    - **Validates: Requirements 3.3, 7.2**

  - [ ]* 1.3 PBT: Property 2 — 审定数公式
    - **Property 2: calcAdjustedAmount(unadjusted, adjustment) === unadjusted + adjustment**
    - **Validates: Requirements 3.3, 7.2**

  - [ ]* 1.4 PBT: Property 3 — 余额小计(三要素加法)
    - **Property 3: calcSubtotal(cost, interestAdj, accruedInterest) === cost + interestAdj + accruedInterest**
    - **Validates: Requirements 3.1, 5.1, 7.2**

  - [ ]* 1.5 PBT: Property 4 — 期末小计公式
    - **Property 4: calcEndingSubtotal === openingSubtotal + increase - decrease + interestIncome**
    - **Validates: Requirements 5.2**

  - [ ]* 1.6 PBT: Property 5 — ECL公式链一致性
    - **Property 5: ⑧=③+⑥ === ⑦×②A 恒等式验证**
    - calcUnadjustedProvision + calcImpairmentAdjustment + 组合验证
    - **Validates: Requirements 6.2**

  - [ ]* 1.7 PBT: Property 6 — 变动率方向性与除零保护
    - **Property 6: calcChangeRate(0, any) === null; current>prior>0 → >0**
    - **Validates: Requirements 3.5, 7.2**

  - [ ]* 1.8 PBT: Property 7 — 借贷平衡恒等
    - **Property 7: isDebitCreditBalanced ↔ |SUM(debits)-SUM(credits)| < 0.01**
    - **Validates: Requirements 7.1, 7.2**

  - [ ]* 1.9 PBT: Property 8 — parseNum健壮性
    - **Property 8: parseNum(null/undefined/''/NaN) === 0; parseNum(n) === n**
    - **Validates: Requirements 7.2**

  - [ ] 1.10 实现 useG6MainFormData.ts（数据加载/保存/selfLoad/writebackTB）
    - selfLoad逻辑：htmlData为null时自动GET render-config
    - 保存时autoSnapshot + 自动重试3次(指数退避) + localStorage暂存
    - writebackTB: 保存后回写trial_balance审定数
    - _Requirements: 1.4, 3.3, 7.3_

  - [ ] 1.11 实现 useG6MainDualMode.ts（双模式OO切换+localStorage）
    - HTML↔OnlyOffice切换 + localStorage持久化偏好
    - _Requirements: 7.7_

  - [ ] 1.12 实现 useG6MainImportExport.ts（3张表导入导出composable）
    - 3张表(G6-2/G6-3/G6-4) × 3端点(export-template/export-data/import-data)
    - G6-2按3区段分sheet导出；G6-3按2区段分sheet导出
    - 使用axios(非fetch)确保Authorization header
    - _Requirements: 5.3, 6.3, 7.1, 7.4_

- [ ] 2. Checkpoint - 公式引擎与composable完成
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. 主入口与sheetName分发
  - [ ] 3.1 实现 GtG6OtherBondInvestmentMain.vue 主入口
    - sheetName prop → 正则提取编码 → v-if分发8个defineAsyncComponent
    - 未匹配 → OnlyOffice fallback（GtOnlyOfficeSheet）
    - provide openReviewDialog / useVersionTrail(autoSnapshot) / useG6MainDualMode
    - _Requirements: 1.1, 1.2, 1.4, 7.3, 7.7_

  - [ ] 3.2 注册四件套
    - htmlRendererRegistry注册 'g6-other-bond-investment-main'
    - wp_code_overrides.json 新增8条映射
    - VALID_COMPONENT_TYPES 新增
    - RENDERER_DISPATCH 注册 render_g6_other_bond_investment_main
    - _Requirements: 1.1, 1.3_

- [ ] 4. G6A程序表 + G6-1审定表
  - [ ] 4.1 实现 G6TabProcedure.vue（G6A程序表）
    - 复用 a-program-console（34行×10列）
    - selfLoad逻辑 + GtVoucherSamplingEngine(抽凭引擎,account='1503') + useCutoffAutoSampling(截止±5天)
    - _Requirements: 2.1, 7.3_

  - [ ] 4.2 实现 G6TabAdjudication.vue（G6-1审定表 77行×11列）
    - 8层多层结构(成本/利息调整/应计利息/小计/公允价值变动/减值/报表数/重分类)
    - 分组折叠(expanded状态) + 虚拟滚动(77行)
    - 方法论上下文(琥珀色左边线+浅黄背景)：FVOCI-Debt计量特征
    - 公式引用：calcAdjustedAmount / calcSubtotal / calcReportAmount / calcChangeRate
    - 四小计=一+二+三；七报表列示数=四+五-六
    - 底部TB取数(1503)比对 + 差异红色>0.01
    - |变动率|>20%橙色高亮+原因分析必填
    - EventBus publish 'substantive:adjudicated' {accountCode:'1503', adjudicatedAmount}
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 7.6_

  - [ ]* 4.3 单元测试: G6-1审定表分组折叠与公式计算
    - 验证8层分组展开/收起状态正确
    - 验证calcReportAmount(subtotal, fvChange, impairment) = subtotal+fvChange-impairment
    - 验证|changeRate|>0.2时reasonAnalysis必填校验
    - _Requirements: 3.1, 3.4, 3.5_

- [ ] 5. G6-2明细表 + G6-3坏账准备
  - [ ] 5.1 实现 G6TabDetail.vue（G6-2明细表 33列→3区段Tab）
    - Tab1基础信息(10列) / Tab2期初+变动(12列) / Tab3期末+审定(11列)
    - 行同步：Tab切换保持行索引
    - 期初小计公式 calcSubtotal / 期末小计公式 calcEndingSubtotal
    - 动态行增删(ElMessageBox.prompt输入项目名称)
    - 底部合计行 + GtIndexChip索引
    - 导入导出el-dropdown(复用useG6MainImportExport)
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ] 5.2 实现 G6TabBadDebtDetail.vue（G6-3坏账准备 20列→2区段Tab）
    - Tab1未审+调整(10列) / Tab2审定数(10列)
    - ECL公式链：calcUnadjustedProvision/calcImpairmentAdjustment/calcAdjustedBookValue
    - Stage分组(Stage1/Stage2/Stage3/单项) + 按Stage小计+总计行
    - 方法论上下文(琥珀色左边线)：ECL公式链推导
    - 行同步 + 动态行增删 + 导入导出
    - 损失率超出[0,1]红框高亮+阻止保存
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 5.3 单元测试: ECL公式链与区段Tab行同步
    - 验证⑧=⑦×②A恒等式在边界值(rate=0, rate=1, adj=0)下成立
    - 验证Tab切换后行索引不变
    - 验证G6-2导出3sheet / G6-3导出2sheet
    - _Requirements: 5.2, 5.3, 6.2, 6.3_

- [ ] 6. Checkpoint - 核心sheet完成
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. G6-4调整分录 + 附注 + 底稿目录
  - [ ] 7.1 实现 G6TabAdjustment.vue（G6-4调整分录 23行×10列）
    - AJE/RJE分录类型 + 借贷平衡实时校验(isDebitCreditBalanced)
    - 不平衡时红色差额提示+阻止保存
    - 汇总回写G6-1(adjustment列) + 动态行增删 + 导入导出
    - _Requirements: 7.1, 7.4_

  - [ ] 7.2 实现 G6TabDisclosureListed.vue（附注上市 137行×16列）
    - 虚拟滚动(137行必须) + 分section结构
    - EventBus subscribe 'substantive:adjudicated'(accountCode='1503')刷新
    - EventBus publish 'disclosure:note-text-updated'
    - AI辅助按钮(每个文本区section标题右侧)
    - _Requirements: 4.1, 4.3, 7.5, 7.6_

  - [ ] 7.3 实现 G6TabDisclosureSOE.vue（附注国企 69行×6列）
    - 虚拟滚动 + EventBus subscribe/publish + AI辅助
    - _Requirements: 4.2, 4.3, 7.5, 7.6_

  - [ ] 7.4 实现 G6TabDirectory.vue（底稿目录 29行×8列）
    - 静态目录页渲染
    - _Requirements: 1.1_

- [ ] 8. 后端服务层
  - [ ] 8.1 实现 _g6_other_bond_investment_main.py（render策略+RENDERER_DISPATCH注册）
    - render_g6_other_bond_investment_main函数
    - 返回componentType='g6-other-bond-investment-main' + sheets配置
    - _Requirements: 1.1, 1.3_

  - [ ] 8.2 实现 _g6_other_bond_investment_main_service.py（业务逻辑）
    - G6OtherBondInvestmentMainService类
    - get_trial_balance_data(project_id, year): 查TB科目1503
    - save_adjudication(wp_id, data): 保存审定数据+EventBus publish
    - validate_formulas(data): 公式验证(借方余额/ECL链/借贷平衡)
    - _Requirements: 3.3, 6.2, 7.1, 7.2_

  - [ ] 8.3 实现 _g6_other_bond_investment_main_import_export.py（9端点）
    - 3张表(G6-2/G6-3/G6-4) × 3端点(export-template/export-data/import-data)
    - G6-2宽表按3区段分sheet导出 / G6-3按2区段分sheet导出
    - multipart/form-data上传 + 422列格式校验
    - StreamingResponse中文文件名RFC5987编码
    - _Requirements: 5.3, 6.3, 7.1, 7.4_

  - [ ] 8.4 实现 _g6_other_bond_investment_main_ai.py（AI生成2 section）
    - POST /api/workpapers/{wp_id}/g6-main/ai/{section}
    - section: adjudication-analysis / disclosure-text
    - _Requirements: 7.5_

- [ ] 9. 后端PBT与单元测试
  - [ ]* 9.1 后端PBT: 公式验证(hypothesis)
    - Property 1~8 后端Python验证（与前端公式引擎一致性）
    - hypothesis max_examples=5
    - **Validates: Requirements 3.3, 5.2, 6.2, 7.2**

  - [ ]* 9.2 单元测试: service + renderer + import-export
    - 测试render策略返回正确componentType
    - 测试TB取数科目1503过滤
    - 测试导入数据列格式校验(422错误)
    - 测试ECL公式链边界值(rate=0/1)
    - _Requirements: 1.1, 3.3, 6.2, 7.4_

- [ ] 10. 集成联动与最终验收
  - [ ] 10.1 五大集成接入验证
    - 版本链: useVersionTrail主入口 + autoSnapshot
    - 抽凭: G6A GtVoucherSamplingEngine dialog(account='1503')
    - 截止: useCutoffAutoSampling(±5天)
    - 附注EventBus: subscribe/publish双向联动
    - 复核: provide/inject openReviewDialog → 子组件section标题栏按钮
    - _Requirements: 7.3_

  - [ ]* 10.2 集成测试: API端点(render + import-export + AI)
    - 测试render-config端点返回8 sheets
    - 测试3张表×3端点=9导入导出端点
    - 测试2 AI section端点
    - _Requirements: 1.1, 7.4, 7.5_

- [ ] 11. Final checkpoint - 全部完成
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 前端使用 TypeScript + Vue 3 Composition API + Element Plus
- 后端使用 Python + FastAPI + asyncpg
- PBT前端: vitest + fast-check (numRuns:100) / 后端: pytest + hypothesis (max_examples=5)
- 公式引擎10个纯函数为核心，前后端需保持一致
- 77行审定表8层结构为本组最复杂特色，虚拟滚动+分组折叠为必要性能优化
- 137行附注(上市)为全项目最长附注表，虚拟滚动为强制要求
- ECL公式链(G6-3)需验证⑧=⑦×②A恒等式
- 本组无OCR无凭证检查（在ECL组G6-15）
- 导入导出必须用axios(非fetch)避免401

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9", "1.10", "1.11", "1.12"] },
    { "id": 2, "tasks": ["3.1", "3.2"] },
    { "id": 3, "tasks": ["4.1", "4.2", "7.4", "8.1"] },
    { "id": 4, "tasks": ["4.3", "5.1", "5.2", "7.1", "8.2"] },
    { "id": 5, "tasks": ["5.3", "7.2", "7.3", "8.3", "8.4"] },
    { "id": 6, "tasks": ["9.1", "9.2", "10.1"] },
    { "id": 7, "tasks": ["10.2"] }
  ]
}
```
