# D4-1 设计

## Overview

D4-1「营业收入审定表」升级为 `xlsx/gt-d4-operating-revenue` entry / `d4.revenue_detail` adapter 的又一张受管 sheet（`d41-managed`），与 D4-2/D4-3/D4-5/D4-15/D4-16 同册同 adapter。HTML、OnlyOffice、checklist snapshot 都是内容表征，统一经 `ContentMutationService` 提交；`useWorkpaperSyncBridge` 只作适配层。

**DEC0：D4-1 走「同 sheet 双区动态行」模式（行 UUID + 插行），参照 D4-9，不是 static-cell。** 前端 `useD4Adjudication` 已用平台动态行共享件 `shared/dynamicAdjudicationRows`（store 键 `D4-1-rows` + per-field），主营/其他两段各为可扩行。目标：先打通双区动态行的双向通道（HTML↔OO 往返 + e2e 验收），公式治理与导入导出按 wave 递进。

## Architecture

统一双向链路（同 D4-2/D4-9）：

```
HTML 编辑 → useWorkpaperSyncBridge.switchToOnlyOffice
  → flushHtml(readStoreProjection: D4-1-rows 主营+其他两区动态行)
  → createPendingMutation → materialize(sheetKey=d41-managed)
      · adapter 按两区 row_identity 写行；超模板预留行经 excel_row_shift 插行
      · E/I/小计/合计/差异(formula_mask) 保留 Excel 公式不写
  → ContentMutationService.commit → OO 打开定位 营业收入审定表D4-1

OO 编辑落盘 → durable callback → OoToHtmlCoordinator
  → adapter.extract(按两区 row_identity 反读; formula_mask 不反读)
  → 三方合并 → merge_projection_into_all_d4_stores(回 D4-1-rows, 按 sectionKey 分流)
  → ContentMutationService.commit → HTML 刷新
```

确认审定（人工 TB 发布，与双向切换正交）：`useD4Adjudication.publishAdjudicated` → 二次确认 → 比较 D4-1 快照审定合计 vs TB 核对（`D4-1-adj-tb-6001/6051`，差异 >0.005 再确认）→ `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`（governance P0-3d 显式发布门）。切模式不触发。

### 决策

- **DEC0 同 sheet 双区动态行**：主营段(锚 R8 起) + 其他段(锚 R14 起) 各一张 row_identity table；两区不同 UUID 列（同 D4-9 W/X 思路）；E/I/12/18/19/21 入 formula_mask。
- **DEC1 依赖 D4-9 前置修复（阻塞）**：同 sheet 双区注入依赖 `excel_instrumentation._attach_table_part` 合并 `<tableParts>`（D4-9 design §2.1.1 路径 A）。D4-9 owner spec 当前 0/15；该修复未落地则 D4-1 Task 标 BLOCKED，不绕过。
- **DEC2 provider 归属**：新建 `phase5_d4_adjudication_sheet.py`（镜像 `phase5_d4_customer_structure.py` 的多 table 结构），由 `phase5_d4_revenue_detail.py` 以 6 点集成（只加不动）。
- **DEC3 store 模型（现状对齐）**：`D4-1-rows`（`rowsItemId(D4_ADJ_ROWS_SPEC)`）+ per-field `D4-1-{rowId}-{field}`（currentUnadjusted/currentAje/currentRje/priorUnadjusted/priorAje/priorRje）；每行 rowKey/label/accountCode/sectionKey/source。旧键 `D4-1-adj-rows` 仅迁移兼容。
- **DEC4 取数（现状对齐 R3.4）**：未审数**不从四表库填**（TB 6001/6051 无产品维度）；明细行由 D4-2/D4-3 SUMIF 派生 + 人工；仅 `D4-1-adj-tb-6001/6051` 标量走 Tier A 公式。
- **DEC5 TB 发布分离**：复用既有 `publishAdjudicated` 发布门（P0-3d 已接），本 spec 不改，只保证与双向切换正交。

## Components and Interfaces

### 后端
- 新建 `backend/app/services/workpaper_sync/phase5_d4_adjudication_sheet.py`（镜像 `phase5_d4_customer_structure.py`）：
  - 常量 `MANAGED_SHEET_D41='营业收入审定表D4-1'` / `TEMPLATE_ID_D41='D41'` / `SHEET_KEY_D41='d41-managed'` / `STORE_ITEM_ID_D41='D4-1-rows'` / 主营 `ROWS_TABLE_KEY_MAIN` + 其他 `ROWS_TABLE_KEY_OTHER`
  - `MANAGED_FIELD_SPECS`（label + 6 金额 × 两区，列 A/B/C/D/F/G/H；row_from=row_identity）
  - `FORMULA_MASK`（E/I 数据行 + 12/18/19/21 的 B–I）
  - `sheet_payload_d41()`（两 row table，各自 anchor/uuid_col/footer_anchor）+ `instrumentation_spec_d41`（两 `ExcelInstrumentationSpec` 同 managed_sheet 不同行段/UUID 列）
  - `build_store_projection_d41`（按 sectionKey 分流两区）/ `merge_projection_into_d41_rows`
  - `mapping_digest`（冻结 + evidence JSON）
- 改 `phase5_d4_revenue_detail.py`：6 点集成，**只加不动**。
- 改 `d_cycle_extraction/presets.py`：D4 seed 锚点 `D4-1-adj-rows` → 与前端新键 `D4-1-rows` 对齐（消除前后端键不一致）。
- 发布链脚本复用：`generate_phase5_d4_contract.py --apply`、`fix_task76_provision_projection_definitions.py --apply`、`d43_rematerialize_dual_sheet.py --apply`。

### 前端
- `GtD4OperatingRevenue.vue`：`isD4DedicatedSyncSheet` 加 `'D4-1'`；D4-1 分支接 `useWorkpaperSyncBridge`（sheetKey=`d41-managed`）+ `WorkpaperSyncEditorHost`，flushHtml 读 `D4-1-rows` store-projection。
- `D4TabAdjudication.vue` / `useD4Adjudication`：保留审定 UI + 动态行 + `publishAdjudicated` 发布门（DEC5 不动），新增在线编辑切换器（参照 D4-15 `D4TabCompleteness.vue`）。

### 守卫
- 后端 `test_d4_1_adjudication_store_roundtrip.py`：两区 build_store_projection→merge 往返逐格一致、两区 rowId 各自唯一不串、formula_mask 不回写、缺码拒绝。
- 前端 `d4AdjudicationSyncHostWiring.spec.ts`：D4-1 接桥 + 宿主登记 dedicated；`d4AdjudicationPublishGate.spec.ts` 不回归。
- e2e `d4-bidirectional-acceptance.spec.ts` 加 D4-1。

## Data Models

### D4-1-rows store（动态行数组）
```jsonc
{
  "rowKey": "<uuid>",           // 稳定行 id（禁下标兜底）
  "label": "批发收入",           // A 列，可编辑
  "accountCode": "6001",         // scope 确认，缺码拒绝
  "sectionKey": "main-revenue",  // main-revenue | other-revenue（分流两区）
  "source": "manual|prefill",
  "currentUnadjusted": 0, "currentAje": 0, "currentRje": 0,  // B/C/D
  "priorUnadjusted": 0, "priorAje": 0, "priorRje": 0          // F/G/H
}
```
per-field 键：`D4-1-{rowId}-{field}`（6 类）。派生（currentAudited/priorAudited/小计/合计）不入受管字段。

### 契约结构（单 sheet 2 row table + formula_mask）
| table | sectionKey | 锚 | 受管列 | UUID 列 |
|-------|-----------|----|-------|--------|
| adjudication_main_rows | main-revenue | 主营段表头 | A/B/C/D/F/G/H | 空列 A |
| adjudication_other_rows | other-revenue | 其他段表头 | A/B/C/D/F/G/H | 空列 B（≠区1）|

formula_mask（不回写）：E/I 数据行 + 行 12/18/19/21 的 B–I。TB 核对 `D4-1-adj-tb-6001/6051` 只读回显不入受管。

## Error Handling

- 模板字节变更（sha256≠哨兵）：`EntrySelectionError` fail-closed。
- 同 sheet 双区注入前置未修（`_attach_table_part` 未合并）：第二区 Table 被丢弃 → 视为假双向，Task BLOCKED，不得交付。
- 缺 accountCode/scope：拒绝该行或转人工，中文原因，不归主营、不猜测。
- 写入失败/行身份缺失或重复/公式不支持：fail-closed，保留原内容、标记 failed/blocked，不 markSynced、不 null→0。
- OO 请求被去重层 abort（CanceledError）：桥回退 html_idle，`useWpDetailGuard` 已对 canceled 短路。

## Testing Strategy

- 后端守卫 `test_d4_1_adjudication_store_roundtrip.py`：两区 `build_store_projection`→`merge` 往返逐格一致、rowId 各区唯一不串、formula_mask 不回写、缺码拒绝、超预留行插行位移正确。
- 契约 digest 断言 + 变异脚本（改错区 anchor/UUID 列 / formula_mask 可回写 / 合并两区 table / 去 rowId / 绕开 ContentMutationService / 发布挂切换 → 均 RED）。
- 前端 `d4AdjudicationSyncHostWiring.spec.ts`：D4-1 接桥 + 宿主 dedicated 登记；`d4AdjudicationPublishGate.spec.ts` 不回归。
- e2e `d4-bidirectional-acceptance.spec.ts` 加 D4-1（进在线编辑→store-projection/materialize 200→callback 四项→OO 挂载）；L2 roundtrip 写行→forcesave cs_error=0→回读。

## Correctness Properties

### Property 1: 统一提交与冲突保留
**Validates: Requirements 1.2, 1.4**
所有写操作共享 descriptor、版本和 ContentMutationService，普通投影不覆盖公式，冲突显式保留。

### Property 2: 同定义与四表取数
**Validates: Requirements 2.2, 3.2**
D4-1 数据读取经四表 scope/叶子聚合；HTML 与 OO 结果来自同一 effective definition。

### Property 3: TB 发布分离
**Validates: Requirements 2.4, 3.2**
TB 发布只能由人工确认触发且读取 D4-1 快照；模式切换不发布；公式定义版本/hash 可追溯。

### Property 4: 双区往返一致
**Validates: Requirements 3.3, 4.1, 4.2**
主营/其他两区动态行 round-trip 逐格一致，两区 rowId 各自唯一不串区，导入缺码拒绝，派生列由定义重算。

### Property 5: 双区几何与 fail-closed
**Validates: Requirements 1.1, 2.3**
provider 两区 anchor/UUID 列/受管列/formula_mask 与核定几何一致；同 sheet 双区注入产出合法单 `<tableParts>`（两区 Table 均被识别）；模板字节变更 fail-closed。
