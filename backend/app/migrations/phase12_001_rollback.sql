-- Phase 12 Migration 001 Rollback
DROP TABLE IF EXISTS wp_edit_sessions;
DROP TABLE IF EXISTS wp_recommendation_feedback;
DROP TABLE IF EXISTS background_job_items;
DROP TABLE IF EXISTS background_jobs;
DROP TABLE IF EXISTS wp_ai_generations;

ALTER TABLE working_paper DROP COLUMN IF EXISTS workflow_status;
ALTER TABLE working_paper DROP COLUMN IF EXISTS explanation_status;
ALTER TABLE working_paper DROP COLUMN IF EXISTS consistency_status;
ALTER TABLE working_paper DROP COLUMN IF EXISTS last_parsed_sync_at;
ALTER TABLE working_paper DROP COLUMN IF EXISTS partner_reviewed_at;
ALTER TABLE working_paper DROP COLUMN IF EXISTS partner_reviewed_by;
