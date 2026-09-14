-- V150: 补齐 ai_chat_message.seq 的序列与默认值
--
-- ## 修的是什么
--
-- V147:284 写的是：
--     ALTER TABLE ai_chat_message ADD COLUMN IF NOT EXISTS seq BIGSERIAL;
--
-- `BIGSERIAL` 是语法糖，展开为「BIGINT + 建序列 + SET DEFAULT nextval(...) + NOT NULL」。
-- 但 `ADD COLUMN IF NOT EXISTS` 的语义是**整句跳过**：只要列已存在，
-- 序列和默认值就一次都不会被创建。
--
-- 而 `ai_chat_message.seq` 在 ORM 里也声明了（`app/models/ai_models.py` 的
-- `AIChatMessage.seq`）。于是在**全新环境**的标准引导顺序下：
--     ① Base.metadata.create_all()   ← 按 ORM 建出 nullable、无 default 的 seq 列
--     ② MigrationRunner.run_pending() ← V147 那句被 IF NOT EXISTS 跳过
-- ⇒ 序列 `ai_chat_message_seq_seq` **永不创建**，`seq` 恒为 NULL。
--
-- ## 后果（不是理论问题，已实测打红）
--
-- `load_recent_history()`（Req 4.10 / Property 10）的排序键是
-- `ORDER BY created_at DESC, seq DESC`。`created_at` 默认 `now()` =
-- **事务开始时刻**，同一事务内追加的多条消息时间完全相同，全靠 `seq` 定序。
-- seq 恒 NULL ⇒ 二级排序失效 ⇒ 同一时间戳的消息返回顺序不确定。
--
-- 2026-08-22 在干净 venv + 全新空库上实测：
--   backend/tests/dsh_agent_panel/test_task3_chat_persistence.py
--   「全量取回时顺序仍是插入序（含第 6/7 条同一时间，靠 seq 定序）」→ 打红
--   （第 7 条排到了第 6 条前面）。同一测试在 dev 库上是绿的。
--
-- ## 为什么 dev 库看不出来
--
-- dev 库上 `ai_chat_message` 表先于 V147 存在且**没有** seq 列
-- ⇒ V147 那句真正执行了 ⇒ 序列建好、默认值设上。实测两库对比：
--   dev   : seq | bigint | nextval('ai_chat_message_seq_seq'::regclass) | NOT NULL
--   clean : seq | bigint | (无 default)                                 | nullable
-- 这是本 spec CLOSURE「已修复项 §3b」记录的
-- 「create_all 抢先 ⇒ 迁移静默变 no-op」的**第二种形态**：
-- §3b 处理的是 `CREATE TABLE IF NOT EXISTS`（解法是引导时 DROP 那 4 张表让
-- V147 自己建），漏了 `ADD COLUMN IF NOT EXISTS` 这一类 —— 而 ai_chat_message
-- 是既有表、不在 DROP 列表里，所以同样的坑第二次生效。
--
-- ## 为什么新增迁移而不是改 V147
--
-- V147 已在 dev/生产应用过，改它会触发 `MigrationRunner.detect_checksum_drift`
-- 报漂移（已应用文件被事后编辑）。新增一条幂等迁移对两种环境都正确：
--   - 已有默认值的库：CREATE SEQUENCE IF NOT EXISTS 跳过，SET DEFAULT 幂等重设同一值
--   - 缺默认值的库：补齐序列 + 默认值 + 回填历史行 + NOT NULL

-- ── ① 建序列（幂等）。名字与 BIGSERIAL 自动生成的一致，dev 库上直接命中已存在 ──
CREATE SEQUENCE IF NOT EXISTS ai_chat_message_seq_seq AS BIGINT;

-- ── ② 绑定归属：序列随列删除（BIGSERIAL 的原生语义），幂等 ──
ALTER SEQUENCE ai_chat_message_seq_seq OWNED BY ai_chat_message.seq;

-- ── ③ 把序列游标推到当前最大值，避免与已有行冲突 ──
-- setval 的第三参 false 表示「下一次 nextval 返回该值本身」，
-- 故传 max(seq)+1；空表时 COALESCE 兜到 1。
SELECT setval(
    'ai_chat_message_seq_seq',
    COALESCE((SELECT MAX(seq) FROM ai_chat_message), 0) + 1,
    false
);

-- ── ④ 设默认值（幂等：重复执行只是重设为同一表达式）──
ALTER TABLE ai_chat_message
    ALTER COLUMN seq SET DEFAULT nextval('ai_chat_message_seq_seq');

-- ── ⑤ 回填历史 NULL 行 ──
-- 按 (created_at, id) 定序保证回填结果本身是确定的：
-- 不能只按 created_at（同一事务的行时间相同，那正是本迁移要修的问题），
-- 也不能不带 ORDER BY（UPDATE ... FROM 的行序不确定 ⇒ 回填结果每次不同）。
WITH ordered AS (
    SELECT id,
           ROW_NUMBER() OVER (ORDER BY created_at, id) AS rn
    FROM ai_chat_message
    WHERE seq IS NULL
),
base AS (
    SELECT COALESCE(MAX(seq), 0) AS max_seq FROM ai_chat_message
)
UPDATE ai_chat_message m
SET seq = base.max_seq + ordered.rn
FROM ordered, base
WHERE m.id = ordered.id;

-- ── ⑥ 推进序列游标到回填后的最大值 ──
SELECT setval(
    'ai_chat_message_seq_seq',
    COALESCE((SELECT MAX(seq) FROM ai_chat_message), 0) + 1,
    false
);

-- ── ⑦ 补 NOT NULL（BIGSERIAL 原生语义的最后一块）──
-- 放在回填之后，否则历史 NULL 行会让 SET NOT NULL 失败。
-- 用 DO 块判断，避免已是 NOT NULL 时重复执行报错。
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'ai_chat_message'
          AND column_name = 'seq'
          AND is_nullable = 'YES'
    ) THEN
        ALTER TABLE ai_chat_message ALTER COLUMN seq SET NOT NULL;
    END IF;
END $$;

COMMENT ON COLUMN ai_chat_message.seq IS
    '单调序（BIGSERIAL 语义）。created_at 默认 now() = 事务开始时刻，'
    '同一事务内多条消息时间相同，load_recent_history 的 ORDER BY 靠本列兜底。'
    'V150 补齐 V147 因 ADD COLUMN IF NOT EXISTS 被跳过而丢失的序列与默认值。';
