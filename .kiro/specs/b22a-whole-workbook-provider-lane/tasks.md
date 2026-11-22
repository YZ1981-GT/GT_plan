# 任务：B22A 整册（whole-workbook）供给链交付 —— provider / 契约 / capability 终裁

> 源起：spec onlyoffice-sheet-open-via-published-artifact 3.4（whole-workbook canary）
> 的阻断链经 2026-11-21 现算确认：10 条 whole-workbook entry 的 per-entry 交付契约 0/10、
> capability 全部未终裁、B22A 宿主 flushHtml 返回空 projection（store 型）。
> 用户裁决（2026-11-21）：建全套 B22A provider + 契约 + capability 终裁，
> 权威册 = B22A-4-1 IT概要（与安徽底稿 54d2cd18 同构），store 用坐标键独立 item，
> 空表合法。

## 结构事实冻结（2026-11-21 openpyxl 直读，禁止凭印象改）

- 权威模板：backend/wp_templates/B/B22A-4-1 IT概要.xlsx，sha256 a509094b8f15beb5a4fb383d598b26567da59e43ce6ed05795411e7970dce7fa，37329 B，2 sheets（正文 + 示例页）
- 受管区：行 7..48、列 A..J；3 个应用程序块（7-20 / 21-34 / 35-48），每块 14 行
- 列语义：A 序号 / B 应用程序 / C 描述 / D 索引号 / E 判断要素类别（块内再分 4 类）/ F 复杂因素 / G 是/否（DV 下拉 G7:G48）/ H 复杂性（**数组公式**）/ I 影响公式 IF(H=..) / J 备注
- H、I 两列全进 formula_mask；G 可编辑；模板存在 100+ 超远 DV 噪声范围（IW/SS/ACO…×48），instrumentation 时需确认不进受管区
- 合并单元格：A/B/C/D/E/I/J 列按块合并（如 A7:A20、E15:E20…）⇒ 物化写值必须走合并区左上角
- 表头 2 行（5/6），footer 行 49（提示文本 A49:J49 合并）
- 无 Excel Table ⇒ 走 instrumentation 注入 GT_B22A41_ROWS + 隐藏 UUID 列 K

## 阶段与验收

- [x] 1 provider 骨架：phase5_b22a_control_matrix.py（ENTRY_ID/ADAPTER_ID=b22a.control_matrix/常量冻结 + assert 3 块结构 + instrumentation_specs 单 sheet）。验收：instrument_workbook_bytes_multi 真模板跑通、GT_B22A41_ROWS 注入、K 列 UUID、往返 extract 字段数=受管格数
  - **2026-11-21 完成**：phase5_b22a_control_matrix.py（常量冻结 / manifest 三重断言 selectable / instrumentation_spec / 双 payload / 真模板 probe）。验收实测：selectable OK（independent=True + whole-workbook 挂载断言 argument=whole-workbook）、template 37329B sha 哨兵一致、template payload 结构哈希 f953d4c8…、instrumentation payload managed_sheets=[b22a41-managed]、注入产物含 GT Table part + _GT_SYNC + 4 个 GT_* definedNames、42 行 UUID（GTROW-B22A41-0007..0048）。🔴 两个实测修正：①manifest 挂载属性形态是 name=bind/argument=whole-workbook（不是 name=whole-workbook）；②首轮写入曾把 IT概要 mojibake 成姒傝（PowerShell GBK 往返）⇒ 文件改用 ASCII-only 源（全部 CJK 用 unicode 转义）重写，从根上消除编码损坏面。
- [x] 2 store 投影与回写：build_store_projection（checklist_responses B22A41-* 坐标键 → FieldValue）+ merge 回写桥（OO→HTML callback 提取后写 item）+ EMPTY_STORE_PAYLOAD 合法声明。验收：空 store 首版可发布（不再 StoreEmptyNotPublishableError）
  - **2026-11-21 done**: b22a_store_merge.py companion (STORE_ITEM_ID=B22A41-rows, ROW_IDENTITY_STORE_KEY=rowId, EMPTY_STORE_PAYLOAD=[] legal, html_store_payload, merge_projection_into_store_rows with formula cols H/I filtered by mode and ghost-row anchor app_name).
  - Main module: RowTableSheetSpec via the shared kernel phase5_row_table_sheet (flat json path = column_key, formula_columns=(H,I), footer_carries_total_formula=False since A49 is a merged note) + build_store_projection facade.
  - Probe: 10 fields, mask=(H7:H48,I7:I48), merge applied=2 with formula keys skipped, ghost row (no app_name) rejected, empty store legal. Contract-level roundtrip runs after phase 3.
- [x] 3 契约交付：build_contract_payload（reviewed_basis 逐格 source_ref）→ 磁盘契约 → DELIVERED_PER_ENTRY_CONTRACTS 登记（delivered_by_task=B22A-canary）。验收：_adjudicate_with_diagnostic 过 L3/L5，L4 仍 undecided
  - **2026-11-21 done**: build_contract_payload (14 fields: 10 row + 4 meta, per-field source_ref/header_source_ref to real cells, html_store section) -> disk contract backend/data/workpaper_sync_contracts/b22a.control_matrix.json -> parse OK review_status=reviewed -> assert_contract_file_matches_source (B60/D4 same canonical-digest kernel).
  - DELIVERED_PER_ENTRY_CONTRACTS: B22A row added (adapter_registered=False, reason records phase-4 gating per AC 1.3). Lane probe: L3 PASSED (was the 2026-11-21 blocker), now L4 capability adjudication = phase 4 boundary.
  - Attribution: 19 pre-existing reds in lane-registry / provider-protocol / regression-gate verified HEAD-preexisting by baseline run with the B22A row removed (byte-identical restore after).
- [x] 4 capability 终裁：manifest 生成器输入源给 B22A 家族终裁 bidirectional + adapter_id（与 registry 报告 zero profile_drift）。验收：assert_projection_lane(projection) 全过
  - **2026-11-21 done**: overlay override for GtB22AControlMatrix.vue (html_store=checklist_responses_b22a41_app_rows, adapter_id=b22a.control_matrix, capability=bidirectional, migration_state=adapter_registered, evidence_patch review_note records the phase 1-3 chain), approved_source_digest refreshed b76adb53->b64c2810 (mount diff = concurrent-session sync-dialog/presentation work, 6 files 210 insertions, no B22A host change).
  - Manifest regenerated: 197 entries / 145 independent / unadjudicated 78->77; B22A now capability=bidirectional + adjudication_state=terminal. Lane probe: LaneVerdict.projection (L1-L5 all pass; L3 was today hard blocker).
  - Downstream generators re-synced: sheet-open bindings --apply 197 / --check OK. B22A sheet-open binding stays pending (correct two-layer semantics: binding state machine advances via reviewed overlay in the parent spec phase 6, after first publication).
  - Guards: 67 passed (sheet-open bindings/resolver/unit/published artifact).
- [x] 5 真实底稿验收：安徽 B22A（54d2cd18）first-publication → entry_state 建行 → descriptor → forcesave → HTML 回读。验收：整册 3.4 的四项证据链
  - **2026-11-21 done (real Anhui acceptance)**: fix_task76 provision --apply created 5 defs + approved bundle (e552b9f3 then 64a9c3de after template split); first-publication 200 (rep 08a0ef7a gen1 rev1); readiness runtime.ready=true, adapter_id=b22a.control_matrix registered, typed_slots_complete=true, can_claim_bidirectional=true, allowed_modes=[html,oo].
  - Two blockers found and fixed en route: (a) provider whitelist -- B22A module added to _ALLOWED_PROVIDER_MODULES (fail-closed working as designed); (b) wp_code adjudication -- explicit B22A entry appended (heuristic bypass forbidden by design); (c) publish-side interface publish_pilot_definitions + resolve_published_frozen_definitions + attach_pilot_adapters added as B60-same-DAG thin shells (shared kernels, no second truth).
  - Template upgrade (user adjudicated footer split): A49 was long text (strip-equal match impossible for the 62-provider shared kernel), A49 now bare marker + long text moved to A50 (merged A50:J50); sha256 a509094b -> 8058b5f0; sentinel + contract + bindings + provision all re-synced; backup tmp_33_repro/B22A-4-1-backup-before-footer-split.xlsx.
- [x] 6 回接 onlyoffice-sheet-open 3.4：reviewed overlay 写 decision=migrated（project_ids 限定安徽 0ec33ac9），重跑生成器，whole-workbook canary 验收
  - **2026-11-21 done (whole-workbook canary closed)**: reviewed overlay decision=migrated (project_ids=[Anhui 0ec33ac9], decision_basis records bundle 64a9c3de + rep 08a0ef7a gen1 + runtime_ready=true); bindings regenerated 197 --check OK, B22A binding now status=migrated with owner recorded (shared-db migrated count 1->2).
  - Canary evidence chain: entry-identity 200 (status=migrated, room_ready=true, allowed_modes=[html,oo], binding_id=sha256:87c24699...); artifact on disk sha256 matches DB, real sheet names B22A-4-1 IT概要 / 【示例】... / _GT_SYNC (console mojibake was PowerShell GBK display only; raw response bytes verified proper UTF-8); materialize-from-store 200 -> descriptor room 869de03a / doc_key wpsync-b7167960e072b5dd94313182-g1 / signed config document.url + callbackUrl present; store-projection 200 (overlay_applied=true, empty-store semantics).
  - No-data-loss check: checklist_responses for Anhui B22A still 0 rows (first publication took the legal empty-store path); entry_state (wp 54d2cd18, gen=1, content_revision=1) created by the real publish chain.

## 红线

- 不复制第二套 instrumentation/contract 内核（全走 Task 17 kernel + build_excel_adapter）
- 磁盘契约与代码双向锁死（assert_contract_file_matches_source）
- 安徽底稿写入型验收保留完整快照，可回滚
- 模板字节哨兵不符即 fail-closed
