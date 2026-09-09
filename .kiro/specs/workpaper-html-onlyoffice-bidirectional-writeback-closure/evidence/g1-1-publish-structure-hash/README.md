# G1-1 Publish Structure Hash

Owner: current G1-1 coding session.
Status: IN_PROGRESS. No production bidirectional completion or G1-2 migration claim.

## Scope

Mother spec execution constraints; content_mutation; publish_time_structure_hash; published_identity_observer frozen reader reuse; materialize_coordinator; oo_to_html; conflict_resolution; excel_entry_gate; focused tests only.

## Gates

- Frozen bundle instrumentation approved state, slot digest and payload digest validated.
- Excel missing anchors/contract rejected; Word independent hash and custom/opaque authoritative bytes preserved.
- Final staged candidate bytes delegated to shared compute_structure_hash_from_artifact.
- Three hosts pass their own frozen anchors; behavior and in-memory mutation counterexamples required.
- No business database writes, rehash --apply, staging or commits.

## Tests

Pending targeted pytest and mutation counterexamples. Real OnlyOffice NOT RUN.

## Rollback

Revert only this package's exact hunks after reviewing concurrent diff; remove only this package's new evidence/test files. Never reset shared files or index. No database rollback is needed because this package performs no business database writes.

## Execution Result

- Targeted regression: `504 passed, 1 skipped` in 38.13s.
- Covered: projection hash consumes final bytes; missing contract/anchors fails closed; broken Excel Table is rejected; Word/custom lanes retain independent digest semantics; frozen payload child/state/digest checks; three ContentCommitPlan hosts use awaited frozen anchors; in-memory fail-open mutation is detected.
- The finalize success-path behavior test is skipped because the existing fixture lacks a persisted per-entry contract definition/blob and cannot honestly exercise the production loader. Existing gate tests remain green; no fake definition was introduced.
- Real OnlyOffice 9.4/browser test: NOT RUN.
- `rehash --apply`: NOT RUN. Business DB writes: NONE. Git stage/commit: NOT RUN.

## Remaining Blocker

A real finalize candidate fixture must provide approved frozen template/instrumentation/contract child rows and blobs plus a real staged XLSX; then assert coordinator receives the shared final-artifact hash. This is required before claiming full G1-1 production closure. G1-2 migration remains out of scope.

### Latest state (supersedes skip explanation above)

Replaced the temporary skip with a scoped `load_contract` fixture override using the existing parsed Task36 contract; the production finalize body still executes. The latest focused rerun was interrupted (`exit -1`, Ctrl+C), so the latest test file is NOT VERIFIED. The 504 passed / 1 skipped result describes the preceding version only. Do not mark G1-1 complete. Scoped `git diff --check` passed before this final fixture edit; recheck is required for final acceptance.
