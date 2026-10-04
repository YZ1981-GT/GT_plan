# Requirements Document

## Introduction

本 spec 把 **F2 存货**的四个 Excel 独立 entry 从 legacy 假双向接成真双向，每个 entry 只覆盖它自己的
template_ref 那一册。它是 umbrella Task 48 的下游 lane spec，F 循环共同裁决 **FC-1~FC-13** 见
`f1-sync-coverage-and-first-canary/design.md` §F 循环共同裁决（本 spec 引用、不复述）。

🔴 **Property 编号 spec-scoped**：本 spec `Property N` 读作 **`F2-P{N}`**。

🔴 **一份 spec 分四条 lane，不拆四份**：main / special / valuation 三个 entry 共用幻影码 `F2I`，matcher 域冲突
（RG-3）只需裁决一次（裁决 F2-H1）；拆成四份会把同一裁决重复四遍且互相依赖。

### 四个 entry 实测（manifest + slice，2026-09-26）

| entry_id | 宿主 | `wp_code_patterns` | template_ref（唯一受管册） | mount |
|---|---|---|---|---|
| `xlsx/gt-f2-inventory-main` | `GtF2InventoryMain.vue` | `F2I` | `F/F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx`（20 sheets） | 2 |
| `xlsx/gt-f2-stocktake-bundle` | `GtF2StocktakeBundle.vue` | `F2S` | `F/F2-21至F2-26 存货及跌价准备 - 盘点类（Leap应对措施- 存货监盘）.xlsx`（9） | 1 |
| `xlsx/gt-f2-inventory-valuation` | `GtF2InventoryValuation.vue` | `F2I` | `F/F2-47至F2-49 存货及跌价准备 -跌价准备测试（Leap应对措施-会计估计）.xlsx`（6） | 2 |
| `xlsx/gt-f2-inventory-special` | `GtF2InventorySpecial.vue` | `F2I` | `F/F2-55至F2-58 合同履约成本.xlsx`（7） | 2 |

四者在 **manifest** 均 `capability=single_onlyoffice` / `legacy_fake_bidirectional` / `adapter_id=None` /
`html_store=unresolved`，profile `xlsx.editable.shared.single.room_service_wired.v1`；
`working_paper_sync_entry_state` F 循环 0 行。
🔴 **manifest 的 `capability` / `html_store` 不是逐 entry 裁决值**（slice BP-6）：它们来自
`workpaper_sync_entry_overlay.json` 的 `defaults_by_component.GtOnlyOfficeSheet` **组件级默认值**
（全 186 条里 180 条同值），slice 重裁结论是 `capability=null` / `html_counterpart_verdict=exists`，
且 slice 守卫**断言两者必须不一致且该不一致已登记**。⇒ 本 spec 引用 manifest 值时 SHALL 标明其为 overlay 默认值，
不得当作裁决真源（详见 F1 design FC-12）。

**模板字节锚（slice `authoritative_templates.files[].sha256` 按值实测，契约 `TEMPLATE_SHA256` 逐字用它）**：

| entry_id | sha256 | 字节 |
|---|---|---|
| `xlsx/gt-f2-inventory-main` | `9e57efd242b47171423e61f63a35be6ae5b46889baa14c246595ea95591fd0d8` | 180,630 |
| `xlsx/gt-f2-stocktake-bundle` | `bdfdcf8a804aab1c11db1cc2cd2deaac4f5bbf94c6a60e43a04108f178079bc7` | 81,418 |
| `xlsx/gt-f2-inventory-valuation` | `bab0abc099cfed3efdde3095bed510b3bbe7422ce32431054811034f6e6d5cd5` | 443,368 |
| `xlsx/gt-f2-inventory-special` | `b9ea248198217827a7b3d142dccca9ab5769c17867d1454ffd9105eaa9cb6c21` | 100,429 |

**逐 entry 阻塞（slice `capability_target_blocked_by`，按值实测）**：

| entry | blocked_by | F2 独有项 |
|---|---|---|
| main | `BP-1..4 + BP-5 + BP-7` | BP-5 整册码回落 · BP-7 行身份退化 |
| stocktake | `BP-1..4 + BP-5 + BP-9` | BP-5 · BP-9 Word writer lane 理由写错 |
| valuation | `BP-1..4 + BP-5` | BP-5 |
| special | `BP-1..4 + BP-5` | BP-5 |

🔴 **BP-5 是四条 lane 的共同前置**，`must_fix_before` 原文「把任一 F2 entry 标 bidirectional **或注册 adapter** 之前」
（比 BP-1~4 的门更早，卡 adapter 注册）。其现状是 **`PARTIALLY_FIXED_WHOLE_CODE_FALLBACK_NOW_RESOLVES_CORRECTLY`**：
commit `82f58ea44` 在 `wp_template_finder.py` 引入 `_PRIMARY_TEMPLATE_TIERS=('审定','常规程序')` + `_pick_by_tier`，
把「审定」抬成严格高于「常规程序」的独立层 ⇒ `find_template_file('F2')` 现返回审定明细表类册（与 main 的 template_ref 一致），
不再返回 14,532 B 的 `F2-16 会计政策` 册。但 slice 的 `still_not_fixed` 明写**结构性缺口仍在**：
整册码回落路径本身还在、F2 约 60 个 sheet 仍无 sheet→模板映射 ⇒ 用户处在 F2-21/F2-38/F2-47 而 sheet 名提不出子码时，
OO 侧打开的仍不是本表（「错得没那么远」而已）。`latent_regression_shape` 另明写复发条件：
**新行为依赖「第一层『审定』在 F2 候选集里恰好只命中 1 条」**，再入库第二本含「审定」的册即复发（守卫
`test_bp5_whole_code_fallback_is_fixed_and_unambiguous` 已把「第一层命中数 == 1」写成断言）。
⇒ 需求 1 给出本 spec 的 BP-5 边界（见 1.8）。

🔴 **BP-8（`F2存货.xlsx` 不可达合册）**的 `must_fix_before` 是「为 F2 任一 entry 发布 authority model /
template definition digest 之前」—— 与本 spec 的契约发布环直接相撞：该 560,160 B / 74 sheet 合册在磁盘上但
**不在 `_index.json`**，⇒「权威模板是哪一份」在 F 目录内有歧义。需求 1.8 一并处置。

**真码与 store 落点（真库只读实测）**：唯一有 F2 载荷的项目 `0ec33ac9` 中，**35 个 `F2-*` 键全部落在
wp_code=`F2` 的同一个 wp**（`2cc1a1ed…`，`file_path` 为空）——覆盖 F2-3/7（main）、F2-21~26（stocktake）、
F2-47~49（valuation）、F2-56（special）以及 6 本「范围外」册的键（F2-29/33/34/35/38~44/64/70）。另项目
`2aa00f57` 在子码 wp（F2-22/F2-23/F2-29）上各有 1 键 ⇒ **store 落点不唯一**，provisioner 定位须由 Task 1 裁决。

**模板册 vs 路由（`backend/app/data/wp_code_overrides.json` L472-L538）**：宿主按 componentType 渲染的 sheet
**多于**其 entry 的 template_ref：`f2-inventory-main` 还渲染 F2-16/18/19/20/29~32；`f2-inventory-valuation-impairment`
渲染 F2-33~35/38~44/47~49/52；`f2-inventory-special` 渲染 F2-55~58 与 F2-61~72 ⇒ 这些册的 sheet 属 FC-3「需新宿主」。

### 四册逐 sheet 几何（openpyxl 直读）

**main 册（20 sheets）**

| sheet | 尺寸 | 公式 | 数据 / footer（实测） | 前端组件 / store 键 | 本 spec |
|---|---|---|---|---|---|
| 修订说明 | hidden 106r×E | 0 | — | — | 不接 |
| 底稿目录 / 存货实质性程序表F2A | 25r×G / 53r×N | 0 / 7 | — | `F2TabProcedure` | 不接 |
| **存货审定表F2-1** | 148r×K | **487** | 13 类别块，大部分派生自 F2-2（引用 F2-2 **167** 次） | `useF2Adjudication`：per-cell `F2-1-${block}-${rowKey}-${field}` + `F2-adjudication-data` + `F2-1-tb-total` | ✅ 最后接 |
| 附注披露信息（上市公司）/（国企） | 88r×N / 43r×H | 269 / 177 | — | 披露 | 不接 |
| **明细汇总表F2-2** | 76r×Q | 366 | 三区 footer R31/R49/R67；引用 F2-3~F2-13 共 94 次 | `useF2DetailSummary`：`F2-2-summary` + 模板化 `F2-2-…` | 🔍 核（派生汇总） |
| **一、原材料明细表F2-3** | 31r×U | 120 | 两级表头 R6/R7；数据 **R9-24**；footer **R25（标记在 B 列）**；R26 跌价 / R27 净额 | `F2DetailSheet` + `useF2DetailSheet`：`${sheetCode}-rows`（**模板化**，`dataKey` L109） | ✅ |
| 二、材料采购、在途物资明细表F2-4 | 30r×W | 138 | R9-24 / R25 | 同上（`noteProfile:'inTransit'`） | ✅ |
| 三、周转材料…明细表F2-5 | 35r×U | 120 | **分组**：小计 R12/R16/R26，合计 R27 | `F2DetailSheetTurnover` + `useF2DetailTurnover` | ✅（分组形态，后置） |
| **四、自制半成品明细表F2-6** | 30r×U | 120 | R9-24 / **R25（A 列）** | `useF2DetailSheet` | ✅ **canary** |
| 五、委托加工物资明细表F2-7 | 287r×O | 31 | R8-16 / R17 | `F2DetailSheetOutsourced` + `useF2DetailOutsourced` | ✅ |
| 六、库存商品明细表F2-8 | 36r×X | 122 | R9-24 / R25 | `useF2DetailSheet`（+V/W/X 在手订单列） | ✅ |
| 七、发出商品F2-9 | 36r×W | 140 | R9-24 / R25 | `useF2DetailSheet`（`noteProfile:'dispatched'`） | ✅ |
| 八、开发产品F2-10 | 95r×AI | 425 | 三块，footer R19 | `useF2DevProductSheet`：`F2-10-rows` | ✅（后置） |
| 九、开发成本F2-11 | 52r×X | 303 | 两块，R19/R33 | `useF2DevCostSheet`：`F2-11-rows` | ✅（后置） |
| 十、合同履约成本F2-12 | 25r×P | 30 | R8-19 / R20 | `useF2ContractPerfSheet`：`F2-12-rows` | ✅ |
| 十一、消耗性生物资产F2-13 | 79r×V | 299 | 三块，R25 | `useF2BioAssetSheet`：`F2-13-rows` | ✅（后置） |
| 调整分录汇总F2-14 | 23r×J | 7 | — | `F2TabAdjustment`：`F2-14-rows`（hub，`useAdjustmentCentralSync`） | 🔍 FC-6 |
| GT_Custom | hidden | 0 | — | — | 不接 |

**stocktake 册（9 sheets）**

| sheet | 尺寸 | 公式 | 数据 / footer（实测） | 前端 store 键（按值） | 本 spec |
|---|---|---|---|---|---|
| 底稿目录 / GT_Custom / 存货监盘程序表F2-21A | — | 0/0/7 | — | `F2-21A-procedure` | 不接 |
| 盘点计划问卷F2-21 | 60r×K | 7 | 问卷 | `F2-21-rows` / `F2-21-fields` / `F2-21-note`（`useF2StocktakeQuestionnaire`） | 🔍 形态核 |
| 监盘计划F2-22 / 监盘小结F2-23 | 6r×B / 3r×K | 0 | **近空壳 sheet**（正文在 docx） | `F2-22-fields` / `F2-23-fields` | 不接（docx lane 归 umbrella Tasks 60/61，slice 已登记） |
| 存货账面余额与仓储台账核对记录F2-24 | 29r×I | 7 | 🔴 **无表格区**：R5/R14 两段标题 + 提示文字，R8-12 / R17-24 空白，R25 审计说明 | `F2-24-rows` + `F2-24-count-rows` 两区（`F2TabStocktakeReconcile`） | ❌ 模板无承载列 ⇒ HTML-only |
| **抽盘结果汇总表F2-25** | 57r×P | 75 | 区（一）账→实：两级表头 R14/R15，数据 **R16-26**，footer **R27**；区（二）实→账：R29/R30，**R31-41**，**R42** | 区一 `F2-25-rows` / 区二 `F2-25-floor-rows`（`F2TabStocktakeSampleResult.vue:614/622`） | ✅ 双区 |
| **盘点倒轧表F2-26** | 30r×O | 49 | 区（一）日后：表头 R7，数据 **R8-14**（**无 footer**）；区（二）日前：表头 R16，数据 **R17-23**（无 footer）；R24 审计说明 | 区一 **`F2-26-after-rows`** / 区二 **`F2-26-rows`**（`F2TabStocktakeRollforward.vue:361/370`，按值确认：旧键 `F2-26-rows` 是**日前**区） | ✅ 双区（无 footer，需求 3.4） |

**valuation 册（6 sheets）**

| sheet | 尺寸 | 公式 | 数据 / footer | store 键 / 载荷形态（真库） | 本 spec |
|---|---|---|---|---|---|
| 底稿目录 / GT_Custom | — | 0 | — | — | 不接 |
| **跌价准备测试表F2-47** | 56r×AB | 107 | 两级表头 R18/R19；数据 **R20-29**；footer **R30** | `F2-47-rows` = **dict** `{auditProcedure, products[], sampling}`；`products[].id` 形如 `f2imp-…` | ✅ dict 子数组 |
| **长库龄 呆滞 超过保质期存货明细表F2-48** | 22r×N | 23 | 两级表头 R5/R6；数据 **R7-16**；footer **R17** | `F2-48-rows` = dict `{products[]}` | ✅ dict 子数组 |
| **跌价转回F2-49** | 36r×X | 36 | 两级表头 R5/R6；数据 **R7-15**；footer **R16** | `F2-49-rows` = dict `{products[]}`；`id` 形如 `f2rev-…` | ✅ dict 子数组 |
| 同行业存货跌价计提情况G2-9-3-删除 | **hidden** | 72 | 残留 | — | 不接 |

**special 册（7 sheets）**

| sheet | 尺寸 | 公式 | 数据 / footer | store 键 / 载荷 | 本 spec |
|---|---|---|---|---|---|
| 底稿目录 / 合同履约成本实质性程序表F2-55A | — | 0 / 7 | — | — | 不接 |
| **合同履约成本构成明细表F2-55** | 40r×AK | 292 | 两级表头 R5/R6；数据 **R7-24**；footer **R25**（SUM 起于 R6，需 Task 核） | `F2-55-rows` = dict `{products[]}` | ✅ |
| **合同履约成本检查表F2-56** | 37r×W | 13 | 两级表头 R15/R16；数据 **R17-31**；footer **R32** | `F2-56-rows` = dict `{samples[], sampling, statNote}` + `F2-56-params` / `-stat` | ✅ |
| **合同履约成本减值准备测算表F2-57** | 27r×N | 76 | 表头 R5；数据 **R6-17**；footer **R18** | `F2-57-rows` = dict `{products[]}` | ✅ |
| **亏损合同预计损失测算表F2-58** | 25r×O | 70 | 表头 R5 + 公式说明行 R6；数据 **R7-20**；footer **R21** | `F2-58-rows` = dict `{products[]}` | ✅ |
| 合同履约成本测试（示例） | visible 44r×AX | 24 | 示例 | — | 不接（示例 sheet） |

🔴 **special 宿主有 IPO 门控**（`GtF2InventorySpecial.vue:15` `isIpoSheet && !formData.isIpoProject`），但 IPO sheet
（F2-61~72）在另一册、不属本 entry；F2-55~58 不受 IPO 门控影响，Task 2 须按值复核。

### 🔴 红基线（实测，非本 spec 引入）

**B1 · BP-7 真实发生（真库证据）**：`useF2DetailSheet.loadRows`（L224-L234）无载荷时 `emptyRow('1', …)`、有载荷时
`String(r.id || i + 1)` ⇒ 行身份退化为**数组下标**。真库 `F2-3-rows[0].id = "1"`（按值查询）——不是理论风险。
同型下标回退另有 6 处（slice BP-7 登记）：`useF2DetailOutsourced:176` / `useF2DetailTurnover:263` /
`useF2BioAssetSheet:219` / `useF2ContractPerfSheet:155` / `useF2DevCostSheet:165` / `useF2DevProductSheet:211`；
`useF2ContractCostCheck.fillFromSampling:252` 以 `` `${Date.now()}-${i}` `` 造 id（时间戳+下标，非稳定身份）。
⇒ main 册任何明细表受管前 SHALL 先修 BP-7（插删行后下标身份会把 OO 回写合并到错行）。

**B2 · 模板公式缺陷（权威模板本身）**：`盘点倒轧表F2-26!J9 = J2+H9-I9`（同列其余 13 行均为 `G{r}+H{r}-I{r}`；
J2 落在标题合并区 `A2:O2` 内、值为空 ⇒ **第 9 行「资产负债表日实存数量」丢失监盘日实存数 G9**）。前端
`F2TabStocktakeRollforward.vue:380-382` 按正确口径计算 ⇒ 受管后 OO 与 HTML 在该行必然分歧。触类旁通全 F 目录
（`_probe_f_rowpattern.py`）：同型离群另有 `F2-64!C101:C104`（IPO 册，范围外，需人工判是否有意）、
`F2-13!A55=A25`（标签引用，非金额）。模板运行时只读、sha 冻结 ⇒ 修法走**模板覆盖层**（spec
`excel-template-override-layer-and-onlyoffice-template-editor`），本 spec 只登记 + 判据，不改模板字节。

**B3 · 公式管理预设缺陷**（`test_f_prefill_extension.py` 2 红 + `test_f2_formula_presets.py` 相关）：

| 块 | 缺陷（按值实测） |
|---|---|
| `[17]` | sheet 名 `审定表F2-1`，模板真名 **`存货审定表F2-1`** ⇒ `wp_template_init_service` 回退到「含『审定表』的 sheet」；块内 `PREV('F2','审定表F2-1',…)` 引用不存在的 sheet |
| `[118]` | `明细汇总表F2-2` 块 22 条 `WP()` 取数，违反 ADR-F2「F2-2 只用 TB/AUX/LEDGER」（`test_f22_master_sheet_uses_aux_or_tb` 红） |
| `[132]` | sheet 名被提交 `873ee7dce`（2026-08-16「清除 26 处虚构 AUX 维度值」）**批量替换误伤**：`长库龄 呆滞 超过保质期存货明细表F2-48` → `XX分类3 XX分类4 超过保质期存货明细表F2-48`（sheet 名里的「长库龄/呆滞」被当成虚构维度值替换）⇒ `test_all_target_sheets_present` 红 |

`fix_f2_prefill_presets.py --check` 与 `fix_f_cycle_prefill_presets.py --check` 实测均 **exit 0**，与红测试口径矛盾（同 F1 B2）。

**B4 · 双 store 落点**：F2 载荷主要落在父码 wp `F2`，但项目 `2aa00f57` 的 `F2-22-fields` / `F2-23-fields` /
`F2-29-rows` 落在子码 wp ⇒ provisioner「一 entry 一 wp」假设不成立，须裁决（需求 1.4）。

**B5 · 死代码**：`useF2ValuationDateSheet.ts` / `useF2ValuationTestSheet.ts` 零消费方（F2 调研已登记）；
`GtF2InventoryValuation` 只载入编号 ≥33 的键 ⇒ F2-35 读 `F2-7-rows` 恒为 null（范围外册，登记移交）。

## Glossary

沿用 F1 spec Glossary；新增：

| 术语 | 含义 |
|------|------|
| lane | 本 spec 内一个 entry 的接入链（main / stocktake / valuation / special），各自 provider + 契约 + adapter |
| 幻影码共用 | 三个 entry 的 manifest `wp_code_patterns` 同为 `F2I` ⇒ `EntryMatcher.overlaps()` 必判重叠（RG-3） |
| dict 子数组行源 | store 是 `{products:[…], …}` 对象，受管行取自其中一个数组（D1-7 `D1-memo-rows.bankRows` 先例） |
| 模板覆盖层 | 不改 `backend/wp_templates/` 字节、以覆盖层修正权威模板缺陷的机制（既有 spec） |

## Requirements

### Requirement 1: Wave 0 裁决 matcher 域与 store 落点（四 lane 共用前置）

**User Story:** 作为维护者，我不希望三个 F2 adapter 因共用幻影码 `F2I` 在注册时互相冲突，或把数据写到错的 wp。

#### Acceptance Criteria

1. WHEN 三个 entry（main / valuation / special）的 `wp_code_patterns` 同为 `F2I` THEN 以 `EntryMatcher(wp_codes={"F2I"})`
   注册第二个 adapter SHALL 被 RG-3 `MatcherOverlapError` 拒绝 —— 本 spec SHALL 先有一条**真跑** `registry.register()`
   的红判据证明该冲突（G7 三 entry 同型先例：`workpaper_sync_entry_wp_code_adjudication.json` 的 G7 条目
   `matcher_domain_conflict.error = "RG-3 MatcherOverlapError"`）。
2. WHEN 裁决 matcher 域 THEN SHALL 采用设计裁决 F2-H1（`sheet_keys` 限定互斥域），并证明：①三个 matcher 的
   `sheet_keys` 两两不相交 ⇒ `overlaps()` 返回空；②运行时解析走 `resolve_for_entry(entry_id)`
   （`wp_sync_router.py:806` / `startup_prewarm.py:164` 均经 `assert_bidirectional_ready(entry_id)`，按值实测），
   不依赖 `resolve(wp_code, sheet_key)` 的 wp_code 路由。
3. WHEN stocktake（`F2S`）THEN 它 SHALL 独占幻影码、不参与上述冲突，但仍须登记 `matcher_domain_conflict=null` 证据。
4. WHEN 裁决 provisioner 定位宿主 THEN SHALL 以真库实测为据（红基线 B4）：默认父码 `F2`（35 键落点），并对子码 wp
   上的孤立载荷（`2aa00f57` 项目 F2-22/F2-23/F2-29）给出迁移或忽略的书面裁决；wp_code 裁决文件 SHALL 新增四条 F2 条目。
5. WHEN 任一 lane 的 `assert_entry_selectable` THEN SHALL 照 FC-2：默认严格、真 manifest 真调、幻影码为 matcher 域。
6. 🔴 WHEN 任一 lane 注册 adapter THEN SHALL 先处置 **BP-5**（四 lane 共同前置，`must_fix_before` 含「或注册 adapter 之前」）。
   本 spec 的边界：①**不**修「F2 约 60 个 sheet 无 sheet→模板映射」这个跨循环结构性缺口（BP-5 `why_not_fixed_here`
   明写与 D slice BP-5 / E slice G1 同型、三处应并为一个 spec，本 spec 不顺手改跨循环解析器）；
   ②但 SHALL 加一条守卫判据锁住**已修的那一半不复发**：`find_template_file('F2')` 返回值 ==
   `F2-1至F2-14 …审定明细表类…`，且第一层 `_PRIMARY_TEMPLATE_TIERS` 的「审定」在 F2 候选集命中数 **== 1**
   （BP-5 `latent_regression_shape` 指定的复发条件；与既有 `test_bp5_whole_code_fallback_is_fixed_and_unambiguous` 同判据，
   不重复造）；③SHALL 证明四条 lane 的受管路径**不经过整册码回落**（provider 走 `resolve_for_entry(entry_id)`，
   不走 `find_template_file(wp_code)`），使 BP-5 的残留缺口不落在受管路径上 —— 这是本 spec 能在 BP-5 未彻底修完时
   仍注册 adapter 的唯一依据，SHALL 有判据而非口头声明。
7. 🔴 WHEN 发布任一 lane 的 authority model / template definition digest THEN SHALL 先处置 **BP-8**：
   `F2存货.xlsx`（560,160 B / 74 sheet，10 本拆分册的并集）在磁盘但不在 `_index.json` ⇒ 判据 SHALL 证明
   ①四条 lane 的 `TEMPLATE_SHA256` 逐字取 slice `authoritative_templates` 的四个值（见上表），
   ②`F2存货.xlsx` 的 sha256（`afc762843ffee1c3…`）不出现在任何 F2 契约里，
   ③该合册运行时不可达的结论现算（`_index.json` 的 `files[].relative_path` 不含它）而非沿用 slice 快照。
8. WHEN 引用 manifest 的 `capability` / `html_store` THEN SHALL 标明其为 overlay 组件级默认值（BP-6），
   判据 SHALL 断言「manifest 值与 slice 重裁值不一致」这一事实本身成立 —— 不得为「对齐」而改 overlay 或 manifest
   （两者皆 source-backed 生成物，手改等于伪造；slice 守卫亦断言该不一致已登记）。

### Requirement 2: main lane —— 明细表族（canary F2-6，先修 BP-7）

**User Story:** 作为审计助理，我希望原材料/半成品/库存商品等明细表在 OO 里增删行也能正确写回对应行。

#### Acceptance Criteria

1. WHEN 选 main lane canary THEN 它 SHALL 是 **`四、自制半成品明细表F2-6`**（30r×U / 120 公式 / 数据 R9-24 /
   footer R25 标记在 **A 列**）—— 与 F2-3/4/8/9 共享 `useF2DetailSheet`（config 驱动），但 F2-3 的 footer 标记在
   **B 列**（R25 `B=合计`）而框架层 `footer_anchor.search_column` 固定为 `"A"`（`phase5_row_table_sheet.py:303`
   按值读），F2-6 无此差异 ⇒ 失败面最小。
2. 🔴 WHEN main lane 任一明细表受管 THEN 红基线 B1 的 BP-7 SHALL 已修：`useF2DetailSheet.loadRows` 载入缺 id 的行时
   SHALL 铸稳定 id 并**立即回写**，不得 `String(r.id || i + 1)`；同型 6 处一并修（触类旁通铁律）；真库
   `F2-3-rows[0].id="1"` 的旧行 SHALL 有迁移判据（迁移后 id 不再是纯数字下标）。
3. WHEN 声明 F2-3/F2-4/F2-6/F2-8/F2-9 THEN SHALL 一个声明文件、五个 spec，只差 `sheetCode` / 列集 / footer 标记列
   （E1-7/8/9 同范式，不复制五份）；`store_item_id` = `f"{sheetCode}-rows"`（按值实测模板化 `dataKey`）。
4. WHEN F2-3 的 footer 标记在 B 列 THEN SHALL 二选一：框架层 `footer_anchor` 增加声明位 `footer_marker_column`
   （默认 `"A"`、零回归）或 F2-3 暂不受管并登记 —— 由 Task 裁决，不得静默按 A 列查找导致定位失败。
5. WHEN 明细表派生列 THEN `formula_columns` SHALL 取模板实测（F/I/L/O 单价 `IF(qty=0,0,amt/qty)`、N/P 期末
   `E+H-K` / `G+J-M`）；前端 `enrichRow`（L187-L214）的 `calcUnitPrice` / `calcEndBalance` / `calcEndAmount` SHALL 与之
   逐列核等价（FC-5），不等价者先修前端。
6. WHEN 账龄 Q-T（4 段）THEN 同 F1 需求 3.3：仅 THREE_YEAR 启用受管；`aging` 为 nested 对象
   （`remapAgingData`），另有 legacy 平铺 `agingLt1/aging1to2/aging2to3/agingGt3`（`LEGACY_AGING` L101）⇒ 契约 SHALL
   只映射 nested，平铺键 SHALL 不进 field_specs（兼容读字段）。
7. WHEN footer 之下 R26「减：存货跌价准备」/ R27「净额」/ R28 校验 THEN SHALL 不受管（HTML-only / 纯公式）。

### Requirement 3: stocktake lane —— F2-25 / F2-26 双区

1. WHEN 声明 F2-25 THEN SHALL 两个 spec：区一 `F2-25-rows`（R16-26 / footer R27）、区二 `F2-25-floor-rows`
   （R31-41 / footer R42），走兄弟 Table ref 位移；两区列集相同（模板 R14/R29 表头逐格一致，Task 2 复核）。
2. WHEN 声明 F2-26 THEN SHALL 两个 spec：区一（日后倒推）**`F2-26-after-rows`**（R8-14）、区二（日前顺推）
   **`F2-26-rows`**（R17-23）—— 🔴 键与区的对应按值确认（`F2TabStocktakeRollforward.vue:361/370` 注释「日前顺推（与旧版
   F2-26-rows 公式一致）」），按键名直觉会把 `F2-26-rows` 错配到区一。
3. 🔴 WHEN F2-26 区一第 9 行 THEN 模板 `J9=J2+H9-I9` 缺陷（红基线 B2）SHALL 在受管前经模板覆盖层修为 `G9+H9-I9`，
   或该区不受管；判据 SHALL 证明 OO 与 HTML 对第 9 行的「资产负债表日实存数量」相等。
4. WHEN F2-26 两区**无合计行** THEN footer SHALL 照 E1-10 / D3-4 先例指向其后第一个非数据锚行（区一 R15
   「（二）资产负债表日前盘点倒轧表」、区二 R24「审计说明：」），`footer_carries_total_formula=False`。
5. WHEN F2-24 THEN 模板两区**无表头、无承载列**（R5/R14 仅标题 + 提示）⇒ `F2-24-rows` / `F2-24-count-rows` SHALL 判
   HTML-only 并中文登记「模板无对应表格区，在线编辑不回写」；F2-21 问卷 SHALL 做形态核（候选 `static_region`）。
6. WHEN stocktake 宿主 THEN `GtF2StocktakeBundle.vue`（mount 1，`:sheet-name="props.sheetName || activeTab"`）接桥时 SHALL
   保持 docx 通道（F2-22/F2-23 `f2-st/plan-sync-*` 端点）不受影响（slice `partially_wired_word_lane`）。

### Requirement 4: valuation lane —— F2-47 / F2-48 / F2-49（dict 子数组）

1. WHEN 判定形态 THEN 三张的 store 均为 dict（真库实测：F2-47 `{auditProcedure, products[], sampling}`、F2-48/F2-49
   `{products[]}`）⇒ SHALL 走 `StoreKind.dict` + 子数组行源 `products`（D1-7 `D1-memo-rows.bankRows` 同范式），
   合并时 SHALL 保留 dict 其余键逐字不变。
2. WHEN 行身份 THEN SHALL 取 `products[].id`（真库形如 `f2imp-…` / `f2rev-…`，非下标）；载入路径 Task 2 按值复核无下标回退。
3. WHEN F2-47 THEN 表头 R18/R19 两级、数据 R20-29、footer R30；公式列 `G/Q/T/U/V/W/X/Z`（按值读 R20）。
   🔴 **FC-10 已实测命中**：N 列「销售费用率」、O 列「税率」在模板参与 `T=N20*Q20` / `U=O20*Q20` 直接相乘（期望小数），
   而前端 `sellingExpenseRate` / `taxRate` 存**百分数**（`useF2ImpairmentTestFormulas.ts:215/225` `unitPrice*qty*(rate/100)`）
   ⇒ 直接受管会让 OO 侧 T/U/V/W/X/Z 放大 100 倍。受管前 SHALL 按 FC-10 裁决（默认引擎 `percent_points` 换算）。
4. WHEN F2-48 THEN 数据 R7-16 / footer R17 / `H=F*G`；F2-49 数据 R7-15 / footer R16 / `T=O/F*N`、`X=U+V+W-T`。
5. WHEN 公式管理预设 THEN 块 `[132]` 的 sheet 名 SHALL 恢复为 `长库龄 呆滞 超过保质期存货明细表F2-48`，并给
   `fix_f2_prefill_presets.py --check` 补「sheet 名 ∈ 模板 tab」校验，防批量替换再次误伤（红基线 B3）。

### Requirement 5: special lane —— F2-55 / F2-56 / F2-57 / F2-58

1. WHEN 判定形态 THEN 四张的 store 均为 dict + 子数组（F2-55/57/58 `products[]`；F2-56 `samples[]` + `sampling` +
   `statNote`，另有 `F2-56-params` / `F2-56-stat` 独立键）。
2. WHEN F2-55 THEN 两级表头 R5/R6、数据 R7-24、footer R25；🔴 footer `SUM(D6:D24)` 起点是 R6（表头叶子行）而非 R7，
   SHALL 实测该 SUM 区间在插行后的位移行为（框架层扩张规则按「区间末行 = last_data_row」判定），并登记。
3. WHEN F2-56 THEN 数据 R17-31 / footer R32；`fillFromSampling`（L252）以 `` `${Date.now()}-${i}` `` 造 id，
   SHALL 改为稳定 UUID（同 B1 触类旁通）后再受管。
4. WHEN F2-57 / F2-58 THEN F2-57 数据 R6-17 / footer R18；F2-58 数据 R7-20 / footer R21（R6 为「①②③…」公式说明行，
   不受管）；`F2-58!C` 完工进度参与 `G=C*F`，前端 `completionRate` 注释「0~1」（`useF2LossContractFormulas.ts:18`）
   与模板小数口径**一致**（FC-10 不命中），但 `F2_58_TIPS` 提示「直接录入进度（0~100%）」⇒ Task 2 SHALL 核 UI 输入控件
   是否把 50 存成 0.5（若存成 50 则 FC-10 命中）。
5. WHEN 示例 sheet `合同履约成本测试（示例）` THEN SHALL 不接（FC-7 不接清单）。

### Requirement 6: F2-2 明细汇总 + F2-14 调整分录 + F2-1 审定表（main lane 后段）

1. WHEN 核 F2-2 THEN 它是对 F2-3~F2-13 的派生汇总（模板引用 94 次、366 公式），前端 `useF2DetailSummary`（rowKey 55 处）
   SHALL 做可行性核：默认 HTML-only（汇总格全是公式，editable 字段极少），核后再定。
2. WHEN 核 F2-14 THEN SHALL 照 FC-6 默认 `single_html`，只产裁决与证据。
3. WHEN 声明 F2-1 THEN SHALL `AdjudicationSheetSpec`，sections 取 13 类别块实测；F2-1 引 F2-2 167 次 ⇒ 依赖 F2-2 的裁决结果；
   🔴 公式管理块 `[17]` sheet 名 SHALL 改为 `存货审定表F2-1`，`PREV` 引用同步。
4. WHEN F2-1 受管 THEN FC-9 TB 红线：sync 路径 TB 写次数为 0，`F2TabAdjudication.vue:36` 的 `publishToTb`（多科目原子发布）
   仍是唯一回写入口。

### Requirement 7: 宿主接桥、公式管理与零回归（四 lane 共用）

1. WHEN 四个宿主接桥 THEN 各自 SHALL 引入 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`，保留 legacy
   `GtOnlyOfficeSheet` 给未接 sheet；受管 sheet 集合从各自 provider 派生；**不得**让 main 宿主因同时渲染 F2-16/F2-18~20/
   F2-29~32（他册）而把它们误判为受管（FC-3）。
2. WHEN 公式管理 THEN SHALL 消费 F-SHELL，不新建按钮 owner；红基线 B3 三块修复后
   `test_f_prefill_extension.py` / `test_f2_formula_presets.py` 相关用例转绿。
3. WHEN 新 provider 纳入 THEN 既有 contract golden digest **逐项不变**（🔴 **现算基线，不写死数字** —— 依 G 循环裁决 GC-10：契约目录已从 10 涨到 12（并发会话交付 d1/d3/d5/d6/d7/e1），写死数字的判据下次交付即 stale；判据形态应为「非本 spec 的 digest 逐项比对」，不断言集合大小）；四个 F2 provider 进 `PROVIDERS`；
   四条 wp_code 裁决、四条 overlay、`DELIVERED_PER_ENTRY_CONTRACTS` / `_ALLOWED_PROVIDER_MODULES` 同步。
4. WHEN 发布链第③环缺供给 THEN 如实 `upstream_gap`（BP-61-1），不伪造通过。

### 不在本 spec 范围

- 6 本他册（F2-16 / F2-18~20 / F2-29~35 / F2-38~44 / F2-52 / F2-61~72）与运行时不可达合册 `F2存货.xlsx`（slice BP-8）——需新宿主，
  建议另立 `f2-auxiliary-volumes-sync-hosts`。
- F2-22 / F2-23 docx 通道（umbrella Tasks 60/61）；F0 函证（Task 57）。
- 模板缺陷 `F2-64!C101:C104`（IPO 册）只登记。
