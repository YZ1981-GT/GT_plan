# G 投资与金融资产循环

G 循环覆盖金融资产 / 金融负债 / 长期股权投资 / 投资相关损益，是**入口数量最多的循环**：
G0~G14 共 14 个科目包，因 G4/G6/G7 各自再拆分，前端共 **20 个 componentType**、后端 20 个 render 策略。

## 组成

| 元素 | 科目 | componentType | 附注（上市 / 国企） |
|---|---|---|---|
| G0 函证 | — | 复用 D0 `confirmation-*`（另有 `alternativeG06` / `diffSecurities`） | — |
| G1 交易性金融资产 | `G1_ACCOUNT_CODE='1501'` ⚠ | `g1-trading-financial-assets` | 五、2 交易性 / 五、3 衍生（八、2 / 八、3） |
| G2 应收利息 | 1132 | `g2-interest-receivable` | 五、8 / 八、9（**并入其他应收款节**） |
| G3 应收股利 | 1131 | `g3-dividend-receivable` | （见 `g3NoteSectionMap`） |
| G4 债权投资 | `G4_ACCOUNT_CODE='1501'` ⚠ / 减值 `1502` ⚠ | `g4-bond-investment-main` / `-sppi` / `-ecl` | — |
| G5 长期应收款 | 1531 | `g5-long-term-receivable` | — |
| G6 其他债权投资 | `G6_ACCOUNT_CODE='1503'` ⚠ | `g6-other-bond-investment-main` / `-sppi` / `-ecl` | — |
| G7 长期股权投资 | 1511 | `g7-long-term-equity-main` / `-method` / `-subsidiary` | 五、18 / 八、18 |
| G8 其他权益工具投资 | `G8_ACCOUNT_CODE='1503'` ⚠（与 G6 同码） | `g8-other-equity-instruments` | 五、19 / 八、N |
| G9 其他非流动金融资产 | 1519 | `g9-other-noncurrent-financial` | 五、20 / 八、N |
| G10 交易性金融负债 | 2101 | `g10-trading-financial-liabilities` | 五、34 交易性 / 五、35 衍生（八、34 / 八、35） |
| G11 投资收益 | 6111（损益） | `g11-investment-income` | 五、69 / 八、70 |
| G12 净敞口套期收益 | 6103（损益） | `g12-net-hedge-gains` | 五、70 / 八、71 |
| G13 公允价值变动收益 | 6101（损益） | `g13-fair-value-changes` | 三、公允价值变动收益 / 八、72 |
| G14 信用减值损失 | 6702（损益） | `g14-credit-impairment-loss` | 三、信用减值损失 / 八、73 |

⚠ = 与平台标准科目表不一致或与其他科目撞码，见 `concern.md`。

## 为什么 G4/G6/G7 要拆

- **G4 债权投资 / G6 其他债权投资**：CAS22 金融工具分类要求三段独立工作量 ——
  **main**（审定/明细/摊余成本计量）、**sppi**（合同现金流量特征测试 + 业务模式）、**ecl**（三阶段预期信用损失）。
  三段各自 sheet 数量都不小，且 sppi/ecl 的结论要回流 main。
- **G7 长期股权投资**：**main**（审定/明细/披露）、**method**（权益法：计算/减值/被投资单位信息）、
  **subsidiary**（子公司：初始计量/后续计量/处置/凭证），成本法与权益法审计逻辑差异大。

## 三条主脉

1. **分类 → 计量 → 减值**：SPPI/业务模式判定 → 摊余成本或公允价值计量 → ECL 三阶段（G4/G6）或减值测试（G7/G8）
2. **资产 → 损益**：G1/G9/G10 公允变动 → G13 公允价值变动收益（6101）；G4/G6/G7 投资收益 → G11（6111）；
   G4/G6/G5 信用减值 → G14 信用减值损失（6702）
3. **权益 → OCI**：G6 其他债权投资 / G8 其他权益工具投资的公允变动进 **其他综合收益（4002）**，
   处置时按准则决定是否结转留存收益（M 循环权益）
