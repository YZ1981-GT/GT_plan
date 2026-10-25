# Design Document

## Overview

G 循环地基 spec：把 17 条 entry 的共性裁决收在一处（**GC-1 ~ GC-10**）、处置四条 G 专属前置的边界、
并用 **G2 应收利息**打通首张 canary。三份下游 lane spec 引用本 spec 的 GC 裁决，不复述。

G 循环与 F 循环的**结构性差异**决定了不能照抄 F 的 spec 形态：

| 维度 | F 循环 | G 循环 |
|---|---|---|
| entry / 册 | 8 entry / 5 册（F2 一册 4 entry 共码） | **17 entry / 13 册**（G4/G6 各一册 3 entry） |
| 一册一 entry（FC-3） | 成立 | 🔴 **不成立**（FD-3） |
| 已有冻结 slice | 有（Task 48） | 有（Task 49）**且更详尽**：FD-1~FD-5 + 12 条 BP + 两条「缺陷不存在」裁定 |
| 已有守卫 | — | ✅ 179 KB `test_task49_g_cycle_migration.py` + 变异脚本 + 51 KB 删除清册 |
| 同循环已迁移先例 | 无 | ✅ G7（但走 `pilot_*` 范式，不是 `phase5_*`） |
| prefill items 死配置（FC-11） | 命中 7 块（F3/F4/F5） | 🔴 **不命中**（47 块全 `cells`） |
| OCR 第二写入方（FC-8） | F1 单弹窗 / E1 七弹窗 | 🔴 **零命中** |
| 真库载荷 | F5 全零（须 seed） | ✅ G1~G14 **每科目都有** |
| 公式管理预设 | F5 = 0 | ✅ 13 科目全非零 |
| 模板 OO 崩溃风险 | 未查（本轮登记为 F 的遗漏） | 🔴 **13 册全带裸 IF**，缓解件已存在 |

## 上游锚定

| 上游 | 复用什么 |
|---|---|
| umbrella Task 49 + G slice | 17 entry 清单 / `capability_target_blocked_by` 逐条 / `authoritative_templates` sha256 与 `belongs_to_entries` / FD-1~FD-5 / BP-1~BP-12 / 两条「缺陷不存在」裁定 / 附注路径审计 |
| G 删除清册（51 KB） | `useG2DualMode.ts` 是唯一包基座的 / `useG1DualMode.ts` 跨 G1-E1 共用 / 不可达旧桩 |
| F1 spec design | FC-1~FC-13（本 spec §FC 适用性重裁逐条处置） |
| `pilot_g7_two_level_dynamic.py` + `g7_oo_crash_if_neutralize.py` | OO 崩溃中性化的**已被真 OO 栈验收过**的口径；`StoreMergePlan.oo_crash_neutralization_fn` 声明式挂点 |
| `phase5_d3_prepaid_receipts.py:830` | `build_registration` 的正确写法（`matcher=` / `declared_capability=`） |
| D4-29 `phase5_transposed_sheet.py` + `transposed_registry.py` | 转置形态先例（G4-9 / G6-11 的 RG-2） |
| `test_i_cycle_formula_presets.test_sheet_exists_in_template` | sheet 名存在性守卫的既有口径（RG-5 补齐时照它，不新造） |

## FC-1 ~ FC-13 在 G 循环的适用性重裁

🔴 **照抄 F 的守卫会在 G 上静默失配**（slice `g_cycle_form_differences.why_this_section_exists` 原文：
正则找不到 `api.get` 就当「没有写入路径」→ 要么假红要么被 `if` 兜住变假绿）。逐条重裁：

| FC | 在 G 的裁定 | 依据 / 替代 |
|---|---|---|
| FC-1 E1 级起点、走完整发布链 | ✅ **适用** | 17 条零 provider / 零契约 / 零 representation |
| FC-2 幻影码 matcher + 真码 provisioning | ✅ 适用但**加强** | `G4B` / `G6O` 各被 **3 条** entry 共用（比 F2 的 `F2I` 被 3 条共用同级），且冲突落在 **representation 层**（BP-8）而非仅 matcher 层 ⇒ 见 GC-1 |
| FC-3 一 entry 恰一 template_ref | 🔴 **不成立** | FD-3：13 册覆盖 17 entry，`belongs_to_entry` 单射不成立 ⇒ 改写为 **GC-1** |
| FC-4 三元组 + 按值 grep | ✅ 适用且**加强** | FD-4 行身份**三族**（F 只有两族）+ FD-5 80 处重复声明 + RG-10 模板化拼接键 ⇒ 见 GC-5 / GC-6 |
| FC-5 以模板为权威（两例外） | ✅ 适用，**例外增至四个** | 新增 G5-2 三处漏加小计 + G5-1!B35 越界（RG-3）⇒ 见 GC-3 |
| FC-6 调整分录表 `single_html` | ✅ 适用 | 13 个 `G{N}TabAdjustment.vue` 各 `useAdjustmentCentralSync=3` |
| FC-7 模板无公式但 HTML 派生列不得 editable | ✅ 适用 | 各 lane spec 逐列核 |
| FC-8 OCR 第二写入方 | 🔴 **不适用** | G 循环全仓零 OCR 命中 |
| FC-9 TB 红线 | ✅ 适用，**但有三家缺口** | 10 家已接 `publishToTb`；G1/G4-main/G6-main 为 0（RG-6）⇒ 见 GC-9 |
| FC-10 百分数 × 小数格 | 🟡 **初判不命中，须逐列取证** | G11-2 占比列 `G/K` 是公式列（`=IF(F10=0,0,F10/$F$31)`）；但 RG-8 的布尔列与 RG-12 的绝对引用另立判据 |
| FC-11 prefill `items` 死配置 | 🔴 **不命中** | 47 个 G 块全用 `cells`、零 `items`；G 的同族缺陷是**不同根因**（sheet 名错位 + 缺守卫，RG-5）⇒ 见 GC-8 |
| FC-12 manifest capability 非裁决值 | ✅ 适用 | = slice BP-6；且 BP-9 实证下游后果（两处生产 docstring 把 overlay 默认值当裁决依据） |
| FC-13 逐 entry 阻塞取 `capability_target_blocked_by` | ✅ 适用 | G 的 17 条逐条不同：BP-1~4 全共有、BP-5/8/9/11 各只命中部分 |

## G 循环共同裁决（GC-1 ~ GC-10，四份 spec 共用）

### GC-1：一 entry 恰一 template_ref，但**一 template_ref 可服务多 entry**；representation pointer 按 `entry_id`

FC-3 在 G 不成立。实测 `G4 债权投资.xlsx` 服务 3 条（main G4A/G4-1~4 · sppi G4-5~8 · ecl G4-9~13），
`G6 其他债权投资.xlsx` 同样 3 条；slice 用 `belongs_to_entries`（复数）表达 1:N。

🔴 **BP-8 的真实危险在 representation 层不在 matcher 层**：若 representation 的 entry pointer 用
`wp_code`（或 `wp_code_pattern`），G4 的三条会各自顶掉对方的 generation。裁决：
- entry pointer / `working_paper_sync_entry_state` 主键 **一律用 `entry_id`**（`xlsx/gt-g4-bond-investment-main` 等）
- matcher 域用 `sheet_keys` 互斥（沿用 F2-H1 的解法：`overlaps()` 任一侧空即重叠；运行时走 `resolve_for_entry`）
- 守卫改断言「owner 模板集合的**并集** == entry 全集」且「每条 entry **恰被一张**模板认领」（单射改满射+唯一认领）

否决「给 G4/G6 各发明三个幻影码」——要动 manifest 生成器与 `wp_code_overrides`，影响面远超本批。

### GC-2：OO 加载期裸 `IF(` —— 13 册全命中，per-file 保守挂中性化

按 `_BARE_IF_CALL` 真实正则实测 13/13 册命中（见 RG-4）。中性化是 **per-file**（整册就地改写 substrate 副本），
缓解件已存在且已收敛为声明式（`StoreMergePlan.oo_crash_neutralization_fn`，Task 13 删掉了
`adapters/excel.py` 两处 `if adapter_id == "g7…"` 字面量分支）。

裁决：**BP-4（真 OO 场景集）未交付前，13 册一律挂中性化**并如实登记为「per-file 保守策略」。
🔴 不得以「裸 IF 数少」推断某册不需要 —— G7 的崩溃不是数量问题而是「参数在 OO 侧解析成 undefined」，
只有真 OO 加载能判。判据：before/after 公式集一致 + `verify_unmanaged_regions` 不报漂移 + 不改权威模板字节。

### GC-3：FC-5 的例外增至四个 —— 模板缺陷走覆盖层，不改前端去对齐错误模板

| 例外 | 所属 spec | 形态 |
|---|---|---|
| F3-4 应计利息 | F3 spec | 模板口径更粗（漏天数折算） |
| F5-7!G31 | F5 spec | 引越界空区 `G56:G61` |
| **G5-2 三处合计漏加小计** | G5 lane spec | 段内四子区只加三个（漏第三个），15 列 × 3 段 = 45 格 |
| **G5-1!B35 = `=B9-B225`** | G5 lane spec | 引越界空区（sheet 仅 87 行）⇒ 恒等于 B9 |

规则不变：**模板缺陷走覆盖层**（`backend/wp_templates/` 运行时只读 + sha 冻结进契约），
FC-5「以模板为权威」只适用于「两边都对、口径不同」。本 spec 只承载裁决结构，修复动作归 G5 lane spec。

### GC-4：转置形态用 `TransposedSheetSpec`，且三张 16384 列表须另择 UUID 策略

`G4-9` / `G6-11`（两个 ECL 主表）是转置形态（列 = 投资1..X），各含三块「分析结论」⇒
用 `RowTableSheetSpec` 会把投资项目当列、投影恒空。裁决走 D4-29 先例的 `phase5_transposed_sheet.py`。

🔴 **RG-1 是硬约束**：G4-9 / G5-9 / G6-11 的 `max_column` = **16384**（XFD，Excel 绝对上限），
有效内容列只有 11 ⇒「UUID 列放 `max_col+1`」结构上不可能。三条候选，由 lane spec 裁决：
① 按**有效内容列**（11）+1 放 UUID，并加判据证明 16384 列的格式化污染不影响 instrumentation 定位
② 先清理列级格式化污染（改权威模板字节 ⇒ 须走覆盖层，代价高）
③ 该表不受管、登记为 HTML-only
默认①（不动模板字节、可被判据锁死）。

### GC-5：payload 列四形态 + null 占位 —— 契约 `json_pointer` 逐 entry 取，先剔占位再判

FD-1 实测四形态（逐 entry 归属由 slice 冻结，守卫现算比对）：

| mode | entry | 数 |
|---|---|---|
| `conclusion_only` | G1 · G3 · G6-sppi | 3 |
| `remark_only` | G2 · G8 · G9 · G10 · G11 · G12 · G13 · G14 | 8 |
| `conclusion_canonical_remark_mirror` | G4-main（走 `g4StorageContract.buildCanonicalPayload()`） | 1 |
| `dual_write_remark_and_conclusion` | G4-sppi · G4-ecl · G5 · G6-main · G6-ecl | 5 |

🔴 **null 占位子形态全 slice 仅 G2 一条**（`useG2Detail.ts#L515-L519` 的
`{item_id, conclusion: null, remark: JSON.stringify(rows)}`）。判 mode 时 SHALL **先剔除字面 null/undefined 占位**
再判，否则 G2 会被误判成 `dual_write`（Task 49 首轮守卫就是这么错的）。剔除是一把放宽判据的刀 ⇒
配套**双向锁**：声称有空占位的写入点真有、没声称的真没有。

真库正向实证（本轮按值查）：`G5-2-rows`/`G5-3-rows`/`G5-4-rows`/`G5-5-rows`/`G5-2-aging-preset` 的
remark 与 conclusion **字节数完全相等** ⇒ 逐字双写确认；`G9-detail-rows`/`G2-2-detail-rows`/`G11-adj-rows`
只有 remark ⇒ `remark_only` 确认。

写死 `remark` 会让 G1/G3/G6-sppi 三条的契约指向**恒空的列**。

### GC-6：键与身份一律按值取 —— 三个陷阱

| 陷阱 | 实测 | 后果 |
|---|---|---|
| **行身份三族**（FD-4） | `generated_prefixed_opaque_string` 10 · `generated_uuid` 3（G4-ecl/G5/G6-ecl）· `generated_timestamp_string` 2（G1/G3）· `generated_opaque_string_with_array_index_fallback` 1（G6-sppi = BP-7）· **`stable_template_row_key` 1（G14）**；字段名 `id` 11 / `rowId` 5 / **`rowKey` 1** | F 的守卫写死 `row_identity_key in ('rowId','id')` 且要求两族都出现 ⇒ 会把 G14 的 `rowKey` 判违规，而 **`rowKey` 恰是最稳的一族**（源模板固定行集，用户不增删） |
| **80 处重复声明**（FD-5 / BP-10） | `G1-2-rows` 8 处 · `G10-detail-rows` 6 · `G11-adj-rows` 6 · `G2-1-rows` 5 · `G2-2-detail-rows` 5；G6 已做对（派生别名），G4 有 storage contract 却仍重复 4 条 | 契约要求「一个 stable_field_key ↔ 一处声明」；改其中一处无守卫发现，`source_ref` 指不准 |
| **模板化拼接键**（RG-10） | 真库有 `G11-adj-tb-writeback`(46 B) / `G9-adj-tb-writeback`(40) / `G8-adj-tb-writeback`(40)，前端按字面量 grep **零命中** | 按字面量普查会漏；须按值匹配 + 模板串两形态都扫 |

🔴 另：`generated_timestamp_string`（G1/G3）有**同毫秒撞 id** 风险（F2 同型已实证）⇒ lane spec 须逐个核有无随机后缀。

### GC-7：BP-7 归属与边界

BP-7 只命中 **`xlsx/gt-g6-other-bond-sppi`** 一条（`useG6SppiFairValue.ts#L331`
`data.rows.map((r, i) => migrateFairValueRow(r, i + 1))` + `#L128` 缺 id 时 `fv-${Date.now()}-${seq}` 回退）。
`must_fix_before` = 「把 `xlsx/gt-g6-other-bond-sppi` 标 bidirectional 之前（也在 step 6 为它发布 contract 之前）」。
裁决：**本 spec 不修**（只卡一条 entry，修它属 G4/G6 lane spec 的作业面），但在此登记形态与门。
与 F 循环对照：F 的 BP-7 命中 F2-main 与 F5 两条 ⇒ **BP 编号跨循环 slice 同号不同义，引用必带循环前缀**。

### GC-8：prefill 的 G 侧缺陷是「sheet 名错位 + 缺守卫」，不是 FC-11 的 items 型

FC-11 在 G 不命中（47 块全 `cells`）。G 的同族后果（预设看得见但预填写不进）根因不同：
- **两块 sheet 名错位**：`[169]` `明细分析表G13-2`（真名 `明细表G13-2`）· `[170]` `明细分析表G14-2`（真名 `明细表G14-2`）
  —— 照抄了 G11 的「明细分析表」前缀（G11 真名确实带「分析」，已按值核三册内含「明细」的 tab）
- **守卫缺失**：D / E1 / F / I / J / K / L / H0 **八个**循环都有「块 sheet ∈ 模板真实 tab」断言；
  `test_g_cycle_formula_presets.py` 只有科目码 / 损益口径 / 披露覆盖 / `KNOWN_BAD_CODES` 四类，**没有该断言**

裁决：本 spec 修这两块 + 补该守卫（照 `test_i_cycle_formula_presets` 的既有口径，**不新造第二套**）。
🔴 断言时 SHALL 保留源模板空格事实（`…G1A ` 尾部空格 / `…G14A -修订前` 名中空格），不得 strip 后比较。

### GC-9：TB 发布门三家缺口 —— 本 spec 裁决与立门，不改造

10 家已接 `publishToTb`（四层齐备），三家为 0（G1 / G4-main / G6-main，均为资产科目本应回写）。
裁决：本 spec **不改造**（改 TB 回写路径属 `tb-writeback-explicit-publish-gate` 的作业面，其 Task 12 已覆盖另 10 家），
但 SHALL ①逐处按值核残留 `trial-balance`/`writeback` 是活路径还是死代码 ②判定为活路径时登记为该 spec 的遗漏项
③在三家受管前立本地硬门（判据必红直到裁决落地）。

🔴 **键名按值取，不按科目码推演**（RG-7）：`G4-1-adj-tb-1501` 真码 1504 · `G6-1-adj-tb-1503` 真码 1506，
且 `useG6MainAdjudication.ts:53` 的注释把真码写成 **1505**（1505 本身在 `KNOWN_BAD_CODES['G6']` 里）⇒ 注释须修。
键名是稳定标识符**不得改**（改了会丢已有项目的 TB 核对数据）。
损益类 G11/G12/G13/G14 的 TB 口径是**本期发生额**（`PL_CYCLES` 已冻结）。

### GC-10：零回归基线一律现算，不写死数字

实测 `check_sync_provider_golden_digest.PROVIDERS` 已含 b60/d1/d2/d3/d4/d5/d6/d7/e1(+g7/h1)，
契约目录现 **12** 个 json —— 并发会话本轮交付了 d1/d3/d5/d6/d7/e1。
⇒ 任何 spec 写「既有 N 个 contract golden digest 不变」都会在下次交付后立刻 stale。
裁决：判据 SHALL 现算「纳入 G provider 前后，**非 G** 的 digest 集合逐项不变」，不断言集合大小。

## Architecture

### 四份 spec 的依赖与分工

```
[本 spec] g-cycle-sync-foundation-and-first-canary
   ├─ GC-1~GC-10 共同裁决（三份 lane 引用）
   ├─ BP-5 修（G1 sheet 标签表 5 条错名）· BP-6/9/11 登记 · BP-7/8 立门不修
   ├─ GC-8 prefill 两块改名 + 补 sheet 存在性守卫
   ├─ GC-9 三家 TB 缺口裁决 + 立门
   └─ canary：G2（明细表G2-2）全链打通
        ↓ 三份 lane spec 并行（互不阻塞）
   ├─ g-cycle-single-region-detail-lanes   G1 G3 G8 G9 G10 G11 G12 G13 G14（9 条，G2 已在本 spec）
   ├─ g4-g6-shared-workbook-three-entry-lanes   G4×3 + G6×3（BP-7/BP-8 + 转置 + 16384 列）
   └─ g5-nested-sections-and-template-defects    G5（三段嵌套 + 两处模板缺陷）
```

### 声明层结构（本 spec 交付部分）

```
backend/app/services/workpaper_sync/
  phase5_g2_interest_receivable.py     ← entry 层 provider（phase5_* 范式，不照 G7 的 pilot_*）
  phase5_g2_02_detail.py               ← canary 薄声明（无 def/class）
backend/data/workpaper_sync_contracts/g2.interest_receivable_detail.json
backend/scripts/gen/generate_phase5_g2_contract.py
backend/tests/four_table/test_g_cycle_formula_presets.py   ← 补 sheet 存在性断言（既有文件）
audit-platform/frontend/src/components/workpaper/composables/g1SheetLabels.ts  ← BP-5 修 5 条错名
```

### canary 受管区

| sheet_key | managed_sheet | store_item_id | 行身份 | 表头 | 数据 | footer | payload 列 | formula_columns |
|---|---|---|---|---|---|---|---|---|
| `g202-managed` | 明细表G2-2 | `G2-2-detail-rows` | `id` | **R9 单级** | R10-15 | R16「合计」`SUM(C10:C15)` | `remark`（+null 占位于 conclusion） | E, H, J |

不受管（本 spec）：审定表G2-1（13 张审定表统一后置）· 调整分录汇总G2-4（FC-6）· 坏账准备明细表G2-3 ·
利息测算表G2-5 · 长期未收回款项检查表G2-6 · 应收利息坏账准备测算G2-7 · 凭证检查表G2-8 · 两张附注披露 · 底稿目录 · G2A 程序表。

## Data Models

不新增数据模型。canary store 形态：`rows` + 行身份 `id`（`generated_prefixed_opaque_string`）。
payload 落 `checklist_responses.remark`（`conclusion` 恒 null 占位）。

## 关键裁决

### 裁决 GF-H1：canary 选 G2（明细表G2-2）

| 候选 | 表头 | 公式列 | 行级 mask | 真库载荷 | 专属 BP | 结论 |
|---|---|---|---|---|---|---|
| **G2-2** | **单级 R9** | **3（E,H,J）** | 无 | **475 B 真实** | 无 | ✅ |
| G4-7 | 单级 R13（B 起） | **0** | 无 | 0 | 🔴 BP-8 卡 representation 发布 | 否决 |
| G10-2 | 两级 R9/R10 | 6 | 无 | 2 B（空数组） | 无 | 次选 |
| G14-2 | 两级 R9/R10 | 4（含布尔 L） | 无 | 2 B | 无 | 次选 |
| G9-2 | 两级 R9/R10 | 12 | 三区 | 605 B（最大） | 无 | 面偏大 |

G2 是**表头最简 + 公式列最少 + 有真实载荷**的唯一交集。另两条加分理由：
- 🔴 它带 FD-1 **唯一的 null 占位子形态** —— 首张就把最易误判的那条锁死（Task 49 首轮守卫在此翻过车）
- 🔴 它是 G 循环**唯一**包共享基座 `useWorkpaperEntryDualMode.ts` 的（`useG2DualMode.ts` 59 行，其余 16 条各自
  独立实现 73~174 行）⇒ 接桥路径最接近平台标准形态，验通后对其余 16 条是「更难不是更易」的诚实基线

否决 G4-7（虽数据区零公式最简，但属 G4 册、被 BP-8 卡住 representation 发布，canary 必须走完发布链）。

### 裁决 GF-H2：G2 不需要 seed，但须断言用的是真实载荷

与 F5（真库全零、必须 seed）相反：`G2-2-detail-rows` 真库有 475 B 真实载荷。
裁决：**不交付 seed 脚本**，但验收判据 SHALL 断言「参与 roundtrip 的行数 > 0 且来自真库」——
防止「空表往返也算 `store_mirrored`」的假绿在 G 上以另一种方式复现（F5-H7 的镜像教训）。

### 裁决 GF-H3：provider 用 `phase5_*` 范式，不照 G7 的 `pilot_*`

G7 是 G 循环唯一已注册 adapter 的 entry，但它走 `pilot_g7_two_level_dynamic.py`（`PILOT_ADAPTER_ID`）。
裁决：新建的 17 条一律用 **`phase5_*` 声明式范式**（D/E/F 已验通 9 家）。
理由：`pilot_*` 是 Tasks 40~43 的四个先导，其形态早于行表引擎；照它会写出无法复用引擎的单例代码。
🔴 但 **G7 的 `oo_crash_neutralization_fn` 挂点必须复用**（GC-2）—— 那是范式无关的 per-file 缓解件。

### 裁决 GF-H4：BP-5 本 spec 修，BP-7/BP-8 立门不修

| BP | 命中面 | 本 spec 动作 | 理由 |
|---|---|---|---|
| BP-5 | G1 一条，但 `must_fix_before` 含「发布 contract 之前（契约 source_ref 要写 sheet 名）」 | **修**（5 条错名 → 真名） | 改动面 = 一个常量表；且它是**全 G 唯一**的 sheet 级解析缺陷，留着会污染所有引用 G1 sheet 名的契约 |
| BP-7 | G6-sppi 一条 | **立门不修** | 属 G4/G6 lane 的作业面；改行身份派生要做存量 id 回填（数据迁移） |
| BP-8 | G4×3 + G6×3 | **只出 GC-1 裁决 + 守卫** | 六条 entry 的实施归 lane spec；但 pointer 规则必须先定，否则 lane 会各写一套 |
| BP-6 / BP-9 / BP-11 | 全局 / G1+E1 / 旧桩 | **登记不动** | 分别归 Task 67 / Task 72 / Task 66-72 |

### 裁决 GF-H5：13 张审定表统一后置，不在本 spec 也不分散到 lane

13 张 `审定表G{N}-1` 有三个共性：①**全部命中裸 IF**（G1-1 126 格最多）②公式密度极高
（G1-1 504f / G5-1 501f / G9-1 390f / G6-1 340f）③TB 发布门落在它们身上（含 GC-9 的三家缺口）。
裁决：**另立第五份 spec `g-cycle-adjudication-sheets-coverage`**（本 spec 不含、三份 lane 也不含），
理由与 F 循环把三家审定表口径统一裁决在 F1 需求 7.3 同源 —— 审定表的共性大于其所属科目的差异。
本 spec 只登记该后置决定与三条共性证据，不产实施任务。

## Error Handling

| 场景 | 处理 | 依据 |
|---|---|---|
| 某册未挂中性化就开 OO | 判据必红；BP-4 前 13 册一律挂 | GC-2 |
| 中性化改了权威模板字节 | 判据必红（只能改 substrate 副本） | GC-2 |
| payload mode 判定未剔 null 占位 | G2 被误判 `dual_write` ⇒ 判据必红 | GC-5 |
| 契约 `json_pointer` 写死 `remark` | G1/G3/G6-sppi 指向恒空列 ⇒ 判据必红 | GC-5 |
| `row_identity_key` 白名单写死 `rowId|id` | G14 的 `rowKey` 被判违规 ⇒ 判据必红 | GC-6 |
| representation pointer 用 wp_code | G4/G6 同码三条互顶 generation ⇒ 判据必红 | GC-1 |
| G1 sheet 标签 strip 后比较 | `…G1A ` 尾部空格被抹掉 ⇒ 判据必红 | GC-8 |
| 三家 TB 缺口未裁决就受管 | 本地硬门必红 | GC-9 |
| 零回归判据断言 digest 集合大小 | 下次并发交付即 stale ⇒ 判据改现算逐项比对 | GC-10 |
| canary 用空表往返收尾 | 判据必红（须断言行数 > 0 且来自真库） | GF-H2 |
| 删 `useG1DualMode.ts` / `useWorkpaperEntryDualMode.ts` | 判据必红（前者打断 E1、后者打断多循环） | BP-9 / 删除清册 |
| 发布链第③环缺供给 | 如实 `upstream_gap`，不伪造通过 | BP-1~3 |

## Correctness Properties

🔴 编号 spec-scoped：`Property N` 读作 `GF-P{N}`。

### Property 1: FC 适用性重裁完整且三条「不适用」有正向证据
**Validates: 1.1, 1.2**　①design 含 FC-1~FC-13 逐条裁定 ②FC-3 判「不成立」有 `belongs_to_entries` 复数证据
③FC-8 判「不适用」有 G 全仓 OCR 零命中证据 ④FC-11 判「不命中」有 47 块全 `cells` 证据。
变异：把 FC-3 改回「成立」⇒ 与 13 册覆盖 17 entry 的实测矛盾，必红。

### Property 2: 两条「缺陷不存在」结论现算成立
**Validates: 1.4**　①13 整册码 + 8 子码经 `find_template_file` 逐一返回同名册 ②磁盘 15 文件 vs `_index.json` 15 条 G 项差集为空。
变异：往 G 目录塞一本未索引的册子 ⇒ 差集非空必红（锁住「将来谁扔冗余合册就打红」）。

### Property 3: 逐 entry 阻塞取 slice 字段且覆盖 17 条全集
**Validates: 1.3**　17 条 `capability_target_blocked_by` 逐元素断言；BP-1~4 全共有、BP-5 仅 G1、
BP-7 仅 G6-sppi、BP-8 仅 G4×3+G6×3、BP-9 仅 G1。变异：把 BP-5 套到 G2 ⇒ 必红。

### Property 4: BP-5 修复后 G1 sheet 标签 18/18 命中真实 tab（含空格）
**Validates: 2.1**　`G1_SHEET_LABEL_MAP` 18 条全部 ∈ `G1 交易性金融资产.xlsx` 的 sheetnames；
`交易性金融资产实质性程序表G1A ` 的**尾部空格逐字保留**。变异：strip 后比较 ⇒ 空格缺陷复活，必红。

### Property 5: representation pointer 按 entry_id，同码三条不互顶
**Validates: 2.2**　构造 G4 三条 entry 先后发布 representation ⇒ 三条各自的 pointer / generation 独立；
owner 模板并集 == entry 全集，且每 entry 恰被一张模板认领。变异：pointer 改用 `wp_code` ⇒ 互顶必红。

### Property 6: BP-9 跨循环共用件不被删且 E1 行为不变
**Validates: 2.4**　`useG1DualMode.ts` 与 `useWorkpaperEntryDualMode.ts` 在本 spec 后仍存在；
`GtE1MonetaryFund.vue` 对前者的引用与 digest 不变。变异：删任一 ⇒ 必红。

### Property 7: manifest 与 slice 的 capability 不一致是既登记事实
**Validates: 2.5**　断言 manifest `capability=='single_onlyoffice'` 且 slice 重裁 `capability is None`（必须不等）；
overlay `defaults_by_component.GtOnlyOfficeSheet` 未被改动。🔴 另断言本 spec 的任何 docstring **不出现**
BP-9 那种论证（「manifest 里 G{N} 的 entry 是 single_onlyoffice，所以走 X lane」）。

### Property 8: 13 册裸 IF 按真实正则现算且全部挂中性化
**Validates: 3.1, 3.2, 3.3**　①用 `_BARE_IF_CALL` 现算 13 册全 > 0 ②13 条 `StoreMergePlan` 全带
`oo_crash_neutralization_fn` ③`adapters/excel.py` 无 `if adapter_id ==` 字面量分支。
变异：改用「`IF(` 后跟 `IS*`」启发式 ⇒ G11-2 从 44 格降到更少，与真实正则不符必红。

### Property 9: 中性化只改 substrate 副本、公式集自洽
**Validates: 3.4**　before/after 公式集一致；权威模板 sha256 不变；`verify_unmanaged_regions` 不报漂移。

### Property 10: canary 几何逐格一致
**Validates: 4.1**　`G2-2-detail-rows` 的 header_row=9（单级）/ first_data_row=10 / last_data_row=15 /
footer_row=16 / `formula_columns=("E","H","J")` / 公式模板 `E=C{r}+D{r}` · `H=C{r}+F{r}-G{r}` · `J=H{r}+I{r}`。
变异：声明两级表头 R9/R10 ⇒ 数据区起点错位必红。

### Property 11: G2 payload 判定为 remark_only（剔占位后）
**Validates: 4.3**　剔除字面 null 占位后 mode == `remark_only`；契约 `json_pointer` 指 `remark`；
双向锁：声称有占位的写入点真有（`useG2Detail.ts#L515-L519`）、其余 16 条真没有。
变异：不剔占位 ⇒ 判成 `dual_write` 必红。

### Property 12: `store_item_id` 取真键且收敛为单一声明
**Validates: 4.4**　变异 `G2-2-detail-rows → G2-2-rows` ⇒ 投影恒空必红；
另断言该键在生产源码中的**声明处**收敛为 1（现状 5 处，RG-9）。

### Property 13: canary 打通后 migration_state 变更
**Validates: 4.5, 4.6**　`legacy_fake_bidirectional → adapter_registered`。变异：跳过发布链任一环 ⇒ 状态不变。

### Property 14: 宿主接桥保留共享基座
**Validates: 4.7**　`GtG2InterestReceivable.vue` 引入桥后，`useG2DualMode.ts` 仍 import
`useWorkpaperEntryDualMode`；未迁移 sheet 仍走 legacy 分支。变异：内联展开基座 ⇒ 必红。

### Property 15: canary 验收用真实载荷，不是空表往返
**Validates: 4.8**　roundtrip 参与行数 > 0 且来源是真库 `G2-2-detail-rows`(475 B)。
变异：允许空载荷通过 ⇒ 假绿必红。

### Property 16: canary 受管后 sync 路径 TB 写次数为 0
**Validates: 4.9**　`publishToTb`（科目 1132、余额口径）仍是唯一入口；legacy 双键
（`G2-1-tb` 主 / `G2-1-adj-tb-1132` 回退）只写主键。变异：sync 回写里调 `publishToTb` ⇒ 必红。

### Property 17: prefill 两块改名 + 新守卫在修复前必红
**Validates: 5.1, 5.2, 5.3, 5.4**　①`[169]`/`[170]` 的 sheet 名 == `明细表G13-2`/`明细表G14-2`
②新断言「块 sheet ∈ 源 xlsx 真实 tab」在**修复前必红**、修复后转绿 ③断言不 strip 空格
④`convert_prefill_presets()` 的 G13/G14 计数不减（14 / 13）。

### Property 18: 三家 TB 缺口有书面裁决且未裁决前硬门必红
**Validates: 6.1, 6.2, 6.3**　G1/G4-main/G6-main 的 `publishToTb` 计数为 0 这一事实被断言；
三家残留 `trial-balance`/`writeback` 逐处有「活路径 / 死代码」结论；未裁决时本地门必红。

### Property 19: TB 键名按值取 + G6 错注释已修
**Validates: 6.4, 6.5**　①契约里的 TB 键逐字等于源码常量（`G4-1-adj-tb-1501` / `G6-1-adj-tb-1503`），
**不由科目码推演** ②`useG6MainAdjudication.ts` 注释不再出现「已纠正为 1505」③G11/G12/G13/G14 口径为发生额。
变异：按 `G_ACCOUNT_CODES` 生成键名（`G4-1-adj-tb-1504`）⇒ 与真库键不符、读不到数据，必红。

### Property 20: 零回归基线现算逐项比对
**Validates: 7.1, 7.2**　纳入 G2 provider 前后，**非 G** 的 contract golden digest 逐项不变
（不断言集合大小）；六个登记点同步。变异：断言「共 12 个」⇒ 下次并发交付即 stale，判据自证脆弱必红。

### Property 21: 既有 G 产物被复用而非重造
**Validates: 7.3**　新判据加在 `test_task49_g_cycle_migration.py` / `test_g_cycle_formula_presets.py` 内，
或有显式「为何另起文件」的证据；三个既有产物文件仍存在且未被替换。

## Testing Strategy

红判据先行：阶段 0 先打红 GF-P3 / P4 / P8 / P17 / P18（对应 BP-5、裸 IF、prefill 错名、TB 缺口四条红基线）。
后端 pytest（`$env:PYTHONIOENCODING='utf-8'`，PBT `max_examples=5`）；前端 vitest；
真栈 Playwright `--workers=1`，fixture `e2e/fixtures/g2-l2-cases.json`。
🔴 G2 真库已有载荷 ⇒ 真栈用例**不 seed**，但须先断言载荷非空（GF-P15）。

## 顺带发现（登记，不在本 spec 处理）

1. 🔴 **G7 spec 已 24/24 归档却带着同型模板缺陷**：`G7 明细表G7-2` 的合计行漏加小计 **36 格**
   （与 G5-2 的 45 格同族）。归档不等于模板无缺陷 ⇒ 建议对已归档的循环 spec 补一轮「合计行漏加小计」全库扫描。
2. 🔴 **F 循环未查 OO 加载期裸 IF**：本轮才发现这是 per-file 崩溃风险且 G 13 册全命中。
   F1~F5 spec 没有对应判据 ⇒ 建议回补一次 F 目录扫描（本轮未做，不在 G spec 范围内伪称已覆盖）。
3. **四张 `-修订前` hidden 残留**（`投资收益实质性程序表G11A-修订前` 34r / `净敞口套期收益审计程序表G12A-修订前` 63r /
   `公允价值变动收益审计程序表G13A-修订前` 46r / `信用减值损失审计程序表G14A -修订前` 46r，末者名中带空格）+
   G1A 尾部空格 ⇒ 模板治理债，与 F 循环 4 张 hidden 残留同族，建议统一立项。
4. **G3 约 480 个 definedName**（整本 legacy 工作簿命名区域残留：`_xlnm.Database` / 大量 `UFPrn*` /
   中文名如「存货93期初」）；G4 有 29 个；其余 11 册为 0 ⇒ G3 受管前须确认 instrumentation 不误伤命名区域。
5. **G12-2 / G13-2 / G14-2 三处布尔校验列**（`=D9=SUM(E9:F9)` / `=J11=D11` / `=D11=K11`）求值为 TRUE/FALSE，
   extract 读回布尔值可能记 `type_normalization_failure`（同 F5 除零族）⇒ lane spec 须加容错判据。
6. **G13-2 父子行结构**（R11 父 = B12+B13 子，合计 `=B11+B14+B17+B19+B20` 只加父行）+
   **G12-2 合计 `I=SUM(I7:I13)` 起点 R7 在表头之上**（同 F2-55 footer SUM 起点异常族）⇒ lane spec 逐格处置。
7. **G11-2 占比列引合计行** `=IF(F10=0,0,F10/$F$31)`；受管后插行会让该绝对引用与真实合计行错位 ⇒ lane spec 判据。
