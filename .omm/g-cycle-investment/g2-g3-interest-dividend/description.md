# G2 应收利息（1132）/ G3 应收股利（1131）

两个科目都是**扁平单目录**（无子目录，只有 `handbooks/` + 一批 `G{n}Tab*.vue`），
且**都没有独立附注节**：作为行并入 **K1 其他应收款 五、8 / 八、9**。

## G2 应收利息（`g2-interest-receivable`）

| 组件 | 作用 |
|---|---|
| `G2TabAdjudication` | 审定表（TB 1132） |
| `G2TabDetail` | 明细 |
| `G2TabInterestCalc` | 利息测算（重算应计利息） |
| `G2TabOverdueCheck` | 逾期利息检查 |
| `G2TabECLCalc` / `G2TabBadDebtDetail` | 预期信用损失测算 / 坏账准备明细 |
| `G2TabVoucherCheck` | 凭证检查 |
| `G2TabAdjustment` | 调整分录 |
| `G2TabDisclosureListed` / `G2TabDisclosureSOE` | 披露（推 五、8 / 八、9 的应收利息分类行 + 重要逾期利息表 + 坏账三阶段） |
| `G2TabIndex` | 目录页 |

`g2NoteSectionMap`：`G2_ACCOUNT_CODE='1132'`，`noteSectionListed='五、8'` / `noteSectionSoe='八、9'`。
`buildG2SyncPayload` 推三张子表（应收利息分类 / 重要逾期利息 / 坏账准备计提三阶段），已登记覆盖率守卫。

## G3 应收股利（`g3-dividend-receivable`）

| 组件 | 作用 |
|---|---|
| `G3TabAdjudication` / `G3TabDetail` / `G3TabAdjustment` | 审定 / 明细 / 调整 |
| `G3TabCalcCheck` | 股利测算检查（宣告分配 vs 应收，可产生 AJE，对方科目 1131） |
| `G3TabOverdueCheck` | 长期未收回股利 |
| `G3TabDisclosureListed` / `G3TabDisclosureSOE` | 披露（被投资方 / 期初 / 增减 / 期末 / 备注） |

`g3Constants`：`G3_WP_CODE='G3'`、`G3_ACCOUNT_CODE='1131'`；审定行存 remark JSON。

## 共同要点

- **无独立附注入口**：跳转/反向跳转都指向节主（K1），不单列 G2/G3 入口
- 利息/股利的来源是 G4/G6/G7 的投资 → 计算基础在各投资底稿，G2/G3 只核应收余额与可收回性
- 收到的利息/股利影响 G11 投资收益与现金流量表投资活动
