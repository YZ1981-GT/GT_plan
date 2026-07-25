-- V128: confirmation-attachment-ocr-linkage
-- 函证台账回函证据链：发函/回函日期 + 附件角色强配对 + append-only 审计留痕

-- 1) confirmations 加 sent_date / reply_date（幂等）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'confirmations' AND column_name = 'sent_date'
    ) THEN
        ALTER TABLE confirmations ADD COLUMN sent_date DATE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'confirmations' AND column_name = 'reply_date'
    ) THEN
        ALTER TABLE confirmations ADD COLUMN reply_date DATE;
    END IF;
END
$$;

-- 2) confirmation_attachment_link（附件角色 + 回函件↔发函件强配对 + 匹配状态）
CREATE TABLE IF NOT EXISTS confirmation_attachment_link (
    id                             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    confirmation_id                UUID NOT NULL REFERENCES confirmations(id) ON DELETE CASCADE,
    attachment_id                  UUID NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
    role                           VARCHAR(10) NOT NULL,
    paired_outbound_attachment_id  UUID,
    match_status                   VARCHAR(12) NOT NULL DEFAULT 'manual',
    match_evidence                 JSONB,
    created_by                     UUID,
    created_at                     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_conf_att_link_role CHECK (role IN ('outbound', 'inbound')),
    CONSTRAINT chk_conf_att_link_match_status CHECK (match_status IN ('manual', 'auto', 'pending', 'assigned'))
);

CREATE INDEX IF NOT EXISTS idx_conf_att_link_conf_role ON confirmation_attachment_link (confirmation_id, role);
CREATE INDEX IF NOT EXISTS idx_conf_att_link_att ON confirmation_attachment_link (attachment_id);

-- 3) confirmation_action_log（append-only 审计留痕）
CREATE TABLE IF NOT EXISTS confirmation_action_log (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    confirmation_id   UUID NOT NULL,
    project_id        UUID NOT NULL,
    action            VARCHAR(24) NOT NULL,
    from_status       VARCHAR(20),
    to_status         VARCHAR(20),
    ocr_original      JSONB,
    final_value       JSONB,
    attachment_id     UUID,
    reason            TEXT,
    actor_user_id     UUID NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_conf_action_log_action CHECK (
        action IN ('reverse','apply_reply','match_assign','attachment_link','attachment_unlink')
    )
);

CREATE INDEX IF NOT EXISTS idx_conf_action_log_conf ON confirmation_action_log (confirmation_id);
CREATE INDEX IF NOT EXISTS idx_conf_action_log_project ON confirmation_action_log (project_id);

-- 4) append-only 触发器：禁止 UPDATE/DELETE confirmation_action_log
CREATE OR REPLACE FUNCTION trg_conf_action_log_forbid_update()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'confirmation_action_log is append-only: UPDATE forbidden';
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION trg_conf_action_log_forbid_delete()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'confirmation_action_log is append-only: DELETE forbidden';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_conf_action_log_no_update ON confirmation_action_log;
CREATE TRIGGER trg_conf_action_log_no_update
    BEFORE UPDATE ON confirmation_action_log
    FOR EACH ROW EXECUTE FUNCTION trg_conf_action_log_forbid_update();

DROP TRIGGER IF EXISTS trg_conf_action_log_no_delete ON confirmation_action_log;
CREATE TRIGGER trg_conf_action_log_no_delete
    BEFORE DELETE ON confirmation_action_log
    FOR EACH ROW EXECUTE FUNCTION trg_conf_action_log_forbid_delete();
