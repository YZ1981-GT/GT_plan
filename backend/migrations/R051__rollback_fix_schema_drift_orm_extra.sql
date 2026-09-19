-- R051: Rollback for V051 (schema drift orm_extra fix)
-- NOTE: enum value removal is not supported in PG without recreating the type.
-- This rollback only removes added columns.

-- deleted_at columns
ALTER TABLE account_mapping DROP COLUMN IF EXISTS deleted_at;
ALTER TABLE tb_ledger DROP COLUMN IF EXISTS deleted_at;
ALTER TABLE tb_aux_balance DROP COLUMN IF EXISTS deleted_at;
ALTER TABLE adjustments DROP COLUMN IF EXISTS deleted_at;
ALTER TABLE import_batches DROP COLUMN IF EXISTS deleted_at;
ALTER TABLE account_chart DROP COLUMN IF EXISTS deleted_at;
ALTER TABLE tb_aux_ledger DROP COLUMN IF EXISTS deleted_at;
ALTER TABLE tb_balance DROP COLUMN IF EXISTS deleted_at;
ALTER TABLE adjustment_entries DROP COLUMN IF EXISTS deleted_at;
ALTER TABLE materiality DROP COLUMN IF EXISTS deleted_at;
ALTER TABLE unadjusted_misstatements DROP COLUMN IF EXISTS deleted_at;
ALTER TABLE trial_balance DROP COLUMN IF EXISTS deleted_at;

-- attachment_working_paper
ALTER TABLE attachment_working_paper DROP COLUMN IF EXISTS working_paper_id;
ALTER TABLE attachment_working_paper DROP COLUMN IF EXISTS description;

-- tb_aux_balance
ALTER TABLE tb_aux_balance DROP COLUMN IF EXISTS accounting_period;

-- t_account_entries
ALTER TABLE t_account_entries DROP COLUMN IF EXISTS entry_date;
ALTER TABLE t_account_entries DROP COLUMN IF EXISTS counterpart_account;
ALTER TABLE t_account_entries DROP COLUMN IF EXISTS credit_amount;
ALTER TABLE t_account_entries DROP COLUMN IF EXISTS debit_amount;
ALTER TABLE t_account_entries DROP COLUMN IF EXISTS cfs_category;

-- disclosure_notes
ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS level;
ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS lock_number;
ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS sort_index;
ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS auto_numbering;
ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS section_id;
ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS parent_section_id;
ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS locked_number;

-- import_batches
ALTER TABLE import_batches DROP COLUMN IF EXISTS updated_at;
ALTER TABLE import_batches DROP COLUMN IF EXISTS is_deleted;

-- review_messages
ALTER TABLE review_messages DROP COLUMN IF EXISTS reason_code;
ALTER TABLE review_messages DROP COLUMN IF EXISTS mentions;
ALTER TABLE review_messages DROP COLUMN IF EXISTS message_version;
ALTER TABLE review_messages DROP COLUMN IF EXISTS reply_to;
ALTER TABLE review_messages DROP COLUMN IF EXISTS edited_at;
ALTER TABLE review_messages DROP COLUMN IF EXISTS trace_id;
ALTER TABLE review_messages DROP COLUMN IF EXISTS redaction_flag;

-- wp_template_custom
ALTER TABLE wp_template_custom DROP COLUMN IF EXISTS formula_valid;

-- custom_query_templates
ALTER TABLE custom_query_templates DROP COLUMN IF EXISTS tags;
ALTER TABLE custom_query_templates DROP COLUMN IF EXISTS use_count;
ALTER TABLE custom_query_templates DROP COLUMN IF EXISTS creator_id;
ALTER TABLE custom_query_templates DROP COLUMN IF EXISTS last_used_at;

-- time_machine_snapshots
ALTER TABLE time_machine_snapshots DROP COLUMN IF EXISTS diff_patch;
ALTER TABLE time_machine_snapshots DROP COLUMN IF EXISTS snapshot_data;
ALTER TABLE time_machine_snapshots DROP COLUMN IF EXISTS module;
ALTER TABLE time_machine_snapshots DROP COLUMN IF EXISTS created_by;

-- review_conversations
ALTER TABLE review_conversations DROP COLUMN IF EXISTS resolved_at;
ALTER TABLE review_conversations DROP COLUMN IF EXISTS resolution_code;
ALTER TABLE review_conversations DROP COLUMN IF EXISTS sla_due_at;
ALTER TABLE review_conversations DROP COLUMN IF EXISTS priority;
ALTER TABLE review_conversations DROP COLUMN IF EXISTS trace_id;
ALTER TABLE review_conversations DROP COLUMN IF EXISTS resolved_by;

-- gate_decisions
ALTER TABLE gate_decisions DROP COLUMN IF EXISTS context;

-- evidence_hash_checks.export_id - no revert needed (kept as VARCHAR)
