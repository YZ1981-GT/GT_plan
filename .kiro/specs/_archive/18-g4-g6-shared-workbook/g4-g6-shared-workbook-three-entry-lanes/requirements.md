# Requirements Document

## Introduction

本 spec 覆盖 **G4 债权投资**与 **G6 其他债权投资**各自的 **3 条 entry**（共 6 条）。
两册的共同特征是 **一册服务 3 entry**（`belongs_to_entries` 复数）——这是 G 循环相对 F 循环最深的结构差异，
也是 BP-8（representation entry pointer 互顶）的来源。

上游：**`g-cycle-sync-foundation-and-first-canary`** 的 **GC-1 ~ GC-10**（本 spec 引用、不复述）+
F 循环 FC-1~FC-13（其中 FC-3 / FC-8 / FC-11 在 G 不成立，见 foundation design §FC 适用性重裁）。

🔴 **Property 编号 spec-scoped**：本 spec `Property N` 读作 **`G46-P{N}`**。

🔴 **一份 spec 分六条 lane，不拆六份**：BP-8 的 pointer 互顶、GC-4 的转置形态、RG-1 的 16384 列
三条裁决对 G4/G6 各三条 entry **完全同型**，拆开会把同一裁决重复六遍且互相依赖。

### 六条 entry 实测（slice + manifest，2026-09-26 复核）

| entry_id | 宿主 | `wp_code_pattern` | sheet 段 | `capability_target_blocked_by` |
|---|---|---|---|---|
| `xlsx/gt-g4-bond-investment-main` | `GtG4BondInvestmentMain.vue` | `G4B` | G4A / G4-1~G4-4 | BP-1~4 + **BP-7** + **BP-8** |
| `xlsx/gt-g4-bond-investment-sppi` | `GtG4BondInvestmentSppi.vue` | `G4B` | G4-5~G4-8 | BP-1~4 + **BP-8** |
| `xlsx/gt-g4-bond-investment-ecl` | `GtG4BondInvestmentEcl.vue` | `G4B` | G4-9~G4-13 | BP-1~4 + **BP-8** |
| `xlsx/gt-g6-other-bond-main` | `GtG6OtherBondMain.vue` | `G6O` | G6A / G6-1~G6-4 | BP-1~4 + **BP-6** + **BP-8** |
| `xlsx/gt-g6-other-bond-sppi` | `GtG6OtherBondSppi.vue` | `G6O` | G6-5~G6-10 | BP-1~4 + **BP-6** + **BP-7** + **BP-8** |
| `xlsx/gt-g6-other-bond-investment-ecl` | `GtG6OtherBondInvestmentEcl.vue` | `G6O` | G6-11~G6-15 | BP-1~4 + **BP-6** + **BP-8** |

🔴 **BP-8 六条全带**（`must_fix_before` = 为 G4/G6 任一 entry 发布 authority model 或 published representation 之前）；
**BP-7 命中两条**（G4-main + G6-sppi —— 🔴 注意 slice BP-7 正文只举 G6-sppi 的 `useG6SppiFairValue.ts#L331`，
G4-main 的 `capability_target_blocked_by` 也列了 BP-7 但正文未展开 ⇒ Task 2 须按值定位 G4-main 那一处）。

模板字节锚（slice `authoritative_templates`）：
`G/G4 债权投资.xlsx` = `da3a3480d37a4b95…`（999,788 B / 19 sheets）·
`G/G6 其他债权投资.xlsx` = `63bf38c797d4612e…`（981,008 B / 21 sheets）——两册是 G 目录最大的两本。

### 六条主受管表几何（openpyxl 逐格实测）

| entry | sheet | 表头 | 数据区 | footer | 有效列 | 公式列 | 形态 |
|---|---|---|---|---|---|---|---|
| G4-main | 明细表G4-2 | R9/R10 | **两区** R12-17 / R20-25 | 小计 R18/R26 + 合计 R27 `=SUM(G18,G26)` | 44(A-AR) | J,L,O,S,T,U,V,X,AC,AF,AG | 两区行表 |
| G4-sppi | 有价证券盘点表G4-7 | R13 单级(**B-G**) | R14-22 | **无合计**（R23「三、审计说明」） | 7 | **零** | 最简；A 列空、R9-12 签字区 |
| G4-ecl | 债权投资三阶段划分G4-9 | R9(A/B + G/H/I/J=投资1..X) | — | R24/R32/R46「分析结论」×3 | 11，**max_col 16384** | 零 | 🔴 转置 |
| G6-main | 明细表G6-2 | R9/R10 | 多区（R12-14 小计 R15 起） | 多个小计 | 33 | J,O,Q,U,V,W,X,Y,AD,AF | 多区行表 |
| G6-sppi | 公允价值测试表G6-5 | **无独立表头行**（R9 即数据） | R9-18 | R19 合计 `SUM(D9:D18)` | 18 | D,H,J | 🔴 行级 mask |
| G6-ecl | 其他债权投资三阶段划分G6-11 | R10（R9 是区标题「（一）信用风险是否显著增加」） | — | R25/R33/R47「分析结论」×3 | 11，**max_col 16384** | 零 | 🔴 转置 |

**store 键与行身份**（slice `dynamic_row_identity` + 按值 grep）：

| entry | store_item_id | 行身份 kind | 字段 | source_ref | payload 列（FD-1） | HTTP 客户端（FD-2） |
|---|---|---|---|---|---|---|
| G4-main | `G4-2-rows` | `generated_prefixed_opaque_string` | `id` | `useG4MainDetail.ts#L249` | `conclusion_canonical_remark_mirror` | `api` |
| G4-sppi | `G4-7-items` | 同上 | `id` | `useG4SppiInventory.ts#L87` | `dual_write` | `api` |
| G4-ecl | `G4-9-rows` | `generated_uuid` | `id` | `useG4EclStageClassification.ts#L413` | `dual_write` | **`http`** |
| G6-main | `G6-2-rows` | `generated_prefixed_opaque_string` | `id` | `useG6MainDetail.ts#L256` | `dual_write` | **`http`** |
| G6-sppi | `G6-5-fair-value-data` | 🔴 `generated_opaque_string_with_array_index_fallback` | `id` | `useG6SppiFairValue.ts#L278` | `conclusion_only` | **`http`** |
| G6-ecl | `G6-11-rows` | `generated_uuid` | `id` | `useG6EclStageClassification.ts#L196` | `dual_write` | **`http`** |

🔴 **四条用 `http`（utils/http）而非 `api`（apiProxy）** —— 全 G 循环的 4 条 `http` 全在本 spec（FD-2）；
F 循环守卫的探针 `api\.get\(\s*`[^`]*checklist-responses`` 对这四条**必然失配**。

**真库载荷**：六条主表里 **只有 `G6-2-rows` 有行**（remark 0 / conclusion 2 = 空数组只落 conclusion）；
`G4-2-rows` / `G4-7-items` / `G4-9-rows` / `G6-5-fair-value-data` / `G6-11-rows` **全零行**。
G4 册唯一载荷是 `G4-4-interest-calc`(445 B)；G6 册有 `G6-disclosure-listed-rows`(4,304 B) 等披露键。
⇒ **本 spec 六条 canary 验收全部需要 seed**（与 foundation 的 G2 相反）。

### 🔴 红基线（实测，非本 spec 引入）

**B1 · BP-8：一册三 entry 共用 wp_code_pattern ⇒ representation pointer 互顶**
slice 原文：「若 representation entry_id 只用 wp_code（或 wp_code_pattern），G4 的三条与 G6 的三条会各自
互相顶掉对方的 entry pointer / representation generation。」六条全带，`must_fix_before` 卡 authority model 发布。

**B2 · RG-1：两张 ECL 主表 `max_column` = 16384（XFD）**
`G4-9` / `G6-11` 有效内容列只有 11，但 `max_column` 实测 16384（Excel 绝对上限）⇒
instrumentation 的「UUID 列放 `max_col+1`」**结构上不可能**。同册 `G5-9` 同病（归 G5 lane spec）。

**B3 · RG-2：两张 ECL 主表是转置形态**
表头 `A:需要考虑的信息 | B:说明 | G:投资1： | H:投资2： | I:投资3： | J:投资X：` ⇒ 列是投资项目。
各含**三块**（G4-9 R24/R32/R46 · G6-11 R25/R33/R47 的「分析结论」锚行）。用 `RowTableSheetSpec` 投影恒空。

**B4 · BP-7：行身份退化成数组下标（两条）**
`useG6SppiFairValue.ts#L331` `data.rows.map((r, i) => migrateFairValueRow(r, i + 1))` +
`#L128` 缺 `raw.id` 时 `` `fv-${Date.now()}-${seq}` `` 回退；G4-main 的 `blocked_by` 也列 BP-7 但 slice 正文未展开
⇒ Task 2 须按值定位。`must_fix_before` = 标 bidirectional 之前**且** step 6 发布 contract 之前。

**B5 · FD-2：四条用 `http` 客户端**（G4-ecl / G6-main / G6-sppi / G6-ecl）
守卫 SHALL 按 slice 逐 entry 登记的 `html_counterpart.http_client_binding` **拼探针**，不得二选一硬编码。

**B6 · RG-8：G6-5 行级 mask**（R9/R10 有 D 列公式、R11+ 无）⇒ 矩形 mask 表达不了（同 F3-H4 族）。

**B7 · 两册各带两张「参考」sheet 不接**
G4：`参考-中证协《证券公司金融工具减值指引》`(178r) / `参考-根据剩余期限折算PD`(20r)；
G6：`参考中证协《证券公司金融工具减值指引》`(179r，**无连字符**) / `参考-根据剩余期限折算PD`(20r)。
🔴 两册的第一张名字**只差一个连字符** ⇒ 排除清单不得用同一字面量。

**B8 · G4-main / G6-main 未接 TB 显式发布门**（= foundation RG-6 的两家）
`useG4MainAdjudication.ts`(738 行, `publishToTb`=0 / `trial-balance`×1 / `writeback`×3) ·
`useG6MainAdjudication.ts`(784 行, 0 / ×1 / ×2)。另 TB 键名嵌错码：`G4-1-adj-tb-1501`（真码 1504）·
`G6-1-adj-tb-1503`（真码 1506，且注释写「已纠正为 1505」本身是错的）⇒ 归 foundation GC-9 裁决，本 spec 依赖其结论。

**B9 · 裸 IF：G4 186 格 / G6 192 格**（G 目录最高两本）
G4 分布：附注披露（上市）77 / 审定表G4-1 54 / 附注披露（国企）38 / 合同现金流量特征分析G4-6 9 /
业务模式分析G4-5 5 / **明细表G4-2 2** / 债权投资减值准备测算表G4-10 1。
G6 分布：审定表G6-1 96 / 附注披露（上市）80 / 合同现金流量特征分析G6-8 9 / 业务模式分析G6-7 6 /
其他债权投资减值准备测算表G6-12 1。⇒ 两册按 GC-2 per-file 挂中性化。

**B10 · BP-10 的本 spec 份额**：G4 有 storage contract（`g4StorageContract.ts` 4,220 B）却仍在
`g4CrossHelpers` 重复 4 条字面量（`G4-1-rows` / `G4-9-rows` / `G4-10-rows` / `G4-11-ecl-measurement`）；
G6 **已做对**（`g6CrossHelpers.G6_11_ROWS_KEY = G6_ITEM_IDS.G6_11_ROWS` 派生别名）⇒ G6 是正面样本、G4 照它改。

## Requirements

### Requirement 1: BP-8 落地 —— 六条 entry 的 pointer 隔离与 matcher 互斥

1. WHEN 为任一条发布 authority model / published representation THEN entry pointer 与
   `working_paper_sync_entry_state` 主键 SHALL 用 **`entry_id`**（照 GC-1），不得用 `wp_code` / `wp_code_pattern`。
2. WHEN 三条同码 entry 注册 adapter THEN matcher 域 SHALL 用 `sheet_keys` 互斥（沿用 F2-H1 解法：
   `overlaps()` 任一侧空即重叠；运行时走 `resolve_for_entry(entry_id)`）；判据 SHALL **真跑** `registry.register()`
   证明三条可同时注册、且两两 `sheet_keys` 不相交。
3. WHEN 声明模板归属 THEN SHALL 用 `belongs_to_entries`（复数）；判据断言「owner 并集 == 六条全集」
   且「每条恰被一册认领」（FC-3 的单射在 G 不成立）。
4. WHEN 构造「G4 三条先后发布 representation」THEN 三条的 generation 互不影响；变异用 wp_code 作 pointer ⇒ 必红。

### Requirement 2: 两张 ECL 主表 —— 转置形态 + 16384 列

1. WHEN 声明 G4-9 / G6-11 THEN SHALL 用 **`TransposedSheetSpec`**（`phase5_transposed_sheet.py`，D4-29 先例），
   **不得**用 `RowTableSheetSpec`；判据变异「改用行表」⇒ 投影恒空必红。
2. WHEN 定位实体列 THEN SHALL 逐格实测（G4-9 R9 / G6-11 R10 的 `G:投资1：`~`J:投资X：`）；
   G6-11 另有区标题 R9「（一）信用风险是否显著增加」SHALL 不当作表头。
3. WHEN 处置三块结构 THEN 三个「分析结论」锚行（G4-9 R24/R32/R46 · G6-11 R25/R33/R47）SHALL 按
   `footer_carries_total_formula=False` 的锚行模式声明（E1-10 / D3-4 先例），**不得**当合计行。
4. 🔴 WHEN 处置 16384 列（B2）THEN SHALL 三选一并给出证据，默认①：
   ①按**有效内容列**（11）+1 放 UUID，并证明 16384 列的格式化污染不影响 instrumentation 定位与打印区域
   ②先清列级格式化污染（改权威模板字节 ⇒ 须走覆盖层，代价高）③该表不受管、登记 HTML-only。
5. WHEN 两表数据区公式为零 THEN `formula_columns=()`；判据断言模板侧 7 个公式全在页眉/表头区。

### Requirement 3: BP-7 两处行身份修复（受管硬前置）

1. 🔴 WHEN G6-sppi 或 G4-main 受管 THEN 其载入路径的下标回退 SHALL 已修：缺 `id` 时铸稳定 UUID 并**立即回写**，
   不得出现 `` `fv-${Date.now()}-${seq}` `` 或 `map((r, i) => …(r, i + 1))` 形态。
2. 🔴 WHEN 定位 G4-main 那一处 THEN SHALL **按值 grep 定位**（slice 的 `capability_target_blocked_by` 列了 BP-7
   但正文只展开了 G6-sppi）；若实测 G4-main 无下标回退 ⇒ SHALL 如实登记「slice 的 blocked_by 与正文不一致」
   并给出证据，**不得**为对齐 slice 而伪造一处缺陷。
3. WHEN 旧载荷含下标型 id THEN SHALL 有迁移判据（重铸后 id 不匹配 `^fv-\d+-\d+$` 等模式）。

### Requirement 4: 六条 lane 的接入与 payload 列

1. WHEN 声明每条的 payload `json_pointer` THEN SHALL 逐条取 FD-1 的登记 mode（G4-main
   `conclusion_canonical_remark_mirror` 走 `g4StorageContract.buildCanonicalPayload()` · G6-sppi `conclusion_only` ·
   其余四条 `dual_write`）；写死 `remark` 会让 G6-sppi 指向恒空列。
2. WHEN 守卫探测写入路径 THEN SHALL 按 slice 逐 entry 的 `http_client_binding` 拼探针（B5）；
   变异「对四条 `http` entry 用 `api\.` 探针」⇒ 失配必红。
3. WHEN 声明 G4-2（两区）THEN 两区各自 `field_specs`；🔴 模板 R11/R19 区标题带
   「【预留插行区：在「小计」行之上填写或插入】」+ R41「两类明细为可扩展预留区（每类默认6行）」
   ⇒ SHALL 把该模板自述的插行语义登记为正向证据（G 循环唯一模板自带插行声明）。
4. WHEN 声明 G4-7 THEN 表头 R13 起于 **B 列**（A 列空）/ 数据 R14-22 / **无合计**（footer 指 R23「三、审计说明」+
   `footer_carries_total_formula=False`）/ `formula_columns=()`。
5. WHEN 声明 G6-5 THEN **无独立表头行**（R9 即数据）/ R9-18 / footer R19 / `formula_columns=("D","H","J")`；
   🔴 行级 mask（B6）：`D` 列只在 R9/R10 有公式 ⇒ SHALL 按 F3-H4 的行级处置（必要时拆两个 spec）。
6. WHEN 声明 G6-2 THEN 多区几何 SHALL 由 Task 2 逐格实测补全（本 spec 只实测到 R12-14 小计 R15，其后未逐格）。
7. WHEN 两册的「参考」sheet THEN SHALL 不接；🔴 排除清单**不得**用同一字面量（B7：两册第一张只差一个连字符）。

### Requirement 5: TB 红线、零回归与依赖边界

1. WHEN G4-main / G6-main 受管 THEN SHALL 先有 foundation GC-9 的三家 TB 缺口裁决结论（本 spec **不独立裁决**）；
   TB 键 SHALL 按值取（`G4-1-adj-tb-1501` / `G6-1-adj-tb-1503`），**不得**按科目码推演。
2. WHEN 任一条受管 THEN FC-9 红线：sync 路径对 `trial_balance` 写次数为 **0**。
3. WHEN 两册 materialize THEN SHALL 已按 GC-2 挂 `oo_crash_neutralization_fn`（G4 186 / G6 192 格裸 IF）。
4. WHEN 收敛 BP-10 的本 spec 份额 THEN G4 的 4 条重复字面量 SHALL 改派生别名，照 **G6 的正面样本**（B10）。
5. WHEN 六条验收 THEN SHALL 先 seed（六条主表真库全零或仅空数组）；不得以空表往返收尾。
6. WHEN 零回归 THEN 照 GC-10 现算逐项比对，**不断言 digest 集合大小**。

### 不在本 spec 范围

- GC-1~GC-10 的裁决本体（foundation spec）· BP-5 / BP-6 / BP-9 / BP-11（foundation 或 Task 66/72）。
- 13 张审定表（含 G4-1 / G6-1）—— 归后置 spec `g-cycle-adjudication-sheets-coverage`。
- 调整分录汇总 G4-3 / G6-4（FC-6 默认 `single_html`，只做核）· 两册的附注披露 sheet。
- 不可达旧桩 `xlsx/gt-g6-other-bond-ecl` 的删除（Task 66/72）。
- `G5-9`（同为 16384 列表）归 `g5-nested-sections-and-template-defects`。
- 平台级供给 BP-1~BP-4。
