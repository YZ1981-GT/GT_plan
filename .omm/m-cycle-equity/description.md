# M 所有者权益循环

M 循环覆盖所有者权益全部科目 + 应付股利。M1~M10 共 **10 个 componentType**，前端目录 `m1/`~`m10/`。
是全平台钩稽关系最密的循环（利润分配枢纽 M6 连接损益结转、盈余公积、股利分配）。

## 组成

| 元素 | 科目 | 性质 | componentType | 后端 render 策略 |
|---|---|---|---|---|
| M1 应付股利 | 2232 | 负债 | `m1-dividends-payable` | `_m1_dividends_payable` |
| M2 实收资本/股本 | 4001 | 权益 | `m2-paid-in-capital` | `_m2_paid_in_capital` |
| M3 库存股 | 4002 ⚠(备抵借方) | 权益备抵 | `m3-treasury-stock` | `_m3_treasury_stock` |
| M4 资本公积 | 4002 ⚠(与M3同码) | 权益 | `m4-capital-reserve` | `_m4_capital_reserve` |
| M5 盈余公积 | 4101 | 权益 | `m5-surplus-reserve` | `_m5_surplus_reserve` |
| M6 利润分配-未分配利润 | 4104 | 权益（**枢纽**）| `m6-retained-earnings` | `_m6_retained_earnings` |
| M7 专项储备 | 4201 | 权益 | `m7-special-reserve` | `_m7_special_reserve` |
| M8 一般风险准备 | 4104 ⚠(与M6同码，金融专属)| 权益 | `m8-general-risk-reserve` | `_m8_general_risk_reserve` |
| M9 其他综合收益 | 4103 | 权益 | `m9-other-comprehensive-income` | `_m9_other_comprehensive_income` |
| M10 其他权益工具 | 4003 | 权益 | `m10-other-equity-instruments` | `_m10_other_equity_instruments` |

⚠ 见 `concern.md`：M3/M4 都用 4002、M6/M8 都用 4104。

## 🔴 科目方向铁律

- 权益类多为**贷方**（4001/4003/4101/4103/4104/4201）：期末 = 期初 + 贷 − 借
- **M3 库存股是权益备抵借方**（4002）：期末 = 期初 + 借 − 贷（方向特殊）

## M6 利润分配是枢纽

M6（未分配利润 4104）连接：
1. **净利润结转**：本年利润（4103 本年利润科目）→ 未分配利润
2. **盈余公积提取**：法定 10% + 任意 → M5（4101）
3. **利润分配**：宣告股利 → M1 应付股利（2232）
4. **一般风险准备**（金融企业）→ M8（也用 4104）

利润分配表的顺序（净利润 → 提取盈余公积 → 提取一般风险准备 → 分配股利 → 期末未分配）是 M 循环的核心勾稽链。

## OCI 与其他权益工具

- **M9 其他综合收益（4103）**：来源 G6 其他债权投资 FVOCI 变动、G8 权益工具投资 FVOCI 变动、
  J2 设定受益计划重新计量、外币报表折算差额；处置时按准则决定是否转损益
- **M10 其他权益工具（4003）**：优先股/永续债/可转换债券权益成分；J3 股份支付权益结算也可能计入

## 统一骨架

MxA 程序表 → Mx-1 审定表（权益变动表口径，回写各科目）→ Mx-2 明细 → 调整 → 附注上市/国企 → 目录
