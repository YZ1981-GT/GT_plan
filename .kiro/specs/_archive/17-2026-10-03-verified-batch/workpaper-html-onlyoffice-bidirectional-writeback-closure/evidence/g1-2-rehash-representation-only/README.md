# G1-2 Rehash Representation-Only Path

Owner: current G1-2 coding session.
Status: IN_PROGRESS. No production bidirectional completion claim. Real PostgreSQL migration (`--apply`) NOT RUN.

## Problem (real design tension, not a rename)

The existing `fix_projection_representation_rehash.py --apply` repairs BP-30 legacy
`structure_hash` by **re-projecting the HTML store business payload** through
`stage_instrumented_substrate` + `publish_first_generation`, which goes through
`ContentMutationService.commit(...)` and therefore advances `content_revision`
(`expected_revision + 1`) and creates a new content version.

Master control §3.4 item 4 and DEC-03 require rehash to become **representation-only**:
create a new representation generation on the **existing** content version via
`RepresentationService.finalize_candidate(...)` with the business `content_revision`
unchanged.

These two are not the same operation. The script itself documents that a store-backed
entry (D2 store ~490KB of real detail rows) must NOT be finalized from an
instrumentation-only candidate because that path carries no business payload and would
publish an empty-managed representation. So a blanket "replace publish_first_generation
with finalize_candidate" would either drop data or be structurally impossible.

## Adjudication (G1-2)

Two distinct stale causes require two distinct repairs:

1. `stale_needs_rehash` where the artifact **bytes are unchanged** and only the frozen
   `structure_hash` column reflects the old whole-file formula (recomputed managed hash
   differs from the frozen column, but the `_GT_SYNC` frozen coordinates are consistent
   with physical structure): this is a pure representation-identity correction. It MUST
   be repaired representation-only: same content version, new representation generation,
   `content_revision` unchanged, old generation retained and not current, failure never
   switches the entry pointer.

2. `stale_needs_reprojection` where the `_GT_SYNC` frozen coordinates have drifted from
   physical structure (the second `_gtsync_structure_drift` == "drift" branch): the
   artifact bytes themselves need to be re-materialized from the current store payload.
   That is genuinely new business content and legitimately produces a new content
   version. It is out of scope for the representation-only owner and remains an explicit
   reprojection branch.

This split is the honest reading of the two existing stale detectors already in the
script; G1-2 does not invent a third detector.

## Scope

- `fix_projection_representation_rehash.py`: split the single `stale_needs_rehash` state
  into pure-hash vs coordinate-drift; route pure-hash through a representation-only
  finalize path; keep coordinate-drift reprojection explicit and labelled as a new
  content version.
- In-memory / seam behavior tests. No shared file edits. No `--apply`.

## Gates

- Pure-hash rehash: existing content version reused, new representation generation,
  `content_revision` before == after, entry pointer only moves to the new generation,
  failure leaves revision and pointer unchanged, second run is idempotent.
- Historical representation rows remain immutable (no UPDATE of `structure_hash`).
- Coordinate-drift reprojection stays on the reprojection branch and is not silently
  routed into the representation-only path.
- custom/opaque and Word lanes untouched.

## Tests

Seam/behavior suite `backend/tests/workpaper_sync/test_g1_2_rehash_representation_only.py`:
`7 passed`. Covered:

- pure-hash stale routes to the representation-only branch and `publish_first_generation`
  is never called (a fake that raises on call proves it);
- coordinate-drift stale is classified `stale_needs_reprojection` (reprojection retained);
- consistent entry is an idempotent no-op;
- representation-only blocks (`no_finalizable_candidate`) without advancing revision when
  no `state=ready` candidate exists;
- the finalize seam blocks with `finalize_inputs_pending_provisioning` rather than falling
  back to first-publication;
- AST guard: the representation-only finalize seam references no real
  `publish_first_generation` call (only the reprojection branch keeps it) and names
  `finalize_definition_upgrade` as the sole revision-locked exit.

`py_compile` and scoped `git diff --check` clean. Real OnlyOffice / real PostgreSQL
migration (`--apply`): NOT RUN.

## Rollback

Revert only this package's exact hunks after reviewing concurrent diff; remove only this
package's new evidence/test files. No database rollback needed because this package
performs no business database writes.

## Real PostgreSQL finalize EXECUTED (2026-09-09, audit-postgres:5432)

Entry `xlsx/gt-h1-fixed-assets` (wp `f663b18c`) had a `state=ready` candidate and a
genuinely pure-hash-stale gen-1 (frozen `c573174d3906` ≠ recompute `1340ff20f9a4`,
`_GT_SYNC` consistent). A dedicated verified-in-steps driver was built:
`backend/scripts/fix/finalize_ready_candidate_representation_only.py` (`--check` read-only
preview, `--apply` real write). It derives finalize inputs (observed structure / business
sheets / dynamic columns / identity inventory) from the candidate's staged instrumented
bytes using the request-time observer primitives, reconstructs `StagedCandidate` from the
DB row + on-disk artifact, and drives the sole revision-locked exit
`ExcelEntryFinalizeGate.finalize_candidate → MaterializeCoordinator.finalize_definition_upgrade`
via the production `build_materialize_coordinator` factory.

`--check` passed read-only (rollback). `--apply` result: `state=finalized`,
`new_generation=2`, `revision_after=1`, `revision_unchanged=True`. Post-write DB facts
(read-only): new gen-2 `definition_upgrade` current with new-formula hash; old gen-1
retained/not-current; **both generations share the same content_version_id**;
`content_revision` unchanged (1); candidate → `finalized`. G1-3 then settled this wp
`verified`.

This confirms the G1-2 representation-only path end-to-end on a real DB: a pure-hash-stale
entry gets a new representation generation without advancing the business revision, and
the request path (observer + registry) verifies the migrated generation.

## Remaining Blocker

D2 / G7 and the second H1 instance have no ready candidate / are not stale, so they are
not migrated (honestly `migration_not_run` / `already_consistent`). Real OnlyOffice /
browser bidirectional verification remains a later phase (G4+).
