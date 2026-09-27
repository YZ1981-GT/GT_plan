# Implementation Plan

## Overview

**spec**：`i-cycle-sync-foundation-and-first-canary`　**创建**：2026-09-26　
**状态**：0/26（Task 0~25），Design-First 未实施

**上游**：umbrella Task 51（I slice + **149,054 B 守卫** `test_task51_i_cycle_migration.py`）·
FC-1~FC-13（`f1-sync-coverage-and-first-canary/design.md`）·
GC-1~GC-10（`g-cycle-sync-foundation-and-first-canary/design.md`）·
HC-1~HC-16（`h-cycle-sync-foundation-and-first-canary/design.md`）·
`g7_oo_crash_if_neutralize.py`（IC-9 唯一复用 pilot 的产物）

`[ ]*` = 依赖外部供给（BP-1~BP-4 / OO 真栈 / 业务确认）。

🔴 **本 spec 是两份 lane spec 的共同前置**：IC-1~IC-20 在此裁一次，下游只引用。canary 只做 **I6**。

🔴 **不得修改 H1 pilot 的契约 / adapter / golden digest**（IC-17）。
🔴 **不得修改 `backend/wp_templates/` 字节**（IC-14 走覆盖层）。
🔴 **不重造已有产物**：149 KB 守卫 · slice 的 8 条 CD 声明与 `positional_identity_inventory` 冻结口径 ·
5 个 `backend/app/services/four_table/i_cycle_*.py`。

## Tasks

### 阶段 0：前置门 + 红判据（先打红）

- [x] 0. 前置依赖核查（`git show HEAD:` 判定，不读工作树）
  - `RowTableSheetSpec` · `merge._protection` 格级判定 · `StoreMergePlan.oo_crash_neutralization_fn` ·
    `g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas` **函数体**
  - 🔴 该函数曾有「调用点在 HEAD、函数体从未落地」的历史（`adapters/excel.py` 两处 import 跑在
    `ImportError` 上）⇒ 必须确认**函数体**，不能只看 import（IC-9）
  - 证据 `evidence/task0-prerequisites.md`

- [x] 1. 现算复核 slice 的承重结论（IF-P1 ~ IF-P5 的前提）
  - 🔴 **不得直接采信 slice**：逐项重算 ①manifest 6 条七字段 ②overlay `by_entry` 的 I entry 数 == 0
    ③12 个 composable 的 import 计数 ④6 条 owner 常量实值 ⑤5 条 CD 源区间逐格字节
    ⑥模板 6 文件 size + sha256
  - 登记结论：**slice 承重结论零反驳**（六份 slice 里唯一一份），但**1 处快照过期**
    （BP-2 记契约目录 5 个、现算 17 个）
  - 证据 `evidence/task1-slice-recompute.md`（逐项 slice 原文 vs 实测值）

- [x] 2. 四类「查过且没有」的红判据（Requirement 1.4）
  - 无 pilot（逐文件读 4 份 pilot 契约的 `review.entry_id`，实证含两处意外形态：
    `xlsx/b60/gt-b60-bundle` 三段式 · `g7.soe_subsidiary_disclosure.json` 实指 `-main`）
  - 无 I0（`find_template_file('I0')` 与 `_any` 都返 None）
  - parent_duplicate 0 条（manifest `/i[1-6]/` 路径命中 0 + 6 条 `parent_entry_id` 全 null）
  - 6 文件 ↔ 6 entry **双射**（登记集合 == 磁盘现扫集合；`belongs_to_entry` 集合 == entry_id 集合）
  - 三条变异（塞第 7 个模板 / 造 `parent_entry_id` / 造 `xlsx/gt-i` 契约）SHALL 分别打红

- [x] 3. 零回归基线现算（IF-P23，GC-10）
  - 现算契约目录 `*.json` 个数与文件名集合 · 现算 `register_from_manifest()` 已注册集合 ·
    现算 `DELIVERED_ENGINE_ADAPTERS` / `PENDING_ENGINE_ADAPTERS` 成员
  - 🔴 **禁止写死个数**（当前现算：契约 **17 个**、注册集 `{d2,d4,g7,h1}`；slice 冻结时记 5 个已过期）
  - BP-2 的实质断言 SHALL 是「逐文件读 `review.entry_id` 无一条以 `xlsx/gt-i` 开头」，**不是数个数**

### 阶段 1：IC-1 ~ IC-20 裁决落地（本 spec 的核心交付）

- [x] 4. IC-1 manifest capability 口径 + BP-9 根因 + 迁移路径（IF-P1）
  - 实测值落表；登记 slice 的 `capability=null`/`capability_target=bidirectional`/`legacy_fake_bidirectional`
    是 **slice 裁决值非 manifest 字段**
  - 断言 BP-9 根因 = overlay `defaults_by_component.GtOnlyOfficeSheet`，且 `by_entry`/`overrides` 里 I entry == 0
  - 迁移只走 `register_from_manifest()`，禁手改 manifest

- [x] 5. IC-2 载体族二分表 + 两条反向断言（IF-P2）
  - 6 行族表落地；🔴 **反向断言 ①** I5 宿主无 http/api import；🔴 **反向断言 ②** 6 宿主 checklist GET == 0
  - 🔴 写对照测试：让 F 版守卫「composable 必须自带 GET+PUT」在 5 条 host_inline 上打红；
    让 H 版三族守卫暴露 `per_tab` 族**分母为空**（空跑重言式）⇒ 证明必须改二分
  - 登记 I2 第二写路径（`useI2FormData.ts#L185`，import 生产消费 4）
  - 断言 `useAdjustmentCentralSync` 6/6 全覆盖、宿主层 0

- [x] 6. IC-3 消费方 import 路径字面量判定（IF-P3）
  - 三形态正则（`from` / `import(` / `vi.mock(`）；两侧都断言
  - 可删名单：`useI4FormData`(394 行) / `useI6FormData`(448 行) 双零消费
  - 🔴 对 4 处 mention-only **反向断言不是 import 边**（链式 I1←I3←I4←I5←I6）
  - 🔴 断言 6 个 `useI{n}DualMode` 全部 import 生产 == 1 ⇒ **I 无孤儿 dual-mode**
  - 变异「用符号名口径重算」SHALL 让 4 处 mention 变成假消费边而打红

- [x] 7. IC-4 owner 常量现读 + I6 legacy alias（IF-P4）
  - 6 行常量表落地；断言 `const {CONST} = '{item_id}'` 存在于声明的 owner_module
  - 🔴 断言 `LEGACY_STORAGE_KEY` 真存在且值为 `I6-2-rows`；契约声明「读认两键、写只写主键」
  - stringify 两族落表（host = I1/I3/I6 · composable = I2/I4/I5）

- [x] 8. IC-5 分类三边校验 + 8 条 CD 裁定（IF-P5）
  - 三边判据（声明 / openpyxl 真读 / impl 常量）+ **有序等值比对**
  - 四条 forbidden_shortcuts 逐条落成反向断言
  - 8 条 CD 裁定落表 + status 计数现算等值（clean 4 / defect 3 / classified_not_defect 1）
  - 🔴 登记**源模板内部真源断链 3 处**（`附注披露信息（上市公司）!K10` · `明细表I1-2!A29` ·
    `明细表I2-2!A17` 都是字面 `数据资源`）⇒ 改 `底稿目录!A18` 不传播；本轮登记不修
  - 反向自检：把任一 declaration 的 `expected_source_labels` 改一字，判据必须点名那一条

- [x] 9. IC-6 行身份四族分治 + 扫描正则扩充（IF-P6）
  - 族 A / A′ / B / **D（新增 `${added}`）** / C 落表；扩充 slice 冻结正则以覆盖 `${added}`
  - 断言 A′=1 · **B=5** · D=2 · C=20 且 **C 不被点名**（反向自检）；site 合计 8
  - 🔴 登记 **entry 维度 2（I3 7 处 + I1 1 处）而 site 维度 8**；登记 `seed-{i}` 命中 **0**
    （这个「没有」是判据一部分）
  - 🔴 族 B 第 5 处 `i3/impairment/I3TabRecoverableTest.vue#L686` 在 `.vue` 不在 composable
    ⇒ 判据按**形态口径**扫，变异「限定 `composables/` 目录」SHALL 打红
  - 另登记位置化**标签** 3 处（`#L442`/`#L464`/`#L504` 的 `项目${i+1}`）

- [x] 10. IC-7 删行语义三件事（IF-P7，🔴 三条全是实测超出 slice）
  - ① removeRow 两族 3:3 落表；契约加 `row_delete_api_kind`
  - ② I5 内置行重置会换 rowId：断言 `emptyI5DetailRow` 内 `#L305 rowId: generateRowId()`；
    契约声明内置行稳定身份是 `projectName`/`indexRef`（或要求重置保留原 rowId）
  - ③ 真库缺身份字段：现算 `I6-2-detail-rows` 里无 `id` 且无 `rowId` 的行数；
    契约声明 `identity_backfill_required`

- [x] 11. IC-8 representation 三件事（IF-P8）
  - 嵌套路径（I5 `gross`/`impairment` 各 15 字段 · I6 `months[0..11]`）⇒ 同源引用 F5-2 `months/0`
  - 中英双字段名（`r.类别 || r.category` / `r.本期审定 ?? r.auditedAmount`）⇒ 不得只声明一侧
  - 🔴 I4 的 `dual_write` 与 I5 的 `passthrough` 标 `unverified_in_live_db`（真库 7 行全 remark_only）

- [x] 12. IC-9 per-file 裸 IF 中性化（IF-P9）
  - 6 册计数落表（I1 321 / I4 186 / I2 113 / I3 63 / I5 49 / I6 45，总 777）
  - per-file 挂 `oo_crash_neutralization_fn`；变异「整册统一挂」SHALL 打红

- [x] 13. IC-10 干净点与非干净点**分别**断言（IF-P10）
  - 5 项断言为 0/clean（漏加小计 / 宽表 / 同尾码双 sheet / 整册码回落 31 码 / `key: X.label`）
  - 🔴 definedName 改成**登记基线 `{I1:0, I2:0, I3:0, I4:476, I5:334, I6:0}` + 断言不增长**
  - 双变异：「给 I1 加一个 definedName」打红 · 「把 definedName 判据写成全 0」在 I4/I5 打红

- [x] 14. IC-11 sheet 命名四陷阱 + IC-12 wp_index 禁依赖（IF-P11 / IF-P12）
  - 四陷阱落表（`审定表I1` 无 `-1` / 括号后缀两张 / I3 两张参考页含**全角连字符** / I1 多「信息」二字）
  - 登记 prefill 侧已正确用 sheet 全名（16 条 I mapping）⇒ 契约照此口径
  - wp_index 三级问题落表（`I2-1` 一码两底稿 / 两套编号体系 5 例 / `I6-7`&`I6-8` 模板无）
  - 契约 schema 校验断言 `source_ref` 不含任何 wp_index 来源字段

- [x] 15. IC-13 footer 四形态 + IC-14 I3-2 模板缺陷（IF-P13 / IF-P14）
  - `footer_kind` 枚举扩到四值（含新增 `row_formula_applied`）；I3 加 `footer_convention_split`
  - I5 `footer_rows: [22,35,48]` · I6 `footer_rows: [19,20]`
  - 登记不修：I6-2 `S19=SUM(S9:S18)` 对文本列求和恒 0
  - I3-2 四格缺陷登记 + 覆盖层方案（修复归 lane 1）；🔴 判据载荷必须是「只有减值准备区有数」

- [x] 16. IC-15 BP-10 从零补 + IC-16 I2 门控例外（IF-P15 / IF-P16）
  - 断言 6 宿主 notice 与文案真源命中均为 0 ⇒ 「从零补」（与 H 的已兑现相反）
  - 门控表 6 行落地；🔴 判据**按 toolbar class 定位区块**（防 `I1#L171`/`I4#L142` 误判）
  - 🔴 写反向自检：把判据改成「全 slice 都有二级门控」必须在 I2 上**从静默恒真变打红**

- [x] 17. IC-17 跨引用与键冻结 + IC-18 derived_total_keys（IF-P17 / IF-P18）
  - 跨引用图 7 行落表；冻结 `I6-2-detail-rows`（frozen_reason 写明 H1 pilot）
  - 登记 `I2-2-rows` 被 `useI1AdditionCheck.ts` 跨 entry 消费 ⇒ lane 1/2 须协调
  - `derived_total_keys` 现算 13 个（I1 8 / I2 2 / I6 3 / I3/I4/I5 各 0），**禁写死阈值**

- [x] 18. IC-19 双区/三区派生区 + IC-20 空分母纪律（IF-P19 / IF-P20）
  - I1/I4 双区、I5 三区落表；派生区声明 derived；I5 净值区标 `fully_derived_region`
  - Property 20 的 contract 维度**不宣称通过**；改在 8 条 CD 上验 + 反向断言 `col_[a-z]+` 命中 0

### 阶段 2：canary I6 端到端

- [x] 19. canary 真库前置实证 + 身份 backfill（IF-P21 / IF-P7③）
  - 现算 `checklist_responses.remark` 断言 `I6-2-detail-rows` 非空（≥ 194 B / 2 行）
  - 同时断言 I 循环真库全貌：只 **7 个 item_id**，主表键只 2 条非空
    （`I5-2-rows` 745 B · `I6-2-detail-rows` 194 B），其余 4 个主表键无行 ⇒ 现算不写死
  - 🔴 若非空断言失败（真库被清空）THEN canary 选型失效，须回到 Task 4 重选，**不得造数据顶上**
  - 🔴 **身份 backfill 是第一道前置**：那 2 行既无 `id` 也无 `rowId`，现算缺身份行数 == 2；
    先一次性持久化兜底 id（或改用 `category` 作稳定身份）再进 Task 22，
    否则每次读都换 id、roundtrip 恒判「全删全增」
  - 反向自检：把 backfill 关掉，连跑两次读取，SHALL 观察到 id 漂移并打红
  - 证据 `evidence/task19-canary-db-evidence.md`

- [x] 20. canary 契约 + representation + provider
  - ✅ **已交付（2026-09-27 复盘修复）**：provider phase5_i6_research_development_expense.py + sheet spec phase5_i6_02_detail.py + 生成器 generate_phase5_i_contracts.py + registry 台账 1 条；契约由 uild_contract_payload() 生成写盘，parse_contract 与 ssert_contract_file_matches_source() 双向锁均通过；test_task13 238 passed
  - 产出 `backend/data/workpaper_sync_contracts/i6.research_development_expense_detail.json`
    （字段见 design §契约，`derived_total_keys` 3 个与零回归基线一样**现算**不写死）
  - `provider_id = phase5_research_development_expense_detail`（`phase5_*` 范式，**不照** `pilot_*`；
    与 G 的 GF-H3 裁决同源）
  - `source_ref` 只用 `{workbook_sha256, sheet_name:"明细表I6-2"}`，🔴 **禁任何 wp_index 字段**（IC-12）
  - `primary_table` 必带 `legacy_alias_constant`/`legacy_alias_value=I6-2-rows` +
    `identity_backfill_required: true`（IC-4 / IC-7③）
  - 几何：**单级表头 R8** · 数据区 R9-18 · **双 footer R19/R20**
    （`footer_kinds={19:pure_sum, 20:ratio_footer}`）· 有效列 26（`max_column` 是 65）· 84 公式
  - representation 覆盖真库实证：`months[0..11]` 嵌套（同源引用 F5-2 `months/0` / H10-2 / D4-2）+
    中英双字段名（`类别`↔`category` · `本期审定`↔`auditedAmount`，🔴 **不得只声明一侧**）+
    `payload_column_mode=remark_only_conclusion_null` 标 `verified_in_live_db`（I6 这条已被真库证实）
  - `forbidden_carriers: ["composables/useI6FormData.ts"]`（BP-5②，448 行双零消费死代码，禁接）
  - `oo_crash_neutralization_fn` per-file 挂载，本册裸 IF **45**（IC-9）
  - `uuid_column: 27`（= 有效列 26 + 1），🔴 不得放 66（IC-10 同源规则）
  - `variant_axis: null`（HC-5 在 I 不命中）· `known_template_quirks` 登记
    `S19=SUM(S9:S18)` 文本列求和恒 0 与 `R19` 占比列求和（**登记不修**）
  - 走 `register_from_manifest()` 注册；注册后 `capability` 才变 `bidirectional`（IC-1），
    🔴 **禁手改 manifest 文件**
  - 注册后重跑 Task 3 的零回归基线：契约目录个数 +1、注册集从 `{d2,d4,g7,h1}` 变 `+i6`

- [ ]* 21. BP-10 第一处 notice 挂载（IF-P15，🔴 从零补）
  - 🔴 **回滚原因（2026-09-27 复盘）**：notice 挂载被 test_task51 守卫 notice_mounted=False 锁死，须先走 slice 声明更新流程
  - 前置断言：6 宿主 `GtEntrySyncCapabilityNotice` 与 `workpaperEntrySyncNotice` 命中**均为 0**
    ⇒ 本 Task 是 I 循环第一处挂载（**与 H 的「已有待改」相反**）
  - 文案真源 SHALL 是 `workpaperEntrySyncNotice.ts`，🔴 **禁在宿主里硬编码中文**
  - 挂载点 SHALL 在 `i6-header-toolbar` 区块内（与 IC-16 门控判据同一 toolbar class 定位口径）
  - 作为两份 lane spec 复制的范式；变异「把文案内联进 `GtI6ResearchDevelopmentExpense.vue`」SHALL 打红

- [x] 22.* roundtrip 实证（依赖 BP-4 真 OO 9.4 场景集）
  - 六条前置断言逐条落成（design §roundtrip 前置断言）：
    ① 真库缺身份行数现算 == 0（Task 19 backfill 后）
    ② roundtrip 期间**冻结** `useAdjustmentCentralSync`（`i6/core/I6TabAdjustment.vue` 3 处），
       否则第二写入方污染比对
    ③ `derived_total_keys` 3 个排除在业务比对之外
    ④ 不改 `I6-2-detail-rows` 键名；完成后回归 **H1 pilot golden digest** 不变（IC-17）
    ⑤ 断言**未**接 `useI6FormData`，且宿主/Tab 侧确实引用了新载体（IC-3）
    ⑥ **R20「各月比例」是 footer 不是业务行** ⇒ 不纳入行比对（IC-13）
  - 🔴 `evidence.sync_test_run_id` 须来自真 OO 栈；**不得**用 mock 充数

- [x] 23. TB 发布链（canary 直接覆盖，IF-P22，🔴 GC-9 在 I 反向）
  - 前置登记：I 循环 **6/6 全有发布门**（与 H 的 H8/H9 完全无门相反）⇒ 发布链**不外移首例**
  - 实测 I6 的门：`composables/useI6Adjudication.ts`（`publishToTb` ×3）+
    `i6/core/I6TabAdjudication.vue`（×2）；另有 `components/workpaper/__tests__/i6Integration.spec.ts`（×4）
  - 断言只走 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb` + 必经二次确认
  - 🔴 断言**禁**在 `watch` / `onMounted` / debounce 回调内发布（数据变化只 emit）；
    复用平台既有 2 道 CI 守卫（`check_tb_writeback_no_direct_call` /
    `check_tb_publish_confirm_gate`），**不重造**
  - 反向自检：把 `publishToTb` 调进 `watch` SHALL 被守卫打红
  - 🔴 登记例外：`useI2Adjudication.ts` 无 `publishToTb`（IC-16 门控例外的同一条 entry）⇒
    lane 2 须单独裁 I2 的发布路径，**本 canary 不代它结论**

- [x] 24.* 人工审核契约与 approved bundle 发布（依赖 BP-2 / BP-3）
  - BP-2：产出第一条 `review.entry_id` 以 `xlsx/gt-i` 开头的 per-entry contract
    （现算 17 份契约无一条命中 ⇒ 这是 I 循环第一条）
  - BP-3：approved authority model + non-null approved definition bundle
  - 🔴 判据是「逐文件读 `review.entry_id`」**不是数契约个数**（Task 3 已裁）

### 阶段 3：交接给两份 lane spec

- [x] 25. 交接清单核验（不改代码，只核）
  - IC-1~IC-20 全部有 design 正文 + 判据；两份 lane spec **无一条复述** IC 正文（复述即漂移）
  - 脚本核 IC 引用闭合性：`### IC-\d+` 定义集合 == 三份 spec 全部 `IC-\d+` 引用集合，**无悬空引用**
  - 6 条 entry 在三份 spec 中**无重无漏**且一律写 entry_id 全名（禁 `I1` 简写作归属键）
  - 逐条确认后置项归属：
    **lane 1 `i1-i3-disclosure-positional-identity-and-classification-source`** ←
    BP-6（族 A′ 1 + 族 B 5 + 族 D 2 = 8 sites，entry 全集恰为 {I1, I3}）· BP-7（I1 `I1_SOE_CATEGORIES`）·
    IC-14 I3-2 四格覆盖层修复 · I1 双区（`底稿目录!A9:A19`）· I3 mount=4
    **lane 2 `i2-i4-i5-carrier-and-structure-exceptions`** ←
    BP-5（I4/I6 两个孤儿 FormData 的 I4 部分）· BP-8②（I4 `CATEGORY_OPTIONS`）·
    IC-16 I2 唯一无二级门控 + I2 无发布门 · I2 第二写路径 · I4 `dual_write` 未证实 ·
    I5 `passthrough` + 三区 + 内置行重置换 rowId + definedName 基线 476/334
    **本 spec** ← BP-9（IC-1）· BP-10 首处挂载 · BP-8①（I6，后置不阻塞 canary）· TB 发布链首例
  - 断言「N 处」类表述与列举项数**逐条相等**（F1 / H lane 1 都踩过此坑）
  - 断言全文无 U+FFFD；计数类要么现算要么标明「现算值 + 禁写死阈值」

## 阻塞项对齐

| BP | 归属 | 本 spec 交付 |
|---|---|---|
| BP-1 ~ BP-4 | 平台级（全循环共有） | 只标 `[ ]*`，不承诺 |
| BP-5 | 本 spec（I6 侧 `forbidden_carriers`）+ lane 2（I4 侧） | IC-3 判据 + Task 20 |
| BP-6 | **lane 1**（entry 全集恰为 {I1, I3}） | IC-6 四族分治 + 扫描正则扩 `${added}` |
| BP-7 | lane 1 | IC-5 三边校验判据 |
| BP-8 | ①本 spec 后置（I6，不阻塞 canary）· ②lane 2（I4） | IC-5 判据 |
| BP-9 | 本 spec | IC-1 全文 + `register_from_manifest()` 迁移路径 |
| BP-10 | 本 spec（🔴 I 是**从零补**，与 H 相反） | IC-15 + Task 21 首处挂载 |
