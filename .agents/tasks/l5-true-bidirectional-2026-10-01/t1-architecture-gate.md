# L5 长期应付款 真双向改线 — T1 三区 Spec 架构硬门坐实

> task `l5-true-bidirectional-2026-10-01` · 第一步 T1。只读调查，不改代码/契约/库，不提交。
> 依据可行性报告 `.agents/tasks/l5-d1-feasibility/report.md`（§六 T1 + §七 身份常量 + §八 风险）。
> 探针（用完即删）：`backend/scripts/analyze/_l5p_t1_architecture_gate.py` + `_l5p_t1_merge_dryrun.py`。
> 参照范式实读：`phase5_g9_02_detail.py` / `phase5_g9_other_noncurrent.py` / `phase5_g9_store_facade.py` /
> 框架层 `phase5_row_table_sheet.py` / materialize 入口 `excel_materialize.py`。

---

## 判定：✅ 候选 C（三区同键）成立

受管表 `明细表L5-2`、科目 2701、`amount_kind=balance`（负债类余额口径，期末=期初+贷-借）。
三个 `RowTableSheetSpec`（R11:15 / R18:22 / R24:24）**共享** `store_item_id='L5-L5-2-rows'`，
用 `row_section_field='section'` + 各段 `row_section_value` 区分，行身份字段 `key`。
全部硬门证据现算通过，**无需引擎扩展，无需退候选 B**，**绝不退候选 A（删小计折叠）**。

---

## 一、模板哨兵核对

| 项 | 值 |
|---|---|
| 文件 | `backend/wp_templates/L/L5 长期应付款.xlsx`（67,514 B） |
| 实测 SHA256 | `09380626107dc1b975662eaa60fa99ec541901c0729bb0d2b35bbb60807a9b68` |
| 冻结哨兵 | `09380626107dc1b975662eaa60fa99ec541901c0729bb0d2b35bbb60807a9b68` |
| 结论 | ✅ 相等，作 `TEMPLATE_SHA256`（PRE_SANITIZE；若 T5 需净化另算） |

`sheet='明细表L5-2'` `max_row=35` `max_col=30(AD)`。

---

## 二、三区 UUID 列最终选位：AD / AE / AF（✅ 全空坐实）

数据区 R11~R25 逐格实测，三候选列全空：

| 列 | R11:R25 实测 |
|---|---|
| **AD** | 空 ⇒ 区① `saleLeaseback` 的 `uuid_col` |
| **AE** | 空 ⇒ 区② `installment` 的 `uuid_col` |
| **AF** | 空 ⇒ 区③ `other` 的 `uuid_col` |

> 注：AD 是物理 `max_col=30` 的最后一列（业务列用到 AC 备注，AD 已空）。AE/AF 在 max_col 之右，
> instrumentation 需扩列（与 G9 的 AC/AD/AE、F3-7 的 S/T/U 同型，框架层已支持 uuid 列超 max_col）。
> 三区各带独立 `uuid_col` 是 G9 范式的硬要求（配对靠 uuid_col 把 spec 与同 sheet 多 table 一一对应）。

**最终选位：AD / AE / AF。** 无需启用备选。

---

## 三、三区几何坐实（R11:15 / R18:22 / R24:24）

| 区 | section_value | 分组标题（静态骨架） | 数据区 | last−first | 小计/合计（静态骨架） | uuid_col | template_id |
|---|---|---|---|---|---|---|---|
| ① 售后租回 | `saleLeaseback` | A10='售后租回业务形成的融资' | **R11:15** | 4 | A16='小计' `B16=SUM(B11:B15)` | AD | L52R1 |
| ② 分期付款 | `installment` | A17='分期付款方式购入固定资产' | **R18:22** | 4 | A23='小计' `B23=SUM(B18:B22)` | AE | L52R2 |
| ③ 「…」 | `other` | A24='…'（兼输入行） | **R24:24** | **0** | — | AF | L52R3 |
| 合计 | — | — | — | — | A25='合计' `B25=SUM(B16,B23,B24)` | — | — |

两级表头 `header_group_row=8` / `header_leaf_row=9`。
`footer_row`：区① 16 / 区② 23 / 区③ 25（合计行作第三段 footer）。

---

## 四、🔴 两个 G9 没有的边角几何 — 引擎行为证据（硬门核心）

### 4.1 单行第三段（R24，last−first=0）

G9 第三段是 R26:28（三行，last−first=2），L5 第三段只有 R24 单行（last−first=0）。实测引擎行为：

- **`formula_mask` 对 first==last 产出合法单格区间**：区③ mask =
  `('E24:E24','L24:L24','M24:M24','N24:N24','O24:O24','R24:R24','S24:S24')`。
  `RowTableSheetSpec.formula_mask` 是 `{col}{first}:{col}{last}`，单行退化为单格区间 —— 合法，
  引擎**无任何「数据区至少 N 行」的假设**。
- **`iter_store_rows` 按 section 过滤，与行数无关**：一份含三段的数组，区③ 只 yield 本段 1 行
  （`l52-u-ddd`）。section 过滤在 identity 校验之前，不会把别段行算进 `seen`。
- **`build_store_projection` 单行第三段只投本段 1 行**：`row_keys['l5_detail_rows_other']==('l52-u-ddd',)`，
  不崩、不多投、不空投。
- **`merge_projection_into_store_rows` 单行第三段**：非本段行原样保留 + 第三段既有行回写 +
  **第三段新增行被补 `section='other'`**（与 iter 过滤成对，OO 侧在区③插的行回前端不落错区）。
- **三区同键穿线合并**（照 `phase5_g9_store_facade`：上段 merged 作下段 base_rows）：三段各自改动都在、
  section 归属不丢、无丢行无重复。

⇒ 单行第三段在 projection / merge / iter 全链路**与行数解耦**，不构成障碍。

### 4.2 非连续 SUM footer（`=SUM(B16,B23,B24)`）

G9 合计 `=SUM(C17,C24,C29)` 已是枚举相加（非连续区间 SUM），L5 合计 `=SUM(B16,B23,B24)` 同型。
实读 `excel_materialize` 坐实其行为：

- materialize 的 footer 归一化**只重写** `_GT_SYNC` 隐藏表里的**行号键**
  （`GT_FOOTER_ROW` / `GT_FOOTER_ROW_<TID>`）与 Excel Table `ref` 的**行分量**；
- 它**不解析也不重写** footer 单元格里的 SUM operand 列表 —— `=SUM(B16,B23,B24)` 作 substrate 原样保留；
- 且归一化**仅在 `plan.row_shift`（真实插行）时触发**（`_grow_managed_table_ref` 入口）。
  等行数往返不插行 ⇒ 该函数不 fire ⇒ 非连续 SUM 原样幸存。

⇒ 非连续 SUM footer 与 G9 的枚举 SUM 合计同型，对三区同键引擎**不构成障碍**。合计行 R25 作静态骨架
（不进受管数据区、不进 footer 公式归一化区），靠 `is_template_skeleton_identity` 不被当 stale 删。

> 🔴 T7 真 OO 往返仍须专门断言：三区受管区**等行数往返不插行**时 R25 合计公式原样 `=`；
> 若 T2+ 受管区扩行（真实插行），须验 `_grow_managed_table_ref` / footer 行号键归一化不打坏 R25，
> 且不打坏 L5-3 的 A 列 `='明细表L5-2'!A{n}` 跨 sheet 镜像引用（报告 §四）。本 T1 不插行、不越界。

---

## 五、公式列同形 + 账龄小计不对称（旁证，与报告一致）

- **7 公式列全 11 输入行同形**（E/L/M/N/O/R/S），R11 / R18 / R24 逐行只换行号：
  `E==B{r}-C{r}+D{r}` · `L==B{r}+F{r}+G{r}` · `M==C{r}+H{r}+J{r}` · `N==D{r}+I{r}+K{r}` ·
  `O==L{r}-M{r}+N{r}` · `R==L{r}-P{r}` · `S==O{r}-Q{r}`。⇒ `formula_columns=("E","L","M","N","O","R","S")`
  整列区间 mask 直接成立，无 L8 那种跨行派生异形，无需引擎扩展、无 warning 退路。
- **账龄 T~X 小计不对称**（模板既有）：`T16/U16/T23/U23` 空（6个月以内 / 6-12月 两桶小计无公式），
  `V/W/X` 的 16/23 有 `=SUM(...)`。账龄列作 editable、小计行作静态骨架即可，不影响受管区。
  账龄用 `AgingLayout.flat` + 单组 5 桶（`T8` 组标题），叶子标签用模板全角字符（`２～3年` 的「２」、
  `1～2年` 的「～」为全角）。

---

## 六、与 G9 三区同键范式逐项对齐确认（照抄对象）

实读 `phase5_g9_02_detail.py` + `phase5_g9_other_noncurrent.py` + `phase5_g9_store_facade.py`，
L5 候选 C 与 G9 范式逐项对应（不是新架构裁决点，是照抄 G9）：

| 维度 | G9 | L5（候选 C） | 对齐 |
|---|---|---|---|
| 三个 `RowTableSheetSpec` 共享 `store_item_id` | `G9-detail-rows` | `L5-L5-2-rows` | ✅ |
| `row_section_field` + 各段 `row_section_value` | `section`：main/mandatory_fvtpl/designated_fvtpl | `section`：saleLeaseback/installment/other | ✅ |
| 共享 `sheet_key`（否则产出同 excel_name 两条） | `g902-managed` | `l52-managed` | ✅ |
| 逐区独立 `template_id` 后缀（instrumentation definedName 唯一） | G92R1/R2/R3 | L52R1/R2/R3 | ✅ |
| 逐区独立 `uuid_col` | AC/AD/AE | AD/AE/AF | ✅ |
| 逐区独立 `footer_row` | 17/24/29 | 16/23/25 | ✅ |
| 合计行枚举 SUM（非连续区间） | `=SUM(C17,C24,C29)` | `=SUM(B16,B23,B24)` | ✅ |
| store 门面「遍历三段」（build/merge/iter + split_by_section） | `phase5_g9_store_facade` 穿线合并 | 同构（本探针干跑坐实） | ✅ |
| `managed_row_table_specs()` / `section_specs()` / `all_store_item_ids()` 去重后 1 键 | ✅ | 照搬 | ✅ |
| 两级表头 group/leaf | R9/R10 | R8/R9 | ✅ |
| 幽灵行防护锚点 | `ghost_row_anchor_index=1`（B 列投资项目，A 列是枚举） | L5 A 列是债权人名称（真业务名）⇒ 锚点 `[0]`（T2 核） | ⚠️ 差异（见下） |

> ⚠️ 唯一差异（非障碍）：G9 的 `[0]` 列是枚举 `category`（R12/R19 模板预填值）故锚点改 `[1]`；
> L5-2 的 A 列是债权人名称（真业务名、R11~R22 待录入、R24 模板占位「…」），锚点取 `[0]` 更贴切。
> **T2 须现算核对**：R24 的 A 列「…」占位是否会让幽灵行防护误剔第三段真行（若「…」被当空名）——
> 若 R24「…」占位导致单行第三段真行被判幽灵，锚点或占位处置须在 T2 调整并加断言。本 T1 不改字段声明。

---

## 七、T1 结论与放行条件

✅ **候选 C 成立，T1 硬门全部通过。** 后续 T2~T7 照报告 §六实施（本步不做 T2 及以后改动）。

硬门逐条：
1. ✅ SHA256 == 哨兵。
2. ✅ 三区 UUID 列最终选位 **AD / AE / AF**（R11~R25 全空坐实）。
3. ✅ 三区几何坐实（R11:15 / R18:22 / R24:24，小计 16/23，合计 25）。
4. ✅ 单行第三段（last−first=0）在 `formula_mask`/`iter_store_rows`/`build_store_projection`/
   `merge_projection_into_store_rows`/三区穿线合并全链路与行数解耦，无「≥N 行」假设。
5. ✅ 非连续 SUM footer `=SUM(B16,B23,B24)` 不被 materialize 重写（往返不插行即原样幸存；
   materialize 只重写行号键与 Table ref 行分量，不碰 SUM operand）。
6. ✅ 与 G9 三区同键范式逐项对齐（照抄对象，非新架构裁决）。

**无触发 warning 的障碍。** 不退候选 B（三独立 store 键），不退候选 A（删小计折叠）。

### 待 T2+ 现算核对（非 T1 障碍，登记备忘）
- R24「…」占位与幽灵行防护锚点 `[0]` 的交互（§六 ⚠️）。
- T2 HTML 列 (b)：L5DetailRow 加 roll-forward 受管字段 + 5 账龄桶 + `section` 字段，融资属性列标 html_only。
- T7 真 OO 往返：受管区扩行（真实插行）时 R25 合计公式 + L5-3 A 列跨 sheet 镜像引用不被打坏。
