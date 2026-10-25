# G4+ Boundary Assessment (why offline work stops here)

Owner: current session.
Status: assessment only. No production frontend/router change made; no fake OO/browser
evidence produced.

## What is already in place (verified read-only)

- Unified forcesave endpoint **exists**: `POST {USER_SYNC_PREFIX}/rooms/{room_id}/forcesave`
  in `wp_sync_router.py` (status 202), with room-bound target derivation from the room row.
- Unified callback endpoint exists: `POST /api/workpaper-sync/rooms/{room_id}/onlyoffice-callback`.
- The `materialize` endpoint + `register_from_manifest` request path are wired (see G3-1).

## Why G4-0a..0d cannot be honestly completed offline here

1. **G4-0a (redirect `GtOnlyOfficeSheet.forceSave()` to the unified endpoint)** is a coupled
   change, not a one-line swap. The unified endpoint requires a `room_id`, which only exists
   after a `materialize` launch descriptor creates a room. Today `forceSave()` posts to the
   legacy `/api/workpapers/{wpId}/d2-sync/forcesave` and 179 entries share this component
   (master control §2.4.5 / DEC-08). Redirecting it without the room lifecycle in place would
   leave 179 entries calling an endpoint for a `room_id` they do not yet hold — the exact
   reverse-order hazard DEC-08 forbids.
2. **G4-0b (room-bound callback URL)** changes `onlyoffice-config` so the callback carries
   `room_id/generation/doc_key/route_credential_id`. Verifying it actually enters the
   `CallbackDeliveryService` branch requires a real OnlyOffice document server issuing the
   callback — not reproducible offline.
3. **G4-0c (checklist save → `ContentMutationService.commit`)** removes the D2 dual-commit
   window. It is verifiable in isolation, but its acceptance is tied to the same real HTML→OO
   round-trip as 0a/0b (otherwise it is an unobservable rewrite).
4. **G4-0d (real OO round-trip evidence)** and **G4-1 (Playwright bidirectional)** require the
   real browser + OnlyOffice 9.4 container with an authenticated user session, per master
   control §9.6. These produce the only evidence that counts for `bidirectional_verified`
   (`HOST-CONSUMES-UNIFIED-PATH` 8 predicates, incl. a `working_paper_content_application`
   row with `state='applied'`). They cannot be fabricated without the live harness.

## Honest status

- Phases G0 (governance milestones), G1 (structure_hash unification + representation-only
  rehash, **with a real PG finalize + G1-3 `verified`**), G2 (BP-21 typography guard;
  structure-engine owner separation + delete matrix; BP-21 delete-test consistency fix), and
  G3 (request-path registry + frozen-definitions resolution on live DB) are done to the
  offline/live-DB-verifiable boundary.
- G4-0a onward is a live-OO/browser migration. The unified endpoints already exist; the
  remaining work is the coupled host migration + real OO/Playwright evidence, which needs the
  running `start-dev.bat` stack and interactive verification.

D2-2 / H1(non-migrated instance) / G7 remain honestly not `bidirectional_verified`:
`HOST-CONSUMES-UNIFIED-PATH` for them is `REQUEST_PATH_LEGACY` / `migration_not_run` until the
G4 host migration and real OO round-trip run.
