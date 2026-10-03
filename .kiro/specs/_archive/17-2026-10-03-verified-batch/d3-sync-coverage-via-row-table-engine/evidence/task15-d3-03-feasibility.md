# Task 15 — D3-3 可行性核 + 裁决（不改生产代码）

**spec**：`d3-sync-coverage-via-row-table-engine`　**实测**：2026-09-26　**裁决**：`single_html`（与 D4-4 一致）

> 🔴 本任务是「可行性核」不是「接入」——**未改任何生产代码**（Property 11 诚实边界红线）。只新建两份证据文件 + 一个守卫判据测试。范式照 `d-cycle-sheet-bidirectional-expansion/evidence/T08-d44-single-html-adjudication.json` 与 `backend/tests/workpaper_sync/test_d1_05_single_html_adjudication.py`。

---

## 一、openpyxl 实测结论（模板真相）

模板 `backend/wp_templates/D/D3 预收账款.xlsx`，sha256 `33165493…`（与 `phase5_d3_prepaid_receipts.TEMPLATE_SHA256` 一致，属冻结哨兵）。

真实 tab 名（openpyxl 直读，非旧脚本推演名）：**`调整分录汇总表D3-3`**。

| 维度 | 实测值 |
|------|--------|
| 几何 | `A1:J23`，23 行 × 10 列 |
| 标题区 | A1「致同会计师事务所」（合并 A1:J1）· A2「预收账款调整分录汇总表」（合并 A2:J2） |
| 页眉/索引区 | 行 3-4：6 处 `=底稿目录!Ax` 引用公式 + I3/J3「索引：/D3-3」+ I4「页次：」 |
| 表头行 | **行 5**（A-J = 10 字段键） |
| 数据区 | 行 **6-20 空模板带**（零内容、零公式） |
| 使用提示 | 行 21（合并 A21:J21）「本底稿适用于调整分录较多、较复杂的项目……项目组可根据项目实际情况选择是否使用该底稿」 |
| 行 22-23 | 空 |

**表头 A→J**：调整事项说明 / 类别（报表调整/账项调整/其他）/ 报表项目 / 科目名称 / 附注项目 / 「……」/ 借方调整金额 / 贷方调整金额 / 索引 / 备注 —— 与 D4-4/D1-5 逐字相同（同一套模板范式）。

### 1.1 有无稳定行身份列 → **无**（复核确认 Task 1 结论）

- 全表 A1:J23 扫 `GTROW`/`_GT`/`UUID`/`rowId` 字样 = **NONE**。
- 候选空列 K/L/M/N 在数据行 6-22 = **全空**（无可复用的现成身份列）。
- 前端 store `D3-aje-rows` 的行 id（`row-<uuid>`）由 `useD3Adjustment.generateRowId()` 在**浏览器侧**生成，模板侧无对应锚列。
- ⇒ 单元格双向回写按行 UUID 定位，缺锚即无法稳定回写。

### 1.2 借贷平衡不变式在哪层强制 → **HTML + 后端双层，Excel 模板零校验**

| 层 | 位置 | 强制方式 |
|----|------|---------|
| HTML computed | `useD3Adjustment.ts` `debitTotal`/`creditTotal`/`isBalanced`/`balanceDiff`（+ 纯函数 `checkBalance`，精确相等 `debitTotal === creditTotal`） | 现算 |
| HTML 门 | `D3TabAdjustment.vue:15` 「同步到集中登记」按钮 `:disabled="isReadonly \|\| !isBalanced \|\| rows.length === 0"` | 不平衡则禁用同步 |
| 后端门 | `AdjustmentSyncService.sync_from_workpaper` **第 1 步** `if total_debit != total_credit: raise AdjustmentSyncError("UNBALANCED", …)` | 服务端硬校验 |
| Excel 模板 | 数据区 6-20 零公式零内容 | **无任何校验** |

> 🔴 与 D4-4 相比 D3-3 是**更强**的 single_html 案例：平衡在 HTML 门（`!isBalanced`）**和**后端 sync 门（`UNBALANCED`）双重强制，而 OO 单元格回写会**同时绕过这两道门**——OO 侧编辑可轻易产生不平衡分录且不经 sync 校验，还可能与已中央登记的记录去同步。

---

## 二、裁决：`single_html`

四条依据（照 T08 范式）：

1. **无行身份列**：全表无 UUID/GTROW 锚，OO 单元格双向回写无法按行稳定定位（§1.1）。
2. **已有专用集中登记同步链，OO 回写会争同一 store**：`D3-aje-rows` 由 `useD3Adjustment` 拥有（双列借贷 + `checkBalance`），喂 `useD3CrossSheet.adjustmentRows`（AJE/RJE 联动）与 `useAdjustmentCentralSync`→后端 `AdjustmentSyncService`（`source_ref={wp_id}:D3-aje-rows`，幂等 by source_ref、approved 锁定）。OO 覆盖会绕过借贷平衡门并与中央登记去同步。
3. **借贷平衡双层强制、Excel 零校验**：见 §1.2；OO 侧可产生不平衡分录且不经门。
4. **空白待填表格、无固定数据行样例**：数据区 6-20 空模板带、行 21 使用提示（可选是否使用）、列 F「……」为排版占位。是中央登记 hub 表，不是网格明细。

**结论**：D3-3 走 `single_html`（单向 HTML，不做单元格双向），与已判 `single_html` 的 D4-4、D1-5 同侧。

---

## 三、Property 11 守卫判据（核阶段不改代码 + 变异改 provider 必红）

判据文件：`backend/tests/workpaper_sync/test_d3_03_single_html_adjudication.py`。

分三组（照 `test_d1_05_single_html_adjudication.py` 范式 + 本任务特有的「受管契约缺席」守卫）：

- **裁决未腐烂**：裁决 JSON `decision == "single_html"`、四条依据齐全；表头与 D4-4 裁决逐字相同；两裁决同判 single_html。
- **四条依据仍成立**（防证据腐烂）：①模板无 UUID/GTROW 痕迹（+ D3-2 有非空 `uuid_col` 作反面对照，证明判据能区分真受管 sheet）②`D3TabAdjustment.vue` 恰 1 条 central-sync import + 1 处调用、`useD3Adjustment.ts` 拥有 `D3-aje-rows`、`D3TabIndex.vue` 读同一键 ③HTML 侧 `isBalanced` computed + 宿主 `!isBalanced` 门、后端 `sync_from_workpaper` 有 `UNBALANCED` 校验、Excel 数据区 6-20 零内容零公式。
- **🔴 受管契约缺席守卫（Property 11 核心）**：断言 `D3-aje-rows` **不在** `phase5_d3_expansion.all_store_item_ids()`、`调整分录汇总表D3-3` **不在** `all_managed_sheet_names()`、无 `phase5_d3_03` 模块 / `SPEC_D303`。
- **🔴 变异必红**：`TestMutationRegisteringD303WouldGoRed` 模拟「给 D3-3 加了个 provider / 把 `D3-aje-rows` 塞进受管契约」——对变异后的（含 D3-3 的）store item 集合逐条跑缺席断言，`pytest.raises(AssertionError)` 证明守卫会打红。若谁想偷偷把 D3-3 接进行表引擎，缺席守卫必红拦住。

运行结果：见 §五。

---

## 四、一致性核对（`D3-aje-rows` 逐字一致，无读无写 bug）

| 角色 | 位置 | 键 |
|------|------|-----|
| 写入方 | `useD3Adjustment.ts:48` `ITEM_ID_ROWS` → `persistRows` 写 `checklist_responses.remark` | `D3-aje-rows` |
| 读取方 | `useD3CrossSheet.ts:319` `adjustmentRows` computed | `D3-aje-rows` |
| 读取方 | `D3TabIndex.vue:67` `case 'D3-3'` `hasJsonRows(m, 'D3-aje-rows')` | `D3-aje-rows` |
| 中央同步 | `D3TabAdjustment.vue:190` `itemId: 'D3-aje-rows'` → `useAdjustmentCentralSync` | `D3-aje-rows` |
| 后端 IE | `_d3_import_export.py:155` `_SHEET_ITEM_ID['D3-3']` | `D3-aje-rows` |

**结论**：键逐字一致、有写入方——**不存在** D6/D7 那种「读无写入方聚合键、目录完成度恒显示未填」的 bug（Task 1 evidence 已核，本任务复核确认）。

---

## 五、六张调整分录汇总表统一裁决 → 建议另立 spec

六张同型：**D1-5 / D2-4 / D3-3 / D4-4（已判 single_html）/ D5-3 / D6-4 / D7-3**。共性：宿主均接 `useAdjustmentCentralSync`（经后端 `AdjustmentSyncService` 中央登记）；模板均为十列表头空白待填、无行身份列、借贷平衡 HTML+后端双门。

**建议**：六张统一裁决 `single_html` 另立 spec 处理；本任务只产 **D3-3** 的核与证，不越界处理其它五张（design F4 已记此意）。

---

## 六、生产代码零改动声明

本任务**未改任何生产代码**：未接行表引擎、未加 provider、未改 composable/vue/后端 service、未碰引擎/框架层/模板/别 lane 在途文件（`phase5_d3_prepaid_receipts.py`/`phase5_d3_expansion.py`/`d3.prepaid_receipts_detail.json`）。仅新建：

- `.kiro/specs/d3-sync-coverage-via-row-table-engine/evidence/task15-d3-03-single-html.json`（JSON 证据，照 T08 schema）
- `.kiro/specs/d3-sync-coverage-via-row-table-engine/evidence/task15-d3-03-feasibility.md`（本文件）
- `backend/tests/workpaper_sync/test_d3_03_single_html_adjudication.py`（守卫判据）

一次性 openpyxl 探针用完即删。
