# Task 21 — Directed verification + four-state mutations

**Date:** 2026-09-08  
**Spec:** platform-architecture-convergence

## Directed tests

| Lane | Command / suite | Result |
|---|---|---|
| Backend | `pytest` capability / wire / planner / startup / events / domain (9 files) | **121 passed** |
| Frontend | `FrontendReferenceIntegrity` + `routeDomainProjection` + `registrySplitEquivalence` + `GtWpRenderer.real-registry.contract` | **39 passed** |
| Mutation baseline | be 55 passed / fe 34 passed | clean |

## Typecheck / build

- Full-repo `vue-tsc --noEmit` / `npm run build`: **OOM** at 8GB heap (known platform limit; same as writeback-closure / procedure-trim notes).
- Isolated probe: `npx vue-tsc --noEmit -p tsconfig.pac-t21.json` covering `renderConfig` wire + `auth` domain + `pacNetworkGate` → **exit 0** (broader domain/.vue include OOMs under isolated program; full domain projection = Vitest).
- CI job `pac-skeleton-typecheck` also runs `vitest run src/__tests__/pacNetworkGate.spec.ts`.

## Mutations (`mutate_pac_platform_architecture_guards.py`)

- Anchors: **11/11 OK**
- Run: **RED 11/11**, guard coverage 9/9 files
- Report: `basis/T21-mutation-report.json`
- 复核 §7 扩充：M09/M10/M11 为此前只有测试内 reverse-check 的三条守卫补外部锚点；
  collision(Req 11.4) 由 registrySplitEquivalence/registryDomainSplit 的常驻 PBT/duplicate
  reverse-check 覆盖（barrel 在 Map 前 assertUnique，注入重复键在 import 期抛错=suite-level，
  不适合单锚点），已在脚本内注明。

| Id | Side | Want | Req | Verdict |
|---|---|---|---|---|
| M01 | be | stage swap → `test_swapping_adjacent_stages_would_red` | 4.1 | RED |
| M02 | be | whitelist literal in plan_sheets | 4.4 | RED |
| M03 | be | idempotency → `trace_id.like` | 9.1 | RED |
| M04 | be | unawaited `event_bus.publish` | 9.3 | RED |
| M05 | be | reverse frozen startup sequence | 5.3 | RED |
| M06 | be | rename domain-boundary CI job | 7.7 | RED |
| M07 | fe | second `beforeEach` | 10.2 | RED |
| M08 | fe | restore `startsWith`/`classifyDomain` | 11.1 | RED |
| M09 | be | replay actor ← request-body `operator_id` | 9.6 | RED |
| M10 | be | drop `name` from startup report dict | 6.2 | RED |
| M11 | fe | duplicate route domain spread | 10.3 | RED |

## Generator fix (Task 20 follow-up → gate hardening)

`generate_component_capability_manifest.extract_html_registry_types` **only** accepts domain-split `registry/entries/*.ts` + `...*Entries` spreads. Legacy `D_FORM_SUBTYPES.map` monolith path is **removed** (synthetic fixtures must use domain-split layout).
