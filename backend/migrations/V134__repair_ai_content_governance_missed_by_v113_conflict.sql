-- V134: Repair — ai_content_governance 表因 V113 版本号冲突被静默跳过而从未建表
--
-- 背景（根因）：schema_version 中 version=113 早在 2026-07-16 被
--   ``V113__wp_visibility_delegation_history_audit_epoch.sql`` 占用（可见性委派迁移当时
--   以 V113 落库并建表）。该可见性迁移后于 2026-07-27 重编号为
--   ``V115__wp_visibility_delegation_history_audit_epoch.sql`` 并作为 version=115 重放，
--   但 schema_version 的 version=113 行**仍指向旧的可见性文件名**。
--   与此同时 canonical 的 ``V113__evidence_governance_ai_content_governance.sql``（建
--   ``ai_content_governance`` 表）虽在磁盘，但 MigrationRunner 的 ``version not in applied``
--   去重把 113 视为已应用 → **该 V113 从未执行 → ai_content_governance 表从未建立**
--   → 启动期 SchemaDriftDetector 报 orm_extra（critical / health=degraded）。
--   同时磁盘 V113(evidence) 的 checksum 与 schema_version(113=visibility) 记录不一致，
--   构成潜在 checksum 漂移。
--
-- 修复（对齐 V114 修复 V112 冲突的既有范式）：
--   1) 幂等补建 ai_content_governance 表 + 索引 + 注释（与 V113/ORM 严格一致，零漂移）。
--   2) 校正 schema_version 中 version=113 的簿记行：filename/checksum 从可见性文件更正为
--      ``V113__evidence_governance_ai_content_governance.sql`` 的真值——使 113 正确归属证据
--      治理迁移（可见性已由 version=115 独立记录），消除 checksum 漂移。
--
-- 约定（migration_allocation.lint_migration_sql）：additive-only（无 DROP/TRUNCATE）；
--   CREATE TABLE/INDEX 幂等 IF NOT EXISTS；FK 默认 ON DELETE RESTRICT；TIMESTAMPTZ；
--   actor XOR CHECK 与其它治理表一致。本表是可变生命周期表（无 immutable 触发器）。

-- ============================================================
-- 1) 幂等补建 ai_content_governance（与 V113 DDL 逐字一致）
-- ============================================================

CREATE TABLE IF NOT EXISTS ai_content_governance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    wp_id UUID,
    entry_point VARCHAR(80) NOT NULL,
    prompt_hash VARCHAR(64),
    model_name VARCHAR(120) NOT NULL,
    service_status VARCHAR(20) NOT NULL DEFAULT 'available',
    output_text TEXT,
    output_hash VARCHAR(64),
    target_cell VARCHAR(200),
    evidence_refs JSONB,
    citation_snapshots JSONB,
    lifecycle_status VARCHAR(20) NOT NULL DEFAULT 'draft',
    content_version INTEGER NOT NULL DEFAULT 1,
    previous_version_id UUID REFERENCES ai_content_governance(id) ON DELETE RESTRICT,
    reject_reason TEXT,
    confirmed_by_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
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

-- ============================================================
-- 2) 校正 schema_version 的 version=113 簿记行（可见性→证据治理）
--    仅当该行仍误指向可见性文件名时才更正（幂等：重复执行不受影响）。
-- ============================================================

UPDATE schema_version
SET filename = 'V113__evidence_governance_ai_content_governance.sql',
    checksum = '0325e002d4e059f6f6c03366e5d288c4b75be17a7b4d1ab4dbc1f17d578642d9'
WHERE version = '113'
  AND filename = 'V113__wp_visibility_delegation_history_audit_epoch.sql';
