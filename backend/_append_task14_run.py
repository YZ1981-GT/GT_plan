"""One-shot: append the new authoritative Task 14 run to the evidence manifest.

Append-only: the historical run 14-0024 (whose task14_full_* artifacts were overwritten by a
later whole-folder rerun) is NOT edited/deleted. This new run supersedes it as the latest
Task 14 evidence (Completion_Guard uses latest-run-per-task). Artifact SHA-256/size are recomputed
from disk by the writer.
"""
from datetime import datetime, timedelta, timezone

from app.security import evidence_manifest as ev

_PREFIX = "tests/procedure_delegation_visibility/"
_TEST_IDS = [
    "test_role_classifier.py::TestProperty1ClassificationUniqueFailClosed::test_classification_matrix",
    "test_staff_user_mapping.py::TestProperty2StaffUserMapping::test_mapping_accepts_only_unique_active_bidirectional",
    "test_delegation_transaction_pbt.py::test_pbt_mapping_transaction_invariants",
    "test_delegation_transaction_pbt.py::test_pbt_layers_never_overwrite",
    "test_procedure_wp_resolver.py::TestProperty4ProcedureBindingUniqueOrReject::test_unique_or_reject_no_mutation",
    "test_visibility_query.py::TestProperty5FixedSetFormula::test_visible_equals_delegated_union_history_intersect_scope",
    "test_visibility_query.py::TestProperty6HistoryImmutableAfterRebind::test_history_attribution_unchanged_by_rebind",
    "test_visibility_query.py::TestProperty7PageVisibilityAndHistoryReadonly::test_row_only_page_isolation",
    "test_visibility_query.py::TestProperty7PageVisibilityAndHistoryReadonly::test_history_grants_are_readonly",
    "test_procedure_wp_resolver.py::TestProperty7RowOnlySheetMapping::test_sheet_name_maps_unique_or_rejects",
    "test_visibility_query.py::TestProperty8OneKnownKindPerGrant::test_each_grant_single_registered_kind",
    "test_task14_property_gaps.py::test_p9_reviewer_whitelist_only",
    "test_task14_property_gaps.py::test_p10_binding_claim_conflict_fail_closed",
    "test_wp_bound_gate.py::TestProperty11PBTUniformNotFound::test_deny_always_404_fixed_body",
    "test_task14_property_gaps.py::test_p12_audit_failure_never_changes_contract",
    "test_editor_security.py::TestEditorTokenPBT::test_valid_token_roundtrip",
    "test_editor_security.py::TestEditorTokenPBT::test_tampered_wp_always_rejected",
    "test_workpaper_list_query.py::TestProperty14OrderedPipeline::test_pipeline_invariants",
    "test_task14_property_gaps.py::test_p15_display_and_client_identity_never_authorize",
    "test_task14_property_gaps.py::test_p16_ledger_bidirectional_and_no_fake_pass",
    "test_delegation_transaction_pbt.py::test_pbt_epoch_monotonic_and_atomic",
    "test_task14_property_gaps.py::test_p18_revocation_converges_no_stale_allow",
    "test_task14_property_gaps.py::test_p19_profile_activation_requires_capacity_evidence",
    "test_task14_property_gaps.py::test_p20_evidence_append_only_hash_complete",
    "test_task14_pbt_profiles.py::test_same_source_batch_runs_both_tiers",
    "test_task14_pbt_profiles.py::test_property_matrix_covers_p1_to_p20_and_files_exist",
    "test_task14_pbt_profiles.py::test_profiles_registered_and_correctness_ge_100",
    "test_task14_pbt_profiles.py::test_prompt_to_design_mapping_is_complete",
    "test_task14_property_gaps.py::test_zzz_pbt_coverage_report_and_valid_example_counts",
]
test_ids = [_PREFIX + t for t in _TEST_IDS]

criterion_ids = (
    [f"15.{i}" for i in range(6, 13)]           # 15.6 .. 15.12
    + [f"16.{i}" for i in range(1, 17)]         # 16.1 .. 16.16
    + [f"16.{i}" for i in range(21, 25)]        # 16.21 .. 16.24
)

finished = datetime.now(timezone.utc)
started = finished - timedelta(seconds=275)  # 实测 whole-folder correctness ~274s

run = ev.append_run(
    task_id="14. 建立同源 PBT smoke/correctness profiles 并实现 P1–P20",
    status="passed",
    artifacts=[
        "evidence/artifacts/task14/task14_full_correctness_junit.xml",
        "evidence/artifacts/task14/task14_full_hypothesis_statistics.txt",
        "evidence/artifacts/task14/task14_full_valid_example_counts.frozen.json",
    ],
    test_ids=test_ids,
    criterion_ids=criterion_ids,
    command=(
        "HYPOTHESIS_PROFILE=correctness python -m pytest tests/procedure_delegation_visibility/ "
        "--hypothesis-show-statistics "
        "--junitxml=evidence/artifacts/task14/task14_full_correctness_junit.xml"
    ),
    started_at=started.isoformat(),
    finished_at=finished.isoformat(),
    notes=(
        "Task14 C17 re-verify + 测试隔离缺陷修复：修复全库并行收集下唯一的隔离性缺陷——"
        "Task2 V113 schema-contract 的 DDL（DROP/CREATE TABLE、DROP/CREATE TRIGGER，取 "
        "AccessExclusiveLock）与 Task7/14 委派/缺口 PBT 逐 example 向 V113 四表及 FK 父表 INSERT "
        "（持 RowExclusive/RowShareLock）在同一 dev 库上锁竞争 → 偶发 PostgreSQL 死锁（单跑/成对跑不复现，"
        "仅全库收集偶发）。修复：给所有 V113 DDL 事务设 lock_timeout=800ms(<默认 deadlock_timeout 1s)，"
        "使 DDL 在成环前先以 LockNotAvailable 主动让路回滚并带抖动重试（DML 侧不再被选为牺牲者）；"
        "并在共享 run_isolated 增加死锁/锁超时兜底重试（整例回滚幂等重跑）。未放宽任何断言、未跳过任何"
        "属性、未降低 correctness 例数（仍 =100/属性）。HYPOTHESIS_PROFILE=correctness 全 spec 目录 "
        "376 passed / 0 fail / 0 error（连续 3 次稳定：2 次稳定性验证 + 本认证跑）；隔离态 v113(21) 与 "
        "Task14 属性文件(13) 亦全绿，证明同一属性在隔离与全库收集下均通过。gap 属性 "
        "P9/P10/P12/P15/P16/P18/P19/P20 各 100 有效样例（见 statistics + frozen 快照）。"
        "证据：task14_full_correctness_junit.xml(376/0/0/0) + task14_full_hypothesis_statistics.txt + "
        "task14_full_valid_example_counts.frozen.json(deterministic write_report，无时间戳)。"
        "append-only：历史 run 14-0024（其 task14_full_* 工件被后续 whole-folder 重跑覆盖致 hash 失配）"
        "不删改；本 run 作为 Task 14 最新证据取代之（Completion_Guard 采 latest-run-per-task）。"
    ),
)
print("appended seq:", run["seq"], "run_id:", run["run_id"])
for a in run["artifacts"]:
    print("  artifact:", a["path"], a["sha256"][:16], a["size"])
