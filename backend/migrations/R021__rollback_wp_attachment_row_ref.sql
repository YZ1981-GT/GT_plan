-- R021: Rollback row_ref column from attachment_working_paper

DROP INDEX IF EXISTS idx_awp_row_ref;
ALTER TABLE attachment_working_paper DROP COLUMN IF EXISTS row_ref;
