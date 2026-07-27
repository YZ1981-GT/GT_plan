# G4 债权投资（`G4_ACCOUNT_CODE='1501'` ⚠ / 减值 `1502` ⚠）

**拆三个 componentType**：`g4-bond-investment-main` / `-sppi` / `-ecl`，对应 CAS22 的
"计量 — 分类 — 减值"三段独立工作量。

| 入口 | 主入口组件 | 子目录 |
|---|---|---|
| main | `GtG4BondInvestmentMain` | `core/`（审定/明细/调整）、`measurement/`（摊余成本、实际利率法）、`handbooks/` + `G4AuditTextCards` / `G4SheetStatusBar` |
| sppi | `GtG4BondInvestmentSppi` | `classification/`（业务模式 + SPPI 合同现金流量特征）、`inspection/`、`G4SppiImportExportDropdown` |
| ecl | `GtG4BondInvestmentEcl` | `impairment/`（三阶段 ECL）、`reference/`（参考资料/内嵌示例）、`voucher/`（凭证检查）、`G4EclImportExportDropdown` |

## 关键机制

- **摊余成本计量**：实际利率法（票面利率 vs 有效利率）、利息调整摊销、应计利息
- **SPPI + 业务模式**：判定是否分类为摊余成本计量；结论回流 main 的分类披露
- **ECL 三阶段**：阶段划分 → 违约概率/损失率 → 减值准备；减值损失进 **G14 信用减值损失（6702）**，
  减值准备对方科目 `G4_IMPAIRMENT_ACCOUNT_CODE='1502'`
- **跨入口存储契约**：`g4CrossHelpers.ts` + `g4StorageContract.ts` 的 `G4_ITEM_IDS`（如 `G4_3_ROWS`），
  main / sppi / ecl 三侧共用，改键必须三处同步
- 变动率阈值 `G4_CHANGE_RATE_THRESHOLD`（Excel 编制说明：变动比例超 30% 需分析）

## 与其他元素的关系

- 投资收益（利息收入）→ G11（6111）
- 信用减值损失 → G14（6702）
- 函证（券商/发行人）→ G0
- 结构与 G6 其他债权投资高度同构（FVOCI vs 摊余成本的差别在公允变动是否进 OCI）
