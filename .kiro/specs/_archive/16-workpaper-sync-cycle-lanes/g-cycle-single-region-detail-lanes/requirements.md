# Requirements Document

## Introduction

本 spec 覆盖 G 循环**剩余 9 条 entry**的主受管明细表：**G1 / G3 / G8 / G9 / G10 / G11 / G12 / G13 / G14**
（G2 已在 foundation spec 作 canary 打通；G4/G6 六条与 G5 各有专属 lane spec）。

九条的共同点是**一册一 entry、无 BP-5/7/8 专属阻塞**（除 G1 带 BP-5/BP-9）、模板都是常规行表族。
差异集中在**表头层级（1~3 级）** 与 **五处形态特例**，逐条实测见下。

上游：**`g-cycle-sync-foundation-and-first-canary`** 的 **GC-1 ~ GC-10**（引用、不复述）+ FC-1~FC-13
（FC-3 / FC-8 / FC-11 在 G 不成立或不命中）。

🔴 **Property 编号 spec-scoped**：本 spec `Property N` 读作 **`G1R-P{N}`**（G single-Region）。

🔴 **一份 spec 分九条 lane，不拆九份**：九条共用同一套声明范式（`RowTableSheetSpec` + 单/多区 +
`id`/`rowId`/`rowKey` 三族身份），拆开会把同一范式重复九遍；而五处形态特例（RG-8/9/10/11/12）
恰好需要在同一份 spec 里对照才能看出是特例还是通例。

### 九条 entry 实测（slice + manifest + 真库，2026-09-26）

🔴 **`entry_id` 是持久化键**（`working_paper_sync_entry_state` 主键 / representation pointer / room key 全用它）
⇒ 本表逐条给出全名，声明与判据 SHALL 用 `entry_id` 而非宿主名或幻影码。

| entry_id | 宿主 | 幻影码 | 真码/科目 | `blocked_by`（BP-1~4 之外） | payload（FD-1） | HTTP（FD-2） | 行身份（FD-4） |
|---|---|---|---|---|---|---|---|
| `xlsx/gt-g1-trading-financial-assets` | `GtG1TradingFinancialAssets.vue` | `G1T` | G1 / 1101 | 🔴 **BP-5 + BP-7 + BP-9** | `conclusion_only` | api | `generated_timestamp_string` / `id` |
| `xlsx/gt-g3-dividend-receivable` | `GtG3DividendReceivable.vue` | `G3D` | G3 / 1131 | BP-7 | `conclusion_only` | api | `generated_timestamp_string` / `id` |
| `xlsx/gt-g8-other-equity-instruments` | `GtG8OtherEquityInstruments.vue` | `G8O` | G8 / 1507 | （无） | `remark_only` | api | prefixed / **`rowId`** |
| `xlsx/gt-g9-other-noncurrent-financial` | `GtG9OtherNoncurrentFinancial.vue` | `G9O` | G9 / 1519 | （无） | `remark_only` | api | prefixed / **`rowId`** |
| `xlsx/gt-g10-trading-financial-liabilities` | `GtG10TradingFinancialLiabilities.vue` | `G10T` | G10 / 2101 | BP-7 | `remark_only` | api | prefixed / **`rowId`** |
| `xlsx/gt-g11-investment-income` | `GtG11InvestmentIncome.vue` | `G11I` | G11 / 6111（**发生额**） | BP-7 | `remark_only` | api | prefixed / `id` |
| `xlsx/gt-g12-net-hedge-gains` | `GtG12NetHedgeGains.vue` | `G12N` | G12 / 6103（**发生额**） | BP-7 | `remark_only` | api | prefixed / **`rowId`** |
| `xlsx/gt-g13-fair-value-changes` | `GtG13FairValueChanges.vue` | `G13F` | G13 / 6101（**发生额**） | BP-7 | `remark_only` | api | prefixed / **`rowId`** |
| `xlsx/gt-g14-credit-impairment-loss` | `GtG14CreditImpairmentLoss.vue` | `G14C` | G14 / 6702（**发生额**） | （无） | `remark_only` | api | 🔴 **`stable_template_row_key` / `rowKey`** |

九条全部：`capability=null` · `legacy_fake_bidirectional` · `adapter_id=None` · `mount_count=2` ·
宿主 `bridge=0` / `legacyOO=4` / `notice=3` · TB 发布门**已接 8 条**（G1 未接，见红基线 B5）。
损益类四条（G11/G12/G13/G14）TB 口径是**本期发生额**（`test_g_cycle_formula_presets.PL_CYCLES` 冻结）。

🔴 **BP-7 在 slice 的 `blocked_by` 里出现在 G3/G10/G11/G12/G13 五条**，但 BP-7 正文只展开了 G6-sppi 一处
⇒ 与 `g4-g6` spec 的 G4-main 同款问题：Task 2 SHALL **按值定位**，定位不到就如实登记「slice `blocked_by`
与 BP 正文不一致」，**不得**为对齐 slice 伪造缺陷。

### 九条主受管表几何（openpyxl 逐格实测）

| entry | sheet | store_item_id | 表头 | 数据区 | footer | 有效列 | formula_columns |
|---|---|---|---|---|---|---|---|
| G1 | 明细表G1-2 | `G1-2-rows` | R9/R10 | **三区** R12-16 / R19-23 / R26-28 | 小计 R17/R24/R29 + 合计 R30 `=SUM(C17,C24,C29)` | 27(A-AA)，max_col 35 | E,H,I,J,L,P,Q,R,U,V,W,Y +**T 仅区①** |
| G3 | 明细表G3-2 | `G3-2-detail-rows` | 🔴 **R9/R10/R11 三级** | 两区 R13-20 / R23-28 | 小计 R21/R29 + 合计 R30 `=C29+C21` | 33(A-AG) | F,M,N,O,P,T,AA,AB,AC,AD,AE,AF |
| G8 | 明细表G8-2 | `G8-detail-rows` | R9/R10 | R11-20 | R21 `SUM(C11:C20)` | 23 | E,H,M,O,P,Q,R,T |
| G9 | 明细表G9-2 | `G9-detail-rows` | R9/R10 | 三区 R12-16 / R19-23 / R26-28 | 小计 R17/R24/R29 + 合计 R30 `=SUM(C17,C24,C29)` | 28 | E,H,I,J,L,P,Q,R,U,V,W,Y |
| G10 | 明细表G10-2 | `G10-detail-rows` | R9/R10 | R11-20 | R21 | 19 | E,G,K,L,M,O |
| G11 | 明细分析表G11-2 | `G11-detail-rows` | R9 单级 | R10-30 | R31 `SUM(D10:D30)` | 13 | F,G,J,K,L |
| G12 | 明细表G12-2 | `G12-hedge-detail-rows` | 🔴 **无表头行**（R9 即数据） | R9-13 | R14 | 10 | G,I |
| G13 | 明细表G13-2 | `G13-detail-rows` | R9/R10 | R11-20 | R21 `=B11+B14+B17+B19+B20`（只加父行） | 12 | B,C,D,I,J,K |
| G14 | 明细表G14-2 | `G14-detail-rows` | R9/R10 | R11-19 | R20 `SUM(B11:B19)` | 13 | D,J,K,L |

**真库载荷**：`G9-detail-rows` **605 B / 2 wp**（九条最大）· 其余七条各 **2 B**（空数组 `[]`）·
`G1-2-rows` / `G3-2-detail-rows` **零行**。非主表大载荷：`G1-note-listed-store` 4,899 B ·
`G11-adj-rows` 2,480 · `G13-disclosure-listed` 940 · `G14-disclosure-listed` 757。
⇒ 只有 **G9** 可不 seed；其余八条验收须 seed。

### 🔴 红基线（实测，非本 spec 引入）

**B1 · 五处形态特例（同一份 spec 内对照才看得出是特例）**

| 特例 | 实测 | 同族先例 |
|---|---|---|
| **G12-2 无表头行** | R9 即第一行数据（`A:预期销售和预期采购的外汇净头寸`）；合计 R14 的 `I=SUM(I7:I13)` **起点 R7 在数据区之上** | F2-55 footer SUM 起点异常族 |
| **G13-2 父子行** | R11 父 = `B12+B13` 子；合计 R21 `=B11+B14+B17+B19+B20` **只加父行**（不是 SUM 区间） | F4-9 / F5-1 「小计相加」族 |
| **三处布尔校验列** | `G12-2!G = =D9=SUM(E9:F9)` · `G13-2!K = =J11=D11` · `G14-2!L = =D11=K11` ⇒ 求值为 TRUE/FALSE | F5 除零的 `type_normalization_failure` 族 |
| **G11-2 占比列引合计行** | `G/K = =IF(F10=0,0,F10/$F$31)` 引**合计行 F31**；R31 自引 `IF(F31=0,0,F31/$F$31)` | 无先例（G 独有） |
| **G8-2 行级 mask** | R11/R12/R13 公式集**互不相同**（R11 有 R+T · R12 有 R 无 T · R13 有 T 无 R；`M` 区间 R11 `SUM(I11:L11)` vs R12 `SUM(I12:K12)`） | F3-H4 行级 mask 族 |

**B2 · G1-2 区① 独有跨表公式列**

`G1-2!T12 = ='公允价值测试表G1-6'!H10-'明细表G1-2'!R12`（区① R12-16 五行同型），
而**区②③ 的 T 列无公式**（手填）⇒ 行级 mask 差异；G9-2 与 G1-2 几何近同构但**无 T 跨表列** ⇒
两条不得共用同一套 `formula_columns`。

**B3 · G1 带 BP-5 / BP-7 / BP-9 三条（九条里最重）**

BP-5（sheet 标签表 5 条错名）由 **foundation spec 修**；BP-9（`useG1DualMode.ts` 跨 G1-E1 共用）由
foundation **登记不动**；BP-7 须本 spec 按值定位。

**B4 · G14 是全 G 循环唯一 `stable_template_row_key`**

`useG14Detail.ts#L61` 的 `G14_LINE_ITEMS` 是源模板固定行集（行集不由用户增删）⇒ 身份字段 `rowKey`。
🔴 F 循环守卫写死 `row_identity_key in ('rowId','id')` 会把它判违规，而它恰是**最稳**的一族（GC-6）。

**B5 · G1 未接 TB 显式发布门**（= foundation RG-6 的三家之一）

`useG1Adjudication.ts`(673 行) `publishToTb`=**0** / `trial-balance`×2 / `writeback`×5，
另有专属测试 `g1AdjudicationWriteback.spec.ts` ⇒ 归 foundation GC-9 裁决，本 spec **依赖其结论**。

**B6 · 裸 IF：九册全命中，主受管表命中一张**

G1 141 / G3 36 / G8 24 / G9 84 / G10 56 / G11 114 / G12 14 / G13 22 / G14 22。
🔴 主受管表自身命中的只有 **G11-2（44 格）**（其余八张主表零命中）；但中性化是 **per-file** ⇒ 九册全挂（GC-2）。

**B7 · G3 约 480 个 definedName**

整本 legacy 工作簿命名区域残留（`_xlnm.Database` / 大量 `UFPrn*` / 中文名如「存货93期初」）⇒
G3 受管前须确认 instrumentation 不误伤命名区域（其余八册为 0）。

**B8 · prefill 两块 sheet 名错位已由 foundation 修**

块 `[169]` `明细分析表G13-2` → `明细表G13-2` · `[170]` `明细分析表G14-2` → `明细表G14-2`
（G11 的 `明细分析表G11-2` 才是真名）⇒ 本 spec **依赖 foundation Task 7 已修**，只做不回归断言。

**B9 · BP-10 的本 spec 份额**：`G1-2-rows` **8 处**（全 G 最多）· `G10-detail-rows` 6 · `G11-adj-rows` 6 ·
`G2-1-rows` 5（G2 归 foundation）⇒ 本 spec 需收敛 `G1-2-rows` / `G10-detail-rows` / `G11-adj-rows` 三键。

**B10 · 四张 `-修订前` hidden 残留全在本 spec 的册里**

`投资收益实质性程序表G11A-修订前`(34r) · `净敞口套期收益审计程序表G12A-修订前`(63r) ·
`公允价值变动收益审计程序表G13A-修订前`(46r) · `信用减值损失审计程序表G14A -修订前`(46r，**名中带空格**)
⇒ 排除清单须逐字取名（空格不得 strip）。

## Requirements

### Requirement 1: 九条 entry 的声明范式与三族行身份

1. WHEN 声明任一条 THEN SHALL 用 `RowTableSheetSpec`；`store_item_id` / `row_identity_key` 逐条**按值取**
   （不得按编号推演）：`id` 3 条（G1/G3/G11）· `rowId` 5 条（G8/G9/G10/G12/G13）· **`rowKey` 1 条（G14）**。
2. 🔴 WHEN 声明 G14 THEN `row_identity_key="rowKey"`、行集取 `useG14Detail.ts#L61` 的 `G14_LINE_ITEMS`
   （源模板固定行集，用户不增删）；判据变异「把 `rowKey` 判违规」⇒ 必红（GC-6：它是最稳的一族）。
3. WHEN 声明 G1/G3（`generated_timestamp_string`）THEN SHALL 按值核其 id 生成是否带随机后缀；
   🔴 若是纯 `Date.now()` ⇒ 同毫秒连加两行会撞 id（F2 同型已实证）⇒ SHALL 修为带随机后缀或 UUID。
4. WHEN 声明 payload `json_pointer` THEN G1/G3 是 **`conclusion_only`**（写死 `remark` 会指向恒空列）、
   其余七条是 `remark_only`；判据逐条断言。
5. WHEN 收敛 BP-10 份额（B9）THEN `G1-2-rows`(8 处) / `G10-detail-rows`(6) / `G11-adj-rows`(6) SHALL 收敛为
   单一真源 + 派生别名（照 G6 的 `g6CrossHelpers` 正面样本）；`must_fix_before` = 发布 per-entry contract 之前。

### Requirement 2: 表头层级 1~3 级与多区几何

1. WHEN 声明 G3 THEN 表头是 **三级 R9/R10/R11**（G 循环唯一）；两区 R13-20 / R23-28，小计 R21/R29，
   合计 R30 `=C29+C21`（枚举相加非 SUM 区间）；判据变异「按两级表头声明」⇒ 数据区起点错位必红。
2. WHEN 声明 G11 THEN 表头 **R9 单级**、数据 R10-30（21 行，九条最长）、footer R31。
3. 🔴 WHEN 声明 G12 THEN **无表头行**（R9 即数据）⇒ `header_row` SHALL 显式声明为「无」或指向 R8 之前的
   锚定方式（同 G6-5 形态）；判据变异「把 R9 当表头」⇒ 丢第一行数据必红。
4. WHEN 声明 G1 / G9 三区 THEN 三区各自 `field_specs`；🔴 **G1 区① 的 T 列有跨表公式而区②③ 无**（B2）⇒
   行级 mask 处置（F3-H4 族）；G9 **无 T 跨表列** ⇒ 两条**不得共用** `formula_columns`（判据断言两者不等）。
5. WHEN footer 是「枚举相加」而非 SUM 区间（G1 R30 / G3 R30 / G13 R21）THEN SHALL 登记该形态
   （插行位移规则与 SUM 区间不同，F4-9 / F5-1 同族）。

### Requirement 3: 五处形态特例的处置

1. 🔴 WHEN 处置 **G13-2 父子行**（B1）THEN SHALL 先按值实测前端是否有父子关系字段；
   父行（R11/R14/R17/R19/R20）的 `B/C/D` 列是子行之和 ⇒ 判 `mode=formula` 不得 editable；
   合计 R21 只加父行 ⇒ 受管区 SHALL 不含合计行。
2. 🔴 WHEN 处置**三处布尔校验列**（`G12-2!G` / `G13-2!K` / `G14-2!L`）THEN 判 `mode=formula`；
   判据 SHALL 证明 extract 读回 TRUE/FALSE 时①不抛 ②异常类型为 `type_normalization_failure`
   ③store 中该字段不出现 `TRUE`/`FALSE` 字面量。变异：标 `editable` ⇒ 布尔值进 store 必红。
3. 🔴 WHEN 处置 **G11-2 占比列引合计行**（`=IF(F10=0,0,F10/$F$31)`）THEN 判 `mode=formula`；
   判据 SHALL 证明插行后该绝对引用**仍指向真实合计行**（Excel 会调整 `$F$31` 的行号，须实测而非假设）。
4. 🔴 WHEN 处置 **G12-2 合计 `I=SUM(I7:I13)` 起点在数据区之上** THEN SHALL 实测该 SUM 区间在插行后的位移行为
   并登记（框架层扩张规则按「区间末行 = last_data_row」判定，起点在表头之上是未覆盖形态）。
5. 🔴 WHEN 处置 **G8-2 行级 mask**（R11/R12/R13 公式集互不相同）THEN SHALL 按 F3-H4 行级处置；
   必要时拆多个 spec（如 `g802-r11` / `g802-r12plus`）；判据变异「用 R11 的列集套全区」⇒
   R12 的 `M` 区间被误声明必红。

### Requirement 4: TB 红线、中性化、definedName 与零回归

1. WHEN G1 受管 THEN SHALL 先有 foundation GC-9 的 TB 缺口裁决结论（B5）；本 spec **不独立裁决**。
2. WHEN 任一条受管 THEN FC-9 红线：sync 路径对 `trial_balance` 写次数为 **0**；
   八条已接 `publishToTb` 的仍是唯一入口；损益类四条口径为**本期发生额**。
3. WHEN 九册 materialize THEN SHALL 按 GC-2 挂 `oo_crash_neutralization_fn`（B6；
   证据须写明主受管表自身只有 G11-2 命中 44 格，但中性化是 per-file）。
4. 🔴 WHEN G3 受管 THEN SHALL 先确认 instrumentation 不误伤其约 **480 个 definedName**（B7）；
   判据断言受管前后 definedName 集合逐项不变。
5. WHEN 排除四张 `-修订前` hidden sheet（B10）THEN SHALL 逐字取名（`信用减值损失审计程序表G14A -修订前`
   **名中空格不得 strip**）。
6. WHEN prefill 不回归 THEN 断言块 `[169]`/`[170]` 的 sheet 名仍为 foundation 修后的真名（B8）。
7. WHEN 零回归 THEN 照 GC-10 现算逐项比对，**不断言 digest 集合大小**。
8. WHEN 验收 THEN 只有 **G9**（605 B / 2 wp）可不 seed；其余八条 SHALL seed 并断言载荷非空。

### 不在本 spec 范围

- GC-1~GC-10 裁决本体、BP-5 修、BP-9 登记、GC-9 三家 TB 裁决、prefill 两块改名（均 foundation spec）。
- G2（foundation canary）· G4/G6 六条（`g4-g6-shared-workbook-three-entry-lanes`）· G5（`g5-nested-sections-…`）。
- 9 张审定表（G1-1/G3-1/G8-1/G9-1/G10-1/G11-1/G12-1/G13-1/G14-1）—— 归后置 spec
  `g-cycle-adjudication-sheets-coverage`。
- 9 张调整分录汇总（FC-6 默认 `single_html`，只核）· 各册附注披露 sheet · 参考类 sheet。
- 四张 `-修订前` hidden 残留的**删除**（模板治理债，另立项）· G3 的 480 个 definedName 清理。
- 平台级供给 BP-1~BP-4。
