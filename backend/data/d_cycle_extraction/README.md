# D-cycle 锚点登记表（Task 1.2 / Wave 0 交付）

> spec: `.kiro/specs/d-cycle-four-table-extraction-formulas/`
> 本目录 `d_cycle_anchor_registry.json` = D-cycle 底稿真实 `checklist_responses` item_id 锚点集，
> 从前端专属组件 composable **反查**（非臆造）。加载/校验入口：
> `backend/app/services/d_cycle_extraction/anchor_registry.py`（`known_anchors(wp_code)` / `is_known_anchor(wp_code, anchor)`）。

**用途**：Tier B 预填 seed 目标 / Tier A 公式 `target_cell` 必须 ∈ 对应 wp_code 的锚点集，
否则拒绝（Property 8，防止提取种子静默写到不存在字段而丢失）。

**条目两类**：
- 精确锚点（普通字符串）：精确相等匹配。
- 模式锚点（`re:` 前缀）：已锚定正则，用于**动态 rowKey** 的 per-field 键（rowKey 可为运行时生成 id `adj-<ts>-<rand>` 或 `deduction`，含连字符，故不能用 `[^-]+`）。

---

## D6 合同资产（科目 1141）

> 🔴 科目码纠正（2026-08-01）：合同资产科目为 `1141`（标准科目表 direction=debit）；
> `report_config` 报表行 **BS-011 合同资产** 四准则一致 `TB('1141','期末余额')`。
> 原全循环登记的 `1402` 是**在途物资**（存货类，属 F2 循环）→ 把存货的钱当合同资产取。

### D6-1 审定表（`useD6Adjudication.ts`，**per-field 存储**）

审定表三区块：**一、原值（block1）/ 二、坏账准备（block2）/ 三、净值（block3=block1−block2，computed 不落库）**。
每动态行 per-field 键：`D6-1-adj-{blockKey}-{rowKey}-{field}`，`blockKey∈{block1,block2}`，
`rowKey` 为动态（生成 id 或来自 D6-2 归集的合同类型名，或特殊行 `deduction`），
`field∈{priorUnadjusted, priorAje, priorRje, currentUnadjusted, currentAje, currentRje, reasonAnalysis}`。

| 锚点 | sheet | 存储形式 | 四表可填? | 说明 / 四表来源 |
|---|---|---|---|---|
| `D6-1-adj-block1-{rowKey}-priorUnadjusted` | D6-1 | per-field | **是（期初未审·原值）** | `tb_balance` 1141 叶子 `opening_balance`（Tier B）|
| `D6-1-adj-block1-{rowKey}-currentUnadjusted` | D6-1 | per-field | **是（期末未审·原值）** | `tb_balance` 1141 叶子 `closing_balance`（Tier B）|
| `D6-1-adj-block1-{rowKey}-{priorAje,priorRje,currentAje,currentRje}` | D6-1 | per-field | 否 | 审计判断（账项/重分类调整），不从四表取 |
| `D6-1-adj-block1-{rowKey}-reasonAnalysis` | D6-1 | per-field | 否 | 文本，原因分析 |
| `D6-1-adj-block2-{rowKey}-*` | D6-1 | per-field | 否 | block2=坏账准备（减值），来源 D6-3 ECL 模型而非 TB |
| `D6-1-adj-block1-rowKeys` / `D6-1-adj-block2-rowKeys` | D6-1 | JSON 数组（行键清单） | 否 | 动态行键追踪（结构性，非数值字段）|
| `D6-1-adj-block1-deduction-*` / `D6-1-adj-block2-deduction-*` | D6-1 | per-field | 否 | 「减：列示于其他非流动资产」扣减行，审计判断 |
| `D6-1-tb-amount` | D6-1 | per-field | 否（核对用） | 试算表 1141 总额（TB↔审定核对行，非分类未审）|
| `D6-1-note-{explanation,impairmentEval,longTermReason,conclusion}` | D6-1 | per-field（文本）| 否 | 审计说明/结论文本 |
| block3（净值）全部 | D6-1 | computed（不落库）| 否 | = block1−block2 逐行派生 |

> **四表可填结论（D6-1）**：仅 block1（原值）动态行的 `priorUnadjusted`/`currentUnadjusted` 是四表可填（1141 期初/期末余额）。block2（坏账准备）来自减值模型；调整/文本/净值均不可填。

### D6-2 明细表（`useD6Detail.ts`，**JSON-array-rows** 单键 `D6-2-rows`）

`D6-2-rows` 存 `DetailRow[]` JSON 数组（30 列）。四表取数走 `importFromAuxBalance`（`tb_aux_balance` 1141 按客户/合同维度归集）+ `importPostSettlementFromLedger`（次年序时账 1141 贷方）——属 **Tier B 复杂归集**，非单条可编辑公式（不做 Tier A）。

`DetailRow` 关键字段（四表可填 = ★）：
`rowId, seqNo, contractName, contractType, customerName, companyCode, relatedPartyType,`
`priorUnadjusted★(7), priorAje(8), priorRje(9), priorAudited(10=7+8+9 computed),`
`agePrior1y..agePrior3yAbove(11-14), debitAmount★(15), creditAmount★(16),`
`endUnadjusted(17=10+15−16 computed·借方科目), endAje(18), endRje(19), endAudited(20=17+18+19 computed),`
`ageEnd1y..ageEnd3yAbove(21-24), receivableWithin1y(25), receivableAbove1y(26),`
`isInConstructionPeriod(27), creditRiskGroup(28), isConfirmed(29), postPeriodSettlement★(30·序时账)`

> ★ = 可由四表库（tb_aux_balance 1141 / 序时账）归集填充；其余为审计判断/账龄/标记/computed。

---

## D2 应收账款（科目 1122）

> **Task 5.1 交付状态（Wave 4）**：
> - 锚点登记表 D2 段已覆盖真实键（从 `useD2Adjudication.ts` / `useD2Detail.ts` 反查确认，无缺失，未新增）。
> - `_d2_accounts_receivable.py` render 已接入灰度分支（ADDITIVE）：**宁缺勿造 R3.4 —— D2 render 不返回 `adjudication_prefill`**（TB 1122 无信用风险组合维度，无法干净映射到 D2-1 分类行）。开关开/关时 render 输出逐字节等价（零回归，Property 9 天然成立）。
> - Tier A 预设已注册：`D2-adj-tb-amount` → `TB('1122','期末余额')`（`d_cycle_extraction_presets.json`，唯一可表达为单条公式的干净候选 = 1122 总额核对标量；通过 `is_known_anchor` + `find_unsupported_formula_functions` 双门；公式管理面板 `extraction.tierA` 可查可编）。
> - Tier B 只读溯源（`presets.py::_TIER_B_PROVENANCE["D2"]`）：诚实登记 D2-2 明细 ← `tb_aux_balance` 1122 客户维度 `importFromAuxBalance` + 序时账期后回款；并声明 D2-1 分类行 = D2-2 SUMIF 派生、不做四表库 seed。
> - 与既有 `importFromAuxBalance`（D2-detail-rows）/ `D2-adj-tb-amount` seed（`useD2FormData.loadAll`）**共存不冲突**：render 只读快照透传、不覆盖（手工优先精度）。

### D2-1 审定表（`useD2Adjudication.ts`，**per-field 存储**）

固定分类行 `rowKey∈{individual(单项计提), aging(账龄组合), customer-type(客户类型组合)}`（`total` 合计行 computed 不落库）。
per-field 键：`D2-adj-{rowKey}-{field}`，`field∈{prior-unadjusted, prior-aje, prior-rje, current-unadjusted, current-aje, current-rje, reason}`（连字符命名）。
**未审数默认由 SUMIF 从 D2-2 明细按「信用风险组合方式」聚合**，per-field 手工键仅为回退/覆盖。

| 锚点 | sheet | 存储形式 | 四表可填? | 说明 |
|---|---|---|---|---|
| `D2-adj-{rowKey}-current-unadjusted` | D2-1 | per-field | ⚠️ 有条件 | 期末未审，但**按信用风险分类无法从 TB 直接拆分**（TB 只有 1122 总额）→ 分类行属 SUMIF(D2-2) / 宁缺勿造 R3.4，Tier B 通常不直接 seed |
| `D2-adj-{rowKey}-prior-unadjusted` | D2-1 | per-field | ⚠️ 有条件 | 期初未审，同上（分类不可从 TB 拆分）|
| `D2-adj-{rowKey}-{prior-aje,prior-rje,current-aje,current-rje}` | D2-1 | per-field | 否 | 审计判断（调整）|
| `D2-adj-{rowKey}-reason` | D2-1 | per-field（文本）| 否 | 原因分析 |
| `D2-adj-tb-amount` | D2-1 | per-field | 否（核对用）| 试算表 1122 总额（TB↔审定核对行，非分类未审）|
| `D2-adj-total-aje` / `D2-adj-total-rje` | D2-1 | per-field | 否 | AJE/RJE 累计（监听 adjustment:created）|
| `D2-adj-confirm-summary` | D2-1 | JSON（函证汇总）| 否 | 监听 confirmation:completed |

> **四表可填结论（D2-1）**：TB 只有 1122 科目总额，无法按信用风险组合（单项/账龄/客户类型）拆分 → **审定表分类行不适合 Tier B 直接 seed**（对齐 R3.4 宁缺勿造）；分类未审由 D2-2 明细 SUMIF 聚合而来。四表可填主要落在 D2-2 明细（下）。

### D2-2 明细表（`useD2Detail.ts`，**JSON-array-rows** 单键 `D2-detail-rows`）

`D2-detail-rows` 存 `DetailRow[]` JSON 数组（含 nested keyed 动态账龄 `agingPrior/agingCurrent/agingAudited`）。
四表取数走 `importFromAuxBalance`（`tb_aux_balance` 1122 按客户维度归集）+ `importPostPaymentFromLedger`（序时账期后回款）——**Tier B 复杂归集**，非单条公式。

`DetailRow` 关键字段（四表可填 = ★）：
`rowId, seq, customerName, companyCode, relationType,`
`priorUnadjusted★, priorAje, priorRje, priorAudited(=未审+AJE+RJE computed), agingPrior{},`
`debitOccurrence★, creditOccurrence★, endBalance(=期初审定+借−贷 computed), reclassification,`
`currentUnadjusted(=期末余额+重分类 computed), agingCurrent{},`
`currentAje, currentRje, currentAudited(computed), agingAudited{},`
`creditRiskClassification(单项计提/账龄组合/客户类型组合), groupName, isConfirmation, postPayment★, remark`

> **legacy（只读回退，非写入目标）**：D2 审定表 SUMIF 兼容旧 flat 格式 `D2-detail-count` + `D2-detail-{n}-{field}`；当前写入统一走 `D2-detail-rows` JSON，故 legacy 键不作为预填/公式 target，不列入锚点集。

---

---

## D1 应收票据（科目 1121）

> **Task 5.2 交付状态（Wave 4）**：
> - 锚点登记表 D1 段已覆盖真实键（从 `useD1Adjudication.ts` / `useD1DetailCategory.ts` / `useD1DetailCustomer.ts` 反查）。
> - `_d1_notes_receivable.py` render 已接入灰度分支（ADDITIVE）：**宁缺勿造 R3.4 —— D1 render 不返回 `adjudication_prefill`**（TB 1121 无「原值/坏账/净值 × 银行/商业」组合维度，无法干净映射到 D1-1 分类行）。开关开/关时 render 输出逐字节等价（零回归，Property 9 天然成立）。
> - Tier A 预设已注册：`D1-adj-tb-amount` → `TB('1121','期末余额')`（唯一可表达为单条公式的干净候选 = 1121 总额核对标量；通过 `is_known_anchor` + `find_unsupported_formula_functions` 双门）。
> - Tier B 只读溯源（`presets.py::_TIER_B_PROVENANCE["D1"]`）：诚实登记 D1-3 客户明细期后兑付 ← 序时账 1121 贷方（`importPostSettlementFromLedger`）；并声明 D1-1 分类行 = D1-2 cross-sheet 派生、不做四表库 seed。
> - `D1-adj-tb-amount` 的 seed 由既有 render `project_context.tb_amount`（前端 `useD1Adjudication` tbSeedAmount 回退）提供，本 render 不重复 seed（手工优先精度）。

### D1-1 审定表（`useD1Adjudication.ts`，**per-field 存储**）

三区块固定分类：**一、原值(gross)/ 二、坏账准备(bad-debt)/ 三、净值(net-value=原值−坏账，computed 不落库)**，每区块固定 2 行按票据类型（银行承兑汇票/商业承兑汇票）。
per-field 键：`D1-adj-{rowKey}-{field}`，`rowKey∈{gross-bank, gross-commercial, bd-bank, bd-commercial}`（`net-*` computed 不落库），`field∈{prior-unadj, prior-aje, prior-rje, current-unadj, current-aje, current-rje, reason}`（连字符命名）。
**原值未审默认由 cross-sheet 从 D1-2 按类别明细（`D1-cat-rows`）按 category 含「银行」/「商业」匹配填入**，per-field 手工键仅为回退/覆盖。

| 锚点 | sheet | 存储形式 | 四表可填? | 说明 |
|---|---|---|---|---|
| `D1-adj-(gross\|bd)-(bank\|commercial)-current-unadj` | D1-1 | per-field | ⚠️ 有条件 | 期末未审，但**按票据类型/区块无法从 TB 直接拆分**（TB 只有 1121 总额）→ 分类行属 cross-sheet(D1-2) / 宁缺勿造 R3.4，Tier B 不直接 seed |
| `D1-adj-(gross\|bd)-(bank\|commercial)-prior-unadj` | D1-1 | per-field | ⚠️ 有条件 | 期初未审，同上 |
| `D1-adj-(gross\|bd)-(bank\|commercial)-{prior-aje,prior-rje,current-aje,current-rje}` | D1-1 | per-field | 否 | 审计判断（调整）|
| `D1-adj-(gross\|bd)-(bank\|commercial)-reason` | D1-1 | per-field（文本）| 否 | 原因分析 |
| `D1-adj-tb-amount` | D1-1 | per-field | 否（核对用）| 试算表 1121 总额（TB↔审定净值核对行）；Tier A 可编辑公式 `TB('1121','期末余额')`；render `project_context.tb_amount` 已 seed |
| `D1-adj-note` / `D1-adj-conclusion` | D1-1 | per-field（文本）| 否 | 审计说明/结论 |
| net-value 区块全部 | D1-1 | computed（不落库）| 否 | = 原值−坏账 逐行派生 |

### D1-2 按类别明细（`useD1DetailCategory.ts`，单键 `D1-cat-rows`）/ D1-3 客户明细（`useD1DetailCustomer.ts`，单键 `D1-cust-rows`）

`D1-cat-rows` 存按类别（银行/商业）明细 JSON，是 D1-1 审定表原值区块的 cross-sheet 来源（SUMIF 派生）。
`D1-cust-rows` 存客户明细 JSON；四表取数走 `importPostSettlementFromLedger`（**序时账 1121 贷方**期后兑付按客户归集）——属 **Tier B 复杂归集**，非单条可编辑公式（不做 Tier A）。

---

## D3 预收账款（科目 2203）

> **Task 5.2 交付状态（Wave 4）**：
> - 锚点登记表 D3 段已覆盖真实键（从 `useD3Adjudication.ts` / `useD3Detail.ts` 反查）。
> - `_d3_prepaid_accounts.py` render 已接入灰度分支（ADDITIVE）：**宁缺勿造 R3.4 —— D3 render 不返回 `adjudication_prefill`**（TB 2203 无「性质/账龄」组合维度，无法干净映射到 D3-1 双区块分类行）。开关开/关时 render 输出逐字节等价（零回归，Property 9 天然成立）。
> - Tier A 预设已注册：`D3-adj-trial-balance-amount` → `TB('2203','期末余额')`（唯一可表达为单条公式的干净候选 = 2203 总额核对标量，同为 D3-2 明细核对标量；通过 `is_known_anchor` + `find_unsupported_formula_functions` 双门）。
> - Tier B 只读溯源（`presets.py::_TIER_B_PROVENANCE["D3"]`）：诚实登记 D3-2 明细 ← `tb_aux_balance` 2203 客户维度（`importFromAuxBalance` → `/d3/import-aux-balance`）；并声明 D3-1 双区块分类行 = D3-2 SUMIF 派生、不做四表库 seed。

### D3-1 审定表（`useD3Adjudication.ts`，**per-field 存储**）

双区块固定分类：**一、按性质分类（NATURE_ROWS 4 行）/ 二、按账龄分类（账龄配置段动态生成）**。
per-field 键：`D3-adj-{section}-{rowKey}-{field}`，`section∈{nature, aging}`，`field∈{priorUnadjusted, priorAje, priorRje, currentUnadjusted, currentAje, currentRje, reasonAnalysis}`（驼峰命名）。
nature rowKeys：`fixed-asset-sales`（预收销售固定资产款）/ `land-use-right`（预收销售土地使用权款）/ `contract-invalid`（合同不成立时已收取的对价）/ `other`（其他）。
aging rowKeys：默认 THREE_YEAR 段沿用旧 rowKey（within-1-year / 1-to-2-years / 2-to-3-years / over-3-years），自定义段用段 key（可含连字符，故用 `re:` 模式 `.+`）。
**未审数默认由 cross-sheet 从 D3-2 明细（`D3-det-rows`）按性质/账龄 SUMIF 聚合填入**，per-field 手工键仅为回退/覆盖。

| 锚点 | sheet | 存储形式 | 四表可填? | 说明 |
|---|---|---|---|---|
| `D3-adj-(nature\|aging)-{rowKey}-currentUnadjusted` | D3-1 | per-field | ⚠️ 有条件 | 期末未审，但**按性质/账龄无法从 TB 直接拆分**（TB 只有 2203 总额）→ 分类行属 SUMIF(D3-2) / 宁缺勿造 R3.4，Tier B 不直接 seed |
| `D3-adj-(nature\|aging)-{rowKey}-priorUnadjusted` | D3-1 | per-field | ⚠️ 有条件 | 期初未审，同上 |
| `D3-adj-(nature\|aging)-{rowKey}-{priorAje,priorRje,currentAje,currentRje}` | D3-1 | per-field | 否 | 审计判断（调整）|
| `D3-adj-(nature\|aging)-{rowKey}-reasonAnalysis` | D3-1 | per-field（文本）| 否 | 原因分析 |
| `D3-adj-trial-balance-amount` | D3-1 | per-field | 否（核对用）| 试算表 2203 总额（TB↔账龄合计核对行，同为 D3-2 明细核对标量）；Tier A 可编辑公式 `TB('2203','期末余额')` |
| `D3-adj-note-{aging-reason,change-analysis,conclusion}` | D3-1 | per-field（文本）| 否 | 审计说明/结论 |

### D3-2 明细表（`useD3Detail.ts`，单键 `D3-det-rows`）

`D3-det-rows` 存明细行 JSON（含 nested keyed 动态账龄）。四表取数走 `importFromAuxBalance`（`tb_aux_balance` 2203 按客户维度归集，`/d3/import-aux-balance`）——属 **Tier B 复杂归集**，非单条可编辑公式（不做 Tier A）。

---

## D4 营业收入（科目 6001 主营 / 6051 其他，收入类 **occurrence**）

> **Task 6.1 交付状态（Wave 5）**：
> - 锚点登记表 D4 段已覆盖真实键（从 `useD4Adjudication.ts` / `useD4RevenueDetail.ts` / `useD4OtherRevenue.ts` 反查）。
> - `_d4_operating_revenue.py` render 已接入灰度分支（ADDITIVE）：**宁缺勿造 R3.4 —— D4 render 不返回 `adjudication_prefill`**（TB 6001/6051 只有科目总额、无产品/项目维度，无法干净映射到 D4-1 明细行）。开关开/关时 render 输出逐字节等价（零回归，Property 9）。
> - Tier A 预设已注册**两条**：`D4-1-adj-tb-6001` → `TB('6001','审定数')` + `D4-1-adj-tb-6051` → `TB('6051','审定数')`（收入类 `audited_amount` 存审定发生额；`_COLUMN_MAP` 中「审定数」「期末余额」同映射 audited_amount，收入语义用「审定数」）。双门通过（`is_known_anchor` + `find_unsupported_formula_functions`）。
> - Tier B 只读溯源（`presets.py::_TIER_B_PROVENANCE["D4"]`）：D4-2 主营明细 ← 序时账 6001 贷方按产品×月归集（`d4_ledger_monthly_by_product` resolver）；D4-1 明细行 = D4-2/D4-3 SUMIF 派生、不做四表库 seed。

### D4-1 审定表（`useD4Adjudication.ts`，**JSON-array-rows** 单键 `D4-1-adj-rows`）

审定表按**主营/其他收入明细行（按产品/项目）**组织，主营 `mainRevenueByProduct` 从 `D4-2-rows` 按产品聚合、其他从 `D4-3-rows` 聚合（SUMIF 派生）。

| 锚点 | sheet | 存储形式 | 四表可填? | 说明 |
|---|---|---|---|---|
| `D4-1-adj-rows` | D4-1 | JSON 数组（审定表行）| 否（SUMIF 派生）| 主营/其他明细行按产品/项目，由 D4-2/D4-3 SUMIF 聚合，TB 无产品维度（宁缺勿造 R3.4）|
| `D4-1-adj-tb-6001` | D4-1 | per-field | 否（核对用）| 试算表 6001 主营审定发生额（TB↔主营小计核对）；Tier A 可编辑公式 `TB('6001','审定数')` |
| `D4-1-adj-tb-6051` | D4-1 | per-field | 否（核对用）| 试算表 6051 其他审定发生额（TB↔其他小计核对）；Tier A 可编辑公式 `TB('6051','审定数')` |
| `D4-1-adj-note` / `D4-1-adj-conclusion` | D4-1 | per-field（文本）| 否 | 审计说明/结论 |

### D4-2 主营明细（`useD4RevenueDetail.ts`，单键 `D4-2-rows`）/ D4-3 其他明细（`useD4OtherRevenue.ts`，单键 `D4-3-rows`）

`D4-2-rows` 存主营明细行 JSON（各产品×12 月）。四表取数走 **序时账 6001 贷方按产品×月归集**（`d4_ledger_monthly_by_product` resolver，「从序时账取数」）——属 **Tier B 复杂归集**，非单条可编辑公式（不做 Tier A）。`D4-3-rows` 存其他业务收入明细。

---

## D5 应收款项融资（科目 1124，balance）

> **Task 6.2 交付状态（Wave 5）**：
> - 锚点登记表 D5 段已覆盖真实键（从 `useD5Adjudication.ts` / `useD5Detail.ts` 反查）。
> - `_d5_receivables_financing.py` render 已接入灰度分支（ADDITIVE）：**宁缺勿造 R3.4 —— D5 render 不返回 `adjudication_prefill`**（TB 1124 无「应收票据/应收账款」类别拆分）。开关开/关时 render 输出逐字节等价（零回归，Property 9）。
> - Tier A 预设已注册：`D5-1-tb-amount` → `TB('1124','期末余额')`（唯一可表达为单条公式的干净候选 = 1124 总额核对标量）。双门通过。
> - Tier B 只读溯源（`presets.py::_TIER_B_PROVENANCE["D5"]`）：D5-2 明细 ← `tb_aux_balance` 1124 按类别归集 + 序时账期后兑现；D5-1 两分类行 = D5-2 category SUMIF 派生、不做四表库 seed；OCI 公允价值变动减项来自 D5-4，非四表库。

### D5-1 审定表（`useD5Adjudication.ts`，**per-field 存储**）

固定分类行 `rowKey∈{notes-receivable(应收票据), accounts-receivable(应收账款)}`（`subtotal/oci-change/fv-total/trial-balance/difference` computed 不落库）。
per-field 键：`D5-1-adj-{rowKey}-{field}`，`field∈{priorUnadjusted, priorAje, priorRje, currentUnadjusted, currentAje, currentRje}`（驼峰）。
**期末未审优先由 crossSheet 从 D5-2 按类别聚合（categoryAggregation），** per-field 手工键仅回退/覆盖。

| 锚点 | sheet | 存储形式 | 四表可填? | 说明 |
|---|---|---|---|---|
| `D5-1-adj-(notes-receivable\|accounts-receivable)-currentUnadjusted` | D5-1 | per-field | ⚠️ 有条件 | 期末未审，但**按类别无法从 TB 直接拆分**（TB 1124 只有总额）→ SUMIF(D5-2) / 宁缺勿造 R3.4 |
| `D5-1-adj-*-{priorUnadjusted,priorAje,priorRje,currentAje,currentRje}` | D5-1 | per-field | 否 | 期初未审/审计判断（调整）|
| `D5-1-tb-amount` | D5-1 | per-field | 否（核对用）| 试算表 1124 总额（试算平衡表数核对行）；Tier A 可编辑公式 `TB('1124','期末余额')`；render `project_context.tb_amount` 已 seed |
| `D5-1-note-explanation` / `D5-1-note-conclusion` | D5-1 | per-field（文本）| 否 | 审计说明/结论 |
| oci-change / subtotal / fv-total / difference | D5-1 | computed（不落库）| 否 | OCI 公允价值变动减项来自 D5-4；小计/合计/差异派生 |

### D5-2 明细表（`useD5Detail.ts`，单键 `D5-2-rows`）

`D5-2-rows` 存明细行 JSON。四表取数走 `importFromAuxBalance`（`tb_aux_balance` 1124 按类别维度归集）+ 序时账期后兑现——属 **Tier B 复杂归集**，非单条可编辑公式（不做 Tier A）。

---

## D7 合同负债（科目 2205，balance，双区块同 D3）

> **Task 6.3 交付状态（Wave 5）**：
> - 锚点登记表 D7 段已覆盖真实键（从 `useD7Adjudication.ts` / `useD7Detail.ts` 反查）。
> - `_d7_contract_liabilities.py` render 已接入灰度分支（ADDITIVE）：**宁缺勿造 R3.4 —— D7 render 不返回 `adjudication_prefill`**（TB 2205 无「性质/账龄」组合维度，无法干净映射到 D7-1 双区块分类行，同 D3）。开关开/关时 render 输出逐字节等价（零回归，Property 9）。
> - Tier A 预设已注册：`D7-1-adj-aging-trial-balance-currentAudited` → `TB('2205','期末余额')`（2205 总额 = 试算平衡表数核对标量；render `project_context.tb_amount`(2205) 亦 seed，前端 tbSeedAmount 回退，本预设作可编辑覆盖）。双门通过。
> - Tier B 只读溯源（`presets.py::_TIER_B_PROVENANCE["D7"]`）：D7-2 明细 ← `tb_aux_balance` 2205 客户/合同维度归集；D7-1 双区块分类行 = D7-2 SUMIF 派生（natAgg/agingByKey）、不做四表库 seed。

### D7-1 审定表（`useD7Adjudication.ts`，**per-field 存储**）

双区块固定分类：**一、按性质（NATURE_BLOCK_CONFIG：预收货款/开发项目预收款/预收工程款/其他 + 减非流动负债扣减）/ 二、按账龄段（账龄配置段动态生成）**。
per-field 键：`D7-1-adj-{block}-{rowKey}-{field}`，`block∈{nature, aging}`，`field∈{priorUnadjusted, priorAje, priorRje, currentUnadjusted, currentAje, currentRje, reasonAnalysis}`（驼峰）。
账龄默认 THREE_YEAR 段沿用旧 rowKey（within-1-year/…），自定义段用段 key（可含连字符，故 `re:` 模式 `.+`）。
**未审数默认由 cross-sheet 从 D7-2（natAgg/agingByKey）SUMIF 聚合填入，** per-field 手工键仅回退/覆盖。

| 锚点 | sheet | 存储形式 | 四表可填? | 说明 |
|---|---|---|---|---|
| `D7-1-adj-(nature\|aging)-{rowKey}-currentUnadjusted` | D7-1 | per-field | ⚠️ 有条件 | 期末未审，但**按性质/账龄无法从 TB 直接拆分**（TB 2205 只有总额）→ SUMIF(D7-2) / 宁缺勿造 R3.4 |
| `D7-1-adj-(nature\|aging)-{rowKey}-{priorUnadjusted,priorAje,priorRje,currentAje,currentRje,reasonAnalysis}` | D7-1 | per-field | 否 | 期初未审/审计判断（调整）/原因分析 |
| `D7-1-adj-aging-trial-balance-currentAudited` | D7-1 | per-field | 否（核对用）| 试算表 2205 期末（试算平衡表数核对行）；Tier A 可编辑公式 `TB('2205','期末余额')`；render `project_context.tb_amount` 已 seed |
| `D7-1-adj-aging-trial-balance-priorAudited` | D7-1 | per-field | 否（核对用）| 试算表 2205 期初（核对行）|
| `D7-1-note-{explanation,conclusion,aging-explanation}` | D7-1 | per-field（文本）| 否 | 审计说明/结论 |

### D7-2 明细表（`useD7Detail.ts`，单键 `D7-2-rows`）

`D7-2-rows` 存明细行 JSON（含 nested keyed 动态账龄）。四表取数走 `tb_aux_balance` 2205 按客户/合同维度归集——属 **Tier B 复杂归集**，非单条可编辑公式（不做 Tier A）。

---

## 差异矩阵小结（四表可填 vs 不可填）

| wp_code | 四表可填锚点（Tier B seed 候选） | 明确不可填（审计判断/核对/computed/分类不可拆） |
|---|---|---|
| D6 | D6-1 block1 `priorUnadjusted`/`currentUnadjusted`（原值·1141 期初/期末余额）；D6-2 行内 `priorUnadjusted`/`debitAmount`/`creditAmount`/`postPeriodSettlement`（aux/序时账归集，Tier B） | block2 坏账准备（ECL 模型）、所有 AJE/RJE、reasonAnalysis/notes、block3 净值(computed)、tb-amount(核对)、rowKeys(结构) |
| D2 | D2-2 行内 `priorUnadjusted`/`debitOccurrence`/`creditOccurrence`/`postPayment`（aux/序时账归集，Tier B） | D2-1 分类行未审（TB 不可按信用风险拆分→宁缺勿造，由 D2-2 SUMIF）、所有 AJE/RJE、reason、tb-amount(核对)、total-aje/rje、confirm-summary、行内 computed 列 |
| D1 | D1-3 `D1-cust-rows` 行内 `postSettlement`（序时账 1121 贷方期后兑付归集，Tier B）；D1-adj-tb-amount（1121 总额，Tier A 可编辑 `TB('1121','期末余额')`，render 已 seed） | D1-1 分类行未审（TB 不可按票据类型×区块拆分→宁缺勿造，原值由 D1-2 cross-sheet、坏账由减值模型、净值 computed）、所有 AJE/RJE、reason、note/conclusion |
| D3 | D3-2 `D3-det-rows` 行内 `priorUnadjusted`/期末等（tb_aux_balance 2203 客户维度归集，Tier B）；D3-adj-trial-balance-amount（2203 总额，Tier A 可编辑 `TB('2203','期末余额')`） | D3-1 双区块分类行未审（TB 不可按性质/账龄拆分→宁缺勿造，由 D3-2 SUMIF）、所有 AJE/RJE、reasonAnalysis、note（aging-reason/change-analysis/conclusion）|
| D4 | D4-2 `D4-2-rows` 行内各产品各月（序时账 6001 贷方按产品×月归集，Tier B）；D4-1-adj-tb-6001/D4-1-adj-tb-6051（6001 主营/6051 其他审定发生额，Tier A 可编辑 `TB('6001','审定数')`/`TB('6051','审定数')`）| D4-1 主营/其他明细行未审（TB 不可按产品/项目拆分→宁缺勿造，由 D4-2/D4-3 SUMIF）、`D4-1-adj-rows`、note/conclusion |
| D5 | D5-2 `D5-2-rows` 行内 期初/期末未审/期后兑现（tb_aux_balance 1124 类别维度归集，Tier B）；D5-1-tb-amount（1124 总额，Tier A 可编辑 `TB('1124','期末余额')`）| D5-1 两分类行未审（TB 不可按应收票据/应收账款拆分→宁缺勿造，由 D5-2 category SUMIF）、OCI 公允价值变动减项（来自 D5-4）、所有 AJE/RJE、note/conclusion、computed（小计/合计/差异）|
| D7 | D7-2 `D7-2-rows` 行内 期初/期末未审等（tb_aux_balance 2205 客户/合同维度归集，Tier B）；D7-1-adj-aging-trial-balance-currentAudited（2205 总额，Tier A 可编辑 `TB('2205','期末余额')`）| D7-1 双区块分类行未审（TB 不可按性质/账龄拆分→宁缺勿造，由 D7-2 SUMIF）、所有 AJE/RJE、reasonAnalysis、note（explanation/conclusion/aging-explanation）|
