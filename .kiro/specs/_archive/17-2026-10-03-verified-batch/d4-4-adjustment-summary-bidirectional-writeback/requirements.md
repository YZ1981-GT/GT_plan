# D4-4 营业收入调整分录汇总 —— HTML ↔ OnlyOffice 双向回写

## Introduction

把 **D4-4 调整分录汇总**（sheet `营业收入调整分录汇总D4-4`）从 `single_html` 接入平台统一双向同步链路，
成为共享 entry `xlsx/gt-d4-operating-revenue` 下的第 **36** 张受管 sheet（契约 `d4.revenue_detail.json`
现声明 35 张 / 775 受管字段）。

**为什么现在做**：D4-4 是 D4 全组 36 张里**唯一**仍为 `⬜ single_html` 的表（D4-13 已落地 `d413-managed`，
清册的 N/A 裁决已作废）。其原裁决的两条理由经 2026-09-28 实测**均已不成立**：

| 原裁决理由 | 复核结论 |
|---|---|
| 模板无行身份 UUID 列载体 | **不成立**。模板 `A1:J23`，**K~O 五列全空**，紧邻 `max_column`(J) 右侧即 K；且前端 `D4AdjustmentRow` **已有 `rowId`**、`removeRow(rowId)` 按身份删。对比 D4-19 是「模板无空列 → **注入列 P**」才落地的，D4-4 连注入都不用 |
| hub store 被 A13/借贷平衡语义占用 | **不成立**。`debitTotal`/`creditTotal`/`balanceDiff`/`isBalanced` 全是 `computed` 不落库；`pushToA13`/`publishAdjustment` 只读 rows 后 `eventBus.emit`；`useAdjustmentCentralSync`（218 行）**零写路径**。落库的 `D4-4-rows` 就是干净的 10 字段行数组 |

它反而是剩余表里**几何最简**的一张：单区动态行表、模板 10 列 ↔ 前端 10 字段 **1:1 双射**、
**数据区公式格 0**、数据区 R6~R20 **完全空白**、数据区无合并单元格、非转置、非静态矩阵。
参照实现 `phase5_d4_discount_sheet.py`（D4-19，单区动态行表，251 行）可近乎同构复用。

**已完成的前置修复（不在本 spec 范围，但本 spec 依赖其结论）**：
- D4-4 的 legacy OnlyOffice 活口已由 `d4Constants.ts` 的 `D4_LEGACY_OO_BLOCKED_SHEETS` 封堵
  （详见 `docs/operations/d4-bidirectional-writeback-inventory.md` 2026-09-28 第六轮 §②）。
  🔴 **本 spec 落地后必须把 `'D4-4'` 从该名单移除**，否则新做的双向入口会被自己的禁入名单挡掉。
- D4-4 导入导出漏 F/J 两列已补齐（`_SHEET_HEADERS["D4-4"]` 8→10 列 + `_export_d4_4_row`）。

## Requirements

### Requirement 1 — 几何与身份冻结（openpyxl 实测，禁凭推断）

**User Story:** 作为实施者，我需要 D4-4 的受管几何被逐项冻结，以免 provider 写错坐标导致静默错列。

#### Acceptance Criteria

1. WHEN 读 `backend/wp_templates/D/D4 收入底稿.xlsx` 的 sheet `营业收入调整分录汇总D4-4`
   THEN 几何 SHALL 与下表逐项一致，任一不符即停止实施并重新裁决：

   | 项 | 冻结值 |
   |---|---|
   | 范围 | `A1:J23`（`max_row=23`, `max_column=10`） |
   | 表头行 | R5（A~J 十列全非空） |
   | 首数据行 | **R6** |
   | 末数据行 | **R20** |
   | footer 行 | **R21** |
   | footer marker | `提示：`（A21 完整文本 63 字，`提示：本底稿适用于调整分录较多、较复杂的项目，且仅列示与本报表项目相关的审计调整。项目组可根据项目实际情况选择是否使用该底稿。`） |
   | 受管末列 | **J** |
   | UUID 载体列 | **K**（K~O 五列全空，取紧邻 J 右侧首个空列） |
   | 数据区公式格 | **0** |
   | 数据区非空格 | **0**（R6~R20 全空白） |
   | 合并单元格 | 仅 `A1:J1` / `A2:J2`（标题行），**数据区无合并** |

2. 表头 A~J 十列 SHALL 逐字为：`调整事项说明` / `类别（报表调整/账项调整/其他）` / `报表项目` /
   `科目名称` / `附注项目` / `……` / `借方调整金额` / `贷方调整金额` / `索引` / `备注`。
3. 行身份键 SHALL 为 **`rowId`**（注意：参照实现 D4-19 用的是 `id`，**不可照抄**）。
4. 🔴 行身份**格式有两种并存**，UUID 载体列与校验 SHALL 同时接纳：
   前端 `useD4Adjustment.generateRowId()` 产出 `d4a-{base36时间}-{7位随机}`（如 `d4a-ms2p8tkl-juz5kck`）；
   导入侧 `_parse_d4_4_row` 产出标准 `uuid4()`。**不得**假设单一格式或加格式正则校验。
5. IF 任何计数类数值与本节冻结值不符 THEN SHALL 以现算为准并在 tasks 中登记更正，不得沿用本文档旧值。

### Requirement 2 — 受管字段与 formula_mask

**User Story:** 作为审计人员，我在 OO 侧改的每一列都应回到结构化视图，且派生量不被 OO 覆盖。

#### Acceptance Criteria

1. 受管字段 SHALL 为 **10 个**，与前端 `D4AdjustmentRow` 的 10 个业务字段一一对应
   （`rowId` 是身份不是字段，不计入）：

   | # | 前端字段 | 列 | value_type | 表头 |
   |---|---|---|---|---|
   | 1 | `description` | A | text | 调整事项说明 |
   | 2 | `category` | B | text | 类别（报表调整/账项调整/其他） |
   | 3 | `reportItem` | C | text | 报表项目 |
   | 4 | `accountName` | D | text | 科目名称 |
   | 5 | `noteItem` | E | text | 附注项目 |
   | 6 | `placeholder` | F | text | `……` |
   | 7 | `debitAmount` | G | amount | 借方调整金额 |
   | 8 | `creditAmount` | H | amount | 贷方调整金额 |
   | 9 | `indexRef` | I | text | 索引 |
   | 10 | `remark` | J | text | 备注 |

2. `formula_mask` SHALL 为**空**。判据：数据区公式格现算为 0，且借贷合计/平衡差额是前端 `computed`
   **不落 cell**（与 D4-19 的 E 列折扣比例不同 —— 那一列在模板里有派生位）。
3. WHEN 契约 schema 校验 CS-13 运行 THEN SHALL 通过：本表无 `mode="formula"` 字段，故「formula 字段
   必须落在 formula_mask 内」的反向约束空分母成立。
4. 受管字段的 `stable_field_key` SHALL 全部小写（`{table_key}/{identity}/{snake_field}`）。
   🔴 D4-8 曾因直接用驼峰前端字段名生成 180 个含大写的非法 key 而打挂整份契约 parse，本表
   `placeholder`/`remark` 等已是全小写，但 `reportItem`/`accountName`/`noteItem`/`debitAmount`/
   `creditAmount`/`indexRef` **必须经 `_snake()` 转换**。

5. 🔴 **HTML 侧必须能看见/编辑全部 10 个受管字段**（2026-09-28 Playwright 实测发现的三方不一致）：

   | 层 | `placeholder`（模板 F「……」） | `remark`（模板 J「备注」） |
   |---|---|---|
   | 模板列 | ✓ 存在 | ✓ 存在 |
   | `D4AdjustmentRow` 类型 | ✓ 有字段 | ✓ 有字段 |
   | `safeParseRows` 解析 | ✓ 解析 | ✓ 解析 |
   | **UI 表格列** | 🔴 **无** | 🔴 **无** |
   | 导入导出 | ✓（本批已补 F/J 两列） | ✓ |

   实测判据：`D4TabAdjustment.vue` 的 `el-table` 恰 8 个业务列（源码注释编号 1~8），DOM 取 `thead th`
   得 `[摘要, 分类, 报表项目, 会计科目, 附注项目, 借方, 贷方, 索引号]`。
   ⚠️ **同名陷阱**：该文件里的 `placeholder="摘要"` 等是 **el-input 的占位文本属性**，与
   `D4AdjustmentRow.placeholder` **字段**同名但完全无关，grep 时不得混为一谈。

   IF 把 10 列全纳入受管而 UI 仍只有 8 列 THEN 用户在 OO 侧改 F/J 列 → 回写进 store → 切回结构化
   视图**看不见** ⇒ 表现为「改动丢了」（实为存了但不可见），这是比不回写更难排查的缺陷。
   ⇒ 本 spec SHALL 在前端表格补这 2 列，使「模板 / 类型 / 解析 / UI / 导入导出」五层一致。
   （备选方案「这 2 列不纳入受管」SHALL 被拒：模板有列 ⇒ OO 侧可编辑 ⇒ 不纳入则 materialize 会
   用 store 旧值覆盖用户在 OO 的输入，静默丢数据。）

### Requirement 3 — 契约与发布链

#### Acceptance Criteria

1. 契约 `backend/data/workpaper_sync_contracts/d4.revenue_detail.json` SHALL 从 35 张增至 **36 张**
   （新增 `d44-managed`），受管字段总数从 775 增至 **785**。
2. WHEN 运行 `python backend/scripts/gen/generate_phase5_d4_contract.py --apply`
   THEN `assert_contract_file_matches_source` SHALL 返回 OK（无 DRIFT）。
3. 发布链 SHALL 按序跑通且各步无异常：`generate --apply` → provision → `rematerialize --apply`；
   `rematerialize --check` 最终 SHALL 返回 `already_on_desired_bundle`。
4. materialize SHALL NOT 抛 `MaterializeSoftTimeoutError`（soft_limit 120s 不得提高）。
   基线：Wave 5 优化后真库 CPU 段 69.33s，加 D4-33 后 82.53s，加 D4-8 后仍未超时。
   🔴 引用性能数字前须确认其所属优化版本 —— 清册里「138s 逼近上限」是 Wave 5 **修复前**的旧值。
5. SHALL NOT 抛 `RoundtripEquivalenceError` / `FooterAnchorDriftError` /
   `adapter_unmanaged_region_drift`。
6. IF 发布链需 live PG 而环境不可用 THEN SHALL 标 `UNVERIFIABLE` 并写明环境门，**不得假绿**。

### Requirement 4 — OO→HTML 消费侧接线（第四维判据，缺一即静默不回写）

**User Story:** 作为实施者，我需要消费侧四点逐一接上，避免「契约已落盘 + 前端已接桥」却永不回写。

#### Acceptance Criteria

1. 🔴 本节是 2026-09-21 实证的**第四维判据**：三维（owner spec + 后端契约 + 前端接桥）全绿仍不足以
   保证真双向 —— D4-8 曾三维全绿却 oo→html 永不回写，D4-9/10/11/15~20/30/31/32 共 13 个 item 曾因
   返回裸 payload 而在 `oo_to_html:2842` 硬解包 4-tuple 处 `ValueError` 打挂**整个 entry** 回写。
2. `phase5_d4_revenue_detail.py` 的 `STORE_ITEM_IDS` SHALL 登记 `D4-4-rows`
   （该常量与 `_normalize_merge_updates` 均定义于**生产者侧** `phase5_d4_revenue_detail.py`，
   **不在** `oo_to_html.py` —— 勿找错文件）。
3. `merge_projection_into_all_d4_stores` 对 `D4-4-rows` 的返回值 SHALL 经 `_normalize_merge_updates`
   归一为 **4-tuple** `(payload, applied, visited, touched)`。
4. combined projection / `values.update` 循环 / `row_keys` 三处 SHALL 一并接上。
   🔴 D4-8 曾只完成 5/8 处，且 `d48_projs` 默认值若用 `{}` 而非 `[]` 会**静默把 180 cell 全投 0**。
5. `oo_to_html.py` 的 `_mirror_d4_dual_stores` SHALL 能取到 D4-4 的 base（list 形态，非 dict-store，
   故走 rows 循环而非 `_dict_store_items`）。
6. 守卫 `test_d4_mirror_shape_invariants.py` SHALL 覆盖 D4-4，且 SHALL 有**变异反证**：
   monkeypatch 掉归一 → 复现非 4-tuple 与 ValueError。

### Requirement 5 — 前端接桥与禁入名单摘除

#### Acceptance Criteria

1. `D4TabAdjustment.vue` SHALL 经**共享 composable `useD4SyncMode`** 接桥（`useD4SyncMode(options)`，
   返回 `{ entryId, syncBridge, descriptor, ooHealthy, checkOoHealth, editorMode, modeOptions,
   switchMode, busy, feedback, syncStateTag, syncHostRef }`），**不得**直接调 `useWorkpaperSyncBridge`
   —— 2026-09-21 治本改造后 entryId/capability/健康门禁/switchMode 已内聚进该 composable。
2. SHALL 挂 `WorkpaperSyncEditorHost`，且 SHALL 包在带**确定高度**的 `.oo-container` 里
   （父级高度 auto 会把编辑区压成一条，已有用户实测截图）。
3. 宿主 `GtD4OperatingRevenue.vue` 的 `isD4DedicatedSyncSheet` SHALL 加入 `'D4-4'`。
4. 🔴 `d4Constants.ts` 的 `D4_LEGACY_OO_BLOCKED_SHEETS` SHALL 移除 `'D4-4'`（保留 `'D4-5'`），
   且 `d4LegacyOoBlocked.spec.ts` 的相关用例 SHALL 同步更新（其「推导 legacy 命中集」用例会因此变化）。
   IF 漏做此步 THEN 新接的双向入口会被禁入名单挡掉、`renderMode` 恒 `'html'`、切换器恒 disabled。
5. 切「在线编辑」SHALL 走统一路径：`/sync/**` → `store-projection` 200 → `materialize` 200 →
   callbackUrl 含 `room_id`/`generation`/`doc_key`/`route_credential_id` → `wp-sync-host` 挂载；
   SHALL NOT 出现 `/d2-sync/*` legacy 旁路。
6. 健康门禁 SHALL 在点击时 `await checkOoHealth()` 再判（不得只读初始 `false` 就静默 return
   —— 第四轮 ③ 的 `ooHealthy` 竞态）。

7. `D4TabAdjustment.vue` 的 `el-table` SHALL 补 `placeholder`（列标题「补充说明」，与导入导出列头
   一致）与 `remark`（列标题「备注」）两列，位置对齐模板 A~J 列序：**补充说明在「附注项目」与
   「借方」之间**、**备注在「索引号」之后**。两列 SHALL 复用既有 `updateCell(row.rowId, field, v)`
   写入路径（不新增保存通路），且 SHALL 受 `isReadonly` 门控。
   验收：DOM 取 `thead th` 得 10 个业务列，顺序为
   `[摘要, 分类, 报表项目, 会计科目, 附注项目, 补充说明, 借方, 贷方, 索引号, 备注]`。

### Requirement 6 — 既有能力不回归

#### Acceptance Criteria

1. 调整分录 CRUD、借贷平衡指示（`isBalanced`/`balanceDiff`）、`pushToA13`、`publishAdjustment`、
   与调整分录中央模块联动（`useAdjustmentCentralSync`）SHALL 全部保持现有行为。
2. 导入导出 SHALL 保持 10 列往返等值（守卫 `test_d4_4_import_export_roundtrip.py` 12 passed 不得转红）。
3. 子表经 window event 保存的既有机制 SHALL 不被破坏：`flushSave()` 仍 dispatch `d4:save-items`，
   宿主监听器仍在（concern §1 记录的结构性脆弱点）。
4. WHEN 行数超过模板 15 个数据行（R6~R20）THEN 插行 SHALL 在 footer marker R21 **之前**完成，
   提示文本不得被覆盖或错位。

### Requirement 7 — 验收分层与 seed 前置

#### Acceptance Criteria

1. **L1**（进在线编辑走统一路径）SHALL 全绿，证据落
   `docs/operations/evidence/d4-bidirectional-acceptance/D4-4.json`，`console_errors`/`http_errors` 为 0。
   ⚠️ SHALL 用 `--workers=1` 串行跑（OnlyOffice 8080 单实例并发 contention 会造成假失败）。
2. **L2**（真 OO canvas 往返：写格 → forcesave `cs_error=0` → callback durable → application
   `applied` → HTML store 镜像可见）SHALL 尝试；`4=no_changes` 不算通过。
3. 🔴 **L2 有 seed 前置**：真库 `D4-4-rows` 现有 3 行**全空白**（`description`/`accountName` 全空、
   `debitAmount`/`creditAmount` 全 0、`category` 是默认值「账项调整」—— 用户点了新增未填）。
   直接跑 L2 会落进 fleet status 的 `empty_payload_skip`（现 19 张）。故 SHALL 先 seed 带借贷金额的
   业务行再跑 L2。
4. IF 真 OO 往返因 env 门（需 start-dev.bat 全栈 + OO 容器）不可跑 THEN SHALL 标 `UNVERIFIABLE`
   并写明，**不得**用 L1 通过冒充 L2。

### Requirement 8 — 文档与登记

#### Acceptance Criteria

1. `docs/operations/d4-bidirectional-writeback-inventory.md` SHALL 追加本轮记录（append-only），
   逐张清册的 D4-4 行 SHALL 由 `⬜ single_html` 改记为 `✅`，并更新统计段
   （`⬜` 由 1 张归 0、契约 35→36 张、字段 775→785）。
2. `.omm/d-cycle-sales/d4-operating-revenue/concern.md` 的 §6 SHALL 更新
   （D4-4 不再是「唯一未接双向的有载荷表」），§7「N/A 结论有保鲜期」SHALL 补记 D4-4 为第四例。
3. `.kiro/specs/INDEX.md` SHALL 登记本 spec（🔴 Active 数一律现扫 `.kiro/specs/*/tasks.md`，
   禁按增量推算）。
4. 归档 spec `_archive/14-d4-bidirectional-writeback/d4-adjustment-and-analysis-gap-closure`
   SHALL NOT 回填修改（append-only 审计轨迹）；其 D4-4 裁决的推翻记录已登记在本 spec 与 inventory。
