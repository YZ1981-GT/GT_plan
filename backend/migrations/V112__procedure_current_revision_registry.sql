-- V112: procedure current-revision registry and cutover hardening (additive only)
-- V105 is immutable. This migration adds explicit revision selection, revision membership,
-- and database-level append-only protection for procedure task history.

CREATE TABLE IF NOT EXISTS procedure_template_revisions (
    id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_code              VARCHAR(80) NOT NULL,
    revision_hash              CHAR(64) NOT NULL,
    status                     VARCHAR(24) NOT NULL DEFAULT 'registered',
    is_current                 BOOLEAN NOT NULL DEFAULT false,
    supersedes_revision_hash   CHAR(64),
    activated_at               TIMESTAMPTZ,
    activated_by               UUID REFERENCES users(id),
    reconcile_detail           JSONB NOT NULL DEFAULT '{}',
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_procedure_template_revision_status
        CHECK (status IN ('registered', 'current', 'reconcile_pending')),
    CONSTRAINT ck_procedure_template_revision_current_status
        CHECK (NOT is_current OR status = 'current')
);

CREATE TABLE IF NOT EXISTS procedure_row_definition_revisions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_code   VARCHAR(80) NOT NULL,
    revision_hash   CHAR(64) NOT NULL,
    sheet_key       VARCHAR(160) NOT NULL,
    definition_key  VARCHAR(200) NOT NULL
        REFERENCES procedure_row_definitions(definition_key),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_procedure_template_revisions_identity') THEN
        CREATE UNIQUE INDEX uq_procedure_template_revisions_identity
            ON procedure_template_revisions(template_code, revision_hash);
    END IF;
END $$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_procedure_template_revisions_current') THEN
        CREATE UNIQUE INDEX uq_procedure_template_revisions_current
            ON procedure_template_revisions(template_code)
            WHERE is_current = true;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_procedure_row_definition_revision_member') THEN
        CREATE UNIQUE INDEX uq_procedure_row_definition_revision_member
            ON procedure_row_definition_revisions(
                template_code, revision_hash, sheet_key, definition_key
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_procedure_template_revisions_resolve
    ON procedure_template_revisions(template_code, status, is_current, revision_hash);
CREATE INDEX IF NOT EXISTS ix_procedure_row_definition_revisions_lookup
    ON procedure_row_definition_revisions(template_code, revision_hash)
    INCLUDE (sheet_key, definition_key);

-- Existing V105 definitions become explicit revision members.
INSERT INTO procedure_row_definition_revisions(
    template_code, revision_hash, sheet_key, definition_key
)
SELECT d.template_code, d.template_revision_hash, d.sheet_key, d.definition_key
FROM procedure_row_definitions d
ON CONFLICT (template_code, revision_hash, sheet_key, definition_key) DO NOTHING;

-- Backfill current only where the template has exactly one provable revision.
-- Ambiguous templates register every revision as reconcile_pending; no timestamp/hash guessing.
INSERT INTO procedure_template_revisions(
    template_code, revision_hash, status, is_current, reconcile_detail
)
SELECT x.template_code,
       x.revision_hash,
       CASE WHEN x.revision_count = 1 THEN 'current' ELSE 'reconcile_pending' END,
       (x.revision_count = 1),
       CASE WHEN x.revision_count = 1 THEN '{}'::jsonb
            ELSE jsonb_build_object('reason', 'multiple_revisions_require_reconcile',
                                    'revision_count', x.revision_count)
       END
FROM (
    SELECT dr.template_code,
           dr.template_revision_hash AS revision_hash,
           rc.revision_count
    FROM (
        SELECT DISTINCT template_code, template_revision_hash
        FROM procedure_row_definitions
    ) dr
    JOIN (
        SELECT template_code, count(*) AS revision_count
        FROM (
            SELECT DISTINCT template_code, template_revision_hash
            FROM procedure_row_definitions
        ) uniq
        GROUP BY template_code
    ) rc ON rc.template_code = dr.template_code
) x
ON CONFLICT (template_code, revision_hash) DO NOTHING;
-- History is append-only in normal application sessions. Controlled maintenance/test cleanup
-- must explicitly SET LOCAL app.procedure_history_maintenance = 'on'.
CREATE OR REPLACE FUNCTION prevent_procedure_row_task_history_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF current_setting('app.procedure_history_maintenance', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'procedure_row_task_history is append-only'
        USING ERRCODE = '55000';
END;
$$;

DROP TRIGGER IF EXISTS trg_procedure_row_task_history_append_only
    ON procedure_row_task_history;
CREATE TRIGGER trg_procedure_row_task_history_append_only
BEFORE UPDATE OR DELETE ON procedure_row_task_history
FOR EACH ROW EXECUTE FUNCTION prevent_procedure_row_task_history_mutation();

COMMENT ON TABLE procedure_template_revisions IS
    'Explicit current-revision registry. Imports register only and activate/reconcile switches current';
COMMENT ON TABLE procedure_row_definition_revisions IS
    'Revision membership for stable definition keys shared by multiple template revisions';