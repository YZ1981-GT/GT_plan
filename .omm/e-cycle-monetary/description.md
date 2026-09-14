# E 货币资金循环

E 循环只有一个科目包 **E1 货币资金**，但它是**单科目 sheet 数最多**的底稿之一（20+ 个 sheet），
也是平台若干全局机制的首个落地地：四表取数、金额显示偏好（千分符/两位小数/单位）、公式管理 surfacing、双模式统一封装。

## 组成

| 元素 | 内容 | componentType |
|---|---|---|
| E0 函证 | 银行函证，**复用 D0 的 `confirmation-*` 组件族** | `confirmation-*` |
| E1 货币资金 | 1001 库存现金 / 1002 银行存款 / 1012 其他货币资金 | `e1-monetary-fund` |

前端 `GtE1MonetaryFund.vue`（主入口，按 `currentSheet` 用 `v-if` 分发），后端 `_e1_monetary_fund.py`。

## Sheet 映射（从主入口 `v-if` 分发链核实）

| sheet | Tab 组件 | 说明 |
|---|---|---|
| 底稿目录 | `E1TabDirectory` | 目录卡 + 结论看板 + 4 阶段泳道 + 本循环 grid |
| E1-1 | `E1TabAdjudication` | 审定表（回写 TB 三科目） |
| E1-2 | `E1TabCashDetail` | 现金明细表 |
| E1-3 | `E1TabBankDetail` | 银行存款明细（双 variant：仅人民币 / 人民币及外币） |
| E1-4 | `E1TabDigitalCurrency` | 数字货币明细 |
| E1-5 | `E1TabAdjustment` | 调整分录 |
| E1-6 | `E1TabReconciliation` | 银行存款余额调节表 |
| E1-7 / E1-8 | `E1TabCashCount`（variant rmb / fx） | 库存现金盘点（人民币 / 外币） |
| E1-9 | `E1TabCertificateCount` | 银行存单盘点 |
| E1-10 | `E1TabAccountList` | 银行账户核对（账户清单） |
| E1-11 | `E1TabAccountCommitment` | 账户完整性承诺书 |
| E1-14 | `E1TabAnalysis` | 分析表 |
| E1-15 | `E1TabInterestAnalysis` | 利息收入月度分析 |
| E1-18 / E1-19 | `E1TabCreditReport`（variant query / check） | 企业信用报告查询 / 核对 |
| E1-20 | `E1TabAccruedInterest` | 应计利息测算 |
| E1-21 / E1-22 | `E1TabCutoffTest`（variant bank / other） | 银行存款 / 其他货币资金截止测试 |
| E1-23 | `E1TabLargeCheck` | 收支检查情况表（凭证级 15 列） |
| E1-26~E1-32 | `E1TabIpoSpecial` 承接 | IPO / 舞弊应对专项族 |
| 附注（上市/国企） | `E1TabDisclosure` | 五、1 / 八、1 |

IPO / 舞弊族已核实的具体表：**E1-26** 现金交易分析、**E1-29** 银行账户分析、**E1-30** 存款规模与利息收入匹配性分析、**E1-31** 银行流水双向核对、**E1-32** 董监高关键岗位及其他关联方资金流水核查（对应 `E1TabCashTxnAnalysis` / `E1TabBankAccountAnalysis` / `E1TabDepositInterestDaily` / `E1TabBankFlowReconcile` / `E1TabKeyPersonFlow`）。E1-27 / E1-28 本轮未核实。

## 与 D 循环的结构差异

- **多变体同组件**：E1-3 / E1-7·E1-8 / E1-18·E1-19 / E1-21·E1-22 都是一个组件按 `variant` prop 服务两个 sheet
- **多科目回写**：审定表一次回写 1001 / 1002 / 1012 三个科目（D 循环各科目基本一对一）
- **OCR 密集**：账户清单 / 承诺书 / 征信报告 / 截止测试 / 大额收支 / 关键人流水 / 银行流水各有专用 OCR 确认弹窗（`E1*OcrConfirmDialog.vue` 共 7 个）
