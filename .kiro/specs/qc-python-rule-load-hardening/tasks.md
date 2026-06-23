# Implementation Plan

## Overview

Bugfix for QC Python Rule Load Hardening: `_load_class_from_dotted_path` 无前缀限制 + 非 admin 可创建 python 类型规则 → 受限 RCE 面。修复策略：前缀白名单 + admin-only 限制 + 去"沙箱"误导注释。

## Tasks

- [ ] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Disallowed Path Loads Successfully / Non-Admin Creates Python Rule
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope to concrete failing cases:
    - `_load_class_from_dotted_path('app.services.data_lifecycle_service.DataLifecycleService')` currently succeeds (should raise ImportError after fix)
    - `_load_class_from_dotted_path('app.services.import_job_runner.ImportJobRunner')` currently succeeds (should raise ImportError after fix)
    - Non-admin (role='qc') POST `expression_type='python'` currently returns 201 (should return 403 after fix)
    - Non-admin (role='qc') PATCH `expression_type='python'` currently returns 200 (should return 403 after fix)
  - Bug Condition from design: `isBugCondition(input) = (expression_type='python' AND user_role!='admin') OR (expression_type='python' AND NOT starts_with_any(dotted_path, _ALLOWED_RULE_PREFIXES))`
  - Property-based: generate random dotted paths NOT starting with `app.services.qc_engine.` or `app.services.qc_rules.`, assert `_load_class_from_dotted_path` raises ImportError (will FAIL on unfixed code)
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples: non-whitelisted paths load successfully; non-admin users create python rules without 403
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 2.1, 2.2_

- [ ] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Allowed QC Rules Load & JsonPath Unaffected
  - **IMPORTANT**: Follow observation-first methodology
  - Observe on UNFIXED code:
    - `_load_class_from_dotted_path('app.services.qc_engine.ConclusionNotEmptyRule')` returns class successfully
    - `_load_class_from_dotted_path('app.services.qc_rules.CustomRule')` returns class successfully (if exists)
    - All existing QC-01~QC-28 rules (paths `app.services.qc_engine.*`) load and execute normally
    - `expression_type='jsonpath'` rule creation by any role (qc/admin) returns 201
    - `expression_type='sql'`/`'regex'` execution raises NotImplementedError
    - `execute_python_rule` timeout behavior returns `RuleExecutionResult(passed=False, error="timed out")`
  - Write property-based tests:
    - For all dotted paths starting with `app.services.qc_engine.` or `app.services.qc_rules.` where module/class exists, function returns class (same as original)
    - For all (role, expression_type='jsonpath') combinations, create_rule succeeds regardless of role
    - Admin + python type + whitelisted path → continues to succeed
  - Verify tests pass on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 3. Fix for QC Python Rule Load Hardening

  - [ ] 3.1 Add `_ALLOWED_RULE_PREFIXES` constant
    - Add module-level constant in `backend/app/services/qc_rule_executor.py`
    - Value: `("app.services.qc_engine.", "app.services.qc_rules.")`
    - Place near top of file after imports
    - _Bug_Condition: isBugCondition(input) where dotted_path NOT starts_with_any(_ALLOWED_RULE_PREFIXES)_
    - _Expected_Behavior: non-whitelisted path → ImportError("Disallowed rule class path: ...")_
    - _Preservation: whitelisted paths continue to load normally_
    - _Requirements: 2.1_

  - [ ] 3.2 Add prefix whitelist check in `_load_class_from_dotted_path`
    - Before `importlib.import_module` call (~L71), add guard: `if not any(dotted_path.startswith(p) for p in _ALLOWED_RULE_PREFIXES): raise ImportError(f"Disallowed rule class path: {dotted_path}")`
    - Do NOT invoke `importlib.import_module` for disallowed paths
    - Existing format validation (rsplit check) remains unchanged
    - _Bug_Condition: isBugCondition(input) where dotted_path not in allowed prefixes_
    - _Expected_Behavior: ImportError raised without importlib call_
    - _Preservation: existing QC-01~QC-28 rules (app.services.qc_engine.*) unaffected_
    - _Requirements: 2.1, 3.1_

  - [ ] 3.3 Add admin-only check in `create_rule` endpoint for python type
    - In `backend/app/routers/qc_rules.py`, `create_rule` function
    - Before service call: `if body.expression_type == 'python' and current_user.role != 'admin': raise HTTPException(403, "Only admin can create python-type rules")`
    - jsonpath/other types remain unrestricted for qc role
    - _Bug_Condition: isBugCondition(input) where user_role != 'admin' AND expression_type = 'python' AND action = 'create'_
    - _Expected_Behavior: HTTP 403 returned, rule NOT created_
    - _Preservation: jsonpath rules creation unaffected for all roles_
    - _Requirements: 2.2, 2.3, 3.2_

  - [ ] 3.4 Add admin-only check in `update_rule` endpoint for python type
    - In `backend/app/routers/qc_rules.py`, `update_rule` function
    - Check both cases: (a) updating expression_type TO python, (b) editing rule that IS already python type
    - Guard: `if (expression_type_is_python) and current_user.role != 'admin': raise HTTPException(403, "Only admin can modify python-type rules")`
    - _Bug_Condition: isBugCondition(input) where user_role != 'admin' AND expression_type = 'python' AND action = 'update'_
    - _Expected_Behavior: HTTP 403 returned, rule NOT modified_
    - _Preservation: non-python rule updates unaffected_
    - _Requirements: 2.2, 3.2_

  - [ ] 3.5 Replace "沙箱" misleading comments
    - In `backend/app/services/qc_rule_executor.py`, replace `# 沙箱 timeout=10s` and similar with `# timeout-only execution (NOT a security sandbox)`
    - Update module docstring to clarify no process isolation/privilege reduction exists
    - Remove any variable naming that implies sandbox capability
    - _Requirements: 2.5_

  - [ ] 3.6 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Disallowed Path Rejected & Non-Admin Blocked
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (ImportError for disallowed paths, 403 for non-admin python rules)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2_

  - [ ] 3.7 Verify preservation tests still pass
    - **Property 2: Preservation** - Allowed QC Rules Load & JsonPath Unaffected
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 4. Checkpoint - Ensure all tests pass
  - Run full test suite: `python -m pytest backend/tests/ -v --tb=short`
  - Ensure all existing tests pass (no regressions beyond this fix)
  - Verify QC-01~QC-28 rules still execute correctly
  - Ask the user if questions arise


## Task Dependency Graph

```json
{
  "waves": [
    ["1", "2"],
    ["3.1", "3.2", "3.3", "3.4", "3.5"],
    ["3.6", "3.7"],
    ["4"]
  ]
}
```

- Wave 1: Task 1 and 2 are independent (bug condition + preservation tests, before fix)
- Wave 2: Task 3.1~3.5 implement the fix (depends on understanding from wave 1)
- Wave 3: Task 3.6 and 3.7 verify tests from tasks 1 and 2 pass after fix
- Wave 4: Task 4 final checkpoint (all tests green)

## Notes

- Tests use Hypothesis (PBT) with `max_examples=5` per project convention
- Bug condition test EXPECTED to FAIL on unfixed code (confirms bug exists)
- Preservation test EXPECTED to PASS on unfixed code (captures baseline)
- After fix: both test types should PASS
- `_ALLOWED_RULE_PREFIXES` 初始值可后续扩展（tuple 便于追加）
