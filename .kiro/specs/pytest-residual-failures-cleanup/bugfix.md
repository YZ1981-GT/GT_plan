# Bugfix Requirements Document

## Introduction

全套 pytest 运行（`python -m pytest backend/tests/ --tb=no -q`）显示 259 failed / 14 errors / 8436 passed（通过率 96.5%），远超目标阈值 ≤50 failed / ≥99% pass rate。

259 个失败分布在 50+ 测试文件中，根因分为 6 类：缺失 override_auth（~34 tests）、业务 schema 漂移（~36 tests）、陈旧断言（~32 tests）、深层 fixture/断言对齐（~50+ tests）、PBT 属性测试过时（~7 tests）、混合杂项（~100+ tests）。14 个 errors 来自 test_smoke_e2e.py 需要真实后端服务。

本 bugfix 仅修改测试基础设施（fixture / assertion / mock），不涉及任何业务逻辑变更。

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN running `python -m pytest backend/tests/ --tb=no -q` THEN the system reports 259 failed tests (target is ≤50)

1.2 WHEN running the full test suite THEN the system reports 14 errors from test_smoke_e2e.py due to backend service unavailability (target is 0 errors)

1.3 WHEN tests in test_wopi_working_paper_qc_review, test_signature_prerequisite, test_extension_services, test_sla_worker_q_ticket execute API calls THEN the system returns 401 Unauthorized because override_auth is not applied (~34 tests)

1.4 WHEN tests in test_workpaper_fill, test_contract_analysis, test_chain_orchestrator, test_phase10_step0_step1 call service methods THEN the system raises AttributeError/KeyError because test assertions reference outdated API signatures (~36 tests)

1.5 WHEN tests in test_report_engine, test_event_bus, test_prefill_provenance, test_prefill_snapshot_diff_endpoint, test_ai_content_confirm_flow, test_ai_content_structured assert on return values THEN the system fails because assertions reference outdated business logic outputs (~32 tests)

1.6 WHEN tests in test_audit_report, test_report_config, test_cfs_worksheet, test_custom_dsl_coding, test_custom_templates, test_consol_* execute THEN the system fails due to deeper fixture/assertion misalignment after initial auth fix (~50+ tests)

1.7 WHEN property-based tests in test_phase0_property, test_phase4_pbt, test_batch_review_pass, test_manager_dashboard_pbt, test_router_registry_split_pbt execute THEN the system fails because generators/oracles reference outdated schemas (~7 tests)

1.8 WHEN miscellaneous tests across 20+ files execute THEN the system fails due to mixed auth, schema, and assertion issues (~100+ tests)

### Expected Behavior (Correct)

2.1 WHEN running `python -m pytest backend/tests/ --tb=no -q` THEN the system SHALL report ≤50 failed tests (pass rate ≥99%)

2.2 WHEN running the full test suite THEN the system SHALL report 0 errors (test_smoke_e2e SHALL use module-level skipif when backend is unavailable)

2.3 WHEN tests requiring authenticated API access execute THEN the system SHALL use `override_auth(app, db_session)` pattern to inject FakeAuthUser and bypass 401 Unauthorized

2.4 WHEN tests call service methods THEN the system SHALL reference current API signatures matching the production service layer (updated method names, parameter lists, return types)

2.5 WHEN tests assert on return values THEN the system SHALL use assertions matching current business logic outputs (updated field names, value formats, enum values)

2.6 WHEN tests use fixtures for project/entity creation THEN the system SHALL provide all required fields (client_name NOT NULL, status as ProjectStatus enum, current schema-required columns)

2.7 WHEN property-based tests execute THEN the system SHALL use generators producing valid inputs per current schemas and oracles validating against current business rules

2.8 WHEN tests depend on external services (real backend, real PostgreSQL) THEN the system SHALL gracefully skip with appropriate pytest.mark.skipif or module-level skipif guards

### Unchanged Behavior (Regression Prevention)

3.1 WHEN tests that currently pass (8436 tests) execute after the fix THEN the system SHALL CONTINUE TO pass all of them without regression

3.2 WHEN production business logic code executes THEN the system SHALL CONTINUE TO behave identically (no changes to app/ source code, only test/ infrastructure changes)

3.3 WHEN the `_test_auth_helper.override_auth` context manager is used THEN the system SHALL CONTINUE TO inject get_db, get_redis, get_current_user overrides with FakeAuthUser(role=admin)

3.4 WHEN `conftest.py` shared fixtures (db_session, app, test_engine) are used THEN the system SHALL CONTINUE TO provide in-memory SQLite async sessions with all models registered

3.5 WHEN pytest markers (pg_only, skipif) are evaluated THEN the system SHALL CONTINUE TO skip tests appropriately based on environment (DATABASE_URL, backend availability)

3.6 WHEN CI pipeline runs the test suite THEN the system SHALL CONTINUE TO enforce existing quality gates (ruff, vue-tsc, vitest) without interference from pytest fixes

---

## Bug Condition (Formal)

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type PytestFullRunResult
  OUTPUT: boolean

  // Returns true when the test suite exceeds acceptable failure threshold
  RETURN X.failed_count > 50 OR X.error_count > 0
END FUNCTION
```

### Property: Fix Checking

```pascal
// Property: Fix Checking — Test Suite Health
FOR ALL X WHERE isBugCondition(X) DO
  result ← run_pytest_full_suite'(backend/tests/)
  ASSERT result.failed_count <= 50
  ASSERT result.error_count = 0
  ASSERT result.pass_rate >= 0.99
END FOR
```

### Property: Preservation Checking

```pascal
// Property: Preservation Checking — No Regression
FOR ALL X WHERE NOT isBugCondition(X) DO
  // All currently-passing tests remain passing
  ASSERT run_pytest_full_suite(X) = run_pytest_full_suite'(X)
  // No production code changes
  ASSERT hash(app_source_code) = hash(app_source_code')
END FOR
```

**Key Definitions:**
- **F**: The original test suite (259 failed / 14 errors / 96.5% pass rate)
- **F'**: The fixed test suite (≤50 failed / 0 errors / ≥99% pass rate)
- **C(X)**: `X.failed_count > 50 OR X.error_count > 0`
- **P(result)**: `result.failed <= 50 AND result.errors == 0 AND result.pass_rate >= 0.99`
