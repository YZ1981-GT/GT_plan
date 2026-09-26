# Design Document

## Overview

F1 预付账款从 legacy 假双向接成真双向：先打通首张 canary（F1-6 关联方检查表），再按形态驱动顺序扩到
F1-5 / F1-7 / F1-4 区④ / F1-2，最后接 F1-1 审定表；F1-3 只做可行性核。

与 E1 同级 —— **连 provider 都没有**，前半段必须走完整发布链；与 D3 同构 —— 每张 sheet 都有 D3 的对应先例。
与二者都不同的是 F1 带两处**双模式口径分歧**（F1-2 O/X 列、F1-1 取数），它们必须在对应 sheet 受管**之前**
修掉，否则真双向一接通就会让两种模式对同一格显示不同的数。

本文件同时承载 **F 循环共同裁决 FC-1~FC-13**，F2~F5 spec 引用、不复述。

## 上游锚定

| 上游 | 本 spec 消费什么 | 不做什么 |
|---|---|---|
| umbrella `workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 48 | F 循环 slice（`workpaper_sync_f_cycle_manifest_slice.json`）+ `test_task48_f_cycle_migration.py` 守卫 | 不重做 slice；Task 1 只核 slice 是否过期 |
| `d1-sync-row-table-engine-and-d1-coverage` | `RowTableSheetSpec` / `AdjudicationSheetSpec` / `StoreKind` / `AgingLayout` | 不在引擎加 `if is_f1` |
| `e1-sync-coverage-and-first-canary` | 从零 provider 骨架（`phase5_e1_monetary_fund.py` 结构）、宿主接桥范式（E1 Task 10） | 不照抄其 `require_wp_codes` 开关（FC-2） |
| `d3-sync-coverage-via-row-table-engine` | 同构 sheet 的逐张裁决（D3-2/D3-4/D3-5/D3-6/D3-7/D3-1/D3-3） | 不照抄其前端口径（D3-2 与 F1-2 同病，见裁决 F1-H3） |

## F 循环共同裁决（FC-1 ~ FC-13，F1~F5 spec 共用）

### FC-1：F 循环是「连 provider 都没有」的 E1 级起点，前半段必须走完整发布链

实测 8 个 F entry 在 manifest 全为 `capability=single_onlyoffice` / `migration_state=legacy_fake_bidirectional` /
`adapter_id=None` / `html_store="unresolved"`，`working_paper_sync_entry_state` 中 F 循环 **0 行**。
⇒ 每个 F entry 都要：provider 从零建 → 契约生成器 → 发布链五环 → adapter 注册 → 宿主接桥。

### FC-2：matcher 域用幻影码，provisioning 用真码；`assert_entry_selectable` 不留关闭开关

| entry | manifest `wp_code_patterns`（幻影码） | 真码（store 落点实测） |
|---|---|---|
| F1 | `F1P` | `F1` |
| F2 main / special / valuation | `F2I`（三者共用） | `F2` |
| F2 stocktake | `F2S` | `F2` |
| F3 | `F3N` | `F3` |
| F4 | `F4A` 🔴 | `F4` |
| F5 | `F5C` | `F5` |

- 模块 `WP_CODES` 取幻影码（D3P/D4O/D5R 同范式：`assert_entry_selectable` / `build_matcher` 用它），
  provisioner 用 `workpaper_sync_entry_wp_code_adjudication.json` 新增条目的真码。
- 🔴 **E1 的反例（本轮实测）**：`phase5_e1_monetary_fund.WP_CODES = {"E1"}`（真码），而 manifest 是 `["E1M"]`；
  `assert_entry_selectable()` 默认调用对真 manifest **抛 `EntrySelectionError`**，且 E1 测试只断言
  `WP_CODES == {"E1"}`、从不调 `assert_entry_selectable` ⇒ 守卫空转。F 系列 SHALL 不带 `require_wp_codes`
  开关、SHALL 有一条对真 manifest 真调的判据；E1 的问题登记为顺带发现移交 E1 spec。
- 🔴 **F4A 撞真码**：`backend/app/data/wp_code_overrides.json:549` 把 `F4A` 路由到 `f4-accounts-payable`
  （程序表码）。幻影码若被当作 wp_code 在 finder/路由层查询会命中真底稿 ⇒ F4 的「零模板回退」判据
  SHALL 按 `_index.json`（无 `F4A` 条目，实测）而非路由表判定；详见 F4 spec。

### FC-3：一 entry 恰一 template_ref；entry 覆盖不到的册另立新宿主 spec

`entry ↔ template blob` 1:1，`_entry_id` 从宿主文件路径派生且是持久化键（`working_paper_sync_entry_state` 主键
`(wp_id, entry_id)`、room key、`workpaperSyncModeKey` 全用它）。F1/F3/F4/F5 各一册，恰好 1:1；F2 有 11 本 xlsx
（10 本拆分 + 1 本运行时不可达合册 `F2存货.xlsx`，slice BP-8），只有 4 本是 entry 的 template_ref ⇒ 其余 6 本
（F2-16 / F2-18~20 / F2-29~35 / F2-38~44 / F2-52 / F2-61~72）归「需新宿主」另立 spec。否决：改 `_entry_id`
派生规则（持久化键）/ 合册（模板 sha 冻结）。

### FC-4：形态判定用前端三元组，键名按值 grep（含模板化拼接与 dict 字面量两形态）

沿用 E1 裁决 H8 与 D2 E2 教训：`binding_kind` 由 `(store 键, addRow/removeRow, composable 归属)` 决定；
受管区数由 openpyxl 实测的**模板物理段**决定，不从前端键数反推。grep 必须同时覆盖 `'F1-x-rows'` 字面量、
`` `${sheetCode}-rows` `` 模板串（F2 明细 11 张共享 `useF2DetailSheet.dataKey`）、dict 值（`storageKey:` 字段）。

### FC-5：双模式口径以权威模板为准

同一格若 HTML composable 公式与模板 Excel 公式数学不等价，受管后两种模式会显示不同的数。裁决：**以模板为权威**
修前端（OO 模式直接执行模板公式；审计底稿以致同权威模板为准）；修复先于该 sheet 受管；改变业务取数口径的
（如审定表 AJE 来源）先出影响评估再实施。F 循环实测分歧：F1-2（O/X）、F1-1（性质/账龄取数）；F4-2 前端已按
模板对齐（`useF4Detail.ts:301` 注释「源表 K 列以期初未审余额（E）为起点」）—— 可作为正确形态的参照。

### FC-6：五张调整分录汇总表默认 `single_html`

F1-3 / F2-14 / F3-3 / F4-3 / F5-4 宿主均接 `useAdjustmentCentralSync`（按值实测五处）⇒ 与 D1-5/D2-4/D3-3/
D4-4/D5-3/D6-4/D7-3/E1-5 同型，统一引用 `cycle-adjustment-sheets-single-html-adjudication`；各 spec 只做可行性核并留证，
不改生产代码。

### FC-7：「模板无公式、HTML 自动派生」的列不得标 `editable`

F1-5 J 列（`auditedBalance = endBalance − badDebtProvision`）类：模板格是空的、HTML 每次重算覆盖。若契约标
`editable`，用户在 OO 改 J 后回写入 store，HTML 下一次 recalc 即静默覆盖。可选处置：①契约 `mode=auto_source`
（受保护，OO 改动产生受保护字段冲突，`contracts.PROTECTED_MODES`）②provider 在 instrumentation 注入模板公式
（改变权威模板字节 ⇒ 需走模板覆盖层，代价高）。默认取①。

### FC-8：OCR 只在「整表替换 -rows 键」时才构成第二批量写入方

E1 的 7 个 OCR 弹窗是整表替换；F1 的 `F1VoucherCheckDialog.runOcr` 回填**单个弹窗表单**再由用户确认保存单行。
每个 F spec 须按值实测其 OCR 入口的写入粒度，只有整表替换才触发 E1-P16 同款「OO 编辑态禁用 OCR」判据。

### FC-9：TB 发布门红线 —— sync 路径对 `trial_balance` 写次数为 0

F1/F2/F3/F4/F5 审定表均已接 `publishToTb`（按值实测：`useF1Adjudication.ts:552` / `F2TabAdjudication.vue:36` /
`useF3Adjudication.ts:318` / `F4TabAdjudication.vue:218` / `F5TabAdjudication.vue:260`），旧 `f*:writeback-trial-balance`
监听全部移除。受管后 SHALL 保持：OO forcesave → store 合并 → 仅 emit `substantive:adjudicated`，绝不触发 TB 写；
CI 守卫 `check_tb_writeback_no_direct_call.py` / `check_tb_publish_confirm_gate.py` 覆盖新 provider 路径。

### FC-10：百分数单位 —— 前端存「% 数值」而模板格是百分比格式时，禁止直接双向

按值实测（F3 首发，F 各 spec 须逐列核）：前端 `useF3Detail` 的 `interestRate` 标签「票面利率(%)」、
`depositRate`「票据保证金比例(%)」，`calcInterest(principal, ratePct, days) = principal*ratePct/100*days/360`
（`useF3NotPayFormulaEngine.ts:12`）⇒ store 存 **3.5 表示 3.5%**；而模板 `明细表F3-2!J15` 格式 `0%`、`U15` `0.00%`、
`F3-4!G11` `0.00%`（期望**小数 0.035**），且 `F3-4!H11=ROUND(F11*G11,2)` 直接相乘。
`merge._DECIMAL_TYPES` 对 `rate`/`ratio` 只做 Decimal 规范化、**不做 ×100 / ÷100 换算**（按值核 `merge.py:457-508`）
⇒ 直接受管会让 OO 显示 350%、H 列利息放大 100 倍。对照：D5 前端 `discountRate` 存小数（`calcDiscountInterest`
不除 100），与模板 `0.00%` 单位一致，**D5 无此问题**。裁决：凡「前端 % 数值 × 模板百分比格式」的列，受管前 SHALL
二选一 ①前端改存小数（迁移旧数据 + 全部读方同步）②引擎新增 `value_type=percent_points`（投影 ÷100 / 合并 ×100）
—— 默认②（不动业务存储，单点换算、可被判据锁死）；在此之前该列 SHALL 判 HTML-only 或该 sheet 不受管。

### FC-11：prefill 预设的 `items` 型块在运行时是死配置（F3 spec 提出，全循环适用）

全库 308 个 mapping 块中有 **7 个块 `cells` 为空、公式写在 `items` 里**，全部属 F3/F4/F5（`[222]`/`[223]`/`[306]` F3 ·
`[224]`/`[225]`/`[307]` F4 · `[226]` F5 共 26 条公式）。运行时四个消费方**全部只读 `cells`**（按值实测）：
`wp_template_init_service.py:670` 预填写入 xlsx · `preset_library.py:163` 公式管理页预设 ·
`formula_reverse_index.py:294` 反向索引 · `linkage_graph_builder.py:214` 依赖图 ⇒ 这些公式在公式管理页看不到、
不预填、不建边。实证：`convert_prefill_presets()` 现算 `workpaper:F0=2 / F1=33 / F2=78 / F3=18 / F4=18`，**F5 完全缺席**。

🔴 **产生机制在工具链**：`fix_f_cycle_prefill_presets.py._ensure_cells`（L418-L423）在块无 `cells` 键时创建
`block["items"] = []`，且 `--check` 兼容读 `items` ⇒ 脚本造出运行时读不到的键、还报 exit 0「全部到位」。这解释了
三个 F 修复脚本 `--check` 全绿而红测试全红的矛盾。裁决：数据迁移（`items` → `cells`）由各 spec 做自己的块，
**工具链根因只改一次**（F3 spec 负责），并建议加全局 CI 守卫。

### FC-12：manifest 的 `capability` / `html_store` 不是逐 entry 裁决值（slice BP-6）

五份 F spec 的「当前状态实测」表都引用 manifest 的 `capability=single_onlyoffice` / `html_store="unresolved"`。
按值实测：这两个值来自 `workpaper_sync_entry_overlay.json` 的 `defaults_by_component.GtOnlyOfficeSheet`
**组件级默认值**（全 186 条 entry 里 180 条同值），slice 对 8 条 F entry 的重裁结论是
`capability=null` / `html_counterpart_verdict=exists` / `capability_target="bidirectional"` /
`capability_verdict_stage="pipeline_entry_pending_definition_delivery"`。slice 守卫**断言两者必须不一致且已登记**
（断言相等会把 overlay 默认值当裁决真源）。

裁决：各 spec 引用 manifest 值时 SHALL 标明「overlay 组件级默认值」，**不得**为对齐而改 overlay 或 manifest
（皆 source-backed 生成物，手改等于伪造）。BP-6 的 `must_fix_before` 是「Task 67 的 structural pre-reconcile
消费 manifest capability 统计之前」，不卡本批 spec 的 adapter 注册。
🔴 下游后果已实证：BP-9 记 `_f2_stocktake_plan_sync._save_fields` / `_f2_stocktake_summary_sync._save_fields`
两处**生产代码 docstring** 把 lane 选择理由写成「manifest 里 F2 的 entry 是 single_onlyoffice」——
把 overlay 默认值当成了裁决依据。F2 spec 的 stocktake lane 须避免复制该论证方式。

### FC-13：逐 entry 阻塞取 slice `capability_target_blocked_by`，不得跨 entry 套用

按值实测 8 条 F entry 的该字段（同一份 slice，逐条不同）：

| entry | `capability_target_blocked_by` |
|---|---|
| `xlsx/gt-f1-prepayment` | `BP-1..4` |
| `xlsx/gt-f2-inventory-main` | `BP-1..4` + **BP-5** + **BP-7** |
| `xlsx/gt-f2-stocktake-bundle` | `BP-1..4` + **BP-5** + **BP-9** |
| `xlsx/gt-f2-inventory-valuation` | `BP-1..4` + **BP-5** |
| `xlsx/gt-f2-inventory-special` | `BP-1..4` + **BP-5** |
| `xlsx/gt-f3-notes-payable` | `BP-1..4` |
| `xlsx/gt-f4-accounts-payable` | `BP-1..4` |
| `xlsx/gt-f5-cost-of-sales` | `BP-1..4` + **BP-7** |

⇒ BP-1~4（instrumentation / 人工审核契约 / approved bundle / 真 OO 场景集）是**全 8 条共有**的平台级供给缺口；
BP-5 / BP-8 / BP-9 是 **F2 专属**；BP-7 只命中 **F2-main 与 F5** 两条。各 spec SHALL 逐元素断言自己那条，
不得写成「F 循环都有 BP-x」或「本 entry 唯一带 BP-x」。🔴 字段名是 `capability_target_blocked_by`，
slice 中**不存在** `blocking_practices` / `not_bidirectional_because` 这两个键（曾按名引用过，属笔误）。

## Architecture

### canary 链路（前半段，同 E1）

```
Task 1  slice 核对（F 循环 slice 是否过期）+ wp_code 裁决条目（F1P→F1）
Task 2  形态判定 + 几何逐格实测 + 下游消费方 grep 补全
   ↓
Task 7  phase5_f1_prepayment.py（ENTRY_ID / ADAPTER_ID / WP_CODES={"F1P"} / 模板 sha 哨兵 /
        assert_entry_selectable 默认严格 / 灰度开关 / managed_row_table_specs / all_store_item_ids /
        instrumentation_specs 复数 / build_contract_payload / attach_pilot_adapters）
Task 8  phase5_f1_06_related_party.py（canary 薄声明，无 def/class）
   ↓
Task 9  生成器 generate_phase5_f1_contract.py --apply → 契约 f1.prepayment_detail.json
        → approved bundle → published representation（BP-61-1 卡点）→ entry_state → register_from_manifest
   ↓
Task 10 宿主接桥 GtF1Prepayment.vue（F1_SHEET_KEY_BY_CODE + isF1SyncManagedSheet 从 provider 清单派生）
Task 11 canary 真栈三谓词
```

### 接入顺序（形态驱动）

```
F1-6 关联方（canary：单级表头 / 无账龄 / 3 行 / 无口径分歧）
  → F1-5 长期挂款（单区；验证 FC-7 派生列处置）
  → F1-7 检查（三区同 sheet；验证兄弟 Table ref 位移 + 三区不同列集）
  → F1-4 区④ 大额供应商（dict 子数组；验证专用 merge 门面保留 pack 其余 8 键）
  → [口径修复 F1-H3 落地] → F1-2 明细（两级表头 + 三套 nested 账龄；仅 THREE_YEAR 启用）
  → [口径修复 F1-H4 影响评估 + 落地] → F1-1 审定表（AdjudicationSheetSpec，最后）
F1-3：可行性核（FC-6，默认 single_html）
```

## Components and Interfaces

### 声明层结构

```
backend/app/services/workpaper_sync/
  phase5_f1_prepayment.py            ← entry 层（provider，含开关与登记）
  phase5_f1_06_related_party.py      ← canary
  phase5_f1_05_long_term.py
  phase5_f1_07_voucher_check.py      ← 三个 spec（current / credit / post）
  phase5_f1_04_analysis.py           ← 区④ suppliers 子数组 + 专用 merge 门面
  phase5_f1_02_detail.py             ← 两级表头 + nested 账龄 ×3
  phase5_f1_01_adjudication.py       ← AdjudicationSheetSpec
backend/data/workpaper_sync_contracts/f1.prepayment_detail.json
backend/scripts/gen/generate_phase5_f1_contract.py
```

sheet 层声明文件 SHALL 只含常量与 spec 实例（**无 `def` / 无 `class`**，E1 Task 13 已钉的判据），算法全在框架层。

### 受管区清单（实测几何）

| sheet_key | managed_sheet | store_item_id | 表头 | 数据 | footer | UUID | formula_columns |
|---|---|---|---|---|---|---|---|
| `f16-managed` | 关联方及交易检查表F1-6 | `F1-rp-rows` | R6 | R7-9 | R10「合计」 | N | F, H |
| `f15-managed` | 长期挂款检查表F1-5 | `F1-lt-rows` | R5 | R6-14 | R15「合计」 | N | （无；J 为 FC-7 派生列） |
| `f17-current` | 预付账款检查表F1-7 | `F1-vc-current-rows` | R15/R16 | R17-37 | R38 | T | （无） |
| `f17-credit` | 同上 | `F1-vc-credit-rows` | R40/R41 | R42-64 | R65 | T | （无） |
| `f17-post` | 同上 | `F1-vc-post-rows` | R67/R68 | R69-85 | R86 | T | （无） |
| `f14-suppliers` | 实质性分析F1-4 | `F1-ana-pack`（`suppliers[]`） | R40 | R41-50 | R51「小计」 | S（Task 2 复核） | E, G |
| `f12-managed` | 明细表F1-2 | `F1-det-rows` | R12/R13 | R14-34 | R35「合计」 | AF | H, O, Q, X |

F1-1 走 `AdjudicationSheetSpec`（非行表），见裁决 F1-H6。

### F1-2 字段（按列实测，键名取自 `useF1Detail.DetailRow` + 真库载荷 23 键）

A `customerName` · B `companyCode` · C `relationType`（DV 三枚举）· D `nature`（DV 五枚举）· E `priorUnadjusted` ·
F `priorAdjustment` · G `priorReclass` · H `priorAudited`(f) · I-L `agingPrior/*` · M `debit` · N `credit` ·
O `endBalance`(f) · P `entityReclass` · Q `endUnadjusted`(f) · R-U `agingCurrent/*` · V `endAje` · W `endRje` ·
X `endAudited`(f) · Y-AB `agingAudited/*` · AC `isConfirmed`（DV `√,×`）· AD `postPeriodSettlement` · AE `remark`。
账龄段键 `within1/y1to2/y2to3/over3`（`useAgingConfig.PRESET_SEGMENTS.THREE_YEAR`，真库一致）。

## Data Models

本 spec **不新增**数据模型类型。store 形态全部既有：`StoreKind.rows`（F1-2/5/6/7）、`StoreKind.dict`（F1-4 pack）、
per-cell 键（F1-1）。唯一新增的持久化产物是契约 JSON、wp_code 裁决条目与 entry overlay 条目。

## 关键裁决

### 裁决 F1-H1：canary 选 F1-6，不选 D3/E1 惯例的「主明细表」

| 候选 | 表头 | 账龄组 | 数据行 | 口径分歧 | 跨 sheet | 结论 |
|---|---|---|---|---|---|---|
| F1-2 明细 | 两级 | nested ×3 | 21 | 🔴 O/X（B1） | 被 5+ 消费方读 | 口径未修前不能接 |
| **F1-6 关联方** | 单级 | 无 | 3 | 无（`recalcRelatedPartyRow` 与 `F=C+D-E`/`H=F-G` 等价，按值核过） | 零 | ✅ |
| F1-5 长期挂款 | 单级 | 无 | 9 | FC-7 派生列 J | `useF1DisclosureSoe` 读 | 次选 |

D3 选 D3-2 作 canary 是因为 D3-2 当时已有 provider；F1 从零起步，canary 的职责是验证**发布链**而非引擎，失败面
越小越好（E1 选 E1-2 同理）。

### 裁决 F1-H2：只有一册，全覆盖；不接 5 类 sheet

F1 只有 `F/F1 预付账款.xlsx` 一册（与 D3 同，与 D2/E1 的多册不同）⇒ 无「另立新宿主」问题。不接：底稿目录 /
F1A 程序表 / 两张附注披露 / **隐藏残留 `预付账款实质性程序表G1A-修订前`**（96r×O，G1 编号出现在 F1 册，
`wp_render_config` 跳过规则已覆盖「修订前」类残留）。

### 裁决 F1-H3：F1-2 口径以模板为权威修前端，先于受管

`useF1Detail.recalcRowFormulas` 改为：

```ts
// 与权威模板 明细表F1-2 R14 逐格一致：O=E+M-N、X=O+V+W（H/Q 不变）
const H = calcPriorAudited(row.priorUnadjusted, row.priorAdjustment, row.priorReclass)
const O = calcEndBalance(row.priorUnadjusted, row.debit, row.credit)
const Q = calcEndUnadjusted(O, row.entityReclass)
const X = calcEndAudited(O, row.endAje, row.endRje)
```

🔴 语义影响须在 Task 中评估：模板口径下「期初调整（F/G）」与「被审计单位重分类（P）」**不进**期末审定数 X
（X 只加本期 AJE/RJE）。这是致同模板的设计（期初调整在上年底稿已体现），但它改变了 HTML 当前显示值 ⇒
修复 SHALL 附：①真库 68 行 before/after 对比（当前 F=G=P=V=W=0 ⇒ 预期零差异）②F1-1/附注/F1-4 下游零回归。
D3-2（`useD3Detail.ts:141`）与 G2（`useG2Detail.ts:224`）同型，登记移交各自 spec，本 spec 不修。

### 裁决 F1-H4：F1-1 取数以模板为权威，影响评估先行

模板性质区 F=Σ明细 O、G/H=Σ明细 V/W、I=F+G+H；账龄区 F=明细 R35（未审账龄合计）、I=明细 Y35（审定账龄合计）、
G 倒挤。前端当前性质区与账龄区都以**审定口径**作未审数、AJE/RJE 逐格手填（`useF1Adjudication.buildRow`）。
对齐模板意味着 F1-1 的 AJE/RJE 从「手填」变为「汇总明细 V/W」⇒ 这是**业务口径变更**，SHALL：①查真库 F1-1
per-cell AJE/RJE 键是否有手填值（有则迁移方案）②核 `adjustmentReconcile`（F1-1 vs F1-3 一致性校验）语义是否随之变化
③与业务确认后实施。在此之前 F1-1 保持未受管（legacy 假双向如实登记）。

### 裁决 F1-H5：F1-4 只接区④，区①~③ 核后再定

区④ `suppliers[]` 是真动态行（`addSupplierRow`/`removeSupplierRow` + `computeTop5` 自动填），符合行表语义；
区①② 是四性质写死行 + 存货/采购对比行（dict 子对象 `balanceNatures`/`debitNatures`/`inventoryBalance`/
`inventoryPurchase`），区③ 是散格。三者受管收益低于风险（D4-9 dict 专用门面的维护成本），默认 HTML-only，
Task 核后如确有「稳定 key 固定行」表达路径再扩。

### 裁决 F1-H6：F1-1 用 AdjudicationSheetSpec，两区不同 row_mode

性质区 5 行写死（`NATURE_ROWS`：`goods/construction/equipment/service/other`，与模板 A8-A12 货款/工程款/设备款/
服务费/其他逐字对应）⇒ `fixed_rows`；账龄区行随账龄口径（THREE_YEAR 4 行 + 模板 R21 空槽；FIVE_YEAR 6 行超出
模板 5 槽）⇒ `slot_driven` 且仅 THREE_YEAR 启用（同需求 3.3）。🔴 不得照 D3-1/D1-1 推演 sections 数。

### 裁决 F1-H7：公式管理不在宿主内加按钮

F1 宿主零 `open-formula-manager` emit，页面级入口由 F-SHELL 提供 ⇒ 本 spec 只加「两种模式下入口可达」判据，
不在 `GtF1Prepayment.vue` 引入 E1 式 `openFormulaManager()`（否则形成第二 owner，违反 F-SHELL 唯一 owner 约束）。

## Error Handling

| 场景 | 处理 | 依据 |
|---|---|---|
| store 行缺 `rowId` | projection fail-closed 抛「缺稳定行身份」，不静默跳过 | E1 裁决（D4-1 事故） |
| `store_item_id` 未在 `all_store_item_ids()` 登记 | `_spec_of_store_item` 抛，不静默跳过 | D4-35 恒空根因 |
| F1-2 账龄口径非 THREE_YEAR | 受管关闭 + 中文原因「当前账龄段数与模板 4 列不一致，在线编辑暂不可回写」 | 需求 3.3 |
| footer 下 note/conclusion | HTML-only，不进动态区（`footer_row > last_data_row` 构造约束） | 需求 2.4 |
| OO 改 FC-7 派生列 | 受保护字段冲突，不合并 | FC-7 |
| 发布链第③环缺供给 | 如实 `upstream_gap`，adapter 保持未注册 | 需求 1.8 / BP-61-1 |
| sync 回写触发 TB 写 | 判据必红；CI 守卫拦截 | FC-9 |

## Correctness Properties

每条都必须被变异打红，否则重写（需求 9.3）。

### Property 1: canary 打通后 migration_state 与 legacy_reasons 正确变更

**Validates: 1.5**　`legacy_fake_bidirectional` → `adapter_registered`，三条 reason 全消。
变异：跳过发布链任一环 ⇒ 注册失败、状态不变。

### Property 2: `store_item_id` 逐字等于按值 grep 实测值

**Validates: 2.3**　变异 ①`F1-vc-current-rows→F1-vc-debit-rows` ②`F1-rp-rows→F1-6-rows` ⇒ 投影恒空必红。

### Property 3: `binding_kind` 与受管区数取自三元组 + 模板物理段

**Validates: 2.2, 4.3**　F1-7 三区 / F1-4 一区（区④）/ 其余单区。变异：把判据改回「公式数阈值」⇒
F1-5/F1-7（数据区零公式）会被误判 `static_region`，必红。

### Property 4: 三谓词 + DB 证据

**Validates: 1.7**　`confirm 200` / `forcesave cs_error=0` / `store_mirrored`+`marker_visible`。

### Property 5: `assert_entry_selectable` 对真 manifest 真调且默认严格

**Validates: 1.2, 1.3**　断言对真 manifest 调用返回 entry；变异：`WP_CODES` 改为真码 `{"F1"}` ⇒ 必抛
（E1 实测反例的防复发判据）。

### Property 6: F1-2 O/X 与模板数学等价

**Validates: 3.2, 7.2**　对随机行（hypothesis `max_examples=5`）断言前端 `recalcRowFormulas` 的 O/X 等于按模板
`O=E+M-N`、`X=O+V+W` 求值。变异：恢复 `calcEndBalance(H, …)` ⇒ 当 F≠0 时必红。

### Property 7: F1-1 性质/账龄取数与模板一致（裁决 F1-H4 落地后）

**Validates: 7.3**　断言 F1-1 F 列 = Σ明细 O（按 nature 分组）、账龄 F = 明细未审账龄合计。

### Property 8: 公式管理入口在两种渲染模式下都可达、且只有一个 owner

**Validates: 7.1**　变异：在 `GtF1Prepayment.vue` 加 `emit('open-formula-manager')` 按钮 ⇒ owner 唯一性判据红。

### Property 9: prefill 预设 sheet 名与源 tab 逐字一致且有 `--check` owner

**Validates: 7.4**　`test_f1_formula_presets.py` 4 条 F1 用例转绿；新 `--check` 对全角块必红。

### Property 10: F1-5 J 列（FC-7 派生列）OO 改动不被静默覆盖

**Validates: 4.2**　OO 改 J → forcesave → 断言产生受保护字段冲突（或 J 在契约中非 editable）。
变异：J 标 `editable` ⇒ HTML recalc 覆盖用户值，判据红。

### Property 11: F1-4 专用 merge 只改 `suppliers[]`，pack 其余 8 键逐字不变

**Validates: 5.2**　变异：merge 整体替换 pack ⇒ `balanceNatures` 等被清空，必红。

### Property 12: F1-7 三区列集互不串用 + 兄弟 Table 位移

**Validates: 4.3, 4.4**　区①插 5 行后区②③ footer SUM 区间与 G 列公式随位移、区②③数据不变。

### Property 13: 其余 contract 的 golden digest 逐项不变（现算，不断言个数）

**Validates: 9.1**　🔴 **现算**当前 `PROVIDERS` 成员与契约目录清单后逐项比对，**不断言集合大小**
（GC-10：本条原列 `b60/d1~d7/e1/g7/h1` 并写「10 个」，实为 11 个名字、目录已涨到 12）。变异：动共享常量。

### Property 14: F1-1 受管后 sync 路径 TB 写次数为 0

**Validates: 8.2**　变异：在 sync 回写里调 `publishToTb` ⇒ 必红（绕过人工二次确认）。

### Property 15: F1-2 非 THREE_YEAR 时受管关闭、账龄第 5 段起金额不丢

**Validates: 3.3**　构造 FIVE_YEAR 载荷 → 断言受管判定为关 + legacy 路径不触碰该键。

### Property 16: 下游消费方在回写后正确重算

**Validates: 3.5**　`useF1CrossSheet` / `useF1Analysis.computeTop5` / 披露 composable 读回写后的新值。

## Testing Strategy

红判据先行：阶段 0 先打红 Property 1（现状必红）/ 5 / 6 / 9。后端 pytest（`$env:PYTHONIOENCODING='utf-8'`；
PBT `max_examples=5`）；前端 vitest（`npx vitest run <file> --reporter=dot`）；真栈 Playwright `--workers=1`，
fixture 照 D4 lane `e2e/fixtures/*-l2-cases.json` 结构，七态结果枚举沿用。

## 顺带发现（登记，不在本 spec 处理）

1. **E1 `assert_entry_selectable` 守卫空转**（FC-2，HEAD 实测）：真 manifest `["E1M"]` vs `WP_CODES={"E1"}`
   （HEAD L110），默认调用必抛，E1 测试只断言常量、未真调 ⇒ 移交 `e1-sync-coverage-and-first-canary`。
   另：E1 provider **工作树未提交**的 `build_registration`（并发会话 WIP，+252 行，本 spec 不碰）实测不可构造 ——
   `EntryMatcher(wp_codes=WP_CODES)` 缺必填 `document_type` ⇒ `TypeError`，且 `AdapterRegistration` 字段是
   `matcher=` / `declared_capability=`（无 `adapter_id` / `entry_matcher`）。F provider 的 `build_registration`
   SHALL 照 **D3**（`phase5_d3_prepaid_receipts.py:830`：`matcher=build_matcher()` +
   `declared_capability=Capability.bidirectional` + `contract=… or load_contract_from_disk()`）写，并有一条真构造判据。
2. **D3-2 / G2 明细期末余额以期初审定起算**（与 F1-2 同病）⇒ 移交 D3 spec / G2 相关 spec。
3. **D3-1 性质区以审定数作未审数**（`useD3CrossSheet.ts:195`，与 F1-1 同病）⇒ 移交 D3 spec。
4. `test_disclosure_blocks_are_not_referenced_by_wp` 红在 **D2** 披露块 PREV 自引用 ⇒ 移交 D2。
5. 红测试引用的 spec `f1-extraction-chain-and-disclosure-source-fidelity` 已归档（`_archive/08-disclosure-notes/`，
   残留 `[ ] 5.3`），其 design 写的是半角国企块，数据文件归档后被回退成全角且无活跃 `--check` owner ⇒ 本 spec
   需求 7.4 接手（给披露块补 `--check`，防再次回退）。
