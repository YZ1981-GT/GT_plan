-- V110: Repair — V105__procedure_row_tasks 因 V105 版本号冲突被跳过
--
-- 背景：schema_version 中 version=105 曾被 V105__evidence_governance_role_eqcr_enum.sql
-- 占用（后重编号为 V109），canonical V105__procedure_row_tasks.sql 从未执行，
-- 导致 procedure_row_* 表、task_events/notifications 扩展列缺失。
--
-- 本迁移幂等重放 V105 procedure-delegation 结构，并补齐 ocr_jobs.next_retry_at（ORM 已有、V108 漏列）。
-- 幂等策略同 V105：CREATE IF NOT EXISTS + information_schema/pg_indexes 守护。

-- schema_version 审计修正（仅误占 filename 时更新，不影响版本号序列）
UPDATE schema_version
SET filename = 'V105__procedure_row_tasks.sql (applied_via_V110_repair)'
WHERE version = '105'
  AND filename = 'V105__evidence_governance_role_eqcr_enum.sql';

-- V105: Procedure Row Task expand 模型（procedure-delegation-notification / Task 2）
-- 模板级 ProcedureRowDefinition + 项目级 ProcedureRowTask + 追加式 history + 一次性 preview
-- 并扩展现有 task_events（Delivery_Outbox）与 notifications（聚合通知 dedup/metadata）。
--
-- Requirements: 1.1-1.2, 2.1-2.2, 4.2, 10.1, 12.1-12.7, 13.3
-- 幂等：CREATE TABLE/INDEX IF NOT EXISTS + DO $$ information_schema.columns 守护列补齐；
--       唯一/覆盖/claim 索引用 pg_indexes 检测后创建。`IF NOT EXISTS` 不作为结构正确性证明，
--       由 tests/procedure_delegation/test_v105_schema_contract.py 用 information_schema/pg_catalog 精校。
-- expand 阶段：只增结构与兼容代码，不删旧列、不改既有读语义（Req 13.3）。

-- ============================================================
-- 1. procedure_row_definitions —— 模板级程序行定义真源（跨项目稳定身份）
-- ============================================================

CREATE TABLE IF NOT EXISTS procedure_row_definitions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    definition_key          VARCHAR(200) NOT NULL,
    template_code           VARCHAR(80)  NOT NULL,
    template_revision_hash  CHAR(64)     NOT NULL,
    sheet_key               VARCHAR(160) NOT NULL,
    source_locator          JSONB        NOT NULL DEFAULT '{}',
    program_no              VARCHAR(80),
    procedure_text          TEXT         NOT NULL,
    ref_snapshot            JSONB        NOT NULL DEFAULT '[]',
    legacy_aliases          JSONB        NOT NULL DEFAULT '[]',
    normalized_content      JSONB        NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- definition_key 全局唯一（模板身份真源）
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_procedure_row_definitions_key') THEN
        CREATE UNIQUE INDEX uq_procedure_row_definitions_key
            ON procedure_row_definitions(definition_key);
    END IF;
END $$;

-- 建议唯一约束：(template_code, template_revision_hash, sheet_key, definition_key)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_procedure_row_definitions_revision') THEN
        CREATE UNIQUE INDEX uq_procedure_row_definitions_revision
            ON procedure_row_definitions(template_code, template_revision_hash, sheet_key, definition_key);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_procedure_row_definitions_template
    ON procedure_row_definitions(template_code, sheet_key);

COMMENT ON TABLE procedure_row_definitions IS
    '模板级程序行定义真源；definition_key 跨项目稳定，template_revision_hash 为规范化内容 SHA-256（不含 mtime/路径/项目数据）';

-- ============================================================
-- 2. procedure_row_tasks —— 项目级程序行任务真源（先委派后生成底稿）
-- ============================================================

CREATE TABLE IF NOT EXISTS procedure_row_tasks (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id               UUID NOT NULL REFERENCES projects(id),
    wp_index_id              UUID NOT NULL REFERENCES wp_index(id),
    wp_id                    UUID REFERENCES working_paper(id),
    definition_key           VARCHAR(200) NOT NULL REFERENCES procedure_row_definitions(definition_key),
    sheet_key                VARCHAR(160) NOT NULL,
    -- 审计/展示快照
    wp_code                  VARCHAR(80),
    sheet_name               VARCHAR(300),
    program_no               VARCHAR(80),
    procedure_text           TEXT,
    ref_snapshot             JSONB        NOT NULL DEFAULT '[]',
    definition_revision_hash CHAR(64)     NOT NULL,
    audit_cycle_snapshot     VARCHAR(40)  NOT NULL,
    -- 适用性与独立状态机
    applicability_status     VARCHAR(20)  NOT NULL DEFAULT 'execute',
    workflow_status          VARCHAR(30)  NOT NULL DEFAULT 'unassigned',
    -- 参与者（staff_members；actor/recipient 走 user 见 history）
    assignee_staff_id        UUID REFERENCES staff_members(id),
    reviewer_staff_id        UUID REFERENCES staff_members(id),
    -- 版本与并发
    assignment_version       INTEGER      NOT NULL DEFAULT 0,
    lock_version             INTEGER      NOT NULL DEFAULT 0,
    -- SLA 时间戳
    due_at                   TIMESTAMPTZ,
    assigned_at              TIMESTAMPTZ,
    acknowledged_at          TIMESTAMPTZ,
    started_at               TIMESTAMPTZ,
    submitted_at             TIMESTAMPTZ,
    reviewed_at              TIMESTAMPTZ,
    cancelled_at             TIMESTAMPTZ,
    -- 提交材料
    execution_summary        TEXT,
    evidence_snapshot        JSONB        NOT NULL DEFAULT '[]',
    -- 迁移证据
    migration_confidence     VARCHAR(20),
    migration_detail         JSONB        NOT NULL DEFAULT '{}',
    -- 生命周期
    is_deleted               BOOLEAN      NOT NULL DEFAULT false,
    deleted_at               TIMESTAMPTZ,
    created_at               TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- active partial unique：不依赖 nullable wp_id；materialize upsert 的 ON CONFLICT 必须完全一致：
--   ON CONFLICT (project_id, wp_index_id, sheet_key, definition_key) WHERE is_deleted = false
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_procedure_row_tasks_active') THEN
        CREATE UNIQUE INDEX uq_procedure_row_tasks_active
            ON procedure_row_tasks(project_id, wp_index_id, sheet_key, definition_key)
            WHERE is_deleted = false;
    END IF;
END $$;

-- assignee covering index（跨项目 user task query；staff→user 归一后以 assignee_staff_id 起始）
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_procedure_row_tasks_assignee_cover') THEN
        CREATE INDEX ix_procedure_row_tasks_assignee_cover
            ON procedure_row_tasks(assignee_staff_id, workflow_status, due_at, project_id)
            INCLUDE (id, wp_index_id, wp_id, sheet_key, definition_key, lock_version, assignment_version)
            WHERE is_deleted = false;
    END IF;
END $$;

-- reviewer covering index
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_procedure_row_tasks_reviewer_cover') THEN
        CREATE INDEX ix_procedure_row_tasks_reviewer_cover
            ON procedure_row_tasks(reviewer_staff_id, workflow_status, due_at, project_id)
            INCLUDE (id, wp_index_id, wp_id, sheet_key, definition_key, lock_version, assignment_version)
            WHERE is_deleted = false;
    END IF;
END $$;

-- 待绑定（wp_id 为空）任务查询：底稿生成后原子绑定
CREATE INDEX IF NOT EXISTS ix_procedure_row_tasks_pending_bind
    ON procedure_row_tasks(project_id, wp_index_id)
    WHERE wp_id IS NULL AND is_deleted = false;

COMMENT ON TABLE procedure_row_tasks IS
    '项目级程序行任务真源；project_id+wp_index_id 锚点，wp_id 可后绑定；适用性/委派/执行/一级复核状态唯一真源';

-- ============================================================
-- 3. procedure_row_task_history —— 追加式动作历史（不可覆盖）
-- ============================================================

CREATE TABLE IF NOT EXISTS procedure_row_task_history (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id                  UUID NOT NULL REFERENCES procedure_row_tasks(id),
    project_id               UUID NOT NULL REFERENCES projects(id),
    event_type               VARCHAR(40) NOT NULL,
    from_status              VARCHAR(30),
    to_status                VARCHAR(30),
    old_assignee_staff_id    UUID REFERENCES staff_members(id),
    new_assignee_staff_id    UUID REFERENCES staff_members(id),
    old_reviewer_staff_id    UUID REFERENCES staff_members(id),
    new_reviewer_staff_id    UUID REFERENCES staff_members(id),
    actor_user_id            UUID REFERENCES users(id),
    reason                   TEXT,
    request_id               VARCHAR(80),
    assignment_version       INTEGER     NOT NULL DEFAULT 0,
    lock_version             INTEGER     NOT NULL DEFAULT 0,
    definition_revision_hash CHAR(64),
    audit_cycle_snapshot     VARCHAR(40),
    detail                   JSONB       NOT NULL DEFAULT '{}',
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- (task_id, request_id, event_type) 唯一：同一请求同一动作不重复写历史（幂等）
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_procedure_row_task_history_request') THEN
        CREATE UNIQUE INDEX uq_procedure_row_task_history_request
            ON procedure_row_task_history(task_id, request_id, event_type)
            WHERE request_id IS NOT NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_procedure_row_task_history_task
    ON procedure_row_task_history(task_id, created_at);
CREATE INDEX IF NOT EXISTS ix_procedure_row_task_history_project
    ON procedure_row_task_history(project_id, created_at);

COMMENT ON TABLE procedure_row_task_history IS
    '程序行任务追加式历史；记录 from/to、旧新 staff、actor user、request_id、assignment_version、definition revision、audit_cycle_snapshot';

-- ============================================================
-- 4. procedure_operation_previews —— 敏感操作一次性凭证（裁剪/委派/转派）
-- ============================================================

CREATE TABLE IF NOT EXISTS procedure_operation_previews (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id             UUID NOT NULL REFERENCES users(id),
    project_id                UUID NOT NULL REFERENCES projects(id),
    operation                 VARCHAR(40) NOT NULL,
    request_hash              CHAR(64)    NOT NULL,
    request_payload_snapshot  JSONB       NOT NULL DEFAULT '{}',
    target_versions           JSONB       NOT NULL DEFAULT '{}',
    membership_snapshot       JSONB       NOT NULL DEFAULT '{}',
    membership_snapshot_hash  CHAR(64)    NOT NULL,
    scheme_revision           VARCHAR(64),
    expires_at                TIMESTAMPTZ NOT NULL,
    consumed_at               TIMESTAMPTZ,
    consumed_request_id       VARCHAR(80),
    result                    JSONB,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- active preview 查询：按 actor/project/operation 找未消费预览
CREATE INDEX IF NOT EXISTS ix_procedure_operation_previews_active
    ON procedure_operation_previews(actor_user_id, project_id, operation)
    WHERE consumed_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_procedure_operation_previews_hash
    ON procedure_operation_previews(request_hash);

COMMENT ON TABLE procedure_operation_previews IS
    '敏感操作 server-side 一次性预览凭证；apply 时行锁校验 request_hash/actor/project/operation/TTL/target_versions/membership/scheme_revision 后置 consumed_at';

-- ============================================================
-- 5. task_events 扩展为 Delivery_Outbox（有序、可领取、可 dead-letter）
--    additive-only：既有 project_id/event_type/payload/status/retry_count/... 不变（Req 13.3）
-- ============================================================

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='task_events' AND column_name='aggregate_type') THEN
        ALTER TABLE task_events ADD COLUMN aggregate_type VARCHAR(40);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='task_events' AND column_name='aggregate_id') THEN
        ALTER TABLE task_events ADD COLUMN aggregate_id UUID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='task_events' AND column_name='aggregate_version') THEN
        ALTER TABLE task_events ADD COLUMN aggregate_version INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='task_events' AND column_name='idempotency_key') THEN
        ALTER TABLE task_events ADD COLUMN idempotency_key VARCHAR(128);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='task_events' AND column_name='delegation_batch_id') THEN
        ALTER TABLE task_events ADD COLUMN delegation_batch_id UUID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='task_events' AND column_name='available_at') THEN
        ALTER TABLE task_events ADD COLUMN available_at TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='task_events' AND column_name='lease_expires_at') THEN
        ALTER TABLE task_events ADD COLUMN lease_expires_at TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='task_events' AND column_name='claimed_by') THEN
        ALTER TABLE task_events ADD COLUMN claimed_by VARCHAR(80);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='task_events' AND column_name='processed_at') THEN
        ALTER TABLE task_events ADD COLUMN processed_at TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='task_events' AND column_name='dead_letter_at') THEN
        ALTER TABLE task_events ADD COLUMN dead_letter_at TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='task_events' AND column_name='last_error') THEN
        ALTER TABLE task_events ADD COLUMN last_error TEXT;
    END IF;
END $$;

-- idempotency_key 唯一（部分索引，历史行 NULL 不冲突）
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_task_events_idempotency_key') THEN
        CREATE UNIQUE INDEX uq_task_events_idempotency_key
            ON task_events(idempotency_key)
            WHERE idempotency_key IS NOT NULL;
    END IF;
END $$;

-- claim/order index：面向未处理、未 dead-letter，按 available_at/lease_expires_at + aggregate version 有序领取
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_task_events_claim_order') THEN
        CREATE INDEX ix_task_events_claim_order
            ON task_events(available_at, lease_expires_at, aggregate_type, aggregate_id, aggregate_version)
            WHERE processed_at IS NULL AND dead_letter_at IS NULL;
    END IF;
END $$;

COMMENT ON COLUMN task_events.idempotency_key IS 'Delivery_Outbox 幂等键；同 idempotency_key 全局唯一，重试不重复投递';
COMMENT ON COLUMN task_events.aggregate_version IS 'aggregate 内单调版本；dispatcher 按 aggregate_version 顺序处理，前序未 processed 不越序';

-- ============================================================
-- 6. notifications 扩展：event_id / recipient_user_id / dedup_key / metadata（聚合通知）
--    additive-only：既有 recipient_id/message_type/... 不变
-- ============================================================

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='notifications' AND column_name='event_id') THEN
        ALTER TABLE notifications ADD COLUMN event_id VARCHAR(128);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='notifications' AND column_name='recipient_user_id') THEN
        ALTER TABLE notifications ADD COLUMN recipient_user_id UUID REFERENCES users(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='notifications' AND column_name='dedup_key') THEN
        ALTER TABLE notifications ADD COLUMN dedup_key VARCHAR(200);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='notifications' AND column_name='metadata') THEN
        ALTER TABLE notifications ADD COLUMN metadata JSONB;
    END IF;
END $$;

-- dedup：至少等价于 (event_id, recipient_user_id) —— 重试不生成重复通知
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_notifications_event_recipient') THEN
        CREATE UNIQUE INDEX uq_notifications_event_recipient
            ON notifications(event_id, recipient_user_id)
            WHERE event_id IS NOT NULL AND recipient_user_id IS NOT NULL;
    END IF;
END $$;

COMMENT ON COLUMN notifications.dedup_key IS '通知去重键；聚合通知 metadata 携带 batch/project/task 列表，不从中文 content 解析路由';

-- ============================================================
-- 7. ocr_jobs.next_retry_at —— OCR 重试退避（ORM / OcrRetryService；V108 建表时漏列）
-- ============================================================

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'ocr_jobs' AND column_name = 'next_retry_at'
    ) THEN
        ALTER TABLE ocr_jobs ADD COLUMN next_retry_at TIMESTAMPTZ;
    END IF;
END $$;

COMMENT ON COLUMN ocr_jobs.next_retry_at IS 'OCR 任务下次可重试时间；有界指数退避（R15.4）';
