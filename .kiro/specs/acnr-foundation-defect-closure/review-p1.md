# Write-stale endpoint project authorization (ACNR P1 batch, T23/T25)

This batch closes an IDOR on the three endpoints that write `stale` markers: it retires the V2 `notify-cell-change` endpoint to a `410`, adds project-level `edit` authorization plus project-driven year backfill to `POST /api/linkage-bus/impact`, and converts the write-via-GET `GET /api/linkage-bus/impact-by-addr` into a side-effect-free read-only preview gated at `readonly`. The frontend stops sending stale-impact requests when no project is in context, silently swallows `403`, and drops the calendar-year fallback so the backend alone decides the audit year. Guard coverage is the strong part: a dedicated permission-world test exercises the 401/403/allow matrix for every endpoint, and the AST-based body-carried authz ratchet drops its identity-only baseline 87→84 and pins both linkage-bus endpoints as project-level with a real source mutation.

**Watch for:** the other P1 concerns named in the review brief (version-lock fail-closed/persistence T17–T19, async-trace canonical addr_id T20, V2 write precision T21, consumer-migration AST ratchet T24, migration V/R pairing) are **not in this diff** — those tasks are still `[ ]` in tasks.md (confirmed). There is one informational behavioral change: `impact-by-addr`'s `max_depth` query param now actually takes effect where the old write path ignored it (possible).

**Verdict**: APPROVED

## High-level view

The authorization fix is fail-closed and lands in the request path, not a comment. `POST /impact` calls `assert_project_permission(db, user, body.project_id, "edit")` as its first awaited statement, so a non-member or under-privileged caller gets `403` before the engine runs; the permission-world test asserts `on_change` is invoked zero times on every rejection path. `GET /impact-by-addr` moves to a new read-only `preview_impact` that mirrors `on_change`'s BFS read path exactly but drops all three write side-effects (DB mark, SSE push, audit log) and, when degraded, returns an empty impact instead of falling back to the coarse `mark_stale` write. `notify-cell-change` is reduced to a docstring plus a single `raise HTTPException(410)`, with the request body parameter removed so it cannot touch data.

Year handling no longer hardcodes `2025`. When the request omits `year`, the backend backfills from `fetch_project_audit_year(db, project_id)` and returns `422 YEAR_REQUIRED` if that is unknown. The frontend was the source of the old calendar-year default (`new Date().getFullYear()`); both `useStaleImpact` and `useEditorSave` now send no `year` when it is unknown and let the backend decide.

The ratchet changes are AST-based and falsifiable, not text matching. `test_project_endpoint_authz_body_carried.py` detects project-carrying endpoints structurally, classifies each as project/identity/none, and the `_FIXED_ENDPOINTS` nail re-parses each pinned endpoint, strips its project gate via an AST transformer, and asserts the scanner then sees it demoted — so a future regression that quietly removes the gate fails the test. The identity-only baseline is a two-sided assertion (`n <= 84` and `84 - n <= 20`), which blocks both growth and hollow overclaiming. T25's claim that the remaining V2 endpoints (`/stats`, `/resolve`, `/anchors`, `/stale-impact`, `/dependencies`) are read-only, project-id-free, and correctly login-only holds: `GET /stale-impact` loads static dependency files and does in-memory BFS with no DB write.

<details>
<summary>Issues (1)</summary>

1. **`impact-by-addr` max_depth now honored** — the read-only `preview_impact(source_uri, max_depth)` passes the query-param `max_depth` (default 3) through to BFS, whereas the old `on_change` path ignored it and always used depth 5. Benign behavioral change worth noting; no action required. (possible)

</details>

<details>
<summary>Details</summary>

### notify-cell-change retirement is fail-closed and body-stripped

The old handler accepted an arbitrary `body: dict`, pulled `project_id` out of it, hardcoded `year = int(body.get("year", 2025))`, and called `stale_engine.on_change(...)` inside a bare `try/except Exception: pass` — a textbook IDOR with a silently-swallowed write. The replacement removes the `body` parameter entirely and raises `410 ENDPOINT_GONE` after only `get_current_user`, so an authenticated caller cannot reach any data layer and an anonymous one still gets `401`. The guard proves this structurally rather than by behavior alone: `test_notify_cell_change_body_is_only_raise` parses the module, finds the function, strips the docstring, and asserts the body is exactly one `ast.Raise` with no `body` parameter in the signature. That AST assertion is what makes "the endpoint touches no data" a claim the test can defend, not a comment to trust.

### /impact gates before the engine and the mutation test proves it

`assert_project_permission(db, current_user, body.project_id, "edit")` is the first awaited call, before the `stale_engine.is_degraded` check and before `on_change`. The permission-world test asserts that every rejected identity (non-member, anonymous, readonly, review, EQCR, QC-review) produces `on_change.count == 0`, and that the allowed set (manager/edit member and global admin) reaches the engine exactly once with the request's own `project_id` and `year`. `ImpactRequest.project_id` is typed `UUID` (rejecting malformed ids at the model boundary) and `year` is `int | None` with a `ge/le` range, so the "no year" and "backfilled year" paths are both covered — `test_impact_missing_year_and_no_project_year_is_422` stubs `fetch_project_audit_year` to `None` and asserts `422 YEAR_REQUIRED` with the engine untouched. The `_FIXED_ENDPOINTS` ratchet adds the real teeth: `test_fixed_endpoint_stays_project_level_and_mutation_is_caught` strips the project-level call from the function body (and swaps a `Depends(require_project_access(...))` default for `get_current_user`), then asserts the scanner re-classifies the endpoint as identity/none — a silent future removal of the gate cannot pass.

### impact-by-addr becomes a true read-only preview

Converting a GET that wrote to the database is the right fix; the concern with such conversions is whether the "read-only" path still has a hidden write. `preview_impact` is a faithful read-only mirror of `on_change`: same `_detect_and_normalize` normalization, same `_addr_id_index` lookup, same `_bfs`, but none of `_mark_stale_by_uri` / `_notify_frontend` / `_write_audit_log`. The degraded branch is the place a careless mirror would leak a write — the original `on_change` degraded path calls `_fallback_mark_stale` (a coarse write). `preview_impact` deliberately returns `{"affected": [], "total": 0, "degraded": True}` instead, and the docstring calls out why. The test asserts `on_change.count == 0` while `preview.count == 1` on the readonly-member success path, which pins the no-write guarantee to behavior rather than to the absence of a call in source.

One behavioral delta: the old write path hardcoded `max_depth=5` inside `on_change` and ignored the endpoint's `max_depth` query param; `preview_impact(source_uri, max_depth)` now passes the query value (default 3) through to BFS. Callers that relied on always getting depth-5 results from this GET will now get depth-3 by default. This is almost certainly an improvement (the query param finally works), but it is a visible change in returned impact breadth.

### Year no longer defaults to the calendar year

The hardcoded `2025` on the backend and `new Date().getFullYear()` on the frontend were two independent sources of a wrong audit year. The backend now backfills from the project and fails closed (`422`) when it cannot. On the frontend, `useStaleImpact` builds the body conditionally (`if (payload.year) body.year = payload.year`) and returns early when `payload.project_id` is falsy — so an editor with no project context issues no request instead of a guaranteed `403`; `useEditorSave` passes `opts.wpDetail.value?.year` without the calendar fallback. The `403` branch in `useStaleImpact` logs and returns `null` (non-blocking), which is correct for a notify-only side effect that must not block a save.

### V2 remaining endpoints stay login-only by design (T25)

`GET /api/address-registry/v2/stale-impact` was worth confirming because it shares the "stale-impact" name with the write endpoints. It takes `wp_code`/`sheet`/`cell` query params (no `project_id`), calls `_load()` to read the static CWR/L3 dependency files, and does an in-memory BFS with no `on_change` and no DB write. The module docstring now records the T25 conclusion that `/stats`, `/resolve`, `/anchors`, `/stale-impact`, `/dependencies` are read-only module-level static graph reads and keep `get_current_user` only. The body-carried ratchet corroborates this independently: after retirement, `notify_cell_change` drops out of the body-carried dimension (no project param), and the scanner finds no project-id-carrying unauthorized write endpoint in V2.

### Scope note — the rest of P1 is not in this diff

The review brief lists version-lock fail-closed/persistence (T17–T19, including migration V/R pairing and `IF NOT EXISTS`), async-trace real addr_id (T20), V2 write precision / exact-match-only (T21), and the consumer-migration AST ratchet with falsifiable exemptions (T24). None of these files appear in `git diff d1da8ea95..HEAD` — no `project_registry_lock.py`, no `migrations/V*.sql`, no `cross_sheet_trace_orchestrator.py`, no `v2_canonical.py`, no `acnr_bypass_scan.py`, no `catalog_snapshot_gc.py`. Those tasks remain `[ ]` in tasks.md. This batch is T23/T25 only; the other concerns have no evidence here because they are not yet implemented, and they are out of scope for this review rather than deficient.

</details>

<details>
<summary>File map</summary>

- `backend/app/routers/linkage_bus.py` — `/impact` gains `edit` project auth + project-year backfill (no hardcoded 2025); `/impact-by-addr` switches from write-via-`on_change` to read-only `preview_impact` + `readonly` auth; `ImpactRequest.project_id` typed `UUID`, `year` optional.
- `backend/app/routers/address_registry_v2.py` — `notify-cell-change` retired to `410` with body param removed; module docstring records T25 read-only conclusion.
- `backend/app/services/stale_propagation_engine.py` — new side-effect-free `preview_impact` (fail-closed on degraded, no `_fallback_mark_stale`).
- `backend/tests/acnr/test_stale_write_endpoint_authz.py` — permission-world 401/403/allow matrix for all three endpoints + AST assertion on retired body.
- `backend/tests/test_project_endpoint_authz_body_carried.py` — identity-only baseline 87→84, two linkage-bus endpoints pinned in `_FIXED_ENDPOINTS`.
- `backend/tests/test_audit_year_calendar_fallback_ratchet.py` — drops `address_registry_v2.py` entry (calendar fallback removed).
- `audit-platform/frontend/src/composables/useStaleImpact.ts` — no-project short-circuit, conditional year, silent `403`.
- `audit-platform/frontend/src/composables/useEditorSave.ts` — drops calendar-year fallback.
- `audit-platform/frontend/src/services/apiPaths/system.ts` — `notifyCellChange` constant deleted.
- `.kiro/specs/acnr-foundation-defect-closure/tasks.md` — T23/T25 marked `[x]`.

Full diff: `git diff d1da8ea95 HEAD`
</details>
