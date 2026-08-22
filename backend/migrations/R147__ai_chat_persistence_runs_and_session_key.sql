-- R147: 回滚 V147（AI chat 持久化模型增强与并发约束）
--
-- Spec: dsh-agent-panel-integration — Wave 2 Task 3
--
-- ⚠️ 回滚会丢弃：
--   - 全部 Chat Run / 工具调用 / 会话附件 metadata / 幂等收据（四张新表整表 DROP）；
--     附件的**物理文件不会被删除**（metadata 没了即失去追踪），回滚前须先跑
--     附件清理或自行记录 storage/ai_chat/ 下的孤儿文件。
--   - ai_chat_message 的 run 关联、status、content_hash、context_manifest 与 seq；
--     消息正文与 referenced_sources（citations）不受影响。
--   - ai_chat_session 的 session_key / host_type / host_id / audit_year /
--     engine_preference / review_mode / last_message_at。
--
-- ⚠️ **V147 的会话合并不可逆**：被合并的重复会话行已删除、其消息已改挂到胜者。
--    回滚只是去掉字段与约束，不会把合并过的会话拆回来（拆回需要 pg_dump 备份）。
--
-- project_id 的 NOT NULL 恢复是**条件性**的：若已存在无项目的全局知识会话，
-- 强行加回 NOT NULL 会失败，故用 DO 块判断——有 NULL 行时跳过并 RAISE NOTICE，
-- 让"回滚后 schema 与 V147 前不完全一致"这件事可见，而不是静默失败。

DROP TABLE IF EXISTS ai_chat_action_receipts;
DROP TABLE IF EXISTS ai_chat_attachments;
DROP TABLE IF EXISTS ai_chat_tool_calls;

ALTER TABLE ai_chat_message DROP CONSTRAINT IF EXISTS ck_ai_chat_message_status;

DROP INDEX IF EXISTS ix_ai_chat_message_recent;
DROP INDEX IF EXISTS ix_ai_chat_message_run;

ALTER TABLE ai_chat_message
    DROP COLUMN IF EXISTS context_manifest,
    DROP COLUMN IF EXISTS content_hash,
    DROP COLUMN IF EXISTS status,
    DROP COLUMN IF EXISTS run_id,
    DROP COLUMN IF EXISTS seq;

-- ai_chat_message.run_id 已删 ⇒ 此时才能安全 DROP runs 表
DROP TABLE IF EXISTS ai_chat_runs;

DROP INDEX IF EXISTS uq_ai_chat_session_user_key;
DROP INDEX IF EXISTS ix_ai_chat_session_host;

ALTER TABLE ai_chat_session DROP CONSTRAINT IF EXISTS ck_ai_chat_session_host_type;
ALTER TABLE ai_chat_session DROP CONSTRAINT IF EXISTS ck_ai_chat_session_engine;
ALTER TABLE ai_chat_session DROP CONSTRAINT IF EXISTS ck_ai_chat_session_project_required;

ALTER TABLE ai_chat_session
    DROP COLUMN IF EXISTS last_message_at,
    DROP COLUMN IF EXISTS review_mode,
    DROP COLUMN IF EXISTS engine_preference,
    DROP COLUMN IF EXISTS audit_year,
    DROP COLUMN IF EXISTS host_id,
    DROP COLUMN IF EXISTS host_type,
    DROP COLUMN IF EXISTS session_key;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM ai_chat_session WHERE project_id IS NULL) THEN
        RAISE NOTICE 'R147: ai_chat_session 存在 project_id 为 NULL 的行（全局知识会话），'
                     '跳过恢复 NOT NULL —— 回滚后 schema 与 V147 前不完全一致，'
                     '需先清理或迁移这些会话';
    ELSE
        ALTER TABLE ai_chat_session ALTER COLUMN project_id SET NOT NULL;
    END IF;
END
$$;
