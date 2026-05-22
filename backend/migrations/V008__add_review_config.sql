-- V008: Add review_config JSONB column to projects + extend WpReviewStatus enum
-- Phase 6 F8: 复核层级灵活化（2-4 级可配置）

-- 1. Add review_config column (safe: IF NOT EXISTS via ALTER TABLE ADD COLUMN IF NOT EXISTS)
ALTER TABLE projects ADD COLUMN IF NOT EXISTS review_config JSONB DEFAULT NULL;

-- 2. Extend wp_review_status enum with level3 and level4 values
ALTER TYPE wp_review_status ADD VALUE IF NOT EXISTS 'pending_level3';
ALTER TYPE wp_review_status ADD VALUE IF NOT EXISTS 'level3_in_progress';
ALTER TYPE wp_review_status ADD VALUE IF NOT EXISTS 'level3_passed';
ALTER TYPE wp_review_status ADD VALUE IF NOT EXISTS 'level3_rejected';
ALTER TYPE wp_review_status ADD VALUE IF NOT EXISTS 'pending_level4';
ALTER TYPE wp_review_status ADD VALUE IF NOT EXISTS 'level4_in_progress';
ALTER TYPE wp_review_status ADD VALUE IF NOT EXISTS 'level4_passed';
ALTER TYPE wp_review_status ADD VALUE IF NOT EXISTS 'level4_rejected';
