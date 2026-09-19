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

- [x] 1. 几何核定与 mapping_digest 冻结
  - openpyxl 直读权威模板 `D/D4 收入底稿.xlsx` sheet `营业收入审定表D4-1`，冻结两区 anchor（主营 R8 起 / 其他 R14 起）、受管列 A/B/C/D/F/G/H、formula_mask（E/I + 12/18/19/21 的 B–I）、两区 UUID 空列；产出 `evidence/d41-geometry.json` + mapping_digest。
  - 判据：几何与前端 `useD4Adjudication` 六金额字段逐项对齐；digest 冻结。
  - _Requirements: 1.1, 2.3_

- [x] 2. 契约结构守卫（parse_contract 真跑）
  - 新增 `backend/tests/workpaper_sync/test_d4_1_adjudication_contract.py`：`build_contract_payload()` 加入 d41-managed 后，`parse_contract` 得 sheet 含 2 张 row table（main/other），各有 row_identity + delete_policy，E/I/小计/合计/差异列落 formula_mask；两区 UUID 列不同。
  - 反向自检：把两区合并成一 table / 去 formula_mask → parse 失败或守卫红。
  - _Requirements: 1.1, 2.3, 5.4_

- [x] 3. 【前置/依赖 D4-9】同 sheet 双区 instrumentation 修复核实
  - 核实 `excel_instrumentation._attach_table_part` 是否已支持同 sheet 合并 `<tableParts count>`（D4-9 design §2.1.1 路径 A）。已修：直接用；未修：本 spec 不擅自改双向内核共享文件（主控 §5.3 共享锁），标 `[-]` BLOCKED 并记录唯一解除条件（D4-9 Task 1 落地）。
  - 判据：`instrument_workbook_bytes_multi` 对 D4-1 两区同 managed_sheet 注入后，openpyxl 同时认出两区 Table（非畸形双 `<tableParts>`）。
  - **核实结论（BLOCKED / NOT FIXED）**：`_attach_table_part`（excel_instrumentation.py:1118）仍无条件插入独立 `<tableParts count="1"><tablePart r:id=.../></tableParts>` 块，不检测/不合并已存在的 `<tableParts>`。`instrument_workbook_bytes_multi` 对同 managed_sheet 的两 spec 逐 spec 调用 `_inject_managed_sheet`→`_attach_table_part`，第二区在已含一个 `<tableParts>` 的 sheet_xml 上再插一个 → **同一 worksheet 出现 2 个 `<tableParts count="1">`（畸形 OOXML）**。
  - **实测证据**（一次性探针，真实模板 `wp_templates/K/K11 资产减值损失.xlsx` sheet `审定表K11-1`，两区 UUID 列 N/P，用完即删）：注入后目标 sheet XML `<tableParts>` 开标签 = 2 个（均 `count="1"`），table 定义文件 = `tableGtRowId.xml` + `tableGtRowId_D41OTHER.xml`（2 个，部件不撞名）；但 `openpyxl.load_workbook` 在该 sheet 仅认出 **1 张 Table**（`GT_D41_OTHER_ROWS`），第一区 `GT_D41_MAIN_ROWS` 被静默丢弃 = 假双向。
  - **唯一解除条件**：D4-9 owner spec（`d4-9-customer-structure-bidirectional-writeback`）**Task 1** 落地——把 `_attach_table_part` 改为「sheet 已有 `<tableParts>` 块时往块内追加 `<tablePart>` 并更新 count，不存在才走原路径」+ 变异守卫（改回无条件新建独立块必红）+ 既有 358 单 sheet 工作簿注入字节 sha256 不回归。当前 D4-9 Task 1 = `[ ]`（未开始，spec 0/15）。本 spec 不擅改共享内核（主控 §5.3 共享锁）。
  - _Requirements: 1.1, 5.4_

- [x] 4. 后端 provider `phase5_d4_adjudication_sheet.py`（镜像 D4-9 多 table）
  - 常量 + `MANAGED_FIELD_SPECS`（两区 × label+6 金额）+ `FORMULA_MASK` + `sheet_payload_d41`（2 row table，各 anchor/uuid_col/footer）+ `instrumentation_spec_d41`（2 spec 同 sheet 不同行段/UUID）+ `build_store_projection_d41`（按 sectionKey 分流）+ `merge_projection_into_d41_rows` + `mapping_digest`。
  - 判据：模块导出符号齐全无桩；contract digest `--check` 一致。
  - _Requirements: 1.1, 2.3, 1.2_

- [x] 5. `phase5_d4_revenue_detail.py` 6 点集成（只加不动）
  - import 别名 / instrumentation_specs / build_contract_payload（sheets + sibling_stores + digest）/ build_combined_store_projection / merge_projection_into_all_d4_stores；不改 D4-2/3/5/15/16/25~28 任何字节。
  - 判据：既有 sheet 的 mapping_digest 与契约不回归；`generate_phase5_d4_contract.py --check` OK。
  - _Requirements: 1.2, 5.4_

- [x] 6. 发布链（契约重生成 + provision + rematerialize）
  - `generate_phase5_d4_contract.py --apply` → `fix_task76_provision_projection_definitions.py --apply --entry xlsx/gt-d4-operating-revenue` → `d43_rematerialize_dual_sheet.py --apply`。
  - 判据（查库不看退出码）：新 bundle 含 d41-managed；rematerialize 后 entry current bundle = desired；store-projection 对含 D4-1 的 entry 返 200（不因 D4-1 打挂 D4-2/3/15/16/25~28）。
  - **执行结论（判据①②③全 GREEN，真栈实跑于 live PG audit-postgres）**：判据①GREEN（契约 --check OK，approved bundle c4c5abe7… 引用含 d41-managed 的契约 digest 7b57a085…，provision 幂等0新增）；判据③GREEN（离线直调 build_combined_store_projection 不抛，D4-1 贡献21格 main/other，D4-2存活18/D4-3存活6，不打挂 entry；live-PG store_bytes 全 entry 正常返回）；判据②GREEN（`d43_rematerialize --apply` status=rematerialized gen50→51，DB 确认 entry 当前 bundle=desired af32bfbd…）。历史阻塞：曾先后卡 (a) ManagedRegionResolutionError（extract 侧「一sheet一动态表」硬 fail，第三处内核修复解除）(b) FooterAnchorDriftError（materialize 侧 footer sheet_key→单 TID 误判，第四处内核修复解除，见下）。
  - **🔴 共享内核缺口（本 spec 识别，共 4 处，全部落地）**：同 sheet 双区需4处内核改动——(1) _attach_table_part XML 合并✅ (2) sibling binding 对齐✅ (3) excel_extract.managed_tables_of + extract_projection extract 侧解析✅（须支持一 sheet N 张动态表各自 binding、逐表反读合并）(4) **excel_materialize footer per-region 解析✅**（冻结侧按 table_name→平行清册 template_id 取 GT_FOOTER_ROW_{TID} + 可见侧 min_row 区分同名 marker，materialize 侧几何门）。
  - **✅ 第三处内核已落地（2026-XX，主控 §5.3 共享锁 GENERALIZE，不回归单动态表）**：`excel_extract.managed_tables_of` 原在同 sheet 见到第二张动态行表就硬抛 `ManagedRegionResolutionError`（"一 sheet 一动态表"），改为**跳过兄弟动态表**（不返回、不 fail-closed）——兄弟表属兄弟 binding，adapter.extract 逐 binding 各调一次 extract_projection 再 merge，各归各的。「每张动态表都有 binding」这条不变式**迁移**到看得见全部 binding 的上游 `projection_first_publication._align_specs_to_sibling_tables`（行 table 总数 == specs 数 + spec↔table 双射，已存在），本函数据此安全跳过而不漏未绑定表。静态表照旧被每个 binding 纳入本 sheet 受管坐标（安全方向，merge 幂等，D4-1 本 sheet 0 静态表）。**diff = 仅 `raise` → `continue`**，无 adapter/上游断言改动。
  - **验证**：新守卫 `test_d4_1_dual_region_managed_tables.py`（7 passed）——两 binding 各返回自己动态表且不抛 + 真实注入双区产物上 resolve_managed_region/managed_tables_of 两区均成功 + 单动态表 sheet 静态清册零回归 + 变异守卫（改回硬抛则双区测试 RED，源级实测 3 红）；旧 `test_task37_excel_extract.py::test_second_dynamic_table_on_same_sheet_*` 由「fails_closed」改为「is_skipped_not_fatal」编码新契约（106 passed）；judge `test_d4_1_adjudication_contract.py`(10/10)/`test_d4_1_sibling_binding_alignment.py` 全绿；D4-3/D4-5/D4-9-IPO 生产 roundtrip + D4-9 双区 instrumentation 零回归。
  - **judge② extract 侧解除，materialize 侧另有独立门**：live-PG `d43_rematerialize_dual_sheet.py --apply` **不再抛 ManagedRegionResolutionError**（extract 侧已通），改抛下游 `FooterAnchorDriftError`（footer marker '小计' 实测 R12，representation 冻结 GT_FOOTER_ROW=31 —— materialize 侧几何门，属**另一**缺口，非本次 extract 修复范畴）。事务回滚，DB 无损（bundle 仍 665eed8a…，generation 50）。current→af32bfbd… 待 footer 几何门单独解除后重跑。
  - **✅ 第四处内核已落地 —— footer per-region 解析（materialize 侧几何门解除，judge② 现 GREEN）**：**ROOT CAUSE**（已核实）= `excel_materialize.assert_footer_anchor_stable` 原用 `_resolve_frozen_footer_row(runtime_binding, sheet_key='d41-managed')` 取冻结 footer，而 `_template_ids_from_sheet_key('d41-managed')` 只得单个 `D41`；但 instrumentation 写的是 **per-SPEC 键** `GT_FOOTER_ROW_D41MAIN`(=12)/`GT_FOOTER_ROW_D41OTHER`(=18)（两 spec template_id=D41MAIN/D41OTHER 共享 sheet_key）→ `GT_FOOTER_ROW_D41` 找不到 → 回退裸 `GT_FOOTER_ROW`（combined entry 里=D4-2 primary 的 31）→ 主营 marker R12≠31 → drift。**两处必修**（sheet_key→单 TID 假设在一 sheet N region 时破产，须按 REGION 解析）：①**冻结侧** `_resolve_frozen_footer_row` 新增 `table_name` 参，优先按本 region 物理 table_name（binding/region）经 `_GT_SYNC` **平行有序清册** `GT_MANAGED_TABLES`(=`GT_D41_MAIN_ROWS,GT_D41_OTHER_ROWS`)/`GT_TEMPLATE_IDS`(=`D41MAIN,D41OTHER`) 定位 template_id，取 `GT_FOOTER_ROW_{TID}`；缺省退回 sheet_key 路径→裸主键（单 region/多 sheet-单区**逐字不变**）。②**可见侧** `_find_marker_row` 新增 `min_row`，同 marker（`小计`）在每区各出现一次，传 `region.first_row`（main=8 从 R8 搜到 R12 / other=14 跳过 R12 命中 R18）两区各归各的。table_key→template_id 桥梁 = 平行清册（契约 TableSpec 无 template_id 字段，binding.table_name 是唯一两侧一致锚点）。同口径贯穿 4 处 footer 解析点（plan 期 `assert_footer_anchor_stable`、apply 后 `assert_shifted_footer_gates`、`_plan_row_shift` 扩张、`_refresh_gt_sync_runtime_binding` 重冻结——后者经新增 `MaterializePlan.managed_table_name` 精确移位本区 per-TID 键不误动 sibling）。**diff = excel_materialize.py 增 `_template_id_for_table_name` 助手 + `_resolve_frozen_footer_row`/`assert_footer_anchor_stable`/`_find_marker_row` 加参 + 4 调用点传 table_name/first_row + MaterializePlan 加 managed_table_name 字段**，无 extract/上游改动。
  - **验证**：①新守卫 `test_d4_1_footer_anchor_per_region.py`（10 passed）——resolver main→12/other→18、真实双区注入产物两区 footer 门各通过（即使裸=31）、变异守卫（退回 sheet_key-only 冻结→裸31→drift 必红 / 不传 min_row→其他区误取主营 R12→drift）、不削弱漂移检测（篡改冻结99→仍 drift）、多 sheet-单区(D4-23 sheet_key→D423→24)零回归；②既有 124 footer/materialize 回归全绿（test_task38/test_d4_dual_sheet/test_d4_1_* /test_excel_shift_aware 相关子集）；③**live-PG `d43_rematerialize_dual_sheet.py --apply` PASS**（status=rematerialized，generation 50→51，revision 75，**无 FooterAnchorDriftError、无第五道门**）；④DB 查库确认 **judge② GREEN**：entry `xlsx/gt-d4-operating-revenue` 当前(gen 51)representation `definition_bundle_sha256` = **`af32bfbde3f1cff8243f2125367547366db9a412ef4684bbdc0b9379e6cb7fd6`**（=desired bundle，此前卡在 665eed8a…gen50）；store-projection 含 D4-1 且不打挂 D4-2/3/25~28（store_bytes 全 entry 正常返回）。**判据①②③全 GREEN，Task 6 收口。**
  - _Requirements: 1.1, 1.2_

- [x] 7. 前端 D4-1 接桥（参照 D4-15）
  - `D4TabAdjudication.vue`：接 `useWorkpaperSyncBridge`（entryId=`xlsx/gt-d4-operating-revenue`，sheetKey=`d41-managed`）+ `WorkpaperSyncEditorHost`；flushHtml 先 flush 再 `readStoreProjection`；fail-visible；新增在线编辑切换器。
  - `GtD4OperatingRevenue.vue`：`isD4DedicatedSyncSheet` 加 `'D4-1'`（防叠加 legacy 双切换器）。
  - `publishAdjudicated` 发布门不动。
  - _Requirements: 1.2, 2.4, 5.1_

- [x] 8. 后端 seed 键对齐（消除前后端不一致）
  - `d_cycle_extraction/presets.py` D4 seed 锚点 `D4-1-adj-rows` → 与前端新键 `D4-1-rows` 对齐；`D4-1-adj-tb-6001/6051` Tier A 公式保持。
  - 判据：seed 落新键，前端 `initRows` 读到；旧键仅迁移路径命中。
  - _Requirements: 2.1, 3.3_

- [x] 9. 后端守卫 + 变异
  - `test_d4_1_adjudication_store_roundtrip.py`：两区 build_store_projection→merge 往返逐格一致、两区 rowId 各自唯一不串、formula_mask 不回写、缺码拒绝。
  - 变异脚本 `mutate_d4_1_adjudication_guards.py`（≥4 锚点：改区 anchor/UUID、formula_mask 可回写、合并两区、去 rowId）四态判定全 RED。
  - _Requirements: 5.1, 5.3, 5.4_

- [x] 10. 前端守卫
  - `d4AdjudicationSyncHostWiring.spec.ts`：D4-1 接桥字面量 entry_id/sheetKey、宿主 `isD4DedicatedSyncSheet` 含 'D4-1'、fail-closed；`d4AdjudicationPublishGate.spec.ts` 不回归。
  - _Requirements: 5.1, 2.4_

- [~] 11. e2e 真栈验收
  - `d4-bidirectional-acceptance.spec.ts` 加 D4-1（L1：进在线编辑→store-projection/materialize 200→callback 四项→OO 挂载）；L2 roundtrip：OO 改主营/其他行→forcesave cs_error=0→切回 HTML 值一致、两区不串。
  - 证据落 `docs/operations/evidence/d4-bidirectional-acceptance/D4-1.json`。
  - _Requirements: 5.1, 5.3_

- [~] 12. 三件套校验与收口
  - `get_diagnostics` 三件套无 error；AC→Property→task 引用齐；waves JSON 唯一；git 入库（只本 spec 产物 + 明确 D4-1 改动）。
  - _Requirements: 5.4_

## Notes

- 顶层任务与 Checkpoint 不纳入依赖图；`[-]` 表示上游（D4-9 `_attach_table_part` 修复）未落地的 BLOCKED，唯一解除条件写在任务正文，禁止绕过。
- D4-1 是审定枢纽（下游 K9/D4-10/D4-21 取审定数 + TB 发布）；provider 半成品会打挂整个 `gt-d4-operating-revenue` entry（如 D4-15/16 曾发生）——发布链必须跑全 + e2e 绿再收，绝不"标注绿"。
- 现状对齐纪律：spec 描述以真实代码为准（`useD4Adjudication` 用 `D4-1-rows` 新模型 + per-field；presets.py seed 仍锚旧键 `D4-1-adj-rows` = 待 Task 8 对齐的真实缺口），不把目标态当现状。
- 改双向内核共享文件（`excel_instrumentation.py`）受主控 §5.3 共享锁约束，需协调 D4-9 owner，不并行编辑。
