# Tasks — D4-4/8/12 gap closure

- [x] 1. C0模板/identity：只读核定D4-4/8/12真实sheet、区域、wp_id稳定身份并反向去重owner；记录已有能力，不重做。
  - **核定结论（2026-09-20，权威源 = `docs/operations/d4-bidirectional-writeback-inventory.md` 逐张 openpyxl 实测冻结清册 + 前端组件实证）**：
  - **D4-4 调整分录汇总**：sheet `调整分录汇总表D4-4`；前端 `D4TabAdjustment.vue`（core）+ `useD4Adjustment` + `useAdjustmentCentralSync`，store 键 `D4-4-rows`（8列：调整事项/类别/报表项目/科目名称/附注项目/借方/贷方/索引/备注）；已有能力：调整分录 CRUD、借贷平衡指示、推送A13、导入导出三级、与调整分录中央模块双向联动。**owner 已裁决 = single_html（不可单元格级双向）**，理由实证成立：hub store 被 A13/借贷平衡语义占用、模板无行身份 UUID 列载体。⇒ **本 spec 不得对 D4-4 新增"双向 identity"，Req 1.2 触发。**
  - **D4-8 重要产品毛利分析**：sheet `重要产品毛利率分析表D4-8`（A1:X40，固定产品块 × 固定12月 static matrix）；前端 `D4TabProductMargin.vue`（analysis）+ store `D4-8-products`（`[{name, months[12], priorMonths[12], industry[3]}]`）；已有能力：产品×月计算、持久化、导入导出。**owner 已裁决 = HTML-only**，理由实证成立：无真实动态行维度（product 块计数动态但块内12月是固定静态行 + 大量 Excel 内部公式），引擎硬约束（受管 cell 必须锚定动态表 `<tableParts>` 载体）不支持纯静态/静态块 sheet 双向回写（同 D4-33/D4-45 precedent）。⇒ **本 spec 不得对 D4-8 新增"双向 identity"，Req 1.2 触发。**
  - **D4-12 合同检查**：sheet `合同检查表D4-12`（A1:K57，**转置动态表**：列=合同 entity、行=21字段，同 D4-29 范式）；前端 `D4TabContract.vue`（inspection）+ `useD4ContractInspection`，store `D4-12-contracts-v2`（`ContractInspectionItem[]`）；已有能力：合同卡片、OCR、AI、导入导出。**owner 已裁决 = 转置大工程，移交专项 spec `d4-12-transposed-writeback`**，理由实证成立：转置引擎完全绑死 D4-29（`adapters/excel.py` 硬编码 `is_enabled`/`materialize_file`/`extract_file` 特判 + D4-29 provider 硬编码 MANAGED_REF/carrier row/definedName），落地需 (a)泛化 D4-29 转置引擎（高回归风险）+ (b)模板加 workbook-scope definedName + 隐藏身份载体行（D4-12 模板两者皆无）+ (c)新 provider，跨度远超本 gap spec。⇒ **本 spec 不承接 D4-12 双向 identity，移交专项 spec。**
  - **横切阻塞（清册记录，优先级最高）**：D4 entry 整册 materialize 已达 138s > 120s 生产软上限，**再落任何一张 D4 双向 sheet 都会使 `xlsx/gt-d4-operating-revenue` entry 生产不可发布**；"D4 entry 拆分/增量 materialize"是前置条件。
  - **UNVERIFIABLE 记录（Req 1.1）**：三张表的"双向 identity + 公式 DAG"均因引擎/模板硬约束或已被专项 spec 认领而**无法在本 spec 范围内做实**；本 spec 的核心前提（"三者已有结构化能力不重做，只补双向 identity/公式/DAG/冲突"）与权威裁决冲突。**结论：本 spec 三张表的 owner 已全部另有裁决归属，按 Req 1.2 应全部从本 spec 移除，本 gap spec 无剩余可实施产物。等待用户对 spec 处置决策。**
  - _Requirements: 1.1, 1.2, 8.1_
- [ ] 2. C1sync：为确认纳管表接入共享服务、字段合并、同字段冲突和applied确认。
  - _Requirements: 2.1, 2.2_
- [ ] 3. C2formula：冻结wp_id公式key、preset/custom、F-SHELL、真实DAG及缺失/损坏/stale/blocked。
  - _Requirements: 2.3_
- [ ] 4. C3linkage：保留已有A13/调整、产品计算、合同OCR/AI，只补真实联动接收端；公式同步不发布TB/A13。
  - _Requirements: 2.4, 3.2_
- [ ] 5. C4逐表验收与变异：roundtrip、权限、Playwright、owner去重、公式/冲突和发布确认；只门控本spec相关产物。
  - _Requirements: 3.1, 3.2_

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1"],"rationale":"C0先核定模板与owner"},{"wave":2,"tasks":["2","3"],"rationale":"sync与formula并行"},{"wave":3,"tasks":["4"],"rationale":"linkage依赖前序契约"},{"wave":4,"tasks":["5"],"rationale":"C4最后"}],"blocking":{"1":"未核定不得新增owner","2":"sync未冻结不得roundtrip","3":"formula未冻结不得接入公式"}}
```
