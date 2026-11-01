-- V236: Chat Run 重启恢复的最小上下文请求快照
-- 只保存 mention/附件稳定 ID、复核开关和 sheet；不保存正文、label、权限或项目断言。

ALTER TABLE ai_chat_runs
    ADD COLUMN IF NOT EXISTS context_request_snapshot JSONB NULL;

COMMENT ON COLUMN ai_chat_runs.context_request_snapshot IS
    'Minimal authorized-context request IDs for restart recovery; no content or permission claims';
