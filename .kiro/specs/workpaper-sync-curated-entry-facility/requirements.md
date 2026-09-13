# Requirements Document

Workpaper Sync Curated-Entry Facility

## Introduction

The workpaper HTML↔OnlyOffice sync manifest is produced by `backend/scripts/gen/generate_workpaper_sync_manifest.py`, which is **strictly discovery-derived**: it groups Vue template AST mount facts by `(source_file, component)`, derives exactly one `entry_id` per host file, and refuses to guess capability. This safety model has one structural gap: **a single frontend host that mounts one dynamic `GtOnlyOfficeSheet` (bound to a runtime `ooSheetName` expression) can back multiple logical workpaper sheets, but discovery can only ever produce one entry for it.**

D4-9 (`重要客户结构分析D4-9`) shares the host `GtD4OperatingRevenue.vue` with D4-1/D4-2/D4-3. Its own contract, bridge, materialize/extract engine, projection, protection set, lineage, import/export, and mutation guards are already delivered (~57 green tests) under spec `d4-9-customer-structure-bidirectional-writeback`, but its adapter `d4.customer_structure` cannot register because the discovery generator produces no independent `xlsx/gt-d4-customer-structure` entry, and the registry enforces unique `entry_id` (RG-4).

This spec adds a **curated-entry facility** to the shared generator: an additive, reviewed, two-way-locked mechanism to emit synthetic manifest entries that are NOT backed by a discoverable physical mount, for the specific case of one host serving multiple logical sheets. The facility must not weaken the existing discovery safety model, must not let a curated entry silently claim `bidirectional`, and must keep the 186 discovered entries byte-identical when no curated entry is declared.

Source-of-truth priority follows `docs/operations/workpaper-html-onlyoffice-bidirectional-writeback-master-control.md`: DB constraints and runtime requests > source-backed manifest/generator/machine gates > this spec.

## Glossary

| Term | Meaning |
|---|---|
| discovery entry | Manifest entry derived from a physical Vue mount fact via `_group_source_facts`. |
| curated entry | Manifest entry declared in the reviewed overlay `curated_entries` section, not backed by a discoverable mount. |
| overlay | `backend/data/workpaper_sync_entry_overlay.json`, the reviewed business adjudication source. |
| manifest | `backend/data/workpaper_sync_entry_manifest.json` + `workpaperSyncManifest.generated.ts`. |
| RG-4 | Registry rule: one independent entry_id resolves to at most one adapter. |
| curated_source_digest | Digest of the reviewed curated-entry declarations, participating in `manifest_digest`. |

## Requirements

### Requirement 1: Additive curated-entry section in the reviewed overlay

**User Story:** As a platform maintainer, I want to declare synthetic sync entries in the reviewed overlay so a single dynamic host can back multiple logical sheets without inventing discovery facts.

#### Acceptance Criteria

1. WHEN the overlay contains a `curated_entries` array THEN the generator SHALL emit one manifest entry per curated declaration, each carrying `entry_id`, `document_type`, `wp_match`, `html_store`, `canonical_resolver`, `adapter_id`, `capability`, `migration_state`, `evidence`, and the source-backed profile fields.
2. WHEN a curated declaration is present THEN it SHALL carry an explicit `curated_reason` and `host_path` referencing the real host it logically rides on, and that `host_path` SHALL correspond to an existing discovered host.
3. WHEN the overlay omits `curated_entries` (or it is empty) THEN the generated manifest and frontend artifact SHALL be byte-identical to the current discovery-only output (no curated entry ⇒ no change).
4. IF a curated `entry_id` collides with any discovery entry_id or another curated entry_id THEN the build SHALL fail closed.
5. IF a curated declaration references a `host_path` that no discovered mount produces THEN the build SHALL fail closed (a curated entry must ride a real host).

### Requirement 2: Curated entries cannot silently claim bidirectional

**User Story:** As a platform maintainer, I want curated entries held to the same fail-closed capability discipline as discovery entries so a synthetic entry can never fake a capability.

#### Acceptance Criteria

1. WHEN a curated declaration sets `capability` THEN the value SHALL be one of the allowed capabilities and SHALL come from the reviewed overlay, never inferred.
2. WHEN a curated declaration sets `capability = bidirectional` THEN it SHALL carry non-empty `adapter_id`, `html_store`, contract-test evidence, and a `review_status`; missing any of these SHALL fail closed.
3. WHEN a curated declaration's profile fields are emitted THEN they SHALL be validated against a reviewed `expected_profile` set exactly as discovery entries are (Requirement 1.2 of the manifest generator), with mismatch failing closed.
4. IF a curated declaration is not reviewed (`review_status` absent/empty) THEN the build SHALL fail closed.

### Requirement 3: Two-way digest lock and stale-declaration gate

**User Story:** As a platform maintainer, I want curated declarations locked into the manifest digest so drift is detected and stale declarations cannot rot silently.

#### Acceptance Criteria

1. WHEN the manifest is built THEN a `curated_source_digest` SHALL be computed over the reviewed curated declarations and SHALL participate in `manifest_digest`.
2. WHEN `--check` runs and any curated-derived output differs from disk THEN the check SHALL fail with a stale/missing diagnostic.
3. WHEN a curated declaration is added, removed, or edited THEN regenerating SHALL change `manifest_digest` and `curated_source_digest` deterministically.
4. WHERE the existing `approved_source_digest` gate governs physical mounts THE curated section SHALL NOT alter or bypass that gate (curated entries are orthogonal to the physical mount inventory).

### Requirement 4: Registry and consumption compatibility

**User Story:** As a platform maintainer, I want curated entries to flow through the registry and frontend exactly like discovery entries so downstream consumers need no special-casing.

#### Acceptance Criteria

1. WHEN the registry attaches adapters THEN a curated `bidirectional` entry SHALL be selectable and attach its adapter exactly like a discovery entry, subject to RG-4 uniqueness.
2. WHEN the frontend manifest projection is rendered THEN curated entries SHALL appear with the same shape as discovery entries (entryId/hostPath/capability/wpMatch/profile fields).
3. WHEN a curated entry's capability is not `bidirectional` THEN adapter attach SHALL fail closed for that entry.

### Requirement 5: Verification, guards, and anti-false-green

**User Story:** As a platform maintainer, I want behavior-level guards and mutation checks so the curated facility cannot regress into a tautology or a silent bypass.

#### Acceptance Criteria

1. WHEN validating the facility THEN guards SHALL run the real generator `build_manifest` with and without a curated declaration and assert byte-identity in the empty case (Requirement 1.3) and correct emission in the populated case.
2. WHEN doing mutation testing THEN a mutation script SHALL provide ≥4 anchors: allow curated bidirectional without adapter/evidence; drop the collision guard; drop the host_path existence guard; exclude curated from `manifest_digest`. Four-state verdict (RED/GREEN/ANCHOR-MISS/WRONG-TEST); GREEN means guard defect.
3. WHERE OnlyOffice runtime is unavailable THE browser-level proof of a curated bidirectional entry SHALL be recorded `UNVERIFIABLE`, not implementation failure.
