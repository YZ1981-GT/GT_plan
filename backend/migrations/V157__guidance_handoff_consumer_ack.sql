-- V157：G-HANDOFF-CONSUMER 的 durable ACK ledger 与 visibility saga（Task 16）
--
-- ═══ 为什么需要它（spec Requirement 13.1–13.7）═══
--
-- C0 wire bundle（V-none / 纯数据）只定义了 CustomGuidanceHandoff / ConsumerAck 的
-- 线格式，没有任何 durable 消费方。custom finalize 采用
--   PENDING visibility → durable ACK ledger → producer commit-visibility
-- 的 saga（design §11）。guidance 作为 consumer 必须把它对 finalized handoff 的
-- 验证结论写成 durable、幂等的 ledger，并维护一个诚实的 visibility 判定。
--
--   1. guidance_consumer_ack        durable ConsumerAck ledger（幂等键见下）
--   2. guidance_handoff_visibility  finalize visibility saga 的 guidance 侧视图
--
-- 🔴 关键约束（由服务端 enforcement）：
--   * candidate handoff 只登记 review_pending，绝不写 ACCEPTED —— 见
--     guidance_handoff_consumer_service.verify_candidate_handoff。
--   * ACK 对 (handoff_id, handoff_digest, consumer, consumer_version) 幂等 ——
--     partial 唯一索引 + 服务层 upsert 双重保证；重复提交命中同一行。
--   * ACK verdict=REJECTED → visibility 保持 0（PENDING/REJECTED），绝不 ACTIVE ——
--     见 resolve_visibility()。
--   * handoff 变化产生新 handoff_digest；旧 ACTIVE 行 stale，不复用旧 digest 的 ACCEPTED。

-- ═══ 1. durable ConsumerAck ledger ═══

CREATE TABLE IF NOT EXISTS guidance_consumer_ack (
    id                     UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    ack_id                 VARCHAR(128)  NOT NULL,
    handoff_id             VARCHAR(128)  NOT NULL,
    handoff_digest         VARCHAR(64)   NOT NULL,
    consumer               VARCHAR(32)   NOT NULL DEFAULT 'guidance'
                                 CHECK (consumer IN ('guidance', 'renderer', 'public_shell', 'entry_namespace')),
    consumer_version       VARCHAR(64)   NOT NULL,
    verdict                VARCHAR(16)   NOT NULL
                                 CHECK (verdict IN ('ACCEPTED', 'REJECTED')),
    validated_digests_json JSONB         NOT NULL DEFAULT '{}'::jsonb,
    reason_codes_json      JSONB         NOT NULL DEFAULT '[]'::jsonb,
    recorded_at            TIMESTAMPTZ   NOT NULL DEFAULT now(),
    created_at             TIMESTAMPTZ   NOT NULL DEFAULT now()
);

COMMENT ON TABLE guidance_consumer_ack IS
    'durable ConsumerAck ledger：guidance 对 finalized handoff 的验证结论；对 (handoff_id, handoff_digest, consumer, consumer_version) 幂等。';
COMMENT ON COLUMN guidance_consumer_ack.handoff_digest IS
    'sha256(canonical handoff)；handoff 内容变化即产生新 digest，旧 ACCEPTED 不复用。';
COMMENT ON COLUMN guidance_consumer_ack.verdict IS
    'ACCEPTED / REJECTED；candidate handoff 绝不进入本表（只登记 review_pending）。';
COMMENT ON COLUMN guidance_consumer_ack.reason_codes_json IS
    '结构化 reason 码；REJECTED 时非空（如 missing-section:formulas / invalid-locator:custom_artifact）。';

-- 幂等键：同一 (handoff, consumer, version) 至多一行 —— 重复提交命中它。
CREATE UNIQUE INDEX IF NOT EXISTS ux_guidance_consumer_ack_idem
    ON guidance_consumer_ack (handoff_id, handoff_digest, consumer, consumer_version);

CREATE INDEX IF NOT EXISTS ix_guidance_consumer_ack_handoff
    ON guidance_consumer_ack (handoff_id, verdict);

-- ═══ 2. finalize visibility saga（guidance 侧视图）═══

CREATE TABLE IF NOT EXISTS guidance_handoff_visibility (
    id                UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    handoff_id        VARCHAR(128)  NOT NULL,
    handoff_digest    VARCHAR(64)   NOT NULL,
    organization_id   VARCHAR(128)  NOT NULL,
    project_id        VARCHAR(128),
    wp_code           VARCHAR(32)   NOT NULL,
    entry_id          VARCHAR(512)  NOT NULL,
    sheet_uid         VARCHAR(128)  NOT NULL,
    state             VARCHAR(16)   NOT NULL DEFAULT 'PENDING'
                            CHECK (state IN ('PENDING', 'ACTIVE', 'REJECTED')),
    decisive_ack_id   VARCHAR(128),
    reason_codes_json JSONB         NOT NULL DEFAULT '[]'::jsonb,
    superseded_by     UUID          REFERENCES guidance_handoff_visibility(id) ON DELETE SET NULL,
    stale             BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT now()
);

COMMENT ON TABLE guidance_handoff_visibility IS
    'finalize visibility saga 的 guidance 侧视图：只有本消费方 ACCEPTED 才允许 ACTIVE；REJECTED/未 ACK 保持 0。不宣称跨系统 ACID。';
COMMENT ON COLUMN guidance_handoff_visibility.state IS
    'PENDING（默认，不可见）/ ACTIVE（可见，需 ACCEPTED）/ REJECTED（不可见）。';
COMMENT ON COLUMN guidance_handoff_visibility.stale IS
    'handoff 变化或 withdraw 后旧行标 stale；stale 行即使 ACTIVE 也不可见。';

-- 同一 (handoff_id, handoff_digest) 至多一行 visibility。
CREATE UNIQUE INDEX IF NOT EXISTS ux_guidance_handoff_visibility_key
    ON guidance_handoff_visibility (handoff_id, handoff_digest);

CREATE INDEX IF NOT EXISTS ix_guidance_handoff_visibility_subject
    ON guidance_handoff_visibility (organization_id, project_id, wp_code, entry_id, sheet_uid)
    WHERE stale = FALSE;
