# Implementation Plan — D4-9 双向回写

## Overview

把 D4-9「重要客户结构分析」作为独立 entry 接入统一双向路径。核心难点：单 sheet 内两个动态行区域 + 4 个表级标量 + 占比/合计物理公式；外加用户公式管理（血缘 + 保护区）与导入导出修复。下方复选框为唯一进度真源；按 waves 推进（见 Task Dependency Graph）。

状态词遵循主控 §2.3：discovery-only 用 `[~]`，upstream 缺失用 `[-]` 并写解除条件，环境不可用记 `UNVERIFIABLE`，机器判据失败记 `FAILED`。

## Tasks

- [x] 1. 修 instrumentation 支持同 sheet 双区（design 阻塞项，动共享内核）
  - 核实已完成（design §2.1.1 实测）：现状 `_attach_table_part` 对同 sheet 二次注入产出非法双 `<tableParts>`，第一区 Table 被 openpyxl 丢弃；路径 A（合并进一个 `<tableParts count>`）已实测可行
  - 改 `excel_instrumentation._attach_table_part`：sheet 已有 `<tableParts>` 块时往块内追加 `<tablePart>` 并更新 count，而非新建独立块；不存在时走原路径（保持其它 358 工作簿注入字节不变）
  - 真实注入回归：`instrument_workbook_bytes_multi` 对 D4-9 同 sheet 两 spec（W/X UUID 列）产出合法 xlsx，openpyxl 同时认出 `GT_D49C_ROWS` + `GT_D49P_ROWS`；对既有单 sheet 案例（D4-2/3、D2、H1、G7）注入字节 sha256 不变（回归守卫）
  - 变异守卫：把修复改回"无条件新建独立块"必打红（同 sheet 双区 openpyxl 只认 1 张 table）
  - openpyxl 复算 `D/D4 收入底稿.xlsx` 现字节 sha256 锁定 TEMPLATE_SHA256；跳过 `~$` 锁文件
  - 🔴 共享文件锁（主控 §5.3）：`excel_instrumentation.py` 与 Structural/Workbook lane 冲突，动前 grep 并发 spec，只加分支不改既有路径语义
  - _Requirements: 2.1, 2.2, 1.4, 8.1, 8.3_

- [-] 2. 前端 store 行补 rowId + 迁移（后端投影 fail-closed 前提）
  - `D4TabCustomerStructure.vue`：`CustomerRow` 加 `rowId`；`defaultRows/addRow` 生成稳定 id；`loadData()` 对历史无 rowId 行补齐并持久化一次，不丢既有手工值
  - current/prior 两区 rowId 各自唯一
  - vitest：加载旧数据（无 rowId）→ 补齐且值不丢；新增行有 rowId
  - _Requirements: 3.1, 3.2, 3.4_

- [~] 3. D4-9 per-entry contract + 生成器 + 磁盘锁死
  - 新建 `phase5_d4_customer_structure.py` 的 contract 相关部分：3 table（current/prior 动态行 + totals 静态标量）字段规格、formula_mask、footer_anchor、mapping_digest
  - 生成器脚本 `backend/scripts/gen/generate_phase5_d4_customer_structure_contract.py --apply` 产出磁盘 JSON `d4.customer_structure.json`
  - `assert_contract_file_matches_source()` 现算 payload 与磁盘双向锁死
  - 校验：parse_contract 真跑通过；字段数 = current 6 + prior 6 + totals 4；无 CS 违规
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [~] 4. bridge 模块 store 投影 / 合并 / 身份
  - `phase5_d4_customer_structure.py`：`iter_store_rows`（复用 store_row_identity fail-closed）、`build_store_projection`（current）、`build_prior_store_projection`、`build_totals_projection`（静态字段 row_key=None）、`build_combined_store_projection`、`merge_projection_into_store_rows`（按 table_key 前缀分流回 current/prior/totals）
  - 缺/重复 rowId → StorePayloadError
  - 单测覆盖三区投影 + 合并 + fail-closed 分支
  - _Requirements: 3.1, 3.3, 3.4, 4.2_

- [~] 5. instrumentation / definitions / 选型 / registry attach
  - `instrumentation_specs()`（同 sheet 两 region，按 Task 1 结论）、`template_definition_payload` / `instrumentation_definition_payload` / `authority_model_payload`
  - `assert_entry_selectable` / `assert_manifest_capability_enabled` / `attach_adapters` / `publish_definitions`（镜像 D4-2，换 ENTRY_ID/ADAPTER_ID）
  - _Requirements: 1.1, 1.4, 1.5_

- [~] 6. manifest entry + reviewed overlay 裁决 capability
  - 在 source-backed manifest 增 `xlsx/gt-d4-customer-structure` entry（document_type xlsx / independent_entry / scenario_profile / wp_match / adapter_id）
  - reviewed overlay 裁决 capability=bidirectional；重生成 manifest
  - capability 未裁决时 attach fail-closed（守卫断言）
  - _Requirements: 1.1, 1.2, 4.6_

- [~] 7. materialize / extract / OO→HTML 镜像
  - 复用 `build_excel_adapter`；确认多 table 按 anchor/row_identity 写区间、totals 按静态 cell 写、formula_mask 保护 D/F 与合计
  - `oo_to_html.py` 加 `adapter_id == "d4.customer_structure"` 分支 → `_mirror_d4_customer_structure`（combined projection 回写 `D4-9-data` 的 {current,prior}+totals）
  - OO 侧增删客户行走 excel_row_shift / workbook_row_change，合计区间随 carries_total_formula 扩张
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [~] 8. 前端宿主接入 + 移除 legacy 单向入口
  - `GtD4OperatingRevenue.vue`：D4-9 走第二个 `useWorkpaperSyncBridge`（entryId=customer-structure，flushHtml 读 D4-9-data store-projection）+ `WorkpaperSyncEditorHost`；按 currentSheet 选 entry/bridge
  - `D4TabCustomerStructure.vue`：移除 `editorMode` 双模式与内部 `GtOnlyOfficeSheet` 分支
  - 能力未裁决/OO 不健康 fail-closed 提示
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [~] 9. 用户公式管理（wp_formula + 保护区 + 血缘）
  - D4-9 用户公式落 `wp_formula`（target_cell 锚定），实例化/导出写 xlsx（用户公式优先）
  - materialize/extract 的 protected 集合 = contract formula_mask ∪ 运行时用户公式 cell；OO 改该 cell 产生受保护字段冲突
  - 引用校验走 ACNR `full_resolve`，中文错误不静默吞
  - 血缘：占比 D→C/$C$24、合计→明细区间、总额←D4-7 取数登记为可追溯 lineage；总额取数不覆盖手工值
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [~] 10. 导入导出修复（本期/上期 + 总额 + 专用 parser）
  - `_d4_import_export.py`：D4-9 表头含期间标识 + 占比列 + 总额；导出按 current/prior 两段含合计/总额，占比导计算值并标注不可回导
  - 新增 `_parse_d4_9_row`（判定本期/上期归属 + 解析总额）；导入组装回 `{current,prior}` 并补 rowId
  - 列名不匹配中文错误
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [~] 11. 后端守卫 + 变异检验
  - 契约/roundtrip/身份守卫（行为级，非符号存在）：parse_contract 真跑、materialize→extract 逐字段对齐、投影 fail-closed
  - `backend/scripts/diagnose/mutate_d4_9_customer_structure_guards.py`，锚点 ≥4：删 D/F formula_mask · 静态标量改 row 域 · 合并两 table · 去 rowId 身份；四态判定
  - 用户公式保护区守卫：故意让用户公式 cell 不进保护集合 → OO 覆盖 → 必红
  - _Requirements: 8.1, 8.2, 8.3_

- [~] 12. 前端守卫（vitest）
  - 断言 D4-9 走新 entry 的 `WorkpaperSyncEditorHost`、字面量 entry_id/端点正确、能力未裁决 fail-closed、legacy `GtOnlyOfficeSheet` 分支已移除
  - 变异：改错 entry_id 前缀必红
  - _Requirements: 8.4, 7.1, 7.5_

- [~] 13. 真栈实测（Playwright + 真实 OO）+ 收口
  - 选真实 D4 底稿：HTML 编辑客户行 + 4 总额 → 在线编辑可见 → OO 改一行 + 改一总额 → 切回 HTML 值逐字对齐；merge 幂等；用户公式 cell 不被 OO 覆盖
  - 证据 JSON 记录 request 路径（命中 USER_SYNC_PREFIX、无 legacy 旁路）、content version、application、operation 终态、artifact digest
  - `get_diagnostics` 校验三件套；`git status --porcelain -- <产物清单>` 核无 `??` 漏登记；`.kiro/specs/INDEX.md` 登记；清理 `tmp_*`/`_wip_*`
  - 环境不可用记 `UNVERIFIABLE`
  - _Requirements: 8.5, 8.6_

## Notes
保留上文旧任务的历史业务细节；以下唯一 waves JSON 为当前执行编排。

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1","2"],"rationale":"C0身份与rowId并行"},{"wave":2,"tasks":["3"],"rationale":"contract依赖C0"},{"wave":3,"tasks":["4","5"],"rationale":"投影与registry依赖contract"},{"wave":4,"tasks":["6","7"],"rationale":"entry和materialize依赖bridge"},{"wave":5,"tasks":["8","9","10"],"rationale":"前端、公式、IO并行"},{"wave":6,"tasks":["11","12"],"rationale":"守卫依赖实现"},{"wave":7,"tasks":["13","14","15"],"rationale":"C4真栈与统一gate最后"}],"blocking":{"1":"双区instrumentation未修不得生成contract","3":"contract未锁死不得投影","6":"capability未裁决不得在线编辑"}}
```

## Notes

- D4-8 单独排期，不在本 spec 范围。
- 不改契约内核：D4-9 的多 table + 表级标量 + 公式已被 `contracts.py` 现有模型（SheetSpec.tables / CellMapping.static_row / FooterAnchorSpec.carries_total_formula / formula_mask）表达（design §2.1 已核实）。
- 共享文件锁：`oo_to_html.py`、manifest、共享生成器与并发会话冲突时按主控 §5.3 只追加不覆盖、收口一次重生成。


## Common Contract Alignment Gate
- [~] 14. C0-C4 alignment：按总纲验证wp_id身份、共享sync、公式状态、真实DAG/联动与逐表gate；durable ack不等于applied，公式同步不是TB/A13。
  - _Requirements: 2.1, 2.2, 3.1, 8.1_
- [~] 15. C4逐D4-9验收：source/template evidence、三table identity、formula mask、roundtrip、权限、Playwright和变异；只门控D4-9相关产物。
  - _Requirements: 3.1, 8.1_
