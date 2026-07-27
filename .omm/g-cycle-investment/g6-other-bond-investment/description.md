# G6 其他债权投资（`G6_ACCOUNT_CODE='1503'` ⚠ 与 G8 同码）

与 G4 同构，也**拆三个 componentType**：`g6-other-bond-investment-main` / `-sppi` / `-ecl`。
差别在于其他债权投资是 **FVOCI（以公允价值计量且其变动计入其他综合收益）**。

| 入口 | 主入口组件 | 子目录 |
|---|---|---|
| main | `GtG6OtherBondMain` | `core/`、`handbooks/` + `G6AuditTextCards` |
| sppi | `GtG6OtherBondSppi` | `classification/`（业务模式 + SPPI）、`fair-value/`（公允价值）、`interest/`（利息/实际利率）、`inspection/`、`handbooks/` |
| ecl | `GtG6OtherBondInvestmentEcl` | `impairment/`（三阶段 ECL）、`voucher/`、`G6EclSheetStatusBar` |

`g6AdjudicationItems`：`G6_ACCOUNT_CODE='1503'`；`useG6MainAdjustment` 另有 `G6_4_STORAGE_KEY='G6-4-rows'`、
`BALANCE_TOLERANCE=0.005`，跨入口派发用 `g6CrossHelpers.dispatchG6SaveItems`。

## FVOCI 的两条特殊逻辑

1. **公允变动进 OCI（4002 其他综合收益）**，不进当期损益 → 与 G4（摊余成本，无公允变动）根本区别
2. **减值仍进损益**：ECL 减值损失进 G14 信用减值损失（6702），但**账面价值仍按公允价值**，
   减值准备在 OCI 中体现（"两条腿"记账，是该科目最易做错的点）
3. 处置时 OCI 累计额**转入当期损益（投资收益）**（与 G8 权益工具的"不得转损益"相反）

## 与其他元素的关系

- OCI 累计 → M 循环其他综合收益（M9）
- 处置结转 → G11 投资收益（6111）
- 减值 → G14（6702）
- SPPI/业务模式判定与 G4、G1 同准则依据（CAS22）
