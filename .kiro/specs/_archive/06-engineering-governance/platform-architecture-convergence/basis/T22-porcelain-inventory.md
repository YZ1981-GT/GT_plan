# T22 — PAC formal-products git porcelain inventory

**Date:** 2026-09-08 · **Satisfies Req 12.7** (`git status --porcelain` 核对本 spec 全部产物是否 tracked，`??` 项必须登记).

## Why this file exists

Req 12.7 requires every PAC product's git state to be scanned and each `??`
登记. T22 closure previously said "See closure scan in tasks.md / INDEX" but never
listed the paths. **This is the only artifact that can reconstruct the product set
after a working-tree loss** — losing the tree loses all 53 untracked products.

Reproduce: `python backend/scripts/diagnose/pac_porcelain_inventory.py`

## Headline

- **55 formal products** tracked in this inventory (incl. this reproducer).
- **54 `??` untracked** — the entire PAC surface lives only in the working tree.
- **1 tracked-modified** (`registrySplitEquivalence.pbt.spec.ts`).
- **Plus 4 tracked-modified shared files** the CI jobs / runtime depend on (below).
- No commit/push performed (user did not request). This inventory does **not**
  authorize a commit — it makes the loss risk auditable.

## 🔴 CI wiring vs untracked products (must ship together)

`.github/workflows/governance-checks.yml` is **tracked-modified (` M`)** and its
`domain-boundary-governance` job runs `test -f` on four files that are all `??`:

| CI-referenced file (job `domain-boundary-governance`) | git state |
|---|---|
| `docs/architecture/domain-boundaries.json` | `??` |
| `docs/architecture/DOMAIN_DEBT_BURNDOWN.md` | `??` |
| `backend/scripts/check/baselines/domain-boundary-debt.json` | `??` |
| `backend/scripts/check/check_domain_boundaries.py` | `??` |
| `backend/tests/scripts/test_check_domain_boundaries.py` | `??` |

`pac-skeleton-typecheck` job → `audit-platform/frontend/tsconfig.pac-t21.json` (`??`)
+ `src/__tests__/pacNetworkGate.spec.ts` (`??`) + its helper (`??`).

**Consequence:** committing the tracked yml without these `??` products makes both
jobs fail on a clean checkout. They must enter the index in the same commit.

## Untracked products by control-plane (53 × `??`)

### spec 三件套 + basis (4)
- `.kiro/specs/platform-architecture-convergence/{requirements,design,tasks}.md`
- `.kiro/specs/platform-architecture-convergence/basis/` (incl. this file, T01/T04/T06/T21/T22/T23 + T22-playwright/)

### render control-plane (19)
- `backend/app/data/component_capabilities.json`, `component_host_declarations.json`
- `backend/app/services/component_capability_registry.py`
- `backend/scripts/gen/generate_component_capability_manifest.py`
- `backend/scripts/check/check_component_capabilities.py`, `check_render_config_wire_contract.py`
- `backend/scripts/diagnose/capture_render_config_wire_golden.py`
- `backend/app/schemas/render_config_contract.py`
- `backend/app/routers/wp_render_pipeline.py`
- `backend/tests/fixtures/platform_architecture/` (wire golden — needed by wire-contract test)
- `backend/tests/test_component_capability_contract.py`, `test_render_config_wire_contract.py`,
  `test_render_config_pipeline_characterization.py`, `test_render_pipeline_stage_guards.py`,
  `test_wp_classification_pipeline.py`, `test_render_config_sheet_context.py`
- `audit-platform/frontend/src/types/renderConfig.ts`, `componentCapabilities.generated.ts`, `types/__tests__/`
- `audit-platform/frontend/src/components/workpaper/WpDecisionTracePanel.vue`
- `audit-platform/frontend/src/components/workpaper/GtWpRenderer.real-registry.contract.test.ts`

### startup control-plane (2)
- `backend/app/core/startup_registry.py`, `backend/tests/test_startup_registry.py`

### governance control-plane (6)
- `docs/architecture/domain-boundaries.json`, `DOMAIN_DEBT_BURNDOWN.md`
- `backend/scripts/check/check_domain_boundaries.py`, `baselines/domain-boundary-debt.json`
- `backend/tests/scripts/test_check_domain_boundaries.py`
- `.kiro/steering/domain-boundaries.md`

### event control-plane (4)
- `backend/app/core/events/` (envelope.py, adapters.py)
- `backend/tests/test_canonical_event_envelope.py`, `test_task_event_bus_idempotency_auth.py`,
  `test_event_call_site_guards.py`

### frontend assembly (5 untracked + 1 tracked-modified)
- `audit-platform/frontend/src/router/domains/` (11 files)
- `audit-platform/frontend/src/router/__tests__/`
- `audit-platform/frontend/src/components/workpaper/registry/entries/` (6 files, 216 entries)
- `audit-platform/frontend/src/components/workpaper/__tests__/registryDomainSplit.spec.ts`
- `backend/scripts/gen/split_html_renderer_registry_domains.py`
- **tracked-modified:** `.../__tests__/registrySplitEquivalence.pbt.spec.ts`

### verification / mutation / e2e (11)
- `backend/scripts/diagnose/mutate_pac_platform_architecture_guards.py`,
  `_freeze_pac_t01_baseline.py`, `probe_platform_baseline.py`, `_pac_t19_t20_probe.py`, `_pac_t22_resolve_wps.py`
- `backend/scripts/diagnose/pac_porcelain_inventory.py` (this inventory's reproducer)
- `backend/tests/scripts/test_pac_skeleton_typecheck_ci.py`
- `audit-platform/frontend/tsconfig.pac-t21.json`
- `audit-platform/frontend/e2e/platform-architecture-convergence.spec.ts`
- `audit-platform/frontend/src/__tests__/pacNetworkGate.spec.ts`, `_helpers/pacNetworkGate.ts`, `pac-t21-typecheck-probe.ts`

## Tracked-modified shared files touched by PAC (precise-merge zones, not owned)

| File | Role for PAC |
|---|---|
| `.github/workflows/governance-checks.yml` | hosts `domain-boundary-governance` + `pac-skeleton-typecheck` jobs |
| `backend/app/routers/wp_render_config.py` | seven-stage orchestrator + `response_model` binding + host_policy projection |
| `backend/app/routers/wp_classification.py` | reuses common classification core |
| `backend/app/main.py`, `backend/app/api/health.py` | startup registry executor + `health.startup` |
| `backend/app/services/{task_event_bus,event_bus,independence_signing_service,review_workflow_service}.py`, `backend/app/routers/{adjustments,dispatch_records,s_transaction_calculation,task_events}.py` | event idempotency / call-site / auth fixes |
| `audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue`, `htmlRendererRegistry.ts`, `registry/index.ts`, `composables/useWpRenderer.ts`, `router/index.ts`, `views/WorkpaperEditor.vue`, `components/workpaper/WorkpaperSidePanel.vue` | renderer/route assembly + decision-trace consumption |

## Cleanup note

Non-product diagnostics to remove at session end (not part of the 54):
`audit-platform/frontend/.pac-t21-vitest-mutation.json`, `audit-platform/frontend/scripts/_tmp/`,
root `tmp_*` from review sessions.
