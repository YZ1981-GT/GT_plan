-- ═══════════════════════════════════════════════════════════════════════════
-- V153 candidate contract/bundle attach 的 append-only 审计轨
--
-- spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 4 Task 76
-- Requirements: 2.1, 2.3, 2.4, 3.4, 3.6, 6.18, 12.1
-- Properties: P4 / P5 / P67
--
-- ═══ 为什么必须新建一张表 ═══
--
-- V151 给 `working_paper_representation_upgrade_candidate` 建了状态机（staged /
-- awaiting_contract / ready / finalized / rejected / orphaned）但**没有**审计轨：
-- candidate 的 `state` 是就地 UPDATE 的一列，谁在什么时候把哪一份 approved contract /
-- bundle 绑上去、绑之前是什么状态，事后一个字都查不到。
--
-- Task 76 交付「candidate 受控 attach 入口」，其正文要求 **state 迁移写 append-only
-- 审计**。四条既有 timeline（operation / application / close-intent / recovery case）
-- 各自只覆盖自己的聚合根，没有一条能承载 candidate 的迁移事实，故新建第五条。
--
-- ═══ 只加不动 ═══
--
-- 本迁移**不修改** V151 的任何表/触发器/约束，只新增一张表 + 复用 V151 已建的
-- `wpsync_forbid_timeline_mutation()` 作 append-only 触发器函数（不复制第二份实现：
-- 复制一份的后果是任一侧被短路都不改变行为 ⇒ 变异检验判 GREEN）。
-- 全部语句幂等（`IF NOT EXISTS` / `CREATE OR REPLACE`），MigrationRunner 重跑安全。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_representation_candidate_event (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL
        REFERENCES working_paper_representation_upgrade_candidate(id) ON DELETE RESTRICT,
    sequence_no INTEGER NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    from_state VARCHAR(30) NOT NULL,
    to_state VARCHAR(30) NOT NULL,
    contract_definition_id UUID
        REFERENCES working_paper_sync_definition_artifact(id) ON DELETE RESTRICT,
    definition_bundle_id UUID
        REFERENCES working_paper_sync_definition_bundle(id) ON DELETE RESTRICT,
    definition_bundle_sha256 CHAR(64),
    actor_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    correlation_id VARCHAR(200) NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_wprce_sequence UNIQUE (candidate_id, sequence_no),
    CONSTRAINT ck_wprce_sequence_positive CHECK (sequence_no >= 1),
    CONSTRAINT ck_wprce_event_type CHECK (event_type IN (
        'contract_bundle_attached', 'attach_refused')),
    CONSTRAINT ck_wprce_from_state CHECK (from_state IN (
        'staged', 'awaiting_contract', 'ready', 'finalized', 'rejected', 'orphaned')),
    CONSTRAINT ck_wprce_to_state CHECK (to_state IN (
        'staged', 'awaiting_contract', 'ready', 'finalized', 'rejected', 'orphaned')),
    -- attach 成功的事件必须同时带 contract + bundle + bundle digest（禁半缺：
    -- 只留 FK 或只留可漂移字符串都无法复现「绑的是哪一份身份」）
    CONSTRAINT ck_wprce_attached_identity CHECK (
        event_type <> 'contract_bundle_attached'
        OR (contract_definition_id IS NOT NULL
            AND definition_bundle_id IS NOT NULL
            AND definition_bundle_sha256 IS NOT NULL)),
    CONSTRAINT ck_wprce_bundle_digest CHECK (
        definition_bundle_sha256 IS NULL OR wpsync_is_digest(definition_bundle_sha256)),
    -- attach 只允许 `awaiting_contract → ready`（其余迁移属别的服务；
    -- 审计轨自己也不得记录本入口无权做的迁移）
    CONSTRAINT ck_wprce_attach_edge CHECK (
        event_type <> 'contract_bundle_attached'
        OR (from_state = 'awaiting_contract' AND to_state = 'ready'))
);

CREATE INDEX IF NOT EXISTS idx_wprce_candidate
    ON working_paper_representation_candidate_event (candidate_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_wprce_bundle
    ON working_paper_representation_candidate_event (definition_bundle_id);

COMMENT ON TABLE working_paper_representation_candidate_event IS
    'V153 candidate contract/bundle attach 的 append-only 审计轨（Task 76）：记录 awaiting_contract → ready 的受控迁移与被绑定的 approved contract/bundle identity；UPDATE/DELETE 由 wpsync_forbid_timeline_mutation() 拒绝（Requirement 6.18 / Property 67）';

-- append-only：复用 V151 的通用 timeline 守卫函数，不复制第二份实现
CREATE OR REPLACE TRIGGER trg_wprce_append_only
    BEFORE UPDATE OR DELETE ON working_paper_representation_candidate_event
    FOR EACH ROW EXECUTE FUNCTION wpsync_forbid_timeline_mutation();
