# S-Cycle P0 Implementation Plan (Tasks 1-19)

> **Correction (planner re-check, 2026-10-25 18:2x–18:4x).** The first version of this file and the
> plan step's output said "zero divergences". That was wrong. A second pass that read HEAD code, ran
> SQL against the dev DB, and opened the S templates (xlrd for the `.xls`) found the divergences and
> defects in section B and section D. FEAT-001 (`e383f4069`), FEAT-002 (`1517804a3`) and FEAT-003
> (`0da7d5905`) were committed before this correction landed, so **section D lists defects that are in
> HEAD now and must be fixed by the convergence loop**. Reviewer: treat every D item as a required
> finding until its verification passes.

## A. Workflow state when this was written

| Step | Commit | Scope delivered |
|---|---|---|
| FEAT-001 | `e383f4069` | Tasks 1-9: 4th match path, biz_ flags, `_WP_APPLICABLE_WHEN` (path correct at HEAD), render-config `applicable_when`, GtWpRenderer overlay (defective, see D1/D2), ipoProjectUtils + tests, useAProgramData dict branch, D4 wrapper kept (see D7) |
| FEAT-002 | `1517804a3` | Tasks 12-15: overrides group A/B, 12 registry types + entries, registry spec. No backend renderer (see D3), components unfixed (D4), S17 mapping per wrong design table (D5) |
| FEAT-003 | `0da7d5905` | Tasks 17-18: resolveProcedureSheetKey S segment + `resolveProcedureSheetKey.s-cycle.spec.ts` |

Side effect to clean up in finalize: FEAT-001/002/003 commits include `.agents/tasks/s-cycle-p0-impl-2026-10-25/features/FEAT-00x.json`
(`.agents/` is not gitignored). Do not add more `.agents/` files; remove the tracked ones with `git rm --cached` only if the user agrees.

## B. On-disk state vs design (baseline `779d8b436`)

| Design assumption | Verified state | Divergence |
|---|---|---|
| §1.1 `match_workpapers` has 3 paths | True at baseline | none |
| §1.2 SELECT lacks `business_category`; `Project.industry`? | True; `Project.industry` does not exist (core.py) | industry flags always empty (design accepts) |
| §1.3.2 mapping at `Path(__file__).parent.parent / "data"` (= `backend/app/data/`) | That file does not exist; real file `backend/data/wp_account_mapping.json` (1025 entries, 107 with `applicable_when`: 91 business_category, 16 industry) | **design path wrong**; HEAD uses `parent.parent.parent` = correct |
| §1.3.2 frontend compares project `business_category` | render-config top level has no `project_context`; project store has no business_category; render-config already loads it as `_prog_biz` (`PROJECT_AUDIT_YEAR_BIZ_SQL`, default "C") | **data source unspecified** → D2 |
| §1.2 `biz_listed` also true when `template_type == 'listed'` | frontend overlay ignores template_type | **parity gap** → D2 |
| Real `business_category` values | SQL: NULL ×76, 'C' ×8, 'IPO' ×1 (all soe). Existing S32 ×2, S34 ×1, S35 ×7 workpapers are all in 'C' projects | after the fix these show「不适用」(intended trimming, user-visible on real projects) |
| §1.5 12 orphans wire by overrides + registry only | Live render-config (`_get_render_config_impl`) rewrites multi-sheet renderer-less types not in `_ONLYOFFICE_HTML_WHITELIST` to `onlyoffice-sheet`; whitelisted renderer-less types get template grid `cells` → GtWpRenderer `noRendererGridFallback` shows GtGridSheet | **design gap** → D3 |
| §1.5 group A for S17: S17-2→reconciliation, S17-3→tax-impact, S17-11/21 unchanged | Template sheets: 审定表S17-1, 审核表（合并）S17-2, 审核表（个别报表）S17-3, 与营业外收支等核对表S17-11, 非经常性损益项目的所得税影响S17-21. Components: NonRecurringDetail has views S17-1/2/3; Reconciliation saves to S17-11; TaxImpact saves to S17-21 | **design table wrong** → D5 |
| §1.5 group B tab names "to be read" | DB `workpaper_sheet_classification`: S1 `S1-1对法律法规的考虑记录表`; S8 `审定表S8-1`; S9 `程序说明`, `电子商务法律法规`; S10 `环境法规` (also `说明`, no component) | keys used at HEAD are correct |
| S17 renders | **0 classification rows for S17** (seed source only scanned `.xlsx`; template is `.xls`) → render-config returns no sheets for the 2 S17 workpapers | **blocker for S17** → D6 |
| Task 10 `useSSpecialImportExport` endpoints work | `/api/s-special/*` not found in `backend/app/routers` or `router_registry` | **missing backend** → D4(f) |
| Components bind to GtWpRenderer | all 12 declare required `isReadonly: boolean`; GtWpRenderer passes `readonly`. 9 saving components PUT `{sheet_name, data}` but `BatchSaveRequest` requires `items[]` → 422 | **binding defects** → D4 |
| §1.6 sheetKeys feed a data source | key is a namespace in the workpaper's own `parsed_data.procedure_status`; `ProcedureControlPanel` reads and writes the same key; SQL: no S workpaper has procedure_status data | change hides nothing |
| S1/S8/S20 `must_have: true` | `match_workpapers` only honours `trigger == "must_have"`; S entries use the boolean `must_have`, so S1/S8/S20 are never auto-generated | out of P0 scope; report only |
| applicable_when as a restriction | 30 of 107 entries also have `account_codes` (E1-26~32, F2-61~72, D4-22, H5*, H7*) and are generated whenever accounts match | out of P0 scope; report only |

## C. Plan by phase (status at HEAD)

### Phase 1 — generation chain (Tasks 1-3)
- [x] 1. `match_workpapers` 4th path — `backend/app/services/wp_generation_matching.py` (refactor in D2a).
- [x] 2. SELECT `Project.business_category` + biz_ flags — `backend/app/services/chain_orchestrator.py` (refactor in D2b).
- [ ] 3. End-to-end check — pure test with the real mapping file, see D2 verification (no DB writes).

### Phase 2 — trimming + IPO utility (Tasks 4-9)
- [x] 4. `audit-platform/frontend/src/utils/ipoProjectUtils.ts` + spec.
- [x] 5. `useAProgramData.ts` dict branch (the procedure-tables API never returns a dict today; forward-compatible only).
- [x] 6. `_WP_APPLICABLE_WHEN` + bundle parent aggregation; 12 types in `VALID_COMPONENT_TYPES`.
- [ ] 7. Overlay — defective, fix D1 + D2.
- [ ] 8. D4/F2 convergence — incomplete, fix D7.
- [ ] 9. ≤2 IPO-judgement sources — after D7.

### Phase 3 — s-checklist wiring (Tasks 10-16)
- [ ] 10/11. Template and binding check — do D4 (with evidence) and D5.
- [x] 12/13. Overrides — done except S17 values (D5).
- [ ] 14. Registry — done in frontend; backend renderer missing (D3).
- [x] 15. Registry spec — done; add strategy/parity tests (D3).
- [ ] 16. Browser check — after D3/D4; S17 blocked by D6. Read-only browsing on real projects is fine; save round-trips only in a【测试】project.

### Phase 4 — sidebar routing (Tasks 17-19)
- [x] 17/18. Done in `0da7d5905`.
- [ ] 19. Browser check.

## D. Verified defects (must fix; evidence → fix → verification)

**D1 — overlay computed is not a template binding.** HEAD `GtWpRenderer.vue` line ~497 declares
`const isWpNotApplicable = computed(...)` inside `function handleRedirectNavigation()` (line ~492, before
`if (targetPath)` at ~507). The template's `v-else-if="isWpNotApplicable"` resolves to undefined, so the
overlay never shows. Fix: move it to top level (after `redirectHint`). Verify: D2 frontend test.

**D2 — overlay compares the wrong value; frontend and generation disagree.** The computed reads
`renderConfig.project_context.business_category`, which the top level never has, so `projectBiz` is always ''.
Fixing D1 alone makes every S32~S35 workpaper show「不适用」, including in IPO projects. The generation
chain also counts `template_type == 'listed'` as biz_listed. Fix with one backend predicate:
- a. `wp_generation_matching.py`: add `business_category_flags(business_category, template_type) -> dict[str, bool]`
  (the 4 biz_ flags exactly as chain_orchestrator builds them) and
  `applicable_when_hit(applicable_when, flags, *, keys=None) -> bool` (OR across keys; prefixes
  business_category→biz_, industry→ind_; optional key filter). The 4th path of `match_workpapers` calls it. Export both.
- b. `chain_orchestrator._step_generate_workpapers`: `project_flags.update(business_category_flags(business_category, template_type))`.
- c. `wp_render_config._get_render_config_impl`: after the sheet loop, `_aw = _WP_APPLICABLE_WHEN.get(wp_code)`;
  only when `_aw.get('business_category')`, run a guarded `SELECT template_type FROM projects WHERE id = :pid`
  (try/except → warning + rollback, default None) and set
  `not_applicable = not applicable_when_hit({'business_category': _aw['business_category']}, business_category_flags(_prog_biz, tpl_type))`;
  else False (industry-only dicts for H5/H7/M8 must not hide those workpapers). Add `"not_applicable"` to the response.
  Keep the extra query inside the `_aw` branch so other render-config tests (mocked by call order) are untouched.
- d. GtWpRenderer: `isWpNotApplicable = renderConfig.value?.not_applicable === true`; drop the unused import.
- Verify: new `backend/tests/test_s_cycle_applicable_when.py` — flags for ('IPO','soe'), ('C','soe'), (None,'listed');
  OR semantics and key filter; real `_WP_APPLICABLE_WHEN` non-empty, S34 ⊇ {ipo, listed, neeq, refinancing},
  S35 == {'business_category': ['refinancing']}; with the real mapping file, `match_workpapers(m, set(), business_category_flags('IPO','soe'))`
  contains S32/S33/S34 and not S35, ('C','soe') none of S32~S35, (None,'listed') S32/S33/S34 (Task 3).
  New `GtWpRenderer.applicable-when.test.ts` (mock style of `GtWpRenderer.background-merge.test.ts`):
  `not_applicable: true` shows「不适用」for an `s34-ipo-bundle` payload and an `a-program-console` payload; false/absent shows none.

**D3 — the 12 new componentTypes never reach the frontend component.** In `_get_render_config_impl`, a multi-sheet sheet
whose type has no `RENDERER_DISPATCH` entry and is not in `_ONLYOFFICE_HTML_WHITELIST` becomes `onlyoffice-sheet`.
S1/S8/S9/S10 are multi-sheet, so since `1517804a3` the 9 overridden sheets render as OnlyOffice. Whitelisting alone
is not enough: renderer-less whitelisted types get template grid `cells` and GtWpRenderer then shows GtGridSheet.
Fix (pattern: `wp_render_strategies/_s3_policy_change.py`, "让 component_type 在 RENDERER_DISPATCH 中命中"):
new `backend/app/routers/wp_render_strategies/_s_checklist_sheets.py` with
`S_CHECKLIST_ITEM_IDS = {s1-regulation-record: 'S1-1-sheet-data', s8-adjudication: 'S8-1-sheet-data', s9-adjudication: 'S9-1-sheet-data',
s9-internal-control: 'S9-2-sheet-data', s10-adjudication: 'S10-1-sheet-data', s10-internal-control: 'S10-2-sheet-data',
s17-nonrecurring-detail: 'S17-1-sheet-data', s17-reconciliation: 'S17-11-sheet-data', s17-tax-impact: 'S17-21-sheet-data',
s9-legal-regulations / s9-program-description / s10-environmental-regulations: None}` and
`async def render(ctx)`: when the id is not None, `SELECT remark FROM checklist_responses WHERE wp_id = :wp_id AND item_id = :item_id`,
merge the JSON object; return `{**payload, 'component_type': ctx.component_type, 'sheet_name': ...}`; never a `cells` key;
on error warn + rollback + return the light dict. Register the 12 keys in `wp_render_strategies/__init__.py`.
Verify: new `backend/tests/test_s_checklist_render_strategy.py` (12 types in RENDERER_DISPATCH ∩ VALID; payload merged, no
`cells`; no row → light dict; id map equals the frontend `sChecklistItemIds.ts`), plus
`backend/tests/formula_management/test_classification_404_classification.py` and `backend/tests/test_dedicated_component_registry_contract.py`.

**D4 — s-checklist components cannot save, ignore readonly, and call a missing API.** Evidence: `BatchSaveRequest`
(`backend/app/routers/checklist_responses.py`) requires `items: [{item_id, conclusion, remark}]`; the 9 saving components send
`{sheet_name, data}` → 422; each `loadData` re-fetches render-config and picks the sheet by name substrings; all 12 require
`isReadonly` while GtWpRenderer passes `readonly`; S1/S17 import menus call `/api/s-special/*`, which does not exist. Fix:
- a. `s-checklist/sChecklistItemIds.ts` with the D3 map.
- b. Save body `{ project_id: props.projectId, items: [{ item_id, conclusion: null, remark: JSON.stringify(payload) }] }`.
- c. `loadData` picks `s.componentType === '<own type>'`; saved keys == loaded keys (list per component in findings).
- d. `readonly?: boolean`, `sheetName?: string`, `const isReadonly = computed(() => props.readonly === true)`.
- e. S17NonRecurringDetailSheet: `watch(() => props.sheetName, …, { immediate: true })` → view S17-1/S17-2/S17-3 (one componentType, no remount).
- f. Disable the import/export dropdown in S1RegulationRecordSheet and S17NonRecurringDetailSheet, label「导入导出（开发中）」; leave `useSSpecialImportExport.ts` unchanged.
- g. Compare reference content and 审定表 columns with the templates (openpyxl; S9 程序说明 69 rows, 电子商务法律法规 98 rows; S10 环境法规 152 rows); fix label/column gaps only; record evidence.
- Verify: new vitest under `s-checklist/__tests__/` (save body via mocked `@/utils/http`, readonly honoured, S17 view sync).

**D5 — S17 overrides follow the wrong design table.** Set `S17-1`, `S17-2`, `S17-3` → `s17-nonrecurring-detail`,
`S17-11` → `s17-reconciliation`, `S17-21` → `s17-tax-impact` in `backend/app/data/wp_code_overrides.json`. The file is CRLF and
round-trips through `json.dumps(d, ensure_ascii=False, indent=2) + '\n'` (verified); write CRLF back; `git diff` must show only these
lines. Append a dated divergence note to the spec `tasks.md` (append-only). Verify: a pytest asserting these 5 values.

**D6 — S17 has no sheet classification.** SQL: 0 rows for `wp_code='S17'` in `workpaper_sheet_classification`
(S1 4, S8 3, S9 6, S10 6 rows exist). Do not write the shared DB without the user: prepare the 8 rows (7 sheets above plus
表头（请先填写）, class codes following S9/S10 — I-占位 / A-S 议题程序 / F-审定表 / D-检查表 / H-辅助说明) as a dry run and ask with
`send_message` severity `warning`. If not approved, mark the S17 part of Task 16 `[ ]*` blocked with this evidence.

**D7 — Task 8 convergence not done.** HEAD keeps `isIpoGroupVisible` (delegating wrapper) and `useD4CrossSheet.ts` still imports it,
so there are 3 IPO-judgement sources (Task 9 requires ≤2). Fix per design §1.4: `useD4FormulaEngine.ts` exports
`D4_IPO_GROUP_CATS = [...IPO_BIZ_KEYWORDS, 'fraud_risk'] as const` and drops `IPO_KEYWORDS` + `isIpoGroupVisible`;
`useD4CrossSheet.ts` calls `isIpoProject(biz, [...D4_IPO_GROUP_CATS])`; update `useD4FormulaEngine.spec.ts` (8 cases) and
`.pbt.spec.ts` (3 properties; add 'refinancing' to the keyword list). `useF2SpecialFormData.ts` exports `isF2IpoProject(ctx)`
whose first level is the util (imported under an alias), then project_type / template_type / IPO_CATEGORIES; the composable still
returns a computed named `isIpoProject` (used by `GtF2InventorySpecial.vue`). Verify: the two D4 spec files + grep shows definitions only
in `ipoProjectUtils.ts` and `useF2SpecialFormData.ts`.

**D8 — type check.** Full `vue-tsc` OOMs here. Use a temporary single-region tsconfig (precedent `tsconfig._g-single-region.json`)
over the touched files, prove it catches an injected `const _x: number = 'a'`, then delete it.

## E. Rules for implementers
- Windows PowerShell; `python` not `python3`; `;` not `&&`; use `cwd` instead of `cd`.
- Backend: `.venv\Scripts\python.exe -m pytest backend/tests/<file> -v --tb=short -p no:playwright` from the repo root.
- Frontend: `npx vitest run <path> --reporter=verbose` with cwd `audit-platform/frontend`.
- Other sessions share this worktree: never `git stash`, never `git add -A`/`.`; stage by name; never stage `.agents/`; commit locally, never push.
- Services flush, routers commit; S-class never writes trial_balance; UI text Chinese.
- Do not save test data in real projects; only【测试】projects.

## F. Pre-existing failures (not caused by this work)
- `backend/tests/test_component_capability_contract.py::test_checked_in_manifest_is_canonical_and_current` fails, and
  `backend/scripts/gen/generate_component_capability_manifest.py --check` exits 2: the generator cannot parse
  `registry/index.ts` (`export type HtmlComponentType = HtmlRendererEntry['componentType']`, unchanged since `82f58ea44`, 2026-09-13).
  Do not run `--apply`; report it.
