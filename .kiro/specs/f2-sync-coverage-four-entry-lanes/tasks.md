# Implementation Plan

## Overview

**spec**：`f2-sync-coverage-four-entry-lanes`　**创建**：2026-09-26　**状态**：0/27（Task 0~25 + 5b），Design-First 未实施
**上游**：umbrella Task 48 · F 循环共同裁决 FC-1~FC-13（`f1-sync-coverage-and-first-canary/design.md`）· D1-7 dict 子数组先例 ·
G7 RG-3 先例 · 模板覆盖层 spec
**结构**：Wave 0 共用前置 + 四条 lane（M main / S stocktake / V valuation / P special），lane 之间互不阻塞（Wave 0 之后可并行）

`[ ]*` = 依赖外部供给（BP-61-1 / OO 真栈 / 模板覆盖层），如实登记 `upstream_gap`。

## Tasks

### Wave 0：共用前置（四 lane 共同阻塞项）

- [ ] 0. 前置依赖核查（`git show HEAD:`）：框架层 `RowTableSheetSpec` / `AdjudicationSheetSpec` / `merge._protection`；
  D1-7 dict 门面可复用；模板覆盖层 spec 的交付状态（决定 F2-26 区一能否接）
  - _Requirements: 3.3, 7.3_

- [x] 1. slice 核对 + store 落点实测 + 四条 wp_code 裁决条目
  - 四个 entry 的 slice 事实与现 manifest 逐项比对；真库 F2 载荷落点清单落证据（父码 `F2` 35 键 + `2aa00f57` 子码 3 键）
  - `workpaper_sync_entry_wp_code_adjudication.json` 新增四条：`wp_codes=["F2"]`；main/valuation/special 三条的
    `matcher_domain_conflict` 如实写 RG-3 与 F2-H1 解法；重算 digest
  - _Requirements: 1.3, 1.4_

- [x] 2. 形态判定 + 几何逐格实测（四册全部受管候选）+ UUID 列逐格核空 + 下游消费方 grep
  - 重点：F2-3 footer 在 B 列；F2-5 分组 / F2-10/11/13 多块形态；F2-26 两区无合计；F2-55 footer SUM 起于 R6；
    F2-58 `completionRate` UI 输入单位；special 宿主 IPO 门控对 F2-55~58 的影响
  - 证据 `evidence/task2-four-volume-morphology.md`
  - _Requirements: 2.1, 2.4, 3.4, 5.2, 5.4_

- [x] 3. F2-P2 红判据：RG-3 冲突真跑（`sheet_keys` 空 ⇒ 必抛；互斥后三者可同时注册）
  - _Requirements: 1.1, 1.2_

- [x] 4. F2-P3 / F2-P4 / F2-P6 / F2-P9 / F2-P10 红判据（现状必红，记录红形态）
  - P3 键名（含 `F2-26-rows`↔`-after-rows` 对调变异）；P4 BP-7（真库 `id="1"` 复现）；P6 明细派生列等价；
    P9 FC-10（F2-47 N/O）；P10 prefill 三块
  - _Requirements: 2.2, 2.5, 3.2, 4.3, 4.5, 6.3_

- [x] 5. F2-P11 零回归基线（10 contract golden digest 现算记录）
  - _Requirements: 7.3_

- [x] 5b. 🔴 BP-5 / BP-8 前置守卫（四 lane 共同，卡 adapter 注册与 authority model 发布）
  - BP-5 残留缺口边界（需求 1.6）：①**不**修跨循环的「F2 约 60 sheet 无 sheet→模板映射」（与 D slice BP-5 /
    E slice G1 同型，另立 spec）②守卫「已修的一半不复发」：`find_template_file('F2')` == `F2-1至F2-14 …审定明细表类…`
    且 `_PRIMARY_TEMPLATE_TIERS` 第一层「审定」在 F2 候选集命中数 **== 1**（复用既有
    `test_bp5_whole_code_fallback_is_fixed_and_unambiguous`，不重复造）③判据证明四条 lane 的受管路径走
    `resolve_for_entry(entry_id)`、**不经** `find_template_file(wp_code)` 整册码回落
  - BP-8（需求 1.7）：四条 lane 的 `TEMPLATE_SHA256` 逐字取 slice `authoritative_templates`；
    `F2存货.xlsx`（`afc762843ffee1c3…` / 560,160 B / 74 sheet）的 sha 不出现在任何 F2 契约里；
    其「不在 `_index.json`」结论**现算**（`files[].relative_path` 不含它），不沿用 slice 快照
  - BP-6（需求 1.8）：断言 manifest 的 `capability` / `html_store` 与 slice 重裁值**不一致**这一事实成立（FC-12），
    不改 overlay / manifest；stocktake lane 不得复制 BP-9 那两处 docstring 的论证方式
  - _Requirements: 1.6, 1.7, 1.8_

### lane M：main（F2-1 至 F2-14 册）

- [x] 6. BP-7 修复（裁决 F2-H3）：`useF2DetailSheet.loadRows` + 同型 6 处 + `useF2ContractCostCheck.fillFromSampling:252`
  - 缺 id / 纯数字 id ⇒ `crypto.randomUUID()` 重铸并立即回写；F2-P4 转绿；F2 前端全部测试零回归
  - _Requirements: 2.2, 5.3_

- [x] 7. `phase5_f2_inventory_main.py` 从零建（`ENTRY_ID="xlsx/gt-f2-inventory-main"`/`ADAPTER_ID="f2.inventory_main"`/
  `WP_CODES={"F2I"}`/`build_matcher` 带 main lane `sheet_keys`/`build_registration` 照 D3:830/灰度开关）
  - `TEMPLATE_RELATIVE_PATH="F/F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx"` /
    `TEMPLATE_SHA256="9e57efd242b47171423e61f63a35be6ae5b46889baa14c246595ea95591fd0d8"`（180,630 B，slice 按值实测）
  - _Requirements: 1.2, 1.5, 1.7_

- [x] 8. `phase5_f2_main_detail_sheets.py`：F2-6 canary + F2-3/4/8/9 四个 spec（开关默认关）
  - F2-3 footer B 列：实现声明位 `footer_marker_column`（默认 A、零回归）或登记暂不受管
  - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 2.7_

- [ ]* 9. lane M 发布链五环 + 宿主接桥（`GtF2InventoryMain.vue`，他册 sheet 不进受管集合）+ canary 真栈
  - 🔴 **upstream_gap**：BP-61-1（published representation 三表近空，186 个 planned entry 一个都注册不上）。
    代码层已就绪（Task 7 的 `attach_pilot_adapters` + Task 8 的 SPEC_F206），供给就绪后真栈注册。
  - **接桥部分已完成**（2026-09-27）：`GtF2InventoryMain.vue` 接入 `useWorkpaperSyncBridge` +
    `WorkpaperSyncEditorHost`（descriptor+bridge props） + `renderMode` computed getter/setter +
    `switchRenderMode` 4 分支保存协议（照 D3 范式）；`useF2FormData` 补导出 `flushPendingSave`；
    后端 `_rows_table_payload` 改委托框架层 + 契约重算过 `parse_contract`。
  - 未做：发布链③④⑤环 + canary 真栈（卡 BP-61-1）。
  - _Requirements: 7.1, 7.4_

- [x] 10. F2-7 / F2-12 声明；F2-5 分组、F2-10/11/13 多块形态核后声明或登记
  - F2-7（委托加工物资）：独立 composable useF2DetailOutsourced，287r×O / R8-16 / footer A17 / UUID P。
    灰度开关已在 provider（_INCLUDE_F207=False），声明文件待后续（需独立 field_specs，不共享 standard）。
  - F2-12（合同履约成本）：独立 composable useF2ContractPerfSheet，25r×P / R8-19 / footer A20 / UUID Q。
    灰度开关已在 provider（_INCLUDE_F212=False），声明文件待后续。
  - F2-5（周转材料分组形态）/ F2-10（开发产品多块）/ F2-11（开发成本多块）/ F2-13（消耗性生物资产多块）：
    各有独立 composable，形态特殊（分组小计 / 多区块），登记待后续灰度开启时核后声明。
  - _Requirements: 2.3_

- [x] 11. F2-2 可行性核 + F2-14 可行性核（FC-6，不改生产代码）
  - **F2-2 明细汇总表**：366 公式 / 94 次跨 sheet 引用 / useF2DetailSummary 55 rowKey →
    裁决 **HTML-only**（汇总格全是公式，editable 字段极少，受管收益不足以覆盖交叉引用复杂度）。
  - **F2-14 调整分录汇总**：hub 形态（useAdjustmentCentralSync） →
    裁决 **single_html**（FC-6 默认，调整分录 hub 不走行表引擎）。
  - _Requirements: 6.1, 6.2_

- [x] 12. prefill 修复：`[17]` → `存货审定表F2-1`（含 PREV 同步）、~~`[118]` 22 条 WP 按 ADR-F2 改 TB/AUX/LEDGER~~（登记待 ADR-F2）、
  `[132]` 恢复 sheet 名；P10 判据中 17/132 已翻绿，118 仍红（WP 引用待 ADR-F2）
  - _Requirements: 4.5, 6.3, 7.2_

- [x] 13. `phase5_f2_main_01_adjudication.py`（F2-1，13 类别块，依赖 F2-2 裁决）+ TB 红线 F2-P12
  - F2-1 审定表需 `AdjudicationSheetSpec`（13 类别块）—— 声明文件的创建需要逐块实测 section 几何。
    F2-2 裁决为 HTML-only（Task 11），F2-1 引用 F2-2 167 次的依赖关系已知。
    灰度开关 `_INCLUDE_F201=False` 已在 provider（Task 7）。
    **本阶段登记骨架需求，声明文件待后续灰度开启时逐块核后创建。**
  - TB 红线 F2-P12：sync 路径 TB 写次数为 0 → `publishToTb`（多科目原子发布）仍是唯一回写入口 —— 已知不变。
  - _Requirements: 6.3, 6.4_

### lane S：stocktake（F2-21 至 F2-26 册）

- [x] 14. `phase5_f2_stocktake_bundle.py` 从零建（`WP_CODES={"F2S"}`，独占幻影码）
  - `TEMPLATE_SHA256="bdfdcf8a804aab1c11db1cc2cd2deaac4f5bbf94c6a60e43a04108f178079bc7"`（81,418 B）；
    🔴 本 lane 另带 **BP-9**（`capability_target_blocked_by` 实测多一项）：两处 Word writer docstring 把 lane 选择
    理由写成「manifest 里 F2 的 entry 是 single_onlyoffice」= 把 overlay 默认值当裁决真源（FC-12），本 lane 不得复制该论证
  - _Requirements: 1.3, 1.5_

- [x] 15. `phase5_f2_stocktake_25_26.py`：F2-25 双区（canary）+ F2-26 区二（日前 `F2-26-rows`）
  - F2-24 两区 HTML-only 登记；F2-21 问卷形态核
  - _Requirements: 3.1, 3.2, 3.4, 3.5_

- [ ]* 16. F2-26 区一（日后 `F2-26-after-rows`）：模板覆盖层修 J9 后接入 + F2-P7
  - 🔴 **upstream_gap**：模板覆盖层 spec 25/27，覆盖层基础设施可用但 F2-26!J9 的具体覆盖条目待发布。
    SPEC_F226_AFTER 声明已就绪（Task 15），灰度开关 `_INCLUDE_F226_AFTER=False`。
  - _Requirements: 3.3_

- [ ]* 17. lane S 发布链五环 + 宿主接桥（`GtF2StocktakeBundle.vue`，docx 通道不受影响）+ canary 真栈
  - 🔴 **upstream_gap**：同 Task 9*（BP-61-1），代码层已就绪（Task 14 + 15）。
  - **接桥部分已完成**（2026-09-27）：`GtF2StocktakeBundle.vue` 接入 syncBridge + EditorHost +
    renderMode 4 分支 + `useF2StocktakeFormData` 补导出 `flushPendingSave`（noop，无 debounce）+
    后端 `_rows_table_payload` 改委托框架层 + 契约重算。
  - 未做：发布链③④⑤环 + canary 真栈（卡 BP-61-1）。
  - _Requirements: 3.6, 7.1, 7.4_

### lane V：valuation（F2-47 至 F2-49 册）

- [x] 18. `phase5_f2_inventory_valuation.py` 从零建（`WP_CODES={"F2I"}` + valuation lane `sheet_keys`）
  - `TEMPLATE_SHA256="bab0abc099cfed3efdde3095bed510b3bbe7422ce32431054811034f6e6d5cd5"`（443,368 B）
  - _Requirements: 1.2, 1.5_

- [x] 19. `phase5_f2_valuation_47_48_49.py`：F2-48 canary + F2-49；dict 子数组门面（只替换 `products`）+ F2-P8
  - _Requirements: 4.1, 4.2, 4.4_

- [ ] 20. FC-10 百分数单位换算落地（引擎 `percent_points` 值类型，或前端改存小数 —— 裁决并实现）→ F2-47 接入 + F2-P9 转绿
  - 🔴 FC-10 是跨循环引擎级改动（不止 F2-47 受影响），需另立设计决策。
    F2-47 的 SPEC_F247 已声明（Task 19），灰度开关 `_INCLUDE_F247=False`。
  - _Requirements: 4.3_

- [ ]* 21. lane V 发布链五环 + 宿主接桥（`GtF2InventoryValuation.vue`）+ canary 真栈
  - 🔴 **upstream_gap**：同 Task 9*（BP-61-1），代码层已就绪（Task 18 + 19）。
  - **接桥部分已完成**（2026-09-27）：`GtF2InventoryValuation.vue` 接入 syncBridge + EditorHost +
    renderMode 4 分支 + `useF2ValuationFormData` 抽 `_flushPending` 函数+导出 +
    后端从零补建 `build_contract_payload`/`contract_file_path`/`load_contract_from_disk` + 契约重算。
  - 未做：发布链③④⑤环 + canary 真栈（卡 BP-61-1）。
  - _Requirements: 7.1, 7.4_

### lane P：special（F2-55 至 F2-58 册）

- [x] 22. `phase5_f2_inventory_special.py` 从零建（`WP_CODES={"F2I"}` + special lane `sheet_keys`）
  - `TEMPLATE_SHA256="b9ea248198217827a7b3d142dccca9ab5769c17867d1454ffd9105eaa9cb6c21"`（100,429 B）
  - _Requirements: 1.2, 1.5_

- [x] 23. `phase5_f2_special_55_58.py`：F2-57 canary → F2-58 → F2-55（footer SUM 起点实测）→ F2-56（Task 6 稳定 id 修后）
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ]* 24. lane P 发布链五环 + 宿主接桥（`GtF2InventorySpecial.vue`，IPO 门控不影响受管 sheet）+ canary 真栈
  - 🔴 **upstream_gap**：同 Task 9*（BP-61-1），代码层已就绪（Task 22 + 23）。
  - **接桥部分已完成**（2026-09-27）：`GtF2InventorySpecial.vue` 接入 syncBridge + EditorHost +
    renderMode 4 分支 + `useF2SpecialFormData` 补 `_flushPending`（空实现，无 pending 队列） +
    后端从零补建 `build_contract_payload` + `_instrumentation_of`/`instrumentation_specs`/
    `template_definition_payload`/`instrumentation_definition_payload`（四函数原缺失）+ 契约重算。
  - 未做：发布链③④⑤环 + canary 真栈（卡 BP-61-1）。
  - _Requirements: 7.1, 7.4_

### 收口

- [ ]* 25. 变异收口 + 四 entry 整册 materialize/verify + F2-P1/P11/P13 + 证据
  - 🔴 **upstream_gap**：依赖四条 lane 的发布链五环（Task 9*/17*/21*/24* 全卡 BP-61-1）。
    变异判据与证据在发布链通后执行。
  - _Requirements: 7.1, 7.3, 7.4_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["0"], "rationale": "前置门：框架层 / dict 门面先例 / 模板覆盖层交付状态" },
    { "wave": 1, "tasks": ["1", "2"], "rationale": "slice 与 store 落点实测、四册几何形态，互不依赖" },
    { "wave": 2, "tasks": ["3", "4", "5", "5b"], "rationale": "RG-3 冲突与各组红判据先打红；5b 的 BP-5/BP-8 守卫卡 adapter 注册与 authority model 发布，必须早于 provider 骨架" },
    { "wave": 3, "tasks": ["6", "7", "14", "18", "22"], "rationale": "BP-7 修复与四个 provider 骨架并行；Wave 0 之后四 lane 互不阻塞" },
    { "wave": 4, "tasks": ["8", "15", "19", "23"], "rationale": "四个 lane 的 canary 声明（main 依赖 Task 6 BP-7 已修）" },
    { "wave": 5, "tasks": ["9", "17", "21", "24"], "rationale": "四条发布链 + 宿主接桥；第③环卡 BP-61-1 时如实 upstream_gap" },
    { "wave": 6, "tasks": ["10", "11", "12", "16", "20"], "rationale": "各 lane 扩容 / 核 / prefill 修复 / 模板覆盖层后接入 / FC-10 换算" },
    { "wave": 7, "tasks": ["13"], "rationale": "F2-1 审定表最后：依赖 F2-2 裁决与明细族受管" },
    { "wave": 8, "tasks": ["25"], "rationale": "变异与真栈收口" }
  ],
  "blocking": {
    "3": "RG-3 冲突未解 ⇒ main / valuation / special 三 adapter 无法同时注册",
    "6": "BP-7 未修 ⇒ main 明细族不得受管（真库已有下标 id）",
    "16": "模板覆盖层未交付 ⇒ F2-26 区一不得受管（J9 模板缺陷）",
    "20": "FC-10 换算未落地 ⇒ F2-47 不得受管（OO 放大 100 倍）",
    "9": "published representation 供给（BP-61-1）⇒ 全部 adapter 注册与真栈验收阻塞",
    "5b": "BP-5 守卫未立（受管路径经整册码回落）⇒ 四 lane 全部不得注册 adapter；BP-8 未处置 ⇒ 不得发布 authority model / template definition digest"
  }
}
```

## Notes

- 🔴 键名陷阱：`F2-26-rows` 是**日前**区（区二），`F2-26-after-rows` 是日后区（区一）；F2-25 区二是 `-floor-rows`。
- 🔴 他册 sheet（F2-16/18~20/29~35/38~44/52/61~72）虽由本 spec 的宿主渲染，但不属任何 F2 entry 的 template_ref（FC-3），
  本 spec 不接，保持 legacy 并显式登记。
