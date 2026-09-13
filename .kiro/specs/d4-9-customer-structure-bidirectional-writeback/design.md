# Design — D4-9 重要客户结构分析双向回写

## Overview

（1. 概述与范围）

把 D4-9 作为**独立 entry** 接入统一双向路径。复用已落地的内核（`ContentMutationService` / `RepresentationService` / `MaterializeCoordinator` / `CallbackDeliveryService` / `OoToHtmlCoordinator` / adapters registry / contracts 强校验器），**不改契约内核**——D4-9 的多区域 + 表级标量已被现有契约模型（`SheetSpec.tables: tuple` + `CellMapping.static_row` + `FooterAnchorSpec.carries_total_formula` + `formula_mask`）表达。

参照实现：`backend/app/services/workpaper_sync/phase5_d4_revenue_detail.py`（+ `phase5_d4_other_revenue_sheet.py`），adapter_id `d4.revenue_detail`，entry_id `xlsx/gt-d4-operating-revenue`。

D4-9 新增：
- 后端 bridge 模块 `phase5_d4_customer_structure.py`（adapter_id `d4.customer_structure`，entry_id `xlsx/gt-d4-customer-structure`）。
- per-entry contract（`d4.customer_structure`，由 bridge `build_contract_payload` 现算 + 磁盘 JSON 锁死 + 生成器脚本）。
- manifest entry + reviewed overlay 裁决 capability。
- 前端 `GtD4OperatingRevenue.vue` 把 D4-9 纳入统一 sync host。
- 前端 `D4TabCustomerStructure.vue` 行补 rowId + 迁移，移除 legacy 单向入口。
- 修 `_d4_import_export.py` 的 D4-9 分支。
- 公式管理：D4-9 用户公式走 `wp_formula` + ACNR 血缘，用户公式 cell 纳入双向保护区。

## Architecture

（2. 契约设计（关键））

### 2.1 契约模型能力（已核实 `contracts.py`）

- `SheetSpec.tables` 是 `tuple[TableSpec, ...]` —— **一张 sheet 支持多张 table**。`SyncContract.all_fields()` 遍历 `sheet.tables → table.fields`。
- `_parse_field`：`cell.row_from` 为 `row_identity`（行域，`row_scoped=True`）或 `>=1 静态行号`（`CellMapping(row_from="static", static_row=n)`，要求 `row_scoped=False`）。→ 表级标量天然可表达。
- `_parse_table`：`row_scoped = (row_identity is not None)`；有 `row_identity` 必须有 `delete_policy`（CS-14）；`mode=formula` 字段的列必须落 `formula_mask`（CS-13）。
- `FooterAnchorSpec.carries_total_formula` 默认 False；为 true 时结构性插行可扩张合计区间。

**结论：D4-9 无需扩展契约内核**（契约模型层）。**但 instrumentation 注入引擎需要一处修复**——见 §2.1.1。

### 2.1.1 instrumentation 同 sheet 双区：实测裁决（决定性）

D4-9 的本期(R13-22)与上期(R27-36)是**同一张 sheet 内的两个受管区**，而 D4-2/3 是**两张不同 sheet 各一区**。全平台无「同 sheet 双区」先例。已用只读探针对 `instrument_workbook_bytes_multi` 跑真实注入（两个 spec 同 `managed_sheet`、不同行段、UUID 列 W/X），实测结论：

- **现状不可行**：`_inject_managed_sheet` 里 `_attach_table_part` 每次无条件插入一个独立 `<tableParts>` 块。同 sheet 注入两次 ⇒ 产出**两个 `<tableParts>` 块**（非法 OOXML，只允许一个）。openpyxl 只认出最后一张 Table（`GT_D49P_ROWS`），本期 Table `GT_D49C_ROWS` 被解析器丢弃 ⇒ 第一区 identity 丢失 = 假双向。
- **路径 A 可行（已实测验证）**：把两个 `<tablePart>` 合并进**一个** `<tableParts count="2">` 块后，openpyxl 同时认出 `GT_D49C_ROWS` + `GT_D49P_ROWS`，OOXML 合法。修复点 = `_attach_table_part`：sheet 已有 `<tableParts>` 时往块内追加 `<tablePart>`，而非新建块。隐藏 UUID 列 W/X 各一列不冲突（两区不同列）。

因此「新建单 entry + 单 sheet 三 table」方案**成立，但前提是先修 `_attach_table_part`**。不修则字节层产出畸形 xlsx。此修改动到双向内核共享文件 `excel_instrumentation.py`（主控 §5.3 共享锁，需协调 + 补变异守卫：改回"新建独立块"必须打红）。

排除的两条路径（不准确）：
- 合成一个连续 Table 覆盖 R13-R37：中间夹合计行 R23/总额 R24/标题 R25/表头 R26，非连续数据区，会把合计/表头当数据行，违背结构真相。
- 绕开 Excel Table 只用 hidden_uuid_column：`_inject_managed_sheet` 与 extract 原生锚点硬依赖 Table present（`IdentityReadbackError`），绕开风险高。

### 2.2 D4-9 contract 结构（单 sheet 3 table）

sheet: `重要客户结构分析D4-9`，locator anchor 走 probe gate allowlist（同 D4-2）。

**table 1 `customer_current_rows`**（本期动态行）
- anchor `A12`，header_rows 1，row_identity kind=field pointer `/current/rows/*/rowId`，delete_policy tombstone。
- 字段（store 路径相对 `/current/rows/{row_uuid}`）：
  - `customer_current_rows/{row_uuid}/customer_name` — B 列 editable text，pointer `.../name`，source_ref `B13`
  - `customer_current_rows/{row_uuid}/sales_amount` — C 列 editable amount，`.../amount`，`C13`
  - `customer_current_rows/{row_uuid}/amount_ratio` — D 列 **formula** ratio，`.../amountRatio`，`D13`（进 formula_mask）
  - `customer_current_rows/{row_uuid}/sales_quantity` — E 列 editable amount，`.../quantity`，`E13`
  - `customer_current_rows/{row_uuid}/quantity_ratio` — F 列 **formula** ratio，`.../quantityRatio`，`F13`（进 formula_mask）
  - `customer_current_rows/{row_uuid}/prior_rank` — G 列 editable text，`.../priorRank`，`G13`
- 序号 A 列不进契约（模板自增，材料化时按行序写或留模板公式）。
- footer_anchor marker「合计」search_column A，carries_total_formula true（C23/E23 =SUM）。
- formula_mask：`D13:D22`、`F13:F22`（占比列）。

**table 2 `customer_prior_rows`**（上期动态行）——同结构，anchor `A26`，row_identity pointer `/prior/rows/*/rowId`，字段列同上但 source_ref 指向 R27 起（`B27/C27/D27/E27/F27/G27`），formula_mask `D27:D36`、`F27:F36`，footer marker「合计」（C37/E37）。

**table 3 `customer_totals`**（表级标量，无 row_identity / 无 delete_policy）
- anchor `A24`（人读，不作行定位），header_rows 1（占位；该 table 只有静态字段）。
- 字段（row_scoped=False，pointer 不含 `{row_uuid}`）：
  - `customer_totals/current_total_amount` — cell C row_from 24，pointer `/current/totalAmount`，editable amount，source_ref `C24`
  - `customer_totals/current_total_quantity` — cell E row_from 24，pointer `/current/totalQuantity`，editable amount，`E24`
  - `customer_totals/prior_total_amount` — cell C row_from 38，pointer `/prior/totalAmount`，editable amount，`C38`
  - `customer_totals/prior_total_quantity` — cell E row_from 38，pointer `/prior/totalQuantity`，editable amount，`E38`
- 注意：该 table 无 formula 字段，故无需 formula_mask；无 row_identity 故无 delete_policy（`_parse_table` 两条件都不触发）。

> **header_rows 对无行 table 的处理**：`_parse_table` 要求 header_rows 1..3；`customer_totals` 给 1 即可（不影响材料化，因为字段用 static_row 直接定位）。materialize/extract 对该 table 按静态 cell 读写，不按行区间。

### 2.3 store 形态与 rowId 迁移

`D4-9-data` remark：
```json
{ "current": {"rows":[{"rowId","name","amount","quantity","priorRank"}], "totalAmount", "totalQuantity"},
  "prior":   {"rows":[...], "totalAmount", "totalQuantity"} }
```
- 前端 `D4TabCustomerStructure.vue`：`CustomerRow` 加 `rowId: string`；`defaultRows()` / `addRow()` 生成 `crypto.randomUUID()`（或既有 id 工具）；`loadData()` 对无 rowId 的历史行补齐并 `persistData()` 一次（Requirement 3.2）。
- 投影 fail-closed：后端 `iter_store_rows` 复用 `phase5` 的 `store_row_identity`（缺/重复 rowId 抛 `StorePayloadError`）。current/prior 各自 seen 集合（区域内唯一，Requirement 3.4）。

## Components and Interfaces

### 3. 后端 bridge 模块 `phase5_d4_customer_structure.py`

镜像 `phase5_d4_revenue_detail.py` 的结构：

- 冻结常量：`ENTRY_ID="xlsx/gt-d4-customer-structure"`、`ADAPTER_ID="d4.customer_structure"`、`TEMPLATE_RELATIVE_PATH="D/D4 收入底稿.xlsx"`、`TEMPLATE_SHA256`（复算冻结）、`MANAGED_SHEET="重要客户结构分析D4-9"`、`STORE_ITEM_ID="D4-9-data"`、`WP_CODES`（宿主幻影码，同 D4O 或按 manifest 冻结）。
- `MANAGED_FIELD_SPECS_CURRENT / _PRIOR / _TOTALS`：三组字段规格 → `_rows_table_payload` × 2 + `_totals_table_payload`。
- `mapping_digest_payload()` / `compute_mapping_digest()` / `assert_mapping_digest()`：冻结列↔单元格映射，字段数校验（current 6 + prior 6 + totals 4）。
- instrumentation（**已实测裁决，见 §2.1.1**）：D4-9 用两个 `ExcelInstrumentationSpec` 指向**同一 managed_sheet**、不同行段：`GT_D49C_ROWS`(R13-22, uuid_col W) + `GT_D49P_ROWS`(R27-36, uuid_col X)，经 `instrument_workbook_bytes_multi` 注入。totals 无 instrumented table（静态 cell 走固定坐标，不需 row identity 载体）。
  - **前置修复（阻塞）**：先修 `excel_instrumentation._attach_table_part` 支持同 sheet 合并 `<tableParts>`（§2.1.1 路径 A），否则同 sheet 第二区注入产出非法双 `<tableParts>`，第一区 Table 被丢弃。此修复 + 变异守卫（改回新建独立块必红）是 Task 1 的实现内容，不再是"只读核实"。
- store 投影/合并：`build_store_projection`（current rows）+ `build_prior_store_projection` + `build_totals_projection`（静态字段，row_key 为 None）；`build_combined_store_projection` 合并三者；`merge_projection_into_store_rows`（按 table_key 前缀分流回 current/prior/totals）。
- `attach_adapters` / `publish_definitions` / `assert_entry_selectable` / `assert_manifest_capability_enabled`：逐一镜像 D4-2 版本，换 ENTRY_ID/ADAPTER_ID。

## 4. materialize / extract

- 复用 `adapters/excel.py` 的 `build_excel_adapter`（definitions + identity_binding + direction）。多 table 由 contract 的 sheet.tables 驱动，materialize 按每 table 的 anchor/row_identity/formula_mask 写区间，totals 按静态 cell 写。
- extract：按 table_key + row identity 分流；totals 按静态 cell 读回。
- OO→HTML 镜像：`oo_to_html.py` 现有 `adapter_id == "d4.revenue_detail"` 分支调 `_mirror_d4_dual_stores`。为 D4-9 加 `adapter_id == "d4.customer_structure"` 分支 → `_mirror_d4_customer_structure`（把 combined projection 回写单一 store item `D4-9-data` 的 `{current,prior}` 结构，含 totals）。
- 行结构变更（OO 侧增删客户行）走 `excel_row_shift` / `excel_workbook_row_change`；合计区间随 `carries_total_formula` 扩张；占比公式随行复制（模板 D/F 公式按行下移）。

## 5. registry / manifest

- **新建独立 entry**（不复用 gt-d4-operating-revenue）。理由：entry 是「可双向的逻辑单元 + 一份 contract + 一个 adapter」，D4-9 contract 与 D4-2/3 完全不同；宿主组件相同不构成复用 entry 的理由（descriptor facts 观测宿主挂载点，D4-9 sheet 可独立观测）。
- manifest entry：document_type xlsx，independent_entry true，scenario_profile 复用 `xlsx.editable.shared.single.room_service_wired.v1`，wp_match wp_code_patterns（宿主幻影码），adapter_id `d4.customer_structure`，capability 由 reviewed overlay 裁决为 bidirectional，browser_case/contract_test 指向本 spec 证据。
- `attach_adapters` 在 `build_production_registry` 请求期被调用；capability!=bidirectional 或 adapter_id 不符时 fail closed。

## Data Models

### 6. 公式管理（用户自定义 + 血缘 + 保护区）

三套公式存储的边界（已核实）：
- `wp_formula` 表（`WpFormula.target_cell`）：**用户自定义公式落这里**，`wp_template_init_service` 写 xlsx 时用户公式优先级最高（`_mark_user_formula_cell`）。各 D 循环 `resolve_effective` 读它。→ **本 spec 的用户公式主存储**。
- `user_formula_v2.py` / `wp_user_formulas_v2` router：formula-toolbar 的 sidecar v2 record（能力壳 + 血缘展示）。→ 血缘/追溯 UI 消费面。
- `note_formula_service`：附注专用，不涉及。

设计：
1. 用户在 D4-9 对可编辑 cell（如某客户金额改成引用、总额引用 D4-7）设公式 → 落 `wp_formula`（target_cell = `重要客户结构分析D4-9!C24` 等）。
2. 引用校验走 ACNR `full_resolve`（`acnr/formula_validation.py`），无法解析给中文错误（Requirement 5.2）。
3. **用户公式 cell 纳入双向保护区**：materialize 时，除 contract 静态 `formula_mask`（D/F 占比、合计）外，动态并入「该 wp 当前存在用户公式的 cell 集合」→ 这些 cell 在 extract/merge 时按 protected 处理（OO 编辑产生受保护字段冲突，不覆盖用户公式）。实现点：adapter 的 protected cell 集合 = contract formula_mask ∪ 运行时用户公式 cell。需在 materialize/extract 入口注入运行时 protected 集合（Requirement 5.3 / 5.6）。
4. 血缘：占比 D→C 与 `$C$24`、合计→明细区间、总额←D4-7 取数，在 formula v2 provider registry 登记为可追溯 lineage（Requirement 5.4）。总额取数登记为来源且手工覆盖保留（Requirement 5.5）——复用 D4-9 现有「总额可手填/或从 D4-7 D26 取」语义，取数不无条件覆盖手工值。
5. 冲突裁决：同 cell 既是契约 formula 字段（如 D 占比）又被用户设公式 → 用户公式优先并纳入保护；契约声明的 formula 字段本就是 protected，二者一致（Requirement 5.6）。

## 7. 导入导出修复（`_d4_import_export.py`）

现状缺陷：D4-9 表头仅「客户名称/销售金额/销售数量/上期排名」，无本期/上期区分、无总额、无 `_parse_d4_9_row`，走通用 flatten 处理 `{current,prior}` 会错。

修复：
- `_SHEET_HEADERS["D4-9"]`：改为含分区标识的列（或导出两块 sheet/两段），列头 = 序号/客户名称/销售金额/销售金额占比/销售数量/销售数量占比/上期排名 + 期间标识（本期/上期）。
- 导出：按 `D4-9-data.current` / `.prior` 各输出一段，含合计/总额行；占比列导出计算值并标注为公式列（不可回导覆盖）。
- 导入：新增 `_parse_d4_9_row(row, headers)` → 判定行属本期/上期，解析金额/数量/客户名/上期排名 + 识别总额行；组装回 `{current:{rows,totalAmount,totalQuantity}, prior:{...}}`；每行补 rowId（与 Requirement 3 同规则）。
- 列名不匹配 → 中文错误（复用现有 400 分支）。

## 8. 前端接入

- `GtD4OperatingRevenue.vue`：`isD4DetailSheet` 扩展逻辑改为「D4-2/D4-3 走 revenue entry 的 bridge；D4-9 走 customer-structure entry 的 bridge」。因两个 entry 不同，需第二个 `useWorkpaperSyncBridge` 实例（entryId=`xlsx/gt-d4-customer-structure`，sheetKey 单一如 `d49-managed`，flushHtml 读 `D4-9-data` 的 store-projection）。或抽象成按 currentSheet 选 entry/bridge 的小工厂。
- `D4TabCustomerStructure.vue`：行加 rowId + 迁移；**移除**内部 `editorMode` 双模式与 `GtOnlyOfficeSheet` 分支（legacy 单向），只保留结构化视图；在线编辑统一由宿主的 `WorkpaperSyncEditorHost` 承担（Requirement 7.1 / 7.5）。
- 能力未裁决/OO 不健康 → `GtEntrySyncCapabilityNotice` + fail-closed 提示（Requirement 7.4）。

## Error Handling

汇总本设计各节已声明的 fail-closed 规则（无新增语义）：

- capability 未被 reviewed overlay 裁决为 `bidirectional` → 不注册 adapter，前端保持非双向（§5，Req 1.2）。
- contract / instrumentation / template digest 与 `phase5` 现算 payload 漂移 → fail closed（§2，Req 1.4）。
- store 行缺 rowId 或重复 rowId → 投影层抛 `StorePayloadError`，不退回下标、不静默合并（§2 投影，Req 3.3）。
- 用户公式引用无法经 ACNR `full_resolve` 解析 → 返回可操作的中文错误，不静默吞（§6，Req 5.2）。
- 三方合并同字段冲突 → 保留三值与解决轨迹，不静默选边（§4，Req 4.3）。
- 导入列名不匹配 → 返回中文列名错误（§7，Req 6.5）。
- 宿主实测不可达（产不出 descriptor 事实）→ 不注册 adapter（Req 1.5）。

## Testing Strategy

- 后端契约守卫：parse_contract 真跑，断言 3 table / 静态标量 / formula_mask 覆盖 / footer 承载（行为级）。
- roundtrip：store（含 rowId + 4 总额）→ build_combined_store_projection → materialize → extract → merge → store，逐字段对齐；OO 改一行/改一总额 → 提取回正确区域。
- 变异脚本（≥4 锚点）：删 D/F formula_mask、静态标量改 row 域、合并两 table、去 rowId 身份；四态判定。
- 前端 vitest：D4-9 走新 entry 的 host、字面量 entry_id/端点正确、fail-closed；变异改错 entry_id 前缀打红。
- 公式：用户公式落 `wp_formula` + 写 xlsx + 保护区并入 + ACNR 校验中文错误；血缘链可查。
- 导入导出：导出含本期/上期+总额；导入 `{current,prior}` 结构正确 + 补 rowId + 占比列不回导。
- Playwright 真栈（真实 OO）：证据 JSON 记录 request 路径 / content version / application / operation 终态 / artifact digest。

## Correctness Properties

### Property 1: 三 table 结构与静态标量
D4-9 contract 经 parse_contract 后，sheet 恰含 3 张 table（`customer_current_rows`/`customer_prior_rows`/`customer_totals`）；前两张有 row_identity+delete_policy，第三张无 row_identity 且其 4 字段均 row_scoped=False 带 static_row。
**Validates: Requirements 2.1, 2.2, 2.3**

### Property 2: 占比公式受 formula_mask 保护
D/F 占比字段 mode=formula 且列落各自 table 的 formula_mask 内；合计行由 footer_anchor.carries_total_formula=true 承载。改任一为非保护/去 formula_mask 使 parse_contract 失败或 roundtrip 覆盖公式。
**Validates: Requirements 2.4, 4.1**

### Property 3: 行身份稳定且区域隔离
store 每行携带稳定 rowId；缺/重复 rowId 时投影 fail closed；current 与 prior 的 rowId 各自唯一、按 table_key 归属不串区域。
**Validates: Requirements 3.1, 3.3, 3.4**

### Property 4: materialize→extract 逐字段往返
materialize→extract roundtrip：current/prior 客户行与 4 个总额单元格逐字段还原；D/F 占比与合计公式不被投影覆盖。
**Validates: Requirements 4.1, 4.2**

### Property 5: 单一 content version 推进
业务提交只经 ContentMutationService.commit 推进恰好一个 content version/revision；不产生独立 file_version/oo_content_revision 自增。
**Validates: Requirements 4.6, 1.3**

### Property 6: 用户公式 cell 纳入保护集
存在用户公式的 cell 纳入运行时保护集合（contract formula_mask ∪ 用户公式 cell）；OO 侧改该 cell 产生受保护字段冲突而非覆盖。
**Validates: Requirements 5.3, 5.6**

### Property 7: 用户公式落库并写入 xlsx
用户自定义公式落 wp_formula 并在导出/实例化写进 xlsx（用户公式优先）；无法解析引用给中文错误不静默吞。
**Validates: Requirements 5.1, 5.2**

### Property 8: 导入导出结构相符
D4-9 导入导出区分本期/上期两表 + 总额；导入用专用 parser 写回 {current,prior} 嵌套结构并补 rowId；占比列不可回导覆盖公式。
**Validates: Requirements 6.1, 6.2, 6.3, 6.4**

### Property 9: 前端走新 entry 且 legacy 移除
前端 D4-9 在线编辑走新 entry 的 WorkpaperSyncEditorHost；能力未裁决时 fail-closed；legacy GtOnlyOfficeSheet 单向入口被移除/不可达。
**Validates: Requirements 7.1, 7.4, 7.5**

### Property 10: 变异检验四锚点全 RED
变异检验四锚点（删 formula_mask / 静态标量改 row 域 / 合并两 table / 去 rowId）全 RED；改错前端 entry_id 前缀打红。
**Validates: Requirements 8.3, 8.4**


## C0-C4 治理对齐
C0核定同sheet双区的模板/identity，`wp_id`是定义key的业务隔离键；C1接入共享sync并区分durable ack/applied；C2验证formula mask、custom/preset版本、缺失/损坏/stale/blocked及schema白名单（禁eval/外链）；C3验证current/prior/totals表内表间DAG与异常回标真实接收端，公式同步不触发TB/A13；C4只门控D4-9相关contract、roundtrip、权限、Playwright和变异证据。