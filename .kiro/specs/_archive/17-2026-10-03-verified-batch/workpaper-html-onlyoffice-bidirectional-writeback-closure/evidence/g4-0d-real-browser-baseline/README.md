# G4 Real Backend + Browser Verification (D2-2 canary)

Owner: current session.
Status: unified backend path proven end-to-end via real HTTP; real browser baseline
captured. Frontend host migration (G4-0a/0b/0c) NOT applied. Full OO round-trip
(`working_paper_content_application` applied row) NOT produced.

## Environment (all live)

`start-dev.bat` stack confirmed online: frontend 3030, backend 9980, OnlyOffice 8080,
vLLM 8100. Postgres audit-postgres:5432. Real admin login worked (Playwright).

## Correction of an earlier sub-agent claim

A sub-agent (no DB access) claimed, from a stale docstring, that D2 "has no published
representation / approved bundle → unified materialize必 422 adapter_not_ready". Live DB
disproves this:

- D2 / G7 / H1 all have current published representation + approved bundle;
- `register_from_manifest` registers all three adapters (`d2.receivable_detail`,
  `g7.soe_subsidiary_disclosure`, `h1.disposal_check`);
- `assert_bidirectional_ready` PASSes for all three.

So D2's unified backend supply is ready. The real remaining blocker is the **frontend
host**, not backend supply.

## Real HTTP verification of the unified path (D2, active project 2aa00f57)

A one-shot probe (admin token via `create_access_token`, since deleted) walked the unified
endpoints against live 9980 for `xlsx/gt-d2-accounts-receivable`:

1. `POST .../sync/entries/{entry}/materialize` with `projection: {}` → 422
   `projection_payload_invalid` ("缺 `values` 对象") — payload shape enforced.
2. with `projection: {"values": {}}`, no token → 409 `pending_mutation_token_required`
   (Requirement 3.2 / Property 8) — 2-step protocol enforced.
3. `POST .../pending-mutations` with `{"values": {}}` → **200**, returns a real
   `pending_mutation_token` (wrapped in `{code,message,data}`).
4. materialize with token but mismatched Idempotency-Key → 409
   `materialize_idempotency_key_mismatch` — token freezes the key; same key required.
5. materialize with matching key + empty `{"values": {}}` → 500
   `roundtrip_projection_mismatch`: the empty projection wrote an empty managed region,
   then extract read back **28491** existing D2 managed fields, and the roundtrip
   equivalence guard correctly rejected it.

Conclusion: the unified path is reachable, authenticated, and enforces every invariant
correctly (payload shape → pending-token → idempotency-key binding → roundtrip
equivalence). Driving it to a successful launch descriptor requires the **real D2 store
projection** (the 28491 managed field values), which is what the frontend bridge
(`useWorkpaperSyncBridge` via a `flushHtml` that projects the D2 store into
`{values: {...}}`) must assemble. The backend is not the blocker.

## Real browser baseline (Playwright, logged-in admin)

- Logged in (admin/admin123), opened D2 editor
  `/projects/2aa00f57.../workpapers/ef7f88e3.../edit` (0 console errors on load).
- Clicked the 明细表D2-2 tab → observed `GET /api/workpapers/{wp}/d2-sync/status => 200`.
  This is the legacy bypass (master control §2.4.2), confirming D2 is still
  `REQUEST_PATH_LEGACY` at the host level. No `USER_SYNC_PREFIX` request was made by the
  D2 host.
- The unified `USER_SYNC_PREFIX` prefix (`/api/projects/{p}/workpapers/{w}/sync/entries/...`)
  is NOT yet requested by the D2 frontend host — that is exactly what G4-0a/0b/0c must
  change.

## G4-0a applied (safe, verified)

`GtOnlyOfficeSheet.vue` `forceSave()` no longer hardcodes the legacy URL. Added an optional
`forcesaveEndpoint` prop defaulting to `''`; when empty it falls back to the legacy
`/api/workpapers/{wpId}/d2-sync/forcesave` (byte-identical current behavior). The host can
now inject `POST {USER_SYNC_PREFIX}/rooms/{room_id}/forcesave` for the unified migration
without editing this shared component. Since only `GtD2AccountsReceivable` ever calls
`forceSave()` (the 178 other entries merely mount the component and never trigger this
path), and the default is unchanged, this is zero-impact on non-D2 entries.

Verified: `d2SyncDurableGate.spec.ts` 10/10 passed (the durable-gate suite exercises the
forceSave path).

## Why the full frontend host migration (0b/0c/0d) was not completed in this pass

`GtD2AccountsReceivable` currently uses `useD2SyncBridge` + `GtOnlyOfficeSheet` (legacy
`/d2-sync/*`, config with `customization.forcesave:true`). Migrating it to the unified
`WorkpaperSyncEditorHost` + `useWorkpaperSyncBridge` requires:

- a `flushHtml` hook that projects the D2 store (`useD2FormData`) into the contract's
  stable-key `{values: {...}}` (28491 fields) — the deep part;
- switching the editor component to the descriptor-driven host (the unified host refuses
  `customization.forcesave:true`, so the legacy config endpoint cannot be reused);
- routing forcesave/confirm/close through the room_id from the materialize descriptor.

This is a substantial rewrite of a live audit component whose only meaningful acceptance
is a full real-OO round-trip (open DocEditor → edit → forcesave → callback → durable
incoming → application `state='applied'` → HTML refresh). Performing that rewrite and its
interactive multi-step browser verification safely is the next unit of work; it was not
completed in this pass to avoid landing an unverified change to a production component.

## Honest status vs HOST-CONSUMES-UNIFIED-PATH

D2-2 remains `REQUEST_PATH_LEGACY`. `working_paper_content_application` for D2 is still 0
(no applied row). The 8 predicates are not met. This evidence advances the picture from
"unknown whether unified path works for D2" to "unified backend path verified working;
only the frontend host + real OO round-trip remain", but it does NOT claim
`bidirectional_verified`.
