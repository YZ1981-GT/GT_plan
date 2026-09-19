# Implementation Plan

## Overview

把 D4-1 营业收入审定表从 legacy 单向 `GtOnlyOfficeSheet` 升级为走统一 `useWorkpaperSyncBridge` + `ContentMutationService` 的真双向 sheet（`d41-managed`，同 entry `xlsx/gt-d4-operating-revenue` / adapter `d4.revenue_detail`）。

**DEC0：同 sheet 双区动态行**（主营段 R8 起 / 其他段 R14 起，各可扩行），参照 D4-9（`phase5_d4_customer_structure.py` 的多 table 结构）。前端已用动态行模型（`useD4Adjudication` + `D4-1-rows` + per-field），本 spec 补齐后端 provider + 契约 + 发布链 + 前端接桥 + 双向。

🔴 **前置阻塞（DEC1）**：同 sheet 双区注入依赖 `excel_instrumentation._attach_table_part` 合并 `<tableParts>`（D4-9 design §2.1.1 路径 A）。D4-9 owner spec 当前 0/15 未做——Task 3 起若该修复未落地则标 `[-]` BLOCKED，唯一解除条件 = `_attach_table_part` 合并修复入库 + 变异守卫（改回新建独立块必红）。

**不重建已通链路**：前端 `D4-1-rows` 新模型、`publishAdjudicated` 发布门（governance P0-3d）保持不动。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "name": "几何核定与契约守卫（判据先行）", "tasks": ["1", "2"], "parallel": true },
    { "wave": 2, "name": "前置：同 sheet 双区 instrumentation 修复（依赖 D4-9）", "tasks": ["3"], "depends_on": [1] },
    { "wave": 3, "name": "后端 provider + 契约集成 + 发布链", "tasks": ["4", "5", "6"], "depends_on": [2, 3] },
    { "wave": 4, "name": "前端接桥 + 宿主登记 + 键对齐", "tasks": ["7", "8"], "depends_on": [4] },
    { "wave": 5, "name": "守卫、变异、e2e 与收口", "tasks": ["9", "10", "11", "12"], "depends_on": [5, 6, 7] }
  ],
  "notes": [
    "双向回写走平台既有 useWorkpaperSyncBridge + ContentMutationService，不新建自同步 composable。",
    "TB 发布分离：复用既有 publishAdjudicated 发布门（P0-3d），双向切换不触发发布。",
    "Task 3 依赖 D4-9 的 _attach_table_part 修复；未落地则 Task 3/4 后段 BLOCKED，如实标 [-]。",
    "未审数不从四表库填（presets.py R3.4），只 D4-1-adj-tb-6001/6051 标量走 Tier A 公式。"
  ]
}
```

## Tasks

- [ ] 1. 几何核定与 mapping_digest 冻结
  - openpyxl 直读权威模板 `D/D4 收入底稿.xlsx` sheet `营业收入审定表D4-1`，冻结两区 anchor（主营 R8 起 / 其他 R14 起）、受管列 A/B/C/D/F/G/H、formula_mask（E/I + 12/18/19/21 的 B–I）、两区 UUID 空列；产出 `evidence/d41-geometry.json` + mapping_digest。
  - 判据：几何与前端 `useD4Adjudication` 六金额字段逐项对齐；digest 冻结。
  - _Requirements: 1.1, 2.3_

- [ ] 2. 契约结构守卫（parse_contract 真跑）
  - 新增 `backend/tests/workpaper_sync/test_d4_1_adjudication_contract.py`：`build_contract_payload()` 加入 d41-managed 后，`parse_contract` 得 sheet 含 2 张 row table（main/other），各有 row_identity + delete_policy，E/I/小计/合计/差异列落 formula_mask；两区 UUID 列不同。
  - 反向自检：把两区合并成一 table / 去 formula_mask → parse 失败或守卫红。
  - _Requirements: 1.1, 2.3, 5.4_

- [ ] 3. 【前置/依赖 D4-9】同 sheet 双区 instrumentation 修复核实
  - 核实 `excel_instrumentation._attach_table_part` 是否已支持同 sheet 合并 `<tableParts count>`（D4-9 design §2.1.1 路径 A）。已修：直接用；未修：本 spec 不擅自改双向内核共享文件（主控 §5.3 共享锁），标 `[-]` BLOCKED 并记录唯一解除条件（D4-9 Task 1 落地）。
  - 判据：`instrument_workbook_bytes_multi` 对 D4-1 两区同 managed_sheet 注入后，openpyxl 同时认出两区 Table（非畸形双 `<tableParts>`）。
  - _Requirements: 1.1, 5.4_

- [ ] 4. 后端 provider `phase5_d4_adjudication_sheet.py`（镜像 D4-9 多 table）
  - 常量 + `MANAGED_FIELD_SPECS`（两区 × label+6 金额）+ `FORMULA_MASK` + `sheet_payload_d41`（2 row table，各 anchor/uuid_col/footer）+ `instrumentation_spec_d41`（2 spec 同 sheet 不同行段/UUID）+ `build_store_projection_d41`（按 sectionKey 分流）+ `merge_projection_into_d41_rows` + `mapping_digest`。
  - 判据：模块导出符号齐全无桩；contract digest `--check` 一致。
  - _Requirements: 1.1, 2.3, 1.2_

- [ ] 5. `phase5_d4_revenue_detail.py` 6 点集成（只加不动）
  - import 别名 / instrumentation_specs / build_contract_payload（sheets + sibling_stores + digest）/ build_combined_store_projection / merge_projection_into_all_d4_stores；不改 D4-2/3/5/15/16/25~28 任何字节。
  - 判据：既有 sheet 的 mapping_digest 与契约不回归；`generate_phase5_d4_contract.py --check` OK。
  - _Requirements: 1.2, 5.4_

- [ ] 6. 发布链（契约重生成 + provision + rematerialize）
  - `generate_phase5_d4_contract.py --apply` → `fix_task76_provision_projection_definitions.py --apply --entry xlsx/gt-d4-operating-revenue` → `d43_rematerialize_dual_sheet.py --apply`。
  - 判据（查库不看退出码）：新 bundle 含 d41-managed；rematerialize 后 entry current bundle = desired；store-projection 对含 D4-1 的 entry 返 200（不因 D4-1 打挂 D4-2/3/15/16/25~28）。
  - _Requirements: 1.1, 1.2_

- [ ] 7. 前端 D4-1 接桥（参照 D4-15）
  - `D4TabAdjudication.vue`：接 `useWorkpaperSyncBridge`（entryId=`xlsx/gt-d4-operating-revenue`，sheetKey=`d41-managed`）+ `WorkpaperSyncEditorHost`；flushHtml 先 flush 再 `readStoreProjection`；fail-visible；新增在线编辑切换器。
  - `GtD4OperatingRevenue.vue`：`isD4DedicatedSyncSheet` 加 `'D4-1'`（防叠加 legacy 双切换器）。
  - `publishAdjudicated` 发布门不动。
  - _Requirements: 1.2, 2.4, 5.1_

- [ ] 8. 后端 seed 键对齐（消除前后端不一致）
  - `d_cycle_extraction/presets.py` D4 seed 锚点 `D4-1-adj-rows` → 与前端新键 `D4-1-rows` 对齐；`D4-1-adj-tb-6001/6051` Tier A 公式保持。
  - 判据：seed 落新键，前端 `initRows` 读到；旧键仅迁移路径命中。
  - _Requirements: 2.1, 3.3_

- [ ] 9. 后端守卫 + 变异
  - `test_d4_1_adjudication_store_roundtrip.py`：两区 build_store_projection→merge 往返逐格一致、两区 rowId 各自唯一不串、formula_mask 不回写、缺码拒绝。
  - 变异脚本 `mutate_d4_1_adjudication_guards.py`（≥4 锚点：改区 anchor/UUID、formula_mask 可回写、合并两区、去 rowId）四态判定全 RED。
  - _Requirements: 5.1, 5.3, 5.4_

- [ ] 10. 前端守卫
  - `d4AdjudicationSyncHostWiring.spec.ts`：D4-1 接桥字面量 entry_id/sheetKey、宿主 `isD4DedicatedSyncSheet` 含 'D4-1'、fail-closed；`d4AdjudicationPublishGate.spec.ts` 不回归。
  - _Requirements: 5.1, 2.4_

- [ ] 11. e2e 真栈验收
  - `d4-bidirectional-acceptance.spec.ts` 加 D4-1（L1：进在线编辑→store-projection/materialize 200→callback 四项→OO 挂载）；L2 roundtrip：OO 改主营/其他行→forcesave cs_error=0→切回 HTML 值一致、两区不串。
  - 证据落 `docs/operations/evidence/d4-bidirectional-acceptance/D4-1.json`。
  - _Requirements: 5.1, 5.3_

- [ ] 12. 三件套校验与收口
  - `get_diagnostics` 三件套无 error；AC→Property→task 引用齐；waves JSON 唯一；git 入库（只本 spec 产物 + 明确 D4-1 改动）。
  - _Requirements: 5.4_

## Notes

- 顶层任务与 Checkpoint 不纳入依赖图；`[-]` 表示上游（D4-9 `_attach_table_part` 修复）未落地的 BLOCKED，唯一解除条件写在任务正文，禁止绕过。
- D4-1 是审定枢纽（下游 K9/D4-10/D4-21 取审定数 + TB 发布）；provider 半成品会打挂整个 `gt-d4-operating-revenue` entry（如 D4-15/16 曾发生）——发布链必须跑全 + e2e 绿再收，绝不"标注绿"。
- 现状对齐纪律：spec 描述以真实代码为准（`useD4Adjudication` 用 `D4-1-rows` 新模型 + per-field；presets.py seed 仍锚旧键 `D4-1-adj-rows` = 待 Task 8 对齐的真实缺口），不把目标态当现状。
- 改双向内核共享文件（`excel_instrumentation.py`）受主控 §5.3 共享锁约束，需协调 D4-9 owner，不并行编辑。
