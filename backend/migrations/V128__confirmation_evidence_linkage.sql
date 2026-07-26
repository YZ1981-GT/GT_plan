-- V128: 函证证据链 — 发函/回函日期 + 附件链 + 操作审计留痕
-- Spec: confirmation-attachment-ocr-linkage / Task 1.2
-- Requirements: 2.1, 2.2, 8.3, 9.5, 9.6
-- Design: §Data Models（confirmation_attachment_link / confirmation_action_log / confirmations 新字段）
-- Properties: P2（append-only 不可篡改）, P11（additive 零回归）
--
-- 约定：
--   * additive-only：仅新增可空列 + 新表，不删除任何已有结构。
--   * 幂等：CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS / information_schema 守护 /
--     CREATE OR REPLACE FUNCTION / CREATE OR REPLACE TRIGGER / CREATE INDEX IF NOT EXISTS。
--   * 复用 V108 evgov_forbid_update() + V111 evgov_forbid_delete() 触发器模式。
--   * 前置：V127（adjustment_entries.detail_account_code）。

-- ============================================================
-- 1. confirmations 表追加可空字段（additive, information_schema 幂等守护）
-- ============================================================

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name = 'confirmations' AND column_name = 'sent_date') THEN
    ALTER TABLE confirmations ADD COLUMN sent_date DATE;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name = 'confirmations' AND column_name = 'reply_date') THEN
    ALTER TABLE confirmations ADD COLUMN reply_date DATE;
  END IF;
END $$;

-- ============================================================
-- 2. confirmation_attachment_link（附件角色 + 回函件↔发函件强配对 + 匹配状态）
-- ============================================================

CREATE TABLE IF NOT EXISTS confirmation_attachment_link (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    confirmation_id UUID NOT NULL REFERENCES confirmations(id) ON DELETE CASCADE,
    attachment_id UUID NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
    role VARCHAR(10) NOT NULL,
    paired_outbound_attachment_id UUID,
    match_status VARCHAR(12) NOT NULL DEFAULT 'manual',
    match_evidence JSONB,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_conf_att_link_role CHECK (role IN ('outbound', 'inbound')),
    CONSTRAINT chk_conf_att_link_match_status CHECK (match_status IN ('manual', 'auto', 'pending', 'assigned'))
);

CREATE INDEX IF NOT EXISTS idx_conf_att_link_conf_role ON confirmation_attachment_link(confirmation_id, role);
CREATE INDEX IF NOT EXISTS idx_conf_att_link_att ON confirmation_attachment_link(attachment_id);

COMMENT ON TABLE confirmation_attachment_link IS 'design §Data Models: 函证↔附件关联，role=outbound(发函件)/inbound(回函件)，inbound 强配对到 paired_outbound_attachment_id';

-- ============================================================
-- 3. confirmation_action_log（append-only 审计留痕）
-- ============================================================

CREATE TABLE IF NOT EXISTS confirmation_action_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    confirmation_id UUID NOT NULL,
    project_id UUID NOT NULL,
    action VARCHAR(24) NOT NULL,
    from_status VARCHAR(20),
    to_status VARCHAR(20),
    ocr_original JSONB,
    final_value JSONB,
    attachment_id UUID,
    reason TEXT,
    actor_user_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_conf_action_log_action CHECK (
        action IN ('reverse', 'apply_reply', 'match_assign', 'attachment_link', 'attachment_unlink')
    )
);

CREATE INDEX IF NOT EXISTS idx_conf_action_log_conf ON confirmation_action_log(confirmation_id);
CREATE INDEX IF NOT EXISTS idx_conf_action_log_project ON confirmation_action_log(project_id);

COMMENT ON TABLE confirmation_action_log IS 'design §Data Models: 函证操作审计留痕，append-only（DB 触发器禁 UPDATE/DELETE，复用 evgov_forbid_update/delete 模式）';

-- ============================================================
-- 4. Append-only 触发器 — 禁止 UPDATE 和 DELETE（复用 V108/V111 evgov 触发器函数）
--    evgov_forbid_update() 和 evgov_forbid_delete() 已在 V108/V111 中 CREATE OR REPLACE，
--    此处仅添加触发器绑定。
-- ============================================================

-- 确保触发器函数存在（幂等守护，万一 V108/V111 未执行时降级不崩）
CREATE OR REPLACE FUNCTION evgov_forbid_update() RETURNS trigger AS $fn$
BEGIN
    RAISE EXCEPTION '% 为不可变/append-only 表，禁止 UPDATE (id=%)', TG_TABLE_NAME, OLD.id
        USING ERRCODE = 'restrict_violation';
    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION evgov_forbid_delete() RETURNS trigger AS $fn$
BEGIN
    RAISE EXCEPTION '% 为不可变表，禁止 DELETE (id=%)', TG_TABLE_NAME, OLD.id
        USING ERRCODE = 'restrict_violation';
    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

-- 绑定 confirmation_action_log 的 append-only 触发器
CREATE OR REPLACE TRIGGER trg_conf_action_log_forbid_update
    BEFORE UPDATE ON confirmation_action_log
    FOR EACH ROW EXECUTE FUNCTION evgov_forbid_update();

CREATE OR REPLACE TRIGGER trg_conf_action_log_forbid_delete
    BEFORE DELETE ON confirmation_action_log
    FOR EACH ROW EXECUTE FUNCTION evgov_forbid_delete();
