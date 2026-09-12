# F-SHELL INDEX

**Overall:** PASS  
**inventoryDigest:** `cb788c0c01b286f7af07e7c7e680eda4db41c89a16fb9fba27dd6a46a7e9301e`  
**Generated:** 2026-09-09T00:30:00.000Z  
**Producer tasks:** 13 (publish) → 15 (inventory pin / archive gate)

## Host denominator

| Host | Status | Detail |
|---|---|---|
| html | reachable | B50-1 |
| univer | reachable | A1-13 |
| onlyoffice | reachable | A14-4 |
| grid | exempted | grid_host_absent_from_registry_and_project_inventory |
| word | reachable | A26-1 |

## Counts

| Metric | Value |
|---|---|
| inventory entries | 216 |
| domain exclusions | 6 |
| raw duplicate hits | 15 |
| forbidden duplicates | 0 |
| legacy findings | 0 |
| stale evidence | 0 |
| blockers | 0 |

## Owners

| Surface | Owner |
|---|---|
| FormulaManagerDialog (workpaper route) | ThreeColumnLayout |
| AI assist | DSH / ThreeColumnLayout |
| AI review | GtWpAiReviewToolbar |
| Guidance rail | WorkpaperCapabilityShell + WpGuidancePanel |
| Human review rail | WorkpaperCapabilityShell (GtWpReviewRail suppressed) |
| Grid host (absent) | T15-grid-host-exemption |

## Blockers

_none_

## Re-run

```bash
cd audit-platform/frontend
npx vitest run src/shell/formula/__tests__/fullInventoryGate.spec.ts src/shell/formula/__tests__/fShellConformance.spec.ts
python ../../backend/scripts/diagnose/mutate_formula_task15_closure.py
SKIP_E2E_SEED=1 npx playwright test e2e/workpaper-formula-toolbar-shell.spec.ts --workers=1
```

## Evidence SHA

`b696f9039f8a7c5bd36d3b51ac1dd3a71dcdb3d2918a954f51515a3a49b786fa`
