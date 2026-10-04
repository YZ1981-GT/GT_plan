# DB Readings Triage — pinned dated measurements vs live database

Scope: the 2 failures in `backend/tests/workpaper_sync/test_projection_lane_regression_gate.py`
that are pinned dated DB measurements disagreeing with the live database.

- `TestBindingConstraintComesFromThreeArmMeasurement::test_measured_block_agrees_with_the_real_database`
  (BP-61-1 `measured_2026_09_04` block in `check_task61_oo94_word_pilot_gate.py`)
- `TestRegisteredReadingsAgreeWithTheDatabase::test_latest_reading_matches_the_database`
  (`opaque_entry_gate.ENTRY_ID_NAMESPACE_SPLIT_NOTE["measured_migration_cost"]` append-only series)

Out of scope: the 4 capability-flip failures in the same file (pending governance decision).

Status: **DONE** — both in-scope failures now pass. 6 failed → 4 failed.

Measured 2026-09-23 (DB clock, UTC). All queries read-only; nothing was written to the DB.

---

## 1. Quiescence evidence

The prior triage declined to record a reading because concurrent subagents were running PG
suites. That precondition is now cleared. Four independent checks:

| Check | Result |
|---|---|
| `pg_stat_activity` on `audit_platform`, excluding self | 30 backends, **0 in state `active`** — all `idle` / `wait_event_type=Client` (uvicorn + Metabase pools) |
| Host processes | **no `pytest` process alive** (only `run_uvicorn.py` dev server and two sibling read-only `_probe_*.py` scripts) |
| Write-intent locks on the 4 tables (`pg_locks`, mode ≠ `AccessShareLock`, other pids) | **none** |
| Row recency (`created_at`) on the three content tables | last write **11:31:58Z**, i.e. `count(* ) WHERE created_at > now() - 30min` = **0** at 12:07Z |

One backend (pid 306117) was `idle in transaction` since 11:52 — its last statement was a
`SELECT` on `users`, and it held **no** lock on any of the four tables, so it cannot have
uncommitted writes pending against them.

**Stability confirmation.** Two fully independent readings from two separate processes /
connections, **112 seconds apart**, spanning the window in which the two sibling probe
scripts started, returned identical figures:

| Table | 12:07:39Z | 12:09:31Z (+ re-read in a fresh tx after 12s) |
|---|---|---|
| `working_paper_content_version` | 198 | 198 |
| `working_paper_content_representation` | 202 | 202 |
| `working_paper_content_application` | 69 | 69 |
| `working_paper_sync_entry_state` | 12 | 12 |

**Scratch schemas — debris, not live runs.** Six leftovers exist:
`tmp_fp_pg_c445b0386189`, `tmp_task24_ci_76c29f8c7519`, `tmp_task24_ci_84aa1bff226d`,
`tmp_task25_mc_ee1c15c00149`, `tmp_task26_oh_37607461dce0`, `tmp_task26_oh_87ac14f71eff`.
They are debris from harness runs that died before their `DROP SCHEMA`, **not** runs in
progress: no pytest process is alive, no backend is `active`, and no backend holds a lock on
the tables. They also live in their own namespaces, so they cannot affect `public`-schema
counts. Worth a separate cleanup; not a blocker here.

⇒ Quiesced. Readings recorded.

## 2. Measured figures — with the exact queries

Queries copied verbatim from the production/test code that does the comparison
(`_collect()` in `test_projection_lane_regression_gate.py`), so the registered reading and
the live reading are literally comparable:

```sql
SELECT COUNT(*) FROM working_paper_content_version;          -- 198
SELECT COUNT(*) FROM working_paper_content_representation;   -- 202
SELECT COUNT(*) FROM working_paper_content_application;      --  69
SELECT COUNT(*) FROM working_paper_sync_entry_state;         --  12
SELECT entry_id FROM working_paper_sync_entry_state ORDER BY entry_id;
```

`entry_state` namespace split, using `writer_migration.OPAQUE_ENTRY_PREFIX == "opaque-"`
(the same constant the assertion uses):

- total **12**
- `opaque-` namespace **1** (`opaque-017624e2-cd7e-4641-bd99-db7c1f1f5f7e`)
- manifest-backed **11** (b60 bundle, d1–d7, g7, h1 ×2)

Deltas against the pins: entry_state 2 → 12, content_version 2 → 198,
content_representation 2 → 202, content_application 0 → 69.

## 3. What was appended, and where

### 3a. `measured_migration_cost` — append-only series (as documented)

`backend/app/services/workpaper_sync/opaque_entry_gate.py`. Appended a third entry after
`task65` and `2026-09-04`, matching the existing entries' key names and ordering exactly:

```python
{
    "measured_at": "2026-09-23",
    "working_paper_content_version_rows": 198,
    "working_paper_content_representation_rows": 202,
    "working_paper_content_application_rows": 69,
    "working_paper_sync_entry_state_rows": 12,
    "note": "...",
}
```

No historical entry was edited or removed. The note records that
`working_paper_content_application` moving 0 → 69 also retires the "application table is
still 0" observation carried by the 2026-09-04 entry, and explicitly states that this entry
registers **row counts only** — whether the constraint is released is not adjudicated here.

### 3b. BP-61-1 — the snapshot is single-dated, so a series was added beside it

`backend/scripts/check/check_task61_oo94_word_pilot_gate.py`.

The block's key **is** its date (`measured_2026_09_04`), and it is the complete evidence for
that day's correction event — the proof that the earlier claim "全表 0 行" was false.
Overwriting its numbers in place would date today's reading as 2026-09-04 and destroy that
evidence, so **editing in place was rejected**. The schema did not force it: a series can be
added beside the snapshot, which is the convention already used for `measured_migration_cost`
in this same spec.

- `measured_2026_09_04` kept **byte-for-byte unchanged**.
- New `measured_readings` tuple: `2026-09-04` (2 / 1 / 1) then `2026-09-23` (12 / 1 / 11).
- `test_measured_block_agrees_with_the_real_database` now compares the **newest** dated
  reading instead of the hardcoded 2026-09-04 key. The assertion is unchanged in strength —
  still two-sided equality against the live DB on all three fields.
- Added `test_the_reading_series_preserves_the_2026_09_04_correction`, which pins two things:
  the first entry is still the `2026-09-04` / 2-row reading, and its three fields equal the
  `measured_2026_09_04` snapshot's, so the series cannot silently become a second source of
  truth that drifts from the snapshot.

**Deliberately not re-asserted.** The 2026-09-23 run also measured
`registered_adapter_ids = ['d2.receivable_detail', 'd4.revenue_detail',
'g7.soe_subsidiary_disclosure', 'h1.disposal_check']` (non-empty) and manifest
`bidirectional = 4` (was 0), plus `manifest_entry_count` 186 → 176. That contradicts
BP-61-1's `why_still_binding` premise and is the capability flip owned by the pending
governance decision, so the new entry records **row counts only** and says so. Announcing the
constraint released is not this task's call.

### 3c. Regenerated projection

`backend/data/workpaper_task61_word_pilot_gate_probes.json` is a byte-exact canonical
projection of the gate's declarations, guarded by
`test_task61_oo94_word_pilot_gate.py::test_generated_registry_data_file_is_fresh`. Editing
`BINDING_CONSTRAINTS` necessarily drifts it, so it was regenerated with
`generate_workpaper_task61_word_pilot_probe_registry.py --apply`; `--check` then passes.
`git diff --numstat` = **+17 / −1**, and probe counts are unchanged
(`probes=41 per_entry=34 scenario=26 gate=7 rows=75`) — no denominator shrank. The generator
contains no per-run results and does not touch the DB, so regenerating it does not bake the
capability-flip state into the artifact.

## 4. Invariants

- `measured_migration_cost`: still a tuple, now 3 entries (`_latest()` needs ≥ 2). ✅
- `test_the_series_preserves_the_task65_zero_reading` — the historical `0` reading survives. ✅
- `test_cost_did_not_silently_go_back_to_zero` — latest is non-zero. ✅
- `measured_2026_09_04` unchanged, and `test_bp_61_1_measured_reading_is_not_the_stale_literal`
  still green off it. ✅
- `test_other_binding_constraints_are_untouched` — no other constraint gained a measured
  block. ✅
- No assertion weakened; no skip/xfail added; one guard test added.

## 5. Before / after

`backend/tests/workpaper_sync/test_projection_lane_regression_gate.py`

| | before | after |
|---|---|---|
| failed | 6 | **4** |
| passed | 35 | 38 |

Fixed (both in scope):

- `TestBindingConstraintComesFromThreeArmMeasurement::test_measured_block_agrees_with_the_real_database`
- `TestRegisteredReadingsAgreeWithTheDatabase::test_latest_reading_matches_the_database`

Still failing — all 4 are the untouched capability-flip cluster owned by the pending
governance decision, failing with the same assertions as before:

- `TestSupplyGateAdmitsAndRegistersAfterFirstPublication::test_other_pilots_are_still_rejected_so_the_denominator_is_not_trivial`
- `TestSupplyGateAdmitsAndRegistersAfterFirstPublication::test_stage_two_is_correctly_still_blocked_by_the_disk_manifest`
- `TestSupplyGateAdmitsAndRegistersAfterFirstPublication::test_production_manifest_registers_nothing_for_g7`
- `TestBindingConstraintComesFromThreeArmMeasurement::test_default_call_reports_bp_61_1`

`backend/tests/workpaper_sync/test_task61_oo94_word_pilot_gate.py` (run because it guards the
edited gate): 3 failed / 157 passed → **2 failed / 158 passed**.
`test_generated_registry_data_file_is_fresh` is green after the regeneration; the remaining 2
(`test_no_f2_entry_is_admitted_today`, `test_the_three_arms_really_run_against_the_database`)
are the same pre-existing capability-flip cluster and were already failing before this change.
