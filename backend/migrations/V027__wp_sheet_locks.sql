-- V027: 底稿 sheet 级软锁表
-- Requirements: 6.1, 6.4 — HTML 渲染器并发协作锁

CREATE TABLE IF NOT EXISTS wp_sheet_locks (
    id              VARCHAR(36) PRIMARY KEY,
    wp_id           VARCHAR(36) NOT NULL,
    sheet_name      VARCHAR(200) NOT NULL,
    locked_by       VARCHAR(36) NOT NULL,
    locked_by_name  VARCHAR(100) DEFAULT '',
    acquired_at     TIMESTAMP WITH TIME ZONE NOT NULL,
    heartbeat_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    released_at     TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_wp_sheet_locks_active
    ON wp_sheet_locks (wp_id, sheet_name)
    WHERE released_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_wp_sheet_locks_heartbeat
    ON wp_sheet_locks (heartbeat_at)
    WHERE released_at IS NULL;
