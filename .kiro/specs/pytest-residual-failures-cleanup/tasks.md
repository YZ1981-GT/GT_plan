# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Test Suite Health Below Threshold
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists (failed > 50 OR errors > 0)
  - **Scoped PBT Approach**: Run `python -m pytest backend/tests/ --tb=no -q` and parse output
  - Confirm current state: expected ~200-259 failed / 0-14 errors (depending on earlier partial fixes)
  - Write a test script that asserts: `failed_count <= 50 AND error_count == 0 AND pass_rate >= 0.99`
  - Run on UNFIXED code - expect FAILURE (this confirms the bug exists)
  - Document actual counterexample: "full suite reports X failed / Y errors / Z% pass rate"
  - _Requirements: 1.1, 1.2, 2.1, 2.2_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - No Regression on Currently-Passing Tests
  - **IMPORTANT**: Follow observation-first methodology
  - Observe: run `python -m pytest backend/tests/ --tb=no -q` on unfixed code, record passed count (expected ~8436)
  - Observe: verify `git diff --stat backend/app/` shows 0 changes (production code untouched)
  - Write preservation test: assert passed_count >= 8436 after each batch (no regression)
  - Write preservation test: assert no files in `backend/app/` are modified (hash check)
  - Verify tests pass on UNFIXED code (baseline passes are already passing)
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [ ] 3. Batch 1: override_auth 接入 (~34 tests, 4 files)

  - [x] 3.1 Run pytest on Batch 1 files to confirm current failure state
    - `python -m pytest backend/tests/test_wopi_working_paper_qc_review.py backend/tests/test_signature_prerequisite.py backend/tests/test_extension_services.py backend/tests/test_sla_worker_q_ticket.py --tb=short -q`
    - Document actual failed count (some may already be partially fixed from earlier commits)
    - _Requirements: 1.3_

  - [x] 3.2 Fix test_wopi_working_paper_qc_review.py
    - Add `from tests._test_auth_helper import override_auth`
    - Replace `client` fixture with `async with override_auth(app, db_session=db_session) as c: yield c`
    - Ensure seeded_db fixture dependency chain is correct
    - _Bug_Condition: isBugCondition(input) where tests return 401 Unauthorized_
    - _Requirements: 2.3_

  - [x] 3.3 Fix test_signature_prerequisite.py
    - Add override_auth import and apply to client fixture
    - Note: uses local FastAPI app + include_router pattern, override_auth(local_app, ...) works
    - _Requirements: 2.3_

  - [x] 3.4 Fix test_extension_services.py
    - Add override_auth import and apply to client fixture
    - _Requirements: 2.3_

  - [x] 3.5 Fix test_sla_worker_q_ticket.py
    - Add override_auth import and apply to client fixture
    - _Requirements: 2.3_

  - [x] 3.6 Verify Batch 1 - run pytest on affected files
    - `python -m pytest backend/tests/test_wopi_working_paper_qc_review.py backend/tests/test_signature_prerequisite.py backend/tests/test_extension_services.py backend/tests/test_sla_worker_q_ticket.py --tb=short -q`
    - Target: 0 failures from auth issues (may still have deeper schema failures)
    - _Requirements: 2.3_

- [ ] 4. Batch 2: Schema drift 修复 (~36 tests, 4 files)

  - [x] 4.1 Run pytest on Batch 2 files to confirm current failure state
    - `python -m pytest backend/tests/test_workpaper_fill.py backend/tests/test_contract_analysis.py backend/tests/test_chain_orchestrator.py backend/tests/test_phase10_step0_step1.py --tb=short -q`
    - Document AttributeError / TypeError patterns
    - _Requirements: 1.4_

  - [x] 4.2 Fix test_workpaper_fill.py
    - Read current WorkpaperFillService signature (check for `year` param, return type changes)
    - Update service calls with new required parameters
    - Update mock return values to match current return structure
    - _Bug_Condition: AttributeError/TypeError from outdated API signatures_
    - _Expected_Behavior: service calls succeed with current signatures_
    - _Requirements: 2.4_

  - [x] 4.3 Fix test_contract_analysis.py
    - Read current ContractAnalysisService signature
    - Update method names, parameter lists, return type assertions
    - _Requirements: 2.4_

  - [x] 4.4 Fix test_chain_orchestrator.py
    - Read current chain_orchestrator service signature
    - Update test calls and assertions to match current API
    - _Requirements: 2.4_

  - [x] 4.5 Fix test_phase10_step0_step1.py
    - Read current phase10 service signatures
    - Update test calls and mock configurations
    - _Requirements: 2.4_

  - [x] 4.6 Verify Batch 2 - run pytest on affected files
    - `python -m pytest backend/tests/test_workpaper_fill.py backend/tests/test_contract_analysis.py backend/tests/test_chain_orchestrator.py backend/tests/test_phase10_step0_step1.py --tb=short -q`
    - Target: 0 TypeError/AttributeError failures
    - _Requirements: 2.4_

- [ ] 5. Batch 3: Stale assertion 更新 (~32 tests, 6 files)

  - [x] 5.1 Run pytest on Batch 3 files to confirm current failure state
    - `python -m pytest backend/tests/test_report_engine.py backend/tests/test_event_bus.py backend/tests/test_prefill_provenance.py backend/tests/test_prefill_snapshot_diff_endpoint.py backend/tests/test_ai_content_confirm_flow.py backend/tests/test_ai_content_structured.py --tb=short -q`
    - Document AssertionError patterns (outdated field names, values)
    - _Requirements: 1.5_

  - [x] 5.2 Fix test_report_engine.py
    - Read current report engine return value structure
    - Update field name assertions and expected values
    - _Bug_Condition: AssertionError from outdated field references_
    - _Expected_Behavior: assertions match current business logic outputs_
    - _Requirements: 2.5_

  - [x] 5.3 Fix test_event_bus.py
    - Update assertions to match current event payload structure
    - _Requirements: 2.5_

  - [x] 5.4 Fix test_prefill_provenance.py
    - Update expected provenance data structure assertions
    - _Requirements: 2.5_

  - [x] 5.5 Fix test_prefill_snapshot_diff_endpoint.py
    - Update snapshot diff response assertions
    - _Requirements: 2.5_

  - [x] 5.6 Fix test_ai_content_confirm_flow.py
    - Update AI content confirmation flow assertions
    - _Requirements: 2.5_

  - [x] 5.7 Fix test_ai_content_structured.py
    - Update structured AI content assertions
    - _Requirements: 2.5_

  - [x] 5.8 Verify Batch 3 - run pytest on affected files
    - `python -m pytest backend/tests/test_report_engine.py backend/tests/test_event_bus.py backend/tests/test_prefill_provenance.py backend/tests/test_prefill_snapshot_diff_endpoint.py backend/tests/test_ai_content_confirm_flow.py backend/tests/test_ai_content_structured.py --tb=short -q`
    - Target: 0 AssertionError failures from stale assertions
    - _Requirements: 2.5_

- [ ] 6. Batch 4: Deeper fixture alignment (~50+ tests, 10+ files)

  - [x] 6.1 Run pytest on Batch 4 files to confirm current failure state
    - `python -m pytest backend/tests/test_audit_report.py backend/tests/test_report_config.py backend/tests/test_cfs_worksheet.py backend/tests/test_custom_dsl_coding.py backend/tests/test_custom_templates.py backend/tests/test_consol_scope.py backend/tests/test_minority_interest.py backend/tests/test_elimination.py backend/tests/test_goodwill.py backend/tests/test_forex.py backend/tests/test_component_auditor.py --tb=short -q`
    - Document IntegrityError / LookupError patterns
    - Note: some files may already have override_auth from earlier commits
    - _Requirements: 1.6_

  - [x] 6.2 Fix test_audit_report.py
    - Add `client_name="Test Client"` to Project fixtures
    - Fix `status` to use `ProjectStatus.execution` enum (not string "active")
    - Fix any deleted enum value references
    - _Bug_Condition: IntegrityError NOT NULL / LookupError enum_
    - _Expected_Behavior: ORM objects flush successfully to SQLite_
    - _Preservation: existing passing assertions unchanged_
    - _Requirements: 2.6_

  - [x] 6.3 Fix test_report_config.py
    - Align fixtures with current ORM model (required fields, enum values)
    - _Requirements: 2.6_

  - [x] 6.4 Fix test_cfs_worksheet.py
    - Align fixtures with current ORM model
    - _Requirements: 2.6_

  - [x] 6.5 Fix test_custom_dsl_coding.py
    - Align fixtures with current ORM model
    - _Requirements: 2.6_

  - [x] 6.6 Fix test_custom_templates.py
    - Align fixtures with current ORM model
    - _Requirements: 2.6_

  - [x] 6.7 Fix test_consol_scope.py
    - Fix `ScopeCompanyType.PARENT` → current valid enum value
    - Add all required fields for consolidation scope entities
    - _Requirements: 2.6_

  - [x] 6.8 Fix test_minority_interest.py
    - Align fixtures with current consolidation model requirements
    - _Requirements: 2.6_

  - [x] 6.9 Fix test_elimination.py
    - Align fixtures with current elimination model requirements
    - _Requirements: 2.6_

  - [x] 6.10 Fix test_goodwill.py
    - Align fixtures with current goodwill model requirements
    - _Requirements: 2.6_

  - [x] 6.11 Fix test_forex.py
    - Add `ForexRates.functional_currency` and other new required fields
    - _Requirements: 2.6_

  - [x] 6.12 Fix test_component_auditor.py
    - Align fixtures with current component auditor model requirements
    - _Requirements: 2.6_

  - [x] 6.13 Verify Batch 4 - run pytest on affected files
    - `python -m pytest backend/tests/test_audit_report.py backend/tests/test_report_config.py backend/tests/test_cfs_worksheet.py backend/tests/test_custom_dsl_coding.py backend/tests/test_custom_templates.py backend/tests/test_consol_scope.py backend/tests/test_minority_interest.py backend/tests/test_elimination.py backend/tests/test_goodwill.py backend/tests/test_forex.py backend/tests/test_component_auditor.py --tb=short -q`
    - Target: ≤5 remaining failures (deep business schema issues may remain)
    - _Requirements: 2.6_


- [ ] 7. (*) Batch 5: PBT/Property test 更新 (~7 tests, 5 files)

  - [x] 7.1 Run pytest on Batch 5 files to confirm current failure state
    - `python -m pytest backend/tests/test_phase0_property.py backend/tests/test_phase4_pbt.py backend/tests/test_batch_review_pass.py backend/tests/test_manager_dashboard_pbt.py backend/tests/test_router_registry_split_pbt.py --tb=short -q`
    - Document ImportError / InvalidArgument patterns
    - _Requirements: 1.7_

  - [x] 7.2 (*) Fix test_phase0_property.py
    - Fix import paths for renamed functions/classes
    - Update hypothesis strategies to generate valid inputs per current schemas
    - Update oracle functions to match current business rules
    - _Requirements: 2.7_

  - [x] 7.3 (*) Fix test_phase4_pbt.py
    - Update strategies and oracles for phase4 schema changes
    - _Requirements: 2.7_

  - [x] 7.4 (*) Fix test_batch_review_pass.py
    - Update PBT generators for current review pass schema
    - _Requirements: 2.7_

  - [x] 7.5 (*) Fix test_manager_dashboard_pbt.py
    - Update PBT generators for current dashboard schema
    - _Requirements: 2.7_

  - [x] 7.6 (*) Fix test_router_registry_split_pbt.py
    - Update PBT generators for current router registry structure
    - _Requirements: 2.7_

  - [x] 7.7 Verify Batch 5 - run pytest on affected files
    - `python -m pytest backend/tests/test_phase0_property.py backend/tests/test_phase4_pbt.py backend/tests/test_batch_review_pass.py backend/tests/test_manager_dashboard_pbt.py backend/tests/test_router_registry_split_pbt.py --tb=short -q`
    - Target: 0 ImportError / InvalidArgument failures
    - _Requirements: 2.7_

- [ ] 8. (*) Batch 6: Miscellaneous remaining (~100+ tests, 20+ files)

  - [x] 8.1 Confirm test_smoke_e2e.py module-level skipif is effective
    - Verify `pytestmark = pytest.mark.skipif(not _backend_alive(), ...)` is in place
    - Run: `python -m pytest backend/tests/test_smoke_e2e.py --tb=short -q`
    - Target: 14 errors → 0 errors (all skipped when backend unavailable)
    - _Requirements: 2.8_

  - [x] 8.2 Confirm test_formula_parser.py event loop fix is effective
    - Verify `asyncio.new_event_loop()` pattern is in place
    - Run: `python -m pytest backend/tests/test_formula_parser.py --tb=short -q`
    - Target: 0 failures from event loop pollution
    - _Requirements: 2.5_

  - [x] 8.3 (*) Diagnose and fix remaining high-impact files
    - Run full suite: `python -m pytest backend/tests/ --tb=no -q`
    - Identify top failing files by count
    - For each file: classify root cause (auth / schema / assertion / fixture)
    - Apply appropriate fix pattern from Batches 1-4
    - Priority files (from memory): test_audit_log_enhanced (~7, chain verify signature), test_workpaper_fill (~11 remaining), test_contract_analysis (~13), test_signature_prerequisite (~10 PasswordConfirm 403)
    - _Requirements: 2.3, 2.4, 2.5, 2.6_

  - [x] 8.4 (*) Add skipif guards for tests requiring external services
    - Tests needing real PostgreSQL: add `@pytest.mark.skipif(not PG_AVAILABLE, ...)`
    - Tests needing real backend: add module-level skipif with health check
    - Tests needing real Redis: add appropriate skipif guard
    - _Requirements: 2.8_

  - [x] 8.5 Verify Batch 6 - run pytest on full suite
    - `python -m pytest backend/tests/ --tb=no -q`
    - Document: passed / failed / errors / skipped / pass rate
    - _Requirements: 2.1, 2.2_

- [ ] 9. Fix implementation validation

  - [x] 9.1 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Test Suite Health Recovered
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (≤50 failed / 0 errors / ≥99%)
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2_

  - [x] 9.2 Verify preservation tests still pass
    - **Property 2: Preservation** - No Regression Confirmed
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm passed_count >= 8436 (no regression from baseline)
    - Confirm 0 files changed in backend/app/
    - _Requirements: 3.1, 3.2_

- [x] 10. Checkpoint - Final validation
  - Run full suite: `python -m pytest backend/tests/ --tb=no -q`
  - **ACCEPTANCE CRITERIA**:
    - failed_count ≤ 50
    - error_count == 0
    - pass_rate ≥ 99% (≥8600 passed out of ~8700 total)
    - passed_count >= 8436 (no regression)
    - 0 files modified in backend/app/ (production code untouched)
  - If criteria not met: identify remaining failures, assess if achievable without production code changes
  - Ask user if questions arise about borderline cases
  - _Requirements: 2.1, 2.2, 3.1, 3.2_
