# Multi-resolver writers — triage

**Verdict: NOT tractable, and the proposed fix would not move the number it was commissioned to move.**
No production code changed. No test changed.

Two independent reasons, both measured:

1. The three writers route through a **resolution pipeline**, not three competing authorities.
   Collapsing them is blocked by characterization tests that positively require the current shape.
2. Even at `multi_resolver == 0`, `milestone_state_counts["BLOCKED"]` stays **6** — because
   `SYNC-MULTI-RESOLVER` is *independently* blocked by `producer-tasks`, and 5 other milestones
   are blocked by the same predicate. `BLOCKED <= 3` is unreachable via this work.

---

## 1. The `multi_resolver` criterion, verbatim

`backend/scripts/gen/generate_workpaper_writer_inventory.py` L1309:

```python
"multi_resolver": len(resolvers) > 1,
```

where `resolvers = _resolver_identities(facts)` (L1025–1029):

```python
def _resolver_identities(facts: dict[str, Any]) -> list[str]:
    identities = list(facts["resolver_calls"])
    if facts["ad_hoc_paths"]:
        identities.append("<ad_hoc_path_construction>")
    return sorted(set(identities))
```

`resolver_calls` is populated per-function by AST walk when a **directly called leaf symbol** is in
`_RESOLVER_SYMBOLS` (L78–92):

```python
_RESOLVER_SYMBOLS: frozenset[str] = frozenset({
    "resolve_wp_file", "find_template_file_any", "find_template_file",
    "_resolve_wp_file", "_resolve_custom_wp_file", "_resolve_docx_template",
    "_resolve_template_path", "_onlyoffice_storage_dir", "_onlyoffice_dir",
})
_CANONICAL_RESOLVER = "resolve_wp_file"
```

Gate side, `backend/scripts/check/check_workpaper_writer_revision_gate.py` L225–226:

```python
if verdicts.get("multi_resolver"):
    issues["multi_resolver"].append(writer_id)
```

**So the criterion counts how many distinct resolver symbols a function calls *in its own body*.**
It does not model whether those symbols are alternatives or composed stages. That distinction is
what decides this case.

## 2. Per-writer resolver inventory (read from `backend/data/workpaper_writer_inventory.json`)

`canonical_resolver: "resolve_wp_file"`; `stats.multi_resolver_count: 3`.

| writer | kind | `resolver_identities` | `canonical_resolver` |
|---|---|---|---|
| `wp_onlyoffice_router::get_sheet_onlyoffice_config` | `resolver` | `_resolve_custom_wp_file`, `_resolve_wp_file`, `find_template_file_any` | `None` |
| `wp_onlyoffice_router::get_sheet_wopi_contents` | `resolver` | `_resolve_custom_wp_file`, `_resolve_wp_file`, `find_template_file_any` | `None` |
| `wp_onlyoffice_router::post_sheet_onlyoffice_callback` | `writer_resolver` | `_onlyoffice_storage_dir`, `_resolve_custom_wp_file` | `None` |

Call sites (AST-measured, `backend/app/routers/wp_onlyoffice_router.py`):

```
get_sheet_onlyoffice_config     (L649-857)
   L695   _candidate_tpl = find_template_file_any(_candidate)
   L705   else find_template_file_any(_sheet_wp_code)
   L708   _custom_file = _resolve_custom_wp_file(wp, _sheet_wp_code)
   L713   file_path = _resolve_wp_file(
get_sheet_wopi_contents         (L949-1027)
   L984   if find_template_file_any(_candidate):
   L1001  else find_template_file_any(_sheet_wp_code)
   L1004  _custom_file = _resolve_custom_wp_file(wp, _sheet_wp_code)
   L1009  file_path = _resolve_wp_file(
post_sheet_onlyoffice_callback  (L1177-1629)
   L1344  _oo_dir = _onlyoffice_storage_dir(project_id)
   L1354  _custom_target = _resolve_custom_wp_file(wp, _save_wp_code or wp_code)
```

### What each resolver actually does

Read from source, not inferred:

- **`find_template_file_any(wp_code)`** — resolves the **template** file for a wp_code.
- **`_resolve_wp_file(project_id, wp_code, template_path, ...)`** (L221) — resolves the **OO working
  copy** under the project's OO cache dir, *seeded by `shutil.copy2(template_path, target)` on first
  use*. It takes `template_path` **as a parameter**.
- **`_onlyoffice_storage_dir(project_id)`** (L129) — returns the project OO **directory**; delegates
  to `canonical_paths.onlyoffice_canonical_dir`. It is a directory helper, not a file resolver.
  `_resolve_wp_file` itself calls it (L~236).
- **`_resolve_custom_wp_file(wp, wp_code)`** (L168) — for **custom** workpapers only; returns the
  **business file itself** (`wp.file_path`), deliberately *not* a cache copy. Returns `None` for
  everything else.

So the shape is a **pipeline plus one short-circuit**, not three rival authorities:

```
find_template_file_any ──► _resolve_wp_file ──► OO working copy
                            (└ _onlyoffice_storage_dir)
_resolve_custom_wp_file ──► business file (custom only; no template exists)
```

`find_template_file_any` is `_resolve_wp_file`'s **input**. `_onlyoffice_storage_dir` is its
**callee**. The gate counts composition depth as if it were multiplicity.

The custom branch is not a stylistic duplicate either — its docstring records a browser-measured
regression: custom workpapers have **no template at all**, so `find_template_file_any` returns
`None`, both of `_resolve_wp_file`'s sources miss, and the config endpoint 404s ("在线编辑" never
opens). And a cache copy would be wrong even if it existed, because `refresh_custom_projection`
reads `wp.file_path` — two xlsx would diverge, breaking the "xlsx is sole authority" invariant.

## 3. The canonical target cannot serve these endpoints today

`CanonicalResolutionService` (`app/services/workpaper_sync/resolution.py`) is the designated single
entry point ("十个意图共用的唯一解析入口"). Its `resolve()` is documented **read-only** ("只读，不写任何行")
and requires, in order: a non-candidate `representation_id` or a **current entry pointer**, an
approved `definition_bundle` with four typed slots, and a published artifact whose `sha256` matches
the representation row. No representation ⇒ `RepresentationNotFoundError`.

It structurally cannot do what `_resolve_wp_file` does, because seeding a working copy from a
template **is a write**.

`word_resolution.py` states the division of labour outright: `CanonicalResolutionService` handles the
already-published representation domain and requires the entry to have been `finalize`d;
`WordCanonicalResolver.resolve` exists precisely to answer "which file" when there is **no published
representation yet**.

Measured supply (live PG + manifest):

| quantity | measured |
|---|---|
| manifest entries (`workpaper_sync_entry_manifest.json`) | **155** |
| distinct entries with any representation row | **11** |
| `working_paper_sync_entry_state` rows with a current pointer | **12** (11 distinct entries) |

⇒ **144 of 155 entries have no published representation.** These three endpoints serve *all* xlsx
workpapers on the live editing path. Switching them to the canonical service would leave the large
majority with no resolvable substrate. (Prior doc §15.8 claimed 3/186; the population has moved, the
structural conclusion is unchanged.)

## 4. Restructuring cannot clear it either — the tests forbid it

Extracting one helper that internally calls all three symbols would (a) not reach zero — it relocates
3 rows into 1 row that still has 3 identities — and (b) red these existing tests, which assert the
multi-resolver shape **positively, inside these function bodies**:

- `backend/tests/test_custom_workpaper_oo_file_resolution.py` — requires `_resolve_custom_wp_file(`
  to appear in the body of all three functions, citing the measured 404 / blank-editor regressions.
- `backend/tests/test_whole_excel_tab_document_identity.py` — requires
  `_whole_workbook_template_or_primary` and `_whole_cache_stem` in config/wopi bodies, and
  `_save_stem`/`target` in the callback.
- `backend/tests/test_task58_word_canonical_resolver.py` — requires `word_canonical_write_target`
  among the callback's called names.
- `backend/tests/test_workpaper_writer_inventory.py` L1230 — `len(issues_real["multi_resolver"]) == 3`,
  all rows in `wp_onlyoffice_router`.
- `backend/tests/workpaper_sync_chaos/test_task71_chaos_gate.py` L1351 — `gate.MULTI_RESOLVER_ROWS`
  must name these three plus `get_whole_excel_grid`.
- `backend/tests/workpaper_sync/test_task20_writer_gate.py` — derives the row names from `tasks.md`
  prose, which is out of scope for this task.

`test_task30_closure_gate.py` is **green today (10 passed)** with `multi_resolver == 3`, because its
criterion is the double-conditional "either cleared, or its blocker is registered in the Task 12
matrix". The nonzero state is the project's registered, adjudicated position — not an unnoticed
regression.

## 5. The decisive measurement: clearing the gate would not change `BLOCKED`

Freshly derived from `generate_workpaper_sync_program_milestones.build_program_registry()`:

```
milestone_state_counts: {BLOCKED: 6, IMPLEMENTED: 3, REQUEST_PATH_VERIFIED: 0,
                         ONLYOFFICE_VERIFIED: 0, CLOSED: 0, STALE: 7}   (total 16)
task_state_counts:      {completed: 246, partial: 9, blocked: 7, pending: 1}
```

**BLOCKED is 6, not 4.** The six, with their blockers:

| milestone | blockers |
|---|---|
| `PUBLISHED-ENTRY-READY` | `producer-tasks` **blocked** `producer_tasks_incomplete`; `published-entry.render-materialize-extract-evidence` unverifiable |
| `ROW-MUTATION-READY` | `producer-tasks` **blocked** `producer_tasks_incomplete` |
| `SYNC-ENTRY-NAMESPACE` | `producer-tasks` **blocked** `producer_tasks_incomplete`; `entry-namespace.request-path-evidence` unverifiable |
| `SYNC-MULTI-RESOLVER` | `producer-tasks` **blocked** `producer_tasks_incomplete`; `multi-resolver.writer-gate-zero` **blocked** `writer_gate_multi_resolver_nonzero` |
| `TEMPLATE-OVERRIDE-CHANGED` | `producer-tasks` **blocked** `producer_tasks_missing`; `template-override-changed.producer-contract` **blocked** |
| `X-RUNTIME-EVIDENCE` | `producer-tasks` **blocked** `producer_tasks_incomplete`; `x-runtime-evidence.bundle` **blocked** |

State derivation, generator L2395–2397:

```python
if "stale" in results:
    return "STALE"
if "fail" in results or "blocked" in results:
    return "BLOCKED"
```

Any single `blocked` predicate forces BLOCKED. `SYNC-MULTI-RESOLVER` carries
`producer-tasks: blocked` **independently** of the writer gate.

### Executed counterfactual — the decisive result

Not inferred. The `multi-resolver.writer-gate-zero` predicate was flipped to `pass` (identified by
`reason_code == "writer_gate_multi_resolver_nonzero"`) and the milestone states were replayed through
the generator's **own** `derive_milestone_state`:

```
ACTUAL          BLOCKED=6  {'BLOCKED': 6, 'IMPLEMENTED': 3, 'STALE': 7}
  FLIPPED one predicate on SYNC-MULTI-RESOLVER
  SYNC-MULTI-RESOLVER actual=BLOCKED counterfactual=BLOCKED
    blocked / producer_tasks_incomplete      <-- survives
    pass    / None                           <-- was writer_gate_multi_resolver_nonzero
    pass    / None
COUNTERFACTUAL  BLOCKED=6  {'BLOCKED': 6, 'IMPLEMENTED': 3, 'STALE': 7}
```

⇒ **Driving `multi_resolver` to 0 takes BLOCKED from 6 to 6.** `SYNC-MULTI-RESOLVER` does not even
leave BLOCKED, let alone move the count. The handover's causal claim — that it "returns BLOCKED to 3
and makes the whole milestones cluster a clean re-sync" — is refuted by the generator's own state
function. `producer-tasks` is blocked by `-`/pending markers in `tasks.md`, which is out of scope here
(and correctly so: those markers denote genuinely incomplete work).

### Reconciliation with `milestone-blocked-regression.md` (prior agent, BLOCKED=4)

That triage measured `fresh BLOCKED = 4 {BLOCKED 4, IMPLEMENTED 3, STALE 9}` with
`PUBLISHED-ENTRY-READY` and `SYNC-ENTRY-NAMESPACE` suppressed to STALE by a
`*.manifest-integrity` stale predicate (`reviewed_overlay_source_digest_stale`). I measure
`BLOCKED 6 / STALE 7` — the same 4 plus those two, un-suppressed.

Both readings are correct for their moment: `backend/data/workpaper_sync_entry_manifest.json` and
`workpaper_sync_entry_overlay.json` are both ` M` in the working tree and owned by other agents, so
the manifest gate flipped back to current between the two measurements, removing the stale mask. The
working tree is moving underneath this measurement; the counts are timestamped, not stable.

This **strengthens** the shared conclusion rather than weakening it. Across every observed
combination of the two gates the count is ≥ 4 (committed-inventory + manifest-current = 5;
regenerated-inventory + manifest-stale = 4; regenerated-inventory + manifest-current = 6), so
`<= 3` is unreachable by any re-sync. The new result here is narrower and sharper: the count is
unreachable *even by completing the multi-resolver work*, because `SYNC-MULTI-RESOLVER` has a second,
independent blocker.

### Corollary: the test-literal re-sync is legitimate but insufficient, so it was not done

On-disk committed projection vs freshly derived:

| | on-disk `workpaper_sync_program_milestones.json` | fresh |
|---|---|---|
| `milestone_state_counts` | BLOCKED **5**, STALE **8**, IMPLEMENTED 3 | BLOCKED **6**, STALE **7**, IMPLEMENTED 3 |
| BLOCKED ids | `PUBLISHED-ENTRY-READY`, `ROW-MUTATION-READY`, `SYNC-ENTRY-NAMESPACE`, `TEMPLATE-OVERRIDE-CHANGED`, `X-RUNTIME-EVIDENCE` | same **+ `SYNC-MULTI-RESOLVER`** |
| `task_state_counts` | `{246, 9, 7, 1}` | `{246, 9, 7, 1}` (identical) |

The whole on-disk↔fresh delta is one milestone: `SYNC-MULTI-RESOLVER` moved STALE → BLOCKED. That is
why `test_generated_projection_is_current_and_self_digest_bound` (`on_disk == registry`, L62) reds.

The task-state literals in the **test file** (`{completed: 240, partial: 15, ...}`, L256–266 / L410–414)
are stale; the committed projection already carries the fresh `{246, 9, 7, 1}`. That part is a genuine
clean re-sync (6 tasks `~`→`x`, total conserved at 263).

But `test_g0_3_does_not_promote_tasks_milestones_or_g0_4` currently dies at **L408** on those task-state
literals, *before* reaching `assert counts["BLOCKED"] <= 3` at **L432**. Re-syncing L408 alone would
simply unmask `BLOCKED 6 > 3` — converting one red assertion into a different red assertion. Since
`BLOCKED <= 3` must not be relaxed, the re-sync was **not** performed: it cannot make the test pass,
and applying it would obscure the real finding. Note that even the *committed* projection (BLOCKED 5)
violates `<= 3`, so the `3` literal predates two further milestones going BLOCKED — a separate,
genuine regression that this task's premise did not account for.

## 6. Measured before / after

| quantity | before | after |
|---|---|---|
| `stats.multi_resolver_count` | 3 | 3 (unchanged — no production change) |
| `milestone_state_counts["BLOCKED"]` (fresh) | 6 | 6 |
| `test_task30_closure_gate.py` | 10 passed | 10 passed |
| `test_workpaper_sync_program_milestones.py` | 5 failed / 17 passed | 5 failed / 17 passed |

The 5 failures (`--tb=line`):

```
L62   test_generated_projection_is_current_and_self_digest_bound   on_disk != registry
L251  test_eight_spec_task_and_dependency_denominators_are_exact   {'1':'x',...} == {'1':'~',...}
L323  test_g0_3_archive_dependency_is_closed_...                   assert 447 == 448
L359  test_g0_3_wave_order_is_valid_...                            wave-order list mismatch
L408  test_g0_3_does_not_promote_tasks_milestones_or_g0_4          task_state_counts literal
```

## 7. What the real migration entails

To legitimately reach `multi_resolver == 0` on these three rows:

1. Give the remaining **144** manifest entries a published representation — approved definition
   bundle (4 typed slots), published artifact with matching `sha256`, current entry pointer. This is
   the per-entry migration the closure spec tracks across its Task 46–57 / 61–64 range.
2. Bring custom workpapers into the representation model, so the `_resolve_custom_wp_file`
   short-circuit is subsumed rather than deleted. Until then, deleting it reintroduces the measured
   404 / blank-editor regressions.
3. Provide a *write* path for first materialization (today `resolve()` is read-only, so the
   template→working-copy seed has no canonical home), or make materialization an explicit
   precondition of the config/WOPI intents.
4. Re-point the three endpoints at `CanonicalResolutionService.resolve(intent=...)`, then update the
   AST-shape characterization tests in §4 **together with** the behavioural evidence that replaces
   them — they are the only thing currently pinning the 404 regressions shut.
5. Withdraw the Task 12 matrix deferral registrations; `test_task30_closure_gate.py` asserts that a
   zero gate must leave **no** deferral rows behind.

The 5 milestones failures remain blocked on that work — and, per §5, **also** on `producer-tasks`,
which no amount of resolver work clears.

---

## Confirmed / corrected against the handover

| handover claim | measured |
|---|---|
| `multi_resolver` non-zero, 3 rows, all in `wp_onlyoffice_router` | ✅ confirmed |
| `SYNC-MULTI-RESOLVER` BLOCKED via `multi-resolver.writer-gate-zero` / `writer_gate_multi_resolver_nonzero` | ✅ confirmed |
| `BLOCKED` measures **4** | ❌ measures **6** at this timestamp (the 4 + two un-suppressed by the manifest gate flipping current; see reconciliation in §5) |
| clearing `multi_resolver` returns BLOCKED to 3 | ❌ executed counterfactual: stays at **6**, and `SYNC-MULTI-RESOLVER` stays BLOCKED on `producer_tasks_incomplete` |
| the 5 failures are all downstream of `multi_resolver` | ❌ none of the 5 is the `BLOCKED` assertion; that assertion (L432) is never reached |
| stale test literals are a legitimate clean re-sync | ⚠️ partly — the task-state literals are stale, but re-syncing them only unmasks `BLOCKED 6 > 3` |
| debt went 4 → 3 on regeneration | ✅ consistent with `test_workpaper_writer_inventory.py` L1226–1230 (`get_whole_excel_grid` converged to one identity) |
