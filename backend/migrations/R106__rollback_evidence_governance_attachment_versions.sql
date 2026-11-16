-- R106: 回滚 V106（Evidence Governance AttachmentVersion 基础结构）。
-- 证据版本、隔离句柄和 service identity 是审计/合规事实；有数据时拒绝自动删除。
DO $$
BEGIN
    IF (to_regclass('public.service_identities') IS NOT NULL AND EXISTS (SELECT 1 FROM service_identities LIMIT 1))
       OR (to_regclass('public.evidence_upload_attempts') IS NOT NULL AND EXISTS (SELECT 1 FROM evidence_upload_attempts LIMIT 1))
       OR (to_regclass('public.evidence_quarantine_handles') IS NOT NULL AND EXISTS (SELECT 1 FROM evidence_quarantine_handles LIMIT 1))
       OR (to_regclass('public.attachment_versions') IS NOT NULL AND EXISTS (SELECT 1 FROM attachment_versions LIMIT 1)) THEN
        RAISE EXCEPTION 'R106 拒绝回滚：证据治理对象存在数据，必须使用备份恢复';
    END IF;
END $$;
DO $$ BEGIN
    IF to_regclass('public.trg_av_immutable') IS NOT NULL THEN DROP TRIGGER trg_av_immutable ON attachment_versions; END IF;
    IF to_regclass('public.trg_av_previous_link') IS NOT NULL THEN DROP TRIGGER trg_av_previous_link ON attachment_versions; END IF;
    IF to_regclass('public.trg_attachment_current_link') IS NOT NULL THEN DROP TRIGGER trg_attachment_current_link ON attachments; END IF;
END $$;
DROP FUNCTION IF EXISTS evgov_attachment_version_immutable();
DROP FUNCTION IF EXISTS evgov_check_av_previous();
DROP FUNCTION IF EXISTS evgov_check_attachment_current();
DROP TABLE IF EXISTS attachment_versions;
DROP TABLE IF EXISTS evidence_quarantine_handles;
DROP TABLE IF EXISTS evidence_upload_attempts;
ALTER TABLE attachments DROP COLUMN IF EXISTS original_creator_unknown;
ALTER TABLE attachments DROP COLUMN IF EXISTS actor_service_identity_id;
ALTER TABLE attachments DROP COLUMN IF EXISTS actor_user_id;
ALTER TABLE attachments DROP COLUMN IF EXISTS actor_type;
ALTER TABLE attachments DROP COLUMN IF EXISTS current_version_id;
ALTER TABLE attachments DROP COLUMN IF EXISTS state;
ALTER TABLE attachments DROP COLUMN IF EXISTS metadata_missing;
ALTER TABLE attachments DROP COLUMN IF EXISTS metadata_status;
ALTER TABLE attachments DROP COLUMN IF EXISTS is_key_evidence;
ALTER TABLE attachments DROP COLUMN IF EXISTS provider;
ALTER TABLE attachments DROP COLUMN IF EXISTS obtained_at;
ALTER TABLE attachments DROP COLUMN IF EXISTS source_type;
ALTER TABLE attachments DROP COLUMN IF EXISTS original_file_name;
ALTER TABLE attachments DROP COLUMN IF EXISTS audit_year;
