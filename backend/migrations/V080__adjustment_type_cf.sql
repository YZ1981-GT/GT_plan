-- Add 'cf' value to adjustment_type enum for CF 调整分录
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumlabel = 'cf'
        AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'adjustment_type')
    ) THEN
        ALTER TYPE adjustment_type ADD VALUE 'cf';
    END IF;
END$$;
