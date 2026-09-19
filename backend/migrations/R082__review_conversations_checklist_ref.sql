-- Rollback
ALTER TABLE review_conversations DROP COLUMN IF EXISTS checklist_ref;
