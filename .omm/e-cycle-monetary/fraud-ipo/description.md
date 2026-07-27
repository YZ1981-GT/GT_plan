# IPO / 舞弊应对专项族（E1-26 ~ E1-32）

主入口对 `ipoSheetCode` 统一分发到 `E1TabIpoSpecial`（外壳 `E1IpoSheetChrome` 提供统一页头/说明）。
这一族的共同目的：**识别资金体外循环、账外账户、关联方资金占用、虚假回款**。

## 已核实的具体表（来自各 Tab 组件文件头注释）

| sheet | 组件 | 内容 |
|---|---|---|
| E1-26 | `E1TabCashTxnAnalysis` | 现金交易分析表：（一）月度总体（二）合理性（三）金额分布（四）客户/供应商概要 + 说明/结论 |
| E1-29 | `E1TabBankAccountAnalysis` | 银行账户分析：（一）清单+开户地（二）多年指标（三）（四）说明结论 + 红旗提示 |
| E1-30 | `E1TabDepositInterestDaily` | 存款规模与利息收入匹配性：日余额 × 年利率 / 360，按月分页 |
| E1-31 | `E1TabBankFlowReconcile` | 银行流水双向核对：（一）月度汇总（二）账→流（三）流→账 + OCR 流水 + 覆盖率/结论 |
| E1-32 | `E1TabKeyPersonFlow` | 董监高关键岗位及其他关联方资金流水核查 |

**E1-27 / E1-28 本轮未核实**（`E1TabIpoSpecial` 的内部分发实现也未逐一查）。

## OCR 是这一族的主要输入

`E1KeyPersonFlowOcrConfirmDialog` / `E1StatementOcrConfirmDialog` 等：银行流水、个人账户流水多为 PDF/扫描件，
靠 OCR 识别后确认回填。**注意**：这类长文档解析是当前 RapidOCR 的弱项（见 memory 里 Unlimited-OCR 评估）。

## 与其他表的联动

- E1-29 消费 E1-10 账户清单 + 征信报告 → 账外账户红旗
- E1-31 双向核对（账→流 / 流→账）的覆盖率是完整性证据，与 E1-6 余额调节互补
- E1-30 的测算利息 ↔ E1-15 账面利息收入（同为流量口径）
- 红旗结论回流主入口全局告警与 B50 风险评估（舞弊风险因素）
