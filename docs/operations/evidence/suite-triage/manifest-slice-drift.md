# C3：entry manifest ↔ per-cycle manifest slice 的真矛盾

集群：C3（20 节点）。矛盾形态 = **同一事实被记了两遍**，两份记录现在互相打脸：

* `backend/data/workpaper_sync_entry_manifest.json`：`xlsx/gt-d2-accounts-receivable`、
  `xlsx/gt-d4-operating-revenue` 是 `capability=bidirectional` + `migration_state=adapter_registered`
  + 非空 `adapter_id`。
* `backend/data/workpaper_sync_d_cycle_manifest_slice.json`：7 条 D entry 的 `adapter_id` 全 `null`、
  `manifest_mirror.capability` 全 `single_onlyoffice`。

---

## 1. 权威方向裁定（先定方向，再动手）

### 裁定：**manifest 侧权威**（manifest + 生产账本），slice 是过时的手写镜像。

| # | 证据 | 观测值 |
|---|------|--------|
| E1 | manifest 自己的契约套件 | `tests/test_workpaper_sync_manifest_contract.py` → **6 passed**（对磁盘上的实况文件全绿） |
| E2 | manifest 是**生成物** | `scripts/gen/generate_workpaper_sync_manifest.py` 现算：live 源发现器 + `workpaper_sync_entry_overlay.json`；文件带 `manifest_digest` / `source_digest` / `profile_source_digest` |
| E3 | overlay 里有**逐 entry 人工复核过**的 override | 4 条 `review_status: published_representation_verified`：D2 / D4 / G7 / H1，各带 `adapter_id` + `capability: bidirectional` + `canonical_resolver: workpaper_sync_published_representation` |
| E4 | **生产代码账本**独立印证 | `app/services/workpaper_sync/adapters/registry.py#DELIVERED_PER_ENTRY_CONTRACTS`：10 行，`adapter_registered=True` 的恰好是 `d2.receivable_detail` / `d4.revenue_detail` / `g7.soe_subsidiary_disclosure` / `h1.disposal_check` |
| E5 | 两个独立源**集合相等** | 账本 `adapter_registered=True` 的 entry_id 集合 == manifest `capability==bidirectional` 的集合 == `{d2, d4, g7, h1}` |
| E6 | 四个 adapter id 在生产代码里真实存在 | `d2.receivable_detail` / `d4.revenue_detail` / `g7.soe_subsidiary_disclosure` / `h1.disposal_check` 均出现在 `adapters/registry.py` 及各自 provider module |
| E7 | 前端已经**只从 manifest 现算** | `workpaperEntrySyncNotice.ts` 的 `SYNC_ADAPTER_REGISTERED_ENTRY_IDS` = `WORKPAPER_SYNC_MANIFEST.filter(capability==='bidirectional').map(entryId)`；其 docstring 逐字记着「手写数组是第二真源，抄漏只会静默误导用户」 |
| E8 | slice 是**手冻结**的 | 带 `frozen_at: "Task 46 收口重写（2026-08-30）"`、`supersedes`，无 `generated_by`；7 条 entry 的 `manifest_mirror` 内容逐字相同（批量手抄特征） |
| E9 | 漂移**只落在迁移过的那两条** | D1/D3/D5/D6/D7 的全部 source-backed 字段 + mirror 与 manifest **逐项相等**；只有 D2/D4 三个字段（`canonical_resolver` / `migration_state` / `mount_count`）+ mirror 不符 ⇒ slice 冻结时是准确的，是这两条迁移后没人回填 |
| E10 | 判据自己写明了处置方向 | `test_manifest_capability_divergence_is_registered` 的失败消息：「若 manifest 已重生成，请同步更新 BP-6 与本判据」；`test_no_d_entry_has_a_registered_adapter...`：「本 slice 的「无已注册 adapter」前提不再成立 ⇒ 必须在此补齐字段级判据」 |

### 有没有「slice 权威、manifest 不可能知道」的部分？有，**不动它**

slice 的 `capability` / `capability_verdict_stage` / `capability_target_blocked_by` 是**裁决**
（AC 12.1 的六件前置是否交付），不是 source-backed 事实。`test_source_backed_profile_fields_match_the_manifest`
的 docstring 明文划界：「这些是生成器从源码推导的事实，不是裁决」。

因此：**source-backed 字段（`canonical_resolver` / `migration_state` / `mount_count` / `adapter_id`
/ `manifest_mirror.*` / `slice_scope.*_count`）改成随 manifest 现算；裁决字段 `capability` 仍留 `null`**。
D2/D4 上「manifest 说 bidirectional、slice 的 AC 12.1 闸门说六件前置未交付」这条分歧
**是真分歧、且未解决**，必须继续登记（BP-6 扩写，见 §3），不得用「把 slice 也改成 bidirectional」抹掉。

### manifest 侧要不要改？**不改，一个字节都不改**

D2/D4/G7/H1 的 `bidirectional` 在 overlay 里有人工复核记录、在 `registry.py` 里有生产账本、
在代码里有真 adapter。manifest 是这三者的现算产物。本轮**没有任何** manifest 侧修改
（`workpaper_sync_entry_manifest.json` / `workpaper_sync_entry_overlay.json` 保持工作树现状，
它们的 ` M` 状态来自根事件那三个 commit 的后续重生成，不是本轮动的）。

---

## 2. 20 节点处置表

分母说明：`manifest` = 实况 entry manifest（155 条）；`ledger` = `registry.py#DELIVERED_PER_ENTRY_CONTRACTS`；
`slice` = 对应 cycle 的手写 manifest slice；`literal` = 测试文件里的冻结字面量。

| # | node | 哪两个源打架 | 权威侧 | 处置 |
|---|------|-------------|--------|------|
| 1 | task29 `test_every_entry_either_derives_or_reports_profile_drift` | — | — | **实测已绿**（130 passed），无需动作 |
| 2 | task42 `TestFrozenEntrySelection::test_entry_is_the_only_h1_candidate_in_the_harness_assessment` | literal `bidirectional_entry_ids == ()` vs manifest/ledger | manifest | 改现算：与 ledger 的 `adapter_registered` 交集互锁 |
| 3 | task42 `TestFrozenEntrySelection::test_required_set_digest_is_this_entry_own` | literal digest `319d10b4…`（翻转前快照） vs manifest 现算 `1858ce59…` | manifest | 改现算 + 与 Task40/41 digest 互异（保住「是本 entry 自己的」原意） |
| 4 | task42 `TestContractIsGroundedInTheTemplate::test_contract_is_registered_in_the_delivery_ledger` | literal `adapter_registered is False` vs ledger `True` | ledger | 改现算：ledger ↔ manifest 双源一致 |
| 5 | task43 `TestFrozenEntrySelection::test_class_really_has_three_candidates` | 同 #2 | manifest | 同 #2 |
| 6 | task43 `TestContractIsGroundedInTheTemplate::test_contract_is_registered_in_the_delivery_ledger` | 同 #4 | ledger | 同 #4 |
| 7 | task44 `TestScenarioDenominatorIsBidirectional::test_close_predicate_is_cross_checked_against_the_raw_manifest` | literal `capability != "bidirectional"` vs manifest | manifest | 改现算：raw manifest 三字段与生产推导同值 |
| 8 | task46 `TestProperty20And21ContractAndAdapter::test_no_d_entry_has_a_registered_adapter_and_pilot_evidence_exists` | slice `adapter_id: null` + 测试前提 vs manifest/ledger | manifest | slice 回填 D2/D4 adapter_id；判据按「有/无 adapter」分流现算 |
| 9 | task46 `TestProperty20And21ContractAndAdapter::test_entries_without_contract_have_no_contract_file` | slice 只登记 D2 契约 vs 契约目录 7 份 D 契约（全 reviewed，ledger 有行） | 磁盘+ledger | slice 登记 7 份；literal `== {D2}` → 现算集合等式 |
| 10 | task46 `TestProperty69EvidencePerEntry::test_slice_scope_is_recomputable_from_the_manifest` | slice `parent_duplicate_count: 31` vs manifest 现算 `0` | manifest | slice 改 0 + selection_rule 实算描述同步 |
| 11 | task46 `TestProperty70NoCrossEntryReuse::test_parent_duplicates_not_counted_as_independent` | literal `31` + slice `d4.parent_duplicate_count: 31` vs manifest `0` | manifest | 两侧改现算 |
| 12 | task46 `TestAc14HonestModeVisibility::test_registered_entry_ids_agree_with_the_slice` | slice `adapter_id: null` vs 前端（现算自 manifest）已注册集 | manifest | slice 回填 ⇒ 走 else 分支 |
| 13 | task46 `TestManifestAlignment::test_source_backed_profile_fields_match_the_manifest` | slice `canonical_resolver` / `mount_count` / `migration_state` vs manifest | manifest | slice 回填 D2/D4 |
| 14 | task46 `TestManifestAlignment::test_manifest_capability_divergence_is_registered` | slice `manifest_mirror.*` vs manifest | manifest | mirror 回填；分歧**继续登记**（BP-6 扩写 + D2/D4 专门的分歧说明） |
| 15 | task48 `TestAc14HonestModeVisibility::test_registered_entry_ids_agree_with_the_slice` | 检测器正则 `=\s*\[` vs 真源已改成现算表达式 | **检测器错** | 端口 task46 已修好的 `_initializer_of` / `_registered_entry_ids` |
| 16 | task49 同名节点 | 同 #15 | 检测器错 | 同 #15 |
| 17 | task50 同名节点 | 同 #15 | 检测器错 | 同 #15 |
| 18 | task57 `TestSliceScopeIsRecomputable::test_parent_duplicate_section_is_absent_because_in_scope_count_is_zero` | literal `33` + slice `global_parent_duplicate_count: 33` vs manifest `12` | manifest | 两侧改现算 |
| 19 | task63 `TestResidencyReverification::test_bp16_manifest_criterion_is_recomputed_from_the_manifest` | 生成记录 `manifest_entry_total: 186` vs manifest `155` | manifest | **留红，跨集群**：唯一解是重跑 `generate_workpaper_task63_subcode_adjudication.py`，而 generated-artifact-drift 集群已把它裁为 `blocked-on-moving-input`（见该文档 #8/#9）。不在此分叉决策，也不弱化 `== len(entries)` 这条真现算 |
| 20 | task76 `TestGuardSelfChecks::test_pilot_denominator_is_four_and_source_backed` | literal `4` vs ledger 10 行 | ledger | **失败在分母不在 source-backed**（`_ALLOWED_PROVIDER_MODULES` 那半截仍成立）；分母改现算，另加「四个原始 pilot 仍在账本里」 |

### 同文件里**不属于本集群**的红（只记 id，不碰）

```
# capability-flip 快照族
task42::TestOrderingGate::{test_capability_is_not_enabled_before_finalize,
                          test_capability_predicate_agrees_with_the_ordering_gate,
                          test_attach_is_a_no_op_before_enablement_and_never_raises,
                          test_ledger_records_adapter_not_registered_yet}
task42::TestUpstreamDebtsAreVisibleFacts::test_dynamic_family_is_structurally_unreachable_for_every_xlsx_entry
task43::TestOrderingGate::{test_capability_is_not_enabled_before_finalize,
                          test_capability_predicate_agrees_with_the_ordering_gate,
                          test_attach_is_a_no_op_before_enablement_and_never_raises,
                          test_ledger_records_adapter_not_registered_yet}
task43::TestUpstreamDebtsAreVisibleFacts::test_dynamic_family_is_structurally_unreachable_for_every_xlsx_entry
task44::TestFinalizeStateIsReadFromProduction::*（6 节点）
task44::TestOrderingIsNotCommutable::test_upstream_gap_is_failed_not_unverifiable
task44::TestValidatorsAreBidirectionallyReachable::test_no_probe_can_pass_on_the_real_unadmitted_pilots
task44::TestReportIsClosedAndMeasured::test_blocking_conditions_keep_the_black_box_fact_visible

# 生成产物漂移族
task42::TestUpstreamRelsAndNamespaceDefectsAreFixed::test_ten_of_the_authoritative_workbooks_share_this_shape
task42::TestPilotIntroducesNoResolverDebt::test_no_function_in_this_module_is_classified_as_writer_or_resolver
task43::TestUpstreamRelsAndNamespaceShapesStillHold::test_ten_authoritative_workbooks_share_this_shape
task44::TestGateAddsNoProductionModule::test_writer_inventory_is_still_fresh
task46::TestProperty28DefinitionDriftFailClosed::{test_authoritative_templates_digests_recompute,
                                                 test_every_entry_template_ref_is_registered_with_digest}
task63::TestAdjudicationRecord::test_record_is_reproducible
task63::TestResidencyReverification::test_source_digests_cover_every_file_the_measured_criteria_read

# 前端结构漂移族
task48::TestProperty28DefinitionDriftFailClosed::test_bp5_wrong_workbook_fallback_is_reproducible
task49::TestProperty70NoCrossEntryReuse::test_unreachable_stub_is_registered_and_still_has_zero_inbound_edges
task50::{TestProperty23DynamicRowIdentity::test_positional_identity_inventory_is_exhaustive_and_partitioned,
         TestProperty23DynamicRowIdentity::test_family_a_hits_write_to_the_declared_key,
         TestOrphanLegacyComposables::test_declared_orphan_formdata_composables_really_have_no_production_consumer,
         TestProperty28DefinitionDriftFailClosed::test_template_resolution_audit_recomputes,
         TestProperty70NoCrossEntryReuse::test_deletion_plan_composables_are_distinct_and_real}
```

---

## 3. 逐项实施与变异验证

（按实施顺序增量填入）

---

## 4. 结论

（实施完成后填）
