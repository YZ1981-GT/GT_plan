-- V122: ACNR 失效传播与 Overlay 治理加固
-- Spec: acnr-invalidation-overlay-hardening (Wave 1)
-- Requirements: R5 (唯一约束), R7 (治理字段), R8 (revision/CAS), R11 (durable epoch + outbox)
-- 全程 additive + 幂等（information_schema / IF NOT EXISTS 守护）；不删 legacy 列。

-- ─── R7 / R8: acnr_project_overlay 增治理字段 + revision（additive nullable / default）──
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name = 'acnr_project_overlay' AND column_name = 'reason') THEN
    ALTER TABLE acnr_project_overlay ADD COLUMN reason TEXT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name = 'acnr_project_overlay' AND column_name = 'owner') THEN
    ALTER TABLE acnr_project_overlay ADD COLUMN owner VARCHAR(100);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name = 'acnr_project_overlay' AND column_name = 'expires_at') THEN
    ALTER TABLE acnr_project_overlay ADD COLUMN expires_at DATE;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name = 'acnr_project_overlay' AND column_name = 'revision') THEN
    ALTER TABLE acnr_project_overlay ADD COLUMN revision INTEGER NOT NULL DEFAULT 1;
  END IF;
END $$;

-- ─── R5.2: 建 Overlay_Unique_Key 前先去重（保留最新 updated_at 一行）────────────
-- 防御性：其他环境若已有违反唯一键的重复行，删除除最新外的重复行。
DELETE FROM acnr_project_overlay a
USING acnr_project_overlay b
WHERE a.project_id = b.project_id
  AND a.parent_wp_code = b.parent_wp_code
  AND a.sheet_code = b.sheet_code
  AND a.overlay_type = b.overlay_type
  AND (
        a.updated_at < b.updated_at
        OR (a.updated_at = b.updated_at AND a.id < b.id)
      );

-- ─── R5.1: 组合唯一约束（幂等：pg_constraint 检测）────────────────────────────
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'uq_overlay_identity'
  ) THEN
    ALTER TABLE acnr_project_overlay
      ADD CONSTRAINT uq_overlay_identity
      UNIQUE (project_id, parent_wp_code, sheet_code, overlay_type);
  END IF;
END $$;

-- ─── R11.1: Durable_Epoch 持久化（per-project 单调递增计数器，DB-backed）────────
CREATE TABLE IF NOT EXISTS acnr_invalidation_epoch (
    project_id UUID PRIMARY KEY,
    epoch      BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─── R11.1: Invalidation_Outbox（业务变更同事务写入 + dispatcher 至少一次投递）──
CREATE TABLE IF NOT EXISTS acnr_invalidation_outbox (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id    UUID NOT NULL,
    wp_id         UUID,
    domain        VARCHAR(20),          -- wp/tb/report/note/aux/overlay
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    dispatched_at TIMESTAMPTZ,          -- NULL = 未投递
    attempts      INTEGER NOT NULL DEFAULT 0
);

-- undispatched 部分索引（dispatcher FOR UPDATE SKIP LOCKED 拉批用）
CREATE INDEX IF NOT EXISTS idx_inval_outbox_undispatched
  ON acnr_invalidation_outbox (created_at) WHERE dispatched_at IS NULL;

COMMENT ON TABLE acnr_invalidation_epoch IS 'ACNR Durable_Epoch — per-project 失效计数器（Redis 不可用仍单调递增）';
COMMENT ON TABLE acnr_invalidation_outbox IS 'ACNR Invalidation_Outbox — 业务变更同事务写入，dispatcher 至少一次投递（递增 epoch + fan-out）';
COMMENT ON COLUMN acnr_project_overlay.reason IS 'overlay 治理：变更原因';
COMMENT ON COLUMN acnr_project_overlay.owner IS 'overlay 治理：责任人';
COMMENT ON COLUMN acnr_project_overlay.expires_at IS 'overlay 治理：过期日期（持久化，重启后 is_expired 生效）';
COMMENT ON COLUMN acnr_project_overlay.revision IS 'overlay 乐观并发版本号（CAS）';
