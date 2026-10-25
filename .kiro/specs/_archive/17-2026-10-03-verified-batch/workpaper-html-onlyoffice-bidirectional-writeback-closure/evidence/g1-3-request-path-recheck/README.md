# G1-3 Request-Path Recheck (post representation-only migration)

Owner: current G1-3 coding session.
Status: IN_PROGRESS. Read-only recheck host + machine predicates only. Real
PostgreSQL recheck NOT RUN because its precondition (a G1-2 representation-only
migration actually applied on a real DB, producing a new generation) is not yet met.

## Scope

- `backend/scripts/check/check_rehash_request_path_recheck.py`: read-only host that, for a
  migrated current generation, re-runs the observer and registry request paths and asserts
  identity consistency + version orthogonality.
- Seam/behavior tests. No DB writes. No migration.

## Predicates (all read-only)

1. Observer request path: `observe_published_frozen_definitions(...)` on the new current
   published representation recomputes the managed `structure_hash` and compares it to the
   frozen value (BP-30 isomorphic formula). Legacy-formula rows raise
   `ObservedIdentityDriftError` here.
2. Registry request path: `build_production_registry().register_from_manifest(session=...)`
   then `resolve_for_entry(entry_id)` must resolve to the same adapter the observer
   reports, and the entry must not appear in the unregistered `reasons`.
3. Version orthogonality: the new current generation must be greater than the
   pre-migration generation, while `content_revision` must be unchanged (Property 4).

## Closed settlement vocabulary

`verified / drift / registry_mismatch / version_domain_violation / not_published /
migration_not_run / blocked`. Any state outside this set raises.

## Tests

`backend/tests/workpaper_sync/test_g1_3_request_path_recheck.py`: `8 passed`. Covered:

- no history generation → `migration_not_run` (does not falsely report verified);
- observer drift → `drift`;
- generation not advanced → `version_domain_violation`;
- registry entry unregistered / adapter disagreement → `registry_mismatch`;
- observer + registry both pass with version orthogonality → `verified`;
- no current representation → `not_published`;
- closed vocabulary guard.

`py_compile` clean.

## Real PostgreSQL recheck EXECUTED (2026-09-09, audit-postgres:5432)

Precondition was met on the live DB: entry `xlsx/gt-h1-fixed-assets` had a `state=ready`
upgrade candidate (contract+bundle attached) bound to the existing content version, and
its current gen-1 representation was genuinely pure-hash stale (frozen `c573174d3906` ≠
publish-side recompute `1340ff20f9a4`, `_GT_SYNC` coordinates consistent).

A real representation-only finalize was applied via
`backend/scripts/fix/finalize_ready_candidate_representation_only.py --apply --entry
xlsx/gt-h1-fixed-assets` (see G1-2 evidence). Post-write DB facts (read-only verified):

- new representation gen-2, `reason=definition_upgrade`, current, structure_hash
  `1340ff20f9a4` (new formula);
- old gen-1 retained, not current, unchanged;
- both generations share the same `content_version_id` (9349d5f8…);
- `content_revision` = 1 before and after (unchanged);
- candidate → `finalized`.

Then this G1-3 host was run against the live DB:

```
xlsx/gt-h1-fixed-assets (wp f663b18c): verified
  observer + registry request paths passed; generation 1 → 2, content_revision unchanged (1)
xlsx/gt-h1-fixed-assets (wp c71b7c54): migration_not_run
```

The two H1 instances settling differently (migrated one `verified`, non-migrated one
`migration_not_run`) demonstrates the predicates truly discriminate state rather than
being uniformly green. The host was fixed during this run to iterate all wp instances of
an entry (BP-27) and to pass a full 16-field representation row to the observer.

## Why other entries remain not-verified

D2 / G7 and the non-migrated H1 instance have no post-migration generation, so the host
settles `migration_not_run` / `not_published` — honest, not a pass.

## Rollback

Revert only this package's exact hunks; remove only this package's new host/test/evidence
files. No database rollback needed (no business DB writes).

## Remaining Blocker

Real PostgreSQL recheck against a migrated generation, gated on G1-2 `--apply` having run
with a ready candidate. Real OnlyOffice / browser bidirectional verification remains a
later phase (G4+).
