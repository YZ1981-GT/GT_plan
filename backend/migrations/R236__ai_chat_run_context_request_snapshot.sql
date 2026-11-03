-- R236: 回滚 Chat Run 上下文请求快照

ALTER TABLE ai_chat_runs
    DROP COLUMN IF EXISTS context_request_snapshot;
