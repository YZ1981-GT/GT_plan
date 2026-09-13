# Wave 3 T3.1 前端 store ↔ 后端 descriptor 字段对齐（✅ D4-21/22/23/24 全对齐）

后端 descriptor（`phase5_d4_ipo_related_sheets.py`）的 `json_path` 是双向 projection 的
字段真源。前端持久化的行对象**键名必须逐字等于**这些 `json_path`，且存行身份键，
item_id 用 `D4-2x-rows`，否则 OO↔HTML 双向只搬空数据（假绿）。

## D4-21 关联方销售/价格（✅ 已对齐）
- 组件 `d4/related/D4TabRelatedPrice.vue` + `composables/useD4RelatedPrice.ts`
- item_id=`D4-21-rows`，行身份 `rowId`
- 12 键：partyName / relationship / product / qty / salesAmount / salesRatio / avgPrice /
  nonrelatedAvgPrice / fairPrice / priorSalesRatio / priorAvgPrice / remark
- 派生（不持久化、不进 projection）：priceDiffRate=I、fairDiffRate=K —— 对应 FORMULA_MASK I/K

## D4-24 第三方回款（✅ 已对齐）
- 组件 `d4/ipo/D4TabThirdParty.vue`（**内联类型**，非 useD4Ipo）
- 关键发现：存储键**本来就是正确的 `D4-24-rows`**，上轮记录的「-data→-rows」不成立。
  真问题是**第三套字段名**：salesAmount/arBalance/thirdPartyName/relationTo*/hasAgreement/
  hasConfirmation/analysis/indexRef/id 共 9 处（含 `id→rowId`，行身份也失效）。
- 已改：内联 `ThirdPartyRow` 全部改成 descriptor canonical 名（annualSales/endingAr/payerName/
  payerCustomerRelation/payerEntityRelation/hasPaymentAgreement/isConfirmed/rationality/indexNo
  + rowId）。`seq` 是 `$index+1` 派生展示列（与 D4-21 范式一致，不持久化）。
- 无内部公式（FORMULA_MASK 空）；J/K 是「是否」枚举。

## D4-23 收入与开票比较（✅ 已对齐 + 去重）
- 组件 `d4/ipo/D4TabInvoiceCompare.vue` + `composables/useD4InvoiceCompare.ts`
- 8 受管键：month / mainRevenue / otherRevenue / vatInvoiceAmount / vatInvoiceCount /
  plainInvoiceAmount / plainInvoiceCount / indexNo；固定 12 月行（template_row_key=month）
- 派生（FORMULA_MASK D/I/J）：revenueTotal=D、invoiceTotal=I、diff=J —— 前端本地派生不入契约。
- **收敛完成**：`useD4InvoiceCompare` 是活实现（有 .vue 宿主），已收敛为唯一实现；
  `useD4Ipo` 的 D4-23 段零消费方（见下）。
- **🔴 真 bug（守卫抓出）**：`loadData()` 曾读旧键 `D4-23-data`，而 `persistAll()` 写
  `D4-23-rows` ⇒ 永不读回自己写的数据（双向回写结构性空搬）。已修。
- 字段重命名波及 `getSummary` 的 `prop` 数组（合计行按列名取数）与 `rowClassName` 的
  `row.vatAmount`——这两处是**功能性**残留（合计/高亮会取错列），守卫用词边界匹配抓出。

## D4-22 重要指标（✅ 已对齐）
- 组件 `d4/ipo/D4TabIpoIndicator.vue` + `composables/useD4KeyIndicator.ts`
- 固定 4 受管键：metricName / currentPeriod / priorPeriod / rationality；行身份=metricName
  （前端 UI 态用 `label`，持久化时映射 `label→metricName`）
- **形态差异（嵌套 vs 扁平）**：前端 UI 态是 `peers:[...]` 数组 + `analysis`，
  descriptor 期望扁平行 `peer_1/peer_2/...`（稳定键 `{slot}_{seq}`，禁 label 作 key）+
  `rationality`。descriptor 的 `merge_projection_into_d422_store_rows` 按 `row.get("metricName")`
  取行身份，旧持久化直接写 `label`/`analysis`/`peers` 数组 ⇒ `rid` 恒空 ⇒ 空搬。
- **已加序列化层**：`toPersistedRows()` 展平（label→metricName、analysis→rationality、
  peers[i]→peer_${i+1}），`loadData()` 逆投影回 UI 态。UI 内部模型不变，仅持久化形态对齐。
- 存储键 `D4-22-data→D4-22-rows`。指标名真源一致：前端 12 个 label 与后端
  `METRIC_ROW_KEYS_D422` 逐字相同（守卫断言覆盖）。

## 🔴 useD4Ipo.ts 是全面死代码（建议单独任务删除）
- `composables/useD4Ipo.ts`（496 行，D4-22~32 通用 composable）**零 .vue/.ts 引用**——
  全部 13 个 `d4/ipo/D4Tab*.vue` 均不 import `useD4Ipo`（多个 tab 自内联类型）。
- 它包含 D4-23/D4-24/D4-25~32 的行类型与 load/persist 逻辑，但**从未接线**。
- 本 spec 范围内**未删除**：它是 git 已跟踪的干净文件，删除会移除 D4-25~32 的行类型定义，
  属超出本 spec（D4-21~24）范围的破坏性操作。登记待单独任务清理。
- 归档 spec 文档 `.kiro/specs/_archive/.../design.md` 第 100 行仍引用它（历史设计记录，不动）。

## 守卫（backend/tests/test_d4_21_24_import_export_roundtrip.py，8 passed）
- `test_d424_frontend_store_keys_match_descriptor_json_paths`：前端 ThirdPartyRow 键集
  == descriptor json_path ∪ {rowId} − {seq}（派生列豁免）。**真行为判据**（读两边源码做
  集合比对），非 grep 存在性。变异检验 RED（加 `_MUTATION_PROBE_` 字段打红 extra 断言）。
- `test_d423_frontend_store_keys_match_descriptor_json_paths`：前端 InvoiceCompareRow 键集
  == descriptor json_path ∪ 派生列（D423_DERIVED_KEYS）。变异检验 RED（加 `_PROBE_` 打红）。
- `test_d422_persist_shape_matches_descriptor`：持久化层覆盖 descriptor 固定列 + 行身份；
  动态列用 `peer_${i+1}` 稳定键；指标名真源覆盖 METRIC_ROW_KEYS_D422。变异检验 RED
  （`peer_${i}` 偏移打红稳定键断言）。
- 旧字段名零残留（D4-23/24 用词边界匹配，防合法新名子串误判）。

> 前端 `vue-tsc --noEmit`：TOTAL_ERROR_TS=0、目标文件 TARGET_HITS=0（本次未 OOM，Exit 0）。
> Playwright OO↔HTML 往返实测待 `start-dev.bat`（backend 当前 down），未做浏览器层验证。
