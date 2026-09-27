# Implementation Plan

## Overview

**spec**：`i1-i3-disclosure-positional-identity-and-classification-source`　**创建**：2026-09-26　
**状态**：0/22（Task 0~20，含 11a），Design-First 未实施

**上游（只引用不复述）**：`i-cycle-sync-foundation-and-first-canary`（**IC-1 ~ IC-20** + canary I6 范式）·
umbrella Task 51 的 I slice · FC-1~FC-13 · GC-1~GC-10 · HC-1~HC-16。

`[ ]*` = 依赖外部供给（BP-1~BP-4 / OO 真栈 / 业务确认）。

🔴 **本 lane 的主线只有一件事**：把 I1/I3 披露层的行身份从「位置」改成「值」。
🔴 **不得修改 `backend/wp_templates/` 字节**（ID-3 走覆盖层）。
🔴 **不得修改 H1 pilot 的契约 / adapter / golden digest**（IC-17）。
🔴 **不得改 `I2-2-rows` 键名**（I1 侧跨 entry 消费它，ID-8）。
🔴 **不重造已有产物**：149 KB 守卫 · `iAdjudicationPublishGate.spec.ts`（已含 `buildI1`/`buildI3`）·
`i1CategoryScope.spec.ts` · `iCycleDynamicRows.spec.ts` · `i1DisclosureAddCategory.spec.ts` ·
`useI3Impairment.ts#L128` 的 cgu id 生成器 · 5 个 `four_table/i_cycle_*.py`。

## Tasks

### 阶段 0：前置门 + 红判据（先打红）

- [x] 0. 前置依赖与已有产物清点（`git show HEAD:` 判定，不读工作树）
  - 核 `RowTableSheetSpec` · `StoreMergePlan.oo_crash_neutralization_fn` ·
    `g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas` **函数体**（IC-9 的历史坑：
    调用点在 HEAD 但函数体曾从未落地）
  - 清点本 lane 不得重造的 5 个既有测试/生成器，逐个写明「已存在 ⇒ 只在其上补断言」
  - 证据 `evidence/task0-prerequisites.md`

- [x] 1. 现算复核三组承重结论（ID-P1 / ID-P7 / ID-P12 的前提，先打红）
  - 🔴 ①**位置化 site 清单 8 项**逐行现读（族 A′ 1 / 族 B 5 / 族 D 2；按 entry I3 7 + I1 1）；
    与 design ID-1 表**逐项等值**，任一不符 SHALL 停止并回地基 spec Task 9 重裁
  - 🔴 ②**CD-1 的 impl 双定义**现读两处字面量（`i1CategoryScope.ts#L19` 的 `I1CategorySlot[]` 与
    `useI1Adjudication.ts#L105` 的 `readonly string[]`），断言两边 label **有序等值** 11 条
  - 🔴 ③两册几何七项 openpyxl 现读（表头 / 数据区 / footer / 有效列 / `max_column` / 公式数 / merged）
  - 另现算：I3 mount==4 · `legacyOO` I1 4 / I3 6 · 裸 IF I1 321 / I3 63 · definedName 两册均 0 ·
    `derived_total_keys` I1 8 / I3 0 · 真库 `I1-2-rows`/`I3-2-rows` **均无行**
  - 证据 `evidence/task1-recompute.md`（逐项「design 声明值 vs 现算值」两列表）

- [x] 2. 零回归基线现算（ID-P25，GC-10）
  - 现算契约目录 `*.json` 个数与**文件名集合** · `register_from_manifest()` 已注册集合 ·
    `DELIVERED_ENGINE_ADAPTERS` / `PENDING_ENGINE_ADAPTERS` 成员
  - 🔴 **禁写死个数**（地基 spec Task 3 现算为 17 个 / 注册集 `{d2,d4,g7,h1}`，canary 注册后会变）
  - 断言本 lane 开工前「无一条契约 `review.entry_id` 以 `xlsx/gt-i1` 或 `xlsx/gt-i3` 开头」

### 阶段 1：ID-1 位置化行身份分治修复（本 lane 主线）

- [x] 3. 形态口径扫描守卫（ID-P1 / ID-P2）
  - 正则按**形态**写：`r.rowId \|\| <下标>` / `` `…-${i}` `` / `${added}`，
    扫描范围含 `.vue`（IC-6 冻结的 235 文件口径，排除 `__tests__`）
  - 🔴 变异「把扫描限定为 `composables/` 目录」SHALL 打红（漏 `I3TabRecoverableTest.vue#L686`）
  - 🔴 变异「正则不含 `${added}`」SHALL 打红（漏 site #7/#8）
  - 守卫输出 SHALL 是「site 列表 + 族标签」而非只给计数（计数相等但成员错也要能看出来）

- [ ]* 4. 修族 A′ site #1 + 落库链路回归（ID-P1）
  - 🔴 **回滚原因（2026-09-27 复盘）**：位置化修复被 test_task51 positional_identity_inventory 锁死（守卫断言缺陷仍在），须先更新 slice 声明
  - `composables/useI3Disclosure.ts#L488` 的 `rowId: \`cgu-${i}\`` 改用稳定生成器；
    生成器 SHALL **复用** `composables/useI3Impairment.ts#L128` 现成的
    `cgu-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`（同 entry 已有产物，不新造 util）
  - 断言落库链路不变：`#L497 _persistSection('cgu_allocation')` → `#L870 _persistSection`
    → `GtI3Goodwill.vue#L319 http.put`，键 `I3-disc-{listed\|soe}-cgu_allocation-rows`
  - 🔴 这是 8 个 site 里**唯一确证真落库**的一处 ⇒ 判据 SHALL 含「写入后重读，rowId 不随行序变」

- [ ]* 5. 修族 B 5 处（ID-P1 / ID-P2）
  - 🔴 **回滚原因（2026-09-27 复盘）**：同上
  - `useI3Disclosure.ts#L441` / `#L463` / `#L503` · `i1DisclosureEnhance.ts#L241` ·
    🔴 `i3/impairment/I3TabRecoverableTest.vue#L686`（**第 5 处在 `.vue`，最容易漏**）
  - 只改**回落分支**：`r.rowId` 存在时仍用上游 rowId（不得反向覆盖上游身份）
  - 判据 SHALL 覆盖两个真实回落情形：「四表 prefill 派生行未保存」「旧数据无 rowId」

- [ ]* 6. 修族 D 2 处（ID-P1）
  - 🔴 **回滚原因（2026-09-27 复盘）**：同上
  - `useI3Disclosure.ts#L665 perf-${Date.now()}-${added}` · `#L725 ap-${Date.now()}-${added}`
  - 去掉 `${added}`，改用与族 A 同一生成器
  - 判据 SHALL **先复现原缺陷**：同一毫秒内两次批量预填、`added` 均从 0 起 ⇒ 撞 id（修复前打红）

- [ ]* 7. grandfather 策略 + 反向自检（ID-P4）
  - 🔴 **回滚原因（2026-09-27 复盘）**：同上
  - 旧格式正则 `^(cgu\|bv\|imp\|perf\|ap\|tc-i18)-\d+$` 读取时仍认，写入只写新格式
  - 契约两份均声明 `legacy_positional_ids_grandfathered: true`
  - 🔴 反向自检：造一条 `cgu-3` 历史行，修复后重读 SHALL 仍是 `cgu-3`（被重写成新格式即打红）

- [x] 8. 族 C 反向断言 20 处不被点名（ID-P3）
  - 断言 `i1AdditionCheckModel.ts#L314` · `i1DisclosureSyncPayload.ts#L43` ·
    `useI{1,2,3}Adjustment.ts` 等 **20 处展示序号**一处都不在守卫输出里
  - 🔴 「20」SHALL 现算并与列举项数逐条相等；变异「把任一族 C 报成缺陷」SHALL 打红

- [x] 9. ID-6 组合判据：下标族删行 × 位置化身份（ID-P19 / ID-P20）
  - 场景：披露区给 5 行 → 按下标删第 3 行 → 重读；
    断言剩余 4 行 rowId 集合 == 原 1/2/4/5 行的 rowId 集合
  - 🔴 修复**前** SHALL 打红（`cgu-${i}` 会让原 4/5 行变成 `cgu-2`/`cgu-3` 与原 3/4 行重合 ⇒ 数据串行）
  - 两份契约 `row_delete_api_kind = "index"`
    （`useI1Detail.ts#L623 removeRow(rowIndex)` / `useI3Detail.ts#L580 removeRow(rowIndex)`）
  - 🔴 本 lane 是唯一「下标族删行 + 位置化身份」双重叠 ⇒ 这条组合判据两个单独判据都抓不到

### 阶段 2：分类真源与模板缺陷

- [x] 10. CD-1 双定义比对 + 收敛（ID-P7 / ID-P8，🔴 本轮新发现）
  - 判据 SHALL **同时比对两处** impl 常量（`i1CategoryScope.ts#I1_DEFAULT_CATEGORIES` 与
    `useI1Adjudication.ts#I1_DEFAULT_CATEGORIES`）对 `底稿目录!A9:A19`，**有序等值**
  - 🔴 变异「只改 `i1CategoryScope.ts` 的第 8 条 `软件`」SHALL 打红（单边判据会静默通过 = 假绿）
  - 收敛：`useI1Adjudication.ts#L105` 改为 `I1_DEFAULT_CATEGORIES.map(c => c.label)` 派生，
    保留导出名与 `as const` 语义，兼容现有 **22 处**引用（个数现算）
  - 零回归跑 `i1CategoryScope.spec.ts` / `useI1Adjudication.spec.ts` / `iCycleDynamicRows.spec.ts` /
    `i1DisclosureAddCategory.spec.ts`（**复用已有，不重造**）
  - 收敛后判据 SHALL 加一条：断言第二份独立字面量已不存在
  - 登记 `i1ListedDisclosureModel.ts#L41` 的注释证明平台收敛过一次但漏了这个文件

- [x] 11. BP-7 三边校验 + 五项差异登记（ID-P5 / ID-P6）
  - 三边：①声明 `附注披露信息（国有企业）!A9:A19` ②openpyxl 真读 **11 格** ③impl
    `i1SoeDisclosureModel.ts#L29-42` **12 条**；🔴 **有序等值**比对，**禁集合比对**
  - 五项差异逐条命中（条数 12↔11 · `软件` 位次 1↔8 · `房屋使用权`↔`住房使用权` ·
    `特许权`/`采矿权`↔`特许经营权`/`矿产权` · 多出 `探矿权`）；「五项」与列举数相等
  - 断言第二真源 `note_template_soe.json` 里 `采矿权`/`探矿权`/`房屋使用权` 命中 **0**
  - 🔴 反向自检：把 declaration 的 `expected_source_labels` 改一字，判据 SHALL 点名那一条
  - 契约 `soe_classification.status = defect_registered_not_fixed` + `fix_blocked_by=business_confirmation`
  - 断言稳定 key 用 `i1CategoryColumnKey`（`i1CategoryScope.ts#L34-36` 生成 `${slot.key}_${slot.seq}`）
    符合 H7 SK-1；反向断言全 I 的 `key: X.label` 与 `row[X.label]` 命中 **0**

- [x] 11a.* BP-7 的修法（依赖业务确认）
  - 源模板 11 类与 `note_template_soe.json` 谁权威 · `探矿权` 去留 · `软件` 位次
  - 🔴 这是会计披露口径问题不是代码问题，**不得擅自改分类名**

- [x] 12. 源模板内部真源断链 2 处登记不修
  - `附注披露信息（上市公司）!K10` 与 `明细表I1-2!A29` 都是字面 `数据资源`（不是 `=底稿目录!A18`）
  - 断言改 `底稿目录!A18` **不会传播**到这 2 处；🔴 不改模板字节、不开新覆盖层例外
  - 登记第 3 处 `明细表I2-2!A17` 同型但属 I2 ⇒ 归 lane 2（本 lane 不代它处置）

- [x] 13. ID-3 `明细表I3-2!AA23:AD23` 四格覆盖层（ID-P9 / ID-P10 / ID-P11）
  - ✅ **i3 契约已交付（2026-09-27）**：provider `phase5_i3_goodwill.py` + sheet spec `phase5_i3_02_detail.py`（🔴 **四级表头 header_rows=4 用到平台上界** / 11 公式列含 Q 镜像列 / footer R23 三形态混行 / B+C 两列数据区全空不进 field_specs / 排除 3 sheet 含全角连字符）+ 台账（已挪到并发会话新建的 `delivered_contracts_ledger.py`）。契约 23,611 B 双向锁通过 / masked_editable=0。🔴 **两处模板缺陷两种处置**：①AA23:AD23 四格 `overlay_fixed`（FC-5 第 5 例外，覆盖层公式已写入契约 `overlay_formulas`）②**本轮新发现 I14 缺公式** `registered_not_fixed`（I15..I18 逐行都有 =SUM(Dx:Ex)-Gx，唯数据区首行 None；前端 costEnding 本就重算落库 ⇒ 不影响回写正确性，但须登记防后来者误判「I 列公式逐行齐全」）
  - openpyxl 现算确认缺陷仍在：四格都是 `=SUM(<列>27:<列>30)` 形态；
    登记根因两条（R27-29 是编制说明文本行 · R30 超 `max_row`=29）
  - 覆盖层改为 `=SUM(<同列>14:<同列>22)`；🔴 `backend/wp_templates/` 字节不动
    （FC-5 的**第 5 个**例外，前四是 `F2-26!J9` / `F5-7!G31` / `G5-2` 45 格 / `G5-1!B35`）
  - 🔴 判据载荷 SHALL 是「**只有减值准备区（R14:R22 的 AA:AD）有数、其他区为 0**」；
    用「全区都有数」载荷 SHALL 打红（会假绿）、用「全区都是 0」SHALL 打红（恒真）
  - 断言修复前四格求值 == 0、修复后 == R14:R22 真实合计
  - 断言 R23 的**非 AA:AD 列**在覆盖层前后取值**不变**（不误伤）
  - 契约 `known_template_quirks[0].handling = "overlay_fixed"`
    （🔴 与 I6 的 `S19` 文本列求和标 `registered_not_fixed` 是两种处置，不得混写）

### 阶段 3：两份契约 + 载体门控 + 注册

- [ ]* 14. `i1.intangible_assets_detail.json`（ID-P12 / ID-P13 / ID-P16~P18）
  - 🔴 **回滚原因（2026-09-27 复盘）**：契约需与 provider + 台账同时交付
  - 字段见 design §两份契约；`provider_id = phase5_intangible_assets_detail`（`phase5_*` 范式）
  - 几何：四级表头 R8-11 · 数据区 R12-17 · footer R18 `pure_sum` · 有效列 **47**（`max_column` 56）·
    公式 179 · merged 72 · `uuid_column: 48`（🔴 不得放 57）
  - 🔴 `regions[1] = {rows:[19,30], kind:"derived", label_source:"底稿目录!A9:A19",
    editable_labels:false}`；判据 SHALL 断言回写时**跳过该区标签列**
    （否则用户改的标签会被下次 render 从 `底稿目录` 静默覆盖）
  - `classification.dual_definition: true` + 收敛目标（Task 10 的产物）
  - `source_ref` 只 `{workbook_sha256, sheet_name:"明细表I1-2"}`，🔴 **禁任何 wp_index 字段**
  - `derived_total_keys` **现算**（当前 8），🔴 禁写死；`defined_name_baseline: 0`（不增长口径）
  - `oo_crash_neutralization_fn` **per-file** 挂（本册裸 IF 321，全 I 最高）；整册统一挂 SHALL 打红
  - `excluded_sheets: ["GT_Custom"]` + `sheet_name_traps` 四条

- [ ]* 15. `i3.goodwill_detail.json`（ID-P12 / ID-P14 / ID-P15 / ID-P21）
  - 🔴 **回滚原因（2026-09-27 复盘）**：契约需与 provider + 台账同时交付
  - `provider_id = phase5_goodwill_detail`
  - 几何：四级表头 R10-13 · 数据区 R14-22 · footer R23 · 有效列 **30**（`max_column` 也 30）·
    公式 133 · `uuid_column: 31`
  - 🔴 `footer_kinds: {23: "row_formula_applied"}`（IC-13 第四值）+ `footer_convention_split: true`；
    变异「照 I1 的 `pure_sum` 口径验 R23」SHALL 假红并被捕获
  - `positional_identity.sites` 列全 **7 处**（I3 侧）+ `persist_chain` + 两个 `persist_keys`
  - `positional_labels` 3 处登记不修（业务确认）
  - `known_template_quirks` 写 Task 13 的四格 `overlay_fixed`
  - 🔴 `excluded_sheets: ["GT_Custom", "参考－商誉减值测试示例", "市场平均收益率2017"]`，
    排除理由**逐条写明**（示例数据 / 固定年份基准 / 平台隐藏页）；
    变异「纳入 sheet 白名单」SHALL 打红；变异「用半角连字符 `参考-…` 匹配」SHALL 找不到而打红
  - `mounts: 4`（🔴 全 I 唯一 ≠2）· `derived_total_keys: []`（现算 0，IC-18 已裁非漏扫）·
    per-file 裸 IF 63 · `defined_name_baseline: 0`

- [x] 16. 载体 / 门控 / 跨引用实例化（ID-P15 / ID-P20 / ID-P22 / ID-P23 / ID-P24）
  - IC-2 二分表两行：I1/I3 都 `host_inline` + `write_client=http` +
    `host_inline_render_config_refetch`；反向断言两宿主 checklist GET == 0、
    `bridge`/`ocr`/`notice`/`localStorage` 命中均 0
  - 🔴 I3 的 `force_component_type` 判据覆盖**全部 4 个挂载点**；只验 1 个 SHALL 打红
  - TB 发布门：**复用** `composables/__tests__/iAdjudicationPublishGate.spec.ts`（已含
    `buildI1()#L81` / `buildI3()#L86`），只补「注册 adapter 后仍走同一显式门」断言
  - 断言只走 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb` + 二次确认；
    🔴 禁 `watch`/`onMounted`/debounce 内发布；**复用**平台既有 2 道 CI 守卫，不重造
  - `useAdjustmentCentralSync` 两处登记（`I1TabAdjustment.vue#L391` / `I3TabAdjustment.vue#L456`）
  - 🔴 跨 lane 闸：`useI1AdditionCheck.ts#L250-251` 读 `I2-2-rows`（`remark` 优先 / `conclusion` 兜底）
    ⇒ lane 2 改该键名或改其 payload mode SHALL 让本判据打红
  - 断言 `expenseWpI1AmortPull.ts` / `i1AmortAllocCounterpartPull.ts` 读 `I6-2-detail-rows`，
    canary 注册后仍取到同一载荷；🔴 断言 **H1 pilot golden digest 不变**
  - 登记 wp_index 两套编号 4 例（`I1-3`/`I1-4`/`I1-5`/`I3-3`）；契约 schema 校验卡死 wp_index 字段

- [ ]* 17. 注册 + 零回归重算（ID-P25，IC-1）
  - 🔴 **回滚原因（2026-09-27 复盘）**：注册需 provider 就绪（禁手改 manifest，IC-1）
  - 只走 `register_from_manifest()`，🔴 **禁手改 manifest 文件**；注册后 `capability` 才变 `bidirectional`
  - 重跑 Task 2 基线：契约目录 +2、注册集 +`{i1, i3}`；🔴 全部**现算**比对，禁写死
  - 复跑 149 KB 守卫 `test_task51_i_cycle_migration.py` 零回归

### 阶段 4：roundtrip + 交接

- [x] 18.* roundtrip 合成载荷实证（ID-P26，依赖 BP-4 真 OO 9.4 场景集）
  - 🔴 前置事实：真库 `I1-2-rows` 与 `I3-2-rows` **都没有行** ⇒ 本 lane **无 canary 资格**，
    复用地基 spec 的 I6 canary 范式；证据 SHALL 标 `synthetic_payload_no_live_db_baseline`
  - 合成载荷三条件齐备：①只有减值准备区有数（喂 Task 13）②披露区 ≥5 行且 rowId 互不相同
    （喂 Task 9）③混入 ≥1 条 `cgu-3` 旧 id 行（喂 Task 7）
  - 四条冻结：冻 `useAdjustmentCentralSync`（两处）· 排除 `derived_total_keys`（I1 8 / I3 0）·
    不改 `I1-2-rows`/`I3-2-rows`/`I2-2-rows` 键名 · 完成后回归 H1 golden digest 不变
  - 🔴 `evidence.sync_test_run_id` 须来自真 OO 栈，**不得** mock 充数

- [x] 19.* 人工审核契约与 approved bundle（依赖 BP-2 / BP-3）
  - 产出 `review.entry_id` 为 `xlsx/gt-i1-…` 与 `xlsx/gt-i3-…` 的 per-entry contract
  - 🔴 判据是「逐文件读 `review.entry_id`」**不是数契约个数**

- [x] 20. 交接与复盘核验（不改代码，只核）
  - IC 引用闭合性：本 spec 的 `IC-\d+` 引用集合 ⊆ 地基 spec 的 `### IC-\d+` 定义集合，无悬空
  - 🔴 断言本 spec **无一条复述** IC 正文（只写编号 + 一句话用途）
  - entry 归属：本 lane 恰为 {`xlsx/gt-i1-intangible-assets`, `xlsx/gt-i3-goodwill`}，
    与地基 spec Task 25 的归属表一致；entry 一律写全名（禁 `I1` 简写作归属键）
  - 「N 处」类表述与列举项数**逐条相等**（8 sites / 五项差异 / 20 处族 C / 4 例编号 / 3 张排除 sheet）
  - 计数类要么现算要么标明「现算值 + 禁写死阈值」；全文无 U+FFFD
  - 逐条确认**未交付项**的归属与理由：BP-7 修法（业务确认）· 位置化标签 3 处（业务确认）·
    真源断链 2 处（登记不修）· roundtrip（BP-4）· 人工审核（BP-2/3）

## 阻塞项对齐

| BP / 事项 | 归属 | 本 spec 交付 |
|---|---|---|
| BP-1 ~ BP-4 | 平台级（全循环共有） | 只标 `[ ]*`，不承诺 |
| **BP-6** | **本 lane**（entry 全集恰为 {I1, I3}） | Task 3~9（8 sites 分治 + grandfather + 组合判据） |
| **BP-7** 判据 | 本 lane | Task 11（三边 + 五项差异） |
| **BP-7** 修法 | `[ ]*` 业务确认 | Task 11a |
| **IC-14 / ID-3** | 本 lane | Task 13（覆盖层，FC-5 第 5 例外） |
| CD-1 双定义（🔴 新） | 本 lane | Task 10（双边比对 + 收敛） |
| 位置化标签 3 处 | `[ ]*` 业务确认 | Task 5 附带登记 |
| 源模板真源断链 2 处 | 登记不修 | Task 12 |
| `I2-2-rows` 冻结 | 跨 lane 闸 | Task 16（lane 2 改名即打红） |
| BP-5 / BP-8② / IC-16 | **lane 2** | 不在本 lane |
| BP-9 / BP-10 / BP-8① | 地基 spec | 不在本 lane |
