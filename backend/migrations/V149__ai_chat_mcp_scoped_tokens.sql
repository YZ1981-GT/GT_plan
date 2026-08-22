-- V149: AI Chat MCP scoped tokens 与 budget tracking
-- dsh-agent-panel-integration Task 25 (Req 11.5/11.7/11.8)
--
-- 设计要点：
-- 1. mcp_token 是短命（<=5min）签名令牌，不需要 DB 存储 token 本身
-- 2. 本迁移只添加配额追踪和审计辅助表
-- 3. ai_chat_runs 增加 mcp_token_issued 标记
-- 4. 全部幂等（IF NOT EXISTS）

BEGIN;

-- 1. ai_chat_runs 新增 MCP token 标记列
ALTER TABLE ai_chat_runs
    ADD COLUMN IF NOT EXISTS mcp_token_issued BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE ai_chat_runs
    ADD COLUMN IF NOT EXISTS mcp_calls_used INTEGER NOT NULL DEFAULT 0;

ALTER TABLE ai_chat_runs
    ADD COLUMN IF NOT EXISTS mcp_total_bytes BIGINT NOT NULL DEFAULT 0;

-- 2. MCP 调用日志表（审计辅助，不是审计链本身，审计链走 audit_log）
CREATE TABLE IF NOT EXISTS ai_chat_mcp_call_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL,
    tool_call_id VARCHAR(128) NOT NULL,
    tool_name VARCHAR(64) NOT NULL,
    token_id VARCHAR(32) NOT NULL,
    user_id UUID NOT NULL,
    project_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'started',
    result_bytes INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    error_code VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 索引：按 run 查询 MCP 调用历史
CREATE INDEX IF NOT EXISTS idx_ai_chat_mcp_call_log_run
    ON ai_chat_mcp_call_log (run_id, created_at);

-- 索引：按 token 查询（撤销审计）
CREATE INDEX IF NOT EXISTS idx_ai_chat_mcp_call_log_token
    ON ai_chat_mcp_call_log (token_id);

-- 3. MCP token 撤销记录（持久化，跨进程可见）
CREATE TABLE IF NOT EXISTS ai_chat_mcp_token_revocations (
    token_id VARCHAR(32) PRIMARY KEY,
    run_id UUID NOT NULL,
    user_id UUID NOT NULL,
    revoked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason VARCHAR(64) NOT NULL DEFAULT 'run_terminal'
);

-- 索引：按 run 批量撤销
CREATE INDEX IF NOT EXISTS idx_ai_chat_mcp_token_revocations_run
    ON ai_chat_mcp_token_revocations (run_id);

-- 4. TTL 清理：撤销记录保留 24 小时（token 最长 5 分钟，保留 24h 是冗余安全边际）
-- 定期清理由后台 job 执行，不在迁移中添加触发器

COMMIT;
