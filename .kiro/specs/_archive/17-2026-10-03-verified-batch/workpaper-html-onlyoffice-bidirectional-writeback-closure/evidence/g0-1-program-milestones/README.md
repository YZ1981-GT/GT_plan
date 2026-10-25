# G0-1 program milestone registry evidence

## Scope and decision

This evidence closes only **G0-1** from `docs/operations/workpaper-html-onlyoffice-bidirectional-writeback-master-control.md`: program milestone registry, deterministic generator, guard, and an attribution-style CI job. It deliberately does **not** change the eight specs' task states (G0-2), does not add core Task 72 → Task 74 (G0-3), and does not implement the eight per-entry `HOST-CONSUMES-UNIFIED-PATH` predicates (G0-4).

Owner: `workpaper-html-onlyoffice-bidirectional-writeback-closure:program-governance`

Reviewed definition single source: `backend/data/workpaper_sync_program_milestone_definitions.json`

Generated projection: `backend/data/workpaper_sync_program_milestones.json` (must not be edited by hand)

## Work-package completeness

The reviewed definition declares every required start field before implementation: owner, modified files, input gates, output artifact, targeted tests, real scenarios, rollback plan, and this evidence path. Rollback is file-only and reversible; G0-1 has no migration or business-data write.

Delivered files:

- `backend/data/workpaper_sync_program_milestone_definitions.json`
- `backend/data/workpaper_sync_program_milestones.json`
- `backend/scripts/gen/generate_workpaper_sync_program_milestones.py`
- `backend/tests/workpaper_sync/test_workpaper_sync_program_milestones.py`
- `.github/workflows/governance-checks.yml` — EOF attribution-only job `workpaper-sync-program-milestones`
- this README

## Machine-recomputed snapshot

Projection identity:

- program state: `STALE` (honest aggregate, not a G0-1 implementation failure)
- program digest: `13751e806a9e26516735eb205d7e3f547be45d64f2f68b069725c1d4f98ec59a`
- definition digest: `82dc29e3e3afc7f48f65c44355c8b1d1ebd0eb886f5856291f3642580a705140`
- source digest: `d0f0550c168e23078011dd7ae10b5d8925902522676a23ddd0e063afcc3de436`
- database probe digest: `fac2c53b411d784ea21690d2a2077a7d9610fef9127682b9cec9b12d4391f405`
- deterministic metadata: `generated_at=null`, `source_commit=null`; freshness is digest-bound rather than wall-clock/Git-HEAD-bound

Denominators and DAG:

- 8 specs / 261 checkbox tasks
- 445 internal dependency edges / 114 cross-spec edges
- combined graph: acyclic
- diagnostics: 7 blockers, all retained in projection

Milestone states:

| State | Milestones |
|---|---|
| `IMPLEMENTED` (3) | `SYNC-DURABLE-APPLICATION`, `SYNC-UNIFIED-ROOM`, `WORKBOOK-PROPAGATION-READY` |
| `BLOCKED` (4) | `HOST-CONSUMES-UNIFIED-PATH`, `ROW-MUTATION-READY`, `TEMPLATE-OVERRIDE-CHANGED`, `X-RUNTIME-EVIDENCE` |
| `STALE` (9) | `F-SHELL`, `G-C0`, `G-HANDOFF-CONSUMER`, `G-ID`, `G-RAIL`, `PUBLISHED-ENTRY-READY`, `SYNC-ENTRY-NAMESPACE`, `SYNC-MULTI-RESOLVER`, `X-HANDOFF-CONFORMANCE` |
| `REQUEST_PATH_VERIFIED` / `ONLYOFFICE_VERIFIED` / `CLOSED` | none |

The generator prevents a checked task, manifest `capability`, class/symbol presence, or a DB table from granting `CLOSED`. Only a passing digest-bound evidence predicate with an explicit `grants_state` can advance beyond `IMPLEMENTED`.

## Mandatory database read-only probe

The initial generator draft omitted the master control's database probe input. The final implementation now executes one transaction-scoped live probe and fails non-zero when it cannot prove read-only mode:

1. acquire the configured PostgreSQL connection;
2. execute `SET TRANSACTION READ ONLY`;
3. execute `SHOW transaction_read_only` and require `on`;
4. run only the closed `_DATABASE_FACT_SQL` SELECT allowlist;
5. rollback the session;
6. classify connection failure, query/read-only failure, and observed schema absence separately.

Current observed stable catalog facts:

- relations: 7 / 7
- required columns: 60 / 60
- required constraints: 23 / 23
- `durable-application-schema`: pass
- `unified-room-schema`: pass

Only stable relation/column/constraint facts enter the committed projection. Mutable application/operation/content-version row counts are intentionally excluded; those are runtime evidence owned by G0-4 and later real-OnlyOffice packages. This avoids binding the committed JSON to one developer database while still satisfying the required live DB probe.

## Diagnostics retained (not papered over)

- core archive Task 72 still lacks dependency on Task 74 — owned by G0-3;
- Custom spec still contains four natural-language `producer_system: workpaper-sync-version-kernel` placeholders;
- `HOST-CONSUMES-UNIFIED-PATH` has no G0-4 producer task yet;
- `TEMPLATE-OVERRIDE-CHANGED` has no concrete producer task yet;
- manifest source derivation is stale;
- writer inventory source check is stale;
- existing Formula/Guidance/Custom evidence has producer/consumer or artifact-digest gaps, so it projects `STALE` rather than `CLOSED`.

## Validation

Executed from repository root on Windows with the configured PostgreSQL database:

```text
python backend/scripts/gen/generate_workpaper_sync_program_milestones.py --check
→ exit 0; program=STALE; specs=8; tasks=261; milestones=16; diagnostics=7
→ digest=13751e806a9e26516735eb205d7e3f547be45d64f2f68b069725c1d4f98ec59a

python -m pytest backend/tests/workpaper_sync/test_workpaper_sync_program_milestones.py -v --tb=short
→ 16 passed, 2 warnings in 134.86s
```

The first pytest attempt hit the command runner's 120-second limit after 14 passing tests; it was not treated as green. A 300-second rerun completed all 16 tests. The two warnings are the pre-existing invalid escape warning in `backend/tests/test_ledger_keyword_escape.py` discovered while the writer gate imports the test inventory.

Guard coverage includes: generated-byte freshness, program/database self-digests, exact eight-spec and task/DAG denominators, `[x]*` optional task syntax, unknown producer rejection, combined cycle rejection, archive-debt diagnostic duality, checkbox/capability anti-closure, evidence artifact digest drift, live read-only DB execution, unavailable/query-failed/empty-catalog fail-closed cases, SQL allowlist AST checks, DB requirement digest mutation, and writer-gate live recomputation.

Browser/real OnlyOffice is **not applicable to G0-1**. Running D2-2 round-trip here would cross the ordered boundary into G4-0d and could falsely imply host-path verification. G0-1's real scenarios are repository/DAG/source/evidence recomputation plus the live read-only database schema probe.

## CI and clean-checkout status

The CI job was appended at EOF after confirming `.github/workflows/governance-checks.yml` had no unstaged changes and its last write was more than six hours old. It bootstraps an isolated PG16/pgvector database, fails if any migration fails, then runs generator `--check` and the 16 guards. The probe itself remains strictly read-only.

Current repository tracking blockers are intentionally visible:

- `.kiro/specs/custom-workpaper-template-ingestion-and-sync-closure/` is untracked;
- `.kiro/specs/workpaper-page-formula-toolbar-closure/` is untracked;
- Guidance spec inputs are staged by another owner.

Therefore a clean checkout cannot yet supply all eight task/evidence inputs and the new CI job is expected to fail closed until those owning lanes add their formal spec artifacts. G0-1 does not copy their tasks into a second truth and does not skip missing inputs.

## Rollback

Remove the five new G0-1 definition/projection/generator/test/evidence paths and remove only the EOF `workpaper-sync-program-milestones` CI job. Do not alter the eight source specs, V151 schema, manifest, writer inventory, or business data.
