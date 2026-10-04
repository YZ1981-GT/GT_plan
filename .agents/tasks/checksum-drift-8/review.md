# Review — checksum 漂移 8 条处置（补迁移 V178/V179 + ledger 登记 + 真库验证）

This change closes the 8 startup checksum-drift WARNINGs by (1) writing two paired repair migrations V178/R178 and V179/R179 that backfill the 3 schema objects the drifted V005/V019 files declare but never executed, (2) applying them to the live DB via the MigrationRunner path so `schema_version` records 178/179, and (3) appending 8 `KnownChecksumDrift` triples to `migration_drift_ledger.py` so the drifts become "explained" without rewriting `schema_version`. The approach follows the ledger docstring's mandated order (backfill missing objects first, register last, never touch `schema_version` checksums). The coder recorded live-DB verification evidence in `verification.md` covering all required objects and the guard-test run.

Watch for: nothing blocking. All consistency, collision, checksum-length, and evidence checks pass (confirmed).

**Verdict**: APPROVED

## High-level view

The two repair migrations are byte-consistent with the authoritative declarations. V178's `admin_query_all_reports()` body matches `V005__enable_rls.sql` character-for-character (`CREATE OR REPLACE FUNCTION … RETURNS SETOF financial_report / LANGUAGE sql SECURITY DEFINER / AS 'SELECT * FROM financial_report WHERE is_deleted = false'`). V179's CHECK constraint and two indexes match the `V019__add_note_section_id_columns.sql` DO-block and index column orders exactly. All DDL is guarded: `CREATE OR REPLACE` for the function, a `pg_constraint.conname` existence DO-block for the constraint, and `CREATE INDEX IF NOT EXISTS` for both indexes. Each V has its paired R rollback as D6 requires.

Version numbering is clean: `scan_migrations()` returns 178 and 179 exactly once each, no duplicates, and does not raise the same-version `RuntimeError`. 178/179 are above the prior max.

The ledger edit appends exactly 8 triples (005/006/010/016/017/019/051/057) after the 7 pre-existing entries, with full 64-char stored and current checksums. Every current value equals the runner's own disk recompute, and every stored value equals the live `schema_version` checksum per the recorded evidence — so `schema_version` was not rewritten. Resolution texts carry the right dispositions (V005→"已由 V178 补齐", V019→"已由 V179 补齐", the other six→"无需补迁移"), each well over the 20-char floor.

The coder's `verification.md` records the pre-flight safety check (0 out-of-range level rows), `schema_version` rows for 178/179, the three objects now present (1 `pg_proc`, 1 `pg_constraint`, 2 `pg_indexes`), the stored-vs-live checksum equality, the guard suite at 37 passed, and cleanup of all `_cd8_*` scripts and `_diffs.txt`. `findings.md` was kept.

<details>
<summary>Issues (0)</summary>

No blocking or non-blocking findings.

</details>

<details>
<summary>Details</summary>

### Byte-consistency of the repair migrations

V178 reproduces the exact function declaration from the current `V005__enable_rls.sql`. Spot-checking the source confirmed the surrounding bytes are `…WHERE is_deleted = false';\n\nCREATE OR REPLACE FUNCTION admin_query_all_reports()\nRETURNS SETOF financial_report\nLANGUAGE sql SECURITY DEFINER\nAS 'SELECT * FROM financial_report WHERE is_deleted = false';` — identical to V178's statement. R178 is `DROP FUNCTION IF EXISTS admin_query_all_reports();`, matching R005.

V179's constraint block is the same DO-block form as V019 (`IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_disclosure_notes_level_range') … ADD CONSTRAINT … CHECK (level IS NULL OR (level BETWEEN 1 AND 5))`), and the two indexes carry the same column orders V019 declares: `(project_id, year, section_id)` and `(parent_section_id)`. R179 drops the two indexes then the constraint — the R019 subset scoped to only the three backfilled objects. All three objects use existence guards, so re-running is safe.

### Version collision

`MigrationRunner(...).scan_migrations()` returns 178 and 179 once each with no duplicates and the max version is 179; the same-version detector does not fire. This is the same algorithm the guard test's `disk_checksums` fixture uses, so the recompute below is same-source.

### Ledger triples

The 8 appended entries sit after the 7 pre-existing ones (042/046/105/128/143/151/163), which are unchanged. For each new entry: stored and current are 64 hex chars; `current == scan_migrations()[version].checksum` holds for all 8; resolution lengths are 153/90/71/101/154/157/98/66 chars. The current checksums equal the findings.md disk values (e.g. V005 `1f090aa8e4b386…`, V019 `ee63dd219d63…`), and the stored values equal the live `schema_version` checksums recorded in `verification.md` — confirming `schema_version` was not rewritten. The guard test `test_entry_current_matches_disk`, `test_exact_triples_are_explained`, and `test_ledger_has_no_duplicate_versions` all exist and are reported green (37 passed).

### Live-DB evidence and cleanup

`verification.md` records, via `docker exec audit-postgres psql`: 0 out-of-range `level` rows before the constraint add; `schema_version` rows for 178/179 (applied through the MigrationRunner path, so no re-run on next startup); `admin_query_all_reports` present in `pg_proc`; `ck_disclosure_notes_level_range` present in `pg_constraint`; both indexes present in `pg_indexes`; and the 8 live `schema_version` checksums matching the ledger stored values. `_cd8_*` scripts, `_diffs.txt`, and the container `/tmp` copy are confirmed gone; `findings.md` and `plan.md` remain. Per the review instructions, this evidence was read rather than re-run.

</details>

<details>
<summary>File map</summary>

- `backend/migrations/V178__repair_v005_admin_query_all_reports.sql` — new; backfills `admin_query_all_reports()` SECURITY DEFINER function, byte-consistent with V005.
- `backend/migrations/R178__rollback_repair_v005_admin_query_all_reports.sql` — new; `DROP FUNCTION IF EXISTS admin_query_all_reports();`.
- `backend/migrations/V179__repair_v019_disclosure_notes_constraint_and_indexes.sql` — new; backfills `ck_disclosure_notes_level_range` CHECK + 2 indexes, byte-consistent with V019.
- `backend/migrations/R179__rollback_repair_v019_disclosure_notes_constraint_and_indexes.sql` — new; drops the 2 indexes + constraint (R019 subset).
- `backend/app/core/migration_drift_ledger.py` — appended 8 `KnownChecksumDrift` triples (005/006/010/016/017/019/051/057); pre-existing entries unchanged.
- `.agents/tasks/checksum-drift-8/verification.md` — coder's recorded live-DB verification evidence.

</details>
