-- V235：调整分录组版本、持久化复核任务与财务处理历史
-- spec: adjustment-practice-linkage-integrity-closure B1/B2
-- additive migration；不改既有金额和复核状态。

ALTER TABLE adjustments
    ADD COLUMN IF NOT EXISTS content_revision INTEGER NOT NULL DEFAULT 1;
ALTER TABLE adjustments
    ADD COLUMN IF NOT EXISTS audit_phase VARCHAR(16) NOT NULL DEFAULT 'final';
ALTER TABLE unadjusted_misstatements
    ADD COLUMN IF NOT EXISTS management_communication_at TIMESTAMPTZ;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_adjustments_content_revision') THEN
        ALTER TABLE adjustments ADD CONSTRAINT ck_adjustments_content_revision
            CHECK (content_revision >= 1) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_adjustments_audit_phase') THEN
        ALTER TABLE adjustments ADD CONSTRAINT ck_adjustments_audit_phase
            CHECK (audit_phase IN ('preliminary', 'final')) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_adjustment_entries_nonnegative') THEN
        ALTER TABLE adjustment_entries ADD CONSTRAINT ck_adjustment_entries_nonnegative
            CHECK (debit_amount >= 0 AND credit_amount >= 0) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_adjustment_entries_one_side') THEN
        ALTER TABLE adjustment_entries ADD CONSTRAINT ck_adjustment_entries_one_side
            CHECK ((debit_amount > 0 AND credit_amount = 0)
                OR (credit_amount > 0 AND debit_amount = 0)) NOT VALID;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_adjustment_entries_active_group_line
    ON adjustment_entries(entry_group_id, line_no)
    WHERE is_deleted = false;

CREATE TABLE IF NOT EXISTS adjustment_review_tasks (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    entry_group_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    required_level VARCHAR(16) NOT NULL DEFAULT 'manager',
    revision INTEGER NOT NULL DEFAULT 1,
    group_content_revision INTEGER NOT NULL DEFAULT 1,
    assigned_reviewer_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    submitted_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    submit_note TEXT,
    decided_by UUID REFERENCES users(id) ON DELETE RESTRICT,
    decided_at TIMESTAMPTZ,
    decision_reason TEXT,
    self_review_override_reason TEXT,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_adjustment_review_tasks_status CHECK (
        status IN ('pending', 'approved', 'rejected', 'withdrawn', 'stale')
    ),
    CONSTRAINT ck_adjustment_review_tasks_required_level CHECK (
        required_level IN ('manager', 'partner')
    ),
    CONSTRAINT ck_adjustment_review_tasks_revision CHECK (revision >= 1),
    CONSTRAINT ck_adjustment_review_tasks_group_revision CHECK (group_content_revision >= 1)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_adjustment_review_tasks_active_group
    ON adjustment_review_tasks(project_id, entry_group_id)
    WHERE status = 'pending' AND is_deleted = false;
CREATE INDEX IF NOT EXISTS ix_adjustment_review_tasks_project_status
    ON adjustment_review_tasks(project_id, year, status, submitted_at DESC);
CREATE INDEX IF NOT EXISTS ix_adjustment_review_tasks_assignees_gin
    ON adjustment_review_tasks USING gin(assigned_reviewer_ids);

CREATE TABLE IF NOT EXISTS adjustment_client_bookings (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    entry_group_id UUID NOT NULL,
    action VARCHAR(12) NOT NULL,
    sequence INTEGER NOT NULL,
    voucher_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
    booked_dataset_id UUID REFERENCES ledger_datasets(id) ON DELETE RESTRICT,
    note TEXT,
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_adjustment_client_bookings_action CHECK (action IN ('book', 'revoke')),
    CONSTRAINT ck_adjustment_client_bookings_sequence CHECK (sequence >= 1),
    CONSTRAINT ck_adjustment_client_bookings_voucher_keys CHECK (jsonb_typeof(voucher_keys) = 'array')
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_adjustment_client_bookings_group_sequence
    ON adjustment_client_bookings(project_id, entry_group_id, sequence);
CREATE INDEX IF NOT EXISTS ix_adjustment_client_bookings_group_time
    ON adjustment_client_bookings(project_id, year, entry_group_id, created_at DESC, id DESC);

ALTER TABLE adjustment_client_bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE adjustment_client_bookings FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS project_isolation ON adjustment_client_bookings;
CREATE POLICY project_isolation ON adjustment_client_bookings
    USING (project_id::text = current_setting('app.current_project_id', true))
    WITH CHECK (project_id::text = current_setting('app.current_project_id', true));

CREATE TABLE IF NOT EXISTS adjustment_treatment_events (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    entry_group_id UUID NOT NULL,
    sequence INTEGER NOT NULL,
    action VARCHAR(40) NOT NULL,
    dataset_id UUID REFERENCES ledger_datasets(id) ON DELETE RESTRICT,
    voucher_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
    misstatement_id UUID REFERENCES unadjusted_misstatements(id) ON DELETE RESTRICT,
    client_booking_id UUID REFERENCES adjustment_client_bookings(id) ON DELETE RESTRICT,
    reverses_event_id UUID REFERENCES adjustment_treatment_events(id) ON DELETE RESTRICT,
    reason TEXT,
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_adjustment_treatment_events_action CHECK (
        action IN ('include_in_working_tb', 'client_booked', 'unadjusted_misstatement', 'withdraw')
    ),
    CONSTRAINT ck_adjustment_treatment_events_sequence CHECK (sequence >= 1),
    CONSTRAINT ck_adjustment_treatment_events_payload CHECK (
        (action = 'client_booked' AND client_booking_id IS NOT NULL AND misstatement_id IS NULL)
        OR (action = 'unadjusted_misstatement' AND misstatement_id IS NOT NULL AND client_booking_id IS NULL)
        OR (action IN ('include_in_working_tb', 'withdraw') AND misstatement_id IS NULL AND client_booking_id IS NULL)
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_adjustment_treatment_events_group_sequence
    ON adjustment_treatment_events(project_id, entry_group_id, sequence);
CREATE INDEX IF NOT EXISTS ix_adjustment_treatment_events_group_time
    ON adjustment_treatment_events(project_id, year, entry_group_id, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS adjustment_import_batches (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_sha256 VARCHAR(64) NOT NULL,
    mode VARCHAR(16) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'processing',
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    uploaded_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    parent_batch_id UUID REFERENCES adjustment_import_batches(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT ck_adjustment_import_batches_mode CHECK (mode IN ('append','overwrite')),
    CONSTRAINT ck_adjustment_import_batches_status CHECK (status IN ('processing','completed','partial','failed'))
);
CREATE INDEX IF NOT EXISTS ix_adjustment_import_batches_scope
    ON adjustment_import_batches(project_id, year, created_at DESC);

CREATE TABLE IF NOT EXISTS adjustment_import_group_results (
    id UUID PRIMARY KEY,
    batch_id UUID NOT NULL REFERENCES adjustment_import_batches(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    group_key VARCHAR(120) NOT NULL,
    external_reference VARCHAR(120),
    source_rows JSONB NOT NULL DEFAULT '[]'::jsonb,
    action VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    entry_group_id UUID,
    error TEXT,
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_adjustment_import_group_results_status CHECK (status IN ('imported','skipped','failed'))
);
CREATE INDEX IF NOT EXISTS ix_adjustment_import_group_results_batch
    ON adjustment_import_group_results(batch_id, status, created_at);
CREATE INDEX IF NOT EXISTS ix_adjustment_import_group_results_external
    ON adjustment_import_group_results(project_id, year, external_reference);

ALTER TABLE adjustments ADD COLUMN IF NOT EXISTS external_reference VARCHAR(120);
ALTER TABLE adjustments ADD COLUMN IF NOT EXISTS import_batch_id UUID;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_adjustments_import_batch') THEN
        ALTER TABLE adjustments ADD CONSTRAINT fk_adjustments_import_batch
            FOREIGN KEY (import_batch_id) REFERENCES adjustment_import_batches(id) ON DELETE SET NULL;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_adjustments_import_batch ON adjustments(import_batch_id);
CREATE INDEX IF NOT EXISTS ix_adjustments_external_reference
    ON adjustments(project_id, year, external_reference)
    WHERE is_deleted = false AND external_reference IS NOT NULL;

-- 新写入的同项目/年度编号不得跨分录组重复。重复行属于同一组，不能用普通 UNIQUE。
CREATE OR REPLACE FUNCTION gt_check_adjustment_group_number() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.is_deleted = false AND EXISTS (
        SELECT 1 FROM adjustments a
        WHERE a.project_id = NEW.project_id
          AND a.year = NEW.year
          AND a.adjustment_no = NEW.adjustment_no
          AND a.entry_group_id <> NEW.entry_group_id
          AND a.is_deleted = false
    ) THEN
        RAISE EXCEPTION 'adjustment number already used by another active group'
            USING ERRCODE = '23505';
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_adjustments_group_number_unique ON adjustments;
CREATE CONSTRAINT TRIGGER trg_adjustments_group_number_unique
AFTER INSERT OR UPDATE OF project_id, year, adjustment_no, entry_group_id, is_deleted
ON adjustments DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION gt_check_adjustment_group_number();

-- 新表按项目上下文 fail closed；项目端点在鉴权依赖中设置 app.current_project_id。
ALTER TABLE adjustment_review_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE adjustment_review_tasks FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS project_isolation ON adjustment_review_tasks;
CREATE POLICY project_isolation ON adjustment_review_tasks
    USING (project_id::text = current_setting('app.current_project_id', true))
    WITH CHECK (project_id::text = current_setting('app.current_project_id', true));

ALTER TABLE adjustment_treatment_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE adjustment_treatment_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS project_isolation ON adjustment_treatment_events;
CREATE POLICY project_isolation ON adjustment_treatment_events
    USING (project_id::text = current_setting('app.current_project_id', true))
    WITH CHECK (project_id::text = current_setting('app.current_project_id', true));
