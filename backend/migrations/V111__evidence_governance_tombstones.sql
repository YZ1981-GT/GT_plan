-- V111: Evidence Governance — EvidenceTombstone（不可变墓碑）
-- Spec: attachment-ocr-ai-evidence-governance-hardening / R13（Legal Hold / 保留 / 清理）
-- Design: §4.6 清理(purge)后保留的永久审计痕迹；§4.5/§4.6 immutable 触发器
-- Properties: P26/P27（hold/retention）—— purge 后墓碑不可变，仅保留脱敏标识元数据
--
-- 背景：ORM `app.models.evidence_governance_models.EvidenceTombstone` 定义了
--   `evidence_tombstones` 表，但 V108 遗漏建表 → 启动 schema drift（orm_extra/critical）。
--   本迁移补齐建表，消除漂移。
--
-- 约定（与 V108 一致，migration lint 守卫）：
--   * additive-only：无 DROP / TRUNCATE。
--   * 幂等：CREATE TABLE / INDEX 用 IF NOT EXISTS；触发器 CREATE OR REPLACE TRIGGER；
--     函数 CREATE OR REPLACE FUNCTION。
--   * 内联 FK 默认 ON DELETE RESTRICT（不级联删除治理对象）。
-- 前置：V108（evgov_forbid_update() 函数 + 各 immutable 触发器）。

-- ============================================================
-- 1. EvidenceTombstone —— 对象被清理(purge)后保留的永久审计痕迹（不记录原始内容/凭据）
-- ============================================================

CREATE TABLE IF NOT EXISTS evidence_tombstones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_object_type VARCHAR(80) NOT NULL,
    original_object_id VARCHAR(200) NOT NULL,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    purge_reason VARCHAR(100) NOT NULL,
    purged_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    purged_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_redacted JSONB,                               -- 脱敏元数据（无原始内容/凭据/绝对路径）
    content_hash VARCHAR(64),
    retention_policy_version VARCHAR(80),
    legal_hold_release_id UUID,                            -- 关联 hold 解除（异构来源，不加 FK）
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_tombstone_purge_reason CHECK (
        purge_reason IN ('retention_expired','manual_purge','compliance_erasure')
    )
);

CREATE INDEX IF NOT EXISTS idx_tombstone_scope ON evidence_tombstones(project_id, audit_year);
CREATE INDEX IF NOT EXISTS idx_tombstone_object ON evidence_tombstones(original_object_type, original_object_id);
CREATE INDEX IF NOT EXISTS idx_tombstone_purged_at ON evidence_tombstones(purged_at);

COMMENT ON TABLE evidence_tombstones IS 'design §4.6 不可变墓碑：对象清理后保留脱敏标识元数据 + 清理原因/操作人；immutable 触发器阻止 UPDATE/DELETE（P26/P27）';
COMMENT ON COLUMN evidence_tombstones.purge_reason IS 'retention_expired|manual_purge|compliance_erasure（chk_tombstone_purge_reason）';

-- ============================================================
-- 2. Immutable 触发器 —— 墓碑一旦创建即不可变（禁止 UPDATE 与 DELETE，P26/P27）
--    UPDATE 复用 V108 的 evgov_forbid_update()；DELETE 新增 evgov_forbid_delete()。
-- ============================================================

CREATE OR REPLACE FUNCTION evgov_forbid_delete() RETURNS trigger AS $fn$
BEGIN
    RAISE EXCEPTION '% 为不可变表，禁止 DELETE (id=%)', TG_TABLE_NAME, OLD.id
        USING ERRCODE = 'restrict_violation';
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_tombstone_immutable_update
    BEFORE UPDATE ON evidence_tombstones
    FOR EACH ROW EXECUTE FUNCTION evgov_forbid_update();

CREATE OR REPLACE TRIGGER trg_tombstone_immutable_delete
    BEFORE DELETE ON evidence_tombstones
    FOR EACH ROW EXECUTE FUNCTION evgov_forbid_delete();
