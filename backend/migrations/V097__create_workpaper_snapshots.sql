-- V097: 创建 workpaper_snapshots 表
-- 底稿版本链通用组件：存储 field-level 数据版本快照，支持时间线展示、diff 对比、回滚
-- 注意：旧版 workpaper_snapshots 表可能已存在（列名不同），用 ALTER 补齐

-- 补充缺失列（旧表用 wp_id，新 ORM 期望 workpaper_id）
DO $$
BEGIN
    -- 如果表不存在，创建完整版
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'workpaper_snapshots') THEN
        CREATE TABLE workpaper_snapshots (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id),
            workpaper_id UUID NOT NULL REFERENCES working_paper(id),
            user_id UUID NOT NULL,
            snapshot_type VARCHAR(50) NOT NULL,
            description TEXT,
            change_summary TEXT,
            data_json JSONB NOT NULL,
            item_count INTEGER NOT NULL DEFAULT 0,
            data_size_bytes INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT now()
        );
    ELSE
        -- 表已存在，补齐新列
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'workpaper_snapshots' AND column_name = 'workpaper_id') THEN
            -- 旧表用 wp_id，添加 workpaper_id 作为别名列
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'workpaper_snapshots' AND column_name = 'wp_id') THEN
                ALTER TABLE workpaper_snapshots RENAME COLUMN wp_id TO workpaper_id;
            ELSE
                ALTER TABLE workpaper_snapshots ADD COLUMN workpaper_id UUID REFERENCES working_paper(id);
            END IF;
        END IF;

        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'workpaper_snapshots' AND column_name = 'user_id') THEN
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'workpaper_snapshots' AND column_name = 'created_by') THEN
                ALTER TABLE workpaper_snapshots RENAME COLUMN created_by TO user_id;
            ELSE
                ALTER TABLE workpaper_snapshots ADD COLUMN user_id UUID;
            END IF;
        END IF;

        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'workpaper_snapshots' AND column_name = 'snapshot_type') THEN
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'workpaper_snapshots' AND column_name = 'trigger_event') THEN
                ALTER TABLE workpaper_snapshots RENAME COLUMN trigger_event TO snapshot_type;
            ELSE
                ALTER TABLE workpaper_snapshots ADD COLUMN snapshot_type VARCHAR(50) NOT NULL DEFAULT 'manual';
            END IF;
        END IF;

        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'workpaper_snapshots' AND column_name = 'description') THEN
            ALTER TABLE workpaper_snapshots ADD COLUMN description TEXT;
        END IF;

        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'workpaper_snapshots' AND column_name = 'change_summary') THEN
            ALTER TABLE workpaper_snapshots ADD COLUMN change_summary TEXT;
        END IF;

        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'workpaper_snapshots' AND column_name = 'data_json') THEN
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'workpaper_snapshots' AND column_name = 'snapshot_data') THEN
                ALTER TABLE workpaper_snapshots RENAME COLUMN snapshot_data TO data_json;
            ELSE
                ALTER TABLE workpaper_snapshots ADD COLUMN data_json JSONB NOT NULL DEFAULT '{}';
            END IF;
        END IF;

        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'workpaper_snapshots' AND column_name = 'item_count') THEN
            ALTER TABLE workpaper_snapshots ADD COLUMN item_count INTEGER NOT NULL DEFAULT 0;
        END IF;

        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'workpaper_snapshots' AND column_name = 'data_size_bytes') THEN
            ALTER TABLE workpaper_snapshots ADD COLUMN data_size_bytes INTEGER NOT NULL DEFAULT 0;
        END IF;

        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'workpaper_snapshots' AND column_name = 'project_id') THEN
            ALTER TABLE workpaper_snapshots ADD COLUMN project_id UUID REFERENCES projects(id);
        END IF;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_wp_snapshots_wp_created
    ON workpaper_snapshots(workpaper_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_wp_snapshots_project
    ON workpaper_snapshots(project_id);
