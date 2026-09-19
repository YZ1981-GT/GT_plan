# G3-1 Request-Path Registry & Frozen-Definitions Resolution

Owner: current session.
Status: request-path registry + observer/extract-adapter build verified on live DB.
Full HTML→OO materialize endpoint (pending mutation + auth + room) deferred to G4.

## Verified on live DB (audit-postgres:5432, read-only)

1. Registry真注册 (`register_from_manifest`):
   - registered adapters: `d2.receivable_detail`, `g7.soe_subsidiary_disclosure`,
     `h1.disposal_check` (3 projection entries);
   - registered entry ids match; 183 other entries carry explicit reasons — no silent skip;
   - `build_production_registry()` binds the manifest-driven plan at construction (callers
     only supply the DB session), matching master control §4.1 step 3.

2. Observer / frozen-definitions request path for the finalized H1 gen-2:
   - `observe_published_frozen_definitions` resolves the current published representation,
     loads frozen template/instrumentation/contract children, and builds the
     extract-capable adapter (`h1.disposal_check`, doc_type `xlsx`, 25 structure items);
   - recomputed managed `structure_hash` matches the frozen value (no `ObservedIdentityDriftError`),
     confirming the request path consumes the migrated generation safely;
   - `resolve_for_entry` returns the same adapter (see G1-3 `verified`).

3. Router wiring (`backend/app/routers/wp_sync_router.py`): the `materialize` endpoint is
   assembled via `build_materialize_coordinator` and `build_production_registry()`, and
   `_attach_pilot_adapters` runs `register_from_manifest` on the request path.

## Deferred (honest boundary)

The full HTML→OO `POST {USER_SYNC_PREFIX}/materialize` end-to-end (create pending mutation
→ authorize → materialize → launch descriptor → OO room) requires an authenticated user
request with a signed pending-mutation token and room creation. That is the Phase 4 (G4)
pilot flow and needs the real browser/OO harness; it is not driven here. What is proven
here is the request-path **registry registration** and **frozen-definitions resolution /
extract-adapter build** — the two things master control Phase 3 exit gate names as
"render-config → materialize → extract uses the same frozen definitions" at the resolution
layer.

## Note

No business DB writes in this package (all queries read-only). The only live write this
session was the G1-2 H1 finalize (its own evidence), which G3-1 then consumed read-only.
