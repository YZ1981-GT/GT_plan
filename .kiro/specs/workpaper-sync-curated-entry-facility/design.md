# Design — Workpaper Sync Curated-Entry Facility

## Overview

Add an additive `curated_entries` section to the reviewed overlay and teach `generate_workpaper_sync_manifest.build_manifest` to emit synthetic entries from it. The facility rides on top of the existing discovery pipeline: discovery entries are built first (unchanged), then curated entries are appended with the same validation, profile derivation constraints, digest participation, and fail-closed capability discipline. When no curated entry is declared, output is byte-identical.

Motivating consumer: D4-9 (`d4.customer_structure` adapter, `xlsx/gt-d4-customer-structure` entry) on shared host `GtD4OperatingRevenue.vue`.

## Architecture

### 2.1 Data flow (unchanged parts in gray)

```
discover_source()  ──► discovery mounts/dispatchers ──► _group_source_facts ──► discovery entries
                                                                                      │
overlay.curated_entries ──► _build_curated_entries(overlay, discovered_hosts) ────────┤
                                                                                      ▼
                                                        merge + collision gate + digest + validate
                                                                                      ▼
                                                        manifest.json + generated.ts
```

### 2.2 Overlay shape (additive)

```jsonc
{
  "schema_version": 1,
  "review_status": "reviewed",
  "approved_source_digest": "…",              // unchanged, governs physical mounts only
  "defaults_by_component": { … },              // unchanged
  "curated_entries": [                          // NEW, optional
    {
      "entry_id": "xlsx/gt-d4-customer-structure",
      "host_path": "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue",
      "curated_reason": "one dynamic GtOnlyOfficeSheet host backs D4-1/2/3/9; D4-9 needs its own contract+adapter",
      "document_type": "xlsx",
      "wp_match": { "wp_code_patterns": ["D4-9"], "component_types": [], "sheet_literals": ["重要客户结构分析D4-9"], "sheet_expressions": [], "source_host": "…" },
      "html_store": "D4-9-data",
      "canonical_resolver": "d4_customer_structure_projection",
      "adapter_id": "d4.customer_structure",
      "capability": "bidirectional",
      "migration_state": "curated_bidirectional",
      "expected_profile": {
        "editability": ["editable"],
        "room_model": ["shared"],
        "scenario_profile_ids": ["xlsx.editable.shared.single.room_service_wired.v1"]
      },
      "profile": { "editability": "editable", "room_model": "shared", "scenario_profile_id": "xlsx.editable.shared.single.room_service_wired.v1" },
      "evidence": {
        "review_status": "curated_reviewed",
        "contract_test": "backend/tests/workpaper_sync/test_d4_9_task3_contract.py",
        "browser_case": null,
        "legacy_reasons": []
      }
    }
  ]
}
```

Rationale for an explicit `profile` block on curated entries: discovery derives profile from AST facts via `entry_source_facts.derive_entry_profile(host_facts)`, but a curated entry has no discoverable second mount to derive from. So the curated declaration states its profile explicitly AND is validated against its own `expected_profile` (Requirement 2.3) — the two-way lock still holds, it just uses declared-vs-reviewed instead of derived-vs-reviewed. This keeps the "reviewer approved this exact value" invariant.

## Components and Interfaces

### Generator changes (`generate_workpaper_sync_manifest.py`)

### 3.1 New constants and validation

- `_CURATED_MIGRATION_STATES = {"curated_bidirectional", "curated_single_html", "curated_single_onlyoffice"}`.
- `_REQUIRED_CURATED_FIELDS` = the field set above.

### 3.2 `_build_curated_entries(overlay, *, discovered_host_paths, discovery_entry_ids) -> list[dict]`

For each declaration:
1. Validate required fields present; unknown keys rejected.
2. `entry_id` must not be in `discovery_entry_ids` nor duplicate another curated id (Requirement 1.4).
3. `host_path` must be in `discovered_host_paths` (Requirement 1.5).
4. `capability` in `_CAPABILITIES`; if `bidirectional`, require non-empty `adapter_id`, `html_store != "unresolved"`, `evidence.contract_test`, `evidence.review_status` (Requirement 2.2).
5. `evidence.review_status` non-empty else fail (Requirement 2.4).
6. Validate declared `profile` against `expected_profile` reusing the same field-membership logic as `_assert_expected_profile` (extract a shared helper `_assert_profile_in_expected(entry_id, profile_values, expectation)`).
7. Build the entry dict with `independent_entry=True`, `parent_entry_id=None`, `mounts=[]` (curated entries carry no template_ast mounts, so they do not participate in the `manifest_mount_ids == source_mount_ids` check — that check filters `sourceKind == "template_ast"`, which curated `mounts=[]` never contributes).

### 3.3 Integration in `build_manifest`

- After the discovery loop and after the stale-rule gates, call `_build_curated_entries` and extend `entries`.
- Add `curated_source_digest = _curated_source_digest(overlay.get("curated_entries") or [])` to the manifest dict BEFORE computing `manifest_digest` (Requirement 3.1) so it participates.
- Collision gate: assert curated entry_ids disjoint from discovery entry_ids (redundant with step 2 but enforced at merge for defense).
- Stats: curated entries count toward `entry_count`, `independent_entry_count`, `capability_counts`, profile counts. Add `curated_entry_count` to stats.

### 3.4 `_curated_source_digest(curated) -> str`

Stable JSON over the sorted curated declarations, sha256. Empty list ⇒ digest of `[]` ⇒ still deterministic; but to guarantee Requirement 1.3 byte-identity with the pre-facility manifest, `curated_source_digest` is only added to the manifest dict WHEN `curated` is non-empty. When empty, the key is omitted so the manifest bytes match the current output exactly.

## Data Models

### Curated declaration model

Each `curated_entries[]` element is an object with keys: `entry_id`, `host_path`, `curated_reason`, `document_type`, `wp_match`, `html_store`, `canonical_resolver`, `adapter_id`, `capability`, `migration_state`, `expected_profile`, `profile`, `evidence`. The emitted manifest entry mirrors the discovery-entry schema so downstream consumers (registry, frontend projection) treat both uniformly. `curated_source_digest` is a sha256 over the stable-JSON of the sorted curated declarations.

## Registry / consumption

No registry code change required: curated entries have the same shape as discovery entries, so `attach_adapters` selects them by `entry_id` + capability. RG-4 uniqueness is preserved because curated ids are gated disjoint from discovery ids. The frontend projection in `render_frontend` iterates `manifest["entries"]` uniformly, so curated entries render without special-casing.

## 5. D4-9 wiring (spec `d4-9…` Task 6 unblocked)

1. Add the D4-9 curated declaration to the overlay (capability `bidirectional`, adapter `d4.customer_structure`, contract-test evidence pointing at the delivered `test_d4_9_task3_contract.py`).
2. Regenerate manifest (`--apply`), verify `entry_count` +1 and the new entry present.
3. D4-9 `attach_adapters`/`assert_manifest_capability_enabled` now resolves the curated entry; `assert_entry_selectable` passes.
4. Browser proof (Task 13/15) remains `UNVERIFIABLE` on this machine (no OO runtime).

## Error Handling

All validation failures raise `ManifestGenerationError` (fail closed): missing required curated fields, unknown keys, entry_id collision, non-existent host_path, invalid/unreviewed capability, bidirectional without adapter/evidence, and profile-vs-expected mismatch. The generator never emits a partial or guessed curated entry.

## Testing Strategy

- `test_curated_entry_facility.py`: run real `build_manifest` with empty curated ⇒ assert byte-identity to a captured baseline; with a synthetic curated declaration ⇒ assert emission, digest change, stats. Fail-closed cases: collision, missing host, bidirectional-without-adapter, unreviewed, profile mismatch.
- Mutation script `mutate_curated_entry_facility_guards.py`: ≥4 anchors (Requirement 5.2), four-state verdict.
- D4-9 side: extend existing D4-9 registry/attach guard to assert the curated entry resolves `d4.customer_structure`.

## Correctness Properties

### Property 1: Empty case byte-identity
With `curated_entries` empty or absent, `build_manifest` output (manifest JSON + frontend TS) is byte-identical to the discovery-only baseline.
**Validates: Requirements 1.3**

### Property 2: Bidirectional discipline
A curated declaration with `capability=bidirectional` but missing adapter_id, html_store, or contract-test evidence causes `build_manifest` to raise ManifestGenerationError.
**Validates: Requirements 2.2**

### Property 3: Collision and host gates
A curated entry_id equal to any discovery entry_id, or a curated host_path not produced by discovery, causes fail-closed.
**Validates: Requirements 1.4, 1.5**

### Property 4: Digest determinism
Adding/removing/editing a curated declaration deterministically changes manifest_digest and curated_source_digest; the empty case omits curated_source_digest.
**Validates: Requirements 3.1, 3.3**

### Property 5: Registry compatibility
A curated bidirectional entry is selectable in the registry and attaches its adapter under RG-4; a non-bidirectional curated entry fails adapter attach closed.
**Validates: Requirements 4.1, 4.3**

### Property 6: Mutation coverage
Mutation anchors (allow bidirectional w/o adapter, drop collision gate, drop host existence gate, exclude curated from digest) all go RED.
**Validates: Requirements 5.2**
