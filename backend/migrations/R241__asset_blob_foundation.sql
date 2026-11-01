-- 安全回退：存在跨域资产数据时禁止删表/列；平时只用于未启用的新环境。
DO $$
BEGIN
    IF to_regclass('public.knowledge_evidence_promotions') IS NOT NULL
       AND EXISTS (SELECT 1 FROM knowledge_evidence_promotions LIMIT 1) THEN
        RAISE EXCEPTION 'knowledge evidence promotions exist; refuse destructive rollback';
    END IF;
    IF to_regclass('public.ai_chat_run_resources') IS NOT NULL
       AND EXISTS (SELECT 1 FROM ai_chat_run_resources LIMIT 1) THEN
        RAISE EXCEPTION 'AI run resources exist; refuse destructive rollback';
    END IF;
    IF to_regclass('public.asset_blobs') IS NOT NULL
       AND EXISTS (SELECT 1 FROM asset_blobs LIMIT 1) THEN
        RAISE EXCEPTION 'asset blobs exist; refuse destructive rollback';
    END IF;
END $$;

DROP TRIGGER IF EXISTS trg_ai_run_resource_immutable ON ai_chat_run_resources;
DROP FUNCTION IF EXISTS gt_ai_run_resource_immutable();
DROP TABLE IF EXISTS ai_chat_run_resources;
DROP TRIGGER IF EXISTS trg_knowledge_evidence_promotion_append_only ON knowledge_evidence_promotions;
DROP FUNCTION IF EXISTS gt_knowledge_evidence_promotion_append_only();
DROP TABLE IF EXISTS knowledge_evidence_promotions;
ALTER TABLE knowledge_documents DROP CONSTRAINT IF EXISTS fk_knowledge_documents_blob;
ALTER TABLE attachment_versions DROP CONSTRAINT IF EXISTS fk_attachment_versions_blob;
DROP INDEX IF EXISTS ix_knowledge_documents_blob;
DROP INDEX IF EXISTS ix_attachment_versions_blob;
-- 先恢复 V106 版本不可变函数，再移除 blob_id；否则函数对该列的依赖会阻止 DROP COLUMN。
CREATE OR REPLACE FUNCTION evgov_attachment_version_immutable() RETURNS trigger AS $fn$
BEGIN
    IF NEW.byte_size IS DISTINCT FROM OLD.byte_size
       OR NEW.storage_key IS DISTINCT FROM OLD.storage_key
       OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
       OR NEW.attachment_id IS DISTINCT FROM OLD.attachment_id
       OR NEW.version_no IS DISTINCT FROM OLD.version_no
       OR NEW.actor_type IS DISTINCT FROM OLD.actor_type
       OR NEW.actor_user_id IS DISTINCT FROM OLD.actor_user_id
       OR NEW.actor_service_identity_id IS DISTINCT FROM OLD.actor_service_identity_id
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'attachment_versions immutable identity cannot be updated (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;
ALTER TABLE knowledge_documents DROP COLUMN IF EXISTS blob_id;
ALTER TABLE attachment_versions DROP COLUMN IF EXISTS blob_id;
DROP TRIGGER IF EXISTS trg_asset_blob_immutable ON asset_blobs;
DROP FUNCTION IF EXISTS gt_asset_blob_immutable();
DROP TABLE IF EXISTS asset_blobs;
