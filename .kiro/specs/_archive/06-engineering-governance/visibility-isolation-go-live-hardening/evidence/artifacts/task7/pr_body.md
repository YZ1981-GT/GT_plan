# Workpaper visibility isolation + go-live hardening

Delivers two specs on one branch (PR flow; not pushed to main/master).

## Summary of changes
**procedure-delegation-visibility-isolation (migration V113)**
- Server-side fail-closed `Wp_Bound_Gate` / `resolve_wp_binding_and_access()` returning `External_Not_Found` (404) on denial.
- Two-layer delegation (workpaper lead + row assignee/reviewer), `scope_cycles` upper bound, `Sheet_Key` page isolation.
- OnlyOffice/WOPI token binding + callback re-validation; policy epoch + invalidation outbox.
- `Route_Coverage_Ledger` + `coverage_guard` + `Evidence_Manifest` / `Completion_Guard`.

**visibility-isolation-go-live-hardening (no new migration; head stays V113)**
- R1 editor token enforcement made env-gated (`ONLYOFFICE_JWT_ENFORCE`) with pure-config rollback.
- R2 `InvalidationDispatcher` mounted in `app.main` lifespan with graceful degradation to the DB epoch safety net.
- R3 audit of 72 `native_authz` entries → 19 gated + 52 justified allowlist + 1 worker.
- R4 capacity acceptance + frozen production `Rate_Limit_Profile` bound to `Capacity_Report_Hash`.
- R5 Playwright 8-role fresh-context acceptance; R7 `Go_Live_Gate` closeout evidence.

## What was tested
- Real FastAPI app + PostgreSQL `audit_platform` integration tests + property-based tests for the visibility gate, resolver, delegation transactions, editor security, coverage guard, capacity/rate-limit.
- Frontend vitest (visibility list/util/views) + Playwright e2e 8-role acceptance.
- Dependency interaction: `procedure-delegation-notification` suite (`backend/tests/procedure_delegation`) run against clean HEAD baseline and this delivery — identical failing-node set (0 new regressions). See `task7_pr_and_interaction_summary.json`.

## Blocked / GAPs
- Go-live activation items (production `ONLYOFFICE_JWT_ENFORCE=true`, Redis dispatcher fan-out, true 6000-concurrency, live Playwright) are validated at gate/API level or via honest extrapolation where the dev box cannot reach the literal target; see the spec evidence manifest.
- This PR excludes unrelated `procedure-delegation-notification` working-tree changes and scratch files.
