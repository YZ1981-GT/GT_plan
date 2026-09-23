# Suite triage — workpaper_sync 全量失败清点（inventory）

Status: IN PROGRESS（先写头，chunk 完成即追加；磁盘上的本文件即交付物）

目的：**只清点，不修复**。产出 `tests/workpaper_sync/` 全套（173 个文件）的失败节点全清单，
并把每个失败节点归入根因族（cluster），最后与已知全套基线 `283 failed, 8294 passed,
2 skipped, 16 xfailed, 16 errors` 对账，明确"已逐条识别"与"仍未落账"的数量。

## 运行方式

分块跑（CHUNK=12，按 `backend/scripts/_inv_files.txt` 的字典序切片），避免单次 pytest
~34 分钟且输出被截断：

```
# chunk 1-6（先前运行，日志 backend/scripts/_inv_log.txt）
..\.venv\Scripts\python.exe scripts\_inv_run.py

# chunk 7-15（本次续跑，日志 backend/scripts/_inv_log2.txt，跳过 1-6 不覆盖）
..\.venv\Scripts\python.exe scripts\_inv_run2.py
```

每块命令等价于（cwd=`backend`）：

```
..\.venv\Scripts\python.exe -m pytest <12 个文件> -q --tb=no -rf -p no:randomly
```

`pytest-randomly` 未安装，`-p no:randomly` 是无害 no-op；收集顺序按文件名字典序确定，
故 chunk 边界在两次运行间完全一致（chunk 1-6 = 文件 1-72，chunk 7 = 文件 73-84，…，
chunk 15 = 文件 169-173）。

---

## 已清点（chunk 1-6，先前运行）

引自 `backend/scripts/_inv_log.txt`（逐块尾行原文）：

| chunk | 文件范围 | 耗时 | 结果行（原文） |
|---|---|---|---|
| 1/15 | 1-12 | 53s | `98 passed, 1 warning in 48.75s` |
| 2/15 | 13-24 | 23s | `93 passed, 1 warning in 18.70s` |
| 3/15 | 25-36 | 13s | `90 passed, 1 warning in 8.81s` |
| 4/15 | 37-48 | 43s | `192 passed, 1 skipped, 1 warning in 39.13s` |
| 5/15 | 49-60 | 37s | `381 passed, 1 xfailed, 1 warning in 32.03s` |
| 6/15 | 61-72 | 72s | `1 failed, 389 passed, 1 xfailed, 3 warnings in 67.33s (0:01:07)` |

chunk 1-6 小计：**1 failed, 1243 passed, 1 skipped, 2 xfailed**。

唯一失败（`-rf` 短摘要原文）：

```
FAILED tests/workpaper_sync/test_projection_structure_hash_semantics.py::TestBp30IsActuallyWired::test_projection_commit_calls_the_new_hash
```

---

## 本次清点（chunk 7-N）

（chunk 完成即追加，逐块记录：文件 | 失败数 | `-rf` 短摘要原文节点 id）

<!-- APPEND-CHUNKS-BELOW -->

### chunk 7/15（文件 73-84，112s）

结果行：`1 failed, 753 passed, 3 warnings in 99.58s (0:01:39)`

| test file | failed | `-rf` 短摘要节点 id（原文） |
|---|---|---|
| `test_task10_orm_repository_contract.py` | 1 | `FAILED tests/workpaper_sync/test_task10_orm_repository_contract.py::test_repository_never_commits` |

其余 11 个文件（test_sync_registration_prewarm / test_task10_repository_pg /
test_task11_artifact_repository / test_task11_retention_orphan_pg / test_task12_resolution_pg /
test_task13_contract_registry / test_task14_merge_conflicts / test_task16_durable_outbox_pg /
test_task16_durable_outbox_wiring / test_task17_excel_instrumentation /
test_task17_excel_instrumentation_pg）全绿，无 skipped / xfailed。

### chunk 8/15（文件 85-96，136s）

结果行：`732 passed, 3 warnings in 131.69s (0:02:11)` — 全绿，无 failed / skipped / xfailed。

文件：test_task18_html_save_unified_revision / _pg、test_task19_writer_migration、
test_task20_writer_gate、test_task21_room_service / _pg、test_task22_callback_claim / _pg、
test_task23_request_application / _pg、test_task24_close_intent / _pg。

### chunk 9/15（文件 97-108，72s）

结果行：`44 failed, 727 passed, 1 warning in 67.33s (0:01:07)`

| test file | failed | 说明 |
|---|---|---|
| `test_task29_timeline_evidence.py` | 1 | manifest 派生 / profile drift |
| `test_task29_timeline_evidence_pg.py` | 41 | 含 `TestHarness::test_no_phase_crashed_during_collection` → 整文件 PG 采集阶段崩溃后连带全红 |
| `test_task31_frontend_contract.py` | 2 | 前端契约投影 |

`-rf` 短摘要节点 id（原文）：

```
FAILED tests/workpaper_sync/test_task29_timeline_evidence.py::TestDerivationOverTheRealManifest::test_every_entry_either_derives_or_reports_profile_drift
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestHarness::test_no_phase_crashed_during_collection
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestAppendOnlyProjection::test_a_healthy_operation_timeline_has_no_defect
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestAppendOnlyProjection::test_the_shell_had_a_null_application_before_correlation
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestAppendOnlyProjection::test_the_timeline_reports_the_bound_application_after_correlation
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestAppendOnlyProjection::test_editing_current_state_directly_is_caught
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestAppendOnlyProjection::test_the_storage_layer_refuses_every_tamper_form[delete]
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestAppendOnlyProjection::test_the_storage_layer_refuses_every_tamper_form[update]
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestAppendOnlyProjection::test_the_storage_layer_refuses_every_tamper_form[dup-seq]
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestAppendOnlyProjection::test_the_timeline_survives_the_tamper_attempts_unchanged
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestAppendOnlyProjection::test_the_timeline_declares_the_server_clock_as_its_time_source
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestAppendOnlyProjection::test_the_projected_event_carries_the_redaction_policy_version
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestAppendOnlyProjection::test_the_projected_event_drops_the_surrogate_id
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestAppendOnlyProjection::test_no_credential_or_business_value_appears_in_the_serialized_timeline
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestAppendOnlyProjection::test_a_cross_scope_read_is_refused
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestTimelineLocators::test_every_locator_returns_events
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestTimelineLocators::test_the_room_query_spans_more_than_one_stream
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestRecoveryCaseHasNoOperationBeforeClaim::test_all_three_entities_are_absent_before_claim
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestRecoveryCaseHasNoOperationBeforeClaim::test_the_pre_claim_timeline_says_so
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestRecoveryCaseHasNoOperationBeforeClaim::test_the_pre_claim_payload_has_no_operation_events_key
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestRecoveryCaseHasNoOperationBeforeClaim::test_claiming_creates_all_three_entities_at_once
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestRecoveryCaseHasNoOperationBeforeClaim::test_the_claim_shell_became_a_primary
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestRecoveryCaseHasNoOperationBeforeClaim::test_the_recovery_timeline_grows_append_only
```

```
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestEvidenceRecomputation::test_a_clean_run_has_exactly_one_known_and_attributed_defect
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestEvidenceRecomputation::test_every_scenario_owns_its_own_application
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestEvidenceRecomputation::test_the_required_set_came_from_the_source_backed_profile
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestEvidenceRecomputation::test_a_missing_scenario_is_unverified
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestEvidenceRecomputation::test_download_only_with_entities_is_refused_by_the_storage_layer
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestEvidenceRecomputation::test_a_dangling_operation_fk_is_unverified
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestEvidenceRecomputation::test_an_entity_from_another_entry_is_unverified
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestEvidenceRecomputation::test_an_extra_unregistered_scenario_is_unverified
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestEvidenceRecomputation::test_a_scenario_whose_bundle_differs_from_its_run_is_refused_by_the_db
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestEvidenceRecomputation::test_an_entry_without_any_run_is_unverified
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestEvidenceRecomputation::test_a_contradictory_profile_reports_drift_instead_of_crashing
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestEvidenceReuseIsRefused::test_reusing_one_operation_for_two_scenarios_is_refused
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestEvidenceReuseIsRefused::test_the_same_entities_in_two_entries_runs_reddens_both
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestEvidenceStaleness::test_a_different_source_commit_makes_the_run_stale
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestEvidenceStaleness::test_the_environment_digest_is_its_own_independent_stale_reason
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestEvidenceStaleness::test_changing_the_oo_or_browser_build_makes_the_run_stale
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestEvidenceStaleness::test_downgrading_the_profile_cannot_keep_old_evidence_fresh
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestEvidenceStaleness::test_a_different_required_set_digest_makes_the_run_stale
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestEvidenceStaleness::test_stale_alone_is_not_reported_as_verified
FAILED tests/workpaper_sync/test_task31_frontend_contract.py::test_a_real_slashed_entry_id_still_routes_through_the_generated_template
FAILED tests/workpaper_sync/test_task31_frontend_contract.py::test_the_callback_route_is_never_projected_to_the_frontend
```

### chunk 10/15（文件 109-120，120s）

结果行：`29 failed, 747 passed, 1 warning in 115.76s (0:01:55)`

| test file | failed |
|---|---|
| `test_task39_pilot_harness.py` | 1 |
| `test_task41_d2_large_json_pilot.py` | 6 |
| `test_task41_d2_large_json_pilot_pg.py` | 2 |
| `test_task42_h1_grouped_dynamic_pilot.py` | 10 |
| `test_task42_h1_grouped_dynamic_pilot_pg.py` | 2 |
| `test_task43_g7_two_level_dynamic_pilot.py` | 8 |

`-rf` 短摘要节点 id（原文）：

```
FAILED tests/workpaper_sync/test_task39_pilot_harness.py::TestPilotClassCoverage::test_no_class_is_verified_today_because_there_is_no_bidirectional_entry
FAILED tests/workpaper_sync/test_task41_d2_large_json_pilot.py::TestUpstreamDebtsAreVisibleFacts::test_dynamic_family_is_structurally_unreachable_for_every_xlsx_entry
FAILED tests/workpaper_sync/test_task41_d2_large_json_pilot.py::TestOrderingGate::test_capability_is_not_enabled_before_finalize
FAILED tests/workpaper_sync/test_task41_d2_large_json_pilot.py::TestOrderingGate::test_capability_predicate_agrees_with_the_ordering_gate
FAILED tests/workpaper_sync/test_task41_d2_large_json_pilot.py::TestOrderingGate::test_attach_is_a_no_op_before_enablement_and_never_raises
FAILED tests/workpaper_sync/test_task41_d2_large_json_pilot.py::TestOrderingGate::test_ledger_records_adapter_not_registered_yet
FAILED tests/workpaper_sync/test_task41_d2_large_json_pilot.py::TestOrderingGate::test_registration_is_refused_while_manifest_says_single_onlyoffice
FAILED tests/workpaper_sync/test_task41_d2_large_json_pilot_pg.py::test_real_store_payload_is_the_frozen_866kb_shape
FAILED tests/workpaper_sync/test_task41_d2_large_json_pilot_pg.py::test_no_other_store_item_is_touched
FAILED tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py::TestFrozenEntrySelection::test_entry_is_the_only_h1_candidate_in_the_harness_assessment
FAILED tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py::TestFrozenEntrySelection::test_required_set_digest_is_this_entry_own
FAILED tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py::TestContractIsGroundedInTheTemplate::test_contract_is_registered_in_the_delivery_ledger
FAILED tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py::TestUpstreamDebtsAreVisibleFacts::test_dynamic_family_is_structurally_unreachable_for_every_xlsx_entry
FAILED tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py::TestUpstreamRelsAndNamespaceDefectsAreFixed::test_ten_of_the_authoritative_workbooks_share_this_shape
FAILED tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py::TestOrderingGate::test_capability_is_not_enabled_before_finalize
FAILED tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py::TestOrderingGate::test_capability_predicate_agrees_with_the_ordering_gate
FAILED tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py::TestOrderingGate::test_attach_is_a_no_op_before_enablement_and_never_raises
FAILED tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py::TestOrderingGate::test_ledger_records_adapter_not_registered_yet
FAILED tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py::TestPilotIntroducesNoResolverDebt::test_no_function_in_this_module_is_classified_as_writer_or_resolver
FAILED tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot_pg.py::test_disposal_store_item_is_empty_across_the_whole_database
FAILED tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot_pg.py::test_contract_declares_the_observed_emptiness
FAILED tests/workpaper_sync/test_task43_g7_two_level_dynamic_pilot.py::TestFrozenEntrySelection::test_class_really_has_three_candidates
FAILED tests/workpaper_sync/test_task43_g7_two_level_dynamic_pilot.py::TestContractIsGroundedInTheTemplate::test_contract_is_registered_in_the_delivery_ledger
FAILED tests/workpaper_sync/test_task43_g7_two_level_dynamic_pilot.py::TestUpstreamDebtsAreVisibleFacts::test_dynamic_family_is_structurally_unreachable_for_every_xlsx_entry
FAILED tests/workpaper_sync/test_task43_g7_two_level_dynamic_pilot.py::TestUpstreamRelsAndNamespaceShapesStillHold::test_ten_authoritative_workbooks_share_this_shape
FAILED tests/workpaper_sync/test_task43_g7_two_level_dynamic_pilot.py::TestOrderingGate::test_capability_is_not_enabled_before_finalize
FAILED tests/workpaper_sync/test_task43_g7_two_level_dynamic_pilot.py::TestOrderingGate::test_capability_predicate_agrees_with_the_ordering_gate
FAILED tests/workpaper_sync/test_task43_g7_two_level_dynamic_pilot.py::TestOrderingGate::test_attach_is_a_no_op_before_enablement_and_never_raises
FAILED tests/workpaper_sync/test_task43_g7_two_level_dynamic_pilot.py::TestOrderingGate::test_ledger_records_adapter_not_registered_yet
```

### chunk 11/15（文件 121-132，541s）

结果行：`42 failed, 1194 passed, 33 warnings in 535.68s (0:08:55)`

| test file | failed |
|---|---|
| `test_task44_oo94_excel_pilot_gate.py` | 12 |
| `test_task45_pilot_legacy_deletion.py` | 1 |
| `test_task46_d_cycle_migration.py` | 13 |
| `test_task48_f_cycle_migration.py` | 2 |
| `test_task49_g_cycle_migration.py` | 2 |
| `test_task50_h_cycle_migration.py` | 9 |
| `test_task52_j_cycle_migration.py` | 2 |
| `test_task54_l_cycle_migration.py` | 1 |

（`test_task47_e` / `test_task51_i` / `test_task53_k` / `test_task55_m` 全绿）

`-rf` 短摘要节点 id（原文）：

```
FAILED tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py::TestProbeRegistryIsLockedToTaskText::test_generated_registry_data_file_is_fresh
FAILED tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py::TestScenarioDenominatorIsBidirectional::test_close_predicate_is_cross_checked_against_the_raw_manifest
FAILED tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py::TestFinalizeStateIsReadFromProduction::test_all_four_pilots_are_blocked_before_task_36_finalize
FAILED tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py::TestFinalizeStateIsReadFromProduction::test_each_signal_flips_independently_under_substitution[d2_large_json]
FAILED tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py::TestFinalizeStateIsReadFromProduction::test_each_signal_flips_independently_under_substitution[g7_two_level_dynamic]
FAILED tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py::TestFinalizeStateIsReadFromProduction::test_each_signal_flips_independently_under_substitution[h1_grouped_dynamic]
FAILED tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py::TestFinalizeStateIsReadFromProduction::test_the_four_pilots_short_circuit_at_different_gates
FAILED tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py::TestFinalizeStateIsReadFromProduction::test_the_stub_session_is_the_only_substituted_part
FAILED tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py::TestFinalizeStateIsReadFromProduction::test_gate_probe_admission_is_state_sensitive_passes_for_all_four
FAILED tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py::TestOrderingIsNotCommutable::test_upstream_gap_is_failed_not_unverifiable
FAILED tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py::TestValidatorsAreBidirectionallyReachable::test_no_probe_can_pass_on_the_real_unadmitted_pilots
FAILED tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py::TestReportIsClosedAndMeasured::test_blocking_conditions_keep_the_black_box_fact_visible
FAILED tests/workpaper_sync/test_task45_pilot_legacy_deletion.py::TestProperty47LegacyDeleted::test_host_imports_bridge_adapter[GtD2AccountsReceivable.vue]
```

```
FAILED tests/workpaper_sync/test_task46_d_cycle_migration.py::TestProperty20And21ContractAndAdapter::test_no_d_entry_has_a_registered_adapter_and_pilot_evidence_exists
FAILED tests/workpaper_sync/test_task46_d_cycle_migration.py::TestProperty20And21ContractAndAdapter::test_entries_without_contract_have_no_contract_file
FAILED tests/workpaper_sync/test_task46_d_cycle_migration.py::TestProperty28DefinitionDriftFailClosed::test_authoritative_templates_digests_recompute
FAILED tests/workpaper_sync/test_task46_d_cycle_migration.py::TestProperty28DefinitionDriftFailClosed::test_every_entry_template_ref_is_registered_with_digest
FAILED tests/workpaper_sync/test_task46_d_cycle_migration.py::TestProperty69EvidencePerEntry::test_slice_scope_is_recomputable_from_the_manifest
FAILED tests/workpaper_sync/test_task46_d_cycle_migration.py::TestProperty70NoCrossEntryReuse::test_parent_duplicates_not_counted_as_independent
FAILED tests/workpaper_sync/test_task46_d_cycle_migration.py::TestAc14HonestModeVisibility::test_every_pending_entry_host_mounts_the_notice
FAILED tests/workpaper_sync/test_task46_d_cycle_migration.py::TestAc14HonestModeVisibility::test_notice_mount_sits_inside_the_mode_toolbar
FAILED tests/workpaper_sync/test_task46_d_cycle_migration.py::TestAc14HonestModeVisibility::test_registered_entry_ids_agree_with_the_slice
FAILED tests/workpaper_sync/test_task46_d_cycle_migration.py::TestAc14HonestModeVisibility::test_hosts_do_not_claim_bidirectional_writeback
FAILED tests/workpaper_sync/test_task46_d_cycle_migration.py::TestSourceCodeStructure::test_hosts_exist_and_import_legacy_composable
FAILED tests/workpaper_sync/test_task46_d_cycle_migration.py::TestManifestAlignment::test_source_backed_profile_fields_match_the_manifest
FAILED tests/workpaper_sync/test_task46_d_cycle_migration.py::TestManifestAlignment::test_manifest_capability_divergence_is_registered
FAILED tests/workpaper_sync/test_task48_f_cycle_migration.py::TestProperty28DefinitionDriftFailClosed::test_bp5_wrong_workbook_fallback_is_reproducible
FAILED tests/workpaper_sync/test_task48_f_cycle_migration.py::TestAc14HonestModeVisibility::test_registered_entry_ids_agree_with_the_slice
FAILED tests/workpaper_sync/test_task49_g_cycle_migration.py::TestProperty70NoCrossEntryReuse::test_unreachable_stub_is_registered_and_still_has_zero_inbound_edges
FAILED tests/workpaper_sync/test_task49_g_cycle_migration.py::TestAc14HonestModeVisibility::test_registered_entry_ids_agree_with_the_slice
FAILED tests/workpaper_sync/test_task50_h_cycle_migration.py::TestHtmlCounterpartIsSourceBacked::test_write_carrier_client_and_put_site_agree_with_the_source
FAILED tests/workpaper_sync/test_task50_h_cycle_migration.py::TestHtmlCounterpartIsSourceBacked::test_payload_column_mode_matches_the_write_site
FAILED tests/workpaper_sync/test_task50_h_cycle_migration.py::TestProperty23DynamicRowIdentity::test_positional_identity_inventory_is_exhaustive_and_partitioned
FAILED tests/workpaper_sync/test_task50_h_cycle_migration.py::TestProperty23DynamicRowIdentity::test_family_a_hits_write_to_the_declared_key
FAILED tests/workpaper_sync/test_task50_h_cycle_migration.py::TestOrphanLegacyComposables::test_declared_orphan_formdata_composables_really_have_no_production_consumer
FAILED tests/workpaper_sync/test_task50_h_cycle_migration.py::TestProperty28DefinitionDriftFailClosed::test_template_resolution_audit_recomputes
FAILED tests/workpaper_sync/test_task50_h_cycle_migration.py::TestProperty70NoCrossEntryReuse::test_deletion_plan_composables_are_distinct_and_real
FAILED tests/workpaper_sync/test_task50_h_cycle_migration.py::TestAc14HonestModeVisibility::test_registered_entry_ids_agree_with_the_slice
FAILED tests/workpaper_sync/test_task50_h_cycle_migration.py::TestSourceCodeStructure::test_hosts_exist_and_are_reachable_from_the_renderer_registry
FAILED tests/workpaper_sync/test_task52_j_cycle_migration.py::TestOrphanDualModeInventory::test_pseudo_string_edges_exist_but_are_not_import_edges
FAILED tests/workpaper_sync/test_task52_j_cycle_migration.py::TestProperty3And20::test_ac14_notice_single_source_exists_and_is_not_duplicated
FAILED tests/workpaper_sync/test_task54_l_cycle_migration.py::TestSheetGranularityAndRouter::test_router_declaration_matches_the_source
```

### chunk 12/15（文件 133-144，96s）

结果行：`12 failed, 812 passed, 12 xfailed, 5 warnings in 90.59s (0:01:30)`

| test file | failed |
|---|---|
| `test_task56_n_cycle_migration.py` | 1 |
| `test_task57_abcs_and_shared_migration.py` | 2 |
| `test_task58_word_canonical_resolver.py` | 1 |
| `test_task61_oo94_word_pilot_gate.py` | 2 |
| `test_task62_generic_docx_entries.py` | 2 |
| `test_task63_subcode_adjudication.py` | 3 |
| `test_task64_dedicated_word_chain.py` | 1 |

```
FAILED tests/workpaper_sync/test_task56_n_cycle_migration.py::TestAdjudicationLegality::test_ac14_notice_single_source_exists_and_is_consumed
FAILED tests/workpaper_sync/test_task57_abcs_and_shared_migration.py::TestSliceScopeIsRecomputable::test_parent_duplicate_section_is_absent_because_in_scope_count_is_zero
FAILED tests/workpaper_sync/test_task57_abcs_and_shared_migration.py::TestAdjudicationLegality::test_ac14_notice_single_source_exists_and_is_consumed_out_of_scope
FAILED tests/workpaper_sync/test_task58_word_canonical_resolver.py::TestAdjudicationLedger::test_ledger_is_in_sync_with_sources
FAILED tests/workpaper_sync/test_task61_oo94_word_pilot_gate.py::TestAdmissionIsRealReadback::test_no_f2_entry_is_admitted_today
FAILED tests/workpaper_sync/test_task61_oo94_word_pilot_gate.py::TestBindingConstraintIsMeasured::test_the_three_arms_really_run_against_the_database
FAILED tests/workpaper_sync/test_task62_generic_docx_entries.py::TestGeneratorIsIdempotentAndCheckIsStrict::test_build_record_is_byte_stable
FAILED tests/workpaper_sync/test_task62_generic_docx_entries.py::TestGeneratorIsIdempotentAndCheckIsStrict::test_check_matches_the_file_on_disk
FAILED tests/workpaper_sync/test_task63_subcode_adjudication.py::TestAdjudicationRecord::test_record_is_reproducible
FAILED tests/workpaper_sync/test_task63_subcode_adjudication.py::TestResidencyReverification::test_bp16_manifest_criterion_is_recomputed_from_the_manifest
FAILED tests/workpaper_sync/test_task63_subcode_adjudication.py::TestResidencyReverification::test_source_digests_cover_every_file_the_measured_criteria_read
FAILED tests/workpaper_sync/test_task64_dedicated_word_chain.py::TestGeneratorContract::test_generator_check_is_idempotent
```

### chunk 13/15（文件 145-156，166s）

结果行：`6 failed, 459 passed, 7 warnings in 159.81s (0:02:39)`

| test file | failed |
|---|---|
| `test_task65_opaque_authority_bundle.py` | 3 |
| `test_task75_entry_adapter_roundtrip.py` | 1 |
| `test_task76_projection_definition_provisioner.py` | 1 |
| `test_task76_wp_code_adjudication.py` | 1 |

```
FAILED tests/workpaper_sync/test_task65_opaque_authority_bundle.py::test_registry_covers_every_source_call_site
FAILED tests/workpaper_sync/test_task65_opaque_authority_bundle.py::test_commit_bytes_lane_arguments_match_registry
FAILED tests/workpaper_sync/test_task65_opaque_authority_bundle.py::test_wrong_lane_id_argument_fails_closed
FAILED tests/workpaper_sync/test_task75_entry_adapter_roundtrip.py::TestRealRun::test_three_pilots_are_all_verified_or_environment_unavailable
FAILED tests/workpaper_sync/test_task76_projection_definition_provisioner.py::TestGuardSelfChecks::test_pilot_denominator_is_four_and_source_backed
FAILED tests/workpaper_sync/test_task76_wp_code_adjudication.py::TestHostResolutionNoLongerTrustsTheHeuristic::test_loader_is_fail_closed_when_the_table_is_missing
```

### chunk 14/15（文件 157-168，52s）

结果行：`6 failed, 349 passed, 1 warning in 48.51s`

```
FAILED tests/workpaper_sync/test_template_override_resolution.py::TestProperty3AuthoritativeFrozen::test_index_size_drift_is_registered_not_growing
FAILED tests/workpaper_sync/test_workbook_row_change_carriers.py::TestScannerRewriterAgreement::test_scanner_agrees_with_rewriter_on_whole_corpus
FAILED tests/workpaper_sync/test_workbook_row_change_carriers.py::TestDefinedNameClassification::test_defined_name_five_way_classification
FAILED tests/workpaper_sync/test_workbook_row_change_reachability.py::test_inventory_matches_current_computation
FAILED tests/workpaper_sync/test_workbook_row_change_reachability.py::test_host_binding_is_content_addressed
FAILED tests/workpaper_sync/test_workbook_row_change_reachability.py::test_binding_verifier_detects_injected_digest_drift
```

### chunk 15/15（文件 169-173，15s）

结果行：`1 failed, 74 passed, 1 skipped, 1 warning in 11.53s`

```
FAILED tests/workpaper_sync/test_workbook_row_change_zero_regression.py::test_behaviour_matches_frozen_baseline
```

### chunk 7-15 小计

| chunk | failed | passed | 其他 |
|---|---|---|---|
| 7 | 1 | 753 | — |
| 8 | 0 | 732 | — |
| 9 | 44 | 727 | — |
| 10 | 29 | 747 | — |
| 11 | 42 | 1194 | — |
| 12 | 12 | 812 | 12 xfailed |
| 13 | 6 | 459 | — |
| 14 | 6 | 349 | — |
| 15 | 1 | 74 | 1 skipped |
| **小计** | **141** | **5847** | 12 xfailed / 1 skipped |

加上 chunk 1-6（1 failed / 1243 passed / 1 skipped / 2 xfailed），
本盘点清单（173 个文件）合计 **142 failed, 7090 passed, 2 skipped, 14 xfailed, 0 errors**。

### ⚠️ 工作树在测量期间被并发会话改动（影响计数可信度）

把 chunk 5 + chunk 6 + chunk 12 的 36 个文件**并成一次**重跑（`-q --tb=no -rf -p no:randomly`）：

```
12 failed, 1584 passed, 14 xfailed, 7 warnings in 192.48s (0:03:12)
```

12 条 FAILED 全部来自 chunk 12，**chunk 6 那条唯一失败
（`test_projection_structure_hash_semantics.py::TestBp30IsActuallyWired::test_projection_commit_calls_the_new_hash`）
在重跑中转绿**，且收集总数 1610 vs 分块 1609（多 1 条）。

**成因已查明：不是顺序污染，是并发会话在改这些测试文件。** 文件 mtime 与日志 mtime 对照：

| 文件 | LastWriteTime |
|---|---|
| `_inv_log.txt`（chunk 1-6 日志，先前运行） | 2026-09-23 19:29:18 |
| `test_projection_structure_hash_semantics.py` | 2026-09-23 **20:47:28** |
| `test_task64_dedicated_word_chain.py` | 2026-09-23 21:05:21 |
| `test_migration_paradigm_contract.py` | 2026-09-23 21:06:45 |
| `_inv_log2.txt`（chunk 7-15 完成） | 2026-09-23 21:06:51 |
| `test_slice_schema_validator_coverage.py` | 2026-09-23 21:07:07 |
| `backend/app/services/workpaper_sync/phase5_d4_revenue_detail.py` | 2026-09-23 21:20:23 |

会话开始时 `git status` 并**未**列出 `test_projection_structure_hash_semantics.py` 为 M，
现在列出了 → 它在 chunk 6 测完（19:29 前）之后、重跑（约 21:03-21:07）之前被改过，
红转绿是**并发修复**，不是分组差异。

对本清单的影响，逐条说清：

- chunk 7-15 的 141 条是**各块跑完那一刻**的实测，块内一致；但整份清单跨了约 40 分钟，
  期间工作树在动（上表 5 个文件 + `test_d4_1_html_shape_store_projection_gap.py`、
  `test_d4_store_item_wiring_gap.py` 两个新增测试文件）。
- 受影响最明确的是 **chunk 6 那 1 条**（已确认转绿）与 **xfailed 清单**（14 条的 3 个宿主文件
  `test_task64_*` / `test_migration_paradigm_contract` / `test_slice_schema_validator_coverage`
  都在 21:05-21:07 被改，与 xfail 重跑窗口重叠；pytest 在收集时 import，重跑读到的
  大概率是改动前版本，但无法排除）。
- 其余 12 个 chunk 的宿主文件均不在上表中，未见改动。
- 处置建议：真要一份可签署的基线，须在**冻结工作树**（或在干净 checkout 上）重跑一次；
  本清单的定位是"当前工作树的失败分布与根因族"，不是可签署的定量基线。

---

## 聚类

口径说明（诚实标注）：本次是 `--tb=no` 清点，**没有读 traceback**。下面的归族依据是
①节点名/测试类名直接表达的断言语义，②同文件内连带关系，③与已知簇的命名对齐。
标 `信度高` 的簇，节点名本身就说明了根因族；标 `信度中` 的簇需要后续逐条读 traceback 确认。

失败总数 142 条，全部落账，无"未归族"残留。

### C1 · capability-flip platform readiness（已知簇）— 29 条｜信度高

形态：断言"**今天**还没有能力 / 还没放行 / 还没有 bidirectional entry"的**负向事实**；
平台能力（Task 36 finalize、pilot admission、capability 标记）翻转后，这些"现状快照"断言过期。

| 文件 | 条数 | 代表节点 |
|---|---|---|
| `test_task39_pilot_harness.py` | 1 | `TestPilotClassCoverage::test_no_class_is_verified_today_because_there_is_no_bidirectional_entry` |
| `test_task41_d2_large_json_pilot.py` | 6 | `TestOrderingGate::test_capability_is_not_enabled_before_finalize` 等 5 条 + `TestUpstreamDebtsAreVisibleFacts::test_dynamic_family_is_structurally_unreachable_for_every_xlsx_entry` |
| `test_task42_h1_grouped_dynamic_pilot.py` | 5 | `TestOrderingGate::*` ×4 + `dynamic_family_is_structurally_unreachable` |
| `test_task43_g7_two_level_dynamic_pilot.py` | 5 | 同上形态 |
| `test_task44_oo94_excel_pilot_gate.py` | 10 | `TestFinalizeStateIsReadFromProduction::test_all_four_pilots_are_blocked_before_task_36_finalize`、`test_each_signal_flips_independently_under_substitution[*]` ×3、`test_the_four_pilots_short_circuit_at_different_gates`、`test_the_stub_session_is_the_only_substituted_part`、`test_gate_probe_admission_is_state_sensitive_passes_for_all_four`、`TestOrderingIsNotCommutable::test_upstream_gap_is_failed_not_unverifiable`、`TestValidatorsAreBidirectionallyReachable::test_no_probe_can_pass_on_the_real_unadmitted_pilots`、`TestReportIsClosedAndMeasured::test_blocking_conditions_keep_the_black_box_fact_visible` |
| `test_task61_oo94_word_pilot_gate.py` | 1 | `TestAdmissionIsRealReadback::test_no_f2_entry_is_admitted_today` |
| `test_task75_entry_adapter_roundtrip.py` | 1 | `TestRealRun::test_three_pilots_are_all_verified_or_environment_unavailable` |

`TestOrderingGate` 的成员（节点 id 原文见 chunk 10 代码块）：task41 有 5 条
（`test_capability_is_not_enabled_before_finalize` / `test_capability_predicate_agrees_with_the_ordering_gate` /
`test_attach_is_a_no_op_before_enablement_and_never_raises` / `test_ledger_records_adapter_not_registered_yet` /
`test_registration_is_refused_while_manifest_says_single_onlyoffice`），task42 与 task43 各 4 条
（无最后那条 `registration_is_refused_*`）。三个文件各再加 1 条
`TestUpstreamDebtsAreVisibleFacts::test_dynamic_family_is_structurally_unreachable_for_every_xlsx_entry`。

### C2 · task29 timeline-evidence PG harness 采集崩溃（整文件连带）— 41 条｜信度高（新簇）

`test_task29_timeline_evidence_pg.py` 的 41 条全红，且其中含
`TestHarness::test_no_phase_crashed_during_collection` —— 该文件用"先跑一轮采集、
各测试再读采集结果"的 harness 模式，**采集阶段崩溃后同文件所有断言连带全红**。
按 1 个根因计（不是 41 个独立缺陷），但清点上是 41 个失败节点。

节点 id 全清单见上文 chunk 9 两个代码块。

### C3 · manifest / slice 派生事实漂移（与已知 `task66/67/68 manifest_entry_total moving target` 同族）— 20 条｜信度高

形态：断言从 `workpaper_sync_entry_manifest.json` / cycle slice / profile 现场重算出来的
派生事实（entry 计数、候选集、required_set digest、capability 分歧、adapter/contract 登记）。
manifest 与 slice 正在被并发改动（`git status` 显示 `workpaper_sync_entry_manifest.json`、
`workpaper_resolver_migration_matrix.json`、各 slice 均 M），故这些断言是移动靶。

```
tests/workpaper_sync/test_task29_timeline_evidence.py::TestDerivationOverTheRealManifest::test_every_entry_either_derives_or_reports_profile_drift
tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py::TestFrozenEntrySelection::test_entry_is_the_only_h1_candidate_in_the_harness_assessment
tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py::TestFrozenEntrySelection::test_required_set_digest_is_this_entry_own
tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py::TestContractIsGroundedInTheTemplate::test_contract_is_registered_in_the_delivery_ledger
tests/workpaper_sync/test_task43_g7_two_level_dynamic_pilot.py::TestFrozenEntrySelection::test_class_really_has_three_candidates
tests/workpaper_sync/test_task43_g7_two_level_dynamic_pilot.py::TestContractIsGroundedInTheTemplate::test_contract_is_registered_in_the_delivery_ledger
tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py::TestScenarioDenominatorIsBidirectional::test_close_predicate_is_cross_checked_against_the_raw_manifest
tests/workpaper_sync/test_task46_d_cycle_migration.py::TestProperty20And21ContractAndAdapter::test_no_d_entry_has_a_registered_adapter_and_pilot_evidence_exists
tests/workpaper_sync/test_task46_d_cycle_migration.py::TestProperty20And21ContractAndAdapter::test_entries_without_contract_have_no_contract_file
tests/workpaper_sync/test_task46_d_cycle_migration.py::TestProperty69EvidencePerEntry::test_slice_scope_is_recomputable_from_the_manifest
tests/workpaper_sync/test_task46_d_cycle_migration.py::TestProperty70NoCrossEntryReuse::test_parent_duplicates_not_counted_as_independent
tests/workpaper_sync/test_task46_d_cycle_migration.py::TestAc14HonestModeVisibility::test_registered_entry_ids_agree_with_the_slice
tests/workpaper_sync/test_task46_d_cycle_migration.py::TestManifestAlignment::test_source_backed_profile_fields_match_the_manifest
tests/workpaper_sync/test_task46_d_cycle_migration.py::TestManifestAlignment::test_manifest_capability_divergence_is_registered
tests/workpaper_sync/test_task48_f_cycle_migration.py::TestAc14HonestModeVisibility::test_registered_entry_ids_agree_with_the_slice
tests/workpaper_sync/test_task49_g_cycle_migration.py::TestAc14HonestModeVisibility::test_registered_entry_ids_agree_with_the_slice
tests/workpaper_sync/test_task50_h_cycle_migration.py::TestAc14HonestModeVisibility::test_registered_entry_ids_agree_with_the_slice
tests/workpaper_sync/test_task57_abcs_and_shared_migration.py::TestSliceScopeIsRecomputable::test_parent_duplicate_section_is_absent_because_in_scope_count_is_zero
tests/workpaper_sync/test_task63_subcode_adjudication.py::TestResidencyReverification::test_bp16_manifest_criterion_is_recomputed_from_the_manifest
tests/workpaper_sync/test_task76_projection_definition_provisioner.py::TestGuardSelfChecks::test_pilot_denominator_is_four_and_source_backed
```

### C4 · AC14 honest-mode notice 单源缺失 / 挂载点漂移 — 6 条｜信度高（新簇）

形态：AC14「诚实模式」提示组件的**单一来源存在性 + 被消费 + 挂载位置**断言。多个 cycle
迁移文件重复同一族断言，说明是一个共享组件事实，不是 6 个独立缺陷。

```
tests/workpaper_sync/test_task46_d_cycle_migration.py::TestAc14HonestModeVisibility::test_every_pending_entry_host_mounts_the_notice
tests/workpaper_sync/test_task46_d_cycle_migration.py::TestAc14HonestModeVisibility::test_notice_mount_sits_inside_the_mode_toolbar
tests/workpaper_sync/test_task46_d_cycle_migration.py::TestAc14HonestModeVisibility::test_hosts_do_not_claim_bidirectional_writeback
tests/workpaper_sync/test_task52_j_cycle_migration.py::TestProperty3And20::test_ac14_notice_single_source_exists_and_is_not_duplicated
tests/workpaper_sync/test_task56_n_cycle_migration.py::TestAdjudicationLegality::test_ac14_notice_single_source_exists_and_is_consumed
tests/workpaper_sync/test_task57_abcs_and_shared_migration.py::TestAdjudicationLegality::test_ac14_notice_single_source_exists_and_is_consumed_out_of_scope
```

### C5 · 生成物 / 台账 / frozen baseline 再计算漂移（digest·byte-stable·idempotent）— 15 条｜信度高（新簇）

形态：断言"生成器再跑一次与磁盘一致 / 台账与源同步 / digest 可重算 / 行为等于冻结基线"。
上游源码与数据（`workpaper_writer_inventory.json`、`workpaper_task61_word_pilot_gate_probes.json`、
`workpaper_sync_legacy_baseline.json`、各 generated 前端清册均 M）改动后，生成物未重跑/未更新。

```
tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py::TestProbeRegistryIsLockedToTaskText::test_generated_registry_data_file_is_fresh
tests/workpaper_sync/test_task46_d_cycle_migration.py::TestProperty28DefinitionDriftFailClosed::test_authoritative_templates_digests_recompute
tests/workpaper_sync/test_task46_d_cycle_migration.py::TestProperty28DefinitionDriftFailClosed::test_every_entry_template_ref_is_registered_with_digest
tests/workpaper_sync/test_task50_h_cycle_migration.py::TestProperty28DefinitionDriftFailClosed::test_template_resolution_audit_recomputes
tests/workpaper_sync/test_task58_word_canonical_resolver.py::TestAdjudicationLedger::test_ledger_is_in_sync_with_sources
tests/workpaper_sync/test_task62_generic_docx_entries.py::TestGeneratorIsIdempotentAndCheckIsStrict::test_build_record_is_byte_stable
tests/workpaper_sync/test_task62_generic_docx_entries.py::TestGeneratorIsIdempotentAndCheckIsStrict::test_check_matches_the_file_on_disk
tests/workpaper_sync/test_task63_subcode_adjudication.py::TestAdjudicationRecord::test_record_is_reproducible
tests/workpaper_sync/test_task63_subcode_adjudication.py::TestResidencyReverification::test_source_digests_cover_every_file_the_measured_criteria_read
tests/workpaper_sync/test_task64_dedicated_word_chain.py::TestGeneratorContract::test_generator_check_is_idempotent
tests/workpaper_sync/test_template_override_resolution.py::TestProperty3AuthoritativeFrozen::test_index_size_drift_is_registered_not_growing
tests/workpaper_sync/test_workbook_row_change_reachability.py::test_inventory_matches_current_computation
tests/workpaper_sync/test_workbook_row_change_reachability.py::test_host_binding_is_content_addressed
tests/workpaper_sync/test_workbook_row_change_reachability.py::test_binding_verifier_detects_injected_digest_drift
tests/workpaper_sync/test_workbook_row_change_zero_regression.py::test_behaviour_matches_frozen_baseline
```

### C6 · 前端宿主 / renderer registry / router 源码结构事实漂移 — 8 条｜信度中（新簇）

形态：以**前端源码为事实来源**的断言（宿主存在性、import 边、renderer registry 可达性、
router 声明、写回载体与写入点一致、生成模板路由）。`git status` 显示
`components.d.ts`、`workpaperSyncManifest.generated.ts`、`workpaperSyncLegacyBaseline.generated.ts`
均已改动，属同一波前端结构变更的下游。

```
tests/workpaper_sync/test_task31_frontend_contract.py::test_a_real_slashed_entry_id_still_routes_through_the_generated_template
tests/workpaper_sync/test_task31_frontend_contract.py::test_the_callback_route_is_never_projected_to_the_frontend
tests/workpaper_sync/test_task46_d_cycle_migration.py::TestSourceCodeStructure::test_hosts_exist_and_import_legacy_composable
tests/workpaper_sync/test_task50_h_cycle_migration.py::TestHtmlCounterpartIsSourceBacked::test_write_carrier_client_and_put_site_agree_with_the_source
tests/workpaper_sync/test_task50_h_cycle_migration.py::TestHtmlCounterpartIsSourceBacked::test_payload_column_mode_matches_the_write_site
tests/workpaper_sync/test_task50_h_cycle_migration.py::TestSourceCodeStructure::test_hosts_exist_and_are_reachable_from_the_renderer_registry
tests/workpaper_sync/test_task54_l_cycle_migration.py::TestSheetGranularityAndRouter::test_router_declaration_matches_the_source
tests/workpaper_sync/test_task76_wp_code_adjudication.py::TestHostResolutionNoLongerTrustsTheHeuristic::test_loader_is_fail_closed_when_the_table_is_missing
```

### C7 · legacy 删除 / orphan 清册（与已知 `d2_sync_retirement (needs authorized deletion)` 同族）— 6 条｜信度中

形态：断言"legacy 宿主/composable 已删除、孤儿无生产消费者、删除计划各项真实且互异、
stub 零入边、本模块不引入 writer/resolver 债务"。这些都要**授权删除**才能转绿，
与 `d2_sync_retirement` 的阻塞条件相同（`test_task45` 那条直接就是 D2 宿主）。

```
tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py::TestPilotIntroducesNoResolverDebt::test_no_function_in_this_module_is_classified_as_writer_or_resolver
tests/workpaper_sync/test_task45_pilot_legacy_deletion.py::TestProperty47LegacyDeleted::test_host_imports_bridge_adapter[GtD2AccountsReceivable.vue]
tests/workpaper_sync/test_task49_g_cycle_migration.py::TestProperty70NoCrossEntryReuse::test_unreachable_stub_is_registered_and_still_has_zero_inbound_edges
tests/workpaper_sync/test_task50_h_cycle_migration.py::TestOrphanLegacyComposables::test_declared_orphan_formdata_composables_really_have_no_production_consumer
tests/workpaper_sync/test_task50_h_cycle_migration.py::TestProperty70NoCrossEntryReuse::test_deletion_plan_composables_are_distinct_and_real
tests/workpaper_sync/test_task52_j_cycle_migration.py::TestOrphanDualModeInventory::test_pseudo_string_edges_exist_but_are_not_import_edges
```

### C8 · PG 真实 store 数据形状漂移 — 5 条｜信度中（新簇）

形态：对真实数据库里 store item 的**形状/空性/独占性**断言（866KB 冻结形状、
其它 store item 未被触碰、disposal store 全库为空、三臂确实跑在库上）。
依赖真实 PG 数据状态，与 memory 里"真实 PG 只有 5 个项目、合并类数据缺位"的底账一致。

```
tests/workpaper_sync/test_task41_d2_large_json_pilot_pg.py::test_real_store_payload_is_the_frozen_866kb_shape
tests/workpaper_sync/test_task41_d2_large_json_pilot_pg.py::test_no_other_store_item_is_touched
tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot_pg.py::test_disposal_store_item_is_empty_across_the_whole_database
tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot_pg.py::test_contract_declares_the_observed_emptiness
tests/workpaper_sync/test_task61_oo94_word_pilot_gate.py::TestBindingConstraintIsMeasured::test_the_three_arms_really_run_against_the_database
```

### C9 · 权威工作簿 / 载体语料形状断言 — 7 条｜信度中（新簇）

形态：对权威 xlsx 模板语料的结构断言（十份工作簿同形、defined name 五分类、
scanner↔rewriter 全语料一致、positional identity 清册穷尽且划分、family A 写到声明键、
BP-5 错工作簿回退可复现）。属"语料/载体扫描器"一族。

```
tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py::TestUpstreamRelsAndNamespaceDefectsAreFixed::test_ten_of_the_authoritative_workbooks_share_this_shape
tests/workpaper_sync/test_task43_g7_two_level_dynamic_pilot.py::TestUpstreamRelsAndNamespaceShapesStillHold::test_ten_authoritative_workbooks_share_this_shape
tests/workpaper_sync/test_task48_f_cycle_migration.py::TestProperty28DefinitionDriftFailClosed::test_bp5_wrong_workbook_fallback_is_reproducible
tests/workpaper_sync/test_task50_h_cycle_migration.py::TestProperty23DynamicRowIdentity::test_positional_identity_inventory_is_exhaustive_and_partitioned
tests/workpaper_sync/test_task50_h_cycle_migration.py::TestProperty23DynamicRowIdentity::test_family_a_hits_write_to_the_declared_key
tests/workpaper_sync/test_workbook_row_change_carriers.py::TestScannerRewriterAgreement::test_scanner_agrees_with_rewriter_on_whole_corpus
tests/workpaper_sync/test_workbook_row_change_carriers.py::TestDefinedNameClassification::test_defined_name_five_way_classification
```

### C10 · task65 opaque lane registry 覆盖缺口 — 3 条｜信度高（新簇）

形态：lane 注册表未覆盖全部源调用点 / commit_bytes lane 实参与注册表不符 / 错 lane id
未 fail-closed。三条同一注册表事实。`git status` 显示 `opaque_entry_gate.py` 已改动。

```
tests/workpaper_sync/test_task65_opaque_authority_bundle.py::test_registry_covers_every_source_call_site
tests/workpaper_sync/test_task65_opaque_authority_bundle.py::test_commit_bytes_lane_arguments_match_registry
tests/workpaper_sync/test_task65_opaque_authority_bundle.py::test_wrong_lane_id_argument_fails_closed
```

### C11 · 单点（各自独立成因）— 2 条｜信度中（新簇）

```
tests/workpaper_sync/test_projection_structure_hash_semantics.py::TestBp30IsActuallyWired::test_projection_commit_calls_the_new_hash
tests/workpaper_sync/test_task10_orm_repository_contract.py::test_repository_never_commits
```

- 第 1 条**顺序敏感**（见上文"顺序敏感性实测"：并入 chunk 5+6+12 合并运行时转绿），
  定位时必须固定分组复现，否则会误判为已修。
- 第 2 条是 repository 层"只 flush 不 commit"契约（与 `#conventions` 的 service 只 flush
  铁律同一约束），`published_identity_observer.py` / `d2_bidirectional_bridge.py` 已改动，疑为下游。

### 聚类计数汇总

| 簇 | 条数 | 类型 |
|---|---|---|
| C1 capability-flip platform readiness | 29 | 已知簇 |
| C2 task29 timeline-evidence PG harness 采集崩溃 | 41 | 新簇 |
| C3 manifest / slice 派生事实漂移（task66/67/68 同族） | 20 | 已知簇 |
| C4 AC14 honest-mode notice 单源 | 6 | 新簇 |
| C5 生成物 / 台账 / frozen baseline 再计算漂移 | 15 | 新簇 |
| C6 前端宿主 / renderer registry / router 结构漂移 | 8 | 新簇 |
| C7 legacy 删除 / orphan 清册（d2_sync_retirement 同族） | 6 | 已知簇 |
| C8 PG 真实 store 数据形状漂移 | 5 | 新簇 |
| C9 权威工作簿 / 载体语料形状断言 | 7 | 新簇 |
| C10 task65 opaque lane registry 覆盖缺口 | 3 | 新簇 |
| C11 单点 | 2 | 新簇 |
| **合计** | **142** | — |

已知簇 `milestones producer_tasks_incomplete` 与 `task28 harness digest fabrication` 在本清单里
**0 条** —— 它们的宿主文件（`test_workpaper_sync_program_milestones.py`、
`test_task28_sync_router.py` / `_pg.py`）不在本盘点清单内（见「总计」）。

---

## xfailed 观察

本盘点清单实测 **14 条 xfailed**（chunk 5 ×1、chunk 6 ×1、chunk 12 ×12）。
为拿到逐条 node id，对 chunk 5+6+12 的 36 个文件重跑了一次 `-rx`（14 xfailed，与分块一致）：

```
XFAIL tests/workpaper_sync/test_migration_paradigm_contract.py::TestAntiPatternCircularJustification::test_single_onlyoffice_entry_states_its_html_counterpart[workpaper_sync_e_cycle_manifest_slice|xlsx/gt-e1-monetary-fund]
XFAIL tests/workpaper_sync/test_slice_schema_validator_coverage.py::test_every_registered_debt_entry_still_has_a_carrier
XFAIL tests/workpaper_sync/test_task60_f2_word_adapter.py::test_bp10_the_lane_contracts_are_installed_into_the_production_inventory
XFAIL tests/workpaper_sync/test_task60_f2_word_adapter.py::test_bp11_the_planned_bundle_slots_pass_the_production_gate
XFAIL tests/workpaper_sync/test_task60_f2_word_adapter.py::test_bp12_the_lane_mount_consumes_a_descriptor
XFAIL tests/workpaper_sync/test_task60_f2_word_adapter.py::test_bp13_each_entry_has_a_server_side_evidence_summary
XFAIL tests/workpaper_sync/test_task60_f2_word_adapter.py::test_bp14_the_lane_extract_no_longer_depends_on_chinese_headings
XFAIL tests/workpaper_sync/test_task64_dedicated_word_chain.py::test_bp16_a16_chain_gains_html_field_surface
XFAIL tests/workpaper_sync/test_task64_dedicated_word_chain.py::test_bp17_production_locator_no_longer_uses_cjk_regex
XFAIL tests/workpaper_sync/test_task64_dedicated_word_chain.py::test_bp18_a17_word_kind_is_now_used
XFAIL tests/workpaper_sync/test_task64_dedicated_word_chain.py::test_bp19_word_hosts_become_descriptor_consumers
XFAIL tests/workpaper_sync/test_task64_dedicated_word_chain.py::test_bp20_authority_model_published_to_db
XFAIL tests/workpaper_sync/test_task64_dedicated_word_chain.py::test_bp21_contract_can_express_multiple_templates
XFAIL tests/workpaper_sync/test_task64_dedicated_word_chain.py::test_bp22_a17_subcode_entries_become_docx
```

分布：`test_task64_dedicated_word_chain.py` 7 条（BP-16~BP-22）、
`test_task60_f2_word_adapter.py` 5 条（BP-10~BP-14）、另 2 条各 1（migration paradigm / slice validator）。
全部带有长 reason（写明解除条件与"不得改用 skip"的禁令），且多为 `strict=True`。

基线 16 xfailed − 本清单 14 = **另 2 条在本清单之外的 30 个文件里**（见「总计」）。

---

## 总计

### 本清单的边界（重要）

`backend/tests/workpaper_sync/` 实有 **203** 个 `test_*.py`；本盘点清单
（`backend/scripts/_inv_files.txt`）只含 **173** 个，刻意排除了已在同目录其它
evidence 文档里定过因的 **30** 个文件：

```
test_d2_store_value_equivalence.py          test_task15_content_mutation.py
test_d2_sync_retirement.py                  test_task15_content_mutation_pg.py
test_downstream_base_reliability_gate.py    test_task26_oo_to_html.py
test_excel_row_insertion_readiness.py       test_task26_oo_to_html_pg.py
test_excel_shift_aware_verification.py      test_task27_conflict_resolution_pg.py
test_excel_typography_rows.py               test_task28_sync_router.py
test_projection_lane_regression_gate.py     test_task28_sync_router_pg.py
test_single_pass_artifact_equivalence.py    test_task30_closure_gate.py
test_single_pass_failure_atomicity.py       test_task30_closure_gate_pg.py
test_single_pass_handle_release.py          test_task66_legacy_deletion_plan.py
test_single_pass_materialize.py             test_task67_census_lock.py
test_single_pass_parse_reuse.py             test_task67_structural_pre_reconcile.py
test_single_pass_verify_not_relaxed.py      test_task68_backend_chain_regression.py
test_task12_canonical_resolver.py           test_task68_radiation_surface.py
                                            test_task73_entry_profile_manifest.py
                                            test_workpaper_sync_program_milestones.py
```

这 30 个正是已知簇的宿主：`task66/67/68 manifest_entry_total moving target`（task66/67/68 共 5 个文件）、
`d2_sync_retirement`、`milestones producer_tasks_incomplete`（program_milestones）、
`task28 harness digest fabrication`（task28 ×2），以及 `small-clusters.md` 的 8 个文件、
`errors.md` / `task15` / `task26` / `task27` / `task30` / `single_pass` 各自的文档。

### 与基线对账

基线（全套件一次跑）：`283 failed, 8294 passed, 2 skipped, 16 xfailed, 16 errors`

| 口径 | failed | passed | skipped | xfailed | errors |
|---|---|---|---|---|---|
| 基线（203 文件） | 283 | 8294 | 2 | 16 | 16 |
| 本清单实测（173 文件） | **142** | 7090 | 2 | 14 | 0 |
| 差额 → 落在排除的 30 文件 | **141** | 1204 | 0 | 2 | 16 |

- **本次逐条个体识别的失败：142 条**（node id 全部在本文件中逐条列出，并 100% 归族，无"归不进任何簇"的残留）。
  其中 chunk 1-6 贡献 1 条，chunk 7-15 贡献 141 条。
- **仍未在本文件落账的失败：141 条**。它们**不是**"找不到"，而是按设计落在被排除的 30 个文件里，
  由同目录既有 evidence 文档负责（small-clusters / errors / task66-bp662 /
  milestone-blocked-regression / task27-28-router-conflict-pg / task15 / task26 / db-readings 等）。
  本文件**未**逐条核对那 141 条与既有文档记载条数是否严丝合缝 —— 这是下一步该做的一次交叉对账
  （做法：对那 30 个文件单独跑一次 `-rf`，与各文档声称的条数逐一核对）。
- **skipped 完全对上**（2 = 2），说明 2 个 skip 全在本清单内（chunk 4、chunk 15 各 1）。
- **16 errors 全部在本清单之外**：分块运行 15 块**一个 error 都没有**，errors 归 `errors.md` 管。
- 计数可信度保留项：本套件存在跨文件顺序敏感项（已实测 1 条在不同分组下由 red 转 green），
  故 283 这个基线数与"142 + 141"的加法一致性只在**同一分组口径**下才严格成立。

### 状态

清点完成（chunk 1-15 全部跑完，`_inv_log2.txt` 末行 `===== ALL CHUNKS DONE =====`）。
本任务**只清点未修复**：本次只新建了 `backend/scripts/_inv_run2.py` 与本文件，
任何生产/测试源码都未由本次改动（工作树里其它 M 项来自并发会话，见上文 mtime 表）。
一次性脚本 `backend/scripts/_inv_run2.py`（`_` 前缀 = 用完即删）与日志
`backend/scripts/_inv_log2.txt` 为本文件的原始证据。

下一步（不在本任务范围）：
1. 对被排除的 30 个文件单独跑一次 `-rf`，与既有各 evidence 文档逐条对账那 141 条；
2. 在冻结工作树上重跑全套，产出可签署的定量基线；
3. 按簇修复，优先 C2（41 条 1 个根因）→ C3（20 条，与 manifest 治理同源）→ C1（29 条，多为过期负向断言）。
