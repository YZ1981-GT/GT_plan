# Design Document

## Overview

本 design 交付 H4 / H8 两条独立 entry **+ 5 条子入口**的实例化设计，重点是：
①子入口改线的链式复用图与「一并改」清单；②BP-5 / BP-6 / BP-7 三条专属缺陷的修复方案；
③H4 footer 第三形态与 H8 重负载的处置。

🔴 **HC-1 ~ HC-16 的裁决正文在 `h-cycle-sync-foundation-and-first-canary/design.md`**，
本 design 只引用 §HC-x 并给实例化参数。

🔴 **Property 编号**：本 spec `Property N` = `HS-P{N}`。

---

## 一、子入口链式复用图（本 spec 的头号风险）

```
useH4DualMode  (生产消费 5)
  ├── GtH4EngineeringMaterials.vue            ← 父宿主
  ├── h4/impairment/H4TabImpairment.vue       ← 子入口 xlsx/h4/impairment/h4-tab-impairment
  ├── h4/impairment/H4TabRecoverable.vue      ← 子入口 xlsx/h4/impairment/h4-tab-recoverable
  ├── composables/useH6DualMode.ts            ← 🔴 跨到 lane 3（H6）
  └── composables/useH8DualMode.ts  (生产消费 2)
        ├── h8/impairment/H8TabRecoverable.vue  ← 子入口 xlsx/h8/impairment/h8-tab-recoverable
        │                                          🔴 父宿主 GtH8RightOfUseAssets.vue 内联自己的实现
        └── composables/useH9DualMode.ts       ← 🔴 跨到 foundation（H9 canary）
              └── GtH9LeaseLiabilities.vue       （实测生产消费 1，非孤儿）
```

**设计含义**：

1. 改 `useH4DualMode` = 同时影响 **H4 / H6 / H8 / H9 四条 entry + 3 条子入口**。
   ⇒ 任何改动必须在本 spec、`h2-h6-h10-pilot-cross-reference-lanes`、foundation 之间协调。
2. 🔴 `h8-tab-recoverable` 是**唯一「父宿主不用、只有子 Tab 用」的形态**：
   父宿主 `GtH8RightOfUseAssets.vue` 内联自己的持久化（`host_inline` 族），
   `useH8DualMode` 只被子 Tab 与 `useH9DualMode` 用 ⇒
   按「删 composable + 改宿主」常规套路走会**完全漏掉这条子入口**。
3. `useH9DualMode` 实测被 `GtH9LeaseLiabilities.vue` 消费（**slice 记零消费是错的**）⇒
   它在 canary 链路上，本 spec **不得删**。

### 「一并改」清单（改线时逐项勾）

| 序 | 文件 | 角色 | 归属 spec |
|---|---|---|---|
| 1 | `GtH4EngineeringMaterials.vue` | H4 父宿主 | 本 spec |
| 2 | `h4/impairment/H4TabImpairment.vue` | 子入口 | 本 spec |
| 3 | `h4/impairment/H4TabRecoverable.vue` | 子入口 | 本 spec |
| 4 | `composables/useH4DualMode.ts` | 链根 | 本 spec（需 3 方协调） |
| 5 | `composables/useH8DualMode.ts` | 链中 | 本 spec（需 3 方协调） |
| 6 | `h8/impairment/H8TabRecoverable.vue` | 子入口 🔴 易漏 | 本 spec |
| 7 | `h8/measurement/*`（annual / monthly 两条子入口的载体） | 子入口 | 本 spec |
| 8 | `composables/useH6DualMode.ts` | 链中，跨 lane | `h2-h6-h10-pilot-cross-reference-lanes` |
| 9 | `composables/useH9DualMode.ts` | 链尾，跨 spec | foundation（canary） |

判据：现算 `useH4DualMode` 消费点 == 5、`useH8DualMode` 消费点 == 2；
改线后对 5 条子入口逐条断言双向链路独立可验。

## 二、BP-5 修复方案（H8 写进零消费方 item_id）

**现状**：`GtH8RightOfUseAssets.vue#L588` 把四表明细种子写进 `H8-2-detail-prefill`。
该字面量全仓命中 **1**（= 写入点自己），真库**零载荷**，且**无对应 total 键**。
真实主键是 `H8-2-rows`（生产命中 12，真库为 `[]`）。

**修复**：写入目标改为 `H8-2-rows`。

**与 H7 正常情形的区分判据**（HC-6，混用会把 H7 误判成缺陷）：

| 特征 | BP-5（`H8-2-detail-prefill`） | H7 正常（`H7-2-cost-rows`） |
|---|---|---|
| 生产命中 | 1（写入点自己） | 1（写入点自己） |
| 有对应 total 键 | ❌ **无** | ✅ `H7-2-cost-total` |
| 被交叉勾稽读取 | ❌ 无任何读取方 | ✅ `useH7CrossSheet.ts#L52 getNum('H7-2-cost-total')` |
| 真库载荷 | ❌ 零载荷 | 零载荷（但勾稽走 total 键，不依赖明细键落库） |
| 判定 | **缺陷** | **正常** |

🔴 **判据必须同时看「有无对应 total 键」与「有无读取方」**，只看生产命中数会误判。

**联动**：`#L578` 的 `seed-${idx}`（BP-6）在同一段种子代码里 ⇒ **一次改完**，不留中间态。

## 三、BP-6 修复方案（种子行身份取数组下标）

**本 lane 2 处**：`h4DetailPrefill.ts#L50` `seed-${idx}` · `GtH8RightOfUseAssets.vue#L578` `seed-${idx}`。
（第三处 `GtH2ConstructionInProgress.vue#L616` `` `seed-${i}` `` 在 H2，归 lane 3。）

**目标形态**：对齐 HC-7 族 A，参照同仓已有安全实现
`useH8Adjudication.ts#L145` `h81-${block}-${category}-${Math.random().toString(36).slice(2,7)}`
（真库实证 `h81-cost-房屋及建筑物-ya2jc`）。

**迁移映射需求判定**：

- 现算真库：`H4-2-rows` **无行**、`H8-2-rows` = `[]` ⇒ **无既有 `seed-*` 数据**
  ⇒ 本 lane BP-6 迁移风险**低**，可省略映射。
- 🔴 但判据 SHALL **现算确认**后才可省略；若现算发现任何 `seed-` 前缀落库，迁移映射变为**必需**。

**后端无关**：H 的四表种子 prefill **后端零参与**
（`prefill_formula_mapping.json` 306 条 mappings 中 H 命中 24 条但 `sheet` 全为 None；
`prefill_anchor_map.py` 691 行 / `prefill_engine.py` 1658 行的 H 字面量命中 0）⇒ 只改前端。

**完成断言**：全 H `` rowId:`seed-${ `` 形态命中从 3 → **1**（剩 H2）；lane 3 完成后 → **0**。

## 四、BP-7 修复方案（唯一背离 H7 动态列范式的地方）

**现状**：`h8DisclosureSyncPayload.ts#L51` `cats.map(c => ({ key: c.label, … }))` +
`#L110` `row[c.label] = …` ⇒ 把稳定动态列 key 降级成**可变 label**。

**为什么是缺陷**：H7 的范式（`h7_stable_slot_seq_key`）正是为
「源模板 `H7 生产性生物资产.xlsx!附注披露信息（上市公司）` 两级表头下四个产业的默认叶子列名
都是同一字面 `类别`（`H7_DEFAULT_CATEGORY_LABEL`）」而创 —— **label 作 key 必然四列撞成一列**。
BP-7 在 H8 附注边界把这个教训退回去了。

**修复**：改为稳定 key（`{prefix}{seq}` 形态），label 只作展示字段。
修后须满足 lane 1（`h3-h5-h7-variant-axis-and-dynamic-column-paradigm`）的 **SK-1 判据**。

**迁移评估**：现算 H8 附注相关键真库载荷 —— 实测 `H8-listed-categories` **137 B**（有数据）·
`H8-listed-movement` = `[]` ⇒ 🔴 `H8-listed-categories` 已落库，
若其中存的是 label 作 key 的结构 THEN **label→key 迁移映射为必需**；判据须先解析该 137 B 载荷确认。

**完成断言**：全 H「背离 H7 范式的地方」从 **1 处 → 0 处**（lane 1 的 HV-P4 断言本 lane 外为 0，
本 spec 的 HS-P 断言修完后全 H 为 0）。

## 五、H4 footer 第三形态与列边界

**footer R28 实测**（HC-16 第三形态，**非纯 SUM**）：

| 列 | 公式 | 性质 |
|---|---|---|
| F | `=G28/E28` | 派生单价（合计口径） |
| I | `=J28/H28` | 派生单价 |
| L | `=M28/K28` | 派生单价 |
| O | `=P28/N28` | 派生单价 |
| 其余合计列 | SUM 族 | 常规 |

**行内同型**：`F=G12/E12`（R12-27 逐行）⇒ **除零风险**，分母为 0 时须产出空/0，不得 `#DIV/0!`。
同族先例：F4-7 `G=365/(E/F)`。

**契约声明**：
```
footer_kind   : "derived_unit_price"        # 🔴 非 pure_sum
derived_footer_columns : ["F","I","L","O"]
derived_row_columns    : ["F","I","L","O"]  # 行内同型
zero_divisor_guard     : true               # 分母 0 → 空/0
effective_columns      : 49                 # 🔴 max_column 是 67，两者不等
uuid_column            : 50                 # 有效列 49 + 1（HC-13），不得放 68
header_rows            : [8,9,10,11]        # 四级表头
data_rows              : [12,27]
footer_row             : 28
```

判据：变异「按 `pure_sum` 校验 H4 footer」SHALL 打红；
变异「UUID 放 68（max_column+1）」SHALL 打红。

## 六、H8 重负载处置

### per-file 中性化（HC-12）

| 册 | 裸 IF | 主来源 |
|---|---|---|
| H8 | **3710**（全平台最多） | `使用权资产 租赁负债初始及后续计量（按月）H8-6`（361r×16c / **3626 公式**） |
| H4 | 48 | — |

🔴 两者差 **77 倍** ⇒ 必须 per-file 挂 `oo_crash_neutralization_fn`，整册统一挂 SHALL 打红。

### H8-6 双 sheet 与两条子入口的对应

| sheet 全名 | 几何 | 对应子入口 |
|---|---|---|
| `使用权资产 租赁负债初始及后续计量（按年）` | 61r × 17c / 263f | `xlsx/h8/measurement/h8-tab-measurement-annual` |
| `使用权资产 租赁负债初始及后续计量（按月）` | 361r × 16c / **3626f** | `xlsx/h8/measurement/h8-tab-measurement-monthly` |

按 HC-5 用 `period_granularity` 轴（`annual` / `monthly`）**或** sheet 全名声明。

🔴 **HC-15 风险 ③ 登记**：`wp_index` 记 `H8-6` 为「使用权资产调整分录」，
模板实测 H8-6 是上表两张 ⇒ 同一子码在两处指不同对象。
契约 SHALL 用**模板 sheet 全名**消歧；该冲突**待平台侧修正**，本 spec 不修 wp_index。

### 列边界（HC-13）

| sheet | max_column | 有效列 | UUID 落位 |
|---|---|---|---|
| H8 `明细表H8-2` | 58 | 58（全 H 最宽主表，17 公式列） | 59 |
| H8 国企侧附注披露 | 255 | 6 | 7 |
| H4 `明细表H4-2` | 67 | 49 | 50 |
| H4 附注披露 ×2 | 254 / 254 | 6 / 8 | 7 / 9 |

（H8 上市侧附注仅 7c，不在宽表之列。）

## 七、两份契约骨架

### `h4.engineering_material_detail.json`

```
entry_id      : xlsx/gt-h4-engineering-materials
provider_id   : phase5_engineering_material_detail
source_ref    : { workbook_sha256: c2c3ee61b33f4a7c…, sheet_name: "明细表H4-2" }
primary_table : { item_id: "H4-2-rows", identity_field: "rowId",
                  header_rows: [8,9,10,11], data_rows: [12,27], footer_row: 28,
                  footer_kind: "derived_unit_price",
                  derived_footer_columns: ["F","I","L","O"],
                  derived_row_columns: ["F","I","L","O"], zero_divisor_guard: true,
                  effective_columns: 49 }
derived_total_keys : <现算；当前现算 15 个，禁写死>
carrier       : { write: "formdata_composable", read: "checklist_get",
                  tb_publish_gate: "composables/useH4Adjudication.ts + h4/core/H4TabAdjudication.vue" }
sub_entries   : ["xlsx/h4/impairment/h4-tab-impairment",
                 "xlsx/h4/impairment/h4-tab-recoverable"]     # GC-1：按 entry_id 不按 wp_code
oo_crash_neutralization_fn : <per-file，本册裸 IF 48>
uuid_column   : 50
```

### `h8.right_of_use_asset_detail.json`

```
entry_id      : xlsx/gt-h8-right-of-use-assets
provider_id   : phase5_right_of_use_asset_detail
source_ref    : { workbook_sha256: 112053f0681642c3…, sheet_name: "明细表H8-2" }
primary_table : { item_id: "H8-2-rows", identity_field: "rowId",
                  header_rows: [8,9,10,11], data_rows: [12,31], footer_row: 32,
                  footer_kind: "pure_sum", effective_columns: 58,
                  formula_column_count: 17 }
forbidden_keys     : ["H8-2-detail-prefill"]       # 🔴 BP-5 修复后必须为 0 命中
variant_axis       : { period_granularity: ["annual","monthly"] }   # H8-6，HC-5
derived_total_keys : <现算；当前现算 21 个（🔴 全 H 最多），禁写死>
derived_fields     : []            # H8 侧派生标记；H9 的 terminatedFromH8 由 H8 写出
carrier       : { write: "host_inline", read: "render_config_force_component_type",
                  tb_publish_gate: null }          # 🔴 无发布门（HD-7 缺口）
sub_entries   : ["xlsx/h8/impairment/h8-tab-recoverable",
                 "xlsx/h8/measurement/h8-tab-measurement-annual",
                 "xlsx/h8/measurement/h8-tab-measurement-monthly"]
frozen_cross_ref : ["H9-2-rows"]    # HC-8：H8 侧消费，改它会打断 H8
oo_crash_neutralization_fn : <per-file，本册裸 IF 3710>
uuid_column   : 59
```

## 八、Property（HS-P）

| # | Property | 引用 |
|---|---|---|
| HS-P1 | `useH4DualMode` 消费点 == 5、`useH8DualMode` == 2；改线漏点打红 | Req 2.1 |
| HS-P2 | 5 条子入口逐条双向链路独立可验（含最易漏的 `h8-tab-recoverable`） | Req 2.3 |
| HS-P3 | 子入口 representation pointer 用 `entry_id`；用 wp_code 打红（`H4T`/`H8T` 必撞） | GC-1 |
| HS-P4 | BP-5 修后 `H8-2-detail-prefill` 全仓命中 == 0 | Req 3.1 |
| HS-P5 | BP-5 判据同时看「有无 total 键」与「有无读取方」；H7 不被误判 | HC-6 |
| HS-P6 | BP-6 修后全 H `seed-${` 命中 3 → 1；迁移映射需求经现算判定 | Req 4 |
| HS-P7 | 后端 prefill 侧无需同步改动（H 字面量 0） | Req 4.5 |
| HS-P8 | BP-7 修后全 H 背离 H7 范式处 == 0；满足 SK-1 判据 | Req 5 |
| HS-P9 | `H8-listed-categories` 137 B 载荷解析后判定 label→key 迁移需求 | Req 5.4 |
| HS-P10 | H4 `footer_kind == derived_unit_price`；按 pure_sum 校验打红 | HC-16 |
| HS-P11 | H4 行内 `F=G12/E12` 族带除零守卫，分母 0 不产 `#DIV/0!` | Req 6.2 |
| HS-P12 | UUID 落位：H4 50（非 68）· H8-2 59 · 宽表按有效列+1 | HC-13 |
| HS-P13 | per-file 中性化计数 == 3710 / 48；整册统一打红 | HC-12 |
| HS-P14 | H8-6 两张 sheet 按 `period_granularity` 或全名可寻址；登记 wp_index 冲突 | HC-5 / HC-15 |
| HS-P15 | H8 `tb_publish_gate == null`（缺口登记，不在本 spec 补） | HD-7 |
| HS-P16 | 可删 == {`useH8FormData`}；`useH8DualMode`/`useH4DualMode` 在禁删名单 | HC-3 |
| HS-P17 | 族 C 2 处修复（`useH4Adjudication.ts#L436` / `useH8Adjudication.ts#L572`）；`#L145` 不改 | HC-7 |
| HS-P18 | `H9-2-rows` 键名未改（H8 侧消费冻结） | HC-8 |
