# Implementation Plan: Trial Balance Version Time Machine

## Task Dependency Graph

```json
{"waves": [[1, 2], [3, 4], [5], [6], [7, 8]]}
```

## Tasks

- [x] 1. Create migration V128 for trial_balance_snapshots table (id UUID, project_id, year, version_no, trigger, actor_id, content_hash, snapshot_data JSONB, row_count, audited_total, created_at; UNIQUE project+year+version; INDEX project+year+created_at DESC) and rollback R128. Add ORM model TrialBalanceSnapshot. Verify migration_runner apply + drift=0.
- [x] 2. Create TbSnapshotService with create_snapshot (read trial_balance + saved summary → JSONB + SHA-256 dedup + INSERT with auto version_no), list_snapshots (ORDER BY version_no DESC LIMIT 50), get_snapshot, _compute_content_hash (sorted JSON keys). Unit tests for dedup + monotonicity.
- [x] 3. Add restore_snapshot (create current-state snapshot trigger='restore' → overwrite trial_balance → emit WORKPAPER_SAVED event). Add diff_snapshots (build row_code→audited maps, compute changed/added/removed + stats). Tests for restore-creates-trail + diff-symmetry + downstream-event.
- [x] 4. Create router tb_snapshot.py with 5 endpoints (POST create, GET list, GET detail, POST restore, GET diff). Register in router_registry. Permission: create=edit, list/detail/diff=readonly, restore=manager+. Endpoint smoke tests.
- [x] 5. Create TbVersionDrawer.vue (el-drawer with el-timeline version list, read-only detail table, inline diff view with row highlighting, restore button with manager gate + confirm dialog). Vitest mount test.
- [x] 6. Integrate into TrialBalance.vue: add "⏱ 版本历史" toolbar button, after onRecalc/saveTbSummary success POST snapshot (best-effort catch), on @restored refresh data. Property 4 test: snapshot failure does not block recalc.
- [x] 7. PBT test file covering Properties 1-8 (immutability, dedup, restore-trail, fail-open, monotonicity, diff-correctness, downstream-event, retention-limit).
- [x] 8. Zero-regression gate: run existing trial_balance test suite with 0 new failures. Verify recalc/save unchanged behavior.

## Notes

- Migration version V128 — check migration_status before apply (current highest may differ)
- Snapshot JSONB ~32KB per version (200 rows × 8 fields), well within PG limits
- Content hash uses sorted JSON keys for determinism
