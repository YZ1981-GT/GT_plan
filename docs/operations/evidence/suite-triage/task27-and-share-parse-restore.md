# Suite triage: task27 conflict resolution + share_parse wiring restore

- Branch: `work/2026-09-14-d4-dual-mode-p0-fixes`
- HEAD at session start: `fb7a0ace2`
- Scope: (1) restore `share_parse=True` in `published_identity_observer.py` `collect_workbook_structure` path;
  (2) fix `backend/tests/workpaper_sync/test_task27_conflict_resolution_pg.py` (24 failures, 1 root cause).

## Status

- [x] Part 1 prerequisite check (pure-read `extract_transposed_workbook` still present?) — **YES, intact**
- [x] Part 1 restore + judgement re-run — **restored, 2 failed → 0 failed**
- [x] Part 2 root cause — **harness never migrated to BP-30** (same family as task26)
- [x] Part 2 fix + before/after — **24 failed / 32 passed → 56 passed**

---

## Part 1 — `share_parse` wiring restore

### Prerequisite check (must pass before flipping to True)

Task 8 established sharing is only safe because `extract_transposed_workbook` is a **pure read**.
Verified still true on HEAD:

| Prerequisite | Location | State |
|---|---|---|
| `_AbsentCell` read-only stand-in | `phase5_transposed_sheet.py:338` | present |
| `_cell_ro()` non-lazy read (`ws._cells.get(...)`) | `phase5_transposed_sheet.py:360` | present |
| `extract_transposed_workbook` reads **every** cell via `_cell_ro` | `:545`, `:552`, `:553`, `:561`, `:571` | no `ws.cell(` left on the read path |
| `resolve_managed_sheet(share_parse=...)` branch → `shared_workbook_from_bytes` | `:365`, `:394-399` | present |
| `shared_workbook_from_bytes` scope cache + "caller must not mutate" contract | `excel_extract.py:3183` | present |
| `materialize_transposed_workbook` still takes a **private** copy (`load_workbook`) | — | unchanged, still default `share_parse=False` |

⇒ Prerequisite was **not** reverted. Flipping to `True` does not change `structure_hash`.

### The change

`published_identity_observer.py:1456-1457` — comment said `True`, code said `False`
(leftover from a prior A/B experiment, committed):

```python
_, ws = _transposed_resolve(data, spec=spec, share_parse=True)   # was False
_transposed_extract(data, spec=spec, share_parse=True)           # was False
```

### Judgements — before / after

Command (`cwd=backend`):
```
rtk ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_single_pass_parse_reuse.py \
    tests/workpaper_sync/test_single_pass_verify_not_relaxed.py -q --tb=line -rf -p no:randomly
```

| | parse_reuse | verify_not_relaxed | total |
|---|---|---|---|
| **before** | 14 passed / **2 failed** | 25 passed | 2 failed, 39 passed (118s) |
| **after** | **16 passed** | 25 passed | **41 passed** (100s) |

The 2 before-failures were exactly the requirement-2.1 guards, and they named the reverted call sites:

- `test_cpu_segment_parses_the_artifact_bytes_once_per_view`
  → `有消费方没开 share_parse ⇒ 它自己又解析了一遍产物：[d4-29-managed private parse ×2, d4-12-managed private parse ×2]`
- `test_segment_load_workbook_total_drops_by_the_shared_parses`
  → `复用后整段 load_workbook 16 ≠ 实测 12；调用点：{... 'phase5_transposed_sheet.py:399 resolve_managed_sheet': 8, 'shared_workbook_from_bytes': 1 ...}`

i.e. 4 extra private parses (2 specs × resolve+extract), exactly the 2 flipped lines.
`verify_not_relaxed` (25 judgements, comparison surface unchanged by parse sharing) was green
before **and** after ⇒ restoring reuse did not relax the comparison surface.

---

## Part 2 — `test_task27_conflict_resolution_pg.py`: 24 failures, one root cause

### Root cause: the harness never migrated to BP-30 (test-side, not production)

Exactly the task26 family. `post_durable` runs
`published_identity_observer.collect_workbook_structure`, which reads the **frozen
instrumentation definition payload** and uses its four anchors to measure the managed
structure out of the xlsx bytes about to be published. The task27 harness gave it
neither a readable carrier nor a same-sourced digest:

| # | Defect | Where (pre-fix) |
|---|---|---|
| 1 | Carrier was an empty `<root/>` `xl/workbook.xml` shell — openpyxl can read no Table / hidden uuid column / veryHidden metadata sheet ⇒ reverse-read empty ⇒ raise | `_ooxml()` |
| 2 | instrumentation blob was the placeholder `{"k":"instr"}` | `_def_payload`-less `blobs` dict |
| 3 | instr definition row froze a **fabricated** digest `_d("task27-instrumentation")` | `create_definition_artifact(kind="instrumentation", ...)` |
| 4 | contract froze the **same fabricated** literal, so all three legs of the three-way lock were independently made up instead of same-sourced | `_contract_payload()["instrumentation_definition_sha256"]` |

⇒ `FrozenChildUnusableError` → `published_identity_frozen_child_unusable @ post_durable`
→ `assert_resolve_apply_landed` (`conflict_resolution.py:579`, called from `:1169`) raises
`ResolveApplyFailedError`. The `resolve_ok` and `resolve_via_duplicate` collection phases
die whole; `rollback` then dies downstream with `ContentVersionNotFoundError: content
version None` because no new content version was ever published.

Failure arithmetic (24): 16 `KeyError` on the 3 missing scenario keys + 2 harness
judgements (`test_no_phase_crashed_during_collection`,
`test_every_scenario_was_collected`) + 6 direct assertions.

**Confirmed NOT caused by Part 1**: the 24-failure BEFORE baseline below was measured
*after* `share_parse=True` was restored — identical failure set. Matches the prior A/B
(flipping to `False` reproduced it identically).

### Ruled out

- **`mkdtemp("tmp_task27_store_")` store isolation** — not the cause. It is deliberate
  (`test_scratch_isolation` asserts `"tmp_task27_store_" in snap["base_root"]`) and the
  same pattern is green in task25/task26. All artifacts are published *into* that root by
  the harness, so production resolution never roots at `backend/`. Untouched.
- **Stale pinned evidence** — none involved; no manifest / `source_commit` / content hash
  was hand-edited. The digests were fabricated literals, now derived from the payload.

### Fixes (all test-side except the Part 1 restore)

1. **`_ooxml()` builds on the real instrumented fixture** — `workbook_fixture(sheet_key="d2-detail")`
   from `tests/workpaper_sync/g1_structure_fixture.py` (the shared fixture task26 uses),
   with the managed parts still appended as zip entries ⇒ the existing
   "real write / real read roundtrip", "unmanaged region comparison" and
   "same content ⇒ same bytes" judgements are unchanged.
2. **`_instrumentation_payload()` + `_instrumentation_digest()`** — the digest is now
   same-sourced in all three places (blob bytes via `D.canonical_json_bytes`, instr
   definition row `sha256`, contract `instrumentation_definition_sha256`), so the
   three-way lock locks onto something real instead of three independent literals.
3. **Unmanaged synthetic part moved `xl/unmanaged.xml` → `_gt_sync/unmanaged.xml`**
   (constant `_UNMANAGED_PART`, both the writer and the `verify_unmanaged_regions`
   reader). The fixture ships a real `[Content_Types].xml` that does not declare it;
   leaving it under `xl/` would bet on openpyxl's tolerance for undeclared parts.
4. **`_JsonCarrierAdapter.verify_unmanaged_regions` now accepts the 4 shift-aware
   kwargs** (`row_shift`, `total_formula_rows`, `propagation`, `per_table_shift`) that
   `adapters/base.py:608` declares — same alignment as the task15 fix. The orchestrator
   passes them unconditionally, so a `before/after/contract`-only stub `TypeError`s on the
   first real commit. JSON carriers do not shift, so they are accepted and ignored.
5. **Fixture zip entries are re-stamped to `_ZIP_EPOCH` instead of copied verbatim.**
   Found by a real guard rather than guessed: after fixes 1-4 the file went 24 → **1**
   failure, and the survivor was `test_the_carrier_payload_is_byte_deterministic`
   (`openpyxl.wb.save()` stamps `time.localtime()` into entry headers). That judgement is
   correct and load-bearing — `resolve_via_duplicate` needs the second same-payload
   delivery to hit one application key, and `rollback` needs the re-materialized
   representation to be byte-identical to history to reach `register_artifact`'s
   content-addressed idempotent branch. Re-stamping touches only container entry headers,
   no part bytes, and makes the carrier deterministic **across** processes (strictly
   stronger than before). No assertion weakened, no skip/xfail added.

### Before / after

Command (`cwd=backend`, `share_parse=True` already restored in both runs):
```
..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task27_conflict_resolution_pg.py -q --tb=line -rf -p no:randomly
```

| | result |
|---|---|
| **before** | `24 failed, 32 passed, 1 warning in 22.44s` |
| after fixes 1-4 | `1 failed, 55 passed, 1 warning in 23.02s` (survivor = byte-determinism guard) |
| **after** | `56 passed, 1 warning in 23.89s` |

Neighbour regression for the Part 1 production change (same observer path):
```
rtk ... -m pytest tests/workpaper_sync/test_task26_oo_to_html_pg.py \
                 tests/workpaper_sync/test_task25_materialize_coordinator_pg.py -q ...
→ 152 passed, 1 warning in 39.96s
```

### Deliberately left

**`_assert_apply_landed` observability (`conflict_resolution.py:579`) — NOT done.** It
propagates only `error_code` + `stage` and drops the observer's `as_dict()` message /
context, which is why 24 tests went red saying nothing. Assessed and skipped, because:

- The outcome dataclass returned by `apply_durable_incoming` carries **no** message
  field. The detail does exist but only as `op.error_detail` persisted on the operation
  row (`materialize_coordinator.py:2224`) ⇒ the information is **not lost**, it is just
  not on the exception. That materially weakens the case.
- Threading it would mean a field on the apply-outcome dataclass, capture in the
  error-recording path, and a **signature change to `assert_resolve_apply_landed`** — a
  deliberately module-level, mutation-tested pure function with its own Task 14
  judgements. 3 modules, production, with its own test surface.

Not required by any red judgement. Recommended as a separate scoped change; a cheap first
step is a `logger.error` at `conflict_resolution.py:579` carrying `op.error_detail`.

`mkdtemp` store isolation left as-is (a judgement asserts it). No production file other
than the Part 1 two-line restore was modified.
