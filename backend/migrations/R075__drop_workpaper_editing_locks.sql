-- R075: 回滚 V075 — 重建 workpaper_editing_locks 空表
-- 注：仅重建表结构满足 V/R 配对完整性要求。
-- 单跑 R075 不能恢复 v1 功能（v1 service/router/注册已删，需配合 git revert + 恢复锁数据）。

CREATE TABLE IF NOT EXISTS workpaper_editing_locks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wp_id       UUID NOT NULL REFERENCES working_paper(id),
    staff_id    UUID NOT NULL REFERENCES users(id),
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    released_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_editing_locks_wp_id ON workpaper_editing_locks(wp_id);
CREATE INDEX IF NOT EXISTS idx_editing_locks_heartbeat_at ON workpaper_editing_locks(heartbeat_at);
