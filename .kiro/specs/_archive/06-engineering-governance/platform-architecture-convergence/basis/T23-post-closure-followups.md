# PAC post-closure follow-ups (non-PAC expansion)

**Date:** 2026-09-08 · Spec remains **22/22 closed**. These items are **neighbor-owned** or **ops process** — do **not** reopen PAC to invent UI / clear reserved by fake consumers / silent baseline growth.

## 1. Frozen-then vs live-now (read before archive/commit)

Machine freeze: `basis/T01-platform-skeleton-baseline.{json,md}` (Task 1 capture).  
Live row: section **「冻结当时 vs 现网」** in that markdown + INDEX PAC row.

| Topic | T01 freeze (then) | Live now (after PAC Tasks 9–22) |
|---|---|---|
| Domain debt baseline | not yet established as PAC product | **905** / **905** (904 forbidden_edge + 1 SCC cycle; `check_domain_boundaries.py` OK, new=0), down from 4761. Baseline file 2.0 MB → ~345 KB after SCC cycle-identity fix. Figures ~**5349 / 4761 / 1042 / 1024** are **obsolete**. |
| TaskEvent idempotency | publish hash + **`trace_id.like`**; column present unused | **`idempotency_key` equality** write/query; mutation M03 RED if reverted to `trace_id.like` |
| `decision_trace` | reserved (wire list) | **active** (`WpDecisionTracePanel`) |
| Reserved wire roots | scope / guidance / sign_status / permissions / decision_trace | **scope / guidance / sign_status / permissions** only |
| Router / registry | monolith | `router/domains/*` + `registry/entries/*` (216) |
| Confirmation mount | N/A at freeze | **light-stub** still (`confirmation-light-stub`); deep mount = follow-on |

## 2. Remaining reserved fields — neighbor ownership (no PAC UI)

| Field | Consumer owner | PAC rule |
|---|---|---|
| `guidance` | `workpaper-guidance-content-closure` | Keep reserved until real panel consumes wire; PAC e2e already names `/guidance` as concurrent WIP exemption only |
| `sign_status` | signing / independence / word-template sessions | Do not add decorative FE binding |
| `permissions` | auth / session / edit-lock consumers | Same |
| `scope` | project/entity scope session (standalone vs consolidated) | Same |

**Forbidden:** inventing a PAC-only widget solely to flip `reserved` → `active`.

## 3. Mount depth — batch smoke (post-PAC)

AC “active frontend capability truly mounts” is **not** literal-complete for all 216 registry entries while confirmation stays light-stub.

Suggested batches (new spec or renderer follow-on — **not** PAC reopen):

1. **forms** (5× `d-form-*`) — shared `GtDForm`, cheap
2. **core** — high-traffic HTML leaves
3. **confirmations** — replace light-stub with real summary/hub; keep heavy leaves behind **digest-backed exemption** in capability manifest
4. **programs / reports / specialized** — sample + exemption for OO/Univer-heavy

Gate: real registry → visible host (not string stub); exemptions require owner + reason + source digest.

## 4. Domain debt 905 (was 4761) — block-new done; two-axis redesign is the burn-down

- Checker + CI **block new** identities. Policy-correction cleared the base-layer
  false debt; **cycle identity switched to SCC node-set** (Tarjan, stdlib) — 120
  path-cycles → 1 SCC, baseline file 2.0 MB → ~345 KB, no more 83-new/85-resolved
  churn on one edge change (review §4).
- **Residual 905 = two-axis conflation** (397 `→backend-services` catch-all,
  ~279 backend↔frontend cross, ~228 other, **1 SCC cycle** = one big layer-blob).
  Fix = split layer axis (routers→services→core, no reverse) from business-domain
  axis; that collapses the SCC. **Separate redesign spec**, not a PAC reopen.
- **Provisional `frontend-shell/shared → formula`** allowances for concurrent
  `shell/formula/**` WIP — documented, owned by that session, to be removed when
  `shell/**` becomes its own host-adapter lane. Not silent `--write-baseline`.
- Rule: **new import → update `paths` / `may_depend_on` first → then code**.
