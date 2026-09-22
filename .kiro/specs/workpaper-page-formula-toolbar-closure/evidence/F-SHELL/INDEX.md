# F-SHELL INDEX

**Overall:** PASS  
**inventoryDigest:** `8134c0d843841df847d7347b8eac3821eb690aa0bb9a2aca71103b7307e3158f`  
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
| raw duplicate hits | 19 |
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

`903c484cb61629f671e7b3754c9464a0530bf5cf820e53b1931d7343c3bdcefe`
