# T14 Playwright closure — F-SHELL host/viewport evidence

**Verdict:** PASS  
**Recorded:** 2026-09-08  
**Suite:** `audit-platform/frontend/e2e/workpaper-formula-toolbar-shell.spec.ts` (4/4)

## Denominator

| Host | Status | Representative | Notes |
|---|---|---|---|
| html | reachable | B50-1 | shell + 3 rails + primary/compat outlets |
| univer | reachable | A1-13 | shell + 2 triggers; compat not mounted |
| onlyoffice | reachable | A14-4 | shell mounts; OO document 503/404 noise recorded |
| grid | skipped | — | no reachable representative this run |
| word | reachable | A26-1 | live Word path (T12 exemption unused) |

## Assertions covered

- Auth seed: sessionStorage `token`/`refreshToken`/`user` (login redirect fail-closed)
- Shell mount: `[data-testid="workpaper-capability-shell"]` on each reachable host
- Capability snapshot network hit
- Single-open guidance rail + Escape close
- Formula dialog uniqueness ≤ 1
- Viewports 1280 / 1440 / 1920 screenshots per reachable host
- C0-shaped envelope `basis/T14-playwright/envelope.json`

## Runtime blockers fixed during T14

1. Inject key typo: importers used `WORKOBPER_*` while export was `WORKPAPPER_*` → standardized to `WORKPAPER_SHELL_ACTIVE_KEY` (WORK+PAPER).
2. Browser crash: `ThreeColumnLayout` → primary outlet host → `workpaperHostInventory` pulled `node:crypto`. Slot constants moved to crypto-free `outletSlots.ts`.

## Artifacts

- `host-matrix.json`
- `host-run-results.json`
- `keyboard-escape.json`
- `envelope.json`
- `*-{1280,1440,1920}.png` per reachable host
- Spec: `e2e/workpaper-formula-toolbar-shell.spec.ts`

## Residual (honest, not false-green)

- Grid skipped (no inventory hit)
- OnlyOffice/Word host console includes 503/404 resource loads (document/service); no `pageerror`
- Full sheet/cell rapid-switch + v2 conflict matrix deferred to T15 inventory gate / directed follow-ups where not exercised live here
