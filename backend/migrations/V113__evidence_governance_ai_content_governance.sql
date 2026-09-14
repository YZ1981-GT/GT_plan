-- V113: Evidence Governance — AiContentGovernance（AI 全入口登记/确认/失效门禁运行时表）
-- Spec: attachment-ocr-ai-evidence-governance-hardening / Task 2.4 补建（6.2 gap 修复）
-- Requirements: R8（AI 全入口登记/门禁）, R12（审计 actor XOR）, R15（证据引用绑定）
-- Design: §4.6「AiContentLog 扩展」/ AIEvidenceGate（§3.2）
-- Properties: P17（AI 状态门禁）, P18（AI 入口覆盖）, P19（已确认内容/依赖变更失效）
--
-- 编号说明：原 V112 与 procedure-delegation-notification 的
--   V112__procedure_current_revision_registry.sql 同号冲突，本迁移改编为 V113（附加式，
--   两表相互独立、无依赖，应用顺序无关）。
--
-- 背景（gap）：app.services.evidence_governance.ai_evidence_gate.AIEvidenceGate 读写
--   ``ai_content_governance`` 表（register_generation / confirm / revise / reject /
--   invalidate / check_formal_output_eligibility 的 INSERT/SELECT/UPDATE），但此前无迁移
--   建表 → AI 门禁 register/confirm/formal-output 往返（UAT-10）与检索引用登记链路阻断。
--   V108 已建 ``citation_snapshots``（不可变 CitationSnapshot）与 ``ai_content_log`` 扩展列，
--   本迁移仅补建缺失的 ``ai_content_governance`` 运行时生命周期表（不与既有 ai_content_log 冲突）。
--
-- 约定（migration_allocation.lint_migration_sql 守卫，design §8.1）：
--   * additive-only：不含 DROP TABLE / DROP COLUMN / TRUNCATE。
--   * 可重复检测（幂等）：CREATE TABLE / CREATE INDEX 用 IF NOT EXISTS。
--   * 所有内联 FK 默认 ON DELETE RESTRICT（不级联删除治理对象）。
--   * TIMESTAMPTZ 时间列；actor XOR CHECK 与其它治理表一致。
--
-- 单一真源（契约）：app.services.evidence_governance.frozen_contracts（ActorType/ACTOR_COLUMNS）。
-- 人工确认使用独立 confirmed_by_user_id（REFERENCES users），Service Identity 不得确认（design §2.2）。
-- 说明：本表是**可变生命周期表**（draft→confirmed/revised/rejected→stale），故不加 immutable 触发器；
--   历史版本通过 previous_version_id 自引用链保留，revise 追加新版本、旧版本置 'revised'。

-- ============================================================
-- ai_content_governance — AI 内容治理运行时表（AIEvidenceGate 的单一持久化载体）
-- ============================================================

CREATE TABLE IF NOT EXISTS ai_content_governance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    wp_id UUID,                                            -- 目标底稿（可空；opaque，无 FK，与 ocr_jobs.attachment_id 一致）
    entry_point VARCHAR(80) NOT NULL,                      -- AI_ENTRY_REGISTRY 声明入口（P18）
    prompt_hash VARCHAR(64),                               -- SHA-256(prompt)（R8.1）
    model_name VARCHAR(120) NOT NULL,                      -- 模型标识（R8.1）
    service_status VARCHAR(20) NOT NULL DEFAULT 'available', -- available|degraded|unavailable（R8.4）
    output_text TEXT,                                      -- 生成内容原文
    output_hash VARCHAR(64),                               -- SHA-256(output)（P17 hash 一致性）
    target_cell VARCHAR(200),                              -- 字段级目标标识
    evidence_refs JSONB,                                   -- 上下文 EvidenceRef id 数组（R15）
    citation_snapshots JSONB,                              -- 关联 CitationSnapshot id 数组
    lifecycle_status VARCHAR(20) NOT NULL DEFAULT 'draft', -- draft|confirmed|revised|rejected|stale
    content_version INTEGER NOT NULL DEFAULT 1,
    previous_version_id UUID REFERENCES ai_content_governance(id) ON DELETE RESTRICT,  -- 修订链自引用
    reject_reason TEXT,
    confirmed_by_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,  -- 人工确认专属（Service Identity 不得确认）
    confirmed_at TIMESTAMPTZ,
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_ai_content_gov_service_status CHECK (
        service_status IN ('available','degraded','unavailable')
    ),
    CONSTRAINT chk_ai_content_gov_lifecycle CHECK (
        lifecycle_status IN ('draft','confirmed','revised','rejected','stale')
    ),
    CONSTRAINT chk_ai_content_gov_actor_xor CHECK (
        (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR
        (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_ai_content_gov_scope ON ai_content_governance(project_id, audit_year);
CREATE INDEX IF NOT EXISTS idx_ai_content_gov_lifecycle ON ai_content_governance(project_id, lifecycle_status);
CREATE INDEX IF NOT EXISTS idx_ai_content_gov_wp ON ai_content_governance(wp_id);
CREATE INDEX IF NOT EXISTS idx_ai_content_gov_entry ON ai_content_governance(entry_point);
CREATE INDEX IF NOT EXISTS idx_ai_content_gov_prev ON ai_content_governance(previous_version_id);

COMMENT ON TABLE ai_content_governance IS 'design §4.6 / AIEvidenceGate：AI 全入口内容治理（prompt hash/model/service status/output hash/context EvidenceRefs/CitationSnapshot 链接/生命周期/actor/stale）；可变生命周期表（无 immutable 触发器），修订链靠 previous_version_id 自引用保留历史（R8/P17/P18/P19）';
COMMENT ON COLUMN ai_content_governance.lifecycle_status IS 'draft|confirmed|revised|rejected|stale；仅 human-confirmed+hash 一致+证据非 stale 方可进 FormalOutput（P17）；confirmed 内容依赖变更 → stale（P19）';
COMMENT ON COLUMN ai_content_governance.service_status IS 'available|degraded|unavailable；unavailable 生成的内容不得进正式输出（R8.4）';
