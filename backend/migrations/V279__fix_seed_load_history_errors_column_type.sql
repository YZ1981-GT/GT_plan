-- V276: 修正 V275 建错的 seed_load_history.errors 列型
--
-- 🔴 V275 的真实缺陷（2026-11-25 接线 ORM 时发现）：
-- V275 按「SELECT 反推列形状」把 `errors` 建成 INTEGER NOT NULL DEFAULT 0，
-- 而生产写入方 `template_library_mgmt._record_history` 的实际 SQL 是：
--
--   INSERT INTO seed_load_history (..., errors, status)
--   VALUES (..., CAST(:errors AS JSONB), :status)
--
-- 其中 `errors` 是**错误明细数组**（json.dumps(errors or [])），不是条数。
-- 类型不匹配 ⇒ 一旦种子加载真的走 _record_history 就
-- `column "errors" is of type integer but expression is of type jsonb`，
-- 而该函数被 try/except 吞掉 ⇒ 静默丢审计轨迹（正是本次技术债要消灭的形态）。
--
-- 修法：errors → JSONB NOT NULL DEFAULT '[]'::jsonb；存量 integer 值按
-- 「非 0 转成 ['legacy error count: N']，0 转空数组」迁移，不丢信息。
-- 幂等：先判当前列型（已经是 jsonb 则跳过）。

DO $$
DECLARE
    current_type TEXT;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'seed_load_history'
           AND column_name = 'errors'
    ) THEN
        -- 表或列不存在（V275 未应用）⇒ 由 V275 直接按正确类型建，这里什么都不做
        RETURN;
    END IF;

    SELECT data_type INTO current_type
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name = 'seed_load_history'
       AND column_name = 'errors';

    IF current_type = 'jsonb' THEN
        RETURN;  -- 已是目标形态，幂等
    END IF;

    -- 1. 先加临时 jsonb 列，按存量整数转换（非 0 → 错误明细数组，0 → 空数组）
    ALTER TABLE seed_load_history
        ADD COLUMN IF NOT EXISTS errors_jsonb JSONB NOT NULL DEFAULT '[]'::jsonb;

    UPDATE seed_load_history
       SET errors_jsonb = CASE
               WHEN errors IS NULL OR errors = 0 THEN '[]'::jsonb
               ELSE jsonb_build_array('legacy error count: ' || errors::text)
           END;

    -- 2. 删旧列、改名新列（保留原列位置语义由 ordinal 决定，无需强求）
    ALTER TABLE seed_load_history DROP COLUMN errors;
    ALTER TABLE seed_load_history RENAME COLUMN errors_jsonb TO errors;

    RAISE NOTICE 'V276: seed_load_history.errors integer -> jsonb 完成';
END $$;

-- 顺手：V275 建的索引若缺失则补（幂等）
CREATE INDEX IF NOT EXISTS idx_seed_load_history_name
    ON seed_load_history (seed_name, loaded_at DESC);
