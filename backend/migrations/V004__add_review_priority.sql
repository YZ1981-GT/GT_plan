-- V004__add_review_priority.sql
-- Phase 2 F5: 复核意见优先级字段
-- must_fix = 必须修改（阻断重新提交）
-- suggest = 建议修改（默认）
-- info = 仅供参考

ALTER TABLE review_records ADD COLUMN IF NOT EXISTS priority VARCHAR(10) NOT NULL DEFAULT 'suggest';

-- 添加约束
ALTER TABLE review_records ADD CONSTRAINT chk_review_priority
  CHECK (priority IN ('must_fix', 'suggest', 'info'));

-- 索引（按优先级过滤查询）
CREATE INDEX IF NOT EXISTS idx_review_records_priority
  ON review_records (working_paper_id, priority)
  WHERE priority = 'must_fix';
