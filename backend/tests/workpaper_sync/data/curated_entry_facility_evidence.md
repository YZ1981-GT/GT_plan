# Curated-Entry Facility — Cross-Spec Closure Evidence

Spec: `workpaper-sync-curated-entry-facility` / Task 6 (cross-spec closure).
Requirements: 5.3 (browser proof UNVERIFIABLE, not implementation failure).
Consumer: `d4-9-customer-structure-bidirectional-writeback` / Task 6.

This note is **factual**: it records exactly what is proven, what is blocked, and
what is unverifiable, with the measured evidence backing each claim. It is the
companion to the closure guard `test_curated_entry_cross_spec_closure.py`.

---

## 1. What is PROVEN (in-memory, real code, green guards)

The curated-entry facility works end to end when the manifest is rebuilt in memory
from the real reviewed overlay (which now carries the D4-9 curated declaration) plus
the Task 1 pinned discovery fixture. Driven through **real generator + real
`entry_profile` + real registry code** (no stubs):

- **Regeneration would produce +1 entry.** `build_manifest(pinned_discovery,
  real_overlay)` yields `entry_count == curated-free baseline + 1`; the only delta is
  `xlsx/gt-d4-customer-structure`. (`test_curated_entry_d4_9_wiring.py`, 10 passed.)
- **The D4-9 curated entry is capability-enabled (bidirectional).** The exact
  underlying logic that D4-9 Task 6's `assert_manifest_capability_enabled` wraps —
  `manifest_entries_by_id(manifest)[ENTRY_ID]` + `entry_profile.capability_of(entry)
  is Capability.bidirectional` + `adapter_id == "d4.customer_structure"` — passes
  against the in-memory-built manifest via the real `manifest=` seam.
- **The D4-9 curated entry is selectable.** The exact underlying logic that D4-9
  Task 6's `assert_entry_selectable` gates into — real
  `WorkpaperSyncAdapterRegistry.register` + `resolve_for_entry` +
  `assert_bidirectional_ready` — resolves `d4.customer_structure` and passes the
  bidirectional-ready gate, with RG-4 uniqueness preserved (a second adapter on the
  same entry_id is rejected).
- **Non-bidirectional curated entry fails attach closed** (RG-18 `FakeBidirectionalError`).

### Why the closure guard drives the *underlying logic* rather than the named functions

`phase5_d4_customer_structure.py` does **not** define
`assert_manifest_capability_enabled` / `assert_entry_selectable` — those are exactly
the symbols D4-9 Task 6 would add, and D4-9 Task 6 is **still open** precisely because
it is blocked on this facility landing on disk. The sibling module
`phase5_d4_revenue_detail.py` (same host family, D4-2) *does* define them, and both:

1. accept an optional `manifest` parameter (an in-memory seam), and
2. fall back to `load_entry_manifest()` (which reads the **disk** manifest, `lru_cache`d)
   when `manifest is None`.

Their bodies are thin wrappers over `manifest_entries_by_id` + `capability_of`
(capability check) and the registry (`assert_bidirectional_ready`). The closure guard
therefore drives that identical real underlying logic against the in-memory manifest,
which is faithful to what the D4-9 functions will do once implemented — no stub, no
fake. This is the "assert against the underlying logic they wrap" branch of the Task 6
instruction, chosen because the named D4-9 functions do not yet exist to call.

---

## 2. What is BLOCKED (disk `--apply`, pre-existing drift, orthogonal to this spec)

The **on-disk** manifest (`backend/data/workpaper_sync_entry_manifest.json`) does
**not** contain the D4-9 curated entry:

- measured: 186 entries, `xlsx/gt-d4-customer-structure` absent, no
  `curated_source_digest` key, `stats.curated_entry_count` absent.
- the shared D4 host entry `xlsx/gt-d4-operating-revenue` is still
  `capability="single_onlyoffice"`, `adapter_id=null`.

Disk regeneration is gated by a **pre-existing** `approved_source_digest` drift, not by
anything in the curated facility (Requirement 3.4 explicitly carves curated entries as
orthogonal to the physical mount inventory):

```
[FAIL] source mounts changed since the reviewed overlay:
  approved='d9fddb64a7b3d9881bb81e247b848c36b7e5668202b0d07e7b7900779cc88a32'
  current ='a18a531d4320edcc5a30fa699cfe1c513ef6aa352db7f1d34e9d14e549e80bae';
  review the mount diff before updating approved_source_digest
```

Because `load_entry_manifest()` reads this disk file, D4-9 Task 6's
`assert_manifest_capability_enabled` / `assert_entry_selectable` in their
**disk-manifest form** (i.e. called with `manifest=None`) would fail: the curated
entry is not present and the host entry is not `bidirectional`. This is expected and
documented — it is the disk-regen block, not a facility defect.

**Deliberately NOT done here** (per Task 6 constraints): no forced disk regen; no bump
of `approved_source_digest`. Unblocking disk regen requires reviewing the physical
mount diff and re-approving the source digest — a separate, higher-blast-radius action
that regenerates the whole 186-entry manifest and is owned by the shared closure spec.

---

## 3. What is UNVERIFIABLE (browser / OnlyOffice runtime)

The browser-level proof of a curated **bidirectional** entry (open the D4-9 sheet in
the OnlyOffice editor, edit a customer row + a total, force-save, mirror back to HTML,
confirm the two-way roundtrip in a real browser) is **UNVERIFIABLE** on this machine:
there is no OnlyOffice runtime available (`D:\DeepHorness` / OO runtime absent).

Per **Requirement 5.3**, this is recorded as `UNVERIFIABLE`, **not** an implementation
failure. The in-memory registry-attach + capability + selectability proof above stands
as the strongest evidence obtainable without an OO runtime. The browser roundtrip
remains the environment-blocked tail (also tracked as D4-9 spec Tasks 13/15).

---

## 4. Summary matrix

| Claim | Status | Evidence |
|---|---|---|
| Curated facility empty-case byte-identity | PROVEN | `test_curated_entry_facility_baseline.py`, `test_curated_entry_facility.py` |
| Regeneration emits +1 D4-9 entry (in-memory) | PROVEN | `test_curated_entry_d4_9_wiring.py` (10 passed) |
| D4-9 entry capability-enabled = bidirectional | PROVEN (in-memory, real underlying logic) | `test_curated_entry_cross_spec_closure.py` |
| D4-9 entry selectable + adapter attaches (RG-4) | PROVEN (in-memory, real registry) | `test_curated_entry_cross_spec_closure.py` |
| Non-bidirectional curated fails attach closed | PROVEN | `test_curated_entry_cross_spec_closure.py`, `test_curated_entry_d4_9_wiring.py` |
| Disk manifest contains D4-9 entry | BLOCKED | pre-existing `approved_source_digest` drift (`d9fddb64…` vs `a18a531d…`) |
| Disk-form `assert_*` for D4-9 pass | BLOCKED (by disk regen) | closure guard asserts D4-9 absent from disk manifest |
| Browser OO bidirectional roundtrip | UNVERIFIABLE | no OO runtime on this machine (Req 5.3) |
