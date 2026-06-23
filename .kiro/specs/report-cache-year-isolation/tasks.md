# Implementation Plan

## Overview

修复 `ReportEngine._cache_key` 缺少 year 维度导致跨年度缓存串数据的 bug。变更范围：`report_engine.py` 内 `_cache_key`、`_get_cached_report`、`_set_cached_report`、`_invalidate_report_cache`、`get_report_cached`、`generate_all_reports` 约 20 行。

## Tasks

- [ ] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - 跨年度缓存串数据
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate cross-year cache pollution
  - **Scoped PBT Approach**: For any (project_id, year_A, year_B, report_type) where year_A ≠ year_B, set cache with year_A then get with year_B should return None
  - Test that `_set_cached_report(pid, rt, data)` followed by `_get_cached_report(pid, rt)` returns data regardless of year (bug: year is ignored in key)
  - The test assertions should match Expected Behavior: after fix, cross-year get must return None
  - Use mock Redis (fakeredis) to isolate cache key behavior
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (confirms bug exists - different years share same cache key)
  - Document counterexample: `_set_cached_report(pid, 'balance_sheet', data_2024)` then `_get_cached_report(pid, 'balance_sheet')` with year=2025 returns data_2024 instead of None
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2_

- [ ] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - 同年度缓存命中行为不变
  - **IMPORTANT**: Follow observation-first methodology
  - Observe: `_set_cached_report(pid, 'balance_sheet', data)` then `_get_cached_report(pid, 'balance_sheet')` with same year returns data on unfixed code
  - Observe: cache miss returns None on unfixed code
  - Observe: `_invalidate_report_cache(pid)` clears cache on unfixed code
  - Write property-based test: for all (project_id, year, report_type, data) where same year is used for set and get, result equals original data
  - Write test: event_handler wildcard `report:{pid}:*` matches keys with current format
  - Verify tests pass on UNFIXED code (same-year behavior is correct today)
  - _Requirements: 3.1, 3.2, 3.3_

- [ ] 3. Fix report cache year isolation

  - [ ] 3.1 Modify `_cache_key` to include year parameter
    - Change signature to `_cache_key(self, project_id: UUID, year: int, report_type: str) -> str`
    - Return `f"report:{project_id}:{year}:{report_type}"`
    - _Bug_Condition: isBugCondition(input) where cached_year ≠ year_requested due to key lacking year_
    - _Expected_Behavior: key includes year → different years produce different keys_
    - _Preservation: same-year requests still hit cache; wildcard `report:{pid}:*` still matches_
    - _Requirements: 2.1_

  - [ ] 3.2 Update `_get_cached_report` and `_set_cached_report` signatures to accept year
    - Add `year: int` parameter to both methods
    - Pass year through to `self._cache_key(project_id, year, report_type)`
    - _Requirements: 2.2_

  - [ ] 3.3 Update `_invalidate_report_cache` to use wildcard pattern
    - Replace per-type key deletion with SCAN + DELETE using pattern `report:{project_id}:*`
    - This aligns with event_handler's existing `_invalidate_report_redis` pattern
    - Covers all years and all report types in one pass
    - _Requirements: 2.3, 2.4, 2.5_

  - [ ] 3.4 Update callers: `get_report_cached` and `generate_all_reports` cache write
    - `get_report_cached`: pass existing `year` param to `_get_cached_report` / `_set_cached_report`
    - `generate_all_reports`: pass `year` to `_set_cached_report` at cache write site
    - _Requirements: 2.1, 2.2_

  - [ ] 3.5 Verify event_handler `report:{pid}:*` still works with new key format
    - Confirm `_invalidate_report_redis` pattern `report:{pid}:*` matches `report:{pid}:{year}:{rt}`
    - No code change needed in event_handlers.py - just verify wildcard coverage
    - _Requirements: 2.5, 3.3_

  - [ ] 3.6 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - 跨年度缓存隔离
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (cross-year get returns None)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2_

  - [ ] 3.7 Verify preservation tests still pass
    - **Property 2: Preservation** - 同年度缓存命中
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm same-year cache hit, invalidation, and event_handler wildcard all still work
    - _Requirements: 3.1, 3.2, 3.3_

- [ ] 4. Checkpoint - Ensure all tests pass
  - Run full test suite for report_engine tests
  - Ensure cross-year isolation test passes (Property 1)
  - Ensure same-year hit + invalidation tests pass (Property 2)
  - Ensure event_handler wildcard coverage confirmed
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

## Notes

- 变更仅涉及 `backend/app/services/report_engine.py`（~20 行），`event_handlers.py` 无需改动
- `_invalidate_report_redis` 已使用 `report:{pid}:*` 通配符，新 key 格式 `report:{pid}:{year}:{rt}` 天然被覆盖
- Redis 不可用时（`self.redis = None`）整条缓存路径被跳过，无需额外处理
- 测试使用 fakeredis mock，不依赖外部 Redis 实例
