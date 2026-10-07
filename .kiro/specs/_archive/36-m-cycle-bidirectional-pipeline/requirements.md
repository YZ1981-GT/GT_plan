# M 循环双向回写管线 · 需求

## 引言

**目标**：为 M1（应付股利）/ M5（盈余公积）/ M8（一般风险准备）/ M9（其他综合收益）四条 entry 走通 `workpaper_sync` 双向回写管线，解除 BP-1 / BP-2 / BP-3 三个阻塞项，使底稿内容能在 HTML 侧与 OnlyOffice 侧真正双向同步。

**上游依赖**：
- `m1-m5-m8-m9-mode-value-and-carrier-exceptions`（27/27 ✅，已完成 orphan 清理 / 位置化消除 / sheet map 修正等前置准备）
- `m-cycle-sync-foundation-and-first-canary`（MC-1~29 共同裁决 + canary M6）
- `m2-m3-m4-m7-m10-sheet-map-drift-and-collapse`（BP-4/BP-6/BP-8 判据定义方）
- D 循环管线（D1~D7 契约已交付，作为格式参照）

**scope**：本 spec 只覆盖 M1/M5/M8/M9 四条 entry。M2/M3/M4/M6/M7/M10 六条由 lane 2 spec 或后续 spec 覆盖。

**权威模板（现算）**：

| entry | 权威册 | sheets | 公式格 | 科目码 | 科目性质 | ITEM_PREFIX | DETERMINATION_SHEET |
|---|---|---|---|---|---|---|---|
| M1 | M1 应付股利（利润）.xlsx | 11 | 338 | 2232 | 负债类 | `M1-` | `审定表M1-1` |
| M5 | M5 盈余公积.xlsx | 10 | 193 | 4101 | 权益类 | `M5-` | `审定表M5-1` |
| M8 | M8 一般风险准备.xlsx | 11 | 227 | 4104 | 权益类 | `M8-` | `审定表M8-1` |
| M9 | M9 其他综合收益.xlsx | 9 | 470 | 4103 | 权益类 | `M9-` | `审定表M9-1` |

---

## Requirement 1：BP-1 解除 —— per-entry contract + authority model + definition bundle

**User Story:** 作为底稿双向回写系统，我需要每条 entry 有经审批的语义契约和定义包，这样 materialize / extract / merge 三个阶段才有可执行的字段级规范。

### 验收准则

1. WHEN 为四条 entry 各创建一份 contract JSON THEN 系统 SHALL 产出 4 份 `backend/data/workpaper_sync_contracts/m{n}.*.json`，格式为 `contract-definition:v1`，`review_status == "reviewed"`。
2. WHEN 契约声明受管 sheet THEN 每份 SHALL 至少包含**审定表**（`xx-1`）和**明细表**（`xx-2`）两个受管 sheet，其中审定表承载 TB 回写、明细表承载动态行数据。
3. WHEN 契约声明字段 THEN 每个 field SHALL 有 `stable_field_key` / `json_pointer` / `mode`（editable 或 formula）/ `value_type` / `source_ref`（指向权威模板单元格）/ `cell`（列 + 行映射），且 `mode` 必须与 openpyxl 现算的公式/非公式一致。
4. WHEN 契约声明 HTML 侧存储 THEN `review.html_store` SHALL 引用 `checklist_responses` 表，`item_id` 前缀与 `useM{n}FormData.ts` 的 `ITEM_PREFIX` 一致。
5. WHEN 契约声明行身份 THEN 动态行表的 `row_identity.kind` SHALL 为 `field` 或 `template_row_key`（禁止 index/ordinal/position）。
6. WHEN authority model 被选择 THEN 系统 SHALL 使用 `projection_contract`（与 D 循环同型）。
7. WHEN definition bundle 被发布 THEN 系统 SHALL 按 DAG `template → instrumentation → contract → bundle` 顺序发布，三个 slot 全部 approved。
8. WHEN 四条 entry 的 slice 字段被更新 THEN `authority_model` / `definition_bundle` SHALL 不再为 null。

## Requirement 2：BP-2 解除 —— published representation

**User Story:** 作为底稿双向回写系统，我需要为每条 entry finalize 出 published representation，这样 OO 编辑器能加载受管模板。

### 验收准则

1. WHEN `ExcelEntryFinalizeGate.finalize_candidate()` 被调用 THEN 系统 SHALL 为每条 entry 产出 `ExcelEntryFinalizeOutcome`，含 `definition_bundle_id` 与 `structure_hash`。
2. WHEN finalize 完成 THEN `instrumentation_candidate` / `published_representation` SHALL 不再为 null。
3. WHEN finalize 被校验 THEN `evidence.instrumented_sha256 == staged_candidate.sha256`（roundtrip 证据与发布字节一致）。
4. WHEN BP-1 未完成时调用 finalize THEN 系统 SHALL 抛出 `PerEntryContractUnapprovedError`（前置依赖严格校验）。

## Requirement 3：BP-3 解除 —— OO 探针验证

**User Story:** 作为质控，我需要每条 entry 在真实 OO 9.4 环境通过逐 scenario 测试，这样才能确认双向回写在真实编辑器中无数据丢失。

### 验收准则

1. WHEN OO 探针执行完成 THEN `EvidenceRecomputer.recompute()` SHALL 对每条 entry 返回 `EvidenceResult.verified`（0 defect + 0 stale + run 存在）。
2. WHEN required scenario set 被推导 THEN 系统 SHALL 覆盖 `projection_contract` 权威模型下的全部必需场景。
3. WHEN 探针发现缺陷 THEN `EvidenceDefect` SHALL 逐条记录（missing_scenario / scenario_not_passed / extra_scenario 等），且不得被静默忽略。
4. WHEN OO 环境不可用 THEN 测试 SHALL 标 `pytest.mark.skipif` 并说明原因，不得假绿。

## Requirement 4：端到端闭环验证

**User Story:** 作为产品负责人，我需要看到 M1/M5/M8/M9 的业务数据能在 HTML 侧编辑后同步到 OO 侧、在 OO 侧编辑后同步回 HTML 侧，且审定数能正确回写到 trial_balance。

### 验收准则

1. WHEN HTML 侧修改明细表字段 THEN OO 侧同一字段 SHALL 更新为相同值（HTML → OO）。
2. WHEN OO 侧修改 editable 字段 THEN HTML 侧 SHALL 提取到相同值（OO → HTML）。
3. WHEN OO 侧修改 formula 字段 THEN extract SHALL 忽略该修改（公式格由 OO 重算，不回写 HTML）。
4. WHEN 审定表的审定数变更 THEN `writebackTB` SHALL 正确回写到 `trial_balance`（M1→2232 / M5→4101 / M8→4104 / M9→4103）。
5. WHEN 四条 entry 闭环通过 THEN slice 中 `migration_state` SHALL 从 `legacy_fake_bidirectional` 变为 `bidirectional`。
6. WHEN 闭环验证需要真库数据 THEN 系统 SHALL 使用真实项目底稿（非合成数据），且 M 域真库至少有有效业务载荷可供验证。

## Requirement 5：adapter 注册与 registry 接入

**User Story:** 作为底稿渲染系统，我需要每条 entry 注册到 adapter registry，这样运行时能按 entry_id 找到正确的 contract 和 sync 策略。

### 验收准则

1. WHEN adapter 被注册 THEN `backend/app/services/workpaper_sync/adapters/registry.py` SHALL 包含四条 M 循环 adapter。
2. WHEN adapter 被加载 THEN `load_contract(adapter_id)` SHALL 返回对应的 `SyncContract` 对象且强校验通过。
3. WHEN adapter 与 contract 绑定 THEN `adapter_build.document_type == "xlsx"` 且 `adapter_build.adapter_id` 与 contract 的 `contract_id` 一致。
