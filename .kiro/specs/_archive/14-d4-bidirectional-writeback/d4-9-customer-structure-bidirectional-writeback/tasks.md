# Implementation Plan — D4-9 双向回写

## Overview

把 D4-9「重要客户结构分析」接入统一双向路径。核心难点：单 sheet 内两个动态行区域 + 4 个表级标量 + 占比/合计物理公式；外加用户公式管理（血缘 + 保护区）与导入导出修复。下方复选框为唯一进度真源。

**🔴 架构裁决（路 B，已定稿）**：D4-9 **不建独立 entry**，作为 `xlsx/gt-d4-operating-revenue`
的 **sibling sheet**（sheetKey=`d49-managed`，共享 adapter `d4.revenue_detail`），与 D4-1/2/3/
5/15/16/21~29/35 同架构（overlay 规则：`d4/**` 下 mount 归父 entry，不独立计数）。后端 provider
`phase5_d4_customer_structure.py` 由父模块 `phase5_d4_revenue_detail.py` 编排。原 design 的
"独立 entry `xlsx/gt-d4-customer-structure`" 措辞已作废——下方任务描述以路 B 为准。

**实现分工（2026-09-20 核实 git HEAD）**：
- 后端 provider + 父模块接线 + 契约 JSON + 契约/instrumentation/用户公式三组测试 + 变异脚本 +
  宿主 dedicated 登记 = 已由他人入库（commit 601cb82e2）。
- 前端接入(Task 8) + 导入导出(Task 10) + oo_to_html 镜像(Task 7) = HEAD 遗漏，本工作树补齐
  （其中导入导出补齐修复了 HEAD 已入库但会红的 test_d4_9_import_export.py）。

状态词：环境不可用记 `UNVERIFIABLE`，机器判据失败记 `FAILED`。

## Tasks

- [x] 1. 修 instrumentation 支持同 sheet 双区（design 阻塞项，动共享内核）
  - 核实已完成（design §2.1.1 实测）：现状 `_attach_table_part` 对同 sheet 二次注入产出非法双 `<tableParts>`，第一区 Table 被 openpyxl 丢弃；路径 A（合并进一个 `<tableParts count>`）已实测可行
  - 改 `excel_instrumentation._attach_table_part`：sheet 已有 `<tableParts>` 块时往块内追加 `<tablePart>` 并更新 count，而非新建独立块；不存在时走原路径（保持其它 358 工作簿注入字节不变）
  - 真实注入回归：`instrument_workbook_bytes_multi` 对 D4-9 同 sheet 两 spec（W/X UUID 列）产出合法 xlsx，openpyxl 同时认出 `GT_D49C_ROWS` + `GT_D49P_ROWS`；对既有单 sheet 案例（D4-2/3、D2、H1、G7）注入字节 sha256 不变（回归守卫）
  - 变异守卫：把修复改回"无条件新建独立块"必打红（同 sheet 双区 openpyxl 只认 1 张 table）
  - openpyxl 复算 `D/D4 收入底稿.xlsx` 现字节 sha256 锁定 TEMPLATE_SHA256；跳过 `~$` 锁文件
  - 🔴 共享文件锁（主控 §5.3）：`excel_instrumentation.py` 与 Structural/Workbook lane 冲突，动前 grep 并发 spec，只加分支不改既有路径语义
  - _Requirements: 2.1, 2.2, 1.4, 8.1, 8.3_

- [x] 2. 前端 store 行补 rowId + 迁移（rowId/createRowId/backfillRowIds/loadData 迁移已实现；vitest 见 Task 12）
  - `D4TabCustomerStructure.vue`：`CustomerRow` 加 `rowId`；`defaultRows/addRow` 生成稳定 id；`loadData()` 对历史无 rowId 行补齐并持久化一次，不丢既有手工值
  - current/prior 两区 rowId 各自唯一
  - vitest：加载旧数据（无 rowId）→ 补齐且值不丢；新增行有 rowId
  - _Requirements: 3.1, 3.2, 3.4_

- [x] 3. D4-9 契约（sibling sheet 并入父 entry 契约，磁盘锁死）— 他人已入库
  - `phase5_d4_customer_structure.py` 的 `sheet_payload_d49()`：3 table（current/prior 动态行 + totals 静态标量）字段规格、formula_mask、footer_anchor、mapping_digest
  - 路 B：D4-9 sheet 并入父 `phase5_d4_revenue_detail.build_contract_payload()` 的 sheets，随父契约 `d4.revenue_detail.json` 磁盘锁死（无独立 d4.customer_structure.json / 无独立生成器）
  - 父 `assert_contract_file_matches_source()` 现算 payload 与磁盘双向锁死；parse_contract 真跑通过；字段数 = current 6 + prior 6 + totals 4；无 CS 违规
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 4. bridge 模块 store 投影 / 合并 / 身份 — 他人已入库
  - `phase5_d4_customer_structure.py`：`iter_store_rows`、`build_d49_current/prior/totals_projection`（totals 静态字段 row_key=None）、`build_d49_store_projection`（三区合并）、`merge_projection_into_d49_store`（4-tuple，按 table_key 前缀分流回 current/prior/totals）+ `merge_projection_into_d49_store_state`（3-tuple 门面，oo_to_html 用）
  - 缺/重复 rowId → StorePayloadError；legacy 裸数组载荷容差（视为空，不打挂共享 entry）
  - 单测覆盖三区投影 + 合并 + fail-closed 分支
  - _Requirements: 3.1, 3.3, 3.4, 4.2_

- [x] 5. instrumentation / definitions / 父模块编排 — 他人已入库
  - `instrumentation_spec_d49()`（同 sheet 两 region W/X，按 Task 1 结论）；父 `instrumentation_specs()` 并入两 spec、combined projection 并入 `build_d49_store_projection`、merge dispatch 并入 `merge_d49_from_projection`、review payload 写 `mapping_digest_d49`
  - 路 B：无独立 attach_adapters/publish_definitions/assert_manifest_capability_enabled——D4-9 随父 entry `d4.revenue_detail` 的 adapter 一起注册/发布
  - _Requirements: 1.1, 1.4, 1.5_

- [x] 6. capability 裁决（路 B：复用父 entry 已裁决 bidirectional）
  - D4-9 **不建 manifest entry / 不改 overlay**：复用父 entry `gt-d4-operating-revenue` 已裁决为 `bidirectional` 的 capability，与 D4-1 同架构（overlay 规则：D4 子表 mount 归父 entry）
  - 宿主 `GtD4OperatingRevenue.vue` 的 `isD4DedicatedSyncSheet` 含 `'D4-9'`（他人已入库），前端 fail-closed 由 `GtEntrySyncCapabilityNotice entry-id="gt-d4-operating-revenue"` 承载
  - _Requirements: 1.1, 1.2, 4.6_

- [x] 7. materialize / extract / OO→HTML 镜像 — 本工作树补齐（HEAD 遗漏）
  - materialize/extract 复用父 entry `build_excel_adapter`：多 table 按 anchor/row_identity 写区间、totals 按静态 cell 写、formula_mask 保护 D/F 与合计（随父 adapter）
  - `oo_to_html.py` `_mirror_d4_dual_stores` 加 **D4-9 专用 dict 块**（不走 rows 循环）：`STORE_ITEM_ID_D49_DICT` 从 rows 循环排除 + `merge_d49_from_projection` 分流回 `D4-9-data` 的 {current,prior}+totals，formula_mask 覆盖的 D/F 占比+合计不回写
  - HEAD 的 oo_to_html 完全无 D4-9 处理，本次为纯新增
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 8. 前端宿主接入 + 移除 legacy 单向入口 — 本工作树补齐（HEAD 遗漏）
  - `D4TabCustomerStructure.vue`：改为子组件自管 `useWorkpaperSyncBridge`（entryId=`gt-d4-operating-revenue`/sheetKey=`d49-managed`，与 D4-1 同架构）+ `WorkpaperSyncEditorHost` + 同步状态 tag + `GtEntrySyncCapabilityNotice`；移除 legacy `editorMode` ref 与 `GtOnlyOfficeSheet` 单向分支/import；rowId/迁移逻辑保留
  - 宿主 `GtD4OperatingRevenue.vue` 的 D4-9 dedicated 登记他人已入库（本次不重复改）
  - 能力未裁决/OO 不健康 fail-closed（modeOptions disabled + fail-visible tag）
  - HEAD 的 D4TabCustomerStructure 仍是 legacy，本次为主要补齐
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 9. 用户公式管理（wp_formula + 保护区计算层 + 血缘）— 他人已入库（计算层）
  - 用户公式落 wp_formula 复用 `wp_formula_service.save`（target_cell 锚 D4-9 sheet）+ ACNR `validate_refs_via_acnr`/`full_resolve` 校验中文错误（save 内已调用）
  - `runtime_protected_cells` = 契约静态 formula_mask ∪ 用户公式 cell（`runtime_user_formula_cells` 过滤 D4-9 受管区可解析 A1）；`user_formulas_for_xlsx` 供 `_fill_workpaper_data` 覆盖（用户公式优先）；`formula_lineage` 声明占比 D→C/$C$24、合计→明细区间、总额←D4-7 取数 + 总额手工覆盖保留
  - 守卫 test_d4_9_user_formula_protection.py 5 passed（含变异锚点：排除用户公式 cell → 不在保护集合）
  - `[ ]*` 运行时保护区**强制执行**接入共享 sync verify 核（verify_before_commit declared_protected_keys 并入 runtime cells）= 需改 D4-2/3/5…全 entry 共用 sync 内核（违"不改契约内核"高风险）+ 需真实 OO/representation 实测 → 归 Task 13 真栈；离线只交付保护集合**计算层**（已测）
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 10. 导入导出修复（本期/上期 + 总额 + 专用 parser）— 本工作树补齐（修 HEAD 红测试）
  - `_SHEET_HEADERS["D4-9"]` 改为 期间/序号/客户名称/销售金额/销售金额占比/销售数量/销售数量占比/上期排名
  - `_build_d4_9_export_rows`：本期/上期两区数据行 + 各一总额行（_period/_seq/_isTotal/_totalAmount）；row-builder 计算占比导出（不可回导）
  - `_parse_d4_9_row`：判本期/上期 + 识别总额行 + 普通行补 rowId + 忽略占比列；导入 merge 按 _period 分流回 {current,prior}，总额行回填 totalAmount/totalQuantity，缺某区保留既有
  - 🔴 HEAD 的 `_d4_import_export.py` 仍是 4 列 legacy，而 HEAD 已入库的 `test_d4_9_import_export.py` 期望增强版 → 对 HEAD 变红；本次补齐后 6 passed + 既有 PBT 不回归
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 11. 后端守卫 + 变异检验 — 他人已入库
  - 契约/roundtrip/身份守卫行为级（33 passed：contract 12 + instrumentation_and_alignment 4 + same_sheet_dual_region 6 + user_formula_protection 5 + import_export 6）
  - `backend/scripts/diagnose/mutate_d4_9_customer_structure_guards.py` 5 锚点四态：M1 删 D 占比 mask / M2 静态标量改行域(CS-9) / M3 合并两 table / M4 去 rowId / M5 用户公式 cell 不进保护集合 —— 全 RED，baseline GREEN，restore OK，pass=true
  - evidence/mutation_report.json 已存
  - _Requirements: 8.1, 8.2, 8.3_

- [x] 12. 前端守卫（vitest）— 本工作树补齐
  - `d4CustomerStructureSyncHostWiring.spec.ts` 18 passed：断言 D4TabCustomerStructure 走 `useWorkpaperSyncBridge`、entryId 字面量=`gt-d4-operating-revenue`/sheetKey=`d49-managed`、flush 先于 readStoreProjection、挂 `WorkpaperSyncEditorHost` 且移除 `GtOnlyOfficeSheet`、fail-visible danger tag、rowId 迁移（CustomerRow.rowId/createRowId/backfillRowIds）、宿主 dedicated 含 D4-9；变异自检（改错 entry_id/legacy 回潮/去列表 打红）
  - _Requirements: 8.4, 7.1, 7.5_

- [~] 13. 真栈实测（Playwright + 真实 OO）+ 收口 — `UNVERIFIABLE`（待运行时）
  - 选真实 D4 底稿：HTML 编辑客户行 + 4 总额 → 在线编辑可见 → OO 改一行 + 改一总额 → 切回 HTML 值逐字对齐；merge 幂等；用户公式 cell 不被 OO 覆盖（含 Task 9 运行时保护区强制执行的真栈验证）
  - 证据 JSON 记录 request 路径（命中 USER_SYNC_PREFIX、无 legacy 旁路）、content version、application、operation 终态、artifact digest
  - 🔴 **运行时阻塞**：D4-9 sheet 并入父 entry 后，父 `d4.revenue_detail` 契约 digest 变化（含 d49-managed），需 representation 升级到新 bundle 才能真栈往返；升级需 `ContentMutationService.commit` 或 instrumentation upgrader（provisioner 不伪造）。属部署时步骤，离线不可完成 → 记 `UNVERIFIABLE`
  - ✅ **上条「运行时阻塞」已过时作废（2026-09-21 真 PG 实证）**：representation 早已升级并远超当初卡点 —— `d43_rematerialize_dual_sheet.py --check` 返 `already_on_desired_bundle`，entry `xlsx/gt-d4-operating-revenue` 当前 **generation 84 / bundle `2a8db807…`**（34 张 sheet，含 `d49-managed`），desired == current 无漂移。故「需先升级 representation」不再是 D4-9 的阻塞。
  - 🔴 **本任务仍 `[~]`，但剩余阻塞已换成另一条（同 D4 全组批次C 标准，非 D4-9 独有）**：真 OO canvas 单元格往返。**新增实证**：`working_paper_content_application` 表里打在**当前 bundle `2a8db807…` 上的 applied 记录数 = 0**（全 14 条 applied 最新一条 2026-09-20 02:25Z，打在旧 bundle `d91cf0f2…` 上；`working_paper_content_version` 的 `source=onlyoffice` 14 条最新 02:26Z，同样早于当前 bundle 13:58Z）⇒ 当前 34 张 bundle 上的 OO→HTML apply 路径**一次都没被真实走过**，包括 commit `808505a15` 修的三处消费侧缺口（P0 硬解包 / P1 D4-8 静默 / P2 基线恒空）目前只有离线守卫覆盖。这是全组共同的最后一道门，不是把 D4-9 单独标绿的理由。
  - _Requirements: 8.5, 8.6_

## Notes
保留上文旧任务的历史业务细节；以下唯一 waves JSON 为当前执行编排。

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1","2"],"rationale":"C0身份与rowId并行"},{"wave":2,"tasks":["3"],"rationale":"contract依赖C0"},{"wave":3,"tasks":["4","5"],"rationale":"投影与registry依赖contract"},{"wave":4,"tasks":["6","7"],"rationale":"entry和materialize依赖bridge"},{"wave":5,"tasks":["8","9","10"],"rationale":"前端、公式、IO并行"},{"wave":6,"tasks":["11","12"],"rationale":"守卫依赖实现"},{"wave":7,"tasks":["13","14","15"],"rationale":"C4真栈与统一gate最后"}],"blocking":{"1":"双区instrumentation未修不得生成contract","3":"contract未锁死不得投影","6":"capability未裁决不得在线编辑"}}
```

## Notes

- **架构裁决路 B（作废 design 的独立 entry 方案）**：平台 manifest 由前端 mount 发现器 + reviewed
  overlay 生成，`d4/**` 下所有 mount 归父 entry `gt-d4-operating-revenue`（overlay 明确"D4 tab
  hosts must not be counted as independent adapters"）。D4-1 先例已证独立 entry 不可行。故 D4-9
  = sibling sheet，复用父 entry/adapter，随父契约锁死、随父 adapter 注册发布。design.md §5 的
  "新建独立 entry" 论证被此平台约束否决。
- D4-8 单独排期，不在本 spec 范围。
- 不改契约内核：D4-9 的多 table + 表级标量 + 公式已被 `contracts.py` 现有模型（SheetSpec.tables /
  CellMapping.static_row / FooterAnchorSpec.carries_total_formula / formula_mask）表达。
- 共享文件锁：`oo_to_html.py`、`_d4_import_export.py`、`phase5_d4_revenue_detail.py` 与并发会话
  （D4-6/17/18/19 批次B）冲突时只追加不覆盖；本工作树的 D4-9 补齐与并发 D4-19 改动在同一批文件里
  各自独立，提交时按文件粒度择取 D4-9 相关 hunk，不裹挟他人在途工作。


## Common Contract Alignment Gate
- [~] 14. C0-C4 alignment：按总纲验证wp_id身份、共享sync、公式状态、真实DAG/联动与逐表gate；durable ack不等于applied，公式同步不是TB/A13。
  - _Requirements: 2.1, 2.2, 3.1, 8.1_
- [~] 15. C4逐D4-9验收：source/template evidence、三table identity、formula mask、roundtrip、权限、Playwright和变异；只门控D4-9相关产物。
  - _Requirements: 3.1, 8.1_

---

## 2026-09-22 归档前状态刷新（append-only；上方复选框与原文一律不动）

> 上方 Task 13 已两次登记「运行时阻塞」并两次自我作废/替换（第一条 representation 未升级已于
> 2026-09-21 实证作废；第二条改成「真 OO canvas 单元格往返，当前 bundle 上 applied 记录数 = 0」）。
> 本节登记第三次核对结果，并把 Task 14/15 的 `[~]` 一并说清。按 append-only 铁律不动上方文字。

**① Task 13 的 L1 侧已完成**：`docs/operations/evidence/d4-bidirectional-acceptance/D4-9.json`
（2026-09-22）—— store-projection 200 → materialize 200 → callbackUrl 四项齐全 → `wp-sync-host`
+ OO iframe，`d2_sync_hits=0`，`console_errors=[]` / `http_errors=[]`。
即「HTML 编辑客户行 → 切在线编辑可见 → 统一路径无 legacy 旁路」这一段已真栈成立。

**② Task 13 剩余的「真 OO canvas 单元格往返 + 当前 bundle 上的 applied 记录」仍未在 D4-9 上产生**，
但同父 entry（`xlsx/gt-d4-operating-revenue` / adapter `d4.revenue_detail`）已有**一份**真实 applied
记录，落在 D4-2：`.kiro/specs/_archive/14-d4-bidirectional-writeback/d4-revenue-matrix-bidirectional/evidence/g5-1-d4-unified-path/db-check.json`
（`operation.state=applied` / `application.state=applied` / `content_version.source=onlyoffice` /
`store_mirror.marker_in_store=true`）+ `network-and-callback.json` 的 `forcesave_cs_error=0`。
⇒ 「链路能不能真 applied」已被证伪为**不是缺陷**；D4-9 缺的是**同一条链路在本 sheet 上再跑一遍**。

**③ Task 14/15 的 `[~]`（C0-C4 alignment / C4 逐 D4-9 验收矩阵）**：这两条的判据锚在总纲的 C4 验收矩阵，
其推进主体是 `d4-dual-mode-formula-governance`（现 16/16 全绿）与总纲
`workpaper-html-onlyoffice-bidirectional-writeback-closure`（Task 70 口径）。本 spec 侧的 D4-9 产物
（同 sheet 双区 instrumentation、sibling sheet 双向回写路 B、用户公式保护区、导入导出补齐、前端接桥）
已全部就位并有守卫；C4 矩阵本身不是本 spec 可独立签发的产物。

**④ 归档判定**：本 spec 无剩余自有产物 ⇒ **可归档**。残留的 per-sheet L2 数据往返按 entry 粒度
移交总纲 Task 70 的「全 entry required scenario」口径，与 D4 其余 28 张同批推进，不单独挂在本 spec。
