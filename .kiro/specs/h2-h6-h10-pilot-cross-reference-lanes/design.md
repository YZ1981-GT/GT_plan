# Design Document

## Overview

本 design 交付 H2 / H6 / H10 三条 entry 的实例化设计，重点是：
①H1 pilot 跨引用的冻结与回归口径；②BP-12 猜键回退链的收敛方案；
③HC-10 三存储并存的长期一致性归口；④TB 发布链首例选型；⑤H10 的月度矩阵 + 双 footer。

🔴 **HC-1 ~ HC-16 的裁决正文在 `h-cycle-sync-foundation-and-first-canary/design.md`**，
本 design 只引用 §HC-x 并给实例化参数。

🔴 **Property 编号**：本 spec `Property N` = `HX-P{N}`。

---

## 一、H1 pilot 跨引用图与冻结口径

```
H1 pilot（h1.disposal_check.json / pilot_class h1_grouped_dynamic / adapter 已注册 / golden 已锁）
  ├── h1CipH2Pull.ts           ──→ H2-2-rows                                      🔴 冻结
  ├── h1SoeClearingH6Pull.ts   ──→ H6-1-end-balance-audited · H6-1-rows · H6-2-rows 🔴 冻结
  ├── h1RelatedH10Pull.ts      ──→ H10-detail-rows                                🔴 冻结
  └── useH1LeaseCheck.ts       ──→ H10-detail-rows（+ H1-2-rows / H1-7-rows / H1-8-rows /
                                     H1-listed-lease-rows / H1-18 / H1-19 / H1-20 / H1-7 / H1-8）

H10 ↔ H6 双向：
  h10RelatedH6Pull.ts / useH10CrossSheet.ts  ──→ H6-2-rows（+ 2 个猜测键，见 §二）
  h6H10Pull.ts / useH6Check.ts               ──→ H10-1-audited-total · H10-adj-total ·
                                                 H10-1-gain-loss-total
```

**冻结口径**：

1. 5 个键（`H2-2-rows` / `H6-1-rows` / `H6-2-rows` / `H6-1-end-balance-audited` / `H10-detail-rows`）
   在本 lane **键名不改**。理由：被已注册 adapter 的 H1 pilot 消费，golden digest 已锁。
2. 回归方式：本 lane 任何改动完成后重跑 H1 golden digest，断言**不变**。
   🔴 **不得修改 H1 的契约 / adapter / golden digest 本身**。
3. 零回归基线**现算**（GC-10）：契约目录 `*.json` 个数与文件名集合、`register_from_manifest()`
   已注册集合。当前现算值：13 个 / `{d2,d4,g7,h1}`。**不得写死**。

## 二、BP-12 猜键回退链收敛方案

**现状**（实测）：

| 位置 | 代码 | 问题 |
|---|---|---|
| `h10RelatedH6Pull.ts#L59` | `const keys = ['H6-2-rows', 'H6-detail-rows', 'H6-clearing-rows']` | 后两键 H6 侧生产命中 **0**、真库零载荷 |
| `useH10CrossSheet.ts` | 引用同一组三键 | 同上 |

同文件 `#L4` 注释已写明真源：
「H6 明细在 H6 WP 的 checklist『H6-2-rows』，不在 H10 allResponses —— 须 HTTP 拉取后勾稽。」
⇒ 作者知道真源是 `H6-2-rows`，后两键是**防御性猜测**。

**为什么是缺陷**：H6 一旦改键，回退链会依次尝试三个键、全部落空、**静默返回空数组** ⇒
H10 的「结转至资产处置收益」勾稽静默变 0，无任何提示。

**收敛方案**：

```
// 改前
const keys = ['H6-2-rows', 'H6-detail-rows', 'H6-clearing-rows']
const list = keys.map(k => pick(k)).find(Boolean) ?? []      // 静默取空

// 改后
const AUTHORITATIVE_KEY = 'H6-2-rows'    // 单一权威键，与 h6 契约 primary_table.item_id 同源
const row = pick(AUTHORITATIVE_KEY)
if (row === undefined) {
  // fail-loud：显式空态 + 可诊断信息，不静默当 0
  return { ok: false, reason: `H6 主表键 ${AUTHORITATIVE_KEY} 未找到`, value: null }
}
```

**判据**：全 H 扫 `const keys\s*=\s*\[` 形态，逐键断言「H 侧生产命中 > 0」；
变异「保留 `H6-detail-rows`」SHALL 打红。

## 三、HC-10 三存储并存的长期一致性归口

**三处存储**（实测）：

| # | 位置 | 生命周期 |
|---|---|---|
| 1 | `checklist_responses.remark`（真源） | 持久 |
| 2 | `props.htmlData.responses_snapshot`（父级 render-config 透传，H2/H6/H10 都读） | 请求级 |
| 3 | 🔴 `localStorage` `h10-draft:{wpId}:{itemId}`（H10 独有） | 跨会话，PUT 失败时产生 |

**roundtrip 前置断言**（防误判，必须有）：
`localStorage` 中 `h10-draft:` 前缀键数 == 0，否则打红并列出键名。

🔴 **但前置断言不是处置**。长期归口设计：

1. **草稿只作故障兜底、不作数据源**：`restoreDrafts()` 回灌后 SHALL 立即重试 PUT，
   成功则删草稿（现状 `#L35` 已删、`#L97` 成功时删），**失败则保留并上报可见错误**
   （现状失败是静默的 —— 这是真正的缺口）。
2. **双向同步期间禁写草稿**：adapter 回写窗口内 SHALL 禁用 `#L105` 的 `setItem` 分支，
   避免 OO 侧回写与本地草稿互相覆盖。
3. **草稿可见化**：UI SHALL 显示「有 N 条未同步草稿」，让用户知道存在第三份数据
   （现状用户完全不知道）。
4. 判据：模拟 PUT 连续失败 3 次 → 断言草稿产生 + **可见错误上报**；
   再模拟恢复 → 断言 `restoreDrafts` 重试成功并删草稿。

## 四、TB 发布链首例选型

**背景**：canary H9 与 H8 **都没有** TB 发布门（HD-7 两条缺口）⇒ 全 H 的发布链在 foundation 与 lane 2
都无处验证，本 lane 三条**都有**门，故发布链首例落在本 lane。

**实测发布门位置**：

| entry | 位置 | `publishToTb` 命中 |
|---|---|---|
| H2 | `useH2Adjudication.ts` + `h2/core/H2TabAdjudication.vue` | 2 + 2（另有测试 4） |
| H6 | `useH6Adjudication.ts` + `h6/core/H6TabAdjudication.vue` | 2 + 2（另有集成测试 1） |
| H10 | `useH10Adjudication.ts` + `h10/core/H10TabAdjudication.vue` + **宿主** + `useH10FormData.ts` | 2 + 3 + 1 + 1 |

**选型裁决：发布链首例 = H6**。理由：

1. **模板最简**：48,865 B（次小）· 主表两级表头 R9/R10 · 数据区仅 R11-15（5 行）· 42 公式 ·
   裸 IF **12（全 H 最少）** · 有效列 16（最少）。
2. **发布门最干净**：只有 composable + Tab 两处（H10 有 4 处含宿主与 FormData，链路最杂）。
3. **无第三存储**：H10 有 localStorage 草稿（HC-10），会污染发布链验证。

**代价与如实登记**：

1. 🔴 H6 **真库零载荷**（0 个 item_id）⇒ 发布链验证需要先有数据；
   **不得造数据当实证** —— 须等真实项目录入，或明确标注为合成场景并在报告写明。
   （这正是 H6 被否决为 canary 的同一理由，见 foundation §否决 H6。）
2. 🔴 H6 被 H1 pilot 与 H10 **双向跨引用**，发布链改动的回归面最大 ⇒ 必须每次回归 H1 golden。
3. H6 footer 是「　合计」全角空格特例（HC-16）⇒ 发布链验证会同时踩这个特例，
   须先落地 footer_marker 全角容错。

**否决 H2 的理由**：四级表头 + 50 有效列 + 226 公式，复杂度高于 H6 且无额外收益。
**否决 H10 的理由**：发布门 4 处 + localStorage 第三存储 + 双 footer + 月度矩阵，
首例不宜同时吃四个特例。

**发布链铁律**（平台级，本 design 只引用）：
审定数入 `trial_balance` **只能**走 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`，
必经二次确认；🔴 **禁止**在 `watch` / `onMounted` / debounce 回调内发布（数据变化只 emit）。

## 五、H10 月度矩阵 + 双 footer + 派生列

**几何**（实测）：单级表头 R7（全 H 最浅）· 数据区 R8-16（9 个模板项目行作**种子**，可增删）·
R17 合计 · 🔴 **R18「各月比例」第二 footer** · 26/26 列 · 96 公式。

**9 个种子项目行**（R 列逐行写勾稽对象）：
持有待售 / 固定资产 / 在建工程 / 生产性生物资产 / 无形资产 / 债务重组 /
非货币性资产交换 / 使用权资产 / 油气资产处置利得 —— 逐行标「与 H1/H2/H5/H7/H8 勾稽」。

🔴 **身份裁决**：实测 `useH10Detail.ts` 有 `addRow#L159` / `removeRow#L172` +
`id: raw.id ?? generateId()#L72` ⇒ 9 行只是**种子**、用户可增删 ⇒
身份是 `generated_opaque_string` + 字段名 **`id`（不是 `rowId`）**，
**不得**因「看起来固定」改成 `stable_template_row_key`。

**派生列**（全部声明 `derived`）：

| 列 | 公式 | 性质 |
|---|---|---|
| B-M | （12 个月度列，用户输入） | 业务列 |
| N | `=SUM(B8:M8)` | 年度合计（月度矩阵族，同源引用 F5-2 / D4-2） |
| T / Y | `=IF($Q$17=0,0,Q8/$Q$17)` | 占比列，**引合计行 R17**（同 G11-2 `$F$31` 形态） |
| Z | `=IF(AND(X8=0,Q8>0),1,IF(AND(X8…` | 嵌套 IF 判断式 |

**双 footer 声明**：
```
footer_rows : [ { row: 17, kind: "pure_sum",      label: "合计" },
                { row: 18, kind: "ratio_footer",  label: "各月比例" } ]   # 🔴 第二 footer
```
变异「只声明单 footer」SHALL 打红（会把 R18 当业务行、把比例值当金额比对）。

**hidden sheet**：H10 有 `GT_Custom`（与 H9 两册独有）⇒ 断言存在且**不纳管**。

## 六、三份契约骨架

### `h2.construction_in_progress_detail.json`

```
entry_id      : xlsx/gt-h2-construction-in-progress
provider_id   : phase5_construction_in_progress_detail
source_ref    : { workbook_sha256: de9426a33e8d51e9…, sheet_name: "明细表H2-2" }
primary_table : { item_id: "H2-2-rows", identity_field: "rowId", frozen_key: true,
                  frozen_reason: "H1 pilot h1CipH2Pull.ts 消费（golden 已锁）",
                  header_rows: [9,10,11,12], data_rows: [13,20], footer_row: 21,
                  footer_kind: "pure_sum", footer_formula: "SUM(J13:J20)",
                  effective_columns: 50 }
derived_total_keys : <现算，约 4 个>
carrier       : { write: "host_inline", read: "html_data_snapshot",
                  tb_publish_gate: "composables/useH2Adjudication.ts + h2/core/H2TabAdjudication.vue" }
oo_crash_neutralization_fn : <per-file，本册裸 IF 138>
uuid_column   : 51
```

### `h6.asset_disposal_clearing_detail.json`（发布链首例）

```
entry_id      : xlsx/gt-h6-asset-disposal-clearing
provider_id   : phase5_asset_disposal_clearing_detail
source_ref    : { workbook_sha256: c7d0d78a798ce9c3…, sheet_name: "明细表H6-2" }
primary_table : { item_id: "H6-2-rows", identity_field: "rowId", frozen_key: true,
                  frozen_reason: "H1 pilot h1SoeClearingH6Pull.ts + H10 双向消费",
                  header_rows: [9,10], data_rows: [11,15], footer_row: 16,
                  footer_kind: "pure_sum",
                  footer_marker: "　合计",          # 🔴 全角空格前缀（HC-16）
                  footer_marker_normalize: "fullwidth_space_tolerant",
                  formula_columns: ["E","I","J","K","L"],   # E=SUM(B:C)-D / I=B+F / L=I+J-K
                  effective_columns: 16 }            # 🔴 max_column 是 25，两者不等
frozen_keys   : ["H6-1-rows", "H6-1-end-balance-audited"]   # 同被 H1 pilot 消费
derived_total_keys : <现算，约 8 个；H6-2-subtotal-* 六键被跨 entry 消费，
                      重算时机须在跨表勾稽读取之前>
carrier       : { write: "host_inline", read: "html_data_snapshot",
                  tb_publish_gate: "composables/useH6Adjudication.ts + h6/core/H6TabAdjudication.vue" }
tb_publish_first_case : true       # 🔴 全 H 发布链首例
oo_crash_neutralization_fn : <per-file，本册裸 IF 12（全 H 最少）>
uuid_column   : 17                 # 有效列 16 + 1，🔴 不得放 26
```

### `h10.asset_disposal_income_detail.json`

```
entry_id      : xlsx/gt-h10-asset-disposal-income
provider_id   : phase5_asset_disposal_income_detail
source_ref    : { workbook_sha256: 9f0d2a64dab1fd76…, sheet_name: "明细表H10-2" }
primary_table : { item_id: "H10-detail-rows",        # 🔴 不含 sheet 尾码（HD-4）
                  identity_field: "id",              # 🔴 不是 rowId
                  identity_kind: "generated_opaque_string",
                  row_mutable: true,                 # addRow#L159 / removeRow#L172
                  seed_rows: 9, seed_is_template_only: true,
                  frozen_key: true,
                  frozen_reason: "H1 pilot h1RelatedH10Pull.ts + useH1LeaseCheck.ts 消费",
                  header_rows: [7], data_rows: [8,16],
                  footer_rows: [ {row:17, kind:"pure_sum"},
                                 {row:18, kind:"ratio_footer", label:"各月比例"} ],
                  monthly_columns: ["B".."M"], annual_total_column: "N",
                  derived_columns: ["N","T","Y","Z"],
                  effective_columns: 26 }
client_draft_store : { kind: "localStorage", prefix: "h10-draft",
                       key_pattern: "h10-draft:{wpId}:{itemId}",
                       roundtrip_precondition: "draft_count == 0" }   # 🔴 HC-10
hidden_sheets_unmanaged : ["GT_Custom"]
derived_total_keys : <现算，约 3 个>
carrier       : { write: "formdata_composable", read: ["checklist_get","html_data_snapshot"],
                  tb_publish_gate: "composables/useH10Adjudication.ts + h10/core/H10TabAdjudication.vue
                                    + 宿主 + composables/useH10FormData.ts" }
oo_crash_neutralization_fn : <per-file，本册裸 IF 56>
uuid_column   : 27
```

## 七、Property（HX-P）

| # | Property | 引用 |
|---|---|---|
| HX-P1 | 5 个冻结键键名未改；H1 侧 4 个消费文件仍能解析 | HC-8 |
| HX-P2 | 本 lane 改动后 H1 golden digest 不变；H1 契约/adapter 未被修改 | Req 2.3 |
| HX-P3 | 零回归基线现算（契约数 / 注册集），不写死 | GC-10 |
| HX-P4 | H10↔H6 双向耦合图落表（含 `h6H10Pull.ts` 反向消费 3 个 total 键） | Req 2.6 |
| HX-P5 | BP-12 收敛为单一权威键 + fail-loud；保留猜测键打红 | Req 3 |
| HX-P6 | 全 H `const keys=[...]` 逐键生产命中 > 0 | Req 3.4 |
| HX-P7 | roundtrip 前 `h10-draft:` 键数 == 0；草稿非空仍跑则打红并列键名 | HC-10 |
| HX-P8 | 草稿长期归口四条（失败可见上报 / 回写窗口禁写 / UI 可见化 / 重试成功即删） | design §三 |
| HX-P9 | H2/H6 断言**无** checklist GET；F 版守卫对这两条打红（证明须族分派） | HC-2 |
| HX-P10 | H10 同时断言 checklist GET 与 snapshot 两读路径 | HC-2 |
| HX-P11 | 可删 == {`useH6FormData`}；`useH6DualMode` 须与 lane 2 协调 | HC-3 |
| HX-P12 | 发布链首例 == H6；走显式发布门 + 二次确认；禁 watch/onMounted/debounce 内发布 | Req 6 |
| HX-P13 | BP-6 第三处修复后全 H `seed-${` 命中 == 0 | Req 7.1 |
| HX-P14 | 族 C 2 处修复带迁移映射；迁移必要性经真库现算判定 | HC-7 |
| HX-P15 | H10 身份保持 `id` + `generated_opaque_string`；改成 `stable_template_row_key` 打红 | HD-4 / Req 7.4 |
| HX-P16 | per-file 中性化计数 == 138 / 12 / 56；整册统一打红 | HC-12 |
| HX-P17 | UUID 落位 H2 51 · H6 **17**（非 26）· H10 27 | HC-13 |
| HX-P18 | H6 `footer_marker == "　合计"` 且全角容错；写成「合计」打红 | HC-16 |
| HX-P19 | H10 双 footer 声明；只声明单 footer 打红 | HC-16 |
| HX-P20 | H10 派生列 `N`/`T`/`Y`/`Z` 全声明 derived；月度矩阵同源引用 | HC-16 |
| HX-P21 | 三册干净点保持为无；H10 `GT_Custom` 存在且不纳管 | HC-14 |
| HX-P22 | `H6-2-subtotal-*` 六键重算时机在跨表勾稽读取之前 | HC-6 |
