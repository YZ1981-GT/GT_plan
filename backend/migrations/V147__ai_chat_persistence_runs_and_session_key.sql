-- V147: AI chat 持久化模型增强与并发约束
--
-- Spec: dsh-agent-panel-integration — Wave 2 Task 3
-- Requirements: 4.10（history 最近 N 条 + 真实元数据）、4.11（会话定位绑定
--   user/project/year/host type/host ID 且有数据库唯一约束）、7.3（附件 metadata）、
--   8.2/8.3（笔记转存幂等：单一定位规则 + 数据库唯一约束，而非"先查后建"）
-- Design: "Components and Interfaces → 6. Persistence Model"
-- Properties: 6（会话与 Run 并发幂等）、10（最近历史顺序与元数据完整）、
--   21（项目笔记并发幂等）
--
-- ═══ 编号沿革 ═══
-- 本 spec 明确不预占 V 号（tasks.md Notes 3）。落地时实测：磁盘
-- `backend/migrations/V*.sql` 共 146 个、最大号 146；`schema_version` 表
-- `MAX(version)` 同为 '146'（磁盘与库双侧一致）⇒ 取 V147。
-- `R1xx__` 是配对回滚脚本，不占用 V 号空间。
--
-- ═══ 复用而非新造 ═══
-- `ai_chat_session` / `ai_chat_message` 已存在（ORM: AIChatSession / AIChatMessage），
-- 本迁移**扩展**它们，不建第二套会话/消息表：
--   - citations 复用既有 `ai_chat_message.referenced_sources`（JSONB），不新增列；
--   - model / token / latency 复用既有 `model_used` / `tokens_used` / `latency_ms`。
-- 新增的只有 design 明列的四张表 + 各表缺失字段。
--
-- ═══ 为什么状态列用 VARCHAR + CHECK 而非 PG enum ═══
-- MigrationRunner 把**整个文件放在一个事务**里执行（`_apply_migration` 的
-- `engine.begin()`）。PG 不允许在同一事务内 `ALTER TYPE ... ADD VALUE` 之后立即
-- 使用该新值，因此"加枚举值 + 同文件写入该值"必然失败。本迁移的取值域全部走
-- VARCHAR + CHECK，从根上避开该约束，也让取值域的单一真源留在 Python 侧
-- （`app/models/ai_models.py` 的 ChatRunStatus / ChatMessageStatus /
-- AttachmentOcrStatus / ActionReceiptStatus / ChatEngineName / HostType），
-- 由守卫对 `pg_get_constraintdef` 与枚举做**双向**比对锁死（不允许单向包含）。
--
-- ═══ 时间列类型的取舍（有意不统一，勿"顺手改齐"）═══
--   - `ai_chat_session.last_message_at` 用 **TIMESTAMP（naive）**：与该表既有
--     `created_at` / `updated_at` 及 `ai_chat_message.created_at` 同类型，
--     history 排序、回填 MAX(created_at) 都不跨类型比较，避免隐式时区转换。
--   - 四张**新表**用 **TIMESTAMPTZ**：lease 过期、run 超时要与 `now()` 做绝对
--     时间比较，naive 列在跨时区部署下会算错。新表内部自洽，不与旧列比较。
--   🔴 Python 侧回写 timestamptz 必须传 `datetime` 对象；`CAST(:x AS timestamptz)`
--      在 asyncpg 下无效（驱动按目标类型先编码再发送）。
--
-- 幂等：全部 DDL 走 `IF NOT EXISTS`；ADD CONSTRAINT 无 IF NOT EXISTS 语法，
-- 用 `pg_constraint` 存在性判断的 DO 块包裹。可重复执行。

-- ---------------------------------------------------------------------------
-- ① ai_chat_session 扩展
-- ---------------------------------------------------------------------------

ALTER TABLE ai_chat_session
    ADD COLUMN IF NOT EXISTS session_key       VARCHAR(64),
    ADD COLUMN IF NOT EXISTS host_type         VARCHAR(32),
    ADD COLUMN IF NOT EXISTS host_id           VARCHAR(128),
    ADD COLUMN IF NOT EXISTS audit_year        INTEGER,
    ADD COLUMN IF NOT EXISTS engine_preference VARCHAR(32),
    ADD COLUMN IF NOT EXISTS review_mode       BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS last_message_at   TIMESTAMP;

COMMENT ON COLUMN ai_chat_session.session_key IS
    '服务端规范化会话定位 hash（sha256 hex，输入含 user/project/year/host type/host ID）；'
    '唯一真源 = app/services/ai_chat/persistence.py::build_session_key。客户端不得提交';
COMMENT ON COLUMN ai_chat_session.host_type IS
    '宿主类型，取值域 = app/services/ai_chat/contracts.py::HostType';
COMMENT ON COLUMN ai_chat_session.host_id IS
    '宿主稳定 ID；无项目的全局知识模式使用显式 sentinel "global-knowledge"，禁止空字符串';
COMMENT ON COLUMN ai_chat_session.engine_preference IS
    '服务端记录的 engine（native/dsh）；由服务端 config/feature flag 决定，客户端不可覆盖';
COMMENT ON COLUMN ai_chat_session.last_message_at IS
    '最后一条消息时间（naive，与 ai_chat_message.created_at 同类型，供会话列表排序）';

-- 全局知识模式（无项目）不得用空 UUID 伪装项目 ⇒ project_id 允许为 NULL，
-- 但**只允许** host_type = 'global_knowledge' 的会话为 NULL（下方 CHECK 锁死）。
ALTER TABLE ai_chat_session ALTER COLUMN project_id DROP NOT NULL;

-- ---------------------------------------------------------------------------
-- ② 回填 session_key / host_type / host_id（在建唯一约束**之前**）
--
-- 存量定位键在 `context_summary`，格式 "{doc_type}:{doc_id}:{user_id}"
-- （app/services/doc_chat_persistence.py::_locator）。回填规则：
--   - 只回填 user_id 非空、且 context_summary 严格匹配三段式定位键的行；
--   - doc_type → host_type、doc_id → host_id；
--   - audit_year 存量未记录 ⇒ 保持 NULL，key 里以 '-' 占位（与 Python 侧
--     build_session_key(audit_year=None) 完全一致）；
--   - 不匹配定位键格式的行（context_summary 被当作真正的"上下文摘要"使用）
--     session_key 保持 NULL ⇒ 不受唯一约束管辖，数据零改动。
--
-- 🔴 canonical 串必须与 Python 侧逐字一致，否则运行时 upsert 会与存量行错位、
--    产生"同一会话两行"。守卫 test_session_key_sql_backfill_matches_python
--    直接把这段 SQL 表达式与 build_session_key() 对同一输入求值比对。
-- ---------------------------------------------------------------------------

UPDATE ai_chat_session s
SET host_type = split_part(s.context_summary, ':', 1),
    host_id   = split_part(s.context_summary, ':', 2),
    session_key = encode(
        sha256(convert_to(
            'v1|' || s.user_id::text
                  || '|' || COALESCE(s.project_id::text, 'global-knowledge')
                  || '|' || COALESCE(s.audit_year::text, '-')
                  || '|' || split_part(s.context_summary, ':', 1)
                  || '|' || split_part(s.context_summary, ':', 2),
            'UTF8'
        )),
        'hex'
    )
WHERE s.session_key IS NULL
  AND s.user_id IS NOT NULL
  AND s.context_summary ~ '^[a-z_]+:[^:]+:[0-9a-fA-F-]{36}$'
  AND split_part(s.context_summary, ':', 1) IN (
        'workpaper', 'note', 'report', 'knowledge_doc',
        'knowledge_folder', 'global_knowledge'
      );

-- ---------------------------------------------------------------------------
-- ③ 合并重复 locator（在建唯一约束**之前**）
--
-- ═══ 去重规则（显式记录，勿凭直觉改）═══
-- 同一 (user_id, session_key) 分组内：
--   胜者 = total_messages 最多者；并列取 created_at 最早者；再并列取 id 最小者。
--   （消息最多 = 信息量最大；created_at 最早 = 原始会话；id 最小 = 确定性兜底，
--     三级排序保证任何数据分布下胜者唯一且可复现。）
-- 败者处理：其 ai_chat_message 全部**改挂**到胜者（不删消息，历史零丢失），
--   随后删除败者会话行。
-- 之后统一按 ai_chat_message 重算胜者的 total_messages / total_tokens /
--   last_message_at（合并后计数必须与消息实况一致）。
-- ---------------------------------------------------------------------------

WITH ranked AS (
    SELECT s.id,
           first_value(s.id) OVER (
               PARTITION BY s.user_id, s.session_key
               ORDER BY s.total_messages DESC NULLS LAST, s.created_at ASC, s.id ASC
           ) AS winner_id
    FROM ai_chat_session s
    WHERE s.session_key IS NOT NULL AND s.user_id IS NOT NULL
)
UPDATE ai_chat_message m
SET session_id = r.winner_id
FROM ranked r
WHERE m.session_id = r.id
  AND r.id <> r.winner_id;

WITH ranked AS (
    SELECT s.id,
           first_value(s.id) OVER (
               PARTITION BY s.user_id, s.session_key
               ORDER BY s.total_messages DESC NULLS LAST, s.created_at ASC, s.id ASC
           ) AS winner_id
    FROM ai_chat_session s
    WHERE s.session_key IS NOT NULL AND s.user_id IS NOT NULL
)
DELETE FROM ai_chat_session s
USING ranked r
WHERE s.id = r.id
  AND r.id <> r.winner_id;

UPDATE ai_chat_session s
SET total_messages  = agg.msg_count,
    total_tokens    = agg.token_sum,
    last_message_at = agg.last_at
FROM (
    SELECT session_id,
           COUNT(*)::int AS msg_count,
           COALESCE(SUM(COALESCE(tokens_used, 0)), 0)::int AS token_sum,
           MAX(created_at) AS last_at
    FROM ai_chat_message
    GROUP BY session_id
) agg
WHERE s.id = agg.session_id;

-- ---------------------------------------------------------------------------
-- ④ ai_chat_session 约束与索引（Req 4.11：数据库唯一约束 + 原子 upsert）
--
-- 部分唯一索引而非表级 UNIQUE：session_key 为 NULL 的存量/非定位键会话不受管辖
-- （PG 的 NULL 在唯一索引里互不相等，若不加谓词这类行会各自占位、语义含混）。
-- 🔴 ON CONFLICT 推断该索引时**必须**带同样的谓词：
--    ON CONFLICT (user_id, session_key) WHERE user_id IS NOT NULL AND session_key IS NOT NULL
-- ---------------------------------------------------------------------------

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_chat_session_user_key
    ON ai_chat_session (user_id, session_key)
    WHERE user_id IS NOT NULL AND session_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_ai_chat_session_host
    ON ai_chat_session (user_id, host_type, host_id, last_message_at DESC);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_ai_chat_session_host_type'
    ) THEN
        ALTER TABLE ai_chat_session ADD CONSTRAINT ck_ai_chat_session_host_type
            CHECK (host_type IS NULL OR host_type IN (
                'workpaper', 'note', 'report', 'knowledge_doc',
                'knowledge_folder', 'global_knowledge'
            ));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_ai_chat_session_engine'
    ) THEN
        ALTER TABLE ai_chat_session ADD CONSTRAINT ck_ai_chat_session_engine
            CHECK (engine_preference IS NULL OR engine_preference IN ('native', 'dsh'));
    END IF;
    -- 无项目会话只允许全局知识模式（禁止空 UUID / 空串伪装项目）
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_ai_chat_session_project_required'
    ) THEN
        ALTER TABLE ai_chat_session ADD CONSTRAINT ck_ai_chat_session_project_required
            CHECK (project_id IS NOT NULL OR host_type = 'global_knowledge');
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- ⑤ ai_chat_runs（唯一键 (actor_id, session_id, idempotency_key)）
--
-- 先于 ai_chat_message 的 run_id 外键创建。状态机（design §4）：
--   queued → running → done | error | cancelled
--   queued → cancelled
--   running（lease 过期）→ interrupted → queued | error
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ai_chat_runs (
    id                  UUID         PRIMARY KEY,
    session_id          UUID         NOT NULL REFERENCES ai_chat_session(id) ON DELETE CASCADE,
    request_id          UUID         NOT NULL,
    idempotency_key     VARCHAR(128) NOT NULL,
    actor_id            UUID         NOT NULL REFERENCES users(id),
    project_id          UUID         REFERENCES projects(id),
    host_type           VARCHAR(32)  NOT NULL,
    host_id             VARCHAR(128) NOT NULL,
    engine              VARCHAR(32)  NOT NULL,
    status              VARCHAR(16)  NOT NULL DEFAULT 'queued',
    capability_snapshot JSONB,
    queued_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    cancel_requested_at TIMESTAMPTZ,
    error_code          VARCHAR(64),
    usage               JSONB,
    latency_ms          INTEGER,
    retry_count         INTEGER      NOT NULL DEFAULT 0,
    lease_owner         VARCHAR(128),
    lease_expires_at    TIMESTAMPTZ,
    CONSTRAINT ck_ai_chat_runs_status CHECK (status IN (
        'queued', 'running', 'done', 'error', 'cancelled', 'interrupted'
    )),
    CONSTRAINT ck_ai_chat_runs_engine CHECK (engine IN ('native', 'dsh')),
    CONSTRAINT ck_ai_chat_runs_host_type CHECK (host_type IN (
        'workpaper', 'note', 'report', 'knowledge_doc',
        'knowledge_folder', 'global_knowledge'
    )),
    CONSTRAINT ck_ai_chat_runs_project_required CHECK (
        project_id IS NOT NULL OR host_type = 'global_knowledge'
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_chat_runs_idempotency
    ON ai_chat_runs (actor_id, session_id, idempotency_key);

CREATE INDEX IF NOT EXISTS ix_ai_chat_runs_session
    ON ai_chat_runs (session_id, queued_at DESC);

-- 启动恢复扫描：lease 过期的 running run（design §5 步骤 7）
CREATE INDEX IF NOT EXISTS ix_ai_chat_runs_lease
    ON ai_chat_runs (status, lease_expires_at)
    WHERE status IN ('queued', 'running');

COMMENT ON TABLE ai_chat_runs IS
    'Chat Run（一次模型/Agent 执行）。唯一键 (actor_id, session_id, idempotency_key) '
    '由数据库保证幂等：重复提交返回原 run，不重复调用 engine（Req 4.6，Property 6）';
COMMENT ON COLUMN ai_chat_runs.usage IS 'token usage 摘要；不逐 token 写行（Req 4.12）';

-- ---------------------------------------------------------------------------
-- ⑥ ai_chat_message 扩展（run/status/content hash/context manifest）
--
-- citations 复用既有 `referenced_sources`，**不新增 citations 列**。
-- `seq` 是新增的单调序：`created_at` 默认 `now()` = **事务开始时刻**，同一事务内
-- 追加的多条消息 created_at 完全相同 ⇒ 仅按 created_at 排序无法给出确定顺序，
-- Req 4.10 的"最近 N 条 + 时间正序"就无法验证（会成为假绿）。BIGSERIAL 在
-- ADD COLUMN 时按物理顺序回填存量行，故存量历史顺序保持不变。
-- ---------------------------------------------------------------------------

ALTER TABLE ai_chat_message
    ADD COLUMN IF NOT EXISTS seq              BIGSERIAL,
    ADD COLUMN IF NOT EXISTS run_id           UUID REFERENCES ai_chat_runs(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS status           VARCHAR(16) NOT NULL DEFAULT 'completed',
    ADD COLUMN IF NOT EXISTS content_hash     VARCHAR(64),
    ADD COLUMN IF NOT EXISTS context_manifest JSONB;

COMMENT ON COLUMN ai_chat_message.seq IS
    '单调插入序（history 排序的确定性兜底：created_at 默认 now() 在同一事务内相同）';
COMMENT ON COLUMN ai_chat_message.status IS
    'draft/completed/failed/cancelled；只有 completed assistant 消息可被复制/转存/采纳（Req 8.1）';
COMMENT ON COLUMN ai_chat_message.referenced_sources IS
    'citations（本列即 citations 的单一存放位置，勿新增 citations 列）';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_ai_chat_message_status'
    ) THEN
        ALTER TABLE ai_chat_message ADD CONSTRAINT ck_ai_chat_message_status
            CHECK (status IN ('draft', 'completed', 'failed', 'cancelled'));
    END IF;
END
$$;

-- history "倒序取最近 N 条"的支撑索引（外层再正序）
CREATE INDEX IF NOT EXISTS ix_ai_chat_message_recent
    ON ai_chat_message (session_id, created_at DESC, seq DESC);

CREATE INDEX IF NOT EXISTS ix_ai_chat_message_run
    ON ai_chat_message (run_id)
    WHERE run_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- ⑦ ai_chat_tool_calls（不保存 scoped token / 完整入参）
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ai_chat_tool_calls (
    id             UUID         PRIMARY KEY,
    run_id         UUID         NOT NULL REFERENCES ai_chat_runs(id) ON DELETE CASCADE,
    parent_call_id UUID         REFERENCES ai_chat_tool_calls(id) ON DELETE SET NULL,
    tool_call_id   VARCHAR(128) NOT NULL,
    tool_name      VARCHAR(128) NOT NULL,
    arg_hash       VARCHAR(64),
    result_bytes   INTEGER,
    status         VARCHAR(16)  NOT NULL DEFAULT 'started',
    error_code     VARCHAR(64),
    started_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finished_at    TIMESTAMPTZ,
    CONSTRAINT ck_ai_chat_tool_calls_status CHECK (status IN (
        'started', 'finished', 'failed', 'cancelled'
    ))
);

-- 同一 run 内 tool_call_id 唯一 ⇒ 重放/重连不会写重复工具调用行
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_chat_tool_calls_run_call
    ON ai_chat_tool_calls (run_id, tool_call_id);

CREATE INDEX IF NOT EXISTS ix_ai_chat_tool_calls_run
    ON ai_chat_tool_calls (run_id, started_at);

COMMENT ON TABLE ai_chat_tool_calls IS
    '工具调用摘要。arg_hash 为入参哈希，**不得**保存 scoped token 或完整入参正文（Req 11.9/12.7）';

-- ---------------------------------------------------------------------------
-- ⑧ ai_chat_attachments（Req 7.3：ID/owner/project/session/run/hash/状态/路径/
--    大小/MIME/创建时间/过期时间；另加 legal_hold 与 deleted_at 供清理策略）
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ai_chat_attachments (
    id                 UUID         PRIMARY KEY,
    owner_id           UUID         NOT NULL REFERENCES users(id),
    project_id         UUID         REFERENCES projects(id),
    -- 🔴 RESTRICT 而非 CASCADE：Req 7.9 明令"磁盘删除失败不得删除 metadata 后失去追踪"。
    -- 若这里 CASCADE，clear session 会把附件 metadata 连带删掉，storage/ai_chat/ 下的
    -- 物理文件就变成无人知晓的孤儿 —— 正是该 AC 要防的形态。RESTRICT 把"先清文件、
    -- 再标 deleted、最后才可删会话"这个顺序变成**数据库层的硬约束**而不是注释约定。
    session_id         UUID         NOT NULL REFERENCES ai_chat_session(id) ON DELETE RESTRICT,
    run_id             UUID         REFERENCES ai_chat_runs(id) ON DELETE SET NULL,
    sha256             VARCHAR(64)  NOT NULL,
    original_name      VARCHAR(255) NOT NULL,
    storage_name       VARCHAR(255) NOT NULL,
    mime_type          VARCHAR(128) NOT NULL,
    size_bytes         BIGINT       NOT NULL,
    ocr_status         VARCHAR(16)  NOT NULL DEFAULT 'pending',
    ocr_text_protected TEXT,
    error_code         VARCHAR(64),
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at         TIMESTAMPTZ,
    legal_hold         BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at         TIMESTAMPTZ,
    CONSTRAINT ck_ai_chat_attachments_ocr_status CHECK (ocr_status IN (
        'pending', 'running', 'succeeded', 'empty',
        'failed', 'unavailable', 'timeout', 'cancelled'
    )),
    CONSTRAINT ck_ai_chat_attachments_size CHECK (size_bytes >= 0)
);

-- 同一 owner + session 内相同内容幂等（Req 7：重复 owner/session/hash 幂等）
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_chat_attachments_owner_session_hash
    ON ai_chat_attachments (owner_id, session_id, sha256)
    WHERE deleted_at IS NULL;

-- 服务端随机文件名全局唯一（防止不同附件落到同一物理文件）
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_chat_attachments_storage_name
    ON ai_chat_attachments (storage_name);

-- 过期清理扫描：未删除、非 legal hold、已到期
CREATE INDEX IF NOT EXISTS ix_ai_chat_attachments_expiry
    ON ai_chat_attachments (expires_at)
    WHERE deleted_at IS NULL AND legal_hold = FALSE;

CREATE INDEX IF NOT EXISTS ix_ai_chat_attachments_session
    ON ai_chat_attachments (session_id, created_at DESC);

COMMENT ON TABLE ai_chat_attachments IS
    '会话附件 metadata（storage/ai_chat/ 独立空间，不写业务证据附件表，Req 7.8）。'
    '聊天请求只提交 attachment ID，服务端不下发物理路径';
COMMENT ON COLUMN ai_chat_attachments.ocr_text_protected IS
    'OCR 文本（design 的 ocr_text_encrypted_or_protected）。平台无字段级加密时'
    '靠 DB/文件权限 + 最短保留期保护，读取路径须走脱敏与定界';

-- ---------------------------------------------------------------------------
-- ⑨ ai_chat_action_receipts（note save / adopt 的通用幂等收据，Req 8.2/8.3）
--
-- 唯一约束 (action_type, actor_id, session_id, idempotency_key)：并发重复请求
-- 只有一个能插入成功，其余读回同一收据 ⇒ 不创建重复文件夹/文档（Property 21）。
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ai_chat_action_receipts (
    id                  UUID         PRIMARY KEY,
    action_type         VARCHAR(32)  NOT NULL,
    actor_id            UUID         NOT NULL REFERENCES users(id),
    session_id          UUID         NOT NULL REFERENCES ai_chat_session(id) ON DELETE CASCADE,
    idempotency_key     VARCHAR(128) NOT NULL,
    source_message_hash VARCHAR(64),
    result_resource_id  UUID,
    status              VARCHAR(16)  NOT NULL DEFAULT 'pending',
    error_code          VARCHAR(64),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_ai_chat_action_receipts_action CHECK (action_type IN (
        'note-create', 'adopt'
    )),
    CONSTRAINT ck_ai_chat_action_receipts_status CHECK (status IN (
        'pending', 'succeeded', 'failed'
    ))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_chat_action_receipts_idempotency
    ON ai_chat_action_receipts (action_type, actor_id, session_id, idempotency_key);

CREATE INDEX IF NOT EXISTS ix_ai_chat_action_receipts_resource
    ON ai_chat_action_receipts (result_resource_id)
    WHERE result_resource_id IS NOT NULL;

COMMENT ON TABLE ai_chat_action_receipts IS
    '项目笔记转存 / AI 内容采纳的幂等收据。禁止"先查后建"：并发去重由'
    'uq_ai_chat_action_receipts_idempotency 唯一约束保证（Req 8.3，Property 21）';
