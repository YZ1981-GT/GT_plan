-- V092: 添加 cancel_requested 列 — 跨 worker 导入取消信号
-- 用途：worker 轮询此列（每 5s），检测到 TRUE 时优雅终止导入任务

ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN DEFAULT FALSE;

COMMENT ON COLUMN import_jobs.cancel_requested IS '跨 worker 取消信号：设为 TRUE 后 worker 在下次轮询时终止导入';
