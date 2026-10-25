# L 循环真双向改线（adapter 注册）— 需求

## 背景

`l-cycle-sync-foundation-and-first-canary` 及其两份 lane spec 已标 37/37 + 22/23 + 26/27
「完成」，但 **manifest 里 L 域 8 条 entry 仍全部是 `legacy_fake_bidirectional` /
`capability=single_onlyoffice` / `adapter_id=null`**。复核那三份 spec 的任务正文后确认：
36 条任务里动生产代码的只有两条（Task 32 删 orphan `useL1DualMode.ts`、Task 33 notice 落位），
其余全是「现算 / 断言 / 变异证明」。**它们交付的是判据体系，不是改线**，这一点与 spec 名里的
`foundation` 相符，与 `first canary` 不符。

本 spec 只做一件事：**把 L 循环真正接成双向回写**，验收口径是 manifest 的
`migration_state` / `capability` / `adapter_id` 现算翻转，不接受「勾选完成」作为证据。

🔴 既有三份 L spec **一律不回填修改**（append-only 审计轨迹）。本 spec 是它们的后继，
勘误与前提推翻都登记在本文件。

## 实证基线（2026-09-28 现算，全部可复算）

| 事实 | 现算值 | 取证方式 |
|---|---|---|
| entry manifest 总 entry | 155 | `backend/data/workpaper_sync_entry_manifest.json` |
| `legacy_fake_bidirectional` | **135**（stats 段自报 137，两处不一致） | 同上，逐 entry 扫 |
| `adapter_registered` | **6**：a51 / d1 / d2 / d4 / g7 / h1 | 同上 |
| `capability_target` 非空 | **0 条** | 同上（slice 里有，主 manifest 没有） |
| L 域 entry | 8 条全 legacy，`adapter_id` 全 null | 同上 |
| reviewed contract | ~49 份 | `backend/data/workpaper_sync_contracts/*.json` |
| candidate contract | 11 份，含 **`l1.short_term_loans.candidate.json`** 与 `l4.bonds_payable.candidate.json` | 同上 |
| `STORE_MERGE_REGISTRY` 已注册 plan | 35+ 条（含 D/E/F/G/H 全域），**不含任何 L** | `store_item_registry.py` |
| `working_paper_content_representation` | **274 行** | 真库 PG 现查 |
| `working_paper_content_version` | **267 行** | 真库 PG 现查 |
| `working_paper_sync_entry_state` | **12 行 / 11 个不同 entry_id** | 真库 PG 现查 |

## 需求 1：BP-61-1 的前提已失效，必须重新裁决后才能推进

L 域 8 条 entry 的 `capability_target_blocked_by` 含 BP-1/BP-2/BP-3，而 registry 注释与
多份 evidence 文档把根因归到 **BP-61-1「`working_paper_sync_entry_state` /
`working_paper_content_version` / `working_paper_content_representation` 三表近空，
186 个 planned entry 一个都注册不上」**。

🔴 本轮真库实测推翻该前提：三表分别 **12 / 267 / 274** 行，且 `entry_state` 覆盖
**11 个 entry**（`b60` / `d1` / `d2` / `d3` / `d4` / `d5` / `d6` / `d7` / `g7` / `h1` +
1 条 opaque）。其中 **D3 / D5 / D6 / D7 已有 published representation 但 manifest 仍标
`legacy_fake_bidirectional`** ⇒ 卡点不在平台供给，在「manifest 重生成 + capability 裁决」
这个治理动作没人执行。

### 验收标准

1. WHEN 复核 BP-61-1，THEN 必须以真库行数现算为据裁决其状态，且裁决结论落成守卫断言
2. 🔴 IF 裁决为「已解除」，THEN 必须同时指出解除证据是「11 个 entry 跑通」而非「三表非空」
   —— 三表非空只证明链路跑过，不证明对 L 域可用
3. WHEN 裁决完成，THEN L 域 8 条 entry 的 `capability_target_blocked_by` 里 BP-1/2/3 的
   保留或删除必须逐条给理由，禁整体沿用
4. 🔴 BP-3（真实 OO 9.4 探针）对 xlsx 的门已由 umbrella Task 44 `[x]` 关闭（Word 侧 Task 61
   仍 `[-]`）⇒ L 域全是 xlsx，BP-3 不得再作为 L 域阻塞理由；docker `audit-onlyoffice`
   实测 healthy，per-entry scenario evidence 有环境可跑

## 需求 2：L1 canary 走通五环发布链

发布顺序（`workpaper_sync_contracts/README.md` 明文，不可颠倒）：

```
template → instrumentation → contract → definition bundle → representation
```

L1 现状是第③环的 **candidate**：`l1.short_term_loans.candidate.json` 有
`contract_id` / `document_type` / `identity_carriers` / `review` / `review_status=candidate` /
`schema_version=contract-definition:v1` / `semantic_version=0.1.0-draft`，
但**缺** `template_definition_sha256` / `instrumentation_definition_sha256` /
`template.*` 三件与整个 `sheets[]` 段 ⇒ 过不了 `contracts.py::parse_contract`。

canary 已由前序 spec 选定且本轮复核成立：键组 `L1-adj-*`、sheet `审定表L1-1`、
真库 33 行 `remark` 非空、`parse_regex = ^L1-adj-(\d+)-(\w+)$`。

### 验收标准

1. WHEN 交付 provider 模块，THEN 必须是 `backend/app/services/workpaper_sync/phase5_l1_short_term_loans.py`，
   并实现注册路径真实读取的那组接口：`managed_row_table_specs()` / `instrumentation_specs()`（复数）/
   `template_definition_payload()` / `instrumentation_definition_payload()` /
   `read_authoritative_template()` / `excel_carrier_gate()` / `all_store_item_ids()`
2. 🔴 IF L 循环出现第二条 entry，THEN 必须先抽 `phase5_l_cycle_common.py`
   （对标既有 `phase5_h_cycle_common.py` 的 `instrumentation_specs_for(IDENTITY, specs)`），
   禁 8 份 provider 各自复制一遍
3. WHEN contract 转 reviewed，THEN 文件必须**改名**去掉 `.candidate` 中缀
   （README：`{adapter_id}.json` 才是生产契约，`contract_id` 必须等于文件名），
   且 `review.entry_id` 从 null 改为 `xlsx/gt-l1-short-term-loans`
4. 🔴 改名会打红既有守卫 `test_task54_l_cycle_migration.py::test_no_pilot_contract_belongs_to_the_l_cycle`
   （它按 `review.entry_id` 判归属且不区分 candidate/reviewed）⇒ 必须同步更新该守卫，
   **且更新方式是「把期望从『L 域零 contract』改成『L 域恰 N 条且逐条具名』」**，
   不得删断言或加豁免
5. WHEN 字段映射落成，THEN 每个受管字段必须同时有
   `stable_field_key` / `json_pointer` / `mode` / `value_type` / `source_ref` / `cell`；
   `row_identity.kind` 只能 `field` 或 `template_row_key`；
   行域 `json_pointer` 含恰好一个 `{row_uuid}`；声明 `row_identity` 必同时声明 `delete_policy`
6. 🔴 `identity_carriers` 只允许 `hidden_sheet` / `defined_name` / `excel_table` /
   `hidden_uuid_column`；sheet 定位锚点只允许 `defined_name_ref` /
   `excel_table_sheet_association` —— `sheet_id` 与 `sheet_display_name` 在 OO 9.4 实测 failed
7. WHEN adapter 注册，THEN 在 `STORE_MERGE_REGISTRY` 增 `l1.short_term_loans` 条目，
   `provider_module="phase5_l1_short_term_loans"`，item 只登记**本轮真受管**的键，
   禁预登记未受管键（会让 `check_sheet_specs_fully_registered` 分母失真）
8. WHEN 五环走完，THEN `working_paper_sync_entry_state` 里必须出现
   `xlsx/gt-l1-short-term-loans` 行，且 manifest 现算得
   `migration_state=adapter_registered` / `capability=bidirectional` / `adapter_id=l1.short_term_loans`

## 需求 3：L1 模板层缺陷先处置再接线

L1 册 `L1 短期借款.xlsx` 13 张 sheet。前序 spec 已登记的模板层事实必须在接线前复核：
`#REF!` definedName、裸 IF（OO 打开即崩，需 `neutralize_oo_crash_if_formulas`）。

### 验收标准

1. WHEN 现算 L1 册裸 IF，THEN 若非 0 必须在 StoreMergePlan 挂
   `oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas"`
2. 🔴 中性化函数与 G7/G2/G9/H9 等**共用同一个**（已被真 OO 栈验收过），
   禁新造、禁在 `adapters/excel.py` 加 `if adapter_id == "l1…"` 字面量分支
   （会打红 `test_excel_adapter_has_no_adapter_id_literal_branch`）
3. WHEN 现算 definedName 的 `#REF!` 数，THEN 登记为基线并断言不增长，不要求本轮修模板

## 需求 4：前端接线与 roundtrip 正确性

### 验收标准

1. WHEN L1 宿主接 sync bridge，THEN mode 开关必须真实驱动 OO 挂点渲染
   （BP-4 的 inert 形态在 L5~L8，L1 不属该形态，需现算确认）
2. WHEN notice 组件落位，THEN `GtEntrySyncCapabilityNotice` 必须真实挂载在 L1 编辑宿主上
   （BP-7 的 DOM 判据需有对象）
3. WHEN roundtrip 验证，THEN 必须跑 HTML→OO→HTML 值等价，且
   `L1-adj-*` 键组的 33 行真库载荷在往返后逐字节不变
4. 🔴 禁以合成测试冒充真栈 —— evidence 必须来自真实 OO 9.4（docker `audit-onlyoffice`），
   跑不通就如实标 `[ ]*` 并写明卡点

## 需求 5：L2~L8 批量推进（本 spec 后段）

### 验收标准

1. WHEN L1 闭环，THEN 按 L4（已有 candidate contract）→ L2/L3（有 HTML 对端与 composable）→
   L5~L8（BP-4 inert 开关，需先修开关）的顺序推进
2. 🔴 L5~L8 的 `ui_toolbar_gate.anchor is None`（连宿主锚点都没有）⇒ 必须先补锚点再接线，
   否则 step 11 的 DOM 判据无对象
3. WHEN 每条 entry 接通，THEN manifest 逐条翻转，禁批量翻转后统一验证

## 需求 6：零回归与并发隔离

### 验收标准

1. WHEN 任何改动落盘，THEN `backend/tests/workpaper_sync/` 全量与前端 vitest 必须无新增红
2. 🔴 现有 golden digest 基线（`test_f2_p11_golden_digest_zero_regression.py` 等）
   在新增 contract 后会变 ⇒ 必须按其既定方式更新基线，禁跳过
3. 🔴 **并发会话隔离**：当前分支 `work/2026-09-27-k-lane1-template-orphan-keys` 有并发会话在
   改 K lane1 与 A 类组件。`store_item_registry.py` 是双方共同触点 ⇒ 本 spec 对该文件
   **只做追加式改动**（新增一个 dict 条目），不重排既有条目、不改既有注释
4. WHEN 提交，THEN L1 的每一环独立 commit，任一环回滚不牵连其他环
