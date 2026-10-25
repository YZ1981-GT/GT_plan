# D2 受管覆盖扩容 · 实施复盘（2026-09-26）

**spec**：`d2-sync-coverage-via-row-table-engine`　**结果**：18/18（16 代码完成 + 2 真栈待环境）

## 一、交付清单

### 后端（新建 2 provider + 接入父模块 + 契约重生成）
- `backend/app/services/workpaper_sync/phase5_d2_03_bad_debt.py`（D2-3 坏账准备，照 D4-9 单 sheet 双区范式）
- `backend/app/services/workpaper_sync/phase5_d2_01_adjudication.py`（D2-1 审定表，照 D4-1 逐格 + D4-6 固定行范式）
- `pilot_d2_large_json.py` 接入 D2-3 sibling（`_INCLUDE_D203_BAD_DEBT` + `_sheet_payload_d23`）
- `backend/data/workpaper_sync_contracts/d2.receivable_detail.json` 重生成（67 字段 / 9 protected）

### 前端（归一 + 清理 + 接线）
- `useD2Adjudication.ts`：`isFromSumif: boolean` → `source: 'tb'|'manual'` 归一（Q9）；删死降级路径（Task 15）
- `useD2CrossSheet.ts`：触类旁通删同型死降级路径 + 未用 `detailCount`
- 删 `useD2VoucherCheck.ts`（310 行死模块，store 键数据保留）
- `D2TabAdjudication.vue`：2 处 `isFromSumif` → `source === 'tb'`
- `GtD2AccountsReceivable.vue`：`isD2DetailSheet` → `isD2SyncedSheet`（集合派生）+ `syncSheetKey` computed +
  `capability`/`flushHtml` 读 ref + 非受管禁用文案改写（不落 legacy）

### 判据（3 个后端测试文件 + 既有测试改写）
- `test_d2_3_bad_debt_contract.py`（15）Q3/Q4/Q4b
- `test_d2_1_adjudication_mask.py`（8）Q6/Q7
- `test_task41_d2_large_json_pilot.py` 改写 3 处旧断言（D2-2 sheet 粒度零回归 + 反向断言）
- `d2SyncHostWiring.spec.ts`（15）宿主接线守卫仍绿
- 变异 6/6 KILLED（`T17-mutation-check.json`）

### evidence
T01-geometry-probe / T01-mapping-analysis / T03-d23-region-adjudication / T05-perf-baseline /
T10-d24-single-html-adjudication / T17-mutation-check / T99-retrospective（本文）

## 二、三个关键实测修正（spec 前提 vs 现实）

| # | spec 假设 | 实测 | 处置 |
|---|---|---|---|
| 1 | D1 框架层（`RowTableSheetSpec`/`AdjudicationSheetSpec`）已入库，D2 只需实例化 | HEAD **不存在**这些类，D1 spec 仍是未跟踪纯文档 | 用户拍板照 **D4 per-sheet 模块范式**落地（每 sheet 一 `phase5_*.py`），不空等抽象层 |
| 2 | D2-3 是 **3 受管区**（依前端 3 store 键） | 模板只有 **2 物理段**（openpyxl 直读）；aging+customer-type 合并成单一段 | binding **1→3**（非 1→4）；组合区按行内 category 分流回两键 |
| 3 | 接入完成即整册 materialize 200 | D2 父模块**无 sibling 注入编排**（`instrumentation_specs` 复数 + `_align_specs_to_sibling_tables`，D4 有 D2 无） | 声明层+投影+merge+判据离线全绿；真栈往返待 sibling 内核引入（照 D4-1/D4-9 路径） |

## 三、教训（沉淀）

1. **受管区数必须实测模板物理段，不得从前端 store 键数反推**。E2 裁决历经「单区→三区→两区」两次反转，
   三次都因未 openpyxl 直读模板段数。前端分类是 UI 需要，与 Excel 物理承载区不必 1:1。
2. **前置门必须 `git show HEAD:` 判定，不读工作树/spec 文档声称**。D1「框架层已交付」是 spec 假设，
   实测 HEAD 零匹配 —— 若照 spec 字面阻塞停工，整个 spec 无法推进；实测后改走 D4 真实范式反而顺畅。
3. **格级 mask（`cell_in_ranges`）是 D2-1 六金额格 editable 的关键**。变异 M5 证明：换整列判定
   （`column_in_ranges`）B10/C10/D10/B11/C11/D11 全被误判 masked，精确复现 D4-1 踩过的坑。

## 四、诚实边界（未完成项，均属外部依赖）

- **真栈 Playwright 往返**（Task 13 视觉 / Task 17 e2e）：需 OO 服务 + D2 父模块 sibling 注入编排内核。
- **整册 materialize 实测耗时**：同上，需 sibling 编排落地后。
- **D2-1 覆盖 UI S2/S4 视觉**：需真实 SUMIF 数据（D2-adj-* 真库 0 行）。
- **D2-4 已判 single_html**：不接入（可行性核裁决，与 D4-4 同型）。

均为「代码/声明层已就绪，真栈实测待环境」，非功能缺失。后续 sibling 编排内核引入 D2 父模块后可解锁。
