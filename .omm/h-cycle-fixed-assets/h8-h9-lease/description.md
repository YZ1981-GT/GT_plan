# H8 使用权资产（1901/1902）/ H9 租赁负债（2205 + 1802）

CAS21 租赁承租方的**资产侧与负债侧**，同一份合同的两半，必须双侧一致。

## H8 使用权资产（`h8-right-of-use-assets`）

| 目录 | 关键 sheet |
|---|---|
| `lease-judgment/` | **H8-4 租赁识别**（三要素：已识别资产 = 物理可区分 ∧ 无实质替换权；主导使用权；经济利益）+ 分拆(AND)/合并(OR) + **H8-5 租赁期确定**（决策树 + 重大事件触发 + 四情形修改） |
| `measurement/` | **H8-6 初始计量**（租赁付款额现值、IBR）/ H8-7 后续计量 |
| `depreciation/` | **H8-8 折旧测算**（不含减值 / 含减值双表；折旧期 = min(租赁期, 使用寿命)）/ H8-9 折旧分配 |
| `impairment/` | H8-10 减值（⑦→期初、⑧→本期计提自动填 + 说明草稿） |
| `inspection/` | H8-12 终止 / H8-13 短期与低价值租赁简化处理 / 凭证检查 |
| `core/` | 审定 H8-1 / 明细 H8-2（三页横排宽表：原值 / 累计折旧 / 减值，4 区段 Tab）/ 调整 H8-3 / 附注上市国企 / 目录 |

- 科目：`ACCOUNT_CODE_1901='1901'`（使用权资产）+ `ACCOUNT_CODE_ACC_DEP='1902'`（累计折旧）
- **H8-4 → H8-5 → H8-6/H8-8/H8-13 推送链**：租赁期一处改动必须推送计量参数、折旧期、短期简化判定
- **H8-5 ↔ H8-6 双向回写**（`pushLeaseTermToH86` / `pullLeaseTermFromH85` + 差异告警 `h85TermMismatch`）
- **H8-5 → H8-8 折旧期同步**（按合同号回写 `leaseTermMonths`，差异告警）
- **H8-5 ↔ H8-13 短期简化联动**（`isShortTermLeaseCandidate`：≤12 月且无购买选择权；含购买权按 CAS21 跳过）
- **H8-12 终止 → 结清 H9-2 对应行**（`applyH8TerminationToH92Rows`，contractNo/contractId 双键落库）
- 附注 **五、25（上市）/ 八、26（国企）**；H8-10 减值自动填期初/本期计提

## H9 租赁负债（`h9-lease-liabilities`）

| 目录 | 关键 sheet |
|---|---|
| `core/` | 审定 H9-1 / 明细 H9-2（承租方）/ H9-3（出租方同步 `syncLessorsFromH92`）/ 调整 H9-4 / 附注上市国企 / 目录 |
| `amortization/` | **实际利率法摊销表**（本期利息键 `H9-amort-current-interest` 对齐 H9-1；`normalizeIbrRate`） |
| `inspection/` | 到期日分析 / 凭证检查 |

- 科目：`ACCOUNT_CODE_2205='2205'`（租赁负债）+ `ACCOUNT_CODE_FINANCE_COST='1802'`（未确认融资费用，借方/负债备抵）
- **H9-4 → H9-1 同步 AJE/RJE**：`syncAjeRjeFromAdjustment`（2205 贷−借 / 1802 借−贷）+ 发 `adjustment:created`
- **H9-1 从明细带入**（`fillFromDetail` 自 H9-2/H9-3）+ 重分类/报表数/变动额率（>30% 警示）+ H9-1↔H9-2 勾稽
- H9-2/H9-3 含到期日分析；附注 **五、47 / 八、52**
- 摊销表复用 H8/H9 共享的实际利率法（`buildH86AmortSchedule` 亦复用）

## 双侧一致性（最易错处）

| 要素 | H8 侧 | H9 侧 |
|---|---|---|
| 租赁期 | H8-5 决定 | 摊销期数 |
| 折现率 IBR | H8-6 现值折现 | H9 摊销表 |
| 租赁付款额 | H8-6 初始计量 | H9-2 付款计划 |
| 终止 | H8-12 | H9-2 结清 |

三者任一不一致 → "资产按 5 年折旧、负债按 3 年摊销"类错误。跨表键有多别名
（`H8-initial-measurement` / `H9-1-initial-liability`）+ `h8:asset-updated` 落 `H9-h8-*`。

## 与其他元素的关系

- 租赁负债利息 → L8 财务费用
- 使用权资产折旧 → F5/K8/K9
- 处置/终止 → H10（`rou_disposal` 行）
- 出租方视角的融资租赁在 G5 长期应收款
