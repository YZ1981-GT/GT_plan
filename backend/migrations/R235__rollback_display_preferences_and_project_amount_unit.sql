-- R233：回滚 V233（显示偏好表 + 项目金额单位列）
-- spec: platform-global-display-settings-closure, 任务 1A, A 组
-- 必须在任何 DROP 前检查数据安全，有数据时 RAISE EXCEPTION 整单回滚。

-- ─── 无损回滚预检 ──────────────────────────────────────────────────────────
DO $$
DECLARE
    non_default_count integer;
    prefs_count integer;
BEGIN
    -- 1. 检查是否存在非默认项目单位
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'projects'
          AND column_name = 'amount_unit'
    ) THEN
        SELECT count(*) INTO non_default_count
        FROM projects
        WHERE amount_unit <> 'yuan';

        IF non_default_count > 0 THEN
            RAISE EXCEPTION
                'R233: % project(s) have non-default amount_unit; '
                'cannot safely rollback V233',
                non_default_count;
        END IF;
    END IF;

    -- 2. 检查是否存在偏好行
    IF to_regclass('public.user_display_preferences') IS NOT NULL THEN
        SELECT count(*) INTO prefs_count
        FROM user_display_preferences;

        IF prefs_count > 0 THEN
            RAISE EXCEPTION
                'R233: % user_display_preferences row(s) exist; '
                'cannot safely rollback V233',
                prefs_count;
        END IF;
    END IF;
END
$$;

-- ─── 预检通过后执行回滚 ────────────────────────────────────────────────────
DROP TABLE IF EXISTS user_display_preferences;

ALTER TABLE projects
    DROP CONSTRAINT IF EXISTS ck_projects_amount_unit;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'projects'
          AND column_name = 'amount_unit'
    ) THEN
        ALTER TABLE projects DROP COLUMN amount_unit;
    END IF;
END
$$;
