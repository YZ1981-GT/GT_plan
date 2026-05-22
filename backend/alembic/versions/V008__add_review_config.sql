-- V008: Add review_config JSONB column to projects + extend WpReviewStatus enum
-- Phase 6 F8: 复核层级灵活化（2-4 级可配置）

-- 1. Add review_config column to projects table
ALTER TABLE projects
ADD COLUMN IF NOT EXISTS review_config JSONB DEFAULT NULL;

COMMENT ON COLUMN projects.review_config IS
  '复核链配置: {"levels":2|3|4,"level_roles":{"L1":"manager","L2":"partner",...}}';

-- 2. Extend wp_review_status enum with level3 and level4 values
ALTER TYPE wp_review_status ADD VALUE IF NOT EXISTS 'pending_level3';
ALTER TYPE wp_review_status ADD VALUE IF NOT EXISTS 'level3_in_progress';
ALTER TYPE wp_review_status ADD VALUE IF NOT EXISTS 'level3_passed';
ALTER TYPE wp_review_status ADD VALUE IF NOT EXISTS 'level3_rejected';
ALTER TYPE wp_review_status ADD VALUE IF NOT EXISTS 'pending_level4';
ALTER TYPE wp_review_status ADD VALUE IF NOT EXISTS 'level4_in_progress';
ALTER TYPE wp_review_status ADD VALUE IF NOT EXISTS 'level4_passed';
ALTER TYPE wp_review_status ADD VALUE IF NOT EXISTS 'level4_rejected';
