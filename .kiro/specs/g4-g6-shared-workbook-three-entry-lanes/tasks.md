# Implementation Plan

## Overview

**spec**：`g4-g6-shared-workbook-three-entry-lanes`　**创建**：2026-09-26　**状态**：0/18（Task 0~17），Design-First 未实施
**上游**：**`g-cycle-sync-foundation-and-first-canary`（GC-1~GC-10，硬前置）** · FC-1~FC-13 ·
D4-29 `phase5_transposed_sheet.py` · F2 spec 裁决 F2-H1（`sheet_keys` 互斥）

`[ ]*` = 依赖外部供给（BP-1~BP-4 / OO 真栈 / foundation GC-9 裁决）。

🔴 **本 spec 不得在 foundation 的 canary（G2）验通前开工 Task 6 起**：GC-1 的 pointer 规则与 GC-2 的中性化
声明位都由 foundation 交付。

## 🔴 2026-09-30：G 域双向回写「备好了但没接上」
现算发现（用户要求「不要假红」后重查）：G 域 **21 个 manifest entry 里只有 1 个**
（`xlsx/gt-g7-long-term-equity-main`）的 `capability` 是 `bidirectional`，其余 19 个仍是
`single_onlyoffice`、`migration_state='legacy_fake_bidirectional'`、
`canonical_resolver='legacy_sheet_onlyoffice_router'` ⇒ **双向回写在运行时从未启用**，
尽管 14 个正式契约 / 14 条 `STORE_MERGE_REGISTRY` / 32 个 provider / 宿主改线都已在库。

本轮已给 `workpaper_sync_entry_overlay.json` 加 **13 条 G 域 bidirectional 裁决**
（含本 spec 的 **G4-main / G6-main**），六项前置逐一现算通过；新建守卫
`backend/tests/workpaper_sync/test_g_cycle_bidirectional_overlay_adjudication.py`
（33 passed + 1 xfailed）。

🔴 **G4 / G6 的子入口刻意不裁决**：`g4-bond-investment-ecl` / `g4-…-sppi` /
`g6-…-ecl` / `g6-…-sppi` 按设计**没有自己的 approved per-entry 契约**，
`build_manifest_registration_plan` 现算把它们判为 blocked ⇒ 裁决它们会造出
「manifest 说双向、registration plan 判 blocked」的自相矛盾状态。守卫里
`test_sub_entries_are_deliberately_excluded` 是这条的反向锁。

**manifest 重生成仍被 `approved_source_digest` 门拒绝**（mount diff 18 处全在 A 类、
G 域 0 处），不擅自过门。完整归因、证据表与解除步骤见
`.kiro/specs/g5-nested-sections-and-template-defects/tasks.md` 的同日勘误节。


## 🔴 2026-09-30 续：两道门逐道实测，manifest 仍未翻（含 G4-main / G6-main）

本轮按「修复卡住那个门，跑通」逐道走到底，结论是**不能过门**：
①第一道 `approved_source_digest` 的 mount diff 已完整复核且能力零损失，但那 17 个
A 类退网宿主 **17/17 未提交**，批准等于把签名落在可能从未进入历史的树态上 ⇒ 已把本轮
一度写入的 digest 完整回滚（21 条 overrides 全保留，含本 spec 的 G4-main / G6-main）。
②第二道 `stale overlay overrides: [GtA51CashflowAudit.vue]` 是并发 A 轮会话的在途产物
（不在 HEAD）⇒ 不可删它放行自己。

🔴 过程中发现更根本的**发现契约缺口**：discoverer 不认 `WorkpaperSyncEditorHost`
⇒ 迁移最彻底的宿主会从挂点清册整体消失（今天已 51 个，`d4/**` 那批 34 个**已经真的
消失过一次**），而并入它会让 45 个双挂宿主撞 `stable entry_id collision` ⇒ 需另立 spec。

完整归因、方法论教训（`mountId` 内嵌行号不可用于 diff）、守卫变更（**40 passed + 1 xfailed**）
与解除步骤，见 `.kiro/specs/g5-nested-sections-and-template-defects/tasks.md` 的同日续节。

## ✅ 2026-09-30 最终结果：门已过，G4-main / G6-main 已随 13 条 G 翻 bidirectional

用户授权代并发会话处置 a51 矛盾 override 后两道门均已过、生成器已 `--apply`。
**上一节「不能过门」的结论已被取代**（原文保留作审计轨迹）。

本 spec 相关：`xlsx/gt-g4-bond-investment-main`（`g4.bond_main`）与
`xlsx/gt-g6-other-bond-main`（`g6.other_bond_main`）现算均为
`capability=bidirectional` + `migration_state=adapter_registered`，
`build_manifest_registration_plan` 判 `blocked_reason is None`。
**四个子入口按设计仍未裁决**（g4-ecl / g4-sppi / g6-ecl / g6-sppi），
`gt-g6-other-bond-ecl` 仍为 `unreachable`（overlay `unreachable_rules` 既有裁决）。

🔴 **「capability 翻了」≠「运行时已接通」**：`registry_bidirectional_without_registered_adapter`
现算 18 条，**包含本来就 bidirectional 的 5 条**（d1/d2/d4/g7/h1）⇒ adapter 进运行时
注册表是**另一步**，对全部 18 条都仍未完成，不是 G4/G6 独有欠账。

完整执行表、三条如实说明（含 HEAD manifest 曾被手改的发现）与 4 条预存红的内存 A/B 归因，
见 `.kiro/specs/g5-nested-sections-and-template-defects/tasks.md` 同日最终结果节。

### 🔴 本轮回归归因与一次产物回退事故

完整的 A/B 归因（修好 15 条、引入 12 条、其余大量预存红的逐族归因）与
「生成产物被并发会话回退一次、重跑生成器后 digest 逐字一致」的事故记录，
见 `.kiro/specs/g5-nested-sections-and-template-defects/tasks.md` 同日最终结果节。

与本 spec 直接相关：`xlsx/gt-g4-bond-investment-main` / `xlsx/gt-g6-other-bond-main`
现算均 `bidirectional` + `adapter_registered`；
🔴 并在 `test_g_foundation_p4_p8_p17_p18_red_baselines.py` 给出**书面裁决**
「受管不引入第二条 TB 写入路径」—— 依据是两个 provider 对 trial_balance
**零引用**（三种书写形态各 0 次）、两族前端四层无任何禁用 TB 写入端点，
且对照组 G1 能被同一口径命中发布门（证明零不是空转）。
**仍存在的真实缺口**：两族完全没有显式发布门 ⇒ 审定数无 TB 通路，另有判据守。

🔴 顺带修掉一个**静默脱管**：`GATE_LAYERS["G4-main"]` 声明的
`composables/useG4MainFormData.ts` **从不存在**（真名 `useG4BonInvFormData.ts`，
由宿主 import 实证）⇒ 该层此前被所有基于 `GATE_LAYERS` 的判据跳过而不报错。
已修正声明并加「声明的字面路径必须都解析到真实文件」判据防复发。

## Tasks

### 阶段 0：前置门 + 几何补测 + 红判据

- [x] 0. 前置依赖核查（`git show HEAD:`）
  - ✅ 全部前置满足（TransposedSheetSpec / RowTableSheetSpec / oo_crash_neutralization / foundation 19/19）
  - 证据 `evidence/task0-prerequisites.md`
  - **`phase5_transposed_sheet.TransposedSheetSpec` + `transposed_registry`**（Req 2 的硬依赖，D4-29 已泛化）
  - `StoreMergePlan.oo_crash_neutralization_fn`（GC-2）· `RowTableSheetSpec` · 兄弟 Table ref 位移（G4-2 两区依赖）
  - foundation spec 的 GC-1 pointer 规则与 GC-9 三家 TB 裁决**交付状态**
  - 证据 `evidence/task0-prerequisites.md`
  - _Requirements: 2.1, 5.1, 5.3_

- [ ] 1. slice 复核 + 六条 wp_code 裁决条目 + BP-8 证据
  - 核六条的 `capability_target_blocked_by`（G4-main 多 BP-7 / G6 三条多 BP-6 / 六条全 BP-8）
  - 🔴 `workpaper_sync_entry_wp_code_adjudication.json` 的 G4 / G6 两条（foundation Task 1 已建）SHALL 补
    `matcher_domain_conflict` 的 BP-8 原文 + GC-1 解法 + `belongs_to_entries` 三元组；重算 digest
  - _Requirements: 1.1, 1.3_

- [ ] 2. 几何补测 + BP-7 按值定位 + 可行性核
  - 🔴 **G6-2 多区几何逐格补全**（本 spec 只实测到 R12-14 小计 R15，其后未逐格）
  - 🔴 **G4-main 的 BP-7 按值 grep 定位**（裁决 G46-H4）：有缺陷给行号、无缺陷给「slice `blocked_by` 与正文不一致」登记
  - G4-9 / G6-11 的实体列逐格核（`投资1：`~`投资X：`）+ 三块锚行行号 + 有效内容列数（应为 11）
  - G6-5 行级 mask 逐行核（D 列在哪几行有公式）；G4-7 表头起始列（应为 B）
  - 两册其余 sheet 的可行性核结论（检查/测算表）；两册「参考」sheet 字面量逐字记录（B7）
  - 证据 `evidence/task2-geometry-and-bp7.md`
  - _Requirements: 2.2, 3.2, 4.4, 4.5, 4.6, 4.7_

- [ ] 3. G46-P1 / P2 / P3 红判据（BP-8 侧，现状必红）
  - P1 pointer 隔离（现状无 provider ⇒ 以合成 representation 构造）；P2 **真跑** `registry.register()` 三条同码；
    P3 `belongs_to_entries` 满射+唯一认领，变异「断言单射」必红
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [ ] 4. G46-P4 / P6 / P8 红判据（转置 / 16384 / BP-7，现状必红）
  - P4 变异「用 RowTableSheetSpec」；P6 变异「UUID 放 max_col+1」证明超 XFD；P8 现状 G6-sppi 必红
  - _Requirements: 2.1, 2.4, 3.1_

- [ ] 5. G46-P10 / P13 / P18 红判据（`http` 探针 / 参考 sheet 字面量 / 零回归现算）
  - P10 变异「全用 `api\.` 探针」证明四条失配；P13 变异「共用字面量」证明 G6 那张漏排除；
    P18 现算基线（**不断言集合大小**，GC-10）
  - _Requirements: 4.2, 4.7, 5.6_

### 阶段 1：BP-7 修复（受管硬前置）

- [ ] 6. BP-7 处置（按 Task 2 的定位结果）
  - G6-sppi：`useG6SppiFairValue.ts#L331` 的 `map((r, i) => migrateFairValueRow(r, i + 1))` +
    `#L128` 的 `` `fv-${Date.now()}-${seq}` `` 回退 ⇒ 缺 id 时铸稳定 UUID 并**立即回写**
  - G4-main：有缺陷则一并修（触类旁通一次修完）；无缺陷则落不一致登记
  - 旧载荷迁移判据（重铸后 id 不匹配 `^fv-\d+-\d+$`）；P8 转绿
  - _Requirements: 3.1, 3.2, 3.3_

### 阶段 2：G4 三条 lane

- [x] 7. `phase5_g4_bond_investment.py` entry 层从零建（三条共用模块、三个 `ADAPTER_ID`）
  - `g4.bond_main` / `g4.sppi_inventory` / `g4.ecl_stage`；三条**共用** `TEMPLATE_SHA256="da3a3480d37a4b95…"`
    （裁决 G46-H2：契约钉同一份字节，pointer 靠 `entry_id` 区分）
  - 三个 `build_matcher()` 各带互斥 `sheet_keys`（G4A/G4-1~4 · G4-5~8 · G4-9~13）+ `document_type="xlsx"`
  - `assert_entry_selectable` 照 D3 同签名；`build_registration` 照 `phase5_d3_prepaid_receipts.py:830` + 真构造判据
  - 🔴 `StoreMergePlan` 三条全带 `oo_crash_neutralization_fn`（G4 册 186 格裸 IF）
  - _Requirements: 1.1, 1.2, 5.3_

- [x] 8. `phase5_g4_07_sppi_inventory.py`（**本 spec 首条**，裁决 G46-H1）
  - ✅ commit `2f88898ec`：零公式 + 表头起于 B 列 + 无合计 + entry 层 + 契约（digest fc3133e4）
  - `G4-7-items` / `id` / 表头 R13 起于 **B 列**（A 列空）/ 数据 R14-22 / **无合计** ⇒ `footer_row=23` +
    `footer_marker="三、审计说明"` + `footer_carries_total_formula=False` / `formula_columns=()`
  - payload `dual_write`（FD-1）；HTTP 客户端 `api`；P12 前半
  - _Requirements: 4.1, 4.4_

- [x] 9. `phase5_g4_02_main_detail.py`（两区）
  - ✅ commit `890557d97`：34 列 × 11 公式列 × 两区（uuid AI/AJ）
  - 两区 R12-17 / R20-25，小计 R18/R26，合计 R27 `=SUM(G18,G26)`；两区各自 `field_specs`（P11）
  - `formula_columns=("J","L","O","S","T","U","V","X","AC","AF","AG")`；有效列 44(A-AR)
  - payload 走 `g4StorageContract.buildCanonicalPayload()`（conclusion 权威 + remark 镜像）
  - 🔴 把模板 R11/R19「【预留插行区：在「小计」行之上填写或插入】」+ R41「每类默认6行」登记为**正向证据**
    （G 循环唯一模板自带插行声明）
  - _Requirements: 4.1, 4.3_

- [x]* 10. G4-ecl 转置声明 + 16384 列裁决落地
  - `phase5_g4_09_ecl_stage.py`：`TransposedSheetSpec` / `G4-9-rows` / `id`(uuid) / 表头 R9 /
    实体列 `投资1：`~`投资X：` / 三块锚行 R24/R32/R46（`footer_carries_total_formula=False`）/ `formula_columns=()`
  - 🔴 16384 列按裁决 G46-H3 取①：UUID 放**有效内容列 11 + 1 = 第 12 列**；P6 转绿
    （`print_area`/`page_setup` 不变 + instrumentation 不做全宽扫描）
  - P4 / P5 / P7 转绿
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x]* 11. G4 三条发布链 + 宿主接桥 + pointer 隔离真验
  - 三条各走五环；🔴 **第三条发布时 P1 必须仍绿**（证明 pointer 不互顶，这是 BP-8 的真验收点）
  - 三个宿主（`GtG4BondInvestmentMain/Sppi/Ecl.vue`）各引入 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`，
    保留 legacy 与 `GtEntrySyncCapabilityNotice`
  - 六个登记点同步；第③环卡 BP-1~3 时如实 `upstream_gap`
  - _Requirements: 1.1, 1.4, 5.6_

### 阶段 3：G6 三条 lane

- [x] 12. `phase5_g6_other_bond.py` entry 层从零建（同 G4 范式）
  - `g6.other_bond_main` / `g6.sppi_fair_value` / `g6.ecl_stage`；共用 `TEMPLATE_SHA256="63bf38c797d4612e…"`
  - 三条互斥 `sheet_keys`（G6A/G6-1~4 · G6-5~10 · G6-11~15）；🔴 三条挂中性化（G6 册 192 格裸 IF）
  - 🔴 三条的 HTTP 客户端全是 **`http`**（FD-2）⇒ 守卫探针按登记名拼（P10）
  - _Requirements: 1.1, 1.2, 4.2, 5.3_

- [x] 13. `phase5_g6_02_main_detail.py`（多区，几何取 Task 2 补测结果）
  - `G6-2-rows` / `id` / R9/R10 两级表头 / 多区 + 多小计 /
    `formula_columns=("J","O","Q","U","V","W","X","Y","AD","AF")` / payload `dual_write`
  - 🔴 真库 `G6-2-rows` 是六条里唯一有行的（remark 0 / conclusion 2 = 空数组只落 conclusion）⇒
    判据 SHALL 覆盖「空数组落 conclusion」这一形态，不得假设 remark 非空
  - _Requirements: 4.1, 4.6_

- [x] 14. `phase5_g6_05_sppi_fair_value.py`（无表头行 + 行级 mask，依赖 Task 6 的 BP-7 已修）
  - `G6-5-fair-value-data` / `id` / **无独立表头行**（R9 即数据）/ R9-18 / footer R19 `SUM(D9:D18)` /
    payload **`conclusion_only`**（写死 remark 会指向恒空列）
  - 🔴 行级 mask（B6）：`D` 列仅 R9/R10 有公式 ⇒ 按 F3-H4 行级处置，必要时拆两个 spec；P12 后半
  - _Requirements: 4.1, 4.5_

- [x]* 15. G6-ecl 转置声明（同 G4-ecl，注意区标题差异）
  - `phase5_g6_11_ecl_stage.py`：表头 **R10**（🔴 R9 是区标题「（一）信用风险是否显著增加」，不得当表头）/
    三块锚行 R25/R33/R47 / UUID 第 12 列 / `formula_columns=()`
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x]* 16. G6 三条发布链 + 宿主接桥 + seed + 真栈验收
  - `backend/scripts/e2e/seed_g4_g6_publish_e2e.py`（幂等、`--dry-run` 可离线验）+
    `e2e/fixtures/g4-l2-cases.json` / `g6-l2-cases.json` + 两个 spec.ts，`--workers=1`
  - 🔴 六条主表真库全零或仅空数组 ⇒ **全部真栈用例前置 seed**；未 seed 时验收脚本显式失败（P17）
  - _Requirements: 5.5_

### 阶段 4：收口

- [ ] 17. 收口：BP-10 份额 + TB 红线 + FC-6 核 + 变异复跑
  - 🔴 G4 的 4 条重复字面量（`G4-1-rows` / `G4-9-rows` / `G4-10-rows` / `G4-11-ecl-measurement`）改派生别名，
    照 **G6 的正面样本**（`g6CrossHelpers.G6_11_ROWS_KEY = G6_ITEM_IDS.G6_11_ROWS`）；**G6 侧不动**（P16）
  - TB 红线 P14：sync 路径 TB 写 0；TB 键按值取（`G4-1-adj-tb-1501` / `G6-1-adj-tb-1503`），
    🔴 依赖 foundation GC-9 裁决结论，本 spec **不独立裁决**
  - G4-3 / G6-4 照 FC-6 默认 `single_html` 只产核结论；P15 / P18；全部变异复跑 + 两册 materialize/verify
  - _Requirements: 5.1, 5.2, 5.4, 5.6_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["0"], "rationale": "前置门：TransposedSheetSpec 是 Req 2 硬依赖；foundation 的 GC-1/GC-9 交付状态决定 Task 11/17 能否收口" },
    { "wave": 1, "tasks": ["1", "2"], "rationale": "slice 复核与几何补测互不依赖；Task 2 含 G4-main 的 BP-7 按值定位（裁决 G46-H4）" },
    { "wave": 2, "tasks": ["3", "4", "5"], "rationale": "三组红判据并行；BP-8/转置/16384/BP-7 四条红基线必须先打红" },
    { "wave": 3, "tasks": ["6"], "rationale": "BP-7 修复是 G6-sppi 受管的硬前置（must_fix_before 含发布 contract 之前）" },
    { "wave": 4, "tasks": ["7"], "rationale": "G4 entry 层（三 ADAPTER_ID + 一 TEMPLATE_SHA256）" },
    { "wave": 5, "tasks": ["8"], "rationale": "G4-sppi 首条：零公式 + 无 footer 锚行 + pointer 隔离首验" },
    { "wave": 6, "tasks": ["9", "10"], "rationale": "G4-main 两区 与 G4-ecl 转置+16384 互不依赖" },
    { "wave": 7, "tasks": ["11"], "rationale": "G4 三条发布链；第三条发布时 P1 仍绿 = BP-8 真验收点" },
    { "wave": 8, "tasks": ["12"], "rationale": "G6 entry 层（三条全用 http 客户端）" },
    { "wave": 9, "tasks": ["13", "14", "15"], "rationale": "G6 三张声明并行；G6-5 依赖 Task 6 的 BP-7 已修" },
    { "wave": 10, "tasks": ["16"], "rationale": "G6 发布链 + seed + 真栈（六条全需 seed）" },
    { "wave": 11, "tasks": ["17"], "rationale": "收口：BP-10 份额 + TB 红线 + FC-6 核 + 变异复跑" }
  ],
  "blocking": {
    "0": "TransposedSheetSpec 未入 HEAD ⇒ Task 10/15 阻塞（两条 ECL 无类型可依）；foundation GC-1 未交付 ⇒ Task 7/12 的 pointer 规则无真源",
    "2": "G6-2 多区几何未补测 ⇒ Task 13 无法声明；G4-main 的 BP-7 未定位 ⇒ Task 6 范围不清",
    "6": "BP-7 未修 ⇒ G6-sppi 不得受管、不得发布 contract（slice must_fix_before 明令）",
    "10": "16384 列裁决未落地 ⇒ 两条 ECL 的 UUID 无处放，instrumentation 写入失败",
    "11": "published representation / approved bundle 供给（BP-1~BP-3）⇒ 六条 adapter 注册与真栈验收阻塞；BP-8 的真验收点也在此",
    "16": "seed 脚本未交付 ⇒ 六条主表空载荷验收是假绿",
    "17": "foundation GC-9 三家 TB 裁决未出 ⇒ G4-main / G6-main 不得收口（本地硬门必红）"
  }
}
```

## Notes

- 🔴 **一册三 entry 是 G 循环相对 F 最深的结构差异**：契约钉**同一份** `TEMPLATE_SHA256`、pointer 靠
  `entry_id` 区分（裁决 G46-H2）。FC-3「一 entry 恰一 template_ref」的单射在此不成立（GC-1）。
- 🔴 **BP-8 的真验收点在 Task 11**：第三条 G4 entry 发布 representation 时 P1 仍绿，才算证明 pointer 不互顶。
  只验前两条会漏掉「第三条顶掉前两条」的形态。
- 🔴 **两条 ECL 主表是转置形态且 16384 列**，是本 spec 最硬的两个约束；UUID 取「有效内容列 11 + 1」
  而非 `max_col+1`（后者超 Excel 上限 XFD）。
- 🔴 **四条 entry 用 `http` 不用 `api`**（FD-2，全 G 循环的 4 条全在本 spec）⇒ 守卫按 slice 登记名拼探针，
  照抄 F 的 `api\.` 探针必失配。
- 🔴 **G4-main 的 BP-7 可能不存在**：slice 的 `blocked_by` 列了它但 BP 正文只展开 G6-sppi ⇒
  按值定位后，无缺陷就如实登记「slice 内部不一致」，**不得**为对齐 slice 伪造缺陷（裁决 G46-H4）。
- 🔴 **G6 是 BP-10 的正面样本**（派生别名），G4 照它改；G6 侧不动。
