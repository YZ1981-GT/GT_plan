# Implementation Plan

## Overview

创建 WorkpaperSaveOrchestrator 统一后处理层，逐步迁移 4 条写入路径，消除孤立 EventBus。

## Tasks

- [ ] 1. Create `WorkpaperSaveOrchestrator` class
  - New file: `backend/app/services/workpaper_save_orchestrator.py`
  - Implement `after_save(db, wp, user, trigger, extra, expected_version)` method
  - Steps: optimistic lock check → file_version++ → prefill_stale → updated_at → audit log → event_bus.publish
  - Only flush, not commit (router统一commit)
  - _Requirements: 1.1, 1.2, 2.1_

- [ ] 2. Unit tests for `WorkpaperSaveOrchestrator`
  - test_after_save_increments_file_version
  - test_after_save_marks_prefill_stale
  - test_after_save_publishes_workpaper_saved_event
  - test_after_save_writes_audit_log
  - test_optimistic_lock_mismatch_raises_409
  - test_concurrent_saves_one_succeeds_one_conflicts (PBT)
  - _Requirements: 1.2, 2.1, 2.2, 2.3_

- [ ] 3. Migrate snapshot_writer to use orchestrator (Phase 1 — 消除孤立总线)
  - [ ] 3.1 Import orchestrator in snapshot_writer.py
  - [ ] 3.2 After _write_workpaper_cell succeeds, call `orchestrator.after_save(...)` instead of manual `prefill_stale` + local `event_bus.emit`
  - [ ] 3.3 Delete `_EventBus` class and `event_bus` instance from `custom_query/metrics.py`
  - [ ] 3.4 Verify cross_ref/stale/SSE triggered after writeback (integration test)
  - _Requirements: 1.3, 3.1, 3.2_

- [ ] 4. Migrate wp_html_save to use orchestrator (Phase 2a)
  - Replace inline version increment + stale + audit + event_bus.publish with `orchestrator.after_save(...)`
  - Adapt `save_html_data` to pass `expected_version=body.data_version`
  - _Requirements: 1.1, 2.2_

- [ ] 5. Migrate wp_editor_router.save_univer_data to use orchestrator (Phase 2b)
  - Replace inline version increment + stale + audit + event_bus with `orchestrator.after_save(...)`
  - Adapt to pass `expected_version=body.get("expected_version")`
  - _Requirements: 1.1, 2.2_

- [ ] 6. Migrate onlyoffice_callback_service to use orchestrator (Phase 3)*
  - Adapt OnlyOffice callback's put_file to call `orchestrator.after_save(...)` after file download
  - OnlyOffice doc_key mechanism remains as upstream lock; orchestrator adds file_version consistency
  - _Requirements: 1.1_

- [ ] 7. Integration test: concurrent writes across different paths → one 409
  - Simulate html_save + univer_save on same wp concurrently → verify exactly one gets 409
  - _Requirements: 2.2, 2.3_

- [ ] 8. Checkpoint
  - All 4 paths use orchestrator
  - Local _EventBus deleted
  - Existing tests pass (no regression)
  - snapshot_writer writeback triggers SSE

## Task Dependency Graph

```json
{"waves":[["1"],["2"],["3"],["4","5"],["6"],["7"],["8"]]}
```
