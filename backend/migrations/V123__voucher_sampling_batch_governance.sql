-- V123: 抽样批次治理（voucher-sampling-hardening Task 7）
-- workpaper_extraction_log 增加批次幂等 / 状态机 / 乐观锁 / 完整性约束。
-- 全部幂等守护（information_schema / pg_constraint / pg_indexes）+ 向后兼容历史行
-- （新列 nullable 或带默认；CHECK NOT VALID / FK NOT VALID 仅约束未来写入，不校验历史）。
--
-- Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6

-- ① 新增列 -------------------------------------------------------------------
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'workpaper_extraction_log' AND column_name = 'batch_id'
  ) THEN
    ALTER TABLE workpaper_extraction_log ADD COLUMN batch_id UUID;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'workpaper_extraction_log' AND column_name = 'idempotency_key'
  ) THEN
    ALTER TABLE workpaper_extraction_log ADD COLUMN idempotency_key TEXT;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'workpaper_extraction_log' AND column_name = 'row_version'
  ) THEN
    ALTER TABLE workpaper_extraction_log ADD COLUMN row_version INTEGER NOT NULL DEFAULT 1;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'workpaper_extraction_log' AND column_name = 'status'
  ) THEN
    ALTER TABLE workpaper_extraction_log ADD COLUMN status TEXT NOT NULL DEFAULT 'filled';
  END IF;
END $$;

-- 历史行状态回填：已撤销(is_undone) → 'undone'，其余 → 'filled'
UPDATE workpaper_extraction_log
   SET status = CASE WHEN is_undone THEN 'undone' ELSE 'filled' END
 WHERE status IS NULL OR status = 'filled';

-- ② CHECK 约束（NOT VALID：仅约束未来写入，不校验历史行，避免遗留脏数据导致迁移失败）--
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_extraction_log_fill_mode'
  ) THEN
    ALTER TABLE workpaper_extraction_log
      ADD CONSTRAINT chk_extraction_log_fill_mode
      CHECK (fill_mode IN ('append', 'replace', 'merge')) NOT VALID;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_extraction_log_type'
  ) THEN
    ALTER TABLE workpaper_extraction_log
      ADD CONSTRAINT chk_extraction_log_type
      CHECK (extraction_type IN ('cutoff', 'voucher_sampling')) NOT VALID;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_extraction_log_status'
  ) THEN
    ALTER TABLE workpaper_extraction_log
      ADD CONSTRAINT chk_extraction_log_status
      CHECK (status IN ('draft', 'confirmed', 'filled', 'undone')) NOT VALID;
  END IF;
END $$;

-- ③ user_id 外键（NOT VALID：约束未来写入，不校验历史孤儿）-----------------------
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_extraction_log_user'
  ) THEN
    ALTER TABLE workpaper_extraction_log
      ADD CONSTRAINT fk_extraction_log_user
      FOREIGN KEY (user_id) REFERENCES users (id) NOT VALID;
  END IF;
END $$;

-- ④ 幂等键唯一（部分索引：仅 idempotency_key 非空时约束）-----------------------
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes WHERE indexname = 'uq_extraction_log_wp_idempotency'
  ) THEN
    CREATE UNIQUE INDEX uq_extraction_log_wp_idempotency
      ON workpaper_extraction_log (workpaper_id, idempotency_key)
      WHERE idempotency_key IS NOT NULL;
  END IF;
END $$;

-- ⑤ 撤销唯一（部分索引：同一 batch_id 至多一条 undone）--------------------------
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes WHERE indexname = 'uq_extraction_log_batch_undone'
  ) THEN
    CREATE UNIQUE INDEX uq_extraction_log_batch_undone
      ON workpaper_extraction_log (batch_id)
      WHERE batch_id IS NOT NULL AND status = 'undone';
  END IF;
END $$;

-- ⑥ batch_id 查询索引 --------------------------------------------------------
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes WHERE indexname = 'idx_extraction_log_batch'
  ) THEN
    CREATE INDEX idx_extraction_log_batch
      ON workpaper_extraction_log (batch_id)
      WHERE batch_id IS NOT NULL;
  END IF;
END $$;

COMMENT ON COLUMN workpaper_extraction_log.batch_id IS '抽样批次ID（V123）';
COMMENT ON COLUMN workpaper_extraction_log.idempotency_key IS '幂等键，(workpaper_id,idempotency_key)唯一（V123）';
COMMENT ON COLUMN workpaper_extraction_log.row_version IS '乐观锁版本（V123）';
COMMENT ON COLUMN workpaper_extraction_log.status IS '批次状态 draft/confirmed/filled/undone（V123）';
