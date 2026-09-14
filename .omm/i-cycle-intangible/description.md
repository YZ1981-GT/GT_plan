# I 无形资产与其他长期资产循环

I 循环覆盖无形资产及其"衍生科目"（开发支出 / 商誉 / 长期待摊 / 其他非流动资产 / 研发费用），
6 个科目包 = **6 个 componentType**，前端目录 `i1/`~`i6/`。

## 组成

| 元素 | 科目 | componentType | 后端 render 策略 | 子目录 |
|---|---|---|---|---|
| I1 无形资产 | 1701 原值 / 1702 累计摊销 / 1703 减值准备 | `i1-intangible-assets` | `_i1_intangible_assets` | core / amortization / impairment / inspection |
| I2 开发支出 | 1717 | `i2-development-expenditure` | `_i2_development_expenditure` | core / cutoff / impairment / inspection |
| I3 商誉 | 1711 | `i3-goodwill` | `_i3_goodwill` | core / impairment / shared |
| I4 长期待摊费用 | 1801 | `i4-long-term-prepaid` | `_i4_long_term_prepaid` | core / amortization / shared |
| I5 其他非流动资产 | 1911 | `i5-other-noncurrent-assets` | `_i5_other_noncurrent_assets` | core / shared |
| I6 研发费用 | 6602（损益，管理费用下研发） | `i6-research-development-expense` | `_i6_research_development_expense` | core / cutoff |

## I 循环的主脉：研发支出的三条出口

研发投入按 CAS6 分流，是 I 循环最核心的审计逻辑：

1. **费用化** → **I6 研发费用（6602）**：研究阶段支出，当期损益
2. **资本化归集** → **I2 开发支出（1717）**：开发阶段满足五条件的支出，在建
3. **达可使用状态 → 转入** → **I1 无形资产（1701）**：形成资产后摊销

I2 的核心争议点是**资本化时点与五条件判定**（技术可行性 / 使用或出售意图 / 有用性 / 资源支持 / 支出可可靠计量），
且 I2/I6 都有 `cutoff/` 截止测试（研发支出的期间归属最易操纵）。

## 其余三个科目的定位

- **I3 商誉（1711）**：非同控合并产生，**不摊销只减值**（CAS8 + 资产组/资产组组合 + 业绩承诺）；来源是 G7-13 投资成本测试的正差额
- **I4 长期待摊费用（1801）**：装修费 / 开办费 / 租赁改良 / 技术转让费 / 其他（`useI4Adjudication.DEFAULT_CATEGORIES`），按期限摊销
- **I5 其他非流动资产（1911）**：兜底科目（预付设备款 / 长期预付租金 / 待处理资产等），
  审定表是**三层矩阵（原值 / 减值 / 净值）** + 期初账项/重分类调整；内置 10 类 + 从 D7/M12/G2-13 等带入

## 统一骨架（与 H 循环同款）

IxA 程序表 → Ix-1 审定表（原值/摊销/减值三段）→ Ix-2 明细 → 摊销测算 → 减值测试 →
增加减少检查（抽凭）→ 调整分录 → 附注上市/国企 → 目录页 + `handbooks/`
