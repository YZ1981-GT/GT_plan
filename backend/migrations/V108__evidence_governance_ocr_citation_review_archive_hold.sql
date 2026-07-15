-- V108: Evidence Governance — OCR Job/Transition/Result/Confirmation/Writeback(+staging),
--       CitationSnapshot, AiContentLog 扩展, ReviewEvidenceSnapshot/ReviewClose,
--       EvidenceAuditCommandRoot/Transition, outbox/inbox,
--       ArchiveManifest/Entry/Edge, LegalHold/Scope, migration checkpoint, quality snapshot
-- Spec: attachment-ocr-ai-evidence-governance-hardening / Task 2.4 (Wave 1)
-- Requirements: R5（持久 OCR 状态机/重试）, R6（Result/确认/原子写回）, R7（Citation 可定位）,
--               R8（AI 全入口登记/门禁）, R10（复核证据闭环）, R11（Archive Manifest 完整性）,
--               R12（审计 command-root 唯一/transition 多条/outbox）, R13（Legal Hold/保留）,
--               R16（质量快照可复算）
-- Design: §4.5（OCR 模型）, §4.6（Citation/AI/Review/Manifest/Hold 与审计）, §7.1（command-root 唯一）
-- Properties: P9(状态机封闭), P11(结果不可变), P12(未确认不可写回), P13/P14(写回原子/幂等),
--             P15/P16(citation), P17/P18/P19(AI 门禁), P21/P22(复核), P23/P24(manifest),
--             P25(command-root 唯一), P26/P27(hold/retention), P30(质量快照可复算)
--
-- 约定（migration_allocation.lint_migration_sql 守卫，design §8.1）：
--   * additive-only：不含 DROP TABLE / DROP COLUMN / TRUNCATE（不删除 legacy 列/结构）。
--   * 可重复检测（幂等）：CREATE TABLE / CREATE (UNIQUE) INDEX 用 IF NOT EXISTS；
--     ADD COLUMN 用 IF NOT EXISTS；ADD CONSTRAINT / CONSTRAINT TRIGGER 用 pg_constraint /
--     pg_trigger 存在性 DO 守卫；函数 CREATE OR REPLACE；immutable 触发器 CREATE OR REPLACE TRIGGER。
--   * 所有内联 FK 默认 ON DELETE RESTRICT（回滚不级联删除治理对象）。
--
-- 单一真源（契约）：app.services.evidence_governance.contracts
--   （OcrState / OCR_TRANSITIONS 封闭集 / OCR_FIELD_DECISIONS / OCR_WRITEBACK_ELIGIBLE_DECISIONS /
--    ACTOR_COLUMNS / HUMAN_ONLY_DECISION_FKS），canonical hash 见 frozen_contracts.content_hash_of。
-- 人工确认/写回批准/复核关闭/hold 解除使用独立 confirmed_by_user_id / written_by_user_id /
--   closed_by_user_id / released_by_user_id（NOT NULL REFERENCES users），不接受 Service Identity。
-- 前置：V106（attachments 复合 scope key + attachment_versions），V107（evidence_refs），
--       V017（ai_content_log）。

-- ============================================================
-- 1. EvidenceAuditCommandRoot / Transition（design §4.6 / §7.1；R12 / P25）
--    每个敏感命令 (command_type, idempotency_key, scope) 恰一个 root（UNIQUE）；
--    状态机步骤/attempt/告警/业务状态变化写零到多条 transition（多行 FK 到 root）。
-- ============================================================

CREATE TABLE IF NOT EXISTS evidence_audit_command_roots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    command_type VARCHAR(80) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    result VARCHAR(30),                                    -- accepted | rejected | replayed | ...（脱敏结果码）
    reason_code VARCHAR(80),
    trace_id VARCHAR(80),
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_audit_root_actor_xor CHECK (
        (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR
        (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
    )
);

-- (command_type, idempotency_key, scope) 唯一：命令执行/拒绝/重放都不多建 root（P25）
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_audit_command_root') THEN
        ALTER TABLE evidence_audit_command_roots ADD CONSTRAINT uq_audit_command_root
            UNIQUE (command_type, idempotency_key, project_id, audit_year);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_audit_root_scope ON evidence_audit_command_roots(project_id, audit_year);
CREATE INDEX IF NOT EXISTS idx_audit_root_type ON evidence_audit_command_roots(command_type);

COMMENT ON TABLE evidence_audit_command_roots IS 'design §7.1 command-root：每敏感命令+幂等键恰一个 root（uq_audit_command_root）；重放不重复建 root（P25）';

CREATE TABLE IF NOT EXISTS evidence_audit_transitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    command_root_id UUID NOT NULL REFERENCES evidence_audit_command_roots(id) ON DELETE RESTRICT,
    transition_type VARCHAR(80) NOT NULL,
    from_state VARCHAR(40),
    to_state VARCHAR(40),
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    metadata_redacted JSONB,                               -- 脱敏元数据（无凭据/原文/绝对路径）
    at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_audit_transition_actor_xor CHECK (
        (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR
        (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_audit_transition_root ON evidence_audit_transitions(command_root_id, at);

COMMENT ON TABLE evidence_audit_transitions IS 'design §7.1 多行 transition FK 到 command-root；零到多条，不把每次状态迁移误计为重复命令（P25）';

-- 补齐 V106 UploadAttempt.command_root_id 的 FK（V106 有意延后到本任务；additive DO 守卫）。
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_upload_attempt_command_root') THEN
        ALTER TABLE evidence_upload_attempts ADD CONSTRAINT fk_upload_attempt_command_root
            FOREIGN KEY (command_root_id) REFERENCES evidence_audit_command_roots(id) ON DELETE RESTRICT;
    END IF;
END $$;

-- ============================================================
-- 2. OCRJob（design §4.5；R5 / P9）
--    绑定确定 AttachmentVersion + hash + canonical parse config + 幂等键 + 状态 + 进度 + attempt + lease + actor。
--    state CHECK 封闭集与 contracts.OcrState 一致（queued/running/awaiting_confirmation/confirmed/written_back/failed）。
-- ============================================================

CREATE TABLE IF NOT EXISTS ocr_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    attachment_id UUID NOT NULL,
    attachment_version_id UUID NOT NULL REFERENCES attachment_versions(id) ON DELETE RESTRICT,
    content_hash VARCHAR(64) NOT NULL,                     -- 绑定确定版本字节（P5）
    parse_config JSONB,                                    -- canonical parse config
    parse_config_version VARCHAR(64),
    idempotency_key VARCHAR(200) NOT NULL,                 -- 版本+hash+config 幂等键（R5.4）
    state VARCHAR(30) NOT NULL DEFAULT 'queued',
    progress INTEGER NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    lease_owner VARCHAR(120),                              -- worker 租约持有者（重启恢复）
    lease_expires_at TIMESTAMPTZ,
    error_code VARCHAR(80),
    error_message TEXT,
    command_root_id UUID REFERENCES evidence_audit_command_roots(id) ON DELETE RESTRICT,
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- 封闭状态集（迁移 = contracts.OCR_STATES 单一真源；非法状态被拒，P9）
    CONSTRAINT chk_ocr_job_state CHECK (
        state IN ('queued','running','awaiting_confirmation','confirmed','written_back','failed')
    ),
    CONSTRAINT chk_ocr_job_progress CHECK (progress BETWEEN 0 AND 100),
    CONSTRAINT chk_ocr_job_actor_xor CHECK (
        (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR
        (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
    )
);

-- 幂等复用（R5.4）：同 scope 同幂等键唯一（活动或已完成任务复用，不重复消费）
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_ocr_job_idempotency') THEN
        ALTER TABLE ocr_jobs ADD CONSTRAINT uq_ocr_job_idempotency
            UNIQUE (project_id, audit_year, idempotency_key);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_ocr_job_scope ON ocr_jobs(project_id, audit_year);
CREATE INDEX IF NOT EXISTS idx_ocr_job_version ON ocr_jobs(attachment_version_id);
CREATE INDEX IF NOT EXISTS idx_ocr_job_state ON ocr_jobs(project_id, state);
CREATE INDEX IF NOT EXISTS idx_ocr_job_lease ON ocr_jobs(state, lease_expires_at);

COMMENT ON TABLE ocr_jobs IS 'design §4.5 OCRJob：绑定确定版本/hash/config/幂等键/lease/actor；state 封闭集 CHECK（contracts.OCR_STATES / OCR_TRANSITIONS）';
COMMENT ON COLUMN ocr_jobs.state IS 'queued|running|awaiting_confirmation|confirmed|written_back|failed；合法迁移见 contracts.OCR_TRANSITIONS（服务层 CAS 强制，P9）';

CREATE TABLE IF NOT EXISTS ocr_job_transitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ocr_job_id UUID NOT NULL REFERENCES ocr_jobs(id) ON DELETE RESTRICT,
    command_root_id UUID REFERENCES evidence_audit_command_roots(id) ON DELETE RESTRICT,
    from_state VARCHAR(30),
    to_state VARCHAR(30) NOT NULL,
    progress INTEGER,
    error_code VARCHAR(80),
    error_message TEXT,
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_ocr_transition_to_state CHECK (
        to_state IN ('queued','running','awaiting_confirmation','confirmed','written_back','failed')
    ),
    CONSTRAINT chk_ocr_transition_actor_xor CHECK (
        (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR
        (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_ocr_transition_job ON ocr_job_transitions(ocr_job_id, at);

COMMENT ON TABLE ocr_job_transitions IS 'design §4.5 每次 OCR 状态迁移一条，关联 command-root；状态机迁移可有零到多条 transition 审计事件';

-- ============================================================
-- 3. OCRResult（design §4.5；R6.1 / P11）—— 不可变原始识别结果。
--    raw text / pages / fields / confidence / page / region / engine / model / config version / result hash。
--    immutable 触发器禁止任何 UPDATE（确认/修正/写回都不改原值）。
-- ============================================================

CREATE TABLE IF NOT EXISTS ocr_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ocr_job_id UUID NOT NULL REFERENCES ocr_jobs(id) ON DELETE RESTRICT,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    attachment_version_id UUID NOT NULL REFERENCES attachment_versions(id) ON DELETE RESTRICT,
    source_content_hash VARCHAR(64) NOT NULL,              -- 来源版本字节 hash（P11 绑定）
    raw_text TEXT,
    pages JSONB,                                           -- 每页文本/结构
    fields JSONB,                                          -- 结构化字段（原始值/置信度/页/区域）
    confidence NUMERIC(5, 4),
    page INTEGER,
    region JSONB,                                          -- 页内区域坐标
    engine VARCHAR(80),
    model_version VARCHAR(120),
    config_version VARCHAR(64),
    result_hash VARCHAR(64) NOT NULL,                      -- canonical result 内容 hash
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_ocr_result_actor_xor CHECK (
        (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR
        (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_ocr_result_job ON ocr_results(ocr_job_id);
CREATE INDEX IF NOT EXISTS idx_ocr_result_scope ON ocr_results(project_id, audit_year);
CREATE INDEX IF NOT EXISTS idx_ocr_result_version ON ocr_results(attachment_version_id);

COMMENT ON TABLE ocr_results IS 'design §4.5 不可变 OCRResult：原始 text/pages/fields/confidence/page/region/engine/model/config version/result hash；immutable 触发器（P11）';

-- ============================================================
-- 4. OCRConfirmation（design §4.5；R6.2 / P12）—— append-only 人工确认修订。
--    每 required 字段最终有 current accepted|corrected|rejected 决定；rejected 永不进 mapping。
--    confirmed_by_user_id NOT NULL（人工专属，Service Identity 不得确认）。
--    append-only：新增修订行；immutable 触发器只允许 is_current 变更（旧修订实质列不可改）。
-- ============================================================

CREATE TABLE IF NOT EXISTS ocr_confirmations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ocr_job_id UUID NOT NULL REFERENCES ocr_jobs(id) ON DELETE RESTRICT,
    ocr_result_id UUID NOT NULL REFERENCES ocr_results(id) ON DELETE RESTRICT,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    field_key VARCHAR(200) NOT NULL,
    is_required BOOLEAN NOT NULL DEFAULT true,
    original_value TEXT,                                   -- 原识别值（快照）
    confirmed_value TEXT,                                  -- 确认/修正值（accepted/corrected 必须有值）
    decision VARCHAR(20) NOT NULL,                         -- accepted | corrected | rejected（contracts.OCR_FIELD_DECISIONS）
    is_current BOOLEAN NOT NULL DEFAULT true,              -- 当前有效修订（append-only：旧修订置 false）
    revision_no INTEGER NOT NULL DEFAULT 1,
    confirmed_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,  -- 人工专属（NOT NULL）
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_ocr_confirmation_decision CHECK (decision IN ('accepted','corrected','rejected')),
    -- accepted/corrected 必须有确认值；rejected 允许无值（“已决定但不采纳”）
    CONSTRAINT chk_ocr_confirmation_value CHECK (
        decision = 'rejected' OR confirmed_value IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_ocr_confirmation_job ON ocr_confirmations(ocr_job_id, field_key);
CREATE INDEX IF NOT EXISTS idx_ocr_confirmation_result ON ocr_confirmations(ocr_result_id);
-- 每字段仅一条 current 决定（append-only 语义：新修订前先把旧修订置 is_current=false）
CREATE UNIQUE INDEX IF NOT EXISTS uq_ocr_confirmation_current
    ON ocr_confirmations (ocr_job_id, field_key)
    WHERE is_current = true;

COMMENT ON TABLE ocr_confirmations IS 'design §4.5 append-only 人工确认修订；rejected 满足 required decided 但永不进 mapping；confirmed_by_user_id NOT NULL 人工专属';
COMMENT ON COLUMN ocr_confirmations.decision IS 'accepted|corrected|rejected；writeback-eligible = accepted/corrected（contracts.OCR_WRITEBACK_ELIGIBLE_DECISIONS）';

-- ============================================================
-- 5. OCRWriteback + ocr_writeback_staging（design §4.5；R6.4 / P13 / P14）
--    OCRWriteback：目标版本、mapping、confirmation IDs、幂等键、payload hash、结果、written_by_user_id NOT NULL。
--    write_mode: transactional-local | staged-external。
--    staged-external 先写 ocr_writeback_staging，目标模块以幂等键消费后回执推进 written_back。
-- ============================================================

CREATE TABLE IF NOT EXISTS ocr_writebacks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ocr_job_id UUID NOT NULL REFERENCES ocr_jobs(id) ON DELETE RESTRICT,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    target_type VARCHAR(50) NOT NULL,
    target_id VARCHAR(200) NOT NULL,
    target_version VARCHAR(64),
    write_mode VARCHAR(30) NOT NULL,                       -- transactional-local | staged-external
    field_mapping JSONB NOT NULL,                          -- 仅 accepted/corrected 字段（rejected/undecided 不得出现，P12）
    confirmation_ids JSONB NOT NULL,                       -- 参与写回的 confirmation IDs
    idempotency_key VARCHAR(200) NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    result VARCHAR(20) NOT NULL DEFAULT 'pending',         -- pending | success | failed
    command_root_id UUID REFERENCES evidence_audit_command_roots(id) ON DELETE RESTRICT,
    written_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,  -- 人工专属（NOT NULL）
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_ocr_writeback_mode CHECK (write_mode IN ('transactional-local','staged-external')),
    CONSTRAINT chk_ocr_writeback_result CHECK (result IN ('pending','success','failed'))
);

-- 幂等：同 scope 同幂等键只一次业务效果（P14）
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_ocr_writeback_idempotency') THEN
        ALTER TABLE ocr_writebacks ADD CONSTRAINT uq_ocr_writeback_idempotency
            UNIQUE (project_id, audit_year, idempotency_key);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_ocr_writeback_job ON ocr_writebacks(ocr_job_id);
CREATE INDEX IF NOT EXISTS idx_ocr_writeback_target ON ocr_writebacks(project_id, target_type, target_id);

COMMENT ON TABLE ocr_writebacks IS 'design §4.5 OCRWriteback：目标版本/mapping/confirmation IDs/幂等键/payload hash/结果/written_by_user_id NOT NULL；幂等 uq_ocr_writeback_idempotency（P14）';

CREATE TABLE IF NOT EXISTS ocr_writeback_staging (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ocr_writeback_id UUID NOT NULL REFERENCES ocr_writebacks(id) ON DELETE RESTRICT,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    target_type VARCHAR(50) NOT NULL,
    target_id VARCHAR(200) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    payload JSONB NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    consume_state VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending | consumed | failed
    consumed_at TIMESTAMPTZ,
    receipt JSONB,                                          -- 目标模块回执
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_ocr_wb_staging_state CHECK (consume_state IN ('pending','consumed','failed'))
);

-- staged-external 幂等消费键（目标模块按幂等键消费，回执前不重复业务效果）
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_ocr_wb_staging_idempotency') THEN
        ALTER TABLE ocr_writeback_staging ADD CONSTRAINT uq_ocr_wb_staging_idempotency
            UNIQUE (target_type, target_id, idempotency_key);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_ocr_wb_staging_writeback ON ocr_writeback_staging(ocr_writeback_id);
CREATE INDEX IF NOT EXISTS idx_ocr_wb_staging_state ON ocr_writeback_staging(consume_state);

COMMENT ON TABLE ocr_writeback_staging IS 'design §4.5 staged-external 写回暂存：外部/跨库目标先写 staging，目标模块以幂等键消费成功后回执推进 written_back（P13）';

-- ============================================================
-- 6. CitationSnapshot（design §4.6；R7 / P15 / P16）—— 不可变。
--    绑定 AiContentLog + EvidenceRef + 版本/hash + page + region + excerpt hash + index/locator version。
--    immutable 触发器禁止 UPDATE；打开时重新鉴权由服务层负责。
-- ============================================================

CREATE TABLE IF NOT EXISTS citation_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ai_content_log_id UUID NOT NULL REFERENCES ai_content_log(id) ON DELETE RESTRICT,
    evidence_ref_id UUID NOT NULL REFERENCES evidence_refs(id) ON DELETE RESTRICT,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    target_version VARCHAR(64),
    target_hash VARCHAR(64),
    page INTEGER,
    region JSONB,                                          -- 页内区域（非空 = P15 区域要求）
    excerpt_hash VARCHAR(64),
    index_version VARCHAR(64),
    locator_version VARCHAR(64),
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_citation_actor_xor CHECK (
        (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR
        (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_citation_ai_log ON citation_snapshots(ai_content_log_id);
CREATE INDEX IF NOT EXISTS idx_citation_evidence_ref ON citation_snapshots(evidence_ref_id);
CREATE INDEX IF NOT EXISTS idx_citation_scope ON citation_snapshots(project_id, audit_year);

COMMENT ON TABLE citation_snapshots IS 'design §4.6 不可变 CitationSnapshot：绑定 AiContentLog/EvidenceRef/版本/hash/page/region/excerpt hash/index/locator version；immutable 触发器（P15/P16）';

-- ============================================================
-- 7. AiContentLog 扩展（design §4.6；R8 / P17 / P18 / P19）—— additive 列（不复制现有生命周期）。
--    现有列已含 prompt_hash / model；此处新增 service status、output hash、EvidenceRef/CitationSnapshot、stale。
-- ============================================================

ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS service_status VARCHAR(20);         -- ok|degraded|stub|timeout|unavailable
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS output_hash VARCHAR(64);
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS evidence_ref_id UUID REFERENCES evidence_refs(id) ON DELETE RESTRICT;
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS citation_snapshot_id UUID REFERENCES citation_snapshots(id) ON DELETE RESTRICT;
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS is_stale BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS stale_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_ai_content_log_evidence_ref ON ai_content_log(evidence_ref_id);
CREATE INDEX IF NOT EXISTS idx_ai_content_log_stale ON ai_content_log(project_id, is_stale);

COMMENT ON COLUMN ai_content_log.service_status IS 'AI 服务状态：ok|degraded|stub|timeout|unavailable（降级不进正式终态，P29/R8.4）';
COMMENT ON COLUMN ai_content_log.is_stale IS 'confirmed 内容或依赖失效后置 true → 回 draft/stale，原确认不再授权输出（P19）';

-- ============================================================
-- 8. ReviewEvidenceSnapshot + ReviewClose（design §4.6；R10 / P21 / P22）
--    冻结提出/关闭时的 ref/version/hash/locator；ReviewClose 使用 closed_by_user_id NOT NULL。
-- ============================================================

CREATE TABLE IF NOT EXISTS review_evidence_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id UUID NOT NULL,                               -- 复核意见 ID（phase15 review comment / thread；异构不加 FK）
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    evidence_ref_id UUID NOT NULL REFERENCES evidence_refs(id) ON DELETE RESTRICT,
    target_version VARCHAR(64),
    target_hash VARCHAR(64),
    locator JSONB,                                         -- 冻结定位（sheet/cell/page/region）
    snapshot_phase VARCHAR(20) NOT NULL DEFAULT 'raised',  -- raised | closed
    is_stale BOOLEAN NOT NULL DEFAULT false,
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_review_snapshot_phase CHECK (snapshot_phase IN ('raised','closed')),
    CONSTRAINT chk_review_snapshot_actor_xor CHECK (
        (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR
        (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_review_snapshot_review ON review_evidence_snapshots(review_id, snapshot_phase);
CREATE INDEX IF NOT EXISTS idx_review_snapshot_scope ON review_evidence_snapshots(project_id, audit_year);
CREATE INDEX IF NOT EXISTS idx_review_snapshot_evidence_ref ON review_evidence_snapshots(evidence_ref_id);

COMMENT ON TABLE review_evidence_snapshots IS 'design §4.6 ReviewEvidenceSnapshot：冻结提出/关闭时的 ref/version/hash/locator；依据失效 → 意见待重新复核（P22）';

CREATE TABLE IF NOT EXISTS review_closes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id UUID NOT NULL,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    close_note TEXT NOT NULL,                              -- 充分关闭说明（R10.2）
    closed_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,  -- 独立人工关闭 FK（NOT NULL）
    command_root_id UUID REFERENCES evidence_audit_command_roots(id) ON DELETE RESTRICT,
    reopened BOOLEAN NOT NULL DEFAULT false,               -- 依据失效自动重开标记（P22）
    reopened_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_review_close_review ON review_closes(review_id);
CREATE INDEX IF NOT EXISTS idx_review_close_scope ON review_closes(project_id, audit_year);

COMMENT ON TABLE review_closes IS 'design §4.6 ReviewClose：closed_by_user_id NOT NULL（人工专属，Service Identity 不得关闭复核）；证据失效自动重开（P22）';

-- ============================================================
-- 9. ArchiveManifest / Entry / Edge（design §4.6 / §5.5；R11 / P23 / P24）
--    冻结 watermark、策略所需图、已有依赖图、版本/hash/state/actor；sealed 后不可变，后续归档递增版本。
-- ============================================================

CREATE TABLE IF NOT EXISTS archive_manifests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    version_no INTEGER NOT NULL,                           -- 每次归档递增（P24）
    watermark VARCHAR(64) NOT NULL,                        -- 两阶段 watermark（UnifiedGraph + policy 证据）
    policy_version VARCHAR(64),
    retention_policy_version VARCHAR(64),                  -- R13.1 保留策略版本
    package_hash VARCHAR(64),                              -- 离线可复算包 hash（sealed 后固化）
    state VARCHAR(20) NOT NULL DEFAULT 'building',         -- building | sealed
    blocking_difference_report JSONB,                      -- 仅验证失败阻断归档时生成（R11.2）
    sealed_at TIMESTAMPTZ,
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_archive_manifest_state CHECK (state IN ('building','sealed')),
    CONSTRAINT chk_archive_manifest_actor_xor CHECK (
        (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR
        (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
    )
);

-- 每 scope 版本号唯一（重复归档创建新版本，不覆盖历史，P24）
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_archive_manifest_version') THEN
        ALTER TABLE archive_manifests ADD CONSTRAINT uq_archive_manifest_version
            UNIQUE (project_id, audit_year, version_no);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_archive_manifest_scope ON archive_manifests(project_id, audit_year);
CREATE INDEX IF NOT EXISTS idx_archive_manifest_state ON archive_manifests(state);

COMMENT ON TABLE archive_manifests IS 'design §4.6/§5.5 ArchiveManifest：watermark/policy/retention/package hash；sealed 后不可变（immutable 触发器），每次归档递增版本（P24）';

CREATE TABLE IF NOT EXISTS archive_manifest_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    archive_manifest_id UUID NOT NULL REFERENCES archive_manifests(id) ON DELETE RESTRICT,
    node_type VARCHAR(50) NOT NULL,                        -- attachment_version|evidence_ref|ocr_job|ocr_result|citation|ai_content|review|deliverable ...
    node_id VARCHAR(200) NOT NULL,
    node_version VARCHAR(64),
    node_hash VARCHAR(64),
    node_state VARCHAR(30),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_archive_entry_manifest ON archive_manifest_entries(archive_manifest_id);
CREATE INDEX IF NOT EXISTS idx_archive_entry_node ON archive_manifest_entries(archive_manifest_id, node_type, node_id);

COMMENT ON TABLE archive_manifest_entries IS 'design §4.6 ArchiveManifestEntry：manifest 覆盖的证据节点（版本/hash/state）；append-only（immutable 触发器）';

CREATE TABLE IF NOT EXISTS archive_manifest_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    archive_manifest_id UUID NOT NULL REFERENCES archive_manifests(id) ON DELETE RESTRICT,
    source_type VARCHAR(50) NOT NULL,
    source_id VARCHAR(200) NOT NULL,
    target_type VARCHAR(50) NOT NULL,
    target_id VARCHAR(200) NOT NULL,
    relation VARCHAR(50) NOT NULL,
    edge_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_archive_edge_manifest ON archive_manifest_edges(archive_manifest_id);
CREATE INDEX IF NOT EXISTS idx_archive_edge_source ON archive_manifest_edges(archive_manifest_id, source_type, source_id);

COMMENT ON TABLE archive_manifest_edges IS 'design §4.6 ArchiveManifestEdge：manifest 冻结的证据图边（canonical edge_hash）；append-only（immutable 触发器，P23）';

-- ============================================================
-- 10. LegalHold / LegalHoldScope（design §4.6 / §5.5；R13 / P26 / P27）
--     固化直接与传递范围；解除使用 released_by_user_id NOT NULL、原因和时间；范围历史不删除。
--     released_by_user_id 列可空（active hold 未解除），但 state='released' 时经 CHECK 强制非空（人工专属）。
-- ============================================================

CREATE TABLE IF NOT EXISTS legal_holds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    reason TEXT NOT NULL,
    state VARCHAR(20) NOT NULL DEFAULT 'active',           -- active | released
    graph_watermark VARCHAR(64),                           -- 激活时固化的统一图闭包 watermark
    release_reason TEXT,
    released_by_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,  -- 解除人（人工专属；released 时 CHECK 强制 NOT NULL）
    released_at TIMESTAMPTZ,
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_legal_hold_state CHECK (state IN ('active','released')),
    -- 解除必须由独立人工 FK 记录原因和时间（released_by_user_id NOT NULL when released）
    CONSTRAINT chk_legal_hold_release CHECK (
        (state = 'active'   AND released_by_user_id IS NULL AND released_at IS NULL)
        OR
        (state = 'released' AND released_by_user_id IS NOT NULL AND released_at IS NOT NULL AND release_reason IS NOT NULL)
    ),
    CONSTRAINT chk_legal_hold_actor_xor CHECK (
        (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR
        (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_legal_hold_scope ON legal_holds(project_id, audit_year);
CREATE INDEX IF NOT EXISTS idx_legal_hold_state ON legal_holds(project_id, state);

COMMENT ON TABLE legal_holds IS 'design §4.6 LegalHold：released_by_user_id 人工专属（released 时 CHECK NOT NULL）；hold 内删除/清理/覆盖零效果无绕过（P26），解除+retention 届满才可 purge（P27）';

CREATE TABLE IF NOT EXISTS legal_hold_scopes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    legal_hold_id UUID NOT NULL REFERENCES legal_holds(id) ON DELETE RESTRICT,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    node_type VARCHAR(50) NOT NULL,
    node_id VARCHAR(200) NOT NULL,
    scope_kind VARCHAR(20) NOT NULL DEFAULT 'direct',      -- direct | transitive
    is_active BOOLEAN NOT NULL DEFAULT true,               -- 范围历史不删除（单调；停用置 false 不物理删）
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_legal_hold_scope_kind CHECK (scope_kind IN ('direct','transitive'))
);

CREATE INDEX IF NOT EXISTS idx_legal_hold_scope_hold ON legal_hold_scopes(legal_hold_id);
CREATE INDEX IF NOT EXISTS idx_legal_hold_scope_node ON legal_hold_scopes(project_id, node_type, node_id, is_active);

COMMENT ON TABLE legal_hold_scopes IS 'design §4.6 LegalHoldScope：固化 direct/transitive 范围闭包；范围历史不删除（is_active 单调）';

-- ============================================================
-- 11. outbox / inbox（design §4.6 / §5.4 / §7.1；R12 / R9）
--     统一 actor/scope 与保留约束；按 event ID 幂等，失败有界退避 + dead-letter。
-- ============================================================

CREATE TABLE IF NOT EXISTS evidence_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    event_id VARCHAR(120) NOT NULL,                        -- 幂等事件 ID
    event_type VARCHAR(80) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',         -- pending | processing | done | dead_letter
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,
    command_root_id UUID REFERENCES evidence_audit_command_roots(id) ON DELETE RESTRICT,
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_evidence_outbox_status CHECK (status IN ('pending','processing','done','dead_letter')),
    CONSTRAINT chk_evidence_outbox_actor_xor CHECK (
        (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR
        (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
    )
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_evidence_outbox_event') THEN
        ALTER TABLE evidence_outbox ADD CONSTRAINT uq_evidence_outbox_event UNIQUE (event_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_evidence_outbox_status ON evidence_outbox(status, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_evidence_outbox_scope ON evidence_outbox(project_id, audit_year);

COMMENT ON TABLE evidence_outbox IS 'design §5.4/§7.1 事务性 outbox：业务变化+command-root+outbox 同事务；按 event_id 幂等，有界退避 + dead_letter';

CREATE TABLE IF NOT EXISTS evidence_inbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    event_id VARCHAR(120) NOT NULL,                        -- 幂等消费键
    event_type VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'received',        -- received | processed | dead_letter
    processed_at TIMESTAMPTZ,
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_evidence_inbox_status CHECK (status IN ('received','processed','dead_letter')),
    CONSTRAINT chk_evidence_inbox_actor_xor CHECK (
        (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR
        (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
    )
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_evidence_inbox_event') THEN
        ALTER TABLE evidence_inbox ADD CONSTRAINT uq_evidence_inbox_event UNIQUE (event_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_evidence_inbox_status ON evidence_inbox(status);
CREATE INDEX IF NOT EXISTS idx_evidence_inbox_scope ON evidence_inbox(project_id, audit_year);

COMMENT ON TABLE evidence_inbox IS 'design §5.4 inbox：按 event_id 幂等消费，避免重复副作用';

-- ============================================================
-- 12. migration checkpoint（design §8.2 M1；R14 / P28）
--     按 project/year/id 小批 checkpoint；批次键含 migration version/project/partition/input hash。
--     重跑不增加根/版本/引用/Job/Writeback，不改历史字节。
-- ============================================================

CREATE TABLE IF NOT EXISTS evidence_migration_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    migration_version VARCHAR(20) NOT NULL,
    batch_key VARCHAR(200) NOT NULL,                       -- migration version/project/partition/input hash
    project_id UUID REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    partition_key VARCHAR(120),
    input_hash VARCHAR(64),
    cursor_position VARCHAR(200),                          -- 恢复游标（R14.3 从检查点恢复）
    status VARCHAR(20) NOT NULL DEFAULT 'pending',         -- pending | running | done | failed
    processed_count INTEGER NOT NULL DEFAULT 0,
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_migration_checkpoint_status CHECK (status IN ('pending','running','done','failed')),
    CONSTRAINT chk_migration_checkpoint_actor_xor CHECK (
        (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR
        (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
    )
);

-- 批次键幂等（P28：相同输入重跑不重复处理）
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_migration_checkpoint_batch') THEN
        ALTER TABLE evidence_migration_checkpoints ADD CONSTRAINT uq_migration_checkpoint_batch
            UNIQUE (migration_version, batch_key);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_migration_checkpoint_status ON evidence_migration_checkpoints(status);
CREATE INDEX IF NOT EXISTS idx_migration_checkpoint_scope ON evidence_migration_checkpoints(project_id, audit_year);

COMMENT ON TABLE evidence_migration_checkpoints IS 'design §8.2 M1 迁移 checkpoint：batch_key 幂等（uq_migration_checkpoint_batch）；重跑从检查点恢复不重复对象（P28）';

-- ============================================================
-- 13. quality snapshot（design §9/§Testing §10.2；R16 / P30）
--     固定不可变快照：重复计算得到相同指标/账龄桶/问题清单，不改业务结论。immutable 触发器。
-- ============================================================

CREATE TABLE IF NOT EXISTS evidence_quality_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    snapshot_key VARCHAR(200) NOT NULL,                    -- 固定快照标识（P30 可复算基准）
    metrics JSONB NOT NULL,                                -- 元数据完整率/created_by 完整率/RAG 可定位率/OCR 修正率/门禁绕过数/归档失败数
    aging_buckets JSONB,                                   -- stale 账龄桶
    issue_list JSONB,                                      -- 治理问题清单
    input_hash VARCHAR(64),                                -- 固定输入快照 hash（可复算校验）
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_quality_snapshot_actor_xor CHECK (
        (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR
        (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
    )
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_quality_snapshot_key') THEN
        ALTER TABLE evidence_quality_snapshots ADD CONSTRAINT uq_quality_snapshot_key
            UNIQUE (snapshot_key);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_quality_snapshot_scope ON evidence_quality_snapshots(project_id, audit_year);

COMMENT ON TABLE evidence_quality_snapshots IS 'design §9 质量快照：固定不可变快照，重复计算相同指标/账龄桶/问题清单（P30）；immutable 触发器';

-- ============================================================
-- 14. Immutable / append-only 触发器（design §4.5/§4.6；P11/P15/P23/P24/P25/P30）
-- ============================================================

-- 通用：完全不可变 / append-only（禁止任何 UPDATE）。
CREATE OR REPLACE FUNCTION evgov_forbid_update() RETURNS trigger AS $fn$
BEGIN
    RAISE EXCEPTION '% 为不可变/append-only 表，禁止 UPDATE (id=%)', TG_TABLE_NAME, OLD.id
        USING ERRCODE = 'check_violation';
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_ocr_result_immutable
    BEFORE UPDATE ON ocr_results
    FOR EACH ROW EXECUTE FUNCTION evgov_forbid_update();

CREATE OR REPLACE TRIGGER trg_ocr_job_transition_append_only
    BEFORE UPDATE ON ocr_job_transitions
    FOR EACH ROW EXECUTE FUNCTION evgov_forbid_update();

CREATE OR REPLACE TRIGGER trg_citation_snapshot_immutable
    BEFORE UPDATE ON citation_snapshots
    FOR EACH ROW EXECUTE FUNCTION evgov_forbid_update();

CREATE OR REPLACE TRIGGER trg_audit_transition_append_only
    BEFORE UPDATE ON evidence_audit_transitions
    FOR EACH ROW EXECUTE FUNCTION evgov_forbid_update();

CREATE OR REPLACE TRIGGER trg_archive_entry_append_only
    BEFORE UPDATE ON archive_manifest_entries
    FOR EACH ROW EXECUTE FUNCTION evgov_forbid_update();

CREATE OR REPLACE TRIGGER trg_archive_edge_append_only
    BEFORE UPDATE ON archive_manifest_edges
    FOR EACH ROW EXECUTE FUNCTION evgov_forbid_update();

CREATE OR REPLACE TRIGGER trg_quality_snapshot_immutable
    BEFORE UPDATE ON evidence_quality_snapshots
    FOR EACH ROW EXECUTE FUNCTION evgov_forbid_update();

-- OCRConfirmation append-only：只允许 is_current 变更（旧修订被新修订取代时置 false）；
-- 其余实质列（决定/原值/确认值/字段/确认人/时间）不可改（P11 语义延伸）。
CREATE OR REPLACE FUNCTION evgov_ocr_confirmation_append_only() RETURNS trigger AS $fn$
BEGIN
    IF NEW.ocr_job_id           IS DISTINCT FROM OLD.ocr_job_id
       OR NEW.ocr_result_id     IS DISTINCT FROM OLD.ocr_result_id
       OR NEW.field_key         IS DISTINCT FROM OLD.field_key
       OR NEW.original_value    IS DISTINCT FROM OLD.original_value
       OR NEW.confirmed_value   IS DISTINCT FROM OLD.confirmed_value
       OR NEW.decision          IS DISTINCT FROM OLD.decision
       OR NEW.confirmed_by_user_id IS DISTINCT FROM OLD.confirmed_by_user_id
       OR NEW.confirmed_at      IS DISTINCT FROM OLD.confirmed_at
       OR NEW.revision_no       IS DISTINCT FROM OLD.revision_no THEN
        RAISE EXCEPTION 'ocr_confirmations 为 append-only；除 is_current 外的实质列禁止 UPDATE (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_ocr_confirmation_append_only
    BEFORE UPDATE ON ocr_confirmations
    FOR EACH ROW EXECUTE FUNCTION evgov_ocr_confirmation_append_only();

-- ArchiveManifest：sealed 后不可变（building→sealed 允许；sealed 后禁止任何 UPDATE，P24）。
CREATE OR REPLACE FUNCTION evgov_archive_manifest_sealed_immutable() RETURNS trigger AS $fn$
BEGIN
    IF OLD.state = 'sealed' THEN
        RAISE EXCEPTION 'archive_manifests 已 sealed，不可变，禁止 UPDATE (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_archive_manifest_sealed_immutable
    BEFORE UPDATE ON archive_manifests
    FOR EACH ROW EXECUTE FUNCTION evgov_archive_manifest_sealed_immutable();
