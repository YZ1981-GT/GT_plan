# Requirements Document

## Introduction

本 spec 把「底稿 HTML ↔ OnlyOffice 双向回写」从**一张底稿手写一份 provider**，收敛为
**框架层单一行表引擎 + 每循环独立 entry + 每 sheet 一份薄声明**，并以 **D1 应收票据全覆盖**
作为首个落地循环（D2 为下一个 spec，本 spec 只为它铺路、不接它）。

用户裁决（2026-09-25）：**D1 / D2 / D4 各自独立成套，就像 D4 现在这样**；顺序 **先 D1 再 D2**。

### 现状红基线（全部实测，非估算）

| 事实 | 实测值 | 出处 |
|---|---|---|
| provider 同名函数 | **33 个逐字相同** | D1/D2/D3/D5/D6/D7/D4 七家 grep |
| 同构代码体量 | 约 **5600 行复制 6 份** | D1 902 / D3 847 / D5 781 / D6 849 / D7 844 / D2 1361 |
| 几何常量 | **6 个 100% 同构**（`TEMPLATE_ID`/`FIRST_DATA_ROW`/`LAST_DATA_ROW`/`FOOTER_ROW`/`UUID_COL`/`TABLE_NAME`），D1/D4 多一个可选 `HEADER_ROW` | 七家 grep |
| `FORMULA_MASK` | **7 家形态一致**，全为列向区间 `{COL}{FIRST}:{COL}{LAST}`，3~4 条，无一逐格 | 七家 grep |
| 账龄组装表达式 | D2/D3/D6/D7 **逐字相同**：`tuple(sorted(SCALAR_FIELD_SPECS + _aging_field_specs(), key=lambda row: _col_index(row[1])))` | 四家 grep |
| helper 复制 | `_snake` / `_col_index` **各四份** | 四家 grep |
| `MANAGED_FIELD_SPECS` 元组 | **D5 是 7 元组**（第 7 位 `group_header_cell`），其余六家 6 元组 + 独立 `GROUP_HEADER_CELLS` mapping | 七家 grep |
| `oo_to_html.py` 污染 | **89 处 D4 提及** / **9 分支 `elif adapter_id ==` 链** / **9 处 `hasattr`** | 3508 行文件 |
| 其余通用层污染 | `excel_extract` 8 处 `contract_id` 分支、`merge` 5 处、`adapters/excel` 2 处、`excel_materialize` 1 处 | grep 计数 |
| D1 受管覆盖率 | **1/21**（模板 21 张 sheet，仅 `原值明细表（按客户）D1-3` 受管） | 模板 openpyxl 直读 + 契约 |
| D4 受管覆盖率 | **30 受管 sheet / 36 binding**，18 个 `_INCLUDE_*` 灰度开关全 True | `instrumentation_specs()` |
| 死降级路径 | `useD2Adjudication:182-188` 逐行读 `D2-detail-{i}-{field}`，全仓**零写入方** | grep |

### 🔴 上游 spec：`d-cycle-sheet-bidirectional-expansion`（9/9 全绿，本 spec 必须消费其裁决）

**2026-09-25 复盘发现**：该 spec 已经在做「D 循环 sheet 级双向扩容」，其分波表里
**Wave 2 = D1-2**、**Wave 4 = D2-3**、**Wave 5 = D5-3/D6-3/D7-3**，正是本 spec 与 D2 spec 的
作业面。本 spec **不另起一套**，而是为它提供引擎层并按它的裁决执行。必须继承的四条：

1. **「一 entry 一 adapter」不变**。多受管 sheet 只扩契约 `sheets[]` + 宿主按 sheet 切
   `sheetKey`，**禁止**同 entry 注册第二个 `adapter_id`（除非先改 registry）。
2. **诚实边界：不是每张 sheet 都该双向**。checklist / 程序表 / 附注 / 与网格不对齐的 →
   诚实判 `single_html`，不得强行单元格双向。已有第五种形态
   `paragraph_block_bidirectional`（D4-5 会计政策检查：分组紧凑表 + 经营模式 B11–B16 static）。
3. **可行性核硬门**（该 spec 的 `blocking.8`）：任一新受管 sheet 必须先过
   「**有行身份列** + **无专用同步链冲突**」可行性核，否则判 `single_html` **不得扩 sheets[]**。
4. **D4-4 调整分录汇总已判 `single_html`**，四条依据：①模板无 GTROW/UUID 行身份列
   ②`D4-4-rows` 是 hub store，已被 `useD4Adjustment`（借贷平衡）+ `useD4CrossSheet`（→D4-1）
   + `useAdjustmentCentralSync`→后端 `AdjustmentSyncService`（`source_ref {wp_id}:D4-4-rows`）
   → A13 联动占用，OO 覆盖会争 store 破坏平衡/A13 ③借贷平衡不变式仅 HTML 侧强制，Excel 不校验
   ④动态插入带 + 排版占位列。

🔴 **据依据 4 同判据，本 spec 把 D1-5 调整分录汇总表移出接入批次**（首版误排在批次 2）——
实测 `D1TabAdjustment.vue` **同样接了 `useAdjustmentCentralSync`**（2 处引用）、
`useD1Adjustment` 同样有 `BALANCE_TOLERANCE = 0.005` 的借贷平衡不变式且只在 HTML 侧强制。
D1-5 改为**先做可行性核再裁决**（需求 5.9），默认倾向 `single_html`。

### 已存在、必须复用而非重造的框架件

- `projection_first_publication._align_specs_to_sibling_tables`（:1139）、`_sibling_identity_bindings`
  （:1256）、`_static_region_bindings`（:1293）—— **三者已接受 `provider=` 参数**，天然支持多
  provider，本 spec 不改造它们，只把 provider 侧的硬编码 import 去掉。
- `phase5_transposed_sheet.TransposedSheetSpec` + `transposed_registry`（500 + 32 行）—— 转置表
  泛化的**成功先例**，本 spec 的行表引擎照它的形态与零回归纪律办。
- `merge._protection` + `_mask_spans_data_column`（:663/:761）—— 格级只读判定已改为格级
  （33 判据实跑全绿）。⚠️ **仅在工作树，未提交**：`git show HEAD:…/merge.py` 实测**不含**
  `_mask_spans_data_column`、仍是只比列的旧实现，判据文件 `test_masked_cell_protection_is_cell_level.py`
  当前是 `??` 未跟踪。⇒ 本 spec **依赖该修复先落 commit**（见需求 10），否则批次 6 的 D1-1
  逐格 mask 会在 merge 侧被整列误判只读，四态 UI 重演「已实现但不可达」。
- `excel_row_shift.CompositeRowShift` + `adapters/excel._sheet_cumulative_shift` —— 同 sheet 多受管区
  累积插行归一化**已修复**，D1 多区 sheet 直接受益。

### 本 spec 冻结的裁决（不再讨论）

1. **三层架构**。框架层（全平台唯一实现）/ 循环层（每循环一个 entry 主模块）/ sheet 声明层
   （每张一个薄模块）。**框架层不得出现任何 wp_code / contract_id / adapter_id 分支**（CI 卡点）。
2. **不合并 entry**。一循环一 entry，共享的是**代码**不是**工作簿**。理由：materialize 是整册的
   （`_materialize_within_scope` 逐 binding 跑、`verify_unmanaged_regions` 逐 binding 全跑），
   任一 binding 失败整册 500；`lock_room_oo_apply` 是 per-room 会话级锁横跨 23–99s CPU 段。
3. **`group_header_cell` 统一为内联第 7 位**（D5 式）。理由：独立 mapping 的 key 需字符串派生，
   而该派生在四家有**两种**写法（D2/D3/D7 用 `f"{_snake(json_prefix)}_{seg_key.lower()}"`，
   D6 用 `_snake(flat_key)`），内联后整类"派生规则漂移"消失。
4. **行模型保留 `rowType` + `source` 两维**，二者正交不可合并：`rowType` = 行在表结构里的角色
   （`fixed|dynamic|summary`，`summary` 为 computed 不落库）；`source` = 行数据来源
   （`tb|manual|legacy`）。重叠处 `dynamic≈manual`、`fixed≈legacy`；不重叠处 `summary` 在 source
   无对应、`tb` 在 rowType 无对应。冗余的 `isFixed` 可由 `rowType !== 'dynamic'` 推导。
5. **零回归门用 canonical JSON 的 sha256**，不落全量快照（D2 单表 28431 字段 / 906KB，全量快照会
   让仓库背几十 MB）。digest 不等时才落全量 diff 供排查。
6. **D2 的 `pilot_` 前缀留别名不改名**（`build_pilot_matcher` / `load_pilot_contract` /
   `register_pilot_adapter` / `assert_pilot_entry_selectable`）。它是 Task 41 交付的历史 pilot，
   改名收益低于全仓 grep 调用方的风险。
7. **逐张灰度接入**，照 D4 的 `_INCLUDE_*: Final[bool]` 开关模式。每张新 sheet = 一个 spec 函数
   + 一个开关，可独立开关、独立验证、独立回滚。
8. **本 spec 不做性能优化**。三端点实测耗时（store-projection 37–46s / pending-mutations 24–33s /
   materialize 23–99s）与其根因归 `oo-html-writeback-performance` 与
   `workpaper-sync-materialize-large-table-performance` 两 spec。本 spec 只承诺**不劣化**（需求 8）。
9. **本 spec 不接 D2**，但框架层必须让 D2 零改动通过零回归门（它是分母里最大的那张）。
10. **D1 不接的三类**：`应收票据业务模式分析提示`（纯提示页）、附注披露两张（10 行接口 +
    `rowType`/`kind` 两处不同构，ROI 不成比例）、`底稿目录`（导航非数据）。

## Glossary

| 术语 | 含义 |
|------|------|
| 受管区 / binding | 契约声明的一个 `(sheet, table)` 受管数据区。一张 sheet 可含多个（D1-4 三区 / D2-3 三区 / D4-20 三区） |
| `RowTableSheetSpec` | 行表型受管 sheet 的声明数据类（几何 + 字段 + store 形态），框架层定义、sheet 层实例化 |
| `AdjudicationSheetSpec` | 审定表型声明数据类，以 `sections` + `row_mode` 参数表达各循环审定表的形态差异 |
| `StoreItemSpec` | store item 形态声明（`rows` / `dict` / `fixed_text` / `dedicated`）+ per-item 缺省值 |
| store 键 / store item | `checklist_responses.item_id`，一条 store 载荷的标识（如 `D1-cust-rows`） |
| `bidirectional` | 该 sheet 走真双向回写（HTML ↔ OO 单元格级合并） |
| `single_html` | 诚实裁决：该 sheet 不做单元格双向（无行身份列 / 有专用同步链冲突 / 与网格不对齐） |
| `paragraph_block_bidirectional` | 第五形态：段落块 + 分组紧凑表双向（D4-5 会计政策检查） |
| 可行性核硬门 | 上游 spec `d-cycle-sheet-bidirectional-expansion` 的 `blocking.8`：「有行身份列 + 无专用同步链冲突」两条同时成立才可扩 `sheets[]` |
| hub store | 被多条专用链共同占用的 store 键（如 `D*-entry-rows` 被借贷平衡 + 中央登记 + cross-sheet 联动占用） |
| golden digest | 零回归门的度量：`build_contract_payload` / `build_store_projection` / `instrumentation_spec(s)` 的 canonical JSON sha256 |
| 四态覆盖状态机 | `resolveCellState(stored, snap, derived)` 穷举 S1 纯派生 / S2 人工覆盖 / S3 自动跟随 / S4 覆盖且上游也变 |
| `formula_mask` | 模板公式格区间，materialize 不覆盖、由 OO 重算 |
| 整册 materialize | `_materialize_within_scope` 对该 entry 全部 binding 逐趟跑 + `verify_unmanaged_regions` 逐 binding 全跑，任一失败整册 500 |

## Requirements

### Requirement 1: 框架层行表引擎单一实现

**User Story:** 作为维护者，我希望「行表型受管 sheet」的读写投影只有一份实现，改一次全部底稿受益。

#### Acceptance Criteria

1. WHEN 需要表达一张行表型受管 sheet THEN 系统 SHALL 提供 `RowTableSheetSpec` 冻结数据类，
   其字段集**仅**来自七家 provider 的实测共性：必填几何 `managed_sheet` / `sheet_key` /
   `table_key` / `template_id` / `first_data_row` / `last_data_row` / `footer_row` / `uuid_col` /
   `table_name`；可选 `header_row`；store 面 `store_item_id` / `empty_payload` /
   `row_identity_key` / `store_kind`；字段面 `field_specs`（7 元组）；公式面 `formula_columns` /
   可选 `formula_templates`；分组面 `aging_layout ∈ {nested, flat, None}`。
2. WHEN 引擎生成 `FORMULA_MASK` THEN 它 SHALL 由 `formula_columns` + `first_data_row` +
   `last_data_row` 现算成列向区间，provider **不得**再各自手写 mask 字面量。
3. WHEN 引擎组装 `MANAGED_FIELD_SPECS` THEN 账龄段的展开与列序排序 SHALL 由引擎按
   `aging_layout` 完成，四家 provider 里那条逐字相同的 `tuple(sorted(...))` 表达式 SHALL 消失。
4. WHEN provider 需要 `_snake` / `_col_index` THEN 它们 SHALL 从框架层单一导入，四份复制 SHALL 删除。
5. WHERE 引擎已存在同类框架件（`_align_specs_to_sibling_tables` / `_static_region_bindings` /
   `TransposedSheetSpec`）THE 本需求 SHALL 复用它们，**不得**新建平行实现。
6. WHEN 引擎被调用 THEN 它 SHALL 不感知任何具体 wp_code —— 判据为 CI 卡点（需求 7.1）。

### Requirement 2: provider 声明化

**User Story:** 作为维护者，我希望接一张新底稿只写声明，不再复制 900 行样板。

#### Acceptance Criteria

1. WHEN 一个循环层 provider 收敛完成 THEN 它 SHALL 只声明 entry 级事实（`ENTRY_ID` /
   `TEMPLATE_RELATIVE_PATH` / 受管 sheet 清单 / store item 清单 / 灰度开关），**不含**任何
   投影、合并、契约装配算法。
2. WHEN 统计收敛后行数 THEN D1/D3/D5/D6/D7 的循环层 provider SHALL 各 ≤150 行（D2 因 39 列 ×
   三套账龄的声明体量放宽至 ≤300 行；D4 因 30 受管 sheet 另计，见 2.5）。
3. WHEN 33 个同名函数被收敛 THEN 每个函数 SHALL 在框架层恰有一处实现；provider 侧若需保留
   同名入口，SHALL 是薄转发（≤3 行）而非副本。
4. WHEN `_attach_sibling_bindings` 被收敛 THEN 它 SHALL 接受 `provider` 参数，
   provider 模块内的硬编码 `import ... as _provider` SHALL 删除。
5. WHERE D4 已有 26 个 per-sheet 模块 THE 本 spec **不重构它们**，只要求它们能被新引擎的
   spec 形态表达（迁移归后续 spec），且 D4 整体通过零回归门。

### Requirement 3: 回写分派注册表化

**User Story:** 作为维护者，我希望接一张新底稿不需要修改通用回写层。

#### Acceptance Criteria

1. WHEN OO→HTML 回写需要按 entry 找 store 合并规则 THEN `oo_to_html._mirror_store_backed_if_needed`
   SHALL 走注册表查表（`dict` O(1)），那条 9 分支 `elif adapter_id ==` 链 SHALL 删除。
2. WHEN 一个 store item 的形态需要被分派 THEN 系统 SHALL 用 `StoreItemSpec(kind, item_id, default)`
   四形态声明（`rows` / `dict` / `fixed_text` / `dedicated`），`hasattr(bridge, "STORE_ITEM_ID_D4xx_DICT")`
   式试探 SHALL 全部删除（现 9 处）。
3. WHEN 出方向（`store_projection_response`）与回方向（`oo_to_html`）各自取 store item 清单 THEN
   两者 SHALL 取自同一 `all_store_item_ids()` 口径，且判据 SHALL 断言两方向集合**逐元素相等**。
4. WHEN 注册表查表未命中 THEN 系统 SHALL 抛显式 `SyncDomainError`（含 adapter_id 与可选项清单），
   **不得**静默跳过 —— 静默跳过正是 D4-35 恒空 / D4-13 正文写不进 OO 两个已修 bug 的根因形态。
5. WHERE 注册表规模增长 THE 查表 SHALL 保持 O(1) dict，**不得**退化成 `for spec in REGISTRY:
   if spec.matches()` 线性试探（那是 `field_by_stable_key` O(n²) 的同款错误）。

### Requirement 4: 零回归门 —— 已接 8 张逐字节等价

**User Story:** 作为质量控制复核合伙人，我要求重构不改变任何已交付底稿的行为。

#### Acceptance Criteria

1. WHEN 引擎抽取前 THEN 系统 SHALL 为全部 8 个已交付 contract（`b60.hour_budget` /
   `d1.notes_receivable_detail` / `d2.receivable_detail` / `d3.prepaid_receipts_detail` /
   `d4.revenue_detail` / `d5.receivables_financing_detail` / `d6.contract_assets_detail` /
   `d7.contract_liabilities_detail`）取 golden digest：`build_contract_payload()`、
   `build_store_projection(...)`、`instrumentation_spec(s)()` 三者的 canonical JSON sha256。
2. WHEN 引擎抽取后 THEN 上述 24 个 digest SHALL 逐个不变；任一不等时判据 SHALL 落全量 diff。
3. WHEN materialize 路径被触及 THEN 至少 D1（已接）与 D4（30 受管 sheet）SHALL 各跑一次真
   materialize + extract 往返，断言 `managed_field_count` 与产物字节 digest 不变。
4. WHEN 前端共享件被触及 THEN `dynamicAdjRowsBackcompatBaseline.spec.ts` 等既有零回归快照
   SHALL 零变化。
5. WHERE 某已接 contract 在真库无数据（实测 D3/D5/D6 的 store item 全库 0 行）THE 零回归门
   SHALL 以合成 payload 驱动，**不得**因无数据而跳过该 contract。

### Requirement 5: D1 受管覆盖从 1 张扩到全部可表达 sheet

**User Story:** 作为审计助理，我希望 D1 的明细类底稿都能切「在线编辑」并把改动写回结构化视图，
而不是只有 D1-3 一张真双向、其余切过去改了就丢。

#### Acceptance Criteria

1. WHEN 列出 D1 接入清单 THEN 它 SHALL 从模板 `D/D1 应收票据.xlsx` 的 **21 张实测 sheet**
   推出，按下表分批（`*` 为本 spec 范围外）：

   | 批次 | sheet | 形态 | 存储键（**按值 grep 实测**） | 受管区 | 累计 |
   |---|---|---|---|---|---|
   | 已接 | `原值明细表（按客户）D1-3` | 动态行 15 列 | `D1-cust-rows` | 1 | 1 |
   | **1** | `原值明细表（按类别）D1-2` | 固定 2 + 动态行 | `D1-cat-rows` | 1 | 2 |
   | **1** | `坏账准备明细表D1-4` | **三区** | `D1-bd-individual-rows` / `-portfolio-rows` / `-notetype-rows` | **3** | 5 |
   | **2** | `应收票据贴现、票据已背书未到期明细表D1-8` | 双区 | `D1-endorse-discount-rows` / `-transfer-rows` | 2 | 7 |
   | **2** | `坏账准备转回、核销检查表D1-16` | 双区 | `D1-writeoff-reversal-rows` / `-writeoff-rows` | 2 | **9** |
   | ~~2~~ | ~~`调整分录汇总表D1-5`~~ | 动态行 | `D1-entry-rows` | **移出** | — |
   | **3** | `应收票据贴息检查表D1-9` | 动态行 | `D1-interest-rows` | 1 | 10 |
   | **3** | `应收票据监盘D1-10` | 动态行 + 3 标量 | `D1-inventory-rows` + recon 标量 | 1 | 11 |
   | **3** | `关联方关系及交易检查表D1-11` | 动态行 | `D1-rp-rows` | 1 | 12 |
   | **3** | `应收票据质押检查表D1-12` | 动态行 | `D1-pledge-rows` | 1 | 13 |
   | **3** | `应收票据坏账准备测试表D1-15` | **双区** + 2 派生列（乘法）| `D1-ecl-individual-rows` / `D1-ecl-portfolio-rows` | **2** | 15 |
   | **4** | `应收票据备查簿核对D1-7` | 嵌套 dict | `D1-memo-rows` = `{bankRows,commercialRows}` | 1 | 16 |
   | **4** | `应收票据坏账准备会计政策检查D1-14` | 纯标量 10 项 | `D1-policy-*` | 0（无行区）| 16 |
   | **4** | `应收票据检查表D1-13` | **双区** + 15 标量 | `D1-sampling-vouching-rows` / `D1-sampling-specific-samples` | **2** | 18 |
   | **5** | `应收票据业务模式分析D1-6` | 行表 + **真二维矩阵** | `D1-bm-basis-rows` + `D1-bm-qa-matrix` | 1 + 矩阵待评估 | 19~20 |
   | **6** | `审定表D1-1` | **per-cell 锚点 3 区** | `D1-adj-{section}-{slug}-{field}` | 3 | 22~23 |
   | `*` | `应收票据审计程序表D1A` | 步骤清单 | 程序 item | — | — |
   | `*` | `附注披露信息（上市公司）` / `（国企）` | 10 行接口多区块 | 披露键 | — | — |
   | `*` | `底稿目录` / `应收票据业务模式分析提示` | 导航 / 提示页 | 无 | — | — |

   🔴 **本表的「存储键」与「受管区」两列是 2026-09-25 复盘按值 grep（`'D1-[A-Za-z0-9_-]+'`）
   重测后补正的**。首版把 D1-15 写成占位「ECL rows」（实测是**双键双区**
   `D1-ecl-individual-rows`/`D1-ecl-portfolio-rows`，dict 字面量形式 `portfolioRows: '…'`），
   D1-13 只写「2 行表」未列键名。⇒ **受管区总数首版从未算过**，tasks 里的 binding 增长数是按
   「一 sheet 一区」估的、全部偏低。教训与 D2-3 同源：**store 键 grep 必须按值匹配**，
   `^const \w+_KEY\s*=\s*'` 这类按声明匹配的模式会漏掉 dict 字面量里的键。

2. WHEN 每张 sheet 接入 THEN 它 SHALL 有独立的 `phase5_d1_*.py` 声明模块 + 独立
   `_INCLUDE_*` 灰度开关，可单独关闭而不影响其他张。
3. WHEN D1 的 `instrumentation_spec()`（单数）不足以表达多受管 sheet THEN provider SHALL 新增
   `instrumentation_specs()`（复数），且 `attach` 路径 SHALL 走已有共享内核
   `_align_specs_to_sibling_tables`（**不新写对齐规则**）。
4. WHERE 一张 sheet 含同 sheet 多受管区（D1-4 三区 / D1-8 双区 / D1-16 双区）THE 它 SHALL 复用
   已修复的兄弟 Table ref 位移 + `_GT_SYNC` footer 重冻结 + verify 累积归一化三层能力，
   且 `test_sibling_table_ref_row_shift.py` 的参数化判据（清单从 `instrumentation_specs()`
   动态算）SHALL 自动覆盖到它们。
5. WHEN 每接完一张 THEN 整册 materialize SHALL 真跑一次并记录耗时；判据 SHALL 断言受管
   binding 数按预期增长且 `verify_unmanaged_regions` 全绿。
6. WHERE 一张 sheet 的形态无法用 `RowTableSheetSpec` 或 `TransposedSheetSpec` 表达
   （如 D1-6 的 `cells: QACell[][]` 真二维）THE 该张 SHALL 显式登记为「引擎表达不了」
   并给出原因，**不得**为它在框架层开特例分支。
7. WHEN 一张接入的 sheet 的 store 键**已有其他 sheet 在回写它** THEN 本 spec SHALL 为该键定序，
   使同一时刻只有一条权威写路径。
   🔴 实测唯一命中：`useD1WriteoffCheck.syncReversalToD14` **回写** `D1-bd-portfolio-rows` 的
   「按组合计提」父行（注释：「D1-4 的期末未审随之重算，并沿 D1-4 → D1-1 → 披露 → 附注
   逐级联动」）⇒ D1-4 接 sync 后该键有**三个写入方**（HTML 保存 / OO 回写 / 跨 sheet 回写）。
   裁决方向：OO 模式期间禁用跨 sheet 回写入口并给中文原因，或把它改走 sync 的
   pending-mutations 通道；**不得**两条路同时直写 store（会与 materialize 产物分叉，
   下次 extract 反读到非预期值 ⇒ roundtrip 门红或静默覆盖 OO 改动）。
8. WHEN 一张接入的 sheet 的 store 键有**下游 computed 消费方** THEN 零回归判据 SHALL 覆盖它们，
   不得只验该 sheet 自身读回等值。实测 D1-4 三键的下游：`useD1EclCalc.d1_4DataAvailable`(:475)
   与 `parseD1_4Rows`(:497/:499) / `useD1Adjudication` 坏账区 / `D1TabIndex.vue:49` 的
   `progressKeys`。
9. WHEN 任一 sheet 进入接入批次前 THEN 它 SHALL 先过上游 spec
   `d-cycle-sheet-bidirectional-expansion` 的**可行性核硬门**（其 `blocking.8`）：
   「**有行身份列**（GTROW / UUID 列或稳定 key）」+「**无专用同步链冲突**」两条同时成立才可扩
   `sheets[]`；任一不成立 SHALL 判 `single_html` 或 `paragraph_block_bidirectional` 并留证，
   **不得**强行单元格双向。
10. WHERE `调整分录汇总表D1-5` 与已判 `single_html` 的 D4-4 同型 THE 它 SHALL 先做可行性核
    再裁决，默认倾向 `single_html`。已实证的三条同型事实：①`D1TabAdjustment.vue` 接了
    `useAdjustmentCentralSync`（2 处引用）②`useD1Adjustment` 有 `BALANCE_TOLERANCE = 0.005`
    借贷平衡不变式且**仅 HTML 侧强制**、Excel 不校验 ③`D1-entry-rows` 是 hub store。
    待核第四条：模板 `调整分录汇总表D1-5` 有无行身份列。
    🔴 **本条是复盘修正**：首版把 D1-5 排在批次 2 直接接入，与上游 spec 对 D4-4 的裁决冲突。

### Requirement 6: D1-1 审定表迁移（批次 6，存量数据不可丢）

**User Story:** 作为审计助理，我已在 D1-1 录入的调整数在改造后必须一个都不丢。

#### Acceptance Criteria

1. WHEN D1-1 从 per-cell 锚点迁向行数组 THEN 迁移 SHALL 保留既有 `D1-adj-{section}-{slug}-{field}`
   键的**读路径**，读回等值判据 SHALL 以真库存量形态的 payload 驱动（不是合成理想数据）。
2. WHEN 迁移完成 THEN 旧键 SHALL 保持可读（双读单写），物理删除归后续 spec —— 与 D4 的
   per-field 双写同一纪律（回滚只需改读侧优先级，不必回填数据）。
3. WHEN D1-1 的行来源是 cross-sheet（原值 ← D1-2 / 坏账 ← D1-4 按票据种类小计）THEN 迁移后
   SHALL 引入与 D4-1 同一套逐格四态覆盖状态机（`resolveCellState`），**不得**保留现状
   「cross-sheet 有值就无条件盖掉手工锚点」的静默丢数据行为。
4. WHEN 四态状态机接入 D1-1 THEN 它 SHALL 复用 `shared/dynamicAdjudicationRows` 的
   `resolveCellState` / `displayValueForCellState`，**不得**在 D1 侧另写一套。
5. WHERE D1-15 现有 `autoPulled: boolean` 标记（从 D1-4 取数）THE 它 SHALL 被归一到
   `source` 维度；现状「上游变了、手工调过的值会怎样」是未定义行为，迁移后 SHALL 有定义。

### Requirement 7: CI 门禁

**User Story:** 作为维护者，我要求"框架层不被特化污染"和"新增底稿不漏接线"由机器守，不靠人记。

#### Acceptance Criteria

1. WHEN CI 运行 THEN 卡点 SHALL AST 扫框架层模块，断言其中**零**处 wp_code / contract_id /
   adapter_id 字面量分支；新增一处必须红。允许白名单（注册表模块本身、错误消息文案）
   且白名单 SHALL 显式登记。
2. WHEN 一个新 `RowTableSheetSpec` 或 `StoreItemSpec` 被声明但未接入注册表 THEN CI SHALL 红并
   精确报漏项 —— 照 `check_store_item_ids_fully_wired.py` 已验证的范式（46 item 收敛 + 变异反证）。
3. WHEN CI 运行 THEN 卡点 SHALL 断言出/回两方向的 store item 集合逐元素相等（需求 3.3）。
4. WHERE 卡点自身可能永绿 THE 每个卡点 SHALL 附带**变异反证**测试（故意去掉一项 ⇒ 卡点必红）。
5. WHEN 卡点接入 THEN 它 SHALL 进 `governance-checks.yml`，且**不**依赖 `tests/workpaper_sync/`
   的既存失败分母。

### Requirement 8: 性能不劣化

**User Story:** 作为多人平台，我不接受重构让本已很慢的三个端点更慢。

#### Acceptance Criteria

1. WHEN 引擎抽取完成 THEN `store-projection` / `pending-mutations` / `materialize` 三端点在同一
   substrate 上的耗时 SHALL 不高于抽取前的 110%（同机同数据，脚本现测，不手抄常量）。
2. WHEN 注册表查表被调用 THEN 它 SHALL 是 O(1) dict 命中（需求 3.5），判据 SHALL 以规模递增的
   合成注册表断言查表耗时不随规模上升。
3. WHEN D1 受管 sheet 从 1 张增至批次 3 完成后的张数 THEN 每批次 SHALL 记录整册 materialize
   实测耗时；IF 耗时超过软上限 THEN 停止继续接入并转性能 spec，**不得**带着退化继续铺量。
4. WHERE 已有缓存（`BASELINE_EXTRACT_CACHE` 键 `{contract_id}:{artifact_sha256}`）THE 重构
   SHALL 不改变其命中语义；判据 SHALL 断言同一 substrate 二次请求仍命中。

### Requirement 9: 变异检验与证据

**User Story:** 作为质控，我要求每条判据都被证明"不是永绿的装饰"。

#### Acceptance Criteria

1. WHEN 每条核心判据落地 THEN SHALL 配一次变异（故意改坏被测行为）并记录打红条数；
   未能打红的判据 SHALL 重写而非保留。
2. WHEN 零回归门落地 THEN 变异 SHALL 至少覆盖：引擎漏生成一条 mask 区间 / 账龄段展开顺序错乱 /
   注册表漏一个 store item / sibling binding 对齐规则改动。
3. WHEN 证据登记 THEN SHALL 落 `docs/operations/evidence/`，且数字 SHALL 由脚本现测得出。
4. WHERE 判据只覆盖 adapter 方法而生产路径在其后还有 `verify_unmanaged_regions` THE 本 spec
   SHALL 显式包含一条**穿过 verify** 的判据 —— 这是 D4 spec「判据绿而生产 500」的成因，不重犯。
5. WHEN 任一 tasks 项标记完成 THEN SHALL 有实跑数字或产物路径作证据；外部依赖未实测的
   SHALL 如实标 `[ ]*` 并写明「代码已改但未实测」。

### Requirement 10: 前置依赖必须先入库

**User Story:** 作为维护者，我不希望本 spec 建立在未提交的工作树状态上 —— 那样一次 checkout
就会让"已修复"的前提消失，而 spec 里的判据会以无法归因的方式红。

#### Acceptance Criteria

1. WHEN 本 spec 开工前 THEN `merge._protection` 的格级判定（`cell_in_ranges` +
   `_mask_spans_data_column`）与其判据 `test_masked_cell_protection_is_cell_level.py`
   SHALL 已在 HEAD 中；实测现状为**工作树已改、HEAD 未含**（判据文件 `??` 未跟踪）。
2. WHEN 检查该前置 THEN 判定 SHALL 用 `git show HEAD:<path>` 而非工作树内容 ——
   本 spec 调研期间正因读工作树而一度把它登记成"已修复"，属同款错误。
3. IF 该前置未入库 THEN 批次 6（D1-1 逐格 mask）SHALL 阻塞；批次 1~5 的明细类底稿
   （mask 全为列向区间、行范围恰等于数据区）**不受影响**可照常推进。
4. WHEN 其余在工作树但未提交的 D4 相关产物（`e2e/d4-1-override-roundtrip.spec.ts` /
   `e2e/d4-35-d4-13-oo-visibility.spec.ts` / `errorEnvelopeNormalisation.spec.ts` 等）被本 spec
   的零回归门依赖 THEN 它们 SHALL 同样先入库或显式声明不依赖。
5. WHERE 本 spec 的任一"已修复/已存在"前提来自工作树 THE 它 SHALL 在 requirements 中标注
   入库状态，不得以"实测已修"笼统表述。

### Requirement 11: 消费引擎已有的形态谱系（**不止行表**）

**User Story:** 作为维护者，我不希望把一张纯静态 cell 的 sheet 硬塞进行表引擎，也不希望为它
在框架层另造一套 —— 引擎已经有 `static_region` 路径，D4 已用它交付三张。

#### Acceptance Criteria

1. WHEN 判定一张 sheet 的形态 THEN 系统 SHALL 在引擎**已有的 binding 二分**内选择，
   **不得**新造第三种（`excel_extract.BindingKind`，:606）：
   * `excel_table`（动态）—— `table_name`（Excel Table displayName）+ `uuid_column`（隐藏 UUID 列）
     必填、`defined_name` 必空。承载动态行区域（D4-1/2/9/34/36）。
   * `static_region`（静态）—— `defined_name`（workbook-scope definedName）必填、
     `table_name`/`uuid_column` **必空**。承载「只有绝对坐标 static cell、无动态行、无 UUID 列」
     的纯静态受管区。D4 已用它交付 **D4-33**（12 月 × 3 业务类型 = 72 static cell）/
     **D4-8** / **D4-13**（A6/A16 各单 cell）。
2. WHEN 一张 sheet 走 `static_region` THEN 它 SHALL 复用引擎静态路径而**不经**动态路径的任何门：
   `_plan_static_writes` 按绝对坐标直写，**无** `row_shift` / footer 两门 / minted UUID /
   workbook 传播（`excel_materialize.py:1657`）；注入时只写 definedName、**不建** Excel Table、
   **不注**隐藏 UUID 列；binding 由 `_static_region_bindings(provider=…)` 从 provider 的
   `static_sheets` 声明**自动生成**，不需手动接线 `sibling_bindings`。
3. WHEN 声明行身份 THEN 系统 SHALL 在**三形态**内选择并显式声明 `row_identity_key`：
   * **UUID 动态行** —— `row_identity_key='rowId'`，行可增删（D1-3 / D2-2 / D4-2）
   * **稳定 key 固定行** —— `row_identity_key='key'`，行**不增删**但仍是 `excel_table` binding
     且**仍注入 UUID 列**（D4-6 范式：12 个固定指标，key 取前端 `DEFAULT_INDICATORS` 稳定键；
     模板无空列 ⇒ 注入列用 I）
   * **无行身份** —— 走 `static_region`，按绝对坐标（D4-13 / D4-33）
4. 🔴 WHEN 区分 `StoreKind` 与 `BindingKind` THEN 二者 SHALL 被当作**正交两维**：
   `StoreKind`（`rows`/`dict`/`fixed_text`/`dedicated`）描述 **store 载荷形状**，
   `BindingKind`（`excel_table`/`static_region`）描述 **Excel 侧几何**。
   一个 `fixed_text` store item 既可能落在 `static_region`（D4-13 单 cell 锚点），也可能寄生在
   姊妹动态表的 `excel_table` binding 上（D4-5 分组紧凑表）。
   **本 spec 首版把二者混为一谈**（把 `fixed_text` 当成「无受管区」），据此把 D1-14 的 10 个标量
   标为「0 受管区」，实测它们应走 `static_region` 各占一个受管区。
5. WHEN 一张受管 sheet 内**部分 item 无法受管** THEN 系统 SHALL 支持 **HTML-only item 子集**
   并显式登记原因 —— 受管 sheet **≠** 该 sheet 全部 item 都受管。先例
   `phase5_d4_policy_check_sheet.HTML_ONLY_ITEM_IDS_D45` 三项
   （`D4-5-credit-policy` / `-audit-note` / `-audit-conclusion`）因「footer 下 `static_row`
   与插行 fail-closed 冲突」保持 HTML-only。
6. WHERE 本 spec 的批次表把若干 sheet 标成「纯标量 / 标量伴生」THE 它们 SHALL 按 11.1 重新判形态：
   D1-14（10 标量）/ D1-13 的 15 标量 / D1-10 的 3 个 recon 标量 —— 候选 `static_region`
   或 HTML-only，由 Task 1 逐项实测（有无可注入 definedName 锚点、是否落在 footer 之下）。
7. WHERE D1-2 是「2 固定行 + 动态行」混合、D1-6 的 `D1-bm-basis-rows` 是 3 固定行
   THE 它们 SHALL 显式声明 `row_identity_key` 取哪一形态 —— 固定行部分用**稳定 key**
   （`fixed-bank` / `fixed-commercial` / `fixed-high-bank` 等已是稳定键），动态行部分用
   `rowId`；两者共存时 SHALL 确认引擎支持同一 table 内混合身份，若不支持则拆区或统一为 `rowId`。
8. WHEN 前端宿主接线 THEN 它 SHALL 覆盖**两套 gating**而非一套 —— D4 实测有
   `isD4DetailSheet`（主 detail 链）与 `isD4DedicatedSyncSheet`（专用同步 sheet 链）两套，
   **漏登记后者会导致工具条叠加冲突**（D4-35 / D4-13 均踩过）。本 spec 的 D1 宿主若引入专用
   同步 sheet（如审定表 D1-1 独立于 detail 链），SHALL 同时登记两套。
