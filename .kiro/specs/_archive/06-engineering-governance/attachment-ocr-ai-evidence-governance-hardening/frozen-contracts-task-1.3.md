# Frozen Contracts — Task 1.3 (Wave 0)

Spec: `attachment-ocr-ai-evidence-governance-hardening`
Requirements: **R1, R3, R5, R14** · Properties: **P3, P6, P7, P9, P28**

Task 1.3 empirically verifies the current codebase state and **freezes four P0
contracts** so Wave 1+ (migrations / ORM / services) implement against a single
source of truth without drift. Nothing here touches the database or external
engines — the contracts are pure definitions + predicates.

- Single source of truth (code): `backend/app/services/evidence_governance/contracts.py`
- Contract tests: `backend/tests/test_evidence_governance_contracts_wave0.py` (34 tests, all green, global `fast` Hypothesis profile)
- Next available migration number (context only; not created here): **V105** (highest existing = V104)

---

## Empirical current-state findings (verified against code)

| Area | Current state (evidence) | Gap vs. target |
|---|---|---|
| `created_by` / actor | `Attachment.created_by: uuid NULL REFERENCES users(id)` — **single, nullable FK** (`backend/app/models/attachment_models.py`). `AttachmentWorkingPaper.created_by` also nullable. | Allows **anonymous** records; **no** `actor_type`/`actor_service_identity_id`; no XOR; no Service Identity table (`service_identities` does not exist). |
| EvidenceRef | **DTO-only** — `EvidenceRef(BaseModel)` in `backend/app/schemas/evidence_ref.py`; fields = `{evidence_type, evidence_id, project_id, year, label, route, hash, version}`. Frontend mirror `src/types/evidenceRef.ts`. No table, no id, no status, no created_by, no intent_hash, no target binding. | Not persistent/queryable/retained; disappears with the request. |
| OCR state | `Attachment.ocr_status: String(20)` free-form, default `'pending'`. De-facto values in code: `pending / processing / completed / failed`. OCR "jobs" are an **in-memory dict** `_ocr_jobs` (`ocr_fields_service.py`) — lost on restart. | No closed enum/CHECK; no persistent job; no `awaiting_confirmation/confirmed/written_back`; no transition audit. |
| Legacy ID | Versioning via `Attachment.version:int` + `previous_version_id` **on the same `attachments` row/table**. No `legacy_attachment_alias` table. `AttachmentLineage` links attachment→target but is not an alias resolver. | Bakes in "old attachment ID == aggregate root/current version"; no root+definite-version resolution. |

---

## Frozen Contract 1 — Actor XOR + no-anonymous (R1.4/R3.1/R5/R14.4; P3)

Every governance table carrying an actor uses a **physical XOR**, never a single
polymorphic `actor_id`.

- `ACTOR_TYPES = {'user','service'}`
- Physical columns (prefix allowed, semantics fixed): `actor_type`, `actor_user_id`, `actor_service_identity_id`
- `user` ⇒ `actor_user_id` set AND `actor_service_identity_id` NULL
- `service` ⇒ `actor_service_identity_id` set AND `actor_user_id` NULL
- `actor_type` NULL / unknown ⇒ **rejected** (no anonymous new records)
- Human-only decision FKs (never a Service Identity, `NOT NULL`): `confirmed_by_user_id`, `written_by_user_id`, `closed_by_user_id`, `released_by_user_id`
- Migration unknown creator ⇒ dedicated migration Service Identity + `original_creator_unknown=true` (never impersonate a human).

Predicate: `validate_actor(...)` / `is_valid_actor(...)`.

## Frozen Contract 2 — Closed OCR enum + state machine (R5.2; P9)

- `OCR_STATES = {queued, running, awaiting_confirmation, confirmed, written_back, failed}`
- Legal transitions (the **only** ones):
  - `queued → running`
  - `running → awaiting_confirmation`
  - `awaiting_confirmation → confirmed`
  - `confirmed → written_back`
  - `queued → failed`, `running → failed`
  - `failed → queued` (retry)
- Terminal: `written_back` (no outgoing edge). Any other `(from,to)` leaves state + history unchanged.
- OCR field decisions: `{accepted, corrected, rejected}`; **writeback-eligible = {accepted, corrected}** — `rejected` is decided but NEVER enters a writeback mapping (R6.2/P12).

Predicate: `is_legal_ocr_transition(from, to)`.

## Frozen Contract 3 — Persistent EvidenceRef physical model (R3.1; P6/P7)

EvidenceRef MUST become a persistent, queryable, retained row. Minimum required columns:

```
id, project_id, audit_year, source_type, source_id, source_version,
evidence_type, evidence_id, attachment_version_id, target_version, target_hash,
label, context, intent_hash, status, created_by, created_at
```

- `status ∈ {active, inactive}`; only `active` participates in new FormalOutput.
- Active-intent idempotency: partial unique `(project_id, audit_year, intent_hash) WHERE status='active'` (P7).
- The current Pydantic `EvidenceRef` is a **compatibility DTO only** and is never the source of truth.

Helper: `evidence_ref_missing_persistent_columns(present_columns)` (empty ⇒ shape satisfied).

## Frozen Contract 4 — Legacy attachment ID resolution (R14/§4.1; P28)

The old attachment ID is **NOT** assumed equal to a new aggregate root.

- `legacy_attachment_alias` columns: `old_attachment_id (PK)`, `attachment_id`, `attachment_version_id`, `project_id`, `audit_year`, `resolution_kind`, `created_at` (composite scope FKs, `ON DELETE RESTRICT`).
- `resolution_kind ∈ {root, current_version, historical_version}`.
- `LegacyAttachmentResolver` ALWAYS returns **both** the aggregate root and a **definite version** — never an id-only or a silent "current version".
- Old-ID == new-root is allowed **only** when the old ID was explicitly created as a new aggregate root (`resolved_as_new_root=true`).

Predicate: `validate_legacy_resolution(res)` / `is_valid_legacy_resolution(res)`.

---

## Handoff to later waves

- **Wave 1 (2.2/2.3/2.4/2.5)**: implement PG tables/enums/CHECK/partial-unique/composite-FK/immutable triggers matching these frozen sets; task 2.5 asserts the physical shape against real PG16 (this Wave-0 doc only froze definitions + documented the DTO/free-form gap).
- **Wave 3 (4.x)**: EvidenceRefService uses `EVIDENCE_REF_ACTIVE_INTENT_UNIQUE` for idempotency and the frozen persistent columns.
- **Wave 4 (5.x)**: OCR orchestrator enforces `OCR_TRANSITIONS`; writeback uses `OCR_WRITEBACK_ELIGIBLE_DECISIONS`.
- **Migration (M1)**: legacy backfill uses `legacy_attachment_alias` per Contract 4; unknown creators use migration Service Identity per Contract 1.

Changing any frozen set/rule is a governance decision requiring a spec update and updated contract tests.
