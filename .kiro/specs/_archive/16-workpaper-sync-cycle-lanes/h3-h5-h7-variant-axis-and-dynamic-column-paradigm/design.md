# Design Document

## Overview

本 design 交付 H3 / H5 / H7 三条 entry 的**实例化设计**：变体轴三维声明的具体参数、
SK-1~SK-4 守卫的落地位置、三条各异载体族的接线点、以及三份契约骨架。

🔴 **HC-1 ~ HC-16 的裁决正文在 `h-cycle-sync-foundation-and-first-canary/design.md`**，
本 design 只引用 §HC-x 并给实例化参数。

🔴 **Property 编号**：本 spec `Property N` = `HV-P{N}`。

---

## 一、变体轴三维声明的实例化（引用 HC-5）

### 契约坐标写法

```
sheet_coordinates: [
  { variant_axis: "measurement_model", variant_value: "cost",
    sheet_code: "H3-2", sheet_name: "明细表（成本模式）H3-2",
    item_id: "H3-2-cost-rows" },
  { variant_axis: "measurement_model", variant_value: "fair_value",
    sheet_code: "H3-2", sheet_name: "明细表（公允价值模式）H3-2",
    item_id: "H3-2-fair-rows" },        # 🔴 HC-8 冻结键（G 循环消费）
  { variant_axis: "impairment_included", variant_value: "excluded",
    sheet_code: "H3-7", sheet_name: "折旧测算表（成本模式不含减值）" },
  { variant_axis: "impairment_included", variant_value: "included",
    sheet_code: "H3-7", sheet_name: "折旧测算表（成本模式含减值）" },
  …
]
```

🔴 **H3-7 的两张 sheet 名同时含「成本模式」与「含否减值」两个轴的取值** ⇒
实测它们是 `(measurement_model=cost) × (impairment_included=?)` 的**交叉**，
不是单轴；契约 SHALL 允许 `variant_axis` 为**复合轴列表**，或直接用 `sheet_name` 全名兜底。
本 design 裁决：**优先 `sheet_name` 全名**，`variant_axis` 仅作查询索引（避免交叉轴组合爆炸）。

### 三条 entry 的轴清单

| entry | 轴 | 取值 | 涉及 sheet_code |
|---|---|---|---|
| H3 | `measurement_model` | `cost` / `fair_value` | H3-1 · H3-2 · 增减检查表 |
| H3 | `impairment_included` | `excluded` / `included` | H3-7（与 `measurement_model=cost` 交叉） |
| H5 | `impairment_included` | `excluded` / `included` | H5-12 |
| H7 | `measurement_model` | `cost` / `fair_value` | 审定表 · H7-2 · 增加检查表 · 减少检查表 |
| H7 | `impairment_included` | `excluded` / `included` | H7-11（`（不含减值）-直线法` / `（含减值）`） |

🔴 **H7-11 的「不含减值」那张 sheet 名还带 `-直线法` 后缀** ⇒ 又是一个隐含轴（折旧方法）。
本 design 不为它单独立轴（只此一处），用 `sheet_name` 全名兜底，并在守卫里登记该不对称。

## 二、SK-1 ~ SK-4 守卫落地位置

| 判据 | 断言位置 | 断言内容 | 反向断言（必须为 0） |
|---|---|---|---|
| SK-1 | `h7ListedDisclosureModel.ts#L50-57` | interface 三字段分离（key / label / 第三字段） | — |
| SK-1 | `createDefaultH7Categories()#L60` | 用 `${ind.key}_1` 生成初始 key | 不得用 label 作 key |
| SK-2 | `nextH7CategoryKey#L74-86` | 出现 `${prefix}${max+1}` | 🔴 全 H 不得出现 `length+1` / `${i}` / `${idx}` 作动态列序号 |
| SK-2 | `h7SoeDisclosureModel.ts#L104-115` | 国企侧同形 | 同上 |
| SK-3 | `h7TotalCellValue#L295` | 合计对动态数组 `reduce` | 🔴 全 H 不得出现 `公司1..公司N` 横向展开字面量（实测 0） |
| SK-4 | `H7_COST_MOVEMENT_ROWS` | 34 行，逐行对应源模板 R11-44 | 🔴 不得出现 `blankRows(x, <整数>)`（实测 0） |
| SK-4 | `H7_FAIR_MOVEMENT_ROWS` | 11 行，逐行对应源模板 R53-64 | 同上 |

**范式来源登记**：源模板 `H7 生产性生物资产.xlsx!附注披露信息（上市公司）` 两级表头下
四个产业的默认叶子列名都是同一字面 `类别`（`H7_DEFAULT_CATEGORY_LABEL`）⇒ label 作 key 必四列撞一列。
下游逐字引用「H7 已踩」5 处：`g7SlotColumns.ts` · `d4DisclosureModel.ts` ·
`i1SoeDisclosureModel.ts` · `e1CurrencyScope.ts` · `e1RestrictedScope.ts`。

🔴 **本 lane 内背离该范式的地方实测 0 处**；唯一背离点 BP-7 在 H8（归 lane 2）。
守卫方向是**断言本 lane 保持为 0**。

## 三、三条各异载体族的接线点（引用 HC-2）

### H3 — `formdata_composable`

载体 `useH3FormData`（实测生产消费 **37 处**，全 H 最活跃）。接线点 1 个。
读 `GET /checklist-responses`；TB 门在 `H3TabAdjudicationCost.vue`（`publishToTb`×2）。
消费方样例：`GtH3InvestmentProperty.vue` · `h3AccountScope.ts` · `useH3AdditionCheck.ts` ·
`useH3AdjudicationCost.ts` · `useH3AdjudicationFair.ts` · `useH3Adjustment.ts` ·
`useH3Depreciation.ts` · `useH3DetailCost.ts` · `useH3DetailFair.ts` · `useH3Disclosure.ts` ·
`useH3FairValueReview.ts` · `useH3Impairment.ts` · `useH3PolicyCheck.ts` …

### H5 — `per_tab_formdata_instance`（🔴 接线点 N 个）

每个子 Tab **各实例化一份** `useH5FormData` ⇒ **不是单实例**。
实施前 SHALL 现算实例化点个数并逐点接线；漏一个点 = 该 Tab 的双向不通但守卫可能全绿。
TB 门在 **`useH5FormData.ts`**（`publishToTb`×1）⇒ 每个实例都带一份发布门，
roundtrip 须确认不会多实例重复发布。

H5 的 16 个 PREFIX 常量（决定所有 item_id）：

| 常量 | 值 | 文件 |
|---|---|---|
| `ITEM_PREFIX` | `H5-1` | `useH5Adjudication.ts#L49` |
| `ITEM_PREFIX` | **`H5-2`** | `useH5Detail.ts#L53`（主表） |
| `ITEM_PREFIX` | `H5-3` | `useH5Adjustment.ts` |
| `ITEM_PREFIX` | `H5-4` | `useH5IdleCheck.ts` |
| `ITEM_PREFIX` | `H5-5` | `useH5PolicyCheck.ts` |
| `ITEM_PREFIX` | `H5-6` | `useH5Analysis.ts` |
| `ITEM_PREFIX` | `H5-7` | `useH5AdditionCheck.ts` |
| `ITEM_PREFIX` | `H5-8` | `useH5DisposalCheck.ts` |
| `PLAN_PREFIX` / `CHECK_PREFIX` / `SUMMARY_PREFIX` | `H5-9` / `H5-10` / `H5-11` | `useH5Stocktake.ts` |
| `ITEM_PREFIX` | `H5-16` | `useH5TitleCheck.ts` |
| `ITEM_PREFIX` | `H5-17` | `useH5RelatedParty.ts` |
| `OP_PREFIX` / `FIN_PREFIX` | `H5-18` / `H5-19` | `useH5Lease.ts` |
| `STORAGE_PREFIX` | `h5-dual-mode:` | `useH5DualMode.ts`（🔴 HC-10 第四存储风险，本 lane 删除该文件即消除） |

### H7 — `per_tab_self_persisting`（🔴 载体是 Tab 不是 composable）

持久化在 `H7TabDetailCost.vue` 内联 `api`；**主表键也内联在该 Tab**（`#L215`）。
🔴 `useH7DetailCost.ts` 是 **26 行取值 stub、不是持久化载体** ⇒ 接到它上面是假绿典型。
TB 门在 **`useH7FormData.ts`**（`publishToTb`×2），该文件 slice 误判为孤儿 ⇒ **禁删**（HC-3）。

### 本 lane legacy 载体处置

| 载体 | 生产消费 | 处置 |
|---|---|---|
| `useH5DualMode` | 0 | **删**（同时消除 HC-10 第四存储风险） |
| `useH7DualMode` | 0 | **删** |
| `useH7FormData` | **1** | 🔴 **禁删**（H7 唯一 TB 发布门） |

## 四、三份契约骨架

### `h3.investment_property_detail.json`

```
entry_id      : xlsx/gt-h3-investment-property
provider_id   : phase5_investment_property_detail
source_ref    : { workbook_sha256: 6526c9fc186230fa…, sheet_name: <按 variant 取全名> }
primary_tables: [
  { variant: {measurement_model: cost},  item_id: "H3-2-cost-rows",
    identity_field: "rowId", header_rows: [9,10,11], data_rows: [13,27],
    footer_row: 28, footer_kind: "pure_sum", footer_formula: "SUM(C13:C27)",
    effective_columns: 45 },
  { variant: {measurement_model: fair_value}, item_id: "H3-2-fair-rows",   # 🔴 HC-8 冻结
    identity_field: "rowId", frozen_key: true, frozen_reason: "G 循环 g13SourceDetailPull/gCycleSourceFv 消费" }
]
derived_total_keys : <现算，约 11 个>
carrier       : { write: "formdata_composable", read: "checklist_get",
                  tb_publish_gate: "h3/core/H3TabAdjudicationCost.vue" }
oo_crash_neutralization_fn : <per-file，本册裸 IF 661>
uuid_column   : 46        # 有效列 45 + 1
```

### `h5.oil_gas_asset_detail.json`

```
entry_id      : xlsx/gt-h5-oil-gas-assets
provider_id   : phase5_oil_gas_asset_detail
primary_table : { item_id: "H5-2-rows",        # 🔴 由 ${ITEM_PREFIX}-rows 拼接，HC-4
                  item_id_resolution: "template_concat",
                  prefix_const: { file: "useH5Detail.ts", line: 53, value: "H5-2" },
                  identity_field: "rowId", header_rows: [9,10,11,12],
                  data_rows: [13,32], footer_row: 33, footer_kind: "pure_sum",
                  effective_columns: 54 }
constant_fields : { isSubtotal: false, isEditable: true }   # HC-11，实测恒值
subtotal_persisted : false     # 🔴 实测不落库（filter 在 #L309-311）
derived_total_keys : <现算，约 5 个>
carrier       : { write: "per_tab_formdata_instance", read: "checklist_get",
                  tb_publish_gate: "composables/useH5FormData.ts",
                  instance_count: "<现算>" }
oo_crash_neutralization_fn : <per-file，本册裸 IF 816>
uuid_column   : 55
```

### `h7.biological_asset_detail.json`

```
entry_id      : xlsx/gt-h7-biological-assets
provider_id   : phase5_biological_asset_detail
primary_tables: [
  { variant: {measurement_model: cost},  item_id: "H7-2-cost-rows",
    item_id_location: "h7/core/H7TabDetailCost.vue#L215",   # 🔴 内联在 Tab
    identity_field: "rowId", header_rows: [9,10,11,12], data_rows: [13,36],
    footer_row: 37, footer_kind: "pure_sum", effective_columns: 51,
    cross_ref_via: "H7-2-cost-total" },                     # HC-6：勾稽走 total 键
  { variant: {measurement_model: fair_value}, item_id: "H7-2-fair-rows",
    item_id_location: "h7/core/H7TabDetailFair.vue", cross_ref_via: "H7-2-fair-total" }
]
dynamic_column_paradigm : h7_stable_slot_seq_key    # SK-1~SK-4
derived_total_keys : <现算，约 6 个>
carrier       : { write: "per_tab_self_persisting", read: "checklist_get",
                  tb_publish_gate: "composables/useH7FormData.ts" }   # 🔴 禁删该文件
oo_crash_neutralization_fn : <per-file，本册裸 IF 1025>
uuid_column   : 52
```

## 五、Property（HV-P）

| # | Property | 引用 |
|---|---|---|
| HV-P1 | 5 组变体轴 × 全部双 sheet 有唯一契约坐标；两维声明打红 | HC-5 |
| HV-P2 | 按 `sheet_code` 定位命中 2 张时要求 `variant_value` 消歧，不静默取首张 | HC-5 |
| HV-P3 | SK-1~SK-4 七条断言位置全命中；三条反向断言保持为 0 | Req 3 |
| HV-P4 | 本 lane 背离 H7 范式的地方 == 0 处 | Req 3.6 |
| HV-P5 | H5 实例化点个数现算并逐点接线；漏点打红 | HC-2 |
| HV-P6 | H7 载体断言在 `H7TabDetailCost.vue`；接到 `useH7DetailCost.ts` 打红 | HC-2 |
| HV-P7 | 可删名单 == {`useH5DualMode`,`useH7DualMode`}；`useH7FormData` 在禁删名单 | HC-3 |
| HV-P8 | `H5-2-rows` 经拼接解析命中；字面量分支缺失时打红 | HC-4 |
| HV-P9 | `H7-2-cost-rows`/`H7-2-fair-rows` 命中 1 判正常（有对应 total 键） | HC-6 |
| HV-P10 | `H3-2-fair-rows` 键名未改 | HC-8 |
| HV-P11 | 族 C **3 处**修复带旧身份迁移映射（全 H 7 = 3 + lane2 的 2 + lane3 的 2） | HC-7 |
| HV-P12 | H5 小计行不落库；`isSubtotal`/`isEditable` 声明为常量 | HC-11 |
| HV-P13 | 三册 per-file 中性化计数 == 1025/816/661 | HC-12 |
| HV-P14 | 6 张宽表有效列 == 实测；UUID 落有效列+1 | HC-13 |
| HV-P15 | 三册干净点保持为无 + 无 `GT_Custom` hidden sheet | HC-14 |
| HV-P16 | 三条 footer 全为纯 SUM；不触发第三形态 | HC-16 |
