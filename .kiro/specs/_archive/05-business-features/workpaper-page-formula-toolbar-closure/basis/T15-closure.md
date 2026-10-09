# T15 closure + retrospective

**Verdict:** PASS (2026-09-09)  
**inventoryDigest:** `307b400a64de83ff6aeaa96de16cdff59c43b264479155f4e527544cac59d551`

## Gate results

| Check | Result |
|---|---|
| Hosts html/univer/onlyoffice/word | reachable (T14 matrix) |
| Host grid | exempted (`basis/T15-grid-host-exemption.json`) |
| Forbidden capability duplicates | 0 |
| Legacy cleanup (production) | 0 |
| Stale evidence | 0 (Word T12 exemption superseded) |
| F-SHELL `inventoryDigest` | pinned non-null |
| Mutations | 3/3 RED (`basis/T15-mutation-report.json`) |
| Directed | fShellConformance 15 + fullInventoryGate 2 |

## Retrospective fixes applied

1. **Scanner false positives** — formula-entry no longer matches “四表取数（公式管理）” labels; AI assist requires real DSH mount; AI review excludes A171 chapter panels; fixed-offset limited to capability-rail carriers; `__tests__` excluded from production carrier scan.
2. **Audit warn scanner** — stopped matching `audit_warning_then_commit` identifier lists; requires `warn-then-commit` / AuditCommitError patterns.
3. **Browser crypto crash class** — `sha256Hex.ts` + `outletSlots.ts`; primary outlet host no longer imports inventory.
4. **Word exemption** — marked `supersededBy` T14 live A26-1.
5. **Grid** — formal exemption (absent from registry/inventory), stays in denominator.
6. **F-SHELL envelope** — Task 15 backfills `inventoryDigest` (was null since T13).

## Honest residuals (owned, not false-green)

| Item | Disposition |
|---|---|
| `outletBaseline.primaryNamedOutletMounted=false` in static inventory | Telemetry is runtime-mounted; Playwright/T14 proved live outlets. Static gate records truth. |
| GtWpReviewRail still present on D-cycle sheets | Self-suppresses under shell (`WORKPAPER_SHELL_ACTIVE_KEY`); adjudicated `allowed_delegate`. |
| AiAssistantSidebar.vue orphan | Not mounted in production; tightened AI scanner no longer flags it. Consider delete in a cleanup PR. |
| OnlyOffice/Word Playwright 503/404 console | Document/service noise; no `pageerror`; recorded in T14 evidence. |
| Spec dir not yet moved to `_archive/` | Progress 15/15; physical archive can follow once git tracks formal artifacts. |

## Re-run

```bash
cd audit-platform/frontend
npx vitest run src/shell/formula/__tests__/fullInventoryGate.spec.ts src/shell/formula/__tests__/fShellConformance.spec.ts
python ../../backend/scripts/diagnose/mutate_formula_task15_closure.py
SKIP_E2E_SEED=1 npx playwright test e2e/workpaper-formula-toolbar-shell.spec.ts --workers=1
```
