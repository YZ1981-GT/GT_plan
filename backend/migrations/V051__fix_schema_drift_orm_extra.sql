-- V051: 修复 orm_extra 类 schema 漂移（ORM 定义了但 DB 缺失的列）
-- 以及 enum_mismatch / type_mismatch

-- ============================================================
-- 1. deleted_at 列（软删除，全部 TIMESTAMPTZ NULL）
-- ============================================================
ALTER TABLE account_mapping ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE tb_ledger ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE adjustments ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE import_batches ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE account_chart ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE tb_aux_ledger ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE tb_balance ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE adjustment_entries ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE materiality ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE unadjusted_misstatements ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE trial_balance ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

-- ============================================================
-- 2. attachment_working_paper
-- ============================================================
ALTER TABLE attachment_working_paper ADD COLUMN IF NOT EXISTS working_paper_id UUID;
ALTER TABLE attachment_working_paper ADD COLUMN IF NOT EXISTS description TEXT;

-- ============================================================
-- 3. tb_aux_balance
-- ============================================================
ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS accounting_period INTEGER;

-- ============================================================
-- 4. t_account_entries
-- ============================================================
ALTER TABLE t_account_entries ADD COLUMN IF NOT EXISTS entry_date DATE;
ALTER TABLE t_account_entries ADD COLUMN IF NOT EXISTS counterpart_account VARCHAR(100);
ALTER TABLE t_account_entries ADD COLUMN IF NOT EXISTS credit_amount NUMERIC(20, 2);
ALTER TABLE t_account_entries ADD COLUMN IF NOT EXISTS debit_amount NUMERIC(20, 2);
ALTER TABLE t_account_entries ADD COLUMN IF NOT EXISTS cfs_category VARCHAR(50);

-- ============================================================
-- 5. disclosure_notes
-- ============================================================
ALTER TABLE disclosure_notes ADD COLUMN IF NOT EXISTS level SMALLINT;
ALTER TABLE disclosure_notes ADD COLUMN IF NOT EXISTS lock_number BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE disclosure_notes ADD COLUMN IF NOT EXISTS sort_index INTEGER NOT NULL DEFAULT 0;
ALTER TABLE disclosure_notes ADD COLUMN IF NOT EXISTS auto_numbering BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE disclosure_notes ADD COLUMN IF NOT EXISTS section_id VARCHAR(100);
ALTER TABLE disclosure_notes ADD COLUMN IF NOT EXISTS parent_section_id VARCHAR(100);
ALTER TABLE disclosure_notes ADD COLUMN IF NOT EXISTS locked_number VARCHAR(50);

-- ============================================================
-- 6. import_batches
-- ============================================================
ALTER TABLE import_batches ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
ALTER TABLE import_batches ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT false;

-- ============================================================
-- 7. review_messages
-- ============================================================
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS reason_code VARCHAR(50);
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS mentions JSONB;
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS message_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS reply_to UUID;
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS edited_at TIMESTAMPTZ;
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS trace_id VARCHAR(100);
ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS redaction_flag BOOLEAN NOT NULL DEFAULT false;

-- ============================================================
-- 8. wp_template_custom
-- ============================================================
ALTER TABLE wp_template_custom ADD COLUMN IF NOT EXISTS formula_valid BOOLEAN;

-- ============================================================
-- 9. custom_query_templates
-- ============================================================
ALTER TABLE custom_query_templates ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE custom_query_templates ADD COLUMN IF NOT EXISTS use_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE custom_query_templates ADD COLUMN IF NOT EXISTS creator_id UUID;
ALTER TABLE custom_query_templates ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMPTZ;

-- ============================================================
-- 10. time_machine_snapshots
-- ============================================================
ALTER TABLE time_machine_snapshots ADD COLUMN IF NOT EXISTS diff_patch JSONB;
ALTER TABLE time_machine_snapshots ADD COLUMN IF NOT EXISTS snapshot_data JSONB NOT NULL DEFAULT '{}';
ALTER TABLE time_machine_snapshots ADD COLUMN IF NOT EXISTS module VARCHAR(50) NOT NULL DEFAULT '';
ALTER TABLE time_machine_snapshots ADD COLUMN IF NOT EXISTS created_by UUID;

-- ============================================================
-- 11. review_conversations
-- ============================================================
ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;
ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS resolution_code VARCHAR(50);
ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS sla_due_at TIMESTAMPTZ;
ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS priority VARCHAR(20) DEFAULT 'medium';
ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS trace_id VARCHAR(100);
ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS resolved_by UUID;

-- ============================================================
-- 12. gate_decisions
-- ============================================================
ALTER TABLE gate_decisions ADD COLUMN IF NOT EXISTS context JSONB;

-- ============================================================
-- 13. enum_mismatch 修复
-- ============================================================
DO $$
BEGIN
    -- activation_type 缺少 force_unbind
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'force_unbind'
        AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'activation_type')) THEN
        ALTER TYPE activation_type ADD VALUE IF NOT EXISTS 'force_unbind';
    END IF;
END $$;

DO $$
BEGIN
    -- subsequent_event_type 缺少 ADJUSTING / NON_ADJUSTING
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'ADJUSTING'
        AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'subsequent_event_type')) THEN
        ALTER TYPE subsequent_event_type ADD VALUE IF NOT EXISTS 'ADJUSTING';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'NON_ADJUSTING'
        AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'subsequent_event_type')) THEN
        ALTER TYPE subsequent_event_type ADD VALUE IF NOT EXISTS 'NON_ADJUSTING';
    END IF;
END $$;

-- ============================================================
-- 14. type_mismatch: evidence_hash_checks.export_id
-- NOTE: ORM 业务定义为 VARCHAR(64)（非 UUID），不做类型变更。
-- ============================================================
