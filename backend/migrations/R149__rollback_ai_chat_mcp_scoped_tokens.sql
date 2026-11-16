-- R149: 回滚 V149（MCP scoped token 审计/撤销）。
DO $$
BEGIN
    IF (to_regclass('public.ai_chat_mcp_call_log') IS NOT NULL AND EXISTS (SELECT 1 FROM ai_chat_mcp_call_log LIMIT 1))
       OR (to_regclass('public.ai_chat_mcp_token_revocations') IS NOT NULL AND EXISTS (SELECT 1 FROM ai_chat_mcp_token_revocations LIMIT 1)) THEN
        RAISE EXCEPTION 'R149 拒绝回滚：MCP 调用/撤销审计数据存在';
    END IF;
END $$;
DROP TABLE IF EXISTS ai_chat_mcp_token_revocations;
DROP TABLE IF EXISTS ai_chat_mcp_call_log;
ALTER TABLE ai_chat_runs DROP COLUMN IF EXISTS mcp_total_bytes;
ALTER TABLE ai_chat_runs DROP COLUMN IF EXISTS mcp_calls_used;
ALTER TABLE ai_chat_runs DROP COLUMN IF EXISTS mcp_token_issued;
