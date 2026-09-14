# Implementation Plan

## Overview

Bugfix for custom-query authorization hardening (Â§5.12 + Â§5.13). Closes IDOR read on execute/batch-execute and cross-project write on cell-writeback by adding project-level visibility/edit permission checks using existing auth infrastructure (`get_visible_project_ids` + `require_project_access`).

## Tasks

- [x] 1. Write bug condition exploration test (IDOR read + cross-project write)
  - **Property 1: Bug Condition** â€?Custom Query Authorization IDOR & Cross-Project Write
  - **CRITICAL**: This test MUST FAIL on unfixed code â€?failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior â€?it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate IDOR read on execute/batch-execute and cross-project write on cell-writeback
  - **Scoped PBT Approach**: Scope the property to concrete failing cases:
    - (a) User with visible_projects={P1} calls execute with project_id=P2 â†?currently returns 200+data (should 403)
    - (b) User with visible_projects={P1} calls batch-execute with project_id=P2 â†?currently returns 200 (should 403)
    - (c) User without edit permission on project_id calls cell-writeback (module=workpaper) â†?currently no auth check (should 403)
    - (d) Projects P1,P2 both have wp_code="D2-1", user in P1 submits writeback without project_id filter â†?LIMIT 1 may hit P2's workpaper (should only hit P1 or 404)
  - Bug Condition (from design): `isBugCondition(input) = project_id NOT IN get_visible_project_ids(current_user)` (for execute/batch-execute) OR `NOT has_edit_permission(current_user, project_id) OR (module=="workpaper" AND wp_lookup_ignores_project_id)` (for cell-writeback)
  - Expected Behavior assertions: result.status == 403 AND no_data_returned AND no_cache_read AND no_query_dispatch (for reads); result.status IN [403, 404] AND no_write_occurred (for writes)
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct â€?it proves the bug exists: endpoints return 200 instead of 403, writes succeed cross-project)
  - Document counterexamples found (e.g., "execute(user_A, project_B) returns 200 with trial balance data instead of 403")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** â€?Legitimate Same-Project Access Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - **Observe on UNFIXED code** (cases where isBugCondition returns false):
    - (a) Admin user calls execute with any project_id â†?returns 200 + query results (admin sees all projects via get_visible_project_ids)
    - (b) User with project membership calls execute on their visible project â†?returns normal query results
    - (c) Same user, same visible project, repeated query â†?returns X-Cache: HIT header (Redis short TTL cache behavior)
    - (d) User with edit permission calls cell-writeback on workpaper with stale X-File-Opened-At â†?returns 409 {conflict: true} (optimistic lock)
    - (e) User with edit permission calls cell-writeback successfully â†?returns {success: true, updated_at: ...}, writes parsed_data JSONB, marks prefill_stale, syncs xlsx cache
    - (f) Partner role accesses any project â†?visible all (get_visible_project_ids returns all for partner)
  - Write property-based tests (Hypothesis) capturing observed behavior:
    - PBT: for all (user, project) where project âˆ?get_visible_project_ids(user), execute returns same result structure as before fix
    - PBT: for all (user, project) where has_edit_permission(user, project) AND workpaper belongs to project, cell-writeback preserves optimistic lock 409 / success 200 / JSONB write / prefill_stale / xlsx sync / audit log
    - PBT: admin/partner for random project_id â†?always passes visibility check
  - Verify tests PASS on UNFIXED code (confirms baseline behavior to preserve)
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 3. Fix for custom-query authorization hardening (Â§5.12 + Â§5.13)

  - [x] 3.1 Add project visibility check to execute_query (BEFORE cache read)
    - In `backend/app/routers/custom_query.py` ~L972, insert visibility check before `source = body.source` assignment
    - Call `get_visible_project_ids(current_user, db)` and verify `UUID(body.project_id) in visible_ids`
    - If not visible: raise HTTPException(403, detail={"error_code": "PROJECT_NOT_VISIBLE"})
    - This MUST execute before any Redis cache read or `_query_*` dispatch
    - _Bug_Condition: isBugCondition_5_12(X) where project_id NOT IN get_visible_project_ids(current_user)_
    - _Expected_Behavior: result.status = 403 AND no_data_returned AND no_cache_read AND no_query_dispatch_
    - _Preservation: Authorized users on visible projects get identical query results (3.1, 3.2, 3.3)_
    - _Requirements: 2.1, 2.3_

  - [x] 3.2 Add project visibility check to batch_execute
    - In `backend/app/routers/custom_query.py` ~L2020, insert same visibility check before the for-loop over wp_codes
    - Call `get_visible_project_ids(current_user, db)` and verify `UUID(body.project_id) in visible_ids`
    - If not visible: raise HTTPException(403, detail={"error_code": "PROJECT_NOT_VISIBLE"})
    - _Bug_Condition: isBugCondition_5_12(X) where project_id NOT IN get_visible_project_ids(current_user)_
    - _Expected_Behavior: result.status = 403 before any wp_code sub-query executes_
    - _Preservation: Authorized batch queries return identical results (3.1)_
    - _Requirements: 2.2_

  - [x] 3.3 Add project_id field to CellWritebackRequest schema
    - In `backend/app/routers/custom_query.py`, locate `CellWritebackRequest` Pydantic model
    - Add `project_id: str` as required field (breaking change â€?frontend must send it)
    - Missing project_id â†?automatic 422 validation error from Pydantic
    - _Bug_Condition: isBugCondition_5_13 â€?workpaper lookup previously ignored project_id_
    - _Expected_Behavior: Schema enforces project_id presence; without it, 422_
    - _Requirements: 2.5_

  - [x] 3.4 Replace role whitelist with unified project edit permission check in cell_writeback
    - In `backend/app/routers/custom_query.py` ~L2121, delete the `if body.module != "workpaper"` role whitelist branch
    - Replace with unified check for ALL modules (including workpaper):
      - Verify `UUID(body.project_id) in get_visible_project_ids(current_user, db)`
      - For non-admin/partner: query ProjectUser to confirm membership + permission_level in ("edit", "admin", "owner")
      - If no visibility or no edit permission: raise HTTPException(403, detail={"error_code": "NO_EDIT_PERMISSION"})
    - This closes the workpaper zero-auth gap AND replaces the overly-permissive role whitelist
    - _Bug_Condition: isBugCondition_5_13(X) where NOT has_edit_permission(current_user, project_id)_
    - _Expected_Behavior: 403 for all unauthorized write attempts, regardless of module_
    - _Preservation: Admin/partner bypass (3.6); users with edit permission still write normally (3.4, 3.5); tb non-audited_amount WritebackPermissionDenied unchanged (3.7)_
    - _Requirements: 2.4, 2.7, 2.8_

  - [x] 3.5 Add project_id filter to workpaper lookup query in cell_writeback
    - Locate the workpaper lookup query: `SELECT id FROM working_paper WHERE wp_code = :code LIMIT 1`
    - Change to: `SELECT id FROM working_paper WHERE wp_code = :code AND project_id = :pid LIMIT 1`
    - Bind `:pid` from `body.project_id`
    - If no row returned â†?raise HTTPException(404, detail="Working paper not found in this project")
    - This eliminates cross-project wp_code collision (multiple projects with same D2-1)
    - _Bug_Condition: isBugCondition_5_13 â€?lookup_ignores_project_id previously true_
    - _Expected_Behavior: Only the target project's workpaper is matched; 404 if not found in project_
    - _Preservation: Users writing to workpapers that exist in their project get same behavior (3.4, 3.5)_
    - _Requirements: 2.5, 2.6_

  - [x] 3.6 Add belt+suspenders project_id validation in snapshot_writer._write_workpaper_cell
    - In `backend/app/services/custom_query/snapshot_writer.py`, modify `_write_workpaper_cell`
    - Extend the `SELECT FOR UPDATE` to also fetch `project_id`: `SELECT updated_at, parsed_data, wp_code, file_path, project_id FROM working_paper WHERE id = :wp_id FOR UPDATE`
    - Add `write_cell` signature: new optional param `project_id: str | None = None`
    - After SELECT: if `project_id` param provided and fetched row's `project_id != expected_project_id`, raise `WritebackPermissionDenied("Project mismatch")`
    - This is defense-in-depth â€?even if router check is bypassed, writer rejects cross-project writes
    - _Bug_Condition: Cross-project write attempt reaching snapshot_writer directly_
    - _Expected_Behavior: WritebackPermissionDenied raised on project mismatch_
    - _Preservation: Normal writes where project matches continue unchanged (3.4, 3.5)_
    - _Requirements: 2.7_

  - [x] 3.7 Update frontend to pass project_id in cell-writeback requests
    - Locate the frontend API call for cell-writeback (likely in `frontend/src/` â€?search for `cell-writeback` or `cellWriteback`)
    - Add `project_id` field to the request payload (read from current project context / route params / store)
    - Verify the field is always present when cell-writeback is invoked
    - If frontend already has project context available (likely via route or store), this is a minimal change
    - _Requirements: 2.5_

  - [x] 3.8 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** â€?IDOR & Cross-Project Write Blocked
    - **IMPORTANT**: Re-run the SAME test from task 1 â€?do NOT write a new test
    - The test from task 1 encodes the expected behavior (403 for unauthorized reads, 403/404 for unauthorized writes)
    - When this test passes, it confirms: execute returns 403 for invisible projects, batch-execute returns 403, cell-writeback returns 403 without edit permission, workpaper lookup returns 404 for wrong-project wp_code
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [x] 3.9 Verify preservation tests still pass
    - **Property 2: Preservation** â€?Legitimate Same-Project Access Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 â€?do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm: admin/partner still access all projects; authorized execute/batch-execute returns same results; cache HIT behavior unchanged; optimistic lock 409 still works; successful writeback still writes JSONB + prefill_stale + xlsx sync + audit log
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 4. Checkpoint â€?Ensure all tests pass
  - Run full test suite: `python -m pytest backend/tests/ -v --tb=short`
  - Ensure bug condition exploration test (Property 1) PASSES
  - Ensure preservation property tests (Property 2) PASS
  - Ensure no other tests regressed
  - Verify 422 for missing project_id in cell-writeback schema
  - Ask the user if questions arise


## Task Dependency Graph

```json
{
  "waves": [
    {"tasks": ["1", "2"]},
    {"tasks": ["3.1", "3.2", "3.3"]},
    {"tasks": ["3.4", "3.5", "3.6", "3.7"]},
    {"tasks": ["3.8", "3.9"]},
    {"tasks": ["4"]}
  ]
}
```

## Notes

- Property 1 (Bug Condition) and Property 2 (Preservation) tests are written and run BEFORE any code fix.
- Property 1 is EXPECTED TO FAIL on unfixed code (confirms bug exists). Property 2 is EXPECTED TO PASS on unfixed code (captures baseline).
- Implementation tasks 3.1â€?.7 are ordered by dependency: schema change (3.3) before router changes (3.4, 3.5) that use `body.project_id`; frontend update (3.7) after schema change.
- Task 3.6 (snapshot_writer belt+suspenders) is defense-in-depth and can be done in parallel with 3.4/3.5.
- All auth checks reuse existing `deps.py` infrastructure â€?no new custom auth logic introduced.
- Frontend change (3.7) is a breaking contract change; coordinate with frontend if deployed separately.
