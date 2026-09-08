# Domain Boundary Debt Burn-down

Owner process for `docs/architecture/domain-boundaries.json` +
`backend/scripts/check/baselines/domain-boundary-debt.json`.

**Live baseline (2026-09-08, post policy-correction + SCC cycle fix):** **905**
identities (904 forbidden_edge + **1 SCC cycle**), current=baseline, new=0.
Down from **4761**. Baseline file shrank **2.0 MB → ~345 KB** because cycle
identities are now strongly-connected-component node-sets, not giant rotated
path strings (see "cycle identity" below). Obsolete figures **~5349 / 4761 /
1042 / 1024** must not be restored.

### Cycle identity = SCC node-set (review §4 fix)

`detect_domain_cycles` now reports one identity per **strongly-connected
component** (`cycle:<sorted,member,domains>`), not one per rotated DFS path.
Path-string identities exploded combinatorially: a single edge add/remove
rewrote the identity of every giant cycle through it, so one real change showed
as dozens of new/resolved cycles (observed 83-new/85-resolved for a net −2, and
a 2.0 MB baseline). An SCC identity changes only when the set of mutually
reachable domains actually changes. 120 path-cycles collapsed to **1 SCC**
(one big blob of layer-conflated domains — the thing the two-axis redesign must
break). Tarjan, stdlib-only, no new dependency.

### 2026-09-08 policy-correction burn-down (4761 → 905, cleared ~3856)

These were **policy-modeling gaps, not real debt** — feature domains that own
frontend components legitimately import the frontend base layer, and the render
domain legitimately calls services. Added `may_depend_on`:

- `frontend-shared` added to every FE-owning feature domain: `workpapers`,
  `workpaper-rendering`, `reports`, `notes`, `formula`, `import-export`,
  `consolidation`, `qc-review`, `ai`, `evidence`, `procedures`, `four-table`,
  `backend-workers` (base-layer `@/utils` `@/stores` `@/composables` `@/types`).
- `workpapers → frontend-features` (FE workpaper hub cross-imports feature views),
  `workpaper-rendering → backend-services` (renderer calls services).
- Owned newly-added `src/shell/formula/**` under `formula`; `formula →
  workpaper-rendering` + `formula → frontend-features` (host inventory scans the
  renderer registry and workpaper components).
- **Provisional shell-consumption allowances (concurrent-WIP, must be revisited):**
  `frontend-shell → formula` and `frontend-shared → formula`. A concurrent session
  is growing `src/shell/formula/**` (host-adapter layer: toolbar arbiter, provider
  registry, capability host) consumed by a layout and a shared composable
  (`useReviewDialog → humanReviewProvider`). `frontend-shared → formula` is a
  base→feature smell; the correct fix is to extract `shell/**` as its own
  host-adapter lane (or into `frontend-shared`) owned by that session. Recorded
  here so the checker isn't permanently red on active WIP — **not** a silent
  `--write-baseline`. Owner: formula-toolbar / shell session.

### Residual 905 = the two-axis problem (needs a dedicated redesign spec)

| Bucket | Count | Root cause |
|---|---|---|
| `X → backend-services` | 397 | `backend-services` is a `services/**` catch-all "layer" masquerading as a domain; sideways service calls have nowhere clean to point |
| backend ↔ frontend cross | ~279 | several domains (`workpapers`, `qc-review`, …) own **both** `backend/app/**` and `frontend/src/**` paths — layer and business axis are conflated on one plane |
| other forbidden | ~228 | mixed |
| cycle (SCC) | 1 | one strongly-connected blob of layer-conflated domains: `core → backend-routers` + `backend-routers → core` etc. are declared reverse edges. Adding allowances does **not** remove it (edges exist regardless of allow-list) — only the two-axis split (layer policy with no reverse edges) collapses it. |

**Do not** paper these over with `--write-baseline` or fake exemptions. The clean
fix is a two-axis model (layer policy: routers → services → core, no reverse;
domain policy: business-domain cross-deps) — tracked as a follow-on redesign, not
PAC. Until then CI correctly blocks *new* identities on top of 1024.

## Rules

1. **CI fails only on new identities.** Shrinking debt is allowed and preferred.
2. **Import order (hard):** before adding a cross-domain import, update
   `paths` and/or `may_depend_on` in `domain-boundaries.json`, then write code.
   Do not land the import first and “fix ownership later.”
3. After intentional ownership / `may_depend_on` fixes that remove historical edges, run:
   ```bash
   python backend/scripts/check/check_domain_boundaries.py --write-baseline
   ```
   and commit the baseline with the ownership change (same PR).
4. **Never** `--write-baseline` solely to absorb concurrent WIP imports. Adjudicate path ownership or `may_depend_on` first.
5. New routers: register via `backend/app/router_registry/**` (domain `backend-routers`). Do not put registry under `core`.

## Owner SLA (suggested)

| Cadence | Expectation |
|---|---|
| Every PR touching `backend/app` or `audit-platform/frontend/src` | checker exit 0; no silent baseline growth |
| Per active domain owner (weekly) | at least one intentional debt shrink **or** documented blocker (file → owning path / port) |
| Quarterly | publish top 10 domain-pair counts; retire catch-all paths (`backend-services` → specialty packages) |

Progress = baseline entry **count trend down**, not silenced CI.

## PR checklist (copy into PR body)

- [ ] New/changed imports: `paths` / `may_depend_on` updated **before** code (or N/A)
- [ ] `python backend/scripts/check/check_domain_boundaries.py` exits 0
- [ ] If HINT says debt shrank: baseline updated in this PR
- [ ] If new forbidden edge: ownership change documented in PR (not silent baseline growth)
- [ ] Domain owners listed in manifest for touched domains

## Quarterly burn-down (suggested)

| Domain pair | Focus | Owner |
|---|---|---|
| `backend-services` → specialty domains | replace broad `services/**` catch-all with explicit packages | platform |
| `frontend-shell` → feature domains | keep router assembly thin | frontend |
| cycles | break with ports/adapters, not exemptions | architecture |

See also PAC handoff: `.kiro/specs/platform-architecture-convergence/basis/T23-post-closure-followups.md`.
