# Milestone BLOCKED regression triage

Status: CONCLUDED — verdict (ii) genuine blocker. **No files changed, no baseline touched.**

Target: `backend/tests/workpaper_sync/test_workpaper_sync_program_milestones.py`
Assertion under scrutiny: `test_g0_3_does_not_promote_tasks_milestones_or_g0_4` →
`assert counts["BLOCKED"] <= 3` where `counts = registry["stats"]["milestone_state_counts"]`
and `registry` is the **freshly built** projection (`source` fixture calls
`generator.build_program_registry()`), not the on-disk snapshot.

## Answer: which milestone went BLOCKED

**`SYNC-MULTI-RESOLVER`** — `STALE → BLOCKED`.

Predicate: `multi-resolver.writer-gate-zero`

| | reason_code | result |
|---|---|---|
| on-disk snapshot | `writer_inventory_source_check_failed:WriterGateError` | `stale` |
| fresh derivation | `writer_gate_multi_resolver_nonzero` | `blocked` |

The blocking fact is the writer revision gate's `multi_resolver` issue bucket being non-zero.
Three writers still resolve through more than one resolver, all in one router:

- `app.routers.wp_onlyoffice_router::get_sheet_onlyoffice_config`
- `app.routers.wp_onlyoffice_router::get_sheet_wopi_contents`
- `app.routers.wp_onlyoffice_router::post_sheet_onlyoffice_callback`

## Verdict: (ii), not (i) — and it is an *unmasking*, not a new break

**(i) is ruled out by measurement.** The manifest gate moves BLOCKED in the *opposite*
direction: `manifest_facts.source_current: True → False`
(reason `reviewed_overlay_source_digest_stale`) **suppresses** two milestones from
BLOCKED to STALE by adding a `*.manifest-integrity` stale predicate:

- `PUBLISHED-ENTRY-READY`: BLOCKED → STALE
- `SYNC-ENTRY-NAMESPACE`: BLOCKED → STALE

Counterfactual run (fresh predicates with the `reviewed_overlay_source_digest_stale`
predicate removed, replayed through the generator's own `derive_milestone_state`):

```
disk            BLOCKED = 5   {BLOCKED 5, IMPLEMENTED 3, STALE 8}
fresh           BLOCKED = 4   {BLOCKED 4, IMPLEMENTED 3, STALE 9}
manifest-green  BLOCKED = 4   {BLOCKED 4, IMPLEMENTED 3, STALE 9}
                              ids: ROW-MUTATION-READY, SYNC-MULTI-RESOLVER,
                                   TEMPLATE-OVERRIDE-CHANGED, X-RUNTIME-EVIDENCE
```

So **BLOCKED is 4 whether or not the overlay/manifest approval lands.** `<= 3` is not
recoverable by any re-sync. In every observed combination of the two gates the count is
≥ 4 (committed-inventory + manifest-current = 5; regenerated-inventory + manifest-stale = 4;
regenerated-inventory + manifest-current = 4).

**What actually changed** is the *visibility* of pre-existing debt, not the debt itself.
`backend/data/workpaper_writer_inventory.json` is regenerated in the working tree
(` M`, uncommitted — alongside ` M backend/data/workpaper_resolver_migration_matrix.json`).
That regeneration cleared the "inventory source digest is stale" `WriterGateError`, so
`writer_gate_facts.source_current` flipped `False → True` and the gate could finally render a
real verdict instead of `stale`. The debt was already recorded in the committed snapshot:

```
disk  writer_gate_facts.issue_counts.multi_resolver = 4   (source_current False -> masked as STALE)
fresh writer_gate_facts.issue_counts.multi_resolver = 3   (source_current True  -> BLOCKED)
```

Debt went **down** 4 → 3. Nothing regressed in the platform; a stale-masked blocker became
observable. The `<= 3` baseline was therefore authored while **both** terminal gates were
stale-masked — the baseline trio is `ROW-MUTATION-READY`, `TEMPLATE-OVERRIDE-CHANGED`,
`X-RUNTIME-EVIDENCE` (inferred: the counterfactual BLOCKED set minus `SYNC-MULTI-RESOLVER`).

## Since when

- `backend/data/workpaper_sync_program_milestones.json` — single commit `0bedc5e1a`
  ("feat(formula): publish F-SHELL milestone artifacts"); the committed snapshot has always
  recorded `BLOCKED: 5`, i.e. `<= 3` was already unreachable at HEAD.
- `backend/data/workpaper_writer_inventory.json` — last committed at `cd9592ff5`
  ("feat(d4-sync): D4 全量迁移至 useD4SyncMode + D4-13 补双向回写"), now **uncommitted-modified**.
  That uncommitted regeneration is what unmasked the blocker.
- `backend/tests/.../test_workpaper_sync_program_milestones.py` — last touched `0bedc5e1a`.

## Action taken

**None, deliberately.** Per the decision rule, a genuine blocker means: do not regenerate the
snapshot, do not bump the literals. `BLOCKED <= 3` stays at 3 — it is now a true red flag, and
relaxing it to 4 would absorb the very regression the direction-aware terminal buckets exist
to catch. The stale literals in the test (`completed:240/partial:15`, `internal_edge_count 448`,
core `state_counts`, the six `~` pins) are real drift from `ebc6e1b92`, but they cannot be
re-synced independently: they all read from the same `source["registry"]` fixture whose
BLOCKED count is 4.

## Unblocking requires one of

1. Drive `multi_resolver` to 0 (migrate the three `wp_onlyoffice_router` writers to a single
   canonical resolver), which returns BLOCKED to 3 and makes the whole cluster a clean re-sync.
2. Or an explicit reviewed decision to raise the BLOCKED ceiling to 4 **with** a recorded
   rationale naming `SYNC-MULTI-RESOLVER` / `writer_gate_multi_resolver_nonzero` — a governance
   call, not a test-maintenance edit.

## Measurement caveat

A stable before/after pytest count could not be taken: a concurrent agent is rewriting
`backend/data/workpaper_sync_entry_manifest.json`, so the generator's own
`_assert_inputs_unchanged` tripwire fires and the module aborts at fixture setup:

```
ProgramMilestoneError: inputs_changed_during_generation:
  ['backend/data/workpaper_sync_entry_manifest.json']
2 passed, 20 errors in 58.91s
```

`manifest_facts.source_current` still reads `False` (`reviewed_overlay_source_digest_stale`),
so the overlay approval has **not** landed yet. Since no file was changed, after == before by
construction; the previously reported "5 failed" shape should reappear once the manifest write
settles. The verdict above is independent of that gate — it was verified by the
manifest-green counterfactual.
