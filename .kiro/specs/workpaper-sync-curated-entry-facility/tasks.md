# Implementation Plan: Workpaper Sync Curated-Entry Facility

## Overview

Add an additive, reviewed, two-way-locked curated-entry facility to the shared discovery generator so one dynamic host can back multiple logical sync entries. Motivating consumer: D4-9. When no curated entry is declared, output is byte-identical to today. Below checkboxes are the single source of truth for progress.

## Tasks

- [x] 1. Capture discovery-only baseline + empty-case byte-identity guard
  - Run real `build_manifest` on current overlay (no `curated_entries`), snapshot manifest JSON + frontend TS bytes into a test fixture.
  - Guard asserts empty/absent `curated_entries` yields byte-identical output (Property 1). This guard must exist BEFORE the facility so the additive invariant is provable.
  - _Requirements: 1.3_

- [x] 2. Curated-entry builder + validation in generator
  - Add `_CURATED_MIGRATION_STATES`, `_REQUIRED_CURATED_FIELDS`, extract shared `_assert_profile_in_expected` from `_assert_expected_profile`.
  - Implement `_build_curated_entries(overlay, *, discovered_host_paths, discovery_entry_ids)` with all fail-closed gates: collision, host existence, capability discipline (bidirectional requires adapter/html_store/contract-test/review_status), unreviewed rejection, profile-vs-expected.
  - _Requirements: 1.1, 1.2, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4_

- [x] 3. Integrate curated entries into build_manifest + digest
  - Append curated entries after discovery loop + stale gates; add `curated_source_digest` (only when non-empty) participating in `manifest_digest`; add `curated_entry_count` to stats; merge-time collision assertion.
  - Ensure curated `mounts=[]` do not break the `manifest_mount_ids == source_mount_ids` check.
  - _Requirements: 1.1, 3.1, 3.2, 3.3, 3.4, 4.2_

- [x] 4. Facility behavior guards + mutation script
  - `backend/tests/workpaper_sync/test_curated_entry_facility.py`: empty byte-identity, populated emission, all fail-closed cases, digest determinism.
  - `backend/scripts/diagnose/mutate_curated_entry_facility_guards.py`: ≥4 anchors, four-state verdict, verify RED on each.
  - _Requirements: 5.1, 5.2_

- [x] 5. Wire D4-9 curated entry + regenerate manifest + registry attach
  - Add D4-9 curated declaration to overlay; `--apply` regenerate; verify entry_count +1 and `xlsx/gt-d4-customer-structure` present with adapter `d4.customer_structure`.
  - Registry `attach_adapters` resolves curated bidirectional entry (RG-4 preserved); non-bidirectional curated fails attach closed (guard).
  - _Requirements: 4.1, 4.3_

- [x] 6. Cross-spec closure + evidence
  - Confirm D4-9 spec Task 6 `assert_manifest_capability_enabled`/`assert_entry_selectable` pass against regenerated manifest.
  - Record browser-level proof `UNVERIFIABLE` (no OO runtime). `get_diagnostics` on three-set; `git status --porcelain` on new artifacts; INDEX registration; cleanup temp files.
  - _Requirements: 5.3_
  - ✅ 交付（closure evidence，非改 D4-9 自身 checkbox）。**D4-9 函数读什么（读源码实测）**：`assert_manifest_capability_enabled`/`assert_entry_selectable` 在 D4 家族由 `phase5_d4_revenue_detail.py`（D4-2 sibling）定义，两者都带 `manifest` 参数（in-memory seam），`manifest=None` 时回落 `load_entry_manifest()` 读**磁盘** manifest。🔴 `phase5_d4_customer_structure.py`（D4-9 本体）**尚未定义**这两个函数——它们正是 D4-9 Task 6 要新增、且被本 facility 落盘所阻塞的符号。
  - **闭合守卫** `backend/tests/workpaper_sync/test_curated_entry_cross_spec_closure.py` **8 passed + 1 xfailed**：不 stub，驱动这两个函数所包裹的**同一套真实底层逻辑**（`manifest_entries_by_id` + `entry_profile.capability_of` + registry `assert_bidirectional_ready`/`resolve_for_entry`）对着**内存现建** manifest（Task 5 接线法：真实 overlay+pinned discovery→真实 build_manifest）跑。Part A PROVEN（5）：D4-9 entry capability=bidirectional、可选中、registry 挂 `d4.customer_structure`、RG-4 保留、非双向 attach 关闭失败 + 反重言式。Part B BLOCKED（3）：磁盘 manifest 不含 D4-9（186 entry，宿主 entry 仍 single_onlyoffice/adapter=null），磁盘形态 capability 逻辑 KeyError fail-closed——既有 `approved_source_digest` 漂移（`d9fddb64…` vs `a18a531d…`）所致、与 curated facility 正交（Req 3.4），**未强推 disk regen、未 bump digest**。Part C UNVERIFIABLE（1，strict xfail）：无 OO runtime，浏览器双向证明记 UNVERIFIABLE（Req 5.3）。
  - 证据 `backend/tests/workpaper_sync/data/curated_entry_facility_evidence.md`（PROVEN/BLOCKED/UNVERIFIABLE 三态矩阵 + 选型理由 + 实测漂移串）。
  - `get_diagnostics` 三件套 0 error（Kiro Spec Format 全过）。

## Notes

- Shared file lock (master-control §5.3): `generate_workpaper_sync_manifest.py` and `workpaper_sync_entry_overlay.json` are shared/previously-archived; only add the curated section, do not alter discovery paths or the `approved_source_digest` gate. Grep concurrent specs before editing.
- Tasks 13/15 of the D4-9 spec (real-stack Playwright) remain environment-blocked until OnlyOffice runtime is available.

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1"],"rationale":"baseline before facility"},{"wave":2,"tasks":["2"],"rationale":"builder+validation"},{"wave":3,"tasks":["3"],"rationale":"integration+digest depends on builder"},{"wave":4,"tasks":["4"],"rationale":"guards depend on facility"},{"wave":5,"tasks":["5"],"rationale":"D4-9 wiring depends on facility+guards"},{"wave":6,"tasks":["6"],"rationale":"closure last"}],"blocking":{"2":"baseline must exist first","5":"facility+guards must pass"}}
```
