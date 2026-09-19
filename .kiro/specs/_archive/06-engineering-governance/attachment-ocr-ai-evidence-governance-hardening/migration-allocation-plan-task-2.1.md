# Migration Allocation Plan — Task 2.1 (Wave 1)

Spec: `attachment-ocr-ai-evidence-governance-hardening`
Requirements: **R14** · Properties: **P3, P28** · Design: **§8.1 MigrationRunner 编号与建表策略**

This task does **not** create governance model tables (those are Tasks 2.2–2.4). It
establishes the authoritative migration state, freezes the dynamic "next available V"
allocation approach, and freezes the migration conventions as executable guards so
Tasks 2.2–2.4 each pick sequential V numbers without collision.

---

## 1. Authoritative current state (empirically verified 2026-07-16)

| Source | Value | Evidence |
|---|---|---|
| **Highest V in directory** | **V105** | `backend/migrations/V*.sql` scan — `V105__evidence_governance_role_eqcr_enum.sql` (added by Task 1.1 for the seven-value `SystemRole` eqcr enum). |
| **Highest V applied in DB** | **V102** | `SELECT max(version) FROM schema_version` (read-only) → `V102__advanced_query_writeback_addr_id.sql`, applied 2026-07-10. |
| **Pending (dir − DB)** | **V103, V104, V105** | `V103__acnr_project_overlay.sql`, `V104__formula_runtime_outbox.sql`, `V105__evidence_governance_role_eqcr_enum.sql`. |
| **Recorded failures** | **none** | `SELECT * FROM schema_migration_failures` → `[]`. |
| **Duplicate version numbers** | **none** | `parse_dir_versions` over the real dir → no version has >1 file. |
| **Applied-but-missing-in-dir** | **none** | every applied version V001–V102 has a matching file. |

### Resolution of the "inconsistency" flagged in Wave 0 / Task 1.1

The Task 1.1 note (DB max applied = V102 while directory has V103/V104/V105 pending)
describes the **normal `MigrationRunner` startup state**, not a blocking inconsistency.

- `MigrationRunner.run_pending()` computes `pending = dir_versions − applied_versions`
  and applies them in version order at startup (advisory-locked, per-migration isolated).
  V103/V104/V105 are legitimately **pending-but-unapplied in this dev DB** because the
  backend has not been restarted since they landed; they apply automatically on next start.
- design §8.1 "若状态源与目录扫描不一致，停止实施并人工解决" refers to **genuinely blocking
  drift**, defined precisely as any of:
  1. a version **applied in DB but missing from the directory** (deleted/renamed/checksum drift),
  2. any row in **`schema_migration_failures`**,
  3. **duplicate version numbers** in the directory.
- **None** of the three blocking conditions hold. Therefore the state is **CONSISTENT** and
  **Tasks 2.2–2.4 are UNBLOCKED**.

Frozen-contract cross-check: `frozen-contracts-task-1.3.md` recorded "highest existing =
V104, next available = V105" at the time of Task 1.3; since then Task 1.1's V105 (eqcr enum)
landed, so the directory highest is now **V105** and the next available is **V106**.

---

## 2. Dynamic "next available V" allocation (single source of truth)

Allocation is **not** a static number. Tasks 2.2–2.4 must call the frozen helper at
implementation time:

```python
from app.services.evidence_governance.migration_allocation import next_available_version

filenames = [p.name for p in migrations_dir.glob("V*.sql")]
applied    = await runner.get_applied_versions()          # from schema_version
failures   = {...}                                        # from schema_migration_failures
nxt = next_available_version(filenames, applied, failures)  # int, e.g. 106
# raises MigrationStateInconsistency on blocking drift → STOP, do not guess/overwrite
```

- `next_available = max(dir_versions ∪ applied_versions) + 1`.
- Pending migrations (dir > DB) do **not** block allocation.
- Blocking drift raises `MigrationStateInconsistency` → stop and resolve manually
  (design §8.1: 不猜号、不覆盖迁移).

### Expected sequential allocation for Tasks 2.2–2.4 (dependency order)

Given the current state (dir highest V105, no drift), and assuming each task allocates
in dependency order at implementation time:

| Task | Content (design §8.1 additive order) | Expected V (if run sequentially now) |
|---|---|---|
| **2.2** | base actor/ServiceIdentity → `UploadAttempt` → Attachment/AttachmentVersion (循环 FK 分阶段) → quarantine/staging → immutable trigger | **V106** (+ optional V107 for staged circular-FK phase) |
| **2.3** | `legacy_attachment_alias`, EvidenceRef/EvidenceDependency, active-intent partial unique, canonical edge hash + 双向索引 | **next available after 2.2** (e.g. V107/V108) |
| **2.4** | OCR Job/Transition/Result/Confirmation/Writeback, Citation/AI ext, Review snapshot, audit/outbox/inbox, Archive Manifest, Legal Hold, checkpoint/quality snapshot | **next available after 2.3** |

The exact numbers are whatever `next_available_version(...)` returns at the moment each
task runs — **never hardcode**. If a task needs multiple migration files (e.g. staged
circular FK), it allocates consecutive V numbers by re-scanning after each file is written.

---

## 3. Frozen migration conventions (executable guard)

All Tasks 2.2–2.4 migration files MUST pass `lint_migration_sql(sql)`:

- **additive-only** — no `DROP TABLE`, no `DROP COLUMN`, no `TRUNCATE`. Legacy columns are
  never removed (retirement / legacy-column drop is explicitly out of scope, design §8.2 M4).
- **repeatable-detection (idempotent)** — every `CREATE TABLE` / `CREATE (UNIQUE) INDEX`
  uses `IF NOT EXISTS`, **or** is wrapped in a `DO $$ ... $$` block guarded by an existence
  check (`information_schema` / `pg_indexes` / `pg_class` / `pg_constraint` / `pg_type` /
  `to_regclass`); every `ADD COLUMN` uses `IF NOT EXISTS` or the same guard. Re-running a
  migration must not error and must not create duplicate objects (P28).
- **FK default `ON DELETE RESTRICT`** — every inline `REFERENCES` must declare
  `ON DELETE RESTRICT` (rollback must not cascade-delete governance objects;
  design §8.1 + release-gate note "回滚不删除 AttachmentVersion/EvidenceRef/OCR 决策/审计/Manifest/Hold").
  (`require_fk_restrict=False` only for enum-only / no-FK migrations such as V105.)

### Regression anchors (already green)

- **V105** (enum-only, `ADD VALUE IF NOT EXISTS`) → additive-only, passes with `require_fk_restrict=False`.
- **V104** (all `information_schema` / `pg_indexes` DO guards + `CREATE TABLE/INDEX IF NOT EXISTS`)
  → additive + repeatable.
- **V103** (`CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`) → additive + repeatable.

---

## 4. Artifacts

| Artifact | Path |
|---|---|
| Allocation + convention-lint helper (pure, single source of truth) | `backend/app/services/evidence_governance/migration_allocation.py` |
| Tests (unit + real-dir scan + real-PG16 read-only state consistency + V103/104/105 regression) | `backend/tests/test_evidence_governance_migration_allocation.py` |
| This plan | `.kiro/specs/attachment-ocr-ai-evidence-governance-hardening/migration-allocation-plan-task-2.1.md` |

**28 tests green** (incl. `test_real_db_state_is_consistent` against real PostgreSQL 16,
read-only). No governance tables created. No migration files added or modified.
Tasks 2.2–2.4 are **unblocked**.
