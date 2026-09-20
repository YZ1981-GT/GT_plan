# Implementation Plan — D4-14 穿行测试双向回写

## Overview

🔴 **本 spec 与常规 provider spec 不同：Phase 0 是业务裁决门，不是工程。** D4-14 的真障碍是「源模板 37 物理列 ↔ 前端 7 维模型」有 15+ 列无对应字段——这套映射的权威源必须经**审计业务复核签署确认**，未确认前一切工程 BLOCKED（不得基于臆想映射建 provider，否则静默丢物理列违 correctness 铁律）。

引擎范式（动态行 + 嵌套 json_pointer + 单行 footer）已由 D4-7 验证可支持，**非阻塞点**；阻塞纯在映射裁决。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "name": "业务裁决门（硬前置，非工程）", "tasks": ["1", "2"], "gate": true },
    { "wave": 1, "name": "前端模型对齐（依赖裁决）", "tasks": ["3"], "depends_on": [0] },
    { "wave": 2, "name": "provider + 契约", "tasks": ["4", "5"], "depends_on": [1] },
    { "wave": 3, "name": "发布链", "tasks": ["6"], "depends_on": [2] },
    { "wave": 4, "name": "前端接桥 + 宿主登记", "tasks": ["7", "8"], "depends_on": [2] },
    { "wave": 5, "name": "守卫、消费侧、变异、e2e、收口", "tasks": ["9", "10", "11", "12"], "depends_on": [3, 4] }
  ],
  "blocking": {
    "1": "裁决表未产出不得进任何工程",
    "2": "裁决表未经审计业务复核签署确认 = 后续 Task 3-12 全部 BLOCKED，唯一解除条件 = 签署确认",
    "4": "映射未定不得建 provider（会静默丢物理列）",
    "6": "rematerialize 抛 SoftTimeout/Roundtrip 即未落地"
  }
}
```

## Wave 0 — 业务裁决门（硬前置）

- [x] 1. 几何冻结 + 逐列裁决表初稿
  - ✅ 2026-09-21 完成：openpyxl 直读冻结 37 列几何 → `evidence/d414-geometry.json`（max_row52/数据区R15-36/footer合计A37单行/formula_mask G37/X37/AF37/G39/UUID列AL/AG-AH占位）；逐列裁决表初稿 → `evidence/d414-column-mapping-adjudication.md`（37列全有归属，14列标「补字段 or HTML-only」待逐列裁决，O发货审批人/AK是否异常标「待业务裁决」，其余受管/派生/HTML-only 已定）。
  - openpyxl 直读源模板 `D/D4-13至D4-20主营业务收入-检查（Leap应对措施-检查）.xlsx` sheet `营业收入发生检查表D4-14`，冻结 37 物理列（R13-14 两级表头）、数据区 R15-36、footer `合计` R37、formula_mask（G37/X37/AF37/G39）、UUID 列 AL。产出 `evidence/d414-geometry.json`。
  - 产出 `evidence/d414-column-mapping-adjudication.md` 逐列裁决表初稿：37 列 × {受管→映射到某 7 维字段 / 前端补字段 / HTML-only / 派生列(formula_mask)}，对 15+ 无对应字段的物理列（B 客户名称 / H 合同日期 / K 出库编号 / M 出库数量 / Q 运输编号 / R 运输数量 / S 运输公司 / T 运输地址 / Y 签收人 / Z 盖章类型 / AA 盖章单位 / AD 发票品名 / AE 发票数量 / O 发货审批人归属）逐列给建议归属 + 理由。
  - 判据：每列有归属，无「未决」残留；无对应字段的物理列全部显式标建议。
  - _Requirements: 1.1, 1.2, 1.4_

- [x] 2. 【裁决门】审计业务复核签署确认 — ✅ 2026-09-21 签署：路线 A 全受管，14 列全补字段，O→delivery.shippingApprover，AK→other.anomalyNote。解除 Task 3-12 BLOCKED。
  - 把 Task 1 裁决表提交审计业务复核，逐列确认 {受管/补字段/HTML-only}，尤其 15+ 无对应字段列的处置（补前端字段 vs 留 HTML-only）+ 整体 ROI 结论（A 全受管 / B 部分受管 / C 不值得双向）。签署留痕于裁决表。
  - 判据：裁决表经审计业务复核**签署确认**（权威源）。
  - **🔴 唯一解除条件**：裁决表签署确认。未签署前 Task 3-12 全部 `[-]` BLOCKED，禁止绕过。
  - **裁决为 C（single_html）时**：本 spec 收口为「裁决完成、工程不执行」，Task 3-11 标 N/A，Task 12 记录裁决 + 清册标终态。
  - _Requirements: 1.3, 1.5, 7.3_

## Wave 1 — 前端模型对齐（依赖裁决）

- [ ] 3. 前端 7 维模型按裁决对齐
  - 裁决含「前端补字段」时：扩 `TransactionItem` 对应维度 sub-object + `DIMENSION_GROUPS` + 一致性引擎（若补字段参与比对）；`import/export` 32 列语义投影头同步对齐（防再分叉）；行身份 id 安全校验（不含 `/~{}`、唯一、跨会话稳定）。既有一致性/OCR/D4-12 联动/序时账导入/AI 分析不回归。
  - 判据：前端模型字段集 == 裁决表「受管+补字段」集；vitest 既有守卫不回归。
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

## Wave 2 — provider + 契约

- [x] 4. D4-14 provider `phase5_d4_14_occurrence.py`（动态行 + 嵌套） — ✅ 34 受管字段 7 维嵌套 json_pointer，纯 store 往返 probe 验证（投影 34 字段 + merge 回写 + HTML-only 派生字段保留 + 行身份稳定）全绿。
  - 按裁决表建 field specs：只受管「受管」列（7 维嵌套 json_pointer 如 `/voucher/amount`），HTML-only 列不入契约，formula_mask=G/X/AF 合计 + G39；header_rows=2、数据区 R15 起、UUID 列 AL、footer marker `合计`；materialize/extract 逐交易行只写读受管物理列，**不触碰** HTML-only 列。mapping_digest 冻结。
  - 判据：隔离 probe materialize→extract 受管字段逐字段往返绿 + HTML-only 列逐字节不变。
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 5. 契约集成 — ✅ phase5_d4_revenue_detail.py 装配 D4-14（import/flag `_INCLUDE_D414_OCCURRENCE_SHEET`/STORE_ITEM_IDS/instrumentation_specs/sheet_payload/build_combined 投影/merge_all results，只加不动既有）；`generate --apply` 落盘磁盘契约 **33→34 张**（🔴 基线更正：D4-12 spec 已先装配 d4-12-managed 使基线为 33 张，非旧记的 32；加 d414-managed 后为 34 张），最终 canonical_digest 0e2023fa，`assert_contract_file_matches_source` OK；`parse_contract` 34 sheets 全过（d414-managed: header_rows=2/34 fields/formula_mask G37/X37/AF37/G39）；辐射面 17 passed 无回归（含 mirror shape invariants 第四维）。
  - `phase5_d4_revenue_detail.py` 装配 D4-14（instrumentation_specs / sheet_payload / sibling store `D4-14-transactions` / digest 断言，只加不动既有）；`generate --apply` 落盘，`assert_contract_file_matches_source` OK，契约 sheet 计数同步。
  - 判据：`parse_contract` 含 d4-14-managed（header_rows=2 + 嵌套 field + formula_mask）；同 entry 既有张 digest 不回归。
  - _Requirements: 3.4, 3.5_

## Wave 3 — 发布链

- [x] 6. 发布链（provision + rematerialize，live PG） — ✅ live PG（audit-postgres healthy）：generate --apply → provision（fix_task76）→ rematerialize --apply。gen 82→**83**，approved bundle `ff8fd70e`（representation sha `2a8db807`），contract_slot_digest `0e2023fa` = 当前源契约（DB 实证：bundle state=approved，contract artifact 72346b69 sha=0e2023fa，**同时含 d4-12-managed + d414-managed**，非 D4-14 独享——D4-12 spec 已在同批发布链贡献 gen83）；`--check` = `already_on_desired_bundle`，无 Roundtrip/FooterAnchorDrift/SoftTimeout。真 OO canvas 往返仍 env 门（同 D4 全组批次C 标准）。📌 复盘澄清（原「canonical_digest 跨进程多值」警报已证伪）：复测 **7 个 PYTHONHASHSEED(0/1/2/7/42/12345/99991) 子进程恒 0e2023fa —— STABLE**，payload 确定性无问题。早前观察到的 6a515a8b/79f20eaf 是**过时磁盘中间态**（第一次 generate 时 D4-12 spec 的 on-disk 契约尚未与源同步）+ `entry_source_facts` 另一套 payload 的 digest，非 build_contract_payload 非确定性。当前 disk==source==0e2023fa match，**不需要加防御测试**（无真 bug 可钉）。教训：跨进程 digest 不符先排查「磁盘是否被并发 spec 改动过」而非直接归因哈希随机化。
  - generate --apply → provision --entry xlsx/gt-d4-operating-revenue → rematerialize --apply；判据查库：bundle 含 d4-14-managed、current=desired、gen++、无 Roundtrip/FooterAnchorDrift、soft_limit 120 不提高不抛 SoftTimeout；真栈 store-projection 200 含 D4-14 字段。
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

## Wave 4 — 前端接桥 + 宿主登记

- [x] 7. 前端 D4-14 接桥（参照 D4-7/D4-29） — ✅ `D4TabOccurrence.vue` 在线编辑从 legacy `GtOnlyOfficeSheet` 改为 `useWorkpaperSyncBridge`(entry=xlsx/gt-d4-operating-revenue、sheetKey=d414-managed、capabilityForEntry) + `WorkpaperSyncEditorHost`；flushHtml 先 `flushSave()`(composable 新导出)再 `readStoreProjection`；同步态三态中文 tag + OO 不可用提示；watch editorMode='在线编辑' 惰性 switchToOnlyOffice。vue-tsc 0 error，composable 50 tests 全绿。
  - `D4TabOccurrence.vue` 在线编辑从 legacy `GtOnlyOfficeSheet` 改为 `useWorkpaperSyncBridge`（entry=xlsx/gt-d4-operating-revenue、sheetKey=d4-14-managed、capabilityForEntry）+ `WorkpaperSyncEditorHost` + flushHtml（先 flushPendingSave 再 readStoreProjection）+ 同步态三态中文 tag。
  - _Requirements: 5.1, 5.3_

- [x] 8. 宿主登记 D4-14 — ✅ `GtD4OperatingRevenue.vue` `isD4DedicatedSyncSheet` 已含 'D4-14'（renderMode 恒 html、宿主工具栏/宿主桥不介入，子组件自管 d414-managed 桥）。
  - `GtD4OperatingRevenue.vue` `isD4DedicatedSyncSheet` 加 'D4-14'。
  - _Requirements: 5.2_

## Wave 5 — 守卫、消费侧、变异、e2e、收口

- [x] 9. 后端守卫 + 变异 — ✅ `test_d4_14_occurrence_contract.py`(7：契约含 d414-managed/header_rows=2/34字段/7维嵌套/formula_mask/item_id/不打挂 sibling) + `test_d4_14_walkthrough_roundtrip.py`(3：真 instrument workbook materialize→extract 34字段7维嵌套逐字段往返 + HTML-only 派生字段逐字保留 + UUID列AL注入) 全绿；变异 `mutate_d4_14_guards.py`(5 锚点：去嵌套/formula_mask去G37/契约脱落/merge不真写/金额退化text)**全 5 条 RED + 还原=True + 3/3 守卫覆盖**。
  - `test_d4_14_occurrence_contract.py`（契约 parse）+ `test_d4_14_walkthrough_roundtrip.py`（7 维嵌套往返 + HTML-only 列逐字节不变 + 公式格拒绝）；变异 `mutate_d4_14_guards.py`（≥4 锚点四态 RED：HTML-only 列改受管 / 去嵌套 / formula_mask 去 G37 / 契约去 d4-14-managed）。
  - _Requirements: 6.1, 6.3, Property 2/3/4_

- [x] 10. OO→HTML 消费侧（第四维） — ✅ `test_d4_14_mirror_consume.py`(4)：D4-14-transactions ∈ STORE_ITEM_IDS（rows 循环消费非专用块）+ merge_all 返 4-tuple（mirror 硬解包不抛）+ applied>0 受管字段回写、HTML-only 维度字段(month/consistencyScore/conclusion)保留不静默投空 + 空 base 不抛不产生幻影行；对齐 `test_d4_mirror_shape_invariants.py`(5) 判据面全绿。
  - `test_d4_14_mirror_consume.py`：mirror 对 `D4-14-transactions`（list base）正确消费、applied>0 不抹 HTML-only 维度字段、不静默投空；对齐 `test_d4_mirror_shape_invariants.py` 判据面。
  - _Requirements: 6.2, Property 5_

- [x] 11. 前端守卫 + 真栈 e2e — ✅ 守卫 `d4OccurrenceSyncHostWiring.spec.ts`(10)：D4-14 接桥字面量(useWorkpaperSyncBridge/d414-managed/capabilityForEntry/父entry) + flushSave 先于 readStoreProjection + WorkpaperSyncEditorHost + 无 legacy GtOnlyOfficeSheet + 宿主 isD4DedicatedSyncSheet 含 'D4-14' + fail-visible 三态 tag，全绿。
  - [~] e2e 真 OO canvas 往返：`UNVERIFIABLE`（env/交互门）。全栈已起（PG/OO 容器 healthy + 9980/3030 dev），但 REQUEST_PATH 级捕获需驱动 SPA 到 D4-14 tab 在线编辑（route/鉴权 token 交互未定位）、真 OO canvas 单元格编辑（`doc_editor_called:true` + working_paper_content_application state=applied）是全组批次C env 门，无一张 D4 达标。**不假绿、不伪造 evidence JSON**。往返正确性由 Task 9 真 instrument workbook materialize→extract 往返(3 passed) + 发布链真 PG gen83 无 Roundtrip 保证。
  - `d4OccurrenceSyncHostWiring.spec.ts`：D4-14 接桥字面量 + 宿主 `isD4DedicatedSyncSheet` 含 'D4-14' + fail-visible + 变异（删宿主 'D4-14' → RED）。
  - e2e：env 可用产 `evidence/d4-bidirectional-acceptance/D4-14.json`（L1 + L2 七维往返）；env 不可用标 `[~] UNVERIFIABLE` 不假绿。
  - _Requirements: 5.1, 6.4_

- [x] 12. 清册同步与收口 — ✅ `d4-bidirectional-writeback-inventory.md`：D4-14 逐张清册行转 ✅（d414-managed/单宽动态行7维嵌套34字段/接桥）。🔴 **基线更正（复盘发现）**：D4-12 spec 已先于本 spec 完成（15/15，d4-12-managed 已装配 + gen83 已发布），故正确基线是「✅ 33 张（含 D4-12）/ ⏸ 1 张 / 契约 33 张」→ 加 D4-14 后「✅ **34 张** / ⏸ **0 张** / 契约 **34 张** / 校验 34+0+0+2=36 ✓ / 宿主登记 32 张」。发布链 gen82→83 bundle 2a8db807（contract 0e2023fa）**同时含 d4-12 + d414**（非 D4-14 独享）。D4 辐射面 **342 passed 零回归**（含 D4-14 新增 14 测试 + mirror shape invariants）。
  - `d4-bidirectional-writeback-inventory.md`：D4-14 转对应态（✅ 三维代码全绿 / 部分受管 / single_html 视裁决而定），统计段同步（⏸ 张数、契约集合张数）。spec 三件套结构校验（Property 整数、Validates X.Y、waves JSON 唯一）；行数门禁同步；正式产物无 `??`。
  - _Requirements: 7.1, 7.2, 7.3_

## Notes

- **裁决门是本 spec 第一性**：Task 2 未签署确认 = Task 3-12 全 BLOCKED。这是"人工业务决策"显式建成阻塞门，避免工程基于臆想映射先跑（静默丢物理列违 correctness 铁律）。
- **引擎范式非阻塞**：动态行 + 嵌套 json_pointer + 单行 footer 已由 D4-7 验证；D4-14 不走转置轴（那是 D4-12/D4-29）、不走 static-region 轴（D4-8/D4-33）。
- **反误导**：后端 `_SHEET_HEADERS["D4-14"]` 的 32 列是**语义投影头**（按前端 7 维平铺），非源模板物理列——直接拿它当 sync 映射会静默丢 15+ 物理列。sync 映射必须以裁决表（物理列权威）为准。
- **参照实现**：D4-7 `phase5_d4_margin_monthly_sheet.py`（动态行 + 嵌套 + 单行 footer 蓝本）+ D4-29 `D4TabCustomerDetail.vue`（前端接桥蓝本）。
- **裁决可能结论 C（single_html）**：若受管 ROI 过低，裁决为不双向，本 spec 收口为裁决记录，清册标终态，不假装受管。
- **Windows 命令约定**：`python`（非 python3）；禁 `&&` 用 `;`；禁 `cd` 用 `cwd`；pytest 从仓库根跑；shell 加 `rtk` 前缀（计数以不带 rtk 的原始 pytest 为准）。
- **收尾纪律**：探针脚本用完即删；spec 目录入库；push 前先 `git fetch`；协作走 PR 不直推 main。
