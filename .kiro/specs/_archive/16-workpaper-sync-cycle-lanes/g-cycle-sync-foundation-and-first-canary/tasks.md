# Implementation Plan

## Overview

**spec**：`g-cycle-sync-foundation-and-first-canary`　**创建**：2026-09-26　**状态**：0/19（Task 0~18），Design-First 未实施
**上游**：umbrella Task 49（G slice / 删除清册 / 179 KB 守卫）· FC-1~FC-13（`f1-sync-coverage-and-first-canary/design.md`）·
D1 引擎 · `phase5_d3_prepaid_receipts.py:830` · `g7_oo_crash_if_neutralize.py` · D4-29 转置先例

`[ ]*` = 依赖外部供给（BP-1~BP-4 / OO 真栈 / 业务确认）。

🔴 **本 spec 是三份 lane spec + 一份后置审定表 spec 的共同前置**：GC-1~GC-10 在此裁一次，
下游只引用。canary 只做 G2 一条。

## Tasks

### 阶段 0：前置门 + 红判据（五条红基线先打红）

- [x] 0. 前置依赖核查（`git show HEAD:` 判定，不读工作树）
  - 框架层 `RowTableSheetSpec` / `phase5_transposed_sheet.TransposedSheetSpec`（GC-4 依赖）/
    `merge._protection` 格级判定 / `StoreMergePlan.oo_crash_neutralization_fn`（GC-2 依赖）/
    `g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas` 函数体是否在 HEAD
  - 🔴 该函数曾有「调用点在 HEAD、函数体从未落地」的历史（`adapters/excel.py` 两处 import 跑在 `ImportError` 上）
    ⇒ 必须 `git show HEAD:` 确认函数体存在，不能只看 import
  - 证据 `evidence/task0-prerequisites.md`
  - _Requirements: 3.1, 3.4_

- [x] 1. slice 复核 + 17 条 entry 事实比对 + wp_code 裁决条目
  - 逐条核 slice `independent_entries` 的 `capability=null` / `capability_target` / `stage` /
    `migration_state` / `adapter_id` / `template_ref` / `mount_count` 与现 manifest 是否漂移（slice 冻结于 2026-08-31）
  - `workpaper_sync_entry_wp_code_adjudication.json` 新增 **13 条** G 条目（按册，G4/G6 各一条覆盖三 entry）：
    真码 `wp_codes=["G{N}"]` + 幻影码见 manifest `wp_code_pattern`；G4/G6 两条的
    `matcher_domain_conflict` 如实写 BP-8 与 GC-1 解法；重算 digest
  - 🔴 `store_payload_evidence` 逐条如实填真库实测值（G5 12,952+2,844 B 最多 / G3 仅 12 B 最少），不伪造
  - _Requirements: 1.3_

- [x] 2. GF-P1 / P2 / P3 红判据：FC 重裁 + 两条「缺陷不存在」+ 逐 entry 阻塞
  - P1 四条子判据（FC-3 不成立 / FC-8 不适用 / FC-11 不命中 各有正向证据）+ 自省变异（把 FC-3 改回成立必红）
  - P2 现算两条（13 整册码 + 8 子码解析正确 / 磁盘 15 vs 索引 15 差集空）+ 变异「塞未索引册子」
  - P3 17 条 `capability_target_blocked_by` 逐元素 + 变异「把 BP-5 套到 G2」
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 3. GF-P4 / P8 / P17 / P18 红判据（四条红基线，现状必红）
  - P4：`G1_SHEET_LABEL_MAP` 18 条 vs 模板真实 tab，现状 **5 条不命中**（RG-5 的 BP-5 侧）
  - P8：用 `_BARE_IF_CALL` 真实正则现算 13 册裸 IF（G1 141 / G4 186 / G6 192 …），现状 13 条
    `StoreMergePlan` **全部无** `oo_crash_neutralization_fn` ⇒ 必红
  - P17：新断言「块 sheet ∈ 源 xlsx 真实 tab」现状 **2 块不命中**（`[169]`/`[170]`）⇒ 必红
  - P18：G1/G4-main/G6-main 的 `publishToTb` 计数现算为 **0** ⇒ 必红
  - _Requirements: 2.1, 3.1, 3.2, 5.1, 5.2, 6.1_

- [x] 4. GF-P20 零回归基线（**现算逐项**，不写死数字）
  - 现算并落证据：`check_sync_provider_golden_digest.PROVIDERS` 当前成员 + 契约目录当前 json 清单
  - 🔴 判据形态 SHALL 是「非 G 的 digest 逐项不变」，**不得**断言集合大小（GC-10；写死数字会因并发交付 stale）
  - _Requirements: 7.1_

### 阶段 1：四条 G 专属前置的处置（canary 之前）

- [x] 5. BP-5 修复：`g1SheetLabels.G1_SHEET_LABEL_MAP` 5 条错名 → 模板真名
  - 逐条按值改（含 `交易性金融资产实质性程序表G1A ` **尾部空格必须保留** —— 空格是源模板事实）；
    `业务模式评估问卷G1-8` → `业务模式分析G1-8` 等余 4 条按 Task 3 的实测清单
  - P4 转绿（18/18 ∈ 模板 sheetnames）+ 变异「strip 后比较」必红
  - 🔴 `must_fix_before` 原文含「也在为它发布 contract 之前 —— 契约的 source_ref 要写 sheet 名」⇒ 排在 canary 之前
  - _Requirements: 2.1_

- [x] 6. GC-2 落地：13 册 per-file 挂 OO 崩溃中性化
  - 13 条 `StoreMergePlan` 全带 `oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas"`
    （复用 G7 已被真 OO 栈验收过的口径，**不新造**）
  - 🔴 **不得**在 `adapters/excel.py` 新增 `if adapter_id ==` 字面量分支（Task 13 已收敛掉两处）
  - P8 转绿 + P9（只改 substrate 副本 / 权威模板 sha 不变 / `verify_unmanaged_regions` 不报漂移）
  - 🔴 BP-4 未交付前如实登记为「per-file 保守策略」，**不得**以裸 IF 数少推断某册不需要
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 7. GC-8 落地：prefill 两块改名 + 补 G 循环缺失的 sheet 存在性守卫
  - 块 `[169]` → `明细表G13-2`、块 `[170]` → `明细表G14-2`（模板真名，Task 3 已按值核）
  - 在**既有文件** `backend/tests/four_table/test_g_cycle_formula_presets.py` 增断言，口径照
    `test_i_cycle_formula_presets.test_sheet_exists_in_template`，**不新造第二套**
  - P17 转绿四条（改名 / 新断言修复前必红 / 不 strip 空格 / G13=14 与 G14=13 计数不减）
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x]* 8. GC-9 落地：三家 TB 缺口书面裁决 + 立本地硬门
  - 逐处按值核 `useG1Adjudication.ts`(trial-balance×2 / writeback×5) · `useG4MainAdjudication.ts`(×1/×3) ·
    `useG6MainAdjudication.ts`(×1/×2) 是**活路径**还是注释/类型残留 —— 不得推断
  - 活路径 ⇒ 登记为 `tb-writeback-explicit-publish-gate` 的遗漏项（附 entry 清单）+ 三家 `blocked_by` 追加本地前置；
    死代码 ⇒ 登记零消费方证据并放行
  - 修 `useG6MainAdjudication.ts:53` 的错注释（「已纠正为 1505」→ 真码 **1506**；1505 在 `KNOWN_BAD_CODES` 里）
  - P18 / P19（TB 键按值取，变异「按 `G_ACCOUNT_CODES` 生成 `G4-1-adj-tb-1504`」必红）
  - 🔴 本 spec **不改造** TB 回写路径（属另一 spec 作业面）
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 9. BP-6 / BP-9 / BP-11 登记（不动代码）
  - BP-6：P7 断言 manifest 与 slice 的 capability **必须不等** + overlay 未改动 +
    🔴 本 spec docstring 不得出现 BP-9 那种论证（「manifest 里是 single_onlyoffice 所以走 X lane」）
  - BP-9：P6 断言 `useG1DualMode.ts` 与 `useWorkpaperEntryDualMode.ts` 均未被删、`GtE1MonetaryFund.vue` digest 不变；
    落 E 循环 deletion plan 的解锁条件原文
  - BP-11：登记不可达旧桩 `GtG6OtherBondEcl.vue` 的 `notice=0` 实测事实 + 断言它不进任何受管清单
  - _Requirements: 2.4, 2.5, 2.6_

- [x] 10. GC-1 守卫：representation pointer 按 `entry_id`（BP-8 的共性裁决，不做六条实施）
  - 构造 G4 三条 entry 先后发布 representation ⇒ pointer / generation 三条独立（P5）
  - owner 模板并集 == entry 全集 且 每 entry 恰被一张模板认领（单射改满射+唯一认领）
  - 变异：pointer 改用 `wp_code` ⇒ 互顶必红
  - 🔴 六条 G4/G6 entry 的实施归 `g4-g6-shared-workbook-three-entry-lanes`
  - _Requirements: 2.2_

### 阶段 2：canary 链路（G2 应收利息）

- [x] 11. `phase5_g2_interest_receivable.py` 从零建（**`phase5_*` 范式，不照 G7 的 `pilot_*`**，裁决 GF-H3）
  - `ENTRY_ID="xlsx/gt-g2-interest-receivable"` / `ADAPTER_ID="g2.interest_receivable_detail"` /
    `WP_CODES={"G2I"}`（幻影码）/ `TEMPLATE_RELATIVE_PATH="G/G2 应收利息.xlsx"` /
    `TEMPLATE_SHA256="c7563e85a3ebffb7…"`（Task 1 逐字补全 64 位）
  - `assert_entry_selectable(*, resolution, manifest=None)`（D3 同签名、无关闭开关、真 manifest 真调）+
    `build_matcher()`（带 `document_type="xlsx"`）+ `build_registration` 照 `phase5_d3_prepaid_receipts.py:830` +
    **真构造判据**；灰度开关（除 G2-2 外默认 False）+ `all_store_item_ids` + `instrumentation_specs()` 复数 +
    `build_contract_payload` + `attach_pilot_adapters`
  - 🔴 `StoreMergePlan` 带 `oo_crash_neutralization_fn`（GC-2，G2 册裸 IF 40 格）
  - _Requirements: 4.2_

- [x] 12. `phase5_g2_02_detail.py` canary 薄声明（无 def/class）
  - `G2-2-detail-rows` / 行身份 **`id`**（`generated_prefixed_opaque_string`，`useG2Detail.ts#L146`）/
    **单级表头 R9** / 数据 R10-15 / footer R16「合计」`=SUM(C10:C15)` / 有效列 13(A-M) /
    `formula_columns=("E","H","J")` / `{"E":"=C{r}+D{r}","H":"=C{r}+F{r}-G{r}","J":"=H{r}+I{r}"}`
  - 🔴 payload `json_pointer` 指 **`remark`**（GC-5；G2 是 `remark_only` + null 占位子形态）
  - 字段键逐字取 `useG2Detail` 行接口（A-M 十三列）；P10 / P11 / P12
  - _Requirements: 4.1, 4.3, 4.4_

- [x] 13. `G2-2-detail-rows` 声明收敛为单一真源（RG-9 的 G2 份额）
  - 现状 slice 冻结口径下 **5 处**重复声明 ⇒ 收敛为一处 + 其余改派生别名（照 G6 的
    `g6CrossHelpers.G6_11_ROWS_KEY = G6_ITEM_IDS.G6_11_ROWS` 范式）
  - P12 后半（声明处计数 == 1）；🔴 `must_fix_before` = 发布 per-entry contract 之前
  - _Requirements: 4.4_

- [x]* 14. 契约发布链五环 + 六个登记点
  - `generate_phase5_g2_contract.py --apply` → `g2.interest_receivable_detail.json` →
    `assert_contract_file_matches_source` → approved bundle → published representation → entry_state →
    `register_from_manifest()`
  - 登记点：`DELIVERED_PER_ENTRY_CONTRACTS` + `_ALLOWED_PROVIDER_MODULES` + `store_item_registry` plan（含中性化声明）+
    `check_sync_provider_golden_digest.PROVIDERS` + wp_code 裁决 + overlay 重生 manifest
  - P13 / P20；🔴 第③环卡 BP-1~3 时如实 `upstream_gap`
  - ⚠️ **残留（2026-09-27）**：①②④⑤环 + 六登记点全交付；**第③环 published representation
    卡 BP-1~BP-3**，已如实登记 `upstream_gap`（未改 overlay 伪造 bidirectional）。
    另：零回归门 `check_sync_provider_golden_digest.py` 整体仍红 —— **F1 既存 bug**
    （`build_store_projection` 两位置参 ⇒ `TypeError`），已在
    `KNOWN_PRE_EXISTING_BLOCKERS` 具名登记；G2 照 E1 的单位置参形态，自身可算。
  - _Requirements: 4.5, 4.6, 7.1, 7.2_

- [x] 15. 宿主接桥（**保留共享基座**）
  - `GtG2InterestReceivable.vue` 引入 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`，
    保留 legacy `GtOnlyOfficeSheet`（4 处）给未迁移 sheet；`isG2SyncManagedSheet` 从 provider 派生
  - 🔴 G2 是 G 循环**唯一**包共享基座的（`useG2DualMode.ts` 59 行 → `useWorkpaperEntryDualMode.ts`）⇒
    接桥 SHALL 保留基座、**不内联展开**（P14；删基座会打断多个循环）
  - 保留 `GtEntrySyncCapabilityNotice`（AC 1.4）
  - _Requirements: 4.7_

- [x]* 16. canary 真栈验收（**不 seed**，但须断言载荷非空）
  - `e2e/fixtures/g2-l2-cases.json` + `e2e/g2-l2-oo-to-html-all.spec.ts`，`--workers=1`
  - 🔴 裁决 GF-H2：真库 `G2-2-detail-rows` 已有 **475 B** 真实载荷 ⇒ 不交付 seed 脚本，
    但验收判据 SHALL 先断言「参与 roundtrip 的行数 > 0 且来自真库」（P15），防「空表往返也算 `store_mirrored`」
  - 三谓词 + DB 证据
  - ⚠️ **残留（2026-09-27）**：fixture + spec + P15 静态守卫（8 条）已交付并全绿，
    真库前置已现算（475 B / **1 行** / wp `ede443da…` / project `0ec33ac9…`）；
    **三谓词本体未实测** —— manifest capability 仍 `single_onlyoffice`（BP-1~BP-3 平台级欠账）
    ⇒ adapter 未注册，用例如实标 `pending_adapter`。供给就绪后改 `pass` 并补五步。
    顺带修：本 lane fixture 走 `readFileSync` —— F1 lane 的裸 JSON import 让其 spec
    **整体加载失败**（`--list` = 0 tests），已具名登记。
  - _Requirements: 4.8_

- [x] 17. FC-9 TB 红线（G2 侧）
  - sync 路径对 `trial_balance` 写次数为 **0**；`publishToTb`（科目 **1132**、余额口径，`useG2Adjudication.ts`）
    仍是唯一入口；变异「sync 回写里调 publishToTb」必红（P16）
  - 🔴 legacy 双键：契约只声明主键 `G2-1-tb`，`G2-1-adj-tb-1132` 读回退**不得删**
  - _Requirements: 4.9_

### 阶段 3：收口 + 交棒

- [x] 18. 收口：既有产物复用核 + 后置决定登记 + 三份 lane 交棒
  - P21：新判据加在 `test_task49_g_cycle_migration.py`(179 KB) / `test_g_cycle_formula_presets.py` 内，
    或有显式「为何另起文件」证据；三个既有产物（守卫 / 变异脚本 / 51 KB 删除清册）未被替换
  - 登记裁决 GF-H5（13 张审定表另立第五份 spec `g-cycle-adjudication-sheets-coverage`）+ 三条共性证据
  - 全部变异复跑 + 整册 materialize/verify + 公式管理入口两模式可达
  - 交棒清单：三份 lane spec 各自的 entry 集合 + 本 spec 已裁的 GC-1~GC-10 引用点
  - _Requirements: 1.1, 7.3, 7.4_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["0"], "rationale": "前置门：TransposedSheetSpec（GC-4）与 oo_crash_neutralization_fn（GC-2）是两条 GC 裁决的硬依赖；后者曾有「调用点在 HEAD、函数体从未落地」的历史，必须 git show HEAD: 确认函数体" },
    { "wave": 1, "tasks": ["1"], "rationale": "slice 复核（冻结于 2026-08-31，需核漂移）+ 13 条 wp_code 裁决条目" },
    { "wave": 2, "tasks": ["2", "3", "4"], "rationale": "三组红判据并行；四条红基线（BP-5 / 裸 IF / prefill 错名 / TB 缺口）必须先打红" },
    { "wave": 3, "tasks": ["5", "6", "7", "9", "10"], "rationale": "四条 G 专属前置的处置互不依赖：BP-5 修 / GC-2 挂中性化 / GC-8 prefill+守卫 / BP-6·9·11 登记 / GC-1 pointer 守卫" },
    { "wave": 4, "tasks": ["8"], "rationale": "GC-9 三家 TB 缺口裁决（需 Task 3 的现算证据；含改 G6 错注释）" },
    { "wave": 5, "tasks": ["11"], "rationale": "provider 从零建（phase5_* 范式），依赖 Task 6 的中性化声明位" },
    { "wave": 6, "tasks": ["12", "13"], "rationale": "canary 薄声明 与 键声明收敛并行；后者是发布契约的硬前置" },
    { "wave": 7, "tasks": ["14"], "rationale": "发布链五环 + 六登记点；第③环卡 BP-1~3 时如实 upstream_gap" },
    { "wave": 8, "tasks": ["15", "17"], "rationale": "宿主接桥（保基座）与 TB 红线判据互不依赖" },
    { "wave": 9, "tasks": ["16"], "rationale": "真栈验收（不 seed 但先断言载荷非空），是三份 lane 真栈的硬前置" },
    { "wave": 10, "tasks": ["18"], "rationale": "收口 + 登记审定表后置决定 + 三份 lane 交棒" }
  ],
  "blocking": {
    "0": "oo_crash_neutralization_fn 函数体未在 HEAD ⇒ Task 6 阻塞、13 册无法挂中性化；TransposedSheetSpec 未入 HEAD ⇒ GC-4 只能留裁决不能实施（不影响本 spec，影响 G4/G6 lane）",
    "5": "BP-5 未修 ⇒ 任何引用 G1 sheet 名的契约 source_ref 不可信（must_fix_before 明令「发布 contract 之前」）",
    "6": "13 册未挂中性化 ⇒ 任一 G entry 开 OO 都可能 editor_error_-82，canary 真栈验收不可信",
    "8": "三家 TB 缺口未裁决 ⇒ G1 / G4-main / G6-main 不得受管（本地硬门必红）",
    "10": "GC-1 pointer 规则未定 ⇒ g4-g6 lane 会各写一套，BP-8 的 representation 互顶无守卫",
    "13": "G2-2-detail-rows 仍 5 处重复声明 ⇒ 不得发布 per-entry contract（BP-10 must_fix_before）",
    "14": "published representation / approved bundle / instrumentation candidate 供给（BP-1~BP-3）⇒ adapter 注册与真栈验收阻塞",
    "16": "BP-4（真 OO 9.4 场景集）未跑 ⇒ 验收状态停在 UNVERIFIABLE，且 GC-2「某册不需中性化」的结论永远不得下"
  }
}
```

## Notes

- 🔴 **本 spec 是 G 循环 17 条 entry 的唯一地基**：GC-1~GC-10 在此裁一次，三份 lane spec + 一份后置审定表 spec
  只引用不复述（否决各 spec 复述 —— F 循环已验证会漂移）。
- 🔴 **FC-3 / FC-8 / FC-11 在 G 循环不成立或不命中**，这是与 F 循环最大的结构差异：
  一册可服务 3 entry（GC-1）· 零 OCR · prefill 47 块全 `cells`。照抄 F 的守卫会静默失配
  （slice 原文：「正则找不到 `api.get` 就当没有写入路径 → 要么假红要么被 `if` 兜住变假绿」）。
- 🔴 **G7 是同循环已迁移先例但范式不同**：它走 `pilot_*`，新建的 17 条一律用 `phase5_*`（裁决 GF-H3）；
  唯一必须复用 G7 的是 `oo_crash_neutralization_fn`（范式无关的 per-file 缓解件）。
- 🔴 **canary 选 G2 而非「数据区零公式」的 G4-7**：后者虽最简但属 G4 册、被 BP-8 卡住 representation 发布，
  而 canary 必须走完发布链。G2 的三条加分理由见裁决 GF-H1。
- 🔴 **零回归基线一律现算**（GC-10）：契约目录本轮从 10 涨到 12（并发会话交付 d1/d3/d5/d6/d7/e1），
  写死数字的判据下次交付即 stale。
- 🔴 **BP 编号跨循环 slice 同号不同义**：G 的 BP-7 命中 G6-sppi 一条，F 的 BP-7 命中 F2-main 与 F5 两条；
  引用时必带循环前缀（`G-BP-7` / `F-BP-7`）。
