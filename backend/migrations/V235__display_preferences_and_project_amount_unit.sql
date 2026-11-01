-- V233：显示偏好表 + 项目默认金额单位列
-- spec: platform-global-display-settings-closure, 任务 1A, A 组
-- 不读取或更新任何四表金额。

-- ─── 1. projects.amount_unit ────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'projects'
          AND column_name = 'amount_unit'
    ) THEN
        ALTER TABLE projects
            ADD COLUMN amount_unit VARCHAR(8) NOT NULL DEFAULT 'yuan';
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_projects_amount_unit'
    ) THEN
        ALTER TABLE projects
            ADD CONSTRAINT ck_projects_amount_unit
            CHECK (amount_unit IN ('yuan', 'qian', 'wan'));
    END IF;
END
$$;

-- ─── 2. user_display_preferences ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_display_preferences (
    user_id             UUID          PRIMARY KEY
                                      REFERENCES users(id) ON DELETE CASCADE,
    amount_unit_override VARCHAR(8)   DEFAULT NULL,
    font_size           VARCHAR(4)    NOT NULL DEFAULT 'sm',
    show_zero           BOOLEAN       NOT NULL DEFAULT false,
    decimals            INTEGER       NOT NULL DEFAULT 2,
    negative_red        BOOLEAN       NOT NULL DEFAULT true,
    highlight_threshold NUMERIC(5,4)  NOT NULL DEFAULT 0.2,
    density             VARCHAR(16)   NOT NULL DEFAULT 'default',
    grid_edit_mode      VARCHAR(16)   NOT NULL DEFAULT 'excel',
    fixed_columns       JSONB         NOT NULL DEFAULT '{}'::jsonb,
    revision            INTEGER       NOT NULL DEFAULT 0,
    updated_at          TIMESTAMPTZ   DEFAULT NULL,

    CONSTRAINT ck_udp_amount_unit_override
        CHECK (amount_unit_override IS NULL
               OR amount_unit_override IN ('yuan', 'qian', 'wan')),
    CONSTRAINT ck_udp_font_size
        CHECK (font_size IN ('xs', 'sm', 'md', 'lg')),
    CONSTRAINT ck_udp_decimals
        CHECK (decimals >= 0 AND decimals <= 6),
    CONSTRAINT ck_udp_highlight_threshold
        CHECK (highlight_threshold >= 0 AND highlight_threshold <= 1),
    CONSTRAINT ck_udp_density
        CHECK (density IN ('compact', 'default', 'comfortable')),
    CONSTRAINT ck_udp_grid_edit_mode
        CHECK (grid_edit_mode IN ('excel', 'click', 'classic')),
    CONSTRAINT ck_udp_revision_nonneg
        CHECK (revision >= 0),
    CONSTRAINT ck_udp_fixed_columns_is_object
        CHECK (jsonb_typeof(fixed_columns) = 'object')
);
