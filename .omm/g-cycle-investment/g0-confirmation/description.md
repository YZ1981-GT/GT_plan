# G0 函证（投资类）

复用 D0 的 9 个 `confirmation-*` 组件（`confirmation-summary` / `-entity-verify` / `-diff-reconcile` /
`-followup` / `-reliability` / `-fraud-risk` / `confirmation-alternative-*` 等），G0 自身只有三块特有内容：

| 目录 | 内容 |
|---|---|
| `g0-confirmation/alternativeG06` | G0-6 替代程序（无法函证/未回函时的替代测试） |
| `g0-confirmation/diffSecurities` | **证券类函证差异核对**（G 循环特有：券商对账单 / 托管账户与账面差异） |
| `g0-confirmation/composables` | G0 专属数据层 |

## 与其他元素的关系

- 券商 / 基金管理人 / 被投资单位函证 → 支撑 G1 / G4 / G6 / G7 的存在性与计价认定
- 回函金额 vs 账面 → 差异核对 → 差异进各科目调整分录
- 函证台账与状态机、`apply_confirmation_result` 下游 stale 传播见 `.omm/d-cycle-sales/d0-confirmation/`
- 替代程序（`alternativeG06`）走 `createAlternativeConfirmationData` 工厂（八套替代程序已收敛为配置驱动）
