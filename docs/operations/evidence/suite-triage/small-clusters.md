# Suite triage — small clusters (workpaper_sync)

Status: IN PROGRESS (stub written first, appended as work proceeds)

Scope: 8 files, 25 failures measured in a deterministic 93-file combined run
(this suite has no `pytest-randomly`, so ordering is stable).

| file | reported failures | reproduced | root cause | action |
|---|---|---|---|---|
| `test_d2_sync_retirement.py` | 8 | pending | | |
| `test_projection_lane_regression_gate.py` | 6 | pending | | |
| `test_excel_typography_rows.py` | 3 | pending | | |
| `test_d2_store_value_equivalence.py` | 3 | pending | | |
| `test_task12_canonical_resolver.py` | 2 | pending | | |
| `test_excel_row_insertion_readiness.py` | 1 | pending | | |
| `test_downstream_base_reliability_gate.py` | 1 | pending | | |
| `test_excel_shift_aware_verification.py` | 1 | pending | | |

Run command (cwd=`backend`):

```
..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/<file> -q --tb=short -rf -p no:randomly
```

---

## Findings

(appended below as each file is triaged)
### Reproduction (baseline, individual runs, `-p no:randomly`)

All 25 reproduce exactly as reported. Two commands:

```
tests/workpaper_sync/test_excel_shift_aware_verification.py + test_task12_canonical_resolver.py
  + test_excel_row_insertion_readiness.py + test_downstream_base_reliability_gate.py
  → 5 failed, 210 passed, 2 xfailed

tests/workpaper_sync/test_d2_sync_retirement.py + test_projection_lane_regression_gate.py
  + test_excel_typography_rows.py + test_d2_store_value_equivalence.py
  → 20 failed, 82 passed
```

---

## 1. `test_excel_shift_aware_verification.py` — 1 → 0 ✅ (test fix: stale second count pin)

**Root cause.** `ROW_BEARING_STRUCTURES` has 16 entries; this test hardcoded `== 15`.

The 16th entry is `("sqref", "text-a1-ranges")` — the `<xm:sqref>` child of
`<x14:dataValidation>` (Excel 2010+ extension), whose content is A1 range text
(D2-2 template measured at `AN65539:AN65553`). It is a **legitimate, already-landed
bug fix**, not a stray addition:

- registered in `excel_row_shift.ROW_BEARING_STRUCTURES` with an explanatory comment;
- handled — `_handled("sqref", "text-a1-ranges")` + `_shift_element_text` regex widened
  to tolerate namespace prefixes (`(?:\w+:)?`);
- `backend/scripts/file_size_whitelist.txt` records the three-site landing as one fix;
- **`test_excel_row_shift.py:247` already asserts `== 16` and passes** — so 16 is the
  agreed number and this file held the stale second pin.

Also recorded as pre-existing in
`.kiro/specs/multi-sheet-materialize-defined-name-shift-normalization/tasks.md:64`
("ROW_BEARING_STRUCTURES 16vs15").

**Fix.** `tests/workpaper_sync/test_excel_shift_aware_verification.py`: `15` → `16`, and the
`text_tags` bucket expectation `{formula, formula1, formula2}` → `+ sqref` (the derivation
already buckets it there). Both remain **exact equality** assertions — nothing relaxed,
nothing skipped. Comment added explaining what the 16th is and where the other pin lives.

**Verification** (`test_excel_shift_aware_verification.py` + `test_excel_row_shift.py` together,
to prove the 16-pin file stays green):

```
117 passed, 1 warning in 8.84s
```

---

## 2. `test_excel_typography_rows.py` — 3 → 0 ✅ (production constant: denominator correction)

**Not what the counts suggest.** The failures read `assert 842 == 879` etc., i.e. the *live
scan* (842/170/37) is **lower** than the registered constant (879/182/39). The library did not
grow; the registered census was measured against a **different population** than the scanner
that shipped with it.

**Root cause — the constant was born inconsistent with its own scanner.**

`check_managed_region_typography_rows.scan()` walks `backend/wp_templates/_index.json`
(**349** xlsx / 2602 sheets). The constant registers `xlsx_scanned=351 / sheets_scanned=2722`,
which is a **disk walk**. Git timeline:

| date | event |
|---|---|
| 2026-05-15 | `_index.json` last generated (349 xlsx) — unchanged since |
| 2026-07-16 | `F/F2存货.xlsx` + `D/D4收入底稿.xlsx` added to disk, **never indexed** |
| 2026-09-05 | census measured → 351 xlsx / 2722 sheets |
| 2026-09-06 | `eed3a34ff` lands the constant **and** the index-based `scan()` in one commit |
| 2026-09-14 | `D/D4 收入底稿.xlsx` (space variant) added — after measurement |

Disk today holds 352 xlsx; index holds 349; the three unindexed files are
`D/D4 收入底稿.xlsx`, `D/D4收入底稿.xlsx`, `F/F2存货.xlsx`. All three are git-tracked and
`git status backend/wp_templates` is clean.

**Per-file reconciliation** (measured with the scan script's own predicates):

| workbook | sheets | narrow cells | rows before footer |
|---|---|---|---|
| `F/F2存货.xlsx` | 74 | 23 | 11 |
| `D/D4收入底稿.xlsx` | 46 | 14 | 1 |

All five registered numbers close exactly: `349+2=351`, `2602+74+46=2722`,
`842+23+14=879`, `170+11+1=182`, `37+2=39`. So the registered reading = index population
+ those two workbooks, i.e. the 2026-09-05 disk walk (before the space-variant D4 existed).

**Why the index is the correct denominator, and why I did NOT regenerate the index.**
`_index.json` is the **runtime authority** for `wp_template_finder`; a file absent from it is
never resolved by any wp_code. That exact case is already adjudicated and gated elsewhere —
`test_task46_d_cycle_migration.py:487`: "首轮 D4 的 template_ref 写的是 `D/D4收入底稿.xlsx`
—— 磁盘上有，但不在 `_index.json` 里，`find_template_file_any()` 对任何 D4 码都永不返回它",
and `test_wp_templates_readonly.py` pins template file count + total bytes + index presence.
This census exists to prove "the narrow criterion is sufficient for the **publication path**",
and the publication path can only reach indexed templates ⇒ the 2 disk-only workbooks are
over-count. Adding them to the index would change D4/F2 runtime template resolution and
trip the readonly baseline — a separate decision that must not ride along on this guard.

**Fix.** `backend/app/services/workpaper_sync/excel_typography_rows.py`:
re-registered the narrow counts against the scanner's actual denominator
(349 / 2602 / 842 / 170 / 37), added an explicit `denominator` field, and preserved the
original disk-walk reading verbatim under `superseded_disk_walk_2026_09_05` (including the
wide counts, which the shipped script cannot re-measure — it has no wide mode, and no test
reads them). The `only_wide_instances` adjudication (K11 `审定表K11-1!A25`) is untouched and
still sound: K11 **is** in the index, and shrinking the denominator can only remove
instances, never add one.

The tripwire is intact — the test still asserts live-scan `==` registered on all three
counts, so any new ASCII-dot template entering the index still turns it red.
Grep confirms no other consumer of the moved `wide_*` keys or of 879/182/39 in code.

**Verification:**

```
27 passed, 1 warning in 9.52s
```

Note left for the record (not edited — evidence dirs are append-only audit trail):
`.kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/g2-1-bp21-typography-rows/README.md`
still quotes "(879 / 182 / 39)" as the registered narrow counts.
---

## 3. `test_task12_canonical_resolver.py` — 2 → 0 ✅ (a) generated-artifact re-sync + census extension

**Root cause.** `backend/data/workpaper_resolver_migration_matrix.json` was never regenerated
after commit `a4c8d20cc` ("chore(task74): adjudicate 5 new writers (d2_sync_router x4 +
guidance_runtime_facts), regenerate inventory"). The matrix is **fully derived** — every row
comes from `workpaper_writer_inventory.json` (the denominator) crossed with the generator's
`POLICY` / `POLICY_BY_WRITER` tables — so a new inventory means a stale matrix. Both failures
are the same staleness seen from two angles: `test_matrix_is_fresh` compares digests,
`test_denominator_matches_inventory` compares the row set against the inventory.

**Behaviour-neutrality proof** (ran a throwaway differ, old on-disk vs freshly built):

```
row_count: 87 -> 93          digest: 0f6f811d7b03… -> 6513c15dbb68…
inventory_digest: 93d18368… -> 84fcce2f…
REMOVED (0): []
regressed: 0 -> 0            migrated: 14 -> 14      deferred: 73 -> 79
```

Six rows added, zero removed, zero `regressed`, `migrated` unchanged at 14:

| added row | kind | fork | group | status | blocking |
|---|---|---|---|---|---|
| `d2_sync_router::_load_context` | resolver | ✓ | out_of_task12_scope | deferred | 19,20,66,67 |
| `guidance_runtime_facts::load_template_source_facts` | resolver | ✓ | out_of_task12_scope | deferred | 19,20,66,67 |
| `wp_whole_workbook_document::whole_workbook_template_or_primary` | resolver | ✓ | out_of_task12_scope | deferred | 19,20,66,67 |
| `wp_template_finder::find_whole_workbook_templates` | resolver | ✓ | template_finder | deferred | 36 |
| `wp_template::create_custom_workpaper` | writer | ✗ | custom | deferred | 65 |
| `wp_template::create_custom_workpaper_batch` | writer | ✗ | custom | deferred | 65 |

The first four are exactly the four the failing test named as missing. The two `wp_template`
writers ride in because `resolver_forks()` unions "POLICY-named modules' *all* rows" onto the
resolver denominator by design. Every added row lands `deferred` **with** a non-empty
`blocking_task` + `reason`, so `test_every_deferred_row_has_blocking_task_and_reason` and
`test_no_regressed_rows` stay green on their own terms.

Only two pre-existing rows changed at all, both in the descriptive `resolver_identities` field,
both **toward** canonical (inventory-sourced facts from already-landed refactors, not something
the regeneration invents):

- `wp_guidance_chat::_resolve_template_path`: `['<ad_hoc_path_construction>']` →
  `['find_template_file_any']`, and its `self_written_markers`
  `['bare_exists_reachability','manual_backend_root']` → `[]` — the module genuinely stopped
  hand-building paths;
- `wp_onlyoffice_router::get_whole_excel_grid`: `['_resolve_wp_file','find_template_file_any']`
  → `['_resolve_wp_file']` — one fewer resolver.

No `status` / `intended_status` / `group` / `blocking_task` / `is_resolver_fork` moved on any
pre-existing row. Grepped the repo: nothing pins the literal digest `6513c15dbb68…` or
`0f6f811d7b03…` outside the artifact itself.

**Fix 1 — regenerate** (documented command, from repo root):

```
python backend/scripts/gen/generate_workpaper_resolver_migration_matrix.py --apply
python backend/scripts/gen/generate_workpaper_resolver_migration_matrix.py --check
→ [check] OK: {"row_count": 93, …, "regressed": 0, …}
```

**Fix 2 — one more failure surfaced, and it is the guard doing its job.**
`test_template_finder_deferral_names_94_and_the_bridge` pins the `wp_template_finder` writer
set as an **enumerated census** (deliberately writer-by-writer, per its own docstring, so a
half-migrated module cannot be waved through wholesale). The sixth member
`find_whole_workbook_templates` is a real resolver: it scans `TEMPLATES_DIR` directly **by
design** — whole-workbook merged templates are deliberately absent from `_index.json`, which
only indexes the range-split packages (`D2-1至D2-4 ….xlsx`) — so it is a genuine
path-resolution fork on the xlsx template-library lane, *not* on the Word lane Task 58
migrated. Added it to the enumerated set **and** to the per-writer invariant loop, so it is
now actually checked (`status == deferred`, non-empty `blocking_task`, `blocking_task` must not
name the completed Task 58 — it reads `36`). Still exact-equality; the guard got one member
stricter, not looser.

**Verification:**

```
before: 2 failed, 97 passed
after:  99 passed, 1 warning in 6.76s
```

**⚠️ Left for adjudication (not mine to touch).** The Task 66 deletion plan reads this matrix
and counts rows whose `blocking_task` names 66. That counter was **already** stale before I
touched anything — `backend/data/workpaper_sync_task66_legacy_deletion_plan.json` records
`rows_naming_task66: 25` while the *pre-existing* on-disk matrix already yielded 29 (the
concurrent owner's scratch `backend/scripts/_t66_fresh.json` independently shows 29). My
regeneration moves the live figure 29 → 32 (the three new `out_of_task12_scope` resolvers).
It changes the magnitude of an already-red drift, not its red/green state. Regenerating that
plan belongs to the subagent holding `test_task66_legacy_deletion_plan.py`; I did not touch it.
---

## 4. `test_excel_row_insertion_readiness.py` — 1 → 0 ✅ (a) stale census pin vs a legitimately grown registry

**Root cause.** `test_all_four_published_contracts_are_assessed` hand-copied a four-id set.
`build_report()` walks `available_contract_ids()`, and the D-cycle migration (commit `cd9592ff5`
`feat(d4-sync)`, production modules `phase5_d1_notes_receivable` / `_d3_prepaid_receipts` /
`_d4_revenue_detail` / `_d5_receivables_financing` / `_d6_contract_assets` /
`_d7_contract_liabilities`) took the published registry from 4 to 10. The guard went red by
reporting **six extra** entries — i.e. it flagged the good news as a fault.

Measured live:

```
registry 10 ['b60.hour_budget', 'd1.notes_receivable_detail', 'd2.receivable_detail',
 'd3.prepaid_receipts_detail', 'd4.revenue_detail', 'd5.receivables_financing_detail',
 'd6.contract_assets_detail', 'd7.contract_liabilities_detail',
 'g7.soe_subsidiary_disclosure', 'h1.disposal_check']
entries 10   errors []
counts {"insertion_safe": 9, "blocked_static_row_below_insertion": 1, …all others 0}
```

All ten assess cleanly; the single block is H1's already-adjudicated
`blocked_static_row_below_insertion`. Nothing regressed — six new entries simply joined.

**Fix.** Renamed to `test_every_published_contract_is_assessed` and made the denominator
**read the registry** instead of a hand-copied literal. This is strictly stronger, not looser:
`build_report()` routes an entry whose assessment *raises* into `report["errors"]` and **not**
into `entries`, so "a published contract blew up and therefore has no verdict" now turns this
guard red — the old literal could never see that. Kept the four AC 10.5 carriers as an explicit
`<=` floor so an emptied registry cannot degrade the equality into `set() == set()`, and the
failure message prints both diff directions plus `errors`.

**Verification:**

```
before: 1 failed, 20 passed
after:  21 passed, 1 warning in 2.36s
```

**Observation (out of scope, not acted on).** The census artifact has never been persisted:
`python scripts/check/check_excel_row_insertion_readiness.py --check` →
`[FAIL] 清册不存在: backend/data/workpaper_excel_row_insertion_readiness.json —— 先跑 --json`.
No test in this cluster asserts that file exists, and minting a new `backend/data/` artifact
could disturb gates that count data files, so I left it. Flagging it in case a CI job runs
`--check`.
---

## 5. `test_d2_store_value_equivalence.py` — 3 → 0 ✅ (c) **real production bug**, root cause fixed

All three failed with `AttributeError: module 'app.services.workpaper_sync.d2_bidirectional_bridge'
has no attribute 'merge_projection_into_store_rows'`.

**This is not test drift — production is broken on the unified path.** `oo_to_html.py` L2581-2585:

```python
if adapter_id == "d2.receivable_detail":
    from app.services.workpaper_sync import d2_bidirectional_bridge as bridge
    store_item_id = bridge.STORE_ITEM_ID
    merge_kind = "rows"
    merge_rows_fn = bridge.merge_projection_into_store_rows   # ← attribute does not exist
```

and L2692 then calls `merge_rows_fn(projection=…, base_rows=…)`. Every sibling branch in that
same dispatch (`h1.disposal_check`, `g7.soe_subsidiary_disclosure`, `d1`, `d3`, `d5`, `d6`, `d7`,
`d4`) binds a bridge that really does export the function — only D2's does not. So a D2
OnlyOffice callback on the unified path raises `AttributeError` at the merge step: the
`content_version` advances while the checklist store keeps the old values, which is exactly the
silent regression of `store_mirrored` / `marker_visible` the test file's docstring warns about.
This is the **capability-flip family** the brief predicted: the D2 entry's manifest capability is
now `bidirectional` (committed `0c9eb40d6`), which makes this branch reachable.

`backend/scripts/check/check_d2_sync_retirement_eligibility.py` L713 independently names
`merge_projection_into_store_rows` as one of three `_REHOMED_SYMBOLS` that must stay covered
after retirement, and `mutate_d2_sync_retirement_guards.py` mutates
`merge_rows_fn = bridge.merge_projection_into_store_rows` in three places — so the name is the
agreed API, not an invention of the test.

Prior record: `docs/operations/d4-bidirectional-writeback-inventory.md:851` logged these 3 as
"API 漂移，测试未跟上" (API drift, test not keeping up). That reading had the direction
backwards — the consumer (`oo_to_html`) drifted *with* the test; it is the bridge that is
missing the function.

**Fix (root cause, no copy).** The merge loop already existed — inlined inside
`pull_excel_to_html`. Extracted it verbatim into a public
`merge_projection_into_store_rows(*, projection, base_rows) -> (rows, applied, visited, touched)`
in `d2_bidirectional_bridge.py`, signature identical to the sibling bridges, and rewrote
`pull_excel_to_html` to call it. One implementation serves both the unified path and the legacy
path — writing a second copy in `oo_to_html` would recreate the two-sources-of-truth drift this
module already guards against (`_same_store_value` is a forwarding alias for the same reason,
asserted with `is`).

Behaviour preserved exactly, so the three properties hold without special-casing:
`applied` counts only real changes via `assign_store_value` (int `5200` vs float `5200.0` is not
a change, and the store keeps the `int`); protected cells `continue` *before* `visited++`, so
`(applied, visited, touched) == (0, 0, set())` and unmanaged keys like `uiOnlyFlag` survive;
Excel-side-only rows are appended. D2 deliberately has **no** ghost-row filter (D1/D3/D5/D6/D7
do) because its managed region has no naming first column — documented in the new docstring.

**Verification:**

```
test_d2_store_value_equivalence.py   before: 3 failed, 21 passed   after: 24 passed in 1.43s
```

Regression companions run together (`test_task41_d2_large_json_pilot`, `test_ghost_row_defense`,
`test_task26_oo_to_html`): **277 passed**, 7 failed — all 7 pre-existing and outside this
cluster. `git status` confirms I never touched `oo_to_html.py`, `pilot_d2_large_json.py` or the
entry manifest, and none of the 7 involves `d2_bidirectional_bridge`: six are
`test_task41::TestOrderingGate` asserting `capability_of(d2) is single_onlyoffice` while the
manifest now says `bidirectional` (same capability-flip family, see §6/§7), plus one
`test_task41` census `176 != 186`; the seventh is
`test_task26_oo_to_html::test_coordinator_source_has_no_bare_warning_swallow` flagging
`oo_to_html.py:2471`, a file another subagent currently holds.
---

## 6. `test_downstream_base_reliability_gate.py` — 1 → 1 🟥 **(b) human-review gate, deliberately NOT touched**

`test_no_evidence_artifact_asserts_a_verified_base_while_the_door_is_blocked` (category C:
while the door is blocked, no on-disk entry node may structurally assert the base is usable):

```
门未过（750 条 blocking facts），但磁盘上有 4 处 entry 级验收断言：
  [evidence_asserts_bidirectional_capability] …entry_manifest.json/entries[65]/capability
      = bidirectional（entry=xlsx/gt-d2-accounts-receivable）
  … entries[67] xlsx/gt-d4-operating-revenue
  … entries[98] xlsx/gt-g7-long-term-equity-main
  … entries[101] xlsx/gt-h1-fixed-assets
```

**Root cause.** The test's own docstring records the state it was written against: "全量 manifest
的 186 条 entry 里 `adapter_id` 等五个身份字段**全部为 null**，capability 只有
`single_onlyoffice`/`single_html`/`unreachable`". Measured now:

```
entries 176
Counter({'single_onlyoffice': 166, 'single_html': 5, 'bidirectional': 4, 'unreachable': 1})
bidir ['xlsx/gt-d2-accounts-receivable', 'xlsx/gt-d4-operating-revenue',
       'xlsx/gt-g7-long-term-equity-main', 'xlsx/gt-h1-fixed-assets']
```

So the manifest went 186 → 176 entries and four entries flipped to `bidirectional`, last changed
in the committed `0c9eb40d6`. The gate is **working exactly as designed**: four entries now claim
a verified base while 750 blocking facts say the door is shut.

**Classification (b) — reported, not bumped.** Turning this green requires either clearing the
door or reverting/re-approving the capability flip. `backend/data/workpaper_sync_entry_overlay.json`
carries the `approved_source_digest` / `review_status` / `review_basis` review gate, and per this
session's earlier finding its approved digest is 111 commits behind — deliberately left red. The
capability flip belongs to that same governance decision. I changed nothing here.

---

## 7. `test_projection_lane_regression_gate.py` — 6 → 6 🟥 (b) ×4 + (b) ×2, deliberately NOT touched

Two sub-clusters, both human-review.

### 7a. Four failures are one fact: the same capability flip (b)

| test | message |
|---|---|
| `test_other_pilots_are_still_rejected_so_the_denominator_is_not_trivial` | 四个 pilot entry 全部放行 ⇒ 本属性退化为重言式 |
| `test_stage_two_is_correctly_still_blocked_by_the_disk_manifest` | 内存 manifest 补丁竟然让 G7 真的注册上了 |
| `test_production_manifest_registers_nothing_for_g7` | 生产 manifest 下 G7 已注册 |
| `TestBindingConstraintComesFromThreeArmMeasurement::test_default_call_reports_bp_61_1` | 实测绑定约束为 None |

Ran the three-arm measurement directly. The control arm's rejection reason is now **`null`**
because the control entry is **registered**, and all four flipped entries register in *every* arm:

```
arm_a_control:  registered_adapter_ids = ['d2.receivable_detail','d4.revenue_detail',
                  'g7.soe_subsidiary_disclosure','h1.disposal_check']
                control_entry_reason = null        planned = 176
arm_b_manifest_flipped / arm_c_supply_stubbed: same four registered
arm_b_reason_equals_control_reason: false   →   binding_constraint_id: null
```

`binding_constraint_id` is `BP-61-1` only while arm_b's reason equals the control's; with the
control no longer rejected at all, the comparison collapses. So all four are downstream of the
one flip, not four independent defects. Note the second test's alarm text ("单一真源被破坏") is a
**misdiagnosis** of today's state: the in-memory patch did not leak — the *disk* manifest already
says `bidirectional`.

The gate states the governance rule itself, quoting arm_c's measured reason: "注册 bidirectional
adapter 前必须先由 reviewed overlay 裁决为 bidirectional 并重生成 manifest（RG-18 会以
FakeBidirectionalError 拒绝伪双向）", and `test_production_manifest_registers_nothing_for_g7`
spells out the required action: "若确已翻转，请核对 `approved_source_digest` 复核门是否被绕过
（Requirement 7.8 明令禁止），并更新本判据". That is a Requirement 7.8 review, not a re-sync.
**Not touched.**

### 7b. Two failures are pinned DB readings vs the live database (b)

```
TestBindingConstraintComesFromThreeArmMeasurement::test_measured_block_agrees_with_the_real_database
  → 登记 2 行、真库现查 12 行   (working_paper_sync_entry_state)
TestRegisteredReadingsAgreeWithTheDatabase::test_latest_reading_matches_the_database
  → working_paper_content_version_rows: 登记 2、真库 198
```

The pins are dated measurement records in production source — BP-61-1's
`measured_2026_09_04` block in `check_task61_oo94_word_pilot_gate.py`, and
`opaque_entry_gate.ENTRY_ID_NAMESPACE_SPLIT_NOTE["measured_migration_cost"]`, which is an
**append-only series** (`_latest()` demands ≥2 dated entries, and
`test_the_series_preserves_the_task65_zero_reading` forbids dropping the historical `0` reading
because it is the only evidence of an earlier wrong conclusion about migration cost).

So the intended maintenance is *appending a new dated reading*, never editing the old one — and
that reading is a substantive claim about migration cost. I did not append one, for two reasons:
hand-writing a number to turn a tripwire green is exactly what this gate exists to prevent, and
the measurement would be garbage right now — this dev database is being actively written to by
concurrent subagents running PG suites, so any figure I recorded would be noise, not a reading.
**Left for the owner to re-measure on a quiesced database.**

---

## 8. `test_d2_sync_retirement.py` — 8 → 8 🟥 (b) forward-looking retirement gate, deliberately NOT touched

All eight are one undelivered task. The file is a **structural ban**, not a deletion record, and
it delegates every criterion to `check_d2_sync_retirement_eligibility.py`. That gate's own report:

```
phase pre_delete   counts {'pass': 6, 'fail': 6, 'unverifiable': 0}
  E0.phase-is-consistent              pass
  E1.milestone-onlyoffice-verified    fail  milestone.state='STALE' != ONLYOFFICE_VERIFIED
  E2a.backend-no-production-caller    fail  backend/app/routers/wp_html_save.py 仍用 `d2-sync`
  E2b.frontend-no-production-caller   fail  GtOnlyOfficeSheet.vue 仍在代码里用 `d2-sync`
  E2c.no-route-registration           pass  (pre-delete：d2_sync_router.py 提供 4 条，registry 2 处待摘)
  E3a.command-service-superset        pass
  E3b.bridge-module-retained          pass
  E3c.defect-a-reverse-lock           fail  取不到两个下标变量（flush=None read=None）
  E3d.four-state-text-guard           pass
  E3e.forcesave-fail-closed           fail  GtOnlyOfficeSheet.vue 缺 ['if (!endpoint)']
  E4.store-value-equivalence-rehomed  pass  覆盖 ['same_store_value','_assign_store_value',
                                             'merge_projection_into_store_rows']
  E5.negative-assertion-inventory     fail  1/7 处负向断言失效（GtOnlyOfficeSheet.spec.ts 缺 d2-sync）
```

Six of the eight test failures are the `pre_delete` phase itself — `d2_sync_router.py`,
`useD2SyncBridge.ts` and the `d2-sync` literals are all still on disk. Executing that deletion is
a destructive, high-blast-radius production change (a router + a frontend bridge + registry
unbinding, on a component shared by 179 entries); it needs explicit authorization and is the
retirement task's own deliverable. **Not done unilaterally.**

**The two phase-independent failures are *not* guard erosion — the anchors never existed.**
`git log -S` over each file's full history returns **zero** commits introducing either anchor:

- `readStoreProjection` has never appeared in `d2SyncHostWiring.spec.ts` (E3c wants
  `expect(<read idx>).toBeGreaterThan(<flush idx>)` built from two `indexOf` bindings; the spec
  has `flushPendingSave` only inside an unrelated `toMatch` regex);
- `d2-sync` has never appeared in `GtOnlyOfficeSheet.spec.ts` (E5's 7th negative assertion).

So both are undelivered preconditions, on the same footing as the deletion itself.

**Ordering constraint worth flagging to the owner:** E5's missing assertion **cannot** be added
today. `GtOnlyOfficeSheet.spec.ts` would assert the component never mentions `d2-sync`, but the
component still does — `GtOnlyOfficeSheet.vue` L300-301:

```js
const endpoint =
  props.forcesaveEndpoint || `/api/workpapers/${props.wpId}/d2-sync/forcesave`
```

That `||` fallback is also exactly what E3e fails on: G4-0a requires **fail-closed**
(`if (!endpoint)` → return `accepted:false` without issuing HTTP), whereas the component
currently *defaults to the retired endpoint*. The in-file comment shows the fallback was a
deliberate byte-compatibility choice ("默认仍指 legacy `/d2-sync/forcesave` …保持…178 个…行为
逐字节不变"), so E2b + E3e + E5 must be cleared as one edit, in that order. Per E3e's own
warning this is not cosmetic: the 179 entries sharing this component would "重新把 forcesave
泄漏到 D2-2（总控 gap 14）" if any of them ever calls `forceSave()`.

**E1 (`milestone.state='STALE'`) belongs to the concurrent owner** of
`test_workpaper_sync_program_milestones` — stayed out of it.

Side note: **E4 passes and names `merge_projection_into_store_rows` as covered** — the symbol §5
restored. That criterion was masked in the original run because pytest stops at the first failing
verdict (E3c), so E3e's finding above had never surfaced either.
---

## Cluster result

| file | before | after | class | disposition |
|---|---|---|---|---|
| `test_excel_shift_aware_verification.py` | 1 | **0** ✅ | test fix | stale second count pin (16 vs 15) |
| `test_excel_typography_rows.py` | 3 | **0** ✅ | (a) | census re-registered against the scanner's real denominator |
| `test_task12_canonical_resolver.py` | 2 | **0** ✅ | (a) | derived matrix regenerated + one census extended |
| `test_excel_row_insertion_readiness.py` | 1 | **0** ✅ | (a) | denominator now read from the registry |
| `test_d2_store_value_equivalence.py` | 3 | **0** ✅ | **(c)** | real `AttributeError` in `oo_to_html`'s D2 branch, root cause fixed |
| `test_d2_sync_retirement.py` | 8 | 8 🟥 | (b) | forward-looking retirement gate — needs authorized deletion |
| `test_projection_lane_regression_gate.py` | 6 | 6 🟥 | (b) | 4× capability-flip review (Req 7.8) + 2× DB readings to re-measure |
| `test_downstream_base_reliability_gate.py` | 1 | 1 🟥 | (b) | capability flip claims a verified base while the door is blocked |
| **total** | **25** | **15** | | 10 closed, 15 all (b) |

Combined run of the six files in this session's scope (cwd=`backend`):

```
before: 21 failed
after:  15 failed, 195 passed, 2 xfailed, 5 warnings in 43.03s
```

No assertion was weakened, no skip/xfail added, no hash or digest hand-edited. The only
generated artifact regenerated with its documented command is
`backend/data/workpaper_resolver_migration_matrix.json`, after proving the diff behaviour-neutral
(§3).

### Files changed

- `backend/app/services/workpaper_sync/d2_bidirectional_bridge.py` — extracted the public
  `merge_projection_into_store_rows` the unified path already binds (production fix)
- `backend/data/workpaper_resolver_migration_matrix.json` — regenerated (derived artifact)
- `backend/tests/workpaper_sync/test_task12_canonical_resolver.py` — finder census +1 member,
  held to the same per-writer invariant
- `backend/tests/workpaper_sync/test_excel_row_insertion_readiness.py` — denominator read live

### Open for adjudication (nothing touched)

1. **The `bidirectional` capability flip** on `xlsx/gt-d2-accounts-receivable`,
   `gt-d4-operating-revenue`, `gt-g7-long-term-equity-main`, `gt-h1-fixed-assets` (committed
   `0c9eb40d6`) drives **5** of the 15 remaining failures across two gate files. The question the
   gates ask is whether it passed the `approved_source_digest` review (Requirement 7.8) — the same
   overlay review whose digest is 111 commits behind. One decision closes all five.
2. **The D2 retirement** (8 failures): requires deleting `d2_sync_router.py` +
   `useD2SyncBridge.ts` + registry unbinding, plus clearing E2b/E3e/E5 as one edit on
   `GtOnlyOfficeSheet.vue` (drop the `|| /d2-sync/forcesave` fallback for a fail-closed
   `if (!endpoint)`), plus writing the two anchors that never existed. Ordering matters — see §8.
3. **Two dated DB readings** (§7b) need re-measuring on a quiesced database, appended to the
   series rather than edited in place.
4. **`workpaper_sync_task66_legacy_deletion_plan.json`** owes a regeneration: its
   `rows_naming_task66` was already stale at 25-vs-29 before this session, and §3's matrix
   regeneration moves the live figure to 32. Belongs to the concurrent owner of
   `test_task66_legacy_deletion_plan.py`.
5. **`workpaper_excel_row_insertion_readiness.json`** has never been written to disk (§4).
