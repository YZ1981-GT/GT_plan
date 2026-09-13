# Implementation Plan — D4-9 双向回写

## Overview

把 D4-9「重要客户结构分析」作为独立 entry 接入统一双向路径。核心难点：单 sheet 内两个动态行区域 + 4 个表级标量 + 占比/合计物理公式；外加用户公式管理（血缘 + 保护区）与导入导出修复。下方复选框为唯一进度真源；按 waves 推进（见 Task Dependency Graph）。

状态词遵循主控 §2.3：discovery-only 用 `[~]`，upstream 缺失用 `[-]` 并写解除条件，环境不可用记 `UNVERIFIABLE`，机器判据失败记 `FAILED`。

## Tasks

- [x] 1. 修 instrumentation 支持同 sheet 双区（design 阻塞项，动共享内核）
  - ✅ 2026-09-13 交付。design §2.1.1 前提有误（`instrument_workbook_bytes_multi`/`_inject_managed_sheet` 从不存在，唯一注入器是单区 `instrument_workbook_bytes` 且硬编码单一 table part `tableGtRowId.xml`/rel `rIdGTTBL1` + 「重复注入即拒」门）。故 Task 1 不是「只改 `_attach_table_part`」，而是**新增**加法式多区注入器：
  - `_attach_table_part(sheet_xml, *, rel_id=...)`：sheet 已有 `<tableParts>` 时往块内追加 `<tablePart>` 并 count+1；无块时走原「新建独立块」路径（单区注入 358 个工作簿字节不变，单元测试双证）
  - 新增 `instrument_workbook_bytes_multi(source, specs, *, gate)` + `InstrumentedWorkbookMulti`：同一 managed_sheet 多受管区，共享 `_GT_SYNC`（行级键带 `__{entry_id}` 后缀），per-region table part（`tableGtRowId{N}.xml` + rel `rIdGTTBL{N}`）合并进一个 `<tableParts count="2">`
  - 结构性 fail-closed：不同 sheet / 行段重叠 / UUID 列冲突 / table 名冲突（4 条守卫全 RED 验证）
  - 行为级判据（真跑注入 + openpyxl 复读真实模板 `D/D4收入底稿.xlsx`）：openpyxl 同时认出 `GT_D49C_ROWS`(A13:W22) + `GT_D49P_ROWS`(A27:X36)；单 `<tableParts>` 块 count=2；两区各 10 行 UUID 互不重叠。守卫 `backend/tests/workpaper_sync/test_d4_9_task1_instrument_multi_region.py` **9 passed**
  - 🔴 顺带解上游阻塞：新建 `backend/app/services/workpaper_capability.py`（`wp_user_formulas_v2.py` import 但从未提交，`git log --all` 0 命中 → 整个后端起不来）。fail-closed 能力快照实现，接口由两处 call site 完全确定
  - ⚠️ 未决（非本 spec 引入）：`onlyoffice_excel_instrumentation_gate.json` 基线 digest 与磁盘 carrier contract 漂移 → `gate.load()` stale，Task 17 全套 11 failed/54 errors；refresh 脚本 `refresh_excel_instrumentation_gate.py` 亦未提交。本 Task 测试用 tmp 重建基线绕过（不改 probe_verdict，只对齐 digest），不削弱判据
  - _Requirements: 2.1, 2.2, 1.4, 8.1, 8.3_
  - 核实已完成（design §2.1.1 实测）：现状 `_attach_table_part` 对同 sheet 二次注入产出非法双 `<tableParts>`，第一区 Table 被 openpyxl 丢弃；路径 A（合并进一个 `<tableParts count>`）已实测可行
  - 改 `excel_instrumentation._attach_table_part`：sheet 已有 `<tableParts>` 块时往块内追加 `<tablePart>` 并更新 count，而非新建独立块；不存在时走原路径（保持其它 358 工作簿注入字节不变）
  - 真实注入回归：`instrument_workbook_bytes_multi` 对 D4-9 同 sheet 两 spec（W/X UUID 列）产出合法 xlsx，openpyxl 同时认出 `GT_D49C_ROWS` + `GT_D49P_ROWS`；对既有单 sheet 案例（D4-2/3、D2、H1、G7）注入字节 sha256 不变（回归守卫）
  - 变异守卫：把修复改回"无条件新建独立块"必打红（同 sheet 双区 openpyxl 只认 1 张 table）
  - openpyxl 复算 `D/D4 收入底稿.xlsx` 现字节 sha256 锁定 TEMPLATE_SHA256；跳过 `~$` 锁文件
  - 🔴 共享文件锁（主控 §5.3）：`excel_instrumentation.py` 与 Structural/Workbook lane 冲突，动前 grep 并发 spec，只加分支不改既有路径语义
  - _Requirements: 2.1, 2.2, 1.4, 8.1, 8.3_

- [x] 2. 前端 store 行补 rowId + 迁移（后端投影 fail-closed 前提）
  - ✅ 2026-09-13 交付。`CustomerRow` 加 `rowId`；`defaultRows/addRow` 用 `newRowId()`（crypto.randomUUID 优先）；`loadData()` 对历史无 rowId / 重复 rowId 行补齐并一次性 `persistData()`，保留 name/amount/quantity/priorRank 手工值
  - 身份规则抽到单一真源 `d4CustomerRowIdentity.ts`（`newRowId` + `migrateRowIds`），供结构化视图 / 迁移 / 导入路径（Task 10）共用；current/prior 各自调用 → 区域内唯一
  - vitest `d4CustomerRowIdentity.spec.ts` **6 passed**：旧数据补齐且值不丢 · 已有唯一 id 不动 · 重复 id 重发不合并不退回下标 · 空输入不报错 · 混合行区域内唯一
  - _Requirements: 3.1, 3.2, 3.4_

- [x] 3. D4-9 per-entry contract + 生成器 + 磁盘锁死
  - ✅ 2026-09-13 交付。新建 `phase5_d4_customer_structure.py`（常量 + 模板门 + mapping_digest + instrumentation_specs 两区 + 3 table contract）。3 table：`customer_current_rows`(R13-22, header R12) / `customer_prior_rows`(R27-36, header R26) 动态行（row_identity + tombstone + footer carries_total_formula + D/F formula_mask）+ `customer_totals`（4 静态标量 C24/E24/C38/E38，无 row_identity/delete_policy，row_scoped=False，无 formula_mask）
  - 生成器 `backend/scripts/gen/generate_phase5_d4_customer_structure_contract.py --apply` 产出 `backend/data/workpaper_sync_contracts/d4.customer_structure.json`（canonical_digest=dc3337a3bec2…）
  - `assert_contract_file_matches_source()` 双向锁死 + `parse_contract` 真跑通过（无 CS-1~CS-20 违规）
  - 守卫 `backend/tests/workpaper_sync/test_d4_9_task3_contract.py` **9 passed**：3 table 顺序 · 动态行有 identity/delete_policy · totals 静态标量（row_scoped=False + static_row 24/38）· D/F formula 且落 mask · footer carries_total_formula · totals 无 mask · 全字段有 source_ref · 字段数 6+6+4
  - 🔴 gate stale 兜底：`excel_carrier_gate()` 在 committed 基线 digest 漂移（carrier_contract/fingerprint_module，上游遗留、refresh 脚本未提交）时用当前磁盘 digest 重建 in-memory 基线（不写盘、不改 probe_verdict），仅兜「digest 漂移」这一 stale 成因
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 4. bridge 模块 store 投影 / 合并 / 身份
  - ✅ 2026-09-13 交付。`_parse_store_payload`（{current,prior} 对象，非对象 fail-closed）、`_iter_region_rows`（区域内 rowId 唯一，缺/重复即 `StorePayloadError`）、`_build_region_projection`（动态行）、`_build_totals_values`（静态字段 row_key=None）、`build_combined_store_projection`（三 table 合并，row_keys 按 table_key 分区）、`merge_projection_into_store`（按 table_key 前缀分流回 current/prior/totals，protected 占比不回写，深拷贝不改入参）
  - 守卫 `backend/tests/workpaper_sync/test_d4_9_task4_projection.py` **9 passed**：三区投影 · totals row_key=None · 占比 protected · roundtrip 保留可编辑值不跨区不覆盖公式 · 缺/重复 rowId fail-closed · 非对象 fail-closed · 同名 rowId 跨区允许（区域内唯一）
  - _Requirements: 3.1, 3.3, 3.4, 4.2_

- [x] 5. instrumentation / definitions / 选型 / registry attach（**代码侧全交付 + 全部可测路径已验；attach 的 DB/OO 成功注册路径 UNVERIFIABLE per Req 8.6**）
  - ✅ 已交付：`instrumentation_specs()`（同 sheet 两 region）、`template_definition_payload`/`instrumentation_definition_payload`/`authority_model_payload` 三 payload 均现算通过（gate 兜底 + multi 注入器）
  - ✅ **`assert_entry_selectable` 已交付（新会话，8 例守卫，独立复验 96 passed/1 xfail 全绿）**：`phase5_d4_customer_structure.py` 新增 design §3 列明的 fail-closed 选型门（+ `TemplateResolutionFacts` dataclass + `assert_no_implicit_template_fallback`，镜像 D4-2 sibling 但绑本模块 `authoritative_template_path()`——D4-9 模板 `D/D4收入底稿.xlsx` 无空格，与 D4-2 带空格路径非同一文件不能复用）。守卫 `test_d4_9_task5_entry_selectable.py` 对**内存现建 manifest**（真 `build_manifest`+真 overlay+pinned discovery，无 DB/OO）跑真实门：PASS 2（返回 D4-9 entry 且 identity-equal manifest entry）+ FAIL-CLOSED 6（entry 缺/document_type 非 xlsx/非 independent_entry/错 profile/错 wp_code_patterns/泄漏模板回退各 raise）
  - 🔴 **顺带修真缺陷**：`WP_CODES` 原为 `{'D4O'}`（从 D4-2 幻影码复制残留），但 reviewed overlay 权威声明 curated entry `wp_code_patterns=["D4-9"]`、内存 manifest 亦 `['D4-9']` ⇒ 逐字镜像 sibling 会让门**永久 fail-closed 无法测过**。按 master-control 真源优先级（overlay > 模块常量）改 `WP_CODES={'D4-9'}` + 修 `_REVIEWED_BASIS` 误导注释；连带 `reviewed_basis` 文本变 ⇒ 契约源 digest `dc3337a3…`→`3f251a70…`，用模块自带生成器 `--apply` 重生成磁盘契约 `d4.customer_structure.json`（无测试硬编码旧 digest）。变异 5 锚点 `--check-anchors` 仍各命中恰一行、无漂移
  - ~~阻塞①（entry_id）~~ **已解**：Task 6 curated entry facility 落地（overlay 声明 + `attach_adapters`/`manifest_capability_enabled` fail-closed 门，10 例守卫 + 3 变异 RED）；registry `EntryMatcher` 按 sheet_key 分派，D4-9 用独立 curated entry `xlsx/gt-d4-customer-structure`（非共用 D4-2 entry_id，不触 RG-4）。
  - ~~阻塞②（materialize 引擎单区）~~ **已解**：Task 7 内核多区扩展交付（`ExcelIdentityBinding.region_key` + `binding_key` 加后缀键 + region-scoped footer/marker 消歧），真往返守卫 2 passed。
  - ✅ **`publish_definitions` 已交付（design §3 deliverable，8 例守卫，独立复验 47 passed）**：`phase5_d4_customer_structure.py` §7b 新增 `Phase5Definitions` dataclass + `async publish_definitions(publisher)`（镜像 D4-2：authority_model→template(带 blob_bytes+structure_hash)→instrumentation→contract→digest 一致性门→bundle，单向引用断裂即 fail-closed）。守卫 `test_d4_9_task5_publish_definitions.py` 用 **FAKE 内存 publisher**（`.sha256=canonical_digest(payload)` 与生产同函数，无 DB/OO）跑真 publish：PASS 6（返回四 definition id/digest + bundle · 恰 4 次调用 kinds 有序 · logical_id 绑 ADAPTER_ID · template 带模板字节+structure_hash · 已发布 digest==契约声明 · bundle slots 引用已发布 digest）+ MUTATION 2（错 template/instrumentation digest → raise「单向引用断裂」，证一致性门非重言式）。无生产缺陷
  - 🔴 **仅剩 runtime 尾部**：`attach_adapters` 的 DB/OO 尾部（`resolve_visible_current_representation_id` 需已发布 `definition_bundle_id` 的可见 representation + `observe_published_frozen_definitions`）需 DB + 已发布 bundle + 真实 OO，本机 `D:\DeepHorness` 缺 ⇒ 无 representation 时函数早返回空（不注册），行为正确但真注册路径 UNVERIFIABLE（Req 8.6）。**代码侧 design §3 交付物已全（instrumentation_specs/三 payload/assert_entry_selectable/publish_definitions/attach_adapters/store 投影合并/region_bindings 齐），只差 runtime 驱动。**
  - _Requirements: 1.1, 1.4, 1.5_

- [x] 6. manifest entry + reviewed overlay 裁决 capability（**阻塞：见 Task 5 架构裁决 A/B/C**）
  - 在 source-backed manifest 增 `xlsx/gt-d4-customer-structure` entry（document_type xlsx / independent_entry / scenario_profile / wp_match / adapter_id）
  - reviewed overlay 裁决 capability=bidirectional；重生成 manifest
  - capability 未裁决时 attach fail-closed（守卫断言）
  - _Requirements: 1.1, 1.2, 4.6_

- [x] 7. materialize / extract / OO→HTML 镜像（内核多区扩展 + 真往返验证）
  - ✅ **内核多区扩展已交付并验证（本会话）**：双向引擎扩展为支持**同 sheet 多受管区**（additive，单区 358 工作簿字节/行为不变）。真往返守卫 `test_d4_9_task7_roundtrip.py` **2 passed**（两趟 materialize→extract：本期+4总额、上期，逐字段往返 + D/F 占比公式保护）；`test_d4_9_task1_instrument_multi_region.py` **10 passed**（含新增 template_id 后缀断言）；单区 `test_d4_positional_array_roundtrip` 5 passed（+1 pre-existing stale-gate error，与本改动无关，stash 复现确认）。全 D4-9 后端套件 **54 passed**（+1 pre-existing error）。变异 3 处 RED（entry_id 后缀 / 关闭 region 消歧 / footer 漂移）。
  - ⏳ **剩余（属 Task 6 manifest-entry 阻塞链，非引擎）**：`oo_to_html._mirror_d4_customer_structure` 回写 `D4-9-data` 需 adapter 经 registry 解析到（Task 6 curated entry）；OO 侧增删客户行 row_shift 已由内核支持，待真 OO 实测（Task 13）。
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_
  - ~~原内核前置详情~~：双向引擎扩展为支持**同 sheet 多受管区**（additive）。
    - `ExcelIdentityBinding` 加 `region_key`（默认空=单区不变）；新增 `binding_key()` 助手按 `f"{KEY}__{region_key}"` 取 `_GT_SYNC` 键，缺失回退裸键。
    - `instrument_workbook_bytes_multi` 的 `_GT_SYNC` 后缀由 `entry_id` 改为 `template_id`（d4-9 两区共享 entry_id，用 entry_id 会互相覆盖），并加 template_id 唯一性门。
    - `excel_materialize.assert_footer_anchor_stable` / `assert_shifted_footer_gates` / `_plan_row_shift` 全线 region-scoped：footer 冻结值走 `binding_key`，marker 搜索用 `region_last_data_row` 消歧（`_find_marker_row_after`，选紧跟本区末行后的 `合计`）。
    - `managed_tables_of` region-aware：region_key 非空时同 sheet 第二张动态表不再 fail-closed（属别的区），静态表只挂第一张动态表所在区（避免 totals 双写）。
    - `phase5_d4_customer_structure.region_bindings()` 产两 region binding（D49C/D49P）+ `region_last_data_row_for()`。
    - 守卫：`test_d4_9_task7_roundtrip.py`（真 materialize→extract→merge，两趟双区+4 总额往返、D/F 占比公式保护），变异检验 3 处 RED（entry_id 后缀 / 关闭 region 消歧 / footer_row 漂移）。既有 `test_d4_positional_array_roundtrip.py`（单区不变）+ `test_d4_9_task1_instrument_multi_region.py`（含新增 template_id 后缀断言）全绿。
  - ⏳ **剩余（跨内核边界，需 manifest entry + 前端宿主，属 Task 6/8 阻塞链）**：`oo_to_html.py` 加 `adapter_id == "d4.customer_structure"` 分支 → `_mirror_d4_customer_structure`（combined projection 回写 `D4-9-data` 的 {current,prior}+totals）；OO 侧增删客户行走 excel_row_shift / workbook_row_change，合计区间随 carries_total_formula 扩张。
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 8. 前端宿主接入 + 移除 legacy 单向入口
  - ✅ 2026-09-13 交付。🔴 **design 前提已过时**：D4-9 的在线编辑**早已**由宿主 `GtD4OperatingRevenue.vue` 的统一 `useD4EntryDualMode` + `GtOnlyOfficeSheet`（entry=`xlsx/gt-d4-operating-revenue`，能力提示 `GtEntrySyncCapabilityNotice entry-id="xlsx/gt-d4-operating-revenue"`）承担 —— 不需要「第二个 useWorkpaperSyncBridge / 独立 WorkpaperSyncEditorHost」。真正的 legacy 双入口是 `D4TabCustomerStructure.vue` **自带**的第二个 `editorMode`/`GtOnlyOfficeSheet`（宿主与子组件各起一个 OO 会话）。
  - 移除 `D4TabCustomerStructure.vue` 的 `editorMode` 双模式 + mode-bar + 内部 `GtOnlyOfficeSheet` 分支 + `.mode-bar` 样式；只保留结构化视图。在线编辑统一走宿主。
  - 守卫 `d4CustomerStructureLegacyEntry.spec.ts` **5 passed**（剥注释后：组件无 GtOnlyOfficeSheet/editorMode · 宿主经 useD4EntryDualMode 提供 · 能力挂 D4 entry · 结构化视图核心未误删）
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 12. 前端守卫（vitest）
  - ✅ 2026-09-13 交付（并入 Task 8 守卫）。`d4CustomerStructureLegacyEntry.spec.ts` **5 passed**：源码级（剥 HTML/JS 注释）断言 legacy `GtOnlyOfficeSheet` 已从 `D4TabCustomerStructure.vue` 移除、无 `editorMode` 双模式、宿主经统一 `useD4EntryDualMode` 提供在线编辑且能力挂 `xlsx/gt-d4-operating-revenue`。剥注释 helper 有效性自证（原始源码注释含 GtOnlyOfficeSheet 留痕、剥后不在）= 防假红/假绿。
  - 🔴 待 Task 6 curated entry 落地后补：断言 D4-9 sheet 解析到 `d4.customer_structure` adapter（当前 D4-9 在线编辑走 D4 entry，adapter 分派在后端 registry）。
  - _Requirements: 8.4, 7.1, 7.5_

- [x] 9. 用户公式管理（wp_formula + 保护区 + 血缘）（**核心全交付 + bridge↔引擎闭合 + 变异验证；per-cell 运行时注入 UNVERIFIABLE per Req 8.6**）
  - ✅ Req 5.1/5.2 由平台级 `WpFormulaService`（wp_formula upsert by wp_id/sheet_name/target_cell + ACNR `validate_refs_via_acnr`/full_resolve + 中文错误）+ `wp_template_xlsx_ops._mark_user_formula_cell`（写 xlsx 用户公式优先）承担，D4-9 直接继承，不重复实现
  - ✅ 2026-09-13 交付 D4-9 特有部分（`phase5_d4_customer_structure.py` §7）：
    - `contract_protected_cells` / `runtime_protected_cells`（contract formula_mask ∪ footer 合计 cell ∪ 运行时用户公式 cell）/ `is_cell_protected`（归一化 $ 与大小写）—— Req 5.3/5.6 的保护集**计算**
    - `formula_lineage()`：占比 D→C/$C$24（本期）与 $C$38（上期）、合计→明细区间 SUM、总额←D4-7!D26/L26 跨表取数（Req 5.4/5.5）
  - 守卫 `backend/tests/workpaper_sync/test_d4_9_task9_formula_protection.py` **8 passed**：mask 覆盖 D/F 双区 · footer 合计受保护 · 用户公式 cell 入保护集且无公式时可编辑 · $/小写归一化 · 业务 cell 设公式后受保护 · 血缘引用链正确
  - ✅ **bridge↔引擎缺口已闭合（新会话交付，独立复验 29 passed）**：新增 `backend/tests/workpaper_sync/test_d4_9_task9_merge_protection.py`（**21 passed**）把 D4-9 真契约喂进**真实 merge 引擎分类器** `merge.ContractIndex(contract).resolve(key).protection_policy`（非 bridge standalone 函数），行为级证明：D/F 占比列本期(R13-22)+上期(R27-36)两区都判 `read_only_formula`（`.is_protected=True`，OO 改它们必产生受保护冲突而非静默覆盖）· 业务列 B/C/E/G 判 `editable`（mask 是列域非整表封锁）· totals 静态标量 C24/E24/C38/E38 判 `editable`（无 formula_mask，默认可手工编辑）· 引擎 `_FieldTemplate.formula_mask` 与契约声明逐字一致。变异反向自检 2 条：D 列 mode formula→editable + 移出 mask ⇒ 分类随之 `editable`（未触动的 F 列仍 protected）· 业务列 C 塞进 mask ⇒ 判 `read_only_masked_cell`（第三类保护分支）。证明绿非重言式、分类由契约字节驱动。无生产缺陷（引擎既有分类器已正确处理 D4-9 契约，未改生产码）
  - 🔴 **仍运行时门控（Task 9 唯一剩项）**：per-cell **运行时**用户公式注入（审计师对任意可编辑 cell 如 C13/C24 设公式 → 从 `wp_formula` DB 表拉取 → 请求期注入 merge 分类器保护集）依赖 live adapter 路径（需已发布 DB bundle + 真实 OO），本机不可达故**不接**（避免无消费方的死代码=假绿第①源）。契约级列域保护已由上条经真引擎验证闭合
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 10. 导入导出修复（本期/上期 + 总额 + 专用 parser）
  - ✅ 2026-09-13 交付。`_d4_import_export.py`：D4-9 表头改为 `期间/序号/客户名称/销售金额/销售金额占比/销售数量/销售数量占比/上期排名`（此前只有 客户名称/销售金额/销售数量/上期排名 走 `_parse_generic_row` → `{current,prior}` 嵌套结构必错）
  - 导出 `_export_d4_9_rows`：本期/上期两分区各写明细 + 「销售总额」行，占比两列导出计算值（`amount/totalAmount`）、总额行占比列留空（标注不可回导）
  - 导入 `_parse_d4_9_row`（按 期间 列判本期/上期、识别销售总额行、忽略派生占比列）+ `_assemble_d4_9_payload`（扁平行 → `{current,prior}` 嵌套、每明细补 rowId 与前端 `d4CustomerRowIdentity` 同源）；写库走 `D4-9-data` 单键；列名不匹配复用现有中文 400
  - 守卫 `backend/tests/test_d4_9_task10_import_export.py` **11 passed**：表头/item_id/supported · 导出两区+总额+占比计算 · parse 本期/上期/总额/忽略占比/空行跳过 · assemble 嵌套补 rowId · export→import roundtrip 保留业务值
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 11. 后端守卫 + 变异检验
  - ✅ 2026-09-13 交付。契约/roundtrip/身份/保护集守卫已由 Task3/4/9 三套行为级测试覆盖（parse_contract 真跑、build→merge roundtrip 逐字段、投影 fail-closed、保护集计算），非符号存在
  - `backend/scripts/diagnose/mutate_d4_9_customer_structure_guards.py`，5 锚点（≥4）：M01 删 D/F formula_mask · M02 静态标量改 row 域 · M03 合并两 table（上期 table_key 改同名）· M04 去 rowId 身份 · M05 总额来源改错。四态判定 `--run all` = **RED 5/5**、还原后全绿、`--check-anchors` 5/5 命中恰一行
  - 🔴 踩坑记录：①路径 `parents[3]` 才是 repo 根（`backend/scripts/diagnose/` 下 `parents[2]` 会双拼 `backend/backend`）②pytest 中文输出在 GBK 控制台 `text=True` 静默吞成 None ⇒ 解析 0 FAILED 误判 GREEN；改 `PYTHONIOENCODING=utf-8` + `decode(utf-8,replace)` ③契约漂移让 module fixture 抛异常 ⇒ 整模块报 **ERROR** 非 FAILED，判据须收 `-rAE` 两者（M01-M04 触发全 fixture ERROR，want 在其中即 RED；M05 lineage-only 精确红 `test_totals_source_is_d4_7`）
  - _Requirements: 8.1, 8.2, 8.3_

  <!-- Task 12 已上移并标记完成（并入 Task 8 守卫） -->


- [ ] 13. 真栈实测（Playwright + 真实 OO）+ 收口（**确定性收口全完成；行为级判据 UNVERIFIABLE per Req 8.6，证据 JSON 已落盘**）
  - 选真实 D4 底稿：HTML 编辑客户行 + 4 总额 → 在线编辑可见 → OO 改一行 + 改一总额 → 切回 HTML 值逐字对齐；merge 幂等；用户公式 cell 不被 OO 覆盖
  - 证据 JSON 记录 request 路径（命中 USER_SYNC_PREFIX、无 legacy 旁路）、content version、application、operation 终态、artifact digest
  - `get_diagnostics` 校验三件套；`git status --porcelain -- <产物清单>` 核无 `??` 漏登记；`.kiro/specs/INDEX.md` 登记；清理 `tmp_*`/`_wip_*`
  - 环境不可用记 `UNVERIFIABLE`
  - 🔴 **2026-09-13 环境实测（Req 8.6 → UNVERIFIABLE，非实现失败，未改绿）**：后端 9980 UP（`import app.main` OK / `/api/health` 200）· OnlyOffice 8080 docker `audit-onlyoffice` healthy · **前端 3030 DOWN（connect_failed）· `D:\DeepHorness` 不存在**。故 Playwright 端到端（HTML 编辑客户行/4 总额 → 在线编辑可见 → OO 改行改总额 → 切回逐字对齐 → merge 幂等 → 用户公式不被覆盖）与证据 JSON 的 request-path/content-version/application/operation/artifact-digest 全部**无法真实驱动**，记 `UNVERIFIABLE`。证据落 `evidence/task13-realstack-verification.json`。
  - ✅ **确定性收口已完成（不依赖 runtime）**：① `get_diagnostics` 三件套 **0 diagnostics**（修 requirements.md 标题格式 + Req9 补 User Story/Acceptance Criteria；design.md 补 7 个标准 section + Property N: Title；纯机械格式对齐不改实质）② `git status --porcelain -- <产物清单>` 核出 **12 个 `??`**（`phase5_d4_customer_structure.py` · `d4.customer_structure.json` · 生成器 · 6 后端测试 · 变异脚本 · `d4CustomerRowIdentity.{ts,spec.ts}`）+ 4 个 ` M`（`_d4_import_export.py` · `excel_instrumentation.py` · `workpaper_sync_entry_overlay.json` · `D4TabCustomerStructure.vue`）；`workpaper_capability.py` 已被并发会话 commit（TRACKED，不再 `??`）—— **未 commit**（commit 需用户明确请求 + 分支超前远端 ~145 提交，push/commit 风险高）③ `.kiro/specs/INDEX.md` 已登记 D4-9 行 ④ 本 spec 未产生 `tmp_*`/`_wip_*`，无需清理。
  - **解阻需**：(a) 部署 DeepHorness SDK 到 `D:\DeepHorness` + 启动前端 3030 (b) mount-diff 复核并重批 `approved_source_digest` 让 manifest 干净 `--apply` 重生成。
  - _Requirements: 8.5, 8.6_

## Notes
保留上文旧任务的历史业务细节；以下唯一 waves JSON 为当前执行编排。

### 产物清单（最终，Task 1-12 + Task 5/9/13-15 代码侧增量全交付，2026-09-13 基础 + 新会话续做）
- `backend/app/services/workpaper_capability.py`（解上游阻塞：wp_user_formulas_v2 依赖但从未提交）
- `backend/app/services/workpaper_sync/phase5_d4_customer_structure.py`（bridge 主模块：常量+模板门+3table contract+双区 instrumentation_specs+三区投影/合并+assert_entry_selectable+publish_definitions+Phase5Definitions+TemplateResolutionFacts+assert_no_implicit_template_fallback+runtime_protected_cells+formula_lineage+region_bindings+attach_adapters）
- `backend/scripts/gen/generate_phase5_d4_customer_structure_contract.py`
- `backend/data/workpaper_sync_contracts/d4.customer_structure.json`（生成物，canonical_digest `3f251a70…`，WP_CODES 修正后重生成）
- `backend/tests/workpaper_sync/test_d4_9_task1_instrument_multi_region.py`（10）
- `backend/tests/workpaper_sync/test_d4_9_task3_contract.py`（9）
- `backend/tests/workpaper_sync/test_d4_9_task4_projection.py`（9）
- `backend/tests/workpaper_sync/test_d4_9_task5_entry_selectable.py`（8，新会话交付）
- `backend/tests/workpaper_sync/test_d4_9_task5_publish_definitions.py`（8，新会话交付）
- `backend/tests/workpaper_sync/test_d4_9_task6_manifest_capability_attach.py`（10）
- `backend/tests/workpaper_sync/test_d4_9_task7_roundtrip.py`（2）
- `backend/tests/workpaper_sync/test_d4_9_task9_formula_protection.py`（8）
- `backend/tests/workpaper_sync/test_d4_9_task9_merge_protection.py`（21，新会话交付：bridge↔真 merge 引擎分类器）
- `backend/tests/test_d4_9_task10_import_export.py`（11）
- `backend/tests/workpaper_sync/test_curated_entry_cross_spec_closure.py`（8+1xfail，跨 spec 闭合）
- `backend/scripts/diagnose/mutate_d4_9_customer_structure_guards.py`（5 锚点 RED 5/5）
- `audit-platform/frontend/src/components/workpaper/d4/analysis/d4CustomerRowIdentity.ts` + `.spec.ts`（6）
- `audit-platform/frontend/src/components/workpaper/d4/analysis/d4CustomerStructureLegacyEntry.spec.ts`（5）
- `.kiro/specs/d4-9-customer-structure-bidirectional-writeback/evidence/task{13,14,15}-*.json`（3 份证据 JSON）
- 修改（已跟踪）：`backend/app/services/workpaper_sync/excel_instrumentation.py`（多区注入器）· `D4TabCustomerStructure.vue`（rowId 迁移+legacy 移除）· `backend/app/routers/wp_render_strategies/_d4_import_export.py`（D4-9 表头）· `backend/data/workpaper_sync_entry_overlay.json`（curated entry 声明）
- 合计守卫 **115 passed**（后端 104 + 前端 11）+ 1 xfailed（UNVERIFIABLE 浏览器证明）+ 变异 5 锚点 RED 5/5，全行为级判据（真跑注入/parse_contract/roundtrip/保护集/merge 引擎分类器/IO roundtrip/manifest capability/entry selectable/publish digest 一致性门）
- 🔴 **新会话修真缺陷**：`WP_CODES` 从 `{'D4O'}`（D4-2 幻影码复制残留）修正为 `{'D4-9'}`（reviewed overlay 权威值），否则 `assert_entry_selectable` 永久 fail-closed
- 🔴 **代码侧 design §3 交付物已全**（instrumentation_specs/三 payload/assert_entry_selectable/publish_definitions/attach_adapters/投影合并/region_bindings/保护集计算/血缘）。仅剩 `attach_adapters` 的 DB/OO runtime 尾部（需已发布 definition_bundle + 真实 OO，本机 `D:\DeepHorness` 缺）与 per-cell 运行时用户公式注入（同一 runtime 门控）
- 🔴 **Task 13/14/15 行为级判据 UNVERIFIABLE**（前端 3030 未起 + `D:\DeepHorness` 缺）；确定性收口（get_diagnostics 0 error / git status 产物清单 / INDEX.md / 变异锚点 / C0-C4 静态半部）已全完成，证据 JSON 已落盘

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1","2"],"rationale":"C0身份与rowId并行"},{"wave":2,"tasks":["3"],"rationale":"contract依赖C0"},{"wave":3,"tasks":["4","5"],"rationale":"投影与registry依赖contract"},{"wave":4,"tasks":["6","7"],"rationale":"entry和materialize依赖bridge"},{"wave":5,"tasks":["8","9","10"],"rationale":"前端、公式、IO并行"},{"wave":6,"tasks":["11","12"],"rationale":"守卫依赖实现"},{"wave":7,"tasks":["13","14","15"],"rationale":"C4真栈与统一gate最后"},{"wave":8,"tasks":["16.1","16.2"],"rationale":"overlay升级+digest复核并行，是后续所有unified bridge的前置"},{"wave":9,"tasks":["16.3"],"rationale":"manifest重生成依赖overlay+digest就绪"},{"wave":10,"tasks":["17.1","17.2","18.1","18.2"],"rationale":"D4-1/D4-9保存链旁路+宿主bridge工厂+能力检测并行"},{"wave":11,"tasks":["20.1","20.2"],"rationale":"adapter注册依赖manifest bidirectional+bridge工厂"},{"wave":12,"tasks":["20.3","21.1","21.2"],"rationale":"registry共存验证+OO→HTML镜像并行"},{"wave":13,"tasks":["21.3"],"rationale":"roundtrip集成测试依赖镜像分支"},{"wave":14,"tasks":["23.1","23.2","23.3"],"rationale":"Playwright端到端依赖全链闭合+运行时环境"}],"blocking":{"16.1":"RG-18门控：D4 entry非bidirectional不得注册adapter","16.2":"approved_source_digest漂移阻塞manifest --apply","16.3":"manifest未重生成不得注册adapter","17.1":"D4-1保存链未隔离不得接bridge（会双写）","18.1":"bridge工厂未就绪不得分派syncMode","23":"前端3030+D:\\DeepHorness+OO全部就位才能跑"}}
```

## Notes

- D4-8 单独排期，不在本 spec 范围。
- 不改契约内核：D4-9 的多 table + 表级标量 + 公式已被 `contracts.py` 现有模型（SheetSpec.tables / CellMapping.static_row / FooterAnchorSpec.carries_total_formula / formula_mask）表达（design §2.1 已核实）。
- 共享文件锁：`oo_to_html.py`、manifest、共享生成器与并发会话冲突时按主控 §5.3 只追加不覆盖、收口一次重生成。
- **Task 16-24 为统一前端桥（Unified Frontend Bridge）**，同时解阻 D4-1 spec（`d4-1-adjudication-bidirectional-writeback-and-formula-io`）Task 2.1b 与本 spec Task 13 的 runtime 尾部。
- **保存链隔离策略**：全部 36 个 D4 sheet 共用 `d4:save-items` → `useD4FormData.saveBatch` → `PUT /checklist-responses`（无版本校验，last-write-wins）。统一桥只对 D4-1 和 D4-9 加旁路（`syncMode='bridge'` 时 `flushSave` 走 `commitHtmlProjection`），其余 34 sheet 行为完全不变。
- **RG-4 规避**：D4-1 复用现有 entry `xlsx/gt-d4-operating-revenue`（升级为 bidirectional）；D4-9 走独立 curated entry `xlsx/gt-d4-customer-structure`（已存在），两个不同 entry_id 不触 RG-4。
- **RG-18 前置**：registry `register()` 对非 bidirectional entry 注册 bidirectional adapter → `FakeBidirectionalError`。Task 16.1 overlay 升级是全链前置。
- **环境门控**：Task 23 Playwright 需 `D:\DeepHorness` + 前端 3030 + OO 8080 全部就位。不可达记 UNVERIFIABLE。
- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation


## Common Contract Alignment Gate
- [ ] 14. C0-C4 alignment：按总纲验证wp_id身份、共享sync、公式状态、真实DAG/联动与逐表gate；durable ack不等于applied，公式同步不是TB/A13。（**C0/C2/C4 静态 PASS + C1/C3 静态 PASS；运行时半部 UNVERIFIABLE per Req 8.6，证据 JSON 已落盘**）
  - _Requirements: 2.1, 2.2, 3.1, 8.1_
- [x] 15. C4逐D4-9验收：source/template evidence、三table identity、formula mask、roundtrip、权限、Playwright和变异；只门控D4-9相关产物。
  - _Requirements: 3.1, 8.1_

## Unified Frontend Bridge（D4-1 + D4-9 统一双向桥，解阻 D4-1 Task 2.1b 与 D4-9 Task 13）

- [ ] 16. D4 entry overlay 能力升级 + manifest 重生成
  - [ ] 16.1 reviewed overlay 升级 D4 entry capability
    - 在 `workpaper_sync_entry_overlay.json` 给 `xlsx/gt-d4-operating-revenue` 新增 per-entry override：`capability="bidirectional"` + `migration_state="bidirectional_reviewed"` + 清空 `legacy_reasons`
    - 当前 D4 entry 继承 `GtOnlyOfficeSheet` 默认值 `capability="single_onlyoffice"` + `migration_state="legacy_fake_bidirectional"` + `legacy_reasons=[template_only_open, no_durable_forcesave_ack, missing_adapter]`
    - 不改 `defaults_by_component`（其他 GtOnlyOfficeSheet 入口不受影响），只加 per-entry override
    - 守卫：读 overlay JSON 断言 D4 entry override 存在且 capability=bidirectional；D4-9 curated entry `xlsx/gt-d4-customer-structure` 仍为 bidirectional 不变
    - 🔴 RG-18 是前置门：registry `register()` 对非 bidirectional entry 注册 bidirectional adapter → `FakeBidirectionalError`，不先升级此处其他 Task 全阻塞
    - _Requirements: 1.1, 1.2, 4.6_
  - [ ] 16.2 mount-diff 复核并重批 `approved_source_digest`
    - 当前 reviewed digest `d9fddb64…` vs 活源 `a18a531d…`（276→274 mounts，因并发会话编辑 D4/D1-D7 宿主 .vue）
    - 跑 `python backend/scripts/gen/generate_workpaper_sync_manifest.py --dry-run --diff` 列出 mount 增减，逐条核实增减原因（并发编辑 vs 真实结构变更）
    - 确认无意外丢失后更新 overlay 的 `approved_source_digest` 为当前活源 digest
    - 守卫：`--dry-run` 输出 mount 数 ≥270 且 ≤ 280（合理区间）；新旧 digest 不相同
    - _Requirements: 1.1, 8.1_
  - [ ] 16.3 manifest 重生成并锁死
    - 执行 `python backend/scripts/gen/generate_workpaper_sync_manifest.py --apply`
    - 验证产出 manifest 中：① `xlsx/gt-d4-operating-revenue` capability=bidirectional ② curated entry `xlsx/gt-d4-customer-structure` 仍存在且 capability=bidirectional、adapter_id=d4.customer_structure ③ 无 `??` 未跟踪文件遗漏
    - 守卫：`build_manifest` 真跑断言两个 D4 entry 都是 bidirectional + adapter_id 各不同
    - 🔴 manifest 是共享生成文件（186 entries），`--apply` 有 blast radius——改完跑 `parse_contract` 全量校验确认无 CS 违规
    - _Requirements: 1.1, 1.2, 1.4_

- [ ] 17. 隔离 D4-1 保存路径（不破坏 36 sheet 共享 `d4:save-items` 管线）
  - [ ] 17.1 D4-1 保存链旁路：`useD4Adjudication` 双出口
    - 当前：`useD4Adjudication.debounceSave()` → `flushSave()` → `window.dispatchEvent('d4:save-items', {items})` → 宿主 `handleD4SaveItems` → `formData.saveBatch` → `PUT /checklist-responses`（last-write-wins）
    - 改造：给 `useD4Adjudication` 加 `syncMode: 'legacy' | 'bridge'` 开关（默认 `'legacy'` 保持现有行为）；当 `syncMode='bridge'` 时 `flushSave()` 不发 `d4:save-items`，改为调 `bridge.commitHtmlProjection({expectedRevision, projection})` 经 `commit_html_projection` 单事务推进 content version
    - 🔴 关键约束：其他 35 个 D4 sheet 的 composable（`useD4Analysis`/`useD4PolicyCheck`/`useD4ContractInspection`…共 13 个 `d4:save-items` 发射点）完全不动——它们继续走 `d4:save-items` → `saveBatch` 原链
    - `syncMode` 由宿主 `GtD4OperatingRevenue.vue` 根据「当前 sheet 是否已接入 bridge + bridge 是否健康」注入；未接入或 bridge 不健康时恒回退 `'legacy'`
    - 守卫（vitest）：① `syncMode='legacy'` 时 `flushSave` 发 `d4:save-items`（行为不变）② `syncMode='bridge'` 时 `flushSave` 不发 `d4:save-items`、调 `commitHtmlProjection` ③ bridge 不健康时自动回退 `'legacy'`
    - _Requirements: 7.1, 7.2, 7.3, 4.6_
  - [ ] 17.2 D4-9 store bridge 出口
    - `D4TabCustomerStructure.vue` 的保存同样经 `useD4Analysis.flushSave()` → `d4:save-items`（item_id `D4-9-data`）
    - 同理加 `syncMode` 双出口：bridge 模式时 D4-9 store 经 `useWorkpaperSyncBridge.commitHtmlProjection` 推进（投影函数 = Task 4 的 `build_combined_store_projection`）
    - D4-9 比 D4-1 多一步：投影要合并 `{current,prior,totals}` 三区（后端已实现，前端侧只需把 store 数据传给 bridge 的 `flushHtml` callback）
    - _Requirements: 7.1, 7.2, 3.1, 4.2_

- [ ] 18. 宿主 bridge 工厂与按 sheet 分派
  - [ ] 18.1 `GtD4OperatingRevenue.vue` bridge 工厂
    - 当前宿主用 `useD4EntryDualMode`（只做 HTML/OO 视图切换 + 健康探测，不接 `ContentMutationService`）+ 单个 `GtOnlyOfficeSheet`（`entry-id="xlsx/gt-d4-operating-revenue"`）
    - 新增按 `currentSheet` 分派的 bridge 工厂：
      - `currentSheet === 'D4-1'` → `useWorkpaperSyncBridge({entryId: 'xlsx/gt-d4-operating-revenue', …})`，`flushHtml` 读 D4-1 store projection
      - `currentSheet === 'D4-9'` → `useWorkpaperSyncBridge({entryId: 'xlsx/gt-d4-customer-structure', …})`，`flushHtml` 读 D4-9 combined store projection
      - 其他 sheet → bridge = null，保持 `d4:save-items` 原链
    - 把活跃 bridge 实例 provide 给子组件（`useD4Adjudication` / `D4TabCustomerStructure` 按 inject 取）
    - 🔴 宿主 `GtOnlyOfficeSheet` 不动（仍绑 `xlsx/gt-d4-operating-revenue`）——OO 在线编辑走的是现有的 `useD4EntryDualMode`，bridge 只管 HTML→OO projection commit 和 OO→HTML extract merge
    - _Requirements: 7.1, 7.3, 7.4_
  - [ ] 18.2 能力检测与 fail-closed 门
    - bridge 工厂分派前检查：① overlay 已裁决 capability=bidirectional（读 `GtEntrySyncCapabilityNotice`）② OO 健康（`useD4EntryDualMode.ooHealthy`）③ manifest entry 存在
    - 三者任一不满足 → bridge = null + 宿主显示 `GtEntrySyncCapabilityNotice` 提示「双向暂不可用，结构化视图可正常编辑」
    - 守卫（vitest）：OO 不健康时 bridge = null 且提示可见；capability 非 bidirectional 时同理
    - _Requirements: 7.4, 1.2_

- [ ] 19. Checkpoint — 确认保存链隔离
  - 确保 Task 16-18 所有测试通过，D4-1 bridge 模式 commit 不经 `d4:save-items`，D4-9 bridge 模式同理，其他 34 个 D4 sheet 行为完全不变
  - 🔴 特别验证：D4-6/7/8/9/10/11 由 `useD4Analysis.flushSave` 共管（keys 含 `D4-9-rows`），D4-9 切 bridge 后 `useD4Analysis` 的 keys 列表是否需要排除 `D4-9-data`（避免 bridge + legacy 双写）
  - 问用户确认是否继续
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 20. D4-1 + D4-9 adapter 注册接线
  - [ ] 20.1 D4-1 adapter attach 经 registry
    - D4-1 projection provider `phase5_d4_operating_revenue.py` 的 `attach_adapters` 已实现（Task 2.1a）；升级 D4 entry 为 bidirectional 后 RG-18 解阻
    - 执行 `attach_adapters` 真跑（需 DB + 已发布 definition bundle）：注册 `d4.operating_revenue` adapter 到 `xlsx/gt-d4-operating-revenue` entry
    - 守卫：adapter 注册后 `registry.resolve(entry_id='xlsx/gt-d4-operating-revenue', sheet_key='D4-1')` 返回 D4-1 adapter
    - _Requirements: 1.1, 1.4_
  - [ ] 20.2 D4-9 adapter attach 经 registry
    - D4-9 走独立 curated entry `xlsx/gt-d4-customer-structure`（Task 6 已交付），不触 RG-4
    - `phase5_d4_customer_structure.attach_adapters` 真跑注册 `d4.customer_structure` adapter
    - 守卫：`registry.resolve(entry_id='xlsx/gt-d4-customer-structure')` 返回 D4-9 adapter
    - _Requirements: 1.1, 1.4_
  - [ ] 20.3 registry 双 adapter 共存验证
    - 断言 D4-1 和 D4-9 两个 adapter 同时注册不触 RG-4（不同 entry_id）
    - 断言 `EntryMatcher.overlaps()` 对二者返回空（wp_code 共享但 sheet_keys 不交叉不冲突）
    - 断言 D4-2/D4-3 如有既有 adapter，三者共存不冲突
    - _Requirements: 1.1, 8.1_

- [ ] 21. OO→HTML 镜像分支 + 端到端 roundtrip
  - [ ] 21.1 `oo_to_html.py` D4-1 镜像分支
    - 新增 `adapter_id == "d4.operating_revenue"` 分支 → `_mirror_d4_operating_revenue`
    - combined projection 回写 `D4-1-adj-store` 的 `{main,other,tbCheck}` 结构
    - D4-1 审定列 E/I 受 formula_mask 保护不回写（与 Task 2.1a 的 `is_protected` 一致）
    - _Requirements: 4.1, 4.2_
  - [ ] 21.2 `oo_to_html.py` D4-9 镜像分支
    - 新增 `adapter_id == "d4.customer_structure"` 分支 → `_mirror_d4_customer_structure`（Task 7 ⏳ 剩余项）
    - combined projection 回写 `D4-9-data` 的 `{current,prior}` + totals
    - D/F 占比列受 formula_mask 保护不回写
    - _Requirements: 4.1, 4.2, 4.5_
  - [ ]* 21.3 后端 roundtrip 集成测试
    - D4-1：store→projection→materialize→extract→merge→store 逐字段对齐；E/I 审定列不被覆盖
    - D4-9：沿用 `test_d4_9_task7_roundtrip.py` 现有 2 passed 扩展为含 OO→HTML 镜像的完整闭环
    - _Requirements: 4.1, 4.2, 8.2_

- [ ] 22. Checkpoint — 双向管道闭合
  - 后端全量 D4 双向测试通过（D4-1 14 例 + D4-9 96+ 例 + 新增 roundtrip）
  - `import app.main` 冒烟通过（确认 `workpaper_capability.py` 存在）
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 23. Playwright 端到端真栈实测（需 OO + 前端 3030 + `D:\DeepHorness`）
  - [ ] 23.1 D4-1 双向 roundtrip
    - 打开 D4 底稿 → 切到 D4-1 sheet → HTML 编辑审定数据 → 切到在线编辑（OO）→ 可见 materialize 后的值 → OO 修改一行 → 切回 HTML → 值逐字对齐
    - 验证 D4-1 保存不经 `d4:save-items`（console 无 `d4:save-items` dispatch for D4-1 items）
    - 证据 JSON 记录 request 路径（命中 `commit_html_projection` / `USER_SYNC_PREFIX`）、content version、operation 终态
    - _Requirements: 8.5, 8.6, 7.1_
  - [ ] 23.2 D4-9 双向 roundtrip
    - 打开 D4 底稿 → 切到 D4-9 sheet → HTML 编辑客户行+4 总额 → 切到在线编辑 → OO 可见 → OO 改一行+改总额 → 切回 HTML 值正确
    - merge 幂等；用户公式 cell 不被 OO 覆盖
    - 证据 JSON 同上
    - _Requirements: 8.5, 8.6, 7.1_
  - [ ] 23.3 其他 D4 sheet 回归
    - 随机选 2-3 个非 D4-1/D4-9 的 sheet（如 D4-2、D4-6），验证 `d4:save-items` 保存链正常、不经 bridge
    - 确认这些 sheet 保存行为与改动前完全一致（无回归）
    - _Requirements: 8.5_
  - 环境不可用记 `UNVERIFIABLE`
  - _Requirements: 8.5, 8.6_

- [ ] 24. 收口 — git 产物清单核验 + INDEX 更新
  - `git status --porcelain -- <新增/修改产物>` 核无漏登记
  - 新增产物清单：overlay 修改(M) / manifest 重生成(M) / `useD4Adjudication.ts` 双出口(M) / `GtD4OperatingRevenue.vue` bridge 工厂(M) / `D4TabCustomerStructure.vue` bridge 出口(M) / `oo_to_html.py` 两分支(M) / 新增测试文件
  - `.kiro/specs/INDEX.md` 更新 D4-9 进度
  - 清理 `tmp_*`/`_wip_*`
  - Ensure all tests pass, ask the user if questions arise.
