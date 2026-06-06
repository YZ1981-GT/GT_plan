-- V057: 通用编辑锁表（能力域 C — global-refinement-v5-closure）
-- 以 (resource_type, resource_id) 为锁维度，支持任意资源类型的编辑互斥

CREATE TABLE IF NOT EXISTS editing_locks (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_type VARCHAR(50)  NOT NULL,
    resource_id   VARCHAR(255) NOT NULL,
    holder_id     UUID         NOT NULL REFERENCES users(id),
    holder_name   VARCHAR(255),
    acquired_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    heartbeat_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    released_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_editing_locks_resource ON editing_locks (resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_editing_locks_heartbeat ON editing_locks (heartbeat_at);

-- 并发不变量最终防线：同资源未释放锁唯一（部分唯一索引）
CREATE UNIQUE INDEX IF NOT EXISTS uq_editing_locks_active
    ON editing_locks (resource_type, resource_id)
    WHERE released_at IS NULL;
