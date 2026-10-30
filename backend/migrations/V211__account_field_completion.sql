-- V211: users.full_name / parent_partner_id / dept_id（权限中心对齐）
-- 对应 ORM：app/models/core.py::User（V149 移植，仅 users 三列；projects 不在本次范围）
--
-- 列宽与 ORM 一致（full_name String(100)），避免 schema 漂移检测报列型不匹配。

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='users' AND column_name='full_name'
    ) THEN
        ALTER TABLE users ADD COLUMN full_name VARCHAR(100);
        RAISE NOTICE 'Added users.full_name column';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='users' AND column_name='parent_partner_id'
    ) THEN
        ALTER TABLE users ADD COLUMN parent_partner_id UUID;
        RAISE NOTICE 'Added users.parent_partner_id column';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='users' AND column_name='dept_id'
    ) THEN
        ALTER TABLE users ADD COLUMN dept_id UUID;
        RAISE NOTICE 'Added users.dept_id column';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name='fk_users_parent_partner' AND table_name='users'
    ) THEN
        ALTER TABLE users
        ADD CONSTRAINT fk_users_parent_partner
        FOREIGN KEY (parent_partner_id) REFERENCES users(id) ON DELETE SET NULL;
        RAISE NOTICE 'Added fk_users_parent_partner constraint';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE indexname='idx_users_parent_partner'
    ) THEN
        CREATE INDEX idx_users_parent_partner ON users(parent_partner_id);
        RAISE NOTICE 'Created idx_users_parent_partner index';
    END IF;
END $$;
