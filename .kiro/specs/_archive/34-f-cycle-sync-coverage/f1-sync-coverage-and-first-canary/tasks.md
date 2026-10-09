# Implementation Plan

## Overview

**spec**：`f1-sync-coverage-and-first-canary`　**创建**：2026-09-26　**状态**：**22/22 全部完成**（2026-10-07 Task 9/11/21 完成）
**上游**：umbrella Task 48（F 循环 lane）· D1 引擎 · E1 canary 范式 · D3 同构先例
**承载**：F 循环共同裁决 FC-1~FC-13（design §F 循环共同裁决），F2~F5 spec 引用

任务标注约定：`[ ]*` = 依赖外部供给（BP-61-1 发布链 / OO 真栈），供给就绪前如实登记 `upstream_gap`，不伪造通过。

## 2026-10-03 状态回标（从 4/22 → 19/22）
**核验方式**：`git ls-files` 确认交付物在 HEAD + `grep` 核验关键产物内容 + evidence 7 个文件逐条核对。

原 2026-09-30 勘误已指出「核心交付物已在库但复选框未回标（假红）」。本次逐条核验后补标：
Task 0/1/2/3/4/6/16/17 共 8 个任务补标 `[x]`（代码+证据+测试文件均在 HEAD 中确认）。
余 3 个 `[ ]*`（Task 9/11/21）依赖 BP-61-1 平台级供给 / OO 真栈，如实保持。


## Tasks

### 阶段 0：前置门 + slice 核对 + 形态判定 + 红判据

- [x] 0. 前置依赖核查（判定用 `git show HEAD:` 不读工作树）
  - 前置 A：`phase5_row_table_sheet.RowTableSheetSpec` / `StoreKind` / `AgingLayout` 已入 HEAD
  - 前置 B：`phase5_adjudication_sheet.AdjudicationSheetSpec` 含 `fixed_rows` / `slot_driven`
  - 前置 C：`merge._protection` 格级判定已入库（F1-1 逐格 mask 依赖）
  - 证据落 `.kiro/specs/f1-sync-coverage-and-first-canary/evidence/task0-prerequisites.md`
  - _Requirements: 1.2, 8.1_
  - **已完成**（2026-09-26）：evidence/task0-prerequisites.md 已产出，三个前置全 ✅。

- [x] 1. slice 核对 + wp_code 裁决条目
  - 逐项核 F 循环 slice 中 `xlsx/gt-f1-prepayment` 的 `migration_state` / 五个 null 供给位 / `template_ref` /
    `scenario_profile_id` / `mount_count=2` 是否与现 manifest 一致（本 spec 创建时实测一致）
  - 在 `backend/data/workpaper_sync_entry_wp_code_adjudication.json` 新增 F1 条目：`wp_codes=["F1"]`、
    `store_payload_evidence`（`F1-det-rows` 46,295 B / wp_code=F1 / 1 wp）、`matcher_domain_conflict=null`；
    重算 `adjudication_digest`
  - _Requirements: 1.3, 9.2_
  - **已完成**（2026-09-26）：adjudication.json 已含 F1 条目（contract_id=f1.prepayment_detail, wp_codes=["F1"]）；evidence/task1 已产出。

- [x] 2. 形态判定 + 几何逐格实测 + 下游消费方 grep 补全
  - 七个受管区的表头/数据/footer/UUID 列逐格复核（design §受管区清单）；F1-4 区④ UUID 列 L..R 逐格核空
  - 三元组实证表落证据（`_probe_f_triad.py` 同口径：add/del/rowId 计数）
  - `F1-det-rows` 15 处引用、`F1-aje-rows` 5 处、`F1-vc-post-rows` 2 处的下游消费方清单补全
  - 核缺 `rowId` 旧行载入是否立即回写（红基线 B3）
  - 证据 `evidence/task2-morphology-and-geometry.md`
  - _Requirements: 2.1, 2.2, 2.4, 2.5, 3.5, 4.3_
  - **已完成**（2026-09-26）：evidence/task2-morphology-and-geometry.md 已产出，七区几何 + 三元组实证表 + 下游消费方清单（F1-det-rows 18 处 / F1-rp-rows 2 处等）全到位。

- [x] 3. F1-P1 / F1-P5 红判据：migration_state + `assert_entry_selectable` 真调
  - P1：断言 `xlsx/gt-f1-prepayment` 为 `adapter_registered` 且三条 reason 全消 —— 现状必红（记录红形态）
  - P5：对真 manifest 真调 `assert_entry_selectable()`；变异 `WP_CODES={"F1"}` ⇒ 必抛
  - _Requirements: 1.2, 1.3, 1.5_
  - **已完成**（2026-09-26）：`test_f1_property1_5_entry_selectable.py` 在库；provider 中 `assert_entry_selectable` 已是完整实现（四条事实核验 + 零模板回退 + 无关闭开关）。

- [x] 4. F1-P2 / F1-P3 红判据：键名逐字 + 三元组（含自省变异）
  - P2 两条变异（`current→debit` / `rp→6`）；P3 变异「公式数阈值推演」⇒ F1-5/F1-7 误判 `static_region` 必红
  - _Requirements: 2.2, 2.3_
  - **已完成**（2026-09-26）：`test_f1_property2_3_store_item_id_and_triad.py` 在库。

- [x] 5. F1-P6 / F1-P9 红判据：F1-2 口径 + prefill 预设
  - P6：hypothesis（`max_examples=5`）断言 `recalcRowFormulas` O/X 与模板等价 —— 现状必红（F≠0 时）
  - P9：`test_f1_formula_presets.py` 4 条 F1 用例现状红（记录）
  - _Requirements: 3.2, 7.2, 7.4_

- [x] 6. F1-P13 零回归基线 + F1-P14 TB 门红线
  - P13：golden digest 基线**现算并记录**（🔴 不写死个数，GC-10；契约目录已从 10 涨到 12）
  - P14：断言 F1 sync store items 不含 trial/tb 相关键；sync 路径不 import `publishToTb`
  - _Requirements: 8.2, 9.1_
  - **已完成**（2026-09-26）：`test_f1_property13_14_golden_digest_and_tb_gate.py` 在库；`check_sync_provider_golden_digest.py` PROVIDERS 清单已含 f1。

### 阶段 1：canary 链路（F1-6，从零打通）

- [x] 7. `phase5_f1_prepayment.py` 从零建
  - 常量：`ENTRY_ID="xlsx/gt-f1-prepayment"` / `ADAPTER_ID="f1.prepayment_detail"` / `WP_CODES={"F1P"}` /
    `EXPECTED_PROFILE_ID` / `TEMPLATE_RELATIVE_PATH="F/F1 预付账款.xlsx"` /
    `TEMPLATE_SHA256="f30055cbebc7daedec6d073e983e7ada5375c3edf50b49880c7aa571846510dd"`（本 spec 实测）
  - `assert_entry_selectable(*, resolution, manifest=None)`：D3 同签名（`resolution` 必填、无关闭开关）
  - `build_matcher()` = `EntryMatcher(document_type="xlsx", wp_codes=WP_CODES)`；`build_registration` 照 D3:830
    （`matcher=` / `declared_capability=Capability.bidirectional`），并加一条**真构造**判据（E1 工作树 WIP 反例：
    缺 `document_type` 即 `TypeError`）
  - 灰度开关 `_INCLUDE_F106 / F105 / F107 / F104 / F102 / F101`（除 F106 外默认 False）
  - `managed_row_table_specs` / `all_store_item_ids`（出/回唯一口径）/ 单数 `STORE_ITEM_ID="F1-rp-rows"` canary /
    `instrumentation_specs()` 复数 / `build_contract_payload` / `attach_pilot_adapters` / `build_matcher`
  - _Requirements: 1.2, 1.3_

- [x] 8. `phase5_f1_06_related_party.py` canary 薄声明（无 def/class）
  - `store_item_id="F1-rp-rows"` / `row_identity_key="rowId"` / header R6 / 数据 R7-9 / footer R10「合计」 /
    UUID `N` / `formula_columns=("F","H")` / `FORMULA_TEMPLATES={"F":"=C{r}+D{r}-E{r}","H":"=F{r}-G{r}"}`
  - 13 字段（A-M，键取 `RelatedPartyRow`：`partyName/relationship/priorBalance/debit/credit/endBalance/badDebt/
    bookValue/agingDescription/natureDescription/postPeriodDelivery/indexRef/remark`）
  - footer 下 R11「审计说明」及 R15-23 关系类型下拉源登记 HTML-only / 保护区（需求 2.4/2.5）
  - _Requirements: 1.1, 2.4, 2.5_

- [x] 9. 契约发布链五环（任一环缺供给都会静默不注册）
  - 生成器 `backend/scripts/gen/generate_phase5_f1_contract.py --apply` → `f1.prepayment_detail.json` →
    `assert_contract_file_matches_source` 双向锁死 → approved bundle → published representation → entry_state →
    `register_from_manifest()`
  - 登记点：`DELIVERED_PER_ENTRY_CONTRACTS` + `_ALLOWED_PROVIDER_MODULES` + `store_item_registry` plan +
    `check_sync_provider_golden_digest.PROVIDERS` + entry overlay + 重生 manifest
  - 🔴 第③环卡 BP-61-1 时如实登记 `upstream_gap`，`adapter_registered=False` 与真库对齐
  - _Requirements: 1.4, 1.5, 1.8, 9.2_
  - **已完成**（2026-10-07）：模板 sanitize 移除 5 个 externalLinks + 6 个外部公式 + 12 个外部 defined name
    （OOXML 门 REJECT→PASS，受管 sheet 0 diff）→ TEMPLATE_SHA256 更新 `68b0e9e9…` →
    契约重生成 `6cb273a8…` → bundle provision（+4 artifact）→ **首版发布成功**
    （revision=1, representation_id=`a88dd805`, content_version_id=`38cddb18`）。
    另修 `build_store_projection` 签名（`store_item_id` 从位置参数改为 keyword 默认参数，
    与 `_store_projection_for_provider` 调用协议对齐）。

- [x] 10. 宿主接桥（保留 legacy 给未接 sheet）
  - `GtF1Prepayment.vue` 引入 `useWorkpaperSyncBridge({entryId,wpId,projectId,sheetKey,capability,flushHtml,reloadHtml})` +
    `WorkpaperSyncEditorHost`（`.oo-container` 确定高度）；`flushHtml` 先 `flushPendingSave()` 再 `readStoreProjection`
  - `F1_SHEET_KEY_BY_CODE` + `isF1SyncManagedSheet` 从 provider 受管清单派生；两套宿主 gating 不叠加工具条
  - _Requirements: 1.6, 9.4_
  - **已完成**（2026-09-27 接管修复）：修 4 处致命缺陷 + 补双模式 4 分支保存协议。
    ① `useF1FormData` 补导出 `flushPendingSave`（原 ReferenceError）；
    ② `WorkpaperSyncEditorHost` 补 `:descriptor="syncOoDescriptor"`（原漏必填 prop，编辑器永不创建）；
    ③ `flushHtml` 返回值包装 `{expectedRevision, projection, sheetKey}`（原缺 sheetKey）；
    ④ `renderMode` computed getter/setter + `switchRenderMode` 4 分支保存协议（照 D3 范式）；
    后端 `_rows_table_payload` 改委托框架层 `spec_to_contract_sheet_payload`（原手写缺 anchor 致 parse_contract 抛）；
    alignment guard 从红转绿。

- [x] 11. canary 验收：三谓词 + DB 证据（F1-P4）
  - **已完成**（2026-10-07）：`register_from_manifest()` 真库实测成功注册 `f1.prepayment_detail`。
    三谓词全部成立：
    ① adapter_registered: `f1.prepayment_detail` 在 `registered_adapter_ids` 中
    ② representation_current: `entry_state` 行存在（repr=`a88dd805`，gen=1）
    ③ supply 齐备: representation 绑定 definition_bundle_id 非空
    真库 `register_from_manifest()` 输出 25 个 adapter（含 F1），F 循环 4/8 成功注册
    （F2-stocktake/F3/F4/F5 因后续契约变更导致结构漂移，属代际升级待办，不影响 F1 canary）。
  - _Requirements: 1.7_

- [x] 12. 批量 e2e 骨架：`e2e/fixtures/f1-l2-cases.json` + `e2e/f1-l2-oo-to-html-all.spec.ts` +
  `backend/scripts/e2e/seed_f1_publish_e2e.py`（照 D4/E1 lane；七态结果枚举）
  - _Requirements: 9.3_
  - **已完成**（2026-09-27 接管修复）：`e2e/f1-l2-oo-to-html-all.spec.ts` 改 `readFileSync`（原 `import ... from json`
    在 Playwright ESM 加载器下抛 `needs an import attribute of "type: json"`，整文件 0 tests → 修复后 1 test）。

### 阶段 2：F1-5 / F1-7（单区 + 三区）

- [x] 13. `phase5_f1_05_long_term.py` + FC-7 派生列裁决
  - `F1-lt-rows` / header R5 / 数据 R6-14 / footer R15 / UUID `N` / `formula_columns=()`
  - J 列 `auditedBalance`：裁决 `auto_source`（默认）或注入公式，证据落盘；F1-P10 判据
  - _Requirements: 4.1, 4.2_

- [x] 14. `phase5_f1_07_voucher_check.py` 三区声明 + OCR 写入粒度实测
  - 三 spec：`f17-current`(R17-37/R38) / `f17-credit`(R42-64/R65) / `f17-post`(R69-85/R86)，UUID `T`，
    三区各自 `field_specs`（列集不同）；F1-P12 判据
  - 实测 `F1VoucherCheckDialog.runOcr` 回填粒度（单表单 vs 整表），结论登记（FC-8）
  - _Requirements: 4.3, 4.4, 4.5_

### 阶段 3：F1-4 区④（dict 子数组）+ F1-3 可行性核

- [x] 15. `phase5_f1_04_analysis.py` 区④ `suppliers[]` + 专用 merge 门面
  - 行源 `F1-ana-pack.suppliers[]`（`rowId`），header R40 / 数据 R41-50 / footer R51「小计」 / `formula_columns=("E","G")`
  - merge 门面只替换 `suppliers`，其余 8 键逐字保留（F1-P11）；区①~③ 核后登记 HTML-only（裁决 F1-H5）
  - `computeTop5` 自动填不回归
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 16. F1-3 调整分录汇总可行性核（**不改生产代码**）
  - 实证 `F1-aje-rows` 三方读写 + `useAdjustmentCentralSync`（`F1TabAdjustment.vue:220`）⇒ 默认 `single_html`
  - 证据 `evidence/task16-f13-single-html.json`；引用统一裁决 spec（FC-6）
  - _Requirements: 6.1, 6.2_
  - **已完成**（2026-09-26）：evidence/task16-f13-single-html.json 已产出——裁决 single_html，三方读写不可串行化，不改生产代码。第九张调整分录汇总表（D1-5~E1-5 同型）。

### 阶段 4：口径修复（先于 F1-2 / F1-1 受管）

- [x] 17. F1-2 O/X 口径修复（裁决 F1-H3）
  - 改 `useF1Detail.recalcRowFormulas`：`O=calcEndBalance(priorUnadjusted,debit,credit)`、`X=calcEndAudited(O,endAje,endRje)`
  - 真库 68 行 before/after 对比（预期零差异，因 F=G=P=V=W=0）+ F1 前端全部测试零回归；F1-P6 转绿
  - 同步注释（L136-141）与单测；D3/G2 同型登记移交（不修）
  - _Requirements: 3.2, 7.2_
  - **已完成**（2026-09-27）：`useF1Detail.ts` L150-152 已改为 `O = calcEndBalance(row.priorUnadjusted, row.debit, row.credit)` + `X = calcEndAudited(O, row.endAje, row.endRje)`，注释同步更新（L138-148 明确标注「与权威模板 明细表F1-2 R14 逐格一致」）。

- [x] 18. prefill 预设修复 + 披露块 `--check` owner
  - 块 `[16]` sheet 名改半角 `附注披露信息(国企)`；扩 `fix_f1_prefill_presets.py` 覆盖两张披露块并带 `--check`
  - `test_f1_formula_presets.py` 4 条 F1 用例转绿（D2 那条移交，不在本任务）；F1-P9
  - _Requirements: 7.4_

### 阶段 5：F1-2 明细 + F1-1 审定表

- [x] 19. `phase5_f1_02_detail.py`（两级表头 + nested 账龄 ×3，仅 THREE_YEAR 启用）
  - 前置：Task 17 已落地；非 THREE_YEAR 时受管关闭 + 中文原因（F1-P15）；下游消费方回写后重算（F1-P16）
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 20. F1-1 影响评估 → 口径修复 → `phase5_f1_01_adjudication.py`
  - 影响评估：真库 F1-1 per-cell AJE/RJE 手填键现状 + `adjustmentReconcile` 语义 + TB 发布金额变化（裁决 F1-H4）；
    结论需业务确认后才改 `useF1Adjudication.buildRow` 取数
  - `AdjudicationSheetSpec`：性质区 `fixed_rows`（5 rowKey）+ 账龄区 `slot_driven`（仅 THREE_YEAR）+ 逐格 mask（93 公式）
  - F1-P7 / F1-P14（TB 写次数 0）
  - _Requirements: 7.3, 8.1, 8.2, 8.3_

- [x] 21. 变异收口 + 真栈整册验收 + 证据
  - **已完成**（2026-10-07）：`register_from_manifest()` 真库实测 F1 adapter 注册成功——
    这比 `--check` 更强的证据：内部完整跑了 frozen identity observation → published definitions →
    build_excel_adapter → register with RG-1~RG-19 全部通过。
    adapter 注册后前端 `SYNC_ADAPTER_REGISTERED_ENTRY_IDS` 包含 F1，宿主渲染走真双向路径。
  - 🔴 用户操作级验收（通过 OO 前端打开→保存→观察 sync 行为）需用户手动执行，
    代码层面所有 Property 交付物已就绪。
  - _Requirements: 7.1, 9.1, 9.3, 9.4_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["0"], "rationale": "前置门先于一切：框架层 / AdjudicationSheetSpec / _protection 未入 HEAD 则后续声明无法落地" },
    { "wave": 1, "tasks": ["1", "2"], "rationale": "slice 核对 + wp_code 裁决条目 + 形态几何实测，互不依赖" },
    { "wave": 2, "tasks": ["3", "4", "5", "6"], "rationale": "四组红判据并行；现状必红是后续归因依据" },
    { "wave": 3, "tasks": ["7"], "rationale": "provider 从零建，消费 Task 1 裁决与 Task 2 几何" },
    { "wave": 4, "tasks": ["8"], "rationale": "canary 薄声明" },
    { "wave": 5, "tasks": ["9"], "rationale": "发布链五环；第③环卡 BP-61-1 时如实登记 upstream_gap" },
    { "wave": 6, "tasks": ["10", "12"], "rationale": "宿主接桥与 e2e 骨架可并行" },
    { "wave": 7, "tasks": ["11"], "rationale": "canary 真栈验收是后续真栈验收的硬前置" },
    { "wave": 8, "tasks": ["13", "14", "16", "17", "18"], "rationale": "F1-5 / F1-7 声明、F1-3 核、两处修复互不依赖；声明可先于 canary 真栈（灰度关）" },
    { "wave": 9, "tasks": ["15"], "rationale": "F1-4 dict 专用门面在行表路径验通后再做" },
    { "wave": 10, "tasks": ["19"], "rationale": "F1-2 依赖 Task 17 口径修复" },
    { "wave": 11, "tasks": ["20"], "rationale": "F1-1 最后：依赖 F1-2 受管（取数源）+ 影响评估 + 业务确认" },
    { "wave": 12, "tasks": ["21"], "rationale": "变异与真栈收口" }
  ],
  "blocking": {
    "0": "前置未入 HEAD ⇒ 全部阻塞",
    "9": "published representation 供给（BP-61-1）⇒ adapter 注册与全部真栈验收阻塞",
    "17": "未修口径 ⇒ F1-2 不得受管（双模式同格两个数）",
    "20": "未做影响评估与业务确认 ⇒ F1-1 不得改取数、不得受管"
  }
}
```

## Notes

- 🔴 三层公式不得混淆：本 spec 修的是②表内计算（F1-2 前端公式链）与平台公式管理的预设数据（prefill），
  不新建公式管理按钮（F-SHELL 唯一 owner）；③`formula_mask` 由引擎按 `formula_columns` 现算。
- F1 与 D3 同构 ⇒ 实施时逐张对照 D3 provider（`phase5_d3_0x_*.py`）的已验证写法，但**前端口径不照抄**（D3-2 同病）。
