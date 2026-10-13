-- R185: V185 可重入校验（幂等）
-- 确保 client_instance 列存在

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'editing_locks' AND column_name = 'client_instance'
    ) THEN
        ALTER TABLE editing_locks ADD COLUMN client_instance VARCHAR(64);
    END IF;
END $$;
