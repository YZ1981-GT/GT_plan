# Task 1 证据：slice 复核 + 九条 wp_code 裁决条目

spec `g-cycle-single-region-detail-lanes` · Task 1 · _Requirements: 1.1_　实测 2026-09-27

---

## 0. 🔴 本 Task 的主要产物已由 foundation Task 1 交付 ⇒ 转为复核 + 登记

tasks.md Task 1 写「`wp_code_adjudication` 九条（foundation Task 1 已建）**补** `store_payload_evidence`」。
实测 `backend/data/workpaper_sync_entry_wp_code_adjudication.json` 的九条条目
**`store_payload_evidence` 已全部存在**（`measured_at: "2026-09-27"`）⇒ 无需补写。

⇒ 本 Task 按 GC-10「既有产物复用不重研」改为**逐条复核**，并登记复核中发现的 spec 偏差。
🔴 **未新增、未改写任何 slice / adjudication 字节**。

## 1. slice 字段名按值确认（禁按 F 循环推演）

| spec 里的简写 | slice 真实字段名 | 位置 |
|---|---|---|
| `blocked_by` | **`capability_target_blocked_by`** | `independent_entries[].capability_target_blocked_by` |
| 「行身份」 | `dynamic_row_identity.tables[].row_identity.{kind,identity_field,source_ref}` | 17 条齐 |
| 「模板 sha」 | `authoritative_templates.files[].sha256` + `belongs_to_entry`（单值）/ `belongs_to_entries`（复数） | 15 册 |

`independent_entries` 共 **17** 条（G 循环全量），`authoritative_templates.files` **15** 册，
`in_runtime_index` **15/15 全在** `_index.json` 索引里 —— G 循环无 D4/F2 那种「磁盘有、索引无」的不可达合册。

## 2. 九条 `capability_target_blocked_by` 逐条实测

| entry_id | 实测 blocked_by | requirements.md 表 | 判定 |
|---|---|---|---|
| `xlsx/gt-g1-trading-financial-assets` | BP-1,2,3,4,**5,7** | 「🔴 BP-5 + BP-7 + **BP-9**」 | 🔴 **偏差**，见 §2.1 |
| `xlsx/gt-g3-dividend-receivable` | BP-1,2,3,4,**7** | BP-7 | ✅ |
| `xlsx/gt-g8-other-equity-instruments` | BP-1,2,3,4 | （无） | ✅ |
| `xlsx/gt-g9-other-noncurrent-financial` | BP-1,2,3,4 | （无） | ✅ |
| `xlsx/gt-g10-trading-financial-liabilities` | BP-1,2,3,4,**7** | BP-7 | ✅ |
| `xlsx/gt-g11-investment-income` | BP-1,2,3,4,**7** | BP-7 | ✅ |
| `xlsx/gt-g12-net-hedge-gains` | BP-1,2,3,4,**7** | BP-7 | ✅ |
| `xlsx/gt-g13-fair-value-changes` | BP-1,2,3,4,**7** | BP-7 | ✅ |
| `xlsx/gt-g14-credit-impairment-loss` | BP-1,2,3,4 | （无） | ✅ |

九条其余字段全一致：`capability=None` · `capability_target="bidirectional"` ·
`migration_state="legacy_fake_bidirectional"` · `adapter_id=None` · `mount_count=2`。

### 2.1 🔴 spec 偏差④：BP-9 不在 G1 的 `capability_target_blocked_by` 里，因为它不阻塞 bidirectional

BP-9 的 `blocks` 字段逐字是：

> `"blocks": "legacy 删除（Task 66/72）与 E 循环延后登记的解除"`

⇒ BP-9 阻塞的是 **legacy composable 删除**，不是 `capability_target=bidirectional`。
requirements.md 红基线 B3 把它写成 G1 的三条阻塞之一（「BP-5 / BP-7 / BP-9 三条，九条里最重」）
属**范畴错误** —— slice 的 `capability_target_blocked_by` 只收阻塞 capability 翻转的项。

**实际含义（不缩小、不放大）**：
- G1 受管 / 注册 adapter / 发布 contract **不被 BP-9 阻塞**（阻塞项是 BP-1~4 + BP-5 + BP-7）。
- 但 BP-9 对 **Task 15 的 legacy 删除范围**有硬约束，逐字：
  > 正确的解锁条件应改写为「G1 与 E1 两条 entry 都完成 step 9 改线到 sync bridge」，执行归 Task 66 / Task 72。
- `useG1DualMode.ts` 实测有且只有两处生产消费方：`GtG1TradingFinancialAssets.vue#L276`（本 spec）
  与 `GtE1MonetaryFund.vue#L166`（E1，**并发会话在途，本 spec 不碰**）。
- 🔴 ⇒ **Task 15 只做 G1 侧改线，不得删 `useG1DualMode.ts`**（删它会直接打断 E1）。
- 另一处 BP-9 登记的事实：两个消费方用法**本就不等价** —— E1 宿主传 `availableSheets = computed(() => [])`，
  G1 宿主传真实列表 ⇒ 改线时不能只按 G1 的用法重构。

### 2.2 BP-5 在 slice 里已是 `FIXED`（与 Task 0 §2.1 互证）

BP-5 的 `status` 实测为 `"FIXED"`，并带 `fixed_note`（foundation Task 5，2026-09-27）。
`fixed_note` 还记了一条按值复核结论：原 `why_not_fixed_here` 的理由①（「改成带空格的值会让按『无空格』约定写的比对行为改变」）
**不成立** —— `resolveG1SheetLabel` 的正则本就是 `${escaped}\s*$`（容忍尾随空白），
`extractG1SheetCode` 用 `/(G1A|G1-\d+)/i`（对 `…G1A ` 照样返回 `G1A`）；
平台旁证：ACNR `backend/data/acnr/global_catalog.json` 早把三个错名登记成 `sheet_name_aliases`、真名登记成 `sheet_name`。
⇒ `g1SheetLabels.ts` 是唯一偏离方，已修。

### 2.3 🔴 BP-7 正文只展开 G6-sppi 一处 —— 确认裁决 G1R-H7 的前提成立，且 slice 自身给出强旁证

BP-7 的 `what` / `source_refs` 实测**只有** G6-sppi 一处：

```
what:        `xlsx/gt-g6-other-bond-sppi` 的主表载入路径会把行身份退化成数组下标：
             useG6SppiFairValue.ts#L331 是 data.rows.map((r, i) => migrateFairValueRow(r, i + 1))，
             而 migrateFairValueRow(#L128) 在 raw.id 缺失时用 String(raw.id || `fv-${Date.now()}-${seq}`)
             —— seq 即数组下标 i+1，命中 forbidden_row_identity_kinds 的 array_index。
source_refs: ["…/composables/useG6SppiFairValue.ts"]   ← 单一文件
```

**slice 自身的两个计数是「五条无缺陷」的强旁证**（但不替代 Task 2 的按值 grep）：

| 计数 | 实测值 | 含义 |
|---|---|---|
| `honest_adjudication_summary.entries_with_positional_row_identity_defect` | **1** | 全 17 条只有**一条**有位置身份缺陷 |
| `dynamic_row_identity.tables` 里 `kind=generated_opaque_string_with_array_index_fallback` | 仅 `G6-5-fair-value-data` **1 条** | 就是 G6-sppi |
| 九条的 `kind` | 无一条是 `*array_index*`（见 §4） | 五条在行身份维度无 BP-7 形态 |

⇒ **先验结论（待 Task 2 按值证实）**：G3/G10/G11/G12/G13 五条的 `capability_target_blocked_by` 里带 BP-7，
属 **slice 内部不一致**（把一条 entry 专属缺陷横向套给了同族 entry），不是五处真缺陷。
🔴 Task 2 SHALL 仍按值 grep 五条的载入路径（`.map((r, i) =>` / `Date.now()` / `seq` / 下标派生 id），
**定位到就修，定位不到就登记不一致** —— 不得因为本节的先验就跳过实测（FC-4 禁推演）。

---

## 3. 九条 `wp_code_adjudication` 条目复核（`contract_id` / 真码 / `store_payload_evidence`）

`adjudications` 共 **35** 条（全循环），九条逐条实测：

| entry | `contract_id`（= adapter_id = 契约文件名，registry RG-4 双向锁死） | `wp_codes` 真码 | 幻影码 | `managed_excel_name` |
|---|---|---|---|---|
| G1 | `g1.trading_financial_assets_detail` | `["G1"]` | `G1T` | `明细表G1-2` |
| G3 | `g3.dividend_receivable_detail` | `["G3"]` | `G3D` | `明细表G3-2` |
| G8 | `g8.other_equity_detail` | `["G8"]` | `G8O` | `明细表G8-2` |
| G9 | `g9.other_noncurrent_detail` | `["G9"]` | `G9O` | `明细表G9-2` |
| G10 | `g10.trading_liabilities_detail` | `["G10"]` | `G10T` | `明细表G10-2` |
| G11 | `g11.investment_income_detail` | `["G11"]` | `G11I` | **`明细分析表G11-2`** |
| G12 | `g12.net_hedge_detail` | `["G12"]` | `G12N` | `明细表G12-2` |
| G13 | `g13.fair_value_changes_detail` | `["G13"]` | `G13F` | `明细表G13-2` |
| G14 | `g14.credit_impairment_detail` | `["G14"]` | `G14C` | `明细表G14-2` |

九条 `resolvable_for_provisioning=true` · `matcher_domain_conflict=null` ·
`heuristic_is_wrong_because` 统一是「CamelCase 启发式产物，在 wp_index **0 命中**」（FC-2）。

🔴 **Task 8~14 的 `ADAPTER_ID` 直接取上表 `contract_id` 列**，不得自造（tasks.md Task 8 写的
`"g9.other_noncurrent_detail"` 与实测一致 ✅）。
🔴 **matcher 域用幻影码、provisioning 用真码**（FC-2）—— 两者不可混用。

### 3.1 `store_payload_evidence` 九条复核（foundation Task 1 已测，本 Task 只核不改）

| entry | `store_item_id` | `max_payload_bytes` | `wp_count_with_payload` | 同册非主表载荷 / 关键注记 |
|---|---|---|---|---|
| G9 | `G9-detail-rows` | **605** | **2** | 两行：605 B 真实 + 2 B 空数组；`G9-adj-tb-writeback` 40 B（RG-10 模板化拼接键） |
| G8 | `G8-detail-rows` | 2 | 1 | `G8-adj-tb-writeback` 40 B；🔴 该键前端按字面量 grep **零命中**（RG-10） |
| G10 | `G10-detail-rows` | 2 | 1 | 🔴 BP-10 第二严重（**6 处**重复声明） |
| G11 | `G11-detail-rows` | 2 | 1 | `G11-adj-rows` **2480 B** 真实载荷；`G11-adj-tb-writeback` 46 B；主表自带 **44 格裸 IF**（G 循环主受管表最多） |
| G12 | `G12-hedge-detail-rows` | 2 | 1 | G 列布尔校验列 `=D9=SUM(E9:F9)` |
| G13 | `G13-detail-rows` | 2 | 1 | prefill 块 `[169]` 错名已修；K 列布尔 `=J11=D11` |
| G14 | `G14-detail-rows` | 2 | 1 | prefill 块 `[170]` 错名已修；🔴 身份 `rowKey` |
| G1 | `G1-2-rows` | **0** | 0 | 🔴 **0 行**（连空数组都没有）；同册 `G1-note-listed-store` 4899 / `G1-note-soe-rows` 597+581 / `G1-8-sub-portfolios` 102 / `G1-14-id-result` 10+7 |
| G3 | `G3-2-detail-rows` | **0** | 0 | 🔴 **0 行**；G3 **全册仅 12 B**（`G3-5-aging-custom-segments` 2 + `G3-5-aging-preset` 10）= G 循环载荷最少的一册 |

**与 requirements.md 的差异（措辞精度，非事实冲突）**：
spec 写「其余七条各 **2 B**（空数组）· `G1-2-rows` / `G3-2-detail-rows` **零行**」。
实测更精确：**2 B 的是七条里的七条**（G8/G10/G11/G12/G13/G14 六条 + G9 的第二行），
G1/G3 是 `max_payload_bytes=0` 且 `wp_count_with_payload=0` ⇒ **连一行 store 记录都没有**，
与「有记录但值是 `[]`（2 B）」是两种状态。
🔴 ⇒ **Req 4.8 的 seed 义务对 G1/G3 更重**：它们不是「空数组待填」而是「键不存在」，
seed 脚本须先**建键**再写行；P18 的「未 seed 时验收脚本显式失败」对 G1/G3 必须能区分这两态。

---

## 4. 九条行身份三族逐条（P1 的声明依据，`source_ref` 供 Task 2 按值核）

| store_item_id | `kind` | `identity_field` | slice 冻结 `source_ref` |
|---|---|---|---|
| `G1-2-rows` | `generated_timestamp_string` | `id` | `useG1Detail.ts#L704` |
| `G3-2-detail-rows` | `generated_timestamp_string` | `id` | `useG3Detail.ts#L358` |
| `G11-detail-rows` | `generated_prefixed_opaque_string` | `id` | `useG11DetailAnalysis.ts#L71` |
| `G8-detail-rows` | `generated_prefixed_opaque_string` | `rowId` | `useG8Detail.ts#L76` |
| `G9-detail-rows` | `generated_prefixed_opaque_string` | `rowId` | `useG9Detail.ts#L82` |
| `G10-detail-rows` | `generated_prefixed_opaque_string` | `rowId` | `useG10Detail.ts#L109` |
| `G12-hedge-detail-rows` | `generated_prefixed_opaque_string` | `rowId` | `useG12HedgeDetail.ts#L40` |
| `G13-detail-rows` | `generated_prefixed_opaque_string` | `rowId` | `useG13Detail.ts#L65` |
| `G14-detail-rows` | 🔴 **`stable_template_row_key`** | 🔴 **`rowKey`** | `useG14Detail.ts#L61` |

⇒ **`id` 3 条（G1/G3/G11）· `rowId` 5 条（G8/G9/G10/G12/G13）· `rowKey` 1 条（G14）**
与 requirements Req 1.1 **逐条一致** ✅（三族分布无偏差）。

`forbidden_identity_kinds` = `["array_index","ordinal","position","mutable_chinese_label"]`
⇒ 九条无一命中 ✅。🔴 `stable_template_row_key` **不在**禁用集合里 —— 它是合法且最稳的一族（GC-6），
F 循环写死 `row_identity_key in ('rowId','id')` 的守卫会把 G14 误判违规，P1 的变异判据正是钉这条。

## 5. 九条权威模板 sha256（64 位全量，Task 8~14 的 `TEMPLATE_SHA256` 直接取）

| entry | 模板文件 | size | sha256 |
|---|---|---|---|
| G1 | `G/G1 交易性金融资产.xlsx` | 157,253 | `eba510b3b7cef68a0e3ea1a16eaa1262468bee11fccbee47a39ff513c33fba73` |
| G3 | `G/G3 应收股利.xlsx` | 480,411 | `02a5727230a7e2b1f0d3504b87e45ab1998505bb891e8687f3fe0bd9be17a093` |
| G8 | `G/G8 其他权益工具投资.xlsx` | 450,079 | `5c8d3de7ee60ffef8677768c6c3966a313d4210ebc96b19a12c56721954b83b6` |
| G9 | `G/G9 其他非流动金融资产.xlsx` | 88,636 | `264322c0ed1b4bf6882687b973377ff0e90bdb5664edb4d7e3752ba39fec2379` |
| G10 | `G/G10 交易性金融负债.xlsx` | 99,458 | `3afd5131f3783c017f3b7e728e1b081188de71acebb46bdb43e2f8b24fb63da3` |
| G11 | `G/G11 投资收益.xlsx` | 75,600 | `a1b1d87f29e2dc63e279326d887b3d09bcda6b48c9c54881d82a875a0fe0f513` |
| G12 | `G/G12 净敞口套期收益.xlsx` | 79,999 | `6645caf0fdfadf38b5cc5919d8b4bc60e59dda7bda54747085a40bdf4b66a8f8` |
| G13 | `G/G13 公允价值变动收益.xlsx` | 58,717 | `fd5e5e9eeca7b392d59ca54beac51e96bb1575894113c0f3e69f05a234b0f099` |
| G14 | `G/G14 信用减值损失.xlsx` | 60,094 | `5ca770907cfd3723159f4eb45871102f1cee382255e391f3aca0b1d57a287dc6` |

tasks.md Task 8 写的 G9 前缀 `264322c0ed1b4bf6…` 与实测一致 ✅。
九条全是 **`belongs_to_entry` 单值** ⇒ **FC-3 在这九条成立**（一册一 entry）；
`belongs_to_entries` 复数只出现在 G4 / G6 两册（`templates_serving_multiple_entries = 2`）⇒ 归 `g4-g6` spec。

## 6. 计数类基线（GC-10 现算，供 P4 / P18 引用；🔴 不写死，Task 15 复算）

| 计数 | 本次现算值 | 用途 |
|---|---|---|
| `row_identity_kind_counts` | `timestamp:2` `prefixed_opaque:10` `uuid:3` `opaque+array_index_fallback:1` `stable_template_row_key:1` | P1 |
| `payload_column_mode_counts` | `conclusion_only:3` `remark_only:8` `conclusion_canonical_remark_mirror:1` `dual_write:5` | P3 |
| `http_client_binding_counts` | `api:13` `http:4` | 九条全 `api` |
| `duplicated_item_id_literals_in_g_cycle` | **80** | BP-10 / P4 |
| `entries_with_positional_row_identity_defect` | **1** | §2.3 的 BP-7 旁证 |
| `templates_serving_multiple_entries` | **2**（G4 / G6） | FC-3 在九条成立的反证边界 |

🔴 `payload_column_mode_counts` 的 `conclusion_only:3` 是**全循环**口径（含 G6-5），
九条里 `conclusion_only` 是 **G1 / G3 两条** —— P3 的断言口径是「九条内」，不得直接引这个 3。

---

## 7. Task 1 结论

| # | 判定 |
|---|---|
| 1 | slice 字段名 = `capability_target_blocked_by`（非 `blocked_by`），已按值确认 |
| 2 | 九条 blocked_by 八条与 spec 一致；🔴 **偏差④：G1 的 BP-9 是范畴错误**（BP-9 阻塞 legacy 删除，不阻塞 bidirectional）⇒ G1 受管不被 BP-9 阻塞，但 **Task 15 不得删 `useG1DualMode.ts`**（E1 共用，并发会话在途） |
| 3 | BP-5 已 `FIXED`（slice 已登记 `fixed_note`），与 Task 0 §2.1 互证 |
| 4 | 🔴 BP-7 正文只展开 G6-sppi；slice 自身 `entries_with_positional_row_identity_defect=1` 与行身份表给出「五条无缺陷」强旁证 ⇒ 裁决 G1R-H7 前提成立，Task 2 仍须按值 grep |
| 5 | `store_payload_evidence` 九条**已齐**，本 Task 未改任何字节；🔴 **G1/G3 是「键不存在」（0 B / 0 wp）而非「空数组」（2 B）** ⇒ seed 须先建键，P18 须能区分两态 |
| 6 | 九条 `contract_id` / 真码 / `managed_excel_name` 已定（Task 8~14 直接取，不自造）；G11 的 sheet 名是 `明细分析表G11-2`（唯一「分析」字样） |
| 7 | 行身份三族与 Req 1.1 逐条一致（`id`3 / `rowId`5 / `rowKey`1）；`stable_template_row_key` 不在禁用集合 |
| 8 | 九条 sha256 全 64 位已取；九条 `belongs_to_entry` 单值 ⇒ FC-3 成立 |
| 9 | 🔴 `payload_column_mode_counts.conclusion_only=3` 是全循环口径，九条内只有 G1/G3 两条 ⇒ P3 断言不得直引 |
