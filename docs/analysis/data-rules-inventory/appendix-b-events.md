# 附录 B：事件触发矩阵

> 由脚本对 `backend/app` 做 AST 静态扫描生成。事件类型定义在 `backend/app/models/audit_platform_schemas.py::EventType`。
> 「发布点」= 在 `EventPayload(...)` 或名字含 publish / enqueue / emit 的调用里出现 `EventType.X` 的位置；
> 「订阅点」= `event_bus.subscribe(EventType.X, 处理函数)` 与 `subscribe_many([...])`。
> 现算：事件类型 58 个，有发布方 33 个，有订阅方 35 个，订阅登记 123 处。

## B1 有订阅、但全后端找不到发布方的事件（处理函数永远不会被触发）

按 `EventType.X` 与事件字符串值（如 `"materiality.changed"`）两种写法全仓（后端 + 前端 + 脚本）核对过，都没有发布方。

| 事件 | 值 | 订阅它的处理函数 |
|---|---|---|
| `CHECKLIST_COMPLETED` | `checklist.completed` | `services/event_handlers/_impl.py:2259` _on_checklist_completed_b3 |
| `CROSS_CHECK_FAILED` | `cross_check.failed` | `services/event_handlers/_impl.py:1383` _on_cross_check_failed |
| `MATERIALITY_CHANGED` | `materiality.changed` | `services/a13_event_handler.py:178` _on_materiality_changed<br>`services/event_handlers/_impl.py:858` _invalidate_procedure_table_cache |
| `NOTE_UPDATED` | `note.updated` | `services/consol_note_stale_handler.py:171` handle_child_note_updated |
| `PREFILL_MAPPING_CHANGED` | `prefill_mapping.changed` | `services/event_handlers/_impl.py:1571` _stale_engine_on_prefill_mapping_changed |
| `REPORT_CONFIG_MASTER_UPDATED` | `report_config.master_updated` | `services/event_handlers/_impl.py:2089` _mark_cloned_configs_stale |
| `WORKPAPER_AUDITED_CONFIRMED` | `workpaper.audited_confirmed` | `services/event_handlers/_impl.py:1380` _on_workpaper_audited_confirmed |
| `WORKPAPER_PROCEDURE_COMPLETED` | `workpaper.procedure_completed` | `services/event_handlers/_impl.py:1382` _on_workpaper_procedure_completed |
| `WORKPAPER_REVIEW_PASSED` | `workpaper.review_passed` | `services/event_handlers/_impl.py:1381` _on_workpaper_review_passed<br>`services/event_handlers/_impl.py:1914` on_event_workpaper_reviewed |
| `WORKPAPER_STALE_DETECTED` | `workpaper.stale_detected` | `services/event_handlers/_impl.py:1379` _on_workpaper_stale_detected |

## B2 有发布、没有后端订阅方的事件（只走 SSE 推给前端或无人消费）

`CROSS_REF_UPDATED`、`DISPATCH_CREATED`、`DISPATCH_REVOKED`、`IMPORT_PROGRESS`、`LINKAGE_STALE_CHANGED`、`SYNC_FAILED`、`WORKPAPER_ASSIGNED`、`WORKPAPER_CONTENT_UPDATED`

## B3 逐个事件：谁发、谁收

### `ACCOUNT_MAPPING_CHANGED` — `account_mapping.changed`

- 发布点（1）：`routers/account_chart.py:513` `batch_update_accounts`
- 订阅点（1）：
  - `services/event_handlers/_impl.py:1573` → _stale_engine_on_account_mapping_changed

### `ADJUSTMENT_APPROVED` — `adjustment.approved`
> adj-formula-repair-and-approval-gate-wiring 需求 4.1: 调整分录复核通过 → 下游重算/stale/SSE payload: {project_id, year, account_codes: [...], entry_group_id}

- 发布点（1）：`services/adjustment_review_coordinator.py:201` `AdjustmentReviewCoordinator.decide`
- 订阅点（8）：
  - `services/adjustment_approved_recalc_handler.py:138` → handle_adjustment_approved
  - `services/event_handlers/_impl.py:831` → _mark_workpapers_stale_by_account
  - `services/event_handlers/_impl.py:1056` → _notify_adjustment_event_sse
  - `services/event_handlers/_impl.py:1238` → _mark_reports_stale_on_adjustment
  - `services/event_handlers/_impl.py:1325` → _record_tb_change_on_adjustment
  - `services/event_handlers/_impl.py:1441` → _stale_engine_on_adjustment
  - `services/event_handlers/_impl.py:1915` → on_event_adjustment_approved
  - `services/event_handlers/_impl.py:2210` → _on_upstream_changed_mark_deliverable_stale

### `ADJUSTMENT_BATCH_COMMITTED` — `adjustment.batch_committed`
> Enterprise Linkage: 批量提交 + 级联降级

- 发布点（1）：`services/adjustment_service.py:212` `AdjustmentService.batch_commit`
- 订阅点（3）：
  - `services/event_handlers/_impl.py:780` → _invalidate_formula_cache_on_adjustment
  - `services/event_handlers/_impl.py:856` → _invalidate_procedure_table_cache
  - `services/event_handlers/_impl.py:1068` → _make_tb_handler('on_adjustment_changed')

### `ADJUSTMENT_CLIENT_BOOKING_CHANGED` — `adjustment.client_booking_changed`
> 客户已入账标记/撤销 → 调整列重算与下游刷新

- 发布点（1）：`services/adjustment_client_booking.py:340` `apply_booking_change`
- 订阅点（2）：
  - `services/event_handlers/_impl.py:833` → _mark_workpapers_stale_by_account
  - `services/event_handlers/_impl.py:1058` → _notify_adjustment_event_sse

### `ADJUSTMENT_CREATED` — `adjustment.created`

- 发布点（1）：`services/adjustment_service.py:176` `AdjustmentService.create_entry`
- 订阅点（6）：
  - `services/event_handlers/_impl.py:401` → _make_tb_handler('on_adjustment_changed')
  - `services/event_handlers/_impl.py:752` → _invalidate_formula_cache_on_adjustment
  - `services/event_handlers/_impl.py:853` → _invalidate_procedure_table_cache
  - `services/event_handlers/_impl.py:965` → _invalidate_addr_tb
  - `services/event_handlers/_impl.py:1053` → _notify_adjustment_event_sse
  - `services/event_handlers/_impl.py:1322` → _record_tb_change_on_adjustment

### `ADJUSTMENT_DELETED` — `adjustment.deleted`

- 发布点（1）：`services/adjustment_service.py:388` `AdjustmentService.delete_entry`
- 订阅点（6）：
  - `services/event_handlers/_impl.py:403` → _make_tb_handler('on_adjustment_changed')
  - `services/event_handlers/_impl.py:760` → _invalidate_formula_cache_on_adjustment
  - `services/event_handlers/_impl.py:855` → _invalidate_procedure_table_cache
  - `services/event_handlers/_impl.py:967` → _invalidate_addr_tb
  - `services/event_handlers/_impl.py:1055` → _notify_adjustment_event_sse
  - `services/event_handlers/_impl.py:1324` → _record_tb_change_on_adjustment

### `ADJUSTMENT_REVIEW_REVOKED` — `adjustment.review_revoked`
> 调整分录撤回复核 → 与审批通过走同一套下游链路

- 发布点（1）：`services/adjustment_review_coordinator.py:265` `AdjustmentReviewCoordinator.revoke`
- 订阅点（8）：
  - `services/adjustment_approved_recalc_handler.py:139` → handle_adjustment_review_revoked
  - `services/event_handlers/_impl.py:832` → _mark_workpapers_stale_by_account
  - `services/event_handlers/_impl.py:1057` → _notify_adjustment_event_sse
  - `services/event_handlers/_impl.py:1239` → _mark_reports_stale_on_adjustment
  - `services/event_handlers/_impl.py:1326` → _record_tb_change_on_adjustment
  - `services/event_handlers/_impl.py:1442` → _stale_engine_on_adjustment
  - `services/event_handlers/_impl.py:1916` → on_event_adjustment_review_revoked
  - `services/event_handlers/_impl.py:2211` → _on_upstream_changed_mark_deliverable_stale

### `ADJUSTMENT_TREATMENT_CHANGED` — `adjustment.treatment_changed`
> 最终财务处理（纳入工作试算表 / 不予更正 / 撤销）变化

- 发布点（1）：`services/adjustment_treatment_service.py:379` `_recalculate_and_enqueue`
- 订阅点（2）：
  - `services/event_handlers/_impl.py:834` → _mark_workpapers_stale_by_account
  - `services/event_handlers/_impl.py:1059` → _notify_adjustment_event_sse

### `ADJUSTMENT_UPDATED` — `adjustment.updated`

- 发布点（1）：`services/adjustment_service.py:316` `AdjustmentService.update_entry`
- 订阅点（6）：
  - `services/event_handlers/_impl.py:402` → _make_tb_handler('on_adjustment_changed')
  - `services/event_handlers/_impl.py:756` → _invalidate_formula_cache_on_adjustment
  - `services/event_handlers/_impl.py:854` → _invalidate_procedure_table_cache
  - `services/event_handlers/_impl.py:966` → _invalidate_addr_tb
  - `services/event_handlers/_impl.py:1054` → _notify_adjustment_event_sse
  - `services/event_handlers/_impl.py:1323` → _record_tb_change_on_adjustment

### `CHECKLIST_COMPLETED` — `checklist.completed`
> B 类底稿联动: B3 独立性核对表完成 → A17-7 声明书状态更新

- 发布点（0）：无
- 订阅点（1）：
  - `services/event_handlers/_impl.py:2259` → _on_checklist_completed_b3

### `CONFIRMATION_RECEIVED` — `confirmation.received`
> D 销售循环 F6: 函证回函 → D2 stale 传播

- 发布点（1）：`services/confirmation_service.py:560` `apply_confirmation_result`
- 订阅点（1）：
  - `services/event_handlers_cycle_linkage.py:668` → _on_confirmation_received

### `CROSS_CHECK_FAILED` — `cross_check.failed`

- 发布点（0）：无
- 订阅点（1）：
  - `services/event_handlers/_impl.py:1383` → _on_cross_check_failed

### `CROSS_REF_UPDATED` — `cross_ref.updated`
> H-F8: 跨底稿引用更新（H9→H8 租赁两表反向回填）

- 发布点（2）：`services/event_handlers/_impl.py:1637` `register_event_handlers._on_h_lease_reverse_backfill`；`services/event_handlers/_impl.py:1719` `register_event_handlers._on_i_rd_reverse_backfill`
- 订阅点（0）：

### `DATA_IMPORTED` — `data.imported`

- 发布点（3）：`services/import_service.py:190` `start_import`；`services/import_service.py:741` `start_import_streaming`；`services/smart_import_engine.py:2207` `write_four_tables`
- 订阅点（6）：
  - `services/event_handlers/_impl.py:408` → _make_tb_handler('on_data_imported')
  - `services/event_handlers/_impl.py:764` → _invalidate_formula_cache_all
  - `services/event_handlers/_impl.py:828` → _mark_workpapers_stale_all
  - `services/event_handlers/_impl.py:862` → _invalidate_procedure_table_cache
  - `services/event_handlers/_impl.py:973` → _invalidate_addr_all
  - `services/event_handlers/_impl.py:1443` → _stale_engine_on_data_imported

### `DISPATCH_CREATED` — `dispatch.created`
> cross-workpaper-dispatch-persistence: D0-1 跨底稿分发事件

- 发布点（1）：`routers/dispatch_records.py:160` `create_dispatch_records`
- 订阅点（0）：

### `DISPATCH_REVOKED` — `dispatch.revoked`

- 发布点（1）：`routers/dispatch_records.py:222` `revoke_dispatch_record`
- 订阅点（0）：

### `ELIMINATION_APPROVED` — `elimination.approved`
> consol-phase1-arch-lock 需求 2.3: 抵销分录审批 → worksheet + trial 重算 consol-elimination-single-source-push 需求 8.1 起改为触发合并推送（差额表 → 试算 → 报表 → 附注标记） payload: {project_id, year, extra: {entry_id}}

- 发布点（1）：`routers/consolidation.py:312` `review_elimination`
- 订阅点（1）：
  - `services/consol_elimination_recalc_handler.py:100` → handle_elimination_approved

### `ELIMINATION_REVOKED` — `elimination.revoked`
> consol-elimination-single-source-push 需求 8.2: 撤销审批（已审批 → 草稿）→ 同样触发合并推送 payload: {project_id, year, extra: {entry_id}}

- 发布点（1）：`routers/consolidation.py:312` `review_elimination`
- 订阅点（1）：
  - `services/consol_elimination_recalc_handler.py:101` → handle_elimination_revoked

### `FORMULA_CONFIG_CHANGED` — `formula_config.changed`
> Global Linkage Bus Sprint 3: 反向联动事件

- 发布点（2）：`services/formula_settings/outbox.py:131` `record_changes`；`services/formula_settings/propagation.py:85` `publish_events`
- 订阅点（2）：
  - `services/event_handlers/_impl.py:1570` → _stale_engine_on_formula_config_changed
  - `services/formula_settings/propagation.py:455` → on_formula_config_changed

### `IMPORT_PROGRESS` — `import.progress`

- 发布点（1）：`services/import_service.py:721` `start_import_streaming`
- 订阅点（0）：

### `IMPORT_ROLLED_BACK` — `import.rolled_back`

- 发布点（1）：`services/import_service.py:408` `rollback_import`
- 订阅点（1）：
  - `services/event_handlers/_impl.py:434` → _make_tb_handler('on_import_rolled_back')

### `LEDGER_DATASET_ACTIVATED` — `ledger.dataset_activated`

- 发布点（3）：`services/dataset_service.py:295` `DatasetService.activate`；`services/dataset_service.py:512` `DatasetService.publish_dataset_activated`；`services/event_handlers/_impl.py:286` `_report_auto_map_outcome`
- 订阅点（9）：
  - `services/event_handlers/_impl.py:412` → _make_tb_handler('on_data_imported')
  - `services/event_handlers/_impl.py:418` → _auto_map_on_dataset_activated
  - `services/event_handlers/_impl.py:424` → _advance_project_status_on_dataset_activated
  - `services/event_handlers/_impl.py:768` → _invalidate_formula_cache_all
  - `services/event_handlers/_impl.py:829` → _mark_workpapers_stale_all
  - `services/event_handlers/_impl.py:863` → _invalidate_procedure_table_cache
  - `services/event_handlers/_impl.py:974` → _invalidate_addr_all
  - `services/event_handlers/_impl.py:1444` → _stale_engine_on_data_imported
  - `services/event_handlers/_impl.py:1913` → on_event_ledger_activated

### `LEDGER_DATASET_ROLLED_BACK` — `ledger.dataset_rolled_back`

- 发布点（2）：`services/dataset_service.py:454` `DatasetService.rollback`；`services/dataset_service.py:538` `DatasetService.publish_dataset_rolled_back`
- 订阅点（6）：
  - `services/event_handlers/_impl.py:428` → _make_tb_handler('on_import_rolled_back')
  - `services/event_handlers/_impl.py:772` → _invalidate_formula_cache_all
  - `services/event_handlers/_impl.py:830` → _mark_workpapers_stale_all
  - `services/event_handlers/_impl.py:864` → _invalidate_procedure_table_cache
  - `services/event_handlers/_impl.py:924` → _mark_downstream_stale_on_rollback
  - `services/event_handlers/_impl.py:976` → _invalidate_addr_all

### `LINKAGE_STALE_CHANGED` — `linkage.stale_changed`
> Global Linkage Bus Sprint 4: stale 传播专用事件

- 发布点（1）：`services/stale_propagation_engine.py:414` `StalePropagationEngine._notify_frontend`
- 订阅点（0）：

### `MAPPING_CHANGED` — `mapping.changed`

- 发布点（1）：`services/mapping_service.py:116` `_publish_mapping_changed`
- 订阅点（4）：
  - `services/event_handlers/_impl.py:404` → _make_tb_handler('on_mapping_changed')
  - `services/event_handlers/_impl.py:776` → _invalidate_formula_cache_on_adjustment
  - `services/event_handlers/_impl.py:835` → _mark_workpapers_stale_by_account
  - `services/event_handlers/_impl.py:1446` → _stale_engine_on_mapping_changed

### `MATERIALITY_CHANGED` — `materiality.changed`

- 发布点（0）：无
- 订阅点（2）：
  - `services/a13_event_handler.py:178` → _on_materiality_changed
  - `services/event_handlers/_impl.py:858` → _invalidate_procedure_table_cache

### `NOTE_SECTION_SAVED` — `note_section.saved`

- 发布点（11）：`routers/ai_content.py:305` `_note_saved_event`；`routers/disclosure_notes.py:270` `generate_notes._event`；`routers/disclosure_notes.py:945` `update_note._event`；`routers/disclosure_notes.py:995` `delete_section._event`；`routers/disclosure_notes.py:1048` `patch_section._event`；`routers/disclosure_notes.py:1100` `restore_section._event`；`routers/note_offline.py:144` `execute_import`；`routers/wp_disclosure_sync.py:229` `_publish_note_saved`；`services/deliverable_writeback_service.py:1129` `DeliverableWritebackService._emit_note_saved`；`services/note_text_batch_apply.py:244` `build_note_saved_events`；`services/formula_push/note_events.py:27` `publish_note_sections`
- 订阅点（4）：
  - `services/consol_note_stale_handler.py:173` → _on_note_section_saved_mark_consol_stale
  - `services/event_handlers/_impl.py:971` → _invalidate_addr_note
  - `services/event_handlers/_impl.py:1572` → _stale_engine_on_note_section_saved
  - `services/event_handlers/_impl.py:2215` → _on_upstream_changed_mark_deliverable_stale

### `NOTE_UPDATED` — `note.updated`

- 发布点（0）：无
- 订阅点（1）：
  - `services/consol_note_stale_handler.py:171` → handle_child_note_updated

### `PREFILL_MAPPING_CHANGED` — `prefill_mapping.changed`

- 发布点（0）：无
- 订阅点（1）：
  - `services/event_handlers/_impl.py:1571` → _stale_engine_on_prefill_mapping_changed

### `REPORTS_UPDATED` — `reports.updated`

- 发布点（3）：`routers/reports.py:115` `generate_reports`；`services/formula_management/refresh_report_scope.py:112` `execute_report_scope`；`services/formula_settings/propagation.py:235` `propagate_report`
- 订阅点（4）：
  - `services/event_handlers/_impl.py:452` → _make_handler(DisclosureEngine, 'on_reports_updated')
  - `services/event_handlers/_impl.py:459` → _make_handler(AuditReportService, 'on_reports_updated')
  - `services/event_handlers/_impl.py:969` → _invalidate_addr_report
  - `services/event_handlers/_impl.py:2213` → _on_upstream_changed_mark_deliverable_stale

### `REPORT_CONFIG_MASTER_UPDATED` — `report_config.master_updated`
> report-config-baseline 需求 2.1: 主模板更新 → 克隆项目 stale 通知 payload: {project_id (placeholder), extra: {standard, report_type, row_code, config_id}}

- 发布点（0）：无
- 订阅点（1）：
  - `services/event_handlers/_impl.py:2089` → _mark_cloned_configs_stale

### `REPORT_ROW_CHANGED` — `report_row.changed`

- 发布点（2）：`services/report_engine.py:1431` `ReportEngine.generate_all_reports`；`services/formula_management/refresh_report_scope.py:110` `execute_report_scope`
- 订阅点（1）：
  - `services/event_handlers/_impl.py:1574` → _stale_engine_on_report_row_changed

### `REVIEW_RECORD_CREATED` — `review_record.created`
> R1 需求 2：复核意见 → 工单补偿联动

- 发布点（1）：`services/wp_review_service.py:164` `WpReviewService._create_issue_ticket_from_review`
- 订阅点（1）：
  - `services/event_handlers/_impl.py:712` → _on_review_record_created

### `STANDARD_CHANGED` — `standard_changed`
> multi-standard-unification 需求 1.5: 适用准则统一源变更事件 payload: {project_id, year, old_standard: dict, new_standard: dict, changed_by: UUID}

- 发布点（1）：`services/standard_unification_service.py:302` `StandardUnificationService.set_standard`
- 订阅点（2）：
  - `services/event_handlers/_impl.py:1995` → _on_standard_changed_notes
  - `services/event_handlers/_impl.py:2029` → _on_standard_changed_reports

### `SYNC_FAILED` — `sync.failed`
> Phase 18: 事件链路失败通知

- 发布点（3）：`services/event_bus.py:465` `EventBus._dispatch`；`services/event_handlers/_impl.py:282` `_report_auto_map_outcome`；`services/formula_push/triggers.py:111` `_notify_failed`
- 订阅点（0）：

### `TRIAL_BALANCE_UPDATED` — `trial_balance.updated`

- 发布点（9）：`routers/tb_sync.py:53` `sync_from_workpaper`；`routers/trial_balance.py:257` `recalc_trial_balance`；`services/adjustment_approved_recalc_handler.py:80` `_handle_adjustment_review_event`；`services/adjustment_client_booking.py:348` `apply_booking_change`；`services/adjustment_review_coordinator.py:209` `AdjustmentReviewCoordinator.decide`；`services/adjustment_review_coordinator.py:273` `AdjustmentReviewCoordinator.revoke`；`services/adjustment_treatment_service.py:387` `_recalculate_and_enqueue`；`services/event_handlers_cycle_linkage.py:583` `_on_d_audit_determination_saved`；`services/tb_publish_service.py:163` `publish_workpaper_rows`
- 订阅点（6）：
  - `services/consol_trial_stale_handler.py:127` → handle_child_tb_updated
  - `services/event_handlers/_impl.py:441` → _make_handler(ReportEngine, 'on_trial_balance_updated', after_commit_event_type=EventType.REPORTS_UPDATED)
  - `services/event_handlers/_impl.py:860` → _invalidate_procedure_table_cache
  - `services/event_handlers/_impl.py:968` → _invalidate_addr_tb
  - `services/event_handlers/_impl.py:1275` → _log_cascade_on_tb_updated
  - `services/formula_push/triggers.py:222` → on_trial_balance_updated

### `WORKPAPER_ASSIGNED` — `workpaper.assigned`
> Batch 3 Fix 3: 批量委派事件供 event_handlers 级联

- 发布点（1）：`routers/batch_assign_enhanced.py:298` `batch_assign_enhanced`
- 订阅点（0）：

### `WORKPAPER_AUDITED_CONFIRMED` — `workpaper.audited_confirmed`
> Sprint 10: 底稿深度优化事件

- 发布点（0）：无
- 订阅点（1）：
  - `services/event_handlers/_impl.py:1380` → _on_workpaper_audited_confirmed

### `WORKPAPER_CONTENT_UPDATED` — `workpaper.content.updated`
> workpaper-html-onlyoffice-bidirectional-writeback-closure Task 15 / AC 13.1: 业务内容 commit 与 representation generation 发布的耐久事件。与 WORKPAPER_SAVED 分开是刻意的：后者是 HTML 保存的既有语义（含状态/复核变化），本事件只在 ContentMutationSe

- 发布点（3）：`services/workpaper_sync/content_mutation.py:1356` `ContentMutationService.commit_html_projection`；`services/workpaper_sync/content_mutation.py:2246` `ContentMutationService._commit_once`；`services/workpaper_sync/representations.py:493` `RepresentationService.finalize_candidate`
- 订阅点（0）：

### `WORKPAPER_PROCEDURE_COMPLETED` — `workpaper.procedure_completed`

- 发布点（0）：无
- 订阅点（1）：
  - `services/event_handlers/_impl.py:1382` → _on_workpaper_procedure_completed

### `WORKPAPER_REVIEW_PASSED` — `workpaper.review_passed`

- 发布点（0）：无
- 订阅点（2）：
  - `services/event_handlers/_impl.py:1381` → _on_workpaper_review_passed
  - `services/event_handlers/_impl.py:1914` → on_event_workpaper_reviewed

### `WORKPAPER_SAVED` — `workpaper.saved`

- 发布点（15）：`routers/checklist_responses.py:367` `_publish_checklist_saved`；`routers/s_estimate_calculation.py:195` `s_estimate_tb_writeback`；`routers/s_estimate_calculation.py:290` `s_estimate_tb_writeback_batch`；`routers/s_transaction_calculation.py:198` `s_transaction_tb_writeback`；`routers/s_transaction_calculation.py:294` `s_transaction_tb_writeback_batch`；`routers/wp_html_save.py:557` `_maybe_publish_determination_writeback`；`services/confirmation_evidence_service.py:999` `apply_reply`；`services/confirmation_service.py:384` `transition_status`；`services/confirmation_service.py:483` `reverse_status`；`services/tb_publish_service.py:156` `publish_workpaper_rows`；`services/wopi_service.py:498` `WOPIHostService.put_file`；`services/workpaper_save_orchestrator.py:147` `WorkpaperSaveOrchestrator.after_save` …
- 订阅点（20）：
  - `services/a13_event_handler.py:162` → _on_a13_sheet_saved
  - `services/event_handlers_cycle_linkage.py:662` → _on_c_control_test_saved
  - `services/event_handlers_cycle_linkage.py:663` → _on_c_deviation_saved
  - `services/event_handlers_cycle_linkage.py:664` → _on_c22_itgc_saved
  - `services/event_handlers_cycle_linkage.py:665` → _on_f_workpaper_conclusion_saved
  - `services/event_handlers_cycle_linkage.py:666` → _on_d_audit_determination_saved
  - `services/event_handlers_cycle_linkage.py:681` → _mark_disclosure_stale
  - `services/event_handlers_cycle_linkage.py:688` → _on_workpaper_saved_wp_formula_stale
  - `services/acnr/events.py:214` → on_workpaper_saved
  - `services/event_handlers/_impl.py:484` → _on_workpaper_saved
  - `services/event_handlers/_impl.py:553` → _on_b515_high_risk
  - `services/event_handlers/_impl.py:614` → _on_b514_high_risk
  - `services/event_handlers/_impl.py:866` → _invalidate_procedure_table_cache
  - `services/event_handlers/_impl.py:1445` → _stale_engine_on_workpaper_saved
  - `services/event_handlers/_impl.py:1653` → _on_h_lease_reverse_backfill
  - `services/event_handlers/_impl.py:1735` → _on_i_rd_reverse_backfill
  - `services/event_handlers/_impl.py:2346` → _on_b23_saved
  - `services/event_handlers/_impl.py:2378` → _on_b50_saved
  - `services/event_handlers/_impl.py:2440` → _on_b2_completed
  - `services/formula_push/triggers.py:223` → on_workpaper_saved

### `WORKPAPER_STALE_DETECTED` — `workpaper.stale_detected`

- 发布点（0）：无
- 订阅点（1）：
  - `services/event_handlers/_impl.py:1379` → _on_workpaper_stale_detected

## B4 定义了但代码里没有任何使用的事件类型

`CONSOL_SCOPE_CHANGED`、`EXPORT_COMPLETE`、`EXPORT_FAILED`、`EXPORT_PROGRESS`、`LEDGER_DATASET_VALIDATED`、`LEDGER_IMPORT_DETECTED`、`LEDGER_IMPORT_FAILED`、`LEDGER_IMPORT_SUBMITTED`、`LINKAGE_CASCADE_DEGRADED`、`PRESENCE_EDITING_STARTED`、`PRESENCE_EDITING_STOPPED`、`PRESENCE_JOINED`、`PRESENCE_LEFT`、`REVIEW_ACCEPTED`、`REVIEW_COMPLETED`

