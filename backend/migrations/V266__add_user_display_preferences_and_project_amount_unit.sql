-- V266: compatibility marker for the display-settings migration
-- Spec: platform-global-display-settings-closure
--
-- The canonical display-settings schema is owned by V250.  V266 was created as
-- a duplicate attempt while V250 was already present, so it must not create a
-- second table shape, constraint, or rollback owner.  Keep this migration as a
-- guarded no-op: a database that reached V266 must already have the V250 schema.
--
-- This guard is intentionally executable rather than an empty migration.  It
-- prevents a missing V250 migration from being silently recorded as complete.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'projects'
          AND column_name = 'amount_unit'
    )
    OR NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = 'public'
          AND t.relname = 'projects'
          AND c.conname = 'ck_projects_amount_unit'
    )
    OR to_regclass('public.user_display_preferences') IS NULL
    OR EXISTS (
        SELECT 1
        FROM (
            VALUES
                ('user_id'),
                ('amount_unit_override'),
                ('font_size'),
                ('show_zero'),
                ('decimals'),
                ('negative_red'),
                ('highlight_threshold'),
                ('density'),
                ('grid_edit_mode'),
                ('fixed_columns'),
                ('revision'),
                ('updated_at')
        ) AS required(column_name)
        WHERE NOT EXISTS (
            SELECT 1
            FROM information_schema.columns actual
            WHERE actual.table_schema = 'public'
              AND actual.table_name = 'user_display_preferences'
              AND actual.column_name = required.column_name
        )
    ) THEN
        RAISE EXCEPTION
            'V266 requires the canonical V250 display-settings schema';
    END IF;
END
$$;
