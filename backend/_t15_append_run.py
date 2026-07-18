"""One-shot: append Task 15 run to the evidence manifest, then run precheck."""
from app.security.evidence_manifest import append_run, precheck

TEST_IDS = [
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestEntryFamilyWire404RealApp::test_render_config_out_of_scope_404",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestEntryFamilyWire404RealApp::test_render_config_nonexistent_404",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestEntryFamilyWire404RealApp::test_render_config_cross_project_404",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestEntryFamilyWire404RealApp::test_checklist_out_of_scope_404",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestEntryFamilyWire404RealApp::test_parsed_data_nonexistent_404",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestEntryFamilyWire404RealApp::test_parsed_data_out_of_scope_blocked",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestEntryFamilyWire404RealApp::test_status_nonexistent_404",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestEntryFamilyWire404RealApp::test_version_list_out_of_scope_404",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestEntryFamilyWire404RealApp::test_procedure_task_out_of_scope_404",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestEntryFamilyWire404RealApp::test_dedicated_out_of_scope_404",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestEntryFamilyWire404RealApp::test_dedicated_nonexistent_404",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestEntryFamilyWire404RealApp::test_file_export_out_of_scope_404",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestEntryFamilyWire404RealApp::test_ai_out_of_scope_404",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestEntryFamilyWire404RealApp::test_ai_nonexistent_404",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestSheetVersionTokenDimensions::test_unmapped_sheet_wire_404",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestSheetVersionTokenDimensions::test_row_only_unmapped_sheet_wire_404",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestSheetVersionTokenDimensions::test_historical_version_wire_404",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestSheetVersionTokenDimensions::test_editor_token_claim_mismatch_wire_404",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestSheetVersionTokenDimensions::test_all_dimensions_identical_wire_body",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestSecurityRegressions::test_outbox_write_failure_keeps_404",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestSecurityRegressions::test_outbox_write_failure_keeps_429",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestSecurityRegressions::test_no_side_effect_before_denial",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestSecurityRegressions::test_two_layer_history_scope_epoch_atomic_commit",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestSecurityRegressions::test_delegation_reject_writes_nothing",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestSecurityRegressions::test_callback_regate_rejects_after_revocation",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestSecurityRegressions::test_bulk_preflight_atomic_deny_before_side_effect",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestCrashBeforePublishNoStaleAllow::test_epoch_and_outbox_block_stale_allow_when_publish_crashes",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestCrashBeforePublishNoStaleAllow::test_within_window_still_allows_bounded_staleness",
    "tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestExplainAndQueryCount::test_explain_plans_and_no_n1_artifact",
]

CRITERION_IDS = [
    "3.14", "3.15",
    "8.1", "8.2", "8.3", "8.4", "8.5", "8.6", "8.11", "8.12", "8.13", "8.14",
    "8.15", "8.16", "8.18", "8.19",
    "9.1", "9.2", "9.3", "9.4", "9.5", "9.6", "9.7", "9.8", "9.9", "9.10", "9.11",
    "10.1", "10.4", "10.5",
    "14.20", "14.21",
    "16.15", "16.16", "16.17",
]

NOTES = (
    "Task 15 C10/C12/C15/C17 全入口集成 + 安全回归 + EXPLAIN. 真实 FastAPI app(app.main:app) + "
    "真实 PostgreSQL(audit_platform). 29 passed. "
    "Section1 每 Entry_Family 代表性路由 wire 404(render/checklist/parsed-data/status/version/"
    "procedure-task/dedicated/file-export/AI): 不存在/越权(out-of-scope)/跨项目 → 404 + "
    "{'detail':'资源不存在或不可访问'}; 写路由(parsed-data/checklist PUT)出示既有 edit 门 403 或 gate 404 "
    "均阻断(不 200). Section2 门服务 sheet/version/token 维度: 未映射页(含 row-only)/历史版本/token "
    "claim 不一致 → 统一 404; 全维度(不存在/跨项目/越权/未映射页/历史版本)字节级相同 wire body. "
    "Section3 安全回归: outbox 写入失败不改 404/429(Property12); 拒绝前无副作用(越权 checklist PUT 后 "
    "checklist_responses 行数=0); 两层委派 working_paper.assigned_to+procedure_instances.assigned_to+"
    "workpaper_delegation_history+policy_epoch+invalidation_outbox 同 flush 单元原子(Property17); "
    "映射不成立拒绝写零行; callback(entry_kind=callback) 撤权后 re-gate 拒绝; bulk 逐资源 preflight "
    "任一 deny 副作用前整请求失败. Section4 permission commit 后 publish(Redis fan-out)崩溃 → dispatcher "
    "从不发布, 持久 epoch(1→2)+invalidation outbox 落库仍在, 缓存节点靠 ≤1s DB epoch 核对收敛拒绝, "
    "绝不 stale-allow(Property18); 配对证明 ≤1s 有界 stale 窗口. Section5 EXPLAIN(ANALYZE,BUFFERS) "
    "visibility UNION + 单资源 gate + list dedupe CTE 计划(artifact explain_plans.txt) + query-count "
    "常量=1(6 可见底稿无 per-wp N+1). INDEX DECISION: 热路径全走既有索引/主键, "
    "workpaper_delegation_history 仅对 59 行 seq scan(成本可忽略), EXPLAIN 未实证证明新增索引改善 → "
    "不新增索引(spec: 仅当 EXPLAIN 证明改善才加); 未来生产规模(Task17)若现扫描热点, 候选 "
    "workpaper_delegation_history(project_id,new_user_id) / working_paper(project_id,assigned_to) "
    "再以新 before/after 计划复评. "
    "GAP(honest): 10.2/10.3(签名/过期)/10.6-10.11(callback token 全量重校验)/8.7-8.10 附件/编辑器/复核 "
    "的完整 token 语义与真实签名回调归 Task 11(test_editor_security)已覆盖, 本 run 仅覆盖 gate 层的 "
    "token claim 一致性(10.1/10.4/10.5); 16.18(Rate_Limit_Profile 来自 6000 并发容量)与真实 6000 并发 "
    "容量冻结归 Task 17; list 族越权表现为可见性过滤(空集)而非 404, 归 Task 8 契约."
)

run = append_run(
    task_id="15. 完成全入口 PostgreSQL/FastAPI 集成、安全回归与 EXPLAIN",
    status="passed",
    artifacts=[
        "evidence/artifacts/task15/task15_junit.xml",
        "evidence/artifacts/task15/explain_plans.txt",
    ],
    test_ids=TEST_IDS,
    criterion_ids=CRITERION_IDS,
    command=(
        "rtk python -m pytest tests/procedure_delegation_visibility/"
        "test_task15_full_entry_integration.py -q "
        "--junitxml=D:/GT_plan/.kiro/specs/procedure-delegation-visibility-isolation/"
        "evidence/artifacts/task15/task15_junit.xml"
    ),
    started_at="2026-07-16T21:05:00+00:00",
    notes=NOTES,
)
print("appended seq:", run["seq"])
problems = precheck()
print("precheck problems:", problems)
