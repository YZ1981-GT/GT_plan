# Tasks — D4-4/8/12 gap closure

- [x] 1. C0模板/identity：只读核定D4-4/8/12真实sheet、区域、wp_id稳定身份并反向去重owner；记录已有能力，不重做。
  - **核定结论（2026-09-20，权威源 = `docs/operations/d4-bidirectional-writeback-inventory.md` 逐张 openpyxl 实测冻结清册 + 前端组件实证）**：
  - **D4-4 调整分录汇总**：sheet `调整分录汇总表D4-4`；前端 `D4TabAdjustment.vue`（core）+ `useD4Adjustment` + `useAdjustmentCentralSync`，store 键 `D4-4-rows`（8列：调整事项/类别/报表项目/科目名称/附注项目/借方/贷方/索引/备注）；已有能力：调整分录 CRUD、借贷平衡指示、推送A13、导入导出三级、与调整分录中央模块双向联动。**owner 已裁决 = single_html（不可单元格级双向）**，理由实证成立：hub store 被 A13/借贷平衡语义占用、模板无行身份 UUID 列载体。⇒ **本 spec 不得对 D4-4 新增"双向 identity"，Req 1.2 触发。**
  - **D4-8 重要产品毛利分析**：sheet `重要产品毛利率分析表D4-8`（A1:X40，固定产品块 × 固定12月 static matrix）；前端 `D4TabProductMargin.vue`（analysis）+ store `D4-8-products`（`[{name, months[12], priorMonths[12], industry[3]}]`）；已有能力：产品×月计算、持久化、导入导出。
    - 🔴 **裁定更正（2026-09-21，本条 C0 时的 HTML-only 结论已作废）**：原写「owner 已裁决 = HTML-only，引擎硬约束不支持纯静态 sheet」——该结论**已被 spec `workpaper-sync-static-cell-sheet-writeback` 推翻**。该 spec 补了 `BindingKind.static_region`（definedName 锚定静态受管区）旁路，D4-8 的 slot0（产品A 块）180 static cell 现经 workbook-scope definedName 直写/反读。**D4-8 现为 ✅ 三维代码全绿**：契约 `d48-managed`（180 cell）已落盘、前端 `D4TabProductMargin.vue` 已接 `useWorkpaperSyncBridge` + 宿主 `isD4DedicatedSyncSheet` 已含 'D4-8'、representation 已 rematerialize（gen 81→82 / rev 106，commit `98ab0eaef`），仅真 OO canvas 往返为 env 门。**owner = `workpaper-sync-static-cell-sheet-writeback`（Task 11）**，不在本 gap spec 范围。⇒ 本 spec 仍不对 D4-8 承接产物（Req 1.2 触发），但**原因是「已被专项 spec 落地」而非「引擎不支持」**。
  - **D4-12 合同检查**：sheet `合同检查表D4-12`（A1:K57，**转置动态表**：列=合同 entity、行=21字段，同 D4-29 范式）；前端 `D4TabContract.vue`（inspection）+ `useD4ContractInspection`，store `D4-12-contracts-v2`（`ContractInspectionItem[]`）；已有能力：合同卡片、OCR、AI、导入导出。**owner 已裁决 = 转置大工程，移交专项 spec `d4-12-transposed-writeback`**，理由实证成立：转置引擎完全绑死 D4-29（`adapters/excel.py` 硬编码 `is_enabled`/`materialize_file`/`extract_file` 特判 + D4-29 provider 硬编码 MANAGED_REF/carrier row/definedName），落地需 (a)泛化 D4-29 转置引擎（高回归风险）+ (b)模板加 workbook-scope definedName + 隐藏身份载体行（D4-12 模板两者皆无）+ (c)新 provider，跨度远超本 gap spec。⇒ **本 spec 不承接 D4-12 双向 identity，移交专项 spec。**
  - ~~**横切阻塞（清册记录，优先级最高）**：D4 entry 整册 materialize 已达 138s > 120s 生产软上限~~ 🔴 **已过时作废（2026-09-21）**：138s 是 spec `workpaper-sync-materialize-large-table-performance` **Wave 5** 性能修复*前*的数字。Wave 5（观测解析复用，同字节被 `load_workbook` 解析 389 次→复用一次）后真库 CPU 段 **138.7s→69.33s**，加 D4-33/D4-8 后实测 ~82s，仍在 120s 软上限内（D4-8 rematerialize gen82 未抛 SoftTimeout 实证）。「再落一张就不可发布」的前提不成立。
  - **UNVERIFIABLE / 归属记录（Req 1.1，2026-09-21 更新）**：本 spec 三张表（D4-4/8/12）在 C0 核定时的裁决现状——
    - **D4-4**：owner = single_html（模板无行身份 UUID 列载体 + hub store 被 A13/借贷平衡语义占用），保持裁决，不做单元格级双向。
    - **D4-8**：**已由专项 spec `workpaper-sync-static-cell-sheet-writeback` 落地为 ✅ 三维代码全绿**（见上条更正），不在本 gap spec 范围。
    - **D4-12**：owner = 转置大工程，移交专项 spec `d4-12-transposed-writeback`（尚未创建，待立项）。
  - **结论：本 gap spec 三张表 owner 已全部另有归属（single_html / 专项 spec 已落地 / 专项 spec 待立项），本 spec 无剩余可实施产物，正式收口。下方 Task 2-5 随之作废（`[-]` N/A，非欠账）。**
  - _Requirements: 1.1, 1.2, 8.1_
- [-] 2. C1sync：~~为确认纳管表接入共享服务、字段合并、同字段冲突和applied确认~~ —— **N/A 作废**：Task 1 已判定三张表无本 spec 可承接的纳管表（D4-4 single_html / D4-8 归专项 spec / D4-12 待专项 spec）。
  - _Requirements: 2.1, 2.2_
- [-] 3. C2formula：~~冻结wp_id公式key、preset/custom、F-SHELL、真实DAG及缺失/损坏/stale/blocked~~ —— **N/A 作废**：公式二次编辑现由平台 `FormulaManagerDialog` + `wp_formula` 统一提供（见 `d4-33-36` spec B3 结论），本 spec 无独立公式 DAG 产物。
  - _Requirements: 2.3_
- [-] 4. C3linkage：~~保留已有A13/调整、产品计算、合同OCR/AI，只补真实联动接收端~~ —— **N/A 作废**：D4-4 的 A13/调整分录中央联动、D4-8 产品计算、D4-12 合同 OCR/AI 均为既有能力，无本 spec 新增联动接收端。
  - _Requirements: 2.4, 3.2_
- [-] 5. C4逐表验收与变异：~~roundtrip、权限、Playwright、owner去重、公式/冲突和发布确认~~ —— **N/A 作废**：无本 spec 产物可验收（D4-8 验收归 static-cell-writeback spec）。
  - _Requirements: 3.1, 3.2_

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1"],"rationale":"C0先核定模板与owner"},{"wave":2,"tasks":["2","3"],"rationale":"sync与formula并行"},{"wave":3,"tasks":["4"],"rationale":"linkage依赖前序契约"},{"wave":4,"tasks":["5"],"rationale":"C4最后"}],"blocking":{"1":"未核定不得新增owner","2":"sync未冻结不得roundtrip","3":"formula未冻结不得接入公式"}}
```
