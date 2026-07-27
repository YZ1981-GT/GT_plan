# J 职工薪酬循环

J 循环覆盖职工薪酬三大块：**短期薪酬 + 离职后福利 + 辞退福利（J1）**、
**设定受益计划（J2）**、**股份支付（J3）**。3 个科目包 = 3 个 componentType。

## 组成

| 元素 | 科目 | componentType | 后端 render 策略 | 目录结构 |
|---|---|---|---|---|
| J1 应付职工薪酬 | 2211 | `j1-employee-compensation` | `_j1_employee_compensation` | core / analysis / inspection / handbooks |
| J2 设定受益计划 | 2221 | `j2-defined-benefit-plan` | `_j2_defined_benefit_plan` | 扁平（`J2Tab*.vue`）+ handbooks |
| J3 股份支付 | 4004 等（权益工具）/ 费用侧计入各成本费用 | `j3-share-based-payment` | `_j3_share_based_payment` | core / handbooks / __tests__ |

## J1 应付职工薪酬（2211）— 循环主体

| 目录 | 组件 |
|---|---|
| `core/` | `J1TabAdjudication`（审定表）/ `J1TabDetail` + `J1DetailSection`（明细，三分区：短期薪酬 / 离职后福利 / 辞退福利）/ `J1TabAdjustment` / `J1TabDisclosureListed` / `J1TabDisclosureSoe` / `J1TabIndex` |
| `analysis/` | `J1TabMonthlyAnalysis` + `MonthlyBlockTable`（月度分析）/ `J1TabIndustryCompare`（行业对比） |
| `inspection/` | `J1TabAccrualCheck` + `AccrualTable`（计提检查）/ `J1TabAllocationCheck`（分配检查）/ `J1TabGeneralCheck`（综合检查）/ `J1TabNonMonetaryCheck`（非货币性福利）/ `J1TabSeveranceCheck`（辞退福利）/ `J1VoucherCard`（凭证卡片视图） |
| 其他 | `J1TabIpoTips`（IPO 关注要点）/ `J1PreparationHandbookDialog` |

**审定表三分区**（对齐 CAS9 与源模板）：短期薪酬（工资/社保/公积金/工会经费/职工教育经费）、
离职后福利（养老/失业/年金），辞退福利。附注 **五、40（上市）/ 八、40（国企）**。

## J2 设定受益计划（2221）

扁平结构（无子目录），7 个 Tab：审定表 J2-1 / 明细 J2-2 / 调整 J2-3 / 计提检查 J2-4 /
附注上市 / 附注国企 / 目录。

**CAS9 六要素**是核心：期初 → 当期损益（当期服务成本 / 过去服务成本 / 结算利得 / 利息净额）→
其他综合收益（重新计量：精算利得 / 计划资产回报 / 资产上限影响）→ 其他变动 → 期末。
另有计划资产公允价值、精算假设、敏感性分析、未折现到期分析。

## J3 股份支付（`j3-share-based-payment`）

| 组件 | 作用 |
|---|---|
| `J3TabDetail` + `J3PlanDialog` | 股份支付情况表 J3-1（14 列）+ **引导式录入弹窗**（5 分组卡片 + 实时分析面板） |
| `J3TabCheck` + `J3VariationDialog` | 股份支付检查表 J3-2（19 列增减变动测算）+ 引导弹窗（测算 vs 账面差异实时勾稽） |
| `J3TabIpoFocus` | IPO 股份支付关注要点 |
| `J3TabIndex` | 目录 |
| `__tests__/` | `useJ3Engines` / `useJ3OptionPricingEngine.pbt`（期权定价 PBT）/ e2e |

**CAS11 要点**：权益结算 vs 现金结算（现金结算需每期重新计量）、授予日/等待期/行权条件、
公允价值确定方法（B-S 模型等，`useJ3OptionPricingEngine`）、专家利用（S12/S12A）。

## 三条主脉

1. **计提 → 分配 → 支付**：J1 计提（贷 2211）→ 分配到成本费用（F5/K8/K9/I6/H 在建）→ 支付（借 2211 / 贷 E1）
2. **精算 → OCI/损益**：J2 六要素分流（当期损益 vs 其他综合收益重新计量）→ M9 其他综合收益
3. **股份支付 → 权益或负债**：J3 权益结算（贷 4004 其他权益工具/资本公积）vs 现金结算（贷应付职工薪酬），
   费用侧计入各成本费用科目
