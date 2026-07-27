# D6 合同资产（1402）

componentType `d6-contract-assets` → `GtD6ContractAssets.vue`，后端 `_d6_contract_assets.py`。
CAS14 收入准则下的合同资产，资产借方。**D 循环里唯一能从四表库干净 seed 审定表原值动态行的科目**。

## Sheet 组成（`d6/` 真实 Tab 组件）

`D6TabIndex` `D6TabProcedure` `D6TabAdjudication`（D6-1，三区块 原值/减值/净值）`D6TabDetail`（D6-2 + `D6DetailRowDialog` 引导录入）
`D6TabAdjustment` `D6TabEclCalculation`（ECL）`D6TabImpairmentDetail`（减值明细）`D6TabInspection`（检查）
`D6TabPolicyCheck` `D6TabRelatedParty` `D6TabWriteoffCheck`（核销）`D6TabDisclosure`

## 联动

- **TB 回写**：`useD6FormData` → `account_code: '1402'`
- **四表取数（唯一真 seed）**：`d-cycle-four-table-extraction-formulas` 的 Tier B 只在 D6 生效——`_build_adjudication_prefill` 从 `tb_balance` 1402 **叶子科目**（过滤父级防双算）seed D6-1 block1 原值期初/期末未审数，**手工优先**（已有非空值不覆盖）；灰度开关 `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 默认关
- **明细→审定**：D6-2 逐项明细 SUMIF 带入；`aggregate_d6_detail_rows`（后端已抽为纯函数）支持从 `tb_aux_balance` 按维度归集
- **期后结算**：`importPostSettlementFromLedger` 读次年序时账 1402 **贷方**按客户归集
- **ECL ↔ 减值勾稽**：D6-8 ECL 应计提 vs D6-3 减值实际计提，差异 > 1 元告警
- **核销确认**：D6-9 结论确认 emit `d6:writeoff-confirmed` → 联动 D6-3
- **抽凭**：`GtVoucherSamplingEngine`（1402 / final）
- **非流动扣减**：D6-2「超 1 年应收」合计 → 非流动扣减参考（`crossSheet.nonCurrentTotal`）
- **关联方完整性**：`missingRelatedParties`（登记表有而明细未识别的漏列告警）
- **列偏好**：`useD6DetailColumnPrefs`（8 组 30 列 / 3 预设 / localStorage）

## 与 D2 的关系

合同资产在客户履约取得无条件收款权后**结转应收账款**，故 D6 与 D2 之间存在结转勾稽；D6 的 ECL 与 D2 的 ECL 用同一套三阶段方法论但组合口径不同。
