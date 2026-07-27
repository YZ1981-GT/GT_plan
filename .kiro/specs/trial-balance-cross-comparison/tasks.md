# Implementation Plan: Trial Balance Cross Comparison

## Task Dependency Graph

```json
{"waves": [[1], [2, 3], [4], [5, 6]]}
```

## Tasks

- [x] 1. Create composable useTbComparison.ts with loadComparisonYear/loadComparisonProject (GET trial-balance cached), joinedRows computed (outer-join by standard_account_code), varianceForTarget (amount+rate+isNew+isRemoved), sortByVariance, filterByThreshold, exportComparison (SheetJS xlsx), invalidateCache. Vitest for join/variance/cache.
- [x] 2. Create TbComparisonView.vue: mode selector (cross-year/cross-project), year dropdown + project multi-select (max 5), comparison el-table with dynamic columns (current + targets + variance), row highlighting (>30% orange / >50% red), unmatched accounts section, filter/sort bar, export button, back button. Vitest mount.
- [x] 3. Implement available years derivation (from project audit years) and cross-project source (consol scope API fallback to accessible projects list). Permission: 403 → placeholder column not blocking.
- [x] 4. Integrate into TrialBalance.vue: add "📊 对比" el-dropdown (跨年度/跨项目), comparisonActive ref, v-if toggle between normal view and TbComparisonView, pass currentRows/projectId/year, on @close deactivate, after onRecalc invalidateCache. Zero regression when comparison inactive.
- [ ] 5. PBT + vitest suite: Property 1 (join correctness), P2 (variance calc including zero-division), P3 (403 handling), P4 (cache invalidation), P5 (max 5 limit), P6 (export headers), P7 (zero regression).
- [ ] 6.\* Playwright end-to-end: toggle comparison → select year → variance renders → filter → export → back to normal view.

## Notes

- No new backend endpoints — reuses GET /trial-balance per project per year
- Cross-project permission enforced by existing project-level auth
- Max 5 targets = 5 parallel requests, ~200ms each typical
- standard_account_code matching requires consistent account_mapping across projects
