# Requirements — D4-14 营业收入发生检查表（穿行测试）双向回写

## 背景与现状（2026-09-21 openpyxl 实读源模板 + 逐文件核实，非推断）

D4-14「营业收入发生检查表」是**七维证据链穿行测试**：每笔交易 × 记账凭证/销售合同/出库单/运输单/签收单/发票/其他 七个证据维度。目标是把 D4-14 从 legacy 单向 `GtOnlyOfficeSheet` 升级为走统一 `useWorkpaperSyncBridge` 的真双向 sheet。

### 🔴 核心裁决门（本 spec 的第一性问题，一切工程的前置）

**真障碍 = 源模板物理列 与 前端 7 维模型 是两套不同的列集，无法逐列对齐。** 这不是 footer/引擎问题（下方实证已排除），而是**语义映射权威源未确认**——源模板有 15+ 个物理列在前端 7 维模型里**无对应字段**，无处安放。**在这套"物理列 ↔ 前端维度字段"逐列映射经审计业务复核裁决前，本 spec 不得建 provider**（否则会把源模板物理列静默丢弃，违 correctness 铁律）。

### 现状实测证据（承重锚点，实现以此为准）

**源模板** `backend/wp_templates/D/D4-13至D4-20主营业务收入-检查（Leap应对措施-检查）.xlsx`，sheet `营业收入发生检查表D4-14`，dims `A1:AK52`（37 列）。

**物理列（R13-R14 两级表头，实测冻结）**：
- A：序号
- **记账凭证**（B13 组，B14-G14）：B=客户名称 · C=日期 · D=编号 · E=品名 · F=数量 · G=金额
- **销售合同/销售订单**（H13 组，H14-I14）：H=日期 · I=合同号/订单号
- **出库单**（J13 组，J14-M14）：J=日期 · K=编号 · L=品名 · M=数量
- N=仓库保管员 · O=发货审批人（独立列，挂在出库/运输之间）
- **运输单**（P13 组，P14-T14）：P=日期 · Q=编号 · R=运输数量 · S=运输公司 · T=运输地址
- **签收单**（U13 组，U14-AA14）：U=日期 · V=品名 · W=数量 · X=金额 · Y=签收人 · Z=盖章类型 · AA=盖章单位
- **发票**（AB13 组，AB14-AF14）：AB=日期 · AC=编号 · AD=品名 · AE=数量 · AF=金额
- AG/AH=……（占位）· AI=其他支持性文件或说明 · AJ=索引号 · AK=是否异常
- 数据区 **R15-R36**（22 行）；footer marker = **单行 `合计` R37**（G37/X37/AF37=SUM 公式 → formula_mask）；`本期发生额` R38 / `检查比例` R39（G39=G37/G38，审计说明辅助行 HTML-only）；R40 审计说明 / R44 审计结论（HTML-only）。

**前端 7 维模型**（`useD4WalkthroughTest.ts` 的 `TransactionItem` + `DIMENSION_GROUPS`，实测冻结，共 27 业务字段）：
- voucher 记账凭证（7）：month/date/number/productName/quantity/amount/accountingDate
- contract 销售合同（5）：number/productName/amount/approver(签发审批)/confirmor(签收确认)
- delivery 出库单（4）：date/productName/amount/warehouseKeeper(仓库保管员)
- shipping 运输单（3）：date/productName/amount
- receipt 签收单（3）：date/productName/amount
- invoice 发票（3）：date/number/amount
- other 其他（2）：description/indexNo
- 派生（3，不入契约）：consistencyScore/consistencyDetails/conclusion + isAnomalous

**后端行式 IO** `_d4_import_export.py` 的 `_SHEET_HEADERS["D4-14"]` = **32 列语义投影头**（凭证 7+合同 5+出库 4+运输 3+签收 3+发票 3+其他 2+派生 3），是**按前端 7 维平铺的投影头，不是源模板物理列**。import/export 走「前端 7 维 ↔ 32 列语义投影」（自洽已实现）；但 sync 双向要求「前端 store ↔ 源模板物理 cell」，两者是不同列集。

**契约/宿主登记**：`d4-14`/`d414` 在 `backend/data/workpaper_sync_contracts/` **零命中**；`isD4DedicatedSyncSheet` **不含 'D4-14'**（前端在线编辑仍 legacy `GtOnlyOfficeSheet`）。

### 🔴 三层深核实（排除误导，锁定真障碍）

1. **footer 不是障碍**：footer marker = 单行 `合计` R37（同 D4-7/D4-20 footer 同构）；`d4-inspection` evidence 当初记的「计算型 footer 超范式」经实测**不成立**。
2. **引擎范式可支持**：footer 排除后，D4-14 是**单宽动态行表**（非转置，非纯静态），引擎的动态行 + 嵌套 json_pointer 能支持（同 D4-7 已验证）。
3. **真障碍 = 物理列 ↔ 前端 7 维列集不对齐**：源模板物理列**多出**前端 7 维没有的字段，逐列对照：
   - 记账凭证：B 客户名称（前端无）
   - 销售合同：H 日期（前端 contract 无 date）、O 发货审批人 / N 仓库保管员挂位（前端 delivery.warehouseKeeper 有，approver/confirmor 归属存疑）
   - 出库单：K 编号、M 数量（前端 delivery 无 number/quantity）
   - 运输单：Q 编号、R 运输数量、S 运输公司、T 运输地址（前端 shipping 只有 date/productName/amount，全无）
   - 签收单：Y 签收人、Z 盖章类型、AA 盖章单位（前端 receipt 只有 date/productName/amount，全无）
   - 发票：AD 品名、AE 数量（前端 invoice 只有 date/number/amount，无 productName/quantity）
   - 合计 **15+ 个物理列在前端 7 维无对应字段**。sync 双向若直接拿 32 列语义投影头当映射会把这些物理列静默丢弃。

### ⚠️ 反误导记录（写进 requirements 防再犯）

**不要**因「后端 import/export 已有 D4-14 的 32 列头 + `_parse_d4_14_row`」就以为 sync 可直接复用——那是**语义投影头**（按前端 7 维平铺），**非源模板物理列头**。直接拿它当 sync 列映射 = 静默丢弃源模板 15+ 物理列（违 correctness 铁律）。

### 关键裁决（DEC）

- **DEC-0（业务裁决门先行，硬前置）**：本 spec 第一阶段 = 产出「源模板 R13-14 物理列 ↔ 前端 7 维字段」逐列裁决表，每个物理列标 {受管映射到某维字段 / 前端补字段 / 留 HTML-only}，经审计业务复核确认权威源后方可进后续。裁决未定 = 后续 Task 全 `[-]` BLOCKED，唯一解除条件写在任务正文。
- **DEC-1（单宽动态行表，非转置）**：D4-14 走动态行表轴（同 D4-7），不走 D4-29 转置轴、不走 D4-8/D4-33 static-region 轴。行身份 = 交易 id，UUID 列可放 AL（物理列到 AK，AL 空）。
- **DEC-2（嵌套 json_pointer）**：受管字段 json_pointer 走 7 维嵌套（如 `/voucher/amount`、`/invoice/date`），同 D4-7 已验证的嵌套投影。
- **DEC-3（footer HTML-only 边界）**：R37 合计（formula_mask）、R38/R39 辅助行、R40+ 审计说明/结论保持 HTML-only，不入受管区。
- **DEC-4（correctness 优先于覆盖率）**：裁决可能结论 = 「前端补字段」（扩前端 7 维模型加缺失字段）或「物理列留 HTML-only」（该列不受管）。**无论哪种，都不得静默丢弃物理列**；若裁决为大量补字段，须评估是否值得（ROI），可能结论是"部分维度受管 + 部分 HTML-only"的混合态。

## Requirements

### Requirement 1: 【业务裁决门】物理列 ↔ 前端 7 维逐列映射裁决（硬前置）
**User Story:** 作为审计业务负责人，我要确认 D4-14 源模板每个物理列如何映射到前端 7 维字段，以便后续 provider 不静默丢弃任何物理列。

#### Acceptance Criteria
1. WHEN 产出裁决表 THEN 系统 SHALL 逐列（A/B/C…AK 全 37 列）标注 {受管→映射到某维字段 / 前端补字段(需扩模型) / HTML-only(不受管) / 派生列(formula_mask)}，每列有明确归属，无「未决」残留。
2. WHEN 裁决涉及前端无对应字段的 15+ 物理列（B 客户名称 / H 合同日期 / K 出库编号 / M 出库数量 / Q 运输编号 / R 运输数量 / S 运输公司 / T 运输地址 / Y 签收人 / Z 盖章类型 / AA 盖章单位 / AD 发票品名 / AE 发票数量 等）THEN 每列 SHALL 明确标「前端补字段」或「HTML-only」，并记录审计业务复核意见。
3. WHEN 裁决表完成 THEN 系统 SHALL 由审计业务复核签署确认（权威源），未签署前 SHALL 视为 BLOCKED。
4. WHEN 裁决为「前端补字段」THEN 系统 SHALL 评估扩前端 7 维模型的影响面（TransactionItem 类型 / DIMENSION_GROUPS / 一致性引擎 / import-export 32 列头是否需同步扩）。
5. IF 裁决未签署确认 THEN 后续 Requirement 2-6 的实现任务 SHALL 保持 BLOCKED（不得基于臆想映射建 provider）。

### Requirement 2: 前端模型对齐（依赖 Req 1 裁决）
**User Story:** 作为编制人，我要前端 7 维模型与裁决表一致，以便受管字段有真实前端归属。

#### Acceptance Criteria
1. WHEN 裁决含「前端补字段」THEN 系统 SHALL 按裁决扩 `TransactionItem` 对应维度 sub-object + `DIMENSION_GROUPS` + 一致性引擎（若补字段参与一致性比对）。
2. WHEN 前端行身份 THEN 系统 SHALL 保证 `TransactionItem.id` 稳定 + 安全（不含 `/~{}`、唯一、跨会话不变）。
3. WHEN 补字段落地 THEN 系统 SHALL 不回归既有一致性校验 / OCR / D4-12 联动 / 序时账导入 / AI 穿行分析能力。
4. WHEN import/export 32 列语义投影头与新裁决冲突 THEN 系统 SHALL 同步对齐（避免语义投影头与 sync 物理映射再次分叉）。

### Requirement 3: D4-14 provider + 契约（依赖 Req 1/2）
**User Story:** 作为编制人，我要 D4-14 的交易行经动态行 provider 双向读写。

#### Acceptance Criteria
1. WHEN provider 实例化 THEN 系统 SHALL 用实测几何：managed_sheet=`营业收入发生检查表D4-14`、sheet_key=`d4-14-managed`、header 两级 R13-14、数据区 R15 起、UUID 列 AL、footer marker `合计`。
2. WHEN 受管字段声明 THEN 系统 SHALL 严格按裁决表的「受管」列建 json_pointer（7 维嵌套），HTML-only 列不入契约，formula_mask = G/X/AF 合计列 + 派生列。
3. WHEN materialize/extract THEN 系统 SHALL 逐交易行按裁决映射写/读物理列，**不触碰** HTML-only 物理列（保留其模板内容）。
4. WHEN 契约重生成 THEN 系统 SHALL 新增 `d4-14-managed` sheet descriptor（两级 header + 嵌套 field + formula_mask）+ sibling store（`D4-14-transactions`）；`assert_contract_file_matches_source` OK；mapping_digest 冻结；契约 sheet 计数同步。
5. WHEN 契约加 D4-14 后 THEN 同 entry 既有张 store-projection SHALL 仍 200（不打挂）。

### Requirement 4: 发布链（依赖 Req 3）
**User Story:** 作为发布者，我要 D4-14 representation 真实发布到 live PG。

#### Acceptance Criteria
1. WHEN 发布链 THEN 系统 SHALL generate --apply → provision → rematerialize --apply，判据查库不看退出码。
2. WHEN rematerialize THEN entry bundle SHALL = desired（含 d4-14-managed）、gen++、无 Roundtrip/FooterAnchorDrift。
3. WHEN D4-14 加入后整册 materialize THEN 系统 SHALL 在 soft_limit 120s（Wave 5 后基线 ~82s）内不抛 SoftTimeout（不得提高 soft_limit 过关）。
4. WHEN 发布后 GET store-projection THEN 系统 SHALL 返 200 含 D4-14 受管字段。

### Requirement 5: 前端接桥 + 宿主登记（依赖 Req 3）
**User Story:** 作为编制人，我要 D4-14 在线编辑走统一同步桥。

#### Acceptance Criteria
1. WHEN `D4TabOccurrence.vue` 在线编辑 THEN 系统 SHALL 用 `useWorkpaperSyncBridge`（entry=xlsx/gt-d4-operating-revenue、sheet=d4-14-managed、capabilityForEntry）+ `WorkpaperSyncEditorHost`，替 legacy `GtOnlyOfficeSheet`；flushHtml 先 flushPendingSave 再 readStoreProjection。
2. WHEN 宿主渲染 D4-14 THEN `isD4DedicatedSyncSheet` SHALL 含 'D4-14'。
3. WHEN OO 不可用 THEN 系统 SHALL fail-visible 三态中文 tag，表格视图不受影响。

### Requirement 6: 守卫、变异、消费侧与真栈验收（依赖 Req 3/5）
**User Story:** 作为质控，我要机器化守卫钉死映射正确、不丢物理列、消费侧接线完整。

#### Acceptance Criteria
1. WHEN 后端守卫 THEN 系统 SHALL 覆盖：materialize→extract 7 维嵌套逐字段往返、HTML-only 物理列不被触碰、公式格拒绝、契约 parse 含 d4-14-managed、item_id 映射字面量。
2. WHEN OO→HTML 消费侧（`oo_to_html` mirror）THEN 系统 SHALL 覆盖第四维（`D4-14-transactions` store item 被正确消费 + merge 基线非空）。
3. WHEN 变异反证 THEN 系统 SHALL 对 ≥4 锚点四态 RED：把某 HTML-only 物理列改成受管（应被守卫挡）、去嵌套 json_pointer、formula_mask 可回写、契约去 d4-14-managed。
4. WHEN 真栈 e2e THEN env 可用产 `evidence/.../D4-14.json`（L1 + L2 七维往返）；env 不可用标 `[~] UNVERIFIABLE` 不假绿，往返正确性由后端单测 + 真 PG 无 Roundtrip 保证。

### Requirement 7: 收口与清册同步
#### Acceptance Criteria
1. WHEN 落地完成 THEN `d4-bidirectional-writeback-inventory.md` D4-14 SHALL 转对应态、统计段同步（⏸ 2→1 或 1→0）。
2. WHEN 收口 THEN spec 三件套 SHALL 过结构校验、行数门禁同步、正式产物无 `??`。
3. IF 裁决结论为「不值得双向」（大量 HTML-only、ROI 过低）THEN 系统 SHALL 如实记录裁决为 single_html/部分受管，清册标终态，本 spec 收口为「裁决完成，工程按裁决执行/不执行」，不假装全受管。
